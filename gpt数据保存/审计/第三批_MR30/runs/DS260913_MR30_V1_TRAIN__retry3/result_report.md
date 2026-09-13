# MR30 V1 TRAIN 运行报告（独立复核）

运行标签：`DS260913_MR30_V1_TRAIN`  
实际有效尝试：`__retry3`（前两次仅为工程失败，均保留在同级目录）  
时间段：2018-02-09～2024-05-31  
品种：`BTCUSDm` · M1 驱动 / M30 信号 · `Model=2` · 入金 500 USD · 杠杆 1:200  
运行时间：2026-09-13 14:13:04～14:14:12（Asia/Shanghai）

## 结论

执行与审计链 **通过**；策略表现触发预注册停止条件，V1 关闭：

- MT5 Total Net Profit：**-392.47 USD**
- 审计净额：**-392.47 USD**（差 0.00）
- Profit Factor：**0.83**
- 官方 Equity Drawdown Relative：**78.86%**（超过 40% 失败线）
- Total Trades：1,714；Total Deals：3,428
- History Quality：98%
- 去前 10 笔最大盈利后：**-443.35 USD**（不是尾单造成的假阳性）

按 MR30 预注册 §4/§5，训练段净利≤0、PF≤1 和 DD>40% 任一项都要求关闭该变体。因此不再运行 `MR30_V1_VALID`，也不把 V1 作为候选策略。

## 独立审计检查

| 检查 | 结果 |
|---|---:|
| 报告有有效 Bars/Ticks/Deposit | PASS（3,302,578 / 13,210,209 / 500） |
| 报告净利 = 审计净利 | PASS |
| Total Trades = HTML closing rows = 审计 rows | PASS（1,714） |
| Total Deals = HTML in + out | PASS（3,428 = 1,714 + 1,714） |
| profit + swap + commission = net | PASS |
| OrderCalcProfit 对账 | PASS（1,714/1,714） |
| 独立合约公式 | PASS，最大差 0.0097 USD |
| deal ticket 唯一 | PASS（1,714/1,714） |
| 关键字段非空 | PASS |
| selfcheck audit_failed / signal_write_failed | PASS（0 / 0） |

退出构成：TP 808、SL 658、时间退出 248。  
方向：多 854、空 860。  
审计成本：profit -264.57、swap -127.90、commission 0.00；swap 是实际净损失的一部分，未被隐藏。

## 证据哈希

| 文件 | SHA-256 |
|---|---|
| `dsh_MR30.mq5` | `3B1331CCB208D2D57D97C1FD0C327F5F3153310C13B519E6817B6877C7ADC09E` |
| `dsh_MR30.ex5` | `D5CCD721B968102A6C4FF2F06A21A81A7178AC53D20BC22567A1D240CE4FE112` |
| `report.htm` | `D9EA79B58983C6F8E7BB0E777F4BFF20041D94FE45AA98B28074AB3CC3D247C2` |
| `trades.csv` | `514377836704E61EE9A0BFDEBEF53B53BE1E7FCBBF0106D25396456225C06056` |
| `signals.csv` | `14A010B407F25723C776A8EACB55FDCDC27C9D2894D73EAB56334CCECDC4C397` |
| `audit_selfcheck.csv` | `2833A137FC181D59DEB0BE5E195ED98607090D5D26619ACCFFB63D7E4E4FE0A5` |

详细机器可读结果：`reconciliation.json`；运行器元数据：`runner_meta.json`。
