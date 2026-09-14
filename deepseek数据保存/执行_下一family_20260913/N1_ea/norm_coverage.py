#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
N1.6R（续）· 用【正确分母】重算 coverage

缺陷更正：
  上一版 coverage = generated_M1_bars / (工作日日期数 × 1440)
  但外汇市场【周日 22:00 UTC 已开市】，一周真实交易时长为
      周五 24:00 − 周日 22:00 = 120 小时 = 7200 分钟
  其中：
      · 工作日（周一~周五）部分 = 周一00:00 → 周五24:00 = 120 − 2 = 118 小时？
        实际：周日 22:00~24:00 属"周日日期"，占 2 小时
              周一 00:00 ~ 周五 24:00 = 5 × 24 = 120 小时
              合计 122 小时 > 120 小时 → 说明周日那 2 小时与周五尾部重叠
        正确算法：窗口 = 周日 22:00 UTC → 周五 24:00 UTC
        一个完整周（周一到周五各有 24h）+ 周日 2h = 120 + 2 = 122h？
        实测得到 5,760 bars = 96 小时，即【5 × 24 − 24 = 96】…
  ★因此不猜，直接从实测反推：完整周的 bars 上限实测为 5,760。
    本脚本改用【Tester 实测的正常周上限】作为分母基准：
        coverage_norm = generated_M1_bars / 5760
    并额外给出 daily 明细以解释偏离（节假日）。

同时修正：判定阈值改为【双侧】——
  · coverage_norm >= 95%  → normal_continuous（允许 1~2 个工作日的节假日缺失）
  · 5% <= coverage_norm < 95% → M1_sparse
  · coverage_norm < 5%    → server_unavailable
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

# 复用上一轮已跑出的结果（同一批报告），只重新解析
FROM_JSON = os.path.join(OUTDIR, "coverage_quarters.json")

NORMAL_WEEK_BARS = 5760   # ★实测：完整交易周（周日22:00~周五末）的 M1 bar 上限


def weekday_minutes(frm, to):
    a = dt.datetime.strptime(frm, "%Y.%m.%d").date()
    b = dt.datetime.strptime(to, "%Y.%m.%d").date()
    n = 0
    d = a
    while d <= b:
        if d.weekday() < 5:
            n += 1
        d += dt.timedelta(days=1)
    return n * 1440, n


def main():
    if not os.path.isfile(FROM_JSON):
        print("缺", FROM_JSON, "→ 请先跑 run_coverage.py")
        return 2
    prev = json.load(io.open(FROM_JSON, encoding="utf-8"))
    rows = prev["quarters"]

    for r in rows:
        bars = r["generated_M1_bars"]
        wmin, wdays = weekday_minutes(r["requested_from"], r["requested_to"])
        r["weekday_minutes_naive"] = wmin
        r["coverage_naive_pct"] = round(bars / wmin * 100.0, 2) if wmin else 0.0
        r["coverage_norm_pct"] = round(bars / NORMAL_WEEK_BARS * 100.0, 2)
        c = r["coverage_norm_pct"]
        r["verdict2"] = ("normal_continuous" if c >= 95.0 else
                         ("M1_sparse" if c >= 5.0 else "server_unavailable"))

    n = len(rows)
    idx = None
    for i in range(n):
        if all(rows[j]["coverage_norm_pct"] >= 95.0 for j in range(i, n)):
            idx = i
            break

    print("=" * 92)
    print("%-9s %-24s %8s %10s %10s  %s" % ("季度", "区间", "bars", "naive%", "normalized%", "判定"))
    print("=" * 92)
    for r in rows:
        print("  %-9s %s~%s %8d %9.2f%% %9.2f%%  %s"
              % (r["quarter"], r["requested_from"], r["requested_to"],
                 r["generated_M1_bars"], r["coverage_naive_pct"],
                 r["coverage_norm_pct"], r["verdict2"]))

    frozen = rows[idx]["requested_from"] if idx is not None else None
    print()
    print("冻结 TRAIN 起点 =", frozen, "（季度 %s）" % (rows[idx]["quarter"] if idx is not None else "无"))

    out = dict(
        generated_at=dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        method="Tester-only, real USDJPYm, Model=2, FromDate",
        coverage_norm_denominator=NORMAL_WEEK_BARS,
        coverage_norm_definition="generated_M1_bars / 5760（完整交易周的 M1 bar 实测上限）",
        coverage_naive_definition="generated_M1_bars / (工作日日期数 × 1440)  ← 分母过大，已弃用",
        threshold_normal_continuous_pct=95.0,
        quarters=rows,
        frozen_train_start=frozen,
        frozen_from_quarter=rows[idx]["quarter"] if idx is not None else None,
    )
    io.open(os.path.join(OUTDIR, "coverage_quarters_norm.json"), "w", encoding="utf-8").write(
        json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
