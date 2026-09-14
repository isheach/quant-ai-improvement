# XAMR30 · N1.5 engineering smoke 报告

- 时间：2026-09-14 15:26:04
- 窗口：WINTER 2023-01-02~01-31 · DSTTR 2023-03-20~04-07 · SUMMER 2023-07-03~07-31
- 只用 V1；**profit/PF 不参与任何策略判断**
- ★本报告验证的是 N1R 两处修复（pending 状态机 / 12-bar off-by-one）

| 窗口 | tag | Bars | Trades | 拒单 | 判定 |
|---|---|---:|---:|---:|---|
| WINTER | `DS260914_XAMR30_SMOKE_WINTER` | 29797 | 12 | 115 | 23/23 PASS |
| DSTTR | `DS260914_XAMR30_SMOKE_DSTTR` | 19862 | 10 | 73 | 23/23 PASS |
| SUMMER | `DS260914_XAMR30_SMOKE_SUMMER` | 28695 | 15 | 98 | 22/23 **FAIL** |

## 逐项

### WINTER

| 检查项 | 结果 | 明细 |
|---|---|---|
| Bars>0 | PASS | Bars=29797 |
| Deposit=500 | PASS | 500.00 |
| Symbol=USDJPYm | PASS | USDJPYm |
| HTML trades == 审计行数 | PASS | HTML=12 审计=12 |
| 实际产生 closing deals | PASS | 12 笔 |
| fatal=0 | PASS | 0 |
| audit_failed=0 | PASS | 0 |
| active_positions=0 | PASS | 0 |
| 入场时序: entry_bar = signal_bar+30min | PASS | 抽查 12 笔，违规 无 |
| 入场时序: entry_time >= signal_close | PASS | 违规 无 |
| 时序抽查（本窗口） | PASS | 12 笔 |
| 每 UTC day <= 1 笔 | PASS | 违反 无 |
| 持有 M30 bar 数 <= 12 | PASS | 最大 12 根（各窗口分别报告） |
| unique_deal_ticket_rows == audit_rows | PASS | 12/12 |
| duplicate_written_rows == 0 | PASS | 重复写入 0 行 |
| duplicate_attempts_blocked（仅 diagnostic） | PASS | dup_hits=12（= 被 seen-table 拦截的重复发现次数，非重复写入） |
| 所有成交 alignment_exact=1 | PASS | 异常 0 笔 |
| cross_asset_missing_bar 有记录 | PASS | 14 条拒单 |
| DEAL_PROFIT↔OCP<=0.05 | PASS | 超容差 无 |
| spread / SL / TP 字段齐备 | PASS | ★JSB30 缺口已解决 |
| median spread/SL <= 30% | PASS | median=0.0449 |
| median spread/TP <= 30% | PASS | median=0.0562 |
| HTML净利 == 审计净利 | PASS | audit -3.76 / html -3.76 |

### DSTTR

| 检查项 | 结果 | 明细 |
|---|---|---|
| Bars>0 | PASS | Bars=19862 |
| Deposit=500 | PASS | 500.00 |
| Symbol=USDJPYm | PASS | USDJPYm |
| HTML trades == 审计行数 | PASS | HTML=10 审计=10 |
| 实际产生 closing deals | PASS | 10 笔 |
| fatal=0 | PASS | 0 |
| audit_failed=0 | PASS | 0 |
| active_positions=0 | PASS | 0 |
| 入场时序: entry_bar = signal_bar+30min | PASS | 抽查 10 笔，违规 无 |
| 入场时序: entry_time >= signal_close | PASS | 违规 无 |
| 时序抽查（本窗口） | PASS | 10 笔 |
| 每 UTC day <= 1 笔 | PASS | 违反 无 |
| 持有 M30 bar 数 <= 12 | PASS | 最大 6 根（各窗口分别报告） |
| unique_deal_ticket_rows == audit_rows | PASS | 10/10 |
| duplicate_written_rows == 0 | PASS | 重复写入 0 行 |
| duplicate_attempts_blocked（仅 diagnostic） | PASS | dup_hits=10（= 被 seen-table 拦截的重复发现次数，非重复写入） |
| 所有成交 alignment_exact=1 | PASS | 异常 0 笔 |
| cross_asset_missing_bar 有记录 | PASS | 0 条拒单 |
| DEAL_PROFIT↔OCP<=0.05 | PASS | 超容差 无 |
| spread / SL / TP 字段齐备 | PASS | ★JSB30 缺口已解决 |
| median spread/SL <= 30% | PASS | median=0.0417 |
| median spread/TP <= 30% | PASS | median=0.0521 |
| HTML净利 == 审计净利 | PASS | audit -21.26 / html -21.26 |

### SUMMER

| 检查项 | 结果 | 明细 |
|---|---|---|
| Bars>0 | PASS | Bars=28695 |
| Deposit=500 | PASS | 500.00 |
| Symbol=USDJPYm | PASS | USDJPYm |
| HTML trades == 审计行数 | PASS | HTML=15 审计=15 |
| 实际产生 closing deals | PASS | 15 笔 |
| fatal=0 | PASS | 0 |
| audit_failed=0 | PASS | 0 |
| active_positions=0 | PASS | 0 |
| 入场时序: entry_bar = signal_bar+30min | PASS | 抽查 15 笔，违规 无 |
| 入场时序: entry_time >= signal_close | PASS | 违规 无 |
| 时序抽查（本窗口） | PASS | 15 笔 |
| 每 UTC day <= 1 笔 | PASS | 违反 无 |
| 持有 M30 bar 数 <= 12 | **FAIL** | 最大 16 根（各窗口分别报告） |
| unique_deal_ticket_rows == audit_rows | PASS | 15/15 |
| duplicate_written_rows == 0 | PASS | 重复写入 0 行 |
| duplicate_attempts_blocked（仅 diagnostic） | PASS | dup_hits=15（= 被 seen-table 拦截的重复发现次数，非重复写入） |
| 所有成交 alignment_exact=1 | PASS | 异常 0 笔 |
| cross_asset_missing_bar 有记录 | PASS | 1 条拒单 |
| DEAL_PROFIT↔OCP<=0.05 | PASS | 超容差 无 |
| spread / SL / TP 字段齐备 | PASS | ★JSB30 缺口已解决 |
| median spread/SL <= 30% | PASS | median=0.0777 |
| median spread/TP <= 30% | PASS | median=0.0972 |
| HTML净利 == 审计净利 | PASS | audit -25.26 / html -25.26 |

```
N1.5: 68/69 通过；实际成交合计 37 笔
```

