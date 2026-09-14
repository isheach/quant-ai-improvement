#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
N1R2 · A 阶段第二层：历史 Tester 时间实测

GPT 裁定：不能再用"周日固定 22:00 UTC 开市"反推 server offset。
改为直接读【真实 USDJPYm、Strategy Tester】的历史 bar 时间戳，
判断 Tester timestamp 是否已经是 UTC+0。

四个时段：2023-01（冬令）/ 2023-03（DST 附近）/ 2023-07（夏令）/ 2023-11（回到冬令）
"""
from __future__ import annotations

import io
import os
import re
import subprocess
import time

TDATA = os.path.join(os.environ.get("APPDATA", ""), "MetaQuotes", "Terminal",
                     "53785E099C927DB68A545C249CDBCE06")
CFGDIR = r"D:\desktop\新量化策略\deepseek数据保存\mql5\config"
TERMINAL = r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"
OUTDIR = r"D:\desktop\新量化策略\deepseek数据保存\执行_下一family_20260913\N1_ea\time_probe"
COMMON = os.path.join(os.environ.get("APPDATA", ""), "MetaQuotes", "Terminal",
                      "Common", "Files", "dshtrend", "JSB30TIME")

PERIODS = [
    ("P2023_01_JAN", "2023.01.02", "2023.02.05"),
    ("P2023_03_DST", "2023.03.06", "2023.04.09"),
    ("P2023_07_JUL", "2023.07.03", "2023.08.06"),
    ("P2023_11_NOV", "2023.10.30", "2023.12.03"),
]


def kill():
    subprocess.run(["taskkill", "/F", "/IM", "terminal64.exe"], capture_output=True)
    subprocess.run(["taskkill", "/F", "/IM", "metatester64.exe"], capture_output=True)
    time.sleep(3)


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
        "Report=report_WEEKPROBE_" + tag, "ReplaceReport=1", "ShutdownTerminal=1",
        "[TesterInputs]", "InpRunTag=" + tag, "InpMaxWeeks=40",
    ]) + "\n"
    p = os.path.join(CFGDIR, "run_WEEKPROBE_%s.ini" % tag)
    io.open(p, "w", encoding="utf-8").write(txt)
    return p


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    res = {}
    for tag, frm, to in PERIODS:
        print("=" * 70)
        print("WEEKPROBE %s  %s ~ %s" % (tag, frm, to))
        ini = make_ini(tag, frm, to)
        kill()
        proc = subprocess.Popen([TERMINAL, "/config:" + ini], cwd=os.path.dirname(TERMINAL))
        try:
            proc.wait(timeout=900)
        except subprocess.TimeoutExpired:
            print("  ! 超时"); kill()
        time.sleep(2)
        src = os.path.join(COMMON, "week_probe_%s.txt" % tag)
        if os.path.isfile(src):
            txt = io.open(src, encoding="utf-8", errors="ignore").read()
            res[tag] = txt
            print(txt[:2600])
            io.open(os.path.join(OUTDIR, "week_probe_%s.txt" % tag), "w", encoding="utf-8").write(txt)
        else:
            print("  ! 未生成", src)
            # 回退：worker 沙盒
            for root, ds, fs in os.walk(os.path.join(os.environ["APPDATA"], "MetaQuotes", "Tester")):
                for f in fs:
                    if f == "week_probe_%s.txt" % tag:
                        p2 = os.path.join(root, f)
                        txt = io.open(p2, encoding="utf-8", errors="ignore").read()
                        res[tag] = txt
                        print(txt[:2600])
                        io.open(os.path.join(OUTDIR, "week_probe_%s.txt" % tag), "w", encoding="utf-8").write(txt)
                        break
    print("\n完成，结果目录:", OUTDIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
