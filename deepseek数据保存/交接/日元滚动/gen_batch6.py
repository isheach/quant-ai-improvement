# -*- coding: utf-8 -*-
"""
gen_batch6.py —— ① w23 零成交异常的诊断  ② 唯一的未测结构："永不卖出 + 逢跌加仓"

背景
  ① w23（2023.06.01–2026.05.31）两个配置【都是 0 笔、net=0】，**连"买入持有"也是 0 笔**。
     而 dsh_TickClock 在 2025.01 上测到 30,246 个 tick ⇒ 那段数据是存在的。
     → 必须查清：是数据边界、还是我的 EA 有潜在失效模式。这触发硬约束「覆盖率 >=90%」。
  ② 我测过的所有结构都指向同一方向："交易越少越好"（7/7 窗口 + P1/P4 两条止盈曲线都单调趋向买入持有）。
     唯一还没测过的、理论上能【打败买入持有】的结构是：
        MaxLayers>1 + TP=∞（永不卖出）+ Stop=0  →  **逢跌加仓、平均成本下移、永不实现亏损**
     它与买入持有的唯一差别是【入场均价更低】；它的代价是【浮亏更大】。
     ★这是"减少交易"方向的终点之外，唯一还剩的相反方向。

输出 inbox_日元滚动_grid6.jsonl（1 网格）+ inbox_日元滚动_single7.jsonl（4 条）
"""
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
GRID_SRC = HERE / "dsh_JPYGrid.mq5"
OUT_G = HERE / "inbox_日元滚动_grid6.jsonl"
OUT_S = HERE / "inbox_日元滚动_single7.jsonl"

text = GRID_SRC.read_text(encoding="utf-8", errors="replace")
text = re.sub(r"//[^\r\n]*", "", text)
text = re.sub(r"/\*[\s\S]*?\*/", "", text)
G_IN = re.findall(r"(?m)^\s*input\s+[A-Za-z_]\w*\s+([A-Za-z_]\w*)\s*=", text)
assert len(G_IN) == 36

P2 = ("2017.01.01", "2022.05.31")     # 5.41 年，最长的"逆风"窗口（买入持有仅 0.086）
BH = 100000.0

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


GRIDS = [dict(
    grid_id="jyrg-g6-pyr-p2", expert="jpygrid", symbol="jpy",
    **{"from": P2[0], "to": P2[1]},
    fixed=fx(InpTPPoints=BH, InpBasketStopPct="0", InpCooldownMinAfterStop="0"),
    opt={"InpMaxLayers": [1, 1, 8], "InpGridStepPoints": [200.0, 200.0, 1600.0]},
    why="★★② 唯一未测的结构：『永不卖出 + 逢跌加仓』。窗口 = P2（2017.01–2022.05，5.41 年）"
        "—— 这是买入持有表现最差的窗口（收益/回撤 0.086），所以它是最好的压力测试场。"
        "  MaxLayers 1→8（8 档）× 层间距 200→1600（8 档）= 64 组；TP=100000（永不卖出）、Stop=0。"
        "  ★判据（预登记）：若【任何一组】的 收益/回撤 明显高于同窗口买入持有的 0.086，"
        "    则『逢跌加仓、平均成本下移』是**真线索**，我立刻在那一区展开、并撤回'网格不可交付'；"
        "  若全部 ≤ 0.086 或只是『净利更高但 DD 更高』⇒ 该结构同样是风险换收益，判定维持。"
        "  ★注意：TP=∞ ⇒ 全部盈亏在期末被强制平仓时实现，所以这条测的正是'永不卖出'的终值。",
    priority="high")]

S = [
    dict(req_id="jyrg-w23d1", expert="jpygrid", symbol="jpy", phase="train",
         window={"from": "2024.06.01", "to": "2025.05.31"},
         params=fx(InpTPPoints=BH),
         why="★① w23 诊断 A：把窗口缩到【已知有数据】的 1 年（2024.06–2025.05），买入持有。"
             "若这条正常成交 ⇒ w23 的 0 笔是【窗口末端】的问题（数据边界），不是 EA 的问题。",
         priority="high"),
    dict(req_id="jyrg-w23d2", expert="jpygrid", symbol="jpy", phase="train",
         window={"from": "2023.06.01", "to": "2025.05.31"},
         params=fx(InpTPPoints=BH),
         why="★① w23 诊断 B：w23 的起点保留，末端从 2026.05 收到 2025.05（2 年）。"
             "若这条正常 ⇒ 确认问题出在 2025.06–2026.05 这段。",
         priority="high"),
    dict(req_id="jyrg-w23d3", expert="jpygrid", symbol="jpy", phase="train",
         window={"from": "2025.06.01", "to": "2026.05.31"},
         params=fx(InpTPPoints=BH),
         why="★① w23 诊断 C：只跑 w23 的【后半段】（2025.06–2026.05）。"
             "若这条 0 笔 ⇒ 该段没有数据（tester 数据末端早于 2026.05）⇒ w23 应判 REJECT-coverage；"
             "若有成交 ⇒ 问题是窗口组合，需要进一步查。",
         priority="high"),
    dict(req_id="jyrg-w23d4", expert="jpygrid", symbol="jpy", phase="train",
         window={"from": "2023.06.01", "to": "2026.05.31"},
         params=fx(InpTPPoints=BH, InpUseERGate="false"),
         why="★① w23 诊断 D：与 jyrg-g3-w23-bh 逐项相同，只把 ER 闸门关掉。"
             "排除『g_er 在整段都 >0.35 导致永不入场』这个可能性。"
             "若这条有成交 ⇒ 我的 ER 闸门有失效模式，我必须改 EA。",
         priority="high"),
]


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
        assert fx_["InpLatencyMs"] == "300" and fx_["InpLatencyTicks"] == "0", eid
        n = 1
        for k, (a, b, c) in opt.items():
            assert a != 0.0
            cnt = int(round((c - a) / b)) + 1
            assert cnt >= 2
            n *= cnt
        assert n <= 5000
        tot += n
    return tot


ng, ns = check(GRIDS, True), check(S, False)
print(f"[info] grid6   = {len(GRIDS)} 网格 / {ng} pass")
print(f"[info] single7 = {len(S)} 条 / {ns} pass")


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
print("=" * 84)
print(f"合计 {len(GRIDS)+len(S)} 条 / {ng+ns} pass")
print("=" * 84)
