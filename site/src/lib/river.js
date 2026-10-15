/**
 * 仕途河流图模型（纯计算，无 DOM 依赖，可在 node 下直接 import 做回归）
 * ---------------------------------------------------------------------------
 * 输入：某人的 events 数组（data/events/<id>.yaml）
 * 输出：河心的采样折线 + 分段带宽 + 节点坐标，供 CareerRiver.astro 渲染 SVG。
 *
 * 三条口径（页面脚注须同步说明，避免读者误读）：
 *  1. 纵轴是「官位高下」，不是严格品级。唐宋明清品秩本不相同（如明代大学士
 *     品级仅正五品而权位最高），故本表是**跨朝代归一近似值**，取 0–10，越大越尊。
 *  2. 河宽随官位：官愈尊则河道愈宽，河口在「致仕」处收束。
 *  3. 只绘生前仕途：卒年之后的追赠、补谥、平反不入河流（另有 excluded 列表回传，
 *     由组件在脚注里点名，不静默丢弃）。
 */

export const CAREER_TYPES = ['授官', '升迁', '贬谪', '致仕'];

/** 渲染门槛：仕途事件少于 3 条不出图（阙如合法） */
export const MIN_NODES = 3;

/**
 * 官位高下表（0–10，越大越尊）。**跨朝代归一近似**。
 * 匹配规则：键按字符长度降序逐一 includes 命中，先长后短，避免「尚书」吃掉「吏部尚书」。
 * 未收录者不臆造：按事件类型回退（见 levelOf 注释）。
 */
export const RANK_TABLE = [
  // —— 宰执、三公、内阁
  ['右丞相', 9.6], ['左丞相', 9.6], ['丞相', 9.6], ['宰相', 9.6], ['枢密使', 9.6],
  ['平章事', 9.6], ['太师', 9.4], ['太傅', 9.4], ['太保', 9.4], ['少师', 9.4], ['少傅', 9.4],
  ['谨身殿大学士', 9.2], ['文渊阁大学士', 9.2], ['华盖殿大学士', 9.2], ['入阁预机务', 9.2],
  ['大学士', 9.2], ['少保', 9.2], ['信国公', 9.2], ['郡王', 9.2], ['亲王', 9.2], ['王郓', 9.2],
  ['太子太保', 9.0], ['太子少保', 9.0], ['义爵', 8.8], ['吏部尚书', 8.8], ['权吏部尚书', 8.8],
  ['兵部尚书', 8.6], ['户部尚书', 8.6], ['刑部尚书', 8.6], ['礼部尚书', 8.6], ['工部尚书', 8.6],
  ['侍中', 8.6], ['魏国公', 8.6], ['副掌率', 8.4], ['顺天燕', 8.4], ['翰林学士', 8.4],
  ['端明殿学士', 8.2], ['资政殿学士', 8.2], ['观文殿学士', 8.2], ['敷文阁直学士', 8.2],
  ['镇凤翔', 8.0], ['恩赏丞相', 8.0], ['大理卿', 7.8], ['农商总长', 7.8], ['农商部总长', 7.8],
  ['四川制置使', 7.8], ['节度使', 7.8], ['制置使', 7.8], ['宣抚使', 7.8],
  // —— 卿寺、部院
  ['敷文阁待制', 7.6], ['权直学士院', 7.6], ['直学士院', 7.6], ['尚书右丞', 7.6], ['尚书左丞', 7.6],
  ['户部侍郎', 7.4], ['刑部侍郎', 7.4], ['吏部侍郎', 7.4], ['礼部侍郎', 7.4], ['兵部侍郎', 7.4],
  ['民部侍郎', 7.4], ['权户部侍郎', 7.4], ['礼部右侍郎', 7.4], ['知制诰', 7.4], ['御史大夫', 7.4],
  ['实业部总长', 7.4], ['水利局总裁', 7.4], ['陕州刺史', 7.4], ['太子中庶子', 7.2], ['中书舍人', 7.2],
  ['大理少卿', 7.0], ['给事中', 7.0], ['太常卿', 7.0], ['转运副使', 6.8], ['转运使', 6.8],
  ['右谏议大夫', 6.8], ['提点刑狱', 6.8], ['江西提刑', 6.8], ['湖南提刑', 6.8], ['侍御史', 6.8],
  ['两淮盐政总理', 6.8], ['秘书少监', 6.6], ['知平江府', 6.6], ['知成都府', 6.6], ['治书侍御史', 6.6],
  ['翰林院侍读', 6.4], ['经筵讲官', 6.4], ['知福州', 6.4], ['中央教育会会长', 6.4], ['侍读', 6.4],
  ['侍讲', 6.4], ['知贡举', 6.2], ['同知贡举', 6.2], ['吏部郎官', 6.2], ['刑部郎官', 6.2],
  ['尚书左司郎官', 6.2], ['库部郎中', 6.2], ['刑部郎中', 6.2], ['吏部郎中', 6.2], ['兵部郎中', 6.2],
  ['户部郎中', 6.2], ['礼部郎中', 6.2], ['右司', 6.2], ['提学使', 6.2], ['咨议局议长', 6.0],
  ['三司关西道判官', 6.0], ['度支判官', 6.0], ['提举皇城司', 6.0], ['知婺州', 6.0], ['知瑞州', 6.0],
  ['知赣州', 6.0], ['知州', 6.0], ['知府', 6.0],
  // —— 监司、郡守、郎官
  ['宁海军节度判官', 5.8], ['军器监', 5.8], ['将作监', 5.8], ['预备立宪公会副会长', 5.8], ['开封府推官', 5.6],
  ['殿中丞', 5.6], ['殿中侍御史', 5.6], ['监察御史', 5.6], ['节度判官', 5.6], ['商部头等顾问官', 5.6],
  ['太子中允', 5.6], ['员外郎', 5.6], ['教育厅厅长', 5.6], ['教育厅长', 5.6], ['镇东军签判', 5.4],
  ['通判', 5.4], ['太常博士', 5.4], ['太常丞', 5.4], ['判官', 5.4], ['内史', 5.4], ['资政院议员', 5.4],
  ['左补阙', 5.2], ['补阙', 5.2], ['直史馆', 5.2], ['推官', 5.2], ['观察推官', 5.2],
  ['高等学堂提调', 5.2], ['高等学堂监督', 5.2], ['翰林院修撰', 5.0], ['修撰', 5.0], ['展书官', 5.0],
  ['农事试验场场长', 5.0], ['议员', 4.8], ['右拾遗', 4.6], ['左拾遗', 4.6], ['拾遗', 4.6],
  ['大理评事', 4.4], ['校书郎', 4.4], ['知鱼台县', 4.2], ['知县', 4.2], ['县令', 4.2],
  ['秘书省正字', 4.2], ['御林侍卫', 4.0], ['太乐丞', 3.8], ['幕府', 2.8], ['司仓参军', 2.6],
  ['司户参军', 2.6], ['参军', 2.6],
];

/** 「官位高下」纵轴的五个区段，用于背景横带与图例 */
export const RANK_BANDS = [
  { from: 8.5, to: 10, label: '内阁·宰执' },
  { from: 7.0, to: 8.5, label: '卿寺·部院' },
  { from: 5.0, to: 7.0, label: '监司·郡守' },
  { from: 3.0, to: 5.0, label: '县令·郎官' },
  { from: 0.0, to: 3.0, label: '幕职·佐贰' },
];

const SORTED_RANKS = [...RANK_TABLE].sort((a, b) => b[0].length - a[0].length);

/** 文本 → 官位高下；无收录官名返回 null（不臆造） */
export function rankOf(text) {
  if (!text) return null;
  for (const [key, v] of SORTED_RANKS) {
    if (text.includes(key)) return v;
  }
  return null;
}

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

/**
 * 单个事件的官位值。
 * **只认 title**：description 里出现的官名未必是传主的（如王维条「张九龄为中书侍郎
 * 同平章事」，同平章事是张九龄的官，不是王维的），全文匹配会张冠李戴。
 * 仅在 title 无名、且该事件本身就是「授官/贬谪」（这类事件的 description 通常写明
 * 除授何职，如「责授太子中允」）时，才回退匹配 description。
 */
function rankFor(n) {
  const hit = rankOf(n.title);
  if (hit != null) return { value: hit, from: 'title' };
  if (n.type === '授官' || n.type === '贬谪') {
    const alt = rankOf(n.description ?? '');
    if (alt != null) return { value: alt, from: 'description' };
  }
  return { value: null, from: null };
}

/**
 * 逐个事件定官位高下。
 * - 命中官名 → 用表值
 * - 未命中：首条取 3.2 起手（贬谪起手 2.6）；此后
 *   授官/升迁 = 沿用前值（**不臆造升幅**，图上仍标「升迁」徽标）；
 *   贬谪 = 前值 − 1.6；致仕 = 前值 − 0.3
 * - 事后约束：升迁不倒退（≥ 前值）；贬谪必降（≤ 前值 − 1.0）；致仕不高于前值
 */
export function levelsOf(nodes) {
  let prev = null;
  return nodes.map((n) => {
    const { value: hit, from } = rankFor(n);
    let v;
    if (hit != null) v = hit;
    else if (prev == null) v = n.type === '贬谪' ? 2.6 : 3.2;
    else if (n.type === '贬谪') v = prev - 1.6;
    else if (n.type === '致仕') v = prev - 0.3;
    else v = prev; // 授官 / 升迁 未见官名 → 不臆造升幅，沿用前值
    if (prev != null) {
      if (n.type === '升迁') v = Math.max(v, prev);
      else if (n.type === '贬谪') v = Math.min(v, prev - 1.0);
      else if (n.type === '致仕') v = Math.min(v, prev - 0.1);
    }
    v = clamp(v, 0.8, 9.8);
    prev = v;
    return { level: Math.round(v * 100) / 100, levelFrom: from };
  });
}

/** 出处最高等级（与档案页时间线同一口径：A 金 / B 墨 / C 朱砂） */
export function topTierOf(sourceIds = [], sources = {}) {
  const tiers = sourceIds.map((s) => sources[s]?.tier).filter(Boolean);
  return tiers.includes('A') ? 'A' : tiers.includes('B') ? 'B' : 'C';
}

/**
 * 构建河流图数据。
 * @param {Array} events 该人物的 events 数组
 * @param {object} opts  { deathYear, sources, width, height }
 * @returns {null | object} 仕途事件 < MIN_NODES 或无生前仕途事件时返回 null
 */
export function buildRiver(events = [], opts = {}) {
  const {
    deathYear = null, sources = {}, width = 760, height = 300,
    padL = 54, padR = 22, padT = 30, padB = 40,
  } = opts;

  const career = (events ?? [])
    .filter((e) => CAREER_TYPES.includes(e?.type))
    .slice()
    .sort((a, b) => a.year - b.year);

  // 生前过滤：卒后追赠／平反不入河流（回传，由脚注点名）
  const drawn = [], excluded = [];
  for (const e of career) {
    if (deathYear != null && e.year > deathYear) excluded.push(e);
    else drawn.push(e);
  }
  if (drawn.length < MIN_NODES) return null;

  const lv = levelsOf(drawn);
  const nodes = drawn.map((e, i) => ({
    event: e,                                   // 回指原始事件，便于组件算时间线锚点
    year: e.year,
    yearPrecision: e.year_precision ?? 'exact',
    type: e.type,
    title: e.title,
    tier: topTierOf(e.source_ids, sources),
    demoted: e.type === '贬谪',
    level: lv[i].level,
    levelFrom: lv[i].levelFrom,
  }));

  // ---- 横轴范围（含卒年，便于把「卒」标在轴上） ----
  const years = nodes.map((n) => n.year);
  let x0 = Math.min(...years), x1 = Math.max(...years);
  if (deathYear != null && deathYear > x1) x1 = deathYear;
  const span = Math.max(x1 - x0, 8);
  x0 -= span * 0.06; x1 += span * 0.06;

  const plotW = width - padL - padR;
  const plotH = height - padT - padB;
  const X = (y) => padL + ((y - x0) / (x1 - x0)) * plotW;
  const Y = (lvl) => padT + (1 - lvl / 10) * plotH;      // 固定 0–10 域，跨人物可比
  const halfW = (lvl) => 4 + (lvl / 10) * 12;             // 河宽随官位 8–32px

  // 同年多事（如商辂 1477、文天祥 1275）横向微错开，避免出现零宽竖段的控制点退化
  const byYear = new Map();
  for (const n of nodes) byYear.set(n.year, [...(byYear.get(n.year) ?? []), n]);
  const nudge = new Map();
  for (const [yr, list] of byYear) {
    if (list.length < 2) continue;
    list.forEach((n, k) => nudge.set(n, (k - (list.length - 1) / 2) * 7));
  }

  const pts = nodes.map((n) => ({
    ...n,
    short: shortLabel(n.title),
    x: X(n.year) + (nudge.get(n) ?? 0), y: Y(n.level), hw: halfW(n.level),
  }));

  // ---- Catmull-Rom → 三次贝塞尔，逐段采样成折线（段与段在节点处共用坐标，接缝无缝）----
  const SAMPLES = 26;
  const spans = [];
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[i - 1] ?? pts[i], p1 = pts[i], p2 = pts[i + 1], p3 = pts[i + 2] ?? pts[i + 1];
    const c1 = { x: p1.x + (p2.x - p0.x) / 6, y: p1.y + (p2.y - p0.y) / 6 };
    const c2 = { x: p2.x - (p3.x - p1.x) / 6, y: p2.y - (p3.y - p1.y) / 6 };
    const top = [], bottom = [], mid = [];
    for (let s = 0; s <= SAMPLES; s++) {
      const t = s / SAMPLES;
      const mt = 1 - t;
      const bx = mt ** 3 * p1.x + 3 * mt * mt * t * c1.x + 3 * mt * t * t * c2.x + t ** 3 * p2.x;
      const by = mt ** 3 * p1.y + 3 * mt * mt * t * c1.y + 3 * mt * t * t * c2.y + t ** 3 * p2.y;
      const hw = p1.hw + (p2.hw - p1.hw) * t;
      mid.push([bx, by]);
      top.push([bx, by - hw]);
      bottom.push([bx, by + hw]);
    }
    spans.push({
      from: i, to: i + 1,
      demoted: pts[i + 1].demoted,
      band: ringPath(top, bottom, p1.hw, p2.hw),
      line: polyline(mid),
    });
  }

  // ---- 年份刻度（1/2/5 × 10^k 里挑最小可用步长，控制在 6 格以内）----
  const yLo = Math.min(...years), yHi = Math.max(...years);
  const cands = [];
  for (let k = 0; k <= 4; k++) for (const m of [1, 2, 5]) cands.push(m * 10 ** k);
  cands.sort((a, b) => a - b);
  const step = cands.find((s) => (yHi - yLo) / s <= 6) ?? cands[cands.length - 1];
  const ticks = [];
  for (let y = Math.ceil(yLo / step) * step; y <= yHi; y += step) ticks.push({ year: y, x: X(y) });
  if (ticks.length < 2) ticks.push({ year: yHi, x: X(yHi) });

  const bands = RANK_BANDS.map((b) => ({
    ...b,
    yTop: Y(b.to), yBottom: Y(b.from), yMid: (Y(b.to) + Y(b.from)) / 2,
    // 本人生涯真正踏到过的官位区段才着色：空段留白，免得读者误以为有过那段经历
    used: pts.some((p) => p.level >= b.from && (p.level < b.to || b.to >= 10)),
  }));

  // ---- 标签挑选与避让 ----
  // 必标：首、末、峰值、全部贬谪；其余隔一标一（避免密集成排）
  const peak = pts.reduce((a, b) => (b.level > a.level ? b : a), pts[0]);
  const labelIdx = new Set([0, pts.length - 1, pts.indexOf(peak)]);
  pts.forEach((p, i) => { if (p.demoted) labelIdx.add(i); });
  const stride = Math.max(1, Math.ceil(pts.length / 6));
  pts.forEach((p, i) => { if (i % stride === 0) labelIdx.add(i); });

  // 夺魁基准线：仅在确实落在横轴范围内时给出，否则为 null（组件不画）
  const qukuiYear = (events ?? []).find((e) => e?.type === '夺魁')?.year ?? null;
  const qukuiX = qukuiYear != null && qukuiYear >= yLo && qukuiYear <= yHi ? X(qukuiYear) : null;

  // 卒年基准线：仅在卒年晚于最后一个仕途节点时给出
  const lastX = pts[pts.length - 1].x;
  const deathX = deathYear != null && deathYear > pts[pts.length - 1].year ? X(deathYear) : null;

  // 已占位：节点圆点 + 两条基准线的抬头文字（免得标签压上去）
  const reserved = [];
  if (qukuiX != null) reserved.push({ x0: qukuiX - 24, x1: qukuiX + 24, y0: 6, y1: 28 });
  if (deathX != null) reserved.push({ x0: deathX - 42, x1: deathX + 2, y0: 6, y1: 28 });
  placeLabels(pts, labelIdx, { width, height, padL, padR, reserved });

  return {
    width, height, padL, padR, padT, padB,
    nodes: pts,
    spans, ticks, bands,
    axis: { x0, x1, yTop: padT, yBottom: padT + plotH, lastX },
    qukuiYear, qukuiX, deathX,
    excludedPosthumous: excluded,
    peak,
    minLevel: Math.min(...pts.map((p) => p.level)),
    maxLevel: Math.max(...pts.map((p) => p.level)),
  };
}

/** 标签文本（年份 + 短标题），约年带「≈」标记 */
export function labelText(n) {
  return `${n.year}${n.yearPrecision === 'about' ? '≈' : ''} ${n.short ?? n.title}`;
}

/** 短标签：14 字以内直接给；更长优先在顿断处收口，收不住才硬截 */
export function shortLabel(t = '') {
  const s = String(t).replace(/\s+/g, '');
  if (s.length <= 14) return s;
  const m = s.slice(0, 15).match(/^.{6,}[，,；;、（(·]/);
  if (m) return m[0].replace(/[，,；;、（(·]$/, '');
  return s.slice(0, 14) + '…';
}

/** 按全文种字宽估标签宽度（font-size 9.5px：CJK 约 9.9px、数字约 5.4px） */
function textWidth(s) {
  let w = 0;
  for (const ch of s) w += /[\u3000-\u9fff\uff00-\uffef]/.test(ch) ? 9.9 : 5.4;
  return w;
}

/**
 * 贪心避让地给节点排标签位置，避免压线、压节点、压基准线抬头、互相叠字。
 * 候选位：正上方 / 正下方 / 再抬一层 / 再压一层；取第一个不撞车的。
 * 贴左边界的标签改为左对齐（text-anchor=start），贴右边界改右对齐，避免飞出画布。
 * 结果直接挂在节点上：labelShow、labelX、labelY、labelAnchor。
 */
function placeLabels(pts, labelIdx, { width, height, padL, padR, reserved = [] }) {
  const GAP = 1.5;
  const EDGE = 2;
  const occupied = [
    ...reserved,
    ...pts.map((p) => ({ x0: p.x - 4.4, x1: p.x + 4.4, y0: p.y - 4.4, y1: p.y + 4.4 })),
  ];

  const candidates = (p) => [
    p.y - p.hw - 7, p.y - p.hw - 20, p.y - p.hw - 33, p.y - p.hw - 46, p.y - p.hw - 59,
    p.y + p.hw + 12.5, p.y + p.hw + 25.5, p.y + p.hw + 38.5, p.y + p.hw + 51.5, p.y + p.hw + 64.5,
  ];

  pts.forEach((p, i) => {
    p.labelShow = labelIdx.has(i);
    p.labelX = p.x;
    p.labelY = p.y;
    p.labelAnchor = 'middle';
    if (!p.labelShow) return;

    const w = textWidth(labelText(p));
    let x0 = p.x - w / 2, x1 = p.x + w / 2;
    if (x0 < padL + EDGE) {
      p.labelAnchor = 'start'; p.labelX = padL + EDGE; x0 = p.labelX; x1 = x0 + w;
    } else if (x1 > width - padR - EDGE) {
      p.labelAnchor = 'end'; p.labelX = width - padR - EDGE; x1 = p.labelX; x0 = x1 - w;
    }

    const area = (b) => occupied.reduce((s, o) => {
      const ox = Math.min(b.x1, o.x1) - Math.max(b.x0, o.x0);
      const oy = Math.min(b.y1, o.y1) - Math.max(b.y0, o.y0);
      return ox > 0 && oy > 0 ? s + ox * oy : s;
    }, 0);

    let best = null;
    for (const y of candidates(p)) {
      const b = { x0: x0 - GAP, x1: x1 + GAP, y0: y - 9.6 - GAP, y1: y + 2.6 + GAP };
      if (b.y0 < 4 || b.y1 > height - 4) continue;
      const a = area(b);
      if (a === 0) { p.labelY = y; occupied.push(b); return; }
      if (!best || a < best.a) best = { y, b, a };
    }
    // 兜底：无空位时取重叠面积最小的一档（仍全部画出，不静默丢弃）
    const y = best ? best.y : p.y - p.hw - 7;
    p.labelY = y;
    occupied.push({ x0: x0 - GAP, x1: x1 + GAP, y0: y - 9.6, y1: y + 2.6 });
  });
}

function polyline(ps) {
  return ps.map((p, i) => `${i ? 'L' : 'M'}${round(p[0])} ${round(p[1])}`).join(' ');
}

/** 闭合流带：河首圆头 → 上边界 → 河尾 → 下边界回程 → 闭合 */
function ringPath(top, bottom, hwStart, hwEnd) {
  const last = top.length - 1;
  const seq = [
    [top[0][0] - hwStart * 0.5, top[0][1]],
    ...top,
    [top[last][0] + hwEnd * 0.5, top[last][1]],
    [bottom[last][0] + hwEnd * 0.5, bottom[last][1]],
    ...bottom.slice().reverse(),
    [bottom[0][0] - hwStart * 0.5, bottom[0][1]],
  ];
  return seq.map((p, i) => `${i ? 'L' : 'M'}${round(p[0])} ${round(p[1])}`).join(' ') + ' Z';
}

const round = (v) => Math.round(v * 10) / 10;
