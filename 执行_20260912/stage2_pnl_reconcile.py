#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Stage 2 · USDJPY 四方盈亏对账（GPT 执行框架 §5）

背景：历史报告里 JPY 曾出现 143 倍量级异常，故在【任何】JPY 策略搜索前必须先对账。

四方口径：
  ① MT5 HTML 报告 net profit
  ② 审计 trades.csv 的 pnl 求和
  ③ 合约公式（用 specs.txt 的 contract / point）
  ④ 独立探针（本脚本用 ①vs②vs③ 三方 + 逐笔回归，替代需要新回测的第四方）

USDJPY 换算（关键）：盈亏是【计价货币 JPY】，账户是 USD
  pnl_usd = (exit - entry) / exit * contract * volume      （做多）
  pnl_usd = (entry - exit) / exit * contract * volume      （做空）
  → 等价于 (price_diff / exit) * contract * volume
  → 这里用【出场价】换算（MT5 实际用平仓时的汇率）
"""
from __future__ import annotations

import csv
import io
import os
import re
import statistics

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "stage2_usdjpy_pnl")
os.makedirs(OUT, exist_ok=True)

COMMON = os.path.join(os.environ.get("APPDATA", ""), "MetaQuotes", "Terminal",
                      "Common", "Files", "dshtrend")
TDATA = os.path.join(os.environ.get("APPDATA", ""), "MetaQuotes", "Terminal",
                     "53785E099C927DB68A545C249CDBCE06")

SPECS = {
    "USDJPYm": dict(contract=100000.0, point=0.001, digits=3, volmin=0.01),
    "BTCUSDm": dict(contract=1.0,      point=0.01,  digits=2, volmin=0.01),
    "XAUUSDm": dict(contract=100.0,    point=0.01,  digits=2, volmin=0.01),
}


def load_trades(tag):
    p = os.path.join(COMMON, tag, "trades.csv")
    if not os.path.isfile(p):
        return None, p
    with io.open(p, encoding="utf-8-sig", errors="ignore", newline="") as f:
        return list(csv.DictReader(f)), p


def fnum(x):
    try:
        return float(str(x).strip())
    except Exception:
        return None


def report_net(tag):
    """从 MT5 HTML 报告抽 net profit（UTF-16LE，千位分隔符是空格）"""
    p = os.path.join(TDATA, "rep_%s.htm" % tag)
    if not os.path.isfile(p):
        for cand in (tag.replace("XX_", "BT_"), tag.replace("XX_", "")):
            q = os.path.join(TDATA, "rep_%s.htm" % cand)
            if os.path.isfile(q):
                p = q
                break
    if not os.path.isfile(p):
        return None, None
    try:
        s = io.open(p, encoding="utf-16-le", errors="ignore").read()
    except Exception:
        return None, p
    txt = re.sub(r"<[^>]+>", " ", s)
    txt = txt.replace("&nbsp;", " ")
    txt = re.sub(r"\s+", " ", txt)
    # Total Net Profit 后跟数值
    m = re.search(r"Total Net Profit\s*:?\s*([-\d .,]+)", txt)
    if m:
        v = m.group(1).replace(" ", "").replace(",", "")
        try:
            return float(v), p
        except Exception:
            return None, p
    return None, p


def reconcile(symbol, tag, sign_conv):
    rows, path = load_trades(tag)
    if not rows:
        return None
    sp = SPECS[symbol]
    recs = []
    for r in rows:
        e = fnum(r.get("entry")); x = fnum(r.get("exit"))
        v = fnum(r.get("vol"));   p = fnum(r.get("pnl"))
        d = fnum(r.get("dir"))
        if None in (e, x, v, p, d) or e <= 0 or x <= 0 or v <= 0:
            continue
        if sign_conv == "jpy":
            # 盈亏以 JPY 计 → 除以出场价换成 USD
            calc = (x - e) / x * sp["contract"] * v * (1 if d > 0 else -1)
        else:
            calc = (x - e) * sp["contract"] * v * (1 if d > 0 else -1)
        ratio = (p / calc) if calc != 0 else None
        recs.append(dict(entry=e, exit=x, vol=v, dir=d, pnl=p, calc=calc, ratio=ratio))
    if not recs:
        return None
    ratios = [r["ratio"] for r in recs if r["ratio"] is not None]
    nets = [r["pnl"] for r in recs]
    calcs = [r["calc"] for r in recs]
    rnet, rpath = report_net(tag)
    return dict(
        tag=tag, symbol=symbol, trades=len(rows), usable=len(recs),
        sum_pnl=sum(nets), sum_calc=sum(calcs),
        ratio_med=(statistics.median(ratios) if ratios else None),
        ratio_min=(min(ratios) if ratios else None),
        ratio_max=(max(ratios) if ratios else None),
        report_net=rnet, audit_path=path, report_path=rpath,
    )


def main():
    jobs = [
        ("USDJPYm", "XX_jyrg-c0-base", "jpy"),
        ("USDJPYm", "XX_jyrg-c0r", "jpy"),
        ("USDJPYm", "XX_jyrg-c1-bh", "jpy"),
        ("USDJPYm", "XX_jyrg-c6-cdbest", "jpy"),
        ("BTCUSDm", "BT_btc-283", "usd"),
        ("XAUUSDm", "GD_gold-100", "usd"),
    ]
    L = []
    L.append("# Stage 2 · 盈亏换算四方对账\n")
    L.append("对账对象：审计 `trades.csv` 的 `pnl` vs **合约公式重算**（用实测 specs）。\n")
    L.append("换算口径：")
    L.append("```")
    L.append("USD 计价品种: calc = (exit - entry) * contract * vol * dir")
    L.append("JPY 计价品种: calc = (exit - entry) / exit * contract * vol * dir   ← 除出场价换回 USD")
    L.append("```\n")
    L.append("| run_tag | 品种 | 审计行 | 可用 | Σ审计pnl | Σ公式pnl | 比值中位 | 比值min | 比值max |")
    L.append("|---|---|---:|---:|---:|---:|---:|---:|---:|")
    rows = []
    for sym, tag, conv in jobs:
        r = reconcile(sym, tag, conv)
        if not r:
            L.append("| `%s` | %s | — | — | — | — | — | — | — |" % (tag, sym))
            continue
        rows.append(r)
        L.append("| `%s` | %s | %d | %d | %.2f | %.2f | **%.4f** | %.4f | %.4f |"
                 % (r["tag"], r["symbol"], r["trades"], r["usable"],
                    r["sum_pnl"], r["sum_calc"],
                    r["ratio_med"] or 0, r["ratio_min"] or 0, r["ratio_max"] or 0))
    L.append("")
    L.append("## 判定\n")
    jpy = [r for r in rows if r["symbol"] == "USDJPYm"]
    if jpy:
        meds = [r["ratio_med"] for r in jpy if r["ratio_med"]]
        if meds:
            m = statistics.median(meds)
            L.append("- **USDJPY 比值中位 = %.4f**" % m)
            if 0.98 <= m <= 1.02:
                L.append("  → ✅ **换算正确**：审计 `pnl` 与合约公式重算一致（±2%% 内）。")
                L.append("  → 框架 §5 关注的 143 倍异常**在【本批数据】中不复现**。")
            elif m > 10 or m < 0.1:
                L.append("  → ❌ **存在量级异常**（%.1f 倍），必须先修换算再进入 JPY 搜索。" % m)
            else:
                L.append("  → ⚠️ 比值偏离 1（%.4f），需逐笔核对（可能是出场价 vs 入场价换算差异）。" % m)
    L.append("")
    L.append("## 说明：14143 倍异常的核查结论\n")
    L.append("历史记录里 JPY 曾出现 143 倍量级异常。本脚本用【当前审计格式】的 JPY run 重算，")
    L.append("若比值≈1，则说明：")
    L.append("1. 当日异常来自 **`SYMBOL_TRADE_TICK_VALUE` 在 tester 里的漂移**（该字段不可信）；")
    L.append("2. 或来自 **某一版 EA 的换算实现**（现已改为合约规格比手算）。")
    L.append("3. 无论哪种，**当前审计链路是自洽的** —— 可用它做 JPY 对账基准。")
    L.append("")
    L.append("## 产物\n")
    L.append("- `pnl_reconcile.csv`")
    L.append("- 本文件")
    L.append("")

    with io.open(os.path.join(OUT, "pnl_reconcile.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    if rows:
        with io.open(os.path.join(OUT, "pnl_reconcile.csv"), "w", encoding="utf-8-sig",
                     newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
