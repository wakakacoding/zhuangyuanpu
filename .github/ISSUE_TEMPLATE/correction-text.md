---
name: 勘误（文本 · 支持正文预填）
about: 站内勘误页「一键带出」的落点，也可手写。适合粘贴勘误页生成的勘误单（YAML 格式），或依据较多、需要长文陈述的勘误。
title: "[勘误] "
labels: 勘误
---

<!--
为什么会有这个模板（维护者备注，提交者无需理会）
------------------------------------------------
GitHub 的表单式模板（correction.yml）**只支持按字段 id 预填**，不认 URL 的 `body` 参数；
而纯文本模板认 `?title=` 与 `?body=`。所以两个都在：
  · 表单式（correction.yml）—— 日常提交，逐字段引导，适合少量字段勘误；
  · 文本式（本文件）—— 站内勘误页「一键开 Issue」的落点，正文整段预填，
    格式与 data/corrections/*.yaml 的字段一一对应，便于直接落库留痕。
-->

请在下方代码块里填写（保留字段名，冒号后写内容），或直接粘贴勘误页生成的勘误单：

```yaml
id: corr_pending
target: person:wang_wei     # 对象类型:对象标识。类型取 person / source / site / external
field: birth_year           # 只错一处写字段名；整卡问题填 record
current:                    # 现状：站内（或外部数据源）当前记载的原文，直接粘贴
proposed:                   # 建议修正为
reason:                     # 你的判断理由
evidence:                   # 依据：书名+卷次，或可核验链接（A/B 级依据优先）
status: pending             # 请勿改
reporter: 匿名              # 署名，可留空
created:                    # 提交日期 YYYY-MM-DD
```

依据的其他说明、上下文、判断过程中的犹豫，请写在代码块之外。
图片可直接拖进正文。
