#!/usr/bin/env python3
"""同年关系生成器（只新增不覆盖，幂等可复跑）

规则: 同 dynasty 且同 exam_year 者互为同年（relation.type = 同年）。
输入: data/persons/*.yaml（只读，绝不修改）
输出: data/relations/<person_id>.yaml
  - 文件已存在时保留全部人工条目，同年边按 (to_id, type) 去重后追加；
  - 无新增边则不落盘，复跑结果逐字节不变（幂等）；
  - 缺 exam_year / dynasty 的人物跳过并计数；
  - 无为避免空文件噪音，没有同年的人物不生成 relations 文件。

用法: python3 scripts/build_relations.py
"""
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PERSONS = DATA / "persons"
RELATIONS = DATA / "relations"

REL_TYPE = "同年"


class IndentDumper(yaml.Dumper):
    """序列短横线缩进两格，与 data/ 下既有手写 YAML 风格一致。"""

    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)


def load_persons() -> dict:
    """读取全部 person 速览卡，返回 {id: card}。"""
    out = {}
    for f in sorted(PERSONS.glob("*.yaml")):
        if f.name.startswith("_"):  # 模板跳过
            continue
        p = yaml.safe_load(f.read_text(encoding="utf-8"))
        if isinstance(p, dict) and p.get("id"):
            out[p["id"]] = p
    return out


def build_tongnian(persons: dict):
    """按 (dynasty, exam_year) 分组，返回 ({from_id: [(to_id, note), ...]}, 跳过名单)。"""
    groups = defaultdict(list)
    skipped = []
    for pid, p in persons.items():
        dy, ey = p.get("dynasty"), p.get("exam_year")
        if not dy or ey is None:
            skipped.append(pid)
            continue
        groups[(str(dy), int(ey))].append(pid)

    edges = {}
    for (_dy, ey), members in groups.items():
        if len(members) < 2:
            continue
        note = f"{ey} 年同科"
        members = sorted(members)
        for pid in members:
            edges[pid] = [(t, note) for t in members if t != pid]
    return edges, skipped


def main() -> None:
    persons = load_persons()
    edges, skipped = build_tongnian(persons)

    if not RELATIONS.exists():
        RELATIONS.mkdir(parents=True)
    n_new_file = n_appended = n_new_edge = 0
    for fid in sorted(edges):
        path = RELATIONS / f"{fid}.yaml"
        existed = path.exists()
        doc = {"from_id": fid, "relations": []}
        if existed:
            old = yaml.safe_load(path.read_text(encoding="utf-8"))
            if isinstance(old, dict):
                doc = old  # 保留人工条目与既有字段
            if not isinstance(doc.get("relations"), list):
                doc["relations"] = []

        have = {(r.get("to_id"), r.get("type"))
                for r in doc["relations"] if isinstance(r, dict)}
        todo = [{"to_id": t, "type": REL_TYPE, "note": note}
                for t, note in edges[fid] if (t, REL_TYPE) not in have]
        if existed and not todo:
            continue  # 无变化不落盘，保证幂等

        doc["relations"].extend(todo)
        path.write_text(
            yaml.dump(doc, Dumper=IndentDumper, allow_unicode=True,
                      sort_keys=False, default_flow_style=False),
            encoding="utf-8",
        )
        n_new_edge += len(todo)
        if existed:
            n_appended += 1
        else:
            n_new_file += 1

    total = 0
    for f in RELATIONS.glob("*.yaml"):
        if f.name.startswith("_"):
            continue
        d = yaml.safe_load(f.read_text(encoding="utf-8"))
        total += len((d or {}).get("relations") or [])

    print(f"persons 载入: {len(persons)}（缺 exam_year/dynasty 跳过 {len(skipped)}）")
    print(f"同年边: 本次新增 {n_new_edge} | relations 边总数 {total}")
    print(f"文件: 新建 {n_new_file} | 追加 {n_appended}")


if __name__ == "__main__":
    main()
