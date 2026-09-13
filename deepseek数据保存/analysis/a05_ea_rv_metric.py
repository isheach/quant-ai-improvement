# -*- coding: utf-8 -*-
"""
a05_ea_rv_metric.py
purpose: replicate the EA's EXACT realized-vol metric so we can check whether the
         Vol-Gate thresholds and InpRefVolPct are calibrated correctly.

EA implementation (verified in eva028 source, CalcRealizedVolPoints + UpdateRealizedVol):
    diff_points[i] = (close[i] - close[i+1]) / point        # 1-minute differences, in points
    rv_points      = sqrt( mean(diff_points^2) )            # RMS, over InpVolWindowMinutes bars
    G_RVRatio      = 100 * rv_points * point / price        # == 100 * RMS(price diff)/price  (%)

So G_RVRatio is RMS 1-minute price change as a % of price. NOT scaled by sqrt(n).
Window default InpVolWindowMinutes = 15.  (InpRefVolPct = 0.024)
"""
import glob
import os

import numpy as np
import pandas as pd

M1DIR = r"D:\desktop\新量化策略\旧量化策略\31代数据\eva_data\eva_data\XAUUSDm\m1"
OUT = r"D:\desktop\新量化策略\deepseek数据保存\analysis\out"
os.makedirs(OUT, exist_ok=True)
pd.set_option("display.width", 220)


def section(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


frames = []
for f in sorted(glob.glob(os.path.join(M1DIR, "*.csv"))):
    frames.append(pd.read_csv(f, usecols=["time_iso", "close", "spread"]))
raw = pd.concat(frames, ignore_index=True)
raw["time"] = pd.to_datetime(raw["time_iso"], format="%Y.%m.%d %H:%M:%S", errors="coerce")
raw = raw.dropna(subset=["time"]).drop_duplicates("time").sort_values("time").reset_index(drop=True)
print(f"M1 bars {len(raw)}  {raw.time.min()} .. {raw.time.max()}")

d1 = raw["close"].diff()               # 1-minute price change (USD)

section("1. G_RVRatio exactly as the EA computes it, for each candidate window")
res = {}
for win in [5, 10, 15, 30, 60]:
    rms = d1.rolling(win).apply(lambda x: np.sqrt(np.mean(x ** 2)), raw=True)
    rv_pct = 100 * rms / raw["close"]
    rv_pct = rv_pct.dropna()
    res[win] = rv_pct
    print(f"window={win:>3} min : median={rv_pct.median():.5f}%  "
          f"p5={rv_pct.quantile(.05):.5f}%  p25={rv_pct.quantile(.25):.5f}%  "
          f"p75={rv_pct.quantile(.75):.5f}%  p95={rv_pct.quantile(.95):.5f}%")
res[15].to_frame("rv_pct").to_csv(os.path.join(OUT, "a05_rv_ea_metric_15.csv"), encoding="utf-8-sig")

section("2. is InpRefVolPct = 0.024 (2.4%) a sane reference for this metric?")
rv = res[15]
print(f"EA reference               InpRefVolPct = 0.024 (i.e. 2.4 in the same units as G_RVRatio?)")
print(f"actual median G_RVRatio(15) = {rv.median():.5f}")
print(f"ratio reference/actual      = {0.024/rv.median():.1f}x")
print()
print("!! The input comment says '参考波动%' and the Vol-Gate thresholds are 0.020/0.026.")
print("   If G_RVRatio's natural scale is ~0.029 (median), then a threshold of 0.020 means")
print("   'RV% below 0.020' = below roughly the 10th percentile -> the gate would be OPEN")
print("   almost always, i.e. the Vol-Gate would almost never block the trend side.")
for thr in [0.015, 0.020, 0.024, 0.026, 0.030, 0.040]:
    print(f"   share of minutes with G_RVRatio(15) < {thr:.3f} : {(rv < thr).mean()*100:5.1f}%")

section("3. monthly median G_RVRatio(15) - does the gate do anything across regimes?")
raw["rv"] = res[15]
raw["ym"] = raw.time.dt.to_period("M").astype(str)
mm = raw.groupby("ym")["rv"].agg(["median", lambda s: (s < 0.020).mean() * 100])
mm.columns = ["median_rv_pct", "pct_below_0.020"]
print(mm.round(5).to_string())
mm.to_csv(os.path.join(OUT, "a05_monthly_rv.csv"), encoding="utf-8-sig")

section("4. sanity: how does the Vol-Gate default (enter 0.020 / exit 0.026, N=30) behave?")
rvv = res[15].values
low = True
need = 30
c_low = c_act = 0
state = True
switches = 0
shares = []
for x in rvv:
    if np.isnan(x):
        continue
    if state:                      # currently low
        if x < 0.020:
            c_low += 1
        else:
            c_low = 0
        if c_low >= need:
            state = False; switches += 1; c_low = 0
    else:                          # currently active
        if x > 0.026:
            c_act += 1
        else:
            c_act = 0
        if c_act >= need:
            state = True; switches += 1; c_act = 0
    shares.append(state)
shares = np.array(shares)
print(f"switches over the sample : {switches}")
print(f"share of time in LOW (gate blocking) : {shares.mean()*100:.1f}%")
print(f"share of time ACTIVE                 : {(1-shares.mean())*100:.1f}%")
print("\nFor reference the eva026 audit doc claims 2023-2024 should be mostly gated and")
print("2026 mostly open. Compare the two.")

section("5. the practical question: does the gate separate high-vol from low-vol REGIMES at all?")
raw["gated"] = np.nan
raw.loc[raw["rv"].notna(), "gated"] = shares[:raw["rv"].notna().sum()]
# forward 60-min absolute move as a proxy for 'is this a trending/high-vol moment'
raw["fwd60"] = (raw["close"].shift(-60) - raw["close"]).abs()
gg = raw.dropna(subset=["gated", "fwd60"]).groupby("gated")["fwd60"].agg(["count", "mean", "median"])
print(gg.round(3).to_string())
print("\nIf LOW and ACTIVE have similar forward moves, the gate is not identifying anything")
print("useful and should be replaced by a direct volatility/ATR-based filter.")

print("\ndone ->", OUT)
