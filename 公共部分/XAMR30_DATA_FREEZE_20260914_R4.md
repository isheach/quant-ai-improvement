# XAMR30 DATA FREEZE · 2026-09-14 R4

本文件是 Monthly v4 全 77 个月数据资格阶段的结论；不包含任何策略收益判断。

## A. Provenance

- v4 source SHA-256: `8E2A46B5301B1FB60090B047C7C5DF7A161F3A3B379842A9287F85BF1199E98C`
- repo/frozen compiled EX5 SHA-256: `ED68B79228EA99359EBF4B5998D60FC0CF119511C60F0270330A8BD6621DA7AA`
- Tester deployed EX5 SHA-256: `ED68B79228EA99359EBF4B5998D60FC0CF119511C60F0270330A8BD6621DA7AA`
- EX5 provenance note: the Git mirror excludes EX5; fresh MetaEditor 6184 recompile probes were 0/0 but produced non-identical transient hashes, so no new binary was deployed. The Tester binary remains the frozen ED68 artifact.
- MetaEditor: build 6184; compile result 0 errors / 0 warnings
- parent commit: `5a853628ed1ebe3c5f8e57f3d111319c05340c99`
- 本阶段 commit: see the final Git commit reported to Planner after this file is committed

## B. Frozen Gate

- Gate A: `common_session_alignment_ratio = exact_intersection / XAU_existing_M30_bars >= 99%`
- Gate B: `info_availability_ratio = exact_intersection / USDJPY_M30_bars >= 90%`
- duplicate JPY/XAU = 0
- non-monotonic JPY/XAU = 0
- outside_requested_month = 0
- thresholds pre-economic frozen; they were not changed after observing 77-month results.

## C. 77 月统计

- total months = 77
- engineering PASS = 77
- engineering INVALID = 0
- Gate A PASS = 77; Gate A FAIL = 0
- Gate B PASS = 77; Gate B FAIL = 0
- both gates PASS = 77

## D. 所有真实 FAIL 月份

无真实 Gate FAIL 月份。

## E. 最接近阈值的月份

- minimum common_session_alignment_ratio = `99.5604`，month `2018-09`
- minimum info_availability_ratio = `90.8491`，month `2023-01`
- 以上仅为描述统计，不用于修改 threshold。

## F. TRAIN 起点机械计算

- last real failing month = `NONE`
- earliest all-pass suffix month = `2018-01`
- TRAIN start month = `2018-01`
- first common M30 timestamp = `2018.01.02 06:00`；只表示数据层 eligible/common bar，不表示 first signal candidate 或 first actual trade。

## G. USDJPY execution coverage provenance

- execution_coverage_evidence = `previously_verified`
- `deepseek数据保存/执行_下一family_20260913/N1_ea/JSB30_history_coverage_final.md`; Tester-only real USDJPYm/Model=2 coverage; authoritative coverage freeze commit `54ca679bf58bfde9da22b3c8ff598529897c8a0e`; review corroboration `公共部分/JSB30_TRAIN_VALID_最终审阅包_20260914_R2.md`.

## H. 禁止区间与未执行项

- VALID = 2024-06-01 ~ 2025-05-31（未运行）
- exposed_oos = 2025-06-01 ~ 2026-05-31（未读取）
- user_holdout = 2026-06-01 ~ 2026-09-30（未读取）
- 未运行 signal double-calc、N0 four-way、V1/V2/V3 TRAIN、bootstrap、VALID、Route B、capital sensitivity、ML。
- 未修改 dsh_XAMR30.mq5、dsh_XAMR30Monthly_v4.mq5、Gate A/B 或既有 v4 regression evidence。

## Final status

- MONTHLY_V4_77M = `PASS`
- DATA_FREEZE = `PASS`
- TRAIN_START = `2018-01`
