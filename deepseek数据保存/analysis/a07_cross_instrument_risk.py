# -*- coding: utf-8 -*-
"""
a07_cross_instrument_risk.py  (v2 - corrected)
purpose: turn the LIVE broker contract specs (probed from MT5) into a risk-comparison
         table across the three target instruments, to decide which are tradable on a
         500 USD account at the 0.01 minimum lot.

CORRECTIONS vs v1:
  - v1 treated SYMBOL_SPREAD as a round-trip cost. It is the current spread in points,
    i.e. the ONE-WAY spread you pay crossing the bid/ask. A round trip pays it twice.
  - v1 used attribute access like r.stop_%_of_price, which pandas cannot parse.
  - v1's conclusions were wrong as a result; see the corrected reading at the bottom.

source : analysis/out/broker_specs_20260910.json (captured 2026-09-10, MT5 build 6184)
"""
import json
import os

import pandas as pd

WS = r"D:\desktop\新量化策略\deepseek数据保存"
SPEC = os.path.join(WS, "analysis", "out", "broker_specs_20260910.json")
OUT = os.path.join(WS, "analysis", "out")

with open(SPEC, "r", encoding="utf-8") as fh:
    data = json.load(fh)

ACC = 500.0
MINLOT = 0.01

usdjpy = next(s["bid"] for s in data["symbols"] if s["name"] == "USDJPYm")

rows = []
for s in data["symbols"]:
    name = s["name"]
    if name not in ("XAUUSDm", "BTCUSDm", "USDJPYm"):
        continue
    point = s["point"]
    contract = s["contract_size"]
    price = s["bid"]
    spread_pts = s["spread_points"]
    is_jpy = name.startswith("USDJPY")
    fx = usdjpy if is_jpy else 1.0

    notional_001 = MINLOT * contract * price / fx
    usd_per_point = MINLOT * contract * point / fx
    spread_1way = spread_pts * usd_per_point
    spread_rt = 2 * spread_1way

    risk1 = ACC * 0.01
    stop_pts = risk1 / usd_per_point
    stop_price = stop_pts * point
    stop_pct = stop_price / price * 100

    rows.append({
        "symbol": name,
        "price": round(price, 3),
        "contract_size": contract,
        "notional_001lot_usd": round(notional_001, 2),
        "usd_per_point_001lot": round(usd_per_point, 6),
        "spread_pts": spread_pts,
        "spread_1way_usd": round(spread_1way, 4),
        "spread_roundtrip_usd": round(spread_rt, 4),
        "spread_rt_pct_of_500": round(spread_rt / ACC * 100, 4),
        "stop_pts_1pct_risk": round(stop_pts, 1),
        "stop_price_units": round(stop_price, 4),
        "stop_pct_of_price": round(stop_pct, 4),
        "move_1pct_of_price_usd": round(notional_001 * 0.01, 2),
    })

df = pd.DataFrame(rows)
pd.set_option("display.width", 250)

print("=" * 122)
print("CROSS-INSTRUMENT RISK TABLE  (account 500 USD, minimum lot 0.01, live Exness specs 2026-09-10)")
print("=" * 122)
print(df.to_string(index=False))
df.to_csv(os.path.join(OUT, "a07_cross_instrument_risk.csv"), index=False, encoding="utf-8-sig")

print("\n" + "=" * 122)
print("PER-INSTRUMENT READOUT")
print("=" * 122)

def g(sym, col):
    return df[df.symbol == sym].iloc[0][col]

for _, r in df.iterrows():
    print(f"\n{r.symbol}")
    print(f"  0.01 lot  = {r.notional_001lot_usd:>10,.2f} USD notional    "
          f"(1 point = {r.usd_per_point_001lot:.6f} USD)")
    print(f"  spread    = {r.spread_pts:>6,.0f} pts = {r.spread_1way_usd:.4f} USD one-way, "
          f"{r.spread_roundtrip_usd:.4f} USD round trip = {r.spread_rt_pct_of_500:.4f}% of the account")
    print(f"  a 1% adverse price move costs {r.move_1pct_of_price_usd:>8,.2f} USD "
          f"= {r.move_1pct_of_price_usd/ACC*100:6.2f}% of the account")
    print(f"  1% risk budget (5.00 USD) buys a stop of {r.stop_pts_1pct_risk:>9,.1f} pts "
          f"= {r.stop_pct_of_price:.4f}% of price")

print("\n" + "=" * 122)
print("CORRECTED CONCLUSIONS")
print("=" * 122)

x = df[df.symbol == "XAUUSDm"].iloc[0]
b = df[df.symbol == "BTCUSDm"].iloc[0]
j = df[df.symbol == "USDJPYm"].iloc[0]
x_move_pct = x.move_1pct_of_price_usd / ACC * 100
b_move_pct = b.move_1pct_of_price_usd / ACC * 100
j_move_pct = j.move_1pct_of_price_usd / ACC * 100

print(f"""
1. SPREAD IS NOT THE PROBLEM. My earlier draft claimed Bitcoin's spread was
   "2% of the account per trade". That was WRONG (I double-counted and mis-scaled).
   Real round-trip spread costs on a 500 USD account at 0.01 lot:
        XAUUSDm {x.spread_roundtrip_usd:.4f} USD ({x.spread_rt_pct_of_500:.4f}%)
        BTCUSDm {b.spread_roundtrip_usd:.4f} USD ({b.spread_rt_pct_of_500:.4f}%)
        USDJPYm {j.spread_roundtrip_usd:.4f} USD ({j.spread_rt_pct_of_500:.4f}%)
   All are negligible. (The 1000-point Bitcoin spread looked alarming only because
   BTC's point is 0.01 USD and 0.01 lot is 0.01 BTC.)

2. THE REAL DIMENSION PROBLEM IS % MOVE vs % OF ACCOUNT.
   0.01 lot is irreducible, so the account absorbs a fixed dollar amount per unit of
   price movement. At CURRENT prices:
        - gold  : a 1% price move = {x.move_1pct_of_price_usd:,.2f} USD = {x_move_pct:.2f}% of a 500 USD account
        - BTC   : a 1% price move = {b.move_1pct_of_price_usd:,.2f} USD = {b_move_pct:.2f}% of a 500 USD account
        - JPY   : a 1% price move = {j.move_1pct_of_price_usd:,.2f} USD = {j_move_pct:.2f}% of a 500 USD account
   Gold is the WORST: a routine 1% daily move is {x_move_pct:.1f}% of the account.
   (Note this is a consequence of GOLD'S PRICE LEVEL, which has risen to 4385 from
   ~1826 in 2023. At 0.01 lot the notional is {x.notional_001lot_usd:,.0f} USD. The legacy project
   was designed when gold was ~2000, where the same lot carried roughly half this risk.
   THIS IS A MAJOR UNNOTICED DRIFT - see conclusion 4.)

3. RISK GRANULARITY RANKING (how finely can you control dollar risk?):
        USDJPY : 1 point = {j.usd_per_point_001lot:.6f} USD -> a 1% risk budget buys {j.stop_pct_of_price:.3f}% of price of stop
        GOLD   : 1 point = {x.usd_per_point_001lot:.6f} USD -> a 1% risk budget buys {x.stop_pct_of_price:.3f}% of price of stop
        BTC    : 1 point = {b.usd_per_point_001lot:.6f} USD -> a 1% risk budget buys {b.stop_pct_of_price:.3f}% of price of stop
   By DOLLAR granularity JPY is finest ({j.usd_per_point_001lot:.5f} USD/point vs gold's {x.usd_per_point_001lot:.5f}).
   By PERCENTAGE-of-price granularity BTC is finest, because BTC's typical 5-minute
   range is a much larger fraction of its price.
   -> The two orderings disagree, which is exactly why risk must be expressed as a
      PERCENTAGE OF ACCOUNT (absolute dollars), not in points or in % of price.

4. THE HEADLINE FINDING: GOLD'S PRICE LEVEL HAS DOUBLED SINCE THE LEGACY DESIGN.
   Legacy data (2023-01) had gold at ~1826; today it is 4385. With the lot pinned at
   0.01, the dollar risk per unit of gold movement is unchanged ($1 per $1), but the
   ACCOUNT is 500 USD -- so every percentage move in gold now costs the same dollars
   against a much smaller account than the EA was designed for.
   Combined with the fact that the minimum lot cannot be reduced, this is the strongest
   possible argument that the gold grid design must be rebuilt around a HARD DOLLAR
   RISK BUDGET rather than around point distances.
""")

print("=" * 122)
print("BOTTOM LINE FOR THE THREE-INSTRUMENT PLAN")
print("=" * 122)
print(f"""
Ranked by suitability for 500 USD at the 0.01 minimum lot:
  1) USDJPY  - finest dollar granularity, cheapest spread, a 1% risk budget buys a
               meaningful {j.stop_pct_of_price:.2f}% of price of stop. BEST FIT.
  2) GOLD    - the only instrument with 42 months of local data and the entire legacy
               research behind it, but a 1% gold move = {x_move_pct:.1f}% of the account,
               so stops must be kept tiny ({x.stop_pct_of_price:.3f}% of price) or the lot problem remains.
  3) BITCOIN - spread is fine, but a 1% move is {b_move_pct:.1f}% of the account and BTC's
               daily ranges are far larger than gold's, so 0.01 lot is likely too big.
               Needs real data before any verdict.
""")
print("done ->", OUT)
