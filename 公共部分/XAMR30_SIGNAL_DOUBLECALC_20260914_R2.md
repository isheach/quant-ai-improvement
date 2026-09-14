# XAMR30 N1R3 Signal Double-Calc R2 Report

- Date: 2026-09-14
- Starting HEAD: `e2777abba28e6f65f84e74e28b4a69dd8f911703`
- R1 disposition: **FAIL_REFERENCE_SPEC** (R1 evidence retained)
- SIGNAL_DOUBLECALC_R2: **PASS**

## R1 correction rationale

R1 used a Python Wilder/RMA ATR reference. The original preregistration only said `ATR14_t = ATR(14) on M30`; it did not prescribe Wilder/RMA. N1R3 had already frozen `iATR(_Symbol, PERIOD_M30, 14)` before any economic run. R1 observed MT5 iATR equal to the arithmetic mean of the current 14 True Range values in 90/90 rows. The R1 FAIL is therefore a verification-reference-spec error, not a strategy failure.
The clarification is recorded in `公共部分/XAMR30_ATR_REFERENCE_CLARIFICATION_20260914.md`; the R1 report and R1 machine outputs were not overwritten.

## Frozen identity and gates

- Strategy source: `CA5AD7339FE415CBC3BD2304B94C47E755B2A6292AA5A69FC1E34D5B7E72826C`; canonical/deployed N1R3 EX5: `F374890F28022FCB88FA55BD34CD5BCE82DFB93A6C4EA549A3ACF34A60F658B2` / `F374890F28022FCB88FA55BD34CD5BCE82DFB93A6C4EA549A3ACF34A60F658B2`.
- Strategy EA modified: **NO**. Preregistration, Data Freeze, Gate A/B, 77-month evidence, and R1 evidence were not modified.
- STRATEGY_PROVENANCE: **PASS**; DATA_FREEZE: **PASS**.
- R1 MQL Probe source and EX5 were reused unchanged; no third Probe run was needed.

## Sample and raw-data identity

- R1/R2 timestamp identity: **True** (90/90 exact); candidate/control remain 60/30.
- Raw USDJPYm/XAUUSDm identity: **PASS**; the R1 manifest SHA, first/last timestamps, and bar counts were unchanged.
- No new sample, window, market export, tolerance, strategy source, binary, or economic result was used.

## R2 Python vs MQL result

- Reference: MT5 iATR observed semantics = arithmetic mean of current 14 True Range values; P20/P80 use the prior 500 ATR values only, nearest-rank indexes 99 and 399.
- Field pass counts: `{"ema48": 90, "residual": 90, "sigma48": 90, "z_score": 90, "atr14": 90, "atr_p20": 90, "atr_p80": 90, "xau_return": 90}`.
- Discrete flag pass counts: `{"v1_candidate": 90, "v3_candidate": 90, "direction": 90, "atr_regime_pass": 90, "xau_filter_pass": 90}`.
- XAU exact timestamp/OHLC: 90/90.
- Maximum diffs: `{"ema48": 4.9539039537194185e-11, "residual": 4.9559356618544825e-11, "sigma48": 4.952993570839226e-11, "z_score": 5.0025317221980004e-11, "atr14": 4.286368482375735e-11, "atr_p20": 4.286020149901759e-11, "atr_p80": 4.2862713378610806e-11, "xau_return": 4.990534125271645e-11}`; worst rows: `{"ema48": "DSTTR_C_04", "residual": "DSTTR_C_04", "sigma48": "WINTER_C_01", "z_score": "SUMMER_C_03", "atr14": "SUMMER_C_15", "atr_p20": "SUMMER_C_12", "atr_p80": "SUMMER_C_10", "xau_return": "WINTER_C_13"}`.
- Explicit ATR/P20/P80 maximum diffs: ATR14=4.28636848238e-11; P20=4.2860201499e-11; P80=4.28627133786e-11.

## Inherited bridge

- Probe → frozen N1R3 final-smoke audit: **37/37 PASS**, inherited without recomputation.
- R1 bridge CSV SHA: `7992FBD5E8F9FB638E2E80393C35BA496EF15D482406BF60E0FA333F792075C1`; JSON SHA: `465E927DC70D9DBCFB57D3F93CE93836E562EAB87D951E813787B993FAE97AE3`; both match the R1 baseline.
- Unexplained mismatch count: **0**.

## Machine evidence

- `deepseek数据保存/执行_XAMR30/doublecalc_xamr30_r2.py`
- `deepseek数据保存/执行_XAMR30/doublecalc_r2/XAMR30_doublecalc_R2_90.csv` / `.json`
- `deepseek数据保存/执行_XAMR30/doublecalc_r2/XAMR30_doublecalc_R2_summary.json`
- `deepseek数据保存/执行_XAMR30/doublecalc_r2/XAMR30_R1_vs_R2_sample_identity.json`
- `公共部分/XAMR30_ATR_REFERENCE_CLARIFICATION_20260914.md`

## Explicit stop

R2 completes the reference correction only. Not run: N1R4, N0 four-way, V1/V2/V3 TRAIN, bootstrap, VALID, exposed OOS, and user holdout. Economic results were not read.
