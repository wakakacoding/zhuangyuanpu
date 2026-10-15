import fs from 'node:fs';
import path from 'node:path';
import yaml from 'js-yaml';
import { DATA_DIR, allPersons, fullProfileIds } from './persons';
import { listStories } from './story';

/**
 * 补全计划看板：全部数字在构建期从 data/ 实测得出，页面不得手写任何数字。
 * 唯一的常量是「阶段目标」（写在开发计划文档里），集中在 GOALS / TARGETS。
 */

/** 阶段目标（来自《下一阶段开发计划》：名录 600、全字段档案 50、故事 15 篇） */
export const GOALS = {
  persons: 600,
  fullProfile: 50,
  stories: 15,
} as const;

/** 达标线：达标即解锁下一阶段功能 */
export const TARGETS = {
  coords: 0.6, // 坐标 60% → 完整籍贯地图
  starYear: 0.5, // 生年或 fl_year 50% → 星图
} as const;

export interface CoverageItem {
  key: string;
  label: string;
  /** 当前实测值 */
  cur: number;
  /** 分母：全量人数或阶段目标 */
  total: number;
  /** 达标线（0–1）；null = 只报进度不设线 */
  target: number | null;
  /** true = 分母是阶段目标（进度），此时不展示百分比——599/600 显示「100%」会失真 */
  goal?: boolean;
  note?: string;
}

export interface SourceItem {
  /** 数据目录名（data/<dir>） */
  key: string;
  label: string;
  /** 条目数 */
  n: number;
  /** 单位 */
  unit: string;
  /** 二级说明（分级构成等），无则省略 */
  detail?: string;
}

export interface CoverageStats {
  generated: string;
  persons: number;
  dynastyCount: number;
  items: CoverageItem[];
  stories: { published: number; goal: number };
  fullProfile: { cur: number; goal: number };
  relations: {
    files: number;
    total: number;
    /** 状元 ↔ 状元（本站内部）边数 */
    internal: number;
    /** 状元 → CBDB 外部人物边数 */
    external: number;
    byType: Array<{ type: string; n: number }>;
  };
  sources: {
    total: number;
    byTier: { A: number; B: number; C: number };
  };
  /** 各数据源条目数（看板末表） */
  sourceItems: SourceItem[];
}

function countYaml(dir: string): number {
  const abs = path.join(DATA_DIR, dir);
  if (!fs.existsSync(abs)) return 0;
  return fs.readdirSync(abs).filter((f) => f.endsWith('.yaml') && !f.startsWith('_')).length;
}

/** 某子目录下所有条目的某个数组字段总条数（如 events 的 83 条生平事件） */
function countEntries(dir: string, key: string): number {
  const abs = path.join(DATA_DIR, dir);
  if (!fs.existsSync(abs)) return 0;
  let n = 0;
  for (const f of fs.readdirSync(abs)) {
    if (!f.endsWith('.yaml') || f.startsWith('_')) continue;
    const doc = yaml.load(fs.readFileSync(path.join(abs, f), 'utf8')) as any;
    n += (doc?.[key] ?? []).length;
  }
  return n;
}

let cached: CoverageStats | null = null;

export function coverageStats(): CoverageStats {
  if (cached) return cached;

  const persons = allPersons();
  const n = persons.length;
  const stories = listStories();
  const fullIds = fullProfileIds();

  // ---- 关系边：逐文件实测 ----
  // 不用 data/index/relations_summary.yaml —— 该文件由 build_index.py 生成，
  // 最后一次生成早于 CBDB 收割（记 55 边），与 data/relations/ 实际不符。
  const relDir = path.join(DATA_DIR, 'relations');
  const byType = new Map<string, number>();
  let relTotal = 0;
  let relInternal = 0;
  let relFiles = 0;
  if (fs.existsSync(relDir)) {
    for (const f of fs.readdirSync(relDir)) {
      if (!f.endsWith('.yaml') || f.startsWith('_')) continue;
      const doc: any = yaml.load(fs.readFileSync(path.join(relDir, f), 'utf8'));
      const list: any[] = doc?.relations ?? [];
      if (list.length) relFiles++;
      for (const r of list) {
        relTotal++;
        if (String(r?.to_id ?? '').startsWith('cbdb:')) continue;
        relInternal++;
        const t = String(r?.type ?? '未分类');
        byType.set(t, (byType.get(t) ?? 0) + 1);
      }
    }
  }

  // ---- 史料出处：总数 + A/B/C 分级 ----
  const srcDir = path.join(DATA_DIR, 'sources');
  const tierCount = { A: 0, B: 0, C: 0 } as { A: number; B: number; C: number };
  let srcTotal = 0;
  if (fs.existsSync(srcDir)) {
    for (const f of fs.readdirSync(srcDir)) {
      if (!f.endsWith('.yaml') || f.startsWith('_')) continue;
      const s: any = yaml.load(fs.readFileSync(path.join(srcDir, f), 'utf8'));
      srcTotal++;
      if (s?.tier === 'A' || s?.tier === 'B' || s?.tier === 'C') tierCount[s.tier]++;
    }
  }

  // ---- 古今地名映射表条数 ----
  const geoFile = path.join(DATA_DIR, 'geo_map.yaml');
  const geoN = fs.existsSync(geoFile)
    ? ((yaml.load(fs.readFileSync(geoFile, 'utf8')) as any[]) ?? []).length
    : 0;

  const items: CoverageItem[] = [
    {
      key: 'persons',
      label: '名录收录',
      cur: n,
      total: GOALS.persons,
      target: null,
      goal: true,
      note: '目标：可考的历代文状元全量',
    },
    {
      key: 'coords',
      label: '坐标覆盖',
      cur: persons.filter((p) => p.lat != null && p.lng != null).length,
      total: GOALS.persons,
      target: TARGETS.coords,
      note: '达标线 60%，解锁完整籍贯地图',
    },
    {
      key: 'starYear',
      label: '生年或活动年',
      cur: persons.filter((p) => p.birth_year || p.fl_year).length,
      total: n,
      target: TARGETS.starYear,
      note: '生年或 CBDB 估算活动年（fl_year）者占比；达标线 50%，解锁星图，图上按精确/估算分色',
    },
    {
      key: 'lifespan',
      label: '生卒双全',
      cur: persons.filter((p) => p.birth_year && p.death_year).length,
      total: n,
      target: null,
      note: '史书多只记卒年，生年常阙如',
    },
    {
      key: 'bio',
      label: '一句话小传',
      cur: persons.filter((p) => p.bio_short).length,
      total: n,
      target: null,
    },
    {
      key: 'fullProfile',
      label: '全字段档案',
      cur: fullIds.size,
      total: GOALS.fullProfile,
      target: null,
      goal: true,
      note: '含仕途时间线（events）者；有 data/events/<id>.yaml 即计入',
    },
    {
      key: 'stories',
      label: '长篇故事',
      cur: stories.length,
      total: GOALS.stories,
      target: null,
      goal: true,
      note: '已发布（status: published）篇数',
    },
  ];

  const sourceItems: SourceItem[] = [
    { key: 'persons', label: '人物卡', n, unit: '人' },
    {
      key: 'events',
      label: '生平事件',
      n: countEntries('events', 'events'),
      unit: '条',
      detail: `${countYaml('events')} 人有事件表`,
    },
    {
      key: 'relations',
      label: '人物关系',
      n: relTotal,
      unit: '条',
      detail: `状元之间 ${relInternal} 条 · 涉外部人物（CBDB）${relTotal - relInternal} 条`,
    },
    { key: 'works', label: '著作', n: countEntries('works', 'works'), unit: '条' },
    {
      key: 'anecdotes',
      label: '轶事（与史实隔离）',
      n: countEntries('anecdotes', 'anecdotes'),
      unit: '条',
    },
    {
      key: 'sources',
      label: '史料出处',
      n: srcTotal,
      unit: '种',
      detail: `A 级 ${tierCount.A} · B 级 ${tierCount.B} · C 级 ${tierCount.C}`,
    },
    {
      key: 'geo_map',
      label: '古今地名映射',
      n: geoN,
      unit: '条',
    },
    { key: 'corrections', label: '勘误记录', n: countYaml('corrections'), unit: '条' },
    {
      key: 'stories',
      label: '长篇故事',
      n: stories.length,
      unit: '篇',
      detail: `目标 ${GOALS.stories} 篇`,
    },
  ];

  cached = {
    generated: new Date().toISOString().slice(0, 10),
    persons: n,
    dynastyCount: new Set(persons.map((p) => p.dynasty)).size,
    items,
    stories: { published: stories.length, goal: GOALS.stories },
    fullProfile: { cur: fullIds.size, goal: GOALS.fullProfile },
    relations: {
      files: relFiles,
      total: relTotal,
      internal: relInternal,
      external: relTotal - relInternal,
      byType: [...byType.entries()]
        .map(([type, c]) => ({ type, n: c }))
        .sort((a, b) => b.n - a.n || a.type.localeCompare(b.type)),
    },
    sources: { total: srcTotal, byTier: tierCount },
    sourceItems,
  };
  return cached;
}

/** 覆盖率百分比（0–100，一位小数） */
export function pct(cur: number, total: number): number {
  return total > 0 ? (cur / total) * 100 : 0;
}
