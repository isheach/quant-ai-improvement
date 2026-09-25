# P1 本地资产盘点报告

盘点依据：当前工作区的文件名、文件大小、既有文档和 Git 元数据；未全量打开行情缓存，未读取保护区，未启动旧策略。

## 结论

- 本地存在 `deepseek数据保存/data/real/XAUUSDm_M1_real.csv` 和 `XAUUSDm_M5_real.csv`，但它们的完整时间覆盖、时间区、行数和费用字段尚未通过受限读取验证，当前不能宣布足够做黄金 M30 研究。
- 本地还存在 USDJPYm、BTCUSDm 的 M1/M5 文件，以及旧项目的 XAUUSDm 月度 M1 文件；本轮不自动展开其他标的，也不把跨越保护区的文件直接作为新研究输入。
- 旧目录中有大量汇总 CSV、审计产物和历史 EA；这些只能作为历史证据或工程参考，不能改名成为新候选。
- 当前可复用范围主要是指标/记录/审计工程思路；策略逻辑必须在新命名空间重写并保留来源路径与哈希。
- 最小手数、费用、时间语义和受保护区隔离仍是正式研究的阻塞点。

## 资产分级

`DATASET_INVENTORY.csv` 记录数据资产；`STRATEGY_LIBRARY.csv` 记录历史策略身份；`HISTORICAL_RESULTS_INDEX.csv` 只索引旧结果；`DATA_EXPOSURE_REGISTER.csv` 记录保护区风险。

状态 `MISSING` 表示本地没有找到可核实材料；`NOT_OPENED` 表示为遵守边界没有读入内容；`UNVERIFIED` 表示存在文件但尚未完成口径验证。
