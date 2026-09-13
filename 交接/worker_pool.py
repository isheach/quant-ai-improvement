#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MT5 并行回测 Worker Pool（v1）

设计依据（全部为实测结论，见 交接\MT5运行请求协议.md）：
  * 同一数据目录启第二个 terminal64 → 第二个直接退出（单实例检测）
  * 复制已登录的数据目录（含 accounts.dat/servers.dat）→ 免密登录成功
  * `/portable` + 独立数据目录 → 多个 terminal 可同时存活并各自出报告
  * MCP 端口 127.0.0.1:22346 冲突（w2 报 bind error）→ **无害**，测试照常完成
  * ini 里的 `Password=` 不被采用 → **必须靠克隆 accounts.dat 带登录态**

隔离策略（每 worker 一个独立数据目录）：
  小文件独立复制（config / MQL5 / logs / Tester）→ 报告、审计、日志天然不冲突
  `bases`（1.6GB 行情缓存）用**目录联接**共享 → 避免 N×1.6GB 磁盘爆炸

用法:
    python worker_pool.py build  --workers 8      # 建/修 worker 池
    python worker_pool.py status                  # 看池状态
    python worker_pool.py run --workers 8         # 跑队列（并行）
    python worker_pool.py probe --workers 4       # 并行吞吐实测
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(BASE_DIR, "run_trend"))

MAIN_DATA = os.path.join(os.environ.get("APPDATA", ""), "MetaQuotes", "Terminal",
                         "53785E099C927DB68A545C249CDBCE06")
INSTALL = r"C:\Program Files\MetaTrader 5 EXNESS"
POOL = os.path.join(BASE_DIR, "mt5workers")
CRED = os.path.join(BASE_DIR, "mql5", "config", "mt5_account.local.txt")

LOGIN = "277335900"
PASSWORD = "yxqY3lab"
SERVER = "Exness-MT5Trial5"


def read_cred():
    """优先读本机凭据文件；缺失则用内置（demo 账户）。"""
    global LOGIN, PASSWORD, SERVER
    if os.path.isfile(CRED):
        for line in open(CRED, encoding="utf-8-sig"):
            line = line.strip()
            if "=" not in line or line.startswith("#"):
                continue
            k, v = line.split("=", 1)
            if k.strip() == "LOGIN":
                LOGIN = v.strip()
            elif k.strip() == "PASSWORD":
                PASSWORD = v.strip()
            elif k.strip() == "SERVER":
                SERVER = v.strip()


def cpu_budget():
    """默认并行度 = max(1, 逻辑核数 - 2)，给系统/AI/IO 留余量。"""
    n = os.cpu_count() or 4
    return max(1, n - 2)


def mklink(src, dst):
    """建目录联接（junction）—— 需要 dst 不存在。"""
    if os.path.exists(dst):
        return True
    r = subprocess.run(["cmd", "/c", "mklink", "/J", dst, src],
                       capture_output=True, text=True)
    return r.returncode == 0


def build_worker(i, template):
    w = os.path.join(POOL, "w%02d" % i)
    if os.path.isdir(w) and os.path.isfile(os.path.join(w, "terminal64.exe")):
        return w, "exists"

    os.makedirs(w, exist_ok=True)

    # 1) exe 与安装侧目录
    for f in ("terminal64.exe", "metatester64.exe", "MetaEditor64.exe", "Terminal.ico"):
        s = os.path.join(INSTALL, f)
        if os.path.isfile(s):
            shutil.copy2(s, os.path.join(w, f))

    # 2) 从模板复制"小"目录（config/MQL5/logs/Tester）
    for d in ("config", "MQL5", "logs", "Tester"):
        s = os.path.join(template, d)
        if os.path.isdir(s):
            shutil.copytree(s, os.path.join(w, d), dirs_exist_ok=True)

    # 3) bases 用联接共享（省 1.6GB/worker）
    s_bases = os.path.join(template, "bases")
    if os.path.isdir(s_bases):
        if not mklink(s_bases, os.path.join(w, "bases")):
            shutil.copytree(s_bases, os.path.join(w, "bases"), dirs_exist_ok=True)
            return w, "built(bases-copied)"
    return w, "built"


def make_ini(w, i, expert, symbol, d_from, d_to, deposit, params, tag,
             model=2, report=None):
    """每 worker 独立 ini：路径含 worker 号，报告名唯一 → 无冲突。"""
    body = ["[Common]", "Login=" + LOGIN, "Password=" + PASSWORD,
            "Server=" + SERVER, "KeepPrivate=1", "NewsEnable=0", "CertInstall=0",
            "[Experts]", "AllowLiveTrading=0", "AllowDllImport=0", "Enabled=1",
            "Account=0", "Profile=0",
            "[Tester]", "Expert=" + expert, "Symbol=" + symbol, "Period=M1",
            "Model=%d" % model, "Optimization=0",
            "FromDate=" + d_from, "ToDate=" + d_to,
            "ForwardMode=0", "Deposit=" + str(deposit), "Currency=USD",
            "Leverage=1:200", "ExecutionMode=0", "Visual=0",
            "Report=" + (report or ("rep_%s" % tag)), "ReplaceReport=1",
            "ShutdownTerminal=1",
            "[TesterInputs]", "InpRunTag=" + tag]
    for k, v in params.items():
        body.append("%s=%s" % (k, v))
    p = os.path.join(w, "config", "run_%s.ini" % tag)
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(body) + "\n")
    return p


def cmd_build(args):
    read_cred()
    os.makedirs(POOL, exist_ok=True)
    template = os.path.join(POOL, "template")
    if not os.path.isdir(template) or args.rebuild_template:
        print(">>> 从主数据目录建模板（排除 Tester 缓存/temp，约 2.4GB）...")
        os.makedirs(template, exist_ok=True)
        # 用 robocopy：/XD 排除大目录
        subprocess.run(["robocopy", MAIN_DATA, template, "/E", "/NFL", "/NDL",
                        "/NJH", "/NJS", "/NP",
                        "/XD", os.path.join(MAIN_DATA, "Tester"),
                        os.path.join(MAIN_DATA, "temp")],
                       capture_output=True)
        for f in ("terminal64.exe", "metatester64.exe", "MetaEditor64.exe", "Terminal.ico"):
            s = os.path.join(INSTALL, f)
            if os.path.isfile(s):
                shutil.copy2(s, os.path.join(template, f))
        print("    模板就绪")
    n = args.workers or cpu_budget()
    t0 = time.time()
    for i in range(1, n + 1):
        w, how = build_worker(i, template)
        print("    w%02d  %s" % (i, how))
    print(">>> %d 个 worker 就绪，用时 %.1fs" % (n, time.time() - t0))
    print(">>> 磁盘占用: %.1f GB" % (dirsize(POOL) / 1024 ** 3))
    return 0


def dirsize(p):
    tot = 0
    for root, _, files in os.walk(p):
        for f in files:
            try:
                fp = os.path.join(root, f)
                if not os.path.islink(fp):
                    tot += os.path.getsize(fp)
            except OSError:
                pass
    return tot


def cmd_status(args):
    read_cred()
    print("逻辑核 = %d   默认并行度 = %d" % (os.cpu_count(), cpu_budget()))
    if not os.path.isdir(POOL):
        print("worker 池未建立")
        return 0
    ws = sorted(d for d in os.listdir(POOL)
                if d.startswith("w") and os.path.isdir(os.path.join(POOL, d)))
    print("worker 数 = %d" % len(ws))
    for d in ws:
        w = os.path.join(POOL, d)
        ok = os.path.isfile(os.path.join(w, "terminal64.exe"))
        cred = os.path.isfile(os.path.join(w, "config", "accounts.dat"))
        bases = os.path.isdir(os.path.join(w, "bases"))
        print("   %-5s exe=%s accounts=%s bases=%s" % (d, ok, cred, bases))
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--workers", type=int, default=None)
    b.add_argument("--rebuild-template", action="store_true")
    s = sub.add_parser("status")
    p = sub.add_parser("probe")
    p.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    if a.cmd == "build":
        return cmd_build(a)
    if a.cmd == "status":
        return cmd_status(a)
    if a.cmd == "probe":
        print("probe 见 worker_probe.py")
        return 0


if __name__ == "__main__":
    sys.exit(main())
