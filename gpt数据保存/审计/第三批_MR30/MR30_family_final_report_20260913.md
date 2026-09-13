# MR30 family 阶段结论

更新时间：2026-09-13 17:56（Asia/Shanghai）  
状态：**`closed / blocked_failed`（执行链通过，策略家族未通过）**

## 1. 一页结论

新 family `MR30` 在真实 `BTCUSDm`、500 USD、Model=2 的训练段上，三个预注册变体全部失败。每个有效运行的 MT5 报告、审计 CSV、OrderCalcProfit、独立合约公式和成本分解均一致，因此这是策略表现失败，不是审计映射失败。

按预注册规则，训练段一旦出现净利≤0、PF≤1 或官方权益 DD>40%，该变体立即关闭，验证段不再运行。故 `V1/V2/V3_VALID` 均明确记为 `not_run_skipped`，不是缺失结果。

| 变体 | 唯一差异 | 净利 USD | PF | 官方权益 DD | 交易数 | 去前十盈利单后 | 裁定 |
|---|---|---:|---:|---:|---:|---:|---|
| V1 TRAIN | TP 1.5×ATR | -392.47 | 0.83 | 78.86% | 1,714 | -443.35 | 关闭 |
| V2 TRAIN | TP 2.5×ATR | -394.71 | 0.83 | 79.80% | 1,640 | -472.47 | 关闭 |
| V3 TRAIN | TP 1.5×ATR + ATR P20–P80 | -319.21 | 0.87 | 65.72% | 1,264 | -375.83 | 关闭 |

三者均远超 `>40%` 失败线，不能作为 500 USD 账户候选，也不能通过提高风险去追求 50%/100% 年收益目标。

## 2. 固定实验口径

- 品种：真实券商品种 `BTCUSDm`（Exness-MT5Trial5）
- 账户：500 USD、USD、杠杆 1:200、hedging
- 测试器：M1 驱动，`Model=2`，内部只用已完成 M1 聚合的 M30 bar
- 训练段：2018-02-09～2024-05-31
- 未使用：2025-06-01～2026-05-31 exposed OOS；2026-06-01～2026-09-30 用户留白
- 风险：1.5%，最小手超配关闭；无网格、无马丁、无移动盈利止损

## 3. 执行链复核

三个有效 run 的独立检查均为 PASS：

- 报告有有效 Bars/Ticks/Deposit（3,302,578 / 13,210,209 / 500）
- `Total Trades = HTML closing rows = 审计 rows`
- `Total Deals = HTML opening rows + HTML closing rows`
- 报告净利与审计净额差 0.00
- `profit + swap + commission = net`
- 每笔 OrderCalcProfit 与报告 profit 一致
- 独立合约公式最大误差 < 0.01 USD
- deal ticket 唯一、关键字段非空、selfcheck 无失败

V1/V2/V3 的具体复核分别见各 run 目录的 `result_report.md` 和 `reconciliation.json`。

## 4. 过程中的工程问题及处置

V1 的前两次尝试没有执行行情：

1. portable tester 拒绝 `FILE_COMMON`，EA 在 `OnInit` 退出；标记为 `invalid`，原目录保留。
2. 修复路径后发现 MQL5 `FileWrite()` 返回的是字节数，不是列数；旧检查误判写入成功；再次标记为 `invalid`，原目录保留。

随后修正为：优先 common 文件空间，失败时回退 worker 沙盒；所有 `FileWrite` 以 `0` 为失败哨兵。修复后的源码/EX5 重新编译为 0 errors / 0 warnings，并用于三个有效 run。上述工程修复发生在有效运行之前，三个变体共享同一封存二进制。

## 5. 证据索引

- 预注册：`deepseek数据保存\执行_第三批\stage3_family_preregistration\family_preregistration.md`
- planned manifest：`gpt数据保存\审计\第三批_MR30\mr30_planned_manifest.jsonl`
- 静态闸门：`gpt数据保存\审计\第三批_MR30\mr30_static_gate_report_20260913.md`
- 机器结果：`gpt数据保存\审计\第三批_MR30\mr30_results.jsonl`
- V1：`runs\DS260913_MR30_V1_TRAIN__retry3\result_report.md`
- V2：`runs\DS260913_MR30_V2_TRAIN\result_report.md`
- V3：`runs\DS260913_MR30_V3_TRAIN\result_report.md`

封存源码 SHA-256：`3B1331CCB208D2D57D97C1FD0C327F5F3153310C13B519E6817B6877C7ADC09E`  
封存 EX5 SHA-256：`D5CCD721B968102A6C4FF2F06A21A81A7178AC53D20BC22567A1D240CE4FE112`

## 6. 后续研究建议

不要重开 MR30、不要为它扫描更多 TP/SL/周期参数。当前证据说明：在这套 BTC M30 逆势结构和 500 USD 最小手约束下，固定收益上限与波动过滤都没有消除负 edge 与高回撤。

下一阶段若继续，应新建并预注册一个结构不同、交易频率更低且能显式处理最小手地板的 family；先做短段执行/成本夹具，再只跑训练段，仍然保留验证段和用户留白。新 family 未完成 provenance、编译、静态闸门前，不启动 MT5。
