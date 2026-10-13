// RSS 订阅源：/rss.xml —— 发布的故事自动进入订阅流
import rss from '@astrojs/rss';
import { listStories } from '../lib/story';

export function GET(context) {
  const stories = listStories();
  return rss({
    title: '状元谱 · 故事',
    description: '历代状元的长篇故事：夺魁、沉浮与身后事。',
    site: context.site,
    trailingSlash: true,
    items: stories.map((s) => ({
      title: s.title,
      description: s.intro ?? s.subtitle ?? '',
      link: `/stories/${s.slug}/`,
      pubDate: s.date ? new Date(s.date) : new Date(),
    })),
  });
}
