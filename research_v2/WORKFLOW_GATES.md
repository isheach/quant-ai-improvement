# Research workflow gates

The research pipeline has four distinct evidence classes:

1. `engineering`: synthetic tests only. It checks accounting, recovery, locks, and deterministic behavior.
2. `quick_screen`: Python replay for parameter rotation and controller feedback. Its output is never a final performance claim.
3. `mt5_final`: MT5 Strategy Tester on the broker native symbol. This is the only class that can support a final strategy statement.
4. `mt5_holdout`: the untouched forward segment. It must be run once, after parameters are frozen, with no feedback written back into the controller.

Every historical run requires explicit authorization in `protocol/APPROVAL.json`. Final modes additionally require a manifest declaring `tester=MetaTrader5_StrategyTester`, a broker native symbol, the exact date range, initial deposit, model, and history source.

The intended research loop is:

- rotate fixed strategy candidates over rolling train/validation/test windows;
- summarize trade spacing, layer count, trend outcomes, drawdown, cost, and rejected orders;
- adjust only pre-registered hyperparameters using the previous window;
- freeze the selected parameters;
- reproduce the selected candidate in MT5;
- run the blank holdout once and report it separately.

A Python result can be used to reject or prioritize a candidate. It cannot be promoted to `final_claim_allowed`.
