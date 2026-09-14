# JSB30 · N1.5 最小工程 smoke 报告

- 时间：2026-09-14 11:57:05
- tag：`DS260914_JSB30_SMOKE_V1`
- 窗口：`2014.01.14 ~ 2014.02.14`（TRAIN 内短片段）
- 口径：`USDJPYm` / 500 USD / Model=2 / ticks=0
- EA：源码 `E3E80B296AC82B560C56C949D3DC3E3F…` / EX5 `7559C19F1FB87ED62C23EDBB30D7840A…`

**★本轮只验证工程链；不使用 smoke 盈利做任何参数/时段调整（GPT §5）。**

| # | 检查项 | 结果 | 明细 |
|---|---|---|---|
| 1 | EA 加载（报告存在） | PASS | report_DS260914_JSB30_SMOKE_V1.htm |
| 2 | Bars > 0（非 environment_error） | **FAIL** | Bars= |
| 3 | Ticks > 0 | **FAIL** | Ticks=None |
| 4 | Initial Deposit = 500 | **FAIL** | dep=None |
| 5 | Symbol = USDJPYm | **FAIL** |  |
| 6 | round-trip 自测执行 | PASS | 7 行 SELFTEST |
| 7 | round-trip 全通过 | PASS | 6/6 |
| 8 | offset 推导无失败 | PASS | offsetFail=0 |
| 9 | trades.csv header 唯一且列匹配 | PASS | 21 列 |
| 10 | reject_audit.csv header 唯一且列匹配 | PASS | 15 列 |
| 11 | trades.csv 已写出 | PASS | 231 B |
| 12 | audit_selfcheck.csv 已写出 | PASS | 300 B |
| 13 | trades 行数 > 0 | **FAIL** | 0 笔 |
| 14 | 每个 UTC 日 <= 1 笔 | PASS | 违反: 无 |
| 15 | hard-flat（出场 UTC < 20:00） | PASS | 越界 0 笔 |
| 16 | profit+swap+commission = net | PASS | 不一致: 无 |
| 17 | deal_ticket 唯一 | PASS | 0/0 |
| 18 | position/schema 字段齐备 | PASS | 缺: 无 |
| 19 | 审计净利 == 报告净利 | PASS | 审计 0.00 / 报告 0.00 / 差 0.00 / 容差 0.020 |
| 20 | 结束时无活动仓位 | PASS | active=0 |
| 21 | offset_undetermined = 0 | PASS | val=0 |
| 22 | audit_failed = 0 | PASS | val=0 |

```
N1.5: 17/22 → FAIL
```

## 原始报告数值（仅供工程核对，不作为收益结论）

| 字段 | 值 |
|---|---|
| Bars |  |
| Ticks |  |
| Initial Deposit |  |
| Total Trades |  |
| Total Deals |  |
| Total Net Profit |  |
| Profit Factor |  |
| Equity Drawdown Relative |  |
| History Quality |  |

## SELFTEST 原始输出（UTC/DST round-trip）

```
RE	0	11:56:57.640	Core 01	2014.05.12 00:00:00   [DS260914_JSB30_SMOKE_V1] SELFTEST winter         in_off=2 -> out_off=2 roundtrip=OK ()
PR	0	11:56:57.640	Core 01	2014.05.12 00:00:00   [DS260914_JSB30_SMOKE_V1] SELFTEST winter         in_off=3 -> out_off=3 roundtrip=OK ()
LS	0	11:56:57.640	Core 01	2014.05.12 00:00:00   [DS260914_JSB30_SMOKE_V1] SELFTEST summer         in_off=2 -> out_off=2 roundtrip=OK ()
NP	0	11:56:57.640	Core 01	2014.05.12 00:00:00   [DS260914_JSB30_SMOKE_V1] SELFTEST summer         in_off=3 -> out_off=3 roundtrip=OK ()
HL	0	11:56:57.640	Core 01	2014.05.12 00:00:00   [DS260914_JSB30_SMOKE_V1] SELFTEST dst-transition in_off=2 -> out_off=2 roundtrip=OK ()
JS	0	11:56:57.640	Core 01	2014.05.12 00:00:00   [DS260914_JSB30_SMOKE_V1] SELFTEST dst-transition in_off=3 -> out_off=3 roundtrip=OK ()
ND	0	11:56:57.640	Core 01	2014.05.12 00:00:00   [DS260914_JSB30_SMOKE_V1] SELFTEST 汇总：6/6 通过
```

