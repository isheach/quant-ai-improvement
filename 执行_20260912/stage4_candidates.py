#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
P4 结果汇总 + 匹配本金核算（框架 §6/§9）

把 500 USD 主口径下的三个预注册变体结果与"匹配本金准则"对照，
回答一个具体问题：为什么 500 USD 下 valid 为正，而 1000 USD 下为负？
"""
from __future__ import annotations

import csv
import io
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "stage4_candidates")
os.makedirs(OUT, exist_ok=True)

# P4 三个变体（本批实跑，500 USD / Model=2 / ticks=0）
ROWS = [
    # variant, phase, net, pf, trades, dd_pct, ann, ret_dd
    ("C1_H1_2side", "train", 2647.10, 1.56, 546, 22.68, 83.59, 6.73),
    ("C1_H1_2side", "valid",   67.19, 1.11,  95, 26.26, 13.44, 0.39),
    ("C2_M30_2side","train",  873.75, 1.08,1019, 61.57, 27.59, 0.68),
    ("C2_M30_2side","valid", -164.08, 0.80, 167, 35.98,-32.82,-0.91),
    ("C3_H1_long",  "train", 1964.60, 1.71, 323, 25.53, 62.04, 5.25),
    ("C3_H1_long",  "valid",  -37.32, 0.88,  55, 21.87, -7.46,-0.32),
]

# 匹配本金核算（框架 §6 / 比特币线"波动尺度匹配准则"）
# 匹配本金 ≈ (0.01 手在止损处的风险) ÷ 1.5%
# 0.01 手在止损处的风险 = 0.01 * contract * SL_ATR * ATR
CONTRACT_BTC = 1.0
SL_ATR = 1.5
ATRS = {"2018 (低价期)": 40, "2022": 300, "2024": 545, "2025-26": 430}


def matching_deposit(atr, risk_pct=1.5, vol=0.01):
    risk = vol * CONTRACT_BTC * SL_ATR * atr
    return risk / (risk_pct / 100.0), risk


L = []
L.append("# Stage 4 · 候选结果与匹配本金核算\n")
L.append("口径：**500 USD** / Model=2 / `InpLatencyTicks=0` / BTCUSDm / 新审计 EA"
         "（源码 `00113738…`、EX5 `5BB03BF9…` → 后经 §1A 增补后为新哈希）\n")

L.append("## 1. 三个预注册变体结果\n")
L.append("| 变体 | 段 | net | PF | 笔数 | DD% | 年化% | 收益/回撤 | 三段门槛 |")
L.append("|---|---|---:|---:|---:|---:|---:|---:|---|")
gate = {}
for v, ph, net, pf, n, dd, ann, rd in ROWS:
    gg = []
    gg.append("净利✅" if net > 0 else "净利❌")
    gg.append("DD✅" if dd <= 40 else "DD❌")
    gate.setdefault(v, []).extend([net > 0, dd <= 40])
    L.append("| %s | %s | %+.2f | %.2f | %d | %.2f | %+.2f | %+.2f | %s |"
             % (v, ph, net, pf, n, dd, ann, rd, " ".join(gg)))
L.append("")

L.append("## 2. 逐条门槛校验（★纪律 10：必须逐条列出并逐条校验）\n")
L.append("| 变体 | ①三段为正 | ②DD≤40% | ③覆盖≥90% | ④50≤频率≤2000 | ⑤持仓≥5min | ⑥点差/止损≤30% | ⑦笔数合计≥500 | 结果 |")
L.append("|---|---|---|---|---|---|---|---|---|")
for v in ("C1_H1_2side", "C2_M30_2side", "C3_H1_long"):
    # train/valid 只有两段（test 按框架 §6 冻结后只跑一次，本轮未跑）
    two_ok = all(gate[v])
    L.append("| %s | %s | %s | 未测 | 未测 | 未测 | 未测 | 未测 | **%s** |"
             % (v,
                "✅" if gate[v][0] else "❌",
                "✅" if gate[v][1] else "❌",
                "lead_only" if two_ok else "**淘汰**"))
L.append("")
L.append("**★说明**：本轮只跑了 train/valid 两段（按框架 §6，测试集须在冻结后只跑一次）。")
L.append("因此上表③–⑦为「未测」，**不构成通过**，只是尚未触发停止条件。")
L.append("")

L.append("## 3. 匹配本金核算（回答：为什么 500 正、1000 负）\n")
L.append("准则：`匹配本金 ≈ (0.01 手在止损处的风险) ÷ 1.5%`，BTC `contract=1`、`SL_ATR=1.5`\n")
L.append("| 时期 | ATR | 0.01 手止损风险 | **匹配本金** | 500 USD 相对位置 |")
L.append("|---|---:|---:|---:|---|")
for k, atr in ATRS.items():
    md, risk = matching_deposit(atr)
    if md < 400:
        pos = "500 远大于匹配 → 手数远超地板（比例配仓）"
    elif md < 600:
        pos = "**500 ≈ 匹配点 → 手数恰好在地板附近（临界）**"
    else:
        pos = "500 小于匹配 → 手数贴 0.01 地板（地板畸变区）"
    L.append("| %s | %d | $%.2f | **$%.0f** | %s |" % (k, atr, risk, md, pos))
L.append("")

md_now, risk_now = matching_deposit(430)
L.append("**★当前 ATR≈430 → 匹配本金 ≈ $%.0f。**" % md_now)
L.append("")
L.append("### 这解释了三个观测的反常关系\n")
L.append("```")
L.append("入金 300  (valid) → + 85.75   手数贴 0.01 地板（地板畸变区，仓位被压低）")
L.append("入金 500  (valid) → + 67.19   ← ★本批：手数 ≈ 地板临界（理想手数 0.0116）")
L.append("入金 1000 (valid) → − 25.99   手数 0.0233，完全脱离地板（比例配仓）")
L.append("```")
L.append("**→ 三个入金点的 valid 结果不是单调的：**")
L.append("- 300：地板把仓位压到 2.15%/笔（**比目标 1.5% 更大**，但方向随机）→ 恰好为正")
L.append("- 500：理想手数 0.0116，**恰好在地板之上一点** → 仍为正（+67.19）")
L.append("- 1000：理想手数 0.0233，**仓位按 1.5% 规则展开** → 暴露为负")
L.append("")
L.append("**★关键推断（可检验）**：")
L.append("> 500 USD 落在 **匹配本金附近（$%.0f）**，处于「地板畸变」与「比例配仓」的**过渡带**。"
         % md_now)
L.append("> 因此它的 valid 结果**既不像 300 那样完全被地板压住，也不像 1000 那样完全展开** —— ")
L.append("> **它落在一个不稳定的中间态。把过渡带当作可交付口径是危险的。**")
L.append("")
L.append("**★检验方法（下一批应做）**：")
L.append("```")
L.append("入金 400 / 450 / 550 / 600 / 700（都乘以同一 ATR 段）")
L.append("→ 若 valid 随入金单调恶化 ⇒ 确认「地板畸变越弱、暴露越彻底」")
L.append("→ 若存在正区间 ⇒ 需要找出该区间的上界，并说明它为何存在")
L.append("```")
L.append("")

L.append("## 4. 结论与停止条件\n")
L.append("**触发框架 §9**：")
L.append("- **C2（M30）**：valid `net = −164.08` **为负** → 淘汰")
L.append("- **C3（单边）**：valid `net = −37.32` **为负** → 淘汰")
L.append("- **C1（现结构）**：valid `+67.19` 为正、DD 26.26% ≤ 40% → **两段通过**")
L.append("")
L.append("**→ 按协议「验证失败后不得继续无边界扫参数」：C2/C3 停止，不再调参。**")
L.append("**→ C1 未触发停止条件，但仅两段通过，③–⑦未测 → 状态 `lead_only`，不得进入 P5。**")
L.append("")

with io.open(os.path.join(OUT, "p4_candidates.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(L))
with io.open(os.path.join(OUT, "p4_candidates.csv"), "w", encoding="utf-8-sig",
             newline="") as f:
    w = csv.writer(f)
    w.writerow(["variant", "phase", "net", "pf", "trades", "dd_pct", "ann_pct", "ret_dd"])
    for r in ROWS:
        w.writerow(r)
print("\n".join(L))

