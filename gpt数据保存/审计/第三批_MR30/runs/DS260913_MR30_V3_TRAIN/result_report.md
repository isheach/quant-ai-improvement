# MR30 V3 TRAIN 运行报告（独立复核）

运行标签：`DS260913_MR30_V3_TRAIN`  
时间段：2018-02-09～2024-05-31  
品种：`BTCUSDm` · M1 驱动 / M30 信号 · `Model=2` · 入金 500 USD · 杠杆 1:200  
运行时间：2026-09-13 17:52:49～17:53:36（Asia/Shanghai）

## 结论

执行与审计链 **通过**；策略表现触发预注册停止条件，V3 关闭：

- MT5 Total Net Profit：**-319.21 USD**
- 审计净额：**-319.21 USD**（差 0.00）
- Profit Factor：**0.87**
- 官方 Equity Drawdown Relative：**65.72%**（超过 40% 失败线）
- Total Trades：1,264；Total Deals：2,528
- History Quality：98%
- 去前 10 笔最大盈利后：**-375.83 USD**
- 波动过滤阻断信号：1,963；实际拒单 741

V3 同时满足净利≤0、PF≤1、DD>40% 三项停止条件。因此不运行 `MR30_V3_VALID`，也不把 V3 作为候选策略。

## 独立审计检查

| 检查 | 结果 |
|---|---:|
| 报告有有效 Bars/Ticks/Deposit | PASS（3,302,578 / 13,210,209 / 500） |
| 报告净利 = 审计净利 | PASS |
| Total Trades = HTML closing rows = 审计 rows | PASS（1,264） |
| Total Deals = HTML in + out | PASS（2,528 = 1,264 + 1,264） |
| profit + swap + commission = net | PASS |
| OrderCalcProfit 对账 | PASS（1,264/1,264） |
| 独立合约公式 | PASS，最大差 0.0096 USD |
| deal ticket 唯一 | PASS（1,264/1,264） |
| 关键字段非空 | PASS |
| selfcheck audit_failed / signal_write_failed | PASS（0 / 0） |

退出构成：TP 620、SL 512、时间退出 132。  
方向：多 623、空 641。  
审计成本：profit -209.04、swap -110.17、commission 0.00。

## 证据哈希

| 文件 | SHA-256 |
|---|---|
| `dsh_MR30.mq5` | `3B1331CCB208D2D57D97C1FD0C327F5F3153310C13B519E6817B6877C7ADC09E` |
| `dsh_MR30.ex5` | `D5CCD721B968102A6C4FF2F06A21A81A7178AC53D20BC22567A1D240CE4FE112` |
| `report.htm` | `D905F923C65F50A6F82AFB7629166EEF328D4A76D1E1E5249D71A71090C3DCFC` |
| `trades.csv` | `458033A65CBB954CA03CC7E05D54F7584FC3C2F8AE6A86401BA1463AA5BB40B8` |
| `signals.csv` | `99A9BE109D4EEFDC334623BA60CD08F447E4427C299E22B26CC6498BC810817F` |
| `audit_selfcheck.csv` | `C9E32623FB8AFFBE93593733E9656E0A3E22E11EC48D336914AE93FABC3E6E5C` |

机器可读结果：`reconciliation.json`；运行器元数据：`runner_meta.json`。
