# XAMR30 N1R3 Signal Double-Calc Report

- Date: 2026-09-14
- Starting HEAD: `f5613d57234307d39459b4258e07c48ae6c1f8d5`
- Provenance: **PASS**
- Final signal double-calc: **FAIL**

## Strategy identity

- Source: `D:\desktop\新量化策略\_repo_量化交易ai改进\deepseek数据保存\mql5\dshtools\dsh_XAMR30.mq5` · `CA5AD7339FE415CBC3BD2304B94C47E755B2A6292AA5A69FC1E34D5B7E72826C`
- Canonical N1R3 EX5: `D:\desktop\新量化策略\_repo_量化交易ai改进\deepseek数据保存\执行_XAMR30\dsh_XAMR30_N1R3.ex5` · `F374890F28022FCB88FA55BD34CD5BCE82DFB93A6C4EA549A3ACF34A60F658B2`
- Deployed Tester EX5: `C:\Users\UIC\AppData\Roaming\MetaQuotes\Terminal\53785E099C927DB68A545C249CDBCE06\MQL5\Experts\dshtrend\dsh_XAMR30.ex5` · `F374890F28022FCB88FA55BD34CD5BCE82DFB93A6C4EA549A3ACF34A60F658B2`
- Build: MetaEditor / MT5 build 6184, 0 errors / 0 warnings.
- The legacy `N1_ea_XAMR30_frozen_hashes.sha256` is preserved as a superseded pre-N1R3 record; it was not overwritten.

## Fixed sample

- Windows: WINTER 2023-01-02 through 2023-01-31; DSTTR 2023-03-20 through 2023-04-07; SUMMER 2023-07-03 through 2023-07-31.
- Selected rows: 90 = 60 candidate + 30 control; bridge rows: 37.
- Algorithm: sort valid pool by timestamp; equally spaced positions round-half-up over the entire pool.
- Candidate pool: valid EMA48/sigma48/ATR500/exact-XAU, |z| >= 1.5. Control pool is the same validity set with |z| < 1.5. ATR regime and XAU filter were not used for selection.

## Raw data and independent math

- Manifest: `deepseek数据保存/执行_XAMR30/doublecalc_raw_manifest.json`.
- USDJPYm warm-up bars before the first selected timestamp: 12526 (requirement >= 5000).
- Raw source: real MT5 Tester M30 OHLC via read-only Probe `CopyRates`; no synthetic symbol and no CSV reinjection.
- Python independently computed EMA48 (alpha 2/(48+1)), residual, sample sigma48 over t-48..t-1, Wilder ATR14, prior-500 nearest-rank P20/P80, exact XAU join, return, v1/v3 flags, direction, ATR regime, and XAU filter.
- MQL independently computed the same fields through iMA EMA48, iATR, SigmaBeforeT, AtrPercentile, and exact XAU M30 lookup; Python values were not fed to the Probe.

## Python vs MQL

- Complete rows: FAIL (90/90).
- XAU exact timestamp/OHLC: 90/90.
- Continuous field pass counts: `{"ema48": 90, "residual": 90, "sigma48": 90, "atr14": 0, "atr_p20": 0, "atr_p80": 0, "z_score": 90, "xau_return": 90}`.
- Discrete flag pass counts: `{"v1_candidate": 90, "v3_candidate": 90, "direction": 90, "atr_regime_pass": 77, "xau_filter_pass": 90}`.
- Maximum diffs: `{"ema48": 4.9539039537194185e-11, "residual": 4.9559356618544825e-11, "sigma48": 4.952993570839226e-11, "atr14": 0.15300157478609555, "atr_p20": 0.026890332207199955, "atr_p80": 0.017025627938293347, "z_score": 5.0025317221980004e-11, "xau_return": 4.990534125271645e-11}`; worst rows: `{"ema48": "DSTTR_C_04", "residual": "DSTTR_C_04", "sigma48": "WINTER_C_01", "atr14": "WINTER_C_09", "atr_p20": "SUMMER_K_06", "atr_p80": "SUMMER_K_06", "z_score": "SUMMER_C_03", "xau_return": "WINTER_C_13"}`.
- iATR semantic diagnostic: MT5 MQL `iATR` matched the current 14-bar simple mean of true range in 90/90 rows (max diagnostic diff 4.28636848238e-11); the mandated Python Wilder ATR reference therefore conflicts with the observed MQL iATR semantics.
- Mismatch detail: `atr14` at `2023.01.02 23:00:00`; Python Wilder=0.125834693983, MQL iATR=0.106, diff=0.0198346939827, tolerance=1e-06. Sixty surrounding raw bars are preserved in `D:\desktop\新量化策略\_repo_量化交易ai改进\deepseek数据保存\执行_XAMR30\doublecalc\XAMR30_atr_mismatch_context_60.csv` and its JSON companion.
- This is recorded as `SIGNAL_DOUBLECALC=FAIL` without changing the strategy EA, tolerances, or sample selection; the reference-semantics decision is left to Planner/N1R4.

## Probe bridge to N1R3 final-smoke audit

- Compared all 37 existing audit rows: PASS.
- Audit continuous field pass counts: `{"ema48": 37, "residual": 37, "sigma48": 37, "z_score": 37, "atr14": 37, "atr_p20": 37, "atr_p80": 37, "xau_open": 37, "xau_close": 37, "xau_return": 37}`.
- Maximum rounded-audit diffs: `{"ema48": 0.0004705090999834738, "residual": 0.0004705091000000161, "sigma48": 0.0004962582999999965, "z_score": 4.934200000139555e-06, "atr14": 0.0005000000000000004, "atr_p20": 0.0005000000000000004, "atr_p80": 0.0005000000000000004, "xau_open": 0.0, "xau_close": 0.0, "xau_return": 4.857999999999946e-07}`; worst rows: `{"ema48": "AUDIT_DSTTR_15", "residual": "AUDIT_DSTTR_15", "sigma48": "AUDIT_DSTTR_17", "z_score": "AUDIT_WINTER_7", "atr14": "AUDIT_SUMMER_31", "atr_p20": "AUDIT_SUMMER_31", "atr_p80": "AUDIT_SUMMER_31", "xau_open": "AUDIT_SUMMER_31", "xau_close": "AUDIT_SUMMER_31", "xau_return": "AUDIT_SUMMER_19"}`.
- Bridge fields include signal timestamp, EMA48/residual/sigma48/z, ATR14/P20/P80, exact XAU timestamp/OHLC/return, and trade direction/required-pass flags.

## Machine evidence

- `deepseek数据保存/执行_XAMR30/doublecalc/XAMR30_doublecalc_90.csv` / `.json`
- `deepseek数据保存/执行_XAMR30/doublecalc/XAMR30_probe_vs_N1R3_audit.csv` / `.json`
- `deepseek数据保存/执行_XAMR30/doublecalc/XAMR30_doublecalc_summary.json`
- `deepseek数据保存/执行_XAMR30/doublecalc/XAMR30_atr_mismatch_context_60.csv` / `.json`
- `deepseek数据保存/mql5/dshtools/dsh_XAMR30SignalProbe_v1.mq5`

No strategy EA, Data Freeze, 77-month evidence, TRAIN/VALID/OOS/holdout data, or tolerance was modified in this stage.
