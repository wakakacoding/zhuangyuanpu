import fs from 'node:fs';
import path from 'node:path';
import yaml from 'js-yaml';

/**
 * 共享数据加载器：构建期读取 data/ 下的 YAML。
 * 各页面统一走这里，避免重复 fs.readdirSync 样板代码。
 */

export const DATA_DIR = path.resolve(process.cwd(), '../data');

/** 部署子路径前缀（GitHub Pages 项目页）：始终以 / 结尾，如 '/zhuangyuanpu/' */
export const BASE = import.meta.env.BASE_URL;

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

/**
 * 姓名 → 繁体名（R3-2b 繁简双匹配用）。
 * 来源：data/index/zhuangyuan_index.yaml 的 name_tw（build_index.py 用 OpenCC + 人名用字
 * 保护表生成，比在前端把查询词转繁更稳）。索引与人物卡一律**按姓名**关联，勿按 slug。
 * 特例收录者（探花／事实状元）不在状元索引里，繁体名在此补全——仅此两人，role 枚举不会增长。
 */
const SPECIAL_NAME_TW: Record<string, string> = { 商衍鎏: '商衍鎏', 赵楷: '趙楷' };

export function traditionalNames(): Record<string, string> {
  cache.nameTw ??= (() => {
    const f = path.join(DATA_DIR, 'index', 'zhuangyuan_index.yaml');
    const list: any[] = fs.existsSync(f) ? (loadYaml(f) as any[]) : [];
    const map: Record<string, string> = {};
    for (const e of list) {
      if (e?.name && e?.name_tw) map[e.name] = e.name_tw;
    }
    return { ...map, ...SPECIAL_NAME_TW };
  })();
  return cache.nameTw;
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

// ---------------------------------------------------------------------------
// 名录身份分层（R1.4-1/R1.4-2）
//   zhuangyuan 状元（缺省） / tanhua 探花 / de_facto 事实状元
//   凡「状元总数、朝代分布、科年密度、籍贯分布、覆盖率」一律以 zhuangyuan 为准；
//   特例是收录，不并入状元统计——否则 599 会被读成「599 位状元」。
// ---------------------------------------------------------------------------
export const ROLE_ORDER = ['zhuangyuan', 'tanhua', 'de_facto'] as const;
export type Role = (typeof ROLE_ORDER)[number];

export const ROLE_LABEL: Record<string, string> = {
  zhuangyuan: '状元',
  tanhua: '探花',
  de_facto: '事实状元',
};

/** 特例身份在页面上的身份说明（列表/档案页徽标配套文案；只讲名分，收录理由由页面统一交代） */
export const ROLE_NOTE: Record<string, string> = {
  zhuangyuan: '',
  tanhua: '本科一甲第三名，非状元',
  de_facto: '殿试唱名第一而以宗室避嫌抑置第二，非名分状元',
};

/** 名录身份：缺省即状元 */
export function roleOf(p: any): Role {
  const r = p?.role;
  return r === 'tanhua' || r === 'de_facto' ? r : 'zhuangyuan';
}

export function isZhuangyuan(p: any): boolean {
  return roleOf(p) === 'zhuangyuan';
}

/** 特例（非状元）：探花 / 事实状元 */
export function isSpecialRole(p: any): boolean {
  return roleOf(p) !== 'zhuangyuan';
}

/** 状元子集（口径基准：一切「状元统计」都从这里取数） */
export function zhuangyuanOnly(persons: any[]): any[] {
  return persons.filter(isZhuangyuan);
}

/** 特例子集（探花 / 事实状元） */
export function specialRoles(persons: any[]): any[] {
  return persons.filter(isSpecialRole);
}

// ---------------------------------------------------------------------------
// 档案状态分层（R1.4-5）
//   「没有小传」有两种成因，页面文案必须分开：
//     pending 待整理   —— 本站尚未撰写（整理进度）          默认
//     absent  史料阙如 —— 已人工查证确认无传世记载（历史结论）  须 verified_absent: true
//   不再把整理进度表述成历史结论。
// ---------------------------------------------------------------------------
export type ProfileStatus = 'filled' | 'pending' | 'absent';

export function profileStatus(p: any): ProfileStatus {
  if (p?.bio_short) return 'filled';
  return p?.verified_absent === true ? 'absent' : 'pending';
}

export interface ProfileStatusText {
  status: ProfileStatus;
  /** 展示文案（filled 时即 bio_short 原文） */
  label: string;
  /** 补充说明，仅 pending / absent 两种情况需要 */
  hint: string;
}

export function profileStatusText(p: any): ProfileStatusText {
  switch (profileStatus(p)) {
    case 'filled':
      return { status: 'filled', label: String(p.bio_short), hint: '' };
    case 'absent':
      return {
        status: 'absent',
        label: '史料阙如——榜上有名，史中无痕。',
        hint: '已经人工查证，确无传世记载留痕。',
      };
    default:
      return {
        status: 'pending',
        label: '待整理',
        hint: '本站尚未撰写小传——这是整理进度，不等于史料无载。',
      };
  }
}

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
