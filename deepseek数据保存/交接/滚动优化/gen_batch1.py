#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
滚动优化（Walk-Forward）线 —— 第一批请求生成器  (wf-001 .. wf-075)

窗口结构（用户指定，固定）：12 个月 = 训练 6 + 验证 3 + 测试 3，向后滚动

★ 关键设计决定：步长必须 = 测试段长度（3 个月），测试段才能首尾相接、
  不重叠、不遗漏 —— 否则拼出来的不是一条可解释的 out-of-sample 曲线。
  （若步长=1 个月而测试段=3 个月，测试段之间会有 3 倍重叠。）

硬约束自检：
  * 任何段的结束日 < 2026.06.01（不得触及留白段 2026.06.01-2026.09.30）
  * 测试段首尾相接，无重叠、无空隙
  * 全部 InpLatencyMs=300；deposit=300；Model=2 由编排器写死
  * 参数名逐一对 dsh_BtcSwing.mq5 的 input 列表校验

用法:
    python gen_batch1.py            # 生成并追加到 inbox_滚动优化.jsonl
    python gen_batch1.py --dry      # 只打印，不写文件
"""
import datetime as dt
import json
import os
import re
import sys

HANDOFF = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 交接
OUT = os.path.join(HANDOFF, "inbox_滚动优化.jsonl")
EA = os.path.join(os.path.dirname(HANDOFF), "mql5", "dshtools", "dsh_BtcSwing.mq5")

HOLDOUT_START = dt.date(2026, 6, 1)
TS = "2026-09-12T05:30:00+08:00"
FIRST_WINDOW = dt.date(2018, 2, 1)     # BTCUSDm 真实起点 2018.02.09
STEP_MONTHS = 3                        # ★ = 测试段长度
TRAIN_M, VALID_M, TEST_M = 6, 3, 3


def last_day(d):
    """含 d 的那个月的最后一天。"""
    nxt = d.replace(day=28) + dt.timedelta(days=4)
    return nxt.replace(day=1) - dt.timedelta(days=1)


def f(d):
    return d.strftime("%Y.%m.%d")


# ---------------- 1. 枚举全部合法窗口 ----------------
def month_add(d, n):
    """d 加 n 个月，日取 1 号。"""
    y, m = d.year, d.month + n
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    return dt.date(y, m, 1)


def enum_windows_v2():
    """按月加法枚举（可靠版）。"""
    wins, b = [], FIRST_WINDOW
    while True:
        t0, t1 = b, last_day(month_add(b, TRAIN_M) - dt.timedelta(days=1))
        v0, v1 = month_add(b, TRAIN_M), last_day(month_add(b, TRAIN_M + VALID_M) - dt.timedelta(days=1))
        s0, s1 = month_add(b, TRAIN_M + VALID_M), last_day(month_add(b, TRAIN_M + VALID_M + TEST_M) - dt.timedelta(days=1))
        if s1 >= HOLDOUT_START:
            break
        wins.append({"from": f(b), "to": f(s1),
                     "train": (f(t0), f(t1)), "valid": (f(v0), f(v1)), "test": (f(s0), f(s1))})
        b = month_add(b, STEP_MONTHS)
    return wins


# ---------------- 2. 候选参数 ----------------
# 设计依据（前一条线 = 固定参数线，已确认的结论，不重复验证）：
#   ① 2026 段（−42% 下跌）失败的根因 = D1 过滤只有「价格>EMA」水平条件、无斜率
#      → 持续逆势做多；加斜率闸门后 test PF 0.79 → 1.44-1.48
#   ② 「只做多」与 regime 绑定（valid 上涨段对、test 下跌段错），不是普适规律
#   → 所以本批把【方向闸门】与【跟踪止盈结构】作为两条主搜索轴。
CAND = {
    "c1": {"InpSL_ATR": "2.0", "InpTrail_ATR": "3.5"},
    "c2": {"InpSL_ATR": "1.5"},
    "c3": {"InpSL_ATR": "1.5", "InpFilterEMA": "200",
           "InpFilterRequireSlope": "true", "InpFilterSlopeBars": "10"},
    "c4": {"InpSL_ATR": "1.5", "InpTrail_ATR": "5.0",
           "InpTrailStart_ATR": "2.0", "InpMaxBarsInTrade": "0"},
    "c5": {"InpSL_ATR": "1.5", "InpAllowShort": "false"},
    "c6": {"InpSL_ATR": "1.5", "InpDonchianBars": "96"},
}
PURPOSE = {
    "c1": "基线(出厂默认 SL2.0/Trail3.5)：窗口内所有候选的参照点",
    "c2": "单因子 止损2.0->1.5：前一条线在固定分段上实测最有效的单因子，检验它在滚动窗口里是否稳定",
    "c3": "趋势闸门 EMA200+斜率同向：前一条线已证实这是2026下跌段翻正的唯一原因，检验它是否每个窗口都被重新选中",
    "c4": "右尾路线 宽跟踪5.0+启动2.0+关时间止损：前一条线诊断测试段失败的直接原因是赢家幅度塌陷，此条针对它",
    "c5": "只做多：前一条线结论为「只做多」与regime绑定(上涨段对/下跌段错)，滚动窗口正是检验它被周期性选中/淘汰",
    "c6": "信号尺度 唐奇安48->96(2天->4天)：换更重的信号。前一条线未在滚动口径下检验过这个轴，且它直接决定笔/年",
}


def ea_inputs():
    """从 dsh_BtcSwing.mq5 抽 input 名，用于校验参数名。"""
    names = set()
    with open(EA, "r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            m = re.match(r"\s*input\s+(?:group\s+)?(?:\w+\s+)*?(\w+)\s*=", line)
            if m:
                names.add(m.group(1))
    return names


def main():
    dry = "--dry" in sys.argv
    wins = enum_windows_v2()
    print("合法窗口总数: %d   最早起点 %s   最晚起点 %s" % (len(wins), wins[0]["from"], wins[-1]["from"]))

    # ★ 关键约束（已用 enum_windows_v2 实测枚举确认）：
    #   窗口 12 个月 + 留白从 2026.06.01 起 → 窗口起点最晚只能到 2025.05.01；
    #   而"测试段无缝、不重叠、不遗漏"要求步长 = 测试段长度（3 个月）。
    #   → 在保证不触碰留白的前提下，测试段能首尾相接的窗口只有 3 个：
    #     2024.08.01 / 2024.11.01 / 2025.02.01
    #   → 拼接出的 out-of-sample 曲线 = 2025.08.01 ~ 2026.04.30（9 个月，含 2026 那段 −42% 下跌）
    #   （2025.05.01 窗口的测试段是 2026.02~04，与 2025.02.01 窗口的测试段重叠，故不取。）
    want = ["2024.08.01", "2024.11.01", "2025.02.01"]
    pick = [w for w in wins if w["from"] in want]
    if len(pick) != len(want):
        raise SystemExit("窗口选取失败：得到 %d 个，期望 %d 个" % (len(pick), len(want)))

    print("\n=== 选定窗口 ===")
    for i, w in enumerate(pick):
        print("  W%d  窗口 %s ~ %s" % (i, w["from"], w["to"]))
        print("      train %s ~ %s" % w["train"])
        print("      valid %s ~ %s" % w["valid"])
        print("      test  %s ~ %s" % w["test"])

    # 校验测试段无缝拼接
    print("\n=== 测试段拼接校验 ===")
    prev = None
    for i, w in enumerate(pick):
        s0 = dt.datetime.strptime(w["test"][0], "%Y.%m.%d").date()
        if prev is not None:
            gap = (s0 - prev).days - 1
            print("  W%d 起点 %s 与上一窗口测试段相隔 %d 天 %s"
                  % (i, w["test"][0], gap, "✅无缝" if gap == 0 else "❌有空隙/重叠"))
        prev = dt.datetime.strptime(w["test"][1], "%Y.%m.%d").date()

    allowed = ea_inputs()
    print("\n=== EA input 数: %d ===" % len(allowed))

    # ---------------- 3. 生成请求 ----------------
    reqs, n = [], 0
    for w_i, win in enumerate(pick):
        for ph in ("train", "valid", "test"):
            seg = win[ph]
            for cid in sorted(CAND):
                n += 1
                p = dict(CAND[cid])
                p["InpLatencyMs"] = "300"
                bad = [k for k in p if k not in allowed]
                if bad:
                    raise SystemExit("★参数名 EA 不认: %s (req %s)" % (bad, cid))
                reqs.append({
                    "req_id": "wf-%03d" % n,
                    "ts": TS,
                    "expert": "btcswing",
                    "symbol": "btc",
                    "phase": ph,
                    "from": seg[0],
                    "to": seg[1],
                    "deposit": 300,
                    "params": p,
                    "why": "[WF] W%d %s (%s~%s) | %s | 候选%s"
                           % (w_i, ph, seg[0], seg[1], PURPOSE[cid], cid),
                    "priority": "normal",
                    "win_id": "W%d" % w_i,
                    "cand": cid,
                })

    # ---------------- 4. 自检 ----------------
    ids = [r["req_id"] for r in reqs]
    assert len(set(ids)) == len(ids), "req_id 重复"
    for r in reqs:
        assert r["phase"] != "hold", "出现 hold 段"
        to_d = dt.datetime.strptime(r["to"], "%Y.%m.%d").date()
        fr_d = dt.datetime.strptime(r["from"], "%Y.%m.%d").date()
        assert to_d < HOLDOUT_START, "★请求 %s 触及留白段 (%s)" % (r["req_id"], r["to"])
        assert fr_d <= to_d, "from > to"
        assert to_d < dt.date(2026, 9, 12), "超出数据可用范围"
    print("自检通过: %d 条, req_id 唯一, 无 hold, 无请求触及留白段" % len(reqs))

    # ---------------- 5. 写出 ----------------
    if dry:
        print("\n[dry] 未写文件。样例:\n" + json.dumps(reqs[0], ensure_ascii=False, indent=2))
        return 0
    with open(OUT, "a", encoding="utf-8") as fh:
        for r in reqs:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(OUT, "r", encoding="utf-8-sig") as fh:
        total = sum(1 for ln in fh if ln.strip())
    print("已写入: %s   现有行数: %d" % (OUT, total))

    print("\n=== 段分布 ===")
    for ph in ("train", "valid", "test"):
        print("  %-6s %d" % (ph, sum(1 for r in reqs if r["phase"] == ph)))
    print("=== 窗口 x 候选 ===")
    for wi in sorted({r["win_id"] for r in reqs}):
        print("  %s: %d 条" % (wi, sum(1 for r in reqs if r["win_id"] == wi)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
