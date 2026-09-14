# XAMR30 N1R3 strategy identity freeze

Date: 2026-09-14
Starting repository HEAD: `f5613d57234307d39459b4258e07c48ae6c1f8d5`
Origin: `main` at the same commit; the working tree was clean before this
stage.

## Frozen strategy identity

| Item | Path / value | Size | SHA-256 |
|---|---|---:|---|
| Canonical source | `deepseek数据保存/mql5/dshtools/dsh_XAMR30.mq5` | 47,596 B | `CA5AD7339FE415CBC3BD2304B94C47E755B2A6292AA5A69FC1E34D5B7E72826C` |
| Execution source copy | `deepseek数据保存/执行_XAMR30/dsh_XAMR30_N1R3.mq5` | 47,596 B | `CA5AD7339FE415CBC3BD2304B94C47E755B2A6292AA5A69FC1E34D5B7E72826C` |
| Canonical frozen EX5 | `deepseek数据保存/执行_XAMR30/dsh_XAMR30_N1R3.ex5` | 50,906 B | `F374890F28022FCB88FA55BD34CD5BCE82DFB93A6C4EA549A3ACF34A60F658B2` |
| Deployed Tester EX5 | `C:/Users/UIC/AppData/Roaming/MetaQuotes/Terminal/53785E099C927DB68A545C249CDBCE06/MQL5/Experts/dshtrend/dsh_XAMR30.ex5` | 50,906 B | `F374890F28022FCB88FA55BD34CD5BCE82DFB93A6C4EA549A3ACF34A60F658B2` |

The source was compiled with MetaEditor / MT5 build 6184, recorded as
`0 errors / 0 warnings`. The Tester deployment uses the generic
`dsh_XAMR30.ex5` filename; the canonical N1R3 artifact is retained under the
N1R3-specific name in the execution evidence directory. No strategy EA source
or EX5 was modified for the signal double-calculation stage.

Existing final-smoke evidence:

`deepseek数据保存/执行_XAMR30/final_smoke_verify/XAMR30_N1R3_final_smoke_report.md`

It records the same N1R3 EX5 and the three engineering windows, with 37 audit
rows total (WINTER 12, DSTTR 10, SUMMER 15). Those rows are used only as a
read-only bridge target in the next validation; no economic result is used.

## Superseded legacy hash record

`deepseek数据保存/执行_XAMR30/N1_ea_XAMR30_frozen_hashes.sha256` is an older
pre-N1R3 record for the blocked/needs-repair source (`D63B2D...` / `BEA547...`).
It is intentionally preserved and not overwritten. The effective N1R3
identity is the source/EX5 pair above and the detailed record
`deepseek数据保存/执行_XAMR30/N1R3_XAMR30_frozen_hashes.sha256`.

The repository provenance for the N1R3 final-smoke chain is the existing
commit `a102c385f231446a3f8489fe10f5a49981368fde`. This document freezes the
identity used for signal verification; it does not authorize TRAIN, VALID,
OOS, holdout, parameter search, or strategy changes.
