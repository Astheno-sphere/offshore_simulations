"""VRPTW end to end (package M1): pyvrp and pyomo solvers, replay honours the windows, template runs, CVRP unchanged.

Instance: four stops on a line east of the base at 2, 4, 6, 8 km, one vessel at 5 m/s, two available. The windows
force a split into two routes, so the CVRP optimum (one out-and-back, ~16 km) is infeasible with them.
"""
import re

import numpy as np
import pytest
import yaml

from conftest import ROOT
from offsim.contract import validate
from offsim.engines.base import Problem, Unsupported, World, get_engine, get_solver
from offsim.solve import ampl_adapter as A
from offsim.solve.pyvrp_adapter import matrix, route_times, windows_violations

LON0, LAT0 = 10.0, 59.9
DX = 1 / (111320 * np.cos(np.radians(LAT0)))          # degrees of longitude per metre at this latitude
SPEED = 5.0
TW = {1: (1500.0, 2500.0), 2: (0.0, 900.0), 3: (0.0, 5000.0), 4: (0.0, 1700.0)}
TEMPLATE = ROOT / "offsim/papers/_templates/vrptw/scenario.yaml"


def inst(cls=("VRPTW",), tw=None, service=None, count=2, cap=10, **kw):
    nodes = [(LON0, LAT0)] + [(LON0 + k * 1000 * DX, LAT0) for k in (2, 4, 6, 8)]
    return Problem(cls=set(cls), nodes=nodes, dist_m=matrix(nodes), demand={i: 1 for i in range(1, 5)},
                   fleet=[{"cls": "psv", "count": count, "capacity": cap, "speed_mps": SPEED, "domain": "sea"}],
                   service_s=service or {}, tw=TW if tw is None else tw, **kw)


def served(plan):
    return sorted(c for r in plan.routes.values() for c in r)


# --- the windows bind --------------------------------------------------------------------------------------
def test_the_windows_bind():
    cvrp = get_solver("pyvrp").solve(inst(("CVRP",), tw={}), seconds=1, seed=1)
    assert windows_violations(inst().dist_m, SPEED, list(cvrp.routes.values()), {}, TW), "CVRP optimum must break a window"
    vr = get_solver("pyvrp").solve(inst(), seconds=1, seed=1)
    assert vr.objective > cvrp.objective + 1000            # splitting into two routes costs real distance
    with pytest.raises(RuntimeError):                       # one vessel cannot meet all four windows: never an infeasible plan
        get_solver("pyvrp").solve(inst(count=1), seconds=1, seed=1)


# --- pyvrp --------------------------------------------------------------------------------------------------
def test_pyvrp_returns_a_window_feasible_plan():
    p = inst(service={1: 60.0, 2: 60.0, 3: 60.0, 4: 60.0})
    plan = get_solver("pyvrp").solve(p, seconds=1, seed=1)
    assert plan.solver == "pyvrp" and plan.objective_unit == "m" and plan.meta["time_windows"] == 4
    assert served(plan) == [1, 2, 3, 4] and set(plan.routes) == {"PSV-1", "PSV-2"}
    assert windows_violations(p.dist_m, SPEED, list(plan.routes.values()), p.service_s, TW) == []
    assert "VRPTW" in get_solver("pyvrp").classes and "CVRP" in get_solver("pyvrp").classes


def test_vrptw_without_windows_is_cvrp_cost():
    a = get_solver("pyvrp").solve(inst(("VRPTW",), tw={}, count=1), seconds=1, seed=1)
    b = get_solver("pyvrp").solve(inst(("CVRP",), tw={}, count=1), seconds=1, seed=1)
    assert a.objective == b.objective


# --- pyomo exact ----------------------------------------------------------------------------------------------
def test_pyomo_exact_certifies_pyvrp():
    p = inst(service={1: 60.0, 2: 60.0, 3: 60.0, 4: 60.0})
    heur = get_solver("pyvrp").solve(p, seconds=1, seed=1)
    ex = get_solver("pyomo").solve(p, seconds=30)
    assert ex.status == "optimal" and ex.solver == "pyomo" and "vrptw_exact" in ex.meta["model"]
    assert ex.objective <= heur.objective + 1e-6                 # exact <= heuristic
    assert ex.bound is not None and ex.bound <= ex.objective + 1e-6 and ex.bound <= heur.objective + 1e-6
    assert served(ex) == [1, 2, 3, 4]
    assert windows_violations(p.dist_m, SPEED, list(ex.routes.values()), p.service_s, TW) == []
    assert set(ex.routes) == set(heur.routes)


def test_pyomo_proves_infeasibility_by_raising():
    with pytest.raises(RuntimeError):
        get_solver("pyomo").solve(inst(count=1), seconds=10)


def test_pyomo_refuses_large_instances():
    nodes = [(LON0 + i * 0.01, LAT0) for i in range(14)]
    p = Problem(cls={"VRPTW"}, nodes=nodes, dist_m=matrix(nodes), demand={i: 1 for i in range(1, 14)},
                fleet=[{"cls": "psv", "count": 3, "capacity": 9, "speed_mps": SPEED}], tw={1: (0.0, 1e5)})
    with pytest.raises(Unsupported):
        get_solver("pyomo").solve(p, seconds=1)


# --- replay honours the windows ---------------------------------------------------------------------------------
def test_replay_honours_windows_and_waits():
    p = inst(service={1: 60.0, 2: 60.0, 3: 60.0, 4: 60.0})
    plan = get_solver("pyvrp").solve(p, seconds=1, seed=1)
    res = get_engine("replay").simulate(p, plan, World(name="open-sea"))
    t = res.traj
    for aid, route in plan.routes.items():
        for node in route:
            lon, lat = p.nodes[node]
            at = t[(t.agent_id == aid) & np.isclose(t.lon, lon) & np.isclose(t.lat, lat) & (t.state == "unload")]
            start = float(at.t.min())
            assert TW[node][0] - 1e-6 <= start <= TW[node][1] + 1e-6, (aid, node, start)
    assert "wait" in set(t.state) and res.kpis["wait_s"] > 0                 # node 1 (2 km) arrives at 400 s, window opens at 1500
    assert (res.events.event == "tw_wait").any()
    assert validate(res.traj, res.agents, land=None).ok
    # replay matches the solver's own schedule (continuous time)
    sched = {b: s for r in plan.routes.values() for b, _, s, _ in route_times(p.dist_m, SPEED, r, p.service_s, TW)}
    assert sched[1] == pytest.approx(1500.0)
    assert res.kpis["distance_km"] == pytest.approx(plan.objective / 1000, rel=0.01)


def test_replay_logs_no_late_service_when_service_is_instant():
    p = inst()
    plan = get_solver("pyvrp").solve(p, seconds=1, seed=1)
    res = get_engine("replay").simulate(p, plan, World(name="open-sea"))
    assert not (res.events.event == "tw_late").any()
    # the CVRP plan, replayed on the same windows, is late: the engine does see the violation
    bad = get_solver("pyvrp").solve(inst(("CVRP",), tw={}), seconds=1, seed=1)
    res2 = get_engine("replay").simulate(p, bad, World(name="open-sea"))
    assert (res2.events.event == "tw_late").any()


# --- offsim run on the template --------------------------------------------------------------------------------
def test_template_reaches_gate_3_as_vrptw(tmp_path):
    from offsim.pipeline import run
    sc = yaml.safe_load(TEMPLATE.read_text())
    assert sc["problem"]["class"] == ["VRPTW"] and sc["solver"] == "pyvrp" and sc["engine"] == "replay"
    rep = run(TEMPLATE, out=tmp_path)
    assert rep["gates"]["0_provenance"]["pass"] and rep["gates"]["1_plan"]["pass"]
    assert rep["gates"]["2_replay_equals_plan"]["pass"] and rep["gates"]["3_contract"]["pass"]
    assert rep["status"].startswith("not comparable")
    assert rep["measured"]["vehicles_used"] >= 1 and rep["kpis"]["wait_s"] >= 0
    assert (tmp_path / "trajectory.csv").exists()


def test_template_with_certify_passes_gate_1b(tmp_path):
    from offsim.pipeline import run
    sc = yaml.safe_load(TEMPLATE.read_text())
    sc["certify"] = {"max_clients": 12, "gap_tol": {"value": 0.02, "assumption": True, "why": "test"}, "solver": "pyomo"}
    path = tmp_path / "scenario.yaml"
    path.write_text(yaml.safe_dump(sc))
    rep = run(path, out=tmp_path / "out", seconds=2.0)
    d = rep["gates"]["1b_exact"]
    assert d["pass"], d
    assert d["detail"]["exact_status"] == "optimal" and d["detail"]["gap"] <= 0.02


# --- CVRP is unchanged -----------------------------------------------------------------------------------------
def test_cvrp_demo_plan_is_unchanged():
    """Golden from before M1 (origin/main d6410c0): demo-oslofjord-supply on great-circle legs, pyvrp, 2 s, seeds 1 and 2."""
    from offsim.pipeline import build_problem
    sc = yaml.safe_load((ROOT / "offsim/papers/demo-oslofjord-supply/scenario.yaml").read_text())
    sc["world"] = "none"
    problem, _, _ = build_problem(sc)
    assert problem.cls == {"CVRP"}
    for seed in (1, 2):
        plan = get_solver("pyvrp").solve(problem, seconds=2, seed=seed)
        assert plan.objective == 114643.0
        assert {frozenset(r) for r in plan.routes.values()} == {frozenset({5, 1, 6}), frozenset({3, 2, 4})}


# --- what still raises Unsupported ----------------------------------------------------------------------------------
@pytest.mark.parametrize("who", ["pyvrp", "pyomo"])
@pytest.mark.parametrize("make", [
    lambda: inst(extra={"release_s": {1: 100.0}}),
    lambda: inst(tw={0: (0.0, 100.0), **TW}),
    lambda: inst(tw={1: (900.0, 100.0)}),
    lambda: inst(tw={9: (0.0, 100.0)}),
    lambda: inst(("CVRP",)),                                   # windows but no VRPTW class: would be dropped silently
    lambda: inst(("VRPTW", "PSV-PDP")),
], ids=["release", "depot-window", "empty-window", "unknown-node", "windows-without-class", "other-class"])
def test_unmapped_features_raise_unsupported(who, make):
    with pytest.raises(Unsupported):
        get_solver(who).solve(make(), seconds=0.5)


@pytest.mark.parametrize("who", ["pyvrp", "pyomo"])
def test_two_fleet_entries_raise_unsupported(who):
    p = inst()
    p.fleet = p.fleet + [dict(p.fleet[0], cls="ctv")]
    with pytest.raises(Unsupported):
        get_solver(who).solve(p, seconds=0.5)


# --- AMPL: model text and data only (no AMPL binary here; parse-check by text, the solve runs on Actions) -------------
MOD = ROOT / "offsim/solve/ampl/vrptw.mod"


def test_vrptw_mod_declares_what_the_dat_writes(tmp_path):
    text = MOD.read_text()
    for needle in ("set NODES;", "param VEH", "param cap", "param tt", "param svc", "param early", "param late",
                   "var x {ARCS} binary;", "var t {CLIENTS}", "minimize total_distance", "subject to mtz",
                   "subject to time_flow", "subject to window_close", "subject to depot_start"):
        assert needle in text, needle
    assert text.count("{") == text.count("}") and text.count("(") == text.count(")") and text.count("[") == text.count("]")
    dat = A.write_dat(inst(service={1: 60.0}), tmp_path / "v.dat").read_text()
    declared = set(re.findall(r"^param (\w+)", text, re.M)) - {"bigM"}       # bigM is computed in the model
    written = set(re.findall(r"^param (\w+)", dat, re.M))
    assert declared == written, (declared, written)
    assert "set CLIENTS := 1 2 3 4;" in dat
    assert re.search(r"param late :=\n1 2500\.000000 2 900\.000000", dat)
    assert re.search(r"param svc :=\n1 60\.000000 2 0\.000000", dat)
    row0 = re.search(r"param tt : 0 1 2 3 4 :=\n0 (\S+) (\S+)", dat)
    assert float(row0.group(2)) == pytest.approx(2000 / SPEED, rel=1e-2)         # tt[0,1] = 400 s


def test_ampl_dat_refuses_unmapped_vrptw_features(tmp_path):
    with pytest.raises(Unsupported):
        A.write_dat(inst(extra={"release": {1: 5}}), tmp_path / "x.dat")
    with pytest.raises(Unsupported):
        A.write_dat(inst(("CVRP",)), tmp_path / "x.dat")            # windows on a CVRP: dropped silently otherwise


def test_ampl_plan_check_sees_windows():
    p = inst()
    assert A.check_plan(p, [[2, 4, 3], [1]])["windows_ok"] is True
    bad = A.check_plan(p, [[1, 2, 3, 4]])
    assert bad["windows_ok"] is False and bad["window_violations"]
    assert "VRPTW" in A.AMPLSolver.classes


def test_ampl_picks_the_vrptw_model(monkeypatch, tmp_path):
    seen = {}

    class Boom(Exception):
        pass

    class FakeAmpl:
        def read(self, path):
            seen["model"] = path
            raise Boom

    monkeypatch.setattr(A, "_start_ampl", lambda: FakeAmpl())
    with pytest.raises(Boom):
        A.AMPLSolver().solve(inst())
    assert seen["model"].endswith("vrptw.mod")
    with pytest.raises(Boom):
        A.AMPLSolver().solve(inst(("CVRP",), tw={}))
    assert seen["model"].endswith("cvrp.mod")
