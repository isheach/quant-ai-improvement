# eva027 评分函数 V2：设计 / 参数 / 口径 / 工作流

配套文件：
- `eva027_VolumetricPulseGrid_ScoreV2.mq5`（EA，交易主体零改动，仅重写评分 + 纯读取测量层）
- `eva027_rescore.py`（外部第二层复评脚本）

> 本版并入了对第一版的 10 项口径修正，摘要见文末「本轮修改点」。

---

## 1. 新评分总结构

```
FinalScore = ProfitScore
           − FinalLossPenalty − MaxDDPenalty − EpisodeDDPenalty
           − UnderwaterPenalty − TooFewTradesPenalty − TooManyTradesPenalty
           − TailExitPenalty
```

- ProfitScore = W_profit · log(1 + max(0, CAGR年化) / 目标年化)
- FinalLossPenalty = W_loss · ( LossPct / (1−LossPct) )^P_loss
- MaxDDPenalty = W_maxdd · ( max(0, MaxDD − 免费MaxDD) / (1−MaxDD) )^P_maxdd
- EpisodeDDPenalty = W_episode · Σ ( max(0, 单次DD − 免费Episode) / (1−单次DD) )^P_episode
- UnderwaterPenalty = W_underwater · ( max(0, 水下比 − 免费水下比) )^P_underwater
- TooFew / TooMany = 频次偏离月均区间的非线性惩罚
- TailExitPenalty = W_tail · ( 年化尾损% )^P_tail
  - 年化尾损% = (末单损 + 截止损 + CutWeight·砍单损) / 归一资金 / 年数
  - 三项损失均为**逐事件亏损累计**（事件内部按净额计算，事件净 PnL<0 才计入；不同风险事件之间不抵消）

---

## 2. 收益年化 = CAGR（复利）

\[
\text{CAGR} = \left(\frac{\text{deposit}+\text{net}}{\text{deposit}}\right)^{1/\text{years}} - 1
\]

若 `deposit+net ≤ 0`（爆仓），年化置 −1、不进正收益项，由最终亏损惩罚接管（避免 pow 异常）。比旧的 `收益率/年数` 更真实。

---

## 3. 回测时间跨度（years / months）

- **mq5**：用行情 tick 时间界定跨度 `G_ScoreLastTickTime − G_ScoreFirstTickTime`（首个 OnTick 记起点、每 tick 更新终点），比 `OnInit` 里的 `TimeCurrent()` 在测试器中更稳；不可用时回退旧逻辑。半年数据≈0.5 年、三月≈0.25 年、两年≈2 年。
- **Python**：提供 `--start/--end` 时用**完整回测区间**算 years/months（推荐）；否则回退「首末成交跨度」并**打印告警**——测试区间首尾有空窗时该跨度偏短，会让年化收益、月均交易、水下比、尾损年化全部失真。
- **`--start/--end` 只定义时间分母，不会自动过滤交易行**：它们用于年化、TPM、水下比、尾损年化的评价区间，传入的 `trade_enriched.csv` 必须**本身就已经是**对应该回测区间的数据。（*They define the full backtest evaluation window for annualization, TPM, underwater ratio, and tail-loss annualization; they do NOT filter trade rows automatically.*）

---

## 4. 水下时间的定义（重要）

**水下时间 = 当前账户权益低于「历史最高权益」的持续时间**。不是「账户亏损时间」，也不是「持仓浮亏时间」。

例：账户 2000 → 2300 → 2250。虽然仍盈利（相对本金 +250），但因未回到上一轮峰值 2300，**仍算处于水下**。最长水下时间 = 最久一次「从某个峰值到重新突破该峰值」的间隔。

- mq5 基于**采样 Equity**（含浮动盈亏）→ 更接近真实。
- Python 基于**逐笔平仓余额曲线**（不含浮动盈亏）→ **低估**真实水下，输出中已标注。

---

## 5. 尾部出口 = 逐事件亏损（不跨事件正负抵消）

旧写法先把同一 exit_reason 的净 PnL 相加再取负部，会让某些风险出口的**盈利事件抵消**其它事件的亏损，**低估风险出口依赖**。现改为：

- **mq5**：三个出场点（`last_order_stop` / `cutoff_line_stop` / `trend_close_opposite_grid`）在平仓前算本次事件 `event_pnl`，`G_TailLoss_X += max(0, −event_pnl)`。变量由 `G_TailPnL_*` 更名为 `G_TailLoss_*` 以免误导。
- **Python**：同一 exit_reason 且成交时间相邻（≤ `tail_event_tol` 秒，默认 5s）合并为一个「出场事件」。**同一事件内部先算整组持仓的净浮动 PnL（事件内的盈利成交会抵消亏损成交）**；事件净 PnL<0 才累计其亏损，事件净 PnL≥0 则该事件不产生 TailLoss。**不同风险出口事件之间不允许正负抵消**。输出中附各出口的事件次数。

> 一句话口径：**事件内部可净额计算；事件之间不能正负抵消**。这与 EA 内三出场点"平仓前对整组持仓求一次浮动 PnL、负则累计"的口径一致。

---

## 6. 归一资金（score_capital / 参考资金）

本 EA 固定 0.01 手，评分**强依赖初始资金**：同一笔交易结果换更大 deposit，回撤%与尾损%被稀释、评分虚高。

**ScoreV2 中所有金额型收益与风险——ProfitScore、FinalLossPenalty、MaxDDPenalty、EpisodeDDPenalty、TailExitPenalty——统一使用固定参考资金 `InpScoreReferenceCapital` 归一**（`risk_pct = risk_amount / score_capital`）：

```
score_capital = InpScoreReferenceCapital > 0 ? InpScoreReferenceCapital
                                             : STAT_INITIAL_DEPOSIT
```

- **MaxDD**：用**金额** `STAT_EQUITY_DD`，再 `/ score_capital`；**不再用** `STAT_EQUITY_DDREL_PERCENT`。
- **EpisodeDD**：单次权益峰谷回撤**金额** `/ score_capital`；**不用权益峰值 peak 作分母**。
- **mq5**：`InpScoreReferenceCapital`。>0 时按它归一；否则用 `STAT_INITIAL_DEPOSIT`；`score_capital<=0` 时安全 fallback。请设为**实盘计划分配给本 EA 的真实资金**。

**为什么不用权益峰值**：如果账户权益峰值增加，MT5 默认的相对回撤百分比会变小，但 ScoreV2 **不使用权益峰值作为风险分母**，而使用固定参考资金——这样才能反映本 EA 实际被分配的**风险预算**。

**数值示例**：`InpScoreReferenceCapital = 2000`，某次权益峰谷回撤金额 = 1000，则 ScoreV2 回撤比例 = 1000 / 2000 = **50%**。即使账户权益峰值已涨到 10000，该事件在 ScoreV2 里仍按 **50%** 风险处理，而不是按 1000 / 10000 = 10%。
- **Python**：`--deposit` 必填，输出顶部醒目标注该值。

---

## 7. 评分权重是「裁判规则」，不能进优化

`InpScore*Weight`、`InpScore*Power`、`InpScoreFree*`、`InpScoreMin/MaxTradesPerMonth`、`InpScoreReferenceCapital`、`InpScoreTargetAnnualReturn` 等都是**裁判规则**，代表用户风险偏好，应**固定**，**严禁**在 MT5 里勾选参与参数优化。优化器只优化**交易参数**（网格间距 `InpGridZ/InpMinGridZ/InpUniGridExpCoef`、持仓上限 `InpUniMaxPos`、砍单开关等）。代码注释与参数组标题已加此警示。

Python 的 `--config`/`--w-*` 覆盖**只用于量级校准**，不是用历史数据拟合权重。

---

## 8. Python 的正确用途：量级校准，不是拟合权重

评分权重是**先验风险偏好**，先固定再用。Python 用于检查：ProfitScore、MaxDDPenalty、UnderwaterPenalty、TooManyTradesPenalty、TailExitPenalty 各项量级是否合理——**没有某项完全压倒其它、也没有某个关键风险项几乎不起作用**。

建议流程：① 选定真实 deposit；② 用几套代表性参数跑 Python；③ 观察各扣分项；④ 按实盘直觉调权重；⑤ **固定**权重；⑥ 再用 MT5 优化交易参数；⑦ Top-N 用 Python 在去训练年验证区间复评定参。

---

## 9. 训练 / 验证工作流

1. **不要单年训练**（已证实严重过拟合，见 §11）。至少连续 2 年，或走前向。
2. 优化时 Custom max + `InpUseNewScore=true`；裁判规则全部固定。
3. **优化范围必须真的覆盖「更宽网格 / 更少持仓」**（放开 `InpGridZ/InpMinGridZ/InpUniGridExpCoef/InpUniMaxPos`），否则新评分想选的参数根本不在搜索空间里。
4. OnTester 粗筛 Top-N。
5. Top-N 用 `eva027_rescore.py` 在**去训练年验证区间**复评，按验证分定参。
6. 定参标准：验证区间 CAGR 为正、最大回撤%可接受、水下比低、月均交易在区间内、尾损占比低。
7. A/B：同搜索空间各跑一次 `InpUseNewScore=true/false`，确认新评分确实推开「小网格高频」。

---

## 10. Top-N 精评：调小采样间隔

- 粗筛可保留 `InpScoreEquitySampleMinutes = 60`（每小时一采）。
- **Top-N 精评建议 `= 5` 或 `15`**，否则回撤事件数与最长水下时间会因采样过粗被低估。
- 最大回撤用官方**金额** `STAT_EQUITY_DD`（再 `/ score_capital`），逐 tick 统计、**不受采样影响**；只有回撤事件数/最长水下时间来自采样曲线、受采样间隔影响。

---

## 11. 实测对照（真实 enriched，完整区间 2023-01-01 ~ 2026-07-01，3.50 年）

两套 `.set` 均全周期运行，参数分别由 2023 / 2024 单年训练。

### 11.1 按年拆分（训练年 vs 样本外）——两条铁律

- `grid_tp_baseline_revert`（网格回归）**每年为正**：唯一稳定 edge。
- 尾部出口（末单+截止+砍单）**每年为负**，样本外常吃光网格利润。
- 单年参数训练年漂亮、样本外趋零/转负 = 典型过拟合（旧评分奖励高频、无水下/尾部/过密惩罚的直接后果）。

### 11.2 余额曲线近似（已实现口径，低估真实回撤）

| 参数 | 全程净利 | 近似最大回撤 | 最长水下 | 月均交易 |
|---|---:|---:|---:|---:|
| train2023 | +607 | ≈$526 | ≈**855天**(66.9%) | 85.5 |
| train2024 | +695 | ≈$667 | ≈639天(50.1%) | 71.9 |

### 11.3 eva027-V2 复评（CAGR + 逐事件尾损 + 区间年化）

deposit 未知，给两个假设值展示百分比框架（**务必用真实入金重算**）：

| 参数 | deposit=2000 | deposit=10000 | 主导减项(2k) |
|---|---:|---:|---|
| train2024 | **−22.5** | **−20.5** | 过密−17.9 / 尾损−17.0 / 水下−10.4 |
| train2023 | **−48.3** | **−52.7** | 过密−40.5 / 水下−18.7 / 尾损−18.1 |

- 两套在新评分下都是负分（应当如此），排序稳定 train2024 > train2023。
- 旧评分**没有**的「交易过密」「水下时间」现在是主导减项——正是把优化器从「小网格高频」推开的力。
- deposit 从 2000 → 10000：回撤/尾损%被稀释，最大回撤落入 20% 免费区，评分结构随之改变 → 再次说明 deposit 必须真实。

---

## 12. 诚实边界

- **本次不能给出「新评分选出的参数」**：需在 MT5 用新评分重跑优化器（本环境无 MT5）。已交付机制 + 复评脚本 + 对现有参数的新评分演示。
- **换评分不创造 edge**：样本外净利本就≈0，最大上行在**压低尾部放血**（每年 −850~−2100），这既是评分问题、**更是参数/搜索空间问题**。
- **别删砍单**：现有明细只有已实现盈亏、无「不砍的反事实」，无法证明删了不恶化。故 `CutWeight=0.5` 折算而非判死。
- **口径差异**：Python 用逐笔平仓余额曲线（低估回撤/水下）；OnTester 用采样 Equity（含浮动、更真，但受采样间隔限制）；最大回撤真值以 tester 官方 Equity DD% 为准。

---

## 本轮修改点（10 项）

1. 尾损改**逐事件亏损累计**，盈利事件不抵消；`G_TailPnL_*` → `G_TailLoss_*`（mq5 + Python）。
2. Python 增 `--start/--end`，用完整回测区间算 years/months；缺省回退首末成交跨度并**告警**。
3. mq5 跨度改用 `G_ScoreFirstTickTime/G_ScoreLastTickTime`（tick 时间，更稳），回退旧逻辑。
4. 明确并注释**水下时间定义**（低于历史最高权益的时长），标注 mq5/Python 口径差异。
5. 收益年化改 **CAGR**（复利），含爆仓保护（final_equity≤0 → 走亏损惩罚）。
6. 新增 `InpScoreReferenceCapital` / Python `--deposit` 醒目标注，强调必须等于真实计划资金。
7. 注释与参数组标题标明**评分权重是裁判规则、不得进优化**。
8. Python 支持 `--config JSON` 与 `--w-tail/--w-maxdd/--w-underwater/--max-tpm/--min-tpm/--free-maxdd/--cut-weight` 覆盖。
9. 文档写清 **Python 用途 = 量级校准而非拟合权重** + 建议校准流程。
10. 文档写明 **Top-N 精评调小 `InpScoreEquitySampleMinutes` 到 5/15**；最大回撤用官方 DD% 不受采样影响。

示例命令：
```
python3 eva027_rescore.py --deposit 2000 --start 2023-01-01 --end 2026-07-01 \
    --label train2024 path/to/enrich_eva026_train2024
```

---

## 本轮(第3轮)修改点：金额型风险统一按固定参考资金归一

1. **MaxDD 口径**（mq5 ScoreV2）：由 `STAT_EQUITY_DDREL_PERCENT/100`（相对权益峰值%）改为 `STAT_EQUITY_DD / score_capital`（金额/固定参考资金），含 `[0, 0.999]` 钳制与 `score_capital<=0` 安全 fallback。
2. **EpisodeDD 口径**（mq5 `ScoreEquityCurveStats`）：单次峰谷回撤由 `(peak-trough)/peak` 改为 `(peak-trough)/score_capital`，含钳制；函数签名新增 `double score_capital` 入参（前置声明与调用处同步）。
3. **变量语义统一**：ScoreV2 内 `deposit` 更名为 `score_capital`；ProfitScore / FinalLoss / MaxDD / EpisodeDD / TailExit 全部按 `score_capital` 归一。
4. **尾损逻辑保持不变**：仍是逐事件亏损 `G_TailLoss_x += max(0, -event_pnl)`，未回退到净额抵消。
5. **文档**：明确"所有金额型收益/风险统一按 `InpScoreReferenceCapital` 归一、不用权益峰值"，附权益涨到 10000 仍按 50% 处理的数值示例。
6. **Python 尾损口径表述更正**：改为"事件内部可净额计算（同事件内盈利成交抵消亏损成交）；事件净 PnL<0 才计入；不同风险事件之间不抵消"。
7. **Python `--start/--end` 说明**：明确只定义年化/TPM/水下/尾损年化的时间分母，**不自动过滤交易行**，CSV 须本身就是对应回测区间数据（docstring + `--help` 中英双语）。
8. **交易主体零改动**：开仓/加仓/网格/砍单/趋势单/Vol-Gate/风控出口真实执行逻辑完全未变；本轮只动评分层、统计层与注释。

各项归一分母一览（ScoreV2）：

| 项 | 分子(金额) | 分母 | MT5 相对回撤%？ |
|---|---|---|---|
| ProfitScore | net(CAGR) | score_capital | 否 |
| FinalLossPenalty | −net | score_capital | 否 |
| MaxDDPenalty | STAT_EQUITY_DD | score_capital | **否(已改)** |
| EpisodeDDPenalty | 单次峰谷回撤额 | score_capital | **否(已改)** |
| TailExitPenalty | 逐事件亏损(年化) | score_capital | 否 |
