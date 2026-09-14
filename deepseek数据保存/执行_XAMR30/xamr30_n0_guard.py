#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""XAMR30 final pre-TRAIN N0 four-way dry-run guard.

The default mode only parses, compares, hashes, and writes evidence.  It does
not invoke MetaTrader or any economic execution process.  ``--init`` creates
the six planned, non-executed INIs and the source-derived static/manifest
artifacts; the default mode then validates those artifacts against the frozen
EA source.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[2]
FAM = REPO / "deepseek数据保存" / "执行_XAMR30"
SOURCE = REPO / "deepseek数据保存" / "mql5" / "dshtools" / "dsh_XAMR30.mq5"
CANONICAL_EX5 = FAM / "dsh_XAMR30_N1R3.ex5"
DEPLOYED_EX5 = Path(
    r"C:\Users\UIC\AppData\Roaming\MetaQuotes\Terminal\53785E099C927DB68A545C249CDBCE06\MQL5\Experts\dshtrend\dsh_XAMR30.ex5"
)
STATIC_PATH = REPO / "公共部分" / "XAMR30_static_inputs_final.md"
PLANNED_PATH = REPO / "公共部分" / "XAMR30_planned_runs.jsonl"
N0_DIR = FAM / "N0_final"
INI_DIR = N0_DIR / "resolved_INIs"
FINAL_SMOKE_JSON = FAM / "final_smoke_independent" / "final_smoke_independent.json"
R2_SUMMARY_JSON = FAM / "doublecalc_r2" / "XAMR30_doublecalc_R2_summary.json"
DATA_FREEZE = REPO / "公共部分" / "XAMR30_DATA_FREEZE_20260914_R4.md"
FINAL_GUARD_DOC = REPO / "公共部分" / "XAMR30_FINAL_PRETRAIN_GUARD_20260914.md"

EXPECTED_SOURCE_SHA = "CA5AD7339FE415CBC3BD2304B94C47E755B2A6292AA5A69FC1E34D5B7E72826C"
EXPECTED_EX5_SHA = "F374890F28022FCB88FA55BD34CD5BCE82DFB93A6C4EA549A3ACF34A60F658B2"
ALLOWED_DYNAMIC_INPUTS = {"InpRunTag", "InpZThreshold", "InpCrossAssetFilter"}
VARIANT_VALUES = {
    "V1": {"InpZThreshold": 1.5, "InpCrossAssetFilter": True},
    "V2": {"InpZThreshold": 1.5, "InpCrossAssetFilter": False},
    "V3": {"InpZThreshold": 2.0, "InpCrossAssetFilter": True},
}
RUNS = [(variant, role) for role in ("TRAIN", "VALID") for variant in ("V1", "V2", "V3")]

INPUT_RE = re.compile(
    r"(?m)^\s*input\s+(?P<type>string|long|int|double|bool)\s+"
    r"(?P<name>Inp[A-Za-z0-9_]+)\s*=\s*(?P<default>[^;]+);"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def clean_default(raw: str) -> str:
    return raw.split("//", 1)[0].strip()


def parse_literal(type_name: str, raw: str) -> Any:
    value = clean_default(raw)
    if type_name == "string":
        if value.startswith('"') and value.endswith('"'):
            return value[1:-1]
        return value
    if type_name == "bool":
        return value.lower() == "true"
    if type_name in ("long", "int"):
        return int(value)
    return float(value)


def format_value(type_name: str, value: Any) -> str:
    if type_name == "string":
        return str(value)
    if type_name == "bool":
        return "true" if bool(value) else "false"
    if type_name in ("long", "int"):
        return str(int(value))
    numeric = float(value)
    if numeric.is_integer():
        return f"{numeric:.1f}"
    return format(numeric, ".15g")


def values_equal(type_name: str, left: Any, right: Any) -> bool:
    if type_name == "double":
        try:
            return abs(float(left) - float(right)) <= 1e-12
        except (TypeError, ValueError):
            return False
    return left == right


def parse_source_inputs() -> tuple[str, list[dict[str, Any]]]:
    source_text = SOURCE.read_text(encoding="utf-8-sig")
    inputs: list[dict[str, Any]] = []
    for match in INPUT_RE.finditer(source_text):
        type_name = match.group("type")
        raw_default = clean_default(match.group("default"))
        inputs.append(
            {
                "name": match.group("name"),
                "type": type_name,
                "default": parse_literal(type_name, raw_default),
                "raw_default": raw_default,
            }
        )
    return source_text, inputs


def static_from_inputs(source_sha: str, inputs: list[dict[str, Any]]) -> str:
    lines = [
        "# XAMR30 Final Static Inputs (pre-TRAIN)",
        "",
        "This is a source-derived static table. It is a configuration freeze only; no MT5 economic run was executed.",
        "",
        f"- Strategy source SHA256: `{source_sha}`",
        f"- Strategy canonical N1R3 EX5 SHA256: `{EXPECTED_EX5_SHA}`",
        "- Allowed dynamic inputs only: `InpRunTag`, `InpZThreshold`, `InpCrossAssetFilter`.",
        "- All other values must equal the source default in every planned run.",
        "- `InpCrossAssetFilter=false` does not disable exact XAU availability; the source structural guard checks availability before the filter branch.",
        "",
        "## Source-parsed input interface",
        "",
        "| Input name | Type | Source default |",
        "|---|---|---|",
    ]
    for item in inputs:
        default = json.dumps(item["default"], ensure_ascii=False)
        lines.append(f"| `{item['name']}` | `{item['type']}` | `{default}` |")
    lines += [
        "",
        "## Variant values",
        "",
        "| Variant | InpZThreshold | InpCrossAssetFilter |",
        "|---|---:|---|",
        "| V1 | 1.5 | true |",
        "| V2 | 1.5 | false |",
        "| V3 | 2.0 | true |",
        "",
        "## Date semantics",
        "",
        "- TRAIN tester interval: `2018.01.01` through `2024.05.31`; Data Freeze TRAIN start month is `2018-01`.",
        "- VALID tester interval: `2024.06.01` through `2025.05.31`.",
        "- First common M30 bar: `2018.01.02 06:00`; this is data eligibility, not first signal or first trade.",
        "- Exposed OOS forbidden: `2025-06-01` through `2026-05-31`.",
        "- User holdout forbidden: `2026-06-01` through `2026-09-30`.",
        "",
    ]
    return "\n".join(lines)


def build_plan(source_inputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    defaults = {item["name"]: item["default"] for item in source_inputs}
    records: list[dict[str, Any]] = []
    for variant, role in RUNS:
        tag = f"DS260914_XAMR30_{variant}_{role}"
        values = dict(defaults)
        values["InpRunTag"] = tag
        values.update(VARIANT_VALUES[variant])
        is_train = role == "TRAIN"
        from_date = "2018.01.01" if is_train else "2024.06.01"
        to_date = "2024.05.31" if is_train else "2025.05.31"
        status = "planned" if is_train else "planned_if_train_pass"
        ini_name = f"run_{tag}.ini"
        report_name = f"{tag}.html"
        record = {
            "run_id": tag,
            "variant": variant,
            "role": role,
            "status": status,
            "run_tag": tag,
            "ini_path": (Path("deepseek数据保存") / "执行_XAMR30" / "N0_final" / "resolved_INIs" / ini_name).as_posix(),
            "report_path": (Path("deepseek数据保存") / "执行_XAMR30" / "N0_final" / "reports" / report_name).as_posix(),
            "audit_directory": f"dshtrend\\{tag}",
            "tester": {
                "Expert": r"dshtrend\dsh_XAMR30",
                "Symbol": "USDJPYm",
                "Period": "M30",
                "Model": 2,
                "Optimization": 0,
                "Deposit": 500,
                "Currency": "USD",
                "Leverage": "1:200",
                "Visual": 0,
                "FromDate": from_date,
                "ToDate": to_date,
                "Report": tag,
            },
            "date_semantics": {
                "tester_from_date": from_date,
                "tester_to_date": to_date,
                "allowed_data_interval": {"from": "2018-01" if is_train else "2024-06-01", "to": "2024-05" if is_train else "2025-05-31"},
                "first_common_m30_bar": "2018.01.02 06:00",
                "first_eligible_signal": "not asserted",
                "first_actual_trade": "not asserted",
            },
            "forbidden_exposed_oos": {"from": "2025-06-01", "to": "2026-05-31"},
            "forbidden_user_holdout": {"from": "2026-06-01", "to": "2026-09-30"},
            "strategy_source_sha256": EXPECTED_SOURCE_SHA,
            "strategy_ex5_sha256": EXPECTED_EX5_SHA,
            "resolved_inputs": values,
            "economic_execution": "NOT_RUN",
        }
        write_ini(record, source_inputs, INI_DIR / ini_name)
        records.append(record)
    return records


def write_ini(record: dict[str, Any], source_inputs: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tester = record["tester"]
    lines = [
        "[Common]",
        "Login=277335900",
        "Server=Exness-MT5Trial5",
        "KeepPrivate=1",
        "NewsEnable=0",
        "CertInstall=0",
        "[Experts]",
        "AllowLiveTrading=0",
        "AllowDllImport=0",
        "Enabled=1",
        "Account=0",
        "Profile=0",
        "[Tester]",
        f"Expert={tester['Expert']}",
        f"Symbol={tester['Symbol']}",
        f"Period={tester['Period']}",
        f"Model={tester['Model']}",
        f"Optimization={tester['Optimization']}",
        f"FromDate={tester['FromDate']}",
        f"ToDate={tester['ToDate']}",
        "ForwardMode=0",
        f"Deposit={tester['Deposit']}",
        f"Currency={tester['Currency']}",
        f"Leverage={tester['Leverage']}",
        "ExecutionMode=0",
        "Visual=0",
        f"Report={tester['Report']}",
        "ReplaceReport=1",
        "ShutdownTerminal=1",
        "[TesterInputs]",
    ]
    for item in source_inputs:
        value = record["resolved_inputs"][item["name"]]
        lines.append(f"{item['name']}={format_value(item['type'], value)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_static() -> dict[str, dict[str, Any]]:
    values: dict[str, dict[str, Any]] = {}
    if not STATIC_PATH.is_file():
        return values
    pattern = re.compile(r"^\|\s*`(?P<name>Inp[A-Za-z0-9_]+)`\s*\|\s*`(?P<type>[^`]+)`\s*\|\s*`(?P<default>[^`]*)`\s*\|$")
    for line in STATIC_PATH.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if not match:
            continue
        type_name = match.group("type")
        values[match.group("name")] = {
            "type": type_name,
            "default": parse_literal(type_name, match.group("default")),
        }
    return values


def parse_ini(path: Path) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    section = ""
    if not path.is_file():
        return result
    for raw_line in path.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith(";") or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            result.setdefault(section, {})
            continue
        if "=" in line and section:
            key, value = line.split("=", 1)
            result[section][key.strip()] = value.strip()
    return result


def date_value(value: str) -> dt.date:
    for fmt in ("%Y.%m.%d", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError(value)


def interval_overlaps(start: str, end: str, other_start: str, other_end: str) -> bool:
    left = date_value(start)
    right = date_value(end)
    other_left = date_value(other_start)
    other_right = date_value(other_end)
    return max(left, other_left) <= min(right, other_right)


def source_availability_check(source_text: str) -> dict[str, Any]:
    exact_declaration = source_text.find("bool exact = false")
    exact_match = source_text.find("if(nearestXau == jt)", exact_declaration)
    missing_branch = source_text.find("if(!exact)", exact_match)
    filter_branch = source_text.find("if(InpCrossAssetFilter)", missing_branch)
    ok = (
        "iBarShift(InpInfoSymbol, PERIOD_M30, jt, false)" in source_text
        and exact_declaration >= 0
        and exact_match > exact_declaration
        and missing_branch > exact_match
        and filter_branch > missing_branch
    )
    return {
        "check": "exact XAU availability precedes InpCrossAssetFilter branch",
        "pass": ok,
        "positions": {
            "exact_declaration": exact_declaration,
            "exact_match": exact_match,
            "missing_branch": missing_branch,
            "filter_branch": filter_branch,
        },
    }


def check_input_map(source_inputs: list[dict[str, Any]], static: dict[str, dict[str, Any]], record: dict[str, Any], ini: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    source_names = [item["name"] for item in source_inputs]
    static_names = list(static)
    resolved = record.get("resolved_inputs") or {}
    ini_inputs = ini.get("TesterInputs") or {}
    add = lambda name, ok, detail: checks.append({"name": name, "pass": bool(ok), "detail": detail})

    add("source/static name set exact", set(source_names) == set(static_names), f"source={len(source_names)} static={len(static_names)}")
    add("static/manifest name set exact", set(source_names) == set(resolved), f"source={len(source_names)} manifest={len(resolved)}")
    add("static/INI name set exact", set(source_names) == set(ini_inputs), f"source={len(source_names)} ini={len(ini_inputs)}")

    source_by_name = {item["name"]: item for item in source_inputs}
    ini_typed: dict[str, Any] = {}
    ini_parse_ok = True
    for name in source_names:
        item = source_by_name[name]
        if name not in ini_inputs:
            ini_parse_ok = False
            continue
        try:
            ini_typed[name] = parse_literal(item["type"], ini_inputs[name])
        except Exception:
            ini_parse_ok = False
    add("INI values parse by source types", ini_parse_ok, "typed parse")

    manifest_vs_ini = all(
        name in ini_typed and values_equal(source_by_name[name]["type"], resolved.get(name), ini_typed.get(name))
        for name in source_names
    )
    add("INI/manifest resolved values exact", manifest_vs_ini, "all source inputs")

    static_values_ok = all(
        name in static
        and static[name]["type"] == source_by_name[name]["type"]
        and values_equal(source_by_name[name]["type"], static[name]["default"], source_by_name[name]["default"])
        for name in source_names
    )
    add("source/static type and default exact", static_values_ok, "source-derived table")

    fixed_bad = []
    unexpected = []
    for name in source_names:
        if name not in resolved:
            fixed_bad.append(name)
            continue
        source_default = source_by_name[name]["default"]
        if name not in ALLOWED_DYNAMIC_INPUTS:
            if not values_equal(source_by_name[name]["type"], resolved[name], source_default):
                fixed_bad.append(name)
        elif not values_equal(source_by_name[name]["type"], resolved[name], ini_typed.get(name)):
            unexpected.append(name)
    add("all fixed inputs equal source defaults", not fixed_bad, f"bad={fixed_bad or 'none'}")
    add("variant overrides only whitelist", not unexpected, f"bad={unexpected or 'none'}")

    expected_variant = VARIANT_VALUES[record["variant"]]
    variant_ok = all(
        name in resolved and values_equal(source_by_name[name]["type"], resolved[name], value)
        for name, value in expected_variant.items()
    )
    add(f"{record['variant']} exact dynamic values", variant_ok, json.dumps(expected_variant, ensure_ascii=False))
    return checks


def run_guard() -> tuple[dict[str, Any], int]:
    source_text, source_inputs = parse_source_inputs()
    source_sha = sha256(SOURCE) if SOURCE.is_file() else "MISSING"
    canonical_sha = sha256(CANONICAL_EX5) if CANONICAL_EX5.is_file() else "MISSING"
    deployed_sha = sha256(DEPLOYED_EX5) if DEPLOYED_EX5.is_file() else "MISSING"
    static = parse_static()
    records = []
    if PLANNED_PATH.is_file():
        for line in PLANNED_PATH.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))

    global_checks: list[dict[str, Any]] = []
    add_global = lambda name, ok, detail: global_checks.append({"name": name, "pass": bool(ok), "detail": detail})
    add_global("strategy source hash", source_sha == EXPECTED_SOURCE_SHA, source_sha)
    add_global("canonical strategy EX5 hash", canonical_sha == EXPECTED_EX5_SHA, canonical_sha)
    add_global("deployed strategy EX5 hash", deployed_sha == EXPECTED_EX5_SHA, deployed_sha)
    add_global("source input parse nonempty", bool(source_inputs), str(len(source_inputs)))
    add_global("source input names unique", len({item["name"] for item in source_inputs}) == len(source_inputs), str(len(source_inputs)))
    add_global("planned manifest exists", PLANNED_PATH.is_file(), str(PLANNED_PATH))
    add_global("planned run count = 6", len(records) == 6, str(len(records)))
    add_global("planned run tags unique", len({record.get("run_tag") for record in records}) == len(records), "run tags")
    add_global("planned report paths unique", len({record.get("report_path") for record in records}) == len(records), "reports")
    add_global("planned audit dirs unique", len({record.get("audit_directory") for record in records}) == len(records), "audit dirs")
    add_global("source/static table exists", STATIC_PATH.is_file(), str(STATIC_PATH))
    add_global("static input count exact", len(static) == len(source_inputs), f"source={len(source_inputs)} static={len(static)}")

    data_freeze_text = DATA_FREEZE.read_text(encoding="utf-8") if DATA_FREEZE.is_file() else ""
    add_global("DATA_FREEZE = PASS", "DATA_FREEZE = `PASS`" in data_freeze_text or "DATA_FREEZE = PASS" in data_freeze_text, "Data Freeze report")
    add_global("TRAIN start month = 2018-01", "TRAIN start month = `2018-01`" in data_freeze_text or "TRAIN start month = 2018-01" in data_freeze_text, "Data Freeze report")

    smoke: dict[str, Any] = {}
    if FINAL_SMOKE_JSON.is_file():
        smoke = json.loads(FINAL_SMOKE_JSON.read_text(encoding="utf-8"))
    smoke_summary = smoke.get("summary") or {}
    add_global("FINAL_SMOKE_INDEPENDENT = PASS", smoke.get("FINAL_SMOKE_INDEPENDENT") == "PASS", str(smoke.get("FINAL_SMOKE_INDEPENDENT")))
    add_global("independent smoke hold checks = 37/37", smoke_summary.get("hold_bar_pass") == 37 and smoke_summary.get("hold_bar_checks") == 37, json.dumps(smoke_summary, ensure_ascii=False))

    r2: dict[str, Any] = {}
    if R2_SUMMARY_JSON.is_file():
        r2 = json.loads(R2_SUMMARY_JSON.read_text(encoding="utf-8"))
    add_global("SIGNAL_DOUBLECALC_R2 = PASS", r2.get("SIGNAL_DOUBLECALC_R2") == "PASS", str(r2.get("SIGNAL_DOUBLECALC_R2")))
    availability = source_availability_check(source_text)
    add_global("exact XAU availability mask before filter branch", availability["pass"], json.dumps(availability["positions"]))

    run_results: list[dict[str, Any]] = []
    for record in records:
        ini_path = REPO / record.get("ini_path", "")
        ini = parse_ini(ini_path)
        checks = check_input_map(source_inputs, static, record, ini)
        tester = ini.get("Tester") or {}
        expected_tester = record.get("tester") or {}
        required_tester = {
            "Expert": r"dshtrend\dsh_XAMR30",
            "Symbol": "USDJPYm",
            "Period": "M30",
            "Model": "2",
            "Optimization": "0",
            "Deposit": "500",
            "Currency": "USD",
            "Leverage": "1:200",
            "Visual": "0",
        }
        for key, expected in required_tester.items():
            actual = tester.get(key, "")
            checks.append({"name": f"Tester {key} frozen", "pass": actual == str(expected), "detail": f"actual={actual} expected={expected}"})
        for key in ("FromDate", "ToDate", "Report"):
            checks.append({"name": f"Tester {key} matches manifest", "pass": tester.get(key) == str(expected_tester.get(key)), "detail": f"actual={tester.get(key)} expected={expected_tester.get(key)}"})
        checks.append({"name": "planned INI exists", "pass": ini_path.is_file(), "detail": str(ini_path)})
        checks.append({"name": "economic execution flag is NOT_RUN", "pass": record.get("economic_execution") == "NOT_RUN", "detail": str(record.get("economic_execution"))})

        date_bad = []
        from_date = expected_tester.get("FromDate", "")
        to_date = expected_tester.get("ToDate", "")
        for label, interval in (("exposed_oos", record.get("forbidden_exposed_oos", {})), ("user_holdout", record.get("forbidden_user_holdout", {}))):
            try:
                if interval_overlaps(from_date, to_date, interval["from"], interval["to"]):
                    date_bad.append(label)
            except Exception:
                date_bad.append(f"{label}:parse")
        checks.append({"name": "forbidden-date overlap = 0", "pass": not date_bad, "detail": str(date_bad or "none")})

        run_results.append(
            {
                "run_id": record.get("run_id"),
                "variant": record.get("variant"),
                "role": record.get("role"),
                "ini_path": str(ini_path),
                "checks": checks,
                "mismatch_count": sum(1 for item in checks if not item["pass"]),
            }
        )

    # Variant equivalence: fixed inputs and frozen tester fields must match
    # across V1/V2/V3 within each role, with only the explicit dynamic values
    # and run identity differing.
    signatures: dict[tuple[str, str], tuple[Any, ...]] = {}
    for record in records:
        values = record.get("resolved_inputs") or {}
        fixed_signature = tuple((key, json.dumps(values.get(key), sort_keys=True)) for key in sorted(values) if key not in ALLOWED_DYNAMIC_INPUTS)
        tester = record.get("tester") or {}
        tester_signature = tuple((key, str(tester.get(key))) for key in sorted(tester) if key not in {"FromDate", "ToDate", "Report"})
        signatures[(record.get("role"), record.get("variant"))] = (fixed_signature, tester_signature)
    train_sigs = [signatures.get(("TRAIN", variant)) for variant in ("V1", "V2", "V3")]
    valid_sigs = [signatures.get(("VALID", variant)) for variant in ("V1", "V2", "V3")]
    global_checks.append({"name": "all TRAIN configs otherwise identical", "pass": len(set(train_sigs)) == 1 and None not in train_sigs, "detail": "fixed inputs/tester core"})
    global_checks.append({"name": "all VALID configs otherwise identical", "pass": len(set(valid_sigs)) == 1 and None not in valid_sigs, "detail": "fixed inputs/tester core"})
    for variant in ("V1", "V2", "V3"):
        train = next((record for record in records if record.get("role") == "TRAIN" and record.get("variant") == variant), None)
        valid = next((record for record in records if record.get("role") == "VALID" and record.get("variant") == variant), None)
        train_inputs = (train or {}).get("resolved_inputs") or {}
        valid_inputs = (valid or {}).get("resolved_inputs") or {}
        train_without_run_tag = {key: value for key, value in train_inputs.items() if key != "InpRunTag"}
        valid_without_run_tag = {key: value for key, value in valid_inputs.items() if key != "InpRunTag"}
        same_inputs = bool(train and valid and train_without_run_tag == valid_without_run_tag and set(train_inputs) == set(valid_inputs))
        global_checks.append({"name": f"{variant} TRAIN/VALID inputs identical", "pass": bool(same_inputs), "detail": "only date/identity changes"})

    role_counts = {role: sum(1 for record in records if record.get("role") == role) for role in ("TRAIN", "VALID")}
    global_checks.append({"name": "TRAIN records = 3", "pass": role_counts["TRAIN"] == 3, "detail": str(role_counts["TRAIN"])})
    global_checks.append({"name": "VALID conditional records = 3", "pass": role_counts["VALID"] == 3 and all(record.get("status") == "planned_if_train_pass" for record in records if record.get("role") == "VALID"), "detail": str(role_counts["VALID"])})

    all_checks = global_checks + [check for result in run_results for check in result["checks"]]
    n0_status = "PASS" if all(check["pass"] for check in all_checks) else "FAIL"
    mismatch_count = sum(1 for check in all_checks if not check["pass"])
    n0 = {
        "N0_FOURWAY": n0_status,
        "NO_MT5_ECONOMIC_EXECUTION": True,
        "strategy_source_sha256": source_sha,
        "strategy_canonical_ex5_sha256": canonical_sha,
        "strategy_deployed_ex5_sha256": deployed_sha,
        "parsed_source_inputs": len(source_inputs),
        "planned_runs": len(records),
        "fourway_mismatch_count": mismatch_count,
        "forbidden_date_overlaps": sum(1 for check in all_checks if check["name"] == "forbidden-date overlap = 0" and not check["pass"]),
        "availability_mask_check": availability,
        "global_checks": global_checks,
        "run_results": run_results,
        "R2_status": r2.get("SIGNAL_DOUBLECALC_R2"),
        "FINAL_SMOKE_INDEPENDENT": smoke.get("FINAL_SMOKE_INDEPENDENT"),
    }
    N0_DIR.mkdir(parents=True, exist_ok=True)
    (N0_DIR / "XAMR30_N0_fourway.json").write_text(json.dumps(n0, ensure_ascii=False, indent=2), encoding="utf-8")

    guard_lines = [
        "# XAMR30 N0 Guard Report",
        "",
        "- Dry-run only: parses, compares, hashes, validates, and writes evidence.",
        "- **NO MT5 ECONOMIC EXECUTION**; no terminal or tester was started.",
        "",
        f"- N0_FOURWAY: **{n0_status}**",
        f"- Parsed source inputs: **{len(source_inputs)}**",
        f"- Planned runs: **{len(records)}**",
        f"- Four-way mismatch count: **{mismatch_count}**",
        f"- Forbidden-date overlaps: **{n0['forbidden_date_overlaps']}**",
        f"- Source SHA: `{source_sha}`",
        f"- Canonical EX5 SHA: `{canonical_sha}`",
        f"- Deployed EX5 SHA: `{deployed_sha}`",
        "",
        "## Global checks",
        "",
        "| Check | Result | Detail |",
        "|---|---|---|",
    ]
    for item in global_checks:
        guard_lines.append(f"| {item['name']} | {'PASS' if item['pass'] else 'FAIL'} | {str(item['detail']).replace('|', '\\|')} |")
    guard_lines += ["", "## Per-run checks", ""]
    for result in run_results:
        guard_lines += [f"### {result['run_id']}", "", "| Check | Result | Detail |", "|---|---|---|"]
        for item in result["checks"]:
            guard_lines.append(f"| {item['name']} | {'PASS' if item['pass'] else 'FAIL'} | {str(item['detail']).replace('|', '\\|')} |")
        guard_lines.append("")
    (N0_DIR / "XAMR30_N0_guard_report.md").write_text("\n".join(guard_lines).rstrip() + "\n", encoding="utf-8")

    fourway_lines = [
        "# XAMR30 N0 Four-Way Report",
        "",
        "A = source input interface; B = static table; C = resolved INI; D = planned manifest.",
        "",
        f"- N0_FOURWAY: **{n0_status}**",
        f"- Source input count: {len(source_inputs)}",
        f"- Planned records: {len(records)} (TRAIN=3, VALID conditional=3)",
        f"- Four-way mismatch count: {mismatch_count}",
        "- Variant overrides: only `InpRunTag`, `InpZThreshold`, `InpCrossAssetFilter`.",
        "- Availability invariant: exact XAU timestamp availability is checked before the filter branch, including V2.",
        "- Forbidden exposed-OOS/user-holdout overlap: zero required.",
        "- No economic execution occurred.",
        "",
        "## Planned runs",
        "",
        "| Run | Variant | Role | Status |",
        "|---|---|---|---|",
    ]
    for record in records:
        result = next(item for item in run_results if item["run_id"] == record["run_id"])
        fourway_lines.append(f"| {record['run_id']} | {record['variant']} | {record['role']} | {'PASS' if result['mismatch_count'] == 0 else 'FAIL'} |")
    (N0_DIR / "XAMR30_N0_fourway_report.md").write_text("\n".join(fourway_lines) + "\n", encoding="utf-8")

    final_smoke_status = smoke.get("FINAL_SMOKE_INDEPENDENT") == "PASS"
    data_freeze_status = any(item["name"] == "DATA_FREEZE = PASS" and item["pass"] for item in global_checks)
    provenance_status = source_sha == EXPECTED_SOURCE_SHA and canonical_sha == EXPECTED_EX5_SHA and deployed_sha == EXPECTED_EX5_SHA
    r2_status = r2.get("SIGNAL_DOUBLECALC_R2") == "PASS"
    final_status = "PASS" if all((data_freeze_status, provenance_status, r2_status, final_smoke_status, n0_status == "PASS")) else "FAIL"
    final_lines = [
        "# XAMR30 FINAL PRE-TRAIN GUARD · 2026-09-14",
        "",
        "This is the final engineering guard before any economic run. It does not authorize TRAIN/VALID.",
        "",
        "| Gate | Status |",
        "|---|---|",
        f"| DATA_FREEZE | {'PASS' if data_freeze_status else 'FAIL'} |",
        f"| STRATEGY_PROVENANCE | {'PASS' if provenance_status else 'FAIL'} |",
        f"| SIGNAL_DOUBLECALC_R2 | {'PASS' if r2_status else 'FAIL'} |",
        f"| FINAL_SMOKE_INDEPENDENT | {'PASS' if final_smoke_status else 'FAIL'} |",
        f"| N0_FOURWAY | {n0_status} |",
        f"| **FINAL_PRETRAIN_GUARD** | **{final_status}** |",
        "",
        "## Frozen identities",
        "",
        f"- Strategy source SHA256: `{source_sha}`",
        f"- Canonical/deployed EX5 SHA256: `{canonical_sha}` / `{deployed_sha}`",
        f"- Parsed source inputs: `{len(source_inputs)}`",
        f"- Planned runs: `{len(records)}`; TRAIN=3, VALID conditional=3",
        "- Exact XAU availability mask is invariant before the V1/V2/V3 filter branch.",
        "- Tester intervals and forbidden exposed-OOS/user-holdout intervals are checked in the N0 manifest.",
        "",
        "## Explicit non-actions",
        "",
        "- `dsh_XAMR30.mq5` was not modified.",
        "- The strategy EX5 was not recompiled or replaced.",
        "- Preregistration, Data Freeze, Double-Calc R1/R2, and the historical smoke verifier were not modified or overwritten.",
        "- No V1/V2/V3 TRAIN, bootstrap, VALID, exposed OOS, user holdout, capital sensitivity, Route B, regime detection, strategy combination, or ML run was executed.",
        "- No economic result was read for strategy judgment.",
        "",
    ]
    FINAL_GUARD_DOC.write_text("\n".join(final_lines), encoding="utf-8")
    return n0, 0 if n0_status == "PASS" and final_status == "PASS" else 1


def init_artifacts() -> int:
    source_text, source_inputs = parse_source_inputs()
    source_sha = sha256(SOURCE)
    STATIC_PATH.write_text(static_from_inputs(source_sha, source_inputs), encoding="utf-8")
    records = build_plan(source_inputs)
    PLANNED_PATH.write_text("\n".join(json.dumps(record, ensure_ascii=False, separators=(",", ":")) for record in records) + "\n", encoding="utf-8")
    print(json.dumps({"generated": True, "source_inputs": len(source_inputs), "planned_runs": len(records), "economic_execution": "NOT_RUN"}, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--init", action="store_true", help="generate source-derived static/manifest/INI plan; never runs MT5")
    args = parser.parse_args()
    if args.init:
        return init_artifacts()
    _, code = run_guard()
    return code


if __name__ == "__main__":
    sys.exit(main())
