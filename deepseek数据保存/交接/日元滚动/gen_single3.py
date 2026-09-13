# -*- coding: utf-8 -*-
"""
gen_single3.py —— 针对 g2-pure「15/20 盈利」的★证伪控制组（逐条格式，单跑通道）

为什么必须做：
  分析见 analysis_batch2.txt。三条硬事实说明那个「正收益」不能当 edge：
   ① PF 随层数【严格单调下降】1.618→1.417→1.273→0.572，4 层时 5/5 把 $300 打光
   ② MaxLayers=1 的 5 行是【同一次运行】（1 层时步长用不上），而它是最好的 = "根本没有网格"
   ③ ★算术不自洽：MaxLayers=1/TP=200点/0.01手/123笔，报告的 PF=1.618 需要毛盈利 $203.18，
      而 123 笔全赢也最多 $159.64 → 缺口 $43.54
  单跑通道会写 baskets.csv / trades.csv（优化模式不写），这 7 条能把三条事实全部定案。

输出 inbox_日元滚动_single3.jsonl
"""
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
GRID_SRC = HERE / "dsh_JPYGrid.mq5"
OUT = HERE / "inbox_日元滚动_single3.jsonl"

BLANK_FROM = "2026.06.01"
W_MAIN = ("2022.06.01", "2025.05.31")     # g2-pure / g2-cd 用的窗口
W_OLD = ("2017.01.01", "2022.05.31")      # 前一条线的旧窗口

text = GRID_SRC.read_text(encoding="utf-8", errors="replace")
text = re.sub(r"//[^\r\n]*", "", text)
text = re.sub(r"/\*[\s\S]*?\*/", "", text)
G_IN = re.findall(r"(?m)^\s*input\s+[A-Za-z_]\w*\s+([A-Za-z_]\w*)\s*=", text)
assert len(G_IN) == 36, len(G_IN)

BASE = {
    "InpTFMinutes": "5",
    "InpGridStepPoints": "200.0", "InpTPPoints": "200.0",
    "InpMaxLayers": "1", "InpLotPerLayer": "0.01", "InpLotMultiplier": "1.0",
    "InpMaxLotPerLayer": "0.10", "InpMaxTotalLot": "0.40",
    "InpGridLong": "true", "InpGridShort": "false",
    "InpBasketStopPct": "0", "InpUseBasketTP": "true",
    "InpCooldownMinAfterStop": "0",
    "InpCloseAllFriday": "false", "InpFridayStopHour": "21",
    "InpUseDailyStop": "true", "InpDailyLossPct": "5.0",
    "InpUseDDKill": "true", "InpMaxDDPct": "30.0",
    "InpDDCooldownMin": "1440", "InpStopAfterDDLock": "false",
    "InpUseERGate": "true", "InpMaxER": "0.35", "InpERPeriod": "24",
    "InpUseSessionFilter": "false", "InpTradeStartHour": "0", "InpTradeEndHour": "23",
    "InpMagic": "20260914", "InpWriteAudit": "true", "InpVerboseLog": "false",
    "InpDDMinDepthPct": "2.0", "InpSlippagePoints": "50",
    "InpLatencyMs": "300", "InpLatencyTicks": "0",
}


def fx(**over):
    d = dict(BASE)
    for k, v in over.items():
        assert k in G_IN, f"jpygrid 无参数 {k}"
        d[k] = str(v)
    return d


R = []
# ── c0：★复现 g2-pure pass 4（MaxLayers=1 / step=200 / TP=200 / 无止损），单跑取两个 CSV
R.append(dict(req_id="jyrg-c0-base", expert="jpygrid", symbol="jpy", phase="train",
              window={"from": W_MAIN[0], "to": W_MAIN[1]}, params=fx(),
              why="★控制组基线（复现 g2-pure pass 4：net +77.64 / PF 1.618 / 123 笔 / dd 43.36%）。"
                  "目的：单跑通道会写 baskets.csv + trades.csv，用来定案三件事："
                  "①§3 的算术不自洽（报告 PF 需要的毛利超过『0.01 手走满 200 点』的上限）"
                  "②exit_reason 分布与 max_float_pct（亏损是不是一直挂着没实现）"
                  "③每笔的 vol / entry / exit / pnl 逐笔可核。",
              priority="high"))

# ── c1：★★★决定性 —— MT5 到底认不认【未平仓】的浮动盈亏
R.append(dict(req_id="jyrg-c1-bh", expert="jpygrid", symbol="jpy", phase="train",
              window={"from": W_MAIN[0], "to": W_MAIN[1]},
              params=fx(InpTPPoints="100000.0"),
              why="★★★本批最重要的一条：把止盈设成 100000 点（≈永不平仓）→ 等价于『买入持有』。"
                  "它回答一个决定性的口径问题：**MT5 的 net/PF 到底算不算未平仓的浮动盈亏？**"
                  " · 若 net=0 且 trades=0 ⇒ MT5 只认已实现 ⇒ g2-pure 的『正收益』= 赢的已实现 + 亏的还挂着，整批结论作废；"
                  " · 若 net≈某个非零值 ⇒ MT5 计入了浮动 ⇒ 同时直接量出『什么都不做、只做多 USDJPY 三年』的基准收益，"
                  "   用来判断 g2-pure 的 +77.64 是不是就是这份 beta。",
              priority="high"))

# ── c2：★方向对照
R.append(dict(req_id="jyrg-c2-short", expert="jpygrid", symbol="jpy", phase="train",
              window={"from": W_MAIN[0], "to": W_MAIN[1]},
              params=fx(InpGridLong="false", InpGridShort="true"),
              why="★方向对照：与 c0 逐项相同，只把方向翻成【只做空】。"
                  "USDJPY 2022.06–2025.05 整体上行（135→161→143），若 c0 的 +77.64 是这份 beta，"
                  "那么 c2 必须是大幅负值。**这是把『网格 edge』与『做多 USDJPY 的 beta』分开的唯一干净办法。**",
              priority="high"))

# ── c3：★时期对照
R.append(dict(req_id="jyrg-c3-oldwin", expert="jpygrid", symbol="jpy", phase="train",
              window={"from": W_OLD[0], "to": W_OLD[1]}, params=fx(),
              why="★时期对照：c0 的配置换到前一条线的旧窗口（2017.01–2022.05，5.41 年）。"
                  "这段包含 2018/2019 的低波动年与 2020 的急跌，与 2022–2025 的形态完全不同。"
                  "若 c0 的正收益只在 2022–2025 出现 ⇒ 是时段/beta，不是策略。",
              priority="high"))

# ── c4：★止损开关对照
R.append(dict(req_id="jyrg-c4-stop15", expert="jpygrid", symbol="jpy", phase="train",
              window={"from": W_MAIN[0], "to": W_MAIN[1]},
              params=fx(InpBasketStopPct="15.0"),
              why="★止损开关对照：c0 只改一个参数——把篮子止损从 0 开成 15%。"
                  "冒烟（BasketStopPct=15）是 0/25 盈利；g2-pure（=0）是 15/20。"
                  "**这条直接量出『停止实现亏损』到底贡献了多少 net** —— 如果 c4 比 c0 差很多，"
                  "那 g2-pure 的『正收益』主要来自会计口径，而不是交易优势。",
              priority="high"))

# ── c5：★手数线性检验
R.append(dict(req_id="jyrg-c5-lot2", expert="jpygrid", symbol="jpy", phase="train",
              window={"from": W_MAIN[0], "to": W_MAIN[1]},
              params=fx(InpLotPerLayer="0.02"),
              why="★手数线性检验：c0 只把手数从 0.01 改成 0.02。若手数真的按 0.01 执行，net/PF/dd 应按比例变化"
                  "（net ≈ 2 倍）；若几乎不变 ⇒ 说明**报告里的手数不是 0.01**，§3 的算术缺口就有了答案。",
              priority="medium"))

# ── c6：★g2-cd 最好那一行，取 baskets.csv 看真实 exit_reason
R.append(dict(req_id="jyrg-c6-cdbest", expert="jpygrid", symbol="jpy", phase="train",
              window={"from": W_MAIN[0], "to": W_MAIN[1]},
              params=fx(InpGridStepPoints="300.0", InpTPPoints="300.0", InpMaxLayers="6",
                        InpBasketStopPct="7.5", InpCooldownMinAfterStop="2940"),
              why="★复现 g2-cd pass 21（net +111.36 / PF 1.028 / 2249 笔 / dd 45.22%），"
                  "单跑取 baskets.csv。这条的 PF 只有 1.028、换手 750 笔/年、3 年总点差 = 入金的 48.6%，"
                  "我需要 baskets.csv 的真实 exit_reason 分布与 max_float_pct 来判断它是 edge 还是噪声。",
              priority="high"))


def d2s(s):
    return tuple(int(x) for x in s.split("."))


ids = set()
for e in R:
    i = e["req_id"]
    assert i not in ids, i
    ids.add(i)
    f, t = e["window"]["from"], e["window"]["to"]
    assert d2s(t) < d2s(BLANK_FROM), f"{i} 触及留白段"
    assert d2s(f) < d2s(t)
    p = e["params"]
    for k in p:
        assert k not in ("InpTF", "InpRunTag"), f"{i}: 违规 {k}"
        assert k in G_IN, f"{i}: jpygrid 无参数 {k}"
    assert p["InpLatencyMs"] == "300", f"{i} 缺延迟标记"
    assert p["InpTFMinutes"] == "5"

with OUT.open("w", encoding="utf-8", newline="\n") as fh:
    for e in R:
        fh.write(json.dumps(e, ensure_ascii=False, separators=(",", ":")) + "\n")
raw = OUT.read_bytes()
assert raw[:3] != b"\xef\xbb\xbf"
back = [json.loads(l) for l in raw.decode("utf-8").splitlines() if l.strip()]
assert len(back) == len(R)
print(f"[out ] {OUT.name}: {len(R)} 条, {len(raw)} bytes")
for e in R:
    d = dict(e["params"])
    diff = {k: v for k, v in d.items() if BASE.get(k) != v}
    print(f"  {e['req_id']:<16} {e['window']['from']}→{e['window']['to']}  与基线差异: {diff if diff else '(无=即复现基线)'}")
