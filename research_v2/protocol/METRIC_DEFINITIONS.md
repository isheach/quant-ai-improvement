# 指标定义

- EMA：前 `period` 个值用简单均值初始化，之后 alpha = 2/(period+1)。
- True Range：首根 high-low；之后 max(high-low, abs(high-prev_close), abs(low-prev_close))。
- ATR：TR 的 EMA，具体 period 由批准参数冻结。
- ER：`abs(close[t]-close[t-L]) / sum(abs(close[i]-close[i-1]))`；分母为 0 返回缺失，状态 NO_TRADE。
- R：`net_profit / initial_stop_risk_usd`，分母来自入场时的止损距离、数量和合约规格。
- lot rounding：`floor(raw_lot / lot_step) * lot_step`；低于 min_lot 返回 0。
- equity：含浮动盈亏、已扣费用、剔除出入金的账户权益。
- Cash：空仓序列。
