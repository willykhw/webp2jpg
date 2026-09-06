"""就地改名的純邏輯（不轉檔）。

把檔案改成指定名稱（保留原副檔名），用兩階段暫存改名避免互相覆蓋。
與 UI 無關，方便單元測試。
"""

from __future__ import annotations

import uuid
from pathlib import Path


def plan_renames(files, stems) -> list[tuple[Path, Path]]:
    """回傳 [(來源, 目標)]；目標在來源同資料夾、用 stem + 來源原副檔名。"""
    return [
        (Path(f), Path(f).parent / (stem + Path(f).suffix))
        for f, stem in zip(files, stems)
    ]


def external_conflicts(plan) -> list[tuple[Path, Path]]:
    """目標已存在、且不是本批任何來源檔 → 改名會覆蓋到別的檔。回傳這些 (來源, 目標)。

    （本批來源之間的「換名/位移」由兩階段改名處理，不算外部衝突。）
    """
    sources = {Path(src).resolve() for src, _ in plan}
    conflicts = []
    for src, tgt in plan:
        tgt = Path(tgt)
        if tgt.exists() and tgt.resolve() not in sources:
            conflicts.append((Path(src), tgt))
    return conflicts


def rename_in_place(plan, on_item=None) -> tuple[list, list]:
    """兩階段就地改名。回傳 (successes[(來源,目標)], failures[(來源,錯誤字串)])。

    先把所有來源改成唯一暫存名（釋放原檔名），再改成目標名；這樣即使某個
    目標名原本被本批另一個檔佔用，也不會互相覆蓋。
    on_item(index, total, src) 每處理一個來源回呼一次（供進度顯示）。
    """
    successes: list[tuple[Path, Path]] = []
    failures: list[tuple[Path, str]] = []
    staged: list[tuple[Path, Path, Path]] = []  # (暫存, 目標, 來源)
    total = len(plan)

    # 階段 1：來源 -> 唯一暫存名
    for i, (src, tgt) in enumerate(plan, start=1):
        src, tgt = Path(src), Path(tgt)
        if on_item:
            on_item(i, total, src)
        try:
            tmp = src.parent / f".rntmp_{uuid.uuid4().hex}{src.suffix}"
            src.rename(tmp)
            staged.append((tmp, tgt, src))
        except OSError as exc:
            failures.append((src, str(exc)))

    # 階段 2：暫存名 -> 目標名
    for tmp, tgt, src in staged:
        try:
            if tgt.exists():
                # 非預期的外部佔用：不覆蓋，還原原檔名並記為失敗
                tmp.rename(src)
                failures.append((src, f"目標已存在：{tgt.name}"))
                continue
            tmp.rename(tgt)
            successes.append((src, tgt))
        except OSError as exc:
            failures.append((src, str(exc)))

    return successes, failures
