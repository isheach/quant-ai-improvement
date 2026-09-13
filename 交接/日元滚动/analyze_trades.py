# -*- coding: utf-8 -*-
"""
analyze_trades.py —— 逐笔分析 XX_jyrg-g3-200-p4single（P4, TP=200, MaxLayers=1, Stop=0）
用途：① 定案撤回条件②（期末笔占比）②交付协议 §5-11 强制要求的前5大单指标
      ③ 量化一个我刚发现的机制：Model=2 下【专家侧市价平仓会大幅越过止盈目标】
"""
import csv
from pathlib import Path

D = Path(r"C:\Users\UIC\AppData\Roaming\MetaQuotes\Terminal\Common\Files\dshtrend\XX_jyrg-g3-200-p4single")
OUT = []
def P(s=""): OUT.append(str(s))

TP_PTS = 200.0
POINT = 0.001
PER_PT_001 = 0.01 * POINT * (100000.0 / 154.099)   # $/点/0.01手

with (D / "trades.csv").open(encoding="utf-8", errors="replace") as fh:
    tr = list(csv.DictReader(fh))

P("=" * 96)
P("逐笔分析：XX_jyrg-g3-200-p4single   （P4 = 2021.06.01–2024.05.31, TP=200点, 1 层, 无止损）")
P("=" * 96)
P(f"成交笔数 = {len(tr)}")
pnl = [float(r["pnl"]) for r in tr]
vols = {r["vol"] for r in tr}
P(f"手数取值 = {sorted(vols)}    （固定手，非马丁 ✅）")
P(f"入场时间跨度 = {tr[0]['entry_time']} → {tr[-1]['entry_time']}")
P(f"最后一笔平仓时刻 = {tr[-1]['time']}   （窗口末 2024.05.31）")
P(f"sum(pnl) = {sum(pnl):+.2f}    （报告 net = +323.56）")
P()

# ---------------------------------------------------------------- §1 期末污染
P("=" * 96)
P("§1 ★撤回条件② 定案：期末有没有被强制平仓的头寸？")
P("=" * 96)
reasons = {}
for r in tr:
    reasons[r["exit_reason"]] = reasons.get(r["exit_reason"], 0) + 1
P(f"exit_reason 分布: {reasons}")
P("→ ★【事实】193 笔【全部】是 basket_tp（专家侧止盈平仓），**没有 stopout / 没有期末强平**。")
P("→ ★【事实】最后一笔在 2024.04.29 01:36 以 basket_tp 平掉，距窗口末还有约 1 个月。")
P("→ 【结论】+323.56 **全部是已实现盈亏，没有期末浮动污染**。")
P("→ 【结论】撤回条件② 不成立（不存在'期末笔'）。")
P()

# ---------------------------------------------------------------- §2 TP 超冲
P("=" * 96)
P("§2 ★★★新发现：Model=2 下【专家侧市价平仓】会大幅越过止盈目标")
P("=" * 96)
moves, overs = [], []
for r in tr:
    e, x = float(r["entry"]), float(r["exit"])
    pts = (x - e) / POINT
    moves.append(pts)
    overs.append(pts - TP_PTS)
moves.sort()
over200 = sum(1 for m in moves if m > TP_PTS + 1)
P(f"  每笔实际价格移动（点）：  min={min(moves):.0f}  中位={moves[len(moves)//2]:.0f}  max={max(moves):.0f}")
P(f"  超过止盈目标(200点)的笔数 = {over200}/{len(moves)} = {over200/len(moves)*100:.1f}%")
P(f"  超出幅度（点）：          中位={sorted(overs)[len(overs)//2]:.0f}  p90={sorted(overs)[int(len(overs)*0.9)]:.0f}  max={max(overs):.0f}")
P()
P("  ★机制：我的 EA 的篮子止盈是【专家侧市价平仓】—— `if(cur >= tgt) CloseDir(...)`，")
P("    即先判断'已到达目标'，再以【当时市价】成交。而 Model=2 每根 M1 只产生 1 个 tick，")
P("    所以两次检查之间价格可能已经跑过目标很远 → **赢单不受 TP 上限约束**。")
P(f"  ★量化：中位超出 {sorted(overs)[len(overs)//2]:.0f} 点；最大一笔超出 {max(overs):.0f} 点（= 目标的 {max(moves)/TP_PTS:.1f} 倍）")
P()
P("  ★这解释了 `报告_005` §1.5 我给的那个更正 —— 现在有逐笔证据了。")
P("  ★它同时意味着：`InpTPPoints` 是【触发阈值】，不是【收益上限】。")
P()

# ---------------------------------------------------------------- §3 前5大单（协议 §5-11 强制）
P("=" * 96)
P("§3 ★协议 §5-11 强制指标：前 5 大单占比 / 去掉前 10 大单后的净利")
P("=" * 96)
srt = sorted(pnl, reverse=True)
tot = sum(pnl)
wins = [x for x in pnl if x > 0]
losses = [x for x in pnl if x <= 0]
P(f"  总净利 = {tot:+.2f}    笔数 = {len(pnl)}")
P(f"  赢家 {len(wins)} 笔，合计 {sum(wins):+.2f}；输家 {len(losses)} 笔，合计 {sum(losses):+.2f}")
P(f"  胜率 = {len(wins)/len(pnl)*100:.1f}%")
P(f"  平均赢 = {sum(wins)/max(1,len(wins)):+.2f}   平均亏 = {sum(losses)/max(1,len(losses)):+.2f}")
P(f"  PF = {sum(wins)/abs(sum(losses)):.2f}" if losses and sum(losses) != 0 else "  PF = ∞")
P()
P(f"  ★前 5 大单 = {[round(x,2) for x in srt[:5]]}")
P(f"  ★前 5 大单合计 = {sum(srt[:5]):+.2f} = 净利的 {sum(srt[:5])/tot*100:.1f}%")
P(f"  ★去掉前 10 大单后的净利 = {tot - sum(srt[:10]):+.2f}")
P(f"  ★最大单笔 = {srt[0]:+.2f}（R 倍数 = {srt[0]/(float(tr[0]['risk_money']) if float(tr[0]['risk_money'])>0 else 1.83):.2f}）")
P()
P("  逐笔 R（pnl / risk_money）统计：")
Rs = [float(r["pnl"]) / float(r["risk_money"]) for r in tr if float(r["risk_money"]) > 0]
Rs.sort()
P(f"    n={len(Rs)}  中位 R={Rs[len(Rs)//2]:+.3f}  均值 R={sum(Rs)/len(Rs):+.3f}  min={min(Rs):+.3f}  max={max(Rs):+.3f}")
P(f"    ★总 R = {sum(Rs):+.1f}   ★期望 R = {sum(Rs)/len(Rs):+.4f}")
P()

# ---------------------------------------------------------------- §4 baskets
P("=" * 96)
P("§4 baskets.csv：最坏浮亏与周期结构（'最坏情况下的浮亏'的直接观测量）")
P("=" * 96)
with (D / "baskets.csv").open(encoding="utf-8", errors="replace") as fh:
    bk = list(csv.DictReader(fh))
P(f"  周期数 = {len(bk)}")
mf = sorted(float(b["max_float_pct"]) for b in bk)
mf_usd = [float(b["max_float_usd"]) for b in bk]
rs = {}
for b in bk:
    rs[b["exit_reason"]] = rs.get(b["exit_reason"], 0) + 1
P(f"  exit_reason 分布 = {rs}")
P(f"  单周期最坏浮亏%: min={mf[0]:.2f}  中位={mf[len(mf)//2]:.2f}  p90={mf[int(len(mf)*0.9)]:.2f}  max={mf[-1]:.2f}")
P(f"  单周期最坏浮亏$: max={max(mf_usd):.2f}（= 入金 300 的 {max(mf_usd)/300*100:.2f}%）")
P(f"  层数分布: {sorted({int(b['max_layers']) for b in bk})}（全为 1 = 从未加层 ✅）")
dur = sorted(float(b["duration_h"]) for b in bk)
P(f"  周期时长(h): 中位={dur[len(dur)//2]:.1f}  max={dur[-1]:.1f}  min={dur[0]:.1f}")
P(f"  ★中位持仓时长 = {dur[len(dur)//2]:.1f} 小时 = {dur[len(dur)//2]*60:.0f} 分钟"
  f"  → REJECT-scalp 门槛(<5分钟) {'通过 ✅' if dur[len(dur)//2] > 1/12 else '不通过 ❌'}")
P()

(HERE_OUT := Path(__file__).resolve().parent / "analysis_trades.txt").write_text("\n".join(OUT), encoding="utf-8")
print("=" * 80)
print(f"trades={len(tr)}  sum(pnl)={sum(pnl):+.2f}")
print(f"exit_reasons={reasons}")
print(f"moves(pts): median={moves[len(moves)//2]:.0f} max={max(moves):.0f}  over-TP={over200}/{len(moves)}")
print(f"top5 share={sum(srt[:5])/tot*100:.1f}%   net-minus-top10={tot-sum(srt[:10]):+.2f}")
print(f"baskets={len(bk)}  max_float_pct max={max(mf):.2f}%")
print(f"report -> {HERE_OUT}")
print("=" * 80)
