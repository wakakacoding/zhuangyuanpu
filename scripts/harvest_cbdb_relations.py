#!/usr/bin/env python3
"""从 CBDB 批量收割状元间及状元与名人的社会关系。

数据源: vendor/cbdb/cbdb_20261010.sqlite3（只读）
锚点:   data/index/zhuangyuan_index.yaml 中 confirmed 且有 cbdb_id 的状元
输出:   data/relations/{slug}.yaml（幂等追加，只新增不覆盖）

规则:
- 查 ASSOC_DATA 与 KIN_DATA 双向关系（我方为 c_personid 或 c_assoc_id/c_kin_id 均可）
- 对方是状元 → to_id 用其 slug；非状元 → to_id 记 cbdb:<c_personid>（外部标记），note 注姓名
- 类型映射为中文枚举: 同年/师生/父子/兄弟/翁婿/同僚/政敌/友人/其他
  （无法归类的标「其他」，note 保留 CBDB 原始类型中文描述）
- note 写明关系性质与年份（有 c_assoc_first_year 时）
- 幂等: 与现有边（含反向）按 (from,to,type) 去重，同人同类型不重复

用法: /Users/mba/.workbuddy/binaries/python/envs/default/bin/python scripts/harvest_cbdb_relations.py [--dry-run]
"""
import argparse
import sqlite3
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "vendor" / "cbdb" / "cbdb_20261010.sqlite3"
INDEX = ROOT / "data" / "index" / "zhuangyuan_index.yaml"
REL_DIR = ROOT / "data" / "relations"
PERSON_DIR = ROOT / "data" / "persons"

# ---------- 类型映射 ----------

def map_kin(kin_chn: str) -> str:
    """KINSHIP_CODES.c_kinrel_chn（如「父」「兄弟」「岳父」）-> 中文枚举。"""
    t = kin_chn or ""
    if any(k in t for k in ("岳父", "岳翁", "妻父", "婿", "女婿", "翁")):
        return "翁婿"
    if any(k in t for k in ("兄", "弟", "姊", "妹", "姐妹", "兄弟")):
        return "兄弟"
    if any(k in t for k in ("父", "子", "祖", "孙", "孫", "直系")):
        return "父子"
    return "其他"


def map_assoc(desc_chn: str, type_chn: str) -> str:
    """ASSOC_CODES.c_assoc_desc_chn + ASSOC_TYPES.c_assoc_type_desc_chn -> 中文枚举。"""
    t = f"{desc_chn or ''} {type_chn or ''}"
    if any(k in t for k in ("同年", "同科", "同榜")):
        return "同年"
    if any(k in t for k in ("门生", "門生", "门人", "門人", "弟子", "受业", "受業",
                            "学生", "學生", "之师", "之師", "为师", "為師", "師生", "师生")):
        return "师生"
    if any(k in t for k in ("弹劾", "彈劾", "攻讦", "攻訐", "政敌", "政敵", "排挤", "排擠",
                            "陷害", "劾", "讦")):
        return "政敌"
    if any(k in t for k in ("同僚", "同事", "同官", "幕僚", "属下", "屬下", "上司", "同曹")):
        return "同僚"
    if any(k in t for k in ("友", "游", "交", "识", "識", "知", "唱和", "唱酬")):
        return "友人"
    return "其他"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只统计不写文件")
    args = ap.parse_args()

    # ---------- 锚点 ----------
    index = yaml.safe_load(INDEX.read_text(encoding="utf-8"))
    anchors = {}  # cbdb_id -> {"slug":..., "name":...}
    for e in index:
        if e.get("status") == "confirmed" and e.get("cbdb_id") is not None:
            anchors[int(e["cbdb_id"])] = {"slug": e["slug"], "name": e["name"]}
    print(f"锚点状元（confirmed + cbdb_id）: {len(anchors)}")
    if not anchors:
        print("无锚点，退出")
        return 1

    # ---------- slug 解析：index slug 与 persons id 可能不一致（如 wen_tian_xiang vs wen_tianxiang）
    person_ids = {p.stem for p in PERSON_DIR.glob("*.yaml") if not p.name.startswith("_")}
    name_year_to_pid = {}
    for p in PERSON_DIR.glob("*.yaml"):
        if p.name.startswith("_"):
            continue
        pd = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        name_year_to_pid[(pd.get("name"), pd.get("exam_year"))] = p.stem

    resolved = {}  # cbdb_id -> person slug（None = 无法解析）
    for cid, info in anchors.items():
        slug = info["slug"]
        if slug in person_ids:
            resolved[cid] = slug
        else:
            hit = None
            for e in index:
                if e["slug"] == slug:
                    hit = name_year_to_pid.get((e["name"], e.get("exam_year")))
                    break
            resolved[cid] = hit
    unresolved = [anchors[c]["name"] for c, s in resolved.items() if not s]
    print(f"slug 解析: {len(resolved) - len(unresolved)}/{len(resolved)} 命中 persons"
          + (f"，未解析: {unresolved}" if unresolved else ""))

    # ---------- 现有边（幂等去重基线） ----------
    existing = set()  # (from_slug, to_id, type)，同时登记反向
    rel_docs = {}
    for f in sorted(REL_DIR.glob("*.yaml")):
        if f.name.startswith("_"):
            continue
        doc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        rel_docs[f.stem] = doc
        for r in doc.get("relations") or []:
            existing.add((doc.get("from_id"), r.get("to_id"), r.get("type")))

    def seen(a: str, b: str, tp: str) -> bool:
        return (a, b, tp) in existing or (b, a, tp) in existing

    def mark(a: str, b: str, tp: str) -> None:
        existing.add((a, b, tp))
        existing.add((b, a, tp))

    # ---------- CBDB ----------
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    ids = ",".join(str(i) for i in anchors)

    assoc_codes = {r["c_assoc_code"]: (r["c_assoc_desc_chn"] or "")
                   for r in conn.execute("SELECT c_assoc_code, c_assoc_desc_chn FROM ASSOC_CODES")}
    kin_codes = {r["c_kincode"]: (r["c_kinrel_chn"] or "")
                 for r in conn.execute("SELECT c_kincode, c_kinrel_chn FROM KINSHIP_CODES")}

    def name_of(pid: int) -> str:
        if pid in anchors:
            return anchors[pid]["name"]
        row = conn.execute("SELECT c_name_chn FROM BIOG_MAIN WHERE c_personid=?", (pid,)).fetchone()
        return row["c_name_chn"] if row and row["c_name_chn"] else f"CBDB#{pid}"

    new_edges = {}  # from_slug -> list of relation dicts
    type_counter = Counter()
    skipped_dup = 0
    skipped_from = 0

    def add_edge(from_cbdb: int, to_cbdb: int, tp: str, note: str) -> None:
        nonlocal skipped_dup, skipped_from
        a = resolved.get(from_cbdb)
        if not a:  # from 无 persons 档案，无法建关系文件
            skipped_from += 1
            return
        if to_cbdb in anchors and resolved.get(to_cbdb):
            b = resolved[to_cbdb]
        elif to_cbdb in anchors:  # 状元但未建档 -> 外部标记
            b = f"cbdb:{to_cbdb}"
            note = note.replace("（CBDB）", f"：{anchors[to_cbdb]['name']}（状元，未建档）")
        else:
            b = f"cbdb:{to_cbdb}"
        if seen(a, b, tp):
            skipped_dup += 1
            return
        mark(a, b, tp)
        new_edges.setdefault(a, []).append({"to_id": b, "type": tp, "note": note})
        type_counter[tp] += 1

    # 我方为 c_personid 的社交关系
    assoc_rows = conn.execute(
        f"SELECT c_personid, c_assoc_id, c_assoc_code, c_assoc_first_year "
        f"FROM ASSOC_DATA WHERE c_personid IN ({ids}) OR c_assoc_id IN ({ids})").fetchall()
    for r in assoc_rows:
        p, q = r["c_personid"], r["c_assoc_id"]
        if p not in anchors and q not in anchors:
            continue
        code = r["c_assoc_code"]
        desc = (assoc_codes.get(code, "") or "").strip()
        if desc in ("", "未詳", "未详"):  # 无信息量，跳过
            continue
        tp = map_assoc(desc, "")
        year = r["c_assoc_first_year"]
        if year is not None and year <= 0:  # CBDB 用 -9999 表示未知
            year = None
        if p in anchors:
            frm, other = p, q
        else:
            frm, other = q, p
        # 双方都是状元时只收一条（按 c_personid -> c_assoc_id 方向）
        if p in anchors and q in anchors and frm != p:
            continue
        note = f"{desc or '社会关系'}（CBDB）"
        if other not in anchors:
            note = f"{desc or '社会关系'}：{name_of(other)}（CBDB 外部人物）"
        if year:
            note += f"，始年 {year}"
        add_edge(frm, other, tp, note)

    # 亲缘关系
    kin_rows = conn.execute(
        f"SELECT c_personid, c_kin_id, c_kin_code FROM KIN_DATA "
        f"WHERE c_personid IN ({ids}) OR c_kin_id IN ({ids})").fetchall()
    for r in kin_rows:
        p, q = r["c_personid"], r["c_kin_id"]
        if p not in anchors and q not in anchors:
            continue
        kc = r["c_kin_code"]
        kchn = (kin_codes.get(str(kc), "") or kin_codes.get(kc, "") or "").strip()
        if kchn in ("", "未詳", "未详"):
            continue
        tp = map_kin(kchn)
        if p in anchors:
            frm, other = p, q
        else:
            frm, other = q, p
        if p in anchors and q in anchors and frm != p:
            continue
        if other in anchors:
            note = f"{kchn or kc or '亲缘关系'}（CBDB）"
        else:
            note = f"{kchn or kc or '亲缘关系'}：{name_of(other)}（CBDB 外部人物）"
        add_edge(frm, other, tp, note)

    total_new = sum(len(v) for v in new_edges.values())
    print(f"新增边: {total_new}（去重跳过 {skipped_dup} 条，from 无档案跳过 {skipped_from} 条）")
    print("类型分布:", dict(type_counter.most_common()))

    if args.dry_run:
        print("dry-run，未写文件")
        return 0

    # ---------- 写入（幂等追加） ----------
    n_files = 0
    for slug, rels in new_edges.items():
        path = REL_DIR / f"{slug}.yaml"
        doc = rel_docs.get(slug)
        if doc is None:
            doc = {"from_id": slug, "relations": []}
        doc.setdefault("relations", []).extend(rels)
        text = yaml.safe_dump(doc, allow_unicode=True, sort_keys=False)
        path.write_text(text, encoding="utf-8")
        n_files += 1
    print(f"写入 {n_files} 个关系文件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
