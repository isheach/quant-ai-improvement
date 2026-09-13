# -*- coding: utf-8 -*-
"""
a04_vol_characterization.py
purpose: characterize XAUUSDm M1 data (the authoritative Exness point data we have)
         so the new design can be stated in SYMBOL-AGNOSTIC units (ATR multiples and
         % of price) instead of hard-coded point counts. This is the prerequisite for
         extending to BTCUSD and USDJPY.
input : legacy eva_data XAUUSDm m1/*.csv (one file per month)
output: console report + out/a04_*.csv
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


files = sorted(glob.glob(os.path.join(M1DIR, "*.csv")))
print(f"m1 files: {len(files)}  ({os.path.basename(files[0])} .. {os.path.basename(files[-1])})")

# inspect header
head = pd.read_csv(files[0], nrows=5)
print("\ncolumns:", list(head.columns))
print(head.to_string())

frames = []
for f in files:
    df = pd.read_csv(f)
    # normalise time column
    tcol = [c for c in df.columns if c.lower() in ("time", "date", "datetime", "timestamp")][0]
    df = df.rename(columns={tcol: "time"})
    frames.append(df)
raw = pd.concat(frames, ignore_index=True)
print(f"\ntotal M1 bars: {len(raw)}")

raw["time"] = pd.to_datetime(raw["time"], errors="coerce")
raw = raw.dropna(subset=["time"]).sort_values("time").reset_index(drop=True)
raw = raw.drop_duplicates(subset=["time"])

# infer point size from price magnitude (gold ~ 2000-4000)
px = float(raw["close"].iloc[0])
print(f"first close = {px}")
print(f"price range: {raw['close'].min():.2f} .. {raw['close'].max():.2f}")

section("1. is the data really 1-minute, and what is the spread field?")
dt = raw["time"].diff().dt.total_seconds()
print(dt.value_counts().head(8).to_string())
if "spread" in raw.columns:
    print("\nspread column stats (broker points):")
    print(raw["spread"].describe(percentiles=[.1, .5, .9, .99]).round(2).to_string())

section("2. price level over time (this matters: the legacy model references InpRefPrice=4000)")
yr = raw.groupby(raw.time.dt.year)["close"].agg(["first", "last", "min", "max", "mean"])
print(yr.round(2).to_string())

section("3. per-bar range in % of price = the natural volatility unit")
raw["range_pct"] = (raw["high"] - raw["low"]) / raw["close"] * 100
print(raw["range_pct"].describe(percentiles=[.5, .75, .9, .95, .99]).round(4).to_string())

section("4. realized vol by timeframe: 15min / 60min window (matches EA InpVolWindowMinutes=15)")
g = raw.set_index("time")
r1 = np.log(g["close"]).diff()

for win, label in [(15, "15min"), (60, "60min"), (240, "4h"), (1440, "1d")]:
    v = r1.rolling(win).std()
    # scale to a % move over the window
    vpct = v * np.sqrt(win) * 100
    vpct = vpct.dropna()
    print(f"\n{label} window: RV% (std of logret * sqrt(n) * 100)")
    print(vpct.describe(percentiles=[.05, .25, .5, .75, .95]).round(4).to_string())
    if win == 15:
        vpct.to_frame("rv_pct_15m").to_csv(os.path.join(OUT, "a04_rv_15m.csv"), encoding="utf-8-sig")

section("5. ATR(14) on M1 and M5, in USD and in % of price  <= the unit we should design in")
for tf_min, tfname in [(1, "M1"), (5, "M5"), (15, "M15")]:
    if tf_min == 1:
        h, l, c = raw["high"], raw["low"], raw["close"]
    else:
        agg = raw.set_index("time").resample(f"{tf_min}min").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
        h, l, c = agg["high"], agg["low"], agg["close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().dropna()
    atr_pct = atr / c.loc[atr.index] * 100
    print(f"\n{tfname} ATR(14): mean={atr.mean():.3f} USD  "
          f"median={atr.median():.3f} USD  = {atr_pct.median():.4f}% of price")
    print(f"   percentiles 5/50/95 USD: "
          f"{atr.quantile(.05):.3f} / {atr.median():.3f} / {atr.quantile(.95):.3f}")

section("6. what the legacy grid distance actually equals, in ATR(M5) units")
# legacy median grid dist = 5514 pts = 5.514 USD
agg5 = raw.set_index("time").resample("5min").agg(
    {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
tr = pd.concat([agg5["high"] - agg5["low"],
                (agg5["high"] - agg5["close"].shift()).abs(),
                (agg5["low"] - agg5["close"].shift()).abs()], axis=1).max(axis=1)
atr5 = tr.rolling(14).mean().dropna()
for dist_usd in [2.0, 4.0, 5.514, 7.0, 8.0]:
    r = dist_usd / atr5
    print(f"grid dist {dist_usd:>5.3f} USD = {r.median():.2f} x ATR(M5)   "
          f"(p25={r.quantile(.25):.2f}, p75={r.quantile(.75):.2f})")

section("7. KEY DESIGN NUMBER: a 1 USD gold move = 1 USD P&L per 0.01 lot")
print("BTC and JPY do NOT have that convenient 1:1 property. Contract sizes:")
print("  XAUUSD  0.01 lot = 1 oz      -> 1.00 USD per 1.00 USD price move")
print("  BTCUSD  depends on broker contract (1 BTC / 0.01 lot typical) -> 1.00 USD per 1 USD move")
print("          but BTC daily range is ~2-4% of price vs gold ~1%; so 0.01 lot BTC carries")
print("          ~2-4x the per-trade dollar risk of 0.01 lot gold at the same % stop.")
print("  USDJPY  0.01 lot = 1000 units -> 1 pip(0.01 JPY) ~= 0.067 USD; ATR is small in USD")
print("          terms, so JPY is the LOW-risk leg and needs a larger lot to matter.")
print("\n=> The three instruments need a NORMALISED risk unit, not a shared point grid.")

section("8. realistic spread cost as % of a reasonable stop, per symbol class")
med_spread_pts = raw["spread"].median() if "spread" in raw.columns else np.nan
print(f"XAUUSDm median spread from data: {med_spread_pts} points = {med_spread_pts/1000:.3f} USD")
for stop_usd in [2, 4, 6, 10]:
    cost = 2 * med_spread_pts / 1000
    print(f"  stop {stop_usd:>5.1f} USD -> round-trip spread cost {cost:.2f} USD = {cost/stop_usd*100:.1f}% of stop")
print("\n=> If the stop is too tight the spread eats the edge. This sets a FLOOR on stop size")
print("   and therefore, together with the account size, sets the maximum lot you can use.")

print("\ndone ->", OUT)
