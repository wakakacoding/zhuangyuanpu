# 状元人生追踪网站

自唐武德五年（622）孙伏伽至清光绪三十年（1904）刘春霖，历代状元人生轨迹的数据底座与网站。

## 目录结构

```
data/           # 数据底座（YAML + Git 版本管理，单一事实来源）
  persons/      # 状元主表（_template.yaml 为模板）
  events/       # 生平事件（每条必须挂出处）
  sources/      # 史料出处（A/B/C 三级可信度）
  relations/    # 人物关系
  works/        # 著作
  anecdotes/    # 轶事（与史实物理隔离，默认 C 级）
  geo_map.yaml  # 古今地名映射表
schema/SCHEMA.md    # Schema v1.0（冻结版）
scripts/
  era.py            # 公元/干支/年号互验
  validate.py       # 数据校验器（构建期强制，三条铁律）
  seed_cards.py     # 一次性速览卡种子（已运行，勿重复执行）
  import_cbdb.py    # CBDB 验证与候选池导出
  build_api.py      # 公开数据 API 导出（site/public/api/*，构建期自动运行）
  build_og_galaxy.py# 星图专用深色 OG 图（手动运行，Pillow）
content/stories/    # 故事长文（Phase 1）
site/           # Astro 静态站（构建期读取 data/）
  public/api/       # 开放数据 API 导出物（build_api.py 生成，勿手改）
vendor/cbdb/    # CBDB 数据库（不提交 Git，学术免费使用）
```

## 开放数据

站点构建期自动导出静态 API（`scripts/build_api.py`），随站点发布：

| 端点 | 内容 |
|---|---|
| `/api/persons.json` | 全量精简字段（一人一条） |
| `/api/persons.csv` | 同上，CSV 版（UTF-8 无 BOM） |
| `/api/persons/<id>.json` | 单人全字段：档案 + 生平事件 + 著作 + 轶事 + 关系 + 所引出处 |
| `/api/index.json` | 清单（版本、生成日期、条目数） |
| `/api/README.md` | 字段字典 + A/B/C 分级约定 + CC BY-SA 4.0 许可说明 |

## 常用命令

```bash
# 数据校验（新增/修改 YAML 后必跑）
python3 scripts/validate.py

# 本地开发（cd site）
npm install
npm run dev        # http://localhost:4321
npm run build      # 构建到 site/dist
```

## 部署（Cloudflare Pages）

1. 仓库推送到 GitHub 后，在 Cloudflare Dashboard → Workers & Pages → Create → Pages → Connect to Git
2. 构建设置：
   - **Root directory**: `site`
   - **Build command**: `npm run build`
   - **Build output directory**: `dist`
3. 此后 `git push` 即自动构建发布

（也可 `cd site && npx wrangler pages deploy dist` 手动部署，需先 `npx wrangler login` 授权）

## 数据协作铁律

1. 任何字段无出处不得标 A 级；事件无 source_ids 不得入库
2. 轶事与史实物理隔离（不同表、不同视觉样式）
3. 「史料阙如」是合法且诚实的展示，不编造补齐
