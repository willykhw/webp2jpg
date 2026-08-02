"""圖片轉檔核心邏輯（純函式，與 UI 無關，方便單元測試）。

支援多種輸入格式轉成 JPG / PNG / WEBP，可調品質，
並依目標格式決定是否保留透明（JPG 不支援透明時填底色）。
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

# JPG 不支援透明通道，遇到帶 alpha 的來源時用這個底色填滿。
DEFAULT_BACKGROUND = (255, 255, 255)  # 白色

# 支援的輸出格式：Pillow 格式名、副檔名、是否有損、是否支援透明
OUTPUT_FORMATS = {
    "JPG": {"pillow": "JPEG", "ext": ".jpg", "lossy": True, "alpha": False},
    "PNG": {"pillow": "PNG", "ext": ".png", "lossy": False, "alpha": True},
    "WEBP": {"pillow": "WEBP", "ext": ".webp", "lossy": True, "alpha": True},
}

# 可接受的輸入副檔名
INPUT_EXTS = {".webp", ".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff"}


def target_extension(target: str) -> str:
    """回傳目標格式的副檔名（例如 'JPG' -> '.jpg'）。"""
    return OUTPUT_FORMATS[target.upper()]["ext"]


def _has_alpha(im: Image.Image) -> bool:
    return im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)


def convert_one(
    src,
    dst_dir,
    target: str = "JPG",
    quality: int = 90,
    background: tuple[int, int, int] = DEFAULT_BACKGROUND,
    out_stem: str | None = None,
) -> Path:
    """把單一圖片轉成指定格式，回傳輸出檔路徑。

    src        : 來源圖片
    dst_dir    : 輸出資料夾（需已存在）；傳 None 代表輸出到來源檔的同一資料夾
    target     : 目標格式 'JPG' / 'PNG' / 'WEBP'
    quality    : 有損格式（JPG/WEBP）的品質 1-100；PNG 無損會忽略
    background : 目標不支援透明（JPG）且來源有透明時，透明區域填的 RGB 底色
    out_stem   : 指定輸出檔名（不含副檔名）；None 則沿用來源檔名
    """
    target = target.upper()
    if target not in OUTPUT_FORMATS:
        raise ValueError(f"不支援的目標格式：{target}")
    if not 1 <= quality <= 100:
        raise ValueError(f"quality 必須介於 1-100，收到 {quality}")

    spec = OUTPUT_FORMATS[target]
    src = Path(src)
    target_dir = src.parent if dst_dir is None else Path(dst_dir)
    stem = src.stem if out_stem is None else out_stem

    with Image.open(src) as im:
        if spec["alpha"]:
            # 目標支援透明：有 alpha 就保留 RGBA，否則存 RGB
            out_im = im.convert("RGBA") if _has_alpha(im) else im.convert("RGB")
        elif _has_alpha(im):
            # 目標不支援透明且來源有透明：貼到不透明底色上
            rgba = im.convert("RGBA")
            canvas = Image.new("RGB", rgba.size, background)
            canvas.paste(rgba, mask=rgba.split()[-1])  # 用 alpha 當遮罩
            out_im = canvas
        else:
            out_im = im.convert("RGB")

        dst = target_dir / (stem + spec["ext"])
        save_kwargs = {}
        if spec["lossy"]:
            save_kwargs["quality"] = quality
        else:  # PNG：無損，開最佳化
            save_kwargs["optimize"] = True
        out_im.save(dst, spec["pillow"], **save_kwargs)

    return dst


def convert_batch(
    sources,
    dst_dir,
    target: str = "JPG",
    quality: int = 90,
    background: tuple[int, int, int] = DEFAULT_BACKGROUND,
    out_stems=None,
    on_progress=None,
):
    """批次轉檔。回傳 (successes, failures)。

    single 檔失敗不會中斷整批，會收集到 failures 裡（Rule 12：失敗要浮出來）。
    out_stems  : 與 sources 等長的輸出檔名清單（不含副檔名）；None 則沿用來源檔名。
    on_progress(index, total, src, result_or_error) 每處理完一個就回呼一次。
    """
    sources = [Path(s) for s in sources]
    if out_stems is not None and len(out_stems) != len(sources):
        raise ValueError("out_stems 長度必須與 sources 相同")
    if dst_dir is not None:
        dst_dir = Path(dst_dir)
        dst_dir.mkdir(parents=True, exist_ok=True)

    successes: list[Path] = []
    failures: list[tuple[Path, str]] = []
    total = len(sources)

    for i, src in enumerate(sources, start=1):
        try:
            out = convert_one(
                src, dst_dir, target=target, quality=quality, background=background,
                out_stem=None if out_stems is None else out_stems[i - 1],
            )
            successes.append(out)
            if on_progress:
                on_progress(i, total, src, out)
        except Exception as exc:  # noqa: BLE001 - 逐檔容錯，錯誤照實記錄
            failures.append((src, str(exc)))
            if on_progress:
                on_progress(i, total, src, exc)

    return successes, failures
