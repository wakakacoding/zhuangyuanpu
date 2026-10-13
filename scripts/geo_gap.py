#!/usr/bin/env python3
"""geo_map 缺口分析：提取全部 unique 籍贯，对比 geo_map，输出待补清单（按朝代/频次排序）"""
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

geo = yaml.safe_load((DATA / "geo_map.yaml").read_text(encoding="utf-8")) or []
mapped = {g["hist"] for g in geo if isinstance(g, dict) and g.get("hist")}

persons = {}
for f in sorted((DATA / "persons").glob("*.yaml")):
    if f.name.startswith("_"):
        continue
    p = yaml.safe_load(f.read_text(encoding="utf-8"))
    if isinstance(p, dict):
        persons[p["id"]] = p

# 缺口：native_hist 存在但既不在 geo_map、卡上也没有 native_modern+坐标
gap: Counter[str] = Counter()
gap_dyn: dict[str, Counter] = defaultdict(Counter)
ok_coord = 0
for p in persons.values():
    nh = p.get("native_hist")
    if p.get("lat") is not None:
        ok_coord += 1
        continue
    if not nh:
        continue
    if nh in mapped:
        # geo_map 有映射但卡片未回填（回填脚本的事）
        gap[f"[geo_map已有·待回填] {nh}"] += 1
        gap_dyn[p.get("dynasty", "?")][nh] += 1
    else:
        gap[nh] += 1
        gap_dyn[p.get("dynasty", "?")][nh] += 1

print(f"总人数 {len(persons)}，卡上已有坐标 {ok_coord}")
print(f"缺口 unique 籍贯 {len([g for g in gap if not g.startswith('[')])} 个（geo_map 已有待回填 {len([g for g in gap if g.startswith('[')])} 个）")
print()
for dyn in ["唐", "五代十国", "宋", "辽", "金", "元", "明", "清", "?"]:
    c = gap_dyn.get(dyn)
    if not c:
        continue
    print(f"== {dyn}（{sum(c.values())} 人 / {len(c)} 地）==")
    for place, n in c.most_common():
        print(f"  {place} ×{n}")
