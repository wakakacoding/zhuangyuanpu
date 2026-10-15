import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';
import { execSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const SITE_ROOT = path.dirname(fileURLToPath(import.meta.url));

// 星图数据切片：构建/起服前自动运行 scripts/build_galaxy.py → public/data/galaxy.json
// 失败即中止构建（数据缺失 = 星图页坏掉，宁缺毋滥）
function galaxyData() {
  const run = () => {
    const managed = '/Users/mba/.workbuddy/binaries/python/envs/default/bin/python';
    const py = existsSync(managed) ? managed : 'python3';
    const script = path.join(SITE_ROOT, '..', 'scripts', 'build_galaxy.py');
    execSync(`${py} "${script}"`, { stdio: 'inherit', cwd: SITE_ROOT });
  };
  return {
    name: 'galaxy-data',
    hooks: {
      'astro:build:start': run,
      'astro:server:start': run,
    },
  };
}

// 静态站：构建期读取 ../data/*.yaml，运行期零数据库
// 部署目标：GitHub Pages（项目页，子路径 /zhuangyuanpu）
export default defineConfig({
  site: 'https://wakakacoding.github.io',
  base: '/zhuangyuanpu',
  output: 'static',
  trailingSlash: 'always',
  integrations: [sitemap(), galaxyData()],
});
