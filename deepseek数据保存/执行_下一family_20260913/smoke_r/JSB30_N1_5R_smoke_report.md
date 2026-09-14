# JSB30 · N1.5R 真实历史工程 smoke 报告

- 时间：2026-09-14 12:47:20
- 依据：GPT 裁定 `N1.5R`（不再用 2014 的 0-data 窗口）
- EA 源码：`D:\desktop\新量化策略\deepseek数据保存\mql5\dshtools\dsh_JSB30.mq5`
- dataset_role：**engineering_smoke**（★不混入正式 TRAIN 统计）
- 参数：三组全部使用 **V1 正式冻结参数**
- **★smoke 的盈利/PF/胜率不用于任何策略判断或参数修改（GPT §N1.5R）**

## 1. 三组窗口与结果

| 组 | tag | 窗口 | Bars | Ticks | Trades | 净利(仅记录) | DD | 判定 |
|---|---|---|---:|---:|---:|---:|---:|---|
| WINTER | `DS260914_JSB30_SMOKE_WINTER` | 2023.01.02 ~ 2023.01.31 | 29797 | 117158 | 13 | 10.74 | 6.58% (33.15) | 23/23 PASS |
| DSTTR | `DS260914_JSB30_SMOKE_DSTTR` | 2023.03.20 ~ 2023.04.07 | 19862 | 78165 | 12 | -6.51 | 6.79% (34.70) | 23/23 PASS |
| SUMMER | `DS260914_JSB30_SMOKE_SUMMER` | 2023.07.03 ~ 2023.07.31 | 28695 | 112995 | 17 | -18.70 | 9.00% (45.21) | 23/23 PASS |

## 2. 逐项检查

### WINTER（`DS260914_JSB30_SMOKE_WINTER`）

| 检查项 | 结果 | 明细 |
|---|---|---|
| Bars > 0 | PASS | Bars=29797 Ticks=117158 |
| Deposit = 500 | PASS | 500.00 |
| Symbol = USDJPYm | PASS | USDJPYm |
| HTML Total Trades == 审计行数 | PASS | HTML=13 审计=13 |
| REALWEEK 有样本 | PASS | (30, 30, 0) |
| REALWEEK 全通过 | PASS | (30, 30, 0) |
| UNIT 三组日期全通过 | PASS | UNIT 汇总：6/6 通过 |
| offsetFail=0 | PASS | offsetFail=0 |
| 真实周 offset ∈ {2,3} | PASS | 观察到 ['2'] |
| trades header 唯一+列匹配 | PASS | 26 列 |
| reject header 唯一+列匹配 | PASS | ok |
| trades 行数 > 0 | PASS | 13 笔 |
| 每 UTC 日 <= 1 笔 | PASS | 违反 无 |
| 无 UTC20 后持仓 | PASS | 越界 0 |
| profit+swap+comm = net | PASS | 不一致 无 |
| ticket 无重复 | PASS | 13/13 |
| OCP 与独立公式可对账 | PASS | 超容差 无 |
| HTML 与 audit 净利可对账 | PASS | audit 10.74 / html 10.74 / 差 0.00 |
| 字段齐备(entry_time_utc 等) | PASS | ok |
| 结束无活动仓位 | PASS | active=0 |
| audit_failed=0 | PASS | val=0 |
| offset_undetermined=0 | PASS | val=0 |
| ocp_mismatch=0 | PASS | val=0 |

```
UNIT   : PO	0	12:46:42.489	Core 01	2023.01.02 00:00:00   [DS260914_JSB30_SMOKE_WINTER] UNIT 汇总：6/6 通过
REALWEEK: NN	0	12:46:42.489	Core 01	2023.01.02 00:00:00   [DS260914_JSB30_SMOKE_WINTER] REALWEEK 汇总：checked=30 OK=30 FAIL=0
观察到的 offset: +2
```

### DSTTR（`DS260914_JSB30_SMOKE_DSTTR`）

| 检查项 | 结果 | 明细 |
|---|---|---|
| Bars > 0 | PASS | Bars=19862 Ticks=78165 |
| Deposit = 500 | PASS | 500.00 |
| Symbol = USDJPYm | PASS | USDJPYm |
| HTML Total Trades == 审计行数 | PASS | HTML=12 审计=12 |
| REALWEEK 有样本 | PASS | (30, 30, 0) |
| REALWEEK 全通过 | PASS | (30, 30, 0) |
| UNIT 三组日期全通过 | PASS | UNIT 汇总：6/6 通过 |
| offsetFail=0 | PASS | offsetFail=0 |
| 真实周 offset ∈ {2,3} | PASS | 观察到 ['2'] |
| trades header 唯一+列匹配 | PASS | 26 列 |
| reject header 唯一+列匹配 | PASS | ok |
| trades 行数 > 0 | PASS | 12 笔 |
| 每 UTC 日 <= 1 笔 | PASS | 违反 无 |
| 无 UTC20 后持仓 | PASS | 越界 0 |
| profit+swap+comm = net | PASS | 不一致 无 |
| ticket 无重复 | PASS | 12/12 |
| OCP 与独立公式可对账 | PASS | 超容差 无 |
| HTML 与 audit 净利可对账 | PASS | audit -6.51 / html -6.51 / 差 0.00 |
| 字段齐备(entry_time_utc 等) | PASS | ok |
| 结束无活动仓位 | PASS | active=0 |
| audit_failed=0 | PASS | val=0 |
| offset_undetermined=0 | PASS | val=0 |
| ocp_mismatch=0 | PASS | val=0 |

```
UNIT   : NP	0	12:46:57.881	Core 01	2023.03.20 00:00:00   [DS260914_JSB30_SMOKE_DSTTR] UNIT 汇总：6/6 通过
REALWEEK: RL	0	12:46:57.881	Core 01	2023.03.20 00:00:00   [DS260914_JSB30_SMOKE_DSTTR] REALWEEK 汇总：checked=30 OK=30 FAIL=0
观察到的 offset: +2
```

### SUMMER（`DS260914_JSB30_SMOKE_SUMMER`）

| 检查项 | 结果 | 明细 |
|---|---|---|
| Bars > 0 | PASS | Bars=28695 Ticks=112995 |
| Deposit = 500 | PASS | 500.00 |
| Symbol = USDJPYm | PASS | USDJPYm |
| HTML Total Trades == 审计行数 | PASS | HTML=17 审计=17 |
| REALWEEK 有样本 | PASS | (30, 30, 0) |
| REALWEEK 全通过 | PASS | (30, 30, 0) |
| UNIT 三组日期全通过 | PASS | UNIT 汇总：6/6 通过 |
| offsetFail=0 | PASS | offsetFail=0 |
| 真实周 offset ∈ {2,3} | PASS | 观察到 ['2'] |
| trades header 唯一+列匹配 | PASS | 26 列 |
| reject header 唯一+列匹配 | PASS | ok |
| trades 行数 > 0 | PASS | 17 笔 |
| 每 UTC 日 <= 1 笔 | PASS | 违反 无 |
| 无 UTC20 后持仓 | PASS | 越界 0 |
| profit+swap+comm = net | PASS | 不一致 无 |
| ticket 无重复 | PASS | 17/17 |
| OCP 与独立公式可对账 | PASS | 超容差 无 |
| HTML 与 audit 净利可对账 | PASS | audit -18.70 / html -18.70 / 差 -0.00 |
| 字段齐备(entry_time_utc 等) | PASS | ok |
| 结束无活动仓位 | PASS | active=0 |
| audit_failed=0 | PASS | val=0 |
| offset_undetermined=0 | PASS | val=0 |
| ocp_mismatch=0 | PASS | val=0 |

```
UNIT   : IQ	0	12:47:12.463	Core 01	2023.07.03 00:00:00   [DS260914_JSB30_SMOKE_SUMMER] UNIT 汇总：6/6 通过
REALWEEK: CG	0	12:47:12.463	Core 01	2023.07.03 00:00:00   [DS260914_JSB30_SMOKE_SUMMER] REALWEEK 汇总：checked=30 OK=30 FAIL=0
观察到的 offset: +2
```

## 3. 汇总

```
总计: 69/69 检查通过
三组实际 closing deal 合计: 42 笔
★若合计为 0，则按 GPT 要求【不能宣布审计交易链 PASS】，
  只能继续用预先定义的工程 probe/unit test 验证写入链。
```

