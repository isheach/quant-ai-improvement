#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
b01_data_audit.py — 审计「两套数据源」的真实可用范围与质量。

两套数据：
  A) 旧项目导出（仅黄金）：旧量化策略\\31代数据\\eva_data\\eva_data\\XAUUSDm\\m1\\*.csv
     2023-01 ~ 2026-06，122.95 万根 M1。**这是 2023-2024 唯一的痕迹。**
  B) 从券商服务器新下载（三品种）：deepseek数据保存\\data\\real\\*_M1_real.csv
     由 dsh_DownloadHistory.mq5 + dsh_ExportRates.mq5 产生。

输出：
  analysis\\out\\b01_data_audit.csv
用法：python b01_data_audit.py
"""
import glob
import os
import sys
import statistics

import pandas as pd

BASE = r"D:\desktop\新量化策略\deepseek数据保存"
LEGACY_GOLD = (r"D:\desktop\新量化策略\旧量化策略\31代数据"
               r"\eva_data\eva_data\XAUUSDm\m1")
REAL_DIR = os.path.join(BASE, "data", "real")
OUT = os.path.join(BASE, "analysis", "out")

# 各品种：point, 0.01 手每 point 的美元价值
SPECS = {
    "XAUUSDm": dict(point=0.001, usd_per_point_001=0.001),
    "BTCUSDm": dict(point=0.01,  usd_per_point_001=0.0001),
    "USDJPYm": dict(point=0.001, usd_per_point_001=0.0064973),
}


def load_legacy_gold():
    files = sorted(glob.glob(os.path.join(LEGACY_GOLD, "*.csv")))
    if not files:
        return None
    parts = []
    for f in files:
        parts.append(pd.read_csv(f, usecols=["time_iso", "open", "high", "low",
                                             "close", "tick_volume", "spread"]))
    df = pd.concat(parts, ignore_index=True)
    df = df.rename(columns={"time_iso": "ts"})
    df["ts"] = pd.to_datetime(df["ts"], format="%Y.%m.%d %H:%M:%S", errors="coerce")
    return df.dropna(subset=["ts"]).reset_index(drop=True)


def load_real(sym):
    p = os.path.join(REAL_DIR, "%s_M1_real.csv" % sym)
    if not os.path.isfile(p):
        return None
    df = pd.read_csv(p, header=None,
                     names=["ts", "open", "high", "low", "close",
                            "tick_volume", "spread"])
    df["ts"] = pd.to_datetime(df["ts"], format="%Y.%m.%d %H:%M:%S", errors="coerce")
    return df.dropna(subset=["ts"]).reset_index(drop=True)


def describe(name, df, sym):
    if df is None or len(df) == 0:
        return None
    sp = SPECS[sym]
    out = {
        "source": name,
        "symbol": sym,
        "bars": len(df),
        "first": df["ts"].min(),
        "last": df["ts"].max(),
        "price_min": round(df["low"].min(), 3),
        "price_max": round(df["high"].max(), 3),
        "spread_pts_median": float(df["spread"].median()),
        "spread_pts_p90": float(df["spread"].quantile(0.90)),
    }
    # 往返点差成本（0.01 手）
    out["roundtrip_cost_usd"] = round(
        2 * out["spread_pts_median"] * sp["usd_per_point_001"], 4)
    # 价格 1% 波动 = 多少美元（0.01 手）
    mid = (out["price_min"] + out["price_max"]) / 2
    one_pct = mid * 0.01
    out["usd_per_1pct_move_001"] = round(one_pct * sp["usd_per_point_001"] / sp["point"], 2)
    out["usd_per_1pct_pct_of_500"] = round(
        out["usd_per_1pct_move_001"] / 500 * 100, 2)
    return out


def main():
    rows = []

    g = load_legacy_gold()
    rows.append(describe("旧项目导出(2023-2026)", g, "XAUUSDm"))

    for sym in ("XAUUSDm", "BTCUSDm", "USDJPYm"):
        rows.append(describe("券商新下载(本次)", load_real(sym), sym))

    rows = [r for r in rows if r]
    df = pd.DataFrame(rows)

    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 50)

    print("=" * 118)
    print("数据源审计（M1）")
    print("=" * 118)
    print(df.to_string(index=False))
    print()

    # ---- 黄金两源的月度覆盖对比 ----
    print("=" * 118)
    print("黄金：两套数据源的月度覆盖对比（根数）")
    print("=" * 118)
    a = g.set_index("ts").resample("MS").size().rename("旧项目导出")
    b = load_real("XAUUSDm").set_index("ts").resample("MS").size().rename("券商新下载")
    cov = pd.concat([a, b], axis=1).fillna(0).astype(int)
    cov.index = cov.index.strftime("%Y-%m")
    print(cov.to_string())
    print()

    # ---- 重叠期一致性检查 ----
    r = load_real("XAUUSDm")
    if g is not None and r is not None:
        lo = max(g["ts"].min(), r["ts"].min())
        hi = min(g["ts"].max(), r["ts"].max())
        if lo < hi:
            ga = g[(g["ts"] >= lo) & (g["ts"] <= hi)].set_index("ts")
            ra = r[(r["ts"] >= lo) & (r["ts"] <= hi)].set_index("ts")
            common = ga.index.intersection(ra.index)
            if len(common) > 0:
                d = (ga.loc[common, "close"] - ra.loc[common, "close"]).abs()
                print("=" * 118)
                print("黄金重叠期一致性（%s ~ %s，%d 根共同 bar）" % (lo, hi, len(common)))
                print("=" * 118)
                print("  收盘价绝对差: 中位 %.4f  均值 %.4f  p95 %.4f  最大 %.4f"
                      % (d.median(), d.mean(), d.quantile(0.95), d.max()))
                print("  旧源点差中位: %.0f 点   新源点差中位: %.0f 点"
                      % (ga.loc[common, "spread"].median(),
                         ra.loc[common, "spread"].median()))
                print()

    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, "b01_data_audit.csv")
    df.to_csv(p, index=False, encoding="utf-8-sig")
    print("saved -> %s" % p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
