#!/usr/bin/env python3
"""繁简切换·人名保护表生成器（build_names.py）

繁简转换最大风险是人名用字被误转（于→於、余→餘、范→範、栗→慄、梁→樑、
咸→鹹、岳→嶽、启→啟、咨→諮 等姓氏/人名用字）。对策：转换前把全量人名
替换为占位符，转换后还原——保护范围 = 全部在库状元的姓名 + 字 + 号。

产物：site/public/data/protected_names.json
    ["孙伏伽", "王维", ...]（按长度降序，前端替换时长名优先，防部分命中）

由 site/astro.config.mjs 的 names-data 集成在构建/起服时自动调用。
"""
import glob
import json
import os

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'site', 'public', 'data', 'protected_names.json')


def main():
    names = set()
    for path in glob.glob(os.path.join(ROOT, 'data', 'persons', '*.yaml')):
        if os.path.basename(path).startswith('_'):
            continue
        with open(path, encoding='utf-8') as f:
            p = yaml.safe_load(f)
        for field in ('name', 'zi', 'hao'):
            v = p.get(field)
            if v and isinstance(v, str):
                names.add(v.strip())

    ordered = sorted(names, key=len, reverse=True)
    payload = json.dumps(ordered, ensure_ascii=False, separators=(',', ':'))
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write(payload)
    print(f'[names] 保护词 {len(ordered)} 个 | 体积 {len(payload.encode("utf-8"))/1024:.1f}KB')


if __name__ == '__main__':
    main()
