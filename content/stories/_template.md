---
# ===== 故事 frontmatter 规范（B2/B3 交付物）=====
# slug：URL 用，小写连字符，发布即冻结
slug: person-keyword
# 主标题 / 副标题：副标题一句话点出「时代断代」感
title: 标题
subtitle: 一句话副标题
# 导语：80–150 字，首页专题流与 OG 分享共用此文案
intro: >-
  导语。
# 出场人物：data/persons/ 里的 id 列表；页尾自动生成互链卡，写作时正逼数据回填
persons:
  - some_person_id
# YYYY-MM-DD；status: draft → published
date: 2026-01-01
status: draft
---

<!-- 写作铁律（发布前自查 Checklist）：
1. 五段式骨架：开场钩子 → 夺魁时刻 → 仕途沉浮 → 历史坐标 → 身后事，用 ## 分章
2. 3000–5000 字封顶；存疑处写「待考」，禁止编造
3. 轶事卡标记（单独成行）：
     [[card:person_id:an:0]]  → 轶事卡（data/anecdotes/<id>.yaml 第 0 条）
     [[card:person_id:ev:2]]  → 史实卡（data/events/<id>.yaml 第 2 条，索引按 YAML 中顺序）
   每篇 ≥3 张卡；传说卡（C 级）与史实卡（A/B 级）不得混排相邻而不加过渡句
4. 正史原文引用进 blockquote（> 开头），并在对应 data/sources/ 补 quote 字段
5. 写完回填：该人物的 event/source/anecdote 补齐 → 跑 scripts/validate.py 须 0 错误
6. 文末「出场人物」由 persons 列表自动生成，正文提到其他状元时确保其已有速览卡
-->

## 一、开场钩子

（一个具体的场景、物件或瞬间。200 字内让读者停下来。）

## 二、夺魁时刻

（科场经过 + 名次的一手证据，配 A 级史实卡。）

[[card:some_person_id:ev:1]]

## 三、仕途沉浮

（夺魁之后的人生主线。）

## 四、历史坐标

（把个人放进时代：制度、风气、同期人物对照。）

## 五、身后事

（结局 + 评价 + 传说层——传说一律进 C 级卡，不在正文当事实陈述。）

[[card:some_person_id:an:0]]
