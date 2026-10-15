#!/usr/bin/env python3
"""关系网络数据切片生成器（build_network.py）

读取 data/relations/*.yaml（278 人有关系记录），生成
site/public/data/network.json —— 供 /network 关系网络图渲染用。

由 site/astro.config.mjs 的 network-data 集成在 `astro build` / `astro dev` 时自动调用，
也可手动复跑：
    /Users/mba/.workbuddy/binaries/python/envs/default/bin/python scripts/build_network.py

产物为生成物，勿手改。

────────────────────────── 双层口径 ──────────────────────────
overlay=false（默认视图）  纯状元网络：只含 from→to 两端都是本谱人物的边。
overlay=true               叠加名士层：额外加入外部人物节点（银色）。
                           外部人物按「与其有关系的状元人数」降序取 top，
                           且总节点数硬约束 ≤ MAX_NODES(300)；当前口径为度数 ≥3。

外部人物在源数据里以 to_id=cbdb:NNNNN 出现，姓名藏在 note 里
（形如「墓誌銘由Y所作：錢大昕（CBDB 外部人物）」），本脚本解析出来做节点名。

──────────────────────────「其他」细分 ──────────────────────────
源数据 type 枚举只有 9 类，但 3000 条「其他」里绝大多数其实是可归类的。
本脚本按 note 的标签前缀（第一个全角冒号前的部分）做两级判定：
  1. 精确命中 TXT_EXACT / KIN_EXACT 表 → 文字缘 / 亲缘
  2. 未命中则按关键词子串兜底（TXT_KW / KIN_KW）
  3. 仍未命中 → 保留「其他」
「文字缘」= 撰述·书问·题赠·唱和一类以文字为媒介的往来（墓誌銘/作序/書跋/致書/贈詩…）。
「亲缘」= 源数据误挂在「其他」下的亲属标签（丈夫/母/女兒/繼母…）；
        它归入既有的「亲缘」筛选组（父子·兄弟·翁婿），避免把亲属关系埋进「其他」。
细分只改写「其他」条目，其余 8 类原样保留。

────────────────────────── 输出结构（短键省体积） ──────────────────────────
    v/gen         版本号 / 生成日期
    types         细分后的类型名表（边 y 为此表下标）
    groups        筛选组：[[类型下标…]…]，前端 chips 一组一个
    gname         筛选组名
    def           groups 默认是否勾选（「其他」= 0）
    nodes[]        {s 主键 / n 姓名 / d 朝代 / ey 科年 / t tier / k 0=状元1=名士 / g 度数}
    edges[]        [a 起点下标, b 终点下标, gi 组下标, yi 类型下标, l 关系标签]
    stats          规模与切割口径（供页面文案与告警核对）
    meta          源数据事实（有向条目数 / 无向对数 / 外部人物总数 / 剔除阈值）

tier 沿用 scripts/build_galaxy.py 的口径（0 有故事 > 1 全档案 > 2 confirmed > 3 suspect
> 4 missing），名士节点 t=-1，保证 /network 与 /galaxy 光度语义一致。
"""
import collections
import glob
import json
import os
import re
import sys
from datetime import date

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'site', 'public', 'data', 'network.json')

SIZE_LIMIT = 220 * 1024   # 体积硬约束（名士层全展开仍须轻量）
MAX_NODES = 300           # 总节点硬约束（含名士层）
EXT_MIN_DEG = 3           # 名士层准入：与该名士有关系的状元人数下限
EDGE_WARN = 100           # 状元间边数低于此值打告警
LABEL_MAX = 26            # 关系标签截断长度

# ── 类型表（顺序即前端色板顺序）──────────────────────────────
TYPES = ['同年', '师生', '父子', '兄弟', '翁婿', '友人', '同僚', '政敌', '文字缘', '亲缘', '其他']
TYPE_IDX = {t: i for i, t in enumerate(TYPES)}

# ── 筛选组（chips 即按组渲染；亲缘组收拢父子/兄弟/翁婿/亲缘四类）────
GROUPS = [
    ('同年', ['同年']),
    ('师生', ['师生']),
    ('亲缘', ['父子', '兄弟', '翁婿', '亲缘']),
    ('友人', ['友人']),
    ('同僚', ['同僚']),
    ('政敌', ['政敌']),
    ('文字缘', ['文字缘']),
    ('其他', ['其他']),
]
# 「其他」类默认不勾选，防毛线团
GROUP_DEFAULT_OFF = {'其他'}

# ────────────────── 「其他」细分词表 ──────────────────
# 文字缘：以文字为媒介的往来（撰述 / 书问 / 题赠 / 唱和 / 哀祭）
TXT_EXACT = {
    '致書Y', '答Y書', '答Y啓', '致Y啓',
    '贈詩、文', '為Y作臨別贈言(送別詩、序)', '為Y作祝詞', '贈Y物',
    '為Y所著書作序', '為Y所作詩文作序', '家譜由Y作序', '神道碑序由Y所作',
    '墓表序由Y所作', '請Y作序、記', '求Y為他人（第三方）作墓誌銘',
    '書跋由Y所作', '為Y之書、畫作跋', '為Y之詩文作跋', '為Y之書題詞',
    '為Y之建築物題詠、記、命名', '為Y作祠記', '為Y作佛寺記',
    '為Y作廟碑記', '為Y作世系碑記', '為Y建立祠廟', '為Y之生祠作記',
    '學記（書院記）由Y所作', '義莊記由Y所作',
    '墓誌銘由Y所作', '墓表由Y所作', '神道碑由Y所作', '壙記由Y所作',
    '碑陰為Y所作', '題Y之墓',
    '行狀由Y所作', '傳記作者為Y', '家傳為Y所作', '年譜由Y所作',
    '畫贊(畫像記)由Y所作', '為Y篆匾額、器銘', '齋、堂銘由Y所作',
    '諡議由Y所作', '為Y作字說、名述', '為Y作名說',
    '為Y作祭文', '哀辭由Y所作', '為Y作哀辭 [併入167]', '挽詩、詞由Y所作',
    '合撰(編)著作', '編輯Y之詩/文', '編輯Y的學術作品', '校訂Y之著述',
    '評論Y之著作', '神道碑的書法由Y所作', '神道碑額篆由Y所作',
}
TXT_KW = ('墓誌銘', '墓表', '神道碑', '行狀', '壙記', '傳記作者', '家傳',
          '年譜', '哀辭', '挽詩', '祭文', '諡議', '作序', '書跋', '作跋',
          '題詠', '字說', '名說', '學記', '祠記', '廟碑', '碑記', '畫贊',
          '畫像記', '唱和', '贈詩', '致書', '答Y書', '答Y啓', '致Y啓',
          '臨別贈言', '為Y所作詩文', '題Y之墓', '校訂Y之著述', '合撰')

# 亲缘：源数据误挂在「其他」下的亲属标签
KIN_EXACT = {
    '丈夫', '母', '繼母', '嫡母', '嗣母', '女兒', '長女', '二女', '三女',
    '母舅', '姐夫', '同族長輩', '族人(輩分不詳)', '妻之叔伯',
    '第一任妻之叔伯', '姻親',
}
KIN_KW = ('丈夫', '妻子', '繼母', '嫡母', '嗣母', '母舅', '女兒', '長女',
          '二女', '三女', '姐夫', '族長輩', '族人', '妻之叔伯', '姻親')

LABEL_NOISE = re.compile(r'（CBDB）|\(CBDB\)|\s*\[併入\d+\]|，始年\s*\d+')
# 展示用清洗：保留「，始年 1789」这类有效信息，只去掉来源标记
NOTE_CLEAN = re.compile(r'（CBDB）|\(CBDB\)|\s*\[併入\d+\]')
# 外部人物姓名同样带来源标记，须一并洗净，否则页面上会显示「葉向高（CBDB 外部人物）」
NAME_NOISE = re.compile(r'（CBDB[^）]*）|\(CBDB[^)]*\)|，始年\s*\d+')
NAME_RE = re.compile(r'[：:]\s*([^（(]+)')
SLUG_RE = re.compile(r'^[a-z0-9_]+$')


def load_yaml(path):
    with open(path, encoding='utf-8') as f:
        return yaml.safe_load(f)


def clean_note(note):
    """note → 界面可读的关系说明。

    CBDB 导出用 Y 作占位符指代「对方」（即该条关系的另一端），直接上屏会读成
    「為Y之幕僚」，故替换为「對方」；再洗掉 （CBDB） 之类来源标记。
    """
    s = NOTE_CLEAN.sub('', (note or '').strip())
    return s.replace('Y', '對方').strip()


def split_label(note):
    """note → (标签, 外部人物姓名)。两处都要洗掉 CBDB 来源标记。"""
    raw = (note or '').strip()
    label = LABEL_NOISE.sub('', raw)
    name = ''
    sep = None
    for i, ch in enumerate(label):
        if ch in '：:':
            sep = i
            break
    if sep is not None:
        name = label[sep + 1:].strip()
        label = label[:sep].strip()
    if not label:
        label = NAME_RE.sub('', raw).strip() or '其他'
    label = LABEL_NOISE.sub('', label).strip()
    name = NAME_NOISE.sub('', name).strip()
    return label[:LABEL_MAX], name[:24]


def classify(raw_type, note):
    """源类型 → 细分后类型。只改写「其他」，其余原样。"""
    if raw_type != '其他':
        return raw_type if raw_type in TYPE_IDX else '其他'
    label, _ = split_label(note)
    if label in TXT_EXACT or any(k in label for k in TXT_KW):
        return '文字缘'
    if label in KIN_EXACT or any(k in label for k in KIN_KW):
        return '亲缘'
    return '其他'


def tier_for(pid, p, idx, stories, fulls, G):
    """与 build_galaxy.py 同口径的 tier 判定。"""
    if pid in stories:
        return 0
    if pid in fulls or G.richness_of(p) >= G.RICH_THRESHOLD:
        return 1
    if idx:
        return {'confirmed': 2, 'suspect': 3, 'missing': 4}.get(idx.get('status'), 3)
    return 3


def main():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import build_galaxy as G  # 复用 tier 判定与故事映射，保证与 /galaxy 光度语义一致

    # ── 一、本谱人物 ──────────────────────────────
    persons = {}
    for path in sorted(glob.glob(os.path.join(ROOT, 'data', 'persons', '*.yaml'))):
        if os.path.basename(path).startswith('_'):
            continue
        p = load_yaml(path)
        if not p or p.get('status') == 'draft':
            continue
        persons[p['id']] = p

    stories = G.story_person_map()
    fulls = G.full_profile_ids()
    by_slug, by_name_year, by_uniq_name = G.load_index()

    def lookup_idx(pid, p):
        return (by_slug.get(pid)
                or by_name_year.get((p['name'], p.get('exam_year')))
                or by_uniq_name.get(p['name']))

    # ── 二、扫 relations，分内/外两类 ──────────────────
    rel_files = [f for f in sorted(glob.glob(os.path.join(ROOT, 'data', 'relations', '*.yaml')))
                 if not os.path.basename(f).startswith('_')]

    inner_entries = []            # (from, to, type, label, note)
    outer_entries = []            # (from, ext_id, type, label, name)
    self_loops = []               # (from_id, type, note) —— 源数据缺陷，剔除并报出
    type_raw = collections.Counter()
    type_final_all = collections.Counter()
    unmatched_from = set()

    for path in rel_files:
        d = load_yaml(path)
        if not d:
            continue
        fid = d.get('from_id')
        if fid not in persons:
            unmatched_from.add(fid)
            continue
        for r in (d.get('relations') or []):
            tid = r.get('to_id')
            if not tid:
                continue
            raw_type = r.get('type') or '其他'
            type_raw[raw_type] += 1
            label, name = split_label(r.get('note'))
            t = classify(raw_type, r.get('note'))
            type_final_all[t] += 1
            if tid in persons:
                if tid == fid:
                    self_loops.append((fid, raw_type, clean_note(r.get('note'))))
                    continue
                inner_entries.append((fid, tid, t, label, clean_note(r.get('note'))))
            else:
                outer_entries.append((fid, tid, t, label, name))

    # 状元↔状元：源数据大量「互指」（A→B 与 B→A 各一条），无向去重
    pair_map = {}
    for fid, tid, t, label, note in inner_entries:
        key = (min(fid, tid), max(fid, tid))
        pair_map.setdefault(key, {'type': t, 'label': label, 'notes': []})
        txt = clean_note(note) or label          # 展示用全文（互指记录去重后并列）
        if txt and txt not in pair_map[key]['notes']:
            pair_map[key]['notes'].append(txt)
    inner_pairs = [(a, b, v) for (a, b), v in sorted(pair_map.items())]

    # 外部人物度（以状元为计数单位；同一状元重复关系只记一次）
    ext_pairs = {}   # (from, ext) → {'type','label','name'}
    for fid, tid, t, label, name in outer_entries:
        ext_pairs.setdefault((fid, tid), {'type': t, 'label': label, 'name': name})
    ext_deg = collections.Counter()
    ext_name = {}
    ext_partners = collections.defaultdict(set)
    for fid, tid in ext_pairs:
        ext_deg[tid] += 1
        ext_partners[tid].add(fid)
        if ext_pairs[(fid, tid)]['name']:
            ext_name.setdefault(tid, ext_pairs[(fid, tid)]['name'])

    inner_nodes = {n for pair in inner_pairs for n in pair[:2]}

    # ── 三、名士层取数 ───────────────────────────────
    # 度数降序贪心；每个候选人会连带引入「只与名士相连」的状元（这类状元在默认
    # 视图里没有边、不可见，仅在名士层出现），预算按 状元+名士 总数封顶 MAX_NODES。
    ext_picked, zy_extra = [], set()
    for tid, deg in sorted(ext_deg.items(), key=lambda kv: (-kv[1], kv[0])):
        if deg < EXT_MIN_DEG:
            break
        gain = ext_partners[tid] - inner_nodes - zy_extra
        if len(inner_nodes) + len(zy_extra) + len(gain) + len(ext_picked) + 1 > MAX_NODES:
            continue
        ext_picked.append(tid)
        zy_extra |= gain
    ext_set = set(ext_picked)
    zy_nodes = inner_nodes | zy_extra

    # ── 四、装节点 ────────────────────────────────
    def make_node(pid):
        p = persons[pid]
        idx = lookup_idx(pid, p)
        return {
            's': pid,
            'n': p['name'],
            'd': p.get('dynasty') or '',
            'ey': p.get('exam_year') or 0,
            't': tier_for(pid, p, idx, stories, fulls, G),
            'k': 0,
            'g': 0,
        }

    nodes = []
    index = {}
    for pid in sorted(zy_nodes):
        index[pid] = len(nodes)
        nodes.append(make_node(pid))
    for tid in sorted(ext_set):
        index[tid] = len(nodes)
        nodes.append({
            's': tid,
            'n': ext_name.get(tid) or tid.replace('cbdb:', 'CBDB:'),
            'd': '',
            'ey': 0,
            't': -1,
            'k': 1,
            'g': 0,
        })

    # ── 五、装边 ──────────────────────────────────
    edges, deg = [], collections.Counter()

    def group_of(t):
        for gi, (_, members) in enumerate(GROUPS):
            if t in members:
                return gi
        return len(GROUPS) - 1

    for a, b, v in inner_pairs:                     # 状元—状元
        edges.append([index[a], index[b], group_of(v['type']), TYPE_IDX[v['type']],
                      (' · '.join(v['notes'])[:LABEL_MAX] if v['notes'] else v['type'])])
        deg[a] += 1
        deg[b] += 1
    for (fid, tid), v in sorted(ext_pairs.items()):  # 状元—名士（仅取中选者）
        if tid not in ext_set:
            continue
        a, b = index[fid], index[tid]
        edges.append([a, b, group_of(v['type']), TYPE_IDX[v['type']], clean_note(v['label'])])
        deg[fid] += 1
        deg[tid] += 1
    for nd in nodes:
        nd['g'] = deg.get(nd['s'], 0)

    # 孤立名士（选中但边被去重掉）理论上不存在；保底校验
    linked = {i for e in edges for i in e[:2]}
    dropped_orphan = [nodes[i]['s'] for i in range(len(nodes)) if i not in linked]

    # ── 六、落盘 ──────────────────────────────────
    doc = {
        'v': 1,
        'gen': date.today().isoformat(),
        'types': TYPES,
        'groups': [[TYPE_IDX[t] for t in members] for _, members in GROUPS],
        'gname': [name for name, _ in GROUPS],
        'def': [0 if name in GROUP_DEFAULT_OFF else 1 for name, _ in GROUPS],
        'nodes': nodes,
        'edges': edges,
        'stats': {
            'nZy': len(inner_nodes),          # 默认视图的状元节点数
            'nZyAll': len(zy_nodes),          # 名士层展开后的状元节点数
            'nExt': len(ext_set),
            'eInner': len(inner_pairs),
            'eExt': len(edges) - len(inner_pairs),
            'relFiles': len(rel_files),
            'zyTotal': len(persons),
            'zyWithRel': len({fid for fid, _ in ext_pairs} | inner_nodes),
            'edgeWarn': EDGE_WARN,
        },
        'meta': {
            'innerEntries': len(inner_entries) + len(self_loops),
            'innerEntriesValid': len(inner_entries),
            'innerPairs': len(inner_pairs),
            'selfLoops': len(self_loops),
            'extEntries': len(outer_entries),
            'extAll': len(ext_deg),
            'extMinDeg': EXT_MIN_DEG,
            'maxNodes': MAX_NODES,
            'typesRaw': dict(sorted(type_raw.items(), key=lambda kv: -kv[1])),
        },
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    payload = json.dumps(doc, ensure_ascii=False, separators=(',', ':'))
    size = len(payload.encode('utf-8'))
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write(payload)

    # ── 七、报告 ──────────────────────────────────
    inner_raw = len(inner_entries) + len(self_loops)
    t_final = collections.Counter(TYPES[e[3]] for e in edges)
    t_inner = collections.Counter(v['type'] for _, _, v in inner_pairs)
    print(f'[network] 节点 {len(nodes)}（状元 {len(zy_nodes)}：默认视图可见 {len(inner_nodes)} + '
          f'仅名士层 {len(zy_extra)}；名士 {len(ext_set)}）| '
          f'边 {len(edges)}（状元间 {len(inner_pairs)} + 状元—名士 {len(edges) - len(inner_pairs)}）'
          f'| 体积 {size / 1024:.1f}KB / {SIZE_LIMIT // 1024}KB')
    print(f'[network] 源数据：关系文件 {len(rel_files)} | 状元间有向条目 {inner_raw}'
          f'（有效 {len(inner_entries)}，自环 {len(self_loops)} → 去重后 {len(inner_pairs)} 对无向边）'
          f' | 状元→外部条目 {len(outer_entries)}'
          f'（外部人物 {len(ext_deg)} 人，取度数 ≥{EXT_MIN_DEG} 者 {len(ext_set)} 人）')
    print(f'[network] 原类型分布: {doc["meta"]["typesRaw"]}')
    print(f'[network] 细分后·状元间边: {dict(t_inner)}')
    print(f'[network] 细分后·入图边: {dict(t_final)}')
    print(f'[network] 「其他」细分：源 {type_raw.get("其他", 0)} 条 → 文字缘 '
          f'{type_final_all.get("文字缘", 0)} / 亲缘 {type_final_all.get("亲缘", 0)} / '
          f'保留其他 {type_final_all.get("其他", 0)}（全量 5000 条口径）；'
          f'其中入图 {t_final.get("文字缘", 0)}/{t_final.get("亲缘", 0)}/{t_final.get("其他", 0)}')
    if self_loops:
        print(f'[network] WARN 源数据自环 {len(self_loops)} 条（to_id == from_id，'
              f'已剔除，建议修 data/relations/）: '
              f'{", ".join(f"{a}({t})" for a, t, _ in self_loops)}')
    if unmatched_from:
        print(f'[network] 跳过 {len(unmatched_from)} 个未知 from_id: '
              f'{", ".join(sorted(unmatched_from)[:8])}')
    if dropped_orphan:
        print(f'[network] WARN 孤立节点（无任何边，建议剔除）: {dropped_orphan[:8]}')

    # ── 八、告警与硬约束 ───────────────────────────
    if inner_raw < EDGE_WARN:
        print(f'[network] WARNING 状元间关系仅 {inner_raw} 条 '
              f'< {EDGE_WARN}（去重后 {len(inner_pairs)} 对无向边）：'
              f'纯状元网络偏稀疏，页面须显式提示「展开名士层」以补足连通性。',
              file=sys.stderr)
    else:
        print(f'[network] 状元间关系 {inner_raw} 条 ≥ {EDGE_WARN}，无需告警')

    errors = []
    if size > SIZE_LIMIT:
        errors.append(f'体积超限 {size} > {SIZE_LIMIT}')
    if len(nodes) > MAX_NODES:
        errors.append(f'节点数超限 {len(nodes)} > {MAX_NODES}')
    bad = [i for e in edges for i in e[:2] if not (0 <= i < len(nodes))]
    if bad:
        errors.append(f'边端点越界: {bad[:5]}')
    bad = [n['s'] for n in nodes if not (n['k'] == 1 or SLUG_RE.match(n['s']))]
    if bad:
        errors.append(f'状元节点 slug 异常: {bad[:5]}')
    if dropped_orphan:
        errors.append(f'存在孤立节点: {dropped_orphan[:5]}')
    if errors:
        for e in errors:
            print(f'[network] ERROR: {e}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
