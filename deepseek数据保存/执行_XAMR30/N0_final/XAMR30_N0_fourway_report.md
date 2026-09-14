# XAMR30 N0 Four-Way Report

A = source input interface; B = static table; C = resolved INI; D = planned manifest.

- N0_FOURWAY: **PASS**
- Source input count: 31
- Planned records: 6 (TRAIN=3, VALID conditional=3)
- Four-way mismatch count: 0
- Variant overrides: only `InpRunTag`, `InpZThreshold`, `InpCrossAssetFilter`.
- Availability invariant: exact XAU timestamp availability is checked before the filter branch, including V2.
- Forbidden exposed-OOS/user-holdout overlap: zero required.
- No economic execution occurred.

## Planned runs

| Run | Variant | Role | Status |
|---|---|---|---|
| DS260914_XAMR30_V1_TRAIN | V1 | TRAIN | PASS |
| DS260914_XAMR30_V2_TRAIN | V2 | TRAIN | PASS |
| DS260914_XAMR30_V3_TRAIN | V3 | TRAIN | PASS |
| DS260914_XAMR30_V1_VALID | V1 | VALID | PASS |
| DS260914_XAMR30_V2_VALID | V2 | VALID | PASS |
| DS260914_XAMR30_V3_VALID | V3 | VALID | PASS |
