# eva027 评分函数 V2：设计说明 / 参数 / 工作流 / 对照

配套文件：
- `eva027_VolumetricPulseGrid_ScoreV2.mq5`（EA，交易主体零改动，仅重写评分 + 加测量层）
- `eva027_rescore.py`（外部第二层复评脚本）

---

## 0. 一句话

把评价函数从"鼓励多交易、按绝对金额算收益/回撤"改成：**收益按年化取 log 平滑；风险全部用百分比；回撤 20% 以内不惩罚，超过后连续、非线性、越接近爆仓越陡；交易频次只做月均区间约束；风险出口（末单/截止/砍单）按出场原因惩罚，砍单按 0.5 折算而非直接判死。**

---

## 1. 新评分总结构

```
FinalScore = ProfitScore
           − FinalLossPenalty − MaxDDPenalty − EpisodeDDPenalty
           − UnderwaterPenalty − TooFewTradesPenalty − TooManyTradesPenalty
           − TailExitPenalty
```

各项（全部百分比 / 免费区间 / 连续非线性）：

- ProfitScore = W_profit · log(1 + max(0, 年化收益) / 目标年化)
- FinalLossPenalty = W_loss · ( LossPct / (1−LossPct) )^P_loss
- MaxDDPenalty = W_maxdd · ( max(0, MaxDD − 免费MaxDD) / (1−MaxDD) )^P_maxdd
- EpisodeDDPenalty = W_episode · Σ ( max(0, 单次DD − 免费Episode) / (1−单次DD) )^P_episode
- UnderwaterPenalty = W_underwater · ( max(0, 水下比 − 免费水下比) )^P_underwater
- TooFew = W_lowfreq · ( max(0, MinTPM/TPM − 1) )^P_freq
- TooMany = W_highfreq · ( max(0, TPM/MaxTPM − 1) )^P_freq
- TailExitPenalty = W_tail · ( 年化尾损% )^P_tail
  - 年化尾损% = (末单损 + 截止损 + CutWeight·砍单损) / 初始资金 / 年数

**对原始需求的一处修正**：原始 `TailLossPct = 尾损/初始资金` 是"全程累计量"，回测越长越虚高，与已年化的收益项口径不一致。故尾损项 **÷年数** 年化。最大回撤/回撤事件是"最大/单次"量，不需年化，保持原样。

---

## 2. 各指标在哪一层计算（可靠性说明）

| 指标 | OnTester 内能否可靠取得 | 口径 |
|---|---|---|
| 净利 / 年化收益 | ✅ | STAT_PROFIT / STAT_INITIAL_DEPOSIT |
| 最终亏损% | ✅ | −净利/初始资金 |
| 最大回撤% | ✅ **最准** | STAT_EQUITY_DDREL_PERCENT（官方逐 tick、峰值相对） |
| 回撤事件数/深度 | ⚠️ 近似 | 由 OnTick **按间隔采样的净值曲线**重建（MT5 无官方统计） |
| 最长水下时间 | ⚠️ 近似 | 同上（采样间隔内更深瞬时回撤会漏采） |
| 月均交易数 | ✅ | STAT_TRADES / 月数 |
| 尾损（按 exit_reason 拆分） | ✅ | 三个出场点**平仓前累计浮动 PnL**（不依赖审计，优化时也生效） |

**关键工程点**：EA 的审计日志在优化时被强制关闭，所以 `exit_reason` 落盘拆分在优化时不可用。为此新增了**独立测量层**（`ScoreSampleEquity` + 三出场点 `ScoreSumFloatingPnL` 累计），纯读取、不改任何交易行为、优化时同样运行。

**采样精度**：默认 `InpScoreEquitySampleMinutes=60`（每小时一采）。回撤事件/水下时间因此有间隔粒度的近似误差；需更精细就调小该值（内存/速度代价），或用外部第二层复评。

---

## 3. 新增 input 参数（第一版起点，非最终值）

```
InpUseNewScore              = true    // false=退回v0.95旧评分(A/B对照)
InpScoreTargetAnnualReturn  = 0.20
InpScoreMinTotalTrades2     = 30

InpScoreFreeMaxDDPct        = 0.20    // ★20%以内回撤不惩罚
InpScoreFreeEpisodeDDPct    = 0.10
InpScoreFreeUnderwaterRatio = 0.15

InpScoreMinTradesPerMonth   = 8
InpScoreMaxTradesPerMonth   = 45

InpScoreProfitWeight        = 100
InpScoreLossWeight          = 100
InpScoreMaxDDWeight         = 150
InpScoreEpisodeDDWeight     = 30
InpScoreUnderwaterWeight    = 50
InpScoreLowFreqWeight       = 20
InpScoreHighFreqWeight      = 50
InpScoreTailExitWeight      = 50

InpScoreLossPower           = 2.0
InpScoreMaxDDPower          = 2.0    // 1.5温和 / 2.5~3.0深回撤迅速淘汰
InpScoreEpisodeDDPower      = 1.5
InpScoreUnderwaterPower     = 1.5
InpScoreFreqPower           = 2.0
InpScoreTailPower           = 1.5

InpScoreCutLossWeight       = 0.5    // 砍单尾损折算(保险,非纯坏)
InpScoreEquitySampleMinutes = 60
InpScoreEquitySampleCap     = 200000
```

调参直觉：想让深回撤更快被淘汰 → 提高 `InpScoreMaxDDPower` 到 2.5~3.0；想更依赖网格回归、更嫌恶尾部 → 提高 `InpScoreTailExitWeight`。

---

## 4. 推荐训练 / 验证流程

1. **不要单年训练**。已证实单年参数严重过拟合（见 §5）。至少用连续 2 年训练，或走前向（walk-forward）。
2. 优化时 **Custom max** + `InpUseNewScore=true`。让 `InpEnableTradeAudit=false`（优化自动关）。
3. **优化范围要真的覆盖"更宽网格/更少持仓"**：`InpGridZ`、`InpMinGridZ`、`InpUniGridExpCoef`、`InpUniMaxPos` 都要放开——否则新评分想选的"宽网格低频"参数根本不在搜索空间里。
4. 第一层（OnTester）粗筛出 Top-N（如 20~50 组）。
5. **第二层复评**：对 Top-N 用 `eva027_rescore.py` 在**去掉训练年的验证区间**上复算评分，按验证分排序定参。
6. 定参标准不是净利最高，而是：验证区间年化为正、最大回撤%可接受、水下比低、月均交易在区间内、尾损占比低。
7. A/B：同一搜索空间各跑一次 `InpUseNewScore=true/false`，对比两者选出的参数，验证新评分确实推开了"小网格高频"。

---

## 5. 实测对照（用你上传的真实 enriched 明细）

两套 `.set` 均为 **2023-01→2026-07 全周期**运行，参数分别由 2023 / 2024 单年训练。

### 5.1 按年拆分（训练年 vs 样本外验证）

| 参数 | 年 | 净利 | 网格回归 | 尾部合计 | 备注 |
|---|---|---:|---:|---:|---|
| train2023 | 2023 | +778 | +1645 | −1042 | 训练年 |
| train2023 | 2024 | −181 | +1429 | −1764 | 样本外 |
| train2023 | 2025 | −19 | +592 | −853 | 样本外 |
| train2023 | 2026 | +28 | +583 | −892 | 样本外 |
| train2024 | 2023 | −622 | +885 | −1312 | 样本外 |
| train2024 | 2024 | +758 | +1480 | −860 | 训练年 |
| train2024 | 2025 | +116 | +1034 | −941 | 样本外 |
| train2024 | 2026 | +444 | +2265 | −2103 | 样本外 |

**铁一样的两个事实（两套参数、每一年都成立）**：
- **网格回归 `grid_tp_baseline_revert` 每年为正** —— 唯一稳定 edge。
- **尾部出口（砍单+末单+截止）每年为负** —— 持续放血，样本外常把网格利润吃光。
- 单年训练参数在训练年很漂亮、样本外趋近于零甚至为负 = 典型过拟合，正是旧评分（奖励高频、无水下/尾部惩罚）的产物。

### 5.2 余额曲线近似风险（已实现口径，低估真实回撤）

| 参数 | 全程净利 | 近似最大回撤($) | 最长水下 | 月均交易 |
|---|---:|---:|---:|---:|
| train2023 | +607 | ≈526（≈净利87%） | ≈**855天**(66.7%) | 85.2 |
| train2024 | +695 | ≈667（≈净利96%） | ≈**639天**(49.9%) | 71.6 |

### 5.3 新评分 eva027-V2 复评（年化尾损后）

初始资金未知，故给两个假设值展示百分比框架（**务必用真实入金重算**）：

| 参数 | 入金2000 SCORE | 入金10000 SCORE | 主导惩罚 |
|---|---:|---:|---|
| train2024 | −18.6 | −19.9 | 过密 −17.5 / 水下 −10.3 / 年化尾损 −16.9(2k) |
| train2023 | −44.7 | −51.7 | 过密 −39.9 / 水下 −18.6 / 年化尾损 −17.9(2k) |

- 两套参数在新评分下**都是负分**（应当如此），排序稳定 train2024 > train2023。
- 旧评分**没有**的两项——**交易过密**与**水下时间**——现在是主导减项，正是把优化器从"小网格高频"推开的力。

---

## 6. 诚实的边界

- **本次不能给出"新评分选出的参数"**：那需要在 MT5 里用新评分重跑优化器（本环境无 MT5）。已提供机制（新 OnTester）+ 复评脚本 + 对现有参数的新评分演示，供你在 MT5 里落地。
- **换评分不会凭空造出 edge**：样本外净利本就趋近于零，真正的上行空间在**压低尾部放血**（每年 −850~−2100），这既是评分问题也是**参数/搜索空间**问题（宽网格、少持仓、砍单门控）。评分只是让优化器**有可能**选到它们，前提是你把这些参数放进优化范围。
- **不要删砍单**：现有明细只有已实现盈亏，没有"不砍的反事实"，无法证明删砍单后尾部风险不恶化。故新评分对砍单用 `CutWeight=0.5` 折算，而非判死。
- **入金假设强烈影响百分比**：入金 2000 时回撤/尾损占比很高、10000 时最大回撤落入 20% 免费区。定参前必须用真实 `STAT_INITIAL_DEPOSIT`。
