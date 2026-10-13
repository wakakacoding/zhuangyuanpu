#!/usr/bin/env python3
"""GitHub Pages 子路径适配：把站内绝对链接改为 ${BASE} 前缀（一次性 codemod）。

规则：
  href="/"            -> href={BASE}
  href="/xxx/"        -> href={`${BASE}xxx/`}
  href={`/xxx...`}    -> href={`${BASE}xxx...`}
并在每个页面 frontmatter 注入 `import { BASE } from '...lib/persons'`（按相对深度）。
inline script（浏览器端）另用 define:vars 注入，见单独处理。
"""
import re
from pathlib import Path

SRC = Path('/Users/mba/WorkBuddy/top_person_life_v2/site/src/pages')
files = [
    SRC / 'index.astro',
    SRC / 'search.astro',
    SRC / 'timeline.astro',
    SRC / 'stats.astro',
    SRC / 'map.astro',
    SRC / 'corrections.astro',
    SRC / 'persons' / 'index.astro',
    SRC / 'persons' / '[id].astro',
    SRC / 'stories' / 'index.astro',
    SRC / 'stories' / '[slug].astro',
]

changed_files = []
for f in files:
    text = f.read_text(encoding='utf-8')
    orig = text

    # 1) href="/" 精确
    text = text.replace('href="/"', 'href={BASE}')
    # 2) href="/xxx..."（静态路径，含尾斜杠）
    text = re.sub(r'href="/([^"{]+)"', lambda m: 'href={`${BASE}' + m.group(1) + '`}', text)
    # 3) href={`/xxx${...}`}（模板串）：把前导 / 换为 ${BASE}
    text = re.sub(r'href=\{`/(?=[^`]*\$\{)', 'href={`${BASE}', text)

    if text == orig:
        continue

    # 4) 注入 BASE import
    depth = len(f.relative_to(SRC).parts)  # 1=pages 直下，2=子目录
    rel = '../' * depth + 'lib/persons'
    if 'from \'../../lib/persons\'' in text or "from '../lib/persons'" in text:
        # 已有 persons import：把 BASE 并入（取最先出现的一处）
        text = re.sub(
            r"import \{([^}]+)\} from '(\.\./)+lib/persons';",
            lambda m: 'import {' + m.group(1).rstrip() + ", BASE} from '" + rel + "';",
            text, count=1)
    else:
        # 无 persons import：在最后一个 import 行后追加
        lines = text.split('\n')
        last_import = max(i for i, ln in enumerate(lines) if ln.startswith('import '))
        lines.insert(last_import + 1, f"import {{ BASE }} from '{rel}';")
        text = '\n'.join(lines)

    f.write_text(text, encoding='utf-8')
    changed_files.append(f.name)

print('changed:', changed_files)
