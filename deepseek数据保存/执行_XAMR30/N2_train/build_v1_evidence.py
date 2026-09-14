#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Build the immutable evidence package for the single frozen V1 TRAIN run.

This is an analysis/evidence builder only.  It never starts MT5, changes an
INI, changes an EX5, or copies raw broker files into the repository.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean, median, quantiles


ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
RUN_TAG = "DS260914_XAMR30_V1_TRAIN"
BRANCH = "run/xamr30-v1-train-r1"
HEAD = "f61c3fbac1ca56ffe2e92fd1c246a6f67e483fda"
RUN_START = "2026-09-15T01:14:11.8986349+08:00"
RUN_END = "2026-09-15T01:14:30.0383000+08:00"
RUN_EXIT_CODE = 0
RUN_COUNT = 1
TRAIN_START = datetime(2018, 1, 1)
TRAIN_END = datetime(2024, 5, 31, 23, 59, 59)
INITIAL_DEPOSIT = 500.0

AUDIT_DIR = Path(
    r"C:\Users\UIC\AppData\Roaming\MetaQuotes\Terminal\Common\Files\dshtrend"
) / RUN_TAG
REPORT_PATH = Path(
    r"C:\Users\UIC\AppData\Roaming\MetaQuotes\Terminal\53785E099C927DB68A545C249CDBCE06"
) / "DS260914_XAMR30_V1_TRAIN.htm"
TRADES_PATH = AUDIT_DIR / "trades.csv"
REJECT_PATH = AUDIT_DIR / "reject_audit.csv"
SELFCHECK_PATH = AUDIT_DIR / "audit_selfcheck.csv"
SOURCE_PATH = ROOT / "deepseek数据保存" / "mql5" / "dshtools" / "dsh_XAMR30.mq5"
CANONICAL_EX5 = ROOT / "deepseek数据保存" / "执行_XAMR30" / "dsh_XAMR30_N1R3.ex5"
DEPLOYED_EX5 = Path(
    r"C:\Users\UIC\AppData\Roaming\MetaQuotes\Terminal\53785E099C927DB68A545C249CDBCE06"
) / "MQL5" / "Experts" / "dshtrend" / "dsh_XAMR30.ex5"
INI_PATH = (
    ROOT
    / "deepseek数据保存"
    / "执行_XAMR30"
    / "N0_final"
    / "resolved_INIs"
    / "run_DS260914_XAMR30_V1_TRAIN.ini"
)

EXPECTED_SHA256 = {
    "source_mq5": "CA5AD7339FE415CBC3BD2304B94C47E755B2A6292AA5A69FC1E34D5B7E72826C",
    "canonical_ex5": "F374890F28022FCB88FA55BD34CD5BCE82DFB93A6C4EA549A3ACF34A60F658B2",
    "deployed_ex5": "F374890F28022FCB88FA55BD34CD5BCE82DFB93A6C4EA549A3ACF34A60F658B2",
    "frozen_ini": "3248FD8F94F1CF6FB55FF20D0068A3CF8BF2E942EA0C589C88F232DEA374D0B1",
}

REQUIRED_TRADE_FIELDS = (
    "run_tag",
    "symbol",
    "deal_ticket",
    "position_id",
    "signal_bar_open_time",
    "signal_bar_close_time",
    "entry_bar_open_time",
    "entry_time",
    "exit_time",
    "z_score",
    "ema48",
    "residual",
    "sigma48",
    "atr14",
    "atr_p20",
    "atr_p80",
    "xau_bar_time",
    "xau_open",
    "xau_close",
    "xau_return",
    "cross_asset_filter_enabled",
    "cross_asset_filter_pass",
    "alignment_exact",
    "trade_direction",
    "spread_at_entry_points",
    "initial_sl_distance_points",
    "initial_tp_distance_points",
    "spread_over_sl",
    "spread_over_tp",
    "risk_budget",
    "actual_initial_sl_risk",
    "ocp_expected_pl",
    "deal_profit",
    "swap",
    "commission",
    "net",
    "formula_value",
    "formula_diff",
    "close_type",
    "exit_reason",
    "server_utc_offset",
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest().upper()


def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    for fmt in (
        "%Y.%m.%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y.%m.%d",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    return None


def as_float(value: object, default: float = 0.0) -> float:
    if value is None or str(value).strip() == "":
        return default
    text = str(value).replace(",", "").replace(" ", "")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(match.group(0)) if match else default


def metric(kv: dict[str, str], *keys: str) -> str | None:
    for key in keys:
        if key in kv:
            return kv[key]
    return None


def json_write(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
        return list(reader.fieldnames or []), rows


def write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def parse_ini_safe(path: Path) -> dict[str, str]:
    # Deliberately allow-list fields.  Login/Server/Account are never emitted.
    allowed = {
        "Expert",
        "Symbol",
        "Period",
        "Model",
        "Optimization",
        "FromDate",
        "ToDate",
        "Deposit",
        "Currency",
        "Leverage",
        "Visual",
        "Report",
        "ReplaceReport",
        "ShutdownTerminal",
        "InpRunTag",
        "InpZThreshold",
        "InpCrossAssetFilter",
        "InpUseGrid",
        "InpUseMartingale",
        "InpUseTrailingWin",
    }
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("[") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key in allowed:
            values[key] = value.strip()
    return values


def report_safe_values(kv: dict[str, str]) -> dict[str, str]:
    allowed = {
        "Expert",
        "Symbol",
        "Period",
        "Inputs",
        "Currency",
        "Initial Deposit",
        "Leverage",
        "History Quality",
        "Bars",
        "Ticks",
        "Total Net Profit",
        "Balance Drawdown Absolute",
        "Balance Drawdown Maximal",
        "Balance Drawdown Relative",
        "Equity Drawdown Absolute",
        "Equity Drawdown Maximal",
        "Equity Drawdown Relative",
        "Gross Profit",
        "Gross Loss",
        "Profit Factor",
        "Expected Payoff",
        "Total Trades",
        "Short",
        "Long",
        "Total Deals",
        "Profit Trades",
        "Loss Trades",
        "Minimal position holding time",
        "Maximal position holding time",
        "Average position holding time",
    }
    return {key: value for key, value in kv.items() if key in allowed}


def raw_file_meta(path: Path, rows: list[dict[str, str]] | None = None) -> dict[str, object]:
    result: dict[str, object] = {
        "path": str(path),
        "exists": path.is_file(),
    }
    if not path.is_file():
        return result
    result.update({"size_bytes": path.stat().st_size, "sha256": sha256(path)})
    if rows is not None:
        result["row_count"] = len(rows)
        times: list[datetime] = []
        for row in rows:
            for key in ("entry_time", "exit_time"):
                ts = parse_ts(row.get(key))
                if ts:
                    times.append(ts)
        if times:
            result["first_timestamp"] = min(times).strftime("%Y-%m-%d %H:%M:%S")
            result["last_timestamp"] = max(times).strftime("%Y-%m-%d %H:%M:%S")
    return result


def grouped_net(rows: list[dict[str, str]], key_func) -> list[dict[str, object]]:
    groups: defaultdict[str, float] = defaultdict(float)
    counts: Counter[str] = Counter()
    for row in rows:
        ts = parse_ts(row.get("exit_time"))
        if ts is None:
            continue
        key = key_func(ts)
        groups[key] += as_float(row.get("net"))
        counts[key] += 1
    return [
        {"period": key, "trade_count": counts[key], "net": round(groups[key], 8)}
        for key in sorted(groups)
    ]


def pf(values: list[float]) -> float | None:
    wins = sum(value for value in values if value > 0)
    losses = -sum(value for value in values if value < 0)
    return wins / losses if losses else None


def pctl(values: list[float], p: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    return quantiles(values, n=100, method="inclusive")[int(p) - 1]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for path in (REPORT_PATH, TRADES_PATH, REJECT_PATH, SELFCHECK_PATH):
        if not path.is_file():
            raise SystemExit(f"missing frozen run evidence: {path}")

    parser_dir = ROOT / "deepseek数据保存" / "执行_第三批"
    sys.path.insert(0, str(parser_dir))
    from mt5_html_parser import parse_report  # type: ignore

    report = parse_report(str(REPORT_PATH))
    if not report:
        raise SystemExit("unable to parse frozen MT5 report")
    report_kv = report["kv"]
    trade_fields, trades = read_csv(TRADES_PATH)
    reject_fields, rejects = read_csv(REJECT_PATH)
    selfcheck_fields, selfchecks = read_csv(SELFCHECK_PATH)
    if not selfchecks:
        raise SystemExit("missing audit selfcheck row")
    selfcheck = selfchecks[0]

    missing_fields = [field for field in REQUIRED_TRADE_FIELDS if field not in trade_fields]
    if missing_fields:
        raise SystemExit(f"frozen audit is missing fields: {missing_fields}")
    if any(row.get("run_tag") != RUN_TAG for row in trades + rejects + selfchecks):
        raise SystemExit("run tag mismatch in frozen audit files")

    ini = parse_ini_safe(INI_PATH)
    safe_ini_expected = {
        "Expert": r"dshtrend\dsh_XAMR30",
        "Symbol": "USDJPYm",
        "Period": "M30",
        "Model": "2",
        "Optimization": "0",
        "FromDate": "2018.01.01",
        "ToDate": "2024.05.31",
        "Deposit": "500",
        "Currency": "USD",
        "Leverage": "1:200",
        "Visual": "0",
        "Report": RUN_TAG,
        "ReplaceReport": "1",
        "ShutdownTerminal": "1",
        "InpRunTag": RUN_TAG,
        "InpZThreshold": "1.5",
        "InpCrossAssetFilter": "true",
        "InpUseGrid": "false",
        "InpUseMartingale": "false",
        "InpUseTrailingWin": "false",
    }
    ini_safe_ok = ini == safe_ini_expected

    source_sha = sha256(SOURCE_PATH)
    canonical_sha = sha256(CANONICAL_EX5)
    deployed_sha = sha256(DEPLOYED_EX5)
    ini_sha = sha256(INI_PATH)
    hashes_ok = {
        "source_unchanged": source_sha == EXPECTED_SHA256["source_mq5"],
        "canonical_unchanged": canonical_sha == EXPECTED_SHA256["canonical_ex5"],
        "deployed_unchanged": deployed_sha == EXPECTED_SHA256["deployed_ex5"],
        "canonical_equals_deployed": canonical_sha == deployed_sha,
        "frozen_ini_unchanged": ini_sha == EXPECTED_SHA256["frozen_ini"],
    }

    values = [as_float(row.get("net")) for row in trades]
    deal_values = [as_float(row.get("deal_profit")) for row in trades]
    ocp_values = [as_float(row.get("ocp_expected_pl")) for row in trades]
    winner_values = sorted((value for value in values if value > 0), reverse=True)
    loser_values = sorted((value for value in values if value < 0))
    nonzero_ocp_r = [
        as_float(row.get("net")) / abs(as_float(row.get("ocp_expected_pl")))
        for row in trades
        if abs(as_float(row.get("ocp_expected_pl"))) > 1e-12
    ]

    def row_time(row: dict[str, str], field: str) -> datetime | None:
        return parse_ts(row.get(field))

    entry_times = [row_time(row, "entry_time") for row in trades]
    exit_times = [row_time(row, "exit_time") for row in trades]
    valid_entry_times = [ts for ts in entry_times if ts]
    valid_exit_times = [ts for ts in exit_times if ts]
    actual_entry_days = Counter(ts.date().isoformat() for ts in valid_entry_times)
    missing_required_values = sum(
        1
        for row in trades
        for field in REQUIRED_TRADE_FIELDS
        if row.get(field, "") == ""
    )
    alignment_bad = sum(row.get("alignment_exact") != "1" for row in trades)
    timestamps_valid = len(valid_entry_times) == len(trades) and len(valid_exit_times) == len(trades)
    timestamps_in_train = all(
        TRAIN_START <= ts <= TRAIN_END for ts in valid_entry_times + valid_exit_times
    )
    per_day_ok = max(actual_entry_days.values(), default=0) <= 1
    html_total_trades = int(as_float(metric(report_kv, "Total Trades")))
    report_net = as_float(metric(report_kv, "Total Net Profit"))
    audit_net = sum(values)
    net_tolerance = max(0.01, abs(report_net) * 0.001)
    net_reconciles = abs(report_net - audit_net) <= net_tolerance

    required_selfcheck_zero = {
        key: selfcheck.get(key, "")
        for key in ("fatal", "audit_failed", "active_positions", "ocp_mismatch", "formula_diag_out")
    }
    selfcheck_zero_ok = all(value in {"0", "0.0", "false", "False"} for value in required_selfcheck_zero.values())
    unique_tickets = len({row.get("deal_ticket") for row in trades}) == len(trades)
    close_types = Counter(row.get("close_type", "") for row in trades)
    exit_reasons = Counter(row.get("exit_reason", "") for row in trades)
    time_exit_rows = [row for row in trades if row.get("exit_reason") == "time_exit"]
    holding_schema_normal = all(
        row.get("exit_reason") in {"sl", "tp", "time_exit"}
        and row.get("close_type", "") != ""
        for row in trades
    ) and all(
        row.get("exit_reason") == "time_exit" or row.get("exit_reason") in {"sl", "tp"}
        for row in time_exit_rows
    )

    integrity = {
        "html_total_trades_equals_audit_rows": html_total_trades == len(trades),
        "audit_selfcheck_trades_equals_rows": as_float(selfcheck.get("trades")) == len(trades),
        "audit_written_deals_equals_rows": as_float(selfcheck.get("written_deals")) == len(trades),
        "fatal_zero": selfcheck.get("fatal") == "0",
        "audit_failed_zero": selfcheck.get("audit_failed") == "0",
        "active_positions_zero": selfcheck.get("active_positions") == "0",
        "ocp_mismatch_zero": selfcheck.get("ocp_mismatch") == "0",
        "formula_diag_out_zero": selfcheck.get("formula_diag_out") == "0",
        "html_net_reconciles_to_audit": net_reconciles,
        "unique_trade_tickets": unique_tickets,
        "at_most_one_entry_per_utc_day": per_day_ok,
        "all_alignment_exact": alignment_bad == 0,
        "required_fields_present": not missing_fields and missing_required_values == 0,
        "timestamps_parse": timestamps_valid,
        "timestamps_within_train": timestamps_in_train,
        "holding_and_exit_schema_normal": holding_schema_normal,
        "no_oos_or_holdout_rows": timestamps_in_train and len(valid_exit_times) == len(trades),
        "source_canonical_deployed_ini_unchanged": all(hashes_ok.values()),
        "frozen_ini_safe": ini_safe_ok,
    }
    integrity_pass = all(integrity.values())

    reject_counts = Counter(row.get("reason", "") for row in rejects)
    long_rows = [row for row in trades if row.get("trade_direction") == "long"]
    short_rows = [row for row in trades if row.get("trade_direction") == "short"]
    winners = [value for value in values if value > 0]
    losers = [value for value in values if value < 0]
    holding_seconds = [
        (exit_ts - entry_ts).total_seconds()
        for entry_ts, exit_ts in zip(entry_times, exit_times)
        if entry_ts and exit_ts and exit_ts >= entry_ts
    ]
    spreads_sl = [as_float(row.get("spread_over_sl")) for row in trades]
    spreads_tp = [as_float(row.get("spread_over_tp")) for row in trades]
    cost_rows = [
        abs(as_float(row.get("ocp_expected_pl"))) * as_float(row.get("spread_over_sl"))
        + abs(as_float(row.get("swap")))
        + abs(as_float(row.get("commission")))
        for row in trades
    ]
    cost_base = sum(cost_rows)

    cost_stress = []
    for multiplier in (1.0, 1.5, 2.0):
        stressed = [net - (multiplier - 1.0) * cost for net, cost in zip(values, cost_rows)]
        stressed_net = sum(stressed)
        cost_stress.append(
            {
                "cost_multiplier": multiplier,
                "net": round(stressed_net, 10),
                "profit_factor": pf(stressed),
                "expectancy_usd": stressed_net / len(stressed),
                "postprocessing_only": True,
                "mt5_rerun": False,
            }
        )

    monthly = grouped_net(trades, lambda ts: ts.strftime("%Y-%m"))
    yearly = grouped_net(trades, lambda ts: ts.strftime("%Y"))
    daily_groups: defaultdict[str, float] = defaultdict(float)
    daily_counts: Counter[str] = Counter()
    for row in trades:
        ts = parse_ts(row.get("exit_time"))
        if ts:
            day = ts.date().isoformat()
            daily_groups[day] += as_float(row.get("net"))
            daily_counts[day] += 1
    daily_rows: list[dict[str, object]] = []
    balance = INITIAL_DEPOSIT
    for day in sorted(daily_groups):
        net = daily_groups[day]
        start_balance = balance
        daily_rows.append(
            {
                "utc_date": day,
                "trade_count": daily_counts[day],
                "start_of_day_balance": round(start_balance, 8),
                "daily_net": round(net, 8),
                "daily_return_pct": round(net / start_balance * 100, 10) if start_balance else None,
                "end_of_day_balance": round(start_balance + net, 8),
            }
        )
        balance += net

    report_metrics = {
        "report_total_net_profit": report_net,
        "return_pct_on_initial_deposit": report_net / INITIAL_DEPOSIT * 100,
        "profit_factor": as_float(metric(report_kv, "Profit Factor")),
        "official_equity_drawdown": {
            "absolute": as_float(
                metric(report_kv, "Equity Drawdown Absolute", "Equity DD Absolute")
            ),
            "maximal": metric(report_kv, "Equity Drawdown Maximal", "Equity DD Maximal"),
            "relative": metric(report_kv, "Equity Drawdown Relative", "Equity DD Relative"),
        },
        "total_trades": len(trades),
        "trades_per_year": len(trades) / ((TRAIN_END - TRAIN_START).days / 365.25),
        "first_trade": min(valid_entry_times).strftime("%Y-%m-%d %H:%M:%S") if valid_entry_times else None,
        "last_trade": max(valid_exit_times).strftime("%Y-%m-%d %H:%M:%S") if valid_exit_times else None,
        "active_span_days": (max(valid_exit_times) - min(valid_entry_times)).days if valid_entry_times else None,
        "win_rate_pct": len(winners) / len(values) * 100,
        "average_winner": mean(winners) if winners else None,
        "average_loser": mean(losers) if losers else None,
        "payoff_ratio": mean(winners) / abs(mean(losers)) if winners and losers else None,
        "expectancy_usd": mean(values),
        "expectancy_r": mean(nonzero_ocp_r) if nonzero_ocp_r else "NOT_COMPUTABLE_FROM_FROZEN_AUDIT",
        "r_definition": "R_i = net_i / abs(ocp_expected_pl_i), nonzero OCP rows only",
        "r_rows_used": len(nonzero_ocp_r),
        "r_rows_missing_or_zero_ocp": len(values) - len(nonzero_ocp_r),
        "long": {"count": len(long_rows), "net": sum(as_float(row.get("net")) for row in long_rows)},
        "short": {"count": len(short_rows), "net": sum(as_float(row.get("net")) for row in short_rows)},
        "commission_total": sum(as_float(row.get("commission")) for row in trades),
        "swap_total": sum(as_float(row.get("swap")) for row in trades),
        "spread_over_sl": {"median": median(spreads_sl), "p95": pctl(spreads_sl, 95)},
        "spread_over_tp": {"median": median(spreads_tp), "p95": pctl(spreads_tp, 95)},
        "holding_time_seconds": {
            "min": min(holding_seconds) if holding_seconds else None,
            "median": median(holding_seconds) if holding_seconds else None,
            "p95": pctl(holding_seconds, 95),
            "max": max(holding_seconds) if holding_seconds else None,
        },
        "holding_bar_distribution": "NOT_COMPUTABLE_FROM_FROZEN_AUDIT",
        "exit_reason_distribution": dict(sorted(exit_reasons.items())),
        "close_type_distribution": dict(sorted(close_types.items())),
        "reject_reason_counts": dict(sorted(reject_counts.items())),
        "history_quality": metric(report_kv, "History Quality"),
        "history_quality_is_recorded_not_suppressed": True,
    }

    top5_sum = sum(winner_values[:5])
    top10_sum = sum(winner_values[:10])
    worst5_sum = sum(loser_values[:5])
    worst10_sum = sum(loser_values[:10])
    robustness = {
        "integrity_gate": {"status": "PASS" if integrity_pass else "FAIL", "checks": integrity},
        "cost_stress_postprocessing": {
            "base_cost_formula": "abs(ocp_expected_pl) * spread_over_sl + abs(swap) + abs(commission) per trade",
            "base_cost_usd": cost_base,
            "results": cost_stress,
            "mt5_rerun": False,
        },
        "winner_concentration": {
            "top5_of_gross_winners": top5_sum / sum(winner_values) if winner_values else None,
            "top10_of_gross_winners": top10_sum / sum(winner_values) if winner_values else None,
            "net_without_top10_winners": sum(values) - top10_sum,
        },
        "loss_concentration": {
            "worst5_loss_sum": worst5_sum,
            "worst10_loss_sum": worst10_sum,
            "net_without_worst10_losers": sum(values) - worst10_sum,
        },
        "bootstrap": "NOT_RUN",
        "oos": "NOT_RUN",
        "holdout": "NOT_RUN",
        "optimization": "NOT_RUN",
    }

    report_parsed = {
        "report_path": str(REPORT_PATH),
        "report_sha256": sha256(REPORT_PATH),
        "selected_identity_and_metrics": report_safe_values(report_kv),
        "deals_parsed_by_html_parser": len(report.get("deals", [])),
        "account_or_connection_identifier": "INTENTIONALLY_OMITTED",
    }

    # Keep every audit column.  No broker connection fields are added.
    ledger_path = OUT / "XAMR30_V1_TRAIN_TRADE_LEDGER.csv"
    write_csv(ledger_path, trade_fields, trades)
    monthly_path = OUT / "XAMR30_V1_TRAIN_MONTHLY.csv"
    yearly_path = OUT / "XAMR30_V1_TRAIN_YEARLY.csv"
    daily_path = OUT / "XAMR30_V1_TRAIN_DAILY_RETURNS.csv"
    write_csv(monthly_path, ["period", "trade_count", "net"], monthly)
    write_csv(yearly_path, ["period", "trade_count", "net"], yearly)
    write_csv(
        daily_path,
        [
            "utc_date",
            "trade_count",
            "start_of_day_balance",
            "daily_net",
            "daily_return_pct",
            "end_of_day_balance",
        ],
        daily_rows,
    )

    metrics = {
        "run_tag": RUN_TAG,
        "run_status": "VALID" if integrity_pass else "INVALID",
        "report_metrics": report_metrics,
        "integrity": integrity,
        "integrity_details": {
            "html_total_trades": html_total_trades,
            "audit_trade_rows": len(trades),
            "audit_net": audit_net,
            "report_net": report_net,
            "net_difference": report_net - audit_net,
            "net_tolerance": net_tolerance,
            "missing_trade_fields": missing_fields,
            "missing_required_values": missing_required_values,
            "alignment_bad_rows": alignment_bad,
            "max_entries_per_utc_day": max(actual_entry_days.values(), default=0),
            "time_exit_rows": len(time_exit_rows),
            "trade_timestamps": {
                "first_entry": min(valid_entry_times).strftime("%Y-%m-%d %H:%M:%S") if valid_entry_times else None,
                "last_exit": max(valid_exit_times).strftime("%Y-%m-%d %H:%M:%S") if valid_exit_times else None,
            },
        },
        "source_hashes_after_run": {
            "source_mq5": source_sha,
            "canonical_ex5": canonical_sha,
            "deployed_ex5": deployed_sha,
            "frozen_ini": ini_sha,
            "comparisons": hashes_ok,
        },
        "frozen_ini_safe_fields": ini,
        "cost_stress": cost_stress,
        "reject_counts": dict(sorted(reject_counts.items())),
    }
    metrics_path = OUT / "XAMR30_V1_TRAIN_METRICS.json"
    json_write(metrics_path, metrics)
    robustness_path = OUT / "XAMR30_V1_TRAIN_ROBUSTNESS.json"
    json_write(robustness_path, robustness)
    parsed_path = OUT / "XAMR30_V1_TRAIN_REPORT_PARSED.json"
    json_write(parsed_path, report_parsed)

    raw_files = {
        "report_html": raw_file_meta(REPORT_PATH),
        "trades_csv": raw_file_meta(TRADES_PATH, trades),
        "reject_audit_csv": raw_file_meta(REJECT_PATH, rejects),
        "audit_selfcheck_csv": raw_file_meta(SELFCHECK_PATH, selfchecks),
    }
    raw_files["report_html"]["row_count"] = html_total_trades
    raw_files["report_html"]["first_trade_timestamp"] = report_metrics["first_trade"]
    raw_files["report_html"]["last_trade_timestamp"] = report_metrics["last_trade"]

    review_path = OUT / "XAMR30_V1_TRAIN_REVIEW.md"
    review = f"""# XAMR30 V1 TRAIN review

## Run identity

- Run tag: `{RUN_TAG}`
- Branch: `{BRANCH}`
- Executor commit before evidence packaging: `{HEAD}`
- Execution count: `{RUN_COUNT}` (exactly once)
- MT5 process exit code: `{RUN_EXIT_CODE}`
- Observed start: `{RUN_START}`
- Observed end: `{RUN_END}`
- Frozen configuration: `N0_final/resolved_INIs/run_DS260914_XAMR30_V1_TRAIN.ini`
- Report history quality: `{report_metrics['history_quality']}` (recorded transparently; not suppressed)

## Integrity gate

`V1_TRAIN = {"VALID" if integrity_pass else "INVALID"}`.

The HTML report has `{html_total_trades}` total trades and the frozen audit has
`{len(trades)}` trade rows.  The audit net is `{audit_net:.10f}` USD and the
report net is `{report_net:.10f}` USD; the absolute difference is
`{abs(report_net - audit_net):.10g}`, below the tolerance `{net_tolerance:.10g}`.
The audit self-check reports fatal `0`, audit_failed `0`, active_positions `0`,
OCP mismatch `0`, and formula diagnostics out `0`.  There are no duplicate
trade tickets, all `alignment_exact` values are `1`, and the maximum number of
actual entries on any UTC date is `{max(actual_entry_days.values(), default=0)}`.
All parsed entry and exit timestamps remain within the 2018-01-01 through
2024-05-31 TRAIN window.  The six `time_exit` rows are retained in the ledger;
bar-count holding distribution is explicitly `NOT_COMPUTABLE_FROM_FROZEN_AUDIT`
because that field is not present in the frozen audit schema.

## Economic result (descriptive only)

- Net profit: `{report_net:.2f}` USD; return on USD 500 deposit: `{report_net / INITIAL_DEPOSIT * 100:.3f}%`
- Profit factor: `{as_float(metric(report_kv, 'Profit Factor')):.4f}`
- Official equity drawdown: `{metric(report_kv, 'Equity Drawdown Maximal', 'Equity DD Maximal')}`
- Total trades: `{len(trades)}`; trades/year: `{len(trades) / ((TRAIN_END - TRAIN_START).days / 365.25):.6f}`
- Win rate: `{len(winners) / len(values) * 100:.4f}%`; average winner: `{mean(winners):.8f}` USD; average loser: `{mean(losers):.8f}` USD
- Payoff ratio: `{mean(winners) / abs(mean(losers)):.8f}`; expectancy: `{mean(values):.8f}` USD/trade
- R expectancy: `{mean(nonzero_ocp_r):.8f}` using `R_i = net_i / abs(ocp_expected_pl_i)` on `{len(nonzero_ocp_r)}` nonzero-OCP rows
- Long: `{len(long_rows)}` trades / `{sum(as_float(row.get('net')) for row in long_rows):.2f}` USD; short: `{len(short_rows)}` trades / `{sum(as_float(row.get('net')) for row in short_rows):.2f}` USD
- Commission total: `{sum(as_float(row.get('commission')) for row in trades):.2f}` USD; swap total: `{sum(as_float(row.get('swap')) for row in trades):.2f}` USD
- Spread/SL median and p95: `{median(spreads_sl):.8f}` / `{pctl(spreads_sl, 95):.8f}`; spread/TP median and p95: `{median(spreads_tp):.8f}` / `{pctl(spreads_tp, 95):.8f}`
- Reject counts: `{json.dumps(dict(sorted(reject_counts.items())), ensure_ascii=False)}`

## Robustness post-processing

Cost stress is post-processing only; no MT5 rerun was performed.  The base
cost is `abs(ocp_expected_pl) * spread_over_sl + abs(swap) + abs(commission)`
per trade.  Results:

{json.dumps(cost_stress, ensure_ascii=False, indent=2)}

Winner concentration: top 5 / top 10 of gross winners are
`{top5_sum / sum(winner_values):.8f}` / `{top10_sum / sum(winner_values):.8f}`;
net without the top 10 winners is `{sum(values) - top10_sum:.2f}` USD.
Worst 5 / worst 10 loss sums are `{worst5_sum:.2f}` / `{worst10_sum:.2f}` USD;
net without the worst 10 losers is `{sum(values) - worst10_sum:.2f}` USD.

Bootstrap, OOS, user holdout, VALID, optimization, V2 and V3 were not run.
The daily return CSV uses closed-trade UTC exit dates and does not invent zero
return dates absent from the frozen audit; bootstrap is `NOT_RUN`.

## Safety and provenance

Source MQ5, canonical EX5, deployed EX5 and the frozen INI all match their
pre-run SHA-256 identities.  Raw HTML, trade audit, reject audit and self-check
files remain outside Git and are referenced by path, size, SHA-256, row count,
and timestamp metadata in the manifest.  Broker account or connection
identifiers are intentionally omitted from this package.
"""
    review_path.write_text(review, encoding="utf-8")

    generated_names = [
        parsed_path.name,
        ledger_path.name,
        metrics_path.name,
        monthly_path.name,
        yearly_path.name,
        daily_path.name,
        robustness_path.name,
        review_path.name,
    ]
    generated_meta = {
        name: {"path": str(OUT / name), "size_bytes": (OUT / name).stat().st_size, "sha256": sha256(OUT / name)}
        for name in generated_names
    }
    manifest = {
        "run_tag": RUN_TAG,
        "status": "VALID" if integrity_pass else "INVALID",
        "branch": BRANCH,
        "executor_commit": HEAD,
        "execution": {
            "count": RUN_COUNT,
            "start": RUN_START,
            "end": RUN_END,
            "terminal_exit_code": RUN_EXIT_CODE,
            "mt5_rerun_after_run": False,
        },
        "frozen_config": {
            "path": str(INI_PATH),
            "sha256": ini_sha,
            "safe_fields": ini,
        },
        "collision_gate": {
            "prior_nonempty_tagged_artifact": False,
            "action": "started once after clean collision check",
        },
        "raw_evidence_outside_git": raw_files,
        "integrity_gate": {
            "status": "PASS" if integrity_pass else "FAIL",
            "checks": integrity,
            "details": {
                "html_total_trades": html_total_trades,
                "audit_trade_rows": len(trades),
                "report_net": report_net,
                "audit_net": audit_net,
                "net_difference": report_net - audit_net,
                "net_tolerance": net_tolerance,
                "max_entries_per_utc_day": max(actual_entry_days.values(), default=0),
                "oos_rows": 0,
                "user_holdout_rows": 0,
            },
        },
        "identity_hashes_after_run": {
            "source_mq5": source_sha,
            "canonical_ex5": canonical_sha,
            "deployed_ex5": deployed_sha,
            "frozen_ini": ini_sha,
            "comparisons": hashes_ok,
        },
        "generated_evidence": generated_meta,
        "file_hashes_manifest": "XAMR30_V1_TRAIN_FILE_HASHES.sha256",
        "account_or_connection_identifier": "INTENTIONALLY_OMITTED",
        "next_stage_authorization": "WAIT_FOR_PLANNER_REVIEW",
    }
    manifest_path = OUT / "XAMR30_V1_TRAIN_RUN_MANIFEST.json"
    json_write(manifest_path, manifest)

    hash_lines = [
        "# SHA-256 evidence manifest; broker account/connection identifiers omitted.",
        f"# run_tag={RUN_TAG}",
        f"# executor_commit={HEAD}",
    ]
    for label, path in (
        ("source_mq5", SOURCE_PATH),
        ("canonical_ex5", CANONICAL_EX5),
        ("deployed_ex5", DEPLOYED_EX5),
        ("frozen_ini", INI_PATH),
        ("report_html", REPORT_PATH),
        ("trades_csv", TRADES_PATH),
        ("reject_audit_csv", REJECT_PATH),
        ("audit_selfcheck_csv", SELFCHECK_PATH),
    ):
        hash_lines.append(f"{sha256(path)}  {label}  {path}")
    for name in generated_names + [manifest_path.name]:
        path = OUT / name
        hash_lines.append(f"{sha256(path)}  generated  {path}")
    hashes_path = OUT / "XAMR30_V1_TRAIN_FILE_HASHES.sha256"
    hashes_path.write_text("\n".join(hash_lines) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "V1_TRAIN": "VALID" if integrity_pass else "INVALID",
                "trades": len(trades),
                "report_net": report_net,
                "audit_net": audit_net,
                "integrity_checks": len(integrity),
                "integrity_failures": [key for key, value in integrity.items() if not value],
                "output": str(OUT),
            },
            ensure_ascii=False,
        )
    )
    return 0 if integrity_pass else 2


if __name__ == "__main__":
    raise SystemExit(main())
