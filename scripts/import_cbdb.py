#!/usr/bin/env python3
"""CBDB 导入器（R10 验证 / Phase 1 全量索引的前置工具）

用途：
  1. --verify  抽样验证：查询若干位已知状元在 CBDB 中的记录质量（本项目的 R10 风险验证）
  2. --export  导出候选池：CBDB 中所有「进士」入仕者 → 极简速览卡 YAML（待人工比对题名碑录后入库）

数据库获取（须遵循 CBDB Data Licensing Terms：属「当前单机版范围内」的数据为
  CC BY-NC-SA 4.0——不得商用、须署名 CBDB、改编须以相同协议发布）：
  https://github.com/cbdb-project/cbdb_sqlite  →  latest.json 给出 HuggingFace 下载地址
  本项目已落地 2026-10-10 版：vendor/cbdb/cbdb_20261010.sqlite3（勿提交 Git）

关键表结构（CBDB 官方文档）：
  BIOG_MAIN       c_personid, c_name_chn, c_surname_chn, c_mingzi_chn, c_birthyear, c_deathyear, c_index_year
  BIOG_ADDR_DATA  c_personid, c_addr_id, c_addr_type(1=籍贯)  →  ADDR_CODES(c_addr_id, c_name_chn, c_first_year, c_last_year)
  ENTRY_DATA      c_personid, c_entry_type, c_year, c_exam_rank  →  ENTRY_TYPES(c_entry_type, c_entry_type_chn)
  DYNASTIES       c_dy, c_dynasty_chn

用法：
  python3 scripts/import_cbdb.py --verify
  python3 scripts/import_cbdb.py --export --out /tmp/cbdb_pool.yaml
"""
import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "vendor" / "cbdb" / "cbdb_20261010.sqlite3"

# 抽样验证名单：覆盖唐宋明清 + 争议案例（王维）+ 跨政权（泰不华）
# 注意：CBDB 使用繁体中文，查询须用繁体名
SAMPLE = [
    ("文天祥", "文天祥"), ("刘春霖", "劉春霖"), ("商辂", "商輅"), ("张謇", "張謇"),
    ("王维", "王維"), ("杨慎", "楊慎"), ("孙伏伽", "孫伏伽"), ("泰不华", "泰不華"),
    ("陈继昌", "陳繼昌"), ("王曾", "王曾"),
]

VERIFY_SQL = """
SELECT b.c_personid, b.c_name_chn, b.c_birthyear, b.c_deathyear, b.c_index_year,
       (SELECT group_concat(a.c_name_chn, ' / ')
          FROM BIOG_ADDR_DATA ba JOIN ADDR_CODES a ON ba.c_addr_id = a.c_addr_id
         WHERE ba.c_personid = b.c_personid AND ba.c_addr_type = 1) AS native_place,
       (SELECT group_concat(e.c_year || ':' || COALESCE(t.c_entry_type_desc_chn, '?')
                              || COALESCE('(' || e.c_exam_rank || ')', ''), ' | ')
          FROM ENTRY_DATA e LEFT JOIN ENTRY_TYPES t ON e.c_entry_code = t.c_entry_type
         WHERE e.c_personid = b.c_personid) AS entries
  FROM BIOG_MAIN b
 WHERE b.c_name_chn = ?
"""


def verify(con):
    print(f"{'姓名':<6}{'CBDB ID':<9}{'生':<6}{'卒':<6}{'籍贯(籍)':<24}入仕记录")
    print("-" * 100)
    for simp, trad in SAMPLE:
        rows = con.execute(VERIFY_SQL, (trad,)).fetchall()
        if not rows:
            print(f"{simp:<6} ** 未收录 **")
            continue
        for r in rows:
            pid, nm, by, dy, iy, place, entries = r
            place = (place or "—")[:20]
            entries = (entries or "—")[:60]
            print(f"{simp:<6}{pid:<9}{by or '?':<6}{dy or '?':<6}{place:<24}{entries}")


def export(con, out: str):
    """导出全部进士入仕者候选池（极简字段，供人工比对后批量转速览卡）。"""
    sql = """
    SELECT DISTINCT b.c_personid, b.c_name_chn, b.c_birthyear, b.c_deathyear,
           e.c_year AS exam_year
      FROM BIOG_MAIN b
      JOIN ENTRY_DATA e ON b.c_personid = e.c_personid
      JOIN ENTRY_TYPES t ON e.c_entry_code = t.c_entry_type
     WHERE t.c_entry_type_desc_chn LIKE '%進士%' AND e.c_year IS NOT NULL
     ORDER BY e.c_year
    """
    rows = con.execute(sql).fetchall()
    out_path = Path(out)
    with out_path.open("w", encoding="utf-8") as f:
        f.write("# CBDB 进士候选池（待人工比对《明清进士题名碑录》等权威名录后转速览卡）\n")
        for pid, nm, by, dy, ey in rows:
            f.write(f"- cbdb_id: {pid}\n  name: {nm}\n  birth_year: {by}\n"
                    f"  death_year: {dy}\n  exam_year: {ey}\n")
    print(f"导出 {len(rows)} 条 → {out_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DB), help="CBDB sqlite 路径")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--export", action="store_true")
    ap.add_argument("--out", default="/tmp/cbdb_pool.yaml")
    args = ap.parse_args()
    db_path = Path(args.db)
    if not db_path.exists():
        sys.exit(f"数据库不存在: {db_path}\n请先按文件头注释下载 CBDB SQLite。")
    con = sqlite3.connect(db_path)
    if args.verify:
        verify(con)
    elif args.export:
        export(con, args.out)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
