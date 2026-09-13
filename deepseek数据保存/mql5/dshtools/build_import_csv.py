#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
build_import_csv.py  —  DeepSeek 新量化策略

把旧项目 42 个月的 XAUUSDm M1 CSV（每月一文件）合并成一份 MT5 CustomRatesUpdate
可直接消费的导入文件。

输入 : 旧量化策略\\31代数据\\eva_data\\eva_data\\XAUUSDm\\m1\\YYYY-MM.csv
       列: time,time_iso,open,high,low,close,tick_volume,spread,real_volume
       - time       = Unix 秒（字符串）※ 不要用，历史上踩过 1970 年 bug
       - time_iso   = "2023.01.02 23:01:00" ← 用这一列
       - spread     = 点数(int)，200 = $0.20（品种 3 位小数 → 1 point = $0.001）

输出 : MT5 可读的制表符分隔文件
       列: datetime \t open \t high \t low \t close \t tick_volume \t spread(price units)

设计约束（重要）：
  * EA（eva028）完全靠 SymbolInfoDouble 推导 点值/手数 缩放，不硬编码品种名。
    所以自定义品种只要 **合约规格与 XAUUSDm 一致**（100 oz / 3 位小数 / 最小手 0.01），
    导入真实价位的 CSV 后，其美元行为与 XAUUSDm 完全一致（0.01 手 = 1 oz → $1 波动 = $1）。
  * 价差：CSV 里的 spread 是「历史点位」，直接保留；另外允许用 --fixed-spread 覆盖。
    （custom symbol 的 tester 用固定点差；用历史中是位数 200 点更贴合旧项目口径。）

用法：
  python build_import_csv.py --out-dir <目录> [--fixed-spread 200] [--from 2023-01] [--to 2026-06]
"""
import argparse
import csv
import os
import sys
import glob

LEGACY_DIR = r"D:\desktop\新量化策略\旧量化策略\31代数据\eva_data\eva_data\XAUUSDm\m1"

FIELDS = ["time", "time_iso", "open", "high", "low", "close",
          "tick_volume", "spread", "real_volume"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=LEGACY_DIR, help="legacy m1 CSV directory")
    ap.add_argument("--out-dir", required=True, help="output directory")
    ap.add_argument("--out-name", default="XAUUSD_HIST_M1.csv")
    ap.add_argument("--fixed-spread", type=float, default=None,
                    help="override spread in POINTS (e.g. 200). If unset, use each row's spread.")
    ap.add_argument("--spread-floor", type=float, default=2.0,
                    help="minimum spread in points (legacy rows sometimes have 0)")
    ap.add_argument("--from", dest="d_from", default=None, help="YYYY-MM inclusive")
    ap.add_argument("--to", dest="d_to", default=None, help="YYYY-MM inclusive")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.src, "*.csv")))
    if not files:
        print("ERROR: no csv found in %s" % args.src)
        return 2

    kept = []
    for f in files:
        stem = os.path.splitext(os.path.basename(f))[0]   # YYYY-MM
        if args.d_from and stem < args.d_from:
            continue
        if args.d_to and stem > args.d_to:
            continue
        kept.append((stem, f))

    os.makedirs(args.out_dir, exist_ok=True)
    out_path = os.path.join(args.out_dir, args.out_name)

    n_rows = 0
    n_bad = 0
    n_gap_dup = 0
    first_t = last_t = None
    prev_t = None
    spread_sum = 0.0
    spread_n = 0
    spread_min = 1e18
    spread_max = -1e18
    price_min = 1e18
    price_max = -1e18

    with open(out_path, "w", encoding="utf-8", newline="") as fout:
        for stem, path in kept:
            with open(path, "r", encoding="utf-8-sig", newline="") as fin:
                rdr = csv.DictReader(fin)
                missing = [c for c in FIELDS if c not in (rdr.fieldnames or [])]
                if missing:
                    print("ERROR: %s missing columns %s" % (path, missing))
                    return 3
                for row in rdr:
                    tstr = (row.get("time_iso") or "").strip()
                    if len(tstr) != 19 or tstr[4] != "." or tstr[13] != ":":
                        n_bad += 1
                        continue
                    if prev_t is not None and tstr <= prev_t:
                        n_gap_dup += 1
                        continue
                    try:
                        o = float(row["open"]); h = float(row["high"])
                        l = float(row["low"]);  c = float(row["close"])
                        v = int(float(row["tick_volume"]))
                        sp = float(row["spread"])
                    except (TypeError, ValueError):
                        n_bad += 1
                        continue

                    if args.fixed_spread is not None:
                        sp = args.fixed_spread
                    if sp < args.spread_floor:
                        sp = args.spread_floor

                    spread_sum += sp
                    spread_n += 1
                    spread_min = min(spread_min, sp)
                    spread_max = max(spread_max, sp)
                    price_min = min(price_min, l)
                    price_max = max(price_max, h)

                    # spread 由「点」换算成「价格单位」：point = 0.001
                    sp_price = sp * 0.001

                    fout.write("%s\t%.3f\t%.3f\t%.3f\t%.3f\t%d\t%.3f\n"
                               % (tstr, o, h, l, c, v, sp_price))
                    n_rows += 1
                    if first_t is None:
                        first_t = tstr
                    last_t = tstr
                    prev_t = tstr

    print("=" * 72)
    print("build_import_csv")
    print("  months used      : %d  (%s .. %s)" % (len(kept), kept[0][0], kept[-1][0]))
    print("  rows written     : %d" % n_rows)
    print("  skipped (bad)    : %d" % n_bad)
    print("  skipped (dup/ord): %d" % n_gap_dup)
    if n_rows:
        print("  time range       : %s  ->  %s" % (first_t, last_t))
        print("  price range      : %.3f  ->  %.3f" % (price_min, price_max))
        print("  spread(points)   : min %.0f  median-ish mean %.1f  max %.0f"
              % (spread_min, spread_sum / spread_n, spread_max))
    print("  output           : %s  (%.1f MB)"
          % (out_path, os.path.getsize(out_path) / 1048576.0))
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
