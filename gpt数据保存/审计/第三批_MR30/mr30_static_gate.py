#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Static/provenance gate for the pre-registered MR30 family.

This script is deliberately read-only.  It validates the source, compiler log,
and six planned MT5 INIs, then prints a JSON result.  It never starts MT5 and
never consumes any market data.
"""
from __future__ import annotations

import configparser
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "deepseek数据保存" / "执行_第三批" / "stage3_family_preregistration" / "dsh_MR30.mq5"
EX5 = SRC.with_suffix(".ex5")
COMPILE_LOG = ROOT / "gpt数据保存" / "审计" / "第三批_R4离线更正" / "compile_MR30.log"
INI_DIR = ROOT / "gpt数据保存" / "mt5_runs" / "mr30"

EXPECTED_INPUTS = [
    "InpRiskPct", "InpUseEquityForRisk", "InpMaxLot", "InpAllowMinLotOvershoot",
    "InpMinLotMaxRiskPct", "InpMAPeriod", "InpSigmaPeriod", "InpEntrySigma",
    "InpNeedReenter", "InpAllowLong", "InpAllowShort", "InpTP_ATR", "InpSL_ATR",
    "InpMaxBarsInTrade", "InpUseVolRegime", "InpVolLookback", "InpVolPctLow",
    "InpVolPctHigh", "InpATRPeriod", "InpMagic", "InpRunTag", "InpWriteAudit",
    "InpSlippagePoints", "InpLatencyTicks", "InpTestEndDate", "InpCloseAtEndHour",
    "InpVerboseLog",
]
TAGS = [
    "DS260913_MR30_V1_TRAIN", "DS260913_MR30_V1_VALID",
    "DS260913_MR30_V2_TRAIN", "DS260913_MR30_V2_VALID",
    "DS260913_MR30_V3_TRAIN", "DS260913_MR30_V3_VALID",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest().upper()


def strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//[^\r\n]*", "", text)


def parse_input_names(text: str) -> list[str]:
    names: list[str] = []
    for line in text.splitlines():
        m = re.match(r"\s*input\s+(?:\w+\s+)?(\w+)\s*=", line)
        if m:
            names.append(m.group(1))
    return names


def load_ini(path: Path) -> configparser.ConfigParser:
    c = configparser.ConfigParser(interpolation=None, strict=False)
    c.optionxform = str
    with path.open(encoding="utf-8-sig") as f:
        c.read_file(f)
    return c


def read_text_auto(path: Path) -> str:
    """Read ordinary UTF-8 files and MetaEditor UTF-16 log files."""
    raw = path.read_bytes()
    if b"\x00" in raw[:256]:
        for enc in ("utf-16", "utf-16-le", "utf-16-be"):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                pass
    return raw.decode("utf-8-sig", errors="replace")


def check() -> dict:
    out: dict = {"ok": True, "checks": {}, "errors": [], "warnings": []}

    def require(name: str, condition: bool, detail: str = "") -> None:
        out["checks"][name] = {"ok": bool(condition), "detail": detail}
        if not condition:
            out["ok"] = False
            out["errors"].append(f"{name}: {detail}")

    require("source_exists", SRC.is_file(), str(SRC))
    require("ex5_exists", EX5.is_file() and EX5.stat().st_size > 0, str(EX5))
    require("compile_log_exists", COMPILE_LOG.is_file(), str(COMPILE_LOG))
    source = SRC.read_text(encoding="utf-8-sig") if SRC.is_file() else ""
    code = strip_comments(source)
    log = read_text_auto(COMPILE_LOG) if COMPILE_LOG.is_file() else ""
    if SRC.is_file():
        out["source_sha256"] = sha256(SRC)
        out["source_bytes"] = SRC.stat().st_size
    if EX5.is_file():
        out["ex5_sha256"] = sha256(EX5)
        out["ex5_bytes"] = EX5.stat().st_size

    require("compile_zero_errors", bool(re.search(r"Result:\s*0 errors", log)), "compiler Result line")
    require("compile_zero_warnings", bool(re.search(r"Result:\s*0 errors,\s*0 warnings", log)), "compiler Result line")

    names = parse_input_names(source)
    require("input_schema_exact", names == EXPECTED_INPUTS, f"got={names!r}")
    required_fragments = {
        "symbol_guard": 'if(_Symbol != "BTCUSDm")',
        "period_guard": "if(Period() != PERIOD_M1)",
        "tag_guard": "if(!IsPreregisteredTag())",
        "risk_guard": "InpRiskPct != 1.5",
        "min_lot_guard": "InpAllowMinLotOvershoot",
        "latency_guard": "InpLatencyTicks != 0",
        "audit_guard": "!InpWriteAudit",
        "date_guard": "InpTestEndDate !=",
        "variant_guard": "DS260913_MR30_V3_",
    }
    for k, frag in required_fragments.items():
        require(k, frag in source, frag)

    forbidden = {
        "sleep": r"\bSleep\s*\(",
        "latency_ms_input": r"InpLatencyMs",
        "position_modify": r"\bPositionModify\s*\(",
        "grid_function": r"\b(?:Grid|Martingale)\b",
        "trailing_stop_function": r"\b(?:Trailing|TrailWinner)\b",
    }
    for k, pat in forbidden.items():
        require(f"forbidden_{k}_absent", not re.search(pat, code, re.I), pat)

    require("only_m1_copyrates", "CopyRates(_Symbol, PERIOD_M1" in code and "PERIOD_M30" not in code,
            "M1 aggregation only")
    require("drops_incomplete_bucket", "Drop the open/current bucket" in source and "ArrayResize(c, nAll - 1)" in code,
            "completed M30 bars only")
    require("v3_lookback_excludes_signal_bar", "for(int i = first; i < last; i++)" in code,
            "trailing ATR percentile distribution")
    require("dedup_after_write", code.find("RememberDealAfterWrite(dealTicket)") > code.find("uint wrote = FileWrite(g_auditFh"),
            "ticket remembered only after successful FileWrite")
    require("filewrite_uses_byte_sentinel", "if(n == 0)" in code and "if(wrote == 0)" in code,
            "FileWrite byte-count semantics")
    require("unique_audit_header", "\"entry_time\",\"exit_time\"" in source and source.count('"entry_time"') == 1,
            "one entry_time column")
    require("ocp_and_formula_audit", "OrderCalcProfit" in code and "formulaDiff" in code,
            "four-way P&L evidence fields")
    require("identifier_not_ticket_fallback", "g_positionIdentifier" in code and "pid == g_positionTicket" not in code,
            "position identifier is distinct from position ticket")

    paths = sorted(INI_DIR.glob("DS260913_MR30_*.ini")) if INI_DIR.is_dir() else []
    require("six_planned_inis", [p.stem for p in paths] == TAGS, f"got={[p.stem for p in paths]!r}")
    ini_records = []
    for p in paths:
        try:
            c = load_ini(p)
            tester = c["Tester"]
            inp = c["TesterInputs"]
            tag = inp.get("InpRunTag", "")
            expected_role = "TRAIN" if tag.endswith("_TRAIN") else "VALID"
            expected_from = "2018.02.09" if expected_role == "TRAIN" else "2024.06.01"
            expected_to = "2024.05.31" if expected_role == "TRAIN" else "2025.05.31"
            expected_v = re.search(r"_V([123])_", tag)
            v = expected_v.group(1) if expected_v else "?"
            checks = {
                "tag_matches_filename": p.stem == tag,
                "symbol": tester.get("Symbol") == "BTCUSDm",
                "period": tester.get("Period") == "M1",
                "model": tester.get("Model") == "2",
                "optimization_off": tester.get("Optimization") == "0",
                "deposit": tester.get("Deposit") == "500",
                "currency": tester.get("Currency") == "USD",
                "from": tester.get("FromDate") == expected_from,
                "to": tester.get("ToDate") == expected_to,
                "expert": tester.get("Expert") == r"dshtrend\dsh_MR30",
                "risk": inp.get("InpRiskPct") == "1.5",
                "no_overshoot": inp.get("InpAllowMinLotOvershoot") == "false",
                "ticks_zero": inp.get("InpLatencyTicks") == "0",
                "end_date": inp.get("InpTestEndDate") == expected_to,
                "tp_variant": inp.get("InpTP_ATR") == ({"1": "1.5", "2": "2.5", "3": "1.5"}.get(v, "?")),
                "regime_variant": inp.get("InpUseVolRegime") == ("true" if v == "3" else "false"),
            }
            unknown = sorted(set(inp) - set(EXPECTED_INPUTS))
            checks["no_unknown_inputs"] = not unknown
            ini_records.append({"path": str(p), "tag": tag, "variant": v, "checks": checks,
                                "unknown_inputs": unknown, "sha256": sha256(p)})
            for k, ok in checks.items():
                require(f"{p.stem}_{k}", ok, f"{p.name}: {k}")
        except Exception as exc:  # malformed INI is a hard failure
            require(f"{p.stem}_parse", False, repr(exc))

    out["inis"] = ini_records
    # Explicit exposure guards, independent of the per-file checks.
    for p in paths:
        raw = p.read_text(encoding="utf-8-sig", errors="replace")
        require(f"{p.stem}_no_holdout", "2026.06" not in raw and "2026.07" not in raw and "2026.08" not in raw and "2026.09" not in raw,
                "user holdout must not appear")
        require(f"{p.stem}_no_exposed_oos", "2025.06" not in raw and "2026.05" not in raw,
                "exposed OOS must not appear")

    return out


if __name__ == "__main__":
    result = check()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ok"] else 1)
