#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MT5 并行 Worker 池（v2 · 混合模式）

================= 实测依据（全部为真机验证过的事实）=================
1. 同一数据目录启第二个 terminal64 → 第二个进程直接退出（单实例检测）
2. 复制"已登录"的数据目录（含 config/accounts.dat、servers.dat）→ **免密登录成功**
   （ini 里的 Password= 不被采用，必须靠克隆凭据文件）
3. `/portable` + 独立数据目录 → 多个 terminal 可**同时存活**并各自出报告
4. MCP 端口 127.0.0.1:22346 冲突（第二个实例报 bind error）→ **无害**，测试照常完成
5. `bases`（1.6GB 行情）用**目录联接**共享 → 4 worker 实占仅 1.5GB
6. ★**真正的瓶颈**：每任务冷启动要重新登录+同步（13–26s），而回测计算只要 3–5s
   → 所以必须让 worker **常驻**，而不是"每任务起停一次"

================= 混合模式 =================
* 批次内：worker **常驻**，逐个任务投喂（只付"回测计算"的钱）
* 批次间：worker **优雅退出**（不留后台进程）
* 隔离：每 worker 独立数据目录 + 独立 report 名 + 独立审计目录
* 队列：SQLite 持久化（pending/running/completed/failed），支持中断恢复
* 并行度：`MAX_PARALLEL_BACKTESTS`（默认 max(1, 逻辑核-2)），可命令行覆盖

用法:
    python pool_v2.py build   --workers 8
    python pool_v2.py run     --inbox inbox_比特币.jsonl --outbox outbox_比特币.jsonl
    python pool_v2.py run     --workers 8 --limit 20
    python pool_v2.py status
    python pool_v2.py reset   --requeue-running
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import shutil
import signal
import sqlite3
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(HERE)
POOL = os.path.join(BASE_DIR, "mt5workers")
DB = os.path.join(HERE, "pool.db")
sys.path.insert(0, os.path.join(BASE_DIR, "run_trend"))

MAIN_DATA = os.path.join(os.environ.get("APPDATA", ""), "MetaQuotes", "Terminal",
                         "53785E099C927DB68A545C249CDBCE06")
INSTALL = r"C:\Program Files\MetaTrader 5 EXNESS"
CRED = os.path.join(BASE_DIR, "mql5", "config", "mt5_account.local.txt")

LOGIN, PASSWORD, SERVER = "277335900", "yxqY3lab@", "Exness-MT5Trial5"

# ==================== ██ 配置区（改这里） ██ ====================
MAX_PARALLEL_BACKTESTS = None      # None → 自动 = max(1, 逻辑核数 - 2)
TASK_TIMEOUT_S = 900               # 单任务超时（秒），超时杀进程记 failed
MAX_RETRIES = 1                    # 失败重试次数
KEEP_WORKERS_WARM = True           # True=批次内常驻（混合模式）；False=每任务起停
# ==============================================================


def cpu_budget():
    n = os.cpu_count() or 4
    return max(1, n - 2)


def read_cred():
    global LOGIN, PASSWORD, SERVER
    if os.path.isfile(CRED):
        for line in open(CRED, encoding="utf-8-sig"):
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                if k.strip() == "LOGIN":
                    LOGIN = v.strip()
                elif k.strip() == "PASSWORD":
                    PASSWORD = v.strip()
                elif k.strip() == "SERVER":
                    SERVER = v.strip()


# ==================== DB ====================
SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
  task_id TEXT PRIMARY KEY,
  payload TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  worker INTEGER,
  tries INTEGER NOT NULL DEFAULT 0,
  started_at REAL, finished_at REAL, runtime REAL,
  result TEXT, error TEXT
);
CREATE INDEX IF NOT EXISTS ix_status ON tasks(status);
"""


def db():
    c = sqlite3.connect(DB, timeout=30)
    c.executescript(SCHEMA)
    return c


def enqueue(conn, tasks):
    n = 0
    for t in tasks:
        tid = t.get("req_id") or t.get("task_id")
        if not tid:
            continue
        cur = conn.execute("SELECT status FROM tasks WHERE task_id=?", (tid,))
        row = cur.fetchone()
        if row and row[0] == "completed":
            continue
        conn.execute(
            "INSERT INTO tasks(task_id,payload,status) VALUES(?,?,'pending') "
            "ON CONFLICT(task_id) DO UPDATE SET payload=excluded.payload,"
            "status=CASE WHEN tasks.status='completed' THEN 'completed' ELSE 'pending' END",
            (tid, json.dumps(t, ensure_ascii=False)))
        n += 1
    conn.commit()
    return n


def claim(conn, worker_id):
    """原子领取一个 pending 任务。"""
    conn.execute("BEGIN IMMEDIATE")
    cur = conn.execute("SELECT task_id,payload FROM tasks WHERE status='pending' "
                       "ORDER BY rowid LIMIT 1")
    row = cur.fetchone()
    if not row:
        conn.commit()
        return None
    conn.execute("UPDATE tasks SET status='running', worker=?, tries=tries+1,"
                 " started_at=? WHERE task_id=?", (worker_id, time.time(), row[0]))
    conn.commit()
    return row[0], json.loads(row[1])


def finish(conn, tid, status, result=None, error=None, t0=None):
    conn.execute("UPDATE tasks SET status=?, result=?, error=?, finished_at=?,"
                 " runtime=? WHERE task_id=?",
                 (status,
                  json.dumps(result, ensure_ascii=False) if result else None,
                  error, time.time(),
                  (time.time() - t0) if t0 else None, tid))
    conn.commit()


# ==================== Worker 池 ====================
class Worker:
    """一个常驻 portable MT5 实例。混合模式：批次内保持存活，批次末退出。"""

    def __init__(self, idx):
        self.idx = idx
        self.dir = os.path.join(POOL, "w%02d" % idx)
        self.exe = os.path.join(self.dir, "terminal64.exe")
        self.proc = None
        self.busy = False
        self.current = None

    def ensure_dir(self):
        os.makedirs(os.path.join(self.dir, "config"), exist_ok=True)

    def submit(self, tag, ini_body):
        """写 ini 并启动一个 terminal 处理它（常驻模式下由 run() 循环调用）。"""
        self.ensure_dir()
        ini = os.path.join(self.dir, "config", "run_%s.ini" % tag)
        with open(ini, "w", encoding="utf-8") as f:
            f.write(ini_body)
        return ini


def build_worker_dir(idx, template, reuse=True):
    w = os.path.join(POOL, "w%02d" % idx)
    if reuse and os.path.isfile(os.path.join(w, "terminal64.exe")):
        return w, "exists"
    os.makedirs(w, exist_ok=True)
    for f in ("terminal64.exe", "metatester64.exe", "MetaEditor64.exe"):
        s = os.path.join(INSTALL, f)
        if os.path.isfile(s):
            shutil.copy2(s, os.path.join(w, f))
    for d in ("config", "MQL5", "logs"):
        s = os.path.join(template, d)
        if os.path.isdir(s):
            shutil.copytree(s, os.path.join(w, d), dirs_exist_ok=True)
    bases = os.path.join(template, "bases")
    if os.path.isdir(bases):
        link = os.path.join(w, "bases")
        if not os.path.exists(link):
            r = subprocess.run(["cmd", "/c", "mklink", "/J", link, bases],
                               capture_output=True, text=True)
            if r.returncode != 0:
                shutil.copytree(bases, link, dirs_exist_ok=True)
    return w, "built"


def cmd_build(args):
    read_cred()
    os.makedirs(POOL, exist_ok=True)
    template = os.path.join(POOL, "template")
    if not os.path.isdir(template) or not os.path.isdir(os.path.join(template, "config")):
        print(">>> 建模板（从主数据目录，排除 Tester 缓存）...")
        os.makedirs(template, exist_ok=True)
        subprocess.run(["robocopy", MAIN_DATA, template, "/E", "/NFL", "/NDL",
                        "/NJH", "/NJS", "/NP",
                        "/XD", os.path.join(MAIN_DATA, "Tester"),
                        os.path.join(MAIN_DATA, "temp")],
                       capture_output=True)
        for f in ("terminal64.exe", "metatester64.exe", "MetaEditor64.exe"):
            s = os.path.join(INSTALL, f)
            if os.path.isfile(s):
                shutil.copy2(s, os.path.join(template, f))
    n = args.workers or cpu_budget()
    t0 = time.time()
    for i in range(1, n + 1):
        _, how = build_worker_dir(i, template, reuse=not args.force)
    print(">>> %d worker 就绪（%.1fs）  池目录: %s" % (n, time.time() - t0, POOL))
    return 0


def cmd_status(args):
    if not os.path.isfile(DB):
        print("无队列数据库")
    else:
        c = db()
        for st, cnt in c.execute("SELECT status, COUNT(*) FROM tasks GROUP BY status"):
            print("  %-10s %d" % (st, cnt))
    ws = []
    if os.path.isdir(POOL):
        ws = sorted(d for d in os.listdir(POOL)
                    if d.startswith("w") and os.path.isdir(os.path.join(POOL, d)))
    print("worker 数 = %d   CPU = %d   MAX_PARALLEL = %s"
          % (len(ws), os.cpu_count(),
             MAX_PARALLEL_BACKTESTS or cpu_budget()))
    return 0


def cmd_reset(args):
    c = db()
    if args.requeue_running:
        c.execute("UPDATE tasks SET status='pending' WHERE status='running'")
        c.commit()
        print("running → pending 已重置")
    if args.retry_failed:
        c.execute("UPDATE tasks SET status='pending' WHERE status='failed'")
        c.commit()
        print("failed → pending 已重置")
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--workers", type=int, default=None)
    b.add_argument("--force", action="store_true")
    r = sub.add_parser("run")
    r.add_argument("--inbox", default=None)
    r.add_argument("--workers", type=int, default=None)
    r.add_argument("--limit", type=int, default=None)
    s = sub.add_parser("status")
    rs = sub.add_parser("reset")
    rs.add_argument("--requeue-running", action="store_true")
    rs.add_argument("--retry-failed", action="store_true")
    a = ap.parse_args()
    if a.cmd == "build":
        return cmd_build(a)
    if a.cmd == "status":
        return cmd_status(a)
    if a.cmd == "reset":
        return cmd_reset(a)
    if a.cmd == "run":
        print("run 由 pool_runner.py 实现（需要与 runexp 集成）")
        return 0


if __name__ == "__main__":
    sys.exit(main())

