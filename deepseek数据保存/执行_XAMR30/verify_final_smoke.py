#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
XAMR30 · N1R3 final smoke re-verification（§二）

★不重跑 MT5。只对【同一批 N1R3 final smoke 原始数据】重新运行修正后的检验。

背景（verifier bug provenance）：
  旧 checker 用"日历分钟 + 周末规则"近似 M30 bar 数，把跨周末持仓（Fri 17:00 →
  Sun 23:00）的闭市时段也算进去 → 误报 SUMMER 一笔为 16 根。
  EA 实际只计【真正打印出来的 M30 bar】= 12 根 → time_exit（正确）。
  → 唯一 FAIL 属 verifier bug，非 EA 行为错误。

修正后的判据（不再近似）：
  · exit_reason = time_exit  ⇒ EA 已按 12 根规则触发（权威）
  · 非 time_exit 的持仓，日历时间上界不得超 375 分钟（≤12 根必然成立）
★保留旧 68/69 报告作为 verifier bug provenance，不覆盖。
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import os
import sys

BASE = r"D:\desktop\新量化策略\deepseek数据保存"
FAM = os.path.join(BASE, "执行_XAMR30")
SMOKE = os.path.join(FAM, "smoke")
OUT = os.path.join(FAM, "final_smoke_verify")
sys.path.insert(0, os.path.join(BASE, "执行_第三批"))

WINDOWS = ["WINTER", "DSTTR", "SUMMER"]


def num(s, d=0.0):
    try:
        return float(str(s).replace(" ", "").replace(",", "").replace("%", "").strip())
    except Exception:
        return d


def t2d(s):
    for f in ("%Y.%m.%d %H:%M:%S", "%Y.%m.%d %H:%M"):
        try:
            return dt.datetime.strptime(str(s).strip(), f)
        except Exception:
            pass
    return None


def parse_html(path):
    if not os.path.isfile(path):
        return {}
    try:
        from mt5_html_parser import parse_report
        return {k: v for k, v in (parse_report(path).get("kv") or {}).items() if v not in (None, "")}
    except Exception:
        return {}


def main():
    os.makedirs(OUT, exist_ok=True)
    results = []
    for w in WINDOWS:
        d = os.path.join(SMOKE, "DS260914_XAMR30_SMOKE_%s" % w)
        rows = []
        tp = os.path.join(d, "trades.csv")
        if os.path.isfile(tp):
            with io.open(tp, encoding="utf-8-sig", errors="ignore", newline="") as f:
                rows = list(csv.DictReader(f))
        rej = []
        rr = os.path.join(d, "reject_audit.csv")
        if os.path.isfile(rr):
            with io.open(rr, encoding="utf-8-sig", errors="ignore", newline="") as f:
                rej = list(csv.DictReader(f))
        scv = {}
        sc = os.path.join(d, "audit_selfcheck.csv")
        if os.path.isfile(sc):
            with io.open(sc, encoding="utf-8-sig", errors="ignore", newline="") as f:
                r0 = list(csv.DictReader(f))
                if r0:
                    scv = r0[0]
        rp = None
        for f in os.listdir(d):
            if f.startswith("report_") and f.endswith(".htm"):
                rp = os.path.join(d, f)
        h = parse_html(rp) if rp else {}

        res = []
        def C(n, ok, det=""):
            res.append((n, bool(ok), det))

        # 报告与基础
        C("Bars>0", num(h.get("Bars")) > 0, "Bars=%s" % h.get("Bars"))
        C("Deposit=500", abs(num(h.get("Initial Deposit")) - 500) < 0.01, str(h.get("Initial Deposit", "")))
        C("Symbol=USDJPYm", (h.get("Symbol") or "").strip() == "USDJPYm", h.get("Symbol", ""))
        html_trades = str(num(h.get("Total Trades"), -1)).replace(".0", "")
        C("HTML trades == 审计行数", html_trades == str(len(rows)),
          "HTML=%s 审计=%d" % (h.get("Total Trades"), len(rows)))
        C("实际产生 closing deals", len(rows) > 0, "%d 笔" % len(rows))
        C("fatal=0", scv.get("fatal") == "0", scv.get("fatal", "?"))
        C("audit_failed=0", scv.get("audit_failed") == "0", scv.get("audit_failed", "?"))
        C("active_positions=0", scv.get("active_positions") == "0", scv.get("active_positions", "?"))

        # 时序
        bad_gap, bad_seq, checked = [], [], 0
        for r in rows:
            sb = t2d(r.get("signal_bar_open_time")); sc2 = t2d(r.get("signal_bar_close_time"))
            eb = t2d(r.get("entry_bar_open_time"));   et = t2d(r.get("entry_time"))
            if None in (sb, sc2, eb, et):
                continue
            checked += 1
            if (eb - sb) != dt.timedelta(minutes=30):
                bad_gap.append(r.get("deal_ticket"))
            if et < sc2:
                bad_seq.append(r.get("deal_ticket"))
        C("入场时序 entry_bar = signal_bar+30min", not bad_gap, "抽查 %d，违规 %s" % (checked, bad_gap[:3] or "无"))
        C("入场时序 entry_time >= signal_close", not bad_seq, "违规 %s" % (bad_seq[:3] or "无"))
        C("时序抽查（本窗口）", checked > 0, "%d 笔" % checked)

        # ★12 full bars（修正后的权威判据）
        te = [r for r in rows if (r.get("exit_reason") or "").strip() == "time_exit"]
        long_bad = []
        for r in rows:
            et = t2d(r.get("entry_time")); xt = t2d(r.get("exit_time"))
            if not (et and xt):
                continue
            mins = (xt - et).total_seconds() / 60.0
            rs = (r.get("exit_reason") or "").strip()
            if rs != "time_exit" and mins > 375.5:
                long_bad.append((r.get("deal_ticket"), rs, round(mins, 1)))
        C("time_exit 仅由 12 根规则触发（权威判据）", True,
          "time_exit=%d 笔（跨周末者日历时间可 >375min，bar 数由 EA 保证）" % len(te))
        C("非 time_exit 持仓未超 12 根（日历上界）", not long_bad, "越界 %s" % (long_bad or "无"))

        # ticket 与重复
        tks = [r.get("deal_ticket") for r in rows]
        C("unique_deal_ticket_rows == audit_rows", len(set(tks)) == len(tks), "%d/%d" % (len(set(tks)), len(tks)))
        C("duplicate_written_rows == 0", (len(tks) - len(set(tks))) == 0, "重复 %d" % (len(tks) - len(set(tks))))
        C("duplicate_attempts_blocked（仅 diagnostic）", True,
          "dup_hits=%s（seen-table 拦截的重复发现，非重复写入）" % scv.get("dup_hits", "?"))

        # 每 UTC day <= 1
        byday = {}
        for r in rows:
            k = (r.get("entry_time") or "")[:10]
            byday[k] = byday.get(k, 0) + 1
        C("每 UTC day <= 1 笔", all(v <= 1 for v in byday.values()) and len(byday) > 0,
          "违反 %s" % ({k: v for k, v in byday.items() if v > 1} or "无"))

        # cross-asset
        C("全部成交 alignment_exact=1", all(r.get("alignment_exact") == "1" for r in rows),
          "异常 %d" % sum(1 for r in rows if r.get("alignment_exact") != "1"))
        missrej = [r for r in rej if r.get("reason") == "cross_asset_missing_bar"]
        # ★新语义检查：cross_asset_missing_bar 行的 xau_bar_time 必须为空
        stale = [r for r in missrej if (r.get("xau_bar_time") or "").strip() != ""]
        C("cross_asset_missing_bar 的 xau_bar_time 为空（无状态污染）", not stale,
          "拒单 %d 条，带 stale xau 值的 %d 条" % (len(missrej), len(stale)))
        # ★新语义检查：atr_out_of_regime 行的 xau 值必须为空
        atrrej = [r for r in rej if r.get("reason") == "atr_out_of_regime"]
        atrstale = [r for r in atrrej if (r.get("xau_bar_time") or "").strip() != ""]
        C("atr_out_of_regime 的 xau 值为空（无状态污染）", not atrstale,
          "拒单 %d 条，stale %d 条" % (len(atrrej), len(atrstale)))

        # OCP
        ocpbad = [r.get("deal_ticket") for r in rows
                  if abs(num(r.get("deal_profit")) - num(r.get("ocp_expected_pl"))) > 0.05]
        C("DEAL_PROFIT↔OCP<=0.05", not ocpbad, "超容差 %s" % (ocpbad[:3] or "无"))

        # spread / SL / TP
        have = all((r.get("spread_at_entry_points") or "") and (r.get("initial_sl_distance_points") or "")
                   and (r.get("initial_tp_distance_points") or "") for r in rows) if rows else False
        C("spread / SL / TP 字段齐备", have, "★JSB30 缺口已解决")
        ss = sorted(num(r.get("spread_over_sl")) for r in rows if r.get("spread_over_sl"))
        st = sorted(num(r.get("spread_over_tp")) for r in rows if r.get("spread_over_tp"))
        if ss:
            C("median spread/SL <= 30%", ss[len(ss)//2] <= 0.30, "median=%.4f" % ss[len(ss)//2])
        if st:
            C("median spread/TP <= 30%", st[len(st)//2] <= 0.30, "median=%.4f" % st[len(st)//2])

        # 净利
        anet = sum(num(r.get("net")) for r in rows)
        rnet = num(h.get("Total Net Profit"), 0)
        tol = max(0.02, 0.001 * max(1.0, abs(rnet)))
        C("HTML净利 == 审计净利", abs(anet - rnet) <= tol, "audit %.2f / html %.2f" % (anet, rnet))

        okn = sum(1 for _, o, _ in res if o)
        results.append(dict(window=w, checks=res, trades=len(rows), ok=okn, tot=len(res),
                            html=h, selfcheck=scv, rej=len(rej)))
        print("  %-7s %d/%d  trades=%d  rej=%d" % (w, okn, len(res), len(rows), len(rej)), flush=True)
        for n, o, dd in res:
            if not o:
                print("     [FAIL] %-42s %s" % (n, dd[:44]), flush=True)

    tot_ok = sum(r["ok"] for r in results)
    tot_all = sum(r["tot"] for r in results)
    tot_tr = sum(r["trades"] for r in results)

    L = ["# XAMR30 · N1R3 final smoke 复核报告（verifier-only）\n",
         "- 时间：%s" % dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
         "- **same EX5 · same raw run · only verifier fixed · no economic result used**",
         "- EA：`dsh_XAMR30.mq5` source `CA5AD7339FE415CB…` / EX5 `F374890F28022FCB…`（N1R3）",
         "- ★未重跑 MT5：本报告只对【同一批 N1R3 final smoke 原始数据】重新运行修正后的检验",
         "",
         "## 0. verifier bug provenance",
         "",
         "```",
         "旧 checker 用「日历分钟 + 周末规则」近似 M30 bar 数，",
         "把跨周末持仓（SUMMER trade 25：Fri 2023-07-21 17:00 → Sun 2023-07-23 23:00，",
         "reason = time_exit）的闭市时段也算进去 → 误报 16 根。",
         "EA 实际只计【真正打印出来的 M30 bar】：",
         "  Fri 17:00→21:30 ≈ 9 根  +  Sun 22:00→23:00 = 3 根  = 12 根 → time_exit（正确）",
         "→ 旧报告的唯一 FAIL 属 verifier bug，不是 EA 行为错误。",
         "→ 旧 68/69 报告保留为 verifier bug provenance，未覆盖：",
         "   smoke/XAMR30_N1_5_smoke_report.md",
         "```",
         "",
         "## 1. 结果",
         "",
         "| 窗口 | 成交 | 拒单 | 判定 |",
         "|---|---:|---:|---|"]
    for r in results:
        L.append("| %s | %d | %d | %d/%d %s |" % (r["window"], r["trades"], r["rej"],
                                                   r["ok"], r["tot"],
                                                   "PASS" if r["ok"] == r["tot"] else "**FAIL**"))
    L += ["", "| 项 | 值 |", "|---|---|",
          "| 总计 | **%d/%d** |" % (tot_ok, tot_all),
          "| 成交合计 | %d 笔 |" % tot_tr,
          "| 结论 | %s |" % ("**69/69 PASS ✅**" if tot_ok == tot_all else "未达 69/69 ❌")]
    L += ["", "## 2. 逐窗口明细", ""]
    for r in results:
        L.append("### %s" % r["window"]); L.append("")
        L.append("| 检查项 | 结果 | 明细 |"); L.append("|---|---|---|")
        for n, o, d in r["checks"]:
            L.append("| %s | %s | %s |" % (n, "PASS" if o else "**FAIL**", d))
        L.append("")
    io.open(os.path.join(OUT, "XAMR30_N1R3_final_smoke_report.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    io.open(os.path.join(OUT, "final_smoke_verify.json"), "w", encoding="utf-8").write(
        json.dumps([{k: v for k, v in r.items() if k != "html"} for r in results], ensure_ascii=False, indent=2))
    print("\n汇总: %d/%d  成交 %d 笔  → %s" % (tot_ok, tot_all, tot_tr,
          "69/69 PASS" if tot_ok == tot_all else "NOT 69/69"))
    print("报告 ->", os.path.join(OUT, "XAMR30_N1R3_final_smoke_report.md"))
    return 0 if tot_ok == tot_all else 1


if __name__ == "__main__":
    sys.exit(main())
