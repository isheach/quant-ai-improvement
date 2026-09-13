# -*- coding: utf-8 -*-
"""
gen_batch4.py —— ★★「1 tick = 83 秒」定案后，必须重测我自己的头条结论

事实（总调度实测，dsh_TickClock）：
    ticks_per_M1 = 1.000          ← Model=2 每根 M1 只产生 1 个 tick
    avg_seconds_per_tick = 83.07  ← 日历平均（含周末/缺bar）
    gap 直方图：99.8% 落在 [60,300) 秒
    → 连续交易时段内 1 tick ≈ 1 根 M1 bar ≈ 60 秒；83.07 是被周末/缺口拉高的
    300ms = 0.00361 tick → ★Model=2 里【无法表示】

后果：我第一批 6 个 W0 网格（648 pass，报告_002 的全部数据）跑在
      InpLatencyTicks = 1 = 被额外施加了 ~60-83 秒延迟。
      → 那不是"300ms 环境"的忠实模拟，而是一个【过度惩罚】。

★★★ 所以我在报告_002 里的头条结论必须在 0 tick 下重测：
   · "M5 训练段盈利数 = 0/108 → 结构性失败"   ← 这句话是 1 tick 下测的
   · "ρ(验证段,测试段)"、"段效应 vs 参数效应"  ← 全是 1 tick 下测的
   · 若 0 tick 下结论翻盘，我的报告_002 就是错的，必须撤回重写。

设计：★完全沿用 W0 的三段、108 组参数空间、窗口，唯一变量 = InpLatencyTicks 1 → 0。
输出 inbox_日元滚动_grid4.jsonl（4 网格 / 432 pass）
"""
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
JPYREV = Path(r"D:\desktop\新量化策略\deepseek数据保存\mql5\dshtools\dsh_JPYRev.mq5")
OUT = HERE / "inbox_日元滚动_grid4.jsonl"

text = JPYREV.read_text(encoding="utf-8", errors="replace")
text = re.sub(r"//[^\r\n]*", "", text)
text = re.sub(r"/\*[\s\S]*?\*/", "", text)
J_IN = re.findall(r"(?m)^\s*input\s+[A-Za-z_]\w*\s+([A-Za-z_]\w*)\s*=", text)
assert "InpLatencyTicks" in J_IN, "dsh_JPYRev 还没有 InpLatencyTicks —— 版本未对齐"

BASE = {
    "InpRiskPct": "0.5", "InpMaxLot": "1.00", "InpUseEquityForRisk": "true",
    "InpAllowMinLotOvershoot": "true", "InpMinLotMaxRiskPct": "1.0",
    "InpMAPeriod": "24", "InpSigmaPeriod": "48", "InpEntrySigma": "1.8",
    "InpNeedReenter": "true", "InpExitFrac": "0.25", "InpStopATR": "3.0",
    "InpMaxBarsInTrade": "12", "InpMaxAdverseATR": "2.0",
    "InpUseRangeFilter": "true", "InpMaxER": "0.35", "InpERPeriod": "24",
    "InpUseSessionFilter": "true", "InpTradeStartHour": "0", "InpTradeEndHour": "23",
    "InpNoFridayLate": "true", "InpFridayStopHour": "20",
    "InpUseDailyStop": "true", "InpDailyLossPct": "3.0",
    "InpUseDDKill": "true", "InpMaxDDPct": "20.0",
    "InpDDCooldownMin": "1440", "InpStopAfterDDLock": "false",
    "InpMagic": "20260913", "InpWriteAudit": "true", "InpVerboseLog": "false",
    "InpDDMinDepthPct": "2.0", "InpSlippagePoints": "50",
    "InpLatencyMs": "300",
    "InpLatencyTicks": "0",          # ★★ 与 W0 的唯一差异：1 → 0
}

WF_SPACE = {
    "InpEntrySigma": [1.2, 0.5, 2.7],
    "InpExitFrac": [0.05, 0.275, 0.60],
    "InpMaxER": [0.25, 0.15, 0.55],
    "InpStopATR": [2.0, 1.0, 4.0],
}
# ★与 W0 完全相同的三段（顺序：tr / va / te）
SEGS = {
    "tr": ("2022.06.01", "2022.11.30"),
    "va": ("2022.12.01", "2023.02.28"),
    "te": ("2023.03.01", "2023.05.31"),
}
SEGNAME = {"tr": "训练段(寻参)", "va": "验证段(选参)", "te": "测试段(OOS)"}


def jfix(tf):
    d = dict(BASE)
    d["InpTFMinutes"] = str(tf)
    for k in d:
        assert k in J_IN, f"jpyrev 无参数 {k}"
    return d


G = []
# ① ★M5 训练段：验证"0/108 盈利"这条头条是否只是 1 tick 惩罚造成的
G.append(dict(grid_id="jyrg-w0tr-m5-0t", expert="jpyrev", symbol="jpy",
              **{"from": SEGS["tr"][0], "to": SEGS["tr"][1]},
              fixed=jfix(5), opt=dict(WF_SPACE),
              why="★★★头条复核：与 jyrg-w0tr-m5 【逐项相同】，唯一变量是 InpLatencyTicks 1→0。"
                  "判据（预登记）：报告_002 声称本网格训练段【盈利数 = 0/108】。"
                  "若 0 tick 下盈利数明显 > 0，则『M5 结构性失败』是【延迟惩罚造成的】，"
                  "我必须撤回该结论并重写报告_002；若仍为 0，则结论加固。",
              priority="high"))
# ②③④ ★M15 三段：把 ρ 解剖与段效应在 0 tick 下整组重测
for seg in ("tr", "va", "te"):
    f, t = SEGS[seg]
    G.append(dict(grid_id=f"jyrg-w0{seg}-m15-0t", expert="jpyrev", symbol="jpy",
                  **{"from": f, "to": t},
                  fixed=jfix(15), opt=dict(WF_SPACE),
                  why=f"★M15 {SEGNAME[seg]} 0-tick 重测：与 jyrg-w0{seg}-m15 逐项相同，只改 InpLatencyTicks。"
                      f"用于在 0 tick 口径下整组重算 ρ(验证段,测试段) 与『段效应 vs 参数效应』。",
                  priority="high" if seg in ("tr", "te") else "medium"))


def d2s(s):
    return tuple(int(x) for x in s.split("."))


ids, tot = set(), 0
for e in G:
    i = e["grid_id"]
    assert i not in ids, i
    ids.add(i)
    assert d2s(e["to"]) < d2s("2026.06.01")
    assert d2s(e["from"]) < d2s(e["to"])
    fx, opt = e["fixed"], e["opt"]
    for k in list(fx) + list(opt):
        assert k not in ("InpTF", "InpRunTag"), f"{i}: 违规 {k}"
        assert k in J_IN, f"{i}: jpyrev 无参数 {k}"
    assert fx["InpLatencyMs"] == "300"
    assert fx["InpLatencyTicks"] == "0", f"{i}: 必须显式 0"
    n = 1
    for k, (a, b, c) in opt.items():
        assert a != 0.0
        cnt = int(round((c - a) / b)) + 1
        assert cnt >= 2
        n *= cnt
    assert n <= 5000
    tot += n
print(f"[info] grid4 = {len(G)} 网格 / {tot} pass")

with OUT.open("w", encoding="utf-8", newline="\n") as fh:
    for e in G:
        fh.write(json.dumps(e, ensure_ascii=False, separators=(",", ":")) + "\n")
raw = OUT.read_bytes()
assert raw[:3] != b"\xef\xbb\xbf"
assert len([l for l in raw.decode("utf-8").splitlines() if l.strip()]) == len(G)
print(f"[out ] {OUT.name}: {len(G)} 条, {len(raw)} bytes")
for e in G:
    print(f"  {e['grid_id']:<22} {e['from']}→{e['to']}  ticks={e['fixed']['InpLatencyTicks']}  combos=108")
