from __future__ import annotations
import argparse, hashlib, json, os, tempfile
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

ROOT = Path(__file__).resolve().parents[1]
POINT = 0.001
CONTRACT = 100.0
LOT = 0.01
ACCOUNT = 500.0

@dataclass(frozen=True)
class Bar:
    t: datetime
    o: float
    h: float
    l: float
    c: float
    spread_pts: float = 0.0
    bid: float | None = None
    ask: float | None = None
    bar_open_time: datetime | None = None
    observed_first_time: datetime | None = None
    observed_last_time: datetime | None = None
    observed_m1_count: int | None = None
    completeness_status: str = "UNKNOWN"
    spread_observation_time: datetime | None = None

    def quote(self, side: int, phase: str) -> float:
        bid = self.bid if self.bid is not None else self.c - self.spread_pts * POINT / 2
        ask = self.ask if self.ask is not None else self.c + self.spread_pts * POINT / 2
        if phase == "entry": return ask if side > 0 else bid
        return bid if side > 0 else ask

@dataclass(frozen=True)
class InstrumentSpec:
    contract_size: float = CONTRACT
    volume_min: float = LOT
    volume_step: float = LOT
    volume_max: float = 100.0
    commission_per_lot_round_turn: float = 0.0
    swap_per_lot_round_turn: float = 0.0

@dataclass
class Account:
    balance: float = ACCOUNT
    floating_pnl: float = 0.0
    risk_budget: float = ACCOUNT
    margin_per_lot: float = 0.0

    @property
    def equity(self) -> float: return self.balance + self.floating_pnl
    @property
    def free_margin(self) -> float: return self.equity - self.margin_per_lot

@dataclass
class Position:
    side: int
    volume: float
    entry: float
    entry_index: int
    stop: float | None = None
    initial_stop_risk: float = 0.0
    entry_commission: float = 0.0
    entry_swap: float = 0.0


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def round_lot_down(volume: float, minimum: float, step: float, maximum: float | None = None) -> float:
    if volume < minimum or step <= 0: return 0.0
    value = (int((volume + 1e-12) / step) * step)
    if maximum is not None: value = min(value, maximum)
    return round(value, 10)


def pnl(side: int, entry: float, exit: float, volume: float, contract_size: float = CONTRACT) -> float:
    return side * (exit - entry) * contract_size * volume


def spread_cost(b: Bar, volume: float, contract_size: float = CONTRACT) -> float:
    return b.spread_pts * POINT * contract_size * volume


def commission(spec: InstrumentSpec, volume: float) -> float:
    return spec.commission_per_lot_round_turn * volume


def can_open(account: Account, requested_volume: float, spec: InstrumentSpec, stop_risk: float = 0.0) -> tuple[bool, float, str]:
    volume = round_lot_down(requested_volume, spec.volume_min, spec.volume_step, spec.volume_max)
    if volume <= 0: return False, volume, "below_volume_min_or_invalid_step"
    if account.equity <= 0 or account.free_margin <= 0: return False, volume, "non_positive_equity_or_free_margin"
    if stop_risk > account.risk_budget: return False, volume, "risk_budget_exceeded"
    return True, volume, "accepted"


def open_position(account: Account, bar: Bar, index: int, side: int, requested_volume: float, spec: InstrumentSpec, stop: float | None = None) -> tuple[Position | None, str]:
    risk = abs((bar.quote(side, "entry") - stop) * spec.contract_size * requested_volume) if stop is not None else 0.0
    ok, volume, reason = can_open(account, requested_volume, spec, risk)
    if not ok: return None, reason
    entry = bar.quote(side, "entry")
    fee = commission(spec, volume) / 2
    account.balance -= fee
    return Position(side, volume, entry, index, stop, abs((entry - stop) * spec.contract_size * volume) if stop is not None else 0.0, fee, 0.0), "accepted"


def close_position(account: Account, position: Position, bar: Bar, index: int, reason: str, spec: InstrumentSpec) -> dict:
    exit_price = bar.quote(position.side, "exit")
    gross = pnl(position.side, position.entry, exit_price, position.volume, spec.contract_size)
    exit_fee = commission(spec, position.volume) / 2
    net = gross - position.entry_commission - position.entry_swap - exit_fee - spec.swap_per_lot_round_turn * position.volume
    account.balance += gross - exit_fee - spec.swap_per_lot_round_turn * position.volume
    account.floating_pnl = 0.0
    return {
        "side": position.side, "volume": position.volume, "entry": position.entry, "exit": exit_price,
        "entry_i": position.entry_index, "exit_i": index, "gross": gross,
        "commission": position.entry_commission + exit_fee, "swap": position.entry_swap + spec.swap_per_lot_round_turn * position.volume,
        "cost": position.entry_commission + exit_fee + position.entry_swap + spec.swap_per_lot_round_turn * position.volume,
        "net": net, "reason": reason, "initial_stop_risk": position.initial_stop_risk,
        "r": net / position.initial_stop_risk if position.initial_stop_risk else None,
    }


def execute_signal_sequence(bars: list[Bar], signals: dict[int, dict], spec: InstrumentSpec | None = None, account: Account | None = None) -> dict:
    """Synthetic/event engine: signal at bar i executes on the next bar event.
    Stops are checked on the current event and gap stops fill at the event quote.
    """
    spec = spec or InstrumentSpec(); account = account or Account(); position = None; legs = []; decisions = []
    for i, bar in enumerate(bars):
        if position is not None:
            stop_hit = (position.side > 0 and bar.l <= (position.stop or -float("inf"))) or (position.side < 0 and bar.h >= (position.stop or float("inf")))
            if stop_hit:
                legs.append(close_position(account, position, bar, i, "stop", spec)); position = None
        event = signals.get(i)
        if event and event.get("action") == "close" and position is not None:
            legs.append(close_position(account, position, bar, i, event.get("reason", "signal_close"), spec)); position = None
        if event and event.get("action") == "open" and position is None:
            if i + 1 >= len(bars):
                decisions.append({"index": i, "decision": "rejected", "reason": "no_next_trade_event"}); continue
            next_bar = bars[i + 1]
            position, reason = open_position(account, next_bar, i + 1, int(event["side"]), float(event.get("volume", LOT)), spec, event.get("stop"))
            decisions.append({"index": i, "execution_index": i + 1, "decision": reason})
        if position is not None:
            account.floating_pnl = pnl(position.side, position.entry, bar.quote(position.side, "exit"), position.volume, spec.contract_size)
    if position is not None:
        legs.append(close_position(account, position, bars[-1], len(bars) - 1, "end", spec))
    return {"account": asdict(account), "baskets": [], "legs": legs, "fills": legs.copy(), "decisions": decisions,
            "ledger_net": sum(x["net"] for x in legs), "final_equity": account.equity}


def summary(trades: Iterable[dict], account: Account | None = None) -> dict:
    legs = list(trades); net = sum(x["net"] for x in legs); wins = [x["net"] for x in legs if x["net"] > 0]; losses = [-x["net"] for x in legs if x["net"] < 0]
    return {"baskets": 0, "legs": len(legs), "fills": len(legs), "net_profit": round(net, 8), "cost_total": round(sum(x.get("cost", 0) for x in legs), 8),
            "win_rate": round(len(wins) / len(legs), 8) if legs else None, "profit_factor": round(sum(wins) / sum(losses), 8) if losses else None,
            "final_equity": round((account.equity if account else ACCOUNT + net), 8), "account_mode": "validated_synthetic_only"}


def load_m30() -> list[Bar]:
    raise RuntimeError("historical loading is disabled in RESEARCH_V2_ENGINE_AND_RECOVERY_REPAIR_R1")


def main(_: list[str] | None = None) -> None:
    raise SystemExit("BLOCKED: historical replay is disabled; use execute_signal_sequence with synthetic bars")

if __name__ == "__main__": main()
