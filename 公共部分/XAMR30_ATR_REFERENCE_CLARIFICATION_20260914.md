# XAMR30 ATR reference clarification

Date: 2026-09-14

This is a pre-economic verification clarification. It is not a strategy
modification, parameter modification, or post-hoc profitability adjustment.

## What was originally frozen

The original XAMR30 preregistration says:

`ATR14_t = ATR(14) on M30`

It does not specify Wilder/RMA, EMA, or SMA recurrence. Before any TRAIN or
VALID run, N1R3 froze the implementation:

`iATR(_Symbol, PERIOD_M30, 14)`

The strategy source and binary remain unchanged:

- source SHA-256: `CA5AD7339FE415CBC3BD2304B94C47E755B2A6292AA5A69FC1E34D5B7E72826C`
- N1R3 EX5 SHA-256: `F374890F28022FCB88FA55BD34CD5BCE82DFB93A6C4EA549A3ACF34A60F658B2`

## R1 finding

R1 used the same fixed 90 timestamps (60 candidate + 30 control), the same
raw MT5 M30 OHLC, and the same MQL5 Probe. It found:

- MQL `iATR` vs Python Wilder ATR: `0/90`.
- MQL `iATR` vs the arithmetic mean of the current 14 True Range values:
  `90/90`, maximum absolute difference approximately `4.29e-11`.
- EMA48, residual, sigma48, z-score, XAU exact OHLC/return, and all other
  discrete fields: `90/90`.
- Probe to the existing N1R3 final-smoke audit bridge: `37/37`.

The R1 result is therefore retained as:

`R1 verification reference = Wilder ATR`
`R1 result = FAIL`
`reason = reference semantics mismatch`

The previous requirement that Python use Wilder ATR was a Planner
verification-spec error. It was an extra assumption, not a requirement in the
original XAMR30 preregistration. It does not indicate an N1R3 strategy bug.

## R2 authoritative reference

For the currently frozen N1R3 strategy, the independent verification
reference is the observed MT5 `iATR` semantics in the frozen MT5 build and
environment:

`ATR14_t = mean(TR_t, TR_(t-1), ..., TR_(t-13))`

where

`TR_t = max(High_t-Low_t, abs(High_t-Close_(t-1)), abs(Low_t-Close_(t-1)))`.

P20/P80 still use the 500 ATR values strictly before the signal bar, with
nearest-rank indexes 99 and 399 (0-based). No sample, window, tolerance, raw
data, strategy source, strategy binary, or economic result is changed.

This clarification only makes the independent calculation match the already
frozen strategy behavior. It does not claim that every ATR implementation in
software or literature uses this averaging convention.

R1 remains at
`公共部分/XAMR30_SIGNAL_DOUBLECALC_20260914_R1.md`; it is not overwritten.
