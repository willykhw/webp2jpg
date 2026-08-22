"""資料夾批次轉檔核心（交易式）。

對每個資料夾「直接層」的圖片：轉成 JPG（先放暫存區）→ 整個資料夾都成功後，
先把被轉檔的原圖丟到回收桶，再把轉好的 JPG 放回資料夾。全有或全無。
所有支援的圖片格式（含既有 jpg，等於重新壓縮）都走同一套流程。
與 UI 無關，方便單元測試（刪除動作用可注入的 trash callable）。
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from converter import INPUT_EXTS, convert_one

# 要處理的來源格式：所有支援的圖片（含 jpg/jpeg；jpg 等於依品質重新壓縮）。
SOURCE_EXTS = set(INPUT_EXTS)


def _default_trash(path):
    # 延遲匯入，讓測試可注入假的 trash 而不需要 send2trash
    from send2trash import send2trash

    send2trash(str(path))


def list_source_images(folder) -> list[Path]:
    """資料夾直接層要處理的圖片（排除子資料夾，含 jpg）。"""
    folder = Path(folder)
    return sorted(
        f for f in folder.iterdir()
        if f.is_file() and f.suffix.lower() in SOURCE_EXTS
    )


def process_folder(folder, tmp_root, quality: int = 90, trash=_default_trash, on_item=None) -> dict:
    """交易式處理單一資料夾。回傳結果 dict：

        status   : "ok" | "empty" | "collision" | "failed"
        folder   : Path
        images   : int            該夾要處理的圖片數
        converted: [Path]         成功放回的 jpg（非 ok 時為空）
        failures : [(Path, str)]  失敗的來源與錯誤（僅 failed 時有內容）

    on_item(path) 會在每張圖片開始轉檔前呼叫一次（供進度顯示）。
    只有整個資料夾都轉成功，才會丟原圖並放回 jpg（全有或全無）。
    """
    folder = Path(folder)
    sources = list_source_images(folder)
    base = {"folder": folder, "images": len(sources), "converted": [], "failures": []}
    if not sources:
        return {**base, "status": "empty"}

    # 同資料夾內多個來源會輸出成相同檔名 -> 放棄該資料夾（避免互相覆蓋、誤刪）
    stems = [s.stem.lower() for s in sources]
    if len(set(stems)) != len(stems):
        return {**base, "status": "collision"}

    tmp_root = Path(tmp_root)
    tmp_root.mkdir(parents=True, exist_ok=True)
    tmp_dir = Path(tempfile.mkdtemp(dir=tmp_root))
    try:
        staged: list[tuple[Path, Path]] = []  # (原圖, 暫存 jpg)
        failures: list[tuple[Path, str]] = []
        for src in sources:
            if on_item:
                on_item(src)
            try:
                out = convert_one(src, tmp_dir, target="JPG", quality=quality)
                staged.append((src, out))
            except Exception as exc:  # noqa: BLE001 - 逐檔容錯
                failures.append((src, str(exc)))

        if failures:
            # 交易失敗：不動任何原檔（暫存區在 finally 清掉）
            return {**base, "status": "failed", "failures": failures}

        # 全部成功。依指定順序：先把原圖丟回收桶，再把 tmp 的 jpg 搬回資料夾。
        for src, _ in staged:
            trash(src)  # 原圖 -> 回收桶
        converted: list[Path] = []
        for src, tmp_out in staged:
            dst = folder / (src.stem + ".jpg")
            if dst.exists():
                dst.unlink()  # 保險：覆蓋既有同名 jpg
            shutil.move(str(tmp_out), str(dst))
            converted.append(dst)
        return {**base, "status": "ok", "converted": converted}
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def process_folders(folders, tmp_root, quality: int = 90, trash=_default_trash, on_progress=None):
    """依序處理多個資料夾，回傳結果清單。

    on_progress(done, total, folder, path) 以「圖片」為單位回呼，供進度條/狀態顯示：
      done  已處理張數、total 總張數、folder 目前資料夾、path 目前圖片（略過時為 None）。
    """
    # 先數總張數，讓進度條有正確的總量
    total = 0
    for f in folders:
        try:
            total += len(list_source_images(f))
        except OSError:
            pass

    done = 0
    results = []
    for folder in folders:
        def item_cb(path):
            nonlocal done
            done += 1
            if on_progress:
                on_progress(done, total, folder, path)

        res = process_folder(folder, tmp_root, quality=quality, trash=trash, on_item=item_cb)
        # 略過（collision）的資料夾其圖片沒觸發 item_cb，補進度讓總量對得上
        if res["status"] == "collision" and res["images"]:
            done += res["images"]
            if on_progress:
                on_progress(done, total, folder, None)
        results.append(res)
    return results
