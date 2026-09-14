#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
§六 XAMR30 Monthly v3 · 四窗口 regression（只验 probe，不是策略实验）

固定四窗口：2018-01 · 2023-01 · 2023-07 · 2024-03
每月必须满足：
  Method A == Method B（完整 timestamp 集合）
  first/last 在 requested month 内
  outside = 0
  0 < monthly_count <= days_in_month * 48
  JPY 月度数量处于合理量级（不能是 1 根，也不能是 12000 根）
★不使用旧 cache count（12477/11817）做 regression target
★三层 diagnostic：Tester journal 的 "bars generated" 另行记录对比
"""
from __future__ import annotations

import calendar
import csv
import datetime as dt
import io
import os
import re
import subprocess
import time

TDATA = os.path.join(os.environ.get("APPDATA", ""), "MetaQuotes", "Terminal",
                     "53785E099C927DB68A545C249CDBCE06")
CFGDIR = r"D:\desktop\新量化策略\deepseek数据保存\mql5\config"
TERMINAL = r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"
OUTDIR = r"D:\desktop\新量化策略\deepseek数据保存\执行_XAMR30\N0_data"
COMMON = os.path.join(os.environ.get("APPDATA", ""), "MetaQuotes", "Terminal",
                      "Common", "Files", "dshtrend", "XAMR30MON3")

WINDOWS = [("2018-01", "2018.01.01", "2018.02.01"),
           ("2023-01", "2023.01.01", "2023.02.01"),
           ("2023-07", "2023.07.01", "2023.08.01"),
           ("2024-03", "2024.03.01", "2024.04.01")]


def kill():
    subprocess.run(["taskkill", "/F", "/IM", "terminal64.exe"], capture_output=True)
    subprocess.run(["taskkill", "/F", "/IM", "metatester64.exe"], capture_output=True)
    time.sleep(2)


def make_ini(tag, frm, to):
    txt = "\n".join([
        "[Common]", "Login=277335900", "Server=Exness-MT5Trial5",
        "KeepPrivate=1", "NewsEnable=0", "CertInstall=0",
        "[Experts]", "AllowLiveTrading=0", "AllowDllImport=0",
        "Enabled=1", "Account=0", "Profile=0",
        "[Tester]", "Expert=dshtrend\\dsh_XAMR30Monthly_v3", "Symbol=USDJPYm",
        "Period=M30", "Model=2", "Optimization=0",
        "FromDate=" + frm, "ToDate=" + to, "ForwardMode=0",
        "Deposit=500", "Currency=USD", "Leverage=1:200",
        "ExecutionMode=0", "Visual=0",
        "Report=report_XM3_" + tag, "ReplaceReport=1", "ShutdownTerminal=1",
        "[TesterInputs]", "InpRunTag=" + tag, "InpInfoSym=XAUUSDm",
        "InpMonthFrom=" + frm, "InpMonthTo=" + to,
    ]) + "\n"
    p = os.path.join(CFGDIR, "run_XM3_%s.ini" % tag.replace("-", "_"))
    io.open(p, "w", encoding="utf-8").write(txt)
    return p


def journal_bars(tag):
    """第三层 diagnostic：从 Tester journal 取该 run 的 bars generated"""
    ld = os.path.join(TDATA, "Tester", "logs")
    if not os.path.isdir(ld):
        return {}
    fs = sorted((os.path.join(ld, f) for f in os.listdir(ld) if f.endswith(".log")),
                key=os.path.getmtime)
    if not fs:
        return {}
    txt = io.open(fs[-1], encoding="utf-16-le", errors="ignore").read()
    out = {}
    for sym in ("USDJPYm", "XAUUSDm"):
        ms = re.findall(re.escape(sym) + r",M30:\s*(\d+)\s*ticks,\s*(\d+)\s*bars generated", txt)
        if ms:
            out[sym] = int(ms[-1][1])
    return out


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    results = []
    for tag, frm, to in WINDOWS:
        ini = make_ini(tag, frm, to)
        kill()
        p = subprocess.Popen([TERMINAL, "/config:" + ini], cwd=os.path.dirname(TERMINAL))
        try:
            p.wait(timeout=900)
        except subprocess.TimeoutExpired:
            kill()
        time.sleep(1.5)
        src = os.path.join(COMMON, "m3_%s.txt" % tag)
        row = None
        hdr = None
        if os.path.isfile(src):
            txt = io.open(src, encoding="utf-8", errors="ignore").read()
            lines = [l for l in txt.splitlines() if l.strip()]
            if len(lines) >= 2:
                hdr = next(csv.reader([lines[0]]))
                row = next(csv.reader([lines[1]]))
        jb = journal_bars(tag)

        y, m = int(tag[:4]), int(tag[5:])
        days = calendar.monthrange(y, m)[1]
        cap = days * 48
        ok = []
        det = {}
        if row is None:
            ok.append(("probe 输出存在", False, "无输出"))
            row = {}
            hdr = []
        else:
            d = dict(zip(hdr, row))
            det = d
            pv = d.get("probe_valid") == "1"
            ok.append(("probe_valid=1", pv, "reason=%s" % d.get("invalid_reason", "")))
            ok.append(("MethodA==MethodB (JPY)", d.get("methodA_methodB_jpy_equal") == "1",
                       "A=%s B=%s" % (d.get("methodA_jpy_count"), d.get("methodB_jpy_count"))))
            ok.append(("MethodA==MethodB (XAU)", d.get("methodA_methodB_xau_equal") == "1",
                       "A=%s B=%s" % (d.get("methodA_xau_count"), d.get("methodB_xau_count"))))
            ok.append(("outside=0", d.get("outside_requested_month") == "0",
                       "outside=%s" % d.get("outside_requested_month")))
            ok.append(("dup=0", d.get("jpy_dup") == "0" and d.get("xau_dup") == "0",
                       "jpy=%s xau=%s" % (d.get("jpy_dup"), d.get("xau_dup"))))
            ok.append(("non-monotonic=0", d.get("jpy_non_monotonic") == "0"
                       and d.get("xau_non_monotonic") == "0",
                       "jpy=%s xau=%s" % (d.get("jpy_non_monotonic"), d.get("xau_non_monotonic"))))
            jc = int(d.get("JPY_M30_bars") or 0)
            ok.append(("0 < JPY_monthly <= days*48", 0 < jc <= cap, "jpy=%d cap=%d" % (jc, cap)))
            ok.append(("JPY 量级合理 (500~4000)", 500 <= jc <= 4000, "jpy=%d" % jc))
            xc = int(d.get("XAU_M30_bars") or 0)
            ok.append(("0 < XAU_monthly <= days*48", 0 < xc <= cap, "xau=%d cap=%d" % (xc, cap)))

        results.append(dict(tag=tag, frm=frm, to=to, det=det, ok=ok, jb=jb, cap=cap))
        npass = sum(1 for _, o, _ in ok if o)
        print("  %-8s %d/%d %s  jpy=%-5s xau=%-5s info=%-8s common=%-8s  journalJPY=%s"
              % (tag, npass, len(ok), "PASS" if npass == len(ok) else "FAIL",
                 det.get("JPY_M30_bars"), det.get("XAU_M30_bars"),
                 det.get("info_availability_ratio"), det.get("common_session_alignment_ratio"),
                 jb.get("USDJPYm", "?")), flush=True)
        for n, o, dd in ok:
            if not o:
                print("       [FAIL] %-34s %s" % (n, dd), flush=True)

    tot = sum(1 for r in results for _, o, _ in r["ok"] if o)
    all_n = sum(len(r["ok"]) for r in results)
    print("\nregression: %d/%d  → %s" % (tot, all_n, "ALL PASS" if tot == all_n else "NOT ALL PASS"))

    # 三层 diagnostic 差异记录
    print("\n=== 三层 diagnostic：journal 'bars generated' vs 过滤后月度 count ===")
    diffs = []
    for r in results:
        d = r["det"]
        jb = r["jb"].get("USDJPYm")
        jc = int(d.get("JPY_M30_bars") or 0)
        diff = (jb - jc) if isinstance(jb, int) else None
        diffs.append(dict(month=r["tag"], journal_jpy_bars=jb, filtered_monthly_jpy=jc, diff=diff))
        print("  %-8s journal=%-6s filtered=%-6s diff=%s" % (r["tag"], jb, jc, diff))

    # 写四窗口 regression 报告数据
    io.open(os.path.join(OUTDIR, "v3_regression.json"), "w", encoding="utf-8").write(
        __import__("json").dumps([{k: v for k, v in r.items() if k != "det"} | {"det": r["det"]}
                                  for r in results], ensure_ascii=False, indent=2))
    io.open(os.path.join(OUTDIR, "v3_journal_vs_filtered.json"), "w", encoding="utf-8").write(
        __import__("json").dumps(diffs, ensure_ascii=False, indent=2))
    return 0 if tot == all_n else 1


if __name__ == "__main__":
    raise SystemExit(main())
