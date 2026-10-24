# 访问统计开通步骤（Cloudflare Web Analytics）

本站已预置统计注入点（`site/src/components/SeoHead.astro`），默认关闭、零请求。
选 Cloudflare Web Analytics 的理由：无 cookie、不采集个人信息、免费、不加依赖——
与「不接第三方追踪」的既定原则一致（T6 运营指标一节的约束）。

## 开通（约 10 分钟）

1. 注册/登录 Cloudflare，进入 Dashboard → Web Analytics → Add a site
2. 填站点域名 `wakakacoding.github.io`（免费版支持任意域名，不要求托管在 CF）
3. 拿到 **Web Analytics token**（形如 `0123456789abcdef…` 的 JS Beacon token）
4. 在本仓库 Settings → Secrets and variables → Actions → Variables 添加：
   - Name: `PUBLIC_CF_BEACON_TOKEN`
   - Value: 上一步的 token
5. 在 `site/.env`（本地预览用，勿提交）写同一变量；不写则本地零统计请求
6. 触发一次部署。查看任意页面源码，`beacon.min.js` 出现即接入成功

## 原理

- 注入点在 SeoHead（全站唯一 head 组件），所有页面自动生效
- 构建期读 `Astro.env.PUBLIC_CF_BEACON_TOKEN`：变量不存在 → `<script>` 整块不渲染
- 统计口径见 T6 报告：只有「请求数」层级的指标（访问、来源、热门路径），
  无「读完率」「访客画像」类数据

## 能看到什么 / 不能看到什么

| 能 | 不能 |
|---|---|
| 页面访问次数、热门路径（故事篇热度） | 区分刷新与新访客（无 cookie） |
| 来源（公众号/GitHub/搜索占比） | 用户身份、设备指纹 |
| 28 天留存趋势 | 单用户行为序列 |

## 若要换 Plausible / Umami

只改 SeoHead 中那一个 `<script>` 块即可，变量名换成对应服务的前缀。
