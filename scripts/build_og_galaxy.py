#!/usr/bin/env python3
"""星图专用 OG 图生成器（build_og_galaxy.py）

绘制 site/public/og-galaxy.png —— 1200×630 的**深色版**社交分享图，供 /galaxy/ 页
（SeoHead 的 image 参数）使用，与全站米色 og.png 构成「日夜双模式」。

视觉语言与 og.png 一致（双线描边框、朱砂「状元之谱」印章、宋体、金色分隔线），
配色换成星图页的夜模式：玄青底 + 金点阵 + 米白文字。

手动运行：
    /Users/mba/.workbuddy/binaries/python/envs/default/bin/python scripts/build_og_galaxy.py

**不接入构建期**：产物是提交进仓库的静态图，且构建机（GitHub Actions ubuntu）无 Pillow，
接入只会徒增风险。数据变化时手动重跑即可。

点阵数量/年份取自 site/public/data/galaxy.json（存在则读，缺失则省略数字）——图上的
「571 星点」这类数字不是手写的。种子固定，同一份数据重跑结果一致。
"""
import json
import os
import random
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GALAXY_JSON = os.path.join(ROOT, 'site', 'public', 'data', 'galaxy.json')
OUT = os.path.join(ROOT, 'site', 'public', 'og-galaxy.png')

W, H = 1200, 630
SEED = 1283  # 1283 年，固定种子 → 可复现

# 夜模式配色（与 site/src/styles/galaxy.css 同源）
BG_TOP = (9, 14, 24)
BG_BOTTOM = (20, 30, 50)
GOLD = (212, 175, 55)
GOLD_LIGHT = (232, 217, 168)
GOLD_DIM = (169, 139, 63)
INK_PALE = (232, 226, 208)
CINNABAR = (158, 43, 34)

# Songti.ttc 子字体索引：0=Black 1=Bold 3=Light 4=STSong 6=Songti SC Regular
FONT_CANDIDATES = [
    ('/System/Library/Fonts/Supplemental/Songti.ttc', 0),
    ('/System/Library/Fonts/Supplemental/Songti.ttc', 1),
    ('/System/Library/Fonts/Songti.ttc', 0),
    ('/System/Library/Fonts/Supplemental/Kaiti.ttc', 0),
    ('/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc', 0),
    ('/usr/share/fonts/truetype/arphic/uming.ttc', 0),
]


def font(size, heavy=True):
    """取宋体；heavy 用 Black 档，正文用 Regular 档。系统无中文字体时退默认字体。"""
    idx_pref = (0, 1) if heavy else (6, 4)
    for path, _ in FONT_CANDIDATES:
        if not os.path.exists(path):
            continue
        for idx in idx_pref:
            try:
                return ImageFont.truetype(path, size, index=idx)
            except Exception:
                continue
    print('[og-galaxy] WARN: 未找到中文宋体，回退默认字体（字形可能不佳）', file=sys.stderr)
    return ImageFont.load_default()


def gradient():
    """玄青底：上深下浅的竖直渐变，叠加右侧暖金辉光。"""
    img = Image.new('RGB', (W, H), BG_TOP)
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / (H - 1)
        d.line(
            [(0, y), (W, y)],
            fill=tuple(round(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOTTOM)),
        )
    # 右上暖金辉光（星团所在）
    glow = Image.new('L', (W, H), 0)
    gd = ImageDraw.Draw(glow)
    gd.ellipse([560, 40, 1180, 560], fill=54)
    glow = glow.filter(ImageFilter.GaussianBlur(120))
    img = Image.composite(Image.new('RGB', (W, H), (58, 48, 26)), img, glow)
    return img


def star_field(img, rng):
    """金点阵：一条自左下向右上隆起的星带 + 稀疏散点；另缀少量米白与朱砂。

    不用均匀随机（那是噪点，不是星河）：主密度沿一条上升带分布，主体落在右半区。
    """
    layer = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    def put(x, y, r, color, a):
        d.ellipse([x - r, y - r, x + r, y + r], fill=color + (int(max(0, min(a, 255))),))

    # --- 星带主体：y = 0.80H 起，向右逐渐抬升到 0.30H ---
    for _ in range(260):
        t = rng.random() ** 0.85
        x = 90 + t * (W - 170)
        cy = H * (0.80 - 0.50 * t)
        y = rng.gauss(cy, 34)
        if not (58 < y < H - 58):
            continue
        r = rng.choice([1, 1, 1.2, 1.5, 2.0, 2.6])
        a = rng.randint(70, 150) + t * 80
        put(x, y, r, GOLD_LIGHT, a)

    # --- 稀疏散点：填满画面但保持克制 ---
    for _ in range(150):
        x = rng.uniform(70, W - 70)
        y = rng.uniform(70, H - 70)
        r = rng.choice([1, 1, 1.3, 1.6])
        put(x, y, r, INK_PALE, rng.randint(30, 68))

    # --- 少量亮星：带光晕，聚在右上星团 ---
    for _ in range(11):
        x = rng.uniform(520, 1140)
        y = rng.gauss(H * 0.42, 90)
        r = rng.choice([2.6, 3.0, 3.6])
        put(x, y, r * 3.4, GOLD, 26)
        put(x, y, r * 1.7, GOLD, 90)
        put(x, y, r, GOLD_LIGHT, 245)

    # --- 极少量朱砂点：呼应星图的 t=1 亮度 ---
    for _ in range(7):
        x = rng.uniform(200, 1130)
        y = rng.gauss(H * 0.62, 110)
        put(x, y, rng.choice([2.0, 2.4]), CINNABAR, rng.randint(150, 210))

    return Image.alpha_composite(img.convert('RGBA'), layer).convert('RGB')


def scrim(img):
    """左侧文字区压暗罩：让标题从点阵里「浮」出来，右侧星团保持明亮。

    罩色即底色，故只压暗点阵，不影响边框（x<58 时系数为 0）。
    """
    layer = Image.new('L', (W, H), 0)
    d = ImageDraw.Draw(layer)
    x0, x1 = 58, 940
    for x in range(x0, x1):
        a = 236 * (1 - (x - x0) / (x1 - x0)) ** 0.65
        d.line([(x, 132), (x, 596)], fill=int(a))
    # 上下羽化
    feather = Image.new('L', (W, H), 0)
    fd = ImageDraw.Draw(feather)
    fd.rectangle([x0, 168, x1, 562], fill=255)
    feather = feather.filter(ImageFilter.GaussianBlur(38))
    mask = ImageChops.multiply(layer, feather)
    base = img.convert('RGB')
    shade = Image.new('RGB', (W, H), (11, 17, 28))
    return Image.composite(shade, base, mask)


def draw_spaced(d, xy, text, fnt, fill, spacing=0.0, anchor_y='la'):
    """逐字绘制以实现字距（Pillow 无 letter-spacing）。spacing 为 em 倍数。"""
    x, y = xy
    for ch in text:
        d.text((x, y), ch, font=fnt, fill=fill, anchor=anchor_y)
        x += d.textlength(ch, font=fnt) + fnt.size * spacing
    return x


def spaced_width(d, text, fnt, spacing=0.0):
    return sum(d.textlength(c, font=fnt) for c in text) + fnt.size * spacing * max(len(text) - 1, 0)


def frame(img):
    """双线描边框（照 og.png 的结构，换金色）。"""
    d = ImageDraw.Draw(img)
    d.rectangle([40, 40, W - 40, H - 40], outline=GOLD_DIM + (170,), width=3)
    d.rectangle([54, 54, W - 54, H - 54], outline=GOLD_DIM + (70,), width=1)
    return img


def seal(img):
    """右上朱砂印章「状元之谱」（与 og.png 同一枚，落在深底上）。"""
    d = ImageDraw.Draw(img)
    x, y, s = 972, 96, 96
    d.rounded_rectangle([x, y, x + s, y + s], radius=8, fill=CINNABAR)
    f = font(30, heavy=False)
    for i, line in enumerate(('状元', '之谱')):
        w = spaced_width(d, line, f, 0.02)
        draw_spaced(d, (x + (s - w) / 2, y + 15 + i * 34), line, f, (245, 240, 228), 0.02)
    return img


def main():
    rng = random.Random(SEED)

    # ---- 星点数据（可选）：数量与年份区间全部取自构建产物 ----
    counts = {}
    if os.path.exists(GALAXY_JSON):
        with open(GALAXY_JSON, encoding='utf-8') as f:
            g = json.load(f)
        stars = g.get('stars') or []
        counts['stars'] = len(stars)
        counts['xr'] = g.get('xr')
        tiers = g.get('tiers') or []
        # 亮度分级 = tiers 表长度（story/full/confirmed/suspect/missing）
        counts['tiers'] = len(tiers)
    else:
        print('[og-galaxy] WARN: 未找到 galaxy.json，图上省略星点数（先跑 build_galaxy.py）',
              file=sys.stderr)

    img = gradient()
    img = star_field(img, rng)
    img = scrim(img)   # 文字区压暗（先点阵、后罩、再画边框，边框不被压暗）
    img = frame(img)
    img = seal(img)

    d = ImageDraw.Draw(img)
    X = 118

    # ---- 主标题：状元星河 ----
    f_title = font(94)  # Black
    draw_spaced(d, (X, 172), '状元星河', f_title, GOLD_LIGHT, 0.16)

    # ---- 副题：622 孙伏伽 — 1904 刘春霖 ----
    f_sub = font(30)
    draw_spaced(d, (X + 2, 306), '622 孙伏伽 — 1904 刘春霖', f_sub, GOLD, 0.10)

    # ---- 一句导语 ----
    f_line = font(26, heavy=False)
    draw_spaced(d, (X + 2, 372), '一千二百八十三年，六百个「天下第一」的人生轨迹，化作一片星海',
                f_line, INK_PALE, 0.05)

    # ---- 读图提示 ----
    f_small = font(22, heavy=False)
    draw_spaced(d, (X + 2, 424), '横轴科年 · 纵轴八朝 · 金亮者皆有其传', f_small, (150, 147, 138), 0.05)

    # ---- 金色分隔线 ----
    d.line([(X + 2, 484), (X + 560, 484)], fill=GOLD_DIM, width=2)

    # ---- 页脚：数据与交互能力（星点数为构建期实测，不手写） ----
    bits = []
    if counts.get('stars'):
        bits.append(f"{counts['stars']} 星点")
    if counts.get('tiers'):
        bits.append(f"{counts['tiers']} 级亮度")
    bits += ['拖拽平移 · 滚轮缩放', '移动端纵滚列表']
    f_foot = font(21, heavy=False)
    draw_spaced(d, (X + 2, 518), ' · '.join(bits), f_foot, GOLD, 0.08)

    img.save(OUT, 'PNG', optimize=True)
    size = os.path.getsize(OUT)
    print(f'[og-galaxy] {W}×{H} → {os.path.relpath(OUT, ROOT)} {size / 1024:.1f}KB'
          f" | 星点 {counts.get('stars', '—')} | 年份区间 {counts.get('xr', '—')}")
    if size > 300 * 1024:
        print('[og-galaxy] WARN: 体积超过 300KB，社交平台加载偏慢', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
