import fs from 'node:fs';
import path from 'node:path';
import yaml from 'js-yaml';

/**
 * 共享数据加载器：构建期读取 data/ 下的 YAML。
 * 各页面统一走这里，避免重复 fs.readdirSync 样板代码。
 */

export const DATA_DIR = path.resolve(process.cwd(), '../data');

const cache: Record<string, any> = {};

function loadYaml(file: string) {
  return yaml.load(fs.readFileSync(file, 'utf8'));
}

function listYaml(dir: string): any[] {
  const abs = path.join(DATA_DIR, dir);
  if (!fs.existsSync(abs)) return [];
  return fs.readdirSync(abs)
    .filter((f) => f.endsWith('.yaml') && !f.startsWith('_'))
    .map((f) => loadYaml(path.join(abs, f)));
}

/** 全部人物卡（按科年升序，阙如排尾） */
export function allPersons(): any[] {
  cache.persons ??= listYaml('persons')
    .sort((a, b) => (a.exam_year ?? 9999) - (b.exam_year ?? 9999));
  return cache.persons;
}

/** 出处字典：id → source */
export function allSources(): Record<string, any> {
  cache.sources ??= Object.fromEntries(
    listYaml('sources').map((s) => [s.id, s])
  );
  return cache.sources;
}

/** 某人物的事件/著作/轶事/关系（无文件返回空数组） */
export function subDocs(dir: 'events' | 'works' | 'anecdotes' | 'relations', id: string): any[] {
  const f = path.join(DATA_DIR, dir, `${id}.yaml`);
  if (!fs.existsSync(f)) return [];
  const doc: any = loadYaml(f);
  return doc?.[dir] ?? [];
}

/** 已建全字段档案的人物 id 集（有 events 文件即算） */
export function fullProfileIds(): Set<string> {
  cache.fullIds ??= new Set(
    fs.readdirSync(path.join(DATA_DIR, 'events'))
      .filter((f) => f.endsWith('.yaml') && !f.startsWith('_'))
      .map((f) => f.replace(/\.yaml$/, ''))
  );
  return cache.fullIds;
}

/** 朝代顺序表（时间线/检索筛选共用） */
export const DYNASTY_ORDER = ['唐', '五代十国', '宋', '辽', '金', '元', '明', '清'];

export function presentDynasties(persons: any[]): string[] {
  return DYNASTY_ORDER.filter((d) => persons.some((p) => p.dynasty === d));
}

/** 干支计算（与 scripts/era.py 同算法：(year-4) % 60） */
const STEMS = '甲乙丙丁戊己庚辛壬癸';
const BRANCHES = '子丑寅卯辰巳午未申酉戌亥';

export function ganzhiOf(year: number): string {
  const i = ((year - 4) % 60 + 60) % 60;
  return STEMS[i % 10] + BRANCHES[i % 12];
}

/** 年号表：与 scripts/era.py REIGNS 同步（扩充时两边一起改） */
export const REIGNS: Record<string, [number, number]> = {
  武德: [618, 626], 开元: [713, 741], 天宝: [742, 756], 建中: [780, 783],
  元和: [806, 820], 开成: [836, 840], 会昌: [841, 846], 大中: [847, 860],
  乾宁: [894, 898],
  乾祐: [948, 950],
  太平兴国: [976, 984], 雍熙: [984, 987], 端拱: [988, 989], 咸平: [998, 1003],
  天圣: [1023, 1032], 皇祐: [1049, 1054], 嘉祐: [1056, 1063], 元丰: [1078, 1085],
  政和: [1111, 1118],
  绍兴: [1131, 1162], 宝祐: [1253, 1258],
  延祐: [1314, 1320], 至治: [1321, 1323],
  洪武: [1368, 1398], 建文: [1399, 1402], 永乐: [1403, 1424], 宣德: [1426, 1435],
  正统: [1436, 1449], 成化: [1465, 1487], 弘治: [1488, 1505], 正德: [1506, 1521],
  嘉靖: [1522, 1566], 万历: [1573, 1620], 天启: [1621, 1627], 崇祯: [1628, 1644],
  顺治: [1644, 1661], 康熙: [1662, 1722], 雍正: [1723, 1735], 乾隆: [1736, 1795],
  嘉庆: [1796, 1820], 道光: [1821, 1850], 咸丰: [1851, 1861],
  同治: [1862, 1874], 光绪: [1875, 1908], 宣统: [1909, 1911],
};

/** 公元年 → 年号纪年（如 1904 → '光绪三十年'）；未收录返回 null */
export function reignYearOf(year: number): string | null {
  for (const [reign, [start, end]] of Object.entries(REIGNS)) {
    if (year >= start && year <= end) return `${reign}${cnNum(year - start + 1)}年`;
  }
  return null;
}

const CN_DIGITS = '零一二三四五六七八九';
function cnNum(n: number): string {
  if (n <= 10) return n === 10 ? '十' : CN_DIGITS[n];
  if (n < 20) return '十' + CN_DIGITS[n % 10];
  const tens = Math.floor(n / 10), ones = n % 10;
  return CN_DIGITS[tens] + '十' + (ones ? CN_DIGITS[ones] : '');
}

/** 三套纪年并列：公元 / 干支 / 年号 */
export function tripleEra(year: number): string {
  const gz = ganzhiOf(year);
  const ry = reignYearOf(year);
  return `${year}（${gz}${ry ? ` · ${ry}` : ''}）`;
}
