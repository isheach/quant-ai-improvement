# -*- coding: utf-8 -*-
"""
gen_batch2.py —— 日元滚动 · 网格策略线  第二批请求生成器
（基于第一批回填的实测结论设计，不是拍脑袋）

输出（4 个文件）：
  inbox_日元滚动_grid1.jsonl   【替换】3 个网格 / 75 pass —— 网格跨窗口排名稳定性（ρ 问题用在网格上）
  inbox_日元滚动_grid2.jsonl   【新增】8 个网格 / 236 pass —— ★网格参数空间主扫描（本批重点）
  inbox_日元滚动_wf2.jsonl     【新增】6 个网格 / 648 pass —— 滚动优化 W1/W2（只 M15，把 ρ 的 n 从 1 提到 3）
  inbox_日元滚动_single2.jsonl 【新增】4 条逐条 —— 网格静默探针 + ★延迟 A/B（用家长新加的 InpLatencyTicks）

自检断言与第一批相同（留白段/延迟标记/档数>=2/起点!=0/组合数<=5000/参数名对源码/InpTF&InpRunTag 禁用/
InpTFMinutes 只进 fixed/窗口日期合法）。
"""
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(r"D:\desktop\新量化策略\deepseek数据保存")
JPYREV = ROOT / "mql5" / "dshtools" / "dsh_JPYRev.mq5"
JPYGRID = HERE / "dsh_JPYGrid.mq5"

OUT_G1 = HERE / "inbox_日元滚动_grid1.jsonl"
OUT_G2 = HERE / "inbox_日元滚动_grid2.jsonl"
OUT_WF2 = HERE / "inbox_日元滚动_wf2.jsonl"
OUT_S2 = HERE / "inbox_日元滚动_single2.jsonl"

BLANK_FROM = "2026.06.01"
DATA_END = "2026.05.31"


def extract_inputs(path: Path):
    text = path.read_text(encoding="utf-8", errors="replace")
    text = re.sub(r"//[^\r\n]*", "", text)
    text = re.sub(r"/\*[\s\S]*?\*/", "", text)
    return re.findall(r"(?m)^\s*input\s+[A-Za-z_]\w*\s+([A-Za-z_]\w*)\s*=", text)


J_IN = extract_inputs(JPYREV)
G_IN = extract_inputs(JPYGRID)
print(f"[info] dsh_JPYRev input = {len(J_IN)} 个（家长重编译后多了 InpLatencyTicks）")
print(f"[info] dsh_JPYGrid input = {len(G_IN)} 个")
assert "InpLatencyTicks" in J_IN, "dsh_JPYRev 没有 InpLatencyTicks —— 版本未对齐！"
assert "InpLatencyTicks" in G_IN
assert len(G_IN) == 36

# ================================================================ jpyrev 基线
JPYREV_BASE = {
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
    "InpLatencyMs": "300", "InpLatencyTicks": "0",
}


def jfix(tf, **over):
    d = {"InpTFMinutes": str(tf)}
    d.update(JPYREV_BASE)
    for k, v in over.items():
        assert k in J_IN, f"jpyrev 无参数 {k}"
        d[k] = str(v)
    return d


# ================================================================ jpygrid 基线
GRID_BASE = {
    "InpTFMinutes": "5",
    "InpGridStepPoints": "300.0", "InpTPPoints": "300.0",
    "InpMaxLayers": "6", "InpLotPerLayer": "0.01", "InpLotMultiplier": "1.0",
    "InpMaxLotPerLayer": "0.10", "InpMaxTotalLot": "0.40",
    "InpGridLong": "true", "InpGridShort": "false",
    "InpBasketStopPct": "10.0", "InpUseBasketTP": "true",
    "InpCooldownMinAfterStop": "1440",
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


def gfix(**over):
    d = dict(GRID_BASE)
    for k, v in over.items():
        assert k in G_IN, f"jpygrid 无参数 {k}"
        d[k] = str(v)
    return d


W_MAIN = ("2022.06.01", "2025.05.31")   # 3 年，完全空白区
SMOKE_OPT = {"InpGridStepPoints": [100.0, 100.0, 500.0], "InpTPPoints": [100.0, 100.0, 500.0]}

# ================================================================ 文件 1：网格跨窗口排名稳定性
# 第一批 smokeL（2022.06–2023.05）已跑：25 组全亏，最好 PF 0.995。
# ★最有价值的追问不是"再扫一遍"，而是：**同一批 25 个参数，在另一个窗口里，排名还一样吗？**
#   这正是"验证段选参有没有预测力"（ρ 问题）在【网格】上的直接检验，且只需 25 pass/窗口。
G1 = []
for tag, (f, t) in [("w2", ("2023.06.01", "2024.05.31")),
                    ("w3", ("2024.06.01", "2025.05.31")),
                    ("w4", ("2019.06.01", "2020.05.31"))]:
    G1.append(dict(
        grid_id=f"jyrg-g1-{tag}", expert="jpygrid", symbol="jpy",
        **{"from": f, "to": t},
        fixed=gfix(),
        opt=dict(SMOKE_OPT),
        why=f"网格跨窗口排名稳定性 {tag}（{f}–{t}）：与已跑的 jyrg-g-smokeL(2022.06–2023.05) "
            f"【完全同一批 25 个参数】。用于算 ρ(窗口A 排名, 窗口B 排名) —— "
            f"这是『验证段选参有无预测力』在网格上的直接检验。25 pass。",
        priority="high" if tag == "w3" else "medium"))

# ================================================================ 文件 2：★网格参数空间主扫描
# 依据第一批 §5b 的铁证：25 组里只有 1 组毛边际为正(+$0.0501) 且它 < 点差($0.0649)
#   → 冒烟测的那个区域（100–500 点、8 层、止损 15%、无冷却）**毛优势本身是负的**。
#   → 所以第二批必须换区域，而不是在同一区域加密。
# 六个新方向（都是冒烟完全没碰过的维度）：
#   ① 篮子止损 + 冷却（治"连环 15% 止损把账户打穿"）
#   ② 最大层数（治"深篮子"）
#   ③ 大尺度 步长×止盈（200–1000 点，毛边际随目标距离放大）
#   ④ 小止盈/大步长（高胜率小赢区，完全未测）
#   ⑤ ★纯网格：关掉篮子止损（把风险交给 MaxLayers 的几何上限）
#   ⑥ ER 闸门严宽（现在 0.35 从未扫过）
#   ⑦ 只做空（多头 swap=0 / 空头 −13.3 点/夜，方向成本从未量过）
G2 = [
    dict(grid_id="jyrg-g2-cd", expert="jpygrid", symbol="jpy",
         **{"from": W_MAIN[0], "to": W_MAIN[1]},
         fixed=gfix(), 
         opt={"InpCooldownMinAfterStop": [60, 720, 4380], "InpBasketStopPct": [5.0, 2.5, 15.0]},
         why="★方向①：篮子止损后冷却 × 止损深度（7×5=35）。第一批显示 DD 高达 72–99%，"
             "机制是『连环 15% 止损』。本网格直接检验冷却能否止住死亡螺旋。",
         priority="high"),
    dict(grid_id="jyrg-g2-ml", expert="jpygrid", symbol="jpy",
         **{"from": W_MAIN[0], "to": W_MAIN[1]},
         fixed=gfix(),
         opt={"InpMaxLayers": [3, 1, 9], "InpBasketStopPct": [5.0, 2.5, 15.0]},
         why="★方向②：单向最大层数 × 止损深度（7×5=35）。层数=左尾的几何上限；"
             "≤4 层时满仓浮亏仅 2.6%，篮子止损永不触发（此时层数本身就是止损）。",
         priority="high"),
    dict(grid_id="jyrg-g2-geo", expert="jpygrid", symbol="jpy",
         **{"from": W_MAIN[0], "to": W_MAIN[1]},
         fixed=gfix(),
         opt={"InpGridStepPoints": [200, 200, 1000], "InpTPPoints": [200, 200, 1000]},
         why="★方向③：大尺度 步长×止盈（200–1000 点，5×5=25）。冒烟只到 500 点；"
             "毛边际/笔 ≈ 0.0064893×TP，所以更大目标才有机会盖过点差 $0.0649。",
         priority="high"),
    dict(grid_id="jyrg-g2-geo2", expert="jpygrid", symbol="jpy",
         **{"from": W_MAIN[0], "to": W_MAIN[1]},
         fixed=gfix(),
         opt={"InpGridStepPoints": [300, 100, 900], "InpTPPoints": [25, 25, 200]},
         why="★方向④：小止盈 × 大步长（TP 25–200 点 / 步长 300–900 点，7×8=56）。"
             "完全未测区域：篮子只需从均价回撤很小就能平，胜率极高但每笔赢很小。",
         priority="high"),
    dict(grid_id="jyrg-g2-pure", expert="jpygrid", symbol="jpy",
         **{"from": W_MAIN[0], "to": W_MAIN[1]},
         fixed=gfix(InpBasketStopPct="0", InpCooldownMinAfterStop="0", InpTPPoints="200.0"),
         opt={"InpMaxLayers": [1, 1, 4], "InpGridStepPoints": [100, 100, 500]},
         why="★方向⑤：纯网格【关掉篮子止损】（层数 1–4 × 步长 100–500，4×5=20）。"
             "把手数固定 0.01、层数封顶后，最大敞口本身就是有界的；这条直接问"
             "『网格到底有没有毛优势』，而不让止损机制污染答案。MaxLayers=1 就是退化基准（单仓无止损）。",
         priority="high"),
    dict(grid_id="jyrg-g2-small", expert="jpygrid", symbol="jpy",
         **{"from": W_MAIN[0], "to": W_MAIN[1]},
         fixed=gfix(InpGridStepPoints="300.0", InpBasketStopPct="8.0", InpTPPoints="300.0"),
         opt={"InpMaxLayers": [1, 1, 4], "InpTPPoints": [300, 300, 1500]},
         why="★方向⑥：少层数 × 大止盈（1–4 层 × 300–1500 点，4×5=20）。"
             "把『每笔赢』做大、把『层数』压小，直接改善 1:3.7 的赢亏比。",
         priority="high"),
    dict(grid_id="jyrg-g2-er", expert="jpygrid", symbol="jpy",
         **{"from": W_MAIN[0], "to": W_MAIN[1]},
         fixed=gfix(),
         opt={"InpMaxER": [0.15, 0.05, 0.35], "InpMaxLayers": [2, 2, 8]},
         why="方向⑦：ER 震荡闸门严宽 × 层数（5×4=20）。ER 闸门从第一批起一直固定在 0.35、"
             "从未扫过；这条量它到底贡献多少（若全无差异，说明它不是有效的 regime 判别）。",
         priority="medium"),
    dict(grid_id="jyrg-g2-short", expert="jpygrid", symbol="jpy",
         **{"from": W_MAIN[0], "to": W_MAIN[1]},
         fixed=gfix(InpGridLong="false", InpGridShort="true"),
         opt={"InpGridStepPoints": [200, 200, 1000], "InpTPPoints": [200, 200, 1000]},
         why="方向⑧：只做空 × 大尺度（5×5=25）。USDJPYm 的 swap_long=0 / swap_short=−13.3 点/夜，"
             "做空每夜付成本；这条量化方向成本，同时是最简单的方向对称性检查。",
         priority="medium"),
]

# ================================================================ 文件 3：滚动优化 W1/W2（只 M15）
# 第一批 W0 实测：M5 训练段 0/108 盈利（结构性无法启动）；M15 有 17/108。
# → 扩展窗口只保留 M15，把 ρ 的 n 从 1 提到 3。这是"数据驱动的取舍"，不是图省事。
WF_SPACE = {
    "InpEntrySigma": [1.2, 0.5, 2.7],
    "InpExitFrac": [0.05, 0.275, 0.60],
    "InpMaxER": [0.25, 0.15, 0.55],
    "InpStopATR": [2.0, 1.0, 4.0],
}
WINDOWS = {
    "w1": {"tr": ("2022.09.01", "2023.02.28"), "va": ("2023.03.01", "2023.05.31"),
           "te": ("2023.06.01", "2023.08.31")},
    "w2": {"tr": ("2022.12.01", "2023.05.31"), "va": ("2023.06.01", "2023.08.31"),
           "te": ("2023.09.01", "2023.11.30")},
}
WF2 = []
for w, segs in WINDOWS.items():
    for seg, (f, t) in segs.items():
        WF2.append(dict(
            grid_id=f"jyrg-{w}{seg}-m15", expert="jpyrev", symbol="jpy",
            **{"from": f, "to": t},
            fixed=jfix(15),
            opt=dict(WF_SPACE),
            why=(f"滚动优化 {w.upper()}·" + {"tr": "训练段", "va": "验证段", "te": "测试段(OOS)"}[seg]
                 + f"·M15·108 组。★只跑 M15：W0 实测 M5 训练段 0/108 盈利（结构性无法启动），"
                   f"而 M15 有 17/108。目的是把 ρ(验证段,测试段) 的样本从 n=1 提到 n=3。"),
            priority="medium" if seg != "te" else "high"))

# ================================================================ 文件 4：逐条
S2 = [
    dict(req_id="jyrg-g-silence", expert="jpygrid", symbol="jpy", phase="train",
         window={"from": "2014.01.14", "to": "2017.04.30"},
         params=gfix(InpGridStepPoints="200.0", InpTPPoints="200.0"),
         why="★网格版静默探针（修好格式后重新提交）：网格核心循环【完全不需要 bar 数据】"
             "（只用 tick 价与层间距比较）。若无成交 ⇒ 是 Model=2 取不到 tick；若有成交 ⇒ "
             "前一条线的静默一定是 EA 闸门/取 bar 造成的。可与 jyrg-001/002 交叉定案。",
         priority="high"),
    dict(req_id="jyrg-lat0", expert="jpyrev", symbol="jpy", phase="train",
         window={"from": "2017.01.01", "to": "2022.05.31"},
         params=jfix(15, InpEntrySigma="3.0", InpExitFrac="0.05", InpLatencyTicks="0"),
         why="★延迟 A/B 对照臂 0-tick（与已排队的 jyrg-008 逐项相同 → 同时是免费的可复现性检查）。"
             "窗口/参数 = 旧窗口『笔数>=200 里 PF 最高』的配置（PF 0.909948 / 224 笔 / DD 7.1043%）。",
         priority="high"),
    dict(req_id="jyrg-lat3", expert="jpyrev", symbol="jpy", phase="train",
         window={"from": "2017.01.01", "to": "2022.05.31"},
         params=jfix(15, InpEntrySigma="3.0", InpExitFrac="0.05", InpLatencyTicks="3"),
         why="★延迟 A/B 处理臂：InpLatencyTicks=3。与 jyrg-lat0 只差这一个参数。"
             "★这是全项目第一次用【在测试器里真正生效】的延迟机制做 A/B —— "
             "此前三条线测的都是 Sleep(InpLatencyMs)，已被证实是空操作。",
         priority="high"),
    dict(req_id="jyrg-lat30", expert="jpyrev", symbol="jpy", phase="train",
         window={"from": "2017.01.01", "to": "2022.05.31"},
         params=jfix(15, InpEntrySigma="3.0", InpExitFrac="0.05", InpLatencyTicks="30"),
         why="★延迟 A/B 剂量臂：InpLatencyTicks=30（约等于一次真实挂单往返）。"
             "用来画出『延迟 tick 数 → 净利衰减』的曲线，判断 300ms 延迟到底值多少钱。",
         priority="medium"),
]


# ================================================================ 自检
def d2s(s):
    return tuple(int(x) for x in s.split("."))


def check(entries, expert_inputs):
    ids, total = set(), 0
    for e in entries:
        eid = e.get("grid_id") or e.get("req_id")
        assert eid and eid not in ids, f"ID 重复/缺失: {eid}"
        ids.add(eid)
        inputs = expert_inputs[e["expert"]]
        is_grid = "grid_id" in e
        f, t = (e["from"], e["to"]) if is_grid else (e["window"]["from"], e["window"]["to"])
        assert d2s(t) < d2s(BLANK_FROM), f"{eid}: 触及留白段"
        assert d2s(f) < d2s(t) <= d2s(DATA_END), f"{eid}: 日期非法"
        fixed = e.get("fixed") or e.get("params") or {}
        opt = e.get("opt") or {}
        for k in list(fixed) + list(opt):
            assert k not in ("InpTF", "InpRunTag"), f"{eid}: 违规使用 {k}"
            assert k in inputs, f"{eid}: {e['expert']} 没有参数 {k}"
        assert fixed.get("InpLatencyMs") == "300", f"{eid}: 缺 InpLatencyMs=300"
        assert "InpTFMinutes" in fixed and "InpTFMinutes" not in opt, f"{eid}: InpTFMinutes 位置错"
        n = 1
        for k, (start, step, stop) in opt.items():
            assert start != 0.0, f"{eid}: {k} 起点=0（已知坑）"
            cnt = int(round((stop - start) / step)) + 1
            assert cnt >= 2, f"{eid}: {k} 只有 {cnt} 档 → MT5 会整体中止"
            assert cnt <= 60, f"{eid}: {k} 档数 {cnt} 过多"
            n *= cnt
        assert n <= 5000, f"{eid}: 组合数 {n} > 5000"
        e["_c"] = n
        total += n
    return total


EI = {"jpyrev": J_IN, "jpygrid": G_IN}
n1 = check(G1, EI)
n2 = check(G2, EI)
n3 = check(WF2, EI)
n4 = check(S2, EI)
print(f"[info] grid1（跨窗口稳定性）= {len(G1)} 网格 / {n1} pass")
print(f"[info] grid2（★主扫描）     = {len(G2)} 网格 / {n2} pass")
print(f"[info] wf2（滚动 W1/W2）     = {len(WF2)} 网格 / {n3} pass")
print(f"[info] single2（逐条）       = {len(S2)} 条 / {n4} pass")

# W1/W2 三段时间连续性
from datetime import date


def pd(s):
    y, m, d = (int(x) for x in s.split("."))
    return date(y, m, d)


for w, segs in WINDOWS.items():
    seq = [segs["tr"], segs["va"], segs["te"]]
    for i in range(2):
        gap = (pd(seq[i + 1][0]) - pd(seq[i][1])).days
        assert gap == 1, f"{w}: {seq[i][1]} → {seq[i+1][0]} 间隔 {gap} 天"
print("[info] W1/W2 三段时间连续（+1 天）校验通过")


def write_jsonl(path, rows):
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps({k: v for k, v in r.items() if not k.startswith("_")},
                                ensure_ascii=False, separators=(",", ":")) + "\n")
    raw = path.read_bytes()
    assert raw[:3] != b"\xef\xbb\xbf"
    assert len([l for l in raw.decode("utf-8").splitlines() if l.strip()]) == len(rows)
    print(f"[out ] {path.name}: {len(rows)} 条, {len(raw)} bytes")


write_jsonl(OUT_G1, G1)
write_jsonl(OUT_G2, G2)
write_jsonl(OUT_WF2, WF2)
write_jsonl(OUT_S2, S2)

print()
print("=" * 90)
print(f"第二批合计 = {len(G1)+len(G2)+len(WF2)+len(S2)} 条 / {n1+n2+n3+n4} pass")
print(f"  网格文件 3 个（grid1 替换 / grid2 新增 / wf2 新增）+ 逐条 1 个（single2）")
print("=" * 90)
