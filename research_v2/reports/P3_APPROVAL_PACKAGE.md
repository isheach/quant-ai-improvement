# P3 审批包（2026-09-25）

## 阶段与范围

P0—P3 已完成。没有启动旧 XAMR30、没有启动新的正式策略回测、没有访问 GitHub、没有把合成测试当作历史收益证据。

## 已确认

- 实际工作区：`D:\desktop\新量化策略`；本地 Git 仓库：`_repo_量化交易ai改进`。
- HEAD：`4703322db35d4110c549def5b7f409a56082d7f1`；分支：`repair/xamr30-v1-daily-r1`。
- `remote_freshness = NOT_CHECKED_OFFLINE`。
- 优先对象：XAUUSDm M30；专家 T、MR、G、CASH。
- 记录系统、恢复快照、数据访问边界、协议定义、参数预算和运行门禁已建立。

## 仍缺与阻塞

- XAUUSDm M30 在允许区间 2018-01-01 至 2024-05-31 的有效覆盖、时间语义、重复/缺失、点差和合约规格尚未通过受限读取验证。
- 500 USD 与最小手数的账户可行性尚未在批准数据上核验。
- exact parameter values、time folds、engine task count 需在 P4 入口冻结；当前正式 run 数为 0。

## 工程测试

测试文件：`tests/test_synthetic_engineering.py`。覆盖 EMA、ATR、ER 零分母、因果性、最小手数向下取整、风险计算、恢复文件和报告幂等性。测试标记为 `SYNTHETIC_TEST`，不产生历史策略结论。

## 下一阶段批准条件

用户批准后，先做受限数据验证并记录数据哈希；验证通过后冻结具体参数与时间折，生成真实 `EXPERIMENT_PLAN.jsonl`，统计每一项 run，才可启动 P4。若数据不满足，状态为 `BLOCKED_DATA`，不擅自换品种。

当前状态：`READY_FOR_EXPERIMENT_APPROVAL`（表示 P3 审批包就绪，不表示已批准 P4）。
