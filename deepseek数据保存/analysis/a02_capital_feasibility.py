# -*- coding: utf-8 -*-
"""
a02_capital_feasibility.py
purpose: decide, from the real audited trade stream, whether a ~500 USD account can
         even carry this strategy at the Exness minimum lot (0.01), and where the real
         drawdown/tail risk sits. Separates "edge quality" from "position size floor".
output : console report + out/a02_*.csv
"""
import os

import numpy as np
import pandas as pd

SRC = r"D:\desktop\新量化策略\旧量化策略\32代数据\train2024\eva_trade_events.csv"
OUT = r"D:\desktop\新量化策略\deepseek数据保存\analysis\out"
os.makedirs(OUT, exist_ok=True)
pd.set_option("display.width", 200)


def section(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


d = pd.read_csv(SRC, encoding="utf-8-sig")
d["entry_time"] = pd.to_datetime(d["entry_time"])
d["exit_time"] = pd.to_datetime(d["exit_time"])
d = d.sort_values("exit_time").reset_index(drop=True)

# ---------------- closed-trade equity curve (realized only) ----------------
d["cum_net"] = d.net_pnl.cumsum()
d["peak"] = d.cum_net.cummax()
d["dd"] = d.cum_net - d.peak
d["dd_pct_of_deposit"] = d.dd / 2000.0 * 100

section("1. realized closed-trade equity curve (deposit was 2000 USD in the run config)")
print(f"final net          : {d.net_pnl.sum():+.2f}")
print(f"peak cum net       : {d.peak.max():+.2f}")
print(f"max closed-trade DD: {d.dd.min():+.2f}  ({d.dd_pct_of_deposit.min():.1f}% of 2000)")
print(f"trades             : {len(d)}")
print(f"win rate           : {(d.net_pnl>0).mean()*100:.1f}%")
print(f"avg win / avg loss : {d.net_pnl[d.net_pnl>0].mean():.2f} / {d.net_pnl[d.net_pnl<0].mean():.2f}")
pf = d.net_pnl[d.net_pnl > 0].sum() / abs(d.net_pnl[d.net_pnl < 0].sum())
print(f"profit factor      : {pf:.3f}")

section("2. SCALING REALITY CHECK: same trade stream, different deposit")
print("The lot is pinned at the 0.01 broker minimum. You cannot reduce risk by sizing down.")
print("So the SAME dollar loss stream becomes a larger % drawdown as deposit shrinks.\n")
rows = []
for dep in [2000, 1000, 500, 400, 300, 200]:
    rows.append({
        "deposit": dep,
        "maxDD_usd": round(d.dd.min(), 2),
        "maxDD_pct": round(abs(d.dd.min()) / dep * 100, 1),
        "worst_single_loss_pct": round(abs(d.net_pnl.min()) / dep * 100, 1),
        "p1_loss_usd": round(d.net_pnl.quantile(0.01), 2),
        "p1_loss_pct": round(abs(d.net_pnl.quantile(0.01)) / dep * 100, 1),
        "annual_net_usd": round(d.net_pnl.sum() / 3.5, 1),
        "annual_net_pct": round(d.net_pnl.sum() / 3.5 / dep * 100, 1),
        "ret_over_dd": round((d.net_pnl.sum()) / abs(d.dd.min()), 2),
    })
sc = pd.DataFrame(rows)
print(sc.to_string(index=False))
sc.to_csv(os.path.join(OUT, "a02_capital_scaling.csv"), index=False, encoding="utf-8-sig")

section("3. interpretation of the scaling table")
print("ret_over_dd = total net / max closed DD. Below ~1.0 means the account barely")
print("survives its own drawdown. Note this understates the true DD because it ignores")
print("floating loss on open baskets (the legacy logs recorded cluster floating peaks")
print("of $260-$860, i.e. several times the realized DD).")

section("4. tail concentration: how few trades carry the whole result?")
losses = d.net_pnl.sort_values()
print(f"worst 1 trade  : {losses.iloc[0]:+.2f}")
print(f"worst 5 sum    : {losses.iloc[:5].sum():+.2f}")
print(f"worst 10 sum   : {losses.iloc[:10].sum():+.2f}")
print(f"worst 42 sum (all last_order_stop): {losses.iloc[:42].sum():+.2f}")
print(f"total net      : {d.net_pnl.sum():+.2f}")
wins = d.net_pnl.sort_values(ascending=False)
print(f"\nbest 10 sum    : {wins.iloc[:10].sum():+.2f}")
print(f"best 50 sum    : {wins.iloc[:50].sum():+.2f}")

section("5. grid edge quality vs fees/spread")
g = d[d.exit_reason == "grid_tp_baseline_revert"]
print(f"grid wins: n={len(g)}  net={g.net_pnl.sum():+.2f}  avg={g.net_pnl.mean():+.2f}")
print(f"median grid win   : {g.net_pnl.median():+.2f}")
print(f"median grid dist  : {g.grid_dist_pts.median():.0f} pts = {g.grid_dist_pts.median()/1000:.2f} USD")
print(f"median spread     : {g.spread_pts_at_entry.median():.0f} pts = {g.spread_pts_at_entry.median()/1000:.2f} USD")
print(f"spread as % of grid distance (median): {g.spread_pts_at_entry.median()/g.grid_dist_pts.median()*100:.1f}%")
print("\nA one-way spread is paid on entry and on exit => cost ~= 2x spread.")
print(f"so cost per grid round trip ~= {2*g.spread_pts_at_entry.median()/1000:.2f} USD")
print(f"vs median gross target    ~= {g.net_pnl.median():.2f} USD (already net)")

section("6. grid win size distribution - is the edge just a few big reversion moves?")
print(g.net_pnl.describe(percentiles=[.05, .25, .5, .75, .95]).round(2).to_string())

section("7. what fraction of grid net comes from the top 5% of grid trades?")
gs = g.net_pnl.sort_values(ascending=False)
k = int(len(gs) * 0.05)
print(f"top 5% ({k} trades) sum = {gs.iloc[:k].sum():+.2f}  of total {gs.sum():+.2f} "
      f"=> {gs.iloc[:k].sum()/gs.sum()*100:.1f}%")

section("8. trend module standalone P&L (trend orders + the cuts they caused)")
trend_orders = d[d.order_kind == "trend"]
cuts = d[d.exit_reason == "trend_close_opposite_grid"]
print(f"trend orders alone : n={len(trend_orders)}  net={trend_orders.net_pnl.sum():+.2f}")
print(f"cuts they trigger  : n={len(cuts)}  net={cuts.net_pnl.sum():+.2f}")
print(f"trend subsystem combined net = {trend_orders.net_pnl.sum() + cuts.net_pnl.sum():+.2f}")
print(f"\ngrid module net = {d[d.order_kind=='grid'].net_pnl.sum():+.2f}")
print("NOTE: the cuts only exist BECAUSE the trend module exists. Removing the trend module")
print("would remove the cut losses AND change the grid's loss path. Cannot be decided from")
print("this file alone - needs an ablation run. That is a concrete experiment to schedule.")

section("9. risk-exit module cost (the 'hard stops' that eva028 is built around)")
for r in ["last_order_stop", "cutoff_line_stop", "risk4_force_exit", "sl"]:
    s = d[d.exit_reason == r]
    if len(s):
        print(f"{r:22s} n={len(s):4d} net={s.net_pnl.sum():+8.2f} avg={s.net_pnl.mean():+7.2f} "
              f"worst={s.net_pnl.min():+7.2f}")

section("10. monthly net: how lumpy? (a 500 USD account cannot average out lumpiness)")
d["ym"] = d.entry_time.dt.to_period("M").astype(str)
m = d.groupby("ym").net_pnl.sum()
print(f"months          : {len(m)}")
print(f"positive months : {(m>0).sum()}  ({(m>0).mean()*100:.0f}%)")
print(f"best month      : {m.max():+.2f}")
print(f"worst month     : {m.min():+.2f}")
print(f"median month    : {m.median():+.2f}")
print(f"std of month    : {m.std():.2f}")
print(f"worst month as % of 500 deposit: {m.min()/500*100:.1f}%")
print(f"worst month as % of 2000 deposit: {m.min()/2000*100:.1f}%")

section("11. breakeven sanity: monthly net needed to matter on 500 USD")
for tgt in [0.02, 0.05, 0.10]:
    print(f"  {tgt*100:4.1f}%/month on 500 USD = {tgt*500:6.2f} USD/month = {tgt*500/21:5.2f} USD/trading day")
print(f"\nactual median monthly net (2000 USD run, 0.01 lot) = {m.median():+.2f} USD")
print("=> at 0.01 lot the strategy's typical month is ~a few USD. On 500 USD that is a")
print("   rounding error against the risk it carries. The lever is NOT parameter tuning;")
print("   it is either (a) a fundamentally lower-variance design, or (b) accepting a")
print("   higher lot with a hard, small, well-placed stop. This is the central design")
print("   decision for the new project.")

print("\ndone ->", OUT)
