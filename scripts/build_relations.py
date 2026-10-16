#!/usr/bin/env python3
"""同年关系生成器（只新增不覆盖，幂等可复跑）

规则（R1.3）：同 **regime**（政权）且同 exam_year 者互为同年（relation.type = 同年）。
  · regime 从 persons.ke_ci 解析（南唐/后周/后梁/后唐/后晋/后汉/北汉/吴越/辽/金/西夏/太平天国…）；
    未命中关键词时，若 dynasty 本身即政权名（宋/唐/明/清/元/辽/金…）则取 dynasty，
    否则回退 dynasty 并记 warning —— 后者只在「五代十国」「其他」这类复合桶里才会发生。
  · 旧版分组键只有 (dynasty, exam_year)，会把「五代十国」桶里不同政权并成同科：
    王克贞（南唐保大十年）与扈载（后周广顺二年）同为 952 被误标同年；
    梁嵩（南汉白龙元年）与王彻（后唐同光三年）同为 925 同理。

输入: data/persons/*.yaml（只读，绝不修改）
输出: data/relations/<person_id>.yaml
  - 文件已存在时保留全部人工条目，同年边按 (to_id, type) 去重后追加；
  - 无新增边则不落盘，复跑结果逐字节不变（幂等）；
  - 缺 exam_year / dynasty 的人物跳过并计数；
  - 没有同年的人物不生成 relations 文件。

用法:
  python3 scripts/build_relations.py                              # 生成/补齐同年边
  python3 scripts/build_relations.py --dry-run                    # 只统计不落盘
  python3 scripts/build_relations.py --purge-tongnian --dry-run   # 先看将清掉的旧同年机器边
  python3 scripts/build_relations.py --purge-tongnian             # 清旧同年机器边后重跑（R1.3-2）
"""
import argparse
import re
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PERSONS = DATA / "persons"
RELATIONS = DATA / "relations"

REL_TYPE = "同年"
# 本脚本生成的同年边 note 形态：`<年> 年同科`。rich/manual 同年边（带 source_ids 或散体说明）不匹配，
# 故 purge 只清「本脚本产物」，人工同年边零损失。
TONGNIAN_NOTE_RE = re.compile(r"^\d{3,4} 年同科$")

# ── R1.3-1a：ke_ci 政权解析表 ──
# 只收多字、无歧义的关键词（单字如「唐」「汉」会与「南唐」「后汉」互吃，故不收）。
# 顺序 = 长词优先，避免短词吃掉长词。
REGIME_KEYWORDS: list[tuple[str, str]] = [
    ("太平天国", "太平天国"),
    ("南唐", "南唐"), ("南汉", "南汉"), ("北汉", "北汉"), ("北漢", "北汉"),
    ("后梁", "后梁"), ("後梁", "后梁"),
    ("后唐", "后唐"), ("後唐", "后唐"),
    ("后晋", "后晋"), ("後晉", "后晋"),
    ("后汉", "后汉"), ("後漢", "后汉"),
    ("后周", "后周"), ("後周", "后周"),
    ("前蜀", "前蜀"), ("后蜀", "后蜀"), ("後蜀", "后蜀"),
    ("南平", "南平"), ("荆南", "荆南"), ("荊南", "荆南"),
    ("吴越", "吴越"), ("吳越", "吴越"),
    ("北辽", "北辽"), ("北遼", "北辽"),
    ("西夏", "西夏"), ("大西", "大西"), ("渤海", "渤海"), ("大理", "大理"),
]

# dynasty 本身即政权名者：ke_ci 无关键词时按 dynasty 取政权，不算解析失败、不告警。
DIRECT_DYNASTY = {"宋", "唐", "明", "清", "元", "辽", "金", "隋", "汉", "晋",
                  "秦", "三国", "南北朝", "后汉"}
# dynasty 已是政权名、只是写法带前缀
DYNASTY_ALIAS = {"五代后汉": "后汉"}


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


def parse_regime(dynasty, ke_ci) -> tuple[str, str]:
    """从 ke_ci 解析政权。返回 (regime, source)，source ∈ {ke_ci, dynasty, fallback}。"""
    kc = ke_ci or ""
    for kw, name in REGIME_KEYWORDS:
        if kw in kc:
            return name, "ke_ci"
    dy = str(dynasty or "")
    if dy in DYNASTY_ALIAS:
        return DYNASTY_ALIAS[dy], "dynasty"
    if dy in DIRECT_DYNASTY:
        return dy, "dynasty"
    return dy, "fallback"


def build_tongnian(persons: dict):
    """按 (regime, exam_year) 分组。

    返回 ({from_id: [(to_id, note), ...]}, 跳过名单, 政权分布, 回退告警)。
    """
    groups = defaultdict(list)
    skipped: list[str] = []
    regimes: Counter = Counter()
    warns: list[tuple[str, str, str]] = []
    for pid, p in persons.items():
        dy, ey = p.get("dynasty"), p.get("exam_year")
        if not dy or ey is None:
            skipped.append(pid)
            continue
        regime, src = parse_regime(dy, p.get("ke_ci"))
        regimes[regime] += 1
        if src == "fallback":
            warns.append((pid, str(dy), str(p.get("ke_ci") or "")))
        groups[(regime, int(ey))].append(pid)

    edges = {}
    for (_regime, ey), members in groups.items():
        if len(members) < 2:
            continue
        note = f"{ey} 年同科"
        members = sorted(members)
        for pid in members:
            edges[pid] = [(t, note) for t in members if t != pid]
    return edges, skipped, regimes, warns


def purge_tongnian(dry: bool) -> tuple[list[tuple], int, int]:
    """清掉本脚本生成的旧同年机器边（note 形如 `NNN 年同科`）。

    返回 (被清清单, 涉及文件数, 删除的空文件数)。
    """
    removed: list[tuple] = []
    n_files = 0
    n_deleted = 0
    for f in sorted(RELATIONS.glob("*.yaml")):
        if f.name.startswith("_"):
            continue
        doc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        rels = doc.get("relations") or []
        keep = []
        for r in rels:
            if r.get("type") == REL_TYPE and TONGNIAN_NOTE_RE.match(str(r.get("note") or "")):
                removed.append((doc.get("from_id") or f.stem, r.get("to_id"), r.get("note")))
            else:
                keep.append(r)
        if len(keep) == len(rels):
            continue
        n_files += 1
        if dry:
            continue
        if keep:
            doc["relations"] = keep
            f.write_text(
                yaml.dump(doc, Dumper=IndentDumper, allow_unicode=True,
                          sort_keys=False, default_flow_style=False),
                encoding="utf-8",
            )
        else:
            f.unlink()
            n_deleted += 1
    return removed, n_files, n_deleted


def main() -> None:
    ap = argparse.ArgumentParser(description="同年关系生成器（政权约束版）")
    ap.add_argument("--dry-run", action="store_true", help="只统计不落盘")
    ap.add_argument("--purge-tongnian", action="store_true",
                    help="先清掉本脚本生成的旧同年边（note=`NNN 年同科`）再重跑（R1.3-2）")
    args = ap.parse_args()

    persons = load_persons()
    edges, skipped, regimes, warns = build_tongnian(persons)

    print(f"persons 载入: {len(persons)}（缺 exam_year/dynasty 跳过 {len(skipped)}）")
    print(f"解析出政权 {len(regimes)} 个："
          + "、".join(f"{k}×{v}" for k, v in regimes.most_common()))
    if warns:
        print(f"⚠ 政权解析回退 dynasty（warning）{len(warns)} 例："
              + "；".join(f"{p}({d}/{k})" for p, d, k in warns[:10]))
    else:
        print("政权解析：0 例回退（全部命中 ke_ci 关键词，或 dynasty 本身即政权名）")

    if args.purge_tongnian:
        removed, n_files, n_deleted = purge_tongnian(args.dry_run)
        verb = "将清掉" if args.dry_run else "已清掉"
        print(f"【--purge-tongnian】{verb}旧同年边 {len(removed)} 条 / {n_files} 文件"
              + (f"；删除变空文件 {n_deleted} 个" if not args.dry_run else ""))
        if args.dry_run:
            for fid, to_id, note in removed[:20]:
                print(f"    {fid:<24} -> {to_id:<24} {note}")

    # 同 (regime, ey) 且成员 ≥2 的组（解绑核对用）
    by_group = defaultdict(list)
    for pid, p in persons.items():
        dy, ey = p.get("dynasty"), p.get("exam_year")
        if not dy or ey is None:
            continue
        regime, _ = parse_regime(dy, p.get("ke_ci"))
        by_group[(regime, int(ey))].append(pid)
    multi = {k: sorted(v) for k, v in by_group.items() if len(v) >= 2}
    print(f"同年组（≥2 人）：{len(multi)} 组")
    for (regime, ey), members in sorted(multi.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        print(f"    {ey} {regime:<6} ×{len(members)}  {'、'.join(members)}")

    if args.dry_run:
        print("dry-run，未写 data/relations/")
        return

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

    print(f"同年边: 本次新增 {n_new_edge} | relations 边总数 {total}")
    print(f"文件: 新建 {n_new_file} | 追加 {n_appended}")


if __name__ == "__main__":
    main()
