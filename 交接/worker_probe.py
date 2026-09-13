#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""并行吞吐实测：串行(1) vs 并行(N)，同一批真实任务。用法: python worker_probe.py [N]"""
import os, subprocess, sys, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(HERE)
POOL = os.path.join(BASE_DIR, "mt5workers")
MAIN_DATA = os.path.join(os.environ.get("APPDATA", ""), "MetaQuotes", "Terminal",
                         "53785E099C927DB68A545C249CDBCE06")
MAIN_EXE = r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"
TASKS = [("t%d" % i, {"InpSL_ATR": v})
         for i, v in enumerate(["1.0", "1.5", "2.0", "2.5", "3.0", "3.5"], 1)]
FROM, TO = "2024.08.01", "2025.01.31"


def make_ini(data_dir, tag, params):
    L = ["[Common]", "Login=277335900", "Password=yxqY3lab@",
         "Server=Exness-MT5Trial5", "KeepPrivate=1",
         "[Experts]", "AllowLiveTrading=0", "AllowDllImport=0", "Enabled=1",
         "Account=0", "Profile=0",
         "[Tester]", "Expert=dshtrend\\dsh_BtcSwing", "Symbol=BTCUSDm",
         "Period=M1", "Model=2", "Optimization=0",
         "FromDate=" + FROM, "ToDate=" + TO,
         "ForwardMode=0", "Deposit=300", "Currency=USD", "Leverage=1:200",
         "ExecutionMode=0", "Visual=0", "Report=rep_PROBE_" + tag,
         "ReplaceReport=1", "ShutdownTerminal=1",
         "[TesterInputs]", "InpRunTag=PROBE_" + tag, "InpLatencyMs=300"]
    for k, v in params.items():
        L.append("%s=%s" % (k, v))
    cfg = os.path.join(data_dir, "config")
    os.makedirs(cfg, exist_ok=True)
    p = os.path.join(cfg, "probe_%s.ini" % tag)
    fd = open(p, "w", encoding="utf-8")
    fd.write("\n".join(L) + "\n")
    fd.close()
    return p


def tester_count():
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq metatester64.exe"],
                         capture_output=True, text=True, errors="ignore").stdout
    return out.lower().count("metatester64.exe")


def kill_all():
    for name in ("terminal64.exe", "metatester64.exe"):
        subprocess.run(["taskkill", "/F", "/IM", name], capture_output=True)
    time.sleep(2)


def run_serial(tasks):
    t0 = time.time(); done = {}
    for tag, params in tasks:
        ini = make_ini(MAIN_DATA, tag, params)
        pr = subprocess.Popen([MAIN_EXE, "/config:" + ini]); pr.wait()
        done[tag] = round(time.time() - t0, 1)
    return time.time() - t0, done, 1


def run_parallel(tasks, n):
    t0 = time.time(); done = {}; peak = [0]
    lock = threading.Lock(); queue = list(tasks)
    workers = [os.path.join(POOL, "w%02d" % i) for i in range(1, n + 1)]
    workers = [w for w in workers if os.path.isdir(w)]
    if not workers:
        print("  [错误] worker 池为空"); return time.time() - t0, done, 0

    def loop(wdir):
        while True:
            with lock:
                if not queue:
                    return
                tag, params = queue.pop(0)
            ini = make_ini(wdir, tag, params)
            exe = os.path.join(wdir, "terminal64.exe")
            pr = subprocess.Popen([exe, "/portable", "/config:" + ini])
            while pr.poll() is None:
                c = tester_count()
                with lock:
                    if c > peak[0]:
                        peak[0] = c
                time.sleep(0.4)
            with lock:
                done[tag] = round(time.time() - t0, 1)

    ts = [threading.Thread(target=loop, args=(w,)) for w in workers]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    return time.time() - t0, done, peak[0]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    for label, fn in (("SERIAL", run_serial), ("PARALLEL x%d" % n, None)):
        kill_all()
        print("\n=== %s ===" % label)
        if fn:
            total, done, peak = fn(TASKS)
        else:
            total, done, peak = run_parallel(TASKS, n)
        print("  total %.1f s" % total)
        print("  peak concurrent metatester64 = %d" % peak)
        print("  throughput %.2f tests/min" % (len(TASKS) / total * 60))
        print("  finish times(s): %s" % sorted(done.values()))
    kill_all()


if __name__ == "__main__":
    main()

