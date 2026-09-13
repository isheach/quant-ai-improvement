# GPT 复核与后续大纲（精简交接）

更新时间：2026-09-11

## 已核验

- 旧版最新 EA 是 `旧量化策略\36代数据\eva028_STAGE1_PACKAGE_v2\eva028_VolumetricPulseGrid_CoreRiskV1.mq5`，属于“网格 + 趋势 + 多层风控”的混合结构。
- DeepSeek 的关键历史数字可由原始审计 CSV 复算：`b1_baseline +272.60/484笔`、`b1a_pure_grid 0笔`、`b1b_pure_trend +272.60/484笔`、`base_locked +76.56`、`base_locked_valid +242.89`、`v_baseline -44.12`。
- stage1 实际 `.set` 使用 `InpGridZ=20000`、`InpMinGridZ=11500`，且仍可优化；baseline 的 484 笔只有趋势退出/止损，没有网格成交。
- 这些数字大多来自旧自建品种/Model=2，不能当作当前真实品种上线证明。
- `dsh_TrendCore` 仍有三类待修硬问题：手数四舍五入可能超风险、出场原因映射不完整、代码/实验周期不一致；`runexp.py` 默认入金 300 且仍面向旧自建品种口径。
- `98% History Quality` 不能等同于全段真实 tick；已有 `.tkc` 和导出签名表明旧区间主要是合成 tick。

## 下一步唯一权威路线

1. 只用 MT5 真实 `XAUUSDm/BTCUSDm/USDJPYm`，由测试器服务器历史取数。
2. 固定训练/验证/测试，保留 2026-06～09 留白。
3. 每次实验记录唯一 run_id、源码/EX5 哈希、入金、模型、日期、完整参数和报告哈希。
4. 先完成手数、盈亏、审计、组合风险单元测试，再跑单仓趋势/无加仓均值回归基线。
5. 通过三段和成本/回撤稳健性后，才进入 demo；未通过不实盘。

详细证据与唤醒信息见：
`gpt数据保存\GPT_MEMORY.md`、
`gpt数据保存\审计\旧代码与DeepSeek输出复核_2026-09-11.md`、
`gpt数据保存\大纲\后续改进大纲.md`。
