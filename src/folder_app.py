"""資料夾批次轉檔工具（Windows 10/11）。

把清單中每個資料夾「直接層」的圖片轉成 JPG，成功後原圖移到資源回收桶。
與主程式 app.py 不同：清單以「資料夾」為單位、且會刪除原檔（交易式、逐夾處理）。

啟動：python folder_app.py
需要：Pillow、send2trash、tkinterdnd2（見 requirements.txt）
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from tkinter import (
    BOTH,
    END,
    HORIZONTAL,
    Listbox,
    StringVar,
    Tk,
    filedialog,
    messagebox,
)
from tkinter import ttk

from folder_core import list_source_images, process_folders
from taskbar import TaskbarProgress

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD

    _DND_OK = True
except ImportError:  # pragma: no cover
    _DND_OK = False

_MUTED = "#777777"
_WARN = "#b00020"


def _base_dir() -> Path:
    # 暫存區與程式放一起：打包後用 exe 所在資料夾，否則用原始碼資料夾。
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def _config_path() -> Path:
    # 用獨立設定檔，避免與主程式 app.py 的 config.json 互相覆蓋。
    return _base_dir() / "folder_config.json"


class FolderApp:
    def __init__(self, root: Tk):
        self.root = root
        root.title("資料夾批次轉檔")
        root.minsize(500, 560)
        self._center_window(560, 620)

        self.folders: list[Path] = []
        settings = self._load_settings()
        self.quality = self._clamp_quality(settings.get("quality", 90))
        self._build_ui()
        self.taskbar = TaskbarProgress(root)  # 工作列圖示進度（Windows；其他平台 no-op）

        # 關閉視窗時把當下設定存下來
        root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------- UI ----------
    def _center_window(self, w, h):
        self.root.update_idletasks()
        x = max(0, (self.root.winfo_screenwidth() - w) // 2)
        y = max(0, (self.root.winfo_screenheight() - h) // 2)
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _build_ui(self):
        style = ttk.Style()
        style.configure("TButton", padding=5)
        style.configure("Muted.TLabel", foreground=_MUTED)
        style.configure("Warn.TLabel", foreground=_WARN)
        style.configure("Ok.TLabel", foreground="#1a7f37", font=("", 10, "bold"))
        style.configure("Err.TLabel", foreground="#b00020", font=("", 10, "bold"))
        style.configure("TLabelframe.Label", font=("", 10, "bold"))
        style.configure("Go.TButton", padding=8, font=("", 10, "bold"))

        outer = ttk.Frame(self.root, padding=14)
        outer.pack(fill=BOTH, expand=True)

        # 破壞性行為警語
        ttk.Label(
            outer,
            text="⚠ 每個資料夾的圖片會就地轉成 JPG，成功後原圖將移到資源回收桶。",
            style="Warn.TLabel", wraplength=520, justify="left",
        ).pack(anchor="w", pady=(0, 10))

        box = ttk.LabelFrame(outer, text=" 資料夾清單 ", padding=12)
        box.pack(fill=BOTH, expand=True)
        hint = "把資料夾拖進下面的清單，或按「加入資料夾」" if _DND_OK \
            else "（未安裝 tkinterdnd2，請按「加入資料夾」）"
        ttk.Label(box, text=hint, style="Muted.TLabel").pack(anchor="w", pady=(0, 8))

        list_frame = ttk.Frame(box)
        list_frame.pack(fill=BOTH, expand=True)
        self.listbox = Listbox(
            list_frame, selectmode="extended", height=8,
            activestyle="none", highlightthickness=1, relief="flat",
        )
        self.listbox.pack(side="left", fill=BOTH, expand=True)
        scroll = ttk.Scrollbar(list_frame, command=self.listbox.yview)
        scroll.pack(side="right", fill="y")
        self.listbox.config(yscrollcommand=scroll.set)
        if _DND_OK:
            self.listbox.drop_target_register(DND_FILES)
            self.listbox.dnd_bind("<<Drop>>", self._on_drop)

        btn_row = ttk.Frame(box)
        btn_row.pack(fill="x", pady=(10, 0))
        ttk.Button(btn_row, text="加入資料夾", command=self._add_folder).pack(side="left")
        ttk.Button(btn_row, text="移除選取", command=self._remove_selected).pack(side="left", padx=6)
        ttk.Button(btn_row, text="移除全部", command=self._clear).pack(side="left")

        q_box = ttk.LabelFrame(outer, text=" JPG 品質 ", padding=12)
        q_box.pack(fill="x", pady=(14, 0))
        self.q_scale = ttk.Scale(
            q_box, from_=1, to=100, orient=HORIZONTAL, command=self._on_quality
        )
        self.q_scale.pack(side="left", fill="x", expand=True)
        self.q_label = ttk.Label(q_box, text=str(self.quality), width=5, anchor="e")
        self.q_label.pack(side="right", padx=(8, 0))
        self.q_scale.set(self.quality)

        run_box = ttk.Frame(outer)
        run_box.pack(fill="x", pady=(14, 0))
        self.progress = ttk.Progressbar(run_box, mode="determinate")
        self.progress.pack(fill="x")
        self.status = StringVar(value="準備就緒")
        self.status_label = ttk.Label(run_box, textvariable=self.status, style="Muted.TLabel")
        self.status_label.pack(anchor="w", pady=(6, 10))
        self.run_btn = ttk.Button(
            run_box, text="開始處理", command=self._start, style="Go.TButton"
        )
        self.run_btn.pack(fill="x")

    def _set_status(self, msg, kind="info"):
        """更新狀態列文字與顏色。kind: info(灰) / ok(綠) / error(紅)。"""
        self.status.set(msg)
        style = {"ok": "Ok.TLabel", "error": "Err.TLabel"}.get(kind, "Muted.TLabel")
        self.status_label.config(style=style)

    def _bring_to_front(self):
        """把視窗帶到所有應用程式最上層（處理完成時提醒使用者）。"""
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.attributes("-topmost", True)
            self.root.after(600, lambda: self.root.attributes("-topmost", False))
            self.root.focus_force()
        except Exception:  # noqa: BLE001
            pass

    # ---------- 清單操作 ----------
    def _on_drop(self, event):
        self._add_paths(self.root.tk.splitlist(event.data))

    def _add_folder(self):
        d = filedialog.askdirectory(title="選擇資料夾")
        if d:
            self._add_paths([d])

    def _add_paths(self, paths):
        self.progress.config(value=0)  # 加入新資料夾＝開新一批，重置上一批的完成進度
        added = skipped = 0
        for p in paths:
            path = Path(p)
            if not path.is_dir():
                skipped += 1  # 只吃資料夾
                continue
            if path not in self.folders:
                self.folders.append(path)
                self.listbox.insert(END, str(path))
                added += 1
        if added or skipped:
            msg = f"已加入 {added} 個資料夾，共 {len(self.folders)} 個"
            if skipped:
                msg += f"（略過 {skipped} 個非資料夾）"
            self._set_status(msg)

    def _remove_selected(self):
        for idx in reversed(self.listbox.curselection()):
            self.listbox.delete(idx)
            del self.folders[idx]
        self.progress.config(value=0)
        self._set_status(f"清單剩 {len(self.folders)} 個資料夾")

    def _clear(self):
        self.listbox.delete(0, END)
        self.folders.clear()
        self.progress.config(value=0)
        self._set_status("清單已清空")

    def _on_quality(self, value):
        self.quality = int(float(value))
        self.q_label.config(text=str(self.quality))

    def _refresh_list(self):
        self.listbox.delete(0, END)
        for f in self.folders:
            self.listbox.insert(END, str(f))

    # ---------- 處理 ----------
    def _start(self):
        if not self.folders:
            messagebox.showwarning("沒有資料夾", "請先加入至少一個資料夾")
            return

        # 預掃有幾張圖要處理，讓確認訊息更具體
        total_imgs = 0
        for f in self.folders:
            try:
                total_imgs += len(list_source_images(f))
            except OSError:
                pass

        ok = messagebox.askyesno(
            "確認處理（會刪除原檔）",
            f"即將處理 {len(self.folders)} 個資料夾、約 {total_imgs} 張圖片：\n\n"
            "• 每個資料夾內的圖片會轉成 JPG（放回原資料夾）\n"
            "• 轉檔成功後，原始圖檔會移到「資源回收桶」\n"
            "• 只要有一張失敗，該資料夾的原檔全部不動\n\n"
            "確定要繼續嗎？",
            icon="warning", default="no",
        )
        if not ok:
            self._set_status("已取消")
            return

        self.run_btn.config(state="disabled")
        self.progress.config(value=0, maximum=max(total_imgs, 1))
        self._set_status("處理中…")
        tmp_root = _base_dir() / "tmp"
        threading.Thread(
            target=self._run,
            args=(list(self.folders), tmp_root, self.quality),
            daemon=True,
        ).start()

    def _run(self, folders, tmp_root, quality):
        def progress(done, total, folder, path):
            self.root.after(0, lambda: self._on_progress(done, total, folder, path))

        try:
            results = process_folders(
                folders, tmp_root, quality=quality, on_progress=progress
            )
        except Exception as exc:  # noqa: BLE001 - 意外錯誤也要回報
            self.root.after(0, lambda: self._fatal(exc))
            return
        self.root.after(0, lambda: self._finish(results))

    def _on_progress(self, done, total, folder, path):
        self.progress.config(maximum=max(total, 1), value=done)
        self.taskbar.set(done, total)  # 同步工作列圖示進度
        loc = Path(folder).name
        if path is not None:
            loc += "\\" + Path(path).name
        self._set_status(f"轉檔中… ({done}/{total}) {loc}")

    def _fatal(self, exc):
        self.run_btn.config(state="normal")
        self.taskbar.clear()
        messagebox.showerror("發生錯誤", f"處理時發生未預期的錯誤：\n{exc}")
        self._set_status("發生錯誤", kind="error")

    def _finish(self, results):
        self.run_btn.config(state="normal")
        self.taskbar.clear()  # 移除工作列進度條

        ok = [r for r in results if r["status"] == "ok"]
        empty = [r for r in results if r["status"] == "empty"]
        collision = [r for r in results if r["status"] == "collision"]
        failed = [r for r in results if r["status"] == "failed"]

        # 成功/空資料夾從清單移除；有問題的（失敗/同名衝突）留著供處理
        done = {r["folder"] for r in ok + empty}
        self.folders = [f for f in self.folders if f not in done]
        self._refresh_list()

        summary = f"完成！成功 {len(ok)} 夾"
        if empty:
            summary += f"，無圖片 {len(empty)} 夾"
        if collision:
            summary += f"，同名衝突 {len(collision)} 夾"
        if failed:
            summary += f"，失敗 {len(failed)} 夾"

        if collision or failed:
            self.progress.config(value=0)  # 有問題：清空進度條
            self._set_status(summary, kind="error")
        else:
            # 全部成功：進度條保持滿格，配綠色訊息更直覺
            self.progress.config(value=self.progress.cget("maximum"))
            self._set_status("✓ " + summary, kind="ok")

        if collision or failed:
            lines = []
            for r in failed:
                names = "、".join(Path(s).name for s, _ in r["failures"])
                lines.append(f"[失敗] {r['folder']}（{names}）")
            for r in collision:
                lines.append(f"[同名衝突] {r['folder']}（資料夾內有同名來源）")
            messagebox.showwarning(
                "部分資料夾未處理（已保留在清單）",
                summary + "\n\n" + "\n".join(lines),
            )
        # 全部成功時不跳視窗，訊息已顯示在狀態列

        self._bring_to_front()  # 處理完成，把視窗帶到最上層提醒使用者

    # ---------- 設定的載入/儲存 ----------
    @staticmethod
    def _clamp_quality(value) -> int:
        try:
            return max(1, min(100, int(value)))
        except (TypeError, ValueError):
            return 90

    def _load_settings(self) -> dict:
        try:
            with open(_config_path(), encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_settings(self):
        path = _config_path()
        data = {"quality": self.quality}
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError as exc:
            print(f"[warn] 無法儲存設定到 {path}: {exc}")

    def _on_close(self):
        self._save_settings()
        self.root.destroy()


def main():
    root = TkinterDnD.Tk() if _DND_OK else Tk()
    FolderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
