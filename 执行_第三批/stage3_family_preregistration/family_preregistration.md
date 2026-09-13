# 新 family 预注册 · `MR30`（Mean-Reversion, M30）

- 预注册者：DeepSeek-执行者
- 时间：2026-09-13（Asia/Shanghai）
- 依据：GPT 第三批裁定 §4 Step 5
- **状态：`closed / blocked_failed` —— 三个 TRAIN 变体均已按预注册停止条件关闭；VALID 未运行。**

---

## 0. 设计动机（直接来自 C1 的失败模式）

```
C1 的失败不是因为参数没调好，而是【收益结构】：
  train: 净利 +3280.42 → 去前 10 大单后 −354.74（前10大单占 110.8%）
  valid: 净利  +187.48 → 去前 10 大单后 −247.67（前10大单占 232.1%）
→ 盈利由极少数大趋势尾单承担，与黄金线是同一结构问题

★ 因此新 family 的核心检验目标是：
   「edge 是否【不依赖尾单】」—— 而不是「能否做到更高年化」
```

**→ 具体手段：使用【有上限的收益/时间退出】，从结构上禁止"靠一单跑很远"。**

---

## 1. 与 C1 的结构差异（这是"新 family"的判定依据）

| 维度 | C1（已 `blocked_failed`） | **MR30（本次预注册）** |
|---|---|---|
| 信号方向 | **顺势**（唐奇安突破） | **逆势**（偏离均值回归） |
| 收益上限 | **无上限**（靠趋势跑） | **★固定止盈 = k×ATR** |
| 止损 | Chandelier 移动止损 | **固定 ATR 止损**（不移动） |
| 退出 | 移动止损 / 趋势反转 | **固定 TP / 固定 SL / 时间退出** |
| 周期 | H1 信号 + D1 EMA200 过滤 | **M30 单周期**（无 D1 过滤） |
| 入场条件 | 突破 + 质量闸门 | **偏离 ≥ n×σ 后回归** |
| 持仓上限 | 无 | **最多 24 根 M30** |
| 禁止项 | — | **无马丁、无网格、无无上限移动赢家** |

**→ 与 C1 无共享参数轴**（不扫描 C1 的 EMA/唐奇安参数邻域）。

---

## 2. 固定口径（三个变体共享，不可变）

| 项 | 值 |
|---|---|
| 品种 | **`BTCUSDm`**（真实券商品种） |
| 本金 / 币种 | **500 USD / USD** |
| 杠杆 | 1:200（hedging，实测 `margin_mode=2`） |
| 模型 | **`Model=2`** |
| 延迟标签 | `InpLatencyTicks=0`（基线）；**不写成 300ms** |
| 数据来源 | MT5 服务器历史，**禁止自建品种 / CSV 回灌** |
| 训练段 | 2018-02-09 ~ 2024-05-31 |
| 验证段 | 2024-06-01 ~ 2025-05-31 |
| **不跑的段** | 2025-06-01~2026-05-31（`exposed_oos`）· 2026-06-01~09-30（`user_holdout`，硬禁止） |
| 最小手规则 | `InpAllowMinLotOvershoot=false`（交付口径）；固定手仅作独立对照 |
| 风险 | `InpRiskPct=1.5`，`InpMinLotMaxRiskPct=3.0` |
| 成本口径 | 点差按 MT5 快照；另做 1.0×/1.5×/2.0× 成本压力 |
| 审计 | 必须含 `deal_ticket/position_id/entry_time/exit_time/entry/exit/volume/profit/swap/commission/net/close_type/exit_reason/signals` |

---

## 3. 三个固定变体（★运行后不得增删）

| 变体 tag | 唯一差异 | 其余全部相同 |
|---|---|---|
| `MR30_V1` | **固定 TP = 1.5×ATR**，时间退出 24 根 | ✅ |
| `MR30_V2` | **固定 TP = 2.5×ATR**，时间退出 24 根 | ✅ |
| `MR30_V3` | **固定 TP = 1.5×ATR** + **波动状态过滤**（ATR 分位在 [P20, P80] 内才入场） | ✅ |

**★三个变体只改变预先写明的【收益上限】与【波动状态过滤】，不扫描入场阈值/周期/止损倍数。**

### 3.1 完整参数（全部预先固定）

```
# 信号（均值回归）
InpEntrySigma      = 2.0      # 收盘偏离 ≥ 2.0σ 触发
InpSigmaPeriod     = 48       # M30 的 48 根 = 24 小时
InpMAPeriod        = 48       # M30 的 48 根 = 24 小时
InpNeedReenter     = true     # 需回归带内确认

# 出场（★这是新 family 的核心差异）
InpTP_ATR          = 1.5 / 2.5  # 变体差异项：固定止盈
InpSL_ATR          = 2.0        # 固定止损（不移动）
InpMaxBarsInTrade  = 24         # 时间退出（24 × M30 = 12 小时）

# 波动状态过滤（仅 V3）
InpUseVolRegime    = false / true
InpVolPctLow       = 20
InpVolPctHigh      = 80
InpVolLookback     = 500        # M30 的 500 根

# 风险与账户
InpRiskPct         = 1.5
InpMinLotMaxRiskPct= 3.0
InpAllowMinLotOvershoot = false

# 禁止项（写死，不可调）
InpUseMartingale   = false
InpUseGrid         = false
InpUseTrailingWin  = false      # ★禁止无上限移动赢家
```

---

## 4. 预期失败机制（先写清，避免事后解释）

```
若 MR30 在 train 或 valid 上出现以下任一条，则【预先认定】为：
① 净利 ≤ 0 或 PF ≤ 1        → 均值回归在 BTC M30 上无 edge
② 官方 Equity DD Relative > 40% → 逆势结构在趋势市中被连续打爆（预期的主要失败模式）
③ 2× 成本后转负              → M30 频率下点差占比过高
④ 去前 10 大单后转负          → ★即使换了结构，尾单依赖仍存在（若发生，说明
                                尾单依赖是【品种/频率】的属性，不是结构属性）
⑤ 只在孤立参数点有效          → 3 个变体是预注册的，不存在此问题；若出现说明实现有 bug
⑥ 依赖最小手超配              → 500 USD 下 0.01 手地板仍主导（与 BTC 的 ATR 尺度有关）
```

**★第 ④ 条是本 family 最关键的观测**：
> **若 MR30（无上限收益结构）仍然"去前 10 大单后转负"，
> 则说明尾单依赖不是 C1 的结构缺陷，而是 BTCUSDm 在 500 USD 账户上的固有属性 —— 
> 那将把结论从"换个策略就能解决"升级为"该品种/资金规模下不可交付"。**

---

## 5. 停止条件（与裁定 §4 Step 6 一致）

任一段出现以下情况立即关闭该变体：
```
· 净利 ≤ 0 或 PF ≤ 1
· 官方权益 DD > 40%
· 2× 成本后转负
· 去前 10 大单后转负
· 审计 / 报告 / OrderCalcProfit 不一致
· 交易主要由最小手超配、拒单副作用或单一极端交易造成
· 结果只在一个孤立参数点有效，或验证样本不足
```

**DD 分级（仅描述，不改变关闭条件）**：≤20% 首选 · 20%~40% 高风险可接受 · >40% 失败。
**年收益 50% 是研究目标、100% 是延伸目标 —— 不得通过提高单笔风险硬凑。**

---

## 6. 需要交付的字段（每个变体）

```
· 真实 symbol / From / To / dataset_role / deposit / currency / Model / ticks
· spread / slippage 口径
· 完整 inputs
· 源码 / EX5 / 报告 / 审计 的 SHA-256
· run_verification（execution_verified / invalid）
· strategy_stage（exploratory / deliverable_candidate / acceptable_candidate / blocked_failed）
· R3 十项诊断（覆盖率 / 频率 / 持仓时长 / 点差占比 / R 七件套 / 集中度 /
              成本压力 / 信号与拒单 / 官方 DD / 逐年频率）
```

---

## 7. 留位（待实现后填写）

| 项 | 值 |
|---|---|
| EA 源码路径 | `执行_第三批\stage3_family_preregistration\dsh_MR30.mq5` |
| EA 源码 SHA-256 | `3B1331CCB208D2D57D97C1FD0C327F5F3153310C13B519E6817B6877C7ADC09E` |
| EX5 SHA-256 | `D5CCD721B968102A6C4FF2F06A21A81A7178AC53D20BC22567A1D240CE4FE112` |
| manifest tag | `DS260913_MR30_{V1,V2,V3}_{TRAIN,VALID}` |
| planned manifest | `gpt数据保存\审计\第三批_MR30\mr30_planned_manifest.jsonl` |
| 静态闸门 | `gpt数据保存\审计\第三批_MR30\mr30_static_gate.py` → 通过；编译 0 errors / 0 warnings |
| 首次运行时间 | `2026-09-13 14:13（有效 V1 TRAIN）` |

## 8. 运行后裁定

三个 TRAIN 均完成执行/审计对账，但均触发停止条件：V1 净利 -392.47、PF 0.83、官方权益 DD 78.86%；V2 -394.71、0.83、79.80%；V3 -319.21、0.87、65.72%。因此 `V1/V2/V3` 均为 `blocked_failed/closed`，对应 VALID 均为 `not_run_skipped`。完整汇总见 `gpt数据保存\审计\第三批_MR30\MR30_family_final_report_20260913.md`。

**★本文件为预注册，未经批准不运行。**
