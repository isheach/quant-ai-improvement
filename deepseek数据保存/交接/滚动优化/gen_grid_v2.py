#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
滚动优化线 —— v2 网格生成器（验证段 + 测试段），★命名彻底消歧

背景（为什么必须有这个 v2）：
    我在第一/二批里把 "train" 与 "test" 的网格 id **都用了 `-t-`**：
        第一批  wf-w0-t-on  = **训练段** 2024.08.01~2025.01.31
        第二批  wf-w0-t-on  = **测试段** 2025.05.01~2025.07.31   ← 同名！
    总调度的去重逻辑是"grid_id 已在 outbox 里就跳过" → 第二节那 6 个**测试网格从未真跑**。
    后果：outbox 里 864 行**全部是训练段**（我已逐段核对），
          **我手上没有任何 out-of-sample 数据**，拼接 OOS 曲线还无从谈起。

    ★命名约定（以后固定）：
        wf-<win>-tr-<dir>   训练段   (已跑完，无需重发)
        wf-<win>-va-<dir>   验证段   (本批)
        wf-<win>-te-<dir>   测试段   (本批)
    三个段名互不相同 → 去重逻辑不可能再误跳。

用法:
    python gen_grid_v2.py            # 生成 inbox_grid_v2_滚动优化.jsonl
    python gen_grid_v2.py --dry
"""
import datetime as dt
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(HERE, "inbox_grid_v2_滚动优化.jsonl")
EA = os.path.join(BASE, "mql5", "dshtools", "dsh_BtcSwing.mq5")

HOLDOUT = dt.date(2026, 6, 1)
TS = "2026-09-12T09:20:00+08:00"

WINDOWS = {
    "w0": {"train": ("2024.08.01", "2025.01.31"), "valid": ("2025.02.01", "2025.04.30"),
           "test": ("2025.05.01", "2025.07.31")},
    "w1": {"train": ("2024.11.01", "2025.04.30"), "valid": ("2025.05.01", "2025.07.31"),
           "test": ("2025.08.01", "2025.10.31")},
    "w2": {"train": ("2025.02.01", "2025.07.31"), "valid": ("2025.08.01", "2025.10.31"),
           "test": ("2025.11.01", "2026.01.31")},
}

# ★验证段与测试段都用**与训练段完全同构的 5 轴**（已经跑通 144 pass 的结构），
#   避免任何"结构不同导致优化不启动"的可能。
#   验证段：Bars 用 3 档 48/144/240 → 4*3*3*3*2 = 216
#   测试段：Bars 用 2 档 48/240    → 4*3*2*3*2 = 144（与训练段逐字相同）
VALID_OPT = {
    "InpSL_ATR":           [1.0, 0.5, 2.5],   # 1.0 / 1.5 / 2.0 / 2.5   (4)
    "InpDonchianBars":     [24, 24, 72],      # 24 / 48 / 72            (3)
    "InpFilterEMA":        [50, 75, 200],     # 50 / 125 / 200          (3)
    "InpMaxBarsInTrade":   [48, 96, 240],     # 48 / 144 / 240          (3)
    "InpFilterSlopeBars":  [5, 5, 10],        # 5 / 10                  (2)
}
TEST_OPT = {
    "InpSL_ATR":           [1.0, 0.5, 2.5],   # (4)
    "InpDonchianBars":     [24, 24, 72],      # (3)
    "InpMaxBarsInTrade":   [48, 192, 240],    # 48 / 240                (2)
    "InpFilterEMA":        [50, 75, 200],     # (3)
    "InpFilterSlopeBars":  [5, 5, 10],        # (2)
}

FIXED_COMMON = {
    "InpLatencyMs": "300",
    "InpRiskPct": "1.5",
    "InpUseVolNormalize": "true",
    "InpAllowMinLotOvershoot": "true",
    "InpMinLotMaxRiskPct": "3.0",
    "InpTF": "16385",                # ★数字，不用 PERIOD_H1
    "InpFilterTF": "16408",          # ★数字，不用 PERIOD_D1
    "InpUseTrendFilter": "true",
    "InpFilterRequireSlope": "true",
    "InpATRPeriod": "14",
    "InpUseChandelier": "true",
    "InpBE_ATR": "0.0",
    "InpTP_ATR": "0.0",
    "InpUseSessionFilter": "false",
    "InpUseDailyStop": "true",
    "InpDailyLossPct": "5.0",
    "InpUseDDKill": "true",
    "InpMaxDDPct": "25.0",
    "InpDDCooldownMin": "1440",
    "InpWriteAudit": "true",
    "InpVerboseLog": "false",
}

SEGNAME = {"train": "tr", "valid": "va", "test": "te"}


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
    dry = "--dry" in sys.argv
    allowed = ea_inputs()
    for k in list(FIXED_COMMON) + list(VALID_OPT) + list(TEST_OPT):
        assert k in allowed, "★参数名 EA 不认: %s" % k

    reqs = []
    for wid in sorted(WINDOWS):
        for direction in ("on", "off"):
            for phase, opt in (("valid", VALID_OPT), ("test", TEST_OPT)):
                a, b = WINDOWS[wid][phase]
                fixed = dict(FIXED_COMMON)
                fixed["InpAllowShort"] = "true" if direction == "on" else "false"
                reqs.append({
                    "grid_id": "wf-%s-%s-%s" % (wid, SEGNAME[phase], direction),
                    "ts": TS,
                    "expert": "btcswing",
                    "symbol": "btc",
                    "from": a,
                    "to": b,
                    "fixed": fixed,
                    "opt": {k: list(v) for k, v in opt.items()},
                    "why": ("[WF] %s %s段(%s~%s) AllowShort=%s | %s"
                            % (wid.upper(), phase, a, b, fixed["InpAllowShort"],
                               "验证段选参：在训练段候选里挑 1 个（与训练段同构的 %d 组）"
                               % prod(opt) if phase == "valid" else
                               "★测试段（第二次提交：第一次因 grid_id 与训练段同名被去重跳过）"
                               "与训练段逐字相同的 %d 组，保证选出的参数必在其中" % prod(opt))),
                    "priority": "high",
                    "win_id": wid,
                    "phase": phase,
                    "expect_passes": prod(opt),
                })

    # ---- 自检 ----
    ids = [r["grid_id"] for r in reqs]
    assert len(set(ids)) == len(ids), "grid_id 重复"
    # ★关键自检：不得与第一批训练段 id 冲突
    for r in reqs:
        assert r["grid_id"].split("-")[2] in ("va", "te"), "★段名必须是 va/te"
        assert dt.datetime.strptime(r["to"], "%Y.%m.%d").date() < HOLDOUT, \
            "★%s 触及留白: %s" % (r["grid_id"], r["to"])
        assert r["fixed"]["InpLatencyMs"] == "300"
        assert r["fixed"]["InpTF"] == "16385" and r["fixed"]["InpFilterTF"] == "16408"
        for k, v in r["opt"].items():
            assert len(levels(*v)) >= 2, "★%s 的 %s 档数 <2" % (r["grid_id"], k)
    print("自检通过: %d 个网格, id 唯一且段名为 va/te(不与训练段 tr 冲突), "
          "300ms, TF 为数字, 每轴档数>=2, 无一触及留白段" % len(reqs))

    if dry:
        print("\n[dry] 未写文件。样例:\n" + json.dumps(reqs[0], ensure_ascii=False, indent=2))
        return 0

    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        for r in reqs:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("已写入: %s  (%d 行)" % (OUT, len(reqs)))

    print("\n=== 网格清单 ===")
    for r in reqs:
        print("  %-14s %s ~ %s  AllowShort=%-5s %3d passes"
              % (r["grid_id"], r["from"], r["to"], r["fixed"]["InpAllowShort"], r["expect_passes"]))
    tot = sum(r["expect_passes"] for r in reqs)
    print("\n总 pass = %d  ≈ %.1f 分钟（~50 tests/min；若单 pass 慢 3 倍则 %.1f 分钟）"
          % (tot, tot / 50.0, tot / 50.0 * 3))
    return 0


if __name__ == "__main__":
    sys.exit(main())
