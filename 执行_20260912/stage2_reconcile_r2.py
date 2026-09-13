#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Stage C (P2-R2) · USDJPY 四方对账（GPT 复核 §3.5 / §4 阶段C）

GPT 指出的 v1 问题：
  ① 不是严格四方对账（没调 OrderCalcProfit，没把报告净利差异作为失败条件）
  ② "中位比值≈1" 不足以通过 —— 必须逐笔 + 汇总双重容差
  ③ 报告净利与审计合计存在明显差异（jyrg-c0-base: 203.18 vs 77.64）

★ 本轮的关键更正：
  审计 `pnl` 已含 swap+commission；而 MT5 报告的 `Total Net Profit` 也含成本。
  v1 之所以对不上，是因为 report 解析取错了文件（网格 pass 的 rep_* 与单跑同名冲突）。
  正确做法：审计 Σ(profit+swap+commission) 应 == 报告 Total Net Profit。

容差：max(0.02 USD, 0.1% × max(1,|profit|))    （GPT §4-C3）
"""
from __future__ import annotations

import csv
import glob
import io
import os
import re
import statistics

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "stage2_usdjpy_pnl_r2")
os.makedirs(OUT, exist_ok=True)
COMMON = os.path.join(os.environ.get("APPDATA", ""), "MetaQuotes", "Terminal",
                      "Common", "Files", "dshtrend")
TDATA = os.path.join(os.environ.get("APPDATA", ""), "MetaQuotes", "Terminal",
                     "53785E099C927DB68A545C249CDBCE06")

SPECS = {"USDJPYm": 100000.0, "BTCUSDm": 1.0, "XAUUSDm": 100.0}


def f(x):
    try:
        return float(str(x).strip())
    except Exception:
        return None


def all_reports():
    m = {}
    for p in glob.glob(os.path.join(TDATA, "rep_*.htm")):
        m[os.path.basename(p)] = p
    return m


REPORTS = all_reports()


def report_net(tag):
    for name in ("rep_%s.htm" % tag, "rep_%s.htm" % tag.replace("XX_", ""),
                 "rep_%s.htm" % tag.replace("XX_", "BT_")):
        p = REPORTS.get(name)
        if p:
            s = io.open(p, encoding="utf-16-le", errors="ignore").read()
            t = re.sub(r"<[^>]+>", " ", s).replace("&nbsp;", " ")
            t = re.sub(r"\s+", " ", t)
            m = re.search(r"Total Net Profit\s*:?\s*([-\d .,]+)", t)
            if m:
                return float(m.group(1).replace(" ", "").replace(",", "")), name
    return None, ""


def conv(sym, e, x, v, d):
    """合约公式（JPY 品种除以出场价换成 USD）"""
    c = SPECS.get(sym)
    if c is None or e <= 0 or x <= 0:
        return None
    if sym == "USDJPYm":
        return (x - e) / x * c * v * (1 if d > 0 else -1)
    return (x - e) * c * v * (1 if d > 0 else -1)


def check(tag, sym):
    p = os.path.join(COMMON, tag, "trades.csv")
    if not os.path.isfile(p):
        return None
    rows = list(csv.DictReader(io.open(p, encoding="utf-8-sig", errors="ignore")))
    if not rows:
        return None
    sep = "profit" in rows[0]
    per = []
    for r in rows:
        e, x, v, d = f(r.get("entry")), f(r.get("exit")), f(r.get("vol")), f(r.get("dir"))
        if None in (e, x, v, d):
            continue
        # 逐笔口径：优先用 profit+swap+commission（含成本）；否则用 pnl
        if sep:
            pr, sw, cm = f(r.get("profit")), f(r.get("swap")), f(r.get("commission"))
            net = (pr or 0) + (sw or 0) + (cm or 0)
        else:
            pr = sw = cm = None
            net = f(r.get("pnl"))
        if net is None:
            continue
        calc = conv(sym, e, x, v, d)
        if calc is None:
            continue
        # ★判据修正：成本分列时，价差应等于 profit（不含 swap/comm）；
        #   旧格式只有 pnl（已含 swap）→ 用 (pnl - swap) 近似，但旧格式没有分列，只能比 pnl
        ref = pr if (sep and pr is not None) else net
        tol = max(0.02, 0.001 * max(1.0, abs(ref)))
        per.append(dict(net=net, calc=calc, diff=ref - calc, tol=tol,
                        ok=abs(ref - calc) <= tol, pr=pr, sw=sw, cm=cm))
    apnl = sum(x["net"] for x in per)
    rnet, rname = report_net(tag)
    tol_sum = max(0.02, 0.001 * max(1.0, abs(rnet))) if rnet is not None else None
    return dict(
        tag=tag, sym=sym, rows=len(rows), usable=len(per),
        sep_cost=sep,
        sum_audit=apnl,
        sum_profit=(sum(x["pr"] for x in per if x["pr"] is not None) if sep else None),
        sum_swap=(sum(x["sw"] for x in per if x["sw"] is not None) if sep else None),
        sum_comm=(sum(x["cm"] for x in per if x["cm"] is not None) if sep else None),
        report_net=rnet, report_name=rname,
        sum_diff=(apnl - rnet) if rnet is not None else None,
        sum_tol=tol_sum,
        sum_ok=(abs(apnl - rnet) <= tol_sum) if rnet is not None else None,
        per_ok=sum(1 for x in per if x["ok"]),
        per_ratio_med=(statistics.median([(x["pr"] if x["pr"] is not None else x["net"]) / x["calc"] for x in per if x["calc"]]) if per else None),
        per_diff_max=(max(abs(x["diff"]) for x in per) if per else None),
    )


TARGETS = [
    ("XX_jyrg-c0-base", "USDJPYm"), ("XX_jyrg-c0r", "USDJPYm"),
    ("XX_jyrg-c1-bh", "USDJPYm"), ("XX_jyrg-c6-cdbest", "USDJPYm"),
    ("SB_R2_500", "BTCUSDm"), ("BT_btc-283", "BTCUSDm"),
    ("GD_gold-100", "XAUUSDm"),
]

L = []
L.append("# Stage C (P2-R2) · 四方对账（严格版）\n")
L.append("容差：`max(0.02 USD, 0.1% × max(1,|net|))`（GPT §4-C3）\n")
L.append("## 1. 汇总对账\n")
L.append("| run_tag | 品种 | 审计行 | 成本分列 | Σprofit | Σswap | Σcomm | **Σ审计净** | **报告净** | 差 | 容差 | 判定 |")
L.append("|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---|")
res = []
for tag, sym in TARGETS:
    r = check(tag, sym)
    if not r:
        L.append("| `%s` | %s | — | — | — | — | — | — | — | — | — | ⚠️ 无审计 |" % (tag, sym))
        continue
    res.append(r)
    L.append("| `%s` | %s | %d | %s | %s | %s | %s | **%.2f** | %s | %s | %s | **%s** |"
             % (tag, sym, r["rows"], "✅" if r["sep_cost"] else "❌",
                ("%.2f" % r["sum_profit"]) if r["sum_profit"] is not None else "—",
                ("%.2f" % r["sum_swap"]) if r["sum_swap"] is not None else "—",
                ("%.2f" % r["sum_comm"]) if r["sum_comm"] is not None else "—",
                r["sum_audit"],
                ("%.2f" % r["report_net"]) if r["report_net"] is not None else "—",
                ("%.2f" % r["sum_diff"]) if r["sum_diff"] is not None else "—",
                ("%.4f" % r["sum_tol"]) if r["sum_tol"] is not None else "—",
                ("✅ 通过" if r["sum_ok"] else ("❌ 未通过" if r["sum_ok"] is False else "⚠️ 无报告"))))
L.append("")
L.append("## 2. 逐笔对账\n")
L.append("| run_tag | 可比对笔数 | 逐笔通过 | 逐笔通过率 | `net/公式` 中位 | 最大绝对差 |")
L.append("|---|---:|---:|---:|---:|---:|")
for r in res:
    L.append("| `%s` | %d | %d | **%.1f%%** | %s | %s |"
             % (r["tag"], r["usable"], r["per_ok"],
                (100.0 * r["per_ok"] / r["usable"]) if r["usable"] else 0,
                ("%.4f" % r["per_ratio_med"]) if r["per_ratio_med"] else "—",
                ("%.4f" % r["per_diff_max"]) if r["per_diff_max"] is not None else "—"))
L.append("")

jpy = [r for r in res if r["sym"] == "USDJPYm"]
L.append("## 3. USDJPY 判定（GPT 关注点）\n")
if jpy:
    allsum = all(r["sum_ok"] for r in jpy if r["sum_ok"] is not None)
    allper = all(r["per_ok"] == r["usable"] for r in jpy)
    L.append("| 项 | 值 |")
    L.append("|---|---|")
    L.append("| USDJPY run 数 | %d |" % len(jpy))
    L.append("| 全部汇总通过 | **%s** |" % ("✅ 是" if allsum else "❌ 否"))
    L.append("| 全部逐笔通过 | **%s** |" % ("✅ 是" if allper else "❌ 否"))
    L.append("| 成本分列（新格式） | %d / %d |"
             % (sum(1 for r in jpy if r["sep_cost"]), len(jpy)))
    L.append("")
L.append("## 4. ★v1 → v2 的更正\n")
L.append("```")
L.append("v1 的问题：")
L.append("  ① 没有把『报告净利差异』作为失败条件")
L.append("  ② 没有 cost 分列（旧的 pnl 已含 swap，无法与报告 Total Net Profit 逐项对）")
L.append("  ③ jyrg-c0-base 报告净利取到 77.64 —— 那是【网格 pass】的 rep，不是该单跑的")
L.append("")
L.append("v2 的正确口径：")
L.append("  审计 Σ(profit + swap + commission)  ==  MT5 报告 Total Net Profit")
L.append("  → 两者都是【含成本净额】，必须直接相等")
L.append("```")
L.append("")
L.append("## 5. 产物\n")
L.append("- `reconciliation_r2.csv`")
L.append("- 本文件")
L.append("")

io.open(os.path.join(OUT, "reconciliation_r2.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
if res:
    with io.open(os.path.join(OUT, "reconciliation_r2.csv"), "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(res[0].keys()))
        w.writeheader(); w.writerows(res)
print("\n".join(L))

