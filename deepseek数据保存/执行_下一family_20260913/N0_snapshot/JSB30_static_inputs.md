# JSB30 静态输入表（N0 产物，供静态闸门校验）

- 生成时间：2026-09-13（Asia/Shanghai）
- 用途：在编译/运行【之前】把 tag、symbol、日期、deposit、Model、输入名逐项固定，
        未知输入直接拒绝。

## 1. 三个变体的 tag 与口径

| 变体 | TRAIN tag | VALID tag | 品种 | 日期 | deposit | Model | ticks |
|---|---|---|---|---|---|---|---|
| V1 | `DS260913_JSB30_V1_TRAIN` | `DS260913_JSB30_V1_VALID` | USDJPYm | 2017.01.02~2024.05.31 / 2024.06.01~2025.05.31 | 500 | 2 | 0 |
| V2 | `DS260913_JSB30_V2_TRAIN` | `DS260913_JSB30_V2_VALID` | USDJPYm | 同上 | 500 | 2 | 0 |
| V3 | `DS260913_JSB30_V3_TRAIN` | `DS260913_JSB30_V3_VALID` | USDJPYm | 同上 | 500 | 2 | 0 |
| 探针 | `DS260913_JSB30_PROBE_2014` | — | USDJPYm | 2014.01.14~2016.12.31 | 500 | 2 | 0 |

## 2. 完整输入清单（将写入 [TesterInputs]）

```
InpRunTag               (每 run 唯一)
InpRangeStartUtcHour    0
InpRangeEndUtcHour      6      # V2: 3
InpBreakoutStartUtcHour 7
InpBreakoutEndUtcHour   12
InpHardFlatUtcHour      20
InpMinRangeATRMult      0.5
InpATRPeriod            14
InpSignalTFMinutes      30
InpSL_ATR               1.0
InpTP_RMult             1.5    # V3: 1.0
InpMaxBarsInTrade       16
InpRiskPct              1.5
InpMinLotMaxRiskPct     3.0
InpAllowMinLotOvershoot false
InpWriteAudit           true
InpLatencyMs            0
InpLatencyTicks         0
InpAllowLong            true
InpAllowShort           true
InpUseGrid              false
InpUseMartingale        false
InpUseTrailingWin       false
InpMagic                20260913
InpVerboseLog           false
```

## 3. 静态闸门检查项（编译前必须逐条通过）

```
[ ] 1. tag 为纯 ASCII，且与既有 tag 不重复
[ ] 2. symbol ∈ {XAUUSDm, BTCUSDm, USDJPYm}
[ ] 3. 日期与 2026-06-01~2026-09-30 无重叠（区间重叠判定）
[ ] 4. 日期与 2025-06-01~2026-05-31 无重叠（本流程不跑 exposed_oos）
[ ] 5. deposit = 500 / Currency = USD / Model = 2
[ ] 6. [TesterInputs] 的每个参数名都存在于 EA 源码 input 清单（check_inputs.py）
[ ] 7. 报告名 = report_<tag>，且不存在同名文件（不覆盖）
[ ] 8. 三个变体只有【一个】结构轴不同（区间长度 / 收益上限）
```

## 4. 当前状态

```
状态：设计草案提交中，**未批准**
已做：本表 + JSB30_design_memo.md
未做：编译、MT5 运行、参数扫描
```
