# XAMR30 FINAL PRE-TRAIN GUARD · 2026-09-14

This is the final engineering guard before any economic run. It does not authorize TRAIN/VALID.

| Gate | Status |
|---|---|
| DATA_FREEZE | PASS |
| STRATEGY_PROVENANCE | PASS |
| SIGNAL_DOUBLECALC_R2 | PASS |
| FINAL_SMOKE_INDEPENDENT | PASS |
| N0_FOURWAY | PASS |
| **FINAL_PRETRAIN_GUARD** | **PASS** |

## Frozen identities

- Strategy source SHA256: `CA5AD7339FE415CBC3BD2304B94C47E755B2A6292AA5A69FC1E34D5B7E72826C`
- Canonical/deployed EX5 SHA256: `F374890F28022FCB88FA55BD34CD5BCE82DFB93A6C4EA549A3ACF34A60F658B2` / `F374890F28022FCB88FA55BD34CD5BCE82DFB93A6C4EA549A3ACF34A60F658B2`
- Parsed source inputs: `31`
- Planned runs: `6`; TRAIN=3, VALID conditional=3
- Exact XAU availability mask is invariant before the V1/V2/V3 filter branch.
- Tester intervals and forbidden exposed-OOS/user-holdout intervals are checked in the N0 manifest.

## Explicit non-actions

- `dsh_XAMR30.mq5` was not modified.
- The strategy EX5 was not recompiled or replaced.
- Preregistration, Data Freeze, Double-Calc R1/R2, and the historical smoke verifier were not modified or overwritten.
- No V1/V2/V3 TRAIN, bootstrap, VALID, exposed OOS, user holdout, capital sensitivity, Route B, regime detection, strategy combination, or ML run was executed.
- No economic result was read for strategy judgment.
