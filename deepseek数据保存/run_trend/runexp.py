#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
runexp.py — dsh_TrendCore 回测实验编排器（三段：训练/验证/测试）

设计要点（都是踩过坑之后的结论）：
  * 三段严格划分，测试段只在最后跑一次：
        训练 train : 2017.04 – 2023.12
        验证 valid : 2024.01 – 2024.12
        测试 test  : 2025.01 – 2026.05   ★只在定案后跑
        留白  hold : 2026.06 – 2026.09   ★完全不用，交给用户自己验证
  * 固定入金 500 USD、固定杠杆 1:200。
  * 用 Model=2（1 分钟 OHLC）。理由：自定义品种没有真实 tick；且已证实
    任何历史区间的"tick"都是 MT5 合成，用 Model=1 只会更慢不会更真。
  * 每笔风险按净值百分比，手数由 EA 自己算 —— 所以"盈利后加仓"是自动的，
    但入金固定、不复利注入。
  * 记录 return/maxDD 这个比值（唯一有意义的性价比指标）。

用法：
  python runexp.py --phase train --set base
  python runexp.py --sweep train rv "0.010,0.015,0.020,0.025"
"""
import argparse
import itertools
import json
import os
import re
import shutil
import subprocess
import sys
import time

TERMINAL = r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"

# MT5 数据目录（报告、日志都在这里）
TERMDIR = os.path.join(os.environ.get("APPDATA", ""), "MetaQuotes", "Terminal",
                       "53785E099C927DB68A545C249CDBCE06")


def phase_years(phase, phases=None):
    """该段的年数（用于年化换算）。"""
    ph = phases or PHASES
    a, b = ph[phase]
    y0, m0, d0 = [int(x) for x in a.split(".")]
    y1, m1, d1 = [int(x) for x in b.split(".")]
    import datetime as _dt
    return max((_dt.date(y1, m1, d1) - _dt.date(y0, m0, d0)).days / 365.25, 1e-6)
TDATA = (r"C:\Users\UIC\AppData\Roaming\MetaQuotes\Terminal"
         r"\53785E099C927DB68A545C249CDBCE06")
BASE = r"D:\desktop\新量化策略\deepseek数据保存"
CFGDIR = os.path.join(BASE, "mql5", "config")
RUNDIR = os.path.join(BASE, "run_trend")
OUTDIR = os.path.join(BASE, "analysis", "out")

EXPERT = "dshtrend\\dsh_TrendCore"

# ★多套 EA 注册表：--expert 选择；每套有自己的参数基线
EXPERTS = {
    "trend":    "dshtrend\\dsh_TrendCore",
    "meanrev":  "dshtrend\\dsh_MeanRev",
    # ★比特币线子代理自建 EA（2026-09-11 编译通过 0 errors / 0 warnings）
    #   改动来自 btc-048 的实测 R 画像：唐奇安突破 + D1 宏观过滤 + Chandelier 宽跟踪 + 波动率归一化
    "btcswing": "dshtrend\\dsh_BtcSwing",
    # ★日元线子代理自建 EA（2026-09-11 编译通过，1 个 long→int 警告）
    #   区间反转 + 效率比过滤，完全移除 RV 闸门
    "jpyrev":   "dshtrend\\dsh_JPYRev",
    # ★日元滚动线子代理自建网格 EA（2026-09-12 编译 0 errors / 0 warnings）
    #   49,542 bytes / SHA256 6CC5FAC4...C473EED（与子代理报的哈希一致）
    #   篮子均价记账 + 三层硬上限 + OnTradeTransaction 反查入场腿 + InpLatencyTicks
    "jpygrid":  "dshtrend\\dsh_JPYGrid",
    # ★日元滚动线交付的【只测量不交易】探针（8,823 B / SHA256 CCD77BC0...0BEACA）
    #   用途：定案"1 tick = ? 秒"，从而判定 300ms 在 Model=2 里能否表示
    "tickclock":"dshtrend\\dsh_TickClock",
}

# dsh_BtcSwing 的参数基线（按源码默认值）
BASE_BTCSWING = {
    "InpRiskPct": "1.5", "InpUseVolNormalize": "true",
    "InpVolNormMin": "0.60", "InpVolNormMax": "1.80", "InpMaxLot": "100.0",
    "InpAllowMinLotOvershoot": "true", "InpMinLotMaxRiskPct": "3.0",
    "InpTF": "16385", "InpDonchianBars": "48",
    "InpAllowLong": "true", "InpAllowShort": "true",
    "InpUseTrendFilter": "true", "InpFilterTF": "16408", "InpFilterEMA": "50",
    "InpATRPeriod": "14", "InpSL_ATR": "2.0",
    "InpUseChandelier": "true", "InpTrail_ATR": "3.5",
    "InpTrailStart_ATR": "1.0", "InpBE_ATR": "0.0",
    "InpMaxBarsInTrade": "96", "InpTP_ATR": "0.0",
    "InpUseSessionFilter": "false", "InpTradeStartHour": "0", "InpTradeEndHour": "23",
    "InpUseDailyStop": "true", "InpDailyLossPct": "5.0",
    "InpUseDDKill": "true", "InpMaxDDPct": "25.0", "InpDDCooldownMin": "1440",
    "InpWriteAudit": "true", "InpVerboseLog": "false", "InpLatencyMs": "0", "InpLatencyTicks": "1",
    "InpFilterSlopeBars": "3", "InpFilterRequireSlope": "false",
    "InpUseEntryQuality": "false", "InpMinBarRangeATR": "1.2",
    "InpMinClosePosFrac": "0.65", "InpRequireMomConfirm": "false",
}

# 第二套（均值回归 dsh_MeanRev）的参数基线
# dsh_JPYRev 的参数基线（按源码默认值；TF 用数值枚举 M5=5, D1=16408）
BASE_JPYREV = {
    "InpRiskPct": "0.5", "InpMaxLot": "1.00", "InpUseEquityForRisk": "true",
    "InpAllowMinLotOvershoot": "true", "InpMinLotMaxRiskPct": "1.0",
    "InpTF": "5", "InpMAPeriod": "24", "InpSigmaPeriod": "48",
    "InpEntrySigma": "1.8", "InpNeedReenter": "true", "InpExitFrac": "0.25",
    "InpStopATR": "3.0", "InpMaxBarsInTrade": "12", "InpMaxAdverseATR": "2.0",
    "InpUseRangeFilter": "true", "InpMaxER": "0.35", "InpERPeriod": "24",
    "InpUseSessionFilter": "true", "InpTradeStartHour": "0", "InpTradeEndHour": "23",
    "InpNoFridayLate": "true", "InpFridayStopHour": "20",
    "InpUseDailyStop": "true", "InpDailyLossPct": "3.0",
    "InpUseDDKill": "true", "InpMaxDDPct": "20.0", "InpDDCooldownMin": "1440",
    "InpStopAfterDDLock": "false",
    "InpWriteAudit": "true", "InpVerboseLog": "false", "InpDDMinDepthPct": "2.0",
    "InpLatencyMs": "0", "InpLatencyTicks": "1",
}
BASE_MEANREV = {
    "InpRiskPct": "0.7", "InpMaxLot": "1.0", "InpUseEquityForRisk": "true",
    "InpAllowMinLotOvershoot": "true", "InpMinLotMaxRiskPct": "3.0",
    "InpTF": "30", "InpMAPeriod": "48", "InpSigmaPeriod": "96",
    "InpEntrySigma": "2.0", "InpExitSigmaFrac": "0.5", "InpStopSigma": "2.0",
    "InpMaxBarsInTrade": "48", "InpAllowLong": "true", "InpAllowShort": "true",
    "InpUseSessionFilter": "true", "InpTradeStartHour": "1", "InpTradeEndHour": "5",
    "InpNoFridayLate": "false", "InpFridayStopHour": "20",
    "InpUseDailyStop": "true", "InpDailyLossPct": "6.0",
    "InpUseDDKill": "false", "InpMaxDDPct": "25.0",
    "InpWriteAudit": "true", "InpVerboseLog": "false", "InpDDMinDepthPct": "2.0",
    "InpLatencyMs": "0", "InpLatencyTicks": "1",
}

SYMBOL = "XAUUSD_HIST"
DEPOSIT = "300"   # ★用户 2026-09-11：本金按 300（实盘金额更高则更安全）

# ★★ 2026-09-11 用户指令：只用 MT5 真实券商品种，禁止自建品种。
#    自建品种（XAUUSD_HIST / BTCUSD_HIST / JPYUSD_HIST）已从终端物理删除。
SYMBOLS = {
    "btc":   "BTCUSDm",
    "gold":  "XAUUSDm",
    "jpy":   "USDJPYm",
}

# ★BTC 三段（用户 2026-09-11 指定：验证/测试各 1 年；留白从 5 月起）
#   训练 2018.02 – 2023.12（约 6 年）
#   验证 2024 全年
#   测试 2025 全年  ← 这样 2026.01 那波大行情落在测试段（压测）
#   留白 2026.05 – 2026.09（留给你，我不碰）
# ★★ 2026-09-11 用户裁决：采用 GPT 在交流板固化的【滚动年度】分段。
#    留白（用户自己测）：2026.06.01 – 2026.09.30   ← 绝不使用
#    测试集：2025.06.01 – 2026.05.31   （★含 2026-01 那波大行情，用于压测）
#    验证集：2024.06.01 – 2025.05.31
#    训练集：品种可用历史起点 – 2024.05.31
#    —— 用户原话："你的时间是不合理的，gpt 的更加合理"。
ROLL = {
    "train": ("__FIRST__", "2024.05.31"),
    "valid": ("2024.06.01", "2025.05.31"),
    "test":  ("2025.06.01", "2026.05.31"),
    "hold":  ("2026.06.01", "2026.09.30"),
}

# 各真实品种的可用历史起点（实测；见 MQL5\Files\dshtools\specs.json）
FIRST_BAR = {
    "BTCUSDm": "2018.02.09",
    "XAUUSDm": "2014.01.14",
    "USDJPYm": "2014.01.14",
}


def phases_for(symbol):
    """按品种把 train 的 __FIRST__ 换成它真实的历史起点。"""
    first = FIRST_BAR.get(symbol, "2014.01.14")
    return {k: (first if a == "__FIRST__" else a, b) for k, (a, b) in ROLL.items()}


PHASES_BTC  = phases_for("BTCUSDm")
PHASES_GOLD = phases_for("XAUUSDm")
PHASES_JPY  = phases_for("USDJPYm")

PHASES = PHASES_GOLD   # 默认

# 基线参数（锁定基座：精度参数取设计值，不进优化空间）
BASE_PARAMS = {
    "InpRiskPct": "1.5",
    "InpMaxLot": "1.0",
    "InpTrendTF": "30",
    "InpFastEMA": "15",
    "InpSlowEMA": "60",
    "InpSlopeLookback": "4",
    "InpBreakoutBars": "30",
    "InpUseTrendConfirm": "true",
    "InpTrendConfirmBars": "3",
    "InpAllowLong": "true",
    "InpAllowShort": "true",
    "InpUseRVGate": "true",
    "InpRVWindowMinutes": "15",
    "InpRVMinPct": "0.020",
    "InpATRPeriod": "14",
    "InpSL_ATR": "2.5",
    "InpTrail_ATR": "3.0",
    "InpTrailStart_ATR": "1.0",
    "InpTP_ATR": "0.0",
    "InpExitOnCross": "true",
    "InpUseDailyStop": "true",
    "InpDailyLossPct": "3.0",
    "InpUseDDKill": "true",
    "InpMaxDDPct": "20.0",
    "InpUseSessionFilter": "true",
    "InpTradeStartHour": "8",
    "InpTradeEndHour": "21",
    "InpNoFridayLate": "true",
    "InpFridayStopHour": "18",
    "InpWriteAudit": "true",
    "InpVerboseLog": "false", "InpLatencyMs": "0", "InpLatencyTicks": "1",
}


def make_ini(tag, phase, params, symbol=None, phases=None, deposit=None, expert=None):
    sym = symbol or SYMBOL
    ph = phases or PHASES
    dep = str(deposit) if deposit else DEPOSIT
    d_from, d_to = ph[phase]
    p = dict(params)          # ★只发调用者给的参数（不再无条件套 BASE_PARAMS，
                              #   否则会把 dsh_TrendCore 的参数名发给 dsh_MeanRev）
    # ★tag 必须是 ASCII：非 ASCII 会让 MT5 的 Report=/InpRunTag= 失效（实测 2.4 秒假成功）
    tag = "".join(ch if (ch.isalnum() or ch in "-_.") else "_" for ch in str(tag))
    p["InpRunTag"] = tag
    lines = [
        "[Common]", "Login=277335900", "Server=Exness-MT5Trial5",
        "KeepPrivate=1", "NewsEnable=0", "CertInstall=0",
        "[Experts]", "AllowLiveTrading=0", "AllowDllImport=0",
        "Enabled=1", "Account=0", "Profile=0",
        "[Tester]",
        "Expert=" + (expert or EXPERT), "Symbol=" + sym, "Period=M1",
        "Model=2", "Optimization=0",
        "FromDate=" + d_from, "ToDate=" + d_to,
        "ForwardMode=0", "Deposit=" + dep, "Currency=USD",
        "Leverage=1:200", "ExecutionMode=0", "Visual=0",
        "Report=rep_" + tag, "ReplaceReport=1", "ShutdownTerminal=1",
        "[TesterInputs]",
    ]
    lines += ["%s=%s" % (k, v) for k, v in p.items()]
    path = os.path.join(CFGDIR, "run_%s.ini" % tag)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path

def read_report(name):
    """解析 MT5 HTML 报告（UTF-16LE）。"""
    p = os.path.join(TDATA, name + ".htm")
    if not os.path.isfile(p):
        return None
    with open(p, "rb") as f:
        raw = f.read()
    html = None
    for enc in ("utf-16", "utf-8-sig", "utf-8"):
        try:
            t = raw.decode(enc)
            if "<td" in t.lower():
                html = t
                break
        except (UnicodeDecodeError, UnicodeError):
            continue
    if html is None:
        return None
    tag = re.compile(r"<[^>]+>")
    cells = [" ".join(tag.sub("", m.group(1)).replace("&nbsp;", " ").split())
             for m in re.finditer(r"<td[^>]*>(.*?)</td>", html, re.S | re.I)]

    d = {}
    for i, t in enumerate(cells):
        if not t.endswith(":"):
            continue
        key = t[:-1].strip()
        if not key or key in d or key.startswith("Inp"):
            continue
        for j in range(i + 1, min(i + 4, len(cells))):
            v = cells[j]
            if v and not v.endswith(":"):
                d[key] = v
                break
    return d


def _clean_num(s):
    """★MT5 用「空格」作千分位（如 '1 620.86'）。
    必须先去掉空格（含不换行空格），否则 re.findall 会把它拆成 '1' 与 '620.86' 两个数，
    导致 eqdd 被读成 1.0、eqdd_pct 被读成 620.86 —— 本 bug 实测踩到过，会让整张表全错。"""
    return (str(s).replace(",", "").replace(" ", "")
            .replace("\xa0", "").replace("\u202f", ""))


def num(s):
    if s is None:
        return None
    s = _clean_num(s).split("(")[0]
    m = re.search(r"-?[\d.]+", s)
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def pctpair(s):
    """从 '1 620.86 (28.48%)' 取出 (绝对值, 百分比)。"""
    if not s:
        return (None, None)
    m = re.findall(r"-?[\d.]+", _clean_num(s))
    if not m:
        return (None, None)
    return (float(m[0]), float(m[1]) if len(m) > 1 else None)


def run_one(tag, phase, params, symbol=None, phases=None, deposit=None,
            expert=None, base=None):
    """base: 基线参数字典；缺省用趋势法 BASE_PARAMS；跑第二套 EA 时传它自己的基线。"""
    merged = dict(base if base is not None else BASE_PARAMS)
    merged.update(params or {})
    ini = make_ini(tag, phase, merged, symbol, phases, deposit, expert)
    t0 = time.time()
    proc = subprocess.Popen([TERMINAL, "/config:" + ini])
    proc.wait()
    el = time.time() - t0

    d = read_report("rep_" + tag)
    if d is None:
        return {"tag": tag, "phase": phase, "error": "no report"}

    net = num(d.get("Total Net Profit"))
    eqdd, eqddpct = pctpair(d.get("Equity Drawdown Maximal"))
    trades = num(d.get("Total Trades"))
    pf = num(d.get("Profit Factor"))
    exp_ = num(d.get("Expected Payoff"))
    winp = num(d.get("Profit Trades (% of total)"))
    maxwin = num(d.get("Largest profit trade"))
    maxloss = num(d.get("Largest loss trade"))
    final = num(d.get("Final Balance"))

    # 年度化：按天数折算
    _ph = phases or PHASES
    d_from, d_to = _ph[phase]
    y0, m0, dd0 = [int(x) for x in d_from.split(".")]
    y1, m1, dd1 = [int(x) for x in d_to.split(".")]
    months = (y1 - y0) * 12 + (m1 - m0) + 1
    years = months / 12.0

    r = {
        "tag": tag, "phase": phase, "elapsed": round(el, 1),
        "net": net, "final": final, "pf": pf, "trades": trades,
        "expectancy": exp_, "winpct": winp,
        "eqdd": eqdd, "eqdd_pct": eqddpct,
        "maxwin": maxwin, "maxloss": maxloss,
        "years": round(years, 2),
        "annual_pct": round(net / (float(deposit) if deposit else DEPOSIT_NUM) / years * 100, 2) if net is not None else None,
        "ret_dd": round(net / eqdd, 2) if (net and eqdd and eqdd > 0) else None,
        "params": params,
    }
    # 收集 exit_reason 归因
    audit = os.path.join(
        r"C:\Users\UIC\AppData\Roaming\MetaQuotes\Terminal\Common\Files",
        "dshtrend", tag, "trades.csv")
    by = {}
    if os.path.isfile(audit):
        with open(audit, "r", encoding="utf-8", errors="replace") as f:
            hdr = f.readline().rstrip("\n").split(",")
            try:
                ri = hdr.index("exit_reason")
                pi = hdr.index("pnl")
            except ValueError:
                ri = pi = -1
            if ri >= 0:
                for line in f:
                    c = line.rstrip("\n").split(",")
                    if len(c) <= max(ri, pi):
                        continue
                    k = c[ri]
                    try:
                        v = float(c[pi])
                    except ValueError:
                        v = 0.0
                    a = by.setdefault(k, [0, 0.0])
                    a[0] += 1
                    a[1] += v
    r["by_exit"] = {k: [v[0], round(v[1], 2)] for k, v in
                    sorted(by.items(), key=lambda x: -abs(x[1][1]))}
    return r


DEPOSIT_NUM = 300.0


def short(r):
    if "error" in r:
        return "%-22s ERROR %s" % (r["tag"], r["error"])
    return ("%-22s net=%8s pf=%5s n=%5s dd=%6s%% ann=%7s%% ret/dd=%6s"
            % (r["tag"], r["net"], r["pf"], r["trades"], r["eqdd_pct"],
               r["annual_pct"], r["ret_dd"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--expert", default="trend", choices=list(EXPERTS.keys()))
    ap.add_argument("--deposit", default=None, help="覆盖入金（默认 300）")
    ap.add_argument("--symbol", default="gold", choices=list(SYMBOLS.keys()),
                    help="标的: gold / jpy / btc（决定 Symbol 与三段日期）")
    ap.add_argument("--phase", default="train")
    ap.add_argument("--set", default="base", help="单次跑，tag 名")
    ap.add_argument("--params", default="", help="k=v,k=v 覆盖")
    ap.add_argument("--sweep", nargs=2, metavar=("PARAM", "VALUES"),
                    help="对单个参数扫一组值（训练段）")
    ap.add_argument("--grid", default="", help="JSON: {param:[v1,v2],...} 笛卡尔积")
    ap.add_argument("--gridfile", default="",
                    help="grid JSON 文件路径（避免 PowerShell 吞引号）")
    ap.add_argument("--jobs", type=int, default=1)
    args = ap.parse_args()

    expert = EXPERTS[args.expert]
    base = {"meanrev": BASE_MEANREV, "btcswing": BASE_BTCSWING, "jpyrev": BASE_JPYREV}.get(args.expert, BASE_PARAMS)
    sym = SYMBOLS[args.symbol]
    if args.symbol == "btc":
        ph = PHASES_BTC
    elif args.symbol == "jpy":
        ph = PHASES_JPY
    else:
        ph = PHASES_GOLD
    os.makedirs(RUNDIR, exist_ok=True)
    results = []

    if args.sweep:
        param, vals = args.sweep
        for v in [x.strip() for x in vals.split(",") if x.strip()]:
            tag = "%s_%s_%s" % (args.phase, param.replace("Inp", ""), v.replace(".", "p"))
            r = run_one(tag, args.phase, {param: v}, sym, ph, args.deposit, expert, base)
            results.append(r)
            print(short(r), flush=True)

    elif args.gridfile or args.grid:
        if args.gridfile:
            with open(args.gridfile, "r", encoding="utf-8-sig") as f:
                grid = json.load(f)
        else:
            grid = json.loads(args.grid)
        keys = list(grid.keys())
        combos = list(itertools.product(*[grid[k] for k in keys]))
        print("grid: %d combos" % len(combos))
        for i, combo in enumerate(combos):
            over = {k: (str(v).lower() if isinstance(v, bool) else str(v))
                    for k, v in zip(keys, combo)}
            tag = "g%03d_" % i + "_".join(
                "%s%s" % (k.replace("Inp", "")[:6], str(v).replace(".", "p"))
                for k, v in zip(keys, combo))
            r = run_one(tag, args.phase, over, sym, ph, args.deposit, expert, base)
            results.append(r)
            print("[%d/%d] %s" % (i + 1, len(combos), short(r)), flush=True)

    else:
        over = {}
        if args.params:
            for kv in args.params.split(","):
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    over[k.strip()] = v.strip()
        r = run_one(args.set, args.phase, over, sym, ph, args.deposit, expert, base)
        results.append(r)
        print(short(r))

    # 汇总落盘
    os.makedirs(OUTDIR, exist_ok=True)
    out = os.path.join(OUTDIR, "trend_results.jsonl")
    with open(out, "a", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("\nsaved -> %s" % out)

    # 简单排序表
    ok = [r for r in results if r.get("net") is not None]
    ok.sort(key=lambda r: -(r.get("ret_dd") or -999))
    print("\n%-24s %9s %7s %7s %8s %9s %8s" %
          ("TAG", "NET", "PF", "N", "DD%", "ANN%", "RET/DD"))
    for r in ok[:25]:
        print("%-24s %9s %7s %7s %8s %9s %8s" %
              (r["tag"][:24], r["net"], r["pf"], r["trades"],
               r["eqdd_pct"], r["annual_pct"], r["ret_dd"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())















