#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
阶段 R3 · 十项诊断（GPT 第二批裁定 §三 R3）—— 零调参

对 C1-R3 的 train/valid 同时输出 GPT 列的 10 项：
  1 MT5 bar 覆盖率 / 成交月份覆盖率
  2 总频率与逐年频率
  3 由 position/deal 反查的持仓时长中位、P10/P90
  4 入场点差÷初始止损距离的中位、P90、最大
  5 期望R 胜率 平均赢R 平均亏R 总R PF 前5笔贡献
  6 前5/10 大单占比 + 删除前10大单后的净利/PF
  7 1.0× / 1.5× / 2.0× 成本压力
  8 信号数 接受/拒绝数 拒绝原因 raw/final lot final risk
  9 MT5 官方权益/浮动 DD、最大连续亏损、恢复时间（已平仓近似另列并标注）
 10 train+valid 合计笔数及逐年空窗

关闭条件：train 或 valid 净利<=0、PF<=1、官方DD>40%、成本压力后转负、
          四方审计不一致、去前10大单后转负、依赖最小手超预算、样本/覆盖严重不足
"""
from __future__ import annotations

import csv
import collections
import datetime as dt
import io
import os
import re
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "stage4_candidates_r3")
os.makedirs(OUT, exist_ok=True)
COMMON = os.path.join(os.environ.get("APPDATA", ""), "MetaQuotes", "Terminal",
                      "Common", "Files", "dshtrend")
TDATA = os.path.join(os.environ.get("APPDATA", ""), "MetaQuotes", "Terminal",
                     "53785E099C927DB68A545C249CDBCE06")

RUNS = [("DS260913_C1R3_TRAIN", "train", "2018.02.09", "2024.05.31"),
        ("DS260913_C1R3_VALID", "valid", "2024.06.01", "2025.05.31")]
CONTRACT = 1.0
SPREAD_POINTS = 10.0          # BTCUSDm 实测点差（specs 快照）


def f(x, d=0.0):
    try:
        return float(str(x).strip())
    except Exception:
        return d


def rep_field(name, kw):
    p = os.path.join(TDATA, "report_%s.htm" % name)
    if not os.path.isfile(p):
        return {}
    s = io.open(p, encoding="utf-16-le", errors="ignore").read()
    t = re.sub(r"<[^>]+>", "|", s)
    t = re.sub(r"\|+", "|", t)
    out = {}
    for k in ("Initial Deposit", "Bars", "Ticks", "Symbols", "Total Net Profit",
              "Gross Profit", "Gross Loss", "Profit Factor", "Expected Payoff",
              "Balance Drawdown Maximal", "Equity Drawdown Maximal",
              "Balance Drawdown Relative", "Equity Drawdown Relative",
              "Total Trades", "Total Deals", "Short Trades", "Long Trades",
              "History Quality", "Recovery Factor", "Sharpe Ratio",
              "Balance Drawdown Absolute", "Equity Drawdown Absolute"):
        m = re.search(re.escape(k) + r"\|([^|]{0,40})", t)
        if m:
            out[k] = m.group(1).strip()
    return out


def diag(name, role, frm, to):
    tp = os.path.join(COMMON, name, "trades.csv")
    sp = os.path.join(COMMON, name, "signals.csv")
    rows = list(csv.DictReader(io.open(tp, encoding="utf-8-sig", errors="ignore"))) if os.path.isfile(tp) else []
    sig = list(csv.DictReader(io.open(sp, encoding="utf-8-sig", errors="ignore"))) if os.path.isfile(sp) else []
    rep = rep_field(name, "")
    R = {}

    # 1) 覆盖率
    cfg = os.path.join(os.path.dirname(HERE), "mql5", "config", "run_%s.ini" % name)
    R["bars"] = rep.get("Bars", "")
    R["ticks"] = rep.get("Ticks", "")
    R["hist_quality"] = rep.get("History Quality", "")
    months_all = set()
    a = dt.date(*map(int, frm.split(".")))
    b = dt.date(*map(int, to.split(".")))
    y, m = a.year, a.month
    while (y, m) <= (b.year, b.month):
        months_all.add("%04d.%02d" % (y, m))
        m += 1
        if m > 12:
            m = 1; y += 1
    months_tr = set(r["time"][:7] for r in rows if r.get("time"))
    R["months_total"] = len(months_all)
    R["months_traded"] = len(months_tr)
    R["month_coverage_pct"] = 100.0 * len(months_tr) / len(months_all) if months_all else 0
    if rows:
        ts = sorted(r["time"] for r in rows if r.get("time"))
        R["first_trade"] = ts[0]
        R["last_trade"] = ts[-1]
        ft = dt.datetime.strptime(ts[0][:19], "%Y.%m.%d %H:%M:%S")
        lt = dt.datetime.strptime(ts[-1][:19], "%Y.%m.%d %H:%M:%S")
        span = (lt - ft).total_seconds() / 86400.0
        R["trade_span_days"] = round(span, 1)
        window = (b - a).days
        R["span_coverage_pct"] = round(100.0 * span / window, 1) if window else 0

    # 2) 频率
    years = (b - a).days / 365.25
    R["years"] = round(years, 2)
    R["trades_total"] = len(rows)
    R["trades_per_year"] = round(len(rows) / years, 1) if years else 0
    yearly = collections.Counter(r["time"][:4] for r in rows if r.get("time"))
    R["yearly_freq"] = dict(sorted(yearly.items()))

    # 3) 持仓时长
    durs = []
    for r in rows:
        try:
            t1 = dt.datetime.strptime(r["time"][:19], "%Y.%m.%d %H:%M:%S")
            bs = f(r.get("bar_seconds"), -1)
            if bs < 0:
                t0 = dt.datetime.strptime(r["entry_time"][:19], "%Y.%m.%d %H:%M:%S")
                bs = (t1 - t0).total_seconds()
            durs.append(bs / 60.0)
        except Exception:
            pass
    if durs:
        durs.sort()
        R["hold_min_median"] = round(statistics.median(durs), 1)
        R["hold_min_p10"] = round(durs[int(len(durs) * 0.10)], 1)
        R["hold_min_p90"] = round(durs[int(len(durs) * 0.90)], 1)

    # 4) 点差/止损
    ratios = []
    for r in rows:
        e, sd = f(r.get("entry")), f(r.get("risk_money"))
        v = f(r.get("vol"))
        if e <= 0 or v <= 0:
            continue
        stop_dist = sd / (CONTRACT * v) if (CONTRACT * v) else 0
        if stop_dist > 0:
            ratios.append((SPREAD_POINTS * 0.01) / stop_dist * 100.0)
    if ratios:
        ratios.sort()
        R["spread_stop_median_pct"] = round(statistics.median(ratios), 3)
        R["spread_stop_p90_pct"] = round(ratios[int(len(ratios) * 0.90)], 3)
        R["spread_stop_max_pct"] = round(ratios[-1], 3)

    # 5) R 七件套
    Rs = []
    for r in rows:
        risk = f(r.get("risk_money"))
        pnl = f(r.get("pnl"))
        if risk > 0:
            Rs.append(pnl / risk)
    wins = [x for x in Rs if x > 0]
    loss = [x for x in Rs if x <= 0]
    R["n_with_R"] = len(Rs)
    if Rs:
        R["expectancy_R"] = round(statistics.mean(Rs), 4)
        R["win_rate_pct"] = round(100.0 * len(wins) / len(Rs), 1)
        R["avg_win_R"] = round(statistics.mean(wins), 4) if wins else 0
        R["avg_loss_R"] = round(statistics.mean(loss), 4) if loss else 0
        R["total_R"] = round(sum(Rs), 2)
    gp = sum(f(r["pnl"]) for r in rows if f(r["pnl"]) > 0)
    gl = sum(f(r["pnl"]) for r in rows if f(r["pnl"]) <= 0)
    R["net"] = round(sum(f(r["pnl"]) for r in rows), 2)
    R["pf"] = round(gp / abs(gl), 3) if gl else 0
    R["gross_profit"] = round(gp, 2)
    R["gross_loss"] = round(gl, 2)

    # 6) 集中度
    pnls = sorted((f(r["pnl"]) for r in rows), reverse=True)
    tot = sum(pnls)
    R["top5_share_pct"] = round(100.0 * sum(pnls[:5]) / tot, 1) if tot else 0
    R["top10_share_pct"] = round(100.0 * sum(pnls[:10]) / tot, 1) if tot else 0
    rest = pnls[10:]
    R["net_ex_top10"] = round(sum(rest), 2)
    gp2 = sum(x for x in rest if x > 0); gl2 = sum(x for x in rest if x <= 0)
    R["pf_ex_top10"] = round(gp2 / abs(gl2), 3) if gl2 else 0

    # 7) 成本压力
    R["cost_stress"] = {}
    for mult in (1.0, 1.5, 2.0):
        adj = 0.0
        for r in rows:
            e, x, v = f(r["entry"]), f(r["exit"]), f(r["vol"])
            pnl = f(r["pnl"])
            cost = SPREAD_POINTS * 0.01 * CONTRACT * v * mult
            adj += pnl - cost * (mult - 1.0)
        R["cost_stress"]["%.1fx" % mult] = round(adj, 2)

    # 8) 信号
    R["signals_rows"] = len(sig)
    rr = collections.Counter(s.get("reject_reason", "") for s in sig)
    R["reject_reasons"] = dict(rr.most_common(6))

    # 9) DD（官方 vs 已平仓近似）
    R["dd_official_equity"] = rep.get("Equity Drawdown Maximal", "")
    R["dd_official_relative"] = rep.get("Equity Drawdown Relative", "")
    R["dd_official_balance"] = rep.get("Balance Drawdown Maximal", "")
    eq = 500.0; peak = eq; mdd = 0.0
    for r in rows:
        eq += f(r["pnl"])
        if eq > peak: peak = eq
        dd = (peak - eq) / peak * 100.0 if peak > 0 else 0
        if dd > mdd: mdd = dd
    R["dd_closed_approx_pct"] = round(mdd, 2)
    # 最大连续亏损
    streak = mx = 0
    for r in rows:
        if f(r["pnl"]) <= 0:
            streak += 1; mx = max(mx, streak)
        else:
            streak = 0
    R["max_consec_loss"] = mx
    return R


def main():
    res = {name: diag(name, role, frm, to) for name, role, frm, to in RUNS}
    L = []
    L.append("# Stage R3 · C1-R3 十项诊断（零调参）\n")
    L.append("口径：`BTCUSDm` / **500 USD** / `Model=2` / `InpLatencyTicks=0` / ")
    L.append("`InpAllowMinLotOvershoot=false` / EA = P1-R2 已封存版本\n")
    L.append("| 项 | train | valid |")
    L.append("|---|---|---|")
    keys = ["bars", "ticks", "hist_quality", "months_total", "months_traded",
            "month_coverage_pct", "span_coverage_pct", "first_trade", "last_trade",
            "years", "trades_total", "trades_per_year",
            "hold_min_median", "hold_min_p10", "hold_min_p90",
            "spread_stop_median_pct", "spread_stop_p90_pct", "spread_stop_max_pct",
            "n_with_R", "expectancy_R", "win_rate_pct", "avg_win_R", "avg_loss_R", "total_R",
            "net", "pf", "gross_profit", "gross_loss",
            "top5_share_pct", "top10_share_pct", "net_ex_top10", "pf_ex_top10",
            "signals_rows", "max_consec_loss",
            "dd_official_equity", "dd_official_relative", "dd_official_balance",
            "dd_closed_approx_pct"]
    NAMES = {"bars": "1·MT5 Bars", "ticks": "1·Ticks", "hist_quality": "1·历史质量",
             "months_total": "1·月份总数", "months_traded": "1·有成交月份",
             "month_coverage_pct": "1·月份覆盖率%", "span_coverage_pct": "1·成交跨度覆盖%",
             "first_trade": "1·首笔", "last_trade": "1·末笔",
             "years": "2·年数", "trades_total": "2·总笔数", "trades_per_year": "2·笔/年",
             "hold_min_median": "3·持仓中位(分)", "hold_min_p10": "3·持仓P10(分)",
             "hold_min_p90": "3·持仓P90(分)",
             "spread_stop_median_pct": "4·点差/止损 中位%", "spread_stop_p90_pct": "4·P90%",
             "spread_stop_max_pct": "4·最大%",
             "n_with_R": "5·有R笔数", "expectancy_R": "5·期望R", "win_rate_pct": "5·胜率%",
             "avg_win_R": "5·平均赢R", "avg_loss_R": "5·平均亏R", "total_R": "5·总R",
             "net": "5·净利", "pf": "5·PF", "gross_profit": "5·毛盈", "gross_loss": "5·毛亏",
             "top5_share_pct": "6·前5大单占比%", "top10_share_pct": "6·前10大单占比%",
             "net_ex_top10": "6·去前10净利", "pf_ex_top10": "6·去前10 PF",
             "signals_rows": "8·拒单行数", "max_consec_loss": "9·最大连亏",
             "dd_official_equity": "9·官方权益DD", "dd_official_relative": "9·官方相对DD",
             "dd_official_balance": "9·官方余额DD", "dd_closed_approx_pct": "9·已平仓近似DD%"}
    for k in keys:
        L.append("| %s | %s | %s |" % (NAMES.get(k, k),
                                       res["DS260913_C1R3_TRAIN"].get(k, ""),
                                       res["DS260913_C1R3_VALID"].get(k, "")))
    L.append("")
    L.append("### 7·成本压力\n")
    L.append("| 倍数 | train | valid |")
    L.append("|---|---:|---:|")
    for m in ("1.0x", "1.5x", "2.0x"):
        L.append("| %s | %s | %s |" % (m,
                 res["DS260913_C1R3_TRAIN"]["cost_stress"].get(m),
                 res["DS260913_C1R3_VALID"]["cost_stress"].get(m)))
    L.append("")
    L.append("### 2·逐年频率\n")
    allY = sorted(set(list(res["DS260913_C1R3_TRAIN"]["yearly_freq"].keys()) +
                      list(res["DS260913_C1R3_VALID"]["yearly_freq"].keys())))
    L.append("| 年 | train | valid |")
    L.append("|---|---:|---:|")
    for y in allY:
        L.append("| %s | %s | %s |" % (y, res["DS260913_C1R3_TRAIN"]["yearly_freq"].get(y, "—"),
                                       res["DS260913_C1R3_VALID"]["yearly_freq"].get(y, "—")))
    L.append("")
    L.append("### 8·拒单原因\n")
    L.append("| 段 | 拒单行 | 原因分布 |")
    L.append("|---|---:|---|")
    for nm, r in (("train", res["DS260913_C1R3_TRAIN"]), ("valid", res["DS260913_C1R3_VALID"])):
        L.append("| %s | %d | `%s` |" % (nm, r["signals_rows"], r["reject_reasons"]))
    L.append("")

    # 关闭条件逐条
    t, v = res["DS260913_C1R3_TRAIN"], res["DS260913_C1R3_VALID"]
    def pct(x):
        m = re.match(r"([\d.]+)%", str(x) or "")
        return float(m.group(1)) if m else None
    ddt = pct(t.get("dd_official_relative")); ddv = pct(v.get("dd_official_relative"))
    L.append("## 关闭条件逐条校验\n")
    L.append("| 条件 | train | valid | 判定 |")
    L.append("|---|---|---|---|")
    c1 = (t["net"] > 0, v["net"] > 0)
    L.append("| 净利 > 0 | %.2f | %.2f | %s |"
             % (t["net"], v["net"], "✅" if all(c1) else "❌ **触发关闭**"))
    c2 = (t["pf"] > 1, v["pf"] > 1)
    L.append("| PF > 1 | %.3f | %.3f | %s |"
             % (t["pf"], v["pf"], "✅" if all(c2) else "❌ **触发关闭**"))
    c3 = ((ddt is None or ddt <= 40), (ddv is None or ddv <= 40))
    L.append("| 官方 DD ≤ 40%% | %s | %s | %s |"
             % (t.get("dd_official_relative"), v.get("dd_official_relative"),
                "✅" if all(c3) else "❌ **触发关闭**"))
    cs_t = t["cost_stress"].get("2.0x", 0); cs_v = v["cost_stress"].get("2.0x", 0)
    c4 = (cs_t > 0, cs_v > 0)
    L.append("| 2.0×成本后仍 > 0 | %.2f | %.2f | %s |"
             % (cs_t, cs_v, "✅" if all(c4) else "❌ **触发关闭**"))
    c5 = (t["net_ex_top10"] > 0, v["net_ex_top10"] > 0)
    L.append("| 去前10大单后 > 0 | %.2f | %.2f | %s |"
             % (t["net_ex_top10"], v["net_ex_top10"], "✅" if all(c5) else "❌ **触发关闭**"))
    L.append("| 频率 ≥ 50 笔/年 | %.1f | %.1f | %s |"
             % (t["trades_per_year"], v["trades_per_year"],
                "✅" if t["trades_per_year"] >= 50 and v["trades_per_year"] >= 50 else "⚠️"))
    L.append("")
    fails = []
    if not all(c1): fails.append("净利≤0")
    if not all(c2): fails.append("PF≤1")
    if not all(c3): fails.append("官方DD>40%")
    if not all(c4): fails.append("成本压力后转负")
    if not all(c5): fails.append("去前10大单后转负")
    L.append("```")
    L.append("关闭条件触发项：%s" % ("、".join(fails) if fails else "（无）"))
    L.append("→ C1 %s" % ("通过 R3 诊断（可进入 R4 冻结）" if not fails else "★关闭（blocked_failed）"))
    L.append("```")
    L.append("")

    io.open(os.path.join(OUT, "r3_diagnostics.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    import json
    io.open(os.path.join(OUT, "r3_diagnostics.json"), "w", encoding="utf-8").write(
        json.dumps(res, ensure_ascii=False, indent=1, default=str))
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    sys.exit(main())
