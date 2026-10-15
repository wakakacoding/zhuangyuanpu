import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';
import { execSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const SITE_ROOT = path.dirname(fileURLToPath(import.meta.url));

// 构建期 Python 步骤：构建/起服前跑 scripts/<script>，产物落 public/
// 失败即中止构建（数据缺失 = 页面坏掉，宁缺毋滥）
function pythonStep(name, script) {
  const run = () => {
    const managed = '/Users/mba/.workbuddy/binaries/python/envs/default/bin/python';
    const py = existsSync(managed) ? managed : 'python3';
    const file = path.join(SITE_ROOT, '..', 'scripts', script);
    execSync(`${py} "${file}"`, { stdio: 'inherit', cwd: SITE_ROOT });
  };
  return {
    name,
    hooks: {
      'astro:build:start': run,
      'astro:server:start': run,
    },
  };
}

// 星图数据切片：scripts/build_galaxy.py → public/data/galaxy.json
const galaxyData = () => pythonStep('galaxy-data', 'build_galaxy.py');

// 公开数据 API：scripts/build_api.py → public/api/{persons.json,persons.csv,persons/<id>.json,README.md}
const apiData = () => pythonStep('api-data', 'build_api.py');

// 关系网络切片：scripts/build_network.py → public/data/network.json（供 /network 关系网络图）
const networkData = () => pythonStep('network-data', 'build_network.py');

// 静态站：构建期读取 ../data/*.yaml，运行期零数据库
// 部署目标：GitHub Pages（项目页，子路径 /zhuangyuanpu）
export default defineConfig({
  site: 'https://wakakacoding.github.io',
  base: '/zhuangyuanpu',
  output: 'static',
  trailingSlash: 'always',
  integrations: [sitemap(), galaxyData(), apiData(), networkData()],
});
