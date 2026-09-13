#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
阶段 R2 · BTC C1-R3 train/valid 重跑（GPT 第二批裁定 §三 R2）

使用 P1-R2 已封存的 dsh_BtcSwing 源码/EX5 + SB_R2_500 参数
固定：500 USD / BTCUSDm / Model=2 / ticks=0 / InpAllowMinLotOvershoot=false
  train：2018-02-09 ~ 2024-05-31
  valid：2024-06-01 ~ 2025-05-31
除日期和 run_id 外所有输入完全相同；不改 EA，不增加候选，不跑测试段。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import io

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from r0_guard import guard, register_run, update_status, GuardReject, sha256  # noqa

OUT = os.path.join(HERE, "stage4_candidates_r3")
os.makedirs(OUT, exist_ok=True)
TDATA = os.path.join(os.environ.get("APPDATA", ""), "MetaQuotes", "Terminal",
                     "53785E099C927DB68A545C249CDBCE06")
COMMON = os.path.join(os.environ.get("APPDATA", ""), "MetaQuotes", "Terminal",
                      "Common", "Files", "dshtrend")
RUNROOT = os.path.join(HERE, "runs_r3")
EADIR = os.path.join(BASE, "mql5", "dshtools")
CFGDIR = os.path.join(BASE, "mql5", "config")
TERMINAL = r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"
EA_SRC = os.path.join(EADIR, "dsh_BtcSwing.mq5")
EA_EX5 = os.path.join(TDATA, "MQL5", "Experts", "dshtrend", "dsh_BtcSwing.ex5")

# ★与 SB_R2_500 完全一致的参数（唯一允许变化的只有日期与 run_id）
P = {
    "InpLatencyMs": "0", "InpLatencyTicks": "0",
    "InpWriteAudit": "true", "InpVerboseLog": "false",
    "InpUseDDKill": "false",
    "InpSL_ATR": "1.5", "InpFilterEMA": "200",
    "InpFilterRequireSlope": "false", "InpAllowShort": "true",
    "InpMinLotMaxRiskPct": "2.5", "InpAllowMinLotOvershoot": "false",
}

RUNS = [
    ("DS260913_C1R3_TRAIN", "BTC C1-R3 训练段", "2018.02.09", "2024.05.31", "train"),
    ("DS260913_C1R3_VALID", "BTC C1-R3 验证段", "2024.06.01", "2025.05.31", "valid"),
]


def make_ini(tag, frm, to):
    p = dict(P)
    p["InpRunTag"] = tag
    lines = [
        "[Common]", "Login=277335900", "Server=Exness-MT5Trial5",
        "KeepPrivate=1", "NewsEnable=0", "CertInstall=0",
        "[Experts]", "AllowLiveTrading=0", "AllowDllImport=0",
        "Enabled=1", "Account=0", "Profile=0",
        "[Tester]",
        "Expert=dshtrend\\dsh_BtcSwing", "Symbol=BTCUSDm", "Period=M1",
        "Model=2", "Optimization=0",
        "FromDate=" + frm, "ToDate=" + to,
        "ForwardMode=0", "Deposit=500", "Currency=USD",
        "Leverage=1:200", "ExecutionMode=0", "Visual=0",
        "Report=report_" + tag, "ReplaceReport=1", "ShutdownTerminal=1",
        "[TesterInputs]",
    ]
    lines += ["%s=%s" % (k, v) for k, v in p.items()]
    path = os.path.join(CFGDIR, "run_%s.ini" % tag)
    with io.open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


def kill_mt5():
    subprocess.run(["taskkill", "/F", "/IM", "terminal64.exe"], capture_output=True)
    subprocess.run(["taskkill", "/F", "/IM", "metatester64.exe"], capture_output=True)
    time.sleep(3)


def run_one(run_id, note, frm, to, role):
    print("\n" + "=" * 72)
    print("RUN %s  (%s)  %s ~ %s" % (run_id, note, frm, to))
    print("=" * 72)
    try:
        g = guard(run_id=run_id, symbol="BTCUSDm", frm=frm, to=to, role=role)
    except GuardReject as e:
        print("  X 护栏拒绝: %s" % e)
        return False
    register_run(g, EA_SRC, EA_EX5, notes=note)
    print("  [1] 已登记 planned -> %s" % g["dir"])
    update_status(run_id, "running")
    ini = make_ini(run_id, frm, to)
    kill_mt5()
    print("  [2] 启动 MT5")
    proc = subprocess.Popen([TERMINAL, "/config:" + ini], cwd=os.path.dirname(TERMINAL))
    try:
        proc.wait(timeout=1500)
    except subprocess.TimeoutExpired:
        print("  ! 超时")
        kill_mt5()
    time.sleep(2)
    d = g["dir"]
    got = {}
    for nm, sp in (("ini", ini),
                   ("trades", os.path.join(COMMON, run_id, "trades.csv")),
                   ("signals", os.path.join(COMMON, run_id, "signals.csv")),
                   ("report", os.path.join(TDATA, "report_%s.htm" % run_id))):
        if os.path.isfile(sp):
            dp = os.path.join(d, os.path.basename(sp))
            shutil.copy2(sp, dp)
            got[nm] = dp
    ok = "trades" in got
    update_status(run_id, "done" if ok else "error",
                  trades_path=got.get("trades", ""), trades_sha256=sha256(got.get("trades", "")),
                  signals_path=got.get("signals", ""), signals_sha256=sha256(got.get("signals", "")),
                  report_path=got.get("report", ""), report_sha256=sha256(got.get("report", "")),
                  ini_path=ini, ini_sha256=sha256(ini))
    n = (sum(1 for _ in io.open(got["trades"], encoding="utf-8-sig")) - 1) if ok else 0
    print("  [3] 审计行=%d  报告=%s" % (n, "有" if got.get("report") else "无"))
    return ok


def main():
    for rid, note, frm, to, role in RUNS:
        run_one(rid, note, frm, to, role)
    print("\n完成。产物目录：runs_r3/ 与 %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
