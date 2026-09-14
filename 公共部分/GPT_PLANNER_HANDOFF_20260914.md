# GPT Planner Handoff · 2026-09-14

> 作用：这是给新的 ChatGPT Planner / Thinker 窗口的项目接续快照。它记录的是当前项目可执行状态、已经冻结的研究裁定、证据链、禁止事项和唯一下一阶段。新的 Planner 必须先重新读取 GitHub 最新 `main`，以仓库真实最新状态为准；本文件是交接索引，不替代各 Source of Truth。

---

## 1. 项目与角色

仓库：`isheach/quant-ai-improvement`

角色：

- **ChatGPT = Planner / Thinker / Independent Reviewer**：负责研究方向、协议设计、独立裁定、下一阶段授权。
- **本地 Codex = Executor**：负责本地检查/修改代码、运行 MT5/Python 测试、生成证据、commit、push；原则上不自行改变研究方向。
- **用户 = 最终决策者**。

项目仅用于历史研究 / 回测，不做真钱交易。

全局基线：

- 初始资金：`500 USD`
- 杠杆：`1:200`
- DD：`<=20%` preferred，`20~40%` high-risk，`>40%` fail
- 已历史测试 8,000+ 组简单规则，没有可交付稳定正 edge。

全局禁止：

- 不读取 / 不使用 `exposed_oos = 2025-06-01 ~ 2026-05-31`
- 不读取 / 不使用 `user_holdout = 2026-06-01 ~ 2026-09-30`
- 不根据 TRAIN 盈利做参数扫描
- 不事后做 long-only / short-only / weekday / month 过滤
- 不构造未预注册的 V2+V3 组合
- 不自建 symbol，不做 CSV 回灌 MT5
- 不覆盖历史旧 EA / 历史证据
- 所有重要协议与修订保留 provenance，不删失败证据

---

## 2. 当前双路线研究规划

正式记录：`公共部分/双路线研究规划与策略库记录_20260914.md`

### Route A：USDJPY + XAUUSD 跨资产信息

当前具体 family：**XAMR30**。

问题：

1. USDJPY M30 均值回归本身是否有 edge？
2. XAUUSD 的同时段方向信息是否能提高 USDJPY 信号质量？

### Route B：策略库 + 市场状态 / 漂移识别 + 动态模型选择

核心不是找一个“永远有效”的 EA，而是：

`market state -> 选择当前适用的 expert -> 允许/禁止交易`

当前策略库按 family 抽象为：

- Grid / Range expert
- Trend expert
- Breakout expert
- Mean-Reversion expert
- Cross-Asset expert（XAMR30）

未来优先研究“切换式组合 / regime controller”，再考虑同时投票/组合，避免自由度爆炸与事后拼曲线。

**当前 Route B 尚未启动实验。先完成 Route A 的严格 XAMR30 测试。**

---

## 3. JSB30 已永久关闭，不得重开调参

Source of Truth：

`公共部分/GPT下一步执行流程_JSB30裁定与实施_20260914.md`

最终关键 commit：

- `54ca679bf58bfde9da22b3c8ff598529897c8a0e`
- cleanup：`6310fd008caf6adf25cd8abda661c668f1f30fd0`

最终策略哈希：

- source `B15D6550A8AFBE101AD661DA0AEB819BC88E946ED760FBFCA5C65CE59D88A267`
- EX5 `7BD34140655427D9B39CCBCA22F4A61A0833F8E176E34A9ADDEFFA86FD02ECF2`

TRAIN：2018-01-01 ~ 2024-05-31。

结果：

- V1：net -377.81，PF 0.84，Equity DD 77.40%，1143 trades
- V2：net -406.81，PF 0.84，DD 82.55%，1293 trades
- V3：net -424.20，PF 0.73，DD 85.16%，1066 trades

全部触发多个 stop conditions，不进 VALID。

状态：`closed / blocked_failed`。

**禁止重调 JSB30。**

---

## 4. XAMR30 冻结策略定义

Source of Truth：

- `公共部分/XAMR30_preregistration_v2_20260914.md`
- `公共部分/XAMR30_preregistration_v2_DATA_ADDENDUM_20260914.md`
- `公共部分/XAMR30_ATR_REFERENCE_CLARIFICATION_20260914.md`

交易：`USDJPYm` M30

信息源：`XAUUSDm` M30，仅辅助，不交易黄金。

信号：

- `EMA48`
- residual = `Close - EMA48`
- `sigma_t` = bar t 之前 48 个 residual 的 sample std，不含当前 residual
- `z = residual / sigma`
- ATR14 = 冻结 EA 的 MT5 `iATR` 实际语义；R2 已独立验证为当前 build 下 `SMA(current 14 True Range)`
- ATR regime：bar t 之前 500 个 ATR，nearest-rank P20/P80，不含当前 ATR
- XAU：exact same M30 open timestamp
- `xau_return = close/open - 1`
- filter ON：`sign(xau_return)==sign(z)` 且 xau_return != 0

Variant：

- V1：z=1.5，XAU direction filter ON
- V2：z=1.5，XAU direction filter OFF（control）
- V3：z=2.0，XAU direction filter ON

**V1/V2/V3 共享同一个 exact-XAU availability mask；V2 只关闭方向确认，不能在 XAU 缺 bar 时额外交易。**

执行 / 风险：

- signal bar 收盘以后，在下一根 M30 的第一个可交易 tick 入场
- SL = 1.0 ATR
- TP = 0.8R
- max hold = 12 个完整 M30 bars
- 1.5% equity risk
- OCP authoritative
- min lot = 0.01
- `InpAllowMinLotOvershoot=false`
- actual SL risk cap = 3%
- 每 UTC day <=1 actual trade
- 无 grid / martingale / add-on / trailing

---

## 5. XAMR30 当前冻结策略身份：N1R3

当前真正准备未来进入经济 TRAIN 的策略版本是 **N1R3**。

正式身份文件：

`公共部分/XAMR30_N1R3_STRATEGY_FREEZE_20260914.md`

哈希：

- source `CA5AD7339FE415CBC3BD2304B94C47E755B2A6292AA5A69FC1E34D5B7E72826C`
- EX5 `F374890F28022FCB88FA55BD34CD5BCE82DFB93A6C4EA549A3ACF34A60F658B2`

N1R3 origin commit：

`a102c385f231446a3f8489fe10f5a49981368fde`

注意：

`deepseek数据保存/执行_XAMR30/N1_ea_XAMR30_frozen_hashes.sha256`

仍是更早的 D63/BEA5 历史版本，只保留 provenance，**不是当前权威 N1R3 身份文件**。

禁止在无 Planner 裁定下生成 N1R4。

---

## 6. XAMR30 Data Qualification 已完全闭合

### Monthly v4 四窗口 regression

commit：

`5a853628ed1ebe3c5f8e57f3d111319c05340c99`

固定窗口：2018-01、2023-01、2023-07、2024-03。

Method A = `iBars + iTime` 全 series 遍历；Method B = narrow `CopyTime`。

四窗口全部：

- parser_valid=1
- probe_valid=1
- finalization=OnTester
- A/B JPY exact timestamp set equal
- A/B XAU exact timestamp set equal
- dup=0
- nonmonotonic=0
- outside=0
- journal JPY count == monthly filtered count
- Gate A/B PASS

### 完整 77 月 Data Freeze

commit：

`f5613d57234307d39459b4258e07c48ae6c1f8d5`

正式文件：

`公共部分/XAMR30_DATA_FREEZE_20260914_R4.md`

范围：2018-01 ~ 2024-05，共 77 月。

结果：

- engineering PASS = 77/77
- engineering INVALID = 0
- Gate A FAIL = 0
- Gate B FAIL = 0
- A/B timestamp mismatch = 0
- journal mismatch = 0
- min common-session alignment = 99.5604%（2018-09）
- min info availability = 90.8491%（2023-01）

Gate 冻结：

- Gate A = `intersection / XAU_existing_M30_bars >= 99%`
- Gate B = `intersection / USDJPY_M30_bars >= 90%`
- dup/nonmonotonic/outside = 0

TRAIN start 机械冻结：

- TRAIN month = `2018-01`
- first common data-layer M30 timestamp = `2018.01.02 06:00`

注意：该 timestamp 只是 first common bar，不等于 first signal / first trade。

VALID 固定：`2024-06-01 ~ 2025-05-31`

禁止：

- exposed_oos：2025-06-01 ~ 2026-05-31
- user_holdout：2026-06-01 ~ 2026-09-30

---

## 7. Signal Double-Calc 已闭合

### R1

commit：

`e2777abba28e6f65f84e74e28b4a69dd8f911703`

R1 使用 Planner 错误指定的 Python Wilder/RMA ATR reference。

结果：

- EMA/residual/sigma/z/XAU 全 90/90
- ATR/P20/P80 0/90
- 诊断发现冻结 MT5 `iATR` 与当前 14 TR arithmetic mean 90/90 一致
- Probe -> N1R3 frozen final-smoke audit = 37/37 PASS

R1 正确保留为：

`FAIL_REFERENCE_SPEC`

不是 strategy failure。

### R2

commit：

`ba6c8e7a6decd7e990b5dd750f3f8e155018b62a`

正式报告：

`公共部分/XAMR30_SIGNAL_DOUBLECALC_20260914_R2.md`

R2 只改 Python verification reference 为冻结 MT5 iATR observed semantics；策略 EA、样本、raw、tolerance、窗口均未改。

固定样本：

- 60 candidate
- 30 control
- total 90
- R1/R2 timestamp identity = 90/90

结果：

连续字段全部 90/90：

- EMA48
- residual
- sigma48
- z
- ATR14
- P20
- P80
- XAU return

离散字段全部 90/90：

- V1 candidate
- V3 candidate
- direction
- ATR regime pass
- XAU filter pass

XAU exact timestamp/OHLC = 90/90。

Probe -> N1R3 audit bridge 继承 37/37 PASS。

unexplained mismatch = 0。

最终：

`SIGNAL_DOUBLECALC_R2 = PASS`

---

## 8. N1R3 smoke 当前状态与最后遗留问题

已有 final smoke：

- WINTER：12 trades
- DSTTR：10 trades
- SUMMER：15 trades
- total = 37

已有 checker 对 entry timing、exact alignment、OCP、spread/SL/TP、daily<=1、audit reconciliation 等均 PASS。

但是当前旧：

`deepseek数据保存/执行_XAMR30/verify_final_smoke.py`

对于 time_exit 仍存在一个证据缺口：

```python
C("time_exit 仅由 12 根规则触发（权威判据）", True, ...)
```

即 checker 仍然“相信 EA 自己说 time_exit”，没有从真实 USDJPY M30 timestamp 独立数出 12 个完整 bars。

这不是已知 EA bug；源码本身的持有逻辑看起来结构正确。当前需要的是**独立 evidence closure**。

特别是曾经争议的 SUMMER 跨周末 trade，旧日历分钟 checker 会把周末闭市算进去造成 false fail；正确做法是使用真实 USDJPY M30 bars：

`full_held_bars = count(bar_open+30m > entry_time and bar_open+30m <= exit_time)`

- time_exit -> exactly 12
- 其他 exit -> <=12

旧 68/69、69/69、75/75-but-labelled-69/69 报告都保留 provenance。

新的 canonical independent checker 应真实报告 75/75（如果仍是 25 checks × 3 windows）。

---

## 9. 当前唯一下一阶段：FINAL_PRETRAIN_GUARD

**截至本交接文件写入前，GitHub main 最新工程 commit 为 `ba6c8e7a6decd7e990b5dd750f3f8e155018b62a`。本交接文件自身会形成一个更新的 docs commit。**

下一阶段尚未执行。

目标只有两个：

### Part A：Independent 12-bar final-smoke closure

新建而不覆盖旧 verifier：

- `deepseek数据保存/执行_XAMR30/verify_final_smoke_independent.py`
- `deepseek数据保存/执行_XAMR30/final_smoke_independent/XAMR30_N1R3_FINAL_SMOKE_INDEPENDENT_REPORT.md`
- `final_smoke_independent.json`
- `hold_bar_counts.csv`

复用 Double-Calc 的真实 MT5 USDJPY M30 raw timestamps。

独立计算 37 笔 smoke trade 的 full held bars；特别列出跨周末 time_exit trade 的 12 个真实 bar timestamps。

PASS：

- 所有 time_exit ==12 real M30 bars
- 所有其他 exits <=12
- 不出现无条件 `True` checker

### Part B：N0 Four-Way 最终冻结

新建：

- `公共部分/XAMR30_static_inputs_final.md`
- `公共部分/XAMR30_planned_runs.jsonl`
- `deepseek数据保存/执行_XAMR30/xamr30_n0_guard.py`
- `deepseek数据保存/执行_XAMR30/N0_final/resolved_INIs/*`
- `XAMR30_N0_guard_report.md`
- `XAMR30_N0_fourway_report.md`
- `XAMR30_N0_fourway.json`

程序解析 `dsh_XAMR30.mq5` 的全部 `input`。

四方：

`source <-> static table <-> resolved INI <-> planned manifest`

必须 exact 一致。

唯一允许随 variant 改的 EA inputs：

- `InpRunTag`
- `InpZThreshold`
- `InpCrossAssetFilter`

V1：1.5 / true
V2：1.5 / false
V3：2.0 / true

所有其余 inputs 等于冻结 source default。

Tester config 冻结：

- Expert = `dshtrend\\dsh_XAMR30`
- Symbol = USDJPYm
- Period = M30
- Model = 2
- Optimization = 0
- Deposit = 500
- Currency = USD
- Leverage = 1:200
- Visual = 0
- source SHA = CA5...
- EX5 SHA = F374...

预先计划 6 个 run，但本阶段**一个都不能执行**：

- XAMR30_V1_TRAIN
- XAMR30_V2_TRAIN
- XAMR30_V3_TRAIN
- XAMR30_V1_VALID（planned_if_train_pass）
- XAMR30_V2_VALID（planned_if_train_pass）
- XAMR30_V3_VALID（planned_if_train_pass）

N0 guard 必须 dry-run，只 parse/hash/compare，不启动 MT5。

Availability-mask static guard 必须确认 exact XAU availability check 在 filter branch 之前，因此 V1/V2/V3 共享 mask。

Forbidden-date overlap 必须为 0。

最终汇总文件：

`公共部分/XAMR30_FINAL_PRETRAIN_GUARD_20260914.md`

只有以下全部 PASS：

- DATA_FREEZE = PASS
- STRATEGY_PROVENANCE = PASS
- SIGNAL_DOUBLECALC_R2 = PASS
- FINAL_SMOKE_INDEPENDENT = PASS
- N0_FOURWAY = PASS

才允许写：

`FINAL_PRETRAIN_GUARD = PASS`

**即使 PASS，也必须停止，不能自行开始经济 TRAIN。**

---

## 10. 下一阶段之后才可能授权的第一次经济测试

只有 Planner 再次复核 FINAL_PRETRAIN_GUARD 后，才可能授权：

`V1 TRAIN -> V2 TRAIN -> V3 TRAIN`

同一冻结 source/EX5、同一 TRAIN 数据、同一 availability mask，只有预注册 variant 差异。

TRAIN 每 variant 要输出至少：

- net profit / return
- PF
- official Equity DD
- trades/year / span
- win rate / avg win / avg loss / payoff
- expectancy USD / R
- long / short
- yearly / monthly P&L
- holding bars
- spread/SL、spread/TP
- swap / commission
- min-lot / risk-cap / ATR / XAU rejects
- 1x / 1.5x / 2x costs
- top5/top10 winner concentration
- remove top10 winners
- worst5/worst10 losers
- remove worst10 losers
- OCP / audit reconciliation

硬 gate 失败的 variant 不进 VALID。

V1 vs V2 attribution：

- daily return 对齐
- delta = V1 - V2
- 20 trading-day moving-block bootstrap
- 10,000 resamples
- seed = 20260914
- effect supported iff mean delta>0 且 95% CI lower>0

VALID 固定 2024-06-01 ~ 2025-05-31，不 retune。

---

## 11. 如果 XAMR30 最终无 VALID 候选

先做最后一个 bounded diagnostic：JSB30 V1/V3 capital/min-lot sensitivity，deposit = 500/1000/2000/5000，仅 TRAIN，不重调策略。

如果高资本仍无稳定 edge：

停止继续发明简单规则 MT5 family；转入 Route B / statistical-ML research plan：

- regime detection
- concept drift
- market-state similarity
- performance drift
- strategy library expert selection
- possibly Mixture-of-Experts / gated ensemble

不要继续无限滚动窗口/参数搜索。

---

## 12. 新 Planner 接手时的操作纪律

新的 ChatGPT 窗口不要直接相信本文件中的 HEAD 是最新。

首先：

1. 连接 GitHub `isheach/quant-ai-improvement`
2. `main` 查看最新 commit history
3. 阅读仓库 `README.md`
4. 阅读本文件
5. 阅读当前阶段对应 Source of Truth：
   - `公共部分/双路线研究规划与策略库记录_20260914.md`
   - `公共部分/XAMR30_preregistration_v2_20260914.md`
   - `公共部分/XAMR30_preregistration_v2_DATA_ADDENDUM_20260914.md`
   - `公共部分/XAMR30_DATA_FREEZE_20260914_R4.md`
   - `公共部分/XAMR30_N1R3_STRATEGY_FREEZE_20260914.md`
   - `公共部分/XAMR30_ATR_REFERENCE_CLARIFICATION_20260914.md`
   - `公共部分/XAMR30_SIGNAL_DOUBLECALC_20260914_R2.md`
6. 检查是否已经有 Executor 在本文件之后提交了 `FINAL_PRETRAIN_GUARD` 结果。

若没有：唯一下一阶段就是第 9 节的 `FINAL_PRETRAIN_GUARD`。

若已经有：独立复核该 commit 和机器证据，再决定是否授权经济 TRAIN。

任何时候发现仓库真实状态与本文件冲突，**以仓库更新后的真实证据为准，不要根据旧对话猜。**
