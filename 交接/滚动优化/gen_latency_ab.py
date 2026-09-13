#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
滚动优化线 —— `InpLatencyMs` 生效性 A/B 判定（网格级）

背景（总调度 2026-09-12 提出的疑点）：
    JPY 线发现: 两个 `.set` 的 `InpLatencyMs` 分别是 300 与 0，但 36 个 pass 结果逐位完全相同
    → 推断"那批网格用的是修复前的 ex5（延迟是空操作）"，并要求我对自己 2,160 pass 的延迟生效性加保留。

我自己的证据（见 报告_004.md §3）：
    * 我的 EA 副本 `opt_wf-*.ex5` 全部 = 45076 B / MD5 81FE0D31540A / 22:44:01
      = **当前主 ex5 `dsh_BtcSwing.ex5` 逐字节相同**
    * 该 ex5 由 `dsh_BtcSwing.mq5`（22:40:14）编译而来，源码 L87-88/L421-423 **确实包含延迟实现**
    * `Sleep()` 在策略测试器里**是生效的**（MT5 会把它按"交易的额外耗时"计入）
    → **【推断·高置信】我的网格用的是"带延迟实现"的 ex5**

**但"ex5 里有实现"≠"延迟真的改变了成交"。** 要证明后者，必须在**完全相同的窗口 + 完全相同的参数**下，
**只变 `InpLatencyMs`** 跑一组网格，然后逐组合对比。这就是本脚本生成的东西。

★设计要点（控制变量）：
    * 窗口、参数空间、参数取值 = 与已跑完的 `wf-w0-te-*` **完全一致**（144 组）
    * 唯一差别 = `InpLatencyMs` 从 300 改成 **0**
    * 若 144 组逐位全同 → **延迟是空操作，我的全部结论都要作废重跑**
    * 若有差异 → 延迟确实生效，本线结论可用；并顺便量出"300ms 延迟的代价有多大"

用法: python gen_latency_ab.py
"""
import datetime as dt
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(HERE, "inbox_grid_lat_滚动优化.jsonl")
EA = os.path.join(BASE, "mql5", "dshtools", "dsh_BtcSwing.mq5")
HOLDOUT = dt.date(2026, 6, 1)
TS = "2026-09-12T10:30:00+08:00"

# 与 wf-w0-te-* 完全相同的窗口（2025.05.01~2025.07.31）与参数空间
WIN = ("2025.05.01", "2025.07.31")
OPT = {
    "InpSL_ATR":          [1.0, 0.5, 2.5],   # 4
    "InpDonchianBars":    [24, 24, 72],      # 3
    "InpMaxBarsInTrade":  [48, 192, 240],    # 2
    "InpFilterEMA":       [50, 75, 200],     # 3
    "InpFilterSlopeBars": [5, 5, 10],        # 2
}                                            # 4*3*2*3*2 = 144

FIXED = {
    "InpRiskPct": "1.5", "InpUseVolNormalize": "true",
    "InpAllowMinLotOvershoot": "true", "InpMinLotMaxRiskPct": "3.0",
    "InpTF": "16385", "InpFilterTF": "16408",
    "InpUseTrendFilter": "true", "InpFilterRequireSlope": "true",
    "InpATRPeriod": "14", "InpUseChandelier": "true",
    "InpBE_ATR": "0.0", "InpTP_ATR": "0.0",
    "InpUseSessionFilter": "false", "InpUseDailyStop": "true",
    "InpDailyLossPct": "5.0", "InpUseDDKill": "true",
    "InpMaxDDPct": "25.0", "InpDDCooldownMin": "1440",
    "InpWriteAudit": "true", "InpVerboseLog": "false",
    # ★这两个是 A/B 的唯一变量
    # InpLatencyMs 在下面按组设置
}


def levels(a, s, b):
    out, x = [], a
    while x <= b + 1e-9:
        out.append(round(x, 10))
        x += s
    return out


def prod(opt):
    n = 1
    for v in opt.values():
        n *= len(levels(*v))
    return n


def ea_inputs():
    names = set()
    with open(EA, "r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            m = re.match(r"\s*input\s+(?:group\s+)?(?:\w+\s+)*?(\w+)\s*=", line)
            if m:
                names.add(m.group(1))
    return names


def main():
    allowed = ea_inputs()
    for k in list(FIXED) + list(OPT) + ["InpLatencyMs", "InpAllowShort"]:
        assert k in allowed, "★参数名 EA 不认: %s" % k
    n = prod(OPT)
    assert n == 144, "期望 144 组，得到 %d" % n
    print("A/B 网格: 窗口 %s~%s, %d 组/网格" % (WIN[0], WIN[1], n))

    reqs = []
    for lat in ("0", "300"):
        fixed = dict(FIXED)
        fixed["InpLatencyMs"] = lat
        fixed["InpAllowShort"] = "false"      # 与已跑的 wf-w0-te-off 对齐（方向不是本次变量）
        reqs.append({
            "grid_id": "wf-w0-lat%s" % lat,
            "ts": TS,
            "expert": "btcswing",
            "symbol": "btc",
            "from": WIN[0],
            "to": WIN[1],
            "fixed": fixed,
            "opt": {k: list(v) for k, v in OPT.items()},
            "why": ("[WF] ★InpLatencyMs 生效性 A/B：lat=%s，窗口/参数空间与 wf-w0-te-off 完全一致，"
                    "唯一变量是延迟。与 lat300 逐组合对比：全同→延迟是空操作（本线结论须作废重跑）；"
                    "有差异→延迟生效并量出 300ms 的代价" % lat),
            "priority": "high",
            "expect_passes": n,
        })

    assert len({r["grid_id"] for r in reqs}) == 2
    for r in reqs:
        assert dt.datetime.strptime(r["to"], "%Y.%m.%d").date() < HOLDOUT
        for k, v in r["opt"].items():
            assert len(levels(*v)) >= 2
    print("自检通过: 2 个网格 / %d pass, id 唯一, 每轴档数>=2, 不触及留白" % (2 * n))

    if "--dry" in sys.argv:
        print(json.dumps(reqs[0], ensure_ascii=False, indent=2))
        return 0

    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        for r in reqs:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("已写入: %s" % OUT)
    print("\n=== 清单 ===")
    for r in reqs:
        print("  %-14s %s ~ %s  InpLatencyMs=%-4s %d passes"
              % (r["grid_id"], r["from"], r["to"], r["fixed"]["InpLatencyMs"], r["expect_passes"]))
    print("\n总 pass = %d ≈ %.1f 分钟" % (2 * n, 2 * n / 50.0))
    print("\n★判据：跑完后把 wf-w0-lat300 与已跑的 wf-w0-te-off 对比，再把 wf-w0-lat0 与之对比。")
    print("   若 lat0 与 lat300 **逐位全同** → 延迟在本 EA/本环境下是空操作 → 本线全部结论须作废重跑。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
