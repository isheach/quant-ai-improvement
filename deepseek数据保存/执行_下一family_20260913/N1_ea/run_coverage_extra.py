#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
N1.6R（补）· 对两个"采样到元旦周"的季度补测非假日周

2018Q1 采样 2018.01.01~01.05（元旦周）→ 68.73%
2024Q1 采样 2024.01.01~01.05（元旦周）→ 76.77%
两者都是【节假日】造成的缺口，不是数据不可用。

同时补测 2017Q2（上一轮 96 bars = 1.67%）与 2017Q1 的非假日周，
以确认 2017 上半年的低覆盖是真缺数据而不是采样偏。
"""
from __future__ import annotations

import datetime as dt
import io
import json
import os
import re
import subprocess
import time

TDATA = os.path.join(os.environ.get("APPDATA", ""), "MetaQuotes", "Terminal",
                     "53785E099C927DB68A545C249CDBCE06")
CFGDIR = r"D:\desktop\新量化策略\deepseek数据保存\mql5\config"
TERMINAL = r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"
OUTDIR = r"D:\desktop\新量化策略\deepseek数据保存\执行_下一family_20260913\N1_ea\coverage"

EXTRA = [
    # 避开元旦/圣诞/长假，取常规周
    ("2017Q1b", "2017.02.06", "2017.02.10"),
    ("2017Q2b", "2017.05.08", "2017.05.12"),
    ("2018Q1b", "2018.02.05", "2018.02.09"),
    ("2024Q1b", "2024.02.05", "2024.02.09"),
]
NORMAL_WEEK_BARS = 5760


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
        "[Tester]", "Expert=dshtrend\\dsh_JSB30WeekProbe", "Symbol=USDJPYm",
        "Period=M1", "Model=2", "Optimization=0",
        "FromDate=" + frm, "ToDate=" + to, "ForwardMode=0",
        "Deposit=500", "Currency=USD", "Leverage=1:200",
        "ExecutionMode=0", "Visual=0",
        "Report=report_XC_" + tag, "ReplaceReport=1", "ShutdownTerminal=1",
        "[TesterInputs]", "InpRunTag=" + tag, "InpMaxWeeks=2",
    ]) + "\n"
    p = os.path.join(CFGDIR, "run_XC_%s.ini" % tag)
    io.open(p, "w", encoding="utf-8").write(txt)
    return p


def log_off():
    ld = os.path.join(TDATA, "Tester", "logs")
    fs = [os.path.join(ld, f) for f in os.listdir(ld) if f.endswith(".log")] if os.path.isdir(ld) else []
    if not fs:
        return None, 0
    p = max(fs, key=os.path.getmtime)
    return p, os.path.getsize(p)


def read_gen(p, off):
    try:
        with open(p, "rb") as f:
            f.seek(off); raw = f.read()
    except Exception:
        return None, None
    t = raw.decode("utf-16-le", errors="ignore")
    ms = re.findall(r"USDJPYm,M1:\s*(\d+)\s*ticks,\s*(\d+)\s*bars generated", t)
    return (int(ms[-1][0]), int(ms[-1][1])) if ms else (None, None)


def main():
    res = []
    for tag, frm, to in EXTRA:
        ini = make_ini(tag, frm, to)
        kill()
        lp, lo = log_off()
        p = subprocess.Popen([TERMINAL, "/config:" + ini], cwd=os.path.dirname(TERMINAL))
        try:
            p.wait(timeout=900)
        except subprocess.TimeoutExpired:
            kill()
        time.sleep(1.5)
        tk, bars = read_gen(lp, lo)
        bars = bars or 0
        cov = bars / NORMAL_WEEK_BARS * 100.0
        v = ("normal_continuous" if cov >= 95.0 else
             ("M1_sparse" if cov >= 5.0 else "server_unavailable"))
        res.append(dict(tag=tag, frm=frm, to=to, bars=bars, ticks=tk,
                        coverage_norm_pct=round(cov, 2), verdict=v))
        print("  %-9s %s~%s  bars=%-6d = %6.2f%%  %s" % (tag, frm, to, bars, cov, v))

    p2 = os.path.join(OUTDIR, "coverage_extra.json")
    io.open(p2, "w", encoding="utf-8").write(json.dumps(res, ensure_ascii=False, indent=2))
    print("\n->", p2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
