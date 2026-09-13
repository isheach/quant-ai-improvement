#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
build_m1_all.py — 把 eva001 导出的每月 CSV 合并成一个 MT5 可导入文件。

输入：data/eva001_export/<SYM>/m1/YYYY-MM.csv
      （eva001 格式：time,time_iso,open,high,low,close,tick_volume,spread,real_volume）
      ⚠️ time 是 Unix 秒；time_iso 才是可读时间 —— 历史上踩过 1970 年的坑
输出：<out>/<PREFIX>_M1_all.csv
      datetime \t open \t high \t low \t close \t tick_volume \t spread(价格单位)

只保留"实心月"（默认 >= min_kb KB，滤掉 2014~2017 那些 2KB 空壳）。

用法：
  python build_m1_all.py --symbol XAUUSDm --from 2017-04 --to 2026-05
"""
import argparse
import glob
import os
import re
import sys

BASE = r"D:\desktop\新量化策略\deepseek数据保存"
SRC_ROOT = os.path.join(BASE, "data", "eva001_export")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--from", dest="d_from", default="2017-01")
    ap.add_argument("--to", dest="d_to", default="2099-12")
    ap.add_argument("--min-kb", type=float, default=100.0,
                    help="小于此大小的月份视为空壳，丢弃")
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--out-name", default=None)
    args = ap.parse_args()

    src_dir = os.path.join(SRC_ROOT, args.symbol, "m1")
    if not os.path.isdir(src_dir):
        print("ERROR: %s 不存在" % src_dir)
        return 2

    out_dir = args.out_dir or os.path.join(BASE, "data", "m1_all")
    os.makedirs(out_dir, exist_ok=True)
    out_name = args.out_name or ("%s_M1_all.csv" % args.symbol.split("m")[0])
    out_path = os.path.join(out_dir, out_name)

    files = sorted(glob.glob(os.path.join(src_dir, "*.csv")))
    kept, skipped = [], []
    for f in files:
        stem = os.path.splitext(os.path.basename(f))[0]      # YYYY-MM
        if stem < args.d_from or stem > args.d_to:
            skipped.append((stem, "range"))
            continue
        if os.path.getsize(f) / 1024.0 < args.min_kb:
            skipped.append((stem, "shell"))
            continue
        kept.append((stem, f))

    if not kept:
        print("ERROR: 没有可用月份")
        return 3

    n_rows = 0
    n_bad = 0
    prev_t = None
    first_t = last_t = None
    sp_sum = 0.0
    sp_n = 0

    with open(out_path, "w", encoding="utf-8", newline="") as fout:
        for stem, path in kept:
            with open(path, "r", encoding="utf-8-sig", newline="") as fin:
                header = fin.readline()
                if "time_iso" not in header:
                    print("ERROR: %s 缺少 time_iso 列" % path)
                    return 4
                cols = header.rstrip("\n").split(",")
                idx = {c: i for i, c in enumerate(cols)}
                need = ["time_iso", "open", "high", "low", "close",
                        "tick_volume", "spread"]
                if any(c not in idx for c in need):
                    print("ERROR: %s 缺列" % path)
                    return 4

                for line in fin:
                    p = line.rstrip("\n").split(",")
                    if len(p) < len(cols):
                        n_bad += 1
                        continue
                    ts = p[idx["time_iso"]].strip()
                    if len(ts) != 19 or ts[4] != ".":
                        n_bad += 1
                        continue
                    if prev_t is not None and ts <= prev_t:
                        continue
                    try:
                        o = float(p[idx["open"]]); h = float(p[idx["high"]])
                        l = float(p[idx["low"]]);  c = float(p[idx["close"]])
                        v = int(float(p[idx["tick_volume"]]))
                        sp = float(p[idx["spread"]])
                    except (ValueError, IndexError):
                        n_bad += 1
                        continue
                    if sp < 1:
                        sp = 1.0
                    sp_sum += sp; sp_n += 1
                    fout.write("%s\t%.3f\t%.3f\t%.3f\t%.3f\t%d\t%.3f\n"
                               % (ts, o, h, l, c, v, sp * 0.001))
                    n_rows += 1
                    if first_t is None:
                        first_t = ts
                    last_t = ts
                    prev_t = ts

    print("=" * 78)
    print("build_m1_all  symbol=%s" % args.symbol)
    print("  months used : %d  (%s .. %s)" % (len(kept), kept[0][0], kept[-1][0]))
    print("  rows        : %d   bad=%d" % (n_rows, n_bad))
    print("  time range  : %s -> %s" % (first_t, last_t))
    if sp_n:
        print("  spread(pts) : mean %.1f" % (sp_sum / sp_n))
    print("  dropped     : %s" % (", ".join("%s(%s)" % (a, b) for a, b in skipped[:12]) +
                                  (" ..." if len(skipped) > 12 else "")))
    print("  output      : %s  (%.1f MB)" % (out_path, os.path.getsize(out_path) / 1048576.0))
    print("=" * 78)

    # 复制到 MT5 Common\Files\dshtrend\ 供 MQL5 脚本读取
    common = (r"C:\Users\UIC\AppData\Roaming\MetaQuotes\Terminal\Common\Files\dshtrend")
    os.makedirs(common, exist_ok=True)
    dst = os.path.join(common, out_name)
    import shutil
    shutil.copy2(out_path, dst)
    print("  copied -> %s" % dst)
    return 0


if __name__ == "__main__":
    sys.exit(main())
