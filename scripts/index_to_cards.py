#!/usr/bin/env python3
"""index_to_cards.py —— 全量索引 → 极简速览卡批量生成器（Phase 1 任务3 / Phase 2 WP1 首交付）

输入：data/index/zhuangyuan_index.yaml（build_index.py 产出，597 人）
输出：data/persons/<slug>.yaml 极简卡（已存在的人物文件一律跳过——精修卡优先）

状态映射：
  confirmed → 普通极简卡（CBDB 字段带入：字号/生卒/籍贯）
  suspect   → 卡 + tags:[待核]（朝代互证不足，页面与检索可识别）
  missing   → 卡 + tags:[待整理]（仅名录三字段，合法空值）

注（R1.4-5）：「史料阙如」是须经人工查证认定（verified_absent: true）才能用的**历史结论**，
不得由脚本按 status 自动贴；未整理的缺载一律标「待整理」——整理进度不冒充史料结论。

用法：
  python3 scripts/index_to_cards.py          # 生成
  python3 scripts/index_to_cards.py --dry    # 只统计不写盘
"""
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "data" / "index" / "zhuangyuan_index.yaml"
PERSONS = ROOT / "data" / "persons"

NATIVE_RE = re.compile(r"^(?P<hist>[^（(]+)[（(]今(?P<modern>[^）)]+)[）)]")


def split_native(raw: str | None) -> tuple[str | None, str | None]:
    """『贝州武城（今山东武城）』→ (贝州武城, 山东武城)"""
    if not raw:
        return None, None
    m = NATIVE_RE.match(raw.strip())
    if m:
        return m.group("hist").strip(), m.group("modern").strip()
    return raw.strip(), None


def main() -> None:
    dry = "--dry" in sys.argv
    entries = yaml.safe_load(INDEX.read_text(encoding="utf-8"))

    # 已有人物（精修卡 + 种子卡）按姓名登记，索引重条一律跳过
    existing_names: dict[str, str] = {}
    used_ids: set[str] = set()
    for f in PERSONS.glob("*.yaml"):
        if f.name.startswith("_"):
            continue
        d = yaml.safe_load(f.read_text(encoding="utf-8"))
        existing_names[d["name"]] = d["id"]
        used_ids.add(d["id"])

    created = {"confirmed": 0, "suspect": 0, "missing": 0}
    skipped: list[str] = []
    files: list[tuple[str, str]] = []

    for e in entries:
        name = e["name"]
        if name in existing_names:
            skipped.append(f"{name}（已有卡 {existing_names[name]}）")
            continue

        slug = e.get("slug") or name
        while slug in used_ids:  # 同名防撞
            slug = slug + "_2" if not slug.endswith("_2") else slug + "3"
        used_ids.add(slug)

        hist, modern = split_native(e.get("native_cbdb") or e.get("native_roster"))
        tags = {"confirmed": [], "suspect": ["待核"], "missing": ["待整理"]}[e["status"]]

        card: dict = {
            "id": slug,
            "name": name,
            "zi": e.get("zi"),
            "hao": e.get("hao"),
            "birth_year": e.get("birth_year"),
            "death_year": e.get("death_year"),
            "native_hist": hist,
            "native_modern": modern,
            "dynasty": e["dynasty"],
            "exam_year": e.get("exam_year"),
            "ganzhi": e.get("ganzhi"),
            "ke_ci": e.get("ke_ci"),
            "rank_detail": "一甲第一名（状元）",
            "bio_short": None,
            "tags": tags,
            "status": "published",
        }
        header = (
            f"# {name} —— 极简卡（index_to_cards.py 自动生成，勿手改字段结构）\n"
            f"# 来源：{INDEX.name} {e['index_id']} | 比对状态：{e['status']}"
            + (f"（{e.get('evidence')}）" if e.get("evidence") else "")
            + (f" | 备考：{e.get('note')}" if e.get("note") else "")
            + "\n"
        )
        body = yaml.safe_dump(card, allow_unicode=True, sort_keys=False, width=100)
        files.append((slug, header + body))
        created[e["status"]] += 1

    if not dry:
        for slug, text in files:
            (PERSONS / f"{slug}.yaml").write_text(text, encoding="utf-8")

    print(f"索引条目：{len(entries)}")
    print(f"跳过已有卡：{len(skipped)}")
    print(f"{'[dry] 将生成' if dry else '已生成'}：{len(files)} 张极简卡")
    print(f"  confirmed {created['confirmed']} / suspect {created['suspect']} / missing {created['missing']}")
    if skipped:
        print("跳过明细：" + "、".join(skipped[:20]) + ("…" if len(skipped) > 20 else ""))


if __name__ == "__main__":
    main()
