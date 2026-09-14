# XAMR30 Monthly v4 · 77 个月执行报告

- 开始 HEAD: `5a853628ed1ebe3c5f8e57f3d111319c05340c99`
- 开始 origin/main: `5a853628ed1ebe3c5f8e57f3d111319c05340c99`
- v4 source SHA-256: `8E2A46B5301B1FB60090B047C7C5DF7A161F3A3B379842A9287F85BF1199E98C`
- repo/frozen compiled EX5 SHA-256: `ED68B79228EA99359EBF4B5998D60FC0CF119511C60F0270330A8BD6621DA7AA`
- Tester deployed EX5 SHA-256: `ED68B79228EA99359EBF4B5998D60FC0CF119511C60F0270330A8BD6621DA7AA`
- EX5 provenance note: the Git mirror excludes EX5; fresh MetaEditor 6184 recompile probes were 0/0 but produced non-identical transient hashes, so no new binary was deployed. The Tester binary remains the frozen ED68 artifact.
- MetaEditor build: `6184`; frozen compile result: `0 errors, 0 warnings`
- command: `python "deepseek数据保存/执行_XAMR30/run_v4_77_months.py"`

## 运行范围与完整性

- months = 77；unique months = 77；raw outputs = 77
- first month = `2018-01`；last month = `2024-05`
- requested windows are generated as `[month_start, next_month_start)`.
- each month used a unique `M4Q_YYYY-MM` RunTag, INI, Tester run, parser result, and raw output.

## 工程与数据统计

- parser invalid = 0
- probe invalid = 0
- engineering PASS = 77
- engineering INVALID = 0
- A/B timestamp mismatch = 0
- journal mismatch = 0
- journal unavailable = 0
- Gate A failures = 0: none
- Gate B failures = 0: none
- both gates PASS = 77
- minimum common ratio = 99.5604 (2018-09)
- minimum info ratio = 90.8491 (2023-01)

## 真实 Gate FAIL 月份

| month | Gate A | Gate B | common % | info % | JPY | XAU | intersection |
|---|---|---|---:|---:|---:|---:|---:|
| none | — | — | — | — | — | — | — |

## TRAIN 起点机械计算

- last real failing month = `NONE`
- earliest all-pass suffix month = `2018-01`
- TRAIN start month = `2018-01`
- first common M30 timestamp = `2018.01.02 06:00` (data-layer eligible/common bar only)
- data start, first common bar, first signal candidate, and first actual trade are not conflated.

## USDJPY execution coverage provenance

- execution_coverage_evidence = `previously_verified`
- `deepseek数据保存/执行_下一family_20260913/N1_ea/JSB30_history_coverage_final.md`; Tester-only real USDJPYm/Model=2 coverage; authoritative coverage freeze commit `54ca679bf58bfde9da22b3c8ff598529897c8a0e`; review corroboration `公共部分/JSB30_TRAIN_VALID_最终审阅包_20260914_R2.md`.
- This stage did not rerun coverage or read any exposed interval.

## 最终状态

- MONTHLY_V4_77M = `PASS`
- DATA_FREEZE = `PASS`
- TRAIN_START = `2018-01`

## 明确未执行

- signal double-calc / final-smoke repair / N0 static inputs / N0 planned runs / N0 four-way: NOT RUN
- V1/V2/V3 TRAIN / bootstrap / VALID: NOT RUN
- exposed_oos (2025-06-01~2026-05-31): NOT READ
- user_holdout (2026-06-01~2026-09-30): NOT READ
- Route B / capital sensitivity / strategy portfolio / ML: NOT RUN
- dsh_XAMR30.mq5 and frozen v1/v2/v3/v4 regression evidence: NOT MODIFIED

The exact machine rows and raw probe files are in `XAMR30_monthly_alignment_v4.csv`, `XAMR30_monthly_alignment_v4.json`, and `monthly_v4_raw/`.
