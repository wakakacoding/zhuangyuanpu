import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';

// 静态站：构建期读取 ../data/*.yaml，运行期零数据库
// site 为 sitemap/RSS 的规范域名（部署前占位，上线后如有独立域名再改）
export default defineConfig({
  site: 'https://zhuangyuanpu.pages.dev',
  output: 'static',
  trailingSlash: 'always',
  integrations: [sitemap()],
});
