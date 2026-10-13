#!/usr/bin/env python3
"""600 人索引构建器（Phase 1 核心工具）

名录 × CBDB 交叉比对：
  输入：data/index/reference/roster_*.yaml   —— 权威名录（题名碑录系/登科记考系，见各文件头注释）
        vendor/cbdb/cbdb_20261010.sqlite3    —— CBDB 候选池
  输出：data/index/zhuangyuan_index.yaml     —— 结构化索引（主交付物）
        data/index/zhuangyuan_index.csv      —— 扁平表（表格查看用）
        data/index/index_report.md           —— 比对报告（统计 + 未匹配清单 + 补核方案）

比对规则（姓名繁体 + 登科年 ±2 + 朝代 三维）：
  confirmed 已确认：CBDB 唯一候选，且入仕年 ±2 内吻合；若 CBDB 另有「状元」名次标记则记 evidence=rank1
  suspect  存疑  ：多名同姓同名人无法消歧 / 年份冲突 >2 年 / CBDB 状元标记年份与名录冲突 / 名录年分阙如
  missing  缺失  ：CBDB 无此人记录（唐宋辽金段属预期，转《登科记考》/碑录人工补核）

反向校验：CBDB 状元标记条目未被名录覆盖者 → 报告附录「CBDB 多出条目」，防名录漏收。

用法：
  /Users/mba/.workbuddy/binaries/python/envs/default/bin/python scripts/build_index.py
"""
import csv
import sqlite3
import sys
from pathlib import Path

import yaml
from opencc import OpenCC
from pypinyin import lazy_pinyin

sys.path.insert(0, str(Path(__file__).resolve().parent))
from era import ganzhi_of  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "vendor" / "cbdb" / "cbdb_20261010.sqlite3"
REF = ROOT / "data" / "index" / "reference"
OUT = ROOT / "data" / "index"

# CBDB 中「殿试第一」的名次标记写法（R10 验证期摸清的全部变体）
RANK1 = {"第1甲第1名", "第一甲第一名", "第一甲第一人", "1甲1名", "1甲第1名",
         "第一甲第第一名", "一甲第一名", "進士第一", "第一甲第一人 "}

DYNASTY_ORDER = ["唐", "五代十国", "宋", "辽", "金", "元", "明", "清", "其他"]
# CBDB 朝代标注 ↔ 名录朝代（政权交界期人物 CBDB 标注宽泛，做宽映射；年分证据优先于朝代）
DY_MAP = {
    "唐": {"唐", "隋", "五代"},
    "五代十国": {"五代", "後梁", "後唐", "後晉", "後漢", "後周", "南唐", "南漢", "北漢",
                 "前蜀", "後蜀", "吳越", "閩國", "楚(馬)", "荊南", "吳", "吳(楊)", "宋"},
    "宋": {"宋", "五代", "遼", "金"},
    "辽": {"遼", "金"},
    "金": {"金", "遼", "元", "宋"},
    "元": {"元", "金", "宋", "明"},
    "明": {"明", "元", "清"},
    "清": {"清", "中華民國", "明"},
    "其他": set(),  # 特例政权不过滤
}

s2t = OpenCC("s2t")

# 人名用字保护：OpenCC 按词汇转换会过度泛化（于→於、余→餘、范→範…），人名须保留原字形
S2T_NAME = {"于": "于", "余": "余", "范": "范", "栗": "栗", "梁": "梁", "咸": "咸",
            "岳": "岳", "启": "啟", "咨": "咨", "钟": "鍾", "朴": "朴", "沈": "沈"}
# CBDB 异体字互换（同一字的不同刻本写法，双向各产一变体）
VARIANT_SWAPS = {"敘": ["敍"], "皋": ["皐", "臯"], "鳴": ["嗚"], "勳": ["勛"],
                 "寬": ["寛"], "兌": ["兊"], "棲": ["栖"], "慤": ["愨"], "升": ["昇"]}
# 已知人物别名（CBDB 立目名 ≠ 名录通行名，人工核实后登记）
NAME_ALIAS = {"马愉": ["馬忄俞"], "王一夔": ["謝一夔"], "周澍": ["周雨樹"],
              "徐郙": ["金郙"], "孙毓溎": ["孫毓桂"], "孙如仅": ["孫如瑾"],
              "赵以炯": ["趙以烱"], "张建勋": ["張建瀛"], "申时行": ["徐時行"],
              "张元忭": ["張元抃"]}


def name_variants(name):
    """生成该名的全部候选繁体写法：OpenCC 转换 + 人名用字保护 + 异体互换 + 登记别名。"""
    base = s2t.convert(name)
    protected = "".join(S2T_NAME.get(c, t) for c, t in zip(name, base))
    variants = [protected] if protected != base else []
    variants.append(base)
    out = list(variants)
    for v in variants:
        for ch, repls in VARIANT_SWAPS.items():
            if ch in v:
                out += [v.replace(ch, r) for r in repls]
    out += NAME_ALIAS.get(name, [])
    return list(dict.fromkeys(out))


def person_brief(con, pid):
    """取 CBDB 人物关键字段：生卒/朝代/籍贯(籍)/字号/全部入仕记录。"""
    row = con.execute(
        "SELECT b.c_name_chn, b.c_birthyear, b.c_deathyear, d.c_dynasty_chn "
        "FROM BIOG_MAIN b LEFT JOIN DYNASTIES d ON b.c_dy = d.c_dy "
        "WHERE b.c_personid = ?", (pid,)).fetchone()
    if not row:
        return None
    name_tw, by, dy, dyn = row
    place = con.execute(
        "SELECT group_concat(a.c_name_chn, ' / ') FROM BIOG_ADDR_DATA ba "
        "JOIN ADDR_CODES a ON ba.c_addr_id = a.c_addr_id "
        "WHERE ba.c_personid = ? AND ba.c_addr_type = 1", (pid,)).fetchone()[0]
    alts = con.execute(
        "SELECT c_alt_name_type_code, c_alt_name_chn FROM ALTNAME_DATA WHERE c_personid = ?", (pid,)).fetchall()
    zi = "；".join(n for t, n in alts if t == 4) or None   # 4=字
    hao = "；".join(n for t, n in alts if t == 5) or None  # 5=室名、別號
    entries = con.execute(
        "SELECT e.c_year, e.c_exam_rank FROM ENTRY_DATA e WHERE e.c_personid = ?", (pid,)).fetchall()
    return {"pid": pid, "name_tw": name_tw, "birth": by, "death": dy, "dynasty": dyn,
            "native": place, "zi": zi, "hao": hao,
            "entries": [(y, r) for y, r in entries if y]}


def has_rank1(brief):
    return any((r or "").strip() in RANK1 for _, r in brief["entries"])


def rank1_years(brief):
    return [y for y, r in brief["entries"] if (r or "").strip() in RANK1]


def match_one(con, name, year, dynasty):
    """比对优先级：年分 ±2（最强证据）→ 朝代相容（次强）→ 唯一性。
    返回 (status, evidence, brief|None, candidates_count)。"""
    variants = name_variants(name)
    name_tw = variants[0]
    ids, seen = [], set()
    for v in variants:
        for (pid,) in con.execute(
                "SELECT c_personid FROM BIOG_MAIN WHERE c_name_chn = ?", (v,)).fetchall():
            if pid not in seen:
                seen.add(pid)
                ids.append(pid)
    if not ids:
        # 别名兜底：CBDB 以别名/原名立目（如 王一夔→謝一夔）
        for v in variants:
            for (pid,) in con.execute(
                    "SELECT DISTINCT c_personid FROM ALTNAME_DATA WHERE c_alt_name_chn = ?", (v,)).fetchall():
                if pid not in seen:
                    seen.add(pid)
                    ids.append(pid)
    if not ids and len(name_tw) >= 2:
        # 满蒙姓名兜底：碑录多略姓氏（麻勒吉 ← 瓜爾佳麻勒吉）
        for (pid,) in con.execute(
                "SELECT c_personid FROM BIOG_MAIN WHERE c_name_chn LIKE ? AND length(c_name_chn) <= ?",
                ("%" + name_tw, len(name_tw) + 4)).fetchall():
            if pid not in seen:
                seen.add(pid)
                ids.append(pid)
    if not ids:
        return "missing", "CBDB 无记录", None, 0
    briefs = [b for b in (person_brief(con, i) for i in ids) if b]
    dy_ok = DY_MAP.get(dynasty, set())

    if year is not None:
        # 第一优先：年分 ±2（不限朝代标签，年分是硬证据）
        year_hits = [b for b in briefs if any(abs(y - year) <= 2 for y, _ in b["entries"])]
        if len(year_hits) == 1:
            b = year_hits[0]
            r1y = rank1_years(b)
            if r1y and not any(abs(y - year) <= 2 for y in r1y):
                return "suspect", f"CBDB 状元标记年 {r1y} 与名录 {year} 冲突", b, len(ids)
            ev = "rank1" if has_rank1(b) else "name+year"
            if dy_ok and b["dynasty"] not in dy_ok:
                ev += f"（朝代标注 {b['dynasty']} 异）"
            return "confirmed", ev, b, len(ids)
        if len(year_hits) > 1:
            # CBDB 重条（同一人多条目）常见：优先持状元名次标记者
            r1 = [b for b in year_hits if has_rank1(b)]
            if len(r1) == 1:
                return "confirmed", "rank1（同年重条，取标记者）", r1[0], len(ids)
            dy_hits = [b for b in year_hits if b["dynasty"] in dy_ok]
            if len(dy_hits) == 1:
                b = dy_hits[0]
                return "confirmed", "rank1" if has_rank1(b) else "name+year+dynasty", b, len(ids)
            pids = [b["pid"] for b in year_hits]
            return "suspect", f"同年同名多条 {pids}（疑似 CBDB 重条，待人工并合）", None, len(ids)

    # 第二优先：朝代相容收窄
    pool = [b for b in briefs if not dy_ok or b["dynasty"] in dy_ok]
    if not pool:
        dyns = sorted({b["dynasty"] or "?" for b in briefs})
        return "missing", f"仅见异代同名者（{'/'.join(dyns)}），按缺失计", None, len(ids)
    if year is None:  # 名录年分阙如（金代较多）
        if len(pool) == 1:
            return "suspect", "名录年分阙如，朝代内唯一候选待人工核年", pool[0], len(ids)
        return "suspect", f"名录年分阙如且朝代内同名 {len(pool)} 人", None, len(ids)
    if len(pool) == 1:
        b = pool[0]
        ey = [y for y, _ in b["entries"]]
        if not ey:
            return "suspect", "朝代互证唯一候选，CBDB 未载科年（待碑录/登科记考补）", b, len(ids)
        return "suspect", f"年份冲突：名录 {year} vs CBDB 入仕年 {ey}", b, len(ids)
    return "suspect", f"朝代内同名 {len(pool)} 人且年分均无命中", None, len(ids)


def main():
    con = sqlite3.connect(DB)
    # 名录加载
    roster = []
    for f in sorted(REF.glob("roster_*.yaml")):
        doc = yaml.safe_load(f.read_text(encoding="utf-8"))
        for e in doc["entries"]:
            e["dynasty"] = doc["dynasty"]
            roster.append(e)

    results, anchors_used = [], set()
    for i, e in enumerate(roster, 1):
        status, evidence, b, ncand = match_one(con, e["name"], e.get("year"), e["dynasty"])
        item = {
            "index_id": "",  # 排序后回填
            "name": e["name"], "name_tw": name_variants(e["name"])[0],
            "dynasty": e["dynasty"], "exam_year": e.get("year"),
            "ganzhi": ganzhi_of(e["year"]) if e.get("year") else None,
            "ke_ci": e.get("ke"), "native_roster": e.get("native"),
            "zi": b and b["zi"], "hao": b and b["hao"],
            "birth_year": b and b["birth"], "death_year": b and b["death"],
            "native_cbdb": b and b["native"], "cbdb_dynasty": b and b["dynasty"],
            "cbdb_id": b and b["pid"],
            "status": status, "evidence": evidence,
            "note": e.get("note"),
        }
        if b:
            anchors_used.add(str(b["pid"]))
        results.append(item)

    # 排序：朝代序 → 年分（None 排末）→ 名录原序
    order = {d: i for i, d in enumerate(DYNASTY_ORDER)}
    results.sort(key=lambda x: (order[x["dynasty"]], x["exam_year"] or 9999))
    seen_slugs = {}
    for i, r in enumerate(results, 1):
        r["index_id"] = f"z{i:04d}"
        base = "_".join(lazy_pinyin(r["name"]))
        seen_slugs[base] = seen_slugs.get(base, 0) + 1
        r["slug"] = base if seen_slugs[base] == 1 else f"{base}_{seen_slugs[base]}"

    # 反向校验：CBDB 状元锚点未被名录覆盖者
    anchors = [l.split("|") for l in (REF / "cbdb_rank1_anchor.tsv").read_text().splitlines() if l.strip()]
    extra = [{"name_tw": a[0], "year": a[1], "dynasty": a[2], "cbdb_id": a[3]}
             for a in anchors if a[3] not in anchors_used]

    # 统计
    def stat(key):
        out = {}
        for r in results:
            k = r[key]
            out[k] = out.get(k, 0) + 1
        return out

    by_status = stat("status")
    lines = ["# 600 人索引比对报告", "",
             f"- 名录总条目：**{len(results)}**",
             f"- 已确认 confirmed：**{by_status.get('confirmed', 0)}**（其中 CBDB 状元标记互证 {sum(1 for r in results if r['evidence']=='rank1')}）",
             f"- 存疑 suspect：**{by_status.get('suspect', 0)}**",
             f"- 缺失 missing：**{by_status.get('missing', 0)}**",
             f"- CBDB 反向多出条目：**{len(extra)}**", "",
             "## 分朝代统计", "",
             "| 朝代 | 总数 | 已确认 | 存疑 | 缺失 |", "|---|---|---|---|---|"]
    for d in DYNASTY_ORDER:
        rows = [r for r in results if r["dynasty"] == d]
        c = sum(1 for r in rows if r["status"] == "confirmed")
        s = sum(1 for r in rows if r["status"] == "suspect")
        m = sum(1 for r in rows if r["status"] == "missing")
        lines.append(f"| {d} | {len(rows)} | {c} | {s} | {m} |")
    lines += ["", "## 存疑条目（需人工补核）", "",
              "| index_id | 姓名 | 朝代 | 名录年 | 原因 |", "|---|---|---|---|---|"]
    for r in results:
        if r["status"] == "suspect":
            lines.append(f"| {r['index_id']} | {r['name']} | {r['dynasty']} | {r['exam_year'] or '阙'} | {r['evidence']} |")
    lines += ["", "## 缺失条目（CBDB 无记录）", "",
              "| index_id | 姓名 | 朝代 | 名录年 | 名录备注 |", "|---|---|---|---|---|"]
    for r in results:
        if r["status"] == "missing":
            lines.append(f"| {r['index_id']} | {r['name']} | {r['dynasty']} | {r['exam_year'] or '阙'} | {r.get('note') or ''} |")
    lines += ["", "## CBDB 多出条目（名录未覆盖，防漏收）", "",
              "| CBDB 名(繁) | 年 | 朝代 | CBDB ID |", "|---|---|---|---|"]
    for a in extra:
        lines.append(f"| {a['name_tw']} | {a['year']} | {a['dynasty']} | {a['cbdb_id']} |")
    lines.append("")

    (OUT / "zhuangyuan_index.yaml").write_text(
        "# 全量状元索引 v1.0（build_index.py 生成，勿手改；改动请修 roster_*.yaml 后重建）\n"
        + yaml.dump(results, allow_unicode=True, sort_keys=False), encoding="utf-8")
    with (OUT / "zhuangyuan_index.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        w.writeheader()
        w.writerows(results)
    (OUT / "index_report.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"名录 {len(results)} | confirmed {by_status.get('confirmed',0)} "
          f"suspect {by_status.get('suspect',0)} missing {by_status.get('missing',0)} "
          f"| CBDB多出 {len(extra)}")
    for d in DYNASTY_ORDER:
        rows = [r for r in results if r["dynasty"] == d]
        c = sum(1 for r in rows if r["status"] == "confirmed")
        print(f"  {d:<4} {len(rows):>3} 条, confirmed {c}")


if __name__ == "__main__":
    main()
