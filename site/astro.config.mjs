import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';

// 静态站：构建期读取 ../data/*.yaml，运行期零数据库
// 部署目标：GitHub Pages（项目页，子路径 /zhuangyuanpu）
export default defineConfig({
  site: 'https://wakakacoding.github.io',
  base: '/zhuangyuanpu',
  output: 'static',
  trailingSlash: 'always',
  integrations: [sitemap()],
});
