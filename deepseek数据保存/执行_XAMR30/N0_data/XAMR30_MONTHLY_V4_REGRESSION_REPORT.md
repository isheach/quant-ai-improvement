# XAMR30 Monthly v4 四窗口回归报告

- scope: fixed four-window Monthly Probe only
- 77-month qualification: NOT RUN
- TRAIN / VALID / Route B / exposed OOS / user holdout: NOT RUN
- starting local HEAD: `c051e688b49c4e4020b110862a4c6103c65186bb`
- starting origin/main: `c051e688b49c4e4020b110862a4c6103c65186bb`
- source SHA256: `8E2A46B5301B1FB60090B047C7C5DF7A161F3A3B379842A9287F85BF1199E98C`
- EX5 SHA256: `ED68B79228EA99359EBF4B5998D60FC0CF119511C60F0270330A8BD6621DA7AA`
- MetaEditor build: `6184`
- compile result: `0 errors, 0 warnings`

## Modified files

- `deepseek数据保存/mql5/dshtools/dsh_XAMR30Monthly_v4.mq5`
- `deepseek数据保存/执行_XAMR30/run_v4_regression.py`
- `deepseek数据保存/执行_XAMR30/N0_data/v4_regression.json`
- `deepseek数据保存/执行_XAMR30/N0_data/v4_regression.csv`
- `deepseek数据保存/执行_XAMR30/N0_data/v4_journal_vs_filtered.json`
- `deepseek数据保存/执行_XAMR30/N0_data/XAMR30_MONTHLY_V4_REGRESSION_REPORT.md`
- `deepseek数据保存/执行_XAMR30/N0_data/v4_regression_raw/m4_<window>.txt` (four raw probe outputs)

## 工程修复

- v3 保留不变；v4 为独立 EA、独立 runner、独立输出目录。
- v3 parser 的根因是读取 `lines[0]`/`lines[1]`，而 EA 文件前两行是 SELFTEST；因此旧的 0/None 与 tag mismatch 是 parser 的 false diagnosis，不是市场数据或文件名问题。
- v4 Method A 使用 `iBars + iTime` 全 series 遍历且无 `break`/`CopyTime`；Method B 使用窄范围 `CopyTime`；两者比较完整 timestamp 集合。
- v4 只允许 `OnTester` 产生有效 probe；`OnDeinitFallback` 会保留真实 provenance 并标为 INVALID。
- 移除了 `reachedEnd >= b-86400` 作为有效性门槛；末端时间仅作诊断。

## 四窗口结果

| window | parser | finalization | JPY | XAU | intersection | info % | common % | Gate A | Gate B | status |
|---|---:|---|---:|---:|---:|---:|---:|---|---|---|
| 2018-01 | 1 | OnTester | 1021 | 972 | 972 | 95.2008 | 100.0000 | PASS | PASS | PASS |
| 2023-01 | 1 | OnTester | 1060 | 963 | 963 | 90.8491 | 100.0000 | PASS | PASS | PASS |
| 2023-07 | 1 | OnTester | 1014 | 965 | 965 | 95.1677 | 100.0000 | PASS | PASS | PASS |
| 2024-03 | 1 | OnTester | 1010 | 922 | 922 | 91.2871 | 100.0000 | PASS | PASS | PASS |

## Parser / journal evidence

- `2018-01` parser_valid=1; parser_invalid_reason=``; journal={'USDJPYm': 1021}; failures=none
- `2023-01` parser_valid=1; parser_invalid_reason=``; journal={'USDJPYm': 1060}; failures=none
- `2023-07` parser_valid=1; parser_invalid_reason=``; journal={'USDJPYm': 1014}; failures=none
- `2024-03` parser_valid=1; parser_invalid_reason=``; journal={'USDJPYm': 1010}; failures=none

## Overall status: PASS

- unexplained mismatch: none

`Monthly v4 four-window regression = PASS`

`77-month qualification = NOT YET RUN / awaiting Planner approval`
