# -*- coding: utf-8 -*-
"""
a03_stop_cap_analysis.py
purpose: the a02 probe showed the strategy's whole P&L is dwarfed by its loss tail
         (-666 closed DD vs +695 total net). The legacy 'cut' exits realize -9.92 avg
         and peak at -104. This script bounds how much of that damage a hard per-position
         loss CAP would remove, and where the cap should sit.

IMPORTANT METHOD NOTE (honesty):
  We only have realized entry/exit prices, not intra-trade tick paths. So we cannot
  know whether a capped trade would have recovered. The calculation below is therefore
  an OPTIMISTIC UPPER BOUND: it rewrites any losing trade whose realized loss exceeds
  the cap as exactly -cap. It ignores (a) that stopped trades never recover, and
  (b) that stopping frees capital but also forgoes later reversion wins.
  Use it to locate the interesting cap range, then confirm with a real EA ablation run.
"""
import os

import numpy as np
import pandas as pd

SRC = r"D:\desktop\新量化策略\旧量化策略\32代数据\train2024\eva_trade_events.csv"
OUT = r"D:\desktop\新量化策略\deepseek数据保存\analysis\out"
os.makedirs(OUT, exist_ok=True)
pd.set_option("display.width", 220)


def section(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


d = pd.read_csv(SRC, encoding="utf-8-sig")
d["entry_time"] = pd.to_datetime(d["entry_time"])
d["exit_time"] = pd.to_datetime(d["exit_time"])
d = d.sort_values("exit_time").reset_index(drop=True)

BASE_NET = d.net_pnl.sum()

section("0. baseline")
print(f"trades={len(d)}  net={BASE_NET:+.2f}  PF={d.net_pnl[d.net_pnl>0].sum()/abs(d.net_pnl[d.net_pnl<0].sum()):.3f}")

# ------------------------------------------------------------------
section("1. how much loss sits below each candidate per-position cap?")
rows = []
for cap in [3, 4, 5, 6, 8, 10, 12, 15, 20, 30, 50, 200]:
    hit = d.net_pnl < -cap
    n_hit = hit.sum()
    saved = (d.net_pnl[hit] + cap).sum()          # negative number; loss reduction
    new_net = BASE_NET - saved
    rows.append({
        "cap_usd": cap,
        "n_capped": int(n_hit),
        "pct_capped": round(n_hit / len(d) * 100, 1),
        "loss_removed": round(-saved, 2),
        "net_if_capped": round(new_net, 2),
        "improvement": round(new_net - BASE_NET, 2),
    })
cap_df = pd.DataFrame(rows)
print(cap_df.to_string(index=False))
cap_df.to_csv(os.path.join(OUT, "a03_stop_cap.csv"), index=False, encoding="utf-8-sig")

section("2. reading")
best = cap_df.loc[cap_df.improvement.idxmax()]
print(f"upper-bound-optimal cap = ${best.cap_usd:.0f}  (removes ${best.loss_removed:.0f} of tail,")
print(f"caps {best.n_capped:.0f} trades = {best.pct_capped:.0f}% of all trades, net -> {best.net_if_capped:+.0f})")
print("\nCaveat: a tighter cap removes more loss but caps MORE trades, many of which")
print("would have reverted into the profitable grid win. The real optimum is looser")
print("than this bound. The point of this table is the ORDER OF MAGNITUDE: the tail")
print("is worth ~$1.5-2.5k over 3.5 years, i.e. 3-4x the strategy's entire net profit.")

# ------------------------------------------------------------------
section("3. decompose: where does the cappable loss live?")
d["capped5"] = d.net_pnl < -5
tab = d.groupby("exit_reason").agg(
    n=("net_pnl", "size"),
    net=("net_pnl", "sum"),
    n_below5=("capped5", "sum"),
    loss_below5=("net_pnl", lambda s: s[s < -5].sum()),
    worst=("net_pnl", "min"),
).sort_values("loss_below5")
print(tab.round(2).to_string())

# ------------------------------------------------------------------
section("4. does the cap idea survive on the GRID BASKET (all open grid positions together)?")
print("A per-position cap is not how the legacy code works: grid is a basket.")
print("Approximate basket loss at each grid exit by summing OPEN positions at that instant.")
d["dir"] = d.direction
# Build a simple event-based basket: at each grid exit time, the closes that happen
# in that minute represent (approximately) one basket being flushed.
grid = d[d.order_kind == "grid"].copy()
grid["exit_min"] = grid.exit_time.dt.floor("min")
basket = grid.groupby("exit_min").agg(n=("net_pnl", "size"), net=("net_pnl", "sum"))
print(f"\nbaskets (grid closes grouped by minute): {len(basket)}")
print(basket.net.describe(percentiles=[.01, .05, .25, .5, .75, .95]).round(2).to_string())
print("\nworst 15 baskets:")
print(basket.nsmallest(15, "net").to_string())
basket.to_csv(os.path.join(OUT, "a03_grid_baskets.csv"), encoding="utf-8-sig")

section("5. basket-level cap: how many baskets, and what would they cost at various caps?")
rows = []
for cap in [10, 15, 20, 30, 40, 50, 75, 100]:
    hit = basket.net < -cap
    saved = (basket.net[hit] + cap).sum()
    rows.append({
        "basket_cap": cap,
        "baskets_capped": int(hit.sum()),
        "pct": round(hit.mean() * 100, 1),
        "loss_removed": round(-saved, 2),
        "net_improvement": round(-saved, 2),
    })
bdf = pd.DataFrame(rows)
print(bdf.to_string(index=False))
bdf.to_csv(os.path.join(OUT, "a03_basket_cap.csv"), index=False, encoding="utf-8-sig")
print("\nThis is the number eva028's InpMaxGridBasketLossMoney (default $30) targets.")
print("Compare 'baskets_capped' and 'loss_removed' here with the real eva028 sweep.")

# ------------------------------------------------------------------
section("6. monthly net stability under a $30 basket cap (upper bound)")
basket_capped = basket.net.clip(lower=-30)
print(f"uncapped basket net total : {basket.net.sum():+.2f}")
print(f"capped@30 basket net total: {basket_capped.sum():+.2f}")
print(f"difference                : {basket_capped.sum()-basket.net.sum():+.2f}")

print("\ndone ->", OUT)
