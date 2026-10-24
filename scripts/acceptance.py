#!/usr/bin/env python3
"""内容验收登记统计（data/acceptance.yaml 的读侧工具）。

区分两个口径：
  - 结构覆盖 = 有 data/events/<id>.yaml 的人物数（fullProfileIds 同口径）
  - 内容验收 = data/acceptance.yaml 中登记通过验收的人数（人工批次验收）

用法：
  python scripts/acceptance.py            # 打印两口径对比
  python scripts/acceptance.py --json     # 机器可读输出
  python scripts/acceptance.py --check    # 校验登记一致性（id 存在、无重复、
                                          # 结构覆盖是内容验收的超集），非零退出即不一致
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def load_accepted() -> list[dict]:
    doc = yaml.safe_load((DATA / "acceptance.yaml").read_text(encoding="utf-8"))
    return doc.get("accepted") or []


def structural_ids() -> set[str]:
    ev = DATA / "events"
    if not ev.exists():
        return set()
    return {f.stem for f in ev.glob("*.yaml") if not f.name.startswith("_")}


def person_ids() -> set[str]:
    p = DATA / "persons"
    return {f.stem for f in p.glob("*.yaml") if not f.name.startswith("_")}


def stats() -> dict:
    acc = load_accepted()
    ids = [a["id"] for a in acc]
    struct = structural_ids()
    persons = person_ids()
    return {
        "accepted": len(ids),
        "accepted_unique": len(set(ids)),
        "structural": len(struct),
        "pending_review": len(struct - set(ids)),  # 有档案未验收
        "by_batch": _count_by(acc, "batch"),
        "by_four_set": _count_by(acc, "four_set"),
        "not_in_persons": sorted(set(ids) - persons),
        "not_structural": sorted(set(ids) - struct),  # 登记了却没有 events 文件
        "duplicates": sorted({i for i in ids if ids.count(i) > 1}),
    }


def _count_by(items: list[dict], key: str) -> dict:
    out: dict[str, int] = {}
    for it in items:
        k = str(it.get(key))
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items()))


def check() -> int:
    s = stats()
    errs: list[str] = []
    if s["duplicates"]:
        errs.append(f"重复登记: {s['duplicates']}")
    if s["not_in_persons"]:
        errs.append(f"登记的人物卡不存在: {s['not_in_persons']}")
    if s["not_structural"]:
        errs.append(f"登记了验收但没有 events 文件: {s['not_structural']}")
    for e in errs:
        print(f"[错误] {e}", file=sys.stderr)
    if errs:
        return 1
    print("acceptance.yaml 一致性检查通过")
    return 0


def main() -> int:
    if "--check" in sys.argv:
        return check()
    s = stats()
    if "--json" in sys.argv:
        print(json.dumps(s, ensure_ascii=False, indent=2))
        return 0
    print(f"内容验收（登记）: {s['accepted']} 人")
    print(f"结构覆盖（events 文件）: {s['structural']} 人")
    print(f"有档案、待验收: {s['pending_review']} 人")
    print("按批次:")
    for k, v in s["by_batch"].items():
        print(f"  {k}: {v}")
    print("四件套状态:", s["by_four_set"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
