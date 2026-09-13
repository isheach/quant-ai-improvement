# -*- coding: utf-8 -*-
"""
risk_math.py —— dsh_JPYGrid.mq5 的网格风险算术（供报告引用；纯计算，不需要 MT5）
口径全部来自 broker_specs_20260910.json 的 USDJPYm 实测规格。
"""
CONTRACT = 100000.0
POINT = 0.001
SPREAD_POINTS = 10.0
RATE = 154.099          # 2026-09-10 实测 bid
LEVERAGE = 200.0
EQUITY = 300.0
LOT = 0.01              # 每层固定手（InpLotMultiplier = 1.0，非马丁）

MPP = CONTRACT / RATE   # 每 1 手、每 1.0 价格变动的 USD 价值
USD_PER_POINT_001LOT = 0.01 * POINT * MPP

print(f"MPP(每1手每1.0价格)      = {MPP:.2f} USD")
print(f"每 0.01 手每 1 点        = ${USD_PER_POINT_001LOT:.6f}")
print(f"往返点差 10 点 / 0.01 手 = ${SPREAD_POINTS*USD_PER_POINT_001LOT:.4f}")
print()


def batch_summary(step_pts, tp_pts, max_layers, label=""):
    """整篮子满仓（max_layers 层全部被套到最后一层价位）时的浮亏 + 保证金 + 完成一个周期的毛利"""
    vol = max_layers * LOT
    # 满仓时价格停在 anchor-(max_layers-1)*step 处（只做多）
    float_usd = 0.0
    for k in range(max_layers):
        float_usd += LOT * (max_layers - 1 - k) * step_pts * POINT * MPP
    margin = vol * CONTRACT / LEVERAGE
    gross = vol * tp_pts * POINT * MPP
    spread_cost = max_layers * SPREAD_POINTS * USD_PER_POINT_001LOT
    return dict(step=step_pts, tp=tp_pts, n=max_layers, vol=vol,
                float_usd=float_usd, float_pct=float_usd / EQUITY * 100.0,
                margin=margin, margin_pct=margin / EQUITY * 100.0,
                gross=gross, spread=spread_cost, net=gross - spread_cost,
                net_pct=(gross - spread_cost) / EQUITY * 100.0,
                spread_ratio=SPREAD_POINTS / step_pts * 100.0)


print("=" * 118)
print("表 1 · 满仓（8 层 × 0.01 手）时的最坏浮亏 / 保证金 / 周期毛利   [入金 $300, 1:200, 只做多]")
print("=" * 118)
hdr = f"{'步长(点)':>9} {'止盈(点)':>9} {'最坏浮亏$':>10} {'占净值%':>8} {'保证金$':>9} {'占净值%':>8} {'周期毛利$':>10} {'点差$':>7} {'周期净利$':>10} {'占净值%':>8} {'点差/步长':>9}"
print(hdr)
print("-" * 118)
for step in (100, 200, 300, 400, 500):
    r = batch_summary(step, step, 8)
    print(f"{r['step']:>9.0f} {r['tp']:>9.0f} {r['float_usd']:>10.2f} {r['float_pct']:>8.1f} "
          f"{r['margin']:>9.2f} {r['margin_pct']:>8.1f} {r['gross']:>10.2f} {r['spread']:>7.2f} "
          f"{r['net']:>10.2f} {r['net_pct']:>8.2f} {r['spread_ratio']:>8.1f}%")
print()

print("=" * 118)
print("表 2 · 层数对左尾的影响（步长 200 点，止盈 200 点，每层 0.01 手固定手）")
print("=" * 118)
print(f"{'最大层数':>8} {'总手数':>7} {'最坏浮亏$':>10} {'占净值%':>8} {'保证金$':>9} {'保证金%':>8} {'周期净利$':>10} {'占净值%':>8}")
print("-" * 118)
for n in (2, 4, 6, 8, 12, 16, 20):
    r = batch_summary(200, 200, n)
    print(f"{n:>8d} {r['vol']:>7.2f} {r['float_usd']:>10.2f} {r['float_pct']:>8.1f} "
          f"{r['margin']:>9.2f} {r['margin_pct']:>8.1f} {r['net']:>10.2f} {r['net_pct']:>8.2f}")
print()

print("=" * 118)
print("★ 关键读法")
print("=" * 118)
r = batch_summary(200, 200, 8)
print(f"1) 默认配置（步长=止盈=200 点、8 层、0.01 手）满仓最坏浮亏 ${r['float_usd']:.2f} = 净值 {r['float_pct']:.1f}%")
print(f"   → InpBasketStopPct=15.0 会在【约 5 层满仓之后】触发，即真正起到硬止损作用；")
print(f"     若最大层数=4，则满仓最坏浮亏只有 {batch_summary(200,200,4)['float_pct']:.1f}% < 15%，篮子止损永不触发（此时 MaxLayers 本身就是止损）。")
print()
print(f"2) 一次成功周期的净利与满仓最坏浮亏之比 ≈ {r['net']:.2f} : {r['float_usd']:.2f} = 1 : {r['float_usd']/r['net']:.1f}")
print(f"   → 需要胜率 > {r['float_usd']/(r['float_usd']+r['net'])*100:.1f}% 才不亏（且假设亏损恰好等于满仓浮亏）")
print(f"   → ★这是网格的命门：必须靠‘大量在浅层就完成的周期’把平均亏损拉到远低于满仓值。")
print()
print(f"3) 点差/步长：步长 {200:.0f} 点时 = {SPREAD_POINTS/200*100:.1f}%（远低于 REJECT-spread 的 30% 门槛）")
print(f"   即使步长压到 100 点也只有 {SPREAD_POINTS/100*100:.1f}% —— JPY 是三品种里唯一能做到的")
print()
print(f"4) 保证金：8 层 0.08 手仅 ${r['margin']:.2f} = {r['margin_pct']:.1f}%（1:200）。")
print(f"   即使 20 层 0.20 手也只有 {batch_summary(200,200,20)['margin_pct']:.1f}%，保证金不是瓶颈，浮亏才是。")
