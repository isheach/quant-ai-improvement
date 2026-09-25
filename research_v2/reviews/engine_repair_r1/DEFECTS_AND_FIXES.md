# Engine repair defects and fixes

- Actual fill volume is carried on every position, leg and fill; P&L and fees use that volume.
- Bid/ask execution is explicit. A fixed 2000.0 bid / 2000.2 ask round trip at 0.01 lot is -0.2, with no second spread deduction.
- Signals execute on the next trade event. Stop gaps fill at the event quote.
- Account state tracks balance, floating P&L, equity, free margin and volume constraints; invalid accounts reject new orders.
- Workflow reservation uses a single instance lock, records run identity before execution, rejects unknown existing output and returns completed runs idempotently.
- Historical loading and replay remain disabled in this repair stage.
