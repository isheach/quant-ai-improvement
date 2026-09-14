# XAMR30 N1R3 Independent Final-Smoke Report

- Same frozen N1R3 smoke evidence; no MT5 rerun.
- Independent held-bar count uses only the frozen real USDJPYm M30 bar-open timestamps.
- No calendar-minute or weekend approximation is used.
- Old `verify_final_smoke.py` and old 68/69 provenance remain unchanged.

## Identity and result

- Raw USDJPYm identity: **PASS**
- Trades: **37** (WINTER 12, DSTTR 10, SUMMER 15)
- Independent full-held-bar checks: **37/37**
- Maximum full-held bars: **12**
- FINAL_SMOKE_INDEPENDENT: **PASS**

## Window summary

| Window | trades | time_exit | max full-held bars | checker |
|---|---:|---:|---:|---|
| WINTER | 12 | 1 | 12 | 24/24 PASS |
| DSTTR | 10 | 0 | 5 | 24/24 PASS |
| SUMMER | 15 | 1 | 12 | 24/24 PASS |

## Diagnostic-only fields

| Window | duplicate_attempts_blocked |
|---|---|
| WINTER | dup_hits=12; recorded from audit_selfcheck.csv; excluded from PASS/FAIL checks |
| DSTTR | dup_hits=10; recorded from audit_selfcheck.csv; excluded from PASS/FAIL checks |
| SUMMER | dup_hits=15; recorded from audit_selfcheck.csv; excluded from PASS/FAIL checks |

## Independent time-exit evidence

- `WINTER` ticket `19`: `2023.01.23 15:30:00` → `2023.01.23 21:30:00`, full_held_bars=`12`.
- `SUMMER` ticket `25`: `2023.07.21 17:00:00` → `2023.07.23 23:00:00`, full_held_bars=`12`.

### Disputed SUMMER cross-weekend trade

- deal_ticket: `25`
- entry_time: `2023.07.21 17:00:00`
- exit_time: `2023.07.23 23:00:00`
- exit_reason: `time_exit`
- full_held_bars: `12`
- first_counted_bar_open: `2023.07.21 17:00:00`
- last_counted_bar_open: `2023.07.23 22:30:00`
- counted_bar_timestamps:
  - `2023.07.21 17:00:00`
  - `2023.07.21 17:30:00`
  - `2023.07.21 18:00:00`
  - `2023.07.21 18:30:00`
  - `2023.07.21 19:00:00`
  - `2023.07.21 19:30:00`
  - `2023.07.21 20:00:00`
  - `2023.07.21 20:30:00`
  - `2023.07.23 21:00:00`
  - `2023.07.23 21:30:00`
  - `2023.07.23 22:00:00`
  - `2023.07.23 22:30:00`

## Checks

### WINTER

| Check | Result | Detail |
|---|---|---|
| Bars>0 | PASS | Bars=29797 |
| Deposit=500 | PASS | 500.00 |
| Symbol=USDJPYm | PASS | USDJPYm |
| HTML trades == 审计行数 | PASS | HTML=12 审计=12 |
| 实际产生 closing deals | PASS | expected=12, actual=12 |
| fatal=0 | PASS | 0 |
| audit_failed=0 | PASS | 0 |
| active_positions=0 | PASS | 0 |
| 入场时序 entry_bar = signal_bar+30min | PASS | 抽查=12, 违规=无 |
| 入场时序 entry_time >= signal_close | PASS | 违规=无 |
| 时序抽查（本窗口） | PASS | 12/12 |
| time_exit exactly 12 real M30 bars | PASS | time_exit=1, bad=无 |
| 非 time_exit 持仓未超 12 根 | PASS | 越界=无 |
| unique_deal_ticket_rows == audit_rows | PASS | 12/12 |
| duplicate_written_rows == 0 | PASS | 重复=0 |
| 每 UTC day <= 1 笔 | PASS | 违反=无 |
| 全部成交 alignment_exact=1 | PASS | 异常=0 |
| cross_asset_missing_bar 的 xau_bar_time 为空 | PASS | 拒单=14, stale=0 |
| atr_out_of_regime 的 xau 值为空 | PASS | 拒单=74, stale=0 |
| DEAL_PROFIT↔OCP<=0.05 | PASS | 超容差=无 |
| spread / SL / TP 字段齐备 | PASS | same frozen audit schema |
| median spread/SL <= 30% | PASS | median=0.0449 |
| median spread/TP <= 30% | PASS | median=0.0562 |
| HTML净利 == 审计净利 | PASS | audit=-3.76, html=-3.76 |

### DSTTR

| Check | Result | Detail |
|---|---|---|
| Bars>0 | PASS | Bars=19862 |
| Deposit=500 | PASS | 500.00 |
| Symbol=USDJPYm | PASS | USDJPYm |
| HTML trades == 审计行数 | PASS | HTML=10 审计=10 |
| 实际产生 closing deals | PASS | expected=10, actual=10 |
| fatal=0 | PASS | 0 |
| audit_failed=0 | PASS | 0 |
| active_positions=0 | PASS | 0 |
| 入场时序 entry_bar = signal_bar+30min | PASS | 抽查=10, 违规=无 |
| 入场时序 entry_time >= signal_close | PASS | 违规=无 |
| 时序抽查（本窗口） | PASS | 10/10 |
| time_exit exactly 12 real M30 bars | PASS | time_exit=0, bad=无 |
| 非 time_exit 持仓未超 12 根 | PASS | 越界=无 |
| unique_deal_ticket_rows == audit_rows | PASS | 10/10 |
| duplicate_written_rows == 0 | PASS | 重复=0 |
| 每 UTC day <= 1 笔 | PASS | 违反=无 |
| 全部成交 alignment_exact=1 | PASS | 异常=0 |
| cross_asset_missing_bar 的 xau_bar_time 为空 | PASS | 拒单=0, stale=0 |
| atr_out_of_regime 的 xau 值为空 | PASS | 拒单=49, stale=0 |
| DEAL_PROFIT↔OCP<=0.05 | PASS | 超容差=无 |
| spread / SL / TP 字段齐备 | PASS | same frozen audit schema |
| median spread/SL <= 30% | PASS | median=0.0417 |
| median spread/TP <= 30% | PASS | median=0.0521 |
| HTML净利 == 审计净利 | PASS | audit=-21.26, html=-21.26 |

### SUMMER

| Check | Result | Detail |
|---|---|---|
| Bars>0 | PASS | Bars=28695 |
| Deposit=500 | PASS | 500.00 |
| Symbol=USDJPYm | PASS | USDJPYm |
| HTML trades == 审计行数 | PASS | HTML=15 审计=15 |
| 实际产生 closing deals | PASS | expected=15, actual=15 |
| fatal=0 | PASS | 0 |
| audit_failed=0 | PASS | 0 |
| active_positions=0 | PASS | 0 |
| 入场时序 entry_bar = signal_bar+30min | PASS | 抽查=15, 违规=无 |
| 入场时序 entry_time >= signal_close | PASS | 违规=无 |
| 时序抽查（本窗口） | PASS | 15/15 |
| time_exit exactly 12 real M30 bars | PASS | time_exit=1, bad=无 |
| 非 time_exit 持仓未超 12 根 | PASS | 越界=无 |
| unique_deal_ticket_rows == audit_rows | PASS | 15/15 |
| duplicate_written_rows == 0 | PASS | 重复=0 |
| 每 UTC day <= 1 笔 | PASS | 违反=无 |
| 全部成交 alignment_exact=1 | PASS | 异常=0 |
| cross_asset_missing_bar 的 xau_bar_time 为空 | PASS | 拒单=1, stale=0 |
| atr_out_of_regime 的 xau 值为空 | PASS | 拒单=66, stale=0 |
| DEAL_PROFIT↔OCP<=0.05 | PASS | 超容差=无 |
| spread / SL / TP 字段齐备 | PASS | same frozen audit schema |
| median spread/SL <= 30% | PASS | median=0.0777 |
| median spread/TP <= 30% | PASS | median=0.0972 |
| HTML净利 == 审计净利 | PASS | audit=-25.26, html=-25.26 |

## Scope

This is a pre-economic verifier-only closure. It does not modify the EA, rerun MT5, read profits for strategy judgment, or authorize TRAIN/VALID.
