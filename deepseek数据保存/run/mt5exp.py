#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
mt5exp.py — DeepSeek 新量化策略 · MT5 实验编排器

职责：
  1. 把旧项目的 .set（UTF-16LE，格式 name=value||start||step||stop||Y/N）
     转成 MT5 可注入的参数表。
  2. 由「锁定基座 + 单变量覆盖」生成一个实验配置（铁律：单变量 + 可反事实）。
  3. 生成 [Tester] 段含 [TesterInputs] 的 ini，无头启动终端跑回测。
  4. 收集审计 CSV（trade_events）与 HTML 报告，落到 run/<exp_id>/。

关键机制：MT5 的 /config ini 支持 [TesterInputs] 段逐项覆盖 EA 的 input，
          不需要人去点 "Load .set"。

用法：
  python mt5exp.py --list
  python mt5exp.py --run base_locked base_locked_valid
  python mt5exp.py --group sens        # 跑一组
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime

# ---------------------------------------------------------------- 路径常量
TERMINAL_EXE = r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"
TERM_DATA = (r"C:\Users\UIC\AppData\Roaming\MetaQuotes\Terminal"
             r"\53785E099C927DB68A545C249CDBCE06")
COMMON_FILES = r"C:\Users\UIC\AppData\Roaming\MetaQuotes\Terminal\Common\Files"

BASE = r"D:\desktop\新量化策略\deepseek数据保存"
RUN_DIR = os.path.join(BASE, "run")
CFG_DIR = os.path.join(BASE, "mql5", "config")

LEGACY_SET = (r"D:\desktop\新量化策略\旧量化策略\36代数据"
              r"\eva028_STAGE1_PACKAGE_v2\eva028_24.3_stage1_full.set")

EXPERT_REL = "eva028\\eva028_VolumetricPulseGrid_CoreRiskV1"

SYMBOL = "XAUUSD_HIST"          # 42 个月真实 XAUUSDm M1 导入的自定义品种
TRAIN_FROM, TRAIN_TO = "2023.01.03", "2024.12.31"
VALID_FROM, VALID_TO = "2025.01.02", "2026.06.30"
SMOKE_FROM, SMOKE_TO = "2023.01.03", "2023.02.03"
DEPOSIT = "500"

# ---------------------------------------------------------------- 锁定基座
# ★铁律二：精度参数永不进优化空间。
# 这 8 个值取「设计默认」，而不是 stage1_full.set 里被优化器压到边界的值。
# 旧项目 6 次翻车的唯一原因就是这个；2026-09-10 实测再次印证（见 MEMORY.md）。
LOCKED_BASE = {
    "InpTrendBreakoutBars": "30",
    "InpTrendConfirmBars": "3",
    "InpTrendMinRVRatio": "0.020",
    "InpMinADX": "25",
    "InpMinEMASepATR": "0.5",
    "InpVolGateEnterLowPct": "0.020",
    "InpVolGateExitLowPct": "0.026",
    "InpVolGateConfirmBars": "30",
}


# ---------------------------------------------------------------- .set 解析
def load_legacy_set(path):
    with open(path, "rb") as f:
        raw = f.read()
    txt = raw.decode("utf-16-le", errors="replace")
    params, order = {}, []
    for line in txt.splitlines():
        line = line.strip()
        if not line or line.startswith(";"):
            continue
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", line)
        if not m:
            continue
        name, rest = m.group(1), m.group(2)
        params[name] = rest.split("||")[0]
        order.append(name)
    return params, order


# ---------------------------------------------------------------- 实验构造
def E(period, over=None, note="", group="misc", raw=False, audit=False):
    """raw=True → 用 stage1_full 原样（不套锁定基座），用于复现旧项目口径。"""
    o = {} if raw else dict(LOCKED_BASE)
    if over:
        o.update(over)
    return dict(period=period, over=o, note=note, group=group, audit=audit)


def _s(param, value, note=None, group="sens"):
    return E("train", {param: value},
             note or "敏感度：%s=%s" % (param, value), group=group)


EXPERIMENTS = {
    # ================= 冒烟 =================
    "smoke": E("smoke", {}, "冒烟：验证注入链路 + 交易 + 审计落盘", "smoke", raw=True),

    # ================= 批次 1：旧项目 4 次提出、从未跑过的基线实验 =================
    "b1_baseline": E("train", {}, "stage1_full 原样（对照基座，含被优化过的精度参数）",
                     "batch1", raw=True),
    "b1a_pure_grid": E("train", {"InpEnableStateMachine": "false"},
                       "纯网格：关状态机（含砍单/禁逆势/趋势单）", "batch1", raw=True),
    "b1b_pure_trend": E("train", {"InpEnableGrid": "false"},
                        "纯趋势：关网格", "batch1", raw=True),
    "b1c_cut_on": E("train", {"InpCloseOppositeGridOnTrend": "true"},
                    "反事实：基线 + 打开砍逆势网格", "batch1", raw=True),
    "b0_norisk": E("train", {"InpEnableStage1Risk": "false"},
                   "关掉全部阶段1硬风控，看策略本体", "batch1", raw=True),

    # ================= ★主基座：锁定精度参数 =================
    "base_locked": E("train", {}, "★锁定基座（训练 2023-2024）", "base"),
    "base_locked_valid": E("valid", {}, "★锁定基座（验证 2025-2026，冻结）", "base"),

    # ================= 批次 3：网格基距扫描（纯网格模式，隔离网格本体）=================
    "g_pg_z1000": E("train", {"InpEnableStateMachine": "false",
                              "InpGridZ": "1000", "InpMinGridZ": "500"},
                    "纯网格 基距1000/地板500", "grid", raw=True),
    "g_pg_z2000": E("train", {"InpEnableStateMachine": "false",
                              "InpGridZ": "2000", "InpMinGridZ": "1000"},
                    "纯网格 基距2000/地板1000", "grid", raw=True),
    "g_pg_z3000": E("train", {"InpEnableStateMachine": "false",
                              "InpGridZ": "3000", "InpMinGridZ": "1500"},
                    "纯网格 基距3000/地板1500", "grid", raw=True),
    "g_pg_z5000": E("train", {"InpEnableStateMachine": "false",
                              "InpGridZ": "5000", "InpMinGridZ": "2500"},
                    "纯网格 基距5000/地板2500", "grid", raw=True),
    "g_pg_z7000": E("train", {"InpEnableStateMachine": "false",
                              "InpGridZ": "7000", "InpMinGridZ": "2000"},
                    "纯网格 基距7000/地板2000（=EA 设计默认）", "grid", raw=True),
    "g_pg_z10000": E("train", {"InpEnableStateMachine": "false",
                               "InpGridZ": "10000", "InpMinGridZ": "5000"},
                     "纯网格 基距10000/地板5000", "grid", raw=True),
    "g_full_z7000": E("train", {"InpGridZ": "7000", "InpMinGridZ": "2000"},
                      "完整策略 基距7000/地板2000（=EA 设计默认）", "grid", raw=True),
    "g_full_z5000": E("train", {"InpGridZ": "5000", "InpMinGridZ": "2500"},
                      "完整策略 基距5000/地板2500", "grid", raw=True),

    # ================= 批次 2：整篮止损标定（往紧里测）=================
    "b2_basket10": E("train", {"InpMaxGridBasketLossMoney": "10",
                               "InpEnableDailyLossStop": "false",
                               "InpEnableStrategyKillSwitch": "false"},
                     "整篮止损 $10（关日损/永久锁以隔离）", "batch2", raw=True),
    "b2_basket20": E("train", {"InpMaxGridBasketLossMoney": "20",
                               "InpEnableDailyLossStop": "false",
                               "InpEnableStrategyKillSwitch": "false"},
                     "整篮止损 $20", "batch2", raw=True),
    "b2_basket40": E("train", {"InpMaxGridBasketLossMoney": "40",
                               "InpEnableDailyLossStop": "false",
                               "InpEnableStrategyKillSwitch": "false"},
                     "整篮止损 $40", "batch2", raw=True),

    # ================= 批次 4：趋势层形式改造 =================
    "t_tp15": E("train", {"InpTrendTP_ATR_Mult": "1.5"}, "趋势单加 ATR 止盈 1.5", "trend", raw=True),
    "t_tp20": E("train", {"InpTrendTP_ATR_Mult": "2.0"}, "趋势单加 ATR 止盈 2.0", "trend", raw=True),
    "t_notrendexit": E("train", {"InpTrendCloseOnStateExit": "false"},
                       "趋势单不因状态退出而平仓", "trend", raw=True),
    "t_cut_on": E("train", {"InpCloseOppositeGridOnTrend": "true"},
                  "打开砍逆势网格（旧默认 false）", "trend", raw=True),

    # ================= ★批次 5：回撤预算（用户口径 30~40%）=================
    "d_k25": E("train", {"InpMaxStrategyDrawdownPct": "25"}, "永久锁放宽到 25%", "dd"),
    "d_k40": E("train", {"InpMaxStrategyDrawdownPct": "40"}, "永久锁放宽到 40%", "dd"),
    "d_koff": E("train", {"InpEnableStrategyKillSwitch": "false"}, "关永久锁（看裸回撤）", "dd"),
    "d_nodaily": E("train", {"InpEnableDailyLossStop": "false"}, "关日损", "dd"),
    "d_k25_valid": E("valid", {"InpMaxStrategyDrawdownPct": "25"},
                     "验证：永久锁 25%", "dd"),
    "d_koff_valid": E("valid", {"InpEnableStrategyKillSwitch": "false"},
                      "验证：关永久锁", "dd"),

    # ================= ★批次 6：鲁棒性敏感度扫描（不是寻优！）=================
    # 判据：真实 edge 应在参数附近平滑变化；偏离一格就归零 = 过拟合。
    "s_bo20": _s("InpTrendBreakoutBars", "20"),
    "s_bo45": _s("InpTrendBreakoutBars", "45"),
    "s_bo60": _s("InpTrendBreakoutBars", "60"),
    "s_rv15": _s("InpTrendMinRVRatio", "0.015"),
    "s_rv25": _s("InpTrendMinRVRatio", "0.025"),
    "s_confirm1": _s("InpTrendConfirmBars", "1"),
    "s_confirm5": _s("InpTrendConfirmBars", "5"),
    "s_fast10": _s("InpTrendFastEMAPeriod", "10"),
    "s_fast30": _s("InpTrendFastEMAPeriod", "30"),
    "s_slow40": _s("InpTrendSlowEMAPeriod", "40"),
    "s_slow100": _s("InpTrendSlowEMAPeriod", "100"),
    "s_sl25": _s("InpTrendSL_ATR_Mult", "2.5"),
    "s_sl50": _s("InpTrendSL_ATR_Mult", "5.0"),
    "s_trail20": _s("InpTrendTrail_ATR_Mult", "2.0"),
    "s_trail45": _s("InpTrendTrail_ATR_Mult", "4.5"),
    "s_gateoff": _s("InpUseVolGateForTrendSide", "false", "关掉 Vol-Gate（看闸门贡献）"),
    "s_gridon": _s("InpEnableGrid", "false", "关掉网格（看网格对锁定基座的贡献）"),

    # ================= ★归因：上涨窗口里趋势跟踪的可信度检验 =================
    # 2026 年金价从 ~2600 单边走强到 ~5600，纯做多也能赚。
    # 必须有对照组，否则无法区分「趋势逻辑有效」与「牛市 beta」。
    "att_valid_gateoff": E("valid", {"InpUseVolGateForTrendSide": "false"},
                           "验证期关 Vol-Gate（闸门是不是在帮倒忙）", "attr"),
    "att_valid_trendoff": E("valid", {"InpEnableStateMachine": "false",
                                      "InpEnableGrid": "false"},
                            "验证期全关（对照：什么都不做）", "attr"),
    "att_valid_confirm1": E("valid", {"InpTrendConfirmBars": "1"},
                            "验证期确认根数=1（更高频趋势）", "attr"),
}


# ---------------------------------------------------------------- 构建与运行
def dates_for(period):
    return {"train": (TRAIN_FROM, TRAIN_TO),
            "valid": (VALID_FROM, VALID_TO),
            "smoke": (SMOKE_FROM, SMOKE_TO)}[period]


def build_params(exp_id):
    exp = EXPERIMENTS[exp_id]
    params, order = load_legacy_set(LEGACY_SET)
    for k, v in exp["over"].items():
        if k not in params:
            print("  !! WARNING: %s 不在基线 .set 里" % k)
        params[k] = v
    params.update({
        "InpParamSetId": exp_id,
        "InpRunTag": exp_id,
        "InpLotSize": "0.01",
        "InpUseDynamicLot": "false",
        "InpAuditUseCommonFile": "true",
        "InpEnableTradeAudit": "true",
        "InpAuditDecisions": "true" if exp.get("audit") else "false",
        "InpEnableTesterLog": "true",
        "InpEnableStateMachineLog": "true",
    })
    return params, order


def make_ini(exp_id, params, order, d_from, d_to, report_name):
    os.makedirs(CFG_DIR, exist_ok=True)
    ini = os.path.join(CFG_DIR, "run_%s.ini" % exp_id)
    lines = [
        "; auto-generated by mt5exp.py — do not edit by hand",
        "[Common]", "Login=277335900", "Server=Exness-MT5Trial5",
        "KeepPrivate=1", "NewsEnable=0", "CertInstall=0",
        "[Experts]", "AllowLiveTrading=0", "AllowDllImport=0",
        "Enabled=1", "Account=0", "Profile=0",
        "[Tester]",
        "Expert=" + EXPERT_REL,
        "Symbol=" + SYMBOL,
        "Period=M1",
        "Model=2",                 # 1 分钟 OHLC（自定义品种无真实 tick）
        "Optimization=0",
        "FromDate=" + d_from, "ToDate=" + d_to,
        "ForwardMode=0", "Deposit=" + DEPOSIT, "Currency=USD",
        "Leverage=1:200", "ExecutionMode=0", "Visual=0",
        "Report=" + report_name, "ReplaceReport=1", "ShutdownTerminal=1",
        "[TesterInputs]",
    ]
    lines += ["%s=%s" % (n, params[n]) for n in order if n in params]
    with open(ini, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return ini


def run_experiment(exp_id):
    exp = EXPERIMENTS[exp_id]
    d_from, d_to = dates_for(exp["period"])
    params, order = build_params(exp_id)
    report_name = "rep_" + exp_id
    ini = make_ini(exp_id, params, order, d_from, d_to, report_name)

    outdir = os.path.join(RUN_DIR, exp_id)
    os.makedirs(outdir, exist_ok=True)

    print("[%s] %s .. %s" % (exp_id, d_from, d_to))
    t0 = time.time()
    proc = subprocess.Popen([TERMINAL_EXE, "/config:" + ini])
    proc.wait()
    el = time.time() - t0

    src_audit = os.path.join(COMMON_FILES, "eva_audit", exp_id)
    dst_audit = os.path.join(outdir, "audit")
    if os.path.isdir(src_audit):
        shutil.rmtree(dst_audit, ignore_errors=True)
        shutil.copytree(src_audit, dst_audit)

    for cand in (os.path.join(TERM_DATA, report_name + ".htm"),):
        if os.path.isfile(cand):
            shutil.copy2(cand, os.path.join(outdir, os.path.basename(cand)))

    today = datetime.now().strftime("%Y%m%d")
    tlog = os.path.join(TERM_DATA, "logs", today + ".log")
    if os.path.isfile(tlog):
        with open(tlog, "r", encoding="utf-16-le", errors="replace") as f:
            tail = f.readlines()[-300:]
        with open(os.path.join(outdir, "terminal_tail.log"), "w",
                  encoding="utf-8") as f:
            f.writelines(tail)

    print("[%s] done %.1fs" % (exp_id, el))
    return exp_id


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--run", nargs="+")
    ap.add_argument("--group", nargs="+")
    args = ap.parse_args()

    if args.run:
        ids = args.run
    elif args.group:
        ids = [k for k, v in EXPERIMENTS.items() if v["group"] in args.group]
    else:
        ids = []

    if args.list or not ids:
        print("%-20s %-7s %-8s %s" % ("EXP_ID", "PERIOD", "GROUP", "NOTE"))
        print("-" * 110)
        for k, v in EXPERIMENTS.items():
            print("%-20s %-7s %-8s %s" % (k, v["period"], v["group"], v["note"]))
        return 0

    for eid in ids:
        if eid not in EXPERIMENTS:
            print("unknown experiment: %s" % eid)
            continue
        run_experiment(eid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
