# -*- coding: utf-8 -*-
"""
gen_batch1.py —— 日元滚动 · 网格策略线  第一批请求生成器
输出：
  inbox_日元滚动.jsonl              （A/B/C 组，14 条：静默探针 + 近期段 + 滚动优化 W0）
  inbox_日元滚动_grid1.jsonl        （D 组，4 条：★依赖 dsh_JPYGrid.mq5 编译成功，未编译请勿跑）

自检断言（全部为硬断言，任一失败即终止）：
  ① JSON 合法、无 BOM、ID 唯一
  ② 每条 fixed 必含 InpLatencyMs=300（硬约束）
  ③ 日期绝不触及留白段 2026.06.01–2026.09.30
  ④ opt 每个参数档数 >= 2（MT5 对"档数<=1"的 Y 参数会整体中止优化）
  ⑤ opt 起点 != 0（已知坑）
  ⑥ 各参数档数之积 <= 5000
  ⑦ 参数名必须在对应 EA 的真实 input 清单里（jpyrev 从源码提取；jpygrid 从交付源码提取）
  ⑧ InpTF / InpRunTag 绝不进 fixed 或 opt（坑1 + 不干扰编排器的审计路径约定）
  ⑨ 滚动窗口三段时间首尾无缝（+1 天）
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(r"D:\desktop\新量化策略\deepseek数据保存")
JPYREV = ROOT / "mql5" / "dshtools" / "dsh_JPYRev.mq5"
JPYGRID = HERE / "dsh_JPYGrid.mq5"

MAIN_OUT = HERE / "inbox_日元滚动.jsonl"
GRID_OUT = HERE / "inbox_日元滚动_grid1.jsonl"

BLANK_FROM = "2026.06.01"   # 留白段起（禁止）
DATA_END = "2026.05.31"     # 本线可用数据末尾（避开留白段）


# ---------------------------------------------------------------- input 清单提取
def extract_inputs(path: Path):
    text = path.read_text(encoding="utf-8", errors="replace")
    text = re.sub(r"//[^\r\n]*", "", text)
    text = re.sub(r"/\*[\s\S]*?\*/", "", text)
    names = re.findall(r"(?m)^\s*input\s+[A-Za-z_]\w*\s+([A-Za-z_]\w*)\s*=", text)
    return names


JPYREV_IN = extract_inputs(JPYREV)
JPYGRID_IN = extract_inputs(JPYGRID)
assert len(JPYREV_IN) == 36, f"dsh_JPYRev 参数数异常: {len(JPYREV_IN)}"
assert len(JPYGRID_IN) == 36, f"dsh_JPYGrid 参数数异常: {len(JPYGRID_IN)}"
print(f"[info] dsh_JPYRev input = {len(JPYREV_IN)} 个")
print(f"[info] dsh_JPYGrid input = {len(JPYGRID_IN)} 个")


# ---------------------------------------------------------------- jpyrev 基线（逐项抄源码默认值）
JPYREV_BASE = {
    "InpRiskPct": "0.5",
    "InpMaxLot": "1.00",
    "InpUseEquityForRisk": "true",
    "InpAllowMinLotOvershoot": "true",
    "InpMinLotMaxRiskPct": "1.0",
    "InpMAPeriod": "24",
    "InpSigmaPeriod": "48",
    "InpEntrySigma": "1.8",
    "InpNeedReenter": "true",
    "InpExitFrac": "0.25",
    "InpStopATR": "3.0",
    "InpMaxBarsInTrade": "12",
    "InpMaxAdverseATR": "2.0",
    "InpUseRangeFilter": "true",
    "InpMaxER": "0.35",
    "InpERPeriod": "24",
    "InpUseSessionFilter": "true",
    "InpTradeStartHour": "0",
    "InpTradeEndHour": "23",
    "InpNoFridayLate": "true",
    "InpFridayStopHour": "20",
    "InpUseDailyStop": "true",
    "InpDailyLossPct": "3.0",
    "InpUseDDKill": "true",
    "InpMaxDDPct": "20.0",
    "InpDDCooldownMin": "1440",     # 冷却式解锁（评估口径，非永久锁）
    "InpStopAfterDDLock": "false",  # 评估口径
    "InpMagic": "20260913",
    "InpWriteAudit": "true",
    "InpVerboseLog": "false",
    "InpDDMinDepthPct": "2.0",
    "InpSlippagePoints": "50",
    "InpLatencyMs": "300",          # ★硬约束口径标记
}
# 说明：InpTF 故意不写（坑1：枚举会被写成符号名）；
#       InpRunTag 故意不写（不干扰编排器的审计路径约定）；
#       InpTFMinutes 单值放 fixed（前一条线已验证的做法）。


def jpyrev_fixed(**over):
    d = dict(JPYREV_BASE)
    for k, v in over.items():
        assert k in JPYREV_IN, f"jpyrev 无参数 {k}"
        d[k] = v
    d["InpTFMinutes"] = over.pop("InpTFMinutes", d.get("InpTFMinutes", "5"))
    return d


# ---------------------------------------------------------------- jpygrid 基线
JPYGRID_BASE = {
    "InpMaxLayers": "8",
    "InpLotPerLayer": "0.01",
    "InpLotMultiplier": "1.0",
    "InpMaxLotPerLayer": "0.10",
    "InpMaxTotalLot": "0.40",
    "InpGridLong": "true",
    "InpGridShort": "false",
    "InpBasketStopPct": "15.0",
    "InpUseBasketTP": "true",
    "InpCooldownMinAfterStop": "0",
    "InpCloseAllFriday": "false",
    "InpFridayStopHour": "21",
    "InpUseDailyStop": "true",
    "InpDailyLossPct": "5.0",
    "InpUseDDKill": "true",
    "InpMaxDDPct": "30.0",
    "InpDDCooldownMin": "1440",
    "InpStopAfterDDLock": "false",
    "InpUseERGate": "true",
    "InpMaxER": "0.35",
    "InpERPeriod": "24",
    "InpUseSessionFilter": "false",
    "InpTradeStartHour": "0",
    "InpTradeEndHour": "23",
    "InpMagic": "20260914",
    "InpWriteAudit": "true",
    "InpVerboseLog": "false",
    "InpDDMinDepthPct": "2.0",
    "InpSlippagePoints": "50",
    "InpLatencyMs": "300",
    "InpLatencyTicks": "0",
}


def jpygrid_fixed(tf, **over):
    d = {"InpTFMinutes": str(tf)}
    d.update(JPYGRID_BASE)
    for k, v in over.items():
        assert k in JPYGRID_IN, f"jpygrid 无参数 {k}"
        d[k] = v
    return d


# ================================================================ 组 A：静默根因 / 覆盖率
# 前一条线发现：TrendCore 的 22 条运行里，除 jpy-006（关 RV 闸门）外，
# **所有**运行的首笔成交都精确落在 2017.04.13 14:00:40，且 M5/M15/M30 三个周期完全相同。
# 他们的结论是"关 RV 未打开 2014–2016"（I-8 证伪），但**始终没有定位真因**。
# 本组用 dsh_JPYRev（无 RV 闸门、无确认条件、另一套信号）从三个角度定案：
#   001 全闸门关闭 + 最松阈值 → 若仍 0 笔，则不是闸门问题（是数据/tick 机制）
#   002 括住边界                → 定位首笔成交时刻
#   003 全段默认                → 真实覆盖率分母（覆盖率 >= 90% 是硬约束）
#   004 默认 vs 001 对照         → 默认闸门是否是真凶
silence_fixed = jpyrev_fixed(
    InpTFMinutes="5",
    InpEntrySigma="1.0",          # 最松
    InpNeedReenter="false",       # 关再入确认
    InpUseRangeFilter="false",    # 关 ER 闸门
    InpUseSessionFilter="false",  # 关时段
    InpUseDailyStop="false",      # 关日损
    InpUseDDKill="false",         # 关回撤锁
    InpStopATR="3.0",
    InpMaxBarsInTrade="12",
    InpVerboseLog="true",         # 计数（bars/nosig/…）用计数代替推断
)

A = [
    dict(req_id="jyrg-001", expert="jpyrev", symbol="jpy", phase="train",
         window={"from": "2014.01.14", "to": "2017.04.30"}, params=silence_fixed,
         why="★静默根因探针1/3：jpyrev 无 RV 闸门，且本配置【全闸门关闭+最松阈值】。若此配置在 2014-2017 仍 0 笔，则‘静默’不是闸门问题而是数据/Model=2 取 tick 的问题；若有成交，则前一条线 TrendCore 的静默确由 EA 闸门造成。",
         priority="high"),
    dict(req_id="jyrg-002", expert="jpyrev", symbol="jpy", phase="train",
         window={"from": "2016.01.01", "to": "2018.12.31"}, params=silence_fixed,
         why="★静默根因探针2/3：同配置括住 2017.04.13 边界。看首笔成交时刻是否恰为 2017.04.13（=前一条线三条不同周期的同一时刻），以判定‘数据起点’还是‘信号起点’。",
         priority="high"),
    dict(req_id="jyrg-003", expert="jpyrev", symbol="jpy", phase="train",
         window={"from": "2014.01.14", "to": "2026.05.31"}, params=jpyrev_fixed(InpTFMinutes="5"),
         why="★覆盖率分母：jpyrev 默认参数在可用全段(12.4年，已避开留白段)上的真实笔数与成交跨度。覆盖率>=90% 是硬约束，这条给出分子分母。",
         priority="high"),
    dict(req_id="jyrg-004", expert="jpyrev", symbol="jpy", phase="train",
         window={"from": "2014.01.14", "to": "2017.04.30"}, params=jpyrev_fixed(InpTFMinutes="5"),
         why="静默根因探针3/3：与 jyrg-001 成对，隔离‘默认闸门（ER/时段/日损/回撤锁/再入确认）’是否是 2014-2017 的真凶。",
         priority="medium"),
]

# ================================================================ 组 B：近期段表征（前一条线完全未测）
# 前一条线所有 JPYRev 网格的窗口都是 2017.01.01–2022.05.31。
# 2022.06–2026.05（4 年，含 2022 干预、2024 套息平仓）是**完全空白区**。
B = [
    dict(req_id="jyrg-005", expert="jpyrev", symbol="jpy", phase="train",
         window={"from": "2022.06.01", "to": "2026.05.31"}, params=jpyrev_fixed(InpTFMinutes="5"),
         why="★空白区表征：jpyrev 默认(M5)在 2022.06-2026.05。前一条线的 691 个 pass 没有一个覆盖这 4 年。",
         priority="high"),
    dict(req_id="jyrg-006", expert="jpyrev", symbol="jpy", phase="train",
         window={"from": "2022.06.01", "to": "2026.05.31"},
         params=jpyrev_fixed(InpTFMinutes="15", InpEntrySigma="3.0", InpExitFrac="0.05"),
         why="★旧窗口【笔数>=200 的配置里】PF 最高者(0.910)/224笔/DD7.1% 的 OOS 迁移检验(jpyg-034 pass3)。注意 224笔/5.41年=41.4笔/年 仍【低于】用户 50 笔/年门槛 —— 它是‘最接近门槛的最优’，不是‘过关最优’。在完全未测的 4 年上是否仍成立。",
         priority="high"),
    dict(req_id="jyrg-007", expert="jpyrev", symbol="jpy", phase="train",
         window={"from": "2022.06.01", "to": "2026.05.31"},
         params=jpyrev_fixed(InpTFMinutes="5", InpEntrySigma="4.0", InpStopATR="4.5", InpMaxER="0.25"),
         why="★低频高PF型的迁移：jpyg-029(pass35/pass23)的形态（EntrySigma4.0+宽止损+严ER）在旧窗口是 PF 最高的一族（净亏最小）。近期段是否延续。",
         priority="medium"),
    dict(req_id="jyrg-008", expert="jpyrev", symbol="jpy", phase="train",
         window={"from": "2017.01.01", "to": "2022.05.31"},
         params=jpyrev_fixed(InpTFMinutes="15", InpEntrySigma="3.0", InpExitFrac="0.05"),
         why="★复现锚点：环境/EA 版本对齐检查。与 jpyg-034 pass3 同口径（PF 0.909948 / 224 笔 / DD 7.1043%）。若回填值不等于这三个数，则说明版本或环境已漂移，本线全部结论需打折。",
         priority="high"),
]

# ================================================================ 组 C：滚动优化 W0（6 条网格 = 3 段 × 2 个周期）
# 窗口结构（沿用滚动优化线的规范）：训练 6 个月 / 验证 3 个月 / 测试 3 个月
# W0: train 2022.06.01–2022.11.30 | valid 2022.12.01–2023.02.28 | test 2023.03.01–2023.05.31
# ★步长 = 测试段长度 = 3 个月（否则相邻窗口测试段重叠、拼出的曲线会重复计数）
#
# ★为什么参数空间这么小（108 组）：
#   前一条线已扫过 691 个 pass，本次训练段必须能装进 ≤5000 组合；
#   且滚动优化需要 train/valid/test **三段同空间**（否则该窗口选出的参数在测试段找不到对应 pass）。
#   空间按‘已证实是主旋钮’的 4 个参数构成：
#     周期(TF)   —— 前一条线实证的主旋钮（M15 > M5），★按 TF 拆网格而不是放进 opt（坑1）
#     EntrySigma —— 频率旋钮（1.5 档 → 2500 笔/5.4年；4.0 档 → 100 笔）
#     ExitFrac   —— 唯一能改变盈亏比 R 的旋钮
#     MaxER      —— ER 是 JPY 上已被证实有效的过滤器
#     StopATR    —— 灾难止损量纲
WF_SPACE = {
    "InpEntrySigma": [1.2, 0.5, 2.7],    # 1.2 / 1.7 / 2.2 / 2.7
    "InpExitFrac":   [0.05, 0.275, 0.60],  # 0.05 / 0.325 / 0.60
    "InpMaxER":      [0.25, 0.15, 0.55],   # 0.25 / 0.40 / 0.55
    "InpStopATR":    [2.0, 1.0, 4.0],      # 2.0 / 3.0 / 4.0
}
WF_SEG = {
    "tr": ("2022.06.01", "2022.11.30"),
    "va": ("2022.12.01", "2023.02.28"),
    "te": ("2023.03.01", "2023.05.31"),
}
WF_TF = [5, 15]

C = []
for tfn in WF_TF:
    for seg, (f, t) in WF_SEG.items():
        C.append(dict(
            grid_id=f"jyrg-w0{seg}-m{tfn}", expert="jpyrev", symbol="jpy",
            **{"from": f, "to": t},
            fixed=jpyrev_fixed(InpTFMinutes=str(tfn)),
            opt=dict(WF_SPACE),
            why=("滚动优化 W0·" + {"tr": "训练段(寻参)", "va": "验证段(选参)", "te": "测试段(OOS)"}[seg]
                 + f"·M{tfn}·108 组。三段同空间，保证该窗口选出的参数在测试段一定能反查到 pass。"),
            priority="high" if seg in ("tr", "te") else "medium",
        ))

# ================================================================ 组 D：网格 EA 冒烟（★需先编译 dsh_JPYGrid.mq5）
D = [
    dict(grid_id="jyrg-g-smokeL", expert="jpygrid", symbol="jpy",
         **{"from": "2022.06.01", "to": "2023.05.31"},
         fixed=jpygrid_fixed(5),
         opt={"InpGridStepPoints": [100.0, 100.0, 500.0], "InpTPPoints": [100.0, 100.0, 500.0]},
         why="网格冒烟1：只做多，层间距×止盈距离 5×5=25 组。目的①验证 EA 真能开层/篮子止盈/篮子止损 ②读出 baskets.csv 的 max_float_pct（最坏浮亏）。先跑这一条，若 0 笔立刻停。",
         priority="high"),
    dict(grid_id="jyrg-g-smokeS", expert="jpygrid", symbol="jpy",
         **{"from": "2022.06.01", "to": "2023.05.31"},
         fixed=jpygrid_fixed(5, InpGridLong="false", InpGridShort="true"),
         opt={"InpGridStepPoints": [100.0, 100.0, 500.0], "InpTPPoints": [100.0, 100.0, 500.0]},
         why="网格冒烟2：只做空（与冒烟1 同一窗口/同一空间）。做空要付 -13.3 点/夜 swap（多头 swap=0），这条同时量出方向成本差异。",
         priority="medium"),
    dict(grid_id="jyrg-g-smoke24", expert="jpygrid", symbol="jpy",
         **{"from": "2024.01.01", "to": "2024.12.31"},
         fixed=jpygrid_fixed(5),
         opt={"InpGridStepPoints": [100.0, 100.0, 500.0], "InpTPPoints": [100.0, 100.0, 500.0]},
         why="网格冒烟3：2024 全年（含 8 月套息平仓的急跌）只做多。这是网格最怕的年份，用来量化左尾——BasketStopPct=15 是否被触发、触发几次。",
         priority="high"),
    dict(req_id="jyrg-g-silence", expert="jpygrid", symbol="jpy", phase="train",
         window={"from": "2014.01.14", "to": "2017.04.30"},
         params=jpygrid_fixed(5, InpGridStepPoints="200.0", InpTPPoints="200.0"),
         why="★网格版静默探针：网格核心循环【完全不需要 bar 数据】（只用 tick 价与层间距比较）。若它在 2014-2017 有成交，则前一条线的静默一定是 EA 闸门/取 bar 造成的；若同样 0 笔，则是测试器取不到 tick（Model=2 需要 M1）——这条可与 jyrg-001/002 交叉定案。",
         priority="high"),
]


# ================================================================ 自检
def d2s(s):
    return tuple(int(x) for x in s.split("."))


def check_entries(entries, expert_inputs):
    ids = set()
    total_pass = 0
    for e in entries:
        eid = e.get("grid_id") or e.get("req_id")
        assert eid, "缺 id"
        assert eid not in ids, f"ID 重复: {eid}"
        ids.add(eid)

        is_grid = "grid_id" in e
        assert e["expert"] in ("jpyrev", "jpygrid", "trend", "meanrev", "btcswing"), e["expert"]
        assert e["symbol"] == "jpy"
        inputs = expert_inputs[e["expert"]]

        if is_grid:
            f, t = e["from"], e["to"]
        else:
            f, t = e["window"]["from"], e["window"]["to"]

        # ③ 留白段
        assert d2s(t) < d2s(BLANK_FROM), f"{eid}: to={t} 触及留白段"
        assert d2s(f) <= d2s(DATA_END), f"{eid}: from 越界"
        assert d2s(f) < d2s(t), f"{eid}: 日期区间非法"

        fixed = e.get("fixed") or e.get("params") or {}
        opt = e.get("opt") or {}

        # ⑧ 禁用参数
        for k in list(fixed) + list(opt):
            assert k not in ("InpTF", "InpRunTag"), f"{eid}: 违规使用 {k}"
            assert k in inputs, f"{eid}: {e['expert']} 没有参数 {k}"

        # ② 延迟口径标记
        assert fixed.get("InpLatencyMs") == "300", f"{eid}: fixed 缺 InpLatencyMs=300"
        # InpTFMinutes 必须在 fixed 且为单值（坑1 的绕开方案）
        assert "InpTFMinutes" in fixed, f"{eid}: fixed 缺 InpTFMinutes"
        assert "InpTFMinutes" not in opt, f"{eid}: InpTFMinutes 不得进 opt（会触发档数<=1 整体中止）"

        # ④⑤⑥ opt 检查
        n = 1
        for k, (start, step, stop) in opt.items():
            assert start != 0.0, f"{eid}: {k} 起点=0（已知坑）"
            assert step != 0.0, f"{eid}: {k} 步长=0"
            cnt = int(round((stop - start) / step)) + 1
            assert cnt >= 2, f"{eid}: {k} 只有 {cnt} 档 → MT5 会整体中止优化"
            assert cnt <= 40, f"{eid}: {k} 档数 {cnt} 过多"
            n *= cnt
        assert n <= 5000, f"{eid}: 组合数 {n} > 5000"
        total_pass += n
        e["_combos"] = n
    return total_pass


expert_inputs = {
    "jpyrev": JPYREV_IN,
    "jpygrid": JPYGRID_IN,
    "trend": JPYREV_IN,     # 本批未使用 trend；占位（若用必须换成 TrendCore 的真实清单）
    "meanrev": JPYREV_IN,
    "btcswing": JPYREV_IN,
}

n_abc = check_entries(A + B + C, expert_inputs)
n_d = check_entries(D, expert_inputs)
print(f"[info] A+B+C = {len(A+B+C)} 条，{n_abc} 个 pass")
print(f"[info] D     = {len(D)} 条，{n_d} 个 pass")

# ⑨ 滚动窗口三段时间无缝
for tfn in WF_TF:
    segs = [(e["from"], e["to"]) for e in C if f"m{tfn}" in e["grid_id"]]
    segs_sorted = sorted(segs)
    from datetime import date, timedelta

    def pd(s):
        y, m, d = (int(x) for x in s.split("."))
        return date(y, m, d)

    for i in range(len(segs_sorted) - 1):
        gap = (pd(segs_sorted[i + 1][0]) - pd(segs_sorted[i][1])).days
        assert gap == 1, f"W0 M{tfn}: {segs_sorted[i][1]} → {segs_sorted[i+1][0]} 间隔 {gap} 天，应为 1"

print("[info] 滚动窗口三段时间连续（+1 天）校验通过")


def write_jsonl(path: Path, rows):
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            r = {k: v for k, v in r.items() if not k.startswith("_")}
            fh.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")
    raw = path.read_bytes()
    assert raw[:3] != b"\xef\xbb\xbf", "写了 BOM"
    # 回读校验
    back = [json.loads(l) for l in raw.decode("utf-8").splitlines() if l.strip()]
    assert len(back) == len(rows)
    print(f"[out ] {path.name}: {len(rows)} 条, {len(raw)} bytes")


write_jsonl(MAIN_OUT, A + B + C)
write_jsonl(GRID_OUT, D)

print()
print("=" * 78)
print(f"第一批已生成：主文件 {len(A+B+C)} 条（A组静默 {len(A)} + B组近期 {len(B)} + C组滚动W0 {len(C)}），"
      f"共 {n_abc} 个 pass")
print(f"             网格文件 {len(D)} 条（★依赖 dsh_JPYGrid.mq5 编译成功），共 {n_d} 个 pass")
print("=" * 78)
