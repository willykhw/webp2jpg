"""WebP -> JPG 圖片轉檔小工具（Windows 10/11）。

啟動：python app.py
需要：Pillow、tkinterdnd2（見 requirements.txt）
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
    BooleanVar,
    Listbox,
    StringVar,
    Tk,
    filedialog,
    messagebox,
)
from tkinter import ttk

from converter import convert_batch

# 拖曳功能靠 tkinterdnd2；沒裝的話程式仍可用「加入檔案」按鈕運作。
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD

    _DND_OK = True
except ImportError:  # pragma: no cover - 取決於執行環境是否安裝
    _DND_OK = False


def _config_path() -> Path:
    """設定檔位置：跟程式放在同一個資料夾（webp2jpg/config.json）。

    注意 --onefile 打包後 __file__ 會指到暫存解壓區，所以要判斷是否被凍結：
    - 打包後（sys.frozen）用 exe 真正所在的資料夾（sys.executable）
    - 原始碼執行則用 app.py 所在資料夾
    """
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).parent
    else:
        base = Path(__file__).resolve().parent
    return base / "config.json"


class ConverterApp:
    def __init__(self, root: Tk):
        self.root = root
        root.title("WebP → JPG 轉檔小工具")
        root.geometry("560x520")
        root.minsize(480, 460)

        self.files: list[Path] = []

        # 讀回上次的設定（輸出資料夾、品質、是否輸出到來源資料夾）
        settings = self._load_settings()
        self.output_dir = StringVar(value=settings.get("output_dir", ""))
        self.quality = self._clamp_quality(settings.get("quality", 90))
        self.use_source_dir = BooleanVar(value=bool(settings.get("use_source_dir", False)))

        self._build_ui()

        # 關閉視窗時把當下設定存下來
        root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------- UI 佈局 ----------
    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}

        hint = "把 .webp 檔拖進下面的清單" if _DND_OK else "（未安裝 tkinterdnd2，請用下方按鈕加入檔案）"
        ttk.Label(self.root, text=hint).pack(anchor="w", **pad)

        # 檔案清單
        list_frame = ttk.Frame(self.root)
        list_frame.pack(fill=BOTH, expand=True, padx=10)
        self.listbox = Listbox(list_frame, selectmode="extended")
        self.listbox.pack(side="left", fill=BOTH, expand=True)
        scroll = ttk.Scrollbar(list_frame, command=self.listbox.yview)
        scroll.pack(side="right", fill="y")
        self.listbox.config(yscrollcommand=scroll.set)

        if _DND_OK:
            self.listbox.drop_target_register(DND_FILES)
            self.listbox.dnd_bind("<<Drop>>", self._on_drop)

        # 檔案操作按鈕
        btn_row = ttk.Frame(self.root)
        btn_row.pack(fill="x", **pad)
        ttk.Button(btn_row, text="加入檔案", command=self._add_files).pack(side="left")
        ttk.Button(btn_row, text="移除選取", command=self._remove_selected).pack(side="left", padx=6)
        ttk.Button(btn_row, text="移除全部", command=self._clear).pack(side="left")

        # 輸出資料夾
        out_row = ttk.Frame(self.root)
        out_row.pack(fill="x", **pad)
        ttk.Label(out_row, text="輸出資料夾：").pack(side="left")
        self.out_entry = ttk.Entry(out_row, textvariable=self.output_dir)
        self.out_entry.pack(side="left", fill="x", expand=True, padx=6)
        self.out_btn = ttk.Button(out_row, text="選擇…", command=self._choose_output)
        self.out_btn.pack(side="left")

        # 「預設」＝輸出到與來源檔相同的資料夾（勾了就不用選路徑）
        ttk.Checkbutton(
            self.root,
            text="預設（輸出到與來源檔相同的資料夾）",
            variable=self.use_source_dir,
            command=self._on_toggle_default,
        ).pack(anchor="w", padx=10)
        self._on_toggle_default()  # 依載入的設定套用初始啟用/停用狀態

        # 品質滑桿
        q_row = ttk.Frame(self.root)
        q_row.pack(fill="x", **pad)
        ttk.Label(q_row, text="JPG 品質：").pack(side="left")
        self.q_label = ttk.Label(q_row, text=str(self.quality), width=4)
        self.q_label.pack(side="right")
        self.q_scale = ttk.Scale(
            q_row, from_=1, to=100, orient=HORIZONTAL, command=self._on_quality
        )
        self.q_scale.set(self.quality)
        self.q_scale.pack(side="left", fill="x", expand=True, padx=6)

        # 轉檔 + 進度
        self.progress = ttk.Progressbar(self.root, mode="determinate")
        self.progress.pack(fill="x", padx=10, pady=(4, 0))
        self.status = StringVar(value="準備就緒")
        ttk.Label(self.root, textvariable=self.status).pack(anchor="w", **pad)
        self.convert_btn = ttk.Button(self.root, text="開始轉檔", command=self._start_convert)
        self.convert_btn.pack(pady=(0, 10))

    # ---------- 事件處理 ----------
    def _on_drop(self, event):
        # DnD 回傳的路徑字串可能含大括號（路徑有空白時），用 splitlist 正確拆解
        paths = self.root.tk.splitlist(event.data)
        # 上一批已轉完（進度條 100%）時再拖新檔，視為開新的一批，先清空舊清單
        if self._progress_full():
            self._clear()
        self._add_paths(paths)

    def _progress_full(self) -> bool:
        try:
            value = float(self.progress["value"])
            maximum = float(self.progress["maximum"])
        except (KeyError, ValueError):
            return False
        return value > 0 and value >= maximum

    def _add_files(self):
        paths = filedialog.askopenfilenames(
            title="選擇 WebP 檔",
            filetypes=[("WebP 圖片", "*.webp"), ("所有檔案", "*.*")],
        )
        self._add_paths(paths)

    def _add_paths(self, paths):
        added = 0
        for p in paths:
            path = Path(p)
            if path.suffix.lower() != ".webp":
                continue  # 目前只吃 webp
            if path not in self.files:
                self.files.append(path)
                self.listbox.insert(END, str(path))
                added += 1
        if added:
            self.status.set(f"已加入 {added} 個檔案，共 {len(self.files)} 個")

    def _remove_selected(self):
        for idx in reversed(self.listbox.curselection()):
            self.listbox.delete(idx)
            del self.files[idx]
        self.progress.config(value=0)  # 清單一有變動，舊的轉檔進度就失效
        self.status.set(f"清單剩 {len(self.files)} 個檔案")

    def _clear(self):
        self.listbox.delete(0, END)
        self.files.clear()
        self.progress.config(value=0)
        self.status.set("清單已清空")

    def _choose_output(self):
        d = filedialog.askdirectory(title="選擇輸出資料夾")
        if d:
            self.output_dir.set(d)

    def _on_toggle_default(self):
        # 勾「預設」時就不需要選輸出路徑，把欄位和按鈕停用（灰掉）
        state = "disabled" if self.use_source_dir.get() else "normal"
        self.out_entry.config(state=state)
        self.out_btn.config(state=state)

    def _on_quality(self, value):
        self.quality = int(float(value))
        self.q_label.config(text=str(self.quality))

    # ---------- 轉檔 ----------
    def _start_convert(self):
        if not self.files:
            messagebox.showwarning("沒有檔案", "請先加入至少一個 .webp 檔案")
            return

        # 勾了「預設」就輸出到各來源檔旁邊（out_dir=None），否則要求選路徑
        if self.use_source_dir.get():
            out_dir = None
        else:
            out = self.output_dir.get().strip()
            if not out:
                messagebox.showwarning("沒有輸出位置", "請先選擇輸出資料夾，或勾選「預設」")
                return
            out_dir = Path(out)

        # 開工前先掃描同名檔，讓使用者決定覆蓋/略過/取消（在主執行緒問，避免
        # 轉檔背景執行緒開對話框造成的同步問題）
        files_to_convert = self._resolve_conflicts(list(self.files), out_dir)
        if files_to_convert is None:
            self.status.set("已取消")
            return  # 使用者取消
        skipped = len(self.files) - len(files_to_convert)
        if not files_to_convert:
            messagebox.showinfo("沒有要轉的檔案", "同名檔案都被略過了，沒有需要轉檔的項目。")
            self.status.set(f"已取消（略過 {skipped} 個）")
            return

        self.convert_btn.config(state="disabled")
        self.progress.config(value=0, maximum=len(files_to_convert))
        self.status.set("轉檔中…")

        # 轉檔放到背景執行緒，避免 UI 卡住
        threading.Thread(
            target=self._run_convert,
            args=(files_to_convert, out_dir, self.quality, skipped),
            daemon=True,
        ).start()

    # 對話框衝突清單最多顯示幾筆，避免視窗爆長
    _MAX_SHOW = 10

    @staticmethod
    def _target_of(f, out_dir) -> Path:
        # 完整輸出路徑。out_dir 為 None（預設模式）時輸出到來源檔旁邊。
        parent = Path(f).parent if out_dir is None else Path(out_dir)
        return parent / (Path(f).stem + ".jpg")

    def _resolve_conflicts(self, files, out_dir):
        """回傳實際要轉的檔案清單；使用者取消則回傳 None。

        以「完整輸出路徑」判斷衝突，涵蓋兩種情況都會跳警告：
          A. 批次內部多個來源會輸出到同一路徑（彼此覆蓋）
          B. 輸出路徑已存在同名 .jpg
        """
        files = self._resolve_duplicate_names(files, out_dir)
        if files is None:
            return None  # 使用者在 A 取消
        return self._resolve_existing_files(files, out_dir)

    def _resolve_duplicate_names(self, files, out_dir):
        """A：處理批次內部同名（多個來源 -> 同一輸出路徑）。"""
        groups: dict[str, list] = {}
        for f in files:
            groups.setdefault(str(self._target_of(f, out_dir)), []).append(f)
        dups = {key: fs for key, fs in groups.items() if len(fs) > 1}
        if not dups:
            return files

        lines = []
        for key, fs in list(dups.items())[: self._MAX_SHOW]:
            srcs = "\n".join(f"    {Path(x)}" for x in fs)
            lines.append(f"{Path(key).name}：\n{srcs}")
        detail = "\n".join(lines)
        if len(dups) > self._MAX_SHOW:
            detail += f"\n…（還有 {len(dups) - self._MAX_SHOW} 組）"

        answer = messagebox.askyesnocancel(
            "檔名重複",
            f"有 {len(dups)} 組來源檔會輸出成相同檔名、彼此覆蓋：\n\n{detail}\n\n"
            "要如何處理？\n\n"
            "［是］每個名稱只轉第一個　　［否］這些全部略過　　［取消］不轉檔",
        )
        if answer is None:
            return None
        if answer is True:
            # 每個輸出路徑只留第一個出現的來源（保持原順序）
            seen = set()
            kept = []
            for f in files:
                key = str(self._target_of(f, out_dir))
                if key not in seen:
                    seen.add(key)
                    kept.append(f)
            return kept
        # 否：把所有牽涉重複的來源整組拿掉，只留輸出路徑唯一的
        return [f for f in files if len(groups[str(self._target_of(f, out_dir))]) == 1]

    def _resolve_existing_files(self, files, out_dir):
        """B：處理與已存在檔案的同名衝突（用完整輸出路徑判斷）。"""
        conflicts = [f for f in files if self._target_of(f, out_dir).exists()]
        if not conflicts:
            return files

        names = "\n".join(self._target_of(f, out_dir).name for f in conflicts[: self._MAX_SHOW])
        if len(conflicts) > self._MAX_SHOW:
            names += f"\n…（還有 {len(conflicts) - self._MAX_SHOW} 個）"

        answer = messagebox.askyesnocancel(
            "檔案已存在",
            f"輸出位置已有 {len(conflicts)} 個同名檔案：\n\n{names}\n\n"
            "要覆蓋這些檔案嗎？\n\n"
            "［是］覆蓋　　［否］略過這些檔案　　［取消］不轉檔",
        )
        if answer is None:
            return None  # 取消
        if answer is False:
            conflict_set = set(conflicts)
            return [f for f in files if f not in conflict_set]  # 略過
        return files  # 覆蓋

    def _run_convert(self, files, out_dir, quality, skipped=0):
        def progress(i, total, src, result):
            # 從背景執行緒安全更新 UI
            self.root.after(0, lambda: self._update_progress(i, total, src))

        successes, failures = convert_batch(
            files, out_dir, quality=quality, on_progress=progress
        )
        self.root.after(0, lambda: self._finish(successes, failures, skipped))

    def _update_progress(self, i, total, src):
        self.progress.config(value=i)
        self.status.set(f"轉檔中… ({i}/{total}) {Path(src).name}")

    def _finish(self, successes, failures, skipped=0):
        self.convert_btn.config(state="normal")
        msg = f"完成！成功 {len(successes)} 個"
        if skipped:
            msg += f"，略過 {skipped} 個"
        if failures:
            msg += f"，失敗 {len(failures)} 個"
            detail = "\n".join(f"{Path(s).name}: {err}" for s, err in failures)
            messagebox.showerror("部分檔案轉檔失敗", detail)
        else:
            messagebox.showinfo("完成", msg)
        self.status.set(msg)

    # ---------- 設定的載入/儲存 ----------
    @staticmethod
    def _clamp_quality(value) -> int:
        # 設定檔可能被手動改壞，讀進來一律夾回合法範圍
        try:
            return max(1, min(100, int(value)))
        except (TypeError, ValueError):
            return 90

    def _load_settings(self) -> dict:
        # 設定檔不存在或壞掉都不該讓程式開不起來，靜默退回預設
        try:
            with open(_config_path(), encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_settings(self):
        path = _config_path()
        data = {
            "output_dir": self.output_dir.get().strip(),
            "quality": self.quality,
            "use_source_dir": self.use_source_dir.get(),
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError as exc:
            # 存不起來不影響使用，但要讓使用者知道（Rule 12：失敗要浮出來）
            print(f"[warn] 無法儲存設定到 {path}: {exc}")

    def _on_close(self):
        self._save_settings()
        self.root.destroy()


def main():
    root = TkinterDnD.Tk() if _DND_OK else Tk()
    ConverterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
