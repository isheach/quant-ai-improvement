#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
analyze_runs.py — 汇总 run/<exp>/ 下的回测报告与成交流水，输出对比表。

判定指标（本项目定义）：
  * 净利 / 最大回撤  (ret_dd)  ← 唯一真正有意义的性价比比值
  * 最大回撤占本金 % (dd_pct)  ← 必须 ≤ 30~40%（用户口径）
  * 月均交易数                  ← 过密 = churn，点差吃死
  * PF / 期望值 / 胜率
  * exit_reason 归因            ← 铁律三：机制必须真的触发过
用法：
  python analyze_runs.py [exp_id ...]
"""
import glob
import json
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parse_report import parse, num   # noqa: E402

BASE = r"D:\desktop\新量化策略\deepseek数据保存"
RUN_DIR = os.path.join(BASE, "run")

DEPOSIT = 500.0

# 报告字段 -> 短名
F = {
    "Total Net Profit": "net",
    "Profit Factor": "pf",
    "Expected Payoff": "payoff",
    "Total Trades": "trades",
    "Profit Trades (% of total)": "winpct",
    "Largest profit trade": "maxwin",
    "Largest loss trade": "maxloss",
    "Equity Drawdown Maximal": "eqdd",
    "Equity Drawdown Relative": "eqddr",
    "Balance Drawdown Maximal": "baldd",
    "Recovery Factor": "rf",
    "Sharpe Ratio": "sharpe",
    "Bars": "bars",
    "Ticks": "ticks",
}


def pct_of_num(s):
    """'15.23 (2.99%)' -> (15.23, 2.99)"""
    if not s:
        return (None, None)
    m = re.findall(r"-?[\d.]+", s.replace(",", ""))
    if not m:
        return (None, None)
    a = float(m[0])
    b = float(m[1]) if len(m) > 1 else None
    return (a, b)


def load_trades(exp):
    p = os.path.join(RUN_DIR, exp, "audit", "eva_trade_events.csv")
    if not os.path.isfile(p):
        return []
    rows = []
    with open(p, "r", encoding="utf-8", errors="replace") as f:
        hdr = f.readline().rstrip("\n").split(",")
        idx = {h: i for i, h in enumerate(hdr)}
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            parts = line.split(",")
            if len(parts) < len(hdr):
                continue
            try:
                rows.append({
                    "exit_reason": parts[idx["exit_reason"]],
                    "entry_reason": parts[idx["entry_reason"]],
                    "net_pnl": float(parts[idx["net_pnl"]] or 0),
                    "profit": float(parts[idx["profit"]] or 0),
                    "holding": float(parts[idx["holding_seconds"]] or 0),
                    "entry_time": parts[idx["entry_time"]],
                })
            except (ValueError, IndexError):
                continue
    return rows


def month_count(rows):
    ms = set()
    for r in rows:
        t = r["entry_time"]
        if len(t) >= 7:
            ms.add(t[:7])
    return len(ms) or 1


def summarize(exp):
    rep = os.path.join(RUN_DIR, exp, "rep_%s.htm" % exp)
    if not os.path.isfile(rep):
        return None
    d = parse(rep)
    row = {"exp_id": exp}
    for k, short in F.items():
        row[short] = d.get(k)
    eqdd_val, eqdd_pct = pct_of_num(d.get("Equity Drawdown Maximal"))
    row["eqdd_val"] = eqdd_val
    row["eqdd_pct"] = eqdd_pct

    net = num(row.get("net")) or 0.0
    row["ret_dd"] = (net / eqdd_val) if (eqdd_val and eqdd_val > 0) else None

    tr = load_trades(exp)
    row["n_tr"] = len(tr)
    months = month_count(tr)
    row["months"] = months
    row["trades_per_month"] = round(len(tr) / months, 1) if months else None

    by = defaultdict(lambda: [0, 0.0])
    for r in tr:
        b = by[r["exit_reason"]]
        b[0] += 1
        b[1] += r["net_pnl"]
    row["by_exit"] = {k: (v[0], round(v[1], 2)) for k, v in
                      sorted(by.items(), key=lambda kv: -abs(kv[1][1]))}
    row["audit_net"] = round(sum(r["net_pnl"] for r in tr), 2)
    return row


def main():
    exps = sys.argv[1:]
    if not exps:
        exps = sorted(os.path.basename(os.path.dirname(p))
                      for p in glob.glob(os.path.join(RUN_DIR, "*", "rep_*.htm")))
    rows = [r for r in (summarize(e) for e in exps) if r]

    print("=" * 132)
    print("回测对比  ·  品种 XAUUSD_HIST（42 个月真实 XAUUSDm M1 导入，合约规格同 XAUUSDm）")
    print("  区间 2023.01.03–2024.12.31（训练，2 年）  入金 $500  固定 0.01 手  Model=2(1分钟OHLC)  点差 200 点固定")
    print("=" * 132)
    hdr = ("%-16s %10s %8s %7s %7s %8s %9s %8s %9s %8s" %
           ("EXP", "净利$", "PF", "笔数", "月均", "权益回撤$", "回撤%", "净利/回撤", "最大赢", "最大亏"))
    print(hdr)
    print("-" * 132)
    for r in rows:
        def g(k):
            v = r.get(k)
            return v if v not in (None, "") else "-"
        print("%-16s %10s %8s %7s %7s %8s %9s %8s %9s %8s" % (
            r["exp_id"], g("net"), g("pf"), g("trades"),
            r.get("trades_per_month", "-"),
            (("%.2f" % r["eqdd_val"]) if r["eqdd_val"] is not None else "-"),
            (("%.2f%%" % r["eqdd_pct"]) if r["eqdd_pct"] is not None else "-"),
            (("%.2f" % r["ret_dd"]) if r["ret_dd"] is not None else "-"),
            g("maxwin"), g("maxloss")))

    print()
    print("=" * 132)
    print("exit_reason 归因（铁律三：机制必须真的触发过）")
    print("=" * 132)
    for r in rows:
        print("\n[%s]  审计成交 %d 笔（报告 %s 笔），跨越 %d 个月" %
              (r["exp_id"], r["n_tr"], r.get("trades", "-"), r.get("months", "-")))
        for k, (n, pnl) in r["by_exit"].items():
            print("    %-34s %6d 笔   %10.2f" % (k, n, pnl))

    # 落盘
    out = os.path.join(BASE, "analysis", "out", "batch1_summary.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)
    print("\nsaved -> %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
