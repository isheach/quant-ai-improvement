# -*- coding: utf-8 -*-
"""
a01_trade_events_probe.py
purpose: probe the legacy audited trade_events.csv to establish, from real data,
         the money-per-point relationship, exit-reason anatomy, tail risk, and
         what a 500 USD account can actually support.
input : legacy eva_trade_events.csv files
output: console report + out/a01_*.csv
"""
import os
import sys
import glob

import numpy as np
import pandas as pd

SRC = r"D:\desktop\新量化策略\旧量化策略"
OUT = r"D:\desktop\新量化策略\deepseek数据保存\analysis\out"
os.makedirs(OUT, exist_ok=True)

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 50)


def load_all():
    files = glob.glob(os.path.join(SRC, "**", "eva_trade_events.csv"), recursive=True)
    frames = []
    for f in files:
        try:
            df = pd.read_csv(f, encoding="utf-8-sig")
        except Exception as e:  # noqa: BLE001
            print(f"[skip] {f}: {e}")
            continue
        if "net_pnl" not in df.columns:
            print(f"[skip] {f}: no net_pnl")
            continue
        df["__src"] = os.path.relpath(f, SRC)
        df["__rows"] = len(df)
        frames.append(df)
        print(f"[load] {os.path.relpath(f, SRC)}  rows={len(df)}  cols={len(df.columns)}")
    if not frames:
        return None
    return pd.concat(frames, ignore_index=True)


def section(title):
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def main():
    df = load_all()
    if df is None:
        print("no trade_events.csv found")
        return

    section("0. sources")
    print(df.groupby("__src").size().to_string())

    # Keep only the largest run per source to avoid mixing runs
    main_src = df.groupby("__src").size().idxmax()
    d = df[df["__src"] == main_src].copy()
    print(f"\nprimary run: {main_src}  rows={len(d)}")

    for c in ["entry_time", "exit_time"]:
        d[c] = pd.to_datetime(d[c], errors="coerce")
    d = d.sort_values("entry_time").reset_index(drop=True)

    section("1. columns")
    print(list(d.columns))

    section("2. date span")
    print("entry:", d.entry_time.min(), "->", d.entry_time.max())
    print("exit :", d.exit_time.min(), "->", d.exit_time.max())
    print("days:", (d.exit_time.max() - d.entry_time.min()).days)

    section("3. exit_reason anatomy (this is the core anatomy of the strategy)")
    g = d.groupby("exit_reason").agg(
        n=("net_pnl", "size"),
        net=("net_pnl", "sum"),
        avg=("net_pnl", "mean"),
        median=("net_pnl", "median"),
        worst=("net_pnl", "min"),
        best=("net_pnl", "max"),
        winrate=("net_pnl", lambda s: (s > 0).mean() * 100),
    ).sort_values("net")
    g["pct_of_total_net"] = g["net"] / d.net_pnl.sum() * 100
    print(g.round(2).to_string())
    g.to_csv(os.path.join(OUT, "a01_exit_reason.csv"), encoding="utf-8-sig")

    section("4. order_kind x direction")
    print(d.groupby(["order_kind", "direction"]).agg(
        n=("net_pnl", "size"), net=("net_pnl", "sum"),
        winrate=("net_pnl", lambda s: (s > 0).mean() * 100)).round(2).to_string())

    section("5. money-per-point calibration  (net_pnl vs price move * volume)")
    dd = d[(d.volume > 0) & d.entry_price.notna() & d.exit_price.notna()].copy()
    dd["raw_move"] = (dd.exit_price - dd.entry_price) * dd.direction
    dd["usd_per_1usd_move_per_lot"] = dd.net_pnl / (dd.raw_move * dd.volume * 100)
    print(dd["usd_per_1usd_move_per_lot"].describe().round(4).to_string())
    print("\nvolume distribution:")
    print(dd.volume.value_counts().head(10).to_string())

    section("6. holding time")
    d["hold_h"] = d.holding_seconds / 3600.0
    print(d.groupby("exit_reason")["hold_h"].describe().round(2).to_string())

    section("7. per-category net (grid / trend / cut) using exit_reason mapping")
    def cat(r):
        if r == "grid_tp_baseline_revert":
            return "grid_regression(win)"
        if r in ("trend_close_opposite_grid",):
            return "cut_countertrend_grid"
        if r in ("trend_state_exit", "trend_trailing_stop", "trend_sl", "trend_tp"):
            return "trend_order"
        return "other:" + str(r)

    d["cat"] = d.exit_reason.map(cat)
    c = d.groupby("cat").agg(n=("net_pnl", "size"), net=("net_pnl", "sum"),
                             winrate=("net_pnl", lambda s: (s > 0).mean() * 100),
                             avg=("net_pnl", "mean")).sort_values("net", ascending=False)
    print(c.round(2).to_string())

    section("8. grid distance actually used (grid_dist_pts) - is GridZ=7000 binding vs MinGridZ?")
    gd = d[d.grid_dist_pts > 0]["grid_dist_pts"]
    print(gd.describe().round(0).to_string())
    print("\nquantiles of grid_dist_pts:")
    print(gd.quantile([0.01, .05, .25, .5, .75, .95, .99]).round(0).to_string())
    print("\nnote: point=0.001 USD for XAUUSDm -> dist_usd = grid_dist_pts/1000")

    section("9. what is the empirical distribution of per-position loss? (tail risk source)")
    for c_ in ["net_pnl"]:
        print(d[c_].describe(percentiles=[.01, .05, .25, .5, .75, .9, .95, .99]).round(2).to_string())

    section("10. worst single positions")
    cols = ["entry_time", "exit_time", "direction", "order_kind", "order_number",
            "entry_reason", "exit_reason", "volume", "net_pnl", "holding_seconds", "grid_dist_pts"]
    print(d.nsmallest(12, "net_pnl")[cols].to_string())

    section("11. monthly net")
    d["ym"] = d.entry_time.dt.to_period("M").astype(str)
    m = d.groupby("ym").agg(n=("net_pnl", "size"), net=("net_pnl", "sum")).round(2)
    print(m.to_string())
    m.to_csv(os.path.join(OUT, "a01_monthly.csv"), encoding="utf-8-sig")

    section("12. concurrent exposure: max positions + simultaneous floating risk (approx)")
    # reconstruct concurrency from entry/exit intervals
    ev = []
    for _, r in d.iterrows():
        ev.append((r.entry_time, 1))
        ev.append((r.exit_time, -1))
    ev.sort()
    cur = mx = 0
    for _, delta in ev:
        cur += delta
        mx = max(mx, cur)
    print(f"max simultaneous positions (whole run): {mx}")

    print("\ndone ->", OUT)


if __name__ == "__main__":
    main()
