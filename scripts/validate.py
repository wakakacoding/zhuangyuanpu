#!/usr/bin/env python3
"""数据底座校验器（构建期强制执行三条铁律）

用法: python3 scripts/validate.py [--data DIR]
退出码: 0 = 通过（允许警告）; 1 = 存在错误
检查项:
  - 必填字段 / id 与文件名一致 / id 命名规范
  - 枚举合法性（event.type / year_precision / source.tier / relation.type）
  - 引用完整性（event.source_ids、relation.to_id 等必须存在）
  - 干支-公元互验（person.exam_year vs ganzhi）
  - 身份分层（R1.1-5）: identity_status 取值合法；科年 > 卒年 -> 错误；suspect 却带生卒 -> 警告
  - 名录身份与档案状态（R1.4）: role 取值合法（缺省=状元）；verified_absent 须为布尔且与 bio_short 互斥；
    标签「史料阙如」已废弃（属历史结论，只能由 verified_absent 驱动页面渲染）
  - 关系方向一致性（R2-1）: CBDB 机器边须带 direction 且恰有 kin_code/assoc_code 之一；
    reverse 须有 note_code 且码已翻转（forward 不得留痕）；note 须以「（CBDB…）」结尾；
    to_id 为 cbdb: 的外部人物须内联姓名并标「外部人物」，站内人物反之；不得残留 Y 占位符；
    抽查：A↔B 双向机器边共用亲属称谓 -> 警告（方向疑未翻转）
  - 铁律 1: 事件无出处（source_ids 为空）-> 错误；史实仅有 C 级出处 -> 警告
  - 铁律 2: 轶事只存在于 anecdotes 表（event.type 枚举中无「轶事」，天然隔离）
  - 覆盖率看板: 坐标 / 生卒覆盖（Phase 3 数据阈值闸门）

`--data DIR` 覆盖数据根目录（等价环境变量 ZYP_DATA_DIR）：供
scripts/test_validate_rules.py 把规则跑在**副本**上，真实 data/ 只读不污染。
"""
import os
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def _data_root() -> Path:
    """解析数据根目录：--data DIR > 环境变量 ZYP_DATA_DIR > 仓库 data/。"""
    argv = sys.argv[1:]
    for i, a in enumerate(argv):
        if a == "--data" and i + 1 < len(argv):
            return Path(argv[i + 1]).resolve()
        if a.startswith("--data="):
            return Path(a.split("=", 1)[1]).resolve()
    env = os.environ.get("ZYP_DATA_DIR")
    return Path(env).resolve() if env else ROOT / "data"


DATA = _data_root()
sys.path.insert(0, str(ROOT / "scripts"))
from era import ganzhi_of, year_in_reign  # noqa: E402

EVENT_TYPES = {"出生", "应试", "中举", "夺魁", "授官", "留学", "升迁",
               "贬谪", "罢官", "被俘", "实业", "致仕", "隐居", "守节", "著作", "卒"}
PRECISIONS = {"exact", "about", "range"}
TIERS = {"A", "B", "C"}
REL_TYPES = {"同年", "师生", "父子", "母子", "父女", "祖孙", "兄弟", "旁系",
             "翁婿", "夫妻", "姻亲", "政敌", "友人", "同僚", "其他"}
# ⚠ 枚举值一律用简体：「祖孙」而非「祖孫」（2026-10-16 全站繁简一致性修复，
#   与 build_network.py:TYPES / harvest_cbdb_relations.py 的 KIN_MAP 三处同步）。
# 名录身份（R1.4-1）：缺省 = zhuangyuan；特例仅 tanhua / de_facto 两种
ROLES = {"zhuangyuan", "tanhua", "de_facto"}
EXT_TO_ID_RE = re.compile(r"^cbdb:\d+$")  # CBDB 外部人物标记
ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")

# ---- R2-1：CBDB 机器（史料派生）边口径与方向一致性常量 ----
# 机器边识别与 harvest_cbdb_relations.py --purge-machine 保持同一口径：
# 显式 src 优先（src 非 cbdb 即人工边，不再按 note 猜测）；无 src 时回退到
# 「note 含 CBDB」或「to_id 带 cbdb: 前缀」。
MACHINE_DIRECTIONS = {"forward", "reverse"}
# 机器边 note 定式：`{标签}[：{姓名}]（CBDB[ 外部人物…]）[，始年 N]`
CBDB_TAIL_RE = re.compile(r"（(?P<mark>CBDB[^）]*)）(?:，始年 (?P<year>\d+))?$")
# Y 占位符（收割期由「對方」替换；夹在拉丁字母中的 Y 不算）
Y_PLACEHOLDER_RE = re.compile(r"(?:^|[^A-Za-z])Y(?:[^A-Za-z]|$)")
# 方向抽查白名单：只认**天生不对称**的亲属称谓（父≠子），
# 避免误伤「同年友」「同僚」这类本就对称的标签。
KIN_TERMS = {
    "父", "母", "子", "女", "兄", "弟", "姊", "妹", "姐", "夫", "妻",
    "嫡母", "生母", "繼母", "養父", "養母", "岳父", "岳母", "女婿", "媳婦",
    "祖父", "祖母", "孫", "孫女", "曾祖", "曾祖母", "曾孫", "曾孫女",
    "伯", "伯父", "叔", "叔父", "姪", "姪女", "甥", "舅", "姑", "姨", "嫂",
}

errors: list[str] = []
warnings: list[str] = []
err = errors.append
warn = warnings.append


def is_machine_edge(r: dict) -> bool:
    """该关系边是否 CBDB 机器边（史料派生），口径同 harvest --purge-machine。"""
    src = r.get("src")
    if src is not None:
        return src == "cbdb"
    to_id = str(r.get("to_id") or "")
    return "CBDB" in str(r.get("note") or "") or to_id.startswith("cbdb:")


def note_label(note: str) -> str:
    """取机器边 note 的称谓/描述标签：尾标「（CBDB…）」之前、首个冒号之前的部分。"""
    m = CBDB_TAIL_RE.search(note)
    body = note[: m.start()] if m else note
    return body.split("：")[0].split(":")[0].strip()


def load_dir(name: str) -> dict:
    d = DATA / name
    out = {}
    if not d.exists():
        return out
    for f in sorted(d.glob("*.yaml")):
        if f.name.startswith("_"):  # 模板跳过
            continue
        try:
            out[f.stem] = yaml.safe_load(f.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            err(f"{name}/{f.name}: YAML 解析失败 {e}")
    return out


persons = load_dir("persons")
events_by = load_dir("events")
sources = load_dir("sources")
rels_by = load_dir("relations")
works_by = load_dir("works")
anec_by = load_dir("anecdotes")
geo_file = DATA / "geo_map.yaml"
geo = yaml.safe_load(geo_file.read_text(encoding="utf-8")) if geo_file.exists() else []
geo_hists = {g.get("hist") for g in (geo or []) if isinstance(g, dict)}

# ---------- person ----------
for stem, p in persons.items():
    if not isinstance(p, dict):
        err(f"persons/{stem}.yaml: 顶层必须是对象")
        continue
    pid = p.get("id")
    if not pid:
        err(f"persons/{stem}.yaml: 缺 id")
        continue
    if pid != stem:
        err(f"persons/{stem}.yaml: id({pid}) 与文件名不一致")
    if not ID_RE.match(pid):
        err(f"person {pid}: id 非法（须小写拼音 slug）")
    for req in ("name", "dynasty", "status"):
        if not p.get(req):
            err(f"person {pid}: 缺必填字段 {req}")
    if p.get("status") not in ("draft", "published"):
        err(f"person {pid}: status 非法（draft/published）")
    # 身份匹配状态：confirmed / suspect；缺省 = 未标注（索引 status 为 confirmed/missing 者不写）
    if p.get("identity_status") not in (None, "confirmed", "suspect"):
        err(f"person {pid}: identity_status 非法（confirmed/suspect，或省略）")
    # 名录身份（R1.4-1）：缺省 = zhuangyuan；特例须显式标注，否则统计口径会被特例污染
    if p.get("role") not in (None, *ROLES):
        err(f"person {pid}: role 非法（zhuangyuan/tanhua/de_facto，或省略=状元）")
    if p.get("role") == "zhuangyuan":
        warn(f"person {pid}: role 显式写 zhuangyuan 属冗余（缺省即状元），建议整行删除")
    # 「史料阙如」人工认定（R1.4-5）：只接受布尔；与 bio_short 互斥
    va = p.get("verified_absent")
    if va is not None and not isinstance(va, bool):
        err(f"person {pid}: verified_absent 须为布尔 true（或省略）；当前 {va!r}")
    if va is True and p.get("bio_short"):
        err(f"person {pid}: verified_absent=true 却已有 bio_short——两者互斥（有传则非阙如）")
    if va is False:
        warn(f"person {pid}: verified_absent 显式写 false 属冗余（省略即未认定），建议整行删除")
    # 两字段语义互斥：identity_status 是「名录身份匹配」结论，verified_absent 是「查无传世记载」结论。
    # 既已确认身份匹配（confirmed）又宣称史料阙如，必有一方是错的 —— 真阙如者根本无从确认匹配。
    if va is True and p.get("identity_status"):
        err(f"person {pid}: verified_absent=true 与 identity_status={p['identity_status']!r} 互斥"
            f"——身份匹配结论与「查无记载」不能同时成立，须二者择一")
    # 「史料阙如」是历史结论，只能经 verified_absent 认定后由页面渲染，**不得作为标签**：
    # 标签会被检索与统计页当成人物分类展示，等于把整理进度冒充史料结论（R1.4-5 定规）
    if "史料阙如" in (p.get("tags") or []):
        err(f"person {pid}: 标签「史料阙如」已废弃——未整理者标「待整理」，"
            f"确无传世记载者置 verified_absent: true（由页面渲染成「史料阙如」）")
    # R1.1-5 时间序：夺魁年不得晚于卒年（两值皆有时）——晚于者几乎必是身份误配（如薛迈 卒645/科861）
    dy = p.get("death_year")
    if dy and p.get("exam_year") and int(p["exam_year"]) > int(dy):
        err(f"person {pid}: 科年({p['exam_year']}) 晚于卒年({dy})——身份或生卒疑为误配")
    # R1.1-5 身份未核者不应带生卒：suspect 卡的生卒系 CBDB 候选人数据（见 schema/SCHEMA.md）
    if p.get("identity_status") == "suspect" and (p.get("birth_year") or p.get("death_year")):
        warn(f"person {pid}: 身份匹配存疑（suspect）却带生卒——须人工核验后补，或回退为 null 并写 identity_note")
    # 生卒不可考必须写 null（渲染为「待考」）；0 会穿透 ?? 兜底渲染成「生年–0」（2026-10-25 清洗定规）
    for fld in ("birth_year", "death_year"):
        if p.get(fld) == 0:
            err(f"person {pid}: {fld} 为 0——不可考请写 null（CBDB 的 0 = 阙如），0 会渲染成「生年–0」")
    for opt in ("exam_year", "native_hist", "rank_detail"):
        if p.get(opt) is None:
            warn(f"person {pid}: 建议字段 {opt} 缺失（未考出可忽略——缺载是合法状态）")
    ey, gz = p.get("exam_year"), p.get("ganzhi")
    if ey is not None and gz:
        if ganzhi_of(int(ey)) != gz:
            err(f"person {pid}: 干支互验失败——{ey} 年应为 {ganzhi_of(int(ey))}，录为 {gz}")
    reign = p.get("reign")
    if ey is not None and reign:
        in_reign = year_in_reign(int(ey), reign)
        if in_reign is False:
            err(f"person {pid}: 年号互验失败——{ey} 不在 {reign} 年间")
        elif in_reign is None:
            warn(f"person {pid}: 年号「{reign}」未收录进 era.py，跳过互验")
    bounds = {"lat": 90, "lng": 180}
    for c in ("lat", "lng"):
        v = p.get(c)
        if v is not None and not (-bounds[c] <= float(v) <= bounds[c]):
            err(f"person {pid}: {c} 越界")
    nh = p.get("native_hist")
    if nh and geo_hists and nh not in geo_hists:
        warn(f"person {pid}: 籍贯「{nh}」未收录进 geo_map.yaml")
    if nh and p.get("lat") is None:
        warn(f"person {pid}: 缺坐标（可视化前置字段）")

# ---------- source ----------
for stem, s in sources.items():
    if not isinstance(s, dict):
        err(f"sources/{stem}.yaml: 顶层必须是对象")
        continue
    sid = s.get("id")
    if not sid or sid != stem:
        err(f"sources/{stem}.yaml: id 缺失或与文件名不一致")
        continue
    if not sid.startswith("src_"):
        err(f"source {sid}: id 须以 src_ 开头")
    if not s.get("title"):
        err(f"source {sid}: 缺 title")
    if s.get("tier") not in TIERS:
        err(f"source {sid}: tier 非法（A/B/C）")
    if s.get("tier") == "A" and not s.get("quote"):
        warn(f"source {sid}: A 级出处建议附原文 quote")

# ---------- event ----------
for stem, doc in events_by.items():
    if not isinstance(doc, dict):
        err(f"events/{stem}.yaml: 顶层必须是对象")
        continue
    pid = doc.get("person_id")
    if pid != stem:
        err(f"events/{stem}.yaml: person_id({pid}) 与文件名不一致")
    if pid not in persons:
        err(f"events/{stem}.yaml: person_id {pid} 不存在")
        continue
    for i, e in enumerate(doc.get("events") or []):
        tag = f"events/{stem}[{i}]"
        if e.get("year") is None:
            err(f"{tag}: 缺 year")
        if e.get("type") not in EVENT_TYPES:
            err(f"{tag}: type 非法 {e.get('type')}")
        if e.get("year_precision") not in PRECISIONS:
            err(f"{tag}: year_precision 非法（exact/about/range）")
        if e.get("year_precision") == "range" and e.get("year_end") is None:
            err(f"{tag}: range 精度缺 year_end")
        if not e.get("title"):
            err(f"{tag}: 缺 title")
        sids = e.get("source_ids") or []
        if not sids:
            err(f"{tag}: 铁律违反——事件无出处（source_ids 为空）")
        for sid in sids:
            if sid not in sources:
                err(f"{tag}: 引用不存在的 source {sid}")
        tiers = {sources[sid].get("tier") for sid in sids if sid in sources}
        if tiers and tiers == {"C"}:
            warn(f"{tag}: 史实事件仅有 C 级出处，建议补 A/B 级或移入 anecdotes")

# ---------- relation ----------
for stem, doc in rels_by.items():
    if not isinstance(doc, dict):
        err(f"relations/{stem}.yaml: 顶层必须是对象")
        continue
    fid = doc.get("from_id")
    if fid != stem:
        err(f"relations/{stem}.yaml: from_id({fid}) 与文件名不一致")
    if fid not in persons:
        err(f"relations/{stem}.yaml: from_id {fid} 不存在")
    for i, r in enumerate(doc.get("relations") or []):
        tag = f"relations/{stem}[{i}]"
        to_id = r.get("to_id")
        if to_id not in persons and not (isinstance(to_id, str) and EXT_TO_ID_RE.match(to_id)):
            err(f"{tag}: to_id {r.get('to_id')} 不存在")
        if r.get("type") not in REL_TYPES:
            err(f"{tag}: type 非法 {r.get('type')}")
        for sid in r.get("source_ids") or []:
            if sid not in sources:
                err(f"{tag}: 引用不存在的 source {sid}")

        # ---- R2-1 关系方向一致性（仅 CBDB 机器边；人工边 note 是自由文本，不套定式）----
        note = str(r.get("note") or "")
        if not is_machine_edge(r):
            continue
        direction = r.get("direction")
        codes = [k for k in ("kin_code", "assoc_code") if k in r]
        if direction not in MACHINE_DIRECTIONS:
            err(f"{tag}: CBDB 机器边缺/非法 direction（须 forward/reverse，当前 {direction!r}）"
                f"——direction 是「note 是否已翻成锚点视角」的唯一凭据")
        if len(codes) != 1:
            err(f"{tag}: CBDB 机器边须恰带 kin_code/assoc_code 之一，当前 {codes or '两者皆缺'}")
        if direction == "reverse":
            # 方向修复的核心证据：反向边的称谓码必须与原始码不同，且必须留痕
            if "note_code" not in r:
                err(f"{tag}: direction=reverse 却无 note_code——反向边必须留痕"
                    f"（记录生成 note 所用码），否则无法复算 note 视角")
            elif codes and r["note_code"] == r[codes[0]]:
                err(f"{tag}: direction=reverse 但 note_code({r['note_code']}) == 原始码"
                    f"({r[codes[0]]})——码未翻转，note 仍是原行视角")
        elif direction == "forward" and "note_code" in r:
            err(f"{tag}: direction=forward 不应带 note_code（{r['note_code']}）"
                f"——正向视角即原码，留痕会让人误判该边已翻转")
        m_tail = CBDB_TAIL_RE.search(note)
        if not m_tail:
            err(f"{tag}: CBDB 机器边 note 须以「（CBDB…）」结尾（可带「，始年 NNNN」），当前 {note!r}")
        else:
            body, mark = note[: m_tail.start()], m_tail.group("mark")
            external = str(to_id or "").startswith("cbdb:")
            inlined_name = "：" in body or ":" in body
            if not note_label(note):
                err(f"{tag}: CBDB 机器边 note 缺称谓/描述标签（尾标前为空）：{note!r}")
            if external and "外部人物" not in mark:
                err(f"{tag}: to_id={to_id} 无站内档案，note 须标「CBDB 外部人物」以区别于站内人物")
            if external and not inlined_name:
                err(f"{tag}: to_id={to_id} 为外部人物，note 须内联姓名（{note!r}）"
                    f"——页面只显示 note，不内联即无法辨识对方是谁")
            if not external and "外部人物" in mark:
                err(f"{tag}: to_id={to_id} 已有站内档案，note 不得标「CBDB 外部人物」（{note!r}）")
            if not external and inlined_name:
                err(f"{tag}: to_id={to_id} 已有站内档案，note 不得内联姓名（{note!r}）"
                    f"——站内人物由页面渲染姓名，内联会造成「标签=冒号后姓名」重复")
        if Y_PLACEHOLDER_RE.search(note):
            err(f"{tag}: note 残留 Y 占位符（{note!r}）——收割期应替换为「對方」，须回头重跑收割")

# ---- R2-1 方向抽查：A↔B 双向机器边共用亲属称谓 = 方向疑未翻转 ----
# 「父」「子」这类称谓天生不对称，A→B 与 B→A 同时标同一个词，说明有一侧没翻视角。
# 只查亲属称谓（KIN_TERMS），「同年友/同僚」等对称标签天然会同词，不入此规则。
machine_labels: dict[tuple[str, str], set[str]] = {}
for stem, doc in rels_by.items():
    if not isinstance(doc, dict):
        continue
    for r in doc.get("relations") or []:
        if not is_machine_edge(r):
            continue
        lab = note_label(str(r.get("note") or ""))
        if lab:
            machine_labels.setdefault((stem, str(r.get("to_id"))), set()).add(lab)
seen_pairs: set[tuple[str, str]] = set()
for (a, b) in sorted(machine_labels):
    if a == b:  # 自环（to_id == from_id）无方向可言，不参与互指抽查
        continue
    pair = (a, b) if a <= b else (b, a)
    if pair in seen_pairs or (b, a) not in machine_labels:
        continue
    seen_pairs.add(pair)
    shared = sorted((machine_labels[(a, b)] & machine_labels[(b, a)]) & KIN_TERMS)
    if shared:
        warn(f"relations: {a} ↔ {b} 双向机器边共用亲属称谓 {shared}——"
             f"称谓天生不对称，方向疑未翻转，须人工核验")

# ---------- works / anecdotes ----------
for stem, doc in works_by.items():
    if not isinstance(doc, dict) or doc.get("person_id") != stem:
        err(f"works/{stem}.yaml: person_id 缺失或与文件名不一致")
    if stem not in persons:
        err(f"works/{stem}.yaml: person {stem} 不存在")
    for i, w in enumerate((doc or {}).get("works") or []):
        if not w.get("title"):
            err(f"works/{stem}[{i}]: 缺 title")

for stem, doc in anec_by.items():
    if not isinstance(doc, dict) or doc.get("person_id") != stem:
        err(f"anecdotes/{stem}.yaml: person_id 缺失或与文件名不一致")
    if stem not in persons:
        err(f"anecdotes/{stem}.yaml: person {stem} 不存在")
    for i, a in enumerate((doc or {}).get("anecdotes") or []):
        tag = f"anecdotes/{stem}[{i}]"
        if a.get("tier") not in TIERS:
            err(f"{tag}: tier 非法（默认应为 C）")
        if not a.get("title") or not a.get("content"):
            err(f"{tag}: 缺 title/content")
        for sid in a.get("source_ids") or []:
            if sid not in sources:
                err(f"{tag}: 引用不存在的 source {sid}")

# ---------- geo_map ----------
for i, g in enumerate(geo or []):
    if isinstance(g, dict) and (not g.get("hist") or not g.get("modern")):
        err(f"geo_map[{i}]: 缺 hist/modern")

# ---------- corrections（勘误记录） ----------
CORR_STATUS = {"pending", "accepted", "rejected", "noted"}
corrs = load_dir("corrections")
for stem, c in corrs.items():
    if not isinstance(c, dict):
        err(f"corrections/{stem}: 结构非法")
        continue
    tag = f"corrections/{stem}"
    if c.get("id") != stem and not stem.startswith(str(c.get("id", "\0")) + "_"):
        err(f"{tag}: id {c.get('id')} 与文件名不一致")
    for req in ("target", "field", "current", "proposed", "evidence", "status", "reporter", "created"):
        if not c.get(req):
            err(f"{tag}: 缺必填字段 {req}")
    if c.get("status") not in CORR_STATUS:
        err(f"{tag}: status 非法（须为 {CORR_STATUS}）")
    tgt = str(c.get("target", ""))
    if tgt.startswith("person:") and tgt.split(":", 1)[1] not in persons:
        err(f"{tag}: target 引用不存在的人物 {tgt}")


# ---------- 覆盖率看板（Phase 3 阈值闸门） ----------
n = len(persons)


def cov(pred):
    m = sum(1 for p in persons.values() if isinstance(p, dict) and pred(p))
    return m, (m / n * 100 if n else 0)


c_geo = cov(lambda p: p.get("lat") is not None)
c_bd = cov(lambda p: bool(p.get("birth_year")) and bool(p.get("death_year")))
c_star = cov(lambda p: bool(p.get("birth_year")) or bool(p.get("fl_year")))
c_ev = sum(1 for stem in persons if stem in events_by)
rel_edges = sum(len((d or {}).get("relations") or []) for d in rels_by.values())
# 机器边（CBDB 派生）与人工边拆分：方向一致性规则只作用于机器边，报数便于核对口径
rel_machine = sum(1 for d in rels_by.values() for r in ((d or {}).get("relations") or [])
                  if isinstance(r, dict) and is_machine_edge(r))
rel_forward = sum(1 for d in rels_by.values() for r in ((d or {}).get("relations") or [])
                  if isinstance(r, dict) and is_machine_edge(r) and r.get("direction") == "forward")
rel_reverse = sum(1 for d in rels_by.values() for r in ((d or {}).get("relations") or [])
                  if isinstance(r, dict) and is_machine_edge(r) and r.get("direction") == "reverse")
# 状元口径（统计以状元为准，特例单列）：覆盖率闸门同样只看状元
g_geo = sum(1 for p in persons.values() if isinstance(p, dict)
            and (p.get("role") or "zhuangyuan") == "zhuangyuan" and p.get("lat") is not None)

print("=" * 56)
print("数据底座校验报告")
print("=" * 56)
print(f"persons: {n} | sources: {len(sources)} | relation 边: {rel_edges}")
print(f"  其中 CBDB 机器边: {rel_machine}（forward {rel_forward} / reverse {rel_reverse}）"
      f" | 人工边: {rel_edges - rel_machine}")
# 名录身份拆分（R1.4）：统计口径 = 状元；特例单列不并入
n_zy = sum(1 for p in persons.values() if isinstance(p, dict) and (p.get("role") or "zhuangyuan") == "zhuangyuan")
n_th = sum(1 for p in persons.values() if isinstance(p, dict) and p.get("role") == "tanhua")
n_df = sum(1 for p in persons.values() if isinstance(p, dict) and p.get("role") == "de_facto")
n_va = sum(1 for p in persons.values() if isinstance(p, dict) and p.get("verified_absent") is True)
print(f"名录身份: 状元 {n_zy} + 特例 {n_th + n_df}（探花 {n_th} · 事实状元 {n_df}）"
      f"   [统计口径以状元为准]")
print(f"史料阙如人工认定（verified_absent）: {n_va} / {n_zy + n_th + n_df}")
print(f"坐标覆盖: {c_geo[0]}/{n} ({c_geo[1]:.0f}%)   [地图闸门 >= 60%]"
      f"  状元口径 {g_geo}/{n_zy}")
print(f"生卒双全: {c_bd[0]}/{n} ({c_bd[1]:.0f}%)   [精确口径]")
print(f"星图可用年: {c_star[0]}/{n} ({c_star[1]:.0f}%)   [星图闸门 >= 50%：生年或 fl_year(CBDB 估算活动年)]")
print(f"有事件档案: {c_ev}/{n}")
print("-" * 56)
for w in warnings:
    print(f"  [警告] {w}")
for e in errors:
    print(f"  [错误] {e}")
print("-" * 56)
print(f"结论: {len(errors)} 错误 / {len(warnings)} 警告")
sys.exit(1 if errors else 0)
