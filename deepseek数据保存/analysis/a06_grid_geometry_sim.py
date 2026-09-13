# -*- coding: utf-8 -*-
"""
a06_grid_geometry_sim.py
purpose: THE decisive question for this project.

The legacy grid earns its money by holding deeply underwater positions until they
revert (63% of trades were >= $3 underwater; 54% of those still turned green), and it
carries a $667 realized drawdown to earn $695 net. On a 500 USD account with the 0.01
lot floor you CANNOT hold that deep. So: if we cap the basket at a level a 500 USD
account can survive (say 15-20 USD), does the reversion edge survive, or does the cap
destroy it?

Method: a transparent event-driven simulation on real XAUUSDm M1 bars.
  - baseline = trailing mean of the last X minutes of closes
  - entry: price deviates >= grid_dist from baseline -> open in the reversion direction
    (buy when below baseline, sell when above) -- this mirrors the legacy logic
  - basket take-profit: close all when price returns to baseline (legacy behaviour)
  - basket stop: when total basket P&L <= -basket_cap, close all and block re-entry
    for cooldown minutes
  - 0.01 lot on gold => 1 USD P&L per 1 USD of price movement per position

We sweep grid_dist (in USD) x basket_cap (in USD) and report net, max drawdown,
trade count, and win rate. This is the single most informative table for the new design.
"""
import glob
import os

import numpy as np
import pandas as pd

M1DIR = r"D:\desktop\新量化策略\旧量化策略\31代数据\eva_data\eva_data\XAUUSDm\m1"
OUT = r"D:\desktop\新量化策略\deepseek数据保存\analysis\out"
os.makedirs(OUT, exist_ok=True)


def load_prices():
    frames = []
    for f in sorted(glob.glob(os.path.join(M1DIR, "*.csv"))):
        frames.append(pd.read_csv(f, usecols=["time_iso", "close", "high", "low"]))
    d = pd.concat(frames, ignore_index=True)
    d["time"] = pd.to_datetime(d["time_iso"], format="%Y.%m.%d %H:%M:%S", errors="coerce")
    d = d.dropna(subset=["time"]).drop_duplicates("time").sort_values("time").reset_index(drop=True)
    return d


def simulate(px, grid_usd, basket_cap_usd, max_pos, x_minutes=40,
             cooldown_min=1440, lot_scale=1.0):
    """
    Returns dict of results. Conservative: uses M1 close for both decisions and fills.
    Position sizing: 0.01 lots * lot_scale, and P&L per position = (exit-entry)*dir*lot_scale
    for gold (1 oz per 0.01 lot).
    """
    n = len(px)
    close = px["close"].values
    baseline = pd.Series(close).rolling(x_minutes, min_periods=5).mean().values

    pos = []            # list of (entry, dir)
    realized = 0.0
    equity = []         # closed-trade equity
    trades = 0
    wins = 0
    cooldown_until = -1

    grid_dist = grid_usd

    for i in range(x_minutes, n):
        b = baseline[i]
        if np.isnan(b):
            continue
        price = close[i]

        # ---- manage open basket ----
        if pos:
            floating = sum((price - e) * dr * lot_scale for e, dr in pos)
            # take profit on reversion to baseline
            long_hit = pos and pos[0][1] == 1 and price >= b
            short_hit = pos and pos[0][1] == -1 and price <= b
            if long_hit or short_hit:
                realized += floating
                trades += 1
                if floating > 0:
                    wins += 1
                equity.append(realized)
                pos = []
                continue
            if floating <= -basket_cap_usd:
                realized += floating
                trades += 1
                equity.append(realized)
                pos = []
                cooldown_until = i + cooldown_min
                continue

        # ---- entries ----
        if i < cooldown_until:
            continue
        if len(pos) >= max_pos:
            continue

        if price < b - grid_dist:
            # buy (below baseline)
            if not pos:
                pos.append((price, 1))
            else:
                dr = pos[0][1]
                if dr == 1:
                    last = pos[-1][0]
                    if price <= last - grid_dist:
                        pos.append((price, 1))
                else:
                    continue
        elif price > b + grid_dist:
            if not pos:
                pos.append((price, -1))
            else:
                dr = pos[0][1]
                if dr == -1:
                    last = pos[-1][0]
                    if price >= last + grid_dist:
                        pos.append((price, -1))
                else:
                    continue

    if not equity:
        return None
    eq = np.array(equity)
    peak = np.maximum.accumulate(eq)
    dd = (eq - peak).min()
    return {
        "net": realized,
        "trades": trades,
        "winrate": wins / trades * 100 if trades else 0,
        "maxdd": dd,
        "ret_dd": realized / abs(dd) if dd < 0 else float("inf"),
        "final_open": len(pos),
    }


def main():
    print("loading XAUUSDm M1 ...")
    raw = load_prices()
    print(f"bars={len(raw)}  {raw.time.min()} .. {raw.time.max()}")

    # subsample: use the full series (1.23M bars is fine for this simple loop in numpy-ish python?)
    # 1.23M iterations x ~4 configs would be slow; take 2023-01..2026-06 as-is but downsample
    # to every bar for correctness. We run a reduced grid and accept runtime.
    print("\n" + "=" * 100)
    print("GRID GEOMETRY SIMULATION - gold, 0.01 lot (1 USD P&L per 1 USD move per position)")
    print("=" * 100)
    print("Question: does the mean-reversion edge survive a basket stop small enough for 500 USD?")
    print("Legacy context: legacy used ~$5.5 grid, 3 max positions, no clean basket stop,")
    print("                and realized a -$667 max drawdown to earn +$695 net.\n")

    rows = []
    for grid_usd in [3.0, 5.0, 7.0, 10.0, 14.0]:
        for cap in [10.0, 15.0, 20.0, 30.0, 60.0, 100000.0]:
            r = simulate(raw, grid_usd, cap, max_pos=3)
            if r is None:
                continue
            rows.append({
                "grid_usd": grid_usd,
                "basket_cap": ("none" if cap > 9999 else f"{cap:.0f}"),
                "net": round(r["net"], 1),
                "trades": r["trades"],
                "winrate": round(r["winrate"], 1),
                "maxdd": round(r["maxdd"], 1),
                "net/maxdd": round(r["ret_dd"], 2),
            })
            print(f"grid=${grid_usd:>5.1f}  cap={rows[-1]['basket_cap']:>4}  "
                  f"net={r['net']:>9.1f}  trades={r['trades']:>5}  win={r['winrate']:>5.1f}%  "
                  f"maxDD={r['maxdd']:>8.1f}  net/DD={r['ret_dd']:>6.2f}")

    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT, "a06_grid_geometry.csv"), index=False, encoding="utf-8-sig")

    print("\n" + "=" * 100)
    print("HOW TO READ THIS")
    print("=" * 100)
    print("'net/maxdd' is the only figure that matters for a 500 USD account: it is how much")
    print("net profit you earn per dollar of worst-case drawdown. Anything near or below 1.0")
    print("means the strategy barely pays for its own risk. Compare each cell's maxDD against")
    print("the account: a 500 USD account dies at -500, and you want maxDD <= ~150 (30%).")
    print("\nAlso compare 'none' caps (the legacy behaviour) against the capped rows: if the")
    print("edge collapses when the cap is tightened, then the legacy edge WAS the deep-holding")
    print("behaviour, and it cannot be transplanted onto a small account.")
    print("\ndone ->", OUT)


if __name__ == "__main__":
    main()
