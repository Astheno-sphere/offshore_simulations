"""Seeded-fault tests for the gates: each gate gets one planted fault and must fail on exactly that fault.

Method (the checker discipline of Abhinav Bhardwaj's Junior Architect Pipeline, tests/examples.test.js, ported as an idea; no
code or text copied, see docs/ABSORB_JAP.md): a gate is only trusted once it has been shown a known-bad input and reported
that fault and no other, next to a clean twin that passes. The fixtures are tiny (tests/fixtures/seeded/), run on `world: none`
and finish in seconds. Faults are planted by a registered fake solver or engine that delegates to the real one and then breaks
one thing, so the gate under test is the real gate in `offsim.pipeline.run`.

  gate 0   unsourced parameter                          G0-SRC-MISSING, detail.unsourced
  gate 1   client served twice / not at all / over capacity / window violated   G1-PLAN-INFEASIBLE, detail.faults
  gate 1b  heuristic far from the exact optimum         G1B-GAP, detail.gap
  gate 2   replay distance differs from the plan cost   G2-REPLAY-DRIFT, failing kpi distance_km
  gate 3   non-monotone time column                     G3-STATE, contract kind `time`
  gate 4   a reported KPI outside tolerance             G4-KPI-MISMATCH, failing kpi named
  gate 4   right cost, wrong fleet composition          G4-KPI-MISMATCH, failing kpi fleet_composition (audit 8)
  gate 4b  simulated speed vs AIS calibration           failing metric sailing_speed_kn   (gate function, no world data here)
  gate 4c  timetable vs observed delays                 reason names the delay, not the travel time (gate function)
"""
import copy

import numpy as np
import pandas as pd
import pytest
import yaml

from conftest import ROOT
from offsim.doctor.codes import code_for_gate, contract_kinds
from offsim.engines import base
from offsim.engines.base import Plan, get_engine, get_solver
from offsim.pipeline import ais_gate, run
from offsim.transit import observed

FIX = ROOT / "tests/fixtures/seeded"
WHELP = ROOT / "offsim/papers/irinagribkovskaia-2025-tactical-helicopter/scenario.synth.yaml"


# ------------------------------------------------------------------------------------------------- helpers
def scenario(name="cvrp_tiny.yaml"):
    return yaml.safe_load((FIX / name).read_text())


def go(tmp_path, sc, tag="run"):
    p = tmp_path / f"{tag}.yaml"
    p.write_text(yaml.safe_dump(sc))
    return run(p, tmp_path / tag, seconds=1)


def route_m(problem, route):
    pts = [0] + list(route) + [0]
    return float(sum(problem.dist_m[a][b] for a, b in zip(pts, pts[1:])))


def plan_of(problem, routes):
    routes = {f"PSV-{i + 1}": list(r) for i, r in enumerate(routes)}
    return Plan(routes=routes, objective=sum(route_m(problem, r) for r in routes.values()), solver="seeded", status="feasible")


def use_solver(monkeypatch, fn, name="seeded_solver"):
    """Register a solver that calls fn(problem) -> Plan. Returns the scenario value to select it."""
    class Seeded:
        classes = {"CVRP", "VRPTW"}

        def __init__(self):
            self.name = name

        def solve(self, problem, seconds=2.0, seed=1):
            return fn(problem)
    monkeypatch.setitem(base._SOLVERS, name, Seeded)
    return name


def use_engine(monkeypatch, fn, name="seeded_engine"):
    """Register an engine that runs the real replay engine, then lets fn(SimResult) break the result."""
    class Seeded:
        classes = {"CVRP", "VRPTW"}
        needs_weather = False

        def __init__(self):
            self.name = name

        def simulate(self, problem, plan, world, weather=None, seed=0):
            return fn(get_engine("replay").simulate(problem, plan, world, weather, seed))
    monkeypatch.setitem(base._ENGINES, name, Seeded)
    return name


def with_solver(sc, name):
    sc = copy.deepcopy(sc)
    sc["solver"] = name
    return sc


def real_plan(problem):
    return get_solver("pyvrp").solve(problem, seconds=1, seed=1)


def failing(rep):
    """Names of the gates that failed. Gate 4 with no reported KPIs has pass False but is 'not comparable', not a failure."""
    nc = str(rep.get("status", "")).startswith("not comparable")
    return [k for k, g in rep["gates"].items() if not g["pass"] and not (nc and k == "4_paper")]


def failed(rep):
    """(gate name, entry) of the one failing gate; asserts there is exactly one and that nothing ran after it."""
    bad = failing(rep)
    assert len(bad) == 1, bad
    assert list(rep["gates"])[-1] == bad[0], "a gate ran after the failing one"
    return bad[0], rep["gates"][bad[0]]


def passed_through(rep, last):
    assert failing(rep) == [] and last in rep["gates"]


# ------------------------------------------------------------------------------------------------- gate 0
def test_gate0_unsourced_parameter_is_named(tmp_path):
    sc = scenario()
    sc["fleet"][0]["capacity"] = {"value": 3}                       # a value with neither src nor assumption
    rep = go(tmp_path, sc, "g0")
    gate, g = failed(rep)
    assert gate == "0_provenance" and g["code"] == rep["code"] == "G0-SRC-MISSING"
    assert g["detail"]["unsourced"] == ["fleet[0].capacity"]       # exactly that leaf
    assert g["detail"]["unsupported_classes"] == []
    assert set(rep["gates"]) == {"0_provenance"}                    # nothing ran after it


def test_gate0_clean_twin_passes(tmp_path):
    rep = go(tmp_path, scenario(), "g0c")
    assert rep["gates"]["0_provenance"]["pass"] and rep["gates"]["0_provenance"]["detail"]["unsourced"] == []


# ------------------------------------------------------------------------------------------------- gate 1
def gate1(tmp_path, monkeypatch, routes, sc=None):
    name = use_solver(monkeypatch, lambda p: plan_of(p, routes))
    return go(tmp_path, with_solver(sc or scenario(), name), "g1")


def test_gate1_client_served_twice(tmp_path, monkeypatch):
    rep = gate1(tmp_path, monkeypatch, [[1, 2], [2, 3, 4]])         # 2 twice; loads 2 and 3 fit capacity 3
    gate, g = failed(rep)
    assert gate == "1_plan" and g["code"] == "G1-PLAN-INFEASIBLE"
    assert g["detail"]["faults"] == {"served_twice": [2]}


def test_gate1_client_not_served(tmp_path, monkeypatch):
    rep = gate1(tmp_path, monkeypatch, [[1, 2], [3]])               # 4 is missing
    gate, g = failed(rep)
    assert gate == "1_plan" and g["code"] == "G1-PLAN-INFEASIBLE"
    assert g["detail"]["faults"] == {"not_served": [4]}


def test_gate1_route_over_capacity(tmp_path, monkeypatch):
    rep = gate1(tmp_path, monkeypatch, [[1, 2, 3, 4]])              # load 4 > capacity 3, one vehicle of two
    gate, g = failed(rep)
    assert gate == "1_plan" and g["code"] == "G1-PLAN-INFEASIBLE"
    assert g["detail"]["faults"] == {"over_capacity": [{"route": 0, "load": 4, "capacity": 3}]}


def test_gate1_more_routes_than_vehicles(tmp_path, monkeypatch):
    rep = gate1(tmp_path, monkeypatch, [[1], [2], [3, 4]])          # three routes, two vessels
    gate, g = failed(rep)
    assert gate == "1_plan" and g["detail"]["faults"] == {"too_many_routes": {"routes": 3, "vehicles": 2}}


def test_gate1_clean_twin_passes(tmp_path):
    rep = go(tmp_path, scenario(), "g1c")
    passed_through(rep, "3_contract")
    assert rep["gates"]["1_plan"]["detail"].get("faults", {}) == {}


# ------------------------------------------------------------------------------------------------- gate 1: time windows (audit 7)
def test_gate1_catches_a_time_window_violation(tmp_path, monkeypatch):
    """Audit 7, risk 1: gate 1 did not check Problem.tw. Route [2, 1] starts service at S1 at 1800 s; its window closes at 1000 s.
    Loads, coverage and vehicle count are fine, so the window is the only fault."""
    rep = gate1(tmp_path, monkeypatch, [[2, 1], [3, 4]], scenario("vrptw_tiny.yaml"))
    gate, g = failed(rep)
    assert gate == "1_plan" and g["code"] == "G1-PLAN-INFEASIBLE"
    assert set(g["detail"]["faults"]) == {"time_window"}
    (v,) = g["detail"]["faults"]["time_window"]
    assert v["client"] == 1 and v["start_s"] == pytest.approx(1800.0, abs=10.0) and v["latest_s"] == 1000.0


def test_gate1_time_window_clean_twin_passes(tmp_path, monkeypatch):
    rep = gate1(tmp_path, monkeypatch, [[1, 2], [3, 4]], scenario("vrptw_tiny.yaml"))
    passed_through(rep, "3_contract")


def test_gate1_waiting_for_a_window_to_open_is_not_a_violation(tmp_path, monkeypatch):
    """Standard rule: arriving early waits. S2 opens at 5000 s and the vessel arrives at 800 s: service starts at 5000 s, inside
    [5000, 6000]. A check that compared the arrival time with the opening would wrongly fail this plan."""
    sc = scenario("vrptw_tiny.yaml")
    sc["instance"]["stops"][1]["tw"]["value"] = [5000, 6000]
    rep = gate1(tmp_path, monkeypatch, [[2], [1, 3, 4]], sc)
    assert rep["gates"]["1_plan"]["pass"], rep["gates"]["1_plan"]


# ------------------------------------------------------------------------------------------------- gate 1b
CERT = {"solver": "pyomo", "max_clients": {"value": 12, "assumption": True, "why": "fixture"},
        "gap_tol": {"value": 0.02, "assumption": True, "why": "fixture"}, "seconds": {"value": 20, "assumption": True, "why": "fixture"}}


def test_gate1b_heuristic_far_from_the_exact_optimum(tmp_path, monkeypatch):
    sc = scenario()
    sc["certify"] = CERT
    name = use_solver(monkeypatch, lambda p: plan_of(p, [[4, 1, 3], [2]]))      # feasible, but criss-crosses the line
    rep = go(tmp_path, with_solver(sc, name), "g1b")
    gate, g = failed(rep)
    d = g["detail"]
    assert gate == "1b_exact" and g["code"] == "G1B-GAP"
    assert d["exact_status"] == "optimal" and d["gap"] > d["gap_tol"] and "error" not in d


def test_gate1b_clean_twin_passes(tmp_path):
    sc = scenario()
    sc["certify"] = CERT
    rep = go(tmp_path, sc, "g1bc")
    d = rep["gates"]["1b_exact"]
    assert d["pass"] and d["detail"]["gap"] <= d["detail"]["gap_tol"]


# ------------------------------------------------------------------------------------------------- gate 2
def test_gate2_replay_distance_differs_from_the_plan(tmp_path, monkeypatch):
    def inflated(p):
        plan = real_plan(p)
        plan.objective *= 1.20                                  # the plan claims 20 % more distance than its routes have
        return plan
    rep = go(tmp_path, with_solver(scenario(), use_solver(monkeypatch, inflated)), "g2")
    gate, g = failed(rep)
    assert gate == "2_replay_equals_plan" and g["code"] == "G2-REPLAY-DRIFT"
    rows = {r["kpi"]: r for r in g["detail"]}
    assert [k for k, r in rows.items() if not r["pass"]] == ["distance_km"]
    assert rows["distance_km"]["rel_gap"] == pytest.approx(1 - 1 / 1.2, abs=1e-3)


def test_gate2_clean_twin_passes(tmp_path):
    rep = go(tmp_path, scenario(), "g2c")
    assert rep["gates"]["2_replay_equals_plan"]["pass"]


# ------------------------------------------------------------------------------------------------- gate 3
def test_gate3_non_monotone_time_column(tmp_path, monkeypatch):
    def scramble(res):
        t = res.traj["t"].to_numpy().copy()
        first = res.traj.index[res.traj["agent_id"] == res.traj["agent_id"].iloc[0]]
        i = first[len(first) // 2]
        t[i], t[i + 1] = t[i + 1] + 1.0, t[i] - 1.0               # one pair of rows out of order, positions untouched
        res.traj = res.traj.assign(t=t)
        return res
    rep = go(tmp_path, {**scenario(), "engine": use_engine(monkeypatch, scramble)}, "g3")
    gate, g = failed(rep)
    assert gate == "3_contract" and g["code"] == "G3-STATE"
    assert contract_kinds(g["detail"]) == ["time"]                  # exactly one kind of violation, and it is time
    assert "time goes backwards" in g["detail"]


def test_gate3_clean_twin_passes(tmp_path):
    rep = go(tmp_path, scenario(), "g3c")
    assert rep["gates"]["3_contract"] == {"pass": True, "detail": "contract: OK"}


# ------------------------------------------------------------------------------------------------- gate 4
def test_gate4_reported_kpi_outside_tolerance(tmp_path):
    clean = go(tmp_path, scenario(), "g4a")
    m = clean["measured"]
    sc = scenario()
    sc["reported"] = {"distance_km": {"value": m["distance_km"] * 1.30, "rel_tol": 0.02, "src": "seeded"},     # 30 % off
                      "vehicles_used": {"value": m["vehicles_used"], "rel_tol": 0.0, "src": "seeded"}}         # right
    rep = go(tmp_path, sc, "g4")
    g = rep["gates"]["4_paper"]
    assert rep["status"] == "did not reproduce" and not g["pass"]
    assert g["code"] == "G4-KPI-MISMATCH"
    assert [r["kpi"] for r in g["detail"] if not r["pass"]] == ["distance_km"]


def test_gate4_clean_twin_passes(tmp_path):
    m = go(tmp_path, scenario(), "g4b")["measured"]
    sc = scenario()
    sc["reported"] = {k: {"value": m[k], "rel_tol": 0.02, "src": "seeded"} for k in ("distance_km", "vehicles_used")}
    rep = go(tmp_path, sc, "g4c")
    assert rep["status"] == "re-run under assumptions" and rep["gates"]["4_paper"]["pass"]
    assert "code" not in rep["gates"]["4_paper"]


# ------------------------------------------------------------------------------------------------- gate 4: fleet composition (audit 8)
def whelp_scenario(**reported_edit):
    sc = yaml.safe_load(WHELP.read_text())
    sc["reported"] = {k: x for k, x in sc["reported"].items() if k != "window_hours"}     # cost and helicopter count only
    sc["reported"].update(reported_edit)
    return sc


def test_gate4_wrong_fleet_composition_with_the_right_cost_fails(tmp_path, monkeypatch):
    """Audit 8: Bergen's cost is within tolerance and the helicopter count matches, but the fleet is [16,16,12,10] where the paper
    has [16,14,10,10]; gate 4 compared cost only and passed. Here the paper's Florø result lists a fleet of one 12 h window where
    the run flies one 10 h window: cost and count match, the composition does not. (Bergen itself takes 12 minutes: not run here.)"""
    from offsim.solve import whelp
    monkeypatch.setitem(whelp.PAPER_RESULT, "floro", {**whelp.PAPER_RESULT["floro"], "windows": [12]})
    rep = go(tmp_path, whelp_scenario(), "g4f")
    g = rep["gates"]["4_paper"]
    rows = {r["kpi"]: r for r in g["detail"]}
    assert rows["plan_cost"]["pass"] and rows["helicopters"]["pass"]       # what gate 4 used to compare, and all it compared
    assert [k for k, r in rows.items() if not r["pass"]] == ["fleet_composition"]
    assert rows["fleet_composition"]["paper"] == [12.0] and rows["fleet_composition"]["ours"] == [10.0]
    assert rep["status"].startswith("did not reproduce") and g["code"] == "G4-KPI-MISMATCH"


def test_gate4_fleet_composition_listed_in_reported(tmp_path):
    """The same check when the scenario lists the composition itself (reported.fleet_composition), wrong then right."""
    bad = go(tmp_path, whelp_scenario(fleet_composition={"value": [12], "src": "seeded", "rel_tol": 0.0}), "g4g")
    assert [r["kpi"] for r in bad["gates"]["4_paper"]["detail"] if not r["pass"]] == ["fleet_composition"]
    good = go(tmp_path, whelp_scenario(fleet_composition={"value": [10], "src": "seeded", "rel_tol": 0.0}), "g4h")
    assert good["gates"]["4_paper"]["pass"] and good["status"].startswith("re-run under assumptions")


def test_gate4_committed_floro_scenario_still_reproduces(tmp_path):
    """Clean twin: the committed Florø scenario, composition taken from the paper result (whelp.PAPER_RESULT, p.29 Table 4)."""
    rep = go(tmp_path, yaml.safe_load(WHELP.read_text()), "g4i")
    rows = {r["kpi"]: r for r in rep["gates"]["4_paper"]["detail"]}
    assert rep["gates"]["4_paper"]["pass"] and rows["fleet_composition"]["pass"] and rows["fleet_composition"]["ours"] == [10.0]


# ------------------------------------------------------------------------------------------------- gate 4b, 4c (gate functions)
def sail_traj(speed_kn, n=11):
    """One vessel sailing east at lat 60 at a constant speed: 600 s per row."""
    mps = speed_kn * 1852 / 3600
    dlon = mps * 600 / (111320 * np.cos(np.radians(60)))
    return pd.DataFrame({"agent_id": "V1", "t": np.arange(n) * 600.0, "lon": 10.0 + np.arange(n) * dlon, "lat": 60.0, "state": "sail"})


def test_gate4b_speed_disagreeing_with_ais_names_the_metric():
    ais = {"src": "seeded", "sailing_speed_kn": {"p10": 20.0, "p50": 20.0, "p90": 20.0, "n": 50}}
    ok, d = ais_gate(sail_traj(10.0), ais, {})
    assert not ok and {r["metric"] for r in d["failed"]} == {"sailing_speed_kn"}
    assert {r["quantile"] for r in d["failed"]} == {"p10", "p50", "p90"}
    assert code_for_gate("4b_ais", d) == "G4B-AIS"


def test_gate4b_clean_twin_and_empty_calibration():
    ais = {"src": "seeded", "sailing_speed_kn": {"p10": 10.0, "p50": 10.0, "p90": 10.0, "n": 50}}
    ok, d = ais_gate(sail_traj(10.0), ais, {})
    assert ok and d["failed"] == []
    ok, d = ais_gate(sail_traj(10.0), {"src": "seeded"}, {})          # judges nothing: not a pass
    assert not ok and "no metric comparable" in d["reason"]


def journeys(delay_s, ratio):
    return pd.DataFrame({"n_used": [10, 12, 9], "delay_p50": [delay_s] * 3, "tt_ratio": [ratio] * 3})


def test_gate4c_delay_disagreement_names_the_delay_not_the_travel_time():
    res = observed.gate_4c(journeys(delay_s=900.0, ratio=1.0))
    assert not res["pass"] and "median |delay|" in res["detail"]["reason"] and "travel-time" not in res["detail"]["reason"]
    assert code_for_gate("4c_entur", res["detail"]) == "G4C-ENTUR"


def test_gate4c_clean_twin_and_nothing_judged():
    assert observed.gate_4c(journeys(delay_s=30.0, ratio=1.0))["pass"]
    res = observed.gate_4c(journeys(30.0, 1.0).assign(n_used=1))      # too few points per journey: nothing judged
    assert not res["pass"] and res["detail"]["n_judged"] == 0
