#!/usr/bin/env python3
"""数据底座校验器（构建期强制执行三条铁律）

用法: python3 scripts/validate.py
退出码: 0 = 通过（允许警告）; 1 = 存在错误
检查项:
  - 必填字段 / id 与文件名一致 / id 命名规范
  - 枚举合法性（event.type / year_precision / source.tier / relation.type）
  - 引用完整性（event.source_ids、relation.to_id 等必须存在）
  - 干支-公元互验（person.exam_year vs ganzhi）
  - 铁律 1: 事件无出处（source_ids 为空）-> 错误；史实仅有 C 级出处 -> 警告
  - 铁律 2: 轶事只存在于 anecdotes 表（event.type 枚举中无「轶事」，天然隔离）
  - 覆盖率看板: 坐标 / 生卒覆盖（Phase 3 数据阈值闸门）
"""
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
sys.path.insert(0, str(ROOT / "scripts"))
from era import ganzhi_of, year_in_reign  # noqa: E402

EVENT_TYPES = {"出生", "应试", "中举", "夺魁", "授官", "留学", "升迁",
               "贬谪", "罢官", "被俘", "实业", "致仕", "隐居", "守节", "著作", "卒"}
PRECISIONS = {"exact", "about", "range"}
TIERS = {"A", "B", "C"}
REL_TYPES = {"同年", "师生", "父子", "翁婿", "政敌", "兄弟", "友人"}
ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")

errors: list[str] = []
warnings: list[str] = []
err = errors.append
warn = warnings.append


def load_dir(name: str) -> dict:
    d = DATA / name
    out = {}
    if not d.exists():
        return out
    for f in sorted(d.glob("*.yaml")):
        if f.name.startswith("_"):  # 模板跳过
            continue
        try:
            out[f.stem] = yaml.safe_load(f.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            err(f"{name}/{f.name}: YAML 解析失败 {e}")
    return out


persons = load_dir("persons")
events_by = load_dir("events")
sources = load_dir("sources")
rels_by = load_dir("relations")
works_by = load_dir("works")
anec_by = load_dir("anecdotes")
geo_file = DATA / "geo_map.yaml"
geo = yaml.safe_load(geo_file.read_text(encoding="utf-8")) if geo_file.exists() else []
geo_hists = {g.get("hist") for g in (geo or []) if isinstance(g, dict)}

# ---------- person ----------
for stem, p in persons.items():
    if not isinstance(p, dict):
        err(f"persons/{stem}.yaml: 顶层必须是对象")
        continue
    pid = p.get("id")
    if not pid:
        err(f"persons/{stem}.yaml: 缺 id")
        continue
    if pid != stem:
        err(f"persons/{stem}.yaml: id({pid}) 与文件名不一致")
    if not ID_RE.match(pid):
        err(f"person {pid}: id 非法（须小写拼音 slug）")
    for req in ("name", "dynasty", "status"):
        if not p.get(req):
            err(f"person {pid}: 缺必填字段 {req}")
    if p.get("status") not in ("draft", "published"):
        err(f"person {pid}: status 非法（draft/published）")
    for opt in ("exam_year", "native_hist", "rank_detail"):
        if p.get(opt) is None:
            warn(f"person {pid}: 建议字段 {opt} 缺失（若史料阙如可忽略）")
    ey, gz = p.get("exam_year"), p.get("ganzhi")
    if ey is not None and gz:
        if ganzhi_of(int(ey)) != gz:
            err(f"person {pid}: 干支互验失败——{ey} 年应为 {ganzhi_of(int(ey))}，录为 {gz}")
    reign = p.get("reign")
    if ey is not None and reign:
        in_reign = year_in_reign(int(ey), reign)
        if in_reign is False:
            err(f"person {pid}: 年号互验失败——{ey} 不在 {reign} 年间")
        elif in_reign is None:
            warn(f"person {pid}: 年号「{reign}」未收录进 era.py，跳过互验")
    bounds = {"lat": 90, "lng": 180}
    for c in ("lat", "lng"):
        v = p.get(c)
        if v is not None and not (-bounds[c] <= float(v) <= bounds[c]):
            err(f"person {pid}: {c} 越界")
    nh = p.get("native_hist")
    if nh and geo_hists and nh not in geo_hists:
        warn(f"person {pid}: 籍贯「{nh}」未收录进 geo_map.yaml")
    if nh and p.get("lat") is None:
        warn(f"person {pid}: 缺坐标（可视化前置字段）")

# ---------- source ----------
for stem, s in sources.items():
    if not isinstance(s, dict):
        err(f"sources/{stem}.yaml: 顶层必须是对象")
        continue
    sid = s.get("id")
    if not sid or sid != stem:
        err(f"sources/{stem}.yaml: id 缺失或与文件名不一致")
        continue
    if not sid.startswith("src_"):
        err(f"source {sid}: id 须以 src_ 开头")
    if not s.get("title"):
        err(f"source {sid}: 缺 title")
    if s.get("tier") not in TIERS:
        err(f"source {sid}: tier 非法（A/B/C）")
    if s.get("tier") == "A" and not s.get("quote"):
        warn(f"source {sid}: A 级出处建议附原文 quote")

# ---------- event ----------
for stem, doc in events_by.items():
    if not isinstance(doc, dict):
        err(f"events/{stem}.yaml: 顶层必须是对象")
        continue
    pid = doc.get("person_id")
    if pid != stem:
        err(f"events/{stem}.yaml: person_id({pid}) 与文件名不一致")
    if pid not in persons:
        err(f"events/{stem}.yaml: person_id {pid} 不存在")
        continue
    for i, e in enumerate(doc.get("events") or []):
        tag = f"events/{stem}[{i}]"
        if e.get("year") is None:
            err(f"{tag}: 缺 year")
        if e.get("type") not in EVENT_TYPES:
            err(f"{tag}: type 非法 {e.get('type')}")
        if e.get("year_precision") not in PRECISIONS:
            err(f"{tag}: year_precision 非法（exact/about/range）")
        if e.get("year_precision") == "range" and e.get("year_end") is None:
            err(f"{tag}: range 精度缺 year_end")
        if not e.get("title"):
            err(f"{tag}: 缺 title")
        sids = e.get("source_ids") or []
        if not sids:
            err(f"{tag}: 铁律违反——事件无出处（source_ids 为空）")
        for sid in sids:
            if sid not in sources:
                err(f"{tag}: 引用不存在的 source {sid}")
        tiers = {sources[sid].get("tier") for sid in sids if sid in sources}
        if tiers and tiers == {"C"}:
            warn(f"{tag}: 史实事件仅有 C 级出处，建议补 A/B 级或移入 anecdotes")

# ---------- relation ----------
for stem, doc in rels_by.items():
    if not isinstance(doc, dict):
        err(f"relations/{stem}.yaml: 顶层必须是对象")
        continue
    fid = doc.get("from_id")
    if fid != stem:
        err(f"relations/{stem}.yaml: from_id({fid}) 与文件名不一致")
    if fid not in persons:
        err(f"relations/{stem}.yaml: from_id {fid} 不存在")
    for i, r in enumerate(doc.get("relations") or []):
        tag = f"relations/{stem}[{i}]"
        if r.get("to_id") not in persons:
            err(f"{tag}: to_id {r.get('to_id')} 不存在")
        if r.get("type") not in REL_TYPES:
            err(f"{tag}: type 非法 {r.get('type')}")
        for sid in r.get("source_ids") or []:
            if sid not in sources:
                err(f"{tag}: 引用不存在的 source {sid}")

# ---------- works / anecdotes ----------
for stem, doc in works_by.items():
    if not isinstance(doc, dict) or doc.get("person_id") != stem:
        err(f"works/{stem}.yaml: person_id 缺失或与文件名不一致")
    if stem not in persons:
        err(f"works/{stem}.yaml: person {stem} 不存在")
    for i, w in enumerate((doc or {}).get("works") or []):
        if not w.get("title"):
            err(f"works/{stem}[{i}]: 缺 title")

for stem, doc in anec_by.items():
    if not isinstance(doc, dict) or doc.get("person_id") != stem:
        err(f"anecdotes/{stem}.yaml: person_id 缺失或与文件名不一致")
    if stem not in persons:
        err(f"anecdotes/{stem}.yaml: person {stem} 不存在")
    for i, a in enumerate((doc or {}).get("anecdotes") or []):
        tag = f"anecdotes/{stem}[{i}]"
        if a.get("tier") not in TIERS:
            err(f"{tag}: tier 非法（默认应为 C）")
        if not a.get("title") or not a.get("content"):
            err(f"{tag}: 缺 title/content")
        for sid in a.get("source_ids") or []:
            if sid not in sources:
                err(f"{tag}: 引用不存在的 source {sid}")

# ---------- geo_map ----------
for i, g in enumerate(geo or []):
    if isinstance(g, dict) and (not g.get("hist") or not g.get("modern")):
        err(f"geo_map[{i}]: 缺 hist/modern")

# ---------- corrections（勘误记录） ----------
CORR_STATUS = {"pending", "accepted", "rejected", "noted"}
corrs = load_dir("corrections")
for stem, c in corrs.items():
    if not isinstance(c, dict):
        err(f"corrections/{stem}: 结构非法")
        continue
    tag = f"corrections/{stem}"
    if c.get("id") != stem and not stem.startswith(str(c.get("id", "\0")) + "_"):
        err(f"{tag}: id {c.get('id')} 与文件名不一致")
    for req in ("target", "field", "current", "proposed", "evidence", "status", "reporter", "created"):
        if not c.get(req):
            err(f"{tag}: 缺必填字段 {req}")
    if c.get("status") not in CORR_STATUS:
        err(f"{tag}: status 非法（须为 {CORR_STATUS}）")
    tgt = str(c.get("target", ""))
    if tgt.startswith("person:") and tgt.split(":", 1)[1] not in persons:
        err(f"{tag}: target 引用不存在的人物 {tgt}")


# ---------- 覆盖率看板（Phase 3 阈值闸门） ----------
n = len(persons)


def cov(pred):
    m = sum(1 for p in persons.values() if isinstance(p, dict) and pred(p))
    return m, (m / n * 100 if n else 0)


c_geo = cov(lambda p: p.get("lat") is not None)
c_bd = cov(lambda p: bool(p.get("birth_year")) and bool(p.get("death_year")))
c_star = cov(lambda p: bool(p.get("birth_year")) or bool(p.get("fl_year")))
c_ev = sum(1 for stem in persons if stem in events_by)
rel_edges = sum(len((d or {}).get("relations") or []) for d in rels_by.values())

print("=" * 56)
print("数据底座校验报告")
print("=" * 56)
print(f"persons: {n} | sources: {len(sources)} | relation 边: {rel_edges}")
print(f"坐标覆盖: {c_geo[0]}/{n} ({c_geo[1]:.0f}%)   [地图闸门 >= 60%]")
print(f"生卒双全: {c_bd[0]}/{n} ({c_bd[1]:.0f}%)   [精确口径]")
print(f"星图可用年: {c_star[0]}/{n} ({c_star[1]:.0f}%)   [星图闸门 >= 50%：生年或 fl_year(CBDB 估算活动年)]")
print(f"有事件档案: {c_ev}/{n}")
print("-" * 56)
for w in warnings:
    print(f"  [警告] {w}")
for e in errors:
    print(f"  [错误] {e}")
print("-" * 56)
print(f"结论: {len(errors)} 错误 / {len(warnings)} 警告")
sys.exit(1 if errors else 0)
