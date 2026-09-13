# -*- coding: utf-8 -*-
"""
gen_single4.py —— ★延迟口径定案：确认 BASE_JPYREV 的 InpLatencyTicks=1 假设 + 确定性检验

背景（我已从源码直接确认，不是推断）：
  runexp.py  L88  BASE_BTCSWING : "InpLatencyTicks": "1"
             L109 BASE_JPYREV   : "InpLatencyTicks": "1"
             L122 BASE_MEANREV  : "InpLatencyTicks": "1"
             L206 BASE_PARAMS   : "InpLatencyTicks": "1"
  batch_run.py L158-159: merged = dict(base); merged.update(params)  → params 覆盖 base

  → 我第一批的 jyrg-008 的 params 里【没有】InpLatencyTicks → 落到 base 的 "1"
  → 我第二批的 jyrg-lat0 显式写了 "0" → 覆盖成 0
  → 所以 jyrg-008(1 tick) 与 jyrg-lat0(0 tick) 【本来就该不同】。

  剂量反应曲线（4 点，net 与 dd 都完美单调、jyrg-008 正好落在 1 tick 的位置）：
     ticks   net      PF    trades  dd%
       0   −9.84   0.910    224   7.10   (lat0)
       1  −13.57   0.880    225   8.14   (jyrg-008)
       3  −15.66   0.860    224   9.44   (lat3)
      30  −16.00   0.840    222  10.47   (lat30)

  → 若假设成立，jyrg-lat1 必须【精确复现】jyrg-008 = net −13.57 / PF 0.88 / 225 笔 / dd 8.14%。
"""
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
GRID_SRC = HERE / "dsh_JPYGrid.mq5"
OUT = HERE / "inbox_日元滚动_single4.jsonl"
BLANK_FROM = "2026.06.01"
W_OLD = ("2017.01.01", "2022.05.31")

text = GRID_SRC.read_text(encoding="utf-8", errors="replace")
text = re.sub(r"//[^\r\n]*", "", text)
text = re.sub(r"/\*[\s\S]*?\*/", "", text)
G_IN = re.findall(r"(?m)^\s*input\s+[A-Za-z_]\w*\s+([A-Za-z_]\w*)\s*=", text)

J = {  # jpyrev 单跑参数（逐项抄 runexp.py BASE_JPYREV + 我方覆盖）
    "InpRiskPct": "0.5", "InpMaxLot": "1.00", "InpUseEquityForRisk": "true",
    "InpAllowMinLotOvershoot": "true", "InpMinLotMaxRiskPct": "1.0",
    "InpTFMinutes": "15", "InpMAPeriod": "24", "InpSigmaPeriod": "48",
    "InpEntrySigma": "3.0", "InpNeedReenter": "true", "InpExitFrac": "0.05",
    "InpStopATR": "3.0", "InpMaxBarsInTrade": "12", "InpMaxAdverseATR": "2.0",
    "InpUseRangeFilter": "true", "InpMaxER": "0.35", "InpERPeriod": "24",
    "InpUseSessionFilter": "true", "InpTradeStartHour": "0", "InpTradeEndHour": "23",
    "InpNoFridayLate": "true", "InpFridayStopHour": "20",
    "InpUseDailyStop": "true", "InpDailyLossPct": "3.0",
    "InpUseDDKill": "true", "InpMaxDDPct": "20.0",
    "InpDDCooldownMin": "1440", "InpStopAfterDDLock": "false",
    "InpMagic": "20260913", "InpWriteAudit": "true", "InpVerboseLog": "false",
    "InpDDMinDepthPct": "2.0", "InpSlippagePoints": "50",
    "InpLatencyMs": "300",
}

G = {  # jpygrid 单跑参数 = c0-base（复现 g2-pure pass 4）
    "InpTFMinutes": "5", "InpGridStepPoints": "200.0", "InpTPPoints": "200.0",
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

R = [
    dict(req_id="jyrg-lat1", expert="jpyrev", symbol="jpy", phase="train",
         window={"from": W_OLD[0], "to": W_OLD[1]},
         params=dict(J, InpLatencyTicks="1"),
         why="★★★决定性确认：与 jyrg-lat0 逐项相同，只把 InpLatencyTicks 从 0 改成 1。"
             "我已从源码确认 runexp.py L109 的 BASE_JPYREV 里写着 InpLatencyTicks=\"1\"，"
             "而 jyrg-008 的 params 里没有这个键 → 它落到 base 的 1。"
             "判据（预先写死）：若本条约等于 net −13.57 / PF 0.88 / 225 笔 / dd 8.14%，"
             "则 ①『测试器不确定』被否证 ②BASE=1 被证实 ③jyrg-008 之谜完全闭合。",
         priority="high"),
    dict(req_id="jyrg-lat0r", expert="jpyrev", symbol="jpy", phase="train",
         window={"from": W_OLD[0], "to": W_OLD[1]},
         params=dict(J, InpLatencyTicks="0"),
         why="★确定性重复实验：与 jyrg-lat0 逐项完全相同，独立再跑一次。"
             "判据：必须精确复现 lat0 = net −9.84 / PF 0.91 / 224 笔 / dd 7.10%。"
             "（若它复现而 lat1 也复现 jyrg-008，则确定性在两个不同 tick 数上各得一次证明。）",
         priority="high"),
    dict(req_id="jyrg-c0r", expert="jpygrid", symbol="jpy", phase="train",
         window={"from": "2022.06.01", "to": "2025.05.31"},
         params=dict(G),
         why="★网格 EA 的确定性重复实验：与 jyrg-c0-base 逐项完全相同，独立再跑一次。"
             "判据：必须精确复现 net +77.64 / PF 1.62 / 123 笔 / dd 43.36%。"
             "顺便拿到第二份 baskets.csv（对照两次是否逐笔相同）。",
         priority="medium"),
    dict(req_id="jyrg-tickclock", expert="tickclock", symbol="jpy", phase="train",
         window={"from": "2025.01.01", "to": "2025.01.31"},
         params={"InpRunTag": "tickclock", "InpWriteFile": "true", "InpPrintEvery": "0"},
         why="★★★延迟口径校准（需先编译 dsh_TickClock.mq5 并注册 expert=tickclock）："
             "全项目的延迟都建在 InpLatencyTicks 这个【tick 计数】上，但没人知道 1 tick 等于多少模拟时间。"
             "若 1 tick ≈ 15 秒（Model=2 每根 M1 约 4 个 tick），则『施加了 300ms 延迟』在全项目都不成立："
             "实际是 ~15 秒（50 倍），而 300ms ≈ 0.02 tick —— 在 Model=2 里根本无法表示。"
             "它不交易、不改仓，只统计 ticks / M1 bar 数 / 平均每 tick 模拟秒数。1 个月窗口足够。",
         priority="medium"),
]


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
    if e["expert"] != "tickclock":
        assert e["params"].get("InpLatencyMs") == "300", f"{i}: 缺 InpLatencyMs=300"
    if e["expert"] == "jpygrid":
        for k in e["params"]:
            assert k in G_IN, f"{i}: jpygrid 无参数 {k}"

with OUT.open("w", encoding="utf-8", newline="\n") as fh:
    for e in R:
        fh.write(json.dumps(e, ensure_ascii=False, separators=(",", ":")) + "\n")
raw = OUT.read_bytes()
assert raw[:3] != b"\xef\xbb\xbf"
assert len([l for l in raw.decode("utf-8").splitlines() if l.strip()]) == len(R)
print(f"[out ] {OUT.name}: {len(R)} 条, {len(raw)} bytes")
for e in R:
    print(f"  {e['req_id']:<16} expert={e['expert']:<10} {e['window']['from']}→{e['window']['to']}"
          f"  ticks={e['params'].get('InpLatencyTicks','—')}")
