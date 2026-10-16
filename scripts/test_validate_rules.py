#!/usr/bin/env python3
"""validate.py 新增规则的正反测试例（R2-1 配套）。

为什么是「副本上跑」而不是「造小 fixture」
------------------------------------------
真实 data/ 是唯一事实来源，规则又在**全量**数据上判「0 错误放行构建」。
若造一个小 fixture，测的是「规则能报错」，却测不出「规则在真实数据上不误报」——
而后者才是接入构建的前提。所以本脚本：

1. 把 data/ 复制成若干份临时目录：``pristine``（基准，只读）+ ``work_<i>``（工作副本）；
2. 每个用例只改某份 work 里的**一个文件**（真实文件名 + 真实字段，不用杜撰结构）；
3. 用**真 CLI**（``validate.py --data work_i``，与构建期挂的完全同一条命令）判定：
   - 反例（bad）：命中预期错误文案 **且** 退出码 1（= 构建会被拦住）；
   - 正例（good）：退出码 0 **且** 结论为 0 错误（= 不误伤合法数据）；
   - 警告例（warn）：命中预期警告文案 **且** 退出码 0（警告不该挡构建）；
4. 用例结束立刻从 ``pristine`` 复原该文件——真实 ``data/`` 全程只读。

用例引用的具体人/边若在数据里消失/改名，脚本会**显式报错**（而不是静默跳过），
提示同步更新用例，避免测试悄悄失效。

关于并行
--------
本机沙箱里单次 validate 约 5s（读 1000+ YAML 的开销占大头），28 个用例串行要 2 分半。
因此默认 4 路并行：每路独占一份工作副本（互不干扰），各自按序跑分配到的用例。

用法
----
    python3 scripts/test_validate_rules.py            # 跑全部用例（默认 4 路并行）
    python3 scripts/test_validate_rules.py -j 1       # 串行（排查用）
    python3 scripts/test_validate_rules.py -k role    # 只跑名称/规则号含该子串的用例
    python3 scripts/test_validate_rules.py -v         # 顺带打印 validate 原始输出
    python3 scripts/test_validate_rules.py --keep     # 保留临时目录（排查用）

退出码: 0 = 全部通过; 1 = 有用例失败; 2 = 环境错误（data/ 缺失、夹具失效等）
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
REAL_DATA = ROOT / "data"
VALIDATE = ROOT / "scripts" / "validate.py"

# ---------------------------------------------------------------- 夹具锚点
# 用例只碰这几个文件的**已存在**条目（新增条目也只加在既有文件里）
REL_REVERSE = "relations/fei_hong.yaml"          # 反向边：岳父：濮炎（reverse + note_code）
REL_FWD_EXT = "relations/an_de_yu.yaml"          # 正向边 + to_id 为外部人物
REL_FWD_INT = "relations/an_shou_liang.yaml"     # 正向边 + to_id 为站内人物
PERSON = "persons/an_shou_liang.yaml"            # 极简卡（bio_short 为 null，适合测档案状态互斥）

REV_TO = "cbdb:118796"        # fei_hong 的反向边目标
EXT_TO = "cbdb:39402"         # an_de_yu 的正向边目标（外部人物）
INT_TO = "an_de_yu"           # an_shou_liang 的正向边目标（站内人物）
BACK_TO = "an_shou_liang"     # an_de_yu 反向指回站内人物（用于构造 A↔B 互指）
GHOST_TO = "cbdb:99999999"    # 不存在的 CBDB 编号（须被豁免）


# ---------------------------------------------------------------- YAML 改写工具

def load_yaml(path: Path) -> dict:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise SystemExit(f"[env] 夹具失效：{path} 顶层不是对象")
    return doc


def save_yaml(path: Path, doc: dict) -> None:
    path.write_text(
        yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )


def edge_of(doc: dict, to_id: str, relpath: str) -> dict:
    """按 to_id 取关系边；取不到即夹具失效（数据变了要更新用例，不许静默跳过）。"""
    for r in doc.get("relations") or []:
        if r.get("to_id") == to_id:
            return r
    raise SystemExit(f"[env] 夹具失效：{relpath} 里找不到 to_id={to_id} 的边")


def rel_mutate(anchor_to: str, relpath: str, **changes):
    """生成「改某条关系边字段」的改写函数；值为 None 表示删除该字段。

    首参名避开 ``to_id``，好让用例能直接把 ``to_id=...`` 当字段改写传进来。
    """
    def mutate(path: Path) -> None:
        doc = load_yaml(path)
        r = edge_of(doc, anchor_to, relpath)
        for k, v in changes.items():
            if v is None:
                r.pop(k, None)
            else:
                r[k] = v
        save_yaml(path, doc)
    return mutate


def rel_inject(relpath: str, **edge):
    """生成「往既有关系文件追加一条边」的改写函数。"""
    def mutate(path: Path) -> None:
        doc = load_yaml(path)
        doc.setdefault("relations", []).append(dict(edge))
        save_yaml(path, doc)
    return mutate


def person_mutate(**changes):
    def mutate(path: Path) -> None:
        doc = load_yaml(path)
        for k, v in changes.items():
            if v is None:
                doc.pop(k, None)
            else:
                doc[k] = v
        save_yaml(path, doc)
    return mutate


# ---------------------------------------------------------------- 用例定义

@dataclass
class Case:
    rule: str            # 规则编号（R2-1 子项）
    name: str            # 用例名
    kind: str            # bad / good / warn
    relpath: str         # 被改的文件（相对 data/）
    mutate: object       # (Path) -> None
    expect: str = ""     # 期望命中/不应命中的文案片段
    desc: str = ""


CASES: list[Case] = [
    # ---- R2-1-A：机器边 direction 合法值 ----
    Case("R-DIR-A1", "机器边缺 direction", "bad", REL_FWD_EXT,
         rel_mutate(EXT_TO, REL_FWD_EXT, direction=None),
         "缺/非法 direction", "direction 是 note 视角的唯一凭据，丢了就无法复算"),
    Case("R-DIR-A2", "机器边 direction 非法枚举", "bad", REL_FWD_EXT,
         rel_mutate(EXT_TO, REL_FWD_EXT, direction="backward"),
         "缺/非法 direction", "只认 forward/reverse"),
    Case("R-DIR-A3", "机器边方向字段合法（正例）", "good", REL_FWD_EXT,
         rel_mutate(EXT_TO, REL_FWD_EXT, direction="reverse", note_code=76, kin_code=181),
         "", "合法的反向边：码已翻转、留痕齐备"),

    # ---- R2-1-B：kin_code / assoc_code 恰有其一 ----
    Case("R-DIR-B1", "机器边两码皆缺", "bad", REL_FWD_EXT,
         rel_mutate(EXT_TO, REL_FWD_EXT, kin_code=None),
         "须恰带 kin_code/assoc_code 之一", "缺码则无法溯源 CBDB 行"),
    Case("R-DIR-B2", "机器边两码并存", "bad", REL_FWD_EXT,
         rel_mutate(EXT_TO, REL_FWD_EXT, assoc_code=1),
         "须恰带 kin_code/assoc_code 之一", "亲属码与社会关系码互斥"),

    # ---- R2-1-C：reverse 必须留痕且码已翻转 ----
    Case("R-DIR-C1", "反向边无 note_code", "bad", REL_REVERSE,
         rel_mutate(REV_TO, REL_REVERSE, note_code=None),
         "direction=reverse 却无 note_code", "反向边必须记录生成 note 所用码"),
    Case("R-DIR-C2", "反向边 note_code 等于原始码", "bad", REL_REVERSE,
         rel_mutate(REV_TO, REL_REVERSE, note_code=181),
         "码未翻转", "码没变 = note 仍是原行视角，方向修复失效"),
    Case("R-DIR-C3", "合法反向边（正例）", "good", REL_REVERSE,
         rel_mutate(REV_TO, REL_REVERSE, note_code=76),
         "", "留痕且码不同于原始码"),

    # ---- R2-1-D：forward 不得留痕 ----
    Case("R-DIR-D1", "正向边带 note_code", "bad", REL_FWD_EXT,
         rel_mutate(EXT_TO, REL_FWD_EXT, note_code=99),
         "forward 不应带 note_code", "正向视角即原码，留痕会误导为「已翻转」"),

    # ---- R2-1-E：note 定式（尾标 + 可选始年）----
    Case("R-DIR-E1", "note 缺（CBDB）尾标", "bad", REL_FWD_EXT,
         rel_mutate(EXT_TO, REL_FWD_EXT, note="父：安重榮"),
         "须以「（CBDB…）」结尾", "尾标是页面识别机器边的依据"),
    Case("R-DIR-E2", "note 带始年仍然合法（正例）", "good", REL_FWD_EXT,
         rel_mutate(EXT_TO, REL_FWD_EXT, note="父：安重榮（CBDB 外部人物），始年 1050"),
         "", "尾标后可跟「，始年 NNNN」"),

    # ---- R2-1-F：note 视角与 to_id 一致 ----
    Case("R-DIR-F1", "外部人物 note 未内联姓名", "bad", REL_FWD_EXT,
         rel_mutate(EXT_TO, REL_FWD_EXT, note="父（CBDB 外部人物）"),
         "须内联姓名", "外部人物无档案，note 是唯一的姓名来源"),
    Case("R-DIR-F2", "外部人物 note 未标外部", "bad", REL_FWD_EXT,
         rel_mutate(EXT_TO, REL_FWD_EXT, note="父：安重榮（CBDB）"),
         "须标「CBDB 外部人物」", "不标则与站内人物边混淆"),
    Case("R-DIR-F3", "站内人物 note 内联姓名", "bad", REL_FWD_INT,
         rel_mutate(INT_TO, REL_FWD_INT, note="父：安德裕（CBDB）"),
         "不得内联姓名", "站内姓名由页面渲染，内联会「标签=姓名」重复"),
    Case("R-DIR-F4", "站内人物 note 标外部", "bad", REL_FWD_INT,
         rel_mutate(INT_TO, REL_FWD_INT, note="父（CBDB 外部人物）"),
         "不得标「CBDB 外部人物」", "站内人物有档案，标外部会误导为无档案"),
    Case("R-DIR-F5", "站内人物 note 定式（正例）", "good", REL_FWD_INT,
         rel_mutate(INT_TO, REL_FWD_INT, note="父（CBDB）"),
         "", "站内视角：只写称谓，不内联姓名"),

    # ---- R2-1-G：Y 占位符不得落盘 ----
    Case("R-DIR-G1", "note 残留 Y 占位符", "bad", REL_FWD_EXT,
         rel_mutate(EXT_TO, REL_FWD_EXT, note="為Y作墓誌銘：安重榮（CBDB 外部人物）"),
         "残留 Y 占位符", "收割期须替换为「對方」"),
    Case("R-DIR-G2", "Y 已替换为「對方」（正例）", "good", REL_FWD_EXT,
         rel_mutate(EXT_TO, REL_FWD_EXT, note="為對方作墓誌銘：安重榮（CBDB 外部人物）"),
         "", "线上口径"),

    # ---- R2-1-H：方向抽查（亲属称谓互指 -> 警告）----
    Case("R-DIR-H1", "A↔B 机器边共用亲属称谓", "warn", REL_FWD_EXT,
         rel_inject(REL_FWD_EXT, to_id=BACK_TO, type="父子", note="父（CBDB）",
                    src="cbdb", kin_code=75, direction="forward"),
         "共用亲属称谓", "称谓天生不对称，同词互指 = 方向疑未翻转（警告不挡构建）"),
    Case("R-DIR-H2", "对称标签互指不告警（正例）", "good", REL_FWD_EXT,
         rel_inject(REL_FWD_EXT, to_id=BACK_TO, type="父子", note="子（CBDB）",
                    src="cbdb", kin_code=63, direction="forward"),
         "共用亲属称谓", "标签不同（父 / 子）= 视角正确"),

    # ---- R1.4：role 合法值 ----
    Case("R-ID-1a", "role 非法值", "bad", PERSON,
         person_mutate(role="bangyan"), "role 非法", "只认 zhuangyuan/tanhua/de_facto"),
    Case("R-ID-1b", "role = tanhua（正例）", "good", PERSON,
         person_mutate(role="tanhua"), "", "名录特例允许"),

    # ---- R1.1：identity_status 合法值 ----
    Case("R-ID-2a", "identity_status 非法值", "bad", PERSON,
         person_mutate(identity_status="maybe"), "identity_status 非法", "只认 confirmed/suspect"),
    Case("R-ID-2b", "identity_status = suspect（正例）", "good", PERSON,
         person_mutate(identity_status="suspect"), "", "身份存疑是合法状态"),

    # ---- R2-1-I：档案状态与身份结论互斥 ----
    Case("R-ID-3a", "verified_absent 与 identity_status 并存", "bad", PERSON,
         person_mutate(verified_absent=True, identity_status="suspect"),
         "互斥", "真「查无记载」者无从确认身份匹配"),
    Case("R-ID-3b", "verified_absent 单独成立（正例）", "good", PERSON,
         person_mutate(verified_absent=True, bio_short=None), "", "合法：认定阙如、无传"),

    # ---- 既有规则回归：to_id 存在性 + cbdb: 豁免 ----
    Case("R-TOID-1", "to_id 不存在", "bad", REL_FWD_INT,
         rel_mutate(INT_TO, REL_FWD_INT, to_id="bu_cun_zai_de_ren"),
         "不存在", "站内关系必须指向真实人物卡"),
    Case("R-TOID-2", "to_id 为不存在的 cbdb: 编号（正例）", "good", REL_FWD_INT,
         rel_mutate(INT_TO, REL_FWD_INT, to_id=GHOST_TO,
                    note="父：虛構外部人物（CBDB 外部人物）"),
         "", "cbdb: 前缀外部人物无站内档案，须豁免存在性"),
]


# ---------------------------------------------------------------- 运行

@dataclass
class Result:
    case: Case
    ok: bool
    detail: str
    output: str = field(default="", repr=False)


def run_validate(data_root: Path) -> tuple[int, str]:
    """跑真 CLI —— 与构建期 pythonStep 挂的是同一条命令。"""
    proc = subprocess.run(
        [sys.executable, str(VALIDATE), "--data", str(data_root)],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    return proc.returncode, proc.stdout + proc.stderr


def error_count(output: str) -> int | None:
    m = re.search(r"结论: (\d+) 错误 / (\d+) 警告", output)
    return int(m.group(1)) if m else None


def check(case: Case, rc: int, out: str) -> tuple[bool, str]:
    n_err = error_count(out)
    if n_err is None:
        return False, "validate 未输出结论行（可能崩溃）"
    if case.kind == "bad":
        if case.expect not in out:
            return False, f"未命中预期错误「{case.expect}」（错误数 {n_err}）"
        if rc != 1:
            return False, f"命中错误但退出码为 {rc}（应为 1，否则拦不住构建）"
        return True, f"命中「{case.expect}」且退出码 1"
    if case.kind == "warn":
        if case.expect not in out:
            return False, f"未命中预期警告「{case.expect}」"
        if rc != 0:
            return False, f"警告不该拦构建，但退出码为 {rc}"
        return True, f"命中「{case.expect}」且退出码 0（不挡构建）"
    # good：不得出现任何错误
    if rc != 0 or n_err != 0:
        return False, f"正例不该报错，但退出码 {rc} / {n_err} 错误"
    if case.expect and case.expect in out:
        return False, f"正例命中了不该出现的「{case.expect}」"
    return True, "0 错误（合法数据未被误伤）"


def run_tree(pristine: Path, work: Path, cases: list[Case]) -> list[Result]:
    """在一份独占的工作副本上按序跑分配到的用例（每例跑完立刻复原）。"""
    out: list[Result] = []
    for case in cases:
        src, dst = pristine / case.relpath, work / case.relpath
        shutil.copy2(src, dst)          # 复原
        case.mutate(dst)                # 注入
        rc, o = run_validate(work)
        ok, detail = check(case, rc, o)
        out.append(Result(case, ok, detail, o))
        shutil.copy2(src, dst)          # 复原
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="validate.py 新增规则的正反测试例")
    ap.add_argument("-j", "--jobs", type=int, default=4,
                    help="并行路数（每路独占一份数据副本；默认 4）")
    ap.add_argument("-v", "--verbose", action="store_true", help="打印 validate 原始输出")
    ap.add_argument("-k", "--filter", default="", help="只跑用例名/规则号含该子串的用例")
    ap.add_argument("--keep", action="store_true", help="保留临时目录")
    args = ap.parse_args(argv)

    if not REAL_DATA.is_dir():
        print(f"[env] 找不到 data/：{REAL_DATA}", file=sys.stderr)
        return 2

    selected = [c for c in CASES
                if not args.filter or args.filter in c.name or args.filter in c.rule]
    if not selected:
        print(f"[env] 没有匹配「{args.filter}」的用例", file=sys.stderr)
        return 2

    trees = max(1, min(args.jobs, len(selected)))
    tmp = Path(tempfile.mkdtemp(prefix="zyp_validate_test_"))
    pristine = tmp / "pristine"
    works = [tmp / f"work_{i}" for i in range(trees)]
    try:
        shutil.copytree(REAL_DATA, pristine)
        for w in works:
            shutil.copytree(REAL_DATA, w)

        # 基线 1：真实数据必须 0 错误（一切误报都会在这里先暴露）
        # 基线 2：真 CLI 的 --data 解析 + 退出码 0（构建期用的就是这条）
        cli_rc, cli_out = run_validate(works[0])
        cli_ok = cli_rc == 0 and error_count(cli_out) == 0
        print("=" * 72)
        print("validate 规则正反测试例")
        print("=" * 72)
        print(f"数据副本 : {tmp}（{trees} 份工作副本，并行 {trees} 路）")
        print(f"用例总数 : {len(selected)}")
        print(f"CLI 基线 : {'通过（真实数据 0 错误，退出码 0）' if cli_ok else f'失败（rc={cli_rc}）'}")
        print("-" * 72)
        if not cli_ok:
            print(cli_out)
            return 2

        # 用例按路数轮转分配到各工作副本（同文件多例天然串行于同一路内）
        buckets: list[list[Case]] = [[] for _ in range(trees)]
        for i, case in enumerate(selected):
            buckets[i % trees].append(case)

        results: list[Result] = []
        with ThreadPoolExecutor(max_workers=trees) as ex:
            futs = [ex.submit(run_tree, pristine, works[i], buckets[i])
                    for i in range(trees) if buckets[i]]
            for fut in futs:
                results.extend(fut.result())
        order = {c.name: i for i, c in enumerate(selected)}
        results.sort(key=lambda r: order[r.case.name])

        for r in results:
            mark = "PASS" if r.ok else "FAIL"
            print(f"[{mark}] {r.case.rule:<9} {r.case.kind:<4} {r.case.name}")
            print(f"        期望: {r.case.desc}")
            print(f"        实测: {r.detail}")
            if args.verbose or not r.ok:
                print("-" * 72)
                print(r.output)
                print("-" * 72)

        bad = [r for r in results if not r.ok]
        n_bad = sum(1 for r in results if r.case.kind == "bad")
        n_good = sum(1 for r in results if r.case.kind == "good")
        n_warn = sum(1 for r in results if r.case.kind == "warn")
        print("=" * 72)
        print(f"结果: {len(results) - len(bad)}/{len(results)} 通过"
              f"（反例 {n_bad} / 正例 {n_good} / 警告例 {n_warn}）")
        for r in bad:
            print(f"  [FAIL] {r.case.name}: {r.detail}")
        print("=" * 72)
        return 1 if bad else 0
    finally:
        if args.keep:
            print(f"[info] 临时目录保留：{tmp}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
