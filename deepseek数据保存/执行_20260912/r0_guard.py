#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
阶段 R0 · 编排器与登记护栏（GPT 第二批裁定 §三 R0）

必须实现（GPT 原文）：
  · 白名单仅允许 XAUUSDm/BTCUSDm/USDJPYm
  · 日期与 2026-06-01~2026-09-30 有任何重叠 → 直接拒绝
  · 每次先创建唯一 run_id 和独立目录，再启动 MT5
  · 每个目录固定保存 INI / HTML / trades / signals / tester log / 源码+EX5 哈希 / manifest
  · 报告名必须含完整 run_id；已存在则拒绝覆盖
  · 状态只追加：planned → running → done/error → execution_verified/invalid
  · 增加 dataset_role = train/valid/exposed_oos/user_holdout/forward_demo
  · 生成 data_exposure_register.md

状态双轴（GPT §0 术语表）：
  run_verification : pending / execution_verified / invalid
  strategy_stage   : exploratory / deliverable_candidate / acceptable_candidate / blocked_failed
"""
from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
OUT = os.path.join(HERE, "stage0_provenance_r3")
os.makedirs(OUT, exist_ok=True)

RUNROOT = os.path.join(HERE, "runs_r3")          # 每个 run 独立目录
REGISTRY = os.path.join(OUT, "run_registry.jsonl")
os.makedirs(RUNROOT, exist_ok=True)

# ---- 护栏常量 ----
SYMBOL_WHITELIST = {"XAUUSDm", "BTCUSDm", "USDJPYm"}
HOLDOUT_FROM, HOLDOUT_TO = dt.date(2026, 6, 1), dt.date(2026, 9, 30)
DATASET_ROLES = {"train", "valid", "exposed_oos", "user_holdout", "forward_demo"}
# 用户留白 = 2026-06-01~09-30（GPT Q4：保持原定义，不擅自顺延）
# exposed_oos = 2025-06-01~2026-05-31（GPT §1.4：历史已跑，标 exposed_oos）
EXPOSED_OOS = (dt.date(2025, 6, 1), dt.date(2026, 5, 31))


class GuardReject(Exception):
    pass


def sha256(p):
    if not p or not os.path.isfile(p):
        return ""
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest().upper()


def nd(s):
    m = re.match(r"^(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", str(s or "").strip())
    if not m:
        return None
    try:
        return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def load_registry():
    if not os.path.isfile(REGISTRY):
        return []
    out = []
    for line in io.open(REGISTRY, encoding="utf-8"):
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def append_registry(rec):
    with io.open(REGISTRY, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def classify_role(a, b):
    """按日期区间推断 dataset_role（护栏用，调用方可覆盖为 forward_demo 等）"""
    if a is None or b is None:
        return None
    if a <= HOLDOUT_TO and b >= HOLDOUT_FROM:
        return "user_holdout"
    if a <= EXPOSED_OOS[1] and b >= EXPOSED_OOS[0]:
        return "exposed_oos"
    if b <= dt.date(2024, 5, 31):
        return "train"
    if a >= dt.date(2024, 6, 1) and b <= dt.date(2025, 5, 31):
        return "valid"
    return "other"


def guard(run_id, symbol, frm, to, role, *, allow_exposed_oos=False, dry=False):
    """★核心护栏：任何一条不满足即拒绝启动"""
    reg = load_registry()
    existing = {r["run_id"] for r in reg if r.get("run_id")}

    # 1) 唯一 run_id
    if not run_id:
        raise GuardReject("未登记：run_id 为空 → 拒绝启动")
    if run_id in existing:
        raise GuardReject("重复 run_id：%s 已存在 → 拒绝启动" % run_id)
    if not re.match(r"^[A-Za-z0-9_\-]{4,64}$", run_id):
        raise GuardReject("run_id 格式非法：%s" % run_id)

    # 2) 品种白名单
    if symbol not in SYMBOL_WHITELIST:
        raise GuardReject("禁用品种：%s（白名单 %s）→ 拒绝启动"
                          % (symbol, sorted(SYMBOL_WHITELIST)))

    # 3) 日期解析
    a, b = nd(frm), nd(to)
    if a is None or b is None:
        raise GuardReject("日期缺失或无法解析：from=%s to=%s → 拒绝启动" % (frm, to))
    if b < a:
        raise GuardReject("日期倒置：%s > %s → 拒绝启动" % (a, b))

    # 4) 留白重叠（GPT Q4：硬禁止）
    if a <= HOLDOUT_TO and b >= HOLDOUT_FROM:
        raise GuardReject(
            "留白重叠：%s~%s 与用户留白 %s~%s 有交集 → 拒绝启动"
            % (a, b, HOLDOUT_FROM, HOLDOUT_TO))

    # 5) dataset_role 合法性
    if role and role not in DATASET_ROLES:
        raise GuardReject("非法 dataset_role：%s" % role)
    guess = classify_role(a, b)
    if guess == "exposed_oos" and not allow_exposed_oos:
        raise GuardReject(
            "原测试段重叠：%s~%s 落在 exposed_oos(%s~%s) → 需 allow_exposed_oos=True 才可运行"
            % (a, b, EXPOSED_OOS[0], EXPOSED_OOS[1]))

    # 6) 目录与报告名唯一（不覆盖）
    d = os.path.join(RUNROOT, run_id)
    if os.path.exists(d):
        raise GuardReject("目录已存在：%s → 拒绝覆盖" % d)
    report = os.path.join(d, "report_%s.htm" % run_id)
    if os.path.exists(report):
        raise GuardReject("报告名已存在：%s → 拒绝覆盖" % report)

    return dict(run_id=run_id, symbol=symbol, from_date=str(a), to_date=str(b),
                dataset_role=role or guess or "other", dir=d, report=report)


def register_run(g, expert_src, expert_ex5, ini_path="", notes=""):
    """登记一条 planned 记录（★先登记，再运行）"""
    rec = dict(
        run_id=g["run_id"], symbol=g["symbol"],
        **{"from": g["from_date"], "to": g["to_date"]},
        dataset_role=g["dataset_role"],
        status="planned",
        run_verification="pending",
        strategy_stage="exploratory",
        dir=g["dir"],
        expert_source_path=expert_src,
        expert_source_sha256=sha256(expert_src),
        ex5_path=expert_ex5,
        ex5_sha256=sha256(expert_ex5),
        ini_path=ini_path, ini_sha256=sha256(ini_path) if ini_path else "",
        report_path=g["report"], report_sha256="",
        trades_path="", trades_sha256="",
        signals_path="", signals_sha256="",
        tester_log_path="", tester_log_sha256="",
        created_at_local=dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        notes=notes,
    )
    os.makedirs(g["dir"], exist_ok=True)
    append_registry(rec)
    return rec


def update_status(run_id, status, **kw):
    """★只追加，不覆盖旧行"""
    reg = load_registry()
    base = None
    for r in reversed(reg):
        if r.get("run_id") == run_id:
            base = dict(r)
            break
    if base is None:
        raise GuardReject("未登记的 run_id：%s" % run_id)
    base["status"] = status
    base["updated_at_local"] = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    base.update(kw)
    append_registry(base)
    return base


# ==================== R0 的模拟测试（不启动 MT5） ====================
def selftest():
    cases = [
        ("未登记（空 run_id）", dict(run_id="", symbol="BTCUSDm", frm="2024.06.01",
                                    to="2025.05.31", role="valid"), True),
        ("重复 run_id", dict(run_id="DUP_TEST_1", symbol="BTCUSDm", frm="2024.06.01",
                             to="2025.05.31", role="valid"), True),
        ("自建品种", dict(run_id="T_SYM", symbol="XAUUSD_HIST", frm="2023.01.03",
                          to="2024.12.31", role="train"), True),
        ("留白日期", dict(run_id="T_HOLDOUT", symbol="BTCUSDm", frm="2025.01.02",
                          to="2026.06.30", role="train"), True),
        ("原测试段（未授权）", dict(run_id="T_EXPOSED", symbol="BTCUSDm", frm="2025.06.01",
                                    to="2026.05.31", role="valid"), True),
        ("非法 role", dict(run_id="T_ROLE", symbol="BTCUSDm", frm="2024.06.01",
                           to="2025.05.31", role="whatever"), True),
        ("日期倒置", dict(run_id="T_REV", symbol="BTCUSDm", frm="2025.05.31",
                          to="2024.06.01", role="valid"), True),
        # 应通过
        ("合法 train（新 id）", dict(run_id="R0_OK_TRAIN2", symbol="BTCUSDm", frm="2018.02.09",
                            to="2024.05.31", role="train"), False),
        ("目录已存在", dict(run_id="R0_PRE_EXIST", symbol="BTCUSDm", frm="2023.01.02",
                          to="2023.12.29", role="train"), True),
        ("exposed_oos 未授权", dict(run_id="T_EXP2", symbol="BTCUSDm", frm="2025.06.01",
                                   to="2025.12.31", role="exposed_oos"), True),
        ("合法 valid", dict(run_id="R0_OK_VALID", symbol="BTCUSDm", frm="2024.06.01",
                            to="2025.05.31", role="valid"), False),
        ("合法 JPY", dict(run_id="R0_OK_JPY", symbol="USDJPYm", frm="2023.01.02",
                          to="2023.12.29", role="train"), False),
    ]
    # 先放一个已存在的 run_id 用于"重复"用例
    append_registry(dict(run_id="DUP_TEST_1", symbol="BTCUSDm", status="planned",
                         run_verification="pending", strategy_stage="exploratory",
                         created_at_local=dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    append_registry(dict(run_id="R0_OK_TRAIN", symbol="BTCUSDm", status="planned",
                         run_verification="pending", strategy_stage="exploratory",
                         created_at_local=dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

    # 为"目录已存在"用例预先创建目录（验证不覆盖）
    os.makedirs(os.path.join(RUNROOT, "R0_PRE_EXIST"), exist_ok=True)

    rows = []
    for name, kw, should_reject in cases:
        try:
            guard(**kw)
            got = "通过"
            ok = not should_reject
        except GuardReject as e:
            got = "拒绝：%s" % str(e)[:60]
            ok = should_reject
        rows.append((name, "应拒绝" if should_reject else "应通过", got, "✅" if ok else "❌"))
    return rows


def data_exposure_register():
    """扫描全部 run_*.ini，登记原测试段重叠与 6–9 月暴露"""
    cfg = os.path.join(BASE, "mql5", "config")
    rows = []
    if os.path.isdir(cfg):
        for f in sorted(os.listdir(cfg)):
            if not (f.startswith("run_") and f.endswith(".ini")):
                continue
            d = io.open(os.path.join(cfg, f), encoding="utf-8-sig", errors="ignore").read()
            sym = (re.search(r"^Symbol=(.*)$", d, re.M) or [None, ""])[1].strip()
            a = nd((re.search(r"^FromDate=(.*)$", d, re.M) or [None, ""])[1])
            b = nd((re.search(r"^ToDate=(.*)$", d, re.M) or [None, ""])[1])
            exp = (re.search(r"^Expert=(.*)$", d, re.M) or [None, ""])[1].strip()
            if not (a and b):
                continue
            ov_oos = a <= EXPOSED_OOS[1] and b >= EXPOSED_OOS[0]
            ov_ho = a <= HOLDOUT_TO and b >= HOLDOUT_FROM
            if ov_oos or ov_ho:
                rows.append(dict(ini=f, symbol=sym, **{"from": str(a), "to": str(b)},
                                 expert=exp, exposed_oos=ov_oos, holdout=ov_ho))
    return rows


def main():
    print("=" * 70)
    print("阶段 R0 · 编排器与登记护栏 · 自检（不启动 MT5）")
    print("=" * 70)
    rows = selftest()
    print("\n%-24s %-8s %-62s %s" % ("用例", "期望", "实际", "判定"))
    print("-" * 100)
    for n, exp, got, ok in rows:
        print("%-24s %-8s %-62s %s" % (n, exp, got, ok))
    allok = all(r[3] == "✅" for r in rows)
    print("-" * 100)
    print("★ 自检结果：%s（%d/%d 通过）"
          % ("全部通过 ✅" if allok else "有失败 ❌",
             sum(1 for r in rows if r[3] == "✅"), len(rows)))

    exp = data_exposure_register()
    oos = [r for r in exp if r["exposed_oos"]]
    hol = [r for r in exp if r["holdout"]]
    L = []
    L.append("# Stage 0 R3 · 数据暴露登记（`data_exposure_register.md`）\n")
    L.append("依据：GPT 第二批裁定 §三 R0 第 6 条。**目的：明确区分「本轮未跑」与「项目历史已跑」。**\n")
    L.append("## 1. 三段定义\n")
    L.append("| 区间 | 名称 | 状态 |")
    L.append("|---|---|---|")
    L.append("| 各品种起点 ～ 2024-05-31 | `train` | 可用 |")
    L.append("| 2024-06-01 ～ 2025-05-31 | `valid` | 可用 |")
    L.append("| **2025-06-01 ～ 2026-05-31** | **`exposed_oos`** | **★历史已跑，不再是干净样本外** |")
    L.append("| **2026-06-01 ～ 2026-09-30** | **`user_holdout`** | **★硬禁止（用户保留）** |")
    L.append("")
    L.append("**★关键更正（GPT §1.4）**：")
    L.append("> 「本轮阶段 E 未跑」**不等于**「项目从未跑过该段」。")
    L.append("> 实测：**%d 份 INI 与 2025-06-01~2026-05-31 重叠** → 该段统一标 `exposed_oos`。" % len(oos))
    L.append("")
    L.append("## 2. 与 `exposed_oos` 重叠的 INI（%d 份）\n" % len(oos))
    L.append("| ini | 品种 | from | to | expert |")
    L.append("|---|---|---|---|---|")
    for r in oos[:60]:
        L.append("| `%s` | %s | %s | %s | %s |" % (r["ini"], r["symbol"], r["from"], r["to"], r["expert"][:42]))
    if len(oos) > 60:
        L.append("| …（其余 %d 份见 CSV） | | | | |" % (len(oos) - 60))
    L.append("")
    L.append("## 3. 与 `user_holdout`（2026-06~09）重叠的 INI（%d 份）\n" % len(hol))
    L.append("| ini | 品种 | from | to | expert |")
    L.append("|---|---|---|---|---|")
    for r in hol:
        L.append("| `%s` | %s | %s | %s | %s |" % (r["ini"], r["symbol"], r["from"], r["to"], r["expert"][:42]))
    L.append("")
    L.append("**★全部为 `eva028` 线产物**（详见 `公共部分\\约束违规记录_eva028_20260913.md`）。")
    L.append("**按 GPT Q4：保持用户原日期定义并继续硬禁止，同时登记历史暴露；不擅自顺延、不删除证据。**")
    L.append("")
    L.append("## 4. 本轮（R0 之后）的承诺\n")
    L.append("```")
    L.append("· 所有 run 必须先登记（run_registry.jsonl），未登记不启动 MT5")
    L.append("· 与 user_holdout 有任何重叠 → 编排器【直接拒绝启动】")
    L.append("· 与 exposed_oos 重叠 → 需显式 allow_exposed_oos=True，并标 dataset_role=exposed_oos")
    L.append("· 品种不在白名单 → 拒绝启动")
    L.append("· run_id 重复 / 目录已存在 / 报告名已存在 → 拒绝覆盖")
    L.append("```")
    L.append("")
    L.append("## 5. 产物\n")
    L.append("- `data_exposure_register.md`（本文件）")
    L.append("- `data_exposure.csv`（%d 行）" % len(exp))
    L.append("- `run_registry.jsonl`（登记表，只追加）")
    L.append("- `r0_guard.py`（护栏实现，含自检）")
    L.append("")

    io.open(os.path.join(OUT, "data_exposure_register.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    import csv as _csv
    with io.open(os.path.join(OUT, "data_exposure.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = _csv.DictWriter(f, fieldnames=list(exp[0].keys()))
        w.writeheader(); w.writerows(exp)

    print("\n数据暴露：exposed_oos 重叠 %d 份 / user_holdout 重叠 %d 份" % (len(oos), len(hol)))
    print("→ %s" % os.path.join(OUT, "data_exposure_register.md"))
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())



