#!/usr/bin/env python3
"""星图数据切片生成器（build_galaxy.py）

读取 data/persons/*.yaml（全部 published 人物卡，含少数特例收录者），合并 stories / events / 比对索引三处信号，
生成 site/public/data/galaxy.json —— 供方案三（星图可视化）渲染用。

由 site/astro.config.mjs 的 galaxy-data 集成在 `astro build` / `astro dev` 时自动调用，
也可手动复跑：
    /Users/mba/.workbuddy/binaries/python/envs/default/bin/python scripts/build_galaxy.py

产物为生成物，勿手改。

星点字段（短写，体积约束 ≤100KB）：
    s  slug（= person.id，页面 URL 主键）
    n  姓名
    d  朝代原文（含 五代十国/西夏 等，tooltip 展示用）
    ey 科年（exam_year，tooltip 三套纪年的公元年）
    x  渲染横坐标（= ey；星图无生年需求）
    y  朝代分带序号 0-7（唐/五代/宋/辽/金/元/明/清）
    t  亮度 tier：0=有故事 > 1=全字段档案 > 2=confirmed 速览 > 3=suspect > 4=missing
    gz 干支（缺时按 (year-4)%60 补算，与 scripts/era.py 同算法）
    rg 年号（预留，多数为 null；前端可按 REIGNS 表换算）
    st 故事 slug（仅 t=0 星携带：该人物所属首篇已发布故事，供弹卡「阅读他的故事」导流）

tier 判定优先级（自上而下，命中即止）：
    0  content/stories/*.md（status: published）frontmatter 的 persons 名单
    1  data/events/<id>.yaml 存在；或档案富度 ≥8
       （富度 = zi/hao/birth_year/death_year/native_hist/native_modern/bio_short/ke_ci/reign
        九字段非空计数 + 有效标签 1 分；「待核」「待整理」不计）
    2  索引 status = confirmed（zhuangyuan_index.yaml）
    3  索引 status = suspect；或索引无此人（手补卡，打印告警）
    4  索引 status = missing

朝代分带：唐/五代*/宋/辽/金/元/明/清 → 0-7；五代十国、五代后汉 等「五代」前缀归带 1。
其他政权（西夏/大西/太平天国等）按科年落入共存主政权带（取 BAND_RANGES 首个包含者：
西夏 1203→宋带，大西 1644→明带，太平天国 1853→清带），d 字段保留原朝代名。

索引匹配三级策略（索引 slug 为逐字拼音，person id 为连写拼音，两套命名并存）：
    1. slug 直配 → 2. (姓名, 科年) 配 → 3. 索引内唯一姓名配
科年阙如（金代集中，年分「待核」）时尝试从索引回补；两边皆阙则剔除该星点并告警
（缺载是合法数据状态，不编造坐标）。
"""
import glob
import json
import os
import re
import sys
from datetime import date

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'site', 'public', 'data', 'galaxy.json')
SIZE_LIMIT = 100 * 1024  # 100KB 硬约束

BANDS = ['唐', '五代', '宋', '辽', '金', '元', '明', '清']
TIERS = ['story', 'full', 'confirmed', 'suspect', 'missing']
X_RANGE = [600, 1910]

# 朝代 → 分带号；五代前缀（五代十国/五代后汉…）统一归 1
DYNASTY_BAND = {'唐': 0, '宋': 2, '辽': 3, '金': 4, '元': 5, '明': 6, '清': 7}

# 其他政权落带用的朝代年表（起止含两端；重叠时取列表首个 → 主政权优先）
BAND_RANGES = [
    (0, 618, 906), (1, 907, 979), (2, 960, 1279), (3, 907, 1125),
    (4, 1115, 1234), (5, 1271, 1368), (6, 1368, 1644), (7, 1636, 1912),
]

STEMS = '甲乙丙丁戊己庚辛壬癸'
BRANCHES = '子丑寅卯辰巳午未申酉戌亥'


def ganzhi_of(year):
    i = (year - 4) % 60
    return STEMS[i % 10] + BRANCHES[i % 12]


def load_yaml(path):
    with open(path, encoding='utf-8') as f:
        return yaml.safe_load(f)


def band_of(dynasty, exam_year):
    """朝代原文 → 分带号。未知政权按科年落共存主政权带。"""
    if dynasty in DYNASTY_BAND:
        return DYNASTY_BAND[dynasty]
    if dynasty and dynasty.startswith('五代'):
        return 1
    if exam_year:
        for band, start, end in BAND_RANGES:
            if start <= exam_year <= end:
                return band
    return None


def story_person_map():
    """已发布故事的人物 → 故事 slug 映射。

    同一人物出现在多篇时取「专篇优先」：persons 仅其一人的专篇 > 多人专题的主角位
    > 客串位；同级按 slug 字典序取先（确定性）。
    """
    solo = {}    # pid -> slug（专篇）
    first = {}   # pid -> slug（专题主角位）
    member = {}  # pid -> slug（客串位）
    for path in sorted(glob.glob(os.path.join(ROOT, 'content', 'stories', '*.md'))):
        slug = os.path.basename(path)[:-3]
        if slug.startswith('_'):
            continue
        text = open(path, encoding='utf-8').read()
        m = re.match(r'^---\r?\n([\s\S]*?)\r?\n---', text)
        if not m:
            continue
        fm = yaml.safe_load(m.group(1)) or {}
        if fm.get('status') != 'published':
            continue
        persons = fm.get('persons') or []
        for i, pid in enumerate(persons):
            if len(persons) == 1:
                solo.setdefault(pid, slug)
            elif i == 0:
                first.setdefault(pid, slug)
            else:
                member.setdefault(pid, slug)
    return {**member, **first, **solo}  # 后者优先级更高


RICH_FIELDS = ['zi', 'hao', 'birth_year', 'death_year', 'native_hist',
               'native_modern', 'bio_short', 'ke_ci', 'reign']
RICH_THRESHOLD = 8


def richness_of(p):
    """档案富度：九字段非空计数 + 有效标签（待核/待整理不算）1 分。"""
    s = sum(1 for f in RICH_FIELDS if p.get(f))
    tags = [t for t in (p.get('tags') or []) if t not in ('待核', '待整理')]
    return s + (1 if tags else 0)


def full_profile_ids():
    """有完整事件表（data/events/<id>.yaml）的人物 id 集。"""
    return {
        os.path.basename(f)[:-5]
        for f in glob.glob(os.path.join(ROOT, 'data', 'events', '*.yaml'))
        if not os.path.basename(f).startswith('_')
    }


def load_index():
    """比对索引：slug / (姓名,科年) / 唯一姓名 三级查找表。"""
    entries = load_yaml(os.path.join(ROOT, 'data', 'index', 'zhuangyuan_index.yaml'))
    by_slug = {e['slug']: e for e in entries}
    by_name_year = {}
    name_count = {}
    for e in entries:
        by_name_year[(e['name'], e.get('exam_year'))] = e
        name_count[e['name']] = name_count.get(e['name'], 0) + 1
    by_uniq_name = {e['name']: e for e in entries if name_count[e['name']] == 1}
    return by_slug, by_name_year, by_uniq_name


def main():
    persons = {}
    for path in sorted(glob.glob(os.path.join(ROOT, 'data', 'persons', '*.yaml'))):
        if os.path.basename(path).startswith('_'):
            continue
        p = load_yaml(path)
        if p.get('status') == 'draft':
            continue
        persons[p['id']] = p

    stories = story_person_map()
    fulls = full_profile_ids()
    by_slug, by_name_year, by_uniq_name = load_index()

    stars, dropped, no_index = [], [], []
    match_stats = {'slug': 0, 'name_year': 0, 'name': 0, 'none': 0}

    for pid, p in persons.items():
        # --- 索引匹配（三级） ---
        idx = by_slug.get(pid)
        if idx:
            match_stats['slug'] += 1
        else:
            idx = by_name_year.get((p['name'], p.get('exam_year')))
            if idx:
                match_stats['name_year'] += 1
            else:
                idx = by_uniq_name.get(p['name'])
                if idx:
                    match_stats['name'] += 1
                else:
                    match_stats['none'] += 1
                    no_index.append(pid)

        # --- 科年：person 优先，阙如从索引回补；皆阙则剔除 ---
        year = p.get('exam_year') or (idx or {}).get('exam_year')
        if not year:
            dropped.append((pid, p['name'], p.get('dynasty')))
            continue

        # --- tier：故事 > 全档案（events 或富度≥8）> 索引比对状态 ---
        if pid in stories:
            tier = 0
        elif pid in fulls or richness_of(p) >= RICH_THRESHOLD:
            tier = 1
        elif idx:
            tier = {'confirmed': 2, 'suspect': 3, 'missing': 4}.get(idx.get('status'), 3)
        else:
            tier = 3  # 索引无此人（手补卡）：按 suspect 处理

        band = band_of(p.get('dynasty'), year)
        if band is None:
            dropped.append((pid, p['name'], p.get('dynasty')))
            continue

        star = {
            's': pid,
            'n': p['name'],
            'd': p.get('dynasty'),
            'ey': year,
            'x': year,
            'y': band,
            't': tier,
            'gz': p.get('ganzhi') or ganzhi_of(year),
            'rg': p.get('reign'),
        }
        if tier == 0:
            star['st'] = stories[pid]
        stars.append(star)

    stars.sort(key=lambda s: (s['x'], s['s']))

    doc = {
        'v': 1,
        'gen': date.today().isoformat(),
        'xr': X_RANGE,
        'bands': BANDS,
        'tiers': TIERS,
        'stars': stars,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    payload = json.dumps(doc, ensure_ascii=False, separators=(',', ':'))
    size = len(payload.encode('utf-8'))
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write(payload)

    # --- 报告 ---
    tier_n = [sum(1 for s in stars if s['t'] == i) for i in range(5)]
    band_n = [sum(1 for s in stars if s['y'] == i) for i in range(8)]
    print(f'[galaxy] 星点 {len(stars)} | 体积 {size/1024:.1f}KB / {SIZE_LIMIT//1024}KB')
    print('[galaxy] tier 分布 故事/全档案/confirmed/suspect/missing:',
          dict(zip(TIERS, tier_n)))
    print('[galaxy] 分带分布:', dict(zip(BANDS, band_n)))
    print('[galaxy] 索引匹配 slug/姓名+年/唯一姓名/无:',
          {k: v for k, v in match_stats.items()})
    if no_index:
        detail = ', '.join(
            f'{i}(tier={0 if i in stories else 1 if i in fulls else 3})'
            for i in sorted(no_index)
        )
        print('[galaxy] 索引无此人（手补卡，tier 按规则另计）:', detail)
    if dropped:
        print(f'[galaxy] 剔除 {len(dropped)} 人（科年阙如，金代年分待核段）:')
        for pid, name, dyn in dropped:
            print(f'  - {pid} {name} {dyn}')

    # --- 硬约束校验 ---
    errors = []
    if size > SIZE_LIMIT:
        errors.append(f'体积超限 {size} > {SIZE_LIMIT}')
    bad = [s['s'] for s in stars if not (X_RANGE[0] <= s['x'] <= X_RANGE[1])]
    if bad:
        errors.append(f'x 越界: {bad[:5]}')
    bad = [s['s'] for s in stars if not (0 <= s['y'] <= 7)]
    if bad:
        errors.append(f'y 越界: {bad[:5]}')
    if errors:
        for e in errors:
            print(f'[galaxy] ERROR: {e}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
