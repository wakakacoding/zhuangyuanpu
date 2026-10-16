#!/usr/bin/env python3
"""一次性迁移：把展示层字段里的 CBDB 繁体文本转为简体（白名单字表，见 `t2s_safe.py`）。

为什么需要：`data/relations/*.yaml` 的 `note` 是 CBDB 原文（繁体），含「关系描述 + 外部人物
姓名」两段，被档案页与网络图直接上屏 → 简体页面夹繁体（实测 389 页可见文本含繁体）。

**范围（白名单）**
  · `data/relations/*.yaml`  → `relations[].note`、`relations[].type`
      （该目录下只有这两处含汉字；`to_id`/`src`/`direction`/`*_code` 均为 ASCII 或 slug）
  · `data/persons/*.yaml`    → `native_hist`、`native_modern`、`zi`、`hao`、`bio_short`
      （行级定位；`bio_short` 可能是 `>-` 块标量，按缩进块处理）
  · `data/geo_map.yaml`      → 全文（`hist` 是与 `persons.native_hist` 配对的键，
      实测 304 条中 124 条 `hist` 为繁体，不一起转会让 193 人丢掉 geo_map 关联 → validate 警告）

**明确不动**（改了会出事）
  · `sources[].quote`（史料原文，不在 CC 范围，必须保真）
  · `sources[].url`（wikisource 中文标题链接，改了 404）
  · `persons.name`（状元本名；含 刘煇/徐徵/张濆/杨紘/孔纁 5 个罕用字，转换产出扩展区字更差）
  · `persons.ke_ci` / `persons.reign`（含唐纪年「乾寧/乾祐」，OpenCC 会误转「干宁/干祐」）
  · `data/index/zhuangyuan_index.yaml` 的 `name_tw`（T8 成果，繁体名 by design）
  · `data/events|anecdotes|works|corrections/`（本站编纂，且可能内含史料引文如「饘粥不继」）

**枚举联动**：`祖孫` → `祖孙` 会改到受控枚举 type，必须与以下三处同批改：
  `scripts/validate.py:REL_TYPES` ／ `scripts/build_network.py:TYPES`+`GROUPS` ／
  `scripts/harvest_cbdb_relations.py` 的 `KIN_TYPES_NEW`/`TYPE_FOLD_LEGACY`/`KIN_MAP`

用法
    python scripts/migrate_t2s.py                 # dry-run（默认，只报告不写盘）
    python scripts/migrate_t2s.py --apply         # 写盘
    python scripts/migrate_t2s.py --root DIR      # 数据根，默认仓库根（测试用）
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from t2s_safe import SAFE_MAP, EXCLUDED, to_simple  # noqa: E402

PERSON_FIELDS = ('native_hist', 'native_modern', 'zi', 'hao', 'bio_short')
FIELD_RE = re.compile(r'^([A-Za-z_][A-Za-z0-9_]*):(.*)$')


def conv_rel_file(text: str) -> tuple[str, int]:
    """关系文件：全文字符级替换（该目录只有 note/type 含汉字）。"""
    out = to_simple(text)
    return out, sum(1 for a, b in zip(text, out) if a != b)


def conv_person_file(text: str) -> tuple[str, int]:
    """人物卡：只转白名单字段的行（含 `>-`/`|` 块标量的缩进块）。"""
    lines = text.split('\n')
    out, changed, in_block = [], 0, False
    for line in lines:
        if in_block:
            if line[:1] in (' ', '\t') and line.strip():
                nl = to_simple(line)
                changed += sum(1 for a, b in zip(line, nl) if a != b)
                out.append(nl)
                continue
            in_block = False
        m = FIELD_RE.match(line)
        if m and m.group(1) in PERSON_FIELDS:
            head, val = m.group(1), m.group(2)
            if val.strip()[:1] in ('>', '|'):
                in_block = True
                out.append(line)
                continue
            nv = to_simple(val)
            changed += sum(1 for a, b in zip(val, nv) if a != b)
            out.append(f'{head}:{nv}')
            continue
        out.append(line)
    return '\n'.join(out), changed


def main() -> int:
    ap = argparse.ArgumentParser(description='展示层 CBDB 繁体 → 简体（白名单字表）')
    ap.add_argument('--apply', action='store_true', help='写盘（默认 dry-run）')
    ap.add_argument('--root', default=None, help='数据根目录，默认仓库根')
    ap.add_argument('--samples', type=int, default=6, help='打印变更样例数')
    args = ap.parse_args()

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parent.parent
    rel_dir, per_dir = root / 'data' / 'relations', root / 'data' / 'persons'
    if not rel_dir.is_dir() or not per_dir.is_dir():
        print(f'✗ 找不到 {rel_dir} 或 {per_dir}', file=sys.stderr)
        return 2

    plan, samples = [], []
    targets = [
        *((p, conv_rel_file, True) for p in sorted(rel_dir.glob('*.yaml'))),
        *((p, conv_person_file, True) for p in sorted(per_dir.glob('*.yaml'))),
        *((p, conv_rel_file, True) for p in [root / 'data' / 'geo_map.yaml'] if p.exists()),
    ]
    for path, fn, _skip_underscore in targets:
        if path.name.startswith('_'):
            continue
        text = path.read_text(encoding='utf-8')
        new, n = fn(text)
        if n:
            plan.append((path, new, n))
            if len(samples) < args.samples:
                a, b = text, new
                i = next(k for k, (x, y) in enumerate(zip(a, b)) if x != y)
                samples.append((path.name, a[max(0, i - 22):i + 24].replace('\n', '⏎'),
                                b[max(0, i - 22):i + 24].replace('\n', '⏎')))

    total = sum(n for _, _, n in plan)
    print(f'待改文件 {len(plan)} 个 / 替换字符 {total} 处  （白名单 {len(SAFE_MAP)} 条，剔除 {len(EXCLUDED)} 条）')
    if samples:
        print('\n变更样例：')
        for name, before, after in samples:
            print(f'  {name}\n    - {before}\n    + {after}')

    # 复核：范围内是否残留「已剔除」的繁体字（这些是本次有意保留的）
    resid = []
    for path, new, _ in plan:
        for f in (*PERSON_FIELDS, 'note', 'type'):
            for m in re.finditer(rf'^\s*{f}:(.*)$', new, re.M):
                for c in m.group(1):
                    if c in EXCLUDED:
                        resid.append((path.name, f, c))
    if resid:
        print(f'\n有意保留的剔除字（{len(resid)} 处，多为外部人物罕用名用字）：')
        for name, f, c in resid[:12]:
            print(f'  {name}  {f}  「{c}」（{EXCLUDED[c][1].split("，")[0]}）')

    if not args.apply:
        print('\n[dry-run] 未写盘。确认无误后加 --apply。')
        return 0

    for path, new, _ in plan:
        path.write_text(new, encoding='utf-8')
    print(f'\n✓ 已写盘 {len(plan)} 个文件，替换 {total} 处。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
