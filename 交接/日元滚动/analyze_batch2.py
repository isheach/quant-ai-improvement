# -*- coding: utf-8 -*-
"""
analyze_batch2.py —— g2-pure / g2-cd 回填分析（★重点是拆穿"15/20 盈利"这个表象）
输出 analysis_batch2.txt
"""
import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = []
def P(s=""): OUT.append(str(s))

CONTRACT, POINT, RATE = 100000.0, 0.001, 154.099
USD_PER_PT_001 = 0.01 * POINT * (CONTRACT / RATE)     # 每 0.01 手每 1 点
SPREAD_USD = 10.0 * USD_PER_PT_001                     # 每平一层（0.01 手往返 10 点）

rows = []
for ln in (HERE / "outbox_日元滚动_grid2.jsonl").read_text(encoding="utf-8", errors="replace").splitlines():
    ln = ln.strip()
    if ln:
        try: rows.append(json.loads(ln))
        except Exception: pass
rows = [r for r in rows if r.get("pass") is not None]
pure = [r for r in rows if r["grid_id"] == "jyrg-g2-pure"]
cd   = [r for r in rows if r["grid_id"] == "jyrg-g2-cd"]
for r in rows:
    r["_net"] = float(r.get("net") or 0); r["_pf"] = float(r.get("profit_factor") or 0)
    r["_tr"] = float(r.get("trades") or 0); r["_dd"] = float(r.get("dd_pct") or 0)
    r["_ep"] = float(r.get("expected_payoff") or 0)

P("=" * 104)
P("日元滚动线 · 第二批网格回填分析（g2-pure / g2-cd）")
P("=" * 104)
P(f"每平一层（0.01 手，往返 10 点）点差 = ${SPREAD_USD:.4f}")
P()

# ---------------------------------------------------------------- §1 层数单调性
P("=" * 104)
P("§1 ★★★【事实】g2-pure：PF 随【网格层数】严格单调下降 —— 『网格』本身是负贡献")
P("=" * 104)
P(f"{'层数':>4}{'n':>4}{'PF 均值':>10}{'PF min':>9}{'PF max':>9}{'net 均值':>11}{'net max':>10}{'dd 均值':>10}{'dd max':>10}{'净亏光次数':>12}")
P("-" * 104)
for n in (1, 2, 3, 4):
    g = [r for r in pure if int(r["params"]["InpMaxLayers"]) == n]
    if not g: continue
    wiped = sum(1 for r in g if r["_net"] <= -250)
    P(f"{n:>4}{len(g):>4}{sum(r['_pf'] for r in g)/len(g):>10.3f}"
      f"{min(r['_pf'] for r in g):>9.3f}{max(r['_pf'] for r in g):>9.3f}"
      f"{sum(r['_net'] for r in g)/len(g):>11.2f}{max(r['_net'] for r in g):>10.2f}"
      f"{sum(r['_dd'] for r in g)/len(g):>10.1f}{max(r['_dd'] for r in g):>10.1f}{wiped:>12}")
P()
P("★★★ 读法：1 层 1.618 → 2 层 1.417 → 3 层 1.273 → 4 层 0.572。")
P("    这是【严格单调下降】，而且 4 层时 5/5 全部把 $300 账户打光（net ≈ −300、dd ≈ 100%）。")
P("    → 【推断 · 高置信】正期望不来自网格；**每多加一层都在毁价值**。")
P("    → 而且 1 层 = 【根本没有网格】（只是单仓 + 200 点止盈 + 无止损），它却是最好的。")
P()

# ---------------------------------------------------------------- §2 重复行
P("=" * 104)
P("§2 ★★【事实】『15/20 盈利』里有多少是同一个配置的复制品？")
P("=" * 104)
g1 = [r for r in pure if int(r["params"]["InpMaxLayers"]) == 1]
sig = {(r["_net"], r["_pf"], r["_tr"], r["_dd"]) for r in g1}
P(f"  MaxLayers=1 的行数 = {len(g1)}，但【互不相同的结果】只有 {len(sig)} 种：")
for s in sorted(sig):
    P(f"     net={s[0]:+.2f}  PF={s[1]:.3f}  trades={s[2]:.0f}  dd={s[3]:.2f}%")
P(f"  → 因为这 5 行的步长分别是 {sorted({r['params']['InpGridStepPoints'] for r in g1})}，")
P(f"    而 **1 层时步长永远用不上** ⇒ 它们本来就是同一次运行。")
distinct = {tuple(sorted(r["params"].items())) for r in pure}
behav = {(r["_net"], r["_pf"], r["_tr"], r["_dd"]) for r in pure}
behav_prof = {b for b in behav if b[0] > 0}
P(f"  ★所以『20 个 pass 里 15 个盈利』实际上是：")
P(f"     20 个参数组合 → 但只有 【{len(behav)} 种互不相同的结果】→ 其中 {len(behav_prof)} 种是盈利的。")
P(f"     差值来自 MaxLayers=1 的 5 行：参数元组不同（步长 100/200/300/400/500），")
P(f"     但 **1 层时步长永远用不上** ⇒ 它们本来就是同一次运行、同一个配置。")
P()

# ---------------------------------------------------------------- §3 算术自洽性
P("=" * 104)
P("§3 ★★★【事实】算术不自洽：MaxLayers=1 的『毛利不足以支撑报告出来的 PF』")
P("=" * 104)
TP_PTS = 200.0
win_usd = TP_PTS * USD_PER_PT_001                       # 0.01 手走满 200 点的毛利
r = g1[0]
# PF = GP/GL ; net = GP-GL  →  GL = net/(PF-1), GP = PF*GL
GL = r["_net"] / (r["_pf"] - 1.0)
GP = r["_pf"] * GL
P(f"  取 pass {r['pass']}（MaxLayers=1, step=200, TP=200, 0.01 手, 无止损）：")
P(f"    trades = {r['_tr']:.0f}    net = {r['_net']:+.2f}    PF = {r['_pf']:.3f}    dd = {r['_dd']:.2f}%")
P(f"    由 PF 与 net 反解： 毛盈利 GP = ${GP:.2f}   毛亏损 GL = ${GL:.2f}")
P(f"    但 0.01 手走满 200 点（=止盈）的【单笔最大毛利】只有 ${win_usd:.4f}")
P(f"    ⇒ {r['_tr']:.0f} 笔全赢也只有 ${r['_tr']*win_usd:.2f} 的毛盈利")
P(f"    ⇒ 需要 ${GP:.2f}，**缺口 ${GP - r['_tr']*win_usd:+.2f}**")
P()
P("  ★结论：**报告的 PF/net 与『0.01 手 + 200 点止盈』在算术上不可能同时成立。**")
P("    三种可能，必须用单跑 trades.csv 定案：")
P("      (a) 手数不是 0.01（fixed 没被应用 / BASE 覆盖）")
P("      (b) 止盈不是 200 点（参数没被应用）")
P("      (c) MT5 的 net/PF 口径与我的理解不同（例如把未平仓的浮动盈亏计入了 GP）")
P("    → 若是 (c)，则 g2-pure 的『正收益』= **赢的已实现 + 亏的还挂着**，整批结论作废。")
P()

# ---------------------------------------------------------------- §4 浮亏未实现
P("=" * 104)
P("§4 ★★【事实】所有『盈利』行的回撤都是灾难级")
P("=" * 104)
prof = [r for r in pure if r["_net"] > 0]
P(f"  g2-pure 盈利行 = {len(prof)}/{len(pure)}")
P(f"  它们的 dd%：min={min(r['_dd'] for r in prof):.1f}  "
  f"中位={sorted(r['_dd'] for r in prof)[len(prof)//2]:.1f}  max={max(r['_dd'] for r in prof):.1f}")
P(f"  它们的 trades：min={min(r['_tr'] for r in prof):.0f}  max={max(r['_tr'] for r in prof):.0f}"
  f"   → 笔/年 = {min(r['_tr'] for r in prof)/3:.0f} ~ {max(r['_tr'] for r in prof)/3:.0f}")
P(f"  ★任何一行 dd 都 > 43%，用户的可接受上限是 30–40%。")
P(f"  ★而且 BasketStopPct=0 ⇒ 亏损篮子【永不被平】，dd 反映的是浮动亏损，不是已实现亏损。")
P()

# ---------------------------------------------------------------- §5 g2-cd
P("=" * 104)
P("§5 【事实】g2-cd（冷却 × 篮子止损）：冷却有效，但 PF 只是勉强 >1")
P("=" * 104)
P(f"  pass={len(cd)}  盈利={sum(1 for r in cd if r['_net']>0)}")
best = max(cd, key=lambda r: r["_net"])
P(f"  最好：pass {best['pass']}  cooldown={best['params']['InpCooldownMinAfterStop']}min  "
  f"stop={best['params']['InpBasketStopPct']}%  net={best['_net']:+.2f}  PF={best['_pf']:.3f}  "
  f"trades={best['_tr']:.0f} ({best['_tr']/3:.0f}笔/年)  dd={best['_dd']:.2f}%")
P(f"     毛边际/笔 = {best['_ep']+SPREAD_USD:+.4f}  = 点差的 {(best['_ep']+SPREAD_USD)/SPREAD_USD:.2f} 倍")
P(f"     3 年总点差 = {best['_tr']*SPREAD_USD:.1f} USD = 入金 300 的 {best['_tr']*SPREAD_USD/300*100:.1f}%")
P()
P(f"{'stop%':>7}{'n':>4}{'net 均值':>11}{'net 最好':>10}{'dd 均值':>9}{'dd 最大':>9}")
P("-" * 60)
for s in ("5.0", "7.5", "10.0", "12.5", "15.0"):
    g = [r for r in cd if r["params"]["InpBasketStopPct"] == s]
    if not g: continue
    P(f"{s:>7}{len(g):>4}{sum(r['_net'] for r in g)/len(g):>11.2f}"
      f"{max(r['_net'] for r in g):>10.2f}{sum(r['_dd'] for r in g)/len(g):>9.1f}"
      f"{max(r['_dd'] for r in g):>9.1f}")
P()
P("★读法：①止损【收紧】到 7.5% 才出现正 net（mean −113.77，最好 +111.36）—— 方向与直觉一致；")
P("        ②但**冷却越短越差**（60min 那一列全是 −265 ~ −293），说明死亡螺旋是真的；")
P("        ③即便如此，最好那行的 dd 仍有 45.2%，PF 只有 1.028 —— **这是噪声量级的边际，不是 edge**。")
P()

# ---------------------------------------------------------------- §6 与冒烟对比
P("=" * 104)
P("§6 ★【事实】冒烟 0/25 与 g2-pure 15/20 的差别，到底差在哪？")
P("=" * 104)
P("  冒烟 smokeL： BasketStopPct=15  Cooldown=0   MaxLayers=8   窗口 12 个月   net 全负  dd 72–99%")
P("  g2-pure     ： BasketStopPct=0   Cooldown=0   MaxLayers=1–4 窗口 36 个月   net 部分正  dd 43–100%")
P("  ★两个变量同时变了（止损 15→0、层数 8→1–4、窗口 12→36 个月）。")
P("  ★但 §1 已经把层数这一维单独钉死了：**层数 1→4 单调变差，4 层直接爆仓。**")
P("  ★剩下的是『止损 15% → 0』：把亏损篮子从『被实现』变成『一直挂着』。")
P("  ★所以『15/20 盈利』最可能的解释是：**我们只是停止了实现亏损**，而不是找到了 edge。")
P("  → 这必须用单跑 baskets.csv（看 exit_reason 分布与 max_float_pct）定案。")
P()

(HERE / "analysis_batch2.txt").write_text("\n".join(OUT), encoding="utf-8")
print("=" * 80)
print(f"g2-pure: {len(pure)} pass, net>0 = {sum(1 for r in pure if r['_net']>0)}")
for n in (1,2,3,4):
    g=[r for r in pure if int(r['params']['InpMaxLayers'])==n]
    print(f"  layers={n}: PF mean = {sum(r['_pf'] for r in g)/len(g):.3f}  net mean = {sum(r['_net'] for r in g)/len(g):8.2f}  dd mean = {sum(r['_dd'] for r in g)/len(g):5.1f}%")
print(f"g2-cd  : {len(cd)} pass, net>0 = {sum(1 for r in cd if r['_net']>0)}")
print(f"report -> {HERE/'analysis_batch2.txt'}")
print("=" * 80)
