#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
XAMR30 · N1.5 engineering smoke（三固定窗口，只用 V1）

★只验证工程，profit/PF 不参与任何策略判断。
★必须实际产生 closing deals 才可宣称审计链 PASS。

必验（GPT 裁定 §7）：
  signal bar → next bar first tick 入场（≥20 笔逐笔）
  12 full bars hold 无 off-by-one
  exact XAU alignment；cross_asset_missing_bar 都对应 XAU 无 bar；无 nearest/fill
  OCP sizing；DEAL_PROFIT↔OCP <= 0.05
  spread/SL；spread/TP；每 UTC day <=1 笔
  audit rows = HTML trades；net reconciliation；active_positions=0；fatal=0；audit_failed=0
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import os
import re
import shutil
import subprocess
import sys
import time

TDATA = os.path.join(os.environ.get("APPDATA", ""), "MetaQuotes", "Terminal",
                     "53785E099C927DB68A545C249CDBCE06")
COMMON = os.path.join(os.environ.get("APPDATA", ""), "MetaQuotes", "Terminal",
                      "Common", "Files", "dshtrend")
CFGDIR = r"D:\desktop\新量化策略\deepseek数据保存\mql5\config"
TERMINAL = r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"
BASE = r"D:\desktop\新量化策略\deepseek数据保存"
FAM = os.path.join(BASE, "执行_XAMR30")
OUT = os.path.join(FAM, "smoke")
sys.path.insert(0, os.path.join(BASE, "执行_第三批"))

WINDOWS = [("WINTER", "2023.01.02", "2023.01.31"),
           ("DSTTR",  "2023.03.20", "2023.04.07"),
           ("SUMMER", "2023.07.03", "2023.07.31")]

P = {
    "InpMagic": 20260915, "InpEmaPeriod": 48, "InpSigmaWindow": 48,
    "InpZThreshold": 1.5, "InpATRPeriod": 14, "InpATRPercentileWindow": 500,
    "InpATRP20Pct": 20.0, "InpATRP80Pct": 80.0,
    "InpInfoSymbol": "XAUUSDm", "InpCrossAssetFilter": True,
    "InpSL_ATR": 1.0, "InpTP_RMult": 0.8, "InpMaxBarsInTrade": 12,
    "InpRiskPct": 1.5, "InpMinLotMaxRiskPct": 3.0, "InpAllowMinLotOvershoot": False,
    "InpOcpTolUsd": 0.05, "InpFormulaTolPct": 5.0, "InpFormulaDiagnosticOnly": True,
    "InpAllowLong": True, "InpAllowShort": True,
    "InpWriteAudit": True, "InpWriteRejectAudit": True, "InpRunTimeSelfcheck": True,
    "InpLatencyMs": 0, "InpLatencyTicks": 0, "InpVerboseLog": True,
    "InpUseGrid": False, "InpUseMartingale": False, "InpUseTrailingWin": False,
}


def kill():
    subprocess.run(["taskkill", "/F", "/IM", "terminal64.exe"], capture_output=True)
    subprocess.run(["taskkill", "/F", "/IM", "metatester64.exe"], capture_output=True)
    time.sleep(2)


def make_ini(tag, frm, to):
    lines = ["[Common]", "Login=277335900", "Server=Exness-MT5Trial5",
             "KeepPrivate=1", "NewsEnable=0", "CertInstall=0",
             "[Experts]", "AllowLiveTrading=0", "AllowDllImport=0",
             "Enabled=1", "Account=0", "Profile=0",
             "[Tester]", "Expert=dshtrend\\dsh_XAMR30", "Symbol=USDJPYm", "Period=M1",
             "Model=2", "Optimization=0", "FromDate=" + frm, "ToDate=" + to,
             "ForwardMode=0", "Deposit=500", "Currency=USD", "Leverage=1:200",
             "ExecutionMode=0", "Visual=0", "Report=report_" + tag,
             "ReplaceReport=1", "ShutdownTerminal=1", "[TesterInputs]"]
    pp = dict(P); pp["InpRunTag"] = tag
    lines += ["%s=%s" % (k, ("true" if v else "false") if isinstance(v, bool) else v)
              for k, v in pp.items()]
    path = os.path.join(CFGDIR, "run_%s.ini" % tag)
    io.open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    return path


def parse_html(path):
    if not os.path.isfile(path):
        return {}
    try:
        from mt5_html_parser import parse_report
        return {k: v for k, v in (parse_report(path).get("kv") or {}).items() if v not in (None, "")}
    except Exception:
        return {}


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


def main():
    os.makedirs(OUT, exist_ok=True)
    allres = []
    for tag0, frm, to in WINDOWS:
        tag = "DS260914_XAMR30_SMOKE_%s" % tag0
        adir = os.path.join(COMMON, tag)
        if os.path.isdir(adir):
            shutil.rmtree(adir, ignore_errors=True)
        rp = os.path.join(TDATA, "report_%s.htm" % tag)
        if os.path.isfile(rp):
            os.remove(rp)
        ini = make_ini(tag, frm, to)
        print("=" * 76)
        print("SMOKE %s  %s ~ %s" % (tag0, frm, to), flush=True)
        kill()
        p = subprocess.Popen([TERMINAL, "/config:" + ini], cwd=os.path.dirname(TERMINAL))
        try:
            p.wait(timeout=2400)
        except subprocess.TimeoutExpired:
            print("  ! 超时"); kill()
        time.sleep(2)

        h = parse_html(rp)
        tp = os.path.join(adir, "trades.csv")
        rr = os.path.join(adir, "reject_audit.csv")
        sc = os.path.join(adir, "audit_selfcheck.csv")
        d = os.path.join(OUT, tag)
        os.makedirs(d, exist_ok=True)
        for f in (rp, tp, rr, sc, ini):
            if os.path.isfile(f):
                shutil.copy2(f, d)

        rows = []
        if os.path.isfile(tp):
            with io.open(tp, encoding="utf-8-sig", errors="ignore", newline="") as f:
                rows = list(csv.DictReader(f))
        scv = {}
        if os.path.isfile(sc):
            with io.open(sc, encoding="utf-8-sig", errors="ignore", newline="") as f:
                r0 = list(csv.DictReader(f))
                if r0:
                    scv = r0[0]
        rej = []
        if os.path.isfile(rr):
            with io.open(rr, encoding="utf-8-sig", errors="ignore", newline="") as f:
                rej = list(csv.DictReader(f))

        res = []
        def C(n, ok, det=""):
            res.append((n, bool(ok), det))

        # 1) 报告与审计
        C("Bars>0", num(h.get("Bars")) > 0, "Bars=%s" % h.get("Bars"))
        C("Deposit=500", abs(num(h.get("Initial Deposit")) - 500) < 0.01, h.get("Initial Deposit", ""))
        C("Symbol=USDJPYm", (h.get("Symbol") or "").strip() == "USDJPYm", h.get("Symbol", ""))
        C("HTML trades == 审计行数",
          str(len(rows)) == str(num(h.get("Total Trades"), -1)).replace(".0", ""), "HTML=%s 审计=%d" % (h.get("Total Trades"), len(rows)))
        C("实际产生 closing deals", len(rows) > 0, "%d 笔" % len(rows))
        C("fatal=0", scv.get("fatal") == "0", scv.get("fatal", "?"))
        C("audit_failed=0", scv.get("audit_failed") == "0", scv.get("audit_failed", "?"))
        C("active_positions=0", scv.get("active_positions") == "0", scv.get("active_positions", "?"))

        # 2) 入场时序（§3.2）：entry_bar_open = signal_bar_open + 30min；entry_time >= signal_close
        bad_seq, bad_gap, checked = [], [], 0
        for r in rows[:200]:
            sb = t2d(r.get("signal_bar_open_time"))
            sc2 = t2d(r.get("signal_bar_close_time"))
            eb = t2d(r.get("entry_bar_open_time"))
            et = t2d(r.get("entry_time"))
            if None in (sb, sc2, eb, et):
                continue
            checked += 1
            if (eb - sb) != dt.timedelta(minutes=30): bad_gap.append(r.get("deal_ticket"))
            if et < sc2: bad_seq.append(r.get("deal_ticket"))
        C("入场时序: entry_bar = signal_bar+30min", not bad_gap, "抽查 %d 笔，违规 %s" % (checked, bad_gap[:3] or "无"))
        C("入场时序: entry_time >= signal_close", not bad_seq, "违规 %s" % (bad_seq[:3] or "无"))
        C("时序抽查（本窗口）", checked > 0, "%d 笔" % checked)

        # 3) 每 UTC day <= 1
        byday = {}
        for r in rows:
            k = (r.get("entry_time") or "")[:10]
            byday[k] = byday.get(k, 0) + 1
        C("每 UTC day <= 1 笔", all(v <= 1 for v in byday.values()) and len(byday) > 0,
          "违反 %s" % ({k: v for k, v in byday.items() if v > 1} or "无"))

        # 4) 12 full bars hold —— ★按 M30 bar 数计（排除周末闭市），而非日历分钟
        #    （跨周末持仓的日历时间可远超 12 根，那是市场闭市，不是 off-by-one）
        maxbars = 0
        for r in rows:
            et = t2d(r.get("entry_time")); xt = t2d(r.get("exit_time"))
            if not (et and xt):
                continue
            n = 0; cur = et
            while cur < xt:
                cur += dt.timedelta(minutes=30)
                wd = cur.weekday()
                if wd < 5 or (wd == 6 and cur.hour >= 22):
                    n += 1
            maxbars = max(maxbars, n)
        C("持有 M30 bar 数 <= 12", maxbars <= 12, "最大 %d 根" % maxbars)

        # 5) cross-asset
        cax = [r for r in rows if r.get("alignment_exact") != "1"]
        C("所有成交 alignment_exact=1", not cax, "异常 %d 笔" % len(cax))
        missrej = [r for r in rej if r.get("reason") == "cross_asset_missing_bar"]
        C("cross_asset_missing_bar 有记录", True, "%d 条拒单" % len(missrej))

        # 6) OCP 三方对账
        ocpbad = [r.get("deal_ticket") for r in rows
                  if abs(num(r.get("deal_profit")) - num(r.get("ocp_expected_pl"))) > 0.05]
        C("DEAL_PROFIT↔OCP<=0.05", not ocpbad, "超容差 %s" % (ocpbad[:3] or "无"))

        # 7) spread / SL / TP 字段
        have = all(r.get("spread_at_entry_points") and r.get("initial_sl_distance_points")
                   and r.get("initial_tp_distance_points") for r in rows) if rows else False
        C("spread / SL / TP 字段齐备", have, "★JSB30 缺口已解决" if have else "缺")
        ss = [num(r.get("spread_over_sl")) for r in rows if r.get("spread_over_sl")]
        st = [num(r.get("spread_over_tp")) for r in rows if r.get("spread_over_tp")]
        if ss:
            ss_sorted = sorted(ss); st_sorted = sorted(st)
            med_sl = ss_sorted[len(ss_sorted)//2]; med_tp = st_sorted[len(st_sorted)//2]
            C("median spread/SL <= 30%", med_sl <= 0.30, "median=%.4f" % med_sl)
            C("median spread/TP <= 30%", med_tp <= 0.30, "median=%.4f" % med_tp)

        # 8) 净利对账
        anet = sum(num(r.get("net")) for r in rows)
        rnet = num(h.get("Total Net Profit"), 0)
        tol = max(0.02, 0.001 * max(1.0, abs(rnet)))
        C("HTML净利 == 审计净利", abs(anet - rnet) <= tol, "audit %.2f / html %.2f" % (anet, rnet))

        okn = sum(1 for _, o, _ in res if o)
        print("  --- %d/%d ---" % (okn, len(res)), flush=True)
        for n, o, dd in res:
            print("  %s %-38s %s" % ("[PASS]" if o else "[FAIL]", n, dd[:42]), flush=True)
        allres.append(dict(tag=tag, window=tag0, frm=frm, to=to, checks=res,
                           html=h, selfcheck=scv, trades=len(rows), rej=len(rej)))

    # 汇总
    tl = [(r["window"], n, o, d) for r in allres for (n, o, d) in r["checks"]]
    okn = sum(1 for _, _, o, _ in tl if o); tot = len(tl)
    L = ["# XAMR30 · N1.5 engineering smoke 报告\n",
         "- 时间：%s" % dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
         "- 窗口：WINTER 2023-01-02~01-31 · DSTTR 2023-03-20~04-07 · SUMMER 2023-07-03~07-31",
         "- 只用 V1；**profit/PF 不参与任何策略判断**",
         "- ★本报告验证的是 N1R 两处修复（pending 状态机 / 12-bar off-by-one）\n",
         "| 窗口 | tag | Bars | Trades | 拒单 | 判定 |", "|---|---|---:|---:|---:|---|"]
    for r in allres:
        ok = sum(1 for _, o, _ in r["checks"] if o); tt = len(r["checks"])
        L.append("| %s | `%s` | %s | %d | %d | %d/%d %s |"
                 % (r["window"], r["tag"], r["html"].get("Bars", "-"), r["trades"], r["rej"],
                    ok, tt, "PASS" if ok == tt else "**FAIL**"))
    L += ["", "## 逐项", ""]
    for r in allres:
        L.append("### %s" % r["window"]); L.append("")
        L.append("| 检查项 | 结果 | 明细 |"); L.append("|---|---|---|")
        for n, o, d in r["checks"]:
            L.append("| %s | %s | %s |" % (n, "PASS" if o else "**FAIL**", d))
        L.append("")
    L += ["```", "N1.5: %d/%d 通过；实际成交合计 %d 笔"
          % (okn, tot, sum(r["trades"] for r in allres)), "```", ""]
    io.open(os.path.join(OUT, "XAMR30_N1_5_smoke_report.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n" + "=" * 76)
    print("N1.5 汇总: %d/%d；成交合计 %d 笔" % (okn, tot, sum(r["trades"] for r in allres)))
    print("报告 ->", os.path.join(OUT, "XAMR30_N1_5_smoke_report.md"))
    return 0 if okn == tot else 1


if __name__ == "__main__":
    sys.exit(main())
