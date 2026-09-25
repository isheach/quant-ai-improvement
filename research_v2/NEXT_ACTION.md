# 下一步

1. 审阅 `reports/P3_APPROVAL_PACKAGE.md` 与 `protocol/APPROVAL.json`。
2. 如果批准，先执行受限数据验证，确认 XAUUSDm M30 在 2018-01-01 至 2024-05-31 的有效覆盖、时间语义、合约规格、点差/佣金/swap 来源和 500 USD 最小手可行性。
3. 数据验证通过后生成最终批准版 `EXPERIMENT_PLAN.jsonl`，统计真实 run 数量，再进入 P4。
4. 恢复时先运行：`python research_v2/tools/research_workflow.py status` 和 `verify`。

当前不启动任何正式策略回测。
