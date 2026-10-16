#!/usr/bin/env python3
"""从 CBDB 批量收割状元间及状元与名人的社会关系（R1.2-1 改造版）。

数据源: vendor/cbdb/cbdb_20261010.sqlite3（**只读**，不给库加锁、不写库）
锚点:   data/index/zhuangyuan_index.yaml 中 status=confirmed 且有 cbdb_id 的状元
输出:   data/relations/{slug}.yaml（**仅 --apply 时写入；默认 dry-run 不碰任何 data/ 文件**）
报告:   outputs/cbdb_relations_review/（非 data 目录，可随时删）

════════════════════════ R1.2-1 的三处修复 ════════════════════════════

1) 方向缺陷（本次核心）
   CBDB 关系行有「主体侧」：
     KIN_DATA(p, k, code)     —— k 是 p 的「code 称谓」（c_kin_id 是 c_personid 的亲属）
     ASSOC_DATA(p, a, code)   —— 中文描述以 p 为主体，描述中的 Y 指代 a
   旧脚本在「锚点落在 c_kin_id / c_assoc_id 侧」时只把起终点对调，却沿用原始描述，
   于是王维档案里崔氏同时出现「母」与「子」两条（「子」把「王維是崔氏的子」挂到了崔氏身上），
   且方向信息在旧数据里已不可追溯。本版把方向写进数据并统一到锚点视角：
     · 锚点在 p 侧 → direction=forward，note 直接用原始码的称谓/描述
     · 锚点在 k/a 侧 → direction=reverse，note 翻转为锚点视角（见下）
     · 无反向词且无镜像行 → 整条跳过并计数（宁缺毋滥，不塞「其他」凑数）
   反向称谓的求取两级（_label_for_reverse）：
     ① **镜像行优先**：CBDB 多双向成对存储。若反向行 (p=q₀, k=q₁, code=C) 存在镜像行
        (p=q₁, k=q₀, code=D)，则 D 就是 CBDB 自己认定的反向码，性别天然正确。
        实测镜像覆盖：KIN 2860/2875 = 99.5%、ASSOC 全成对。
     ② 无镜像行时查**反向称谓映射表**：
        · 人工校订层 REV_KIN_MANUAL / REV_ASSOC_MANUAL（显式、可审、最高优先级）
        · CBDB 配对列 KINSHIP_CODES.c_kin_pair1/pair2、ASSOC_CODES.c_assoc_pair
          （本版未启用人工层：实测配对列已自洽——父↔子/女兒、母↔子/女兒、子↔父/母、
           岳父↔女婿、43↔44 墓誌銘……；pair1/pair2 皆有效时按「**对方**性别」择一）
   覆盖率（按码值 / 按边数）见 coverage_report.md，硬闸门 ≥95%。

2) Y 占位符（R1.2-2）
   CBDB 描述里的 Y 指代关系另一端。旧数据原样上屏（**现存 2639 处 / 177 个文件**），
   页面与网络图各洗各的（build_network.clean_note 自行把 Y 换成「對方」）。
   本版在**落盘前**替换，页面与网络图从此共用同一份干净数据：
     · --y-fill name （默认）→「為韋斌作墓誌銘」：按工单字面把 Y 换成对方姓名
     · --y-fill other        →「為對方作墓誌銘」：与 build_network 现有显示逐字一致，零视觉回归
   两种写法都保留「冒号 + 姓名」——**不可省**：scripts/build_network.py 的 split_label()
   靠冒号后的姓名给名士层（cbdb:NNNNN）节点命名，去掉会直接坏掉网络图名士层。
   ⚠ 类型判定始终用**未填充的原始描述**（否则对方姓名里的「友/交/知/游」会污染 map_assoc）。

3) map_kin 修正（R1.2-3）
   旧表只有 父/子/祖/孫，故「母」「女」「曾祖」「妻子」等一律落「其他」（现存「母」类边 type=其他）。
   新表按亲属称谓映射到 15 类，新增 6 个枚举值：母子 / 父女 / 祖孫 / 旁系 / 夫妻 / 姻亲。
   实际命中的称谓 100% 有归属，**不再落「其他」**（见报告第 3 节）。
   ⚠ 落盘前必须同步下游枚举（属 R1.2-5 / R2-1 范围，本任务禁动）：
     · scripts/validate.py      REL_TYPES  += 母子/父女/祖孫/旁系/夫妻/姻亲
     · scripts/build_network.py TYPES      += 同上（并决定是否并入 GROUPS 的「亲缘」组）
   --legacy-types 把新增值折回既有 9 类（母子/父女/祖孫→父子、旁系→兄弟、夫妻→翁婿、
   姻亲→其他），用于对照「不动枚举」的代价。

════════════════════════ 越界清单（硬约束）════════════════════════
data/relations/_cbdb_out_of_scope.yaml 的 excluded[].cbdb_id 一律跳过。依《CBDB Data
Licensing Terms》R0-1 结论，这些 personid 建档于当前单机版发布日期之后，属范围外，
不得出现在公开面。**重收割必须消费本清单**，否则已剔除的 12 条边会复活。

════════════════════════ 用法 ════════════════════════
  PY=/Users/mba/.workbuddy/binaries/python/envs/default/bin/python
  $PY scripts/harvest_cbdb_relations.py                   # 全量 dry-run（默认）
  $PY scripts/harvest_cbdb_relations.py --sample-default  # 10 锚点小样本（R1.2-1d）
  $PY scripts/harvest_cbdb_relations.py --sample wang_wei,lv_nan
  $PY scripts/harvest_cbdb_relations.py --export-codes    # 码表全量导出（R1.2-1a）
  $PY scripts/harvest_cbdb_relations.py --legacy-types    # 折回既有 9 类对照
  $PY scripts/harvest_cbdb_relations.py --apply           # 真正落盘
  $PY scripts/harvest_cbdb_relations.py --purge-machine --dry-run   # 只出待删机器边清单（R1.2-4b）
  $PY scripts/harvest_cbdb_relations.py --purge-machine --apply --y-fill other   # 清洗后全量重跑（R1.2-4c）

未实现（属后续任务）：build_network 适配（R1.2-5）、档案页机器边标注（R1.2-6）。
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "vendor" / "cbdb" / "cbdb_20261010.sqlite3"
INDEX = ROOT / "data" / "index" / "zhuangyuan_index.yaml"
REL_DIR = ROOT / "data" / "relations"
PERSON_DIR = ROOT / "data" / "persons"
OUT_OF_SCOPE = REL_DIR / "_cbdb_out_of_scope.yaml"
REPORT_DIR = ROOT / "outputs" / "cbdb_relations_review"

SENTINEL_CODES = {-10000, -1, 0}
BAD_WORDS = {"", "未詳", "未详", "非可用", "[missing data]", "[Missing Data]",
             "[Undefined]", "[缺乏信息]", "[Missing Data]"}
MACHINE_NOTE_RE = re.compile(r"CBDB")          # 与 R1.2-4b 的机器边识别口径保持一致
MACHINE_TO_RE = re.compile(r"^cbdb:\d+$")

# ─────────────── 反向称谓映射表 · 人工校订层（R1.2-1b）───────────────
# 仅在「镜像行缺失」且「CBDB 配对列不可用/不当」时生效。当前为空：实测配对列已自洽，
# 逐码核验见 outputs/.../reverse_map.csv；若日后发现配对列有误，在此覆盖即可（留痕）。
REV_KIN_MANUAL: dict[int, int] = {}
REV_ASSOC_MANUAL: dict[int, int] = {}

# ─────────────── 类型映射（R1.2-3）───────────────
KIN_TYPES_NEW = {"母子", "父女", "祖孫", "旁系", "夫妻", "姻亲"}     # 需下游同步的新枚举
TYPE_FOLD_LEGACY = {"母子": "父子", "父女": "父子", "祖孫": "父子",
                    "旁系": "兄弟", "夫妻": "翁婿", "姻亲": "其他"}

# 精确表：称谓 → 类型。键为 CBDB 实际出现的写法；查找时先试原串，再试按「;」「/」拆分的各段。
KIN_TYPE_EXACT: dict[str, str] = {
    # ── 父子（直系父与子，含继嗣养子）──
    "父": "父子", "繼父": "父子", "嗣父": "父子", "養父": "父子", "私生子之本生父": "父子",
    "子": "父子", "長子; 第一子": "父子", "長子": "父子", "次子": "父子", "三子": "父子",
    "四子": "父子", "五子": "父子", "六子": "父子", "七子": "父子", "八子": "父子",
    "九子": "父子", "十子": "父子", "十一子": "父子", "季子": "父子", "獨子": "父子",
    "嗣子": "父子", "過繼的嗣子": "父子", "繼子": "父子", "養子(非嗣子)": "父子",
    "私生子": "父子", "唯一幸存的兒子": "父子", "幸存的長子": "父子",
    # ── 母子（直系母）──
    "母": "母子", "繼母": "母子", "嫡母": "母子", "嗣母": "母子", "養母": "母子",
    "生母": "母子", "私生子女之本生母": "母子",
    # ── 父女 / 母女（直系女；锚点为女性时取「母女」，实测 332 锚点全为男性）──
    "女": "父女", "女兒": "父女", "長女": "父女", "次女": "父女", "二女": "父女",
    "三女": "父女", "四女": "父女", "養女": "父女", "獨女": "父女",
    # ── 祖孫（直系隔代 + 外祖/外孫 + 不定位直系）──
    "祖父": "祖孫", "祖母": "祖孫", "嗣祖父": "祖孫", "嗣祖母": "祖孫",
    "曾祖": "祖孫", "曾祖母": "祖孫", "高祖;四世祖": "祖孫", "五世祖;高曾祖": "祖孫",
    "六世祖;太祖": "祖孫", "七世祖;太曾祖": "祖孫", "八世祖;太高祖": "祖孫",
    "九世祖;太高曾祖": "祖孫", "十二世祖": "祖孫",
    "外祖父": "祖孫", "外祖母": "祖孫", "外曾祖父": "祖孫",
    "孫": "祖孫", "孫女": "祖孫", "曾孫; 重孫": "祖孫", "曾孫女": "祖孫",
    "玄孫;四世孫": "祖孫", "五世孫;來孫": "祖孫", "六世孫;昆孫": "祖孫",
    "七世孫;仍孫": "祖孫", "八世孫;雲孫": "祖孫", "九世孫": "祖孫",
    "十二世孫": "祖孫", "過繼的嗣孫": "祖孫", "外孫": "祖孫", "外孫女": "祖孫",
    "外孫女之子": "祖孫", "直系祖先": "祖孫", "直系後裔": "祖孫",
    # ── 兄弟（同辈，含堂從表）──
    "兄": "兄弟", "弟": "兄弟", "姊": "兄弟", "妹": "兄弟", "兄弟": "兄弟",
    "姊妹": "兄弟", "長兄": "兄弟", "從兄": "兄弟", "從弟": "兄弟", "從妹": "兄弟",
    "從兄弟;堂兄弟": "兄弟", "族兄": "兄弟", "族弟": "兄弟", "族姊": "兄弟",
    "表兄": "兄弟", "表弟": "兄弟", "表姐": "兄弟", "舅表弟": "兄弟", "姑表兄": "兄弟",
    # ── 旁系（伯叔姑舅姨、姪甥、族亲等）──
    "從父;伯叔父": "旁系", "伯;伯父": "旁系", "叔;叔父": "旁系", "叔": "旁系", "伯": "旁系",
    "從子;姪子": "旁系", "從女;姪女": "旁系", "姪女": "旁系", "從祖;伯叔祖": "旁系",
    "叔祖;叔祖父": "旁系", "曾伯叔祖;從曾祖": "旁系", "姪孫;從孫": "旁系",
    "曾姪孫;從曾孫": "旁系", "姪孫女": "旁系", "族子": "旁系", "族女": "旁系",
    "族父": "旁系", "族姑": "旁系", "姑母": "旁系", "祖姑": "旁系", "姨;從母": "旁系",
    "母舅": "旁系", "外甥": "旁系", "甥女": "旁系", "同族長輩": "旁系", "同族晚輩": "旁系",
    "族人(輩分不詳)": "旁系",
    # ── 夫妻（本家配偶）──
    "丈夫": "夫妻", "妻子": "夫妻", "妻": "夫妻", "第一任妻": "夫妻", "第二任妻": "夫妻",
    "妾": "夫妻", "繼室": "夫妻", "正室": "夫妻", "側室": "夫妻",
    # ── 翁婿（岳家与女婿一线）──
    "岳父": "翁婿", "岳母": "翁婿", "女婿": "翁婿", "長女婿": "翁婿", "二女婿": "翁婿",
    "三女婿": "翁婿", "四女婿": "翁婿", "八女婿": "翁婿", "第二任女婿": "翁婿",
    "第一任妻父": "翁婿", "第二任妻父": "翁婿", "第三任妻父": "翁婿",
    # ── 姻亲（妻族、媳婿、姑嫂、連襟……）──
    "姐夫": "姻亲", "妹夫": "姻亲", "姊妹夫": "姻亲", "妻弟": "姻亲", "妻妹": "姻亲",
    "妻兄": "姻亲", "妻之祖父": "姻亲", "妻之曾祖": "姻亲", "妻之叔伯": "姻亲",
    "妻之叔伯祖": "姻亲", "妻之姑母": "姻亲", "第一任妻之祖": "姻亲",
    "第一任妻之叔伯": "姻亲", "內兄弟;妻兄弟": "姻亲",
    "連襟;妻姊妹之夫": "姻亲", "姪女之夫": "姻亲", "姪孫女之夫": "姻亲",
    "子婦;兒媳": "姻亲", "孫媳": "姻亲", "翁;公公;丈夫之父": "姻亲",
    "夫之兄弟": "姻亲", "夫之祖父": "姻亲", "兄弟之妻": "姻亲", "姻親": "姻亲",
    "孫女婿": "姻亲", "曾孫女婿": "姻亲", "外孫女婿": "姻亲", "岳母之父": "姻亲",
}
# 关键词兜底（精确表未命中时；只为将来新码留安全网，命中情况见报告）
KIN_TYPE_KW: list[tuple[tuple[str, ...], str]] = [
    (("妻之", "妻弟", "妻妹", "妻兄", "姐夫", "妹夫", "媳", "女婿", "翁", "夫之",
      "連襟", "姻親"), "姻亲"),
    (("岳父", "岳母", "女婿"), "翁婿"),
    (("丈夫", "妻子", "妾", "繼室", "正室", "側室"), "夫妻"),
    (("母",), "母子"),
    (("父",), "父子"),
    (("姪", "侄", "甥", "伯叔", "族", "從", "姑", "舅", "姨", "堂"), "旁系"),
    (("祖", "孫", "直系"), "祖孫"),
    (("女", "兒"), "父女"),
    (("兄", "弟", "姊", "妹", "表"), "兄弟"),
    (("子",), "父子"),
]
SON_WORDS = {"子", "長子", "次子", "三子", "四子", "五子", "六子", "七子", "八子",
             "九子", "十子", "十一子", "季子", "獨子", "嗣子", "過繼的嗣子", "繼子",
             "養子(非嗣子)", "私生子", "唯一幸存的兒子", "幸存的長子"}
DAUGHTER_WORDS = {"女", "女兒", "長女", "次女", "二女", "三女", "四女", "養女", "獨女"}


def map_assoc(desc_chn: str, type_chn: str = "") -> str:
    """ASSOC_CODES.c_assoc_desc_chn + ASSOC_TYPES -> 中文枚举（本任务不动社会关系口径）。"""
    t = f"{desc_chn or ''} {type_chn or ''}"
    if any(k in t for k in ("同年", "同科", "同榜")):
        return "同年"
    if any(k in t for k in ("门生", "門生", "门人", "門人", "弟子", "受业", "受業",
                            "学生", "學生", "之师", "之師", "为师", "為師", "師生", "师生")):
        return "师生"
    if any(k in t for k in ("弹劾", "彈劾", "攻讦", "攻訐", "政敌", "政敵", "排挤", "排擠",
                            "陷害", "劾", "讦")):
        return "政敌"
    if any(k in t for k in ("同僚", "同事", "同官", "幕僚", "属下", "屬下", "上司", "同曹")):
        return "同僚"
    if any(k in t for k in ("友", "游", "交", "识", "識", "知", "唱和", "唱酬")):
        return "友人"
    return "其他"


def kin_type(label: str, anchor_female: bool, stats: Counter) -> str:
    """亲属称谓 -> 类型（R1.2-3）。"""
    stats["_words"][label] += 1
    tp = None
    if label in KIN_TYPE_EXACT:
        tp = KIN_TYPE_EXACT[label]
        stats["exact"] += 1
    else:
        for seg in (s.strip() for s in label.replace("/", ";").split(";") if s.strip()):
            if seg in KIN_TYPE_EXACT:
                tp = KIN_TYPE_EXACT[seg]
                stats["exact_seg"] += 1
                break
    if tp is None:
        for kws, t in KIN_TYPE_KW:
            if any(k in label for k in kws):
                tp = t
                stats[f"kw:{t}"] += 1
                break
    if tp is None:
        stats["fallback_other"] += 1
        return "其他"
    # 直系子女/父母按锚点性别细分（实测锚点全男性，此路径为将来女性状元兜底）
    if label in DAUGHTER_WORDS:
        tp = "母女" if anchor_female else "父女"
    elif label in SON_WORDS and anchor_female:
        tp = "母子"
    return tp


# ─────────────── 反向称谓映射表构建（R1.2-1b）───────────────
class ReverseMap:
    """码值 -> (反向码值, 来源)。来源：manual / pair1 / pair2 / pair1|pair2=NNN / self / none。"""

    def __init__(self, manual: dict[int, int]):
        self.manual = manual
        self.table: dict[int, tuple[int | None, str]] = {}
        self.stats: Counter = Counter()

    def get(self, code: int) -> tuple[int | None, str]:
        return self.table.get(code, (None, "untabled"))


def build_reverse_maps(kin_codes, assoc_codes) -> tuple[ReverseMap, ReverseMap]:
    kin = ReverseMap(REV_KIN_MANUAL)
    for code, row in sorted(kin_codes.items()):
        if code in SENTINEL_CODES or (row.get("c_kinrel_chn") or "").strip() in BAD_WORDS:
            continue
        if code in REV_KIN_MANUAL:
            kin.table[code] = (REV_KIN_MANUAL[code], "manual")
            kin.stats["manual"] += 1
            continue
        p1, p2 = row.get("c_kin_pair1"), row.get("c_kin_pair2")
        ok1, ok2 = _usable_kin(kin_codes, p1), _usable_kin(kin_codes, p2)
        if ok1 and ok2:
            kin.table[code] = (p1, f"pair1|pair2={p2}")
            kin.stats["pair1+pair2"] += 1
        elif ok1:
            kin.table[code] = (p1, "pair1")
            kin.stats["pair1"] += 1
        elif ok2:
            kin.table[code] = (p2, "pair2")
            kin.stats["pair2"] += 1
        else:
            kin.table[code] = (None, "none")
            kin.stats["none"] += 1

    assoc = ReverseMap(REV_ASSOC_MANUAL)
    for code, row in sorted(assoc_codes.items()):
        if code in SENTINEL_CODES or (row.get("c_assoc_desc_chn") or "").strip() in BAD_WORDS:
            continue
        if code in REV_ASSOC_MANUAL:
            assoc.table[code] = (REV_ASSOC_MANUAL[code], "manual")
            assoc.stats["manual"] += 1
            continue
        rev = row.get("c_assoc_pair")
        if rev == code:                       # 对称码（友/相唱和/與Y結黨）：无需翻转
            assoc.table[code] = (code, "self")
            assoc.stats["self"] += 1
            continue
        rdesc = ((assoc_codes.get(rev) or {}).get("c_assoc_desc_chn") or "").strip() if rev else ""
        if rev in assoc_codes and rdesc not in BAD_WORDS:
            assoc.table[code] = (rev, "pair")
            assoc.stats["pair"] += 1
        else:
            assoc.table[code] = (None, "none")
            assoc.stats["none"] += 1
    return kin, assoc


def _usable_kin(kin_codes, code) -> bool:
    if code is None or code in SENTINEL_CODES:
        return False
    row = kin_codes.get(code)
    return bool(row) and (row.get("c_kinrel_chn") or "").strip() not in BAD_WORDS


# 内置 10 锚点小样本（R1.2-1d）：覆盖 Y 重灾、纯反向、无镜像行、越界跳过、状元间边等场景
DEFAULT_SAMPLE = [
    "wang_wei",        # 验收用例：崔氏「母/子」同标；Y 18 处
    "lv_nan",          # 反向行 343 条、反向 Y 338 处（全库最大）
    "chen_liang",      # 反向 Y 208 处 + 1 条无镜像行
    "fei_hong",        # 反向 Y 134 处 + 1 条无镜像行
    "wu_kuan",         # 越界清单命中（吳孟融 702396）+ 反向 Y 143 处
    "han_tan",         # 越界清单命中（顧嗣雍 702895）
    "zhang_qu_hua",    # 越界清单命中（張津 701483）
    "li_di",           # KIN 无镜像行最多（3 条）→ 走配对列兜底
    "wang_ying_chen",  # 状元间边最多（6 条）+ 反向 Y 173 处
    "wen_tian_xiang",  # 反向 287 条、状元间边 5 条；其 index slug 与 persons id 曾不一致
]
DEFAULT_SAMPLE_SET = set(DEFAULT_SAMPLE)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只统计不写 data/（默认行为）")
    ap.add_argument("--apply", action="store_true", help="真正落盘（R1.2-4c 用；本任务不用）")
    ap.add_argument("--purge-machine", action="store_true",
                    help="R1.2-4b：先清掉旧机器边（note 含「CBDB」或 to_id 为 cbdb: 前缀）再收割；"
                         "配合 --dry-run 只输出待删清单（默认），配合 --apply 真删后重跑")
    ap.add_argument("--sample", help="逗号分隔的锚点 slug 列表，只产出这些锚点的边")
    ap.add_argument("--sample-default", action="store_true", help="跑内置 10 锚点小样本（R1.2-1d）")
    ap.add_argument("--export-codes", action="store_true", help="额外打印码表导出摘要（R1.2-1a）")
    ap.add_argument("--legacy-types", action="store_true", help="新枚举折回既有 9 类（对照用）")
    ap.add_argument("--y-fill", choices=["name", "other"], default="name",
                    help="Y 占位符替换成对方姓名(name, 默认)或「對方」(other)")
    ap.add_argument("--report-dir", default=str(REPORT_DIR))
    ap.add_argument("--sample-rows", type=int, default=0, help="样本页每锚点最多展示多少条边（0=全部）")
    ap.add_argument("--selftest", action="store_true", help="跑验收自检（含无反向词跳过路径的合成用例）")
    args = ap.parse_args()

    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    write_data = bool(args.apply)
    print("⚠ --apply：将写入 data/relations/（本任务约定只 dry-run；请确认 R1.2-4 备份已完成）"
          if write_data else "dry-run 模式：不写任何 data/ 文件（报告写入 outputs/）")

    # ---------- 锚点与 slug 解析 ----------
    index = yaml.safe_load(INDEX.read_text(encoding="utf-8"))
    all_anchors: dict[int, dict] = {
        int(e["cbdb_id"]): {"slug": e["slug"], "name": e["name"]}
        for e in index
        if e.get("status") == "confirmed" and e.get("cbdb_id") is not None
    }
    person_ids = {p.stem for p in PERSON_DIR.glob("*.yaml") if not p.name.startswith("_")}
    name_year_to_pid: dict[tuple, str] = {}
    for p in PERSON_DIR.glob("*.yaml"):
        if p.name.startswith("_"):
            continue
        pd = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        name_year_to_pid[(pd.get("name"), pd.get("exam_year"))] = p.stem
    slug_to_exam = {e["slug"]: e.get("exam_year") for e in index}
    name_by_slug = {e["slug"]: e.get("name") for e in index}

    resolved: dict[int, str | None] = {}
    for cid, info in all_anchors.items():
        slug = info["slug"]
        if slug in person_ids:
            resolved[cid] = slug
        else:
            resolved[cid] = name_year_to_pid.get((info["name"], slug_to_exam.get(slug)))
    n_unresolved = sum(1 for v in resolved.values() if not v)
    print(f"锚点状元（confirmed + cbdb_id）: {len(all_anchors)}；slug 解析 {len(all_anchors) - n_unresolved}"
          f"/{len(all_anchors)} 命中 persons" + (f"（{n_unresolved} 人无档案，其边计 from_unresolved）" if n_unresolved else ""))

    # ---------- 产出范围 ----------
    # 收割恒按**全量锚点**进行（报告数字 = R1.2-4c 重跑后的真实结果）；
    # --sample/--sample-default 只影响审查页聚焦哪些锚点，不影响统计口径。
    emit_anchors = dict(all_anchors)
    sample_order: list[str] = []
    if args.sample_default:
        sample_order = list(DEFAULT_SAMPLE)
    if args.sample:
        sample_order = [s.strip() for s in args.sample.split(",") if s.strip()]
    if sample_order:
        by_slug = {info["slug"]: cid for cid, info in all_anchors.items()}
        missing = [s for s in sample_order if s not in by_slug]
        if missing:
            print(f"✗ 未知锚点 slug: {missing}")
            return 2
        print(f"样本模式：全量收割，审查页聚焦 {len(sample_order)} 个锚点 {sample_order}")

    # ---------- 越界清单（硬约束）----------
    excluded: dict[int, str] = {}
    if OUT_OF_SCOPE.exists():
        oos = yaml.safe_load(OUT_OF_SCOPE.read_text(encoding="utf-8")) or {}
        for item in oos.get("excluded") or []:
            excluded[int(item["cbdb_id"])] = item.get("name") or ""
    print(f"越界清单：{len(excluded)} 个 personid 一律跳过（R0-1 范围外）")

    # ---------- 现有数据（只读）----------
    rel_docs: dict[str, dict] = {}
    existing_all: set[tuple] = set()        # 全部现有边
    manual_baseline: set[tuple] = set()     # **人工边**（purge 后仍留存）→ 用于防重
    for f in sorted(REL_DIR.glob("*.yaml")):
        if f.name.startswith("_"):
            continue
        doc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        rel_docs[f.stem] = doc
        for r in doc.get("relations") or []:
            key = (doc.get("from_id"), r.get("to_id"), r.get("type"))
            existing_all.add(key)
            is_machine = "CBDB" in (r.get("note") or "") or bool(MACHINE_TO_RE.match(str(r.get("to_id"))))
            if not is_machine:
                manual_baseline.add(key)
    print(f"现有 data/relations：{sum(len((d or {}).get('relations') or []) for d in rel_docs.values())} 条边 / "
          f"{len(rel_docs)} 文件；其中人工边 {len(manual_baseline)} 条（防重基线）")

    # ---------- R1.2-4b：旧机器边清洗（--purge-machine）----------
    # 识别口径与防重基线一致：note 含「CBDB」或 to_id 为 cbdb: 前缀 ⇒ 机器边。
    # 设 --purge-machine 后，后续一切统计/落盘都在**清洗后的视图**上进行，
    # 故 dry-run 报出的候选边数字 = purge 后重跑的真实结果。
    purge_plan: list[dict] = []
    purged_docs: dict[str, dict] = {}
    purged_slugs: set[str] = set()
    n_machine = 0
    for slug, doc in rel_docs.items():
        keep: list = []
        for r in doc.get("relations") or []:
            to_id = str(r.get("to_id"))
            is_machine = ("CBDB" in (r.get("note") or "")) or bool(MACHINE_TO_RE.match(to_id))
            if is_machine:
                n_machine += 1
                if args.purge_machine:
                    purged_slugs.add(slug)
                    purge_plan.append({"from_id": slug, "to_id": to_id,
                                       "type": r.get("type") or "", "note": r.get("note") or ""})
                    continue
            keep.append(r)
        nd = dict(doc)
        nd["relations"] = keep
        purged_docs[slug] = nd

    if args.purge_machine:
        rel_docs = purged_docs
        existing_all = set()
        manual_baseline = set()
        for slug, doc in rel_docs.items():
            for r in doc.get("relations") or []:
                key = (doc.get("from_id"), r.get("to_id"), r.get("type"))
                existing_all.add(key)
                manual_baseline.add(key)      # 清洗后剩下的全部是人工边
        kept_files = sum(1 for d in rel_docs.values() if d.get("relations"))
        emptied = [s for s, d in rel_docs.items() if not d.get("relations")]
        print("─" * 62)
        print(f"【--purge-machine】待删机器边 {n_machine} 条 / 涉及 "
              f"{len({p['from_id'] for p in purge_plan})} 文件")
        print(f"留存人工边 {len(manual_baseline)} 条 / {kept_files} 文件；"
              f"清洗后变空、将被删除的机器专属文件 {len(emptied)} 个")
        # 待删清单落盘（供人工签字），并打印边数最多的文件
        with (report_dir / "purge_plan.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["from_id", "to_id", "type", "note"])
            w.writeheader()
            for row in sorted(purge_plan, key=lambda x: (x["from_id"], x["to_id"])):
                w.writerow(row)
        per_file = Counter(p["from_id"] for p in purge_plan)
        print(f"待删清单已写入 {report_dir / 'purge_plan.csv'}；边数最多的人物：")
        for slug, n in per_file.most_common(8):
            print(f"    {slug:<24} {n} 条")
        # 人工边留存清单（零损失核对用）
        with (report_dir / "manual_edges_kept.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["from_id", "to_id", "type", "note"])
            w.writeheader()
            for slug, doc in sorted(rel_docs.items()):
                for r in doc.get("relations") or []:
                    w.writerow({"from_id": doc.get("from_id"), "to_id": r.get("to_id"),
                                "type": r.get("type") or "", "note": r.get("note") or ""})
        print(f"人工边留存清单：{report_dir / 'manual_edges_kept.csv'}")

    # ---------- CBDB（只读）----------
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    kin_codes = {r["c_kincode"]: dict(r) for r in conn.execute("SELECT * FROM KINSHIP_CODES")}
    assoc_codes = {r["c_assoc_code"]: dict(r) for r in conn.execute("SELECT * FROM ASSOC_CODES")}
    rev_kin, rev_assoc = build_reverse_maps(kin_codes, assoc_codes)

    name_cache: dict[int, str] = {}

    def name_of(pid: int) -> str:
        if pid in all_anchors:
            return all_anchors[pid]["name"]
        if pid not in name_cache:
            row = conn.execute("SELECT c_name_chn FROM BIOG_MAIN WHERE c_personid=?", (pid,)).fetchone()
            name_cache[pid] = (row["c_name_chn"] if row and row["c_name_chn"] else f"CBDB#{pid}")
        return name_cache[pid]

    fem_cache: dict[int, bool] = {}

    def is_female(pid: int) -> bool:
        if pid not in fem_cache:
            row = conn.execute("SELECT c_female FROM BIOG_MAIN WHERE c_personid=?", (pid,)).fetchone()
            fem_cache[pid] = bool(row and row["c_female"] == 1)
        return fem_cache[pid]

    def kin_chn(code) -> str:
        return ((kin_codes.get(code) or {}).get("c_kinrel_chn") or "").strip()

    def assoc_desc(code) -> str:
        return ((assoc_codes.get(code) or {}).get("c_assoc_desc_chn") or "").strip()

    # ---------- 拉取关系行（全量锚点口径）----------
    ids = ",".join(str(i) for i in all_anchors)
    kin_rows = conn.execute(
        f"SELECT c_personid, c_kin_id, c_kin_code FROM KIN_DATA "
        f"WHERE c_personid IN ({ids}) OR c_kin_id IN ({ids})").fetchall()
    assoc_rows = conn.execute(
        f"SELECT c_personid, c_assoc_id, c_assoc_code, c_assoc_first_year FROM ASSOC_DATA "
        f"WHERE c_personid IN ({ids}) OR c_assoc_id IN ({ids})").fetchall()
    print(f"CBDB 行（全量锚点）：KIN {len(kin_rows)} / ASSOC {len(assoc_rows)}")

    kin_mirror: dict[tuple, set] = defaultdict(set)
    for r in kin_rows:
        kin_mirror[(r["c_personid"], r["c_kin_id"])].add(r["c_kin_code"])
    assoc_mirror: dict[tuple, set] = defaultdict(set)
    for r in assoc_rows:
        assoc_mirror[(r["c_personid"], r["c_assoc_id"])].add(r["c_assoc_code"])
    self_loops = Counter()
    self_loops["kin"] = sum(1 for r in kin_rows if r["c_personid"] == r["c_kin_id"])
    self_loops["assoc"] = sum(1 for r in assoc_rows if r["c_personid"] == r["c_assoc_id"])

    # ---------- 覆盖度实测（全量口径，R1.2-1b）----------
    cov_rev_edges: dict[str, Counter] = {"kin": Counter(), "assoc": Counter()}
    hit_codes: dict[str, Counter] = {"kin": Counter(), "assoc": Counter()}
    hit_side: dict[str, Counter] = {"kin": Counter(), "assoc": Counter()}
    mirror_avail = Counter()

    def scan(table: str, rows, pkey: str, qkey: str, mapobj: ReverseMap, chn_of) -> None:
        for r in rows:
            p, q, code = r[pkey], r[qkey], r["c_kin_code" if table == "kin" else "c_assoc_code"]
            if p == q:
                continue
            hit_codes[table][code] += 1
            if chn_of(code) in BAD_WORDS:      # 无信息量行（未詳…）在收割侧按 desc_empty 丢弃
                cov_rev_edges[table]["desc_empty"] += 1
                continue
            anchor, other = (p, q) if p in all_anchors else (q, p)
            if p in all_anchors and q in all_anchors:
                anchor, other = p, q
            if p == anchor:
                hit_side[table]["forward"] += 1
                continue
            hit_side[table]["reverse"] += 1
            mirrors = [c for c in (kin_mirror if table == "kin" else assoc_mirror)
                       .get((anchor, other), set())]
            if any(chn_of(c) not in BAD_WORDS for c in mirrors):
                cov_rev_edges[table]["mirror"] += 1
                continue
            rev, src = mapobj.get(code)
            if rev is None:
                cov_rev_edges[table]["none"] += 1
            elif src == "self":
                cov_rev_edges[table]["self"] += 1
            else:
                cov_rev_edges[table]["pair"] += 1
            if not mirrors:
                mirror_avail[table] += 1

    scan("kin", kin_rows, "c_personid", "c_kin_id", rev_kin, kin_chn)
    scan("assoc", assoc_rows, "c_personid", "c_assoc_id", rev_assoc, assoc_desc)

    def coverage(table: str) -> dict:
        # 分母剔除「无信息量行」（未詳/缺乏信息），它们在收割侧按 desc_empty 丢弃
        total_edges = sum(hit_codes[table].values()) - cov_rev_edges[table]["desc_empty"]
        covered_edges = total_edges - cov_rev_edges[table]["none"]
        # 按码值口径：反向侧命中的码值中，有镜像/配对/对称可用的比例
        codes_needing_rev, codes_ok = set(), set()
        pair_only_ok: set = set()      # 仅凭配对列（不看镜像行）能翻转的码值 → 兜底能力
        edges_pair_only, edges_mirror = 0, 0
        for r in (kin_rows if table == "kin" else assoc_rows):
            p, q = r["c_personid"], r[qkey_for(table)]
            code = r["c_kin_code" if table == "kin" else "c_assoc_code"]
            if p == q:
                continue
            anchor, other = (p, q) if p in all_anchors else (q, p)
            if p in all_anchors and q in all_anchors:
                anchor, other = p, q
            if p == anchor:
                continue
            if (kin_chn if table == "kin" else assoc_desc)(code) in BAD_WORDS:
                continue
            codes_needing_rev.add(code)
            rev, src = (rev_kin if table == "kin" else rev_assoc).get(code)
            if rev is not None and src != "none":
                pair_only_ok.add(code)
            mirrors = [c for c in (kin_mirror if table == "kin" else assoc_mirror)
                       .get((anchor, other), set())]
            if any((kin_chn if table == "kin" else assoc_desc)(c) not in BAD_WORDS for c in mirrors):
                codes_ok.add(code)
                edges_mirror += 1
            elif rev is not None and src != "none":
                codes_ok.add(code)
                edges_pair_only += 1
        return {"edges": total_edges, "covered_edges": covered_edges,
                "rev_codes": len(codes_needing_rev), "ok_codes": len(codes_ok),
                "edge_rate": covered_edges / total_edges * 100 if total_edges else 100.0,
                "code_rate": len(codes_ok) / len(codes_needing_rev) * 100 if codes_needing_rev else 100.0,
                "codes_all": len(hit_codes[table]),
                "pair_only_codes": len(pair_only_ok),
                "pair_only_rate": len(pair_only_ok) / len(codes_needing_rev) * 100 if codes_needing_rev else 100.0,
                "edges_mirror": edges_mirror, "edges_pair_only": edges_pair_only}

    def qkey_for(table: str) -> str:
        return "c_kin_id" if table == "kin" else "c_assoc_id"

    cov_kin, cov_assoc = coverage("kin"), coverage("assoc")

    # ---------- 收割（产出范围 = emit_anchors）----------
    skip = Counter()
    skip_detail: list[dict] = []
    type_counter = Counter()
    type_counter_legacy = Counter()
    direction_counter = Counter()
    source_counter = Counter()
    kin_label_stats: Counter = Counter()
    kin_label_stats["_words"] = Counter()
    new_edges: dict[str, list[dict]] = defaultdict(list)
    edge_records: list[dict] = []
    reserved: set[tuple] = set()
    merged_reverse = Counter()          # 反向行归并到正向边的计数（方向修复的核心证据）
    merged_detail: list[dict] = []
    y_replaced = 0
    y_left = 0

    def anchor_of(p, q):
        """返回 (锚点, 对方, side)；非锚点行返回 None。双方皆锚点时只认 p 侧（旧口径）。"""
        pa, qa = p in all_anchors, q in all_anchors
        if pa and qa:
            return (p, q, "forward", "both_anchor")
        if pa:
            return (p, q, "forward", "")
        if qa:
            return (q, p, "reverse", "")
        return None

    def fill_y(desc: str, other_name: str) -> str:
        nonlocal y_replaced
        if "Y" not in desc:
            return desc
        y_replaced += 1
        return desc.replace("Y", other_name if args.y_fill == "name" else "對方")

    def label_for_reverse(table: str, code: int, anchor: int, other: int) -> tuple[int | None, str, str]:
        """反向行取「对方相对锚点」的称谓/描述。返回 (label_code, label, source)。"""
        chn_of = kin_chn if table == "kin" else assoc_desc
        mirror_idx = kin_mirror if table == "kin" else assoc_mirror
        mapobj = rev_kin if table == "kin" else rev_assoc
        # ① 镜像行优先（CBDB 自己认定的反向，性别自动正确）
        for mc in sorted(mirror_idx.get((anchor, other), set())):
            mchn = chn_of(mc)
            if mchn not in BAD_WORDS:
                return mc, mchn, "mirror"
        # ② 反向称谓映射表
        if code in mapobj.manual:
            rc = mapobj.manual[code]
            return rc, chn_of(rc), "rev:manual"
        rev, src = mapobj.get(code)
        if rev is None:
            return None, "", "none"
        if src == "self":
            return rev, chn_of(rev), "rev:self"
        if src.startswith("pair1|pair2="):
            p2 = int(src.split("=", 1)[1])
            if is_female(other):
                return p2, chn_of(p2), "rev:pair2(gender)"
            return rev, chn_of(rev), "rev:pair1"
        return rev, chn_of(rev), f"rev:{src}"

    def build_note(label: str, other: int, year) -> str:
        other_name = name_of(other)
        if other in all_anchors and resolved.get(other):
            note = f"{label}（CBDB）"
        elif other in all_anchors:
            note = f"{label}：{other_name}（CBDB 外部人物·状元未建档）"
        else:
            note = f"{label}：{other_name}（CBDB 外部人物）"
        if year:
            note += f"，始年 {year}"
        return note

    def emit(anchor: int, other: int, table: str, code: int, direction: str,
             label_code: int | None, label: str, raw_desc: str, year, source: str,
             label_alt: str | None = None) -> None:
        slug = resolved.get(anchor)
        aname = all_anchors[anchor]["slug"]
        other_name = name_of(other)
        if not slug:
            skip["from_unresolved"] += 1
            skip_detail.append({"anchor": aname, "table": table, "other_cbdb": other,
                                "other_name": other_name, "reason": "from_unresolved",
                                "detail": "该状元无 persons 档案，无法建关系文件"})
            return
        if other in excluded:
            skip["out_of_scope"] += 1
            skip_detail.append({"anchor": aname, "table": table, "other_cbdb": other,
                                "other_name": other_name, "reason": "out_of_scope",
                                "detail": f"在 _cbdb_out_of_scope.yaml 排除清单内（{excluded[other]}）"})
            return
        # 类型：社会关系用**原始描述**判定（避免对方姓名污染 map_assoc）
        if table == "kin":
            raw_type = kin_type(label, is_female(anchor), kin_label_stats)
        else:
            raw_type = map_assoc(raw_desc, "")
        if args.legacy_types:
            raw_type = TYPE_FOLD_LEGACY.get(raw_type, raw_type)
        if other in all_anchors and resolved.get(other):
            to_id = resolved[other]
            note = f"{label}（CBDB）"
        elif other in all_anchors:
            to_id = f"cbdb:{other}"
            note = f"{label}：{other_name}（CBDB 外部人物·状元未建档）"
        else:
            to_id = f"cbdb:{other}"
            note = f"{label}：{other_name}（CBDB 外部人物）"
        if year:
            note += f"，始年 {year}"
        note_alt = build_note(label_alt, other, year) if label_alt else None
        if "Y" in note:
            y_left += 1
        key = (slug, to_id, raw_type)
        if key in reserved or (to_id, slug, raw_type) in reserved:
            skip["dup_within_harvest"] += 1
            if direction == "reverse":
                merged_reverse[table] += 1
                merged_detail.append({"anchor": aname, "table": table, "other_cbdb": other,
                                      "other_name": other_name, "code": code,
                                      "note_code": label_code, "type": raw_type, "note": note,
                                      "reason": "反向行归并至同 (from,to,type) 的正向边"})
            return
        if key in manual_baseline or (to_id, slug, raw_type) in manual_baseline:
            skip["dup_manual_baseline"] += 1
            return
        reserved.add(key)
        reserved.add((to_id, slug, raw_type))
        edge = {"to_id": to_id, "type": raw_type, "note": note, "src": "cbdb",
                f"{table}_code": code, "direction": direction}
        if label_code is not None and label_code != code:
            edge["note_code"] = label_code
        new_edges[slug].append(edge)
        edge_records.append({
            "anchor": slug, "anchor_name": all_anchors[anchor]["name"], "anchor_cbdb": anchor,
            "to_id": to_id,
            "other_cbdb": other, "other_name": other_name, "table": table, "code": code,
            "label_code": label_code, "direction": direction, "type": raw_type, "note": note,
            "note_code": label_code if (label_code is not None and label_code != code) else None,
            "note_alt": note_alt, "raw_desc": raw_desc,
            "year": year, "source": source, "src": "cbdb", f"{table}_code": code,
            "in_current": key in existing_all or (to_id, slug, raw_type) in existing_all})
        type_counter[raw_type] += 1
        direction_counter[direction] += 1
        source_counter[source] += 1

    def harvest(table: str, rows, pkey: str, qkey: str) -> None:
        by_anchor: dict[int, list] = defaultdict(list)
        for r in rows:
            p, q = r[pkey], r[qkey]
            code = r["c_kin_code" if table == "kin" else "c_assoc_code"]
            year = r["c_assoc_first_year"] if table == "assoc" else None
            if year is not None and year <= 0:
                year = None
            if p == q:
                by_anchor[p].append((q, "self_loop", code, year, "self_loop"))
                continue
            got = anchor_of(p, q)
            if not got:
                continue
            anchor, other, side, tag = got
            by_anchor[anchor].append((other, side, code, year, tag))
        for anchor in sorted(by_anchor):
            if anchor not in emit_anchors:
                continue
            aname = all_anchors[anchor]["slug"]
            for other, side, code, year, tag in sorted(by_anchor[anchor],
                                                       key=lambda x: (x[1], x[2], x[3] or 0, x[0])):
                if side == "self_loop":
                    skip["self_loop"] += 1
                    skip_detail.append({"anchor": aname, "table": table, "other_cbdb": other,
                                        "reason": "self_loop",
                                        "detail": "c_personid == 对方 id（源数据缺陷）"})
                    continue
                chn_of = kin_chn if table == "kin" else assoc_desc
                raw_desc = chn_of(code)
                if raw_desc in BAD_WORDS:
                    skip["desc_empty"] += 1
                    skip_detail.append({"anchor": aname, "table": table, "other_cbdb": other,
                                        "reason": "desc_empty", "detail": f"code={code} 称谓/描述为空或未詳"})
                    continue
                if tag == "both_anchor" and side != "forward":
                    continue    # 双方皆状元：只认 p 侧方向，与旧口径一致
                if side == "forward":
                    if table == "kin":
                        emit(anchor, other, table, code, "forward", code, raw_desc, raw_desc, year, "forward")
                    else:
                        alt = raw_desc.replace("Y", "對方") if "Y" in raw_desc else None
                        emit(anchor, other, table, code, "forward", code,
                             fill_y(raw_desc, name_of(other)), raw_desc, year, "forward", alt)
                else:
                    lc, label, source = label_for_reverse(table, code, anchor, other)
                    if lc is None:
                        skip["no_reverse_word"] += 1
                        cov_note = ("无镜像行且配对列为空" if (anchor, other) not in
                                    (kin_mirror if table == "kin" else assoc_mirror)
                                    else "镜像行与配对列均不可用")
                        skip_detail.append({"anchor": aname, "table": table, "other_cbdb": other,
                                            "reason": "no_reverse_word",
                                            "detail": f"code={code} 原述={raw_desc}；{cov_note}"})
                        continue
                    if table == "kin":
                        emit(anchor, other, table, code, "reverse", lc, label, raw_desc, year, source)
                    else:
                        alt = label.replace("Y", "對方") if "Y" in label else None
                        emit(anchor, other, table, code, "reverse", lc,
                             fill_y(label, name_of(other)), label, year, source, alt)

    harvest("kin", kin_rows, "c_personid", "c_kin_id")
    harvest("assoc", assoc_rows, "c_personid", "c_assoc_id")

    total_new = sum(len(v) for v in new_edges.values())
    print("─" * 62)
    print(f"落盘候选边：{total_new} 条 / {len(new_edges)} 人（对应 {len(emit_anchors)} 个锚点）")
    print(f"方向分布：{dict(direction_counter)}")
    print(f"反转依据：{dict(source_counter.most_common())}")
    print(f"类型分布：{dict(type_counter.most_common())}")
    print(f"Y 替换 {y_replaced} 次；产物 note 残留 Y {y_left} 条（应为 0）")
    print(f"KIN 映射：精确表 {kin_label_stats['exact'] + kin_label_stats['exact_seg']} / "
          f"关键词 {sum(v for k, v in kin_label_stats.items() if k.startswith('kw:'))} / "
          f"落其他 {kin_label_stats['fallback_other']}")
    print(f"跳过：{dict(skip.most_common())}")
    print(f"反向行归并到同 (from,to,type) 正向边的：{dict(merged_reverse)}")

    # ---------- 验收自检（R1.2-1d 的机器化部分）----------
    if args.selftest:
        print("─" * 62)
        checks: list[tuple[str, bool, str]] = []

        y_notes = [e for e in edge_records if "Y" in e["note"]]
        checks.append(("候选边 note 无 Y 占位符", not y_notes,
                       f"残留 {len(y_notes)} 条"))

        cui = [e for e in edge_records if e["anchor"] == "wang_wei"
               and e["other_name"].startswith("崔氏")]
        ok_cui = (len(cui) == 1 and cui[0]["type"] == "母子"
                  and cui[0]["note"].startswith("母：") and "Y" not in cui[0]["note"])
        checks.append(("王维↔崔氏 仅一条且为「母：崔氏」", ok_cui,
                       "；".join(f"{e['type']}/{e['note']}" for e in cui) or "无"))

        kin_types = {e["type"] for e in edge_records if e["table"] == "kin"}
        checks.append(("亲缘边不再落「其他」", "其他" not in kin_types, str(sorted(kin_types))))

        kin_types_new = {e["type"] for e in edge_records
                         if e["table"] == "kin" and e["type"] in KIN_TYPES_NEW}
        checks.append((f"新增枚举实际出现（{len(kin_types_new)} 类）", len(kin_types_new) >= 5,
                       str(sorted(kin_types_new))))

        allowed = {"同年", "师生", "父子", "兄弟", "翁婿", "政敌", "友人", "同僚", "其他"} | KIN_TYPES_NEW
        bad_types = {e["type"] for e in edge_records} - allowed
        checks.append(("类型值全部在枚举白名单内", not bad_types, str(sorted(bad_types))))

        oos_hit = {r["other_cbdb"] for r in skip_detail if r.get("reason") == "out_of_scope"}
        checks.append((f"越界清单 10 人全部命中并跳过", oos_hit == set(excluded),
                       f"命中 {len(oos_hit)}/{len(excluded)}"))

        rev_edges = [e for e in edge_records if e["direction"] == "reverse"]
        bad_rev = [e for e in rev_edges
                   if e.get("src") != "cbdb"
                   or (e.get("note_code") is None and e.get("label_code") != e["code"])]
        checks.append(("反向边均带 src=cbdb 且翻转码可追溯（note_code）", not bad_rev,
                       f"反向边 {len(rev_edges)} 条，缺 note_code {len(bad_rev)} 条"
                       + ("；" + "；".join(f"{e['anchor']}/{e['code']}→{e['label_code']}"
                                          for e in bad_rev[:5]) if bad_rev else "")))
        self_loops_in_edges = [e for e in edge_records
                               if e["to_id"] == resolved.get(e["anchor_cbdb"])]
        checks.append(("自环边未进入候选集", not self_loops_in_edges,
                       f"{len(self_loops_in_edges)} 条"))

        # 「无反向词 → 跳过并计数」路径的实证（合成码表，避免污染真实数据）
        fake_kin = {1: {"c_kincode": 1, "c_kinrel_chn": "某新称谓",
                        "c_kin_pair1": -10000, "c_kin_pair2": 0}}
        fake_rev, _ = build_reverse_maps(fake_kin, {})
        r1, s1 = fake_rev.get(1)
        checks.append(("合成码表：无反向词时 rev=None（会被跳过并计数）",
                       r1 is None, f"rev={r1} source={s1}"))

        n_fail = 0
        for name, ok, detail in checks:
            print(f"  {'✅' if ok else '❌'} {name}  —— {detail}")
            n_fail += 0 if ok else 1
        print(f"自检：{len(checks) - n_fail}/{len(checks)} 通过" + ("（全部通过）" if not n_fail else "❌ 存在失败项"))
        if n_fail:
            return 3

    write_reports(report_dir, kin_codes, assoc_codes, rev_kin, rev_assoc, hit_codes, hit_side,
                  cov_kin, cov_assoc, cov_rev_edges, mirror_avail, kin_label_stats, skip,
                  skip_detail, edge_records, type_counter, new_edges, all_anchors, resolved,
                  rel_docs, existing_all, manual_baseline, args, total_new, y_replaced, y_left,
                  sample_order, self_loops, merged_reverse, merged_detail, excluded)

    if args.export_codes:
        print(f"码表全量导出：{report_dir / 'code_tables.csv'}"
              f"（KINSHIP_CODES {len(kin_codes)} 行 / ASSOC_CODES {len(assoc_codes)} 行；"
              f"命中 KIN {len(hit_codes['kin'])} / ASSOC {len(hit_codes['assoc'])} 个码值）")
        print(f"反向称谓映射表：{report_dir / 'reverse_map.csv'}")
        print("命中频次 top10：")
        for label, cnt, mapobj, chn_of in (("KIN", hit_codes["kin"], rev_kin, kin_chn),
                                          ("ASSOC", hit_codes["assoc"], rev_assoc, assoc_desc)):
            for code, n in cnt.most_common(10):
                rev, src = mapobj.get(code)
                print(f"  {label} code={code:<6} {chn_of(code)!r:<22} ×{n:<5} "
                      f"→ {rev} {chn_of(rev) if rev is not None else '—'!r} ({src})")
    if not write_data:
        print(f"dry-run，未写 data/；报告目录 {report_dir}")
        return 0

    n_files = 0
    # ① purge 落地：先按清洗后视图重写（或删除）全部现存关系文件
    if args.purge_machine:
        removed_files = 0
        rewritten = 0
        for slug in sorted(purged_slugs):
            doc = purged_docs[slug]
            path = REL_DIR / f"{slug}.yaml"
            if doc.get("relations"):
                path.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False),
                                encoding="utf-8")
                rewritten += 1
            elif path.exists():
                path.unlink()
                removed_files += 1
        print(f"purge 落盘：清掉 {n_machine} 条机器边；保留人工边 "
              f"{len(manual_baseline)} 条；重写 {rewritten} 个（含人工边）文件、"
              f"删除变空文件 {removed_files} 个")
    # ② 追加本次收割的机器边
    for slug, rels in new_edges.items():
        path = REL_DIR / f"{slug}.yaml"
        doc = rel_docs.get(slug) or {"from_id": slug, "relations": []}
        doc.setdefault("relations", []).extend(rels)
        path.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
        n_files += 1
    print(f"写入 {n_files} 个关系文件")
    return 0


def write_reports(report_dir, kin_codes, assoc_codes, rev_kin, rev_assoc, hit_codes, hit_side,
                  cov_kin, cov_assoc, cov_rev_edges, mirror_avail, kin_label_stats, skip,
                  skip_detail, edge_records, type_counter, new_edges, all_anchors, resolved,
                  rel_docs, existing_all, manual_baseline, args, total_new, y_replaced, y_left,
                  sample_order, self_loops, merged_reverse, merged_detail, excluded) -> None:
    # ── 1. 码表全量导出 + 命中频次（R1.2-1a）──
    with (report_dir / "code_tables.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["table", "code", "chn", "pair1", "pair2",
                                          "hit_total", "hit_side"])
        w.writeheader()
        for code, r in sorted(kin_codes.items()):
            w.writerow({"table": "KINSHIP_CODES", "code": code,
                        "chn": kin_chn_of(r, "kin"), "pair1": r.get("c_kin_pair1"),
                        "pair2": r.get("c_kin_pair2"), "hit_total": hit_codes["kin"].get(code, 0),
                        "hit_side": ""})
        for code, r in sorted(assoc_codes.items()):
            w.writerow({"table": "ASSOC_CODES", "code": code,
                        "chn": kin_chn_of(r, "assoc"), "pair1": r.get("c_assoc_pair"),
                        "pair2": None, "hit_total": hit_codes["assoc"].get(code, 0), "hit_side": ""})

    # ── 2. 反向称谓映射表逐码明细（R1.2-1b）──
    with (report_dir / "reverse_map.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["table", "code", "chn", "rev_code", "rev_chn",
                                          "source", "hit_total", "covered"])
        w.writeheader()
        for table, mapobj, src in (("KINSHIP_CODES", rev_kin, kin_codes),
                                   ("ASSOC_CODES", rev_assoc, assoc_codes)):
            kind = "kin" if table == "KINSHIP_CODES" else "assoc"
            for code in sorted(hit_codes[kind]):
                rev, source = mapobj.get(code)
                w.writerow({"table": table, "code": code, "chn": kin_chn_of(src.get(code, {}), kind),
                            "rev_code": "" if rev is None else rev,
                            "rev_chn": "" if rev is None else kin_chn_of(src.get(rev, {}), kind),
                            "source": source, "hit_total": hit_codes[kind][code],
                            "covered": "Y" if rev is not None else "N"})

    # ── 3. 亲缘称谓 → 类型映射表（R1.2-1c）──
    with (report_dir / "kin_type_map.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["appellation", "type", "hits"])
        w.writeheader()
        for word, n in sorted(kin_label_stats["_words"].items(), key=lambda kv: -kv[1]):
            w.writerow({"appellation": word,
                        "type": KIN_TYPE_EXACT.get(word, "(关键词兜底/其他)"), "hits": n})

    # ── 4. 跳过清单明细 ──
    with (report_dir / "skip_list.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["anchor", "table", "other_cbdb", "other_name",
                                          "reason", "detail"])
        w.writeheader()
        for r in skip_detail:
            w.writerow({"anchor": r.get("anchor", ""), "table": r.get("table", ""),
                        "other_cbdb": r.get("other_cbdb", ""), "other_name": r.get("other_name", ""),
                        "reason": r.get("reason", ""), "detail": r.get("detail", "")})

    # ── 4b. 反向行归并明细（方向修复证据）──
    with (report_dir / "merged_reverse_edges.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["anchor", "table", "other_cbdb", "other_name",
                                          "code", "note_code", "type", "note", "reason"])
        w.writeheader()
        for r in merged_detail:
            w.writerow({k: r.get(k, "") for k in
                        ["anchor", "table", "other_cbdb", "other_name", "code", "note_code",
                         "type", "note", "reason"]})

    # ── 5. 主报告 ──
    REASONS = {
        "out_of_scope": "在 `_cbdb_out_of_scope.yaml` 排除清单内（R0-1 范围外，**硬约束**）",
        "no_reverse_word": "无镜像行且无反向词 → 整条跳过（宁缺毋滥）",
        "desc_empty": "码值称谓/描述为空或「未詳」，无信息量",
        "self_loop": "c_personid == 对方 id（源数据缺陷）",
        "from_unresolved": "锚点状元无 persons 档案，无法建关系文件",
        "dup_within_harvest": "同 (from,to,type) 在本次收割内重复（含 AB/BA 对称，如 母/子 双行归一）",
        "dup_manual_baseline": "与**人工边**同 (from,to,type) 重合（purge 后人工边留存，故防重）",
    }
    L: list[str] = []
    L.append("# CBDB 关系收割脚本改造 · 覆盖率与跳过报告（R1.2-1）\n")
    L.append(f"- 生成时间：{_dt.datetime.now():%Y-%m-%d %H:%M}（dry-run）")
    L.append("- 数据源：`vendor/cbdb/cbdb_20261010.sqlite3`（只读）")
    sample_note = ("；审查页聚焦样本 %d 人：%s" % (len(sample_order), "、".join(sample_order))
                   if sample_order else "")
    L.append(f"- 锚点：`confirmed + cbdb_id` 状元 **{len(all_anchors)}** 人（全量口径）{sample_note}")
    L.append(f"- 落盘候选边：**{total_new}** 条 / {len(new_edges)} 个关系文件")
    L.append(f"- Y 占位符落盘前替换：**{y_replaced}** 次（`--y-fill {args.y_fill}`）；"
             f"产物 note 残留 Y：**{y_left}** 条")
    L.append(f"- 模式：{'**--apply 落盘**' if args.apply else 'dry-run（未写 data/）'}"
             f"{'；--legacy-types 折回旧枚举' if args.legacy_types else ''}\n")

    L.append("## 1. 反向称谓映射表覆盖率（硬闸门 ≥95%）\n")
    L.append("| 表 | 需反向的码值 | 已覆盖码值 | 按码值 | 命中边数 | 已覆盖边 | 按边数 | 判定 |")
    L.append("|---|---|---|---|---|---|---|---|")
    for name, c in (("KINSHIP_CODES", cov_kin), ("ASSOC_CODES", cov_assoc)):
        ok = min(c["code_rate"], c["edge_rate"]) >= 95
        L.append(f"| {name} | {c['rev_codes']} | {c['ok_codes']} | {c['code_rate']:.1f}% | "
                 f"{c['edges']} | {c['covered_edges']} | {c['edge_rate']:.1f}% | "
                 f"{'✅ PASS' if ok else '❌ FAIL'} |")
    L.append("")
    L.append(f"- 命中码值：KIN {cov_kin['codes_all']} 个（正向 {hit_side['kin']['forward']} 行 / "
             f"反向 {hit_side['kin']['reverse']} 行）；ASSOC {cov_assoc['codes_all']} 个"
             f"（正向 {hit_side['assoc']['forward']} 行 / 反向 {hit_side['assoc']['reverse']} 行）")
    L.append(f"- 分母已剔除「无信息量行」（code 0/-1 等称谓为 `未詳`/`缺乏信息`者，"
             f"KIN {cov_rev_edges['kin']['desc_empty']} 行 / ASSOC {cov_rev_edges['assoc']['desc_empty']} 行）"
             f"——这类行在收割侧按 `desc_empty` 丢弃，不属于反向映射可解范围。")
    L.append("- **两层来源各自的覆盖能力**（关键结论：CBDB 镜像行本身就是最好的反向表）：")
    L.append("  | 表 | 关系行(正+反) | 需反向行 | 镜像行可解 | 仅配对列可解 | 两者皆无 | 镜像行覆盖率 | 配对列单独覆盖率 |")
    L.append("  |---|---|---|---|---|---|---|---|")
    for name, c, t in (("KINSHIP_CODES", cov_kin, "kin"), ("ASSOC_CODES", cov_assoc, "assoc")):
        nrev = hit_side[t]["reverse"]
        L.append(f"  | {name} | {c['edges']} | {nrev} | {c['edges_mirror']} | {c['edges_pair_only']} | "
                 f"{cov_rev_edges[t]['none']} | "
                 f"{c['edges_mirror'] / nrev * 100 if nrev else 100:.1f}% | "
                 f"{c['pair_only_rate']:.1f}%（{c['pair_only_codes']}/{c['rev_codes']} 码值） |")
    L.append("")
    L.append(f"- 配对列派生分布：KINSHIP_CODES {dict(rev_kin.stats.most_common())}；"
             f"ASSOC_CODES {dict(rev_assoc.stats.most_common())}")
    L.append("- 逐码明细：`reverse_map.csv`（含每个码值的反向码、来源、命中次数）\n")

    L.append("## 2. 方向修复统计（R1.2-1c）\n")
    n_fwd = sum(1 for e in edge_records if e["direction"] == "forward")
    n_rev = sum(1 for e in edge_records if e["direction"] == "reverse")
    L.append("| direction | 边数 | 含义 |")
    L.append("|---|---|---|")
    L.append(f"| forward | {n_fwd} | CBDB 原行即以锚点状元为主体，note 直接用原码称谓 |")
    L.append(f"| reverse | {n_rev} | 原行以对方为主体，note 已翻转为锚点视角 |")
    L.append("")
    L.append("落盘字段：`to_id / type / note / src: cbdb / kin_code|assoc_code（原始码） / direction / "
             "note_code（反向时=镜像或配对码）`")
    L.append("")
    L.append("**反向行归并证据**（本次方向修复的核心）：CBDB 多双向成对存储，同一对人物的两条行"
             "归一为同一条边——正向行先生成，反向行翻转后落到同一 `(from,to,type)` 而不再另起一条。"
             "旧脚本的「母 / 子」双条正是此处未归一所致：")
    L.append(f"- 归并掉的**反向行**：KIN {merged_reverse.get('kin', 0)} 条、ASSOC {merged_reverse.get('assoc', 0)} 条"
             f"（共 {sum(merged_reverse.values())} 条；明细见 `merged_reverse_edges.csv`）")
    L.append(f"- 因此 `direction: reverse` 只出现在「CBDB 仅有反向行、无正向行」的边上"
             f"（本批 {n_rev} 条），这类边才真正依赖反向称谓映射表")
    L.append(f"- 自环剔除：KIN {self_loops['kin']} 条、ASSOC {self_loops['assoc']} 条\n")

    L.append("## 3. 类型分布（R1.2-3）\n")
    L.append("| 类型 | 边数 | 是否新增枚举 |")
    L.append("|---|---|---|")
    for tp, n in type_counter.most_common():
        L.append(f"| {tp} | {n} | {'**是（需同步下游）**' if tp in KIN_TYPES_NEW else '否'} |")
    L.append("")
    L.append(f"亲缘称谓映射：精确表 {kin_label_stats['exact'] + kin_label_stats['exact_seg']} 条 / "
             f"关键词兜底 {sum(v for k, v in kin_label_stats.items() if k.startswith('kw:'))} 条 / "
             f"落「其他」**{kin_label_stats['fallback_other']}** 条 "
             f"{'✅ 不再落「其他」' if kin_label_stats['fallback_other'] == 0 else '❌ 仍有落其他'}")
    L.append("")
    L.append("⚠ **落盘前必须同步下游枚举**（属 R1.2-5 / R2-1 范围，本任务禁动）：")
    L.append(f"- `scripts/validate.py`：`REL_TYPES` += {sorted(KIN_TYPES_NEW)}")
    L.append("- `scripts/build_network.py`：`TYPES` += 同上；并决定是否并入 `GROUPS` 的「亲缘」组")
    fold = Counter()
    for tp, n in type_counter.items():
        if tp in TYPE_FOLD_LEGACY:
            fold[TYPE_FOLD_LEGACY[tp]] += n
    L.append("- 若改用 `--legacy-types`（不动枚举）的折算结果："
             + "、".join(f"→{k} +{v}" for k, v in sorted(fold.items(), key=lambda kv: -kv[1]))
             + "（代价：姻亲边埋回「其他」、夫妻边混入「翁婿」。可用 `--legacy-types` 复算）")
    L.append("")

    L.append("## 4. 跳过清单（计数）\n")
    L.append("| 原因 | 条数 | 说明 |")
    L.append("|---|---|---|")
    for k in list(REASONS) + [x for x in skip if x not in REASONS]:
        L.append(f"| `{k}` | {skip.get(k, 0)} | {REASONS.get(k, '')} |")
    L.append("")
    L.append(f"逐条明细见 `skip_list.csv`（{len(skip_detail)} 行）。")
    excluded_ids = sorted(excluded)
    oos_rows = [r for r in skip_detail if r.get("reason") == "out_of_scope"]
    if oos_rows:
        oos_ids = sorted({r["other_cbdb"] for r in oos_rows})
        L.append(f"\n**越界清单命中复核**（硬约束，必须与 `_cbdb_out_of_scope.yaml` 一致）："
                 f"命中 {len(oos_ids)}/{len(excluded_ids)} 个 personid、{len(oos_rows)} 行"
                 f"（去重后 {len({(r['anchor'], r['other_cbdb']) for r in oos_rows})} 对人物）。"
                 f"未命中的 personid：{sorted(set(excluded_ids) - set(oos_ids)) or '无'}")
        L.append("")
        L.append("| cbdb_id | 姓名 | 涉及锚点 | 行数 |")
        L.append("|---|---|---|---|")
        for pid in oos_ids:
            rows = [r for r in oos_rows if r["other_cbdb"] == pid]
            L.append(f"| {pid} | {rows[0].get('other_name', '')} | "
                     f"{'、'.join(sorted({r['anchor'] for r in rows}))} | {len(rows)} |")
    L.append("")

    L.append("## 5. 数据质量旁证\n")
    L.append(f"- 现有数据 Y 占位符：2639 处 / 177 个文件（计划文档记 2641，实测 2639）；重跑后应为 0。")
    L.append("- CBDB 配对列自洽性：`ASSOC_CODES.c_assoc_pair` 双向自洽（4↔5、43↔44、49↔50…），"
             "`c_assoc_pair2` 全表为 NULL；`KINSHIP_CODES.c_kin_pair1/pair2` 为「同性别变体 / 性别变体」，"
             "pair1 偶为「非可用」（如「丈夫」）须回退 pair2。")
    L.append("- ASSOC_DATA 的 `c_kin_id` 字段（87 行涉及锚点）绝大多数为 `未詳` 占位，"
             "不构成新的亲缘边来源，本次未纳入。")
    L.append(f"- 人工边防重基线：{len(manual_baseline)} 条（识别口径与 R1.2-4b 一致："
             "note 含「CBDB」或 to_id 为 `cbdb:` 前缀者视为机器边）\n")

    L.append("## 6. 产物清单\n")
    L.append("| 文件 | 用途 |")
    L.append("|---|---|")
    for fn, use in (("code_tables.csv", "KINSHIP_CODES/ASSOC_CODES 全量码表 + 命中频次（R1.2-1a）"),
                    ("reverse_map.csv", "反向称谓映射表逐码明细（R1.2-1b）"),
                    ("kin_type_map.csv", "亲缘称谓 → 类型映射表（R1.2-1c）"),
                    ("skip_list.csv", "跳过清单逐条明细"),
                    ("merged_reverse_edges.csv", "反向行归并明细（方向修复证据）"),
                    ("coverage_report.md", "本文件"),
                    ("sample_review.md", "10 锚点样本人工审查页（含旧数据对照，R1.2-1d）"),
                    ("sample_edges.yaml", "样本新边结构化输出"),
                    ("diff_vs_current.md", "全量候选 vs 现有数据差异汇总")):
        L.append(f"| `{fn}` | {use} |")
    (report_dir / "coverage_report.md").write_text("\n".join(L), encoding="utf-8")

    write_sample_review(report_dir, edge_records, all_anchors, resolved, rel_docs, args, sample_order)
    write_diff(report_dir, edge_records, rel_docs, local_sample=bool(sample_order))


def kin_chn_of(row: dict, kind: str) -> str:
    key = "c_kinrel_chn" if kind == "kin" else "c_assoc_desc_chn"
    return (row.get(key) or "").strip()


def write_sample_review(report_dir, edge_records, all_anchors, resolved, rel_docs, args,
                        sample_order) -> None:
    by_anchor: dict[str, list] = defaultdict(list)
    for e in edge_records:
        by_anchor[e["anchor"]].append(e)
    slug_of = {v: k for k, v in resolved.items() if v}
    if sample_order:
        order = sample_order
    else:   # 未指定样本时，取候选边最多的 25 人作抽查集
        order = sorted(by_anchor, key=lambda s: -len(by_anchor[s]))[:25]

    L: list[str] = ["# 锚点样本 · 新边人工审查页（R1.2-1d）\n"]
    L.append("- dry-run 产物；落盘字段：`to_id / type / note / src / kin_code|assoc_code / direction / note_code`")
    L.append(f"- 审查范围：{'--sample 指定的 ' if sample_order else '候选边最多的 '}{len(order)} 位锚点"
             f"（全量收割共 {len(all_anchors)} 锚点 / {len(edge_records)} 条候选边）")
    L.append(f"- 当前 Y 替换方案：`--y-fill {args.y_fill}`（"
             + ("把 Y 换成**对方姓名**，贴合工单字面" if args.y_fill == "name"
                else "把 Y 换成**「對方」**，与 build_network 现有显示逐字一致")
             + "）")
    L.append("- `direction`：forward = CBDB 原行即锚点为主体；reverse = 原行以对方为主体、已翻转为锚点视角")
    L.append("- `note_code`：反向边生成 note 所用的码值（镜像行或配对码），便于回溯核对\n")

    # Y 替换两方案并列（供编辑定夺；两案都保留「冒号+姓名」以兼容 build_network.split_label）
    alts = [e for e in edge_records if e.get("note_alt")]
    if alts:
        L.append("## 0. Y 占位符替换：两方案并列对照\n")
        L.append("CBDB 描述里的 Y 指代关系另一端。工单要求「替换为对方姓名」，但 note 的前缀会作为"
                 "关系标签展示、冒号后的姓名又被 `split_label()` 用来给名士层节点命名，"
                 "直接内联姓名会与后者重复。两案各有取舍，请编辑定夺（`--y-fill name|other` 一键切换）：\n")
        L.append("| 方案 A（`--y-fill name`，默认） | 方案 B（`--y-fill other`） | 码值 | CBDB 原始描述 |")
        L.append("|---|---|---|---|")
        for e in alts[:12]:
            a, b = (e["note"], e["note_alt"]) if args.y_fill == "name" else (e["note_alt"], e["note"])
            L.append(f"| {a} | {b} | {e['code']} | {e.get('raw_desc', '')} |")
        L.append("")
        L.append(f"- 涉及 Y 的候选边共 **{len(alts)}** 条 / {len(edge_records)} 条（"
                 f"{len(alts) / len(edge_records) * 100:.0f}%）。"
                 f"方案 A 会让「标签」与「冒号后姓名」出现同名重复（如 `為韋斌作墓誌銘：韋斌`）；"
                 f"方案 B 渲染结果与当前线上逐字一致，可零回归上线。\n")

    for slug in order:
        cid = slug_of.get(slug)
        info = all_anchors.get(cid, {}) if cid else {}
        edges = by_anchor.get(slug, [])
        old_rels = (rel_docs.get(slug) or {}).get("relations") or []
        L.append(f"## {slug} {info.get('name', '')}（CBDB {cid}）\n")
        L.append(f"新边 **{len(edges)}** 条；现有文件 {len(old_rels)} 条（含人工回填边）\n")
        new_by_to: dict[str, list] = defaultdict(list)
        for e in edges:
            new_by_to[e["to_id"]].append(e)
        old_by_to: dict[str, list] = defaultdict(list)
        for r in old_rels:
            old_by_to[str(r.get("to_id"))].append(r)
        fixes = []
        for to_id, news in new_by_to.items():
            new_types = {n["type"] for n in news}
            for o in old_by_to.get(to_id, []):
                if o.get("type") not in new_types:
                    fixes.append((to_id, o, news))
        if fixes:
            L.append("### ⚠ 方向/类型修正对照（同 to_id，旧 type ∉ 新 type）\n")
            L.append("| to_id | 旧 type | 旧 note | 新 type | 新 note | 新 direction |")
            L.append("|---|---|---|---|---|---|")
            for to_id, o, news in fixes[:40]:
                n = news[0]
                L.append(f"| {to_id} | {o.get('type')} | {o.get('note')} | {n['type']} | "
                         f"{n['note']} | {n['direction']} |")
            if len(fixes) > 40:
                L.append(f"| … | | 共 {len(fixes)} 条 | | | |")
            L.append("")
        else:
            L.append("（无同 to_id 类型冲突的旧边）\n")
        L.append("### 新边（全部）\n")
        L.append("| to_id | 姓名 | type | direction | code | note_code | note |")
        L.append("|---|---|---|---|---|---|---|")
        show = edges if not args.sample_rows else edges[:args.sample_rows]
        for e in show:
            code = e.get("kin_code", e.get("assoc_code"))
            L.append(f"| {e['to_id']} | {e['other_name']} | {e['type']} | {e['direction']} | "
                     f"{code} | {e.get('note_code', '')} | {e['note']} |")
        if len(edges) > len(show):
            L.append(f"| … | | | | | | 共 {len(edges)} 条 |")
        L.append("")
        if slug == "wang_wei":
            cui = [e for e in edges if e["other_name"].startswith("崔氏")]
            L.append("### ✅ 验收核对：王维 ↔ 崔氏\n")
            L.append(f"- 崔氏相关新边 **{len(cui)}** 条：")
            for e in cui:
                L.append(f"  - type=`{e['type']}` direction=`{e['direction']}` "
                         f"kin_code={e.get('kin_code')} note_code={e.get('note_code', e.get('kin_code'))} "
                         f"note=`{e['note']}`")
            L.append(f"- 是否出现「子」类边：{'**是（不合格）**' if any(e['type'] == '父子' for e in cui) else '否 ✅'}")
            L.append(f"- 是否出现「其他」类边：{'是（不合格）' if any(e['type'] == '其他' for e in cui) else '否 ✅'}")
            L.append(f"- note 是否含 Y：{'是（不合格）' if any('Y' in e['note'] for e in cui) else '否 ✅'}")
            L.append(f"- 旧文件中崔氏相关边（对照）：")
            for r in (rel_docs.get("wang_wei") or {}).get("relations") or []:
                if "崔氏" in (r.get("note") or ""):
                    L.append(f"  - type=`{r.get('type')}` note=`{r.get('note')}`")
            L.append("")
    (report_dir / "sample_review.md").write_text("\n".join(L), encoding="utf-8")

    dump = {}
    for slug in order:
        edges = by_anchor.get(slug, [])
        if edges:
            out = []
            for e in edges:
                item = {"to_id": e["to_id"], "type": e["type"], "note": e["note"],
                        "src": e.get("src", "cbdb")}
                if "kin_code" in e:
                    item["kin_code"] = e["kin_code"]
                else:
                    item["assoc_code"] = e["assoc_code"]
                item["direction"] = e["direction"]
                if e.get("note_code") is not None:
                    item["note_code"] = e["note_code"]
                out.append(item)
            dump[slug] = out
    (report_dir / "sample_edges.yaml").write_text(
        "# R1.2-1d 样本新边（dry-run 产物，未写入 data/relations/）\n"
        "# src=来源；kin_code/assoc_code=CBDB 原始码；direction=锚点是否为原行主体；\n"
        "# note_code=生成 note 所用码值（反向边=镜像行/配对码）\n"
        + yaml.safe_dump(dump, allow_unicode=True, sort_keys=False), encoding="utf-8")


def write_diff(report_dir, edge_records, rel_docs, local_sample: bool = False) -> None:
    by_anchor: dict[str, list] = defaultdict(list)
    for e in edge_records:
        by_anchor[e["anchor"]].append(e)
    old_total = sum(len((d or {}).get("relations") or []) for d in rel_docs.values())
    L = ["# 全量收割候选 vs 现有 data/relations（dry-run）\n"]
    L.append(f"- 本次收割候选边：**{len(edge_records)}** 条 / {len(by_anchor)} 人")
    L.append(f"- 现有 data/relations：{old_total} 条 / {len(rel_docs)} 文件")
    L.append(f"- 与现有数据 (from,to,type) 重合：{sum(1 for e in edge_records if e['in_current'])} 条")
    L.append("- ⚠ 重跑前须先做 R1.2-4b 的 `--purge-machine`（本脚本不实现），否则机器边会与现有边叠加。\n")
    L.append("## 候选边最多的锚点（top 30）\n")
    L.append("| 锚点 | 候选边 | 其中已在现有数据 | 反向边占比 |")
    L.append("|---|---|---|---|")
    for slug in sorted(by_anchor, key=lambda s: -len(by_anchor[s]))[:30]:
        es = by_anchor[slug]
        rev = sum(1 for e in es if e["direction"] == "reverse")
        L.append(f"| {slug} | {len(es)} | {sum(1 for e in es if e['in_current'])} | "
                 f"{rev / len(es) * 100:.0f}% |")
    (report_dir / "diff_vs_current.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
