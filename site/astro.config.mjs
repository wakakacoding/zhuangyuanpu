import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';
import { execSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const SITE_ROOT = path.dirname(fileURLToPath(import.meta.url));

// 构建期 Python 解释器：托管 Python（本机沙箱内已装 PyYAML）优先；
// CI 上该路径不存在，回退系统 python3（deploy.yml 里预装 PyYAML）
function pythonBin() {
  const managed = '/Users/mba/.workbuddy/binaries/python/envs/default/bin/python';
  return existsSync(managed) ? managed : 'python3';
}

function runPython(script, args = []) {
  const file = path.join(SITE_ROOT, '..', 'scripts', script);
  const tail = args.length ? ` ${args.join(' ')}` : '';
  execSync(`${pythonBin()} "${file}"${tail}`, { stdio: 'inherit', cwd: SITE_ROOT });
}

// 构建/起服前跑 scripts/<script>（产物落 public/），失败即中止构建
// （数据缺失 = 页面坏掉，宁缺毋滥）
function pythonStep(name, script, args = []) {
  const run = () => runPython(script, args);
  return {
    name,
    hooks: {
      'astro:build:start': run,
      'astro:server:start': run,
    },
  };
}

// 构建**之后**跑：脚本读的是构建产物（dist），只能挂 astro:build:done。
// 不能复用 pythonStep —— 那是 astro:build:start，那时 dist 还没生成；
// dev server 也不会触发本钩子（改代码不跑全量死链扫描）。
function pythonPostBuildStep(name, script, args = []) {
  const run = () => runPython(script, args);
  return { name, hooks: { 'astro:build:done': run } };
}

// 数据底座校验：scripts/validate.py —— 0 错误才放行构建
const validateData = () => pythonStep('validate-data', 'validate.py');

// 星图数据切片：scripts/build_galaxy.py → public/data/galaxy.json
const galaxyData = () => pythonStep('galaxy-data', 'build_galaxy.py');

// 公开数据 API：scripts/build_api.py → public/api/{persons.json,persons.csv,persons/<id>.json,README.md}
const apiData = () => pythonStep('api-data', 'build_api.py');

// 关系网络切片：scripts/build_network.py → public/data/network.json（供 /network 关系网络图）
const networkData = () => pythonStep('network-data', 'build_network.py');

// 繁简切换人名保护表：scripts/build_names.py → public/data/protected_names.json
const namesData = () => pythonStep('names-data', 'build_names.py');

// 站内死链检查：scripts/check_links.py 爬 dist 内部 href/src，有任何 404 即失败
const linksCheck = () => pythonPostBuildStep('links-check', 'check_links.py');

// 静态站：构建期读取 ../data/*.yaml，运行期零数据库
// 部署目标：GitHub Pages（项目页，子路径 /zhuangyuanpu）
export default defineConfig({
  site: 'https://wakakacoding.github.io',
  base: '/zhuangyuanpu',
  output: 'static',
  trailingSlash: 'always',
  integrations: [sitemap(), validateData(), galaxyData(), apiData(), networkData(), namesData(), linksCheck()],
});
