"""converter 的單元測試。

重點不只是「有沒有產出檔」，而是驗證商業意圖：
- JPG 不能有透明通道（否則存檔會壞）
- 透明區域必須被指定底色填滿（不是變黑或亂掉）
- 品質參數要真的影響輸出（越低檔案越小）
- 單檔失敗不能拖垮整批
"""

from pathlib import Path

import pytest
from PIL import Image

from converter import convert_batch, convert_one, target_extension


def _make_webp(path: Path, mode="RGB", color=(120, 60, 200), size=(64, 64)):
    Image.new(mode, size, color).save(path, "WEBP")
    return path


def test_convert_produces_rgb_jpg(tmp_path):
    src = _make_webp(tmp_path / "a.webp")
    out = convert_one(src, tmp_path, quality=90)
    assert out.exists() and out.suffix == ".jpg"
    with Image.open(out) as im:
        assert im.format == "JPEG"
        assert im.mode == "RGB"  # 絕不能帶 alpha，否則就不是合法 JPG


def test_transparent_area_filled_with_background(tmp_path):
    # 左半透明、右半不透明的圖；轉檔後左半應該變成指定底色
    src = tmp_path / "t.webp"
    im = Image.new("RGBA", (2, 1), (0, 0, 0, 0))
    im.putpixel((0, 0), (0, 0, 0, 0))      # 全透明
    im.putpixel((1, 0), (10, 20, 30, 255))  # 不透明
    im.save(src, "WEBP")

    out = convert_one(src, tmp_path, quality=95, background=(255, 255, 255))
    with Image.open(out) as res:
        # 透明像素應被填成白底（JPEG 有壓縮誤差，容忍幾階）
        r, g, b = res.getpixel((0, 0))
        assert r > 245 and g > 245 and b > 245


def test_lower_quality_yields_smaller_file(tmp_path):
    # 用有細節的圖，品質差異才看得出來
    src = tmp_path / "noise.webp"
    im = Image.effect_noise((128, 128), 80).convert("RGB")
    im.save(src, "WEBP")

    hi_dir = tmp_path / "hi"
    lo_dir = tmp_path / "lo"
    hi_dir.mkdir()
    lo_dir.mkdir()
    high = convert_one(src, hi_dir, quality=95)
    low = convert_one(src, lo_dir, quality=20)
    assert low.stat().st_size < high.stat().st_size  # 品質確實生效


def test_invalid_quality_rejected(tmp_path):
    src = _make_webp(tmp_path / "a.webp")
    with pytest.raises(ValueError):
        convert_one(src, tmp_path, quality=150)


def test_invalid_target_rejected(tmp_path):
    src = _make_webp(tmp_path / "a.webp")
    with pytest.raises(ValueError):
        convert_one(src, tmp_path, target="GIF")  # 不在支援清單


def test_png_output_keeps_transparency(tmp_path):
    # 輸出 PNG 時透明必須被保留（這是選 PNG 而非 JPG 的核心理由）
    src = tmp_path / "t.webp"
    im = Image.new("RGBA", (4, 4), (0, 0, 0, 0))  # 全透明
    im.save(src, "WEBP")

    out = convert_one(src, tmp_path, target="PNG")
    assert out.suffix == ".png"
    with Image.open(out) as res:
        assert res.mode == "RGBA"
        assert res.getpixel((0, 0))[3] == 0  # alpha 仍為 0（透明）


def test_jpg_output_flattens_transparency(tmp_path):
    # 對照組：輸出 JPG 時透明必須被填底色、不能帶 alpha
    src = tmp_path / "t.webp"
    Image.new("RGBA", (4, 4), (0, 0, 0, 0)).save(src, "WEBP")

    out = convert_one(src, tmp_path, target="JPG", background=(255, 255, 255))
    with Image.open(out) as res:
        assert res.mode == "RGB"
        assert all(c > 245 for c in res.getpixel((0, 0)))


def test_webp_output(tmp_path):
    src = _make_webp(tmp_path / "src.webp")  # 拿 png 當來源更中性
    png = tmp_path / "src.png"
    Image.new("RGB", (8, 8), (10, 20, 30)).save(png, "PNG")
    (tmp_path / "out").mkdir()
    out = convert_one(png, tmp_path / "out", target="WEBP")
    assert out.suffix == ".webp"
    with Image.open(out) as res:
        assert res.format == "WEBP"


def test_resize_shrinks_long_edge_only(tmp_path):
    # 寬 200 高 100，限制最長邊 50 -> 應變成 50x25（等比例）
    src = tmp_path / "wide.png"
    Image.new("RGB", (200, 100), (0, 0, 0)).save(src, "PNG")
    (tmp_path / "o").mkdir()
    out = convert_one(src, tmp_path / "o", target="PNG", max_edge=50)
    with Image.open(out) as res:
        assert res.size == (50, 25)


def test_resize_never_upscales(tmp_path):
    # 圖片已比上限小，不應被放大
    src = tmp_path / "small.png"
    Image.new("RGB", (30, 20), (0, 0, 0)).save(src, "PNG")
    (tmp_path / "o2").mkdir()
    out = convert_one(src, tmp_path / "o2", target="PNG", max_edge=500)
    with Image.open(out) as res:
        assert res.size == (30, 20)


def test_target_extension():
    assert target_extension("JPG") == ".jpg"
    assert target_extension("png") == ".png"  # 大小寫不敏感
    assert target_extension("WEBP") == ".webp"


def test_dst_none_outputs_beside_source(tmp_path):
    # dst_dir=None 代表「預設」模式：輸出到來源檔的同一資料夾
    sub = tmp_path / "sub"
    sub.mkdir()
    src = _make_webp(sub / "pic.webp")
    out = convert_one(src, None, quality=80)
    assert out == sub / "pic.jpg"  # 就在來源旁邊
    assert out.exists()


def test_batch_dst_none_keeps_each_beside_its_source(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    s1 = _make_webp(a / "x.webp")
    s2 = _make_webp(b / "y.webp")
    successes, failures = convert_batch([s1, s2], None)
    assert not failures
    assert set(successes) == {a / "x.jpg", b / "y.jpg"}


def test_batch_isolates_failures(tmp_path):
    good = _make_webp(tmp_path / "good.webp")
    bad = tmp_path / "bad.webp"
    bad.write_text("this is not an image")  # 壞檔

    successes, failures = convert_batch([good, bad], tmp_path / "out")
    # 壞檔不能拖垮好檔（Rule 12：失敗要浮出來，但不吞掉成功的）
    assert len(successes) == 1
    assert len(failures) == 1
    assert failures[0][0] == bad
