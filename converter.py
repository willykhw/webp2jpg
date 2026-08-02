"""WebP -> JPG 轉檔核心邏輯（純函式，與 UI 無關，方便單元測試）。"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

# JPG 不支援透明通道，遇到帶 alpha 的來源時用這個底色填滿。
DEFAULT_BACKGROUND = (255, 255, 255)  # 白色


def convert_one(
    src: Path,
    dst_dir: Path | None,
    quality: int = 90,
    background: tuple[int, int, int] = DEFAULT_BACKGROUND,
) -> Path:
    """把單一 WebP 檔轉成 JPG，回傳輸出檔路徑。

    src        : 來源 .webp 檔
    dst_dir    : 輸出資料夾（需已存在）；傳 None 代表輸出到來源檔的同一資料夾
    quality    : JPG 品質 1-100，數字越大畫質越好、檔案越大
    background : 來源含透明時，透明區域要填的 RGB 底色
    """
    if not 1 <= quality <= 100:
        raise ValueError(f"quality 必須介於 1-100，收到 {quality}")

    src = Path(src)
    target_dir = src.parent if dst_dir is None else Path(dst_dir)

    with Image.open(src) as im:
        # 有透明通道（RGBA / LA / P 帶 transparency）就先貼到不透明底色上，
        # 否則直接轉成 RGB。
        if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
            rgba = im.convert("RGBA")
            canvas = Image.new("RGB", rgba.size, background)
            canvas.paste(rgba, mask=rgba.split()[-1])  # 用 alpha 當遮罩
            rgb = canvas
        else:
            rgb = im.convert("RGB")

        dst = target_dir / (src.stem + ".jpg")
        rgb.save(dst, "JPEG", quality=quality)

    return dst


def convert_batch(
    sources,
    dst_dir: Path,
    quality: int = 90,
    background: tuple[int, int, int] = DEFAULT_BACKGROUND,
    on_progress=None,
):
    """批次轉檔。回傳 (successes, failures)。

    single 檔失敗不會中斷整批，會收集到 failures 裡（Rule 12：失敗要浮出來）。
    on_progress(index, total, src, result_or_error) 每處理完一個就回呼一次。
    """
    sources = [Path(s) for s in sources]
    if dst_dir is not None:
        dst_dir = Path(dst_dir)
        dst_dir.mkdir(parents=True, exist_ok=True)

    successes: list[Path] = []
    failures: list[tuple[Path, str]] = []
    total = len(sources)

    for i, src in enumerate(sources, start=1):
        try:
            out = convert_one(src, dst_dir, quality=quality, background=background)
            successes.append(out)
            if on_progress:
                on_progress(i, total, src, out)
        except Exception as exc:  # noqa: BLE001 - 逐檔容錯，錯誤照實記錄
            failures.append((src, str(exc)))
            if on_progress:
                on_progress(i, total, src, exc)

    return successes, failures
