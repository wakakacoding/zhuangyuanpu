# T6 交付报告 · GitHub Issue 勘误模板 + 死链检查器

> 任务来源：`状元人生追踪网站-评审修复与质量攻坚计划.md` 附录 A 的 **R3-3a**（Issue 勘误模板）与 **R2-2 开发部分**（站内链接检查器）
> 执行日期：2026-10-15　|　范围：**只开发不接入**（未改 `astro.config.mjs`、未改 `deploy.yml`、未动任何页面）

---

## 0. 交付物清单

| 文件 | 状态 | 说明 |
|---|---|---|
| `.github/ISSUE_TEMPLATE/correction.yml` | 新建 | 表单式勘误模板（GitHub Issue Form），10 个 body 元素，9 个可预填字段 |
| `.github/ISSUE_TEMPLATE/correction-text.md` | 新建 | 文本式勘误模板，**唯一支持 `?body=` 整段预填**的入口，供站内勘误页「一键开 Issue」用 |
| `.github/ISSUE_TEMPLATE/config.yml` | 新建 | 模板选择器配置：保留空白 Issue，追加 2 条 contact link（勘误页 / 关于页） |
| `scripts/check_links.py` | 新建 | 站内内部链接死链检查器（只读、纯标准库、626 页 2.3 秒） |
| 本报告 | 新建 | 含死链基线（4893 处 cbdb 前缀）+ 1 处新发现的非 cbdb 死链 |

未改动：`site/astro.config.mjs`、`.github/workflows/deploy.yml`、`site/src/pages/**`、`data/**`。`data/relations/_cbdb_out_of_scope.yaml` 只读。

---

## 一、Issue 勘误模板

### 1.1 为什么是两个模板（不是画蛇添足）

GitHub 的两种 Issue 模板，预填能力**不一样**：

| | 表单式 `.yml` | 文本式 `.md` |
|---|---|---|
| 认 `?title=` | ✅ | ✅ |
| 认 `?body=` | ❌ **忽略** | ✅ |
| 按字段预填 | ✅ `&字段id=值`（官方 schema 明确 `id` 即预填参数名） | ❌（正文是整块的） |
| 逐字段必填校验 | ✅ | ❌ |

所以：**表单式负责日常提交的引导性**，**文本式负责「从站内一键带出整段勘误单」**——这也正是 R3-3b（勘误页 / 档案页按钮）真正要用的那个。两者模板 `name` 不同、文件基名不同（`correction` / `correction-text`），GitHub 要求模板名全局唯一且 **`.yml` 与 `.md` 不得同基名**，已避开这个坑。

### 1.2 correction.yml · 字段与预填参数对照

| # | 元素 | `id`（= 预填参数名） | 必填 | 对应站内勘误表单字段 |
|---|---|---|---|---|
| 1 | markdown | — | — | 提交前须知（依据分级 / 异说不是错误 / 先查受理记录） |
| 2 | dropdown | `target-kind` | 是 | 对象类型：`人物（person）` / `出处（source）` / `站点页面（site）` / `外部数据源（external）` |
| 3 | input | `target-id` | 是 | 对象标识（人物 id / 页面路径 / 出处 id / 外部库记录号） |
| 4 | input | `field` | 是 | 涉及字段，`value` 默认 `record`（与 `data/corrections/*.yaml` 的 `field` 口径一致） |
| 5 | textarea | `current` | 是 | 现状（要求粘贴原文，禁止转述） |
| 6 | textarea | `proposed` | 是 | 建议修正为 |
| 7 | textarea | `evidence` | 是 | 依据（书名+卷次 / 可核验链接，A/B 级优先） |
| 8 | input | `reporter` | 否 | 署名（空 = 匿名） |
| 9 | textarea | `note` | 否 | 补充说明 |
| 10 | checkboxes | `affirm` | 第 1 项必勾 | 提交前确认：① 引用的是原文；② 理解「异说备录」不等于驳回 |

复选框预填要传**选项下标**（`&affirm=0`），不能传文字——这是 GitHub 的既有行为。

### 1.3 给 R3-3b 的预填配方（可直接抄）

**A. 表单式 · 字段级预填**（档案页「勘误此卡」按钮最顺手）

```
https://github.com/wakakacoding/zhuangyuanpu/issues/new?template=correction.yml
  &title=%5B勘误%5D+王维（wang_wei）·+birth_year
  &target-kind=人物（person）
  &target-id=wang_wei
  &field=birth_year
```
实测拼接结果 263 字符，远低于 URL 2000 字符上限。

**B. 文本式 · 正文整段预填**（勘误页「一键开 Issue」，正文即勘误单 YAML）

```
?template=correction-text.md&title=…&body=<百分号编码的整段勘误单>
```
示例正文（1003 字符，含 `%0A` 换行）：

```yaml
id: corr_pending
target: person:wang_wei
field: birth_year
current: 生年 701（CBDB 候选匹配值，未经核验）
proposed: 生年 699 或 701 存疑，宜标「生年不详」
reason: 该值来自 CBDB 候选匹配，本站未做人工考证
evidence: 《旧唐书》卷一九〇下·王维传未载生年
status: pending
reporter: 匿名
created: 2026-10-15
```

要点：① 目标 URL 一律用完整的 `https://github.com/...`，**不要走短链**（短链 302 会丢掉整个 query，预填全部失效）；② 值必须百分号编码（换行 → `%0A`）；③ 务必带 `template=`，否则 GitHub 会拦到模板选择页，预填参数一并丢弃。

### 1.4 自检结果（对齐 GitHub 官方 schema 的硬约束）

```
[1] correction.yml     YAML 解析 OK；name/description/body 齐备；10 个元素
                       id 字符集 [A-Za-z0-9_-] 合法且唯一；dropdown options 非空无重复、default 不越界；
                       checkboxes 每项有 label；validations 仅用 required/min_length/accept；
                       markdown 元素无 id 且有 attributes.value
[2] correction-text.md frontmatter 键合法（name/about/title/labels）
[3] config.yml         blank_issues_enabled: True；contact_links 2 条，name/url/about 齐备
[4] 模板 name 唯一性 OK；.yml/.md 同基名冲突检查 OK
==================================================
自检结果：全部通过 ✅
```

复跑自检（PyYAML 需用托管 Python；系统 python3 无 yaml）：

```bash
cd /Users/mba/WorkBuddy/top_person_life_v2 && /Users/mba/.workbuddy/binaries/python/envs/default/bin/python - <<'EOF'
import yaml, pathlib
for f in sorted(pathlib.Path('.github/ISSUE_TEMPLATE').iterdir()):
    d = yaml.safe_load(f.read_text()); print(f.name, '->', 'OK')
EOF
```

### 1.5 两处需要你知道的运维前提

1. **`勘误` 标签要先在仓库里建**。GitHub 文档明确：模板里 `labels` 指定的标签若仓库中不存在，**不会**自动创建、也不会加到 Issue 上（静默跳过，不报错）。建议建标签 `勘误`（建议配色 `#b21f1f` 之类朱红），否则提交上来的 Issue 是光板。
2. **目视验收要靠一次推送**。schema 自检只能证明「结构合规」，真正渲染成表单要 GitHub 侧渲染。推上去之后开 `https://github.com/wakakacoding/zhuangyuanpu/issues/new/choose` 看两条模板与两条 contact link；若想零风险试，可以先在一个空白测试仓库里放同样三个文件看一眼。

---

## 二、死链检查器 `scripts/check_links.py`

### 2.1 判定口径

| 判定 | 含义 | 是否致命 |
|---|---|---|
| `dead` | dist 里找不到对应文件（部署即 404） | 错误 |
| `case-mismatch` | 文件在，但**大小写不符**（macOS 本机能打开、GitHub Pages 404） | 错误 |
| `missing-base` | 以 `/` 开头的绝对路径没带 `/zhuangyuanpu` 前缀（本地根目录预览看不出） | 错误 |
| `outside-dist` | 相对路径 `../..` 越出 dist 根 | 错误 |
| `no-trailing-slash` | 指向目录却漏了结尾斜杠（Pages 会 301，不算错） | 警告 |
| 跳过 | 外链、`mailto:`/`tel:`/`javascript:`/`data:`、纯锚点、空值 | 计数不计错 |

实现上刻意做了两件事：**① 剥掉 `<script>`/`<style>` 的内容再取链接**（保留开标签，`<script src>` 仍算数）——否则 Astro 内联脚本里的 `` `href="${base}persons/${s.s}"` `` 会被当成 6 条假死链误报；**② 逐段按真实大小写核对路径**，因为 macOS 大小写不敏感而 Pages 敏感，这类坑只在部署后才炸。

另外声明边界：只覆盖 `.html` 里的 `href`/`src`/`srcset`；`rss.xml`、`sitemap-0.xml` 的 `<loc>` 与 CSS 内的 `url()` 不在范围内。

### 2.2 用法与退出码

```bash
P=/Users/mba/.workbuddy/binaries/python/envs/default/bin/python

# 基线报告（只报告，永远退出 0）
$P scripts/check_links.py --report-only --top 30

# 严格模式：有任何死链即非零退出（供 R2-2 接入构建用）
$P scripts/check_links.py --max-errors 0

# 排除已知存量，只盯新引入的死链
$P scripts/check_links.py --ignore 'cbdb:' --report-only

# 落盘：完整 JSON（含逐条清单）+ Markdown 报告
$P scripts/check_links.py --md /tmp/links.md --json /tmp/links.json
```

| 退出码 | 条件 |
|---|---|
| 0 | 错误数 ≤ `--max-errors`（默认 0）；或带 `--report-only`；或 dist 缺失但带 `--allow-missing-dist` |
| 1 | 错误数 > `--max-errors` |
| 2 | 用法/环境错误（dist 不存在且未放宽、`--ignore` 正则非法等） |

已实测各分支：`--max-errors 0`→1、`--max-errors 5000`→0、dist 缺失→2。判定分支用临时夹具逐条验过（ok / dead / case / base / outside / warn / 四类跳过全部命中预期）。

### 2.3 基线报告（当前 `site/dist`，2026-10-15）

| 指标 | 数值 |
|---|---:|
| 扫描 HTML 文件 | 626 |
| 提取 href/src 链接 | 11 909 |
| 其中站内待检 | 11 739 |
| 外链 / 锚点·协议·空值跳过 | 8 / 162 |
| **错误** | **4 894 条（唯一目标 3 953 个）** |
| 警告 | 0 条 |

按类型：

| 出现次数 | 唯一目标 | 涉及来源页 | 类型 |
|---:|---:|---:|---|
| **4 893** | 3 952 | 232 | **`cbdb:` 前缀外部人物链接**（CBDB 编号被拼成站内链接） |
| 1 | 1 | 1 | 其他死链（见 §2.5） |

按来源目录：`persons/` 4 893 条（覆盖 232 / 600 个档案页）、`api/` 1 条。

单页最多的三张：吕柟 `persons/lv_nan/` 266 处、文天祥 242 处、陈亮 170 处——即关系条目最密的几张卡，是 R3-1 修好后的最大受益者。

Top 5 唯一目标（完整 3 952 个唯一目标在 `--json` 产物里）：

| 次数 | 目标 |
|---:|---|
| 13 | `/zhuangyuanpu/persons/cbdb:3257/` |
| 12 | `/zhuangyuanpu/persons/cbdb:7197/` |
| 9 | `/zhuangyuanpu/persons/cbdb:1384/` |
| 9 | `/zhuangyuanpu/persons/cbdb:1488/` |
| 9 | `/zhuangyuanpu/persons/cbdb:3624/` |

### 2.4 根因与一次漂亮的交叉验证

数据侧实测：`data/relations/` 278 个文件、**4 975 条边**，其中 `to_id` 以 `cbdb:` 开头 **4 881 条**。

产物侧报出 **4 893** 处 —— 差 12。追下去发现多出的 10 个编号

```
701483 / 701787 / 702229 / 702370 / 702396 / 702424 / 702596 / 702833 / 702895 / 703952
```

**正是 T2 已从 `data/relations/` 删除的那 10 个越界 CBDB 记录**（留痕在 `data/relations/_cbdb_out_of_scope.yaml`）。它们的 12 条边已从数据里删掉，但当前 `dist` 是 T2 purge **之前**的构建产物，所以还挂着。

于是：

```
产物实测 4 893 − 已删除边的残留 12 = 4 881 = 数据侧现存 cbdb: 边数  ✔ 完全吻合
```

**由此得到两条结论：**

1. **真实基线 = 4 881 处**（新构建后）。计划文档里写的「约 4893 处」是 purge 前的旧口径，两者都能对上，不是矛盾。
2. **检查器必须跑在同一次构建之后**——产物陈旧会把「数据已删、页面未重建」的链接计入死链。这条已写进脚本 docstring，跑之前先 `npm run build`。

### 2.5 顺带发现：1 处非 cbdb 的真死链（**未修，等你定**）

| 来源 | 目标 | 性质 |
|---|---|---|
| `api/index.html` | `/zhuangyuanpu/」；` | 真 404，非 cbdb 存量 |

成因：`scripts/build_api.py:432` 的许可文案

```
1. **署名**：注明「数据来源：状元谱 {SITE_URL}」；
```

`SITE_URL` 是裸 URL 且**紧跟全角右引号与分号**，Markdown 自动链接（GFM autolink literal）把 `」；` 一起吞进了 href，产物渲染成：

```html
<a href="https://wakakacoding.github.io/zhuangyuanpu/%E3%80%8D%EF%BC%9B">…/zhuangyuanpu/」；</a>
```

点击会 404（路径变成了 `/zhuangyuanpu/」；`）。

一行修法（**我没有动**，因为它落在禁区「不动页面」的灰区上，且改它会连带刷新 `/api/` 页渲染结果）：

```
∨ 现状：注明「数据来源：状元谱 {SITE_URL}」；
∨ 改为：注明「数据来源：状元谱 {SITE_URL} 」；        # 前加一个空格隔断自动链接
∨ 或：  注明「数据来源：状元谱」{SITE_URL}；
∨ 或：  用尖括号包住 URL：注明「数据来源：状元谱 <{SITE_URL}>」；
```

**这一处必须在 R2-2 接入构建之前处理掉**，否则 `--max-errors 0` 永远过不了（接入后的门禁是「0 死链」）。

### 2.6 接入构建时该怎么接（本任务**未**接入）

已备好接入所需的一切，但按计划 R2-2 的硬依赖（须等 R3-1 修完 cbdb 链接），**接入留给 T10 / R2-2 接入任务**：

1. `check_links.py` 属**构建后**检查，不能挂在现有 `pythonStep()` 的 `astro:build:start` 钩子上（那时 dist 还没生成），要在 `astro.config.mjs` 里用 `astro:build:done` 钩子，并传 `--max-errors 0`；
2. 若图省事挂在 CI，`deploy.yml` 里 `withastro/action` 之后加一步 `python3 scripts/check_links.py --max-errors 0` 亦可（脚本纯标准库，CI 不需装依赖）；
3. 接入前先按 §2.5 修掉那 1 处、并确认 cbdb 死链已清零；验收口径：`--max-errors 0` 退出码 0、且 `--report-only` 报告里「错误 0 条 / 警告 0 条」。
4. 建议同时留一个 `--ignore 'cbdb:'` 的临时开关说明，别把「忽略」写进配置当常态——它只是排查用的。

---

## 三、验收对照

| 验收项 | 结果 |
|---|---|
| 勘误模板可渲染（yaml 语法自检） | ✅ YAML 解析通过 + 逐条对齐 GitHub 官方 schema 硬约束（id 字符集/唯一性、options 非空无重复、default 越界、validations 白名单、markdown 无 id、顶层键白名单、模板名唯一、同基名冲突）共 4 组检查全通过；**GitHub 侧实际渲染需一次推送后目视确认**（见 §1.5） |
| 字段齐备（对象类型/标识/字段/现状/建议/依据/署名） | ✅ 全部覆盖，另加「补充说明」与「提交前确认」两项 |
| 支持 URL query 预填（title/body） | ✅ `title` + 按字段 id 预填（表单式）；`title` + `body` 整段预填（文本式）。已在报告中给出可直接抄的拼接示例与 3 条易错点 |
| check_links.py 对 dist 全量爬内部 href/src、404 报错出清单 | ✅ 626 个 HTML、11 909 条链接，错误清单 + 按类型/来源分桶 + 唯一目标 Top N + 全量 JSON |
| `--max-errors 0` 模式供构建接入 | ✅ 已实测退出码语义（0/1/2），并说明需挂 `astro:build:done` 而非现有 `pythonStep` |
| 基线报告输出 | ✅ 本节 §2.3–2.5：**4 893 处 cbdb 死链**（新构建应为 4 881）+ 1 处非 cbdb 死链 + 根因与交叉验证 |
| 只开发不接入 | ✅ 未动 `astro.config.mjs` / `deploy.yml` / 任何页面 / 任何 data |
