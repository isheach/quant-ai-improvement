# XAMR30 V1 post-train closure

## Decision

- Economic execution count: `1`.
- `RUN_INTEGRITY_STATUS`: `VALID`.
- `VARIANT_TRAIN_GATE_STATUS`: `CLOSED`.
- `V1_VALID_AUTHORIZED`: `NO`.
- Closure reason: preregistered hard gates failed.
- No research source, canonical EX5, deployed EX5, frozen INI, static input,
  or N0 guard was changed by this closure.

The V1 result remains a valid, reproducible negative result. The observed net
was `-446.84` USD, report profit factor was `0.66`, equity drawdown was
`89.92%`, 2x-cost net was `-764.2701354` USD, and net without the top ten
winners was `-504.32` USD. Audit consistency passed.

## Calendar and bootstrap closure

R1 and R2 were each executed once as data-only probes and both ended with
`FAILED_ENGINEERING_NO_DATA`. R1 produced no calendar CSV or metadata. R2
produced only an empty/header-only calendar artifact and metadata recording the
folder error (`4401`) with zero bars and zero trading days. No economic strategy
was run during either probe.

- Total data-only probes: `2`.
- `DATA_PROBE_R3_AUTHORIZED`: `NO`.
- Canonical TRAIN trading calendar: `UNAVAILABLE`.
- Canonical V1 daily bootstrap series: unavailable.
- V1-vs-V2 paired bootstrap: `BLOCKED_PRECONDITION`.
- Bootstrap executed: `NO`.
- Weekday, trade-date, and reject-date proxy calendars: forbidden.

No additional calendar probe, MT5 economic rerun, V2, V3, VALID, OOS,
holdout, or optimization run was performed.

V2 and V3 remain independently preregistered. V1 closure does not invalidate
them, but they require a later Planner authorization before execution.

## Frozen identity and provenance

The source MQ5, canonical EX5, deployed EX5, and frozen INI SHA-256 identities
are unchanged before and after this closure. Raw V1 ledger, parsed report,
monthly summary, and yearly summary bodies are unchanged. Broker account and
connection identifiers are intentionally omitted.
