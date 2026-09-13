# -*- coding: utf-8 -*-
"""
gen_batch5.py —— ★★ K-4 触发后的决定性检验（不是我"撤回判定"，是"先把线索验死或验活"）

我在 报告_005 §4.3 预登记了 K-4：
  "任何时期的 收益/回撤 都 < 0.75（用户目标下限）→ 若某时期 >=0.75 ⇒ 那是唯一值得追的线索，
   我立刻撤回'不可交付'判定并展开。"
实测 P4（2021.06–2024.05）触发：买入持有 1.40、网格 TP200 1.10。

★但我在 报告_006 刚立了一条纪律："惊人数字必须标注是分布统计量还是单次抽样；后者不得作为
  方法有效性的证据"。P4 的 1.40 恰好就是【单次抽样】（一个窗口）。所以我不能直接撤回 --
  那会犯我刚写下的那个错误。正确做法：**在撤回之前，把这条线索验死或验活**，并预登记判据。

本批 = 5 类检验：
  ① 方向对照      —— P4 换成只做空。若 +323.56 是 beta ⇒ 必须大幅为负
  ② 期末污染      —— 200-p4 单跑取 trades.csv/baskets.csv：+323.56 里有多少是【期末未平仓】的浮动
  ③ 端点依赖      —— 同长度、起点移 3 个月、期末落在 2024.08 崩盘里
  ④ ★时期分布      —— 8 个三年期窗口（5 新 + 3 已有）看 收益/回撤 的分布；P4 是不是离群值
  ⑤ P4 的止盈曲线  —— TP 200→4800 扫一遍，看"止盈越大越好"在 P4 是否仍成立

输出 inbox_日元滚动_grid5.jsonl（1 网格）+ inbox_日元滚动_single6.jsonl（14 条）
"""
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
GRID_SRC = HERE / "dsh_JPYGrid.mq5"
OUT_G = HERE / "inbox_日元滚动_grid5.jsonl"
OUT_S = HERE / "inbox_日元滚动_single6.jsonl"

text = GRID_SRC.read_text(encoding="utf-8", errors="replace")
text = re.sub(r"//[^\r\n]*", "", text)
text = re.sub(r"/\*[\s\S]*?\*/", "", text)
G_IN = re.findall(r"(?m)^\s*input\s+[A-Za-z_]\w*\s+([A-Za-z_]\w*)\s*=", text)
assert len(G_IN) == 36

P4 = ("2021.06.01", "2024.05.31")          # 触发 K-4 的窗口
P4S = ("2021.09.01", "2024.08.31")         # 同长度、移 3 个月、期末落在 2024.08 崩盘里
WINS = {                                    # ★8 个三年期窗口（P1/P3/P4 已有）
    "w14": ("2014.06.01", "2017.05.31"),
    "w16": ("2016.06.01", "2019.05.31"),
    "w18": ("2018.06.01", "2021.05.31"),
    "w20": ("2020.06.01", "2023.05.31"),
    "w23": ("2023.06.01", "2026.05.31"),
}

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
BH = 100000.0    # 止盈 100000 点 ≈ 永不平仓 = 买入持有


def fx(**over):
    d = dict(BASE)
    for k, v in over.items():
        assert k in G_IN, f"jpygrid 无参数 {k}"
        d[k] = str(v)
    return d


# ── 文件 1：P4 的止盈曲线（1 网格 / 12 pass）
GRIDS = [dict(
    grid_id="jyrg-g3-tp-p4", expert="jpygrid", symbol="jpy",
    **{"from": P4[0], "to": P4[1]}, fixed=fx(),
    opt={"InpTPPoints": [200.0, 400.0, 4800.0]},          # 200,600,...,4800 → 12 档
    why="★⑤ P4 的止盈曲线（TP 200→4800 步 400，12 档）。P1 上已实测【止盈越大越好、趋近买入持有】"
        "（收益/回撤 0.199→0.319）。本网格检验 P4 上是否仍成立 —— 若 P4 上出现相反的单调性"
        "（小止盈更好），那说明 P4 的 +323.56 来自【短线择时】而不是 beta，是真线索；"
        "若同样单调趋向买入持有，则 +323.56 只是 beta。",
    priority="high")]

# ── 文件 2：14 条逐条
S = []
# ① 方向对照
S.append(dict(req_id="jyrg-g3-short-p4", expert="jpygrid", symbol="jpy", phase="train",
              window={"from": P4[0], "to": P4[1]},
              params=fx(InpGridLong="false", InpGridShort="true"),
              why="★★① 方向对照：与 jyrg-g3-200-p4 逐项相同，只翻成【只做空】。"
                  "预登记判据：若 +323.56 是 USDJPY 的 beta，本条必须【大幅为负】。"
                  "参照：P1 上 long +77.64 / short −202.56（同结构，反向幅度约 2 倍）。"
                  "→ 我的预判：本条约等于 −300（账户被打光，DD≈100%）。"
                  "若本条意外为正或接近零，则 P4 的正收益不是 beta，必须展开。",
              priority="high"))
# ② 期末污染：单跑取 CSV
S.append(dict(req_id="jyrg-g3-200-p4single", expert="jpygrid", symbol="jpy", phase="train",
              window={"from": P4[0], "to": P4[1]}, params=fx(),
              why="★★② 复现 jyrg-g3-200-p4（net +323.56 / PF 23.45 / 193 笔 / dd 32.63%）的【单跑】版本，"
                  "取 trades.csv + baskets.csv。目的：PF 23.45 意味着 3 年只有约 $14 的毛亏损 —— "
                  "这是『BasketStopPct=0 ⇒ 亏损永不实现』的结构特征。"
                  "我要逐笔核出：①有多少笔是期末被强制平仓的 ②那笔浮盈占 +323.56 的多少 "
                  "③exit_reason 分布与 max_float_pct。",
              priority="high"))
# ③ 端点依赖
for tag, w in (("bh", BH), ("200", 200.0)):
    S.append(dict(req_id=f"jyrg-g3-{tag}-p4shift", expert="jpygrid", symbol="jpy", phase="train",
                  window={"from": P4S[0], "to": P4S[1]}, params=fx(InpTPPoints=w),
                  why=f"★③ 端点依赖检验（{'买入持有' if w == BH else '网格 TP=200'}）：同 3 年长度、"
                      f"起点从 2021.06 移到 2021.09，**期末从 2024.05 移到 2024.08 —— 正好落在套息平仓的急跌里**。"
                      f"若结果相比 P4 大幅变化，则 P4 的 收益/回撤 是【期末点位决定的】，不是策略能力。",
                  priority="high" if tag == "200" else "medium"))
# ④ 时期分布：5 个新窗口 × 2 配置
for tag, (f, t) in WINS.items():
    for kind, w in (("bh", BH), ("200", 200.0)):
        S.append(dict(req_id=f"jyrg-g3-{tag}-{kind}", expert="jpygrid", symbol="jpy", phase="train",
                      window={"from": f, "to": t}, params=fx(InpTPPoints=w),
                      why=f"★④ 时期分布（{f}–{t}，三年）：{'买入持有' if w == BH else '网格 TP=200'}。"
                          f"与已有的 P1(0.32)/P3(0.53)/P4(1.40)/P2(0.086) 合起来构成 8 个窗口的分布，"
                          f"用来判定 P4 的 1.40 是不是【离群值】。",
                      priority="medium"))


def d2s(s):
    return tuple(int(x) for x in s.split("."))


def check(entries, is_grid):
    ids, tot = set(), 0
    for e in entries:
        eid = e.get("grid_id") or e.get("req_id")
        assert eid and eid not in ids, f"ID 重复 {eid}"
        ids.add(eid)
        f, t = (e["from"], e["to"]) if is_grid else (e["window"]["from"], e["window"]["to"])
        assert d2s(t) < d2s("2026.06.01"), f"{eid} 触及留白段"
        assert d2s(f) < d2s(t)
        fx_ = e["fixed"] if is_grid else e["params"]
        opt = e.get("opt") or {}
        for k in list(fx_) + list(opt):
            assert k not in ("InpTF", "InpRunTag"), f"{eid} 违规 {k}"
            assert k in G_IN, f"{eid} jpygrid 无参数 {k}"
        assert fx_["InpLatencyMs"] == "300"
        assert fx_["InpLatencyTicks"] == "0", f"{eid} 必须显式 0"
        n = 1
        for k, (a, b, c) in opt.items():
            assert a != 0.0
            cnt = int(round((c - a) / b)) + 1
            assert cnt >= 2
            n *= cnt
        tot += n
    return tot


ng = check(GRIDS, True)
ns = check(S, False)
print(f"[info] grid5   = {len(GRIDS)} 网格 / {ng} pass")
print(f"[info] single6 = {len(S)} 条 / {ns} pass")


def write_jsonl(path, rows):
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")
    raw = path.read_bytes()
    assert raw[:3] != b"\xef\xbb\xbf"
    assert len([l for l in raw.decode("utf-8").splitlines() if l.strip()]) == len(rows)
    print(f"[out ] {path.name}: {len(rows)} 条, {len(raw)} bytes")


write_jsonl(OUT_G, GRIDS)
write_jsonl(OUT_S, S)
print("=" * 90)
print(f"合计 {len(GRIDS)+len(S)} 条 / {ng+ns} pass")
print("=" * 90)
