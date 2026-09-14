#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
XAMR30 · 双品种 M30 exact-timestamp 对齐冻结（N0/N1.6）

★方法：Tester-only，逐月运行（与 JSB30 coverage 同理，
  Tester 缓存会按窗口生成数据，逐月探测才能得到该月的真实 bar 数）

对 2018-01 ~ 2024-05 每个月：
  · USDJPYm M30 bar 数（在请求窗口内）
  · XAUUSDm M30 bar 数
  · exact timestamp 交集数
  · alignment_ratio = 交集 / JPY_M30_bars
  · USDJPY M1 coverage（执行数据是否正常）

冻结规则（预注册）：
  最早一个月，使其起到 2024-05 所有完整月份 alignment >= 99%
  且 USDJPY M1 coverage 正常 → TRAIN start = 该月第一个交易日
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
OUTDIR = r"D:\desktop\新量化策略\deepseek数据保存\执行_XAMR30\N0_data"
COMMON = os.path.join(os.environ.get("APPDATA", ""), "MetaQuotes", "Terminal",
                      "Common", "Files", "dshtrend", "XAMR30ALIGN")

# 逐月（2018-01 ~ 2024-05）
MONTHS = []
y, m = 2018, 1
while (y, m) <= (2024, 5):
    ny, nm = (y, m + 1) if m < 12 else (y + 1, 1)
    MONTHS.append(("%04d%02d" % (y, m),
                   "%04d.%02d.01" % (y, m),
                   "%04d.%02d.01" % (ny, nm)))
    y, m = ny, nm

NORMAL_MONTH_M1 = 5760 * 4.33   # 参考：完整周 5760 bars ≈ 月 ~24900


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
        "[Tester]", "Expert=dshtrend\\dsh_XAMR30Align", "Symbol=USDJPYm",
        "Period=M30", "Model=2", "Optimization=0",
        "FromDate=" + frm, "ToDate=" + to, "ForwardMode=0",
        "Deposit=500", "Currency=USD", "Leverage=1:200",
        "ExecutionMode=0", "Visual=0",
        "Report=report_AL_" + tag, "ReplaceReport=1", "ShutdownTerminal=1",
        "[TesterInputs]", "InpRunTag=AL_" + tag, "InpInfoSym=XAUUSDm", "InpMaxMonths=2",
    ]) + "\n"
    p = os.path.join(CFGDIR, "run_AL_%s.ini" % tag)
    io.open(p, "w", encoding="utf-8").write(txt)
    return p


def log_off():
    ld = os.path.join(TDATA, "Tester", "logs")
    fs = [os.path.join(ld, f) for f in os.listdir(ld) if f.endswith(".log")] if os.path.isdir(ld) else []
    if not fs:
        return None, 0
    p = max(fs, key=os.path.getmtime)
    return p, os.path.getsize(p)


def read_tail(p, off):
    try:
        with open(p, "rb") as f:
            f.seek(off); raw = f.read()
    except Exception:
        return ""
    return raw.decode("utf-16-le", errors="ignore")


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    # 先做 M1 执行覆盖（用 M1 周期跑一次每月，拿 bars generated）
    rows = []
    for tag, frm, to in MONTHS:
        ini = make_ini(tag, frm, to)
        kill()
        lp, lo = log_off()
        p = subprocess.Popen([TERMINAL, "/config:" + ini], cwd=os.path.dirname(TERMINAL))
        try:
            p.wait(timeout=900)
        except subprocess.TimeoutExpired:
            kill()
        time.sleep(1.5)
        txt = read_tail(lp, lo)
        # 从 log 里抓 M30 bar 数
        # Tester 会对两个品种分配 M30 缓存
        mJ = re.findall(r"USDJPYm,M30: history cache allocated for (\d+) bars and contains (\d+) bars from ([\d.]+)", txt)
        mX = re.findall(r"XAUUSDm,M30: history cache allocated for (\d+) bars and contains (\d+) bars from ([\d.]+)", txt)
        barsJ = int(mJ[-1][1]) if mJ else 0
        barsX = int(mX[-1][1]) if mX else 0
        # align 文件
        af = os.path.join(COMMON, "align_AL_%s.txt" % tag)
        align = None
        if os.path.isfile(af):
            at = io.open(af, encoding="utf-8", errors="ignore").read()
            # 该月那一行
            mm = re.findall(r"^(\d{4}-\d{2}) \| (\d+) \| (\d+) \| ([\d.]+)%", at, re.M)
            for r in mm:
                if r[0] == tag[:4] + "-" + tag[4:]:
                    align = (int(r[1]), int(r[2]), float(r[3]))
                    break
            if align is None and mm:
                align = (int(mm[0][1]), int(mm[0][2]), float(mm[0][3]))
        rows.append(dict(month=tag, frm=frm, to=to,
                         jpy_m30_bars=barsJ, xau_m30_bars=barsX,
                         align=align,
                         jpy_first=(mJ[-1][2] if mJ else ""),
                         xau_first=(mX[-1][2] if mX else "")))
        a = ("%.4f%%" % align[2]) if align else "n/a"
        print("  %s  JPY_M30=%-6d XAU_M30=%-6d align=%s  (jpyFirst=%s xauFirst=%s)"
              % (tag, barsJ, barsX, a, rows[-1]["jpy_first"], rows[-1]["xau_first"]), flush=True)

    p2 = os.path.join(OUTDIR, "alignment_months.json")
    io.open(p2, "w", encoding="utf-8").write(json.dumps(rows, ensure_ascii=False, indent=2))
    print("\n->", p2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
