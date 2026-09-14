# XAMR30 N0 Guard Report

- Dry-run only: parses, compares, hashes, validates, and writes evidence.
- **NO MT5 ECONOMIC EXECUTION**; no terminal or tester was started.

- N0_FOURWAY: **PASS**
- Parsed source inputs: **31**
- Planned runs: **6**
- Four-way mismatch count: **0**
- Forbidden-date overlaps: **0**
- Source SHA: `CA5AD7339FE415CBC3BD2304B94C47E755B2A6292AA5A69FC1E34D5B7E72826C`
- Canonical EX5 SHA: `F374890F28022FCB88FA55BD34CD5BCE82DFB93A6C4EA549A3ACF34A60F658B2`
- Deployed EX5 SHA: `F374890F28022FCB88FA55BD34CD5BCE82DFB93A6C4EA549A3ACF34A60F658B2`

## Global checks

| Check | Result | Detail |
|---|---|---|
| strategy source hash | PASS | CA5AD7339FE415CBC3BD2304B94C47E755B2A6292AA5A69FC1E34D5B7E72826C |
| canonical strategy EX5 hash | PASS | F374890F28022FCB88FA55BD34CD5BCE82DFB93A6C4EA549A3ACF34A60F658B2 |
| deployed strategy EX5 hash | PASS | F374890F28022FCB88FA55BD34CD5BCE82DFB93A6C4EA549A3ACF34A60F658B2 |
| source input parse nonempty | PASS | 31 |
| source input names unique | PASS | 31 |
| planned manifest exists | PASS | D:\desktop\新量化策略\_repo_量化交易ai改进\公共部分\XAMR30_planned_runs.jsonl |
| planned run count = 6 | PASS | 6 |
| planned run tags unique | PASS | run tags |
| planned report paths unique | PASS | reports |
| planned audit dirs unique | PASS | audit dirs |
| source/static table exists | PASS | D:\desktop\新量化策略\_repo_量化交易ai改进\公共部分\XAMR30_static_inputs_final.md |
| static input count exact | PASS | source=31 static=31 |
| DATA_FREEZE = PASS | PASS | Data Freeze report |
| TRAIN start month = 2018-01 | PASS | Data Freeze report |
| FINAL_SMOKE_INDEPENDENT = PASS | PASS | PASS |
| independent smoke hold checks = 37/37 | PASS | {"trades": 37, "time_exit_count": 2, "hold_bar_checks": 37, "hold_bar_pass": 37, "max_full_held_bars": 12, "weekend_trade": [{"window": "SUMMER", "deal_ticket": "25", "position_id": "24", "entry_time": "2023.07.21 17:00:00", "exit_time": "2023.07.23 23:00:00", "exit_reason": "time_exit", "full_held_bars": 12, "first_counted_bar_open": "2023.07.21 17:00:00", "last_counted_bar_open": "2023.07.23 22:30:00", "counted_bar_timestamps": ["2023.07.21 17:00:00", "2023.07.21 17:30:00", "2023.07.21 18:00:00", "2023.07.21 18:30:00", "2023.07.21 19:00:00", "2023.07.21 19:30:00", "2023.07.21 20:00:00", "2023.07.21 20:30:00", "2023.07.23 21:00:00", "2023.07.23 21:30:00", "2023.07.23 22:00:00", "2023.07.23 22:30:00"]}], "checks": {"passed": 72, "total": 72}} |
| SIGNAL_DOUBLECALC_R2 = PASS | PASS | PASS |
| exact XAU availability mask before filter branch | PASS | {"exact_declaration": 35170, "exact_match": 35363, "missing_branch": 35801, "filter_branch": 36419} |
| all TRAIN configs otherwise identical | PASS | fixed inputs/tester core |
| all VALID configs otherwise identical | PASS | fixed inputs/tester core |
| V1 TRAIN/VALID inputs identical | PASS | only date/identity changes |
| V2 TRAIN/VALID inputs identical | PASS | only date/identity changes |
| V3 TRAIN/VALID inputs identical | PASS | only date/identity changes |
| TRAIN records = 3 | PASS | 3 |
| VALID conditional records = 3 | PASS | 3 |

## Per-run checks

### DS260914_XAMR30_V1_TRAIN

| Check | Result | Detail |
|---|---|---|
| source/static name set exact | PASS | source=31 static=31 |
| static/manifest name set exact | PASS | source=31 manifest=31 |
| static/INI name set exact | PASS | source=31 ini=31 |
| INI values parse by source types | PASS | typed parse |
| INI/manifest resolved values exact | PASS | all source inputs |
| source/static type and default exact | PASS | source-derived table |
| all fixed inputs equal source defaults | PASS | bad=none |
| variant overrides only whitelist | PASS | bad=none |
| V1 exact dynamic values | PASS | {"InpZThreshold": 1.5, "InpCrossAssetFilter": true} |
| Tester Expert frozen | PASS | actual=dshtrend\dsh_XAMR30 expected=dshtrend\dsh_XAMR30 |
| Tester Symbol frozen | PASS | actual=USDJPYm expected=USDJPYm |
| Tester Period frozen | PASS | actual=M30 expected=M30 |
| Tester Model frozen | PASS | actual=2 expected=2 |
| Tester Optimization frozen | PASS | actual=0 expected=0 |
| Tester Deposit frozen | PASS | actual=500 expected=500 |
| Tester Currency frozen | PASS | actual=USD expected=USD |
| Tester Leverage frozen | PASS | actual=1:200 expected=1:200 |
| Tester Visual frozen | PASS | actual=0 expected=0 |
| Tester FromDate matches manifest | PASS | actual=2018.01.01 expected=2018.01.01 |
| Tester ToDate matches manifest | PASS | actual=2024.05.31 expected=2024.05.31 |
| Tester Report matches manifest | PASS | actual=DS260914_XAMR30_V1_TRAIN expected=DS260914_XAMR30_V1_TRAIN |
| planned INI exists | PASS | D:\desktop\新量化策略\_repo_量化交易ai改进\deepseek数据保存\执行_XAMR30\N0_final\resolved_INIs\run_DS260914_XAMR30_V1_TRAIN.ini |
| economic execution flag is NOT_RUN | PASS | NOT_RUN |
| forbidden-date overlap = 0 | PASS | none |

### DS260914_XAMR30_V2_TRAIN

| Check | Result | Detail |
|---|---|---|
| source/static name set exact | PASS | source=31 static=31 |
| static/manifest name set exact | PASS | source=31 manifest=31 |
| static/INI name set exact | PASS | source=31 ini=31 |
| INI values parse by source types | PASS | typed parse |
| INI/manifest resolved values exact | PASS | all source inputs |
| source/static type and default exact | PASS | source-derived table |
| all fixed inputs equal source defaults | PASS | bad=none |
| variant overrides only whitelist | PASS | bad=none |
| V2 exact dynamic values | PASS | {"InpZThreshold": 1.5, "InpCrossAssetFilter": false} |
| Tester Expert frozen | PASS | actual=dshtrend\dsh_XAMR30 expected=dshtrend\dsh_XAMR30 |
| Tester Symbol frozen | PASS | actual=USDJPYm expected=USDJPYm |
| Tester Period frozen | PASS | actual=M30 expected=M30 |
| Tester Model frozen | PASS | actual=2 expected=2 |
| Tester Optimization frozen | PASS | actual=0 expected=0 |
| Tester Deposit frozen | PASS | actual=500 expected=500 |
| Tester Currency frozen | PASS | actual=USD expected=USD |
| Tester Leverage frozen | PASS | actual=1:200 expected=1:200 |
| Tester Visual frozen | PASS | actual=0 expected=0 |
| Tester FromDate matches manifest | PASS | actual=2018.01.01 expected=2018.01.01 |
| Tester ToDate matches manifest | PASS | actual=2024.05.31 expected=2024.05.31 |
| Tester Report matches manifest | PASS | actual=DS260914_XAMR30_V2_TRAIN expected=DS260914_XAMR30_V2_TRAIN |
| planned INI exists | PASS | D:\desktop\新量化策略\_repo_量化交易ai改进\deepseek数据保存\执行_XAMR30\N0_final\resolved_INIs\run_DS260914_XAMR30_V2_TRAIN.ini |
| economic execution flag is NOT_RUN | PASS | NOT_RUN |
| forbidden-date overlap = 0 | PASS | none |

### DS260914_XAMR30_V3_TRAIN

| Check | Result | Detail |
|---|---|---|
| source/static name set exact | PASS | source=31 static=31 |
| static/manifest name set exact | PASS | source=31 manifest=31 |
| static/INI name set exact | PASS | source=31 ini=31 |
| INI values parse by source types | PASS | typed parse |
| INI/manifest resolved values exact | PASS | all source inputs |
| source/static type and default exact | PASS | source-derived table |
| all fixed inputs equal source defaults | PASS | bad=none |
| variant overrides only whitelist | PASS | bad=none |
| V3 exact dynamic values | PASS | {"InpZThreshold": 2.0, "InpCrossAssetFilter": true} |
| Tester Expert frozen | PASS | actual=dshtrend\dsh_XAMR30 expected=dshtrend\dsh_XAMR30 |
| Tester Symbol frozen | PASS | actual=USDJPYm expected=USDJPYm |
| Tester Period frozen | PASS | actual=M30 expected=M30 |
| Tester Model frozen | PASS | actual=2 expected=2 |
| Tester Optimization frozen | PASS | actual=0 expected=0 |
| Tester Deposit frozen | PASS | actual=500 expected=500 |
| Tester Currency frozen | PASS | actual=USD expected=USD |
| Tester Leverage frozen | PASS | actual=1:200 expected=1:200 |
| Tester Visual frozen | PASS | actual=0 expected=0 |
| Tester FromDate matches manifest | PASS | actual=2018.01.01 expected=2018.01.01 |
| Tester ToDate matches manifest | PASS | actual=2024.05.31 expected=2024.05.31 |
| Tester Report matches manifest | PASS | actual=DS260914_XAMR30_V3_TRAIN expected=DS260914_XAMR30_V3_TRAIN |
| planned INI exists | PASS | D:\desktop\新量化策略\_repo_量化交易ai改进\deepseek数据保存\执行_XAMR30\N0_final\resolved_INIs\run_DS260914_XAMR30_V3_TRAIN.ini |
| economic execution flag is NOT_RUN | PASS | NOT_RUN |
| forbidden-date overlap = 0 | PASS | none |

### DS260914_XAMR30_V1_VALID

| Check | Result | Detail |
|---|---|---|
| source/static name set exact | PASS | source=31 static=31 |
| static/manifest name set exact | PASS | source=31 manifest=31 |
| static/INI name set exact | PASS | source=31 ini=31 |
| INI values parse by source types | PASS | typed parse |
| INI/manifest resolved values exact | PASS | all source inputs |
| source/static type and default exact | PASS | source-derived table |
| all fixed inputs equal source defaults | PASS | bad=none |
| variant overrides only whitelist | PASS | bad=none |
| V1 exact dynamic values | PASS | {"InpZThreshold": 1.5, "InpCrossAssetFilter": true} |
| Tester Expert frozen | PASS | actual=dshtrend\dsh_XAMR30 expected=dshtrend\dsh_XAMR30 |
| Tester Symbol frozen | PASS | actual=USDJPYm expected=USDJPYm |
| Tester Period frozen | PASS | actual=M30 expected=M30 |
| Tester Model frozen | PASS | actual=2 expected=2 |
| Tester Optimization frozen | PASS | actual=0 expected=0 |
| Tester Deposit frozen | PASS | actual=500 expected=500 |
| Tester Currency frozen | PASS | actual=USD expected=USD |
| Tester Leverage frozen | PASS | actual=1:200 expected=1:200 |
| Tester Visual frozen | PASS | actual=0 expected=0 |
| Tester FromDate matches manifest | PASS | actual=2024.06.01 expected=2024.06.01 |
| Tester ToDate matches manifest | PASS | actual=2025.05.31 expected=2025.05.31 |
| Tester Report matches manifest | PASS | actual=DS260914_XAMR30_V1_VALID expected=DS260914_XAMR30_V1_VALID |
| planned INI exists | PASS | D:\desktop\新量化策略\_repo_量化交易ai改进\deepseek数据保存\执行_XAMR30\N0_final\resolved_INIs\run_DS260914_XAMR30_V1_VALID.ini |
| economic execution flag is NOT_RUN | PASS | NOT_RUN |
| forbidden-date overlap = 0 | PASS | none |

### DS260914_XAMR30_V2_VALID

| Check | Result | Detail |
|---|---|---|
| source/static name set exact | PASS | source=31 static=31 |
| static/manifest name set exact | PASS | source=31 manifest=31 |
| static/INI name set exact | PASS | source=31 ini=31 |
| INI values parse by source types | PASS | typed parse |
| INI/manifest resolved values exact | PASS | all source inputs |
| source/static type and default exact | PASS | source-derived table |
| all fixed inputs equal source defaults | PASS | bad=none |
| variant overrides only whitelist | PASS | bad=none |
| V2 exact dynamic values | PASS | {"InpZThreshold": 1.5, "InpCrossAssetFilter": false} |
| Tester Expert frozen | PASS | actual=dshtrend\dsh_XAMR30 expected=dshtrend\dsh_XAMR30 |
| Tester Symbol frozen | PASS | actual=USDJPYm expected=USDJPYm |
| Tester Period frozen | PASS | actual=M30 expected=M30 |
| Tester Model frozen | PASS | actual=2 expected=2 |
| Tester Optimization frozen | PASS | actual=0 expected=0 |
| Tester Deposit frozen | PASS | actual=500 expected=500 |
| Tester Currency frozen | PASS | actual=USD expected=USD |
| Tester Leverage frozen | PASS | actual=1:200 expected=1:200 |
| Tester Visual frozen | PASS | actual=0 expected=0 |
| Tester FromDate matches manifest | PASS | actual=2024.06.01 expected=2024.06.01 |
| Tester ToDate matches manifest | PASS | actual=2025.05.31 expected=2025.05.31 |
| Tester Report matches manifest | PASS | actual=DS260914_XAMR30_V2_VALID expected=DS260914_XAMR30_V2_VALID |
| planned INI exists | PASS | D:\desktop\新量化策略\_repo_量化交易ai改进\deepseek数据保存\执行_XAMR30\N0_final\resolved_INIs\run_DS260914_XAMR30_V2_VALID.ini |
| economic execution flag is NOT_RUN | PASS | NOT_RUN |
| forbidden-date overlap = 0 | PASS | none |

### DS260914_XAMR30_V3_VALID

| Check | Result | Detail |
|---|---|---|
| source/static name set exact | PASS | source=31 static=31 |
| static/manifest name set exact | PASS | source=31 manifest=31 |
| static/INI name set exact | PASS | source=31 ini=31 |
| INI values parse by source types | PASS | typed parse |
| INI/manifest resolved values exact | PASS | all source inputs |
| source/static type and default exact | PASS | source-derived table |
| all fixed inputs equal source defaults | PASS | bad=none |
| variant overrides only whitelist | PASS | bad=none |
| V3 exact dynamic values | PASS | {"InpZThreshold": 2.0, "InpCrossAssetFilter": true} |
| Tester Expert frozen | PASS | actual=dshtrend\dsh_XAMR30 expected=dshtrend\dsh_XAMR30 |
| Tester Symbol frozen | PASS | actual=USDJPYm expected=USDJPYm |
| Tester Period frozen | PASS | actual=M30 expected=M30 |
| Tester Model frozen | PASS | actual=2 expected=2 |
| Tester Optimization frozen | PASS | actual=0 expected=0 |
| Tester Deposit frozen | PASS | actual=500 expected=500 |
| Tester Currency frozen | PASS | actual=USD expected=USD |
| Tester Leverage frozen | PASS | actual=1:200 expected=1:200 |
| Tester Visual frozen | PASS | actual=0 expected=0 |
| Tester FromDate matches manifest | PASS | actual=2024.06.01 expected=2024.06.01 |
| Tester ToDate matches manifest | PASS | actual=2025.05.31 expected=2025.05.31 |
| Tester Report matches manifest | PASS | actual=DS260914_XAMR30_V3_VALID expected=DS260914_XAMR30_V3_VALID |
| planned INI exists | PASS | D:\desktop\新量化策略\_repo_量化交易ai改进\deepseek数据保存\执行_XAMR30\N0_final\resolved_INIs\run_DS260914_XAMR30_V3_VALID.ini |
| economic execution flag is NOT_RUN | PASS | NOT_RUN |
| forbidden-date overlap = 0 | PASS | none |
