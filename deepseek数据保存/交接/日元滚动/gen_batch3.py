# -*- coding: utf-8 -*-
"""
gen_batch3.py —— ★收官诊断：「买入持有(0.32) 是不是天花板？」

动机（来自报告_003 §2 的最强结果）：
  在 =>1,336 次回测<= 里，收益/回撤比的最高值是 0.32，而它来自「0.01 手买入持有、不做任何交易」。
  c0-base(TP=200) = +77.64 / DD 43.36% = 0.20
  c1-bh  (TP=∞ ) = +104.41 / DD 36.37% = 0.32
  → 两者【只差止盈距离】，而更大的止盈在两个维度上都更好 ⇒ 提示"交易越少越好"。

本批要回答三个问题（都很便宜）：
  ① 止盈距离的形状：在 200 → 30000 点之间，收益/回撤有没有一个比两端都好的中间点？
  ② ★分段检验（项目纪律 #2）：c1-bh 的 0.32 是【一个时段】的数字。
     换成 P2/P3/P4 三个时期，它还是 0.32 吗？
  ③ ★口径校正：c0/c1 都带着 ER 震荡闸门 ⇒ c1-bh 其实不是"纯买入持有"，而是
     "等到第一个低 ER 时刻才买入，然后一直持有"。本批加一条【关闸门】的纯买入持有做对照。

输出 inbox_日元滚动_grid3.jsonl（3 网格 / 32 pass）+ inbox_日元滚动_single5.jsonl（6 条逐条）
全部窗口 to <= 2026.05.31，不触留白段。
"""
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
GRID_SRC = HERE / "dsh_JPYGrid.mq5"
OUT_G = HERE / "inbox_日元滚动_grid3.jsonl"
OUT_S = HERE / "inbox_日元滚动_single5.jsonl"

text = GRID_SRC.read_text(encoding="utf-8", errors="replace")
text = re.sub(r"//[^\r\n]*", "", text)
text = re.sub(r"/\*[\s\S]*?\*/", "", text)
G_IN = re.findall(r"(?m)^\s*input\s+[A-Za-z_]\w*\s+([A-Za-z_]\w*)\s*=", text)
assert len(G_IN) == 36

P1 = ("2022.06.01", "2025.05.31")   # 主窗口（c0/c1 已跑）
P2 = ("2017.01.01", "2022.05.31")   # 旧窗口（c3-oldwin 已跑 TP=200）
P3 = ("2019.06.01", "2022.05.31")   # 3 年
P4 = ("2021.06.01", "2024.05.31")   # 3 年（含 2022 干预 + 2024 套息平仓）

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


GRIDS = [
    dict(grid_id="jyrg-g3-tpmid", expert="jpygrid", symbol="jpy",
         **{"from": P1[0], "to": P1[1]}, fixed=fx(),
         opt={"InpTPPoints": [200.0, 200.0, 2400.0]},
         why="★诊断①（中段）：MaxLayers=1 / 无止损 / ER 门开，止盈 200→2400 步 200（12 档）。"
             "已知两端：TP=200 → +77.64/DD43.36%（=0.20）、TP=∞ → +104.41/DD36.37%（=0.32）。"
             "本条填中间，看收益/回撤是不是单调的（即『交易越少越好』是否成立）。",
         priority="high"),
    dict(grid_id="jyrg-g3-tphi", expert="jpygrid", symbol="jpy",
         **{"from": P1[0], "to": P1[1]}, fixed=fx(),
         opt={"InpTPPoints": [3000.0, 3000.0, 30000.0]},
         why="★诊断①（高段）：同上，止盈 3000→30000 步 3000（10 档）。"
             "用来判断『趋近买入持有』的过程是渐近的还是有拐点。",
         priority="medium"),
    dict(grid_id="jyrg-g3-noer", expert="jpygrid", symbol="jpy",
         **{"from": P1[0], "to": P1[1]}, fixed=fx(InpUseERGate="false"),
         opt={"InpTPPoints": [200.0, 200.0, 2000.0]},
         why="★诊断③（口径校正）：关掉 ER 震荡闸门，止盈 200→2000 步 200（10 档）。"
             "因为 c0/c1 都带着 ER 门，c1-bh 其实不是『纯买入持有』而是"
             "『等到第一个低 ER 时刻才买入、然后一直持有』。本条量出这个闸门对基准值的影响。",
         priority="high"),
]

SINGLES_TAIL = [
    ("jyrg-g3-bh-noer-p1", P1, 100000.0, False,
     "★★纯买入持有（关 ER 门）：与 c1-bh 只差 ERGate=false。这是『什么都不做』的真正基准 —— "
     "若它明显不同于 +104.41，说明 c1-bh 的基准值里混进了 ER 择时的贡献。"),
    ("jyrg-g3-bh-p2", P2, 100000.0, True,
     "★分段检验 P2（2017.01–2022.05，5.41 年）：买入持有在该时期的收益/回撤。"
     "c3-oldwin（TP=200，同期）只有 4.43%/55.17% = 0.08 ⇒ 本批判 0.32 是不是时段特有的。"),
    ("jyrg-g3-200-p3", P3, 200.0, True,
     "★分段检验 P3：TP=200 / ER 门开 / 2019.06–2022.05。"),
    ("jyrg-g3-bh-p3", P3, 100000.0, True,
     "★分段检验 P3：买入持有 / 2019.06–2022.05。与上一条配对。"),
    ("jyrg-g3-200-p4", P4, 200.0, True,
     "★分段检验 P4：TP=200 / ER 门开 / 2021.06–2024.05（含 2022 干预 + 2024 套息平仓）。"),
    ("jyrg-g3-bh-p4", P4, 100000.0, True,
     "★分段检验 P4：买入持有 / 2021.06–2024.05。与上一条配对。"),
]

SINGLES = []
for rid, (f, t), tp, ergate, why in SINGLES_TAIL:
    SINGLES.append(dict(req_id=rid, expert="jpygrid", symbol="jpy", phase="train",
                        window={"from": f, "to": t},
                        params=fx(InpTPPoints=tp, InpUseERGate=("true" if ergate else "false")),
                        why=why, priority="high" if "bh" in rid else "medium"))


def d2s(s):
    return tuple(int(x) for x in s.split("."))


def check(entries, is_grid, limit=5000):
    ids = set()
    tot = 0
    for e in entries:
        eid = e.get("grid_id") or e.get("req_id")
        assert eid and eid not in ids, f"ID 重复/缺失 {eid}"
        ids.add(eid)
        f, t = (e["from"], e["to"]) if is_grid else (e["window"]["from"], e["window"]["to"])
        assert d2s(t) < d2s("2026.06.01"), f"{eid} 触及留白段"
        assert d2s(f) < d2s(t)
        fixed = e["fixed"] if is_grid else e["params"]
        opt = e.get("opt") or {}
        for k in list(fixed) + list(opt):
            assert k not in ("InpTF", "InpRunTag"), f"{eid}: 违规 {k}"
            assert k in G_IN, f"{eid}: jpygrid 无参数 {k}"
        assert fixed.get("InpLatencyMs") == "300", f"{eid}: 缺 InpLatencyMs=300"
        # ★必须显式写 InpLatencyTicks，否则 opt_runner.py L246-248 会默认成 1
        assert fixed.get("InpLatencyTicks") == "0", f"{eid}: 必须显式 InpLatencyTicks=0"
        n = 1
        for k, (a, b, c) in opt.items():
            assert a != 0.0, f"{eid}: {k} 起点=0"
            cnt = int(round((c - a) / b)) + 1
            assert cnt >= 2, f"{eid}: {k} 只有 {cnt} 档"
            n *= cnt
        assert n <= limit
        tot += n
    return tot


ng = check(GRIDS, True)
ns = check(SINGLES, False)
print(f"[info] grid3   = {len(GRIDS)} 网格 / {ng} pass")
print(f"[info] single5 = {len(SINGLES)} 条 / {ns} pass")


def write_jsonl(path, rows):
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")
    raw = path.read_bytes()
    assert raw[:3] != b"\xef\xbb\xbf"
    assert len([l for l in raw.decode("utf-8").splitlines() if l.strip()]) == len(rows)
    print(f"[out ] {path.name}: {len(rows)} 条, {len(raw)} bytes")


write_jsonl(OUT_G, GRIDS)
write_jsonl(OUT_S, SINGLES)
print("=" * 80)
print(f"第三批合计 {len(GRIDS)+len(SINGLES)} 条 / {ng+ns} pass")
print("=" * 80)
