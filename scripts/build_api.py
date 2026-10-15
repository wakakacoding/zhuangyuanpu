#!/usr/bin/env python3
"""公开数据 API 导出器（build_api.py）

把 data/ 数据底座导出为静态 API，供第三方复用与引证：

    site/public/api/persons.json          全量精简字段（一人一行；含 role 字段以分辨状元与特例）
    site/public/api/persons.csv           同上，CSV 版（UTF-8 无 BOM）
    site/public/api/persons/<slug>.json   单人全字段（含 events/works/anecdotes/relations/sources）
    site/public/api/index.json            清单：版本、许可、条目数、端点表
    site/public/api/README.md             数据字典 + 分层许可说明
                                          （自主编纂内容 CC BY-SA 4.0 / CBDB 派生数据 CC BY-NC-SA 4.0）

由 site/astro.config.mjs 的 api-data 集成在 `astro build` / `astro dev` 时自动调用，
也可手动复跑：
    /Users/mba/.workbuddy/binaries/python/envs/default/bin/python scripts/build_api.py

产物为生成物，勿手改（每次构建整目录重建，删除的人物卡不会残留）。

纪律：导出内容一律取自 data/ 原始 YAML，不做任何加工、补全或推测；
字段为空即输出 null / 空串——「史料阙如」是合法数据状态。
"""
import csv
import glob
import json
import os
import shutil
import sys
from datetime import date

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_DIR = os.path.join(ROOT, 'site', 'public', 'api')
DETAIL_DIR = os.path.join(API_DIR, 'persons')

SITE_URL = 'https://wakakacoding.github.io/zhuangyuanpu/'

# ---------------------------------------------------------------------------
# 分层许可（R0-1 / R0-2）
#   ① 本站自主编纂内容 → CC BY-SA 4.0（含商用）
#   ② CBDB 派生数据     → CC BY-NC-SA 4.0（不得商用，须署名 CBDB）
#   ③ 史料原文          → 不在上述任一授权范围内
# 依据：CBDB Data Licensing Terms（2026-08-20 生效；属「当前单机版范围内」的数据适用 CC BY-NC-SA 4.0）
# ---------------------------------------------------------------------------
LICENSE = 'CC BY-SA 4.0'
LICENSE_URL = 'https://creativecommons.org/licenses/by-sa/4.0/deed.zh'
LICENSE_CBDB = 'CC BY-NC-SA 4.0'
LICENSE_CBDB_URL = 'https://creativecommons.org/licenses/by-nc-sa/4.0/deed.zh'
CBDB_NAME = '中国历代人物传记资料库（China Biographical Database Project, CBDB）'
CBDB_HOME = 'https://cbdb.hsites.harvard.edu/'
CBDB_TERMS = 'https://cbdb.hsites.harvard.edu/cbdb-data-licensing-terms'

# 所用 CBDB 数据版本：官方单机版 SQLite 发行版（sha256 与官方仓库 latest.json 一致，非私人副本）
CBDB_RELEASE = 'cbdb_20261010（SQLite 单机版，生成于 2026-10-10）'
CBDB_DERIVED_FIELDS = [
    'fl_year', 'birth_year', 'death_year', 'zi', 'hao',
    'native_hist', 'native_modern', 'relations',
]
CBDB_ATTRIBUTION = (
    f'本数据集中取自{CBDB_NAME}的字段（{" / ".join(CBDB_DERIVED_FIELDS)}）'
    f'依 CC BY-NC-SA 4.0 使用：须注明 CBDB 为数据来源并标明所用版本，不得用于商业目的，'
    f'改编后须以相同协议发布。版本：{CBDB_RELEASE}；条款：{CBDB_TERMS}'
)
LICENSE_NOTE = (
    '分层许可：本站自主编纂内容（考证、编排、标点、长篇故事、事件/著作/轶事/出处的登记、人工关系条目）'
    '为 CC BY-SA 4.0，含商用；CBDB 派生数据为 CC BY-NC-SA 4.0，不含商用（须署名 CBDB）；'
    '史料原文（sources[].quote）不在上述任一授权范围内。'
)
API_VERSION = 1


def license_meta():
    """分层许可元数据（persons.json / index.json 的 meta 与单人 JSON 共用同一口径）。"""
    return {
        'license': LICENSE,
        'license_url': LICENSE_URL,
        'license_note': LICENSE_NOTE,
        'cbdb_license': LICENSE_CBDB,
        'cbdb_license_url': LICENSE_CBDB_URL,
        'cbdb_attribution': CBDB_ATTRIBUTION,
        'cbdb_source': CBDB_NAME,
        'cbdb_source_url': CBDB_HOME,
        'cbdb_license_terms': CBDB_TERMS,
        'cbdb_release': CBDB_RELEASE,
        'cbdb_derived_fields': CBDB_DERIVED_FIELDS,
    }


def license_meta_compact():
    """单人 JSON 用的精简许可元数据（完整声明见 index.json 与 README.md）。"""
    return {
        'license': LICENSE,
        'cbdb_license': LICENSE_CBDB,
        'cbdb_attribution': CBDB_ATTRIBUTION,
    }


# 精简字段（persons.json / persons.csv 的列序即此序）
SLIM_FIELDS = [
    ('id', 'slug，与档案页 URL /persons/<id>/ 一致，亦为单人 JSON 文件名'),
    ('name', '姓名'),
    ('zi', '字（经索引带入者源自 CBDB ALTNAME_DATA）'),
    ('hao', '号（经索引带入者源自 CBDB ALTNAME_DATA）'),
    ('dynasty', '朝代（原文，含「五代十国」等）'),
    ('reign', '年号（夺魁之年所在年号）'),
    ('exam_year', '科年（公元，夺魁之年）'),
    ('ganzhi', '科年干支'),
    ('ke_ci', '科次原文，如「武德五年壬午科」'),
    ('rank_detail', '名次原文，如「一甲第一名（状元）」'),
    ('role', '名录身份：zhuangyuan 状元 / tanhua 探花 / de_facto 事实状元。'
             '导出时已归一——原始 YAML 缺省即为状元，此处显式写出；'
             '统计状元时应筛 role=zhuangyuan，勿把人物卡总数当状元数'),
    ('birth_year', '生年（公元，含 CBDB 机器回填部分）'),
    ('death_year', '卒年（公元，含 CBDB 机器回填部分）'),
    ('fl_year', '活动年（CBDB 估算，BIOG_MAIN.c_index_year，多用于生年阙如者）'),
    ('native_hist', '籍贯（史料原文地名；CBDB BIOG_ADDR_DATA 优先，名录兜底）'),
    ('native_modern', '籍贯今地名（与上一字段同源）'),
    ('lat', '纬度（WGS84，籍贯今地近似点）'),
    ('lng', '经度（WGS84）'),
    ('bio_short', '一句话小传；阙如时为 null'),
    ('tags', '标签数组；无标签为 []'),
]

# 单人 JSON 里 person 对象的完整字段（= 精简 + 以下）
FULL_EXTRA_FIELDS = [
    ('status', '卡片状态：published / draft'),
    ('verified_absent', '「史料阙如」人工认定：true = 已查证确认无传世记载；'
                        '缺省/null = 尚未整理。据此可分辨「整理进度」与「历史结论」'),
]

SUB_DOCS = {
    'events': ('events', '生平事件（每条带 source_ids 出处编号）'),
    'works': ('works', '著作'),
    'anecdotes': ('anecdotes', '轶事（与史实物理隔离，默认 C 级）'),
    'relations': ('relations', '人物关系（to_id 前缀 cbdb: 表示 CBDB 外部人物）'),
}


def load_yaml(path):
    with open(path, encoding='utf-8') as f:
        return yaml.safe_load(f)


def list_yaml(dirname):
    """列出某数据目录下的全部条目（跳过 _ 前缀模板）。"""
    out = []
    for path in sorted(glob.glob(os.path.join(ROOT, 'data', dirname, '*.yaml'))):
        if os.path.basename(path).startswith('_'):
            continue
        out.append((os.path.basename(path)[:-5], load_yaml(path) or {}))
    return out


def person_records():
    """全量人物卡，按科年升序（阙如排尾）、再按 id 稳定排序。"""
    recs = list_yaml('persons')
    recs = [(pid, p) for pid, p in recs if p.get('status') != 'draft' and p.get('id')]
    recs.sort(key=lambda t: (t[1].get('exam_year') or 9999, t[0]))
    return recs


def sub_docs(pid):
    """某人的 events / works / anecdotes / relations 列表（无文件则为空表）。"""
    out = {}
    for dirname, (key, _) in SUB_DOCS.items():
        f = os.path.join(ROOT, 'data', dirname, f'{pid}.yaml')
        doc = load_yaml(f) if os.path.exists(f) else None
        out[key] = (doc or {}).get(key) or []
    return out


def slim_of(p):
    """精简字段视图。"""
    row = {}
    for k, _ in SLIM_FIELDS:
        v = p.get(k)
        row[k] = [] if (k == 'tags' and v is None) else v
    # role 归一：原始 YAML 缺省即状元，导出时显式化——免得消费方还要知道默认约定
    row['role'] = p.get('role') or 'zhuangyuan'
    return row


def tag_str(v):
    return '｜'.join(v) if v else ''


def csv_cell(v):
    if v is None:
        return ''
    if isinstance(v, list):
        return tag_str(v)
    if isinstance(v, bool):
        return 'true' if v else 'false'
    return str(v)


def build(dump_all=True):
    persons = person_records()
    if not persons:
        print('[api] ERROR: data/persons 为空', file=sys.stderr)
        return 1

    # --- 出处字典（单人 JSON 内联其引用到的出处，便于离线引用） ---
    sources = dict(list_yaml('sources'))

    if os.path.isdir(API_DIR):
        shutil.rmtree(API_DIR)
    os.makedirs(DETAIL_DIR, exist_ok=True)

    # --- 1. persons.json（全量精简） ---
    slim_rows = [slim_of(p) for _, p in persons]
    index_doc = {
        'meta': {
            'v': API_VERSION,
            'generated': date.today().isoformat(),
            'source': SITE_URL,
            **license_meta(),
            'count': len(slim_rows),
            'note': '每次站点构建重新生成；字段含义见 README.md 数据字典。',
            'detail_endpoint': 'persons/{id}.json',
        },
        'persons': slim_rows,
    }
    write(os.path.join(API_DIR, 'persons.json'), json.dumps(index_doc, ensure_ascii=False, separators=(',', ':')))

    # --- 2. persons.csv（同字段集，UTF-8 无 BOM） ---
    csv_path = os.path.join(API_DIR, 'persons.csv')
    with open(csv_path, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow([k for k, _ in SLIM_FIELDS])
        for row in slim_rows:
            w.writerow([csv_cell(row[k]) for k, _ in SLIM_FIELDS])

    # --- 3. persons/<slug>.json（单人全字段） ---
    detail_bytes = 0
    doc_bytes = {}
    sub_counts = {k: 0 for k in SUB_DOCS}
    for pid, p in persons:
        docs = sub_docs(pid)
        for k in SUB_DOCS:
            sub_counts[k] += len(docs[k])
        person = {k: p.get(k) for k, _ in SLIM_FIELDS}
        for k, _ in FULL_EXTRA_FIELDS:
            person[k] = p.get(k)
        person['tags'] = p.get('tags') or []
        person['url'] = f'{SITE_URL}persons/{pid}/'

        # 内联该人引用的全部出处（events/anecdotes 的 source_ids + relations 的 source_ids）
        used = set()
        for group in ('events', 'anecdotes', 'relations'):
            for item in docs[group]:
                for sid in item.get('source_ids') or []:
                    used.add(sid)
        inline = {}
        missing = sorted(used - set(sources))
        for sid in sorted(used & set(sources)):
            s = sources[sid]
            inline[sid] = {
                'id': s.get('id'), 'title': s.get('title'), 'tier': s.get('tier'),
                'juan': s.get('juan'), 'quote': s.get('quote'), 'url': s.get('url'),
                'note': s.get('note'),
            }

        doc = {
            'v': API_VERSION,
            'generated': index_doc['meta']['generated'],
            'source': SITE_URL,
            **license_meta_compact(),
            'person': person,
            'events': docs['events'],
            'works': docs['works'],
            'anecdotes': docs['anecdotes'],
            'relations': docs['relations'],
            'sources': inline,
        }
        payload = json.dumps(doc, ensure_ascii=False, separators=(',', ':'))
        write(os.path.join(DETAIL_DIR, f'{pid}.json'), payload)
        detail_bytes += len(payload.encode('utf-8'))
        doc_bytes[pid] = len(payload.encode('utf-8'))
        if missing:
            print(f'[api] WARN {pid}: source_ids 未登记 {missing}', file=sys.stderr)

    # --- 4. index.json 清单 ---
    manifest = {
        'v': API_VERSION,
        'generated': index_doc['meta']['generated'],
        'source': SITE_URL,
        **license_meta(),
        'counts': {
            'persons': len(persons),
            'person_files': len(doc_bytes),
            'sources': len(sources),
            'events': sub_counts['events'],
            'anecdotes': sub_counts['anecdotes'],
            'works': sub_counts['works'],
            'relations': sub_counts['relations'],
        },
        'endpoints': {
            'persons': 'persons.json',
            'persons_csv': 'persons.csv',
            'person_detail': 'persons/{id}.json',
            'readme': 'README.md',
        },
        'fields': [k for k, _ in SLIM_FIELDS],
    }
    write(os.path.join(API_DIR, 'index.json'), json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')

    # --- 5. README.md 数据字典（数字全部取自本次构建，不手写） ---
    # 数据字典里的单人 JSON 示例链接取「内容最丰者」，便于读者一眼看清全字段形态
    sample_id = max(doc_bytes.items(), key=lambda t: t[1])[0]
    sample_name = dict(persons)[sample_id].get('name') or sample_id
    write(os.path.join(API_DIR, 'README.md'), readme(manifest['counts'], sample_id, sample_name))

    # --- 报告 ---
    def kb(n):
        return f'{n / 1024:.1f}KB'

    print(f'[api] persons.json {kb(os.path.getsize(os.path.join(API_DIR, "persons.json")))}'
          f' | persons.csv {kb(os.path.getsize(csv_path))}'
          f' | 单人 JSON {len(doc_bytes)} 个 {kb(detail_bytes)}'
          f' | 合计 {kb(sum(os.path.getsize(os.path.join(API_DIR, f)) for f in os.listdir(API_DIR) if os.path.isfile(os.path.join(API_DIR, f))) + detail_bytes)}')
    print(f'[api] 条目数: ' + ', '.join(f'{k}={v}' for k, v in manifest['counts'].items()))
    top = sorted(doc_bytes.items(), key=lambda t: -t[1])[:3]
    print('[api] 单人 JSON 最大三:' + ', '.join(f'{k} {kb(v)}' for k, v in top))

    # --- 硬约束校验 ---
    errors = []
    for pid, p in persons:
        if not p.get('name'):
            errors.append(f'{pid} 无 name')
    if not os.path.getsize(os.path.join(API_DIR, 'persons.json')):
        errors.append('persons.json 为空')
    if len(slim_rows) != len(doc_bytes):
        errors.append(f'条目数不一致 {len(slim_rows)} vs {len(doc_bytes)}')
    if errors:
        for e in errors:
            print(f'[api] ERROR: {e}', file=sys.stderr)
        return 1
    return 0


def write(path, text):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


def readme(c, sample_id, sample_name):
    """数据字典 + 许可说明。"""
    slim_tbl = '\n'.join(f'| `{k}` | {desc} |' for k, desc in SLIM_FIELDS)
    extra_tbl = '\n'.join(f'| `{k}` | {desc} |' for k, desc in FULL_EXTRA_FIELDS)
    return f'''# 状元谱 · 开放数据 API

> 自唐武德五年（622）孙伏伽至清光绪三十年（1904）刘春霖，历代文状元的结构化人生轨迹数据。
> 本目录为**构建期生成物**，随站点每次构建刷新（当前版本 v{API_VERSION}，生成于 {date.today().isoformat()}）。

## 一、端点

| 端点 | 内容 | 当前条目数 |
|---|---|---|
| [`persons.json`](persons.json) | 全量**精简字段**，一行一人（含 `role`，可分离状元与特例） | {c['persons']} 张人物卡 |
| [`persons.csv`](persons.csv) | 同上，CSV 版（UTF-8 **无 BOM**，换行 LF） | {c['persons']} 行 + 表头 |
| [`persons/<id>.json`](persons/{sample_id}.json) | **单人全字段**：档案 + 生平事件 + 著作 + 轶事 + 关系 + 所引出处（示例：{sample_name}） | {c['person_files']} 个文件 |
| [`index.json`](index.json) | 清单：版本、生成日期、条目数、端点表 | — |

字段为空的语义：JSON 为 `null`（标签为 `[]`），CSV 为空串。**空值本身是合法数据状态**，不作推测填充；
但「没有值」有两层成因，引用时请分清：缺省 = **尚未整理**（本站进度），仅 `verified_absent: true` 者才是
**已经人工查证确认「史无明文」**。「史料阙如」这一表述只用于后者。

## 二、字段字典 · 精简字段（persons.json / persons.csv）

| 字段 | 含义 |
|---|---|
{slim_tbl}

`tags` 在 JSON 中为字符串数组，CSV 中为 `｜`（全角竖线）连接，如 `父子状元｜直谏`。

> **许可分层提示（重要）**：上表中 `zi` / `hao` / `birth_year` / `death_year` / `fl_year` /
> `native_hist` / `native_modern` 可能含 CBDB 派生值，属**第 ② 层**——CC BY-NC-SA 4.0，
> **不含商用**、须署名 CBDB；其余字段属**第 ① 层**——CC BY-SA 4.0，含商用。详见第五节。

## 三、单人全字段（persons/<id>.json）

顶层结构：

```json
{{
  "v": {API_VERSION},
  "generated": "YYYY-MM-DD",
  "source": "{SITE_URL}",
  "license": "{LICENSE}",
  "cbdb_license": "{LICENSE_CBDB}",
  "cbdb_attribution": "…CBDB 署名与版本声明…",
  "person":    {{ ...档案字段... }},
  "events":    [ ...生平事件... ],
  "works":     [ ...著作... ],
  "anecdotes": [ ...轶事... ],
  "relations": [ ...人物关系... ],
  "sources":   {{ "src_xxx": {{ ...出处原文... }} }}
}}
```

`person` 对象 = 精简字段 + `url`（本站档案页地址）+ 以下字段：

| 字段 | 含义 |
|---|---|
{extra_tbl}

**子文档字段**

- `events[]`：`year`（公元年）、`year_precision`（`exact` 精确 / `approx` 约）、`type`（授官/贬谪/夺魁…）、`title`、`description`、`source_ids[]`。**每条事件必挂出处，无出处的条目不入库。**
- `works[]`：`title`、`type`、`status`（存世/佚/待考）、`note`。
- `anecdotes[]`：`title`、`content`、`tier`、`source_ids[]`、`note`。轶事与史实**物理隔离**，默认 C 级，请勿与 `events` 混同视作史实。
- `relations[]`：`to_id`、`type`（同年/师生/父子/兄弟/翁婿/同僚/友人/政敌/其他）、`note`、`source_ids[]`。`to_id` 以 `cbdb:` 开头者为本站尚未立卡的外部人物（来源 CBDB），仅有编号、无姓名，引用时请自行核验。
- `sources{{}}`：以 `source_ids` 为键的出处字典，含 `title`、`tier`、`juan`（卷次）、`quote`（原文摘录）、`url`、`note`。

## 四、可信度分级（重要）

每条史料出处均标 A/B/C 三级，**引用本数据时请连带 `tier` 一并传播**，勿把 C 级当史实：

| 级别 | 范围 |
|---|---|
| **A** | 正史 / 进士题名碑 / 朱卷 / 登科录 —— 原始或接近原始的记录 |
| **B** | 地方志 / 年谱 / 墓志 / 回忆录 —— 二手但严肃的文献 |
| **C** | 笔记小说 / 民间传说 —— 与史实物理隔离，单独归入轶事 |

生卒年、籍贯有异说时，本站**并存多版本**并在 `note` 中标明分歧，不强行定论。

## 五、许可（分层，务必分别遵循）

本数据集是两层材料的叠加，授权不同；「许可层」与 JSON 顶层 `cbdb_derived_fields` 字段一一对应。

### 5.1 第 ① 层 · 本站自主编纂内容 —— CC BY-SA 4.0（含商用）

覆盖：人物档案的编纂与标点、A/B/C 三级考证结论、生平事件／著作／轶事与出处的登记编排、
人物关系的**人工条目**、长篇故事正文。

以 **CC BY-SA 4.0** 发布：{LICENSE_URL}
可自由复制、分发、改编（**含商用**），条件为：

1. **署名**：注明「数据来源：状元谱 {SITE_URL}」；
2. **相同方式共享**：改编后的数据集须以相同许可发布。

### 5.2 第 ② 层 · CBDB 派生数据 —— CC BY-NC-SA 4.0（**不含商用**，须署名 CBDB）

覆盖字段（即 JSON 顶层 `cbdb_derived_fields` 所列）：

| 字段 / 段落 | CBDB 来源 |
|---|---|
| `fl_year` | `BIOG_MAIN.c_index_year`（估算活动年） |
| `birth_year` / `death_year`（机器回填部分） | `BIOG_MAIN.c_birthyear` / `c_deathyear` |
| `zi` / `hao`（经索引带入者） | `ALTNAME_DATA`（类型 4=字 / 5=号） |
| `native_hist` / `native_modern`（CBDB 籍贯优先） | `BIOG_ADDR_DATA`（type=1） |
| `relations`（机器收割边，`to_id` 前缀 `cbdb:`） | `ASSOC_DATA` + `KIN_DATA` |

以 **CC BY-NC-SA 4.0** 发布：{LICENSE_CBDB_URL}

- **署名**：须注明数据来源为{CBDB_NAME}，并标明所用版本（{CBDB_RELEASE}）；
- **非商业**：**不得用于商业目的**；
- **相同方式共享**：改编后的数据集须以相同协议发布。

依据《CBDB Data Licensing Terms》（2026-08-20 生效）：属「当前单机版范围内」的 CBDB 数据适用
CC BY-NC-SA 4.0。条款原文：{CBDB_TERMS}　数据库主页：{CBDB_HOME}

> 口径：第 ② 层为**保守下限声明**——凡取值可能来自 CBDB 的字段一律计入；
> 个别记录实际另有名录或一手史料来源，以该条记录的出处链为准。

### 5.3 第 ③ 层 · 史料原文 —— 不在上述任一授权范围内

`sources[].quote` 等古籍摘录，版权属原书及其点校本，本站仅作考证性引用（合理使用），
转引请回查原书。

### 5.4 免责

本站对数据准确性不作担保；**引用前请回溯 `sources[].quote` 原文**，发现错误欢迎提勘误。

## 六、更新节奏

数据底座以 YAML + Git 版本管理，站点每次构建重新生成本目录。
条目数增长、字段修订都会同步反映在 `index.json` 的 `counts` 与 `generated` 字段。

本站不提供 API 密钥，无速率限制；请勿高频轮询，建议按周缓存。
'''


if __name__ == '__main__':
    sys.exit(build())
