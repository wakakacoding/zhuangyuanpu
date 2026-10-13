#!/usr/bin/env python3
"""生卒年批量回填（Phase 2 / WP1 续）：索引 cbdb_id → CBDB BIOG_MAIN → 卡片

铁律：只填空（缺字段 / null / 0 占位），绝不覆盖已有值（王维 701 异说案例保护）。
诚实性：c_birthyear/c_deathyear 为精确生卒才回填；CBDB 的 c_index_year 是估算
活动年（约中年），回填为独立字段 fl_year 并标注来源，绝不混入 birth_year。
用法:
  python3 scripts/fill_lifespan.py --dry-run
  python3 scripts/fill_lifespan.py
"""
import re
import sqlite3
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CBDB = ROOT / "vendor" / "cbdb" / "cbdb_20261010.sqlite3"


def main():
    dry = "--dry-run" in sys.argv

    # slug → cbdb_id（索引是比对后的权威映射）
    index = yaml.safe_load((DATA / "index" / "zhuangyuan_index.yaml").read_text(encoding="utf-8"))
    slug2cbdb = {r["slug"]: r["cbdb_id"] for r in index if r.get("cbdb_id")}

    conn = sqlite3.connect(f"file:{CBDB}?mode=ro", uri=True)

    def cbdb_years(pid: int):
        row = conn.execute(
            "SELECT c_birthyear, c_deathyear, c_index_year FROM BIOG_MAIN WHERE c_personid=?", (pid,)
        ).fetchone()
        if not row:
            return None, None, None
        b, d, iy = row
        return (
            b if b and b > 0 else None,
            d if d and d > 0 else None,
            iy if iy and iy > 0 else None,
        )

    pdir = DATA / "persons"
    filled_b = filled_d = filled_fl = skipped_kept = no_cbdb = no_year = 0
    for f in sorted(pdir.glob("*.yaml")):
        if f.name.startswith("_"):
            continue
        doc = yaml.safe_load(f.read_text(encoding="utf-8"))
        if not isinstance(doc, dict):
            continue
        pid = slug2cbdb.get(doc["id"])
        if not pid:
            no_cbdb += 1
            continue
        need_b = not doc.get("birth_year")
        need_d = not doc.get("death_year")
        need_fl = not doc.get("fl_year")
        if not (need_b or need_d or need_fl):
            skipped_kept += 1
            continue
        b, d, iy = cbdb_years(pid)
        if not b and not d and not iy:
            no_year += 1
            continue

        text = f.read_text(encoding="utf-8")
        changed = False
        if need_b and b:
            if re.search(r"^birth_year:", text, flags=re.M):
                text = re.sub(r"^birth_year:.*$", f"birth_year: {b}", text, count=1, flags=re.M)
            else:
                text = re.sub(r"^(name:.*)$", "\\1\nbirth_year: " + str(b), text, count=1, flags=re.M)
            filled_b += 1
            changed = True
        if need_d and d:
            if re.search(r"^death_year:", text, flags=re.M):
                text = re.sub(r"^death_year:.*$", f"death_year: {d}", text, count=1, flags=re.M)
            else:
                text = re.sub(r"^(birth_year:.*)$", "\\1\ndeath_year: " + str(d), text, count=1, flags=re.M)
            filled_d += 1
            changed = True
        # 活动年（CBDB 估算）：仅当无精确生年时记录，避免重复信息
        if need_fl and iy and not (doc.get("birth_year") or b):
            if re.search(r"^fl_year:", text, flags=re.M):
                text = re.sub(r"^fl_year:.*$", f"fl_year: {iy}", text, count=1, flags=re.M)
            else:
                text = re.sub(r"^(death_year:.*)$", "\\1\nfl_year: " + str(iy), text, count=1, flags=re.M)
            filled_fl += 1
            changed = True
        if changed and not dry:
            f.write_text(text, encoding="utf-8")

    conn.close()
    print(f"{'[DRY-RUN] ' if dry else ''}cbdb 无锚点 {no_cbdb} | CBDB 无任何年 {no_year} | 已齐跳过 {skipped_kept}")
    print(f"回填生年 {filled_b} / 卒年 {filled_d} / 活动年(fl_year, CBDB 估算) {filled_fl}")


if __name__ == "__main__":
    main()
