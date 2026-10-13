# Schema v1.0（冻结版）—— 状元人生追踪网站数据底座

> 冻结日期：2026-10-12 | 状态：**冻结**。30 天内不允许 breaking change；字段新增以 PR 评审。
> 三案共用此 Schema：方案二（故事）、方案一（数据库）、方案三（可视化）只读不写本层定义。

## 0. 全局约定

- **存储形态**：YAML 文件 + Git 版本管理（史料修订天然需要留痕）。构建期读取，运行期零数据库。
- **ID 规则**：`person.id` 用姓名拼音小写、下划线连接（如 `liu_chunlin`），重名加 `_2` 后缀；`source.id` 用 `src_` 前缀。ID 一经发布永不修改（页面 URL 与之绑定）。
- **文件命名**：与实体 id 同名，如 `data/persons/liu_chunlin.yaml`；`_` 开头的文件是模板，校验与构建均跳过。
- **空值合法**：允许一个状元只有「姓名 + 朝代 + 科年」三个字段，页面展示「史料阙如」——这本身就是有价值的信息。**禁止编造补齐**。
- **异说并存**：生卒年、籍贯有争议时，存多个版本并各挂出处，前端标注「存疑」。实现方式：争议字段写作列表（见 person 模板 `birth_year_alt` 示例）。
- **纪年**：公元年为机器主键；干支由 `scripts/era.py` 校验（公元—干支不一致即构建失败）；年号仅作展示字段。
- **坐标**：一律 WGS84 十进制度数，`lat` 北纬 / `lng` 东经。

## 1. person（状元主表）—— `data/persons/<id>.yaml`

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| id | str | ✅ | 拼音 slug，稳定唯一 |
| name | str | ✅ | 姓名 |
| zi / hao | str | – | 字 / 号 |
| birth_year / death_year | int | – | 生卒年（公元）；约年用 `c.` 前缀场景见 `_alt` 字段 |
| birth_year_alt 等 `*_alt` | list | – | 异说并存：每项含 `value` + `source_id` |
| fl_year | int | – | 估算活动年（约中年）。**仅填外部权威估算值**（当前来源：CBDB c_index_year），与生卒年物理隔离，绝不互推；星图等可视化以此定位时需标注「估算」 |
| native_hist | str | – | 历史籍贯（原文照录，如「直隶省河间府肃宁县」） |
| native_modern | str | – | 今地名 |
| lat / lng | float | – | 今地坐标（可视化前置字段） |
| dynasty | str | ✅ | 朝代（唐/宋/辽/金/元/明/清/西夏…） |
| reign | str | – | 帝号（如「光绪」） |
| exam_year | int | 建议 | 夺魁公元年 |
| ganzhi | str | 建议 | 干支，须与 exam_year 互验通过 |
| ke_ci | str | – | 科次全称（如「光绪三十年甲辰恩科」） |
| rank_detail | str | 建议 | 榜次（如「一甲第一名（状元）」） |
| bio_short | str | – | 百字速览 |
| tags | list[str] | – | 标签（寒门/三元及第/末代状元…） |
| status | str | ✅ | `draft` / `published` |

## 2. event（生平事件表）—— `data/events/<person_id>.yaml`

仕途轨迹的核心。**每条事件必须挂出处（source_ids 非空），否则校验失败。**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| person_id | str | ✅ | 文件级字段，须与已存在的 person.id 对应 |
| events[] | list | ✅ | 事件列表，按年份升序 |
| events[].year | int | ✅ | 事件年（公元） |
| events[].year_end | int | 条件 | `range` 精度时的止年 |
| events[].year_precision | enum | ✅ | `exact` 确年 / `about` 约年 / `range` 年间 |
| events[].type | enum | ✅ | 见下方枚举 |
| events[].title | str | ✅ | 事件标题 |
| events[].description | str | – | 详述 |
| events[].source_ids | list[str] | ✅ | 引用 source.id，**不可为空** |

**event.type 枚举**：`出生` `应试` `中举` `夺魁` `授官` `留学` `升迁` `贬谪` `罢官` `被俘` `实业` `致仕` `隐居` `守节` `著作` `卒`
（注意：本表**不含「轶事」类型**——轶事与史实物理隔离，一律进 anecdote 表。）

## 3. source（史料出处表）—— `data/sources/<id>.yaml`

本 Schema 的灵魂。

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| id | str | ✅ | `src_` 前缀 |
| title | str | ✅ | 书名 |
| tier | enum | ✅ | **A**=正史/题名碑/朱卷/登科录；**B**=地方志/年谱/墓志/回忆录；**C**=笔记小说/民间传说 |
| juan | str | – | 卷次（A 级建议必填） |
| quote | str | 建议 | 原文摘录（A 级建议必填） |
| url | str | – | 电子化链接（如 ctext.org） |
| note | str | – | 版本、册页等待补说明 |

## 4. relation（人物关系表）—— `data/relations/<from_id>.yaml`

| 字段 | 说明 |
|---|---|
| from_id | 文件级字段，起点人物 |
| relations[].to_id | 终点人物（须已存在） |
| relations[].type | 枚举：`同年` `师生` `父子` `翁婿` `政敌` `兄弟` `友人` |
| relations[].note / source_ids | 说明与出处 |

## 5. work（著作表）—— `data/works/<person_id>.yaml`

| 字段 | 说明 |
|---|---|
| works[].title | 著作名 |
| works[].type | `诗文` `书法` `学术` `奏议` 等自由枚举 |
| works[].status | 存世状态：`存世` `存世（影印流传）` `佚` `待考` |

## 6. anecdote（轶事表）—— `data/anecdotes/<person_id>.yaml`

与 event **物理隔离**，默认 C 级，前端用不同视觉样式呈现，**明确区分「史实」与「传说」**。

| 字段 | 说明 |
|---|---|
| anecdotes[].title / content | 标题与内容 |
| anecdotes[].tier | 默认 `C`；升为 B 须有笔记类一手出处 |
| anecdotes[].source_ids / note | 出处与备考（如「异说并存」说明） |

## 7. geo_map（古今地名映射表）—— `data/geo_map.yaml`（单文件列表）

| 字段 | 说明 |
|---|---|
| hist | 历史地名（与 person.native_hist 逐字一致） |
| modern / lat / lng | 今地名与坐标 |
| chgis_id | CHGIS 对应 ID（可空，后续对齐） |
| note | 备注（如县治位置、附郭说明） |

## 三条铁律（构建期强制）

1. 任何字段无出处不得标 A 级；事件无 source_ids 不得入库。
2. 轶事与史实物理隔离（不同表、不同视觉样式）。
3. 「史料阙如」是合法且诚实的展示，不编造补齐。
