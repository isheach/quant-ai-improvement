# JSB30 静态输入表（N1R2 · 由源码自动生成，零漂移）

- ★本表由 `dsh_JSB30.mq5` 的 input 声明【自动生成】，避免手工维护造成漂移
- 四方一致性（source / 本表 / INI `[TesterInputs]` / manifest `resolved_inputs`）
  由 `n0_fourway.py` 强制检查；任何缺项、额外项、值不一致 → 拒绝运行

| # | 名称 | 类型 | 默认值 | 说明 |
|---|---|---|---|---|
| 1 | `InpRunTag` | string | "JSB30" |  |
| 2 | `InpMagic` | long | 20260914 | --- 时段（UTC；★server==UTC，故直接用 server 时间） |
| 3 | `InpRangeStartUtcHour` | int | 0 |  |
| 4 | `InpRangeEndUtcHour` | int | 6 | V2 -> 3 |
| 5 | `InpBreakoutStartUtcHour` | int | 7 |  |
| 6 | `InpBreakoutEndUtcHour` | int | 12 |  |
| 7 | `InpHardFlatUtcHour` | int | 20 | --- 信号 |
| 8 | `InpSignalTFMinutes` | int | 30 |  |
| 9 | `InpATRPeriod` | int | 14 |  |
| 10 | `InpMinRangeATRMult` | double | 0.5 | --- 出场 |
| 11 | `InpSL_ATR` | double | 1.0 |  |
| 12 | `InpTP_RMult` | double | 1.5 | V3 -> 1.0 |
| 13 | `InpMaxBarsInTrade` | int | 16 | --- 风险 |
| 14 | `InpRiskPct` | double | 1.5 |  |
| 15 | `InpMinLotMaxRiskPct` | double | 3.0 |  |
| 16 | `InpAllowMinLotOvershoot` | bool | false | --- 方向 |
| 17 | `InpAllowLong` | bool | true |  |
| 18 | `InpAllowShort` | bool | true | --- ★时间系统：N1R2 裁定为 UTC+0（保留为 provenance / 自检开关） |
| 19 | `InpUseDynamicDstOffset` | bool | false | ★恒 false：不做任何 offset 转换 |
| 20 | `InpExpectedServerOffsetMin` | int | 0 | ★实测 0 |
| 21 | `InpExpectedServerOffsetMax` | int | 0 | ★实测 0 |
| 22 | `InpOcpTolUsd` | double | 0.05 | ★预注册：|DEAL_PROFIT - OCP| <= 0.05 |
| 23 | `InpFormulaTolPct` | double | 5.0 | 独立公式仅作【诊断】，不参与 pass/fail |
| 24 | `InpFormulaDiagnosticOnly` | bool | true | ★恒为诊断用 |
| 25 | `InpWriteAudit` | bool | true |  |
| 26 | `InpWriteRejectAudit` | bool | true |  |
| 27 | `InpRunTimeSelfcheck` | bool | true |  |
| 28 | `InpLatencyMs` | int | 0 |  |
| 29 | `InpLatencyTicks` | int | 0 |  |
| 30 | `InpVerboseLog` | bool | false | --- 禁止项（写死） |
| 31 | `InpUseGrid` | bool | false |  |
| 32 | `InpUseMartingale` | bool | false |  |
| 33 | `InpUseTrailingWin` | bool | false | ==================== 时间系统（N1R2：恒等映射）==================== |

## 变体差异（★只允许这两处）

| input | V1 (baseline) | V2 | V3 |
|---|---|---|---|
| `InpRangeEndUtcHour` | 6（expected 12 bars） | **3（expected 6 bars）** | 6 |
| `InpTP_RMult` | 1.5 | 1.5 | **1.0** |

## 固定口径

```
TRAIN = 2018-01-01 ~ 2024-05-31     （N1.6R coverage 冻结）
VALID = 2024-06-01 ~ 2025-05-31
server_utc_offset = 0                （N1R2 实测裁定，server == UTC）
OCP 主判据 = |DEAL_PROFIT - OCP| <= 0.05 USD
独立公式 = diagnostic only（不参与 pass/fail）
range 完整性 = rangeCount == expected（V1/V3: 12, V2: 6），否则当天不交易
```

