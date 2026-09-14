# XAMR30 V1 TRAIN review

## Run identity

- Run tag: `DS260914_XAMR30_V1_TRAIN`
- Branch: `run/xamr30-v1-train-r1`
- Executor commit before evidence packaging: `f61c3fbac1ca56ffe2e92fd1c246a6f67e483fda`
- Execution count: `1` (exactly once)
- MT5 process exit code: `0`
- Observed start: `2026-09-15T01:14:11.8986349+08:00`
- Observed end: `2026-09-15T01:14:30.0383000+08:00`
- Frozen configuration: `N0_final/resolved_INIs/run_DS260914_XAMR30_V1_TRAIN.ini`
- Report history quality: `99%` (recorded transparently; not suppressed)

## Integrity gate

`V1_TRAIN = VALID`.

The HTML report has `937` total trades and the frozen audit has
`937` trade rows.  The audit net is `-446.8400000000` USD and the
report net is `-446.8400000000` USD; the absolute difference is
`5.684341886e-14`, below the tolerance `0.44684`.
The audit self-check reports fatal `0`, audit_failed `0`, active_positions `0`,
OCP mismatch `0`, and formula diagnostics out `0`.  There are no duplicate
trade tickets, all `alignment_exact` values are `1`, and the maximum number of
actual entries on any UTC date is `1`.
All parsed entry and exit timestamps remain within the 2018-01-01 through
2024-05-31 TRAIN window.  The six `time_exit` rows are retained in the ledger;
bar-count holding distribution is explicitly `NOT_COMPUTABLE_FROM_FROZEN_AUDIT`
because that field is not present in the frozen audit schema.

## Economic result (descriptive only)

- Net profit: `-446.84` USD; return on USD 500 deposit: `-89.368%`
- Profit factor: `0.6600`
- Official equity drawdown: `451.73 (89.92%)`
- Total trades: `937`; trades/year: `146.131191`
- Win rate: `45.4642%`; average winner: `2.01190141` USD; average loser: `-2.55168297` USD
- Payoff ratio: `0.78846057`; expectancy: `-0.47688367` USD/trade
- R expectancy: `-0.09333522` using `R_i = net_i / abs(ocp_expected_pl_i)` on `937` nonzero-OCP rows
- Long: `404` trades / `-216.72` USD; short: `533` trades / `-230.12` USD
- Commission total: `0.00` USD; swap total: `-9.48` USD
- Spread/SL median and p95: `0.13510000` / `0.26566600`; spread/TP median and p95: `0.16888000` / `0.33208000`
- Reject counts: `{"atr_out_of_regime": 8046, "cross_asset_filter_fail": 3698, "cross_asset_missing_bar": 274, "min_lot_risk_reject": 1691}`

## Robustness post-processing

Cost stress is post-processing only; no MT5 rerun was performed.  The base
cost is `abs(ocp_expected_pl) * spread_over_sl + abs(swap) + abs(commission)`
per trade.  Results:

[
  {
    "cost_multiplier": 1.0,
    "net": -446.84,
    "profit_factor": 0.657307636263239,
    "expectancy_usd": -0.47688367129135545,
    "postprocessing_only": true,
    "mt5_rerun": false
  },
  {
    "cost_multiplier": 1.5,
    "net": -605.5550677,
    "profit_factor": 0.5685886599799062,
    "expectancy_usd": -0.6462700829242263,
    "postprocessing_only": true,
    "mt5_rerun": false
  },
  {
    "cost_multiplier": 2.0,
    "net": -764.2701354,
    "profit_factor": 0.4918893170542975,
    "expectancy_usd": -0.8156564945570971,
    "postprocessing_only": true,
    "mt5_rerun": false
  }
]

Winner concentration: top 5 / top 10 of gross winners are
`0.03383621` / `0.06706570`;
net without the top 10 winners is `-504.32` USD.
Worst 5 / worst 10 loss sums are `-40.96` / `-77.29` USD;
net without the worst 10 losers is `-369.55` USD.

Bootstrap, OOS, user holdout, VALID, optimization, V2 and V3 were not run.
The daily return CSV uses closed-trade UTC exit dates and does not invent zero
return dates absent from the frozen audit; bootstrap is `NOT_RUN`.

## Safety and provenance

Source MQ5, canonical EX5, deployed EX5 and the frozen INI all match their
pre-run SHA-256 identities.  Raw HTML, trade audit, reject audit and self-check
files remain outside Git and are referenced by path, size, SHA-256, row count,
and timestamp metadata in the manifest.  Broker account or connection
identifiers are intentionally omitted from this package.
