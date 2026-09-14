# XAMR30 Final Static Inputs (pre-TRAIN)

This is a source-derived static table. It is a configuration freeze only; no MT5 economic run was executed.

- Strategy source SHA256: `CA5AD7339FE415CBC3BD2304B94C47E755B2A6292AA5A69FC1E34D5B7E72826C`
- Strategy canonical N1R3 EX5 SHA256: `F374890F28022FCB88FA55BD34CD5BCE82DFB93A6C4EA549A3ACF34A60F658B2`
- Allowed dynamic inputs only: `InpRunTag`, `InpZThreshold`, `InpCrossAssetFilter`.
- All other values must equal the source default in every planned run.
- `InpCrossAssetFilter=false` does not disable exact XAU availability; the source structural guard checks availability before the filter branch.

## Source-parsed input interface

| Input name | Type | Source default |
|---|---|---|
| `InpRunTag` | `string` | `"XAMR30"` |
| `InpMagic` | `long` | `20260915` |
| `InpEmaPeriod` | `int` | `48` |
| `InpSigmaWindow` | `int` | `48` |
| `InpZThreshold` | `double` | `1.5` |
| `InpATRPeriod` | `int` | `14` |
| `InpATRPercentileWindow` | `int` | `500` |
| `InpATRP20Pct` | `double` | `20.0` |
| `InpATRP80Pct` | `double` | `80.0` |
| `InpInfoSymbol` | `string` | `"XAUUSDm"` |
| `InpCrossAssetFilter` | `bool` | `true` |
| `InpSL_ATR` | `double` | `1.0` |
| `InpTP_RMult` | `double` | `0.8` |
| `InpMaxBarsInTrade` | `int` | `12` |
| `InpRiskPct` | `double` | `1.5` |
| `InpMinLotMaxRiskPct` | `double` | `3.0` |
| `InpAllowMinLotOvershoot` | `bool` | `false` |
| `InpOcpTolUsd` | `double` | `0.05` |
| `InpFormulaTolPct` | `double` | `5.0` |
| `InpFormulaDiagnosticOnly` | `bool` | `true` |
| `InpAllowLong` | `bool` | `true` |
| `InpAllowShort` | `bool` | `true` |
| `InpWriteAudit` | `bool` | `true` |
| `InpWriteRejectAudit` | `bool` | `true` |
| `InpRunTimeSelfcheck` | `bool` | `true` |
| `InpLatencyMs` | `int` | `0` |
| `InpLatencyTicks` | `int` | `0` |
| `InpVerboseLog` | `bool` | `false` |
| `InpUseGrid` | `bool` | `false` |
| `InpUseMartingale` | `bool` | `false` |
| `InpUseTrailingWin` | `bool` | `false` |

## Variant values

| Variant | InpZThreshold | InpCrossAssetFilter |
|---|---:|---|
| V1 | 1.5 | true |
| V2 | 1.5 | false |
| V3 | 2.0 | true |

## Date semantics

- TRAIN tester interval: `2018.01.01` through `2024.05.31`; Data Freeze TRAIN start month is `2018-01`.
- VALID tester interval: `2024.06.01` through `2025.05.31`.
- First common M30 bar: `2018.01.02 06:00`; this is data eligibility, not first signal or first trade.
- Exposed OOS forbidden: `2025-06-01` through `2026-05-31`.
- User holdout forbidden: `2026-06-01` through `2026-09-30`.
