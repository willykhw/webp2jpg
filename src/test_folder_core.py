"""folder_core 的單元測試。

重點驗證交易式語意：
- 全部成功才丟原圖、放回 jpg；先刪後搬（順序）
- 任一失敗則整個資料夾原檔不動（全有或全無）
- 只刪被轉檔的原圖，非圖片檔（.txt）保留
- 所有圖片（含 jpg）走同一流程；同名來源會放棄該資料夾
- 進度以「圖片」為單位回呼
"""

from pathlib import Path

from PIL import Image

from folder_core import list_source_images, process_folder, process_folders


def _img(path: Path, fmt="WEBP", color=(120, 60, 200)):
    Image.new("RGB", (16, 16), color).save(path, fmt)
    return path


def _make_trash():
    """回傳 (trash callable, 被丟清單)。用實際刪除模擬移到回收桶。"""
    trashed: list[Path] = []

    def trash(p):
        trashed.append(Path(p))
        Path(p).unlink()

    return trash, trashed


def test_empty_folder(tmp_path):
    folder = tmp_path / "f"
    folder.mkdir()
    (folder / "note.txt").write_text("hi")  # 非圖片
    trash, trashed = _make_trash()
    res = process_folder(folder, tmp_path / "tmp", trash=trash)
    assert res["status"] == "empty"
    assert trashed == []
    assert (folder / "note.txt").exists()


def test_success_converts_and_trashes_only_originals(tmp_path):
    folder = tmp_path / "f"
    folder.mkdir()
    a = _img(folder / "a.webp")
    b = _img(folder / "b.png", fmt="PNG")
    note = folder / "note.txt"
    note.write_text("keep me")
    trash, trashed = _make_trash()

    res = process_folder(folder, tmp_path / "tmp", trash=trash)

    assert res["status"] == "ok"
    assert (folder / "a.jpg").exists() and (folder / "b.jpg").exists()
    assert not a.exists() and not b.exists()
    assert set(trashed) == {a, b}
    assert note.exists() and note.read_text() == "keep me"  # 非圖片保留


def test_failure_is_atomic(tmp_path):
    folder = tmp_path / "f"
    folder.mkdir()
    good = _img(folder / "good.webp")
    bad = folder / "bad.webp"
    bad.write_text("not an image")
    trash, trashed = _make_trash()

    res = process_folder(folder, tmp_path / "tmp", trash=trash)

    assert res["status"] == "failed"
    assert [p for p, _ in res["failures"]] == [bad]
    assert good.exists() and bad.exists()
    assert not (folder / "good.jpg").exists()
    assert trashed == []


def test_trashes_before_moving(tmp_path):
    # 驗證順序：先把原圖丟回收桶，之後才把 tmp 的 jpg 搬回資料夾。
    folder = tmp_path / "f"
    folder.mkdir()
    _img(folder / "a.webp")
    _img(folder / "b.png", fmt="PNG")

    events = []

    def trash(p):
        events.append(sorted(x.name for x in folder.glob("*.jpg")))
        Path(p).unlink()

    process_folder(folder, tmp_path / "tmp", trash=trash)
    assert len(events) == 2
    for jpgs in events:
        assert jpgs == [], f"刪除時不該已有 jpg：{jpgs}（搬移必須在刪除之後）"
    assert (folder / "a.jpg").exists() and (folder / "b.jpg").exists()


def test_same_stem_collision_skips_folder(tmp_path):
    folder = tmp_path / "f"
    folder.mkdir()
    _img(folder / "pic.webp")
    _img(folder / "pic.png", fmt="PNG")  # 與 pic.webp 同名 -> 都輸出 pic.jpg
    trash, trashed = _make_trash()

    res = process_folder(folder, tmp_path / "tmp", trash=trash)

    assert res["status"] == "collision"
    assert (folder / "pic.webp").exists() and (folder / "pic.png").exists()
    assert trashed == []


def test_webp_and_existing_jpg_is_collision(tmp_path):
    # jpg 現在也是來源：a.webp 與 a.jpg 都要輸出 a.jpg -> 同名衝突，整夾不動
    folder = tmp_path / "f"
    folder.mkdir()
    _img(folder / "a.webp")
    Image.new("RGB", (16, 16)).save(folder / "a.jpg", "JPEG")
    trash, trashed = _make_trash()

    res = process_folder(folder, tmp_path / "tmp", trash=trash)

    assert res["status"] == "collision"
    assert (folder / "a.webp").exists() and (folder / "a.jpg").exists()
    assert trashed == []


def test_jpg_only_folder_recompresses(tmp_path):
    # 整夾都是 jpg：一律處理（依品質重新壓縮），原檔進回收桶、放回新壓的
    folder = tmp_path / "f"
    folder.mkdir()
    a = folder / "a.jpg"
    Image.new("RGB", (64, 64), (123, 222, 64)).save(a, "JPEG", quality=95)
    trash, trashed = _make_trash()

    res = process_folder(folder, tmp_path / "tmp", quality=40, trash=trash)

    assert res["status"] == "ok"
    assert set(trashed) == {a}
    assert (folder / "a.jpg").exists()


def test_list_source_images_includes_jpg_excludes_subfolders(tmp_path):
    folder = tmp_path / "f"
    folder.mkdir()
    _img(folder / "x.webp")
    Image.new("RGB", (8, 8)).save(folder / "y.jpg", "JPEG")  # jpg 也算來源
    (folder / "sub").mkdir()  # 子資料夾排除
    (folder / "z.txt").write_text("x")  # 非圖片排除
    names = [p.name for p in list_source_images(folder)]
    assert names == ["x.webp", "y.jpg"]


def test_process_folders_reports_per_image_progress(tmp_path):
    f1 = tmp_path / "f1"
    f2 = tmp_path / "f2"
    f1.mkdir()
    f2.mkdir()
    _img(f1 / "a.webp")
    _img(f1 / "b.png", fmt="PNG")
    _img(f2 / "c.webp")
    trash, _ = _make_trash()

    events = []

    def on_prog(done, total, folder, path):
        events.append((done, total, None if path is None else Path(path).name))

    process_folders([f1, f2], tmp_path / "tmp", trash=trash, on_progress=on_prog)

    assert {e[1] for e in events} == {3}          # 總數一致為 3
    assert [e[0] for e in events] == [1, 2, 3]     # 逐張遞增
    assert [e[2] for e in events] == ["a.webp", "b.png", "c.webp"]
