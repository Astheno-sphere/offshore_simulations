"""Doctor: every failure code is produced (real failing scenario or synthetic report) and classified; every code has a playbook
whose checks exist; auto repairs never touch scenario values; lessons need a guard; old reports without `code` still classify."""
import copy
import json
import re

import numpy as np
import pandas as pd
import pytest
import yaml

from conftest import ROOT
from offsim import doctor
from offsim.doctor import checks as C, cli, lessons
from offsim.doctor.codes import CODES, classify, code_for_gate
from offsim.pipeline import run

DEMO = ROOT / "offsim/papers/demo-oslofjord-supply/scenario.yaml"


def demo(tmp_path, name="s.yaml", **edit):
    sc = yaml.safe_load(DEMO.read_text())
    sc["world"] = "none"
    sc.update(edit)
    p = tmp_path / name
    p.write_text(yaml.safe_dump(sc))
    return p


def gate_report(name, detail, extra=None):
    """A synthetic old-style report (no code field): one failing gate."""
    return {"paper": {"id": "synthetic"}, "gates": {name: {"pass": False, "detail": detail}}, "status": f"stopped at gate {name}", **(extra or {})}


def contract_text(kind):
    from offsim.contract import validate
    from shapely.geometry import box
    agents = pd.DataFrame([{"agent_id": "A", "cls": "psv", "vmax_mps": 5.0 if kind == "speed" else 100.0, "capacity": 10, "domain": "sea"}])
    rows = {
        "speed": [(0, 0, 0, "sail"), (10, 0.1, 0, "sail")],
        "teleport": [(0, 0, 0, "sail"), (0, 0.1, 0, "sail")],
        "state": [(0, 0, 0, "wait"), (1000, 0.1, 0, "wait")],
        "land": [(0, 0, 0, "sail"), (100000, 0.2, 0, "sail")],
        "capacity": [(0, 0, 0, "wait"), (100, 0, 0, "wait")],
        "time": [(100, 0, 0, "sail"), (0, 0.001, 0, "sail")],
    }[kind]
    df = pd.DataFrame(rows, columns=["t", "lon", "lat", "state"]).assign(agent_id="A")
    if kind == "capacity":
        df["load"] = [0, 99]
    rep = validate(df, agents, land=box(0.05, -1, 0.15, 1) if kind == "land" else None)
    assert not rep.ok and kind in str(rep)
    return str(rep)


GATE_ENTRIES = {   # code -> (gate, detail) that the pipeline writes
    "G0-SRC-MISSING": ("0_provenance", {"unsourced": ["fleet[0].capacity"], "unsupported_classes": []}),
    "G0-CLASS-UNSUPPORTED": ("0_provenance", {"unsourced": [], "unsupported_classes": ["PDP"], "tool_mismatch": ["solver pyvrp handles ['CVRP'], problem needs ['PDP']"]}),
    "G0-TOOL-UNAVAILABLE": ("0_provenance", {"unsourced": [], "unsupported_classes": [], "unavailable": {"engine:nope": "KeyError: \"unknown engine 'nope'\""}}),
    "G0-TOOL-MISMATCH": ("0_provenance", {"unsourced": [], "unsupported_classes": [], "tool_mismatch": ["engine gtfs handles ['TRANSIT-REPLAY'], problem needs ['CVRP']"]}),
    "G1B-GAP": ("1b_exact", {"gap": 0.5, "gap_tol": 0.02, "exact_status": "optimal", "heuristic_m": 150.0, "exact_m": 100.0, "n_clients": 5}),
    "G2-REPLAY-DRIFT": ("2_replay_equals_plan", [{"kpi": "distance_km", "paper": 100.0, "ours": 130.0, "rel_gap": 0.3, "rel_tol": 0.01, "pass": False}]),
    "G3E-ENSEMBLE": ("3e_ensemble", {"n_runs": 4, "n_valid": 3, "seeds": [0, 1], "years": [2000], "weather_sources": ["synthetic"],
                                     "failures": ["seed 1 year 2000: [speed] A: 1 leg(s) above vmax"]}),
    "G4B-AIS": ("4b_ais", {"src": "calib", "failed": [{"metric": "sailing_speed_kn", "pass": False}], "table": []}),
    "G4C-ENTUR": ("4c_entur", {"reason": "median delay 420 s above limit", "t0_utc": "2025-01-01T00:00:00Z", "journeys": []}),
    "G0-DATA-MISSING": ("0_provenance", {"missing_roads": "/nonexistent/osm/roads.geojson", "fix": "python -m offsim.worlds.fetch_world --place x --modes road"}),
    "G1-PLAN-INFEASIBLE": ("1_plan", {"routes": [[1, 2], [2, 3]], "loads": [9, 9], "capacity": 8, "objective_m": 10.0}),
}
for _k, _code in {"speed": "G3-SPEED", "teleport": "G3-TELEPORT", "land": "G3-LAND-CROSSING", "capacity": "G3-CAPACITY", "state": "G3-STATE"}.items():
    GATE_ENTRIES[_code] = ("3_contract", None)       # detail filled lazily (needs shapely/pandas)
TEXT_CASES = {"DATA-HOST-TIMEOUT": "fetch: metocean nora3_wind exceeded 2400 s", "DATA-SCHEMA": "KeyError: 'objective_total'",
              "VIS-GATE": "shot 2 (section): visual gate: balance: empty half: bottom half holds 11% of the ink (< 13%)",
              "CI-ENV": "ImportError: libEGL.so.1: cannot open shared object file", "UNKNOWN": "the flux capacitor is out of phase"}
QA_CASE = {"name": "s92", "dims": [{"name": "rotor_diameter_m", "value": 20.0, "sourced": True, "measured": 16.0, "rel_err": 0.2, "pass": False}],
           "tol": 0.01, "dims_checked": 1, "dims_failed": ["rotor_diameter_m"], "missing_required": [], "principal_sourced": ["rotor_diameter_m"]}


def synthetic(code):
    if code in GATE_ENTRIES:
        gate, detail = GATE_ENTRIES[code]
        if detail is None:
            detail = contract_text({v: k for k, v in {"speed": "G3-SPEED", "teleport": "G3-TELEPORT", "land": "G3-LAND-CROSSING",
                                                       "capacity": "G3-CAPACITY", "state": "G3-STATE"}.items()}[code])
        return gate_report(gate, detail)
    if code in TEXT_CASES:
        return TEXT_CASES[code]
    if code == "QA-ASSET-DIM":
        return QA_CASE
    return None


# ---------------------------------------------------------------------------------- codes from real failing scenarios
def real(tmp_path, name, **edit):
    return run(demo(tmp_path, name + ".yaml", **edit), tmp_path / name, seconds=1)


def test_real_runs_get_codes_on_the_failing_gate(tmp_path):
    base = yaml.safe_load(DEMO.read_text())
    sc_unsourced = copy.deepcopy(base)
    sc_unsourced["fleet"][0]["capacity"] = {"value": 12}
    r = real(tmp_path, "src", fleet=sc_unsourced["fleet"])
    assert r["gates"]["0_provenance"]["code"] == r["code"] == "G0-SRC-MISSING" and classify(r) == "G0-SRC-MISSING"
    # why: A1: ortools covers PDP now, so PSV-PDP (no tool) is the unsupported class
    assert real(tmp_path, "cls", problem={**base["problem"], "class": ["PSV-PDP"]})["code"] == "G0-CLASS-UNSUPPORTED"
    assert real(tmp_path, "tool", engine="nope")["code"] == "G0-TOOL-UNAVAILABLE"
    assert real(tmp_path, "mm", engine="gtfs")["code"] == "G0-TOOL-MISMATCH"
    r = real(tmp_path, "data", weather={"dir": "data/does-not-exist", "point": [10.0, 59.0], "years": [2000, 2001]})
    assert r["code"] == "G0-DATA-MISSING" and "missing_metocean" in r["gates"]["0_provenance"]["detail"]
    tiny = copy.deepcopy(base)
    tiny["fleet"][0]["count"] = {"value": 1, "assumption": True} if isinstance(tiny["fleet"][0]["count"], dict) else 1
    tiny["fleet"][0]["capacity"] = {"value": 1, "assumption": True}
    r = real(tmp_path, "plan", fleet=tiny["fleet"])
    assert r["gates"]["1_plan"]["pass"] is False and r["code"] == "G1-PLAN-INFEASIBLE"
    first = run(demo(tmp_path, "k.yaml"), tmp_path / "k", seconds=1)
    km = first["kpis"]["distance_km"]
    r = real(tmp_path, "kpi", reported={"distance_km": {"value": km * 0.5, "rel_tol": 0.01, "src": "test"}})
    assert r["status"] == "did not reproduce" and r["gates"]["4_paper"]["code"] == "G4-KPI-MISMATCH" and classify(r) == "G4-KPI-MISMATCH"
    assert classify(first) is None and doctor.diagnose(first)["ok"]          # "not comparable" is not a failure
    assert "code" not in first and all("code" not in g for g in first["gates"].values())       # passing runs are unchanged


@pytest.mark.parametrize("code", sorted(set(CODES) - {"G4-KPI-MISMATCH"}))
def test_each_code_is_classified_from_a_failing_report(code):
    rep = synthetic(code)
    assert rep is not None, f"no failing case written for {code}"
    assert classify(rep) == code
    if isinstance(rep, dict) and "gates" in rep:               # the new field wins and the old text path agrees
        (name, g), = rep["gates"].items()
        assert code_for_gate(name, g["detail"]) == code
        assert classify({**rep, "code": code}) == code


def test_every_code_has_a_case():
    covered = set(GATE_ENTRIES) | set(TEXT_CASES) | {"QA-ASSET-DIM", "G4-KPI-MISMATCH"}
    assert covered == set(CODES)


def test_contract_kinds_map_to_g3_codes_and_old_reports_still_classify():
    for kind, code in {"speed": "G3-SPEED", "teleport": "G3-TELEPORT", "land": "G3-LAND-CROSSING", "capacity": "G3-CAPACITY",
                       "state": "G3-STATE", "time": "G3-STATE"}.items():
        assert classify(gate_report("3_contract", contract_text(kind))) == code
    assert classify({"gates": {"0_provenance": {"pass": True}}, "status": "reproduced"}) is None
    # the other gate-0 shapes, old style (no code)
    assert classify(gate_report("0_provenance", {"unsourced": ["fleet[0].capacity"], "unsupported_classes": []})) == "G0-SRC-MISSING"
    assert classify(gate_report("0_provenance", {"unsourced": [], "unsupported_classes": [], "unavailable": {"engine:x": "unknown engine"}})) == "G0-TOOL-UNAVAILABLE"
    assert classify(gate_report("0_provenance", {"missing_metocean": "/x", "fix": "..."})) == "G0-DATA-MISSING"
    assert classify(gate_report("1_plan", {"solver": "pyvrp", "error": "RuntimeError: PyVRP returned an infeasible plan"})) == "G1-PLAN-INFEASIBLE"
    assert classify(gate_report("1_plan", {"solver": "x", "error": "Unsupported: class PDP"})) == "G0-CLASS-UNSUPPORTED"
    assert classify(gate_report("2_replay_equals_plan", {"replay_engine": "KeyError: 7"})) == "G2-REPLAY-DRIFT"
    assert classify("stopped at gate 4c_entur") == "G4C-ENTUR" and classify("stopped at gate 3_contract") == "UNKNOWN"
    assert classify(RuntimeError("HTTP 429 Too Many Requests")) == "DATA-HOST-TIMEOUT"


# ---------------------------------------------------------------------------------- playbooks
def all_playbooks():
    return {c: doctor.load_playbook(c) for c in CODES}


def test_every_code_has_a_loadable_playbook_with_existing_checks():
    assert {p.stem for p in doctor.PLAYBOOKS.glob("*.yaml")} == set(CODES)
    for code, pb in all_playbooks().items():
        assert pb["code"] == code and pb["gate"] == CODES[code][0] and pb["symptoms"] and pb["question"]
        assert pb["checks"], code
        for name in pb["checks"]:
            assert callable(getattr(C, name, None)), f"{code}: check {name} missing in checks.py"
        assert pb["repairs"] and all(r["kind"] in ("auto", "human") and r["id"] and r["action"] and r["why_safe"] for r in pb["repairs"]), code
        ids = [r["id"] for r in pb["repairs"]]
        assert len(ids) == len(set(ids)), code


BANNED = re.compile(r"\b(edit|edits|change|changes|widen|loosen|relax|raise|increase|modify|overwrite|patch|set|replace|add|"
                    r"tolerance|assumption|src|rel_tol|gap_tol|vmax|capacity)\b", re.I)


def test_auto_repairs_are_deterministic_value_preserving_and_never_edit_scenario_values():
    n = 0
    for code, pb in all_playbooks().items():
        for r in pb["repairs"]:
            if r["kind"] != "auto":
                assert "op" not in r, f"{code}/{r['id']}: human repairs are never executable"
                continue
            n += 1
            assert r["op"] in doctor.AUTO_OPS, f"{code}/{r['id']}: op {r['op']!r}"
            assert not BANNED.search(r["action"]), f"{code}/{r['id']}: auto action touches a value: {r['action']}"
    assert n >= 5


def test_diagnose_runs_every_check_without_crashing_for_every_code():
    for code in CODES:
        if code == "G4-KPI-MISMATCH":
            continue
        d = doctor.diagnose(synthetic(code), root=ROOT)
        assert d["code"] == code and d["question"] and d["repairs"] and d["checks"] and not d["ok"]
        for c in d["checks"]:
            assert "check_error" not in c["evidence"], (code, c)
            assert c["ok"] in (True, False, None)
    kpi = gate_report("4_paper", [{"kpi": "distance_km", "paper": 100.0, "ours": None, "rel_gap": None, "rel_tol": 0.02, "pass": False}])
    d = doctor.diagnose(kpi)
    assert d["code"] == "G4-KPI-MISMATCH" and any(c["name"] == "kpi_names_measurable" and c["ok"] is False for c in d["checks"])
    assert doctor.diagnose({"gates": {"0": {"pass": True}}, "status": "reproduced"})["ok"] is True


def test_check_evidence_finds_the_cause():
    d = doctor.diagnose(synthetic("G1-PLAN-INFEASIBLE"))
    pr = next(c for c in d["checks"] if c["name"] == "plan_recheck")
    assert pr["ok"] is False and pr["evidence"]["duplicated"] == [2]
    d = doctor.diagnose(synthetic("G3-SPEED"))
    assert next(c for c in d["checks"] if c["name"] == "worst_speed_vs_vmax")["evidence"]["ratio"] > 1
    d = doctor.diagnose(synthetic("G0-DATA-MISSING"))
    assert d["fix_command"].startswith("python -m offsim.worlds.fetch_world")
    assert next(c for c in d["checks"] if c["name"] == "data_paths_present")["ok"] is False


def test_lesson_checks_hold_on_this_repo():
    ctx = doctor.build_ctx({}, root=ROOT)
    for name in ("pyvrp_only_via_adapter", "numpy_float_in_approx", "stage_budgets_present", "intake_kpi_label_tolerant",
                 "ci_workflow_retries_apt", "lessons_have_guards"):
        assert getattr(C, name)(ctx)["ok"] is True, name


def test_numpy_float_in_approx_check_flags_the_offender(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_a.py").write_text("import numpy as np, pytest\ndef test_x():\n    assert 1 == pytest.approx(np.float32(1))\n")
    r = C.numpy_float_in_approx({"root": tmp_path})
    assert r["ok"] is False and r["evidence"]["hits"] == ["test_a.py:3"]


# ---------------------------------------------------------------------------------- repair
def write_failing_report(tmp_path, code="G1-PLAN-INFEASIBLE"):
    gate, detail = GATE_ENTRIES[code]
    rep = gate_report(gate, detail)
    rep["paper"] = {"id": "demo-oslofjord-supply"}          # so the doctor finds offsim/papers/<id>/scenario.yaml
    p = tmp_path / "rep" / "report.json"
    p.parent.mkdir()
    p.write_text(json.dumps(rep))
    return p


def test_repair_plans_without_running_and_writes_diagnosis(tmp_path):
    p = write_failing_report(tmp_path)
    called = []
    d = doctor.repair(p, run=False, runner=lambda *a: called.append(a))
    assert not called and d["attempts"] == [] and any(x["op"] == "rerun_seed" for x in d["planned"])
    on_disk = json.loads((p.parent / "diagnosis.json").read_text())
    assert on_disk["code"] == "G1-PLAN-INFEASIBLE" and on_disk["resolved"] is False and on_disk["run"] is False


def test_repair_run_executes_only_auto_repairs_and_stops_when_the_gate_passes(tmp_path):
    p = write_failing_report(tmp_path)
    seeds = []

    def runner(scenario, out, seed):
        seeds.append(seed)
        return {"paper": {"id": "x"}, "gates": {"1_plan": {"pass": True}}, "status": "reproduced"}
    d = doctor.repair(p, run=True, runner=runner)
    assert d["resolved"] is True and seeds == [2] and d["attempts"][-1]["passed"] is True
    assert not (tmp_path / "rep" / "report.json").read_text().count("reproduced")        # the failing report is kept
    assert json.loads((p.parent / "diagnosis.json").read_text())["resolved"] is True


def test_repair_honours_max_attempts(tmp_path):
    p = write_failing_report(tmp_path, "G0-DATA-MISSING")
    seeds = []
    still_bad = lambda s, o, sd: (seeds.append(sd), gate_report("0_provenance", GATE_ENTRIES["G0-DATA-MISSING"][1]))[1]
    import offsim.doctor as dmod
    orig = dmod._run_cmd
    dmod._run_cmd = lambda cmd, timeout: {"cmd": " ".join(cmd), "returncode": 0, "tail": "stub: no network in tests"}
    try:
        d = doctor.repair(p, max_attempts=1, run=True, runner=still_bad)
    finally:
        dmod._run_cmd = orig
    # data-missing has no world in the demo scenario ("none" after edit is not applied here): at most one rerun, never more than max_attempts
    assert len(seeds) <= 1 and d["resolved"] is False


def test_no_rerun_for_human_only_failures(tmp_path):
    p = write_failing_report(tmp_path, "G3-SPEED")
    called = []
    d = doctor.repair(p, run=True, runner=lambda *a: called.append(a))
    assert not called and d["attempts"] == [] and d["resolved"] is False and d["question"]


# ---------------------------------------------------------------------------------- lessons
def test_learn_refuses_a_lesson_without_a_guard(tmp_path):
    jl, md = tmp_path / "l.jsonl", tmp_path / "LESSONS.md"
    with pytest.raises(lessons.LessonRefused):
        lessons.add("G3-SPEED", "s", "c", "f", guard=None, path=jl, doc=md)
    with pytest.raises(lessons.LessonRefused):
        lessons.add("G3-SPEED", "s", "c", "f", guard="tests/test_doctor.py::test_that_does_not_exist", path=jl, doc=md)
    with pytest.raises(lessons.LessonRefused):
        lessons.add("G3-SPEED", "s", "c", "f", guard="playbook:G3-SPEED::no_such_check", path=jl, doc=md)
    with pytest.raises(lessons.LessonRefused):
        lessons.add("NOT-A-CODE", "s", "c", "f", guard="tests/test_doctor.py::test_learn_refuses_a_lesson_without_a_guard", path=jl, doc=md)
    assert not jl.exists()
    r = lessons.add("G3-SPEED", "s", "c", "f", guard="tests/test_doctor.py::test_learn_refuses_a_lesson_without_a_guard", path=jl, doc=md)
    assert r["open"] is False and "G3-SPEED" in md.read_text()
    r = lessons.add("G3-TELEPORT", "s2", "c2", "f2", guard="playbook:G3-TELEPORT::teleport_count", path=jl, doc=md)
    o = lessons.add("DATA-SCHEMA", "s3", "c3", "f3", open_=True, path=jl, doc=md)
    assert o["open"] is True and md.read_text().index("Open (no guard yet)") < md.read_text().index("## G3-SPEED")
    assert [x["id"] for x in lessons.load(jl)] == [1, 2, 3]


def test_cli_learn_and_doctor(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(lessons, "PATH", tmp_path / "l.jsonl")
    monkeypatch.setattr(lessons, "DOC", tmp_path / "L.md")
    monkeypatch.setattr(lessons.add, "__defaults__", (None, False, tmp_path / "l.jsonl", tmp_path / "L.md", lessons.ROOT, None))
    args = ["learn", "--code", "G3-SPEED", "--symptom", "s", "--cause", "c", "--fix", "f"]
    assert cli.main(args) == 2 and "refused" in capsys.readouterr().err
    assert cli.main(args + ["--guard", "playbook:G3-SPEED::worst_speed_vs_vmax"]) == 0
    assert cli.main(["--code", "DATA-SCHEMA", "--symptom", "s", "--cause", "c", "--fix", "f", "--open"]) == 0      # no sub-command word
    p = write_failing_report(tmp_path, "G3-SPEED")
    assert cli.main(["doctor", str(p)]) == 1
    out = capsys.readouterr().out
    assert "G3-SPEED" in out and "ask:" in out and (p.parent / "diagnosis.json").exists()
    assert cli.main([str(p), "--repair", "--dry-run"]) == 1
    ok = tmp_path / "ok.json"
    ok.write_text(json.dumps({"gates": {"0_provenance": {"pass": True}}, "status": "reproduced"}))
    assert cli.main(["doctor", str(ok)]) == 0 and cli.main(["doctor", str(tmp_path / "missing.json")]) == 2


def test_seed_lessons_have_guards_or_are_open():
    items = lessons.load()
    assert len(items) >= 9
    for x in items:
        assert x["code"] in CODES
        assert x["open"] or lessons.guard_exists(x["guard"]), x
    assert (ROOT / "docs/LESSONS.md").read_text() == lessons.render(items)
