#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
§四 XAMR30 · 77 个月逐月双品种数据资格证明（Tester-only，独立 date-scoped run）

Gate A: common_session_alignment_ratio >= 99%
Gate B: info_availability_ratio       >= 90%
结构:   dup=0 / non-monotonic=0 / outside_requested_month=0

★每月独立 run tag / 独立输出；不共享结果文件
★不使用长窗口 + iBars 倒推（已证明受缓存污染）
"""
from __future__ import annotations

import csv
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
                      "Common", "Files", "dshtrend", "XAMR30MON")
RAW = os.path.join(OUTDIR, "monthly_raw")

MONTHS = []
y, m = 2018, 1
while (y, m) <= (2024, 5):
    ny, nm = (y, m + 1) if m < 12 else (y + 1, 1)
    MONTHS.append(("%04d%02d" % (y, m),
                   "%04d.%02d.01" % (y, m),
                   "%04d.%02d.01" % (ny, nm)))
    y, m = ny, nm
print("总月数 =", len(MONTHS))


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
        "[Tester]", "Expert=dshtrend\\dsh_XAMR30Monthly", "Symbol=USDJPYm",
        "Period=M30", "Model=2", "Optimization=0",
        "FromDate=" + frm, "ToDate=" + to, "ForwardMode=0",
        "Deposit=500", "Currency=USD", "Leverage=1:200",
        "ExecutionMode=0", "Visual=0",
        "Report=report_XMON_" + tag, "ReplaceReport=1", "ShutdownTerminal=1",
        "[TesterInputs]", "InpRunTag=" + tag, "InpInfoSym=XAUUSDm",
        "InpMonthFrom=" + frm, "InpMonthTo=" + to,
    ]) + "\n"
    p = os.path.join(CFGDIR, "run_XMON_%s.ini" % tag)
    io.open(p, "w", encoding="utf-8").write(txt)
    return p


def main():
    os.makedirs(RAW, exist_ok=True)
    rows = []
    f_out = os.path.join(OUTDIR, "XAMR30_monthly_alignment_v2.csv")
    hdr = ["month", "requested_from", "requested_to", "JPY_M30_bars", "XAU_M30_bars",
           "exact_intersection", "info_availability_ratio", "common_session_alignment_ratio",
           "jpy_dup_ts", "xau_dup_ts", "jpy_non_monotonic", "xau_non_monotonic",
           "first_jpy", "last_jpy", "first_xau", "last_xau",
           "counted_outside_requested_month", "server_utc_offset"]
    of = io.open(f_out, "w", encoding="utf-8", newline="")
    w = csv.writer(of)
    w.writerow(hdr)

    for tag, frm, to in MONTHS:
        ini = make_ini(tag, frm, to)
        kill()
        p = subprocess.Popen([TERMINAL, "/config:" + ini], cwd=os.path.dirname(TERMINAL))
        try:
            p.wait(timeout=600)
        except subprocess.TimeoutExpired:
            kill()
        time.sleep(1.0)
        src = os.path.join(COMMON, "m_%s.txt" % tag)
        got = None
        if os.path.isfile(src):
            txt = io.open(src, encoding="utf-8", errors="ignore").read()
            io.open(os.path.join(RAW, "m_%s.txt" % tag), "w", encoding="utf-8").write(txt)
            for line in txt.splitlines():
                if line.startswith(tag + ","):
                    got = next(csv.reader([line]))
                    break
        if got is None:
            got = [tag, frm, to] + ["ERR"] * (len(hdr) - 3)
        w.writerow(got)
        of.flush()
        rows.append(got)
        try:
            info = float(got[6]); common = float(got[7])
        except Exception:
            info = common = -1.0
        ga = "PASS" if common >= 99.0 else "FAIL"
        gb = "PASS" if info >= 90.0 else "FAIL"
        print("  %s  JPY=%-6s XAU=%-6s inter=%-6s info=%7.2f%% common=%7.2f%%  A=%s B=%s"
              % (tag, got[3], got[4], got[5], info, common, ga, gb), flush=True)

    of.close()
    print("\n->", f_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
