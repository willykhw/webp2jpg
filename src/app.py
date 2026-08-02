"""圖片轉檔小工具（Windows 10/11）。

輸入 WebP/PNG/JPG/BMP/GIF/TIFF，輸出 JPG/PNG/WEBP，可調品質。
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

from converter import INPUT_EXTS, OUTPUT_FORMATS, convert_batch, target_extension

# 拖曳功能靠 tkinterdnd2；沒裝的話程式仍可用「加入檔案」按鈕運作。
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD

    _DND_OK = True
except ImportError:  # pragma: no cover - 取決於執行環境是否安裝
    _DND_OK = False

# 次要/提示文字用的柔和灰
_MUTED = "#777777"


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
        root.title("圖片轉檔小工具")
        root.geometry("580x800")
        root.minsize(500, 780)

        self.files: list[Path] = []

        # 讀回上次的設定
        settings = self._load_settings()
        self.output_dir = StringVar(value=settings.get("output_dir", ""))
        self.quality = self._clamp_quality(settings.get("quality", 90))
        self.use_source_dir = BooleanVar(value=bool(settings.get("use_source_dir", False)))
        fmt = str(settings.get("target_format", "JPG")).upper()
        self.target_format = StringVar(value=fmt if fmt in OUTPUT_FORMATS else "JPG")
        self.rename_on = BooleanVar(value=bool(settings.get("rename_on", False)))
        start = str(settings.get("rename_start", "1"))
        valid_start = start.isascii() and start.isdigit() and 1 <= len(start) <= 4
        self.rename_start = StringVar(value=start if valid_start else "1")

        self._build_ui()

        # 關閉視窗時把當下設定存下來
        root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------- UI 佈局 ----------
    def _setup_style(self):
        # 沿用系統原生主題（可調的元件看起來就明顯可調），只做少量間距與字重調整。
        style = ttk.Style()
        style.configure("TButton", padding=5)
        style.configure("Muted.TLabel", foreground=_MUTED)
        style.configure("TLabelframe.Label", font=("", 10, "bold"))
        style.configure("Go.TButton", padding=8, font=("", 10, "bold"))

    def _build_ui(self):
        self._setup_style()
        outer = ttk.Frame(self.root, padding=14)
        outer.pack(fill=BOTH, expand=True)

        self._build_source_section(outer)
        self._build_output_section(outer)
        self._build_naming_section(outer)
        self._build_run_section(outer)

        # 依載入的設定套用初始啟用/停用狀態
        self._on_toggle_default()
        self._on_format_change()
        self._on_toggle_rename()

    def _build_source_section(self, parent):
        """區塊 1：來源圖片清單與加入/移除按鈕。"""
        box = ttk.LabelFrame(parent, text=" 來源圖片 ", padding=12)
        box.pack(fill=BOTH, expand=True)

        hint = "把圖片拖進下面的清單，或按「加入檔案」" if _DND_OK \
            else "（未安裝 tkinterdnd2，請按「加入檔案」）"
        ttk.Label(box, text=hint, style="Muted.TLabel").pack(anchor="w", pady=(0, 8))

        list_frame = ttk.Frame(box)
        list_frame.pack(fill=BOTH, expand=True)
        self.listbox = Listbox(
            list_frame, selectmode="extended", height=7,
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
        ttk.Button(btn_row, text="加入檔案", command=self._add_files).pack(side="left")
        ttk.Button(btn_row, text="移除選取", command=self._remove_selected).pack(side="left", padx=6)
        ttk.Button(btn_row, text="移除全部", command=self._clear).pack(side="left")

    def _build_output_section(self, parent):
        """區塊 2：輸出格式、位置、品質（grid 對齊）。"""
        box = ttk.LabelFrame(parent, text=" 輸出設定 ", padding=12)
        box.pack(fill="x", pady=(14, 0))
        box.columnconfigure(1, weight=1)

        ttk.Label(box, text="輸出格式").grid(row=0, column=0, sticky="w", pady=5)
        self.fmt_combo = ttk.Combobox(
            box, textvariable=self.target_format, state="readonly",
            values=list(OUTPUT_FORMATS.keys()), width=10,
        )
        self.fmt_combo.grid(row=0, column=1, columnspan=2, sticky="w", padx=8, pady=5)
        self.fmt_combo.bind("<<ComboboxSelected>>", lambda e: self._on_format_change())

        ttk.Label(box, text="輸出位置").grid(row=1, column=0, sticky="w", pady=5)
        self.out_entry = ttk.Entry(box, textvariable=self.output_dir)
        self.out_entry.grid(row=1, column=1, sticky="ew", padx=8, pady=5)
        self.out_btn = ttk.Button(box, text="選擇…", width=8, command=self._choose_output)
        self.out_btn.grid(row=1, column=2, sticky="e", pady=5)

        ttk.Checkbutton(
            box, text="輸出到與來源檔相同的資料夾",
            variable=self.use_source_dir, command=self._on_toggle_default,
        ).grid(row=2, column=1, columnspan=2, sticky="w", padx=8)

        ttk.Separator(box, orient=HORIZONTAL).grid(
            row=3, column=0, columnspan=3, sticky="ew", pady=12
        )

        self.q_title = ttk.Label(box, text="品質")
        self.q_title.grid(row=4, column=0, sticky="w", pady=5)
        q_frame = ttk.Frame(box)
        q_frame.grid(row=4, column=1, columnspan=2, sticky="ew", padx=8, pady=5)
        self.q_scale = ttk.Scale(
            q_frame, from_=1, to=100, orient=HORIZONTAL, command=self._on_quality
        )
        self.q_scale.pack(side="left", fill="x", expand=True)
        self.q_label = ttk.Label(q_frame, text=str(self.quality), width=5, anchor="e")
        self.q_label.pack(side="right", padx=(8, 0))
        # q_label 建好後才設定滑桿值：set() 會觸發 _on_quality，需要 q_label 已存在
        self.q_scale.set(self.quality)

    def _build_naming_section(self, parent):
        """區塊 3：檔名（重新命名為流水號）。獨立於品質，避免混淆。"""
        box = ttk.LabelFrame(parent, text=" 檔名 ", padding=12)
        box.pack(fill="x", pady=(14, 0))

        row = ttk.Frame(box)
        row.pack(fill="x")
        ttk.Checkbutton(
            row, text="重新命名（流水號）",
            variable=self.rename_on, command=self._on_toggle_rename,
        ).pack(side="left")
        ttk.Label(row, text="起始數字").pack(side="left", padx=(16, 4))
        vcmd = (self.root.register(self._validate_start_digit), "%P")
        self.rename_start_entry = ttk.Entry(
            row, textvariable=self.rename_start, width=5,
            validate="key", validatecommand=vcmd, justify="center",
        )
        self.rename_start_entry.pack(side="left")

        # 預覽放在下一行，避免太長擠壓
        self.rename_preview = ttk.Label(box, style="Muted.TLabel")
        self.rename_preview.pack(anchor="w", pady=(8, 0))
        self.rename_start.trace_add("write", lambda *_: self._update_rename_preview())

    def _build_run_section(self, parent):
        """區塊 3：進度條、狀態列與主要動作按鈕。"""
        box = ttk.Frame(parent)
        box.pack(fill="x", pady=(14, 0))
        self.progress = ttk.Progressbar(box, mode="determinate")
        self.progress.pack(fill="x")
        self.status = StringVar(value="準備就緒")
        ttk.Label(box, textvariable=self.status, style="Muted.TLabel").pack(
            anchor="w", pady=(6, 10)
        )
        self.convert_btn = ttk.Button(
            box, text="開始轉檔", command=self._start_convert, style="Go.TButton"
        )
        self.convert_btn.pack(fill="x")

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
        pattern = " ".join(f"*{e}" for e in sorted(INPUT_EXTS))
        paths = filedialog.askopenfilenames(
            title="選擇圖片",
            filetypes=[("圖片", pattern), ("所有檔案", "*.*")],
        )
        self._add_paths(paths)

    def _add_paths(self, paths):
        added = skipped = 0
        for p in paths:
            path = Path(p)
            if path.suffix.lower() not in INPUT_EXTS:
                skipped += 1  # 不支援的格式略過
                continue
            if path not in self.files:
                self.files.append(path)
                self.listbox.insert(END, str(path))
                added += 1
        if added or skipped:
            msg = f"已加入 {added} 個檔案，共 {len(self.files)} 個"
            if skipped:
                msg += f"（略過 {skipped} 個不支援的格式）"
            self.status.set(msg)

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

    def _on_format_change(self):
        # PNG 為無損格式，品質滑桿沒作用，選 PNG 時停用它並標示「無損」
        lossy = OUTPUT_FORMATS[self.target_format.get()]["lossy"]
        self.q_scale.config(state="normal" if lossy else "disabled")
        self.q_label.config(text=str(self.quality) if lossy else "無損")
        self._update_rename_preview()  # 副檔名變了，預覽要跟著更新

    @staticmethod
    def _validate_start_digit(proposed: str) -> bool:
        # 起始數字只允許空字串，或 1-4 位的阿拉伯數字 0-9
        return proposed == "" or (
            len(proposed) <= 4 and proposed.isascii() and proposed.isdigit()
        )

    def _on_toggle_rename(self):
        state = "normal" if self.rename_on.get() else "disabled"
        self.rename_start_entry.config(state=state)
        self._update_rename_preview()

    def _update_rename_preview(self):
        if not self.rename_on.get():
            self.rename_preview.config(text="")
            return
        start = int(self.rename_start.get() or "0")
        ext = self._current_ext()
        sample = "、".join(f"{start + i:03d}{ext}" for i in range(3))
        self.rename_preview.config(text=f"→ {sample} …")

    def _on_quality(self, value):
        self.quality = int(float(value))
        self.q_label.config(text=str(self.quality))

    # ---------- 轉檔 ----------
    def _start_convert(self):
        if not self.files:
            messagebox.showwarning("沒有檔案", "請先加入至少一張圖片")
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

        target = self.target_format.get()

        # 每個檔案的輸出檔名（重新命名模式=流水號，否則沿用原檔名），與 files 等長。
        files = list(self.files)
        stems = self._output_stems(files)
        jobs = list(zip(files, stems))  # [(src, out_stem), ...]

        # 開工前先掃描同名檔，讓使用者決定覆蓋/略過/取消（在主執行緒問，避免
        # 轉檔背景執行緒開對話框造成的同步問題）
        jobs = self._resolve_conflicts(jobs, out_dir)
        if jobs is None:
            self.status.set("已取消")
            return  # 使用者取消
        skipped = len(self.files) - len(jobs)
        if not jobs:
            messagebox.showinfo("沒有要轉的檔案", "同名檔案都被略過了，沒有需要轉檔的項目。")
            self.status.set(f"已取消（略過 {skipped} 個）")
            return

        files_to_convert = [src for src, _ in jobs]
        out_stems = [stem for _, stem in jobs]

        self.convert_btn.config(state="disabled")
        self.progress.config(value=0, maximum=len(jobs))
        self.status.set("轉檔中…")

        # 轉檔放到背景執行緒，避免 UI 卡住
        threading.Thread(
            target=self._run_convert,
            args=(files_to_convert, out_stems, out_dir, target, self.quality, skipped),
            daemon=True,
        ).start()

    def _output_stems(self, files) -> list[str]:
        """依目前設定算出每個檔案的輸出檔名（不含副檔名）。"""
        if self.rename_on.get():
            start = int(self.rename_start.get() or "0")
            return [f"{start + i:03d}" for i in range(len(files))]
        return [Path(f).stem for f in files]

    # 對話框衝突清單最多顯示幾筆，避免視窗爆長
    _MAX_SHOW = 10

    def _current_ext(self) -> str:
        """目前選定輸出格式的副檔名（例如 '.jpg'）。"""
        return target_extension(self.target_format.get())

    def _target_of(self, src, stem, out_dir) -> Path:
        # 完整輸出路徑（用目前選定的輸出格式副檔名）。
        # out_dir 為 None（預設模式）時輸出到來源檔旁邊。
        parent = Path(src).parent if out_dir is None else Path(out_dir)
        return parent / (stem + self._current_ext())

    def _resolve_conflicts(self, jobs, out_dir):
        """輸入/回傳 [(src, out_stem), ...]；使用者取消則回傳 None。

        以「完整輸出路徑」判斷衝突，兩種情況都會跳警告：
          A. 批次內部多個來源會輸出到同一路徑（彼此覆蓋）
          B. 輸出路徑已存在同名檔
        """
        jobs = self._resolve_duplicate_names(jobs, out_dir)
        if jobs is None:
            return None  # 使用者在 A 取消
        return self._resolve_existing_files(jobs, out_dir)

    def _resolve_duplicate_names(self, jobs, out_dir):
        """A：處理批次內部同名（多個來源 -> 同一輸出路徑）。"""
        groups: dict[str, list] = {}
        for src, stem in jobs:
            groups.setdefault(str(self._target_of(src, stem, out_dir)), []).append(src)
        dups = {key: srcs for key, srcs in groups.items() if len(srcs) > 1}
        if not dups:
            return jobs

        lines = []
        for key, srcs in list(dups.items())[: self._MAX_SHOW]:
            shown = "\n".join(f"    {Path(x)}" for x in srcs)
            lines.append(f"{Path(key).name}：\n{shown}")
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
            # 每個輸出路徑只留第一個出現的工作項（保持原順序）
            seen = set()
            kept = []
            for src, stem in jobs:
                key = str(self._target_of(src, stem, out_dir))
                if key not in seen:
                    seen.add(key)
                    kept.append((src, stem))
            return kept
        # 否：把所有牽涉重複的工作項整組拿掉，只留輸出路徑唯一的
        return [
            (src, stem)
            for src, stem in jobs
            if len(groups[str(self._target_of(src, stem, out_dir))]) == 1
        ]

    def _resolve_existing_files(self, jobs, out_dir):
        """B：處理與已存在檔案的同名衝突（用完整輸出路徑判斷）。"""
        conflicts = [
            (src, stem) for src, stem in jobs if self._target_of(src, stem, out_dir).exists()
        ]
        if not conflicts:
            return jobs

        names = "\n".join(
            self._target_of(src, stem, out_dir).name for src, stem in conflicts[: self._MAX_SHOW]
        )
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
            return [job for job in jobs if job not in conflict_set]  # 略過
        return jobs  # 覆蓋

    def _run_convert(self, files, out_stems, out_dir, target, quality, skipped=0):
        def progress(i, total, src, result):
            # 從背景執行緒安全更新 UI
            self.root.after(0, lambda: self._update_progress(i, total, src))

        successes, failures = convert_batch(
            files, out_dir, target=target, quality=quality,
            out_stems=out_stems, on_progress=progress,
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
            "target_format": self.target_format.get(),
            "rename_on": self.rename_on.get(),
            "rename_start": self.rename_start.get() or "1",
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
