# Strategy repair checkpoint: R20 / R21

Date: 2026-09-25

## Evidence status

- R20 completed as a Python quick screen over seven rolling windows using 6 months train, 3 months validation, and 3 months test. It produced net `-74.1041 USD`, annualized `-6.20%`, `131` test trades, and maximum fold drawdown `8.56%`. This is a failed candidate and is not a final performance claim.
- The fixed-parameter comparison was worse: net `-406.5606 USD`, annualized `-48.78%`, `875` trades, maximum fold drawdown `38.40%`.
- R20 adaptive control reduced activity and drawdown, but did not make the strategy profitable. Trend trades were `0` in every reported test fold.
- The reserved blank holdout remains `2026-04..2026-06` and was not read or used for feedback.
- R21 was engineered to address minimum-lot rejection and risk discretization, but the full replay did not finish within the local execution limit and produced no result file. It must not be treated as evidence.

## Repair actions

- Workflow authorization now accepts both explicit `historical_replay_authorized` and the existing `formal_runs_authorized` approval field.
- Cost-incomplete approval still blocks `mt5_final` promotion to a final claim.
- R20/R21 preserve next-bar entry ordering and spread-aware exits.
- R21 adds a minimum-lot-aware risk floor, an account-risk cap, wider risk candidates, and a low-trade penalty.

## Next experiment

Use a cached/vectorized pre-screen or a single frozen parameter set before full rolling replay. The next candidate must report rejected orders, grid/trend decomposition, trade spacing, and layer count. Only a frozen candidate may proceed to local MT5 Strategy Tester; Python output cannot establish profitability.
