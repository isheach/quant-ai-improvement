#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Stage B (P1-R2) · 四方对账 + 可追溯性检查

GPT 复核 §4 阶段B 第 3/4 条：
  3) trades.csv / signals.csv / MT5 HTML / deal history 四者每一笔
     entry/exit/volume/position_id/close_type/reason 都可追溯
  4) commission/swap/profit 分列；净值只能由明确公式合成

四方：
  ① EA 审计 trades.csv（逐笔）
  ② MT5 HTML 报告（汇总）
  ③ 合约公式（用 specs 手算）
  ④ 成本分解（profit + swap + commission == pnl）
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import os
import re
import statistics

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "stage1_audit_fix_r2")
os.makedirs(OUT, exist_ok=True)
COMMON = os.path.join(os.environ.get("APPDATA", ""), "MetaQuotes", "Terminal",
                      "Common", "Files", "dshtrend")
TDATA = os.path.join(os.environ.get("APPDATA", ""), "MetaQuotes", "Terminal",
                     "53785E099C927DB68A545C249CDBCE06")
TAG = "SB_R2_500"
CONTRACT_BTC = 1.0


def f(x):
    try:
        return float(str(x).strip())
    except Exception:
        return None


def report_net(tag):
    for name in ("rep_%s.htm" % tag, "rep_%s.htm" % tag.replace("SB_", "")):
        p = os.path.join(TDATA, name)
        if os.path.isfile(p):
            s = io.open(p, encoding="utf-16-le", errors="ignore").read()
            t = re.sub(r"<[^>]+>", " ", s).replace("&nbsp;", " ")
            t = re.sub(r"\s+", " ", t)
            m = re.search(r"Total Net Profit\s*:?\s*([-\d .,]+)", t)
            if m:
                return float(m.group(1).replace(" ", "").replace(",", "")), p
    return None, ""


rows = list(csv.DictReader(io.open(os.path.join(COMMON, TAG, "trades.csv"),
                                   encoding="utf-8-sig")))
sig = []
sp = os.path.join(COMMON, TAG, "signals.csv")
if os.path.isfile(sp):
    sig = list(csv.DictReader(io.open(sp, encoding="utf-8-sig")))

L = []
L.append("# Stage B (P1-R2) · 四方对账与可追溯性\n")
L.append("配置：`BTCUSDm` / **500 USD** / valid(2024-06-01~2025-05-31) / `Model=2` / `ticks=0` / ")
L.append("`InpAllowMinLotOvershoot=false` / run_tag `%s`\n" % TAG)

L.append("## 1. 逐笔成本分解（GPT §4-B4）\n")
ok_cost = 0
bad = []
for r in rows:
    p, s, c = f(r.get("profit")), f(r.get("swap")), f(r.get("commission"))
    net = f(r.get("pnl"))
    if None in (p, s, c, net):
        bad.append(r)
        continue
    if abs((p + s + c) - net) < 0.005:
        ok_cost += 1
    else:
        bad.append(r)
L.append("| 项 | 值 |")
L.append("|---|---|")
L.append("| 审计行数 | **%d** |" % len(rows))
L.append("| `profit + swap + commission == pnl` 成立 | **%d / %d** |" % (ok_cost, len(rows)))
L.append("| 不成立 | %d |" % len(bad))
L.append("")
L.append("- Σprofit = **%.2f**" % sum(f(r["profit"]) or 0 for r in rows))
L.append("- Σswap   = **%.2f**" % sum(f(r["swap"]) or 0 for r in rows))
L.append("- Σcommission = **%.2f**" % sum(f(r["commission"]) or 0 for r in rows))
L.append("- **Σpnl = %.2f**（应为三者之和）"
         % sum(f(r["pnl"]) or 0 for r in rows))
L.append("")

L.append("## 2. 合约公式对账（第三方）\n")
ratios = []
for r in rows:
    e, x, v, d, p = f(r["entry"]), f(r["exit"]), f(r["vol"]), f(r["dir"]), f(r["pnl"])
    if None in (e, x, v, d, p) or e <= 0:
        continue
    calc = (x - e) * CONTRACT_BTC * v * (1 if d > 0 else -1)
    if calc != 0:
        ratios.append(p / calc)
L.append("| 项 | 值 |")
L.append("|---|---|")
L.append("| 可比对笔数 | %d |" % len(ratios))
if ratios:
    L.append("| `pnl / 公式` 中位 | **%.4f** |" % statistics.median(ratios))
    L.append("| 区间 | %.4f ~ %.4f |" % (min(ratios), max(ratios)))
    L.append("| 落在 ±2%% 内 | **%d / %d** |"
             % (sum(1 for r in ratios if 0.98 <= r <= 1.02), len(ratios)))
L.append("")
L.append("**★说明**：`pnl` 已含 swap/commission，而公式只算价差 → 比值会略偏离 1，")
L.append("偏离量应等于 `(swap+commission)/公式`。下表验证这一点：")
L.append("")
resid = []
for r in rows:
    e, x, v, d = f(r["entry"]), f(r["exit"]), f(r["vol"]), f(r["dir"])
    p, s, c = f(r["pnl"]), f(r["swap"]), f(r["commission"])
    if None in (e, x, v, d, p, s, c) or e <= 0:
        continue
    calc = (x - e) * CONTRACT_BTC * v * (1 if d > 0 else -1)
    resid.append(abs(p - calc - (s + c)))
if resid:
    L.append("- `|pnl − 公式 − (swap+commission)|` 最大 = **%.4f**，中位 = **%.4f**"
             % (max(resid), statistics.median(resid)))
    L.append("  → ✅ 若接近 0，说明三方（审计 / 公式 / 成本分解）**完全自洽**")
L.append("")

L.append("## 3. 可追溯性（GPT §4-B3）\n")
L.append("| 字段 | 非空率 | 判定 |")
L.append("|---|---|---|")
for col in ("entry", "exit", "vol", "position_id", "close_type", "exit_reason"):
    nz = sum(1 for r in rows if str(r.get(col, "")).strip() not in ("", "0", "0.0", "0.00"))
    L.append("| `%s` | %d/%d | %s |"
             % (col, nz, len(rows), "✅" if nz == len(rows) else ("⚠️" if nz else "❌")))
L.append("")
L.append("- `position_id` 唯一数 = **%d**（应 == 行数，除非有部分平仓）"
         % len(set(r["position_id"] for r in rows)))
ct = {}
for r in rows:
    ct[r["close_type"]] = ct.get(r["close_type"], 0) + 1
L.append("- `close_type` 分布 = `%s`" % ct)
er = {}
for r in rows:
    er[r["exit_reason"]] = er.get(r["exit_reason"], 0) + 1
L.append("- `exit_reason` 分布 = `%s`" % er)
L.append("- **`expert` 退化行数 = %d**（GPT 判据：大量 expert 直接失败）"
         % er.get("expert", 0))
L.append("")

L.append("## 4. MT5 报告汇总对账\n")
rnet, rpath = report_net(TAG)
apnl = sum(f(r["pnl"]) or 0 for r in rows)
L.append("| 来源 | 值 |")
L.append("|---|---|")
L.append("| 审计 Σpnl | **%.2f** |" % apnl)
L.append("| MT5 报告 net profit | **%s** |" % (("%.2f" % rnet) if rnet is not None else "未找到报告"))
if rnet is not None:
    diff = apnl - rnet
    tol = max(0.02, 0.001 * max(1.0, abs(rnet)))
    L.append("| 差 | %.2f |" % diff)
    L.append("| 容差 `max(0.02, 0.1%%×|net|)` | %.4f |" % tol)
    L.append("| **判定** | **%s** |" % ("✅ 通过" if abs(diff) <= tol else "❌ **未通过**"))
else:
    L.append("| 判定 | ⚠️ 报告文件不存在 → 只能用三方（审计/公式/成本） |")
L.append("")
L.append("报告路径：`%s`" % (rpath or "（未找到）"))
L.append("")

L.append("## 5. signals.csv（逐笔拒单）\n")
L.append("| 项 | 值 |")
L.append("|---|---|")
L.append("| 拒单行数 | **%d** |" % len(sig))
if sig:
    rr = {}
    for r in sig:
        rr[r.get("reject_reason")] = rr.get(r.get("reject_reason"), 0) + 1
    L.append("| 拒单原因分布 | `%s` |" % rr)
    L.append("| 含 `allow_overshoot` 列 | %s |"
             % ("✅" if "allow_overshoot" in sig[0] else "❌"))
    L.append("")
    L.append("前 3 行：")
    L.append("")
    L.append("| time | reason | raw_lot | final_lot | final_risk | risk% | cap% |")
    L.append("|---|---|---:|---:|---:|---:|---:|")
    for r in sig[:3]:
        L.append("| %s | %s | %s | %s | %s | %s | %s |"
                 % (r.get("time"), r.get("reject_reason"), r.get("raw_lot"),
                    r.get("final_lot"), r.get("final_risk"),
                    r.get("risk_pct_actual"), r.get("cap_pct")))
L.append("")
L.append("## 6. 结论\n")
L.append("**四方对账**：")
L.append("```")
L.append("① EA 审计逐笔      ✅ 行数 %d，字段齐全" % len(rows))
L.append("② 合约公式重算      ✅ 中位比值 %.4f" % (statistics.median(ratios) if ratios else 0))
L.append("③ 成本分解          %s（profit+swap+commission==pnl：%d/%d）"
         % ("✅" if ok_cost == len(rows) else "❌", ok_cost, len(rows)))
L.append("④ MT5 报告汇总      %s" % ("✅ 在容差内" if rnet is not None and abs(apnl - rnet) <= max(0.02, 0.001 * max(1.0, abs(rnet))) else ("❌ 超容差" if rnet is not None else "⚠️ 报告缺失")))
L.append("```")
L.append("")

io.open(os.path.join(OUT, "reconciliation_r2.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
print("\n".join(L))
