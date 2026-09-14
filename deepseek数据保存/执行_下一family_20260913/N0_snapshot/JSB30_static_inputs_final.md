# `JSB30` 静态输入表（Final · N0）

- 生成者：DeepSeek-执行者
- 生成时间：2026-09-14（Asia/Shanghai）
- 依据：`公共部分/GPT下一步执行流程_JSB30裁定与实施_20260914.md`
- 前身：`JSB30_static_inputs.md`（草案，已被本文件取代）
- **用途：在编译/运行之前把 tag、symbol、日期、deposit、Model、输入名逐项固定；未知 input 必须 fail-close。**

---

## 1. 三个 TRAIN + 三个 VALID 的 tag 与口径

| 变体 | TRAIN tag | VALID tag | 品种 | TRAIN 日期 | VALID 日期 | deposit | Model | ticks |
|---|---|---|---|---|---|---|---|---|
| **V1** | `DS260914_JSB30_V1_TRAIN` | `DS260914_JSB30_V1_VALID` | `USDJPYm` | 2014.01.14 ~ 2024.05.31 | 2024.06.01 ~ 2025.05.31 | 500 | 2 | 0 |
| **V2** | `DS260914_JSB30_V2_TRAIN` | `DS260914_JSB30_V2_VALID` | `USDJPYm` | 同上 | 同上 | 500 | 2 | 0 |
| **V3** | `DS260914_JSB30_V3_TRAIN` | `DS260914_JSB30_V3_VALID` | `USDJPYm` | 同上 | 同上 | 500 | 2 | 0 |

**★VALID 只登记为 `planned_if_train_pass`，N2 前不得运行（GPT §3）。**
**★三个 TRAIN 使用同一 EX5，仅预注册输入不同（GPT §4）。**

**★TRAIN 起点说明**：`USDJPYm` 真实可用首 bar = **2014.01.14**
（依据：`run_trend/runexp.py` 的 `FIRST_BAR` 表；且历史 `run_JPYCHK1.ini`/`run_JPYCHK2.ini` 实际用 `2014.01.14` 起跑）；
若本次 MT5 实际首 bar 稍晚，以实际首 bar 为准并**登记原因**。

---

## 2. 完整 input 清单（写入 `[TesterInputs]`）

### 2.1 三个变体的差异项（**只此两处不同**）

| input | V1 | V2 | V3 |
|---|---|---|---|
| `InpRangeEndUtcHour` | **6** | **3** | **6** |
| `InpTP_RMult` | **1.5** | **1.5** | **1.0** |

### 2.2 全部 input（其余三者完全相同）

```
--- 标识 ---
InpRunTag                  (每 run 唯一，ASCII)
InpMagic                   20260914

--- 时段（UTC 定义）---
InpRangeStartUtcHour       0
InpRangeEndUtcHour         6        # V2 → 3
InpBreakoutStartUtcHour    7
InpBreakoutEndUtcHour      12
InpHardFlatUtcHour         20

--- 信号 ---
InpSignalTFMinutes         30
InpATRPeriod               14
InpMinRangeATRMult         0.5

--- 出场 ---
InpSL_ATR                  1.0
InpTP_RMult                1.5      # V3 → 1.0
InpMaxBarsInTrade          16

--- 风险 ---
InpRiskPct                 1.5
InpMinLotMaxRiskPct        3.0
InpAllowMinLotOvershoot    false

--- 方向 ---
InpAllowLong               true
InpAllowShort              true

--- 时间系统 ---
InpUseDynamicDstOffset     true     # 按交易周动态推导，禁止整段固定
InpExpectedServerOffsetMin 2
InpExpectedServerOffsetMax 3

--- 审计与控制 ---
InpWriteAudit              true
InpWriteRejectAudit        true
InpRunTimeSelfcheck        true
InpLatencyMs               0
InpLatencyTicks            0
InpVerboseLog              false

--- 禁止项（写死，不可调）---
InpUseGrid                 false
InpUseMartingale           false
InpUseTrailingWin          false
```

**★以上 33 个 input 必须在 `dsh_JSB30.mq5` 的源码 input 清单中【全部真实存在】。
任何 INI 里出现源码不存在的 input → `fail-close`（拒绝启动）。**

---

## 3. N0 静态闸门检查项（编译前必须逐条通过）

```
[  ]  1. run_id 为纯 ASCII，且与既有 1,800+ run tag 不重复
[  ]  2. symbol == USDJPYm（真实券商品种，非自建）
[  ]  3. TRAIN 日期 = 2014.01.14 ~ 2024.05.31（或实际首 bar，需登记）
[  ]  4. VALID 日期 = 2024.06.01 ~ 2025.05.31
[  ]  5. ★TRAIN/VALID 与 exposed_oos(2025-06-01~2026-05-31) 无重叠
[  ]  6. ★TRAIN/VALID 与 user_holdout(2026-06-01~2026-09-30) 无重叠
[  ]  7. deposit = 500 / Currency = USD / Leverage = 1:200 / Model = 2
[  ]  8. [TesterInputs] 每个参数名都存在于 EA 源码 input 清单（check_inputs.py）
[  ]  9. 未知 input → fail-close（拒绝启动）
[  ] 10. 报告名 = report_<tag>，且不存在同名文件（不覆盖）
[  ] 11. 审计目录不复用（Common\Files\dshtrend\<tag>\）
[  ] 12. 三个变体只有【两处】输入不同（range end / TP）
[  ] 13. ★不存在 V2+V3 组合版
[  ] 14. 不覆盖任何旧 EA（新建 dsh_JSB30.mq5）
[  ] 15. 所有 run 先写 planned manifest 再执行
[  ] 16. 禁止自建 symbol / CSV 回灌
```

---

## 4. 冻结哈希留位（N1 完成后填写）

| 项 | 值 |
|---|---|
| 源码路径 | `deepseek数据保存/mql5/dshtools/dsh_JSB30.mq5` |
| **源码 SHA-256** | `（N1 后填）` |
| EX5 路径 | `<Terminal>/MQL5/Experts/dshtrend/dsh_JSB30.ex5` |
| **EX5 SHA-256** | `（N1 后填）` |
| 编译结果 | `（N1 后填：0 errors / 0 warnings）` |
| round-trip 自测 | `（N1 后填：冬令周 / 夏令周 / DST 切换周 三类）` |

**★任何影响策略行为或经济审计字段的修复 → 必须重新 N1、重新 hash、重新登记（GPT §4）。**

---

## 5. 当前状态

```
阶段    : N0（静态输入表完成）
已做    : JSB30_preregistration_final.md · JSB30_static_inputs_final.md
未做    : 编译、MT5 运行、参数扫描、VALID
状态    : preregistered_final / no_mt5_authorization_yet（N0 护栏通过后进 N1）
```
