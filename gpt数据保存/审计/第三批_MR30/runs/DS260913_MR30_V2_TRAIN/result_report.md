# MR30 V2 TRAIN 运行报告（独立复核）

运行标签：`DS260913_MR30_V2_TRAIN`  
时间段：2018-02-09～2024-05-31  
品种：`BTCUSDm` · M1 驱动 / M30 信号 · `Model=2` · 入金 500 USD · 杠杆 1:200  
运行时间：2026-09-13 17:51:18～17:52:03（Asia/Shanghai）

## 结论

执行与审计链 **通过**；策略表现触发预注册停止条件，V2 关闭：

- MT5 Total Net Profit：**-394.71 USD**
- 审计净额：**-394.71 USD**（差 0.00）
- Profit Factor：**0.83**
- 官方 Equity Drawdown Relative：**79.80%**（超过 40% 失败线）
- Total Trades：1,640；Total Deals：3,280
- History Quality：98%
- 去前 10 笔最大盈利后：**-472.47 USD**

V2 同时满足净利≤0、PF≤1、DD>40% 三项停止条件。因此不运行 `MR30_V2_VALID`，也不把 V2 作为候选策略。

## 独立审计检查

| 检查 | 结果 |
|---|---:|
| 报告有有效 Bars/Ticks/Deposit | PASS（3,302,578 / 13,210,209 / 500） |
| 报告净利 = 审计净利 | PASS |
| Total Trades = HTML closing rows = 审计 rows | PASS（1,640） |
| Total Deals = HTML in + out | PASS（3,280 = 1,640 + 1,640） |
| profit + swap + commission = net | PASS |
| OrderCalcProfit 对账 | PASS（1,640/1,640） |
| 独立合约公式 | PASS，最大差 0.0098 USD |
| deal ticket 唯一 | PASS（1,640/1,640） |
| 关键字段非空 | PASS |
| selfcheck audit_failed / signal_write_failed | PASS（0 / 0） |

退出构成：TP 465、SL 703、时间退出 472。  
方向：多 816、空 824。  
审计成本：profit -246.55、swap -148.16、commission 0.00。

## 证据哈希

| 文件 | SHA-256 |
|---|---|
| `dsh_MR30.mq5` | `3B1331CCB208D2D57D97C1FD0C327F5F3153310C13B519E6817B6877C7ADC09E` |
| `dsh_MR30.ex5` | `D5CCD721B968102A6C4FF2F06A21A81A7178AC53D20BC22567A1D240CE4FE112` |
| `report.htm` | `F384BFCD97066044C96370B46B64F3830F75D36CE6CD51E29B36FF4DFC66C4B4` |
| `trades.csv` | `86370136D4B441E30CFF3AE8F125FA049DBC6B1AE68FF7A4C7AE8F2A9212A4B1` |
| `signals.csv` | `144DA2AF5EB22A9F0DFDBB96DF3EF4F1C3A67201C92B095BD3C6E275E7493AF5` |
| `audit_selfcheck.csv` | `955012765A475044169F2F59860D8F8C16B412C1755910167B0EF3FA50B27A7B` |

机器可读结果：`reconciliation.json`；运行器元数据：`runner_meta.json`。
