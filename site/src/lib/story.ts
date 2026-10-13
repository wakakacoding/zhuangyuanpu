// 故事管线：content/stories/*.md → 渲染 HTML（含轶事卡/史实卡注入）
// 卡片标记语法（正文内单独成行）：
//   [[card:person_id:an:0]]  → 该人物 anecdotes 第 0 条（轶事卡）
//   [[card:person_id:ev:2]]  → 该人物 events 第 2 条（史实卡）
import fs from 'node:fs';
import path from 'node:path';
import yaml from 'js-yaml';
import { createMarkdownProcessor } from '@astrojs/markdown-remark';
import { anecdoteCardHTML, eventCardHTML, missingCardHTML, type SourceRec } from './cards';

const ROOT = process.cwd();
const DATA_DIR = path.resolve(ROOT, '../data');
const STORY_DIR = path.resolve(ROOT, '../content/stories');

export interface StoryMeta {
  slug: string;
  title: string;
  subtitle?: string;
  intro?: string;
  persons: string[];
  date?: string;
  featured?: boolean;
  status: 'draft' | 'published';
}

export interface Story extends StoryMeta {
  body: string;
}

let _sources: Record<string, SourceRec> | null = null;
export function loadSources(): Record<string, SourceRec> {
  if (_sources) return _sources;
  const dir = path.join(DATA_DIR, 'sources');
  _sources = Object.fromEntries(
    fs.readdirSync(dir)
      .filter((f) => f.endsWith('.yaml') && !f.startsWith('_'))
      .map((f) => {
        const d = yaml.load(fs.readFileSync(path.join(dir, f), 'utf8')) as SourceRec;
        return [d.id, d];
      }),
  );
  return _sources!;
}

export function loadPerson(id: string): any | null {
  const f = path.join(DATA_DIR, 'persons', `${id}.yaml`);
  return fs.existsSync(f) ? yaml.load(fs.readFileSync(f, 'utf8')) : null;
}

function loadEntityList(dir: string, id: string, key: string): any[] {
  const f = path.join(DATA_DIR, dir, `${id}.yaml`);
  if (!fs.existsSync(f)) return [];
  return (yaml.load(fs.readFileSync(f, 'utf8')) as any)?.[key] ?? [];
}

function parseStoryFile(file: string): Story | null {
  const raw = fs.readFileSync(file, 'utf8');
  const m = raw.match(/^---\n([\s\S]*?)\n---\n?([\s\S]*)$/);
  if (!m) return null;
  const fm = yaml.load(m[1]) as any;
  return {
    slug: fm.slug,
    title: fm.title,
    subtitle: fm.subtitle,
    intro: fm.intro,
    persons: fm.persons ?? [],
    date: fm.date,
    featured: !!fm.featured,
    status: fm.status ?? 'draft',
    body: m[2],
  };
}

export function listStories(includeDraft = false): StoryMeta[] {
  if (!fs.existsSync(STORY_DIR)) return [];
  return fs.readdirSync(STORY_DIR)
    .filter((f) => f.endsWith('.md') && !f.startsWith('_'))
    .map((f) => parseStoryFile(path.join(STORY_DIR, f)))
    .filter((s): s is Story => !!s && !!s.slug && !!s.title)
    .filter((s) => includeDraft || s.status === 'published')
    .map(({ body, ...meta }) => meta)
    .sort((a, b) =>
      Number(b.featured) - Number(a.featured) ||
      String(b.date ?? '').localeCompare(String(a.date ?? ''))
    );
}

export function getStory(slug: string): Story | null {
  if (!fs.existsSync(STORY_DIR)) return null;
  for (const f of fs.readdirSync(STORY_DIR)) {
    if (!f.endsWith('.md') || f.startsWith('_')) continue;
    const s = parseStoryFile(path.join(STORY_DIR, f));
    if (s?.slug === slug) return s;
  }
  return null;
}

const CARD_RE = /^\[\[card:([a-z0-9_]+):(an|ev):(\d+)\]\]\s*$/gm;

/** 把卡片标记替换为卡片 HTML（raw HTML 会被 markdown 渲染器原样透传） */
export function injectCards(body: string): { html: string; missing: string[] } {
  const sources = loadSources();
  const missing: string[] = [];
  const html = body.replace(CARD_RE, (whole, pid: string, kind: string, idxStr: string) => {
    const idx = Number(idxStr);
    const person = loadPerson(pid);
    if (!person) { missing.push(whole.trim()); return missingCardHTML(whole.trim()); }
    if (kind === 'an') {
      const a = loadEntityList('anecdotes', pid, 'anecdotes')[idx];
      if (!a) { missing.push(whole.trim()); return missingCardHTML(whole.trim()); }
      return `\n\n${anecdoteCardHTML(person.name, a, sources)}\n\n`;
    }
    const e = loadEntityList('events', pid, 'events')[idx];
    if (!e) { missing.push(whole.trim()); return missingCardHTML(whole.trim()); }
    return `\n\n${eventCardHTML(person.name, e, sources)}\n\n`;
  });
  return { html, missing };
}

let _processor: Awaited<ReturnType<typeof createMarkdownProcessor>> | null = null;
async function processor() {
  if (!_processor) _processor = await createMarkdownProcessor({ syntaxHighlight: false });
  return _processor;
}

export async function renderStory(slug: string) {
  const story = getStory(slug);
  if (!story) return null;
  const { html: withCards, missing } = injectCards(story.body);
  const p = await processor();
  const result = await p.render(withCards);
  const persons = story.persons
    .map((id) => loadPerson(id))
    .filter(Boolean);
  return {
    meta: story,
    html: result.code,
    headings: result.metadata.headings.filter((h) => h.depth === 2),
    persons,
    missing,
  };
}
