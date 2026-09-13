#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
滚动优化线 —— 第二批：验证段 + 测试段网格

依据第一批（训练段 864 pass）的实测结论，见 报告_002.md。

设计决定：
  1. **验证段网格只扫"训练段过关 pass 里出现过的参数值"** —— 这是真正的 walk-forward：
     验证段的作用是"在训练段选出的候选里挑一个"，不是重新做一次全空间搜索。
     参数空间从 144 组收窄到 108 组。
  2. **测试段跑满 144 组** —— 因为测试段要用"该窗口选出的参数"，
     而选出的参数必然是训练段 144 组里的某一个，所以在满网格里一定能找到对应 pass。
  3. 全部数值参数（避免 ENUM_TIMEFRAMES 符号名坑；总调度 2026-09-12 提醒）。

用法:
    python gen_grid2.py            # 生成 inbox_grid2_滚动优化.jsonl
    python gen_grid2.py --dry
"""
import datetime as dt
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
HANDOFF = os.path.dirname(HERE)
BASE = os.path.dirname(HANDOFF)
OUT = os.path.join(HERE, "inbox_grid2v_滚动优化.jsonl")
EA = os.path.join(BASE, "mql5", "dshtools", "dsh_BtcSwing.mq5")
OUTBOX1 = os.path.join(HERE, "outbox_grid_滚动优化.jsonl")

HOLDOUT = dt.date(2026, 6, 1)
TS = "2026-09-12T07:30:00+08:00"

WINDOWS = {
    "w0": {"train": ("2024.08.01", "2025.01.31"), "valid": ("2025.02.01", "2025.04.30"),
           "test": ("2025.05.01", "2025.07.31")},
    "w1": {"train": ("2024.11.01", "2025.04.30"), "valid": ("2025.05.01", "2025.07.31"),
           "test": ("2025.08.01", "2025.10.31")},
    "w2": {"train": ("2025.02.01", "2025.07.31"), "valid": ("2025.08.01", "2025.10.31"),
           "test": ("2025.11.01", "2026.01.31")},
}

# ---- 训练段过关候选里出现过的参数值（由 outbox 实测得出，见报告_002）----
# ★★ 2026-09-12 v2 修订：v1 的验证段（4 个优化轴 / 108 组）6 个网格全部报 0 pass。
#    诊断见 报告_003.md §1：
#      * 总调度给的"某 Y 参数档数<=1"判据**不能解释**我的情况 —— 我实测最小档数 = 3
#      * 但为一次性规避所有可能原因，v2 让验证段与训练段**结构同构**（同样的 5 个优化轴），
#        即与"已跑通 144 pass 的测试网格"只剩取值差异（Bars 用 3 档 48/144/240）
#    v2 验证段 = 4 x 3 x 3 x 3 x 2 = 216 组/网格（覆盖也比 v1 的 108 组更好）
VALID_OPT = {
    "InpSL_ATR":           [1.0, 0.5, 2.5],   # 1.0/1.5/2.0/2.5  (4)
    "InpDonchianBars":     [24, 24, 72],      # 24/48/72         (3)
    "InpFilterEMA":        [50, 75, 200],     # 50/125/200       (3)
    "InpMaxBarsInTrade":   [48, 96, 240],     # 48/144/240       (3)
    "InpFilterSlopeBars":  [5, 5, 10],        # 5/10             (2) ← v2 新增的轴
}
# 测试段网格 = 与训练段完全相同的 144 组，保证"选出的参数"必定在里面
TEST_OPT = {
    "InpSL_ATR":         [1.0, 0.5, 2.5],
    "InpDonchianBars":   [24, 24, 72],
    "InpMaxBarsInTrade": [48, 192, 240],
    "InpFilterEMA":      [50, 75, 200],
    "InpFilterSlopeBars": [5, 5, 10],
}

# ★v2 网格 ID 后缀：总调度按 grid_id 去重，v1 的验证段 id 已被占用（且那 6 个 0 pass）
VALID_SUFFIX = "2"

FIXED_COMMON = {
    "InpLatencyMs": "300",
    "InpRiskPct": "1.5",
    "InpUseVolNormalize": "true",
    "InpAllowMinLotOvershoot": "true",
    "InpMinLotMaxRiskPct": "3.0",
    "InpTF": "16385",                # ★数字写，不用 PERIOD_H1 符号名
    "InpFilterTF": "16408",          # ★数字写
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

    pv, pt = prod(VALID_OPT), prod(TEST_OPT)
    print("验证段网格 = %d 组/网格   测试段网格 = %d 组/网格" % (pv, pt))
    assert pv <= 5000 and pt <= 5000
    for k in list(FIXED_COMMON) + list(VALID_OPT) + list(TEST_OPT):
        assert k in allowed, "★参数名 EA 不认: %s" % k
    print("参数名全部在 dsh_BtcSwing 的 input 列表内 ✅")

    reqs, n = [], 0
    for wid in sorted(WINDOWS):
        for direction in ("on", "off"):
            # ★v2 只发**验证段**：测试段的 6 个网格与第一批窗口/参数空间完全相同，
            #   第一批结果本来就是有效结果（总调度已确认是"复用"而非"重跑"）→ 不重复提交。
            for phase in ("valid",):
                opt = VALID_OPT
                n += 1
                a, b = WINDOWS[wid][phase]
                fixed = dict(FIXED_COMMON)
                fixed["InpAllowShort"] = "true" if direction == "on" else "false"
                gid = "wf-%s-%s%s-%s" % (wid, phase[0], VALID_SUFFIX, direction)
                reqs.append({
                    "grid_id": gid,
                    "ts": TS,
                    "expert": "btcswing",
                    "symbol": "btc",
                    "from": a,
                    "to": b,
                    "fixed": fixed,
                    "opt": {k: list(v) for k, v in opt.items()},
                    "why": ("[WF] %s 验证段(%s~%s) AllowShort=%s | 验证段选参(v2 修订版)："
                            "与训练段同构的 5 轴 %d 组，在训练段候选里挑 1 个，"
                            "不做第二次全空间搜索；v1 的 108 组版本报 0 pass，本版每轴档数>=2"
                            % (wid.upper(), a, b, fixed["InpAllowShort"], prod(opt))),
                    "priority": "high",
                    "win_id": wid,
                    "phase": phase,
                    "expect_passes": prod(opt),
                })

    ids = [r["grid_id"] for r in reqs]
    assert len(set(ids)) == len(ids), "grid_id 重复"
    for r in reqs:
        assert dt.datetime.strptime(r["to"], "%Y.%m.%d").date() < HOLDOUT, \
            "★%s 触及留白: %s" % (r["grid_id"], r["to"])
        assert r["fixed"]["InpLatencyMs"] == "300"
        assert r["fixed"]["InpTF"] == "16385" and r["fixed"]["InpFilterTF"] == "16408", \
            "★TF 必须是数字"
        # ★v2 自检：每个优化轴的档数必须 >= 2（规避"档数<=1 被 MT5 拒优化"的风险）
        for k, v in r["opt"].items():
            a_, s_, b_ = v
            lv, x = 0, a_
            while x <= b_ + 1e-9:
                lv += 1
                x += s_
            assert lv >= 2, "★%s 的 %s 只有 %d 档" % (r["grid_id"], k, lv)
    print("自检通过: %d 个网格, 唯一, 300ms, TF 为数字, 每轴档数>=2, 无一触及留白段" % len(reqs))

    if dry:
        print("\n[dry] 未写文件。样例:\n" + json.dumps(reqs[0], ensure_ascii=False, indent=2))
        return 0

    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        for r in reqs:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("\n已写入: %s  (%d 行)" % (OUT, len(reqs)))
    tot = sum(r["expect_passes"] for r in reqs)
    print("\n=== 网格清单 ===")
    for r in reqs:
        print("  %-16s %s ~ %s  AllowShort=%-5s %3d passes"
              % (r["grid_id"], r["from"], r["to"], r["fixed"]["InpAllowShort"], r["expect_passes"]))
    print("\n总 pass = %d  ≈ %.1f 分钟（按 ~50 tests/min；若单 pass 慢 3 倍则 %.1f 分钟）"
          % (tot, tot / 50.0, tot / 50.0 * 3))
    return 0


if __name__ == "__main__":
    sys.exit(main())
