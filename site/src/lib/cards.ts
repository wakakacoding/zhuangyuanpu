// 轶事卡 / 史实卡 HTML 生成器 —— 正史(A) / 方志·笔记(B) / 传说(C) 三级视觉
// 供故事管线 lib/story.ts 注入卡片使用；person 详情页后续可复用同套 class
export interface SourceRec {
  id: string;
  title: string;
  tier: 'A' | 'B' | 'C';
  juan?: string | null;
  quote?: string | null;
  url?: string | null;
  note?: string | null;
}

export const TIER_LABEL: Record<string, string> = {
  A: '正史',
  B: '方志·笔记',
  C: '传说',
};

const esc = (s: unknown): string =>
  String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');

function sourcesBlockHTML(sourceIds: string[] | undefined, sources: Record<string, SourceRec>): string {
  const rows = (sourceIds ?? [])
    .map((sid) => sources[sid])
    .filter(Boolean)
    .map((s) => {
      const head = `<span class="tier tier-${esc(s.tier)}">${esc(s.tier)}</span> ${esc(s.title)}${s.juan ? ` · ${esc(s.juan)}` : ''}`;
      const inner =
        (s.quote ? `<blockquote>${esc(s.quote)}</blockquote>` : '') +
        (s.note ? `<p class="note">${esc(s.note)}</p>` : '');
      return inner
        ? `<details class="src"><summary>${head}</summary>${inner}</details>`
        : `<div class="src-flat">${head}</div>`;
    });
  if (rows.length === 0) return '';
  return `<div class="s-card-srcs">${rows.join('')}</div>`;
}

/** 轶事卡：数据来自 data/anecdotes/<person>.yaml，tier 即 C 级传说为主 */
export function anecdoteCardHTML(
  personName: string,
  a: { title: string; content: string; tier?: string; source_ids?: string[]; note?: string },
  sources: Record<string, SourceRec>,
): string {
  const tier = (a.tier ?? 'C').toUpperCase();
  const label = TIER_LABEL[tier] ?? '传说';
  return `
<aside class="s-card s-anecdote tier-${esc(tier)}">
  <header class="s-card-head"><span class="s-chip">${esc(label)} · ${esc(tier)} 级</span><span class="s-card-person">${esc(personName)}</span></header>
  <h4 class="s-card-title">${esc(a.title)}</h4>
  <p class="s-card-body">${esc(a.content)}</p>
  ${sourcesBlockHTML(a.source_ids, sources)}
  ${a.note ? `<p class="s-note">备考：${esc(a.note)}</p>` : ''}
</aside>`;
}

/** 史实卡：数据来自 data/events/<person>.yaml，source 决定 tier（A=正史…） */
export function eventCardHTML(
  personName: string,
  e: { year: number; year_end?: number; year_precision?: string; type: string; title: string; description?: string; source_ids?: string[] },
  sources: Record<string, SourceRec>,
): string {
  const tiers = (e.source_ids ?? []).map((sid) => sources[sid]?.tier).filter(Boolean) as string[];
  const top = tiers.includes('A') ? 'A' : tiers.includes('B') ? 'B' : 'C';
  const year = `${e.year}${e.year_end ? `–${e.year_end}` : ''}${e.year_precision === 'about' ? '（约）' : ''}`;
  return `
<aside class="s-card s-fact tier-${esc(top)}">
  <header class="s-card-head"><span class="s-chip">${esc(TIER_LABEL[top])} · ${esc(top)} 级</span><span class="s-card-person">${esc(personName)} · ${esc(year)}</span></header>
  <h4 class="s-card-title">【${esc(e.type)}】${esc(e.title)}</h4>
  ${e.description ? `<p class="s-card-body">${esc(e.description)}</p>` : ''}
  ${sourcesBlockHTML(e.source_ids, sources)}
</aside>`;
}

/** 占位卡：标记引用了不存在的数据，构建期可见（不静默吞掉） */
export function missingCardHTML(marker: string): string {
  return `<aside class="s-card s-missing"><p class="s-note">卡片数据缺失：${esc(marker)}（请检查 data/ 对应 YAML）</p></aside>`;
}
