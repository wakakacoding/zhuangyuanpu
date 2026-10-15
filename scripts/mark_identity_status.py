#!/usr/bin/env python3
"""身份匹配分层标注（R1.1-1）：按索引 status 给人物卡批量写 `identity_status`。

规则
----
  - `data/index/zhuangyuan_index.yaml` 中 `status: suspect` 的条目（CBDB 候选匹配、
    未核实）→ 对应人物卡写 `identity_status: suspect`（继承索引口径）；
  - 其中**已人工考证**者 → 写 `identity_status: confirmed`。判定（自动，二选一即可）：
      a) 有全档案：存在 `data/events/<card_id>.yaml`；
      b) 有专篇故事：`content/stories/*.md` 里出现 `[[card:<card_id>]]` 引用。
    另可把人工判定结果写进 EXTRA_CONFIRMED（id 集合），一并置 confirmed；
  - 索引 status 为 confirmed / missing 的条目**不写此字段**（缺省 = 未标注，语义见
    schema/SCHEMA.md）。

索引条目与人物卡按**姓名**关联（不是 slug）——索引 slug 与卡 id 有 7 处不一致
（如索引 `sun_fu_ga` ↔ 卡 `sun_fujia`：同名精修卡先存在时索引重条被跳过）。

字段插在 `status:` 行之后；已存在则原地替换。幂等：重跑结果一致，无需变动者不计。

用法:
  python3 scripts/mark_identity_status.py --dry
  python3 scripts/mark_identity_status.py
"""
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PERSONS = DATA / "persons"
STORIES = ROOT / "content" / "stories"
INDEX = DATA / "index" / "zhuangyuan_index.yaml"

# 人工判定为「已考证」但机器无从推断者（当前为空；如后续有单篇故事但无 card 引用，可登记于此）
EXTRA_CONFIRMED: set[str] = set()

CARD_REF_RE = re.compile(r"\[\[card:([a-z0-9_]+)")


def card_ids_in_stories() -> set[str]:
    ids: set[str] = set()
    if not STORIES.exists():
        return ids
    for f in STORIES.glob("*.md"):
        ids |= set(CARD_REF_RE.findall(f.read_text(encoding="utf-8")))
    return ids


def full_profile_ids() -> set[str]:
    d = DATA / "events"
    if not d.exists():
        return set()
    return {f.stem for f in d.glob("*.yaml") if not f.name.startswith("_")}


def main() -> None:
    dry = "--dry" in sys.argv

    index = yaml.safe_load(INDEX.read_text(encoding="utf-8"))
    suspect_by_name = {e["name"]: e for e in index if e.get("status") == "suspect"}

    story_ids = card_ids_in_stories()
    profile_ids = full_profile_ids()

    cards = []
    for f in sorted(PERSONS.glob("*.yaml")):
        if f.name.startswith("_"):
            continue
        doc = yaml.safe_load(f.read_text(encoding="utf-8"))
        if isinstance(doc, dict) and doc.get("id"):
            cards.append((f, doc))

    to_suspect, to_confirmed, already = [], [], []
    for f, doc in cards:
        entry = suspect_by_name.get(doc["name"])
        if not entry:
            continue  # 非 suspect 条目：不写字段
        pid = doc["id"]
        verified = pid in profile_ids or pid in story_ids or pid in EXTRA_CONFIRMED
        want = "confirmed" if verified else "suspect"
        if doc.get("identity_status") == want:
            already.append((f, pid, want))
            continue
        (to_confirmed if want == "confirmed" else to_suspect).append((f, pid, want))

    pending = to_suspect + to_confirmed
    if not dry:
        for f, pid, want in pending:
            text = f.read_text(encoding="utf-8")
            line = f"identity_status: {want}"
            if re.search(r"^identity_status:.*$", text, flags=re.M):
                text = re.sub(r"^identity_status:.*$", line, text, count=1, flags=re.M)
            elif re.search(r"^status:.*$", text, flags=re.M):
                text = re.sub(r"^(status:.*)$", "\\1\n" + line, text, count=1, flags=re.M)
            else:
                text = text.rstrip("\n") + "\n" + line + "\n"
            f.write_text(text, encoding="utf-8")

    tag = "[dry] 待写" if dry else "已写"
    print(f"索引 suspect 条目 {len(suspect_by_name)} | 匹配到人物卡 {len(to_suspect)+len(to_confirmed)+len(already)}")
    print(f"{tag}：suspect {len(to_suspect)} / confirmed {len(to_confirmed)} | 已是目标值（幂等跳过）{len(already)}")
    print("置 confirmed（已人工考证）明细：")
    names = {doc["id"]: doc["name"] for _, doc in cards}
    for f, pid, _ in to_confirmed + [(f, p, w) for f, p, w in already if w == "confirmed"]:
        why = []
        if pid in profile_ids:
            why.append("全档案")
        if pid in story_ids:
            why.append("专篇故事")
        if pid in EXTRA_CONFIRMED:
            why.append("人工登记")
        print(f"  {pid:16s} {names.get(pid, '?'):8s} {'+'.join(why)}")


if __name__ == "__main__":
    main()
