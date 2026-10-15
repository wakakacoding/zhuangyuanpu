#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_links.py —— 站点内部链接死链检查器（构建产物侧）

用途
----
对构建产物 site/dist 全量爬取 HTML 里的内部 href/src，把每个链接按 URL 规则
映射回文件系统；映射不到的（= 部署到 GitHub Pages 后必然 404）即判为错误，
输出清单并按「错误类型 / 来源页面」分桶统计。

为什么必须查构建产物而不是源码
------------------------------
Astro 里 ``href={BASE + 'persons/' + id + '/'}`` 这种拼接在源码层看不出问题，
只有产物里才能发现 ``cbdb:110375`` 这类不存在的目标（本项目现存 4893 处）。
本脚本立场同 validate.py：**宁缺毋滥**——解析不了的一律进 errors，不静默放行。

三类判定
--------
* ``dead``         路径在 dist 里找不到对应文件（真 404）
* ``case-mismatch`` 文件存在但**大小写不符**（macOS 本机能打开、GitHub Pages 404）
* ``missing-base`` 以 ``/`` 开头的绝对路径没带 ``/zhuangyuanpu`` 前缀
                   （localhost 根目录预览时看不出，部署到项目页必 404）
* 警告 ``no-trailing-slash``：指向目录却漏了结尾斜杠（Pages 会 301，不致命）

设计约束
--------
* 只读：不修改、不新建任何站点文件；纯标准库，无第三方依赖。
* 只查站内（同源）：外链、``mailto:`` / ``tel:`` / ``javascript:`` / ``data:``
  一律跳过并计数；``http(s)://wakakacoding.github.io`` 视为站内。
* 边界：只扫 ``.html`` 里的 href/src/srcset（含 CSS 内联 ``url()`` 不做）。
  rss.xml / sitemap 的 ``<loc>`` 不在覆盖范围。

⚠ 必须是**同一次构建之后**的 dist
----------------------------------
产物陈旧会把「数据里已经删掉、页面还没重建」的链接报成死链。实测：T2 已从
``data/relations/`` 删除 10 个越界 CBDB 记录的 12 条边，但当时的 dist 仍是旧产物，
于是多报 12 处（4893 vs 数据侧现存 4881）。跑之前先 ``npm run build``。

用法
----
    # 基线报告（只报告，不因此失败）
    python3 scripts/check_links.py --report-only --top 30

    # 接入构建后的严格模式：有任何死链即非零退出
    python3 scripts/check_links.py --max-errors 0

    # 排查时排除已知存量、只关心新引入的死链
    python3 scripts/check_links.py --ignore 'cbdb:' --report-only

    # 落盘机器可读结果 + Markdown 报告
    python3 scripts/check_links.py --json /tmp/links.json --md /tmp/links.md

退出码
------
0  错误数 <= --max-errors（默认 0）；或指定了 --report-only；或 dist 缺失但带了 --allow-missing-dist
1  错误数 > --max-errors
2  用法 / 环境错误（dist 不存在且没给 --allow-missing-dist、参数非法等）
"""

from __future__ import annotations

import argparse
import json
import os
import posixpath
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit

# ---------------------------------------------------------------- 常量与正则

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIST = REPO_ROOT / "site" / "dist"
DEFAULT_BASE = "/zhuangyuanpu"
SITE_HOST = "wakakacoding.github.io"

HTML_SUFFIXES = {".html", ".htm"}

# href="..." / src="..."（单双引号均支持）
_ATTR_RE = re.compile(r"""\b(?:href|src)\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.I)
# srcset="a.png 1x, b.png 2x" 取每个候选的首段
_SRCSET_RE = re.compile(r"""\bsrcset\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.I)
# <script>/<style> 的**内容**（保留开标签，见 strip_script_bodies）
_SCRIPT_BODY_RE = re.compile(r"(<(script|style)\b[^>]*>)(.*?)(</\2\s*>)", re.I | re.S)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)

# 明确跳过、不算站内链接的协议
_SKIP_SCHEMES = {
    "mailto", "tel", "sms", "javascript", "data", "blob",
    "ftp", "ftps", "magnet", "irc", "whatsapp", "file", "chrome",
}

# 错误分类标签
TYPE_DEAD = "dead"
TYPE_CASE = "case-mismatch"
TYPE_BASE = "missing-base"
TYPE_OUTSIDE = "outside-dist"
TYPE_TRAILING = "no-trailing-slash"

TYPE_LABEL = {
    TYPE_DEAD: "死链（dist 内无此文件）",
    TYPE_CASE: "大小写不符（本机可开、Pages 404）",
    TYPE_BASE: "绝对路径缺 base 前缀",
    TYPE_OUTSIDE: "相对路径越出 dist 根",
}


# ---------------------------------------------------------------- 文件系统映射

class DistIndex:
    """dist 目录的惰性索引，带目录列举缓存（大小写精确性检查用）。"""

    def __init__(self, dist: Path) -> None:
        self.dist = dist
        self._dirs: dict[str, set[str] | None] = {}

    def entries(self, rel_dir: str) -> set[str] | None:
        if rel_dir in self._dirs:
            return self._dirs[rel_dir]
        abs_dir = self.dist / rel_dir if rel_dir else self.dist
        try:
            got = set(os.listdir(abs_dir))
        except OSError:
            got = None
        self._dirs[rel_dir] = got
        return got

    def exact_exists(self, rel: str) -> bool:
        """逐段按真实大小写核对 rel 是否存在。"""
        cur = ""
        parts = [p for p in rel.split("/") if p not in ("", ".")]
        for part in parts:
            got = self.entries(cur)
            if got is None or part not in got:
                return False
            cur = f"{cur}/{part}" if cur else part
        return True


def resolve(raw: str, src_dir: str, idx: DistIndex, base: str) -> tuple[str, str, str]:
    """把一个原始链接解析为 (kind, target, detail)。

    kind ∈ {skip-external, skip-scheme, skip-fragment, skip-empty,
            ok, warn, error}；target 为归一化后的站内路径（绝对，带 base）。
    """
    raw = (raw or "").strip()
    if not raw:
        return "skip-empty", "", ""
    if raw.startswith("#"):
        return "skip-fragment", "", ""

    split = urlsplit(raw)
    scheme = (split.scheme or "").lower()
    if scheme in _SKIP_SCHEMES:
        return "skip-scheme", "", scheme
    if scheme not in ("", "http", "https"):
        return "skip-scheme", "", scheme or "(无 scheme)"

    if split.netloc and split.netloc.lower() != SITE_HOST:
        return "skip-external", "", split.netloc
    if raw.startswith("//") and not split.netloc:
        return "skip-external", "", raw[:60]

    path = unquote(split.path)
    if not path:
        # 纯 query / 空路径
        return "skip-fragment", "", ""

    # --- 归一化为 dist 相对路径 rel -------------------------------------
    if path.startswith("/"):
        if path == base or path.startswith(base + "/"):
            rel = path[len(base):].lstrip("/")
        else:
            return "error", path, TYPE_BASE
    else:
        rel = posixpath.normpath(posixpath.join(src_dir, path))
        if rel == ".":
            rel = ""
        if rel.startswith(".."):
            return "error", path, TYPE_OUTSIDE
        if rel.startswith("/"):
            rel = rel.lstrip("/")

    abs_url = f"{base}/{rel}" if rel else f"{base}/"

    # --- 落到文件系统 ----------------------------------------------------
    if rel == "" or path.endswith("/"):
        cand = [posixpath.join(rel, "index.html") if rel else "index.html"]
    else:
        cand = [rel, posixpath.join(rel, "index.html"), rel + ".html"]

    for c in cand:
        if (idx.dist / c).exists():
            if not idx.exact_exists(c):
                return "error", abs_url, TYPE_CASE
            # c == rel 只可能是「不带结尾斜杠却指向目录」这一种情况
            # （带斜杠时候选直接是 xxx/index.html）：Pages 会 301，不算错，记警告。
            # 注意 macOS 的 Path.exists() 对目录同样返回 True，必须显式判 is_dir()。
            if c == rel and not path.endswith("/") and (idx.dist / c).is_dir():
                return "warn", abs_url, TYPE_TRAILING
            return "ok", abs_url, ""

    return "error", abs_url, TYPE_DEAD


# ---------------------------------------------------------------- 扫描

def strip_script_bodies(html: str) -> str:
    """挖掉 <script>/<style> 的**内容**、以及 HTML 注释，只留开标签。

    开标签必须保留：``<script src="...">`` 的 src 是真链接；而内联脚本里的
    JS 模板字符串（``href="${base}persons/${s.s}"``）不是链接，直接爬会误报。
    """
    def _blank(m: re.Match[str]) -> str:
        return m.group(1) + m.group(4)

    html = _SCRIPT_BODY_RE.sub(_blank, html)
    return _COMMENT_RE.sub("", html)


def extract_links(html: str) -> list[str]:
    html = strip_script_bodies(html)
    out: list[str] = []
    for m in _ATTR_RE.finditer(html):
        out.append(m.group(1) if m.group(1) is not None else m.group(2))
    for m in _SRCSET_RE.finditer(html):
        val = m.group(1) if m.group(1) is not None else m.group(2)
        for item in (val or "").split(","):
            url = item.strip().split(" ")[0] if item.strip() else ""
            if url:
                out.append(url)
    return out


def scan(dist: Path, base: str, ignore: list[re.Pattern[str]]) -> dict:
    idx = DistIndex(dist)
    files = sorted(p for p in dist.rglob("*") if p.is_file() and p.suffix.lower() in HTML_SUFFIXES)

    stats = {
        "files_scanned": len(files),
        "links_total": 0,
        "links_checked": 0,
        "skipped": {"external": 0, "scheme": 0, "fragment": 0, "empty": 0, "ignored": 0},
    }
    errors: list[dict] = []
    warnings: list[dict] = []

    for f in files:
        rel_file = f.relative_to(dist).as_posix()
        src_dir = posixpath.dirname(rel_file)
        try:
            html = f.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:  # pragma: no cover
            print(f"[warn] 读不了 {rel_file}: {exc}", file=sys.stderr)
            continue

        for raw in extract_links(html):
            stats["links_total"] += 1
            kind, target, detail = resolve(raw, src_dir, idx, base)
            if kind.startswith("skip-"):
                key = kind.split("-", 1)[1]
                if key == "external":
                    stats["skipped"]["external"] += 1
                elif key == "scheme":
                    stats["skipped"]["scheme"] += 1
                elif key == "fragment":
                    stats["skipped"]["fragment"] += 1
                else:
                    stats["skipped"]["empty"] += 1
                continue
            if any(rx.search(target) for rx in ignore):
                stats["skipped"]["ignored"] += 1
                continue
            stats["links_checked"] += 1
            rec = {"source": rel_file, "raw": raw, "target": target, "type": detail}
            if kind == "error":
                errors.append(rec)
            elif kind == "warn":
                warnings.append(rec)

    return {"stats": stats, "errors": errors, "warnings": warnings}


# ---------------------------------------------------------------- 汇总

def bucket_by(errors: list[dict]) -> tuple[list[dict], list[dict]]:
    """按错误类型、来源页面分桶（同时给出现次数与唯一目标数）。"""
    type_rows: list[dict] = []
    by_type: dict[str, dict] = {}
    for e in errors:
        key = e["type"]
        if key == TYPE_DEAD and "cbdb:" in e["target"]:
            key = "死链：cbdb: 前缀外部人物（CBDB 编号作链接）"
        row = by_type.setdefault(key, {"type": key, "count": 0, "targets": set(), "sources": set()})
        row["count"] += 1
        row["targets"].add(e["target"])
        row["sources"].add(e["source"])
    for row in by_type.values():
        type_rows.append({
            "type": row["type"],
            "count": row["count"],
            "unique_targets": len(row["targets"]),
            "unique_sources": len(row["sources"]),
        })
    type_rows.sort(key=lambda r: -r["count"])

    by_src: dict[str, dict] = {}
    for e in errors:
        parts = e["source"].split("/")
        key = parts[0] if len(parts) > 1 else "(dist 根)"
        row = by_src.setdefault(key, {"bucket": key, "count": 0, "sources": set()})
        row["count"] += 1
        row["sources"].add(e["source"])
    src_rows = sorted(
        ({"bucket": r["bucket"], "count": r["count"], "unique_sources": len(r["sources"])}
         for r in by_src.values()),
        key=lambda r: -r["count"],
    )
    return type_rows, src_rows


def unique_targets(errors: list[dict]) -> list[dict]:
    agg: dict[str, int] = {}
    for e in errors:
        agg[e["target"]] = agg.get(e["target"], 0) + 1
    return [{"target": t, "count": c} for t, c in sorted(agg.items(), key=lambda kv: (-kv[1], kv[0]))]


# ---------------------------------------------------------------- 渲染

def render_text(result: dict, dist: Path, base: str, top: int, list_all: bool) -> str:
    s = result["stats"]
    errs, warns = result["errors"], result["warnings"]
    uniq = unique_targets(errs)
    type_rows, src_rows = bucket_by(errs)

    L: list[str] = []
    L.append("=" * 72)
    L.append("站内链接检查报告")
    L.append("=" * 72)
    L.append(f"dist        : {dist}")
    L.append(f"base        : {base}")
    L.append(f"扫描 HTML   : {s['files_scanned']} 个")
    L.append(f"提取链接    : {s['links_total']} 条"
             f"（站内待检 {s['links_checked']} / 外链跳过 {s['skipped']['external']}"
             f" / 协议跳过 {s['skipped']['scheme']}"
             f" / 锚点 {s['skipped']['fragment']}"
             f" / 空值 {s['skipped']['empty']}"
             f" / 规则忽略 {s['skipped']['ignored']}）")
    L.append(f"错误        : {len(errs)} 条（唯一目标 {len(uniq)} 个）")
    L.append(f"警告        : {len(warns)} 条")
    L.append("")

    if errs:
        L.append("-- 按错误类型 ----------------------------------------------------")
        L.append(f"{'次数':>7}  {'唯一目标':>8}  {'来源页':>6}  类型")
        for r in type_rows:
            L.append(f"{r['count']:>7}  {r['unique_targets']:>8}  {r['unique_sources']:>6}  {r['type']}")
        L.append("")
        L.append("-- 按来源目录 ----------------------------------------------------")
        L.append(f"{'次数':>7}  {'来源页':>6}  目录")
        for r in src_rows:
            L.append(f"{r['count']:>7}  {r['unique_sources']:>6}  {r['bucket']}")
        L.append("")
        L.append(f"-- 唯一死链目标 Top {min(top, len(uniq))} -------------------------------------")
        L.append(f"{'次数':>7}  目标")
        for r in uniq[:top]:
            L.append(f"{r['count']:>7}  {r['target']}")
        if len(uniq) > top:
            L.append(f"（其余 {len(uniq) - top} 个唯一目标省略；完整清单见 --json 产物）")
        L.append("")
        if list_all:
            L.append("-- 全量清单（来源 → 目标）-----------------------------------------")
            for e in errs:
                L.append(f"[{e['type']}] {e['source']}  ->  {e['target']}")
            L.append("")
    if warns:
        L.append("-- 警告明细（前 20 条）-------------------------------------------")
        for w in warns[:20]:
            L.append(f"[{w['type']}] {w['source']}  ->  {w['target']}")
        L.append("")
    if not errs:
        L.append("OK：未发现死链。")
    return "\n".join(L)


def render_md(result: dict, dist: Path, base: str, top: int) -> str:
    s = result["stats"]
    errs, warns = result["errors"], result["warnings"]
    uniq = unique_targets(errs)
    type_rows, src_rows = bucket_by(errs)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    L: list[str] = []
    L.append(f"# 站内链接检查基线报告")
    L.append("")
    L.append(f"> 生成时间：{now}　|　生成脚本：`scripts/check_links.py`（只读、标准库）")
    L.append(f"> 目标：`{dist}`　|　base：`{base}`")
    L.append("")
    L.append("## 1. 总览")
    L.append("")
    L.append("| 指标 | 数值 |")
    L.append("|---|---:|")
    L.append(f"| 扫描 HTML 文件 | {s['files_scanned']} |")
    L.append(f"| 提取 href/src 链接 | {s['links_total']} |")
    L.append(f"| 其中站内待检 | {s['links_checked']} |")
    L.append(f"| 外链跳过 | {s['skipped']['external']} |")
    L.append(f"| 锚点/协议/空值跳过 | "
             f"{s['skipped']['fragment'] + s['skipped']['scheme'] + s['skipped']['empty']} |")
    L.append(f"| 规则忽略 | {s['skipped']['ignored']} |")
    L.append(f"| **错误** | **{len(errs)} 条（唯一目标 {len(uniq)} 个）** |")
    L.append(f"| 警告 | {len(warns)} 条 |")
    L.append("")
    if errs:
        L.append("## 2. 按错误类型")
        L.append("")
        L.append("| 出现次数 | 唯一目标 | 涉及来源页 | 类型 |")
        L.append("|---:|---:|---:|---|")
        for r in type_rows:
            L.append(f"| {r['count']} | {r['unique_targets']} | {r['unique_sources']} | {r['type']} |")
        L.append("")
        L.append("## 3. 按来源目录")
        L.append("")
        L.append("| 出现次数 | 来源页数 | 目录 |")
        L.append("|---:|---:|---|")
        for r in src_rows:
            L.append(f"| {r['count']} | {r['unique_sources']} | `{r['bucket']}` |")
        L.append("")
        L.append(f"## 4. 唯一死链目标 Top {min(top, len(uniq))}")
        L.append("")
        L.append("| 出现次数 | 目标 |")
        L.append("|---:|---|")
        for r in uniq[:top]:
            L.append(f"| {r['count']} | `{r['target']}` |")
        if len(uniq) > top:
            L.append("")
            L.append(f"（其余 {len(uniq) - top} 个唯一目标略；完整清单见 `--json` 产物）")
        L.append("")
    if warns:
        L.append("## 5. 警告明细（前 20 条）")
        L.append("")
        for w in warns[:20]:
            L.append(f"- `{w['type']}`　{w['source']} → `{w['target']}`")
        L.append("")
    return "\n".join(L)


# ---------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="check_links.py",
        description="站点内部 href/src 死链检查器（读 site/dist，只读不改文件）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("用法\n----")[-1].strip(),
    )
    ap.add_argument("--dist", default=str(DEFAULT_DIST), help="构建产物目录（默认 site/dist）")
    ap.add_argument("--base", default=DEFAULT_BASE, help=f"站点 base 前缀（默认 {DEFAULT_BASE}）")
    ap.add_argument("--max-errors", type=int, default=0, metavar="N",
                    help="允许的最大错误数；超出则以 1 退出（默认 0，供构建接入）")
    ap.add_argument("--report-only", action="store_true",
                    help="只报告不失败：无论多少错误都以 0 退出")
    ap.add_argument("--allow-missing-dist", action="store_true",
                    help="dist 不存在时视为跳过（退出 0），便于构建期早于产物阶段调用")
    ap.add_argument("--ignore", action="append", default=[], metavar="REGEX",
                    help="忽略 target 命中该正则的链接，可重复；用于排除已知存量")
    ap.add_argument("--top", type=int, default=20, help="文本报告中唯一目标清单条数（默认 20）")
    ap.add_argument("--list-all", action="store_true", help="文本报告输出全量错误清单")
    ap.add_argument("--json", metavar="PATH", help="把完整结果写成 JSON")
    ap.add_argument("--md", metavar="PATH", help="把报告写成 Markdown")
    ap.add_argument("--quiet", action="store_true", help="不打印文本报告")
    args = ap.parse_args(argv)

    dist = Path(args.dist).resolve()
    if not dist.is_dir():
        msg = f"[error] dist 目录不存在：{dist}"
        if args.allow_missing_dist:
            print(f"{msg}（--allow-missing-dist：跳过）", file=sys.stderr)
            return 0
        print(msg, file=sys.stderr)
        print("        构建产物尚未生成，或 --dist 指错了。", file=sys.stderr)
        return 2

    try:
        ignore = [re.compile(p) for p in args.ignore]
    except re.error as exc:
        print(f"[error] --ignore 正则非法：{exc}", file=sys.stderr)
        return 2

    result = scan(dist, args.base, ignore)
    result["dist"] = str(dist)
    result["base"] = args.base
    result["generated_at"] = datetime.now().isoformat(timespec="seconds")

    if not args.quiet:
        print(render_text(result, dist, args.base, args.top, args.list_all))

    if args.json:
        payload = dict(result)
        payload["unique_error_targets"] = unique_targets(result["errors"])[:500]
        payload["unique_error_target_count"] = len(unique_targets(result["errors"]))
        payload["error_count"] = len(result["errors"])
        payload["warning_count"] = len(result["warnings"])
        payload["bucket_by_type"], payload["bucket_by_source"] = bucket_by(result["errors"])
        Path(args.json).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"[info] JSON 报告已写入 {args.json}")

    if args.md:
        Path(args.md).write_text(render_md(result, dist, args.base, args.top), encoding="utf-8")
        print(f"[info] Markdown 报告已写入 {args.md}")

    n_err = len(result["errors"])
    if args.report_only:
        return 0
    if n_err > args.max_errors:
        print(f"\n[FAIL] 站内死链 {n_err} 条 > 允许上限 {args.max_errors}。", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
