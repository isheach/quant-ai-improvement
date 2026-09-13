# -*- coding: utf-8 -*-
"""
a04b_vol_fix.py
purpose: corrected ATR / grid-distance-in-ATR analysis. a04 failed on the M5/M15 resample
         because the m1 CSVs store `time` as a unix-seconds STRING and `time_iso` as the
         human-readable stamp. This version uses time_iso.
output : console report + out/a04b_*.csv
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
    df = pd.read_csv(f, usecols=["time_iso", "open", "high", "low", "close", "spread", "tick_volume"])
    frames.append(df)
raw = pd.concat(frames, ignore_index=True)
raw["time"] = pd.to_datetime(raw["time_iso"], format="%Y.%m.%d %H:%M:%S", errors="coerce")
raw = raw.dropna(subset=["time"]).drop_duplicates(subset=["time"]).sort_values("time").reset_index(drop=True)
print(f"M1 bars: {len(raw)}   span: {raw.time.min()} .. {raw.time.max()}")

section("1. point size verification")
# Exness XAUUSDm has 3 decimals -> point = 0.001
prices = raw["close"]
dec = prices.astype(str).str.split(".").str[-1].str.len().value_counts()
print("decimal places in close:", dec.to_dict())

section("2. ATR(14) per timeframe, in USD and as % of price")
out = {}
for tf, name in [("1min", "M1"), ("5min", "M5"), ("15min", "M15"), ("60min", "H1")]:
    agg = raw.set_index("time").resample(tf).agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    pc = agg["close"].shift()
    tr = pd.concat([agg["high"] - agg["low"],
                    (agg["high"] - pc).abs(),
                    (agg["low"] - pc).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().dropna()
    atr = atr[atr > 0]
    pct = (atr / agg["close"].reindex(atr.index) * 100)
    out[name] = {"median_usd": atr.median(), "mean_usd": atr.mean(),
                 "p5": atr.quantile(.05), "p95": atr.quantile(.95),
                 "median_pct": pct.median()}
    print(f"\n{name}: median ATR={atr.median():.3f} USD ({pct.median():.4f}% of price)   "
          f"p5={atr.quantile(.05):.3f}  p95={atr.quantile(.95):.3f}")
    agg.to_csv(os.path.join(OUT, f"a04b_{name}.csv"), encoding="utf-8-sig")
    atr.to_frame("atr").to_csv(os.path.join(OUT, f"a04b_{name}_atr.csv"), encoding="utf-8-sig")

pd.DataFrame(out).T.round(4).to_csv(os.path.join(OUT, "a04b_atr_table.csv"), encoding="utf-8-sig")

section("3. the legacy grid distance expressed in ATR(M5)  <- the symbol-agnostic unit")
agg5 = raw.set_index("time").resample("5min").agg(
    {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
pc = agg5["close"].shift()
tr5 = pd.concat([agg5["high"] - agg5["low"], (agg5["high"] - pc).abs(), (agg5["low"] - pc).abs()], axis=1).max(axis=1)
atr5 = tr5.rolling(14).mean()
atr5 = atr5[atr5 > 0]

rows = []
for dist in [2.0, 3.0, 4.0, 5.0, 5.514, 6.0, 7.0, 8.0, 10.0]:
    r = dist / atr5
    rows.append({"grid_dist_usd": dist, "xATR_M5_p25": r.quantile(.25),
                 "xATR_M5_median": r.median(), "xATR_M5_p75": r.quantile(.75)})
    print(f"grid dist {dist:>5.3f} USD = {r.median():.2f} x ATR(M5)  (p25={r.quantile(.25):.2f}, p75={r.quantile(.75):.2f})")
pd.DataFrame(rows).round(3).to_csv(os.path.join(OUT, "a04b_grid_in_atr.csv"), index=False, encoding="utf-8-sig")

section("4. spread cost versus candidate stop sizes (the real constraint on a small account)")
ms = raw["spread"].median() / 1000.0
print(f"median spread = {raw['spread'].median():.0f} pts = {ms:.3f} USD   (p90 = {raw['spread'].quantile(.9)/1000:.3f} USD)")
for stop in [2, 3, 4, 5, 6, 8, 10, 15]:
    rt = 2 * ms
    print(f"  stop {stop:>4.1f} USD -> round-trip spread {rt:.2f} USD = {rt/stop*100:5.1f}% of stop   "
          f"| p90 spread -> {2*raw['spread'].quantile(.9)/1000/stop*100:5.1f}% of stop")

section("5. THE ACCOUNT-SIZE BINDING CONSTRAINT")
print("At 0.01 lot on gold: 1 USD price move = 1 USD P&L. Risk per trade = stop_usd * 1.0 * 0.01/0.01")
print("i.e. risk_usd = stop_in_USD  (for 0.01 lot).\n")
for dep in [500, 400]:
    print(f"deposit {dep} USD:")
    for risk_pct in [0.01, 0.02, 0.03, 0.05]:
        allowed = dep * risk_pct
        print(f"   {risk_pct*100:>4.1f}% risk = {allowed:6.2f} USD  -> stop can be at most {allowed:5.2f} USD of gold price")
    print()

print("Compare with the spread floor above: a stop below ~2-3 USD is mostly paying spread.")
print("=> On 500 USD with 0.01 lot you get a usable stop of roughly 3-10 USD, i.e. the")
print("   strategy must be designed so that a 3-10 USD adverse move is a REAL invalidation,")
print("   not noise. A grid that needs 10-40 USD of adverse room cannot run on 500 USD.")

section("6. how often does gold move more than X USD within 60 minutes? (stop-out probability)")
w = raw.set_index("time")["close"]
fwd = w.shift(-60)
mv = (fwd - w).abs()
for x in [2, 3, 4, 5, 6, 8, 10, 15, 20]:
    print(f"  |60min move| > {x:>4.1f} USD in {((mv > x).mean()*100):5.2f}% of minutes")

section("7. how often does gold run X USD without a Y USD retracement? (mean-reversion horizon)")
print("Simplified: distribution of the maximum adverse excursion within the next 240 minutes")
print("(this approximates how deep a fresh grid position goes before it can revert).")
sub = w.iloc[::30]  # sample every 30 min to keep it fast
res = {}
for horizon in [60, 240, 1440]:
    arr = w.values
    idx = np.arange(0, len(arr) - horizon, 30)
    mae = []
    for i in idx[:20000]:
        seg = arr[i + 1:i + 1 + horizon]
        mae.append(seg.min() - arr[i])
    mae = np.array(mae)
    res[horizon] = mae
    print(f"\nhorizon {horizon} min: adverse excursion (USD, negative is against a long)")
    print("  " + "  ".join(f"p{p}={np.percentile(mae, p):.2f}" for p in [5, 25, 50, 75, 95, 99]))

print("\ndone ->", OUT)
