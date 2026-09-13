#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
滚动优化线 —— 第一批「参数网格」生成器（outbox_滚动优化 / inbox_grid_滚动优化.jsonl）

依据: 交接\原生优化接口规范.md (v1)
    opt = {参数名: [起点, 步长, 终点]}  →  总调度转成 .set 的 参数名=val||起点||步长||终点||Y
    档数之积 <= 5000

★ 设计原则（针对规范未明确的部分做保守选择）:
  1. **只用数值参数做优化** —— bool 参数在 .set 里的优化语法是
     `InpX=true||false||0||true||Y`（不是等差三档，规范 §2.1 自己也承认枚举优化要特殊处理）。
     规范没有说明我提交 [false,1,true] 会不会被正确转换，**所以我不依赖它**：
     bool 轴一律拆成**两个独立网格**（一个固定 true、一个固定 false）。
  2. **每个网格的 fixed 里必须显式写 InpLatencyMs=300**（规范 §五-4）。
  3. 窗口只取已裁定的 3 个月步长口径，且**任何段都不触及留白 2026.06**。

用法:
    python gen_grid1.py            # 生成 inbox_grid_滚动优化.jsonl
    python gen_grid1.py --dry      # 只打印
"""
import datetime as dt
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
HANDOFF = os.path.dirname(HERE)                     # 交接
BASE = os.path.dirname(HANDOFF)                     # deepseek数据保存
OUT = os.path.join(HERE, "inbox_grid_滚动优化.jsonl")
EA = os.path.join(BASE, "mql5", "dshtools", "dsh_BtcSwing.mq5")

HOLDOUT = dt.date(2026, 6, 1)
TS = "2026-09-12T06:30:00+08:00"

# ---- 已裁定的 3 个窗口（步长 3 个月 = 测试段长度，测试段无缝拼接）----
WINDOWS = {
    "w0": {"train": ("2024.08.01", "2025.01.31"), "valid": ("2025.02.01", "2025.04.30"),
           "test": ("2025.05.01", "2025.07.31")},
    "w1": {"train": ("2024.11.01", "2025.04.30"), "valid": ("2025.05.01", "2025.07.31"),
           "test": ("2025.08.01", "2025.10.31")},
    "w2": {"train": ("2025.02.01", "2025.07.31"), "valid": ("2025.08.01", "2025.10.31"),
           "test": ("2025.11.01", "2026.01.31")},
}

# ---- 优化轴（全部数值；opt = {名: [起点, 步长, 终点]}）----
# ★预算: 总 pass ≈ (每窗口 pass 数) × 3 窗口，目标 ≤ ~800 passes（约 15–30 分钟）
#   InpSL_ATR 刻意取 4 档跨过 2.0：rep_OPT3 实测 SL≥2.5 → 0 笔（$300 账户最小手闸门），
#   我要用最少的 pass 把这条"有/无交易"边界钉出来。
OPT = {
    # 出场结构（4 档）
    "InpSL_ATR":         [1.0, 0.5, 2.5],     # 1.0 / 1.5 / 2.0 / 2.5 ← 含 0 笔边界
    # 入场尺度
    "InpDonchianBars":   [24, 24, 72],        # 24 / 48 / 72
    "InpMaxBarsInTrade": [48, 192, 240],      # 48 / 240（2 档）
    # 宏观过滤
    "InpFilterEMA":      [50, 75, 200],       # 50 / 125 / 200
    "InpFilterSlopeBars": [5, 5, 10],         # 5 / 10（2 档）
}
# 4 × 3 × 2 × 3 × 2 = 144 组/网格 → ×3 窗口 ×2 方向 = 864 passes

# ---- 固定的"承重"参数（不作为优化轴，但必须钉住，保证可复现 & 与前一条线可比）----
FIXED_COMMON = {
    "InpLatencyMs": "300",          # ★规范 §五-4 强制
    "InpRiskPct": "1.5",
    "InpUseVolNormalize": "true",
    "InpAllowMinLotOvershoot": "true",
    "InpMinLotMaxRiskPct": "3.0",
    "InpTF": "16385",               # H1
    "InpFilterTF": "16408",         # D1
    "InpUseTrendFilter": "true",
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

# 第一批只扫训练段；确认布尔/笔数量级后再发验证段与测试段
PHASE = "train"


def span(levels):
    """[起点,步长,终点] 展开成实际档位，用于自检打印。"""
    a, s, b = levels
    out, x = [], a
    while x <= b + 1e-9:
        out.append(round(x, 10))
        x += s
    return out


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

    # ---- 自检：档数与积 ----
    prod = 1
    print("=== 优化轴档位 ===")
    for k, v in OPT.items():
        lv = span(v)
        prod *= len(lv)
        assert k in allowed, "★参数名 EA 不认: %s" % k
        print("  %-22s %d 档  %s" % (k, len(lv), lv))
    print("\n单网格档数积 = %d  %s" % (prod, "✅ <=5000" if prod <= 5000 else "❌ 超限"))
    assert prod <= 5000, "档数积超限"
    for k in FIXED_COMMON:
        assert k in allowed, "★fixed 参数名 EA 不认: %s" % k

    # ---- 生成 ----
    reqs = []
    n = 0
    for wid in sorted(WINDOWS):
        a, b = WINDOWS[wid][PHASE]
        for direction in ("short_on", "short_off"):
            n += 1
            fixed = dict(FIXED_COMMON)
            fixed["InpAllowShort"] = "true" if direction == "short_on" else "false"
            # RequireSlope 固定 true：斜率闸门是前一条线唯一被证实的修复，保留它做搜索空间
            fixed["InpFilterRequireSlope"] = "true"
            reqs.append({
                "grid_id": "wf-%s-%s-%s" % (wid, PHASE[0], "on" if direction == "short_on" else "off"),
                "ts": TS,
                "expert": "btcswing",
                "symbol": "btc",
                "from": a,
                "to": b,
                "fixed": fixed,
                "opt": {k: list(v) for k, v in OPT.items()},
                "why": ("[WF] %s %s段(%s~%s) 参数扫描 %d 组 | AllowShort=%s RequireSlope=true | "
                        "为滚动窗口寻参；★频率门槛≥50笔/年 → 回填必须带 trades，否则无法筛掉'0笔高PF'的假最优"
                        % (wid.upper(), PHASE, a, b, prod, fixed["InpAllowShort"])),
                "priority": "high",
                "win_id": wid,
                "phase": PHASE,
                "expect_passes": prod,
            })

    # ---- 自检：留白 / 唯一性 ----
    ids = [r["grid_id"] for r in reqs]
    assert len(set(ids)) == len(ids), "grid_id 重复"
    for r in reqs:
        for f_, t_ in ((r["from"], r["to"]),):
            assert dt.datetime.strptime(t_, "%Y.%m.%d").date() < HOLDOUT, \
                "★%s 触及留白: %s" % (r["grid_id"], t_)
        assert r["fixed"]["InpLatencyMs"] == "300", "缺 300ms 延迟"
        assert r["expect_passes"] <= 5000
    print("自检通过: %d 个网格, grid_id 唯一, 全部 InpLatencyMs=300, 无一触及留白段" % len(reqs))

    if dry:
        print("\n[dry] 未写文件。样例:\n" + json.dumps(reqs[0], ensure_ascii=False, indent=2))
        return 0

    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        for r in reqs:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("\n已写入: %s  (%d 行)" % (OUT, len(reqs)))

    print("\n=== 网格清单 ===")
    for r in reqs:
        print("  %-14s %s ~ %s  AllowShort=%-5s  %d passes"
              % (r["grid_id"], r["from"], r["to"], r["fixed"]["InpAllowShort"], r["expect_passes"]))
    print("\n预计总 pass 数 = %d" % sum(r["expect_passes"] for r in reqs))
    tot = sum(r["expect_passes"] for r in reqs)
    print("按实测 ~50 tests/min 估算 ≈ %.1f 分钟" % (tot / 50.0))
    print("（若单 pass 比 1 个月窗口慢 ~3 倍，则约 %.1f 分钟）" % (tot / 50.0 * 3))
    return 0


if __name__ == "__main__":
    sys.exit(main())
