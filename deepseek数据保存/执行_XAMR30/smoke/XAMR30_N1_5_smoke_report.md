# XAMR30 · N1.5 engineering smoke 报告

- 时间：2026-09-14 15:02:16
- 窗口：WINTER 2023-01-02~01-31 · DSTTR 2023-03-20~04-07 · SUMMER 2023-07-03~07-31
- 只用 V1；**profit/PF 不参与任何策略判断**
- ★本报告验证的是 N1R 两处修复（pending 状态机 / 12-bar off-by-one）

| 窗口 | tag | Bars | Trades | 拒单 | 判定 |
|---|---|---:|---:|---:|---|
| WINTER | `DS260914_XAMR30_SMOKE_WINTER` | 29797 | 14 | 89 | 20/20 PASS |
| DSTTR | `DS260914_XAMR30_SMOKE_DSTTR` | 19862 | 10 | 72 | 20/20 PASS |
| SUMMER | `DS260914_XAMR30_SMOKE_SUMMER` | 28695 | 16 | 88 | 20/20 PASS |

## 逐项

### WINTER

| 检查项 | 结果 | 明细 |
|---|---|---|
| Bars>0 | PASS | Bars=29797 |
| Deposit=500 | PASS | 500.00 |
| Symbol=USDJPYm | PASS | USDJPYm |
| HTML trades == 审计行数 | PASS | HTML=14 审计=14 |
| 实际产生 closing deals | PASS | 14 笔 |
| fatal=0 | PASS | 0 |
| audit_failed=0 | PASS | 0 |
| active_positions=0 | PASS | 0 |
| 入场时序: entry_bar = signal_bar+30min | PASS | 抽查 14 笔，违规 无 |
| 入场时序: entry_time >= signal_close | PASS | 违规 无 |
| 时序抽查（本窗口） | PASS | 14 笔 |
| 每 UTC day <= 1 笔 | PASS | 违反 无 |
| 持有 M30 bar 数 <= 12 | PASS | 最大 12 根 |
| 所有成交 alignment_exact=1 | PASS | 异常 0 笔 |
| cross_asset_missing_bar 有记录 | PASS | 12 条拒单 |
| DEAL_PROFIT↔OCP<=0.05 | PASS | 超容差 无 |
| spread / SL / TP 字段齐备 | PASS | ★JSB30 缺口已解决 |
| median spread/SL <= 30% | PASS | median=0.0445 |
| median spread/TP <= 30% | PASS | median=0.0556 |
| HTML净利 == 审计净利 | PASS | audit 8.12 / html 8.12 |

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
| 持有 M30 bar 数 <= 12 | PASS | 最大 6 根 |
| 所有成交 alignment_exact=1 | PASS | 异常 0 笔 |
| cross_asset_missing_bar 有记录 | PASS | 0 条拒单 |
| DEAL_PROFIT↔OCP<=0.05 | PASS | 超容差 无 |
| spread / SL / TP 字段齐备 | PASS | ★JSB30 缺口已解决 |
| median spread/SL <= 30% | PASS | median=0.0420 |
| median spread/TP <= 30% | PASS | median=0.0525 |
| HTML净利 == 审计净利 | PASS | audit -30.29 / html -30.29 |

### SUMMER

| 检查项 | 结果 | 明细 |
|---|---|---|
| Bars>0 | PASS | Bars=28695 |
| Deposit=500 | PASS | 500.00 |
| Symbol=USDJPYm | PASS | USDJPYm |
| HTML trades == 审计行数 | PASS | HTML=16 审计=16 |
| 实际产生 closing deals | PASS | 16 笔 |
| fatal=0 | PASS | 0 |
| audit_failed=0 | PASS | 0 |
| active_positions=0 | PASS | 0 |
| 入场时序: entry_bar = signal_bar+30min | PASS | 抽查 16 笔，违规 无 |
| 入场时序: entry_time >= signal_close | PASS | 违规 无 |
| 时序抽查（本窗口） | PASS | 16 笔 |
| 每 UTC day <= 1 笔 | PASS | 违反 无 |
| 持有 M30 bar 数 <= 12 | PASS | 最大 10 根 |
| 所有成交 alignment_exact=1 | PASS | 异常 0 笔 |
| cross_asset_missing_bar 有记录 | PASS | 1 条拒单 |
| DEAL_PROFIT↔OCP<=0.05 | PASS | 超容差 无 |
| spread / SL / TP 字段齐备 | PASS | ★JSB30 缺口已解决 |
| median spread/SL <= 30% | PASS | median=0.0777 |
| median spread/TP <= 30% | PASS | median=0.0972 |
| HTML净利 == 审计净利 | PASS | audit 12.09 / html 12.09 |

```
N1.5: 60/60 通过；实际成交合计 40 笔
```

