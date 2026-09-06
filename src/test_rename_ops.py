"""rename_ops 的單元測試。

重點：
- 目標保留原副檔名、在同資料夾
- 兩階段改名能處理「位移」而不互相覆蓋（[1,2,3] -> [2,3,4]）
- 外部佔用（目標是不在本批的既有檔）會被偵測，且改名時不覆蓋它
"""

from pathlib import Path

from rename_ops import external_conflicts, plan_renames, rename_in_place


def _touch(p: Path, text="x"):
    p.write_text(text)
    return p


def test_plan_keeps_extension_and_folder(tmp_path):
    a = tmp_path / "photo.PNG"
    b = tmp_path / "sub"
    b.mkdir()
    c = b / "img.jpeg"
    plan = plan_renames([a, c], ["1", "2"])
    assert plan == [(a, tmp_path / "1.PNG"), (c, b / "2.jpeg")]


def test_rename_basic(tmp_path):
    a = _touch(tmp_path / "cat.png")
    b = _touch(tmp_path / "dog.webp")
    plan = plan_renames([a, b], ["1", "2"])
    ok, fail = rename_in_place(plan)
    assert not fail
    assert (tmp_path / "1.png").exists() and (tmp_path / "2.webp").exists()
    assert not a.exists() and not b.exists()
    assert [s for s, _ in ok] == [a, b]


def test_two_phase_shift_no_data_loss(tmp_path):
    # [1,2,3].png 往後位移成 [2,3,4].png，內容不能互相覆蓋
    for n, content in [("1", "one"), ("2", "two"), ("3", "three")]:
        _touch(tmp_path / f"{n}.png", content)
    files = [tmp_path / f"{n}.png" for n in ("1", "2", "3")]
    plan = plan_renames(files, ["2", "3", "4"])
    ok, fail = rename_in_place(plan)
    assert not fail
    assert (tmp_path / "2.png").read_text() == "one"
    assert (tmp_path / "3.png").read_text() == "two"
    assert (tmp_path / "4.png").read_text() == "three"


def test_external_conflict_detected(tmp_path):
    a = _touch(tmp_path / "cat.png")
    _touch(tmp_path / "1.png", "unrelated")  # 既有、非本批 -> 佔用了目標名
    plan = plan_renames([a], ["1"])
    conflicts = external_conflicts(plan)
    assert conflicts == [(a, tmp_path / "1.png")]


def test_source_held_target_is_not_external(tmp_path):
    # 目標名被「本批另一個來源」佔用，不算外部衝突（由兩階段處理）
    a = _touch(tmp_path / "1.png")
    b = _touch(tmp_path / "2.png")
    plan = plan_renames([a, b], ["2", "3"])  # a 的目標 2.png 是 b（本批）
    assert external_conflicts(plan) == []


def test_rename_does_not_overwrite_unexpected_existing(tmp_path):
    # 防禦：若目標意外已存在（外部），不覆蓋、還原原檔、記為失敗
    a = _touch(tmp_path / "cat.png", "cat")
    _touch(tmp_path / "1.png", "keep")
    plan = plan_renames([a], ["1"])
    ok, fail = rename_in_place(plan)  # 沒先過濾外部衝突就執行
    assert ok == []
    assert len(fail) == 1
    assert (tmp_path / "1.png").read_text() == "keep"  # 未被覆蓋
    assert a.exists() and a.read_text() == "cat"       # 原檔還原
