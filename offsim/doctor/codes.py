"""Stable failure codes for the gates (docs/SYSTEM_PLAN.md 3.2) and the classifier that maps a report to one code.

A code is attached by `offsim.pipeline` to every failing gate entry (`report["gates"][g]["code"]`). `classify` reads that
field first; for reports written before the field existed it falls back to the gate name and the detail text, so old
reports keep working. Pure functions, no imports from the rest of offsim (pipeline imports this module).

    classify(report)                       -> code of the first failing gate (None when nothing failed)
    classify(gate_entry, gate="3_contract") -> code of one entry
    classify("some error text")            -> code from the text
    code_for_gate("0_provenance", detail)  -> what pipeline.stop() records
"""
from __future__ import annotations

import re

# code -> (gate it comes from, one-line meaning)
CODES = {
    "G0-SRC-MISSING": ("0_provenance", "a scenario value has neither src (page/table) nor assumption: true"),
    "G0-CLASS-UNSUPPORTED": ("0_provenance", "the problem class is handled by no registered solver or engine (or a tool raised Unsupported)"),
    "G0-TOOL-UNAVAILABLE": ("0_provenance", "the chosen solver/engine is unknown or does not import"),
    "G0-TOOL-MISMATCH": ("0_provenance", "the chosen solver/engine exists but does not handle this problem class or validation"),
    "G0-DATA-MISSING": ("0_provenance", "world, metocean, gtfs, entur or ais data the scenario needs is absent (fetch hint recorded)"),
    "G1-PLAN-INFEASIBLE": ("1_plan", "the solver failed, or its plan fails the outside re-check (served once, capacity, vehicles)"),
    "G1B-GAP": ("1b_exact", "heuristic objective is further from the exact objective/bound than gap_tol (or the exact solve errored)"),
    "G2-REPLAY-DRIFT": ("2_replay_equals_plan", "the simulated replay does not reproduce the plan (distance/cost) or the engine could not replay it"),
    "G3-SPEED": ("3_contract", "a leg exceeds the agent's vmax"),
    "G3-TELEPORT": ("3_contract", "position jump with zero elapsed time"),
    "G3-LAND-CROSSING": ("3_contract", "a sea leg crosses land"),
    "G3-CAPACITY": ("3_contract", "load outside [0, capacity]"),
    "G3-STATE": ("3_contract", "bookkeeping: moves while stationary, time runs backwards"),
    "G3E-ENSEMBLE": ("3e_ensemble", "an ensemble run failed the contract or an ensemble member could not run"),
    "G4-KPI-MISMATCH": ("4_paper", "measured KPIs are outside the paper's tolerance (status 'did not reproduce')"),
    "G4B-AIS": ("4b_ais", "simulated speeds/port-call dwell disagree with the AIS calibration, or nothing was comparable"),
    "G4C-ENTUR": ("4c_entur", "timetable replay disagrees with observed Entur vehicle positions"),
    "QA-ASSET-DIM": ("asset-qa", "a CAD asset's solid disagrees with its declared dimensions, or required dims are missing"),
    "VIS-GATE": ("visual-gate", "a rendered frame fails offsim.cinema.visual_gate: ink balance, edge density, stroke width, palette, accent share, text contrast, type scale or safe margins"),
    "DATA-HOST-TIMEOUT": ("data", "an external data host timed out, rate-limited (429) or did not answer"),
    "DATA-SCHEMA": ("data", "a file, table or API answer does not have the shape the code expects"),
    "CI-ENV": ("ci", "the runner/workspace environment lacks a system library, display or package index"),
    "UNKNOWN": ("-", "no rule matches: diagnose by hand, then add a playbook and a lesson"),
}

# contract violation kind (offsim.contract.validate) -> code. `time` (time goes backwards) is bookkeeping; `schema` is the shape
# of the trajectory table, so it is a data-shape failure, not physics.
CONTRACT_KIND = {"speed": "G3-SPEED", "teleport": "G3-TELEPORT", "land": "G3-LAND-CROSSING", "capacity": "G3-CAPACITY",
                 "state": "G3-STATE", "time": "G3-STATE", "schema": "DATA-SCHEMA"}

GATE_CODE = {"1b": "G1B-GAP", "2": "G2-REPLAY-DRIFT", "3e": "G3E-ENSEMBLE", "4": "G4-KPI-MISMATCH", "4b": "G4B-AIS",
             "4c": "G4C-ENTUR", "1": "G1-PLAN-INFEASIBLE"}

_VIOLATION = re.compile(r"\[(schema|time|teleport|speed|state|capacity|land)\]")
_TEXT_RULES = [   # (regex, code): first match wins; order matters (most specific first)
    (r"dims off by more than|principal dimension|missing required dims|dims_failed|asset '[^']*'[: ]", "QA-ASSET-DIM"),
    (r"visual gate|empty half|ink density in region|below 4\.5:1|text sizes.*rule 17|ink clipped|accent (share|covers)", "VIS-GATE"),
    (r"libEGL|libGL\b|apt-get|Unable to locate package|E: (Failed|Unable)|no display|DISPLAY|HYPERFRAMES_BROWSER_PATH|"
     r"chrome (was )?not found|externally-managed-environment", "CI-ENV"),
    (r"timed out|timeout|StageTimeout|exceeded \d+ ?s|HTTP 429|429 Client|Too Many Requests|ConnectionError|Max retries exceeded|"
     r"HTTP 50[234]|Remote end closed", "DATA-HOST-TIMEOUT"),
    (r"sea leg\(s\) cross land", "G3-LAND-CROSSING"),
    (r"position jump", "G3-TELEPORT"),
    (r"above vmax", "G3-SPEED"),
    (r"moves \d+ m while|time goes backwards", "G3-STATE"),
    (r"load range", "G3-CAPACITY"),
    (r"ModuleNotFoundError|ImportError|is not installed|unknown (engine|solver)|does not import", "G0-TOOL-UNAVAILABLE"),
    (r"tool_mismatch|handles \[.*\], (problem needs|got \[)|engine is '\w+', not 'gtfs'", "G0-TOOL-MISMATCH"),
    (r"unsupported_classes|Unsupported\b", "G0-CLASS-UNSUPPORTED"),
    (r"unsourced|without src|neither src", "G0-SRC-MISSING"),
    (r"missing_(roads|world|gtfs|metocean|ais_calibration|entur_vehicles|weather)|weather_error|road_graph_error|"
     r"fetch_world --(pull|place|world)", "G0-DATA-MISSING"),
    (r"did not reproduce", "G4-KPI-MISMATCH"),
    (r"KeyError|missing columns|unexpected column|JSONDecodeError|schema|ParserError|could not convert", "DATA-SCHEMA"),
]


def gate_prefix(gate):
    """'1b_exact' -> '1b', '3_contract' -> '3', None -> None."""
    m = re.match(r"^(\d+[a-z]?)(?:_|$)", str(gate or ""))
    return m.group(1) if m else None


def meaning(code):
    return CODES[code][1]


def gate_of(code):
    return CODES[code][0]


def contract_kinds(text):
    """Violation kinds in a contract report string, in order of first appearance: 'contract: 2 ...\\n  [speed] PSV-1: ..'."""
    seen = []
    for k in _VIOLATION.findall(str(text or "")):
        if k not in seen:
            seen.append(k)
    return seen


def classify_text(text):
    s = str(text or "")
    kinds = contract_kinds(s)
    if kinds:
        return CONTRACT_KIND[kinds[0]]
    for rx, code in _TEXT_RULES:
        if re.search(rx, s, re.I if code in ("CI-ENV", "DATA-HOST-TIMEOUT") else 0):
            return code
    return "UNKNOWN"


def _is_import_error(s):
    return bool(re.search(r"ModuleNotFoundError|ImportError|No module named|is not installed", s))


def _error_code(msg, default):
    """A tool's recorded exception text -> code. `Unsupported` is the engines' refusal to approximate and covers many causes:
    not installed, wrong class, missing weather, malformed weather, an infeasible instance. Only what is none of those is
    a class that no tool models."""
    s = str(msg)
    if _is_import_error(s):
        return "G0-TOOL-UNAVAILABLE"
    if re.search(r"handles \[.*\], got \[", s):
        return "G0-TOOL-MISMATCH"
    if re.search(r"needs a WeatherSeries|weather series too short", s):
        return "G0-DATA-MISSING"
    if re.search(r"weather column|NaN in|strictly hourly|at least 24 hourly|weather must start", s):
        return "DATA-SCHEMA"
    if re.search(r"\bUnsupported\b", s):
        if default == "G1-PLAN-INFEASIBLE" and re.search(r"exceeds|infeasible|capacity", s):
            return default
        return "G0-CLASS-UNSUPPORTED"
    return default


def _gate0(d):
    if isinstance(d, dict):
        if d.get("unsourced"):
            return "G0-SRC-MISSING"
        if d.get("unsupported_classes"):
            return "G0-CLASS-UNSUPPORTED"
        if d.get("unavailable"):
            return "G0-TOOL-UNAVAILABLE"
        if d.get("tool_mismatch") or d.get("entur_validation"):
            return "G0-TOOL-MISMATCH"
        if any(k.startswith("missing_") or k in ("weather_error", "road_graph_error") for k in d):
            return "G0-DATA-MISSING"
        return classify_text(str(d))
    return classify_text(d)


def code_for_gate(gate, detail, passed=False):
    """The code pipeline.stop() records for a failing gate. None for a passing gate."""
    if passed:
        return None
    p = gate_prefix(gate)
    if p == "0":
        return _gate0(detail)
    if p == "3":
        kinds = contract_kinds(detail)
        return CONTRACT_KIND[kinds[0]] if kinds else classify_text(detail)
    if p == "1":
        if isinstance(detail, dict) and detail.get("error"):
            return _error_code(detail["error"], "G1-PLAN-INFEASIBLE")
        return "G1-PLAN-INFEASIBLE"
    if p == "1b":
        if isinstance(detail, dict) and detail.get("error") and _is_import_error(str(detail["error"])):
            return "G0-TOOL-UNAVAILABLE"
        return "G1B-GAP"
    if p == "2":
        if isinstance(detail, dict):
            for k, val in detail.items():
                if str(k).endswith("_engine"):
                    return _error_code(val, "G2-REPLAY-DRIFT")
        return "G2-REPLAY-DRIFT"
    if p == "3e":
        if isinstance(detail, dict) and detail.get("unsupported"):
            return "G0-CLASS-UNSUPPORTED"
        return "G3E-ENSEMBLE"
    if p in GATE_CODE:
        return GATE_CODE[p]
    return classify_text(detail if detail is not None else gate)


def first_failure(report):
    """(gate name, entry) of the first failing gate of a report, else (None, None)."""
    not_comparable = str(report.get("status", "")).startswith("not comparable")      # gate 4 pass is False, but nothing failed
    for name, g in (report.get("gates") or {}).items():
        if isinstance(g, dict) and g.get("pass") is False and not (not_comparable and gate_prefix(name) == "4"):
            return name, g
    return None, None


def classify(x, gate=None):
    """Code for a report, a gate entry, a gate-detail, an exception or free text. None when nothing failed."""
    if x is None:
        return None
    if isinstance(x, BaseException):
        return classify_text(f"{type(x).__name__}: {x}")
    if isinstance(x, str):
        m = re.fullmatch(r"\s*stopped at gate (\S+)\s*", x)
        if m:                                        # status word only: single-code gates are known, 0 and 3 are not
            return "UNKNOWN" if gate_prefix(m.group(1)) in ("0", "3") else code_for_gate(m.group(1), None)
        return classify_text(x)
    if isinstance(x, dict):
        if x.get("code") in CODES:
            return x["code"]
        if "gates" in x:
            name, g = first_failure(x)
            if g is not None:
                return g.get("code") if g.get("code") in CODES else code_for_gate(name, g.get("detail"))
            return classify(x["status"]) if str(x.get("status", "")).startswith("stopped") else None
        if "pass" in x and "detail" in x:
            if x["pass"]:
                return None
            return code_for_gate(gate, x["detail"]) if gate else classify_text(x["detail"])
        if "dims_failed" in x:                                   # offsim.assets.cad.qa.qa() report
            bad = x["dims_failed"] or x.get("missing_required") or not x.get("dims_checked") or not x.get("principal_sourced")
            return "QA-ASSET-DIM" if bad else None
        return code_for_gate(gate, x) if gate else classify_text(str(x))
    return "UNKNOWN"
