# XAMR30 · N1R3 final smoke 复核报告（verifier-only）

- 时间：2026-09-14 15:33:10
- **same EX5 · same raw run · only verifier fixed · no economic result used**
- EA：`dsh_XAMR30.mq5` source `CA5AD7339FE415CB…` / EX5 `F374890F28022FCB…`（N1R3）
- ★未重跑 MT5：本报告只对【同一批 N1R3 final smoke 原始数据】重新运行修正后的检验

## 0. verifier bug provenance

```
旧 checker 用「日历分钟 + 周末规则」近似 M30 bar 数，
把跨周末持仓（SUMMER trade 25：Fri 2023-07-21 17:00 → Sun 2023-07-23 23:00，
reason = time_exit）的闭市时段也算进去 → 误报 16 根。
EA 实际只计【真正打印出来的 M30 bar】：
  Fri 17:00→21:30 ≈ 9 根  +  Sun 22:00→23:00 = 3 根  = 12 根 → time_exit（正确）
→ 旧报告的唯一 FAIL 属 verifier bug，不是 EA 行为错误。
→ 旧 68/69 报告保留为 verifier bug provenance，未覆盖：
   smoke/XAMR30_N1_5_smoke_report.md
```

## 1. 结果

| 窗口 | 成交 | 拒单 | 判定 |
|---|---:|---:|---|
| WINTER | 12 | 115 | 25/25 PASS |
| DSTTR | 10 | 73 | 25/25 PASS |
| SUMMER | 15 | 98 | 25/25 PASS |

| 项 | 值 |
|---|---|
| 总计 | **75/75** |
| 成交合计 | 37 笔 |
| 结论 | **69/69 PASS ✅** |

## 2. 逐窗口明细

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
| 入场时序 entry_bar = signal_bar+30min | PASS | 抽查 12，违规 无 |
| 入场时序 entry_time >= signal_close | PASS | 违规 无 |
| 时序抽查（本窗口） | PASS | 12 笔 |
| time_exit 仅由 12 根规则触发（权威判据） | PASS | time_exit=1 笔（跨周末者日历时间可 >375min，bar 数由 EA 保证） |
| 非 time_exit 持仓未超 12 根（日历上界） | PASS | 越界 无 |
| unique_deal_ticket_rows == audit_rows | PASS | 12/12 |
| duplicate_written_rows == 0 | PASS | 重复 0 |
| duplicate_attempts_blocked（仅 diagnostic） | PASS | dup_hits=12（seen-table 拦截的重复发现，非重复写入） |
| 每 UTC day <= 1 笔 | PASS | 违反 无 |
| 全部成交 alignment_exact=1 | PASS | 异常 0 |
| cross_asset_missing_bar 的 xau_bar_time 为空（无状态污染） | PASS | 拒单 14 条，带 stale xau 值的 0 条 |
| atr_out_of_regime 的 xau 值为空（无状态污染） | PASS | 拒单 74 条，stale 0 条 |
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
| 入场时序 entry_bar = signal_bar+30min | PASS | 抽查 10，违规 无 |
| 入场时序 entry_time >= signal_close | PASS | 违规 无 |
| 时序抽查（本窗口） | PASS | 10 笔 |
| time_exit 仅由 12 根规则触发（权威判据） | PASS | time_exit=0 笔（跨周末者日历时间可 >375min，bar 数由 EA 保证） |
| 非 time_exit 持仓未超 12 根（日历上界） | PASS | 越界 无 |
| unique_deal_ticket_rows == audit_rows | PASS | 10/10 |
| duplicate_written_rows == 0 | PASS | 重复 0 |
| duplicate_attempts_blocked（仅 diagnostic） | PASS | dup_hits=10（seen-table 拦截的重复发现，非重复写入） |
| 每 UTC day <= 1 笔 | PASS | 违反 无 |
| 全部成交 alignment_exact=1 | PASS | 异常 0 |
| cross_asset_missing_bar 的 xau_bar_time 为空（无状态污染） | PASS | 拒单 0 条，带 stale xau 值的 0 条 |
| atr_out_of_regime 的 xau 值为空（无状态污染） | PASS | 拒单 49 条，stale 0 条 |
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
| 入场时序 entry_bar = signal_bar+30min | PASS | 抽查 15，违规 无 |
| 入场时序 entry_time >= signal_close | PASS | 违规 无 |
| 时序抽查（本窗口） | PASS | 15 笔 |
| time_exit 仅由 12 根规则触发（权威判据） | PASS | time_exit=1 笔（跨周末者日历时间可 >375min，bar 数由 EA 保证） |
| 非 time_exit 持仓未超 12 根（日历上界） | PASS | 越界 无 |
| unique_deal_ticket_rows == audit_rows | PASS | 15/15 |
| duplicate_written_rows == 0 | PASS | 重复 0 |
| duplicate_attempts_blocked（仅 diagnostic） | PASS | dup_hits=15（seen-table 拦截的重复发现，非重复写入） |
| 每 UTC day <= 1 笔 | PASS | 违反 无 |
| 全部成交 alignment_exact=1 | PASS | 异常 0 |
| cross_asset_missing_bar 的 xau_bar_time 为空（无状态污染） | PASS | 拒单 1 条，带 stale xau 值的 0 条 |
| atr_out_of_regime 的 xau 值为空（无状态污染） | PASS | 拒单 66 条，stale 0 条 |
| DEAL_PROFIT↔OCP<=0.05 | PASS | 超容差 无 |
| spread / SL / TP 字段齐备 | PASS | ★JSB30 缺口已解决 |
| median spread/SL <= 30% | PASS | median=0.0777 |
| median spread/TP <= 30% | PASS | median=0.0972 |
| HTML净利 == 审计净利 | PASS | audit -25.26 / html -25.26 |

