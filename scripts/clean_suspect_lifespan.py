#!/usr/bin/env python3
"""存量 suspect 生卒清洗（R1.1-3）：机器回填值 → null + 加 identity_note。

背景
----
`zhuangyuan_index.yaml` 中 `status: suspect` = 只找到 CBDB **候选**、未消歧。这类卡上
的年份全部来自那个候选人：

  - `birth_year` / `death_year` ← 索引（build_index.py 取 BIOG_MAIN.c_birthyear/deathyear）
  - `fl_year`                 ← fill_lifespan.py 取 BIOG_MAIN.c_index_year

身份既未核实，这些数字就不是「本人的」——本脚本按下列规则回退：

  1. 索引 suspect 且 `identity_status == suspect` 的**自动生成极简卡**
     （`index_to_cards.py` 产物）：`birth_year` / `death_year` → null；
  2. **全部** suspect 卡的 `fl_year` → null（该字段只可能来自 CBDB 候选人，见 schema/SCHEMA.md）；
  3. `birth_year: 0` / `death_year: 0` 的占位值 → null（0 非年份，渲染有「生年–0」隐患）；
  4. 每张被改动的卡追加 `identity_note`（说明为何阙如、待补依据）。

**不碰**：人工立目卡（非 index_to_cards 生成）的 birth/death —— 那是自主编纂的史料，
不是候选人数据；以及已被 accepted 勘误（data/corrections/）锁定字段的卡。

用法:
  python3 scripts/clean_suspect_lifespan.py --dry     # 只出清单（默认）
  python3 scripts/clean_suspect_lifespan.py --apply
  python3 scripts/clean_suspect_lifespan.py --apply --bd-only   # 只清生卒，不动 fl_year
"""
import re
import sqlite3
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PERSONS = DATA / "persons"
CBDB = ROOT / "vendor" / "cbdb" / "cbdb_20261010.sqlite3"

NOTE_BD = "CBDB 候选匹配，生卒系候选人数据，待碑录／《登科记考》补"
NOTE_FL = "CBDB 候选匹配，活动年（fl_year）系候选人数据，待碑录／《登科记考》补"

AUTO_MARK = "index_to_cards.py 自动生成"  # 极简卡文件头标记（人工立目卡没有）


def corr_locked_fields() -> dict[str, set[str]]:
    """被 accepted 勘误锁定的字段：{person_id: {field, ...}}（这些字段人工已定，勿自动回退）"""
    locked: dict[str, set[str]] = {}
    for f in sorted((DATA / "corrections").glob("*.yaml")):
        if f.name.startswith("_"):
            continue
        c = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        if c.get("status") != "accepted":
            continue
        tgt = str(c.get("target", ""))
        if tgt.startswith("person:"):
            locked.setdefault(tgt.split(":", 1)[1], set()).add(str(c.get("field")))
    return locked


def set_line(text: str, key: str, value: str, anchor: str | None = None) -> str:
    """把 `key: ...` 行改成 `key: value`；没有该行则插在 anchor 行之后。"""
    if re.search(rf"^{key}:", text, flags=re.M):
        return re.sub(rf"^{key}:.*$", f"{key}: {value}", text, count=1, flags=re.M)
    if anchor and re.search(rf"^{anchor}:.*$", text, flags=re.M):
        return re.sub(rf"^({anchor}:.*)$", f"\\1\n{key}: {value}", text, count=1, flags=re.M)
    return text.rstrip("\n") + f"\n{key}: {value}\n"


def main() -> None:
    apply = "--apply" in sys.argv
    bd_only = "--bd-only" in sys.argv

    index = yaml.safe_load((DATA / "index" / "zhuangyuan_index.yaml").read_text(encoding="utf-8"))
    suspect_by_name = {e["name"]: e for e in index if e.get("status") == "suspect"}
    locked = corr_locked_fields()

    conn = sqlite3.connect(f"file:{CBDB}?mode=ro", uri=True)

    def cand_years(cbdb_id):
        if not cbdb_id:
            return None, None, None
        row = conn.execute(
            "SELECT c_birthyear, c_deathyear, c_index_year FROM BIOG_MAIN WHERE c_personid=?",
            (cbdb_id,)).fetchone()
        if not row:
            return None, None, None
        return tuple(v if v and v > 0 else None for v in row)

    rows: list[tuple[str, str, str, str, str, str]] = []  # 卡id, 姓名, 科年, 被清字段, 原值, 依据
    files: list[tuple[Path, str]] = []
    for f in sorted(PERSONS.glob("*.yaml")):
        if f.name.startswith("_"):
            continue
        text = f.read_text(encoding="utf-8")
        doc = yaml.safe_load(text)
        if not isinstance(doc, dict):
            continue
        entry = suspect_by_name.get(doc["name"])
        if not entry or doc.get("identity_status") != "suspect":
            continue
        pid = doc["id"]
        if pid in locked:
            continue  # 已被勘误锁定（如 ma_lei_ji corr_004），交人工
        auto = AUTO_MARK in text
        cb_b, cb_d, cb_i = cand_years(entry.get("cbdb_id"))

        targets: list[str] = []
        if auto:
            for k, cb_v in (("birth_year", cb_b), ("death_year", cb_d)):
                v = doc.get(k)
                if locked.get(pid, set()) and k in locked[pid]:
                    continue
                if v is None or v == 0:
                    continue  # 已是空值/0 占位：null 化在下面统一处理
                if cb_v is not None and v != cb_v:
                    continue  # 与候选人数据不符 → 疑为人工填写，保留
                targets.append(k)
            # 0 占位 null 化（渲染隐患，schema 空值合法）
            if (doc.get("birth_year") == 0 or doc.get("death_year") == 0) and "birth_year" not in targets:
                targets += [k for k in ("birth_year", "death_year") if doc.get(k) == 0]
        if not bd_only and doc.get("fl_year") and "fl_year" not in locked.get(pid, set()):
            targets.append("fl_year")
        if not targets:
            continue

        new_text = text
        if "birth_year" in targets:
            new_text = set_line(new_text, "birth_year", "null")
        if "death_year" in targets:
            new_text = set_line(new_text, "death_year", "null")
        if "fl_year" in targets:
            new_text = set_line(new_text, "fl_year", "null", anchor="death_year")
        note = NOTE_BD if ("birth_year" in targets or "death_year" in targets) else NOTE_FL
        if doc.get("identity_note") != note:
            new_text = set_line(new_text, "identity_note", note, anchor="identity_status")
        if new_text != text:
            files.append((f, new_text))
            old = " / ".join(f"{k}={doc.get(k)}" for k in targets)
            src = f"CBDB#{entry.get('cbdb_id')} 候选 b/d/活动年={cb_b}/{cb_d}/{cb_i}"
            rows.append((pid, doc["name"], str(entry.get("exam_year")), ",".join(targets), old, src))

    conn.close()

    print(f"{'[DRY] 将清理' if not apply else '已清理'} {len(rows)} 张卡 / 涉及 {len({r[0] for r in rows})} 人"
          f"（fl_year {'不动' if bd_only else '一并回退'}）")
    print(f"{'卡id':18s}{'姓名':8s}{'科年':>6s}  {'被清字段':22s}{'原值':26s}依据")
    for pid, name, ey, fields, old, src in rows:
        print(f"{pid:18s}{name:8s}{ey:>6s}  {fields:22s}{old:26s}{src}")

    if apply:
        for f, new_text in files:
            f.write_text(new_text, encoding="utf-8")
        print(f"\n已写入 {len(files)} 个文件。")


if __name__ == "__main__":
    main()
