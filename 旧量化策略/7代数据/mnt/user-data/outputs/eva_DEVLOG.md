# eva 量化策略可审计化 / 数据流水线 —— 开发日志（eva_DEVLOG，本轮代际 = eva010）

> 标的：XAUUSDm（Exness 黄金，point=0.001），平台 Exness / MT5。
> 策略：`VolumetricPulseGrid_StateMachine`，参数集起点 `true01_2`。
> 本版重点：①代际规则更正；②按你确认的方案**实改 EA 源码**（趋势门控离场 + pacing 开关 + 浮亏硬熔断 + 趋势止损放宽）并逐处标注；③讲清 `InpTrendTrail_ATR_Mult`；④配套新 `.set`；⑤下一阶段（回测/寻优/验证）操作规划。

---

## ★ 代际命名规则（更正并记牢）
- **eva 编号 = 「这一轮输出的所有产物」的代数，不是单个程序的版本号。** 每轮整体进位。
- 上一轮全部产物 = eva009；**本轮全部产物 = eva010**：
  - EA 源码 → `eva010_VolumetricPulseGrid_StateMachine.mq5`
  - 参数集 → `eva010_true.set`
  - 流水线本轮未改动，仍是上一轮的 `eva009_data_pipeline.py`（无新输出就不进位）。
- 下一轮（无论改哪个文件）整体进位为 eva011，除非你明确说"不进位"。

## ★ 长期事实
- 有效数据起点 2017-05；训练窗口 2025-01~2026-04；回测 2024-01~2026-06（前/后段样本外）。
- 回测固定手数、不开复利（隔离"策略问题 vs 复利问题"）。
- net_pnl ≈ 价格行程美元 ×1（0.01 手 $1/$1）。

---

## 1. 此前工作摘要（压缩）
- 架构：行情只导一次 → EA 原样输出 trade_events → Python 流水线后处理 → 分析/回测解耦。
- 诊断：**过拟合**（样本外 PF 1.10、利润集中两月占 59%）+ **真实风险=浮亏**（单簇峰值浮亏 $338.9）。
- **机制发现**：源码已有「趋势确认平逆势网格」(`InpCloseOppositeGridOnTrend`)，但趋势状态机太慢，全样本触发 **0 次**。
- followup 定量结论（A）：pacing 砍暴跌**净正确**（继续扛合计更亏、39% 永不回归），但**砍得太粗**（39% 是会快速反弹的噪声坑被误砍）→ 改用趋势门控判据。
- 趋势单诊断：<15 分钟巨亏、>60 分钟胜率 76% → **止损太紧把好单震出**。
- 流水线迭代：v3.1→v3.2→v3.3→eva009（新增 followup）。

---

## 2. 本轮代码改动（changelog）—— EA：eva010_VolumetricPulseGrid_StateMachine.mq5

> 在你上传的 `eva002` 源码基础上修改，所有改动均以 `// eva010` 注释标注。**我无法在此环境编译 MQL5**，请在 MetaEditor 编译确认（已做结构自检：去注释/字符串后括号平衡相对原文件零净变化）。

| # | 改了什么 | 在哪/怎么改 | 为什么 |
|---|---|---|---|
| 1 | **新增开关 `InpEnablePacingPanic`（默认 false）** | 新 input 组「eva010：风控开关」；在 `CheckAddPacingAndMaybePanic` 的 `if(panic)` 内：开关开=维持旧的全平+冷静期；**开关关=只返回 `ADD_PACING_BLOCK`（阻止加仓但不强平）** | A：pacing 砍暴跌虽净正确但太粗；关掉强平，把"砍不砍"交给趋势门控 |
| 2 | **新增 `InpMaxClusterFloatingUSD`（默认 200）+ 浮亏硬熔断** | 新增 `GetStrategyFloatingProfit()`（汇总网格持仓 `POSITION_PROFIT+SWAP`）与 `CheckMaxClusterFloatingStop()`；在 `OnTick` 的截止线止损之后调用：簇浮亏 ≤ −200 即全平+冷静期，出场原因 `max_cluster_floating_stop` | B：现有止损全是"价格线"，没有"按账户美元"的熔断；设到账户 ~40% 仅防极端尾部，日常不靠它（避免你担心的反复砍仓）|
| 3 | **激活趋势门控 + 调快趋势状态机（缩参数）** | 默认值：`InpCloseOppositeGridOnTrend` false→**true**；`InpTrendBreakoutBars` 30→**15**；`InpTrendConfirmBars` 维持 2（.set 里 4→2）| B+C：让「趋势确认→平逆势网格」能及时触发，替代 pacing 的活，且只砍真单边 |
| 4 | **放宽趋势单止损** | 默认值：`InpTrendSL_ATR_Mult` 1.50→**3.00**；`InpTrendTrail_ATR_Mult` 1.20→**2.50** | C：止损太紧把 >60 分钟的好单震出；放宽让趋势单活到趋势展开 |

**新增的出场原因 `max_cluster_floating_stop`**：下次 enrich/followup 会在 `exit_reason` 看到它，用于验证熔断是否在兜底极端尾部。

### 配套参数集：eva010_true.set
从 `true01_2.set` 改出，便于你回测时直接 Load（`.set` 会覆盖源码默认值，所以必须用新 set）：
| 参数 | 旧值 | 新值（当前‖优化范围） |
|---|---|---|
| InpTrendBreakoutBars | 45 | `15 ‖ 5~30 step5, 优化Y` |
| InpTrendConfirmBars | 4 | `2 ‖ 1~4 step1, 优化Y` |
| InpTrendSL_ATR_Mult | 1.8 | `3.0 ‖ 2.0~4.0 step0.25, 优化Y` |
| InpTrendTrail_ATR_Mult | 1.6 | `2.5 ‖ 1.5~3.5 step0.25, 优化Y` |
| InpCloseOppositeGridOnTrend | true | `true（保持）` |
| InpEnablePacingPanic（新）| — | `false（关）` |
| InpMaxClusterFloatingUSD（新）| — | `200 ‖ 50~300 step25` |

### 历代代码记录
| 代际 | 产物 | 改了什么 / 为什么 |
|---|---|---|
| eva008 v3.1–3.3 | data_pipeline | PyCharm 化 / 进度条·ETA·多进程 / 日历月任务·跨月合并 |
| eva009 | data_pipeline | 新增 `followup`（平仓后路径分析），为 A 反事实定量 |
| **eva010** | **EA + .set** | 趋势门控离场 + pacing 开关 + 浮亏硬熔断 + 趋势止损放宽（见上表）|

---

## 3. `InpTrendTrail_ATR_Mult` 详解（你问的）

- **是什么**：趋势单的**移动止损（trailing stop）**距离 = `该倍数 × ATR`。源码 `.set` 里 = 1.6。
- **怎么工作**（看 `ManageTrendTrailing`）：以多单为例，止损被不断上移到 `当前买价 − Trail×ATR`，且**只升不降**——价格涨，止损跟着抬，锁住利润；价格回落超过 `Trail×ATR` 就触发止损出场。
- **和初始止损 `InpTrendSL_ATR_Mult` 的区别**：后者是开仓时一次性设的**保护性止损**（防一开就错）；前者是持仓中**动态跟随**的止损（落袋盈利）。
- **为什么调宽到 2.5**：1.6 ATR 太紧，趋势中正常的回踩（经常 >1.6 ATR）就把单子移损出局，**吃不到大段趋势**。放宽到 2.5 ATR 让趋势单能扛住中途回踩、跟到更远。代价：回吐多一点利润才出场；但对"能活过 60 分钟胜率 76%"的趋势单是划算的。

---

## 4. 下一阶段操作规划（回答你的问题 5）

> 总流程：**编译 → 单次回测自检 → 寻优 → 选稳健参数 → 重导 trade_events → enrich + followup 验证**。

### 步骤 1：编译 + 单次回测自检（不寻优）
- MetaEditor 编译 `eva010_VolumetricPulseGrid_StateMachine.mq5`（确认 0 error）。
- 策略测试器：Load `eva010_true.set`，**先单跑** 2024-01~2026-06，确认：
  - 能正常出单、`exit_reason` 出现 `trend_close_opposite_grid`（说明趋势门控这次真触发了，对比旧版 0 次）；
  - 出现极端行情时能看到 `max_cluster_floating_stop` 兜底；
  - 没有报错/异常爆仓。

### 步骤 2：寻优（要寻优，但**只优 4 个新方向参数**，别全开）
- **只对这几个开优化（.set 里已设 Y）**：`InpTrendBreakoutBars`、`InpTrendConfirmBars`、`InpTrendSL_ATR_Mult`、`InpTrendTrail_ATR_Mult`。其余全部锁定，避免重新过拟合。
- **优化区间 = 训练窗口 2025-01~2026-04**（保持和以前一致，使 2024 与 2026-05+ 仍是样本外）。
- 优化目标：用现有 OnTester 评分即可；但**选参数时不要只看净利**，要同时看下面步骤 3 的样本外表现。

### 步骤 3：选稳健参数（关键，抗过拟合）
- 从优化结果里**别直接选净利最高那行**。挑选规则：
  1. 在训练窗口排名靠前（不必第一）；
  2. **邻域是"高原"**（相邻参数行绩效也不错，不是孤立尖峰）；
  3. 拿这组参数去**样本外**（2024 + 2026-05~06）单跑，PF 仍 ≥ 1、最大浮亏可接受。
- 满足三条的才是"稳"的参数。

### 步骤 4：重导 + 流水线验证（和以前一样）
- 用选定参数跑一次完整回测，导出新的 `eva_trade_events.csv`。
- 跑 `eva009_data_pipeline.py`：
  - `MODE="enrich"` → 看**单簇峰值浮亏是否从 $339 压下来**、`max_cluster_floating_stop` 是否只在极端处触发；
  - `MODE="followup"`（`FOLLOWUP_EXIT_REASONS` 可加上 `trend_close_opposite_grid`）→ 看趋势门控砍的单子，是不是确实砍在"不回归的暴跌"上（对比旧 pacing）。
- 把新的 enrich/followup 结果发我，我对比新旧、定量看改善，再决定要不要二次微调。

### 要不要每轮都导 followup？
- **不必每轮都导**。enrich 是每轮必看（浮亏/问题单画像）；**followup 只在你想验证"某类出场该不该砍/会不会回归"时才导**（比如这次验证 `max_cluster_floating_stop`、`trend_close_opposite_grid` 是否砍得对）。

---

## 5. 待你定 / 下一步
1. 按 §4 步骤 1–2 编译 + 单跑 + 寻优；卡在哪步把日志/报错发我。
2. 寻优出结果后，把优化报告（或前若干名参数）发我，我帮你按"高原 + 样本外"挑稳健组。
3. 需要的话我把 D 的 **Bootstrap 脚本**给你（现有 trade_events 即可跑，看 +4316 是中枢还是右尾运气）。

---

*本日志随版本更新；代际默认进位（除非你说不进位）。代码改动在 §2 追加，写明改了什么、为什么。*
*（以上为基于回测数据的工程与分析，不构成投资建议；改动后务必在测试器充分验证，实盘与回测存在差异。）*
