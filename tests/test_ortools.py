"""OR-Tools routing end to end (package A1): second independent solver for CVRP/VRPTW, and the PDP class.

Cross-check first: on the demo CVRP instance OR-Tools, PyVRP and the exact Pyomo model must agree (the exact optimum
is a floor for every heuristic). Then the windows bind (VRPTW), pickup-delivery precedence / same vehicle / load hold
in the plan and in the replay, determinism, and every unmapped feature raises Unsupported.

Instance PDP-line: stops on a line east of the base at 2, 4, 6, 8 km (nodes 1..4), 5 m/s. Pairs: pickup 3 (6 km) ->
delivery 1 (2 km) and pickup 4 (8 km) -> delivery 2 (4 km), 3 units each. Visiting nearest-first (1, 2, 3, 4) delivers
before it picks up: infeasible. Any feasible route goes out to the pickups first.
"""
import sys

import numpy as np
import pytest
import yaml

from conftest import ROOT
from offsim.contract import validate
from offsim.engines.base import Problem, Unsupported, World, get_engine, get_solver
from offsim.solve.ortools_solver import check_pdp, pdp_violations
from offsim.solve.pyvrp_adapter import matrix, windows_violations

LON0, LAT0 = 10.0, 59.9
DX = 1 / (111320 * np.cos(np.radians(LAT0)))          # degrees of longitude per metre at this latitude
SPEED = 5.0
TEMPLATE = ROOT / "offsim/papers/_templates/pdp/scenario.yaml"
TW = {1: (1500.0, 2500.0), 2: (0.0, 900.0), 3: (0.0, 5000.0), 4: (0.0, 1700.0)}      # as tests/test_vrptw.py


def line(km):
    """Base plus stops at the given signed distances (km) east (+) or west (-) of the base."""
    return [(LON0, LAT0)] + [(LON0 + k * 1000 * DX, LAT0) for k in km]


def vrptw_inst(cls=("VRPTW",), tw=None, count=2, **kw):
    nodes = line((2, 4, 6, 8))
    return Problem(cls=set(cls), nodes=nodes, dist_m=matrix(nodes), demand={i: 1 for i in range(1, 5)},
                   fleet=[{"cls": "psv", "count": count, "capacity": 10, "speed_mps": SPEED, "domain": "sea"}],
                   service_s={i: 60.0 for i in range(1, 5)}, tw=TW if tw is None else tw, **kw)


def pdp_inst(km=(2, 4, 6, 8), pairs=None, count=1, cap=10, q=3, cls=("PDP",), **kw):
    nodes = line(km)
    pairs = {3: 1, 4: 2} if pairs is None else pairs
    demand = {}
    for p, d in pairs.items():
        demand[d], demand[p] = q, -q
    return Problem(cls=set(cls), nodes=nodes, dist_m=matrix(nodes), demand=demand, pairs=pairs,
                   fleet=[{"cls": "psv", "count": count, "capacity": cap, "speed_mps": SPEED, "domain": "sea"}], **kw)


def served(plan):
    return sorted(c for r in plan.routes.values() for c in r)


def demo_cvrp():
    from offsim.pipeline import build_problem
    sc = yaml.safe_load((ROOT / "offsim/papers/demo-oslofjord-supply/scenario.yaml").read_text())
    sc["world"] = "none"
    return build_problem(sc)[0]


# --- (a) the cross-check -------------------------------------------------------------------------------------------
def test_ortools_agrees_with_pyvrp_and_the_exact_bound_on_the_demo_cvrp():
    p = demo_cvrp()
    assert p.cls == {"CVRP"}
    orp = get_solver("ortools").solve(p, seconds=2, seed=1)
    pv = get_solver("pyvrp").solve(p, seconds=2, seed=1)
    ex = get_solver("pyomo").solve(p, seconds=30)           # after ortools: both stay usable in one process
    assert ex.status == "optimal" and ex.bound is not None
    TOL = 0.005                                              # 0.5 % between the two heuristics
    assert orp.objective >= ex.bound - 1e-6                  # nobody beats the exact optimum
    assert orp.objective <= ex.objective * (1 + TOL)         # OR-Tools no worse than the exact optimum + 0.5 %
    assert abs(orp.objective - pv.objective) <= TOL * pv.objective
    assert served(orp) == served(pv) == [1, 2, 3, 4, 5, 6]
    assert {frozenset(r) for r in orp.routes.values()} == {frozenset(r) for r in ex.routes.values()}
    assert orp.solver == "ortools" and orp.objective_unit == "m" and set(orp.routes) == set(pv.routes)
    loads = [sum(p.demand[c] for c in r) for r in orp.routes.values()]
    assert max(loads) <= p.fleet[0]["capacity"]


def test_ortools_and_highspy_share_one_process():
    """ortools and highspy clash on HiGHS symbols if both are imported in one interpreter; the solver isolates ortools."""
    get_solver("ortools").solve(vrptw_inst(("VRPTW",), tw={}), seconds=0.5)
    assert "ortools" not in sys.modules and "ortools.constraint_solver" not in sys.modules
    import highspy  # noqa: F401  (would have failed to import after an in-process ortools import)
    assert get_solver("pyomo").solve(vrptw_inst(("VRPTW",), tw={}), seconds=10).status == "optimal"


def test_registry_and_classes():
    s = get_solver("ortools")
    assert s.name == "ortools" and s.classes == {"CVRP", "VRPTW", "PDP"}


# --- (b) the windows bind ---------------------------------------------------------------------------------------
def test_vrptw_windows_bind_and_the_plan_is_window_feasible():
    cvrp = get_solver("ortools").solve(vrptw_inst(("CVRP",), tw={}), seconds=1)
    p = vrptw_inst()
    assert windows_violations(p.dist_m, SPEED, list(cvrp.routes.values()), p.service_s, TW), "CVRP optimum must break a window"
    plan = get_solver("ortools").solve(p, seconds=1)
    assert plan.objective > cvrp.objective + 1000            # splitting into two routes costs real distance
    assert served(plan) == [1, 2, 3, 4] and plan.meta["time_windows"] == 4
    assert windows_violations(p.dist_m, SPEED, list(plan.routes.values()), p.service_s, TW) == []
    ex = get_solver("pyomo").solve(p, seconds=30)
    assert ex.status == "optimal" and plan.objective >= ex.objective - 1e-6         # exact <= heuristic
    assert plan.objective <= get_solver("pyvrp").solve(p, seconds=1, seed=1).objective * 1.005
    with pytest.raises(RuntimeError):                       # one vessel cannot meet all four windows: never an infeasible plan
        get_solver("ortools").solve(vrptw_inst(count=1), seconds=1)


def test_vrptw_replay_waits_for_the_window():
    p = vrptw_inst()
    plan = get_solver("ortools").solve(p, seconds=1)
    res = get_engine("replay").simulate(p, plan, World(name="open-sea"))
    t = res.traj
    for aid, route in plan.routes.items():
        for node in route:
            lon, lat = p.nodes[node]
            start = float(t[(t.agent_id == aid) & np.isclose(t.lon, lon) & np.isclose(t.lat, lat) & (t.state == "unload")].t.min())
            assert TW[node][0] - 1e-6 <= start <= TW[node][1] + 1e-6
    assert validate(res.traj, res.agents, land=None).ok
    assert res.kpis["distance_km"] == pytest.approx(plan.objective / 1000, rel=0.01)


# --- (c) PDP: precedence, same vehicle, load -----------------------------------------------------------------------
def test_naive_route_is_infeasible_and_ortools_plan_is_not():
    p = pdp_inst()
    naive = [[1, 2, 3, 4]]                                    # nearest first: delivers before it picks up
    bad = pdp_violations(p, naive)
    assert any("delivery before pickup" in b for b in bad) and any("load" in b for b in bad)
    plan = get_solver("ortools").solve(p, seconds=1)
    assert plan.meta["pairs"] == 2 and served(plan) == [1, 2, 3, 4]
    assert pdp_violations(p, plan.routes) == []
    route = plan.routes["PSV-1"]
    assert route.index(3) < route.index(1) and route.index(4) < route.index(2)       # pickup before delivery
    assert plan.objective == pytest.approx(16000.0, rel=0.005)      # out to 8 km and back along the line: nothing shorter exists


def test_precedence_holds_when_pickup_and_delivery_are_at_the_same_position():
    # nodes 1 and 2 are co-located (as are 3 and 4); the strict order must still hold
    p = pdp_inst(km=(4, 4, 2, 2), pairs={1: 2, 3: 4})
    assert p.dist_m[1][2] == 0
    for _ in range(2):
        plan = get_solver("ortools").solve(p, seconds=1)
        r = plan.routes["PSV-1"]
        assert pdp_violations(p, plan.routes) == [] and r.index(1) < r.index(2) and r.index(3) < r.index(4)


def test_same_vehicle_holds_when_two_vehicles_are_forced():
    """East pair and west pair with windows that no single vehicle can meet: two vehicles, each keeps its pair together."""
    km = (2, 4, -2, -4)
    base = pdp_inst(km=km, pairs={1: 2, 3: 4}, count=2, q=1, cls=("PDP", "VRPTW"))
    p = Problem(**{**base.__dict__, "tw": {i: (0.0, 1200.0) for i in range(1, 5)}})       # 4 km = 800 s; both sides need > 1200 s
    plan = get_solver("ortools").solve(p, seconds=1)
    assert plan.meta["vehicles_used"] == 2 and pdp_violations(p, plan.routes) == []
    where = {n: aid for aid, r in plan.routes.items() for n in r}
    assert where[1] == where[2] and where[3] == where[4] and where[1] != where[3]
    assert windows_violations(p.dist_m, SPEED, list(plan.routes.values()), {}, p.tw) == []
    assert plan.objective == pytest.approx(16000.0, rel=0.005)
    # the checker itself sees a split pair
    split = pdp_violations(p, [[1, 3], [2, 4]])
    assert any("split over vehicles" in b for b in split)


def test_replay_honours_the_pdp_plan_and_the_contract_passes():
    p = pdp_inst()
    plan = get_solver("ortools").solve(p, seconds=1)
    # The replay engine is class-agnostic about demand (it only unloads signed demand); it lists CVRP/VRPTW, so the
    # engine is handed the same Problem labelled CVRP. The pipeline wiring of the PDP label is the integrator's (A1 report).
    as_cvrp = Problem(**{**p.__dict__, "cls": {"CVRP"}})
    res = get_engine("replay").simulate(as_cvrp, plan, World(name="open-sea"))
    load = res.traj["load"]
    assert load.min() >= 0 and load.max() == 6 and load.iloc[0] == 0                  # rises at the pickups, falls at the deliveries
    assert validate(res.traj, res.agents, land=None).ok
    assert res.kpis["distance_km"] == pytest.approx(plan.objective / 1000, rel=0.01)
    # unload events happen in route order: the pickup's stop precedes its delivery's stop for each pair
    t = res.traj[res.traj.state == "unload"]
    first = {}
    for node in (1, 2, 3, 4):
        lon, lat = p.nodes[node]
        first[node] = float(t[np.isclose(t.lon, lon) & np.isclose(t.lat, lat)].t.min())
    assert first[3] < first[1] and first[4] < first[2]
    # the naive route is rejected by the contract: the load on board goes negative
    naive = Problem(**{**p.__dict__, "cls": {"CVRP"}})
    bad = get_engine("replay").simulate(naive, type(plan)(routes={"PSV-1": [1, 2, 3, 4]}, objective=0.0), World(name="open-sea"))
    assert not validate(bad.traj, bad.agents, land=None).ok


# --- (d) offsim run on the template --------------------------------------------------------------------------------
def test_template_declares_pairs_ortools_and_replay():
    sc = yaml.safe_load(TEMPLATE.read_text())
    assert sc["problem"]["class"] == ["PDP"] and sc["solver"] == "ortools" and sc["engine"] == "replay"
    roles = {}
    for s in sc["instance"]["stops"]:
        roles.setdefault(s["pair"], []).append(s["role"])
        assert "assumption" in s["demand"] or "src" in s["demand"]
    assert all(sorted(r) == ["delivery", "pickup"] for r in roles.values())


@pytest.mark.xfail(strict=True, reason="gate 0 tool_mismatch: the replay engine lists CVRP/VRPTW only and the pipeline does not "
                   "build Problem.pairs (pipeline.py and the engines are outside package A1). Wiring below; strict so the "
                   "integrator removes this mark when it lands.")
def test_template_reaches_gate_3_as_pdp(tmp_path):
    from offsim.pipeline import run
    rep = run(TEMPLATE, out=tmp_path)
    assert rep["gates"]["3_contract"]["pass"]


@pytest.fixture
def pdp_wired(monkeypatch):
    """The three edits the integrator needs, applied in-process: ROUTING gains PDP, build_problem fills pairs and the
    signed demand from `role` / `pair`, and the replay engine lists PDP."""
    from offsim import pipeline
    from offsim.engines.replay_engine import ReplayEngine
    orig = pipeline.build_problem

    def build(sc, data_root=None):
        problem, world, meta = orig(sc, data_root)
        stops = sc["instance"]["stops"]
        by_pair = {}
        for i, s in enumerate(stops, 1):
            by_pair.setdefault(s["pair"], {})[s["role"]] = i
        problem.pairs = {r["pickup"]: r["delivery"] for r in by_pair.values()}
        for pk, dl in problem.pairs.items():
            problem.demand[pk] = -abs(problem.demand[dl])
        return problem, world, meta

    monkeypatch.setattr(pipeline, "ROUTING", pipeline.ROUTING | {"PDP"})
    monkeypatch.setattr(pipeline, "build_problem", build)
    monkeypatch.setattr(ReplayEngine, "classes", {"CVRP", "VRPTW", "PDP"})


def test_template_reaches_gate_3_with_the_pipeline_hooks(tmp_path, pdp_wired):
    from offsim.pipeline import run
    rep = run(TEMPLATE, out=tmp_path)
    g = rep["gates"]
    assert g["0_provenance"]["pass"] and g["1_plan"]["pass"] and g["2_replay_equals_plan"]["pass"] and g["3_contract"]["pass"], g
    assert rep["provenance"]["solver"] == "ortools" and rep["provenance"]["engine"] == "replay"
    assert rep["measured"]["vehicles_used"] >= 1 and (tmp_path / "trajectory.csv").exists()
    import pandas as pd
    assert pd.read_csv(tmp_path / "trajectory.csv")["load"].min() >= 0


# --- (e) what raises Unsupported -------------------------------------------------------------------------------------
def _with(p, **kw):
    return Problem(**{**p.__dict__, **kw})


@pytest.mark.parametrize("make", [
    lambda: vrptw_inst(extra={"release_s": {1: 100.0}}),
    lambda: vrptw_inst(tw={0: (0.0, 100.0), **TW}),
    lambda: vrptw_inst(tw={1: (900.0, 100.0)}),
    lambda: vrptw_inst(tw={9: (0.0, 100.0)}),
    lambda: vrptw_inst(("CVRP",)),                                       # windows without VRPTW: dropped silently otherwise
    lambda: vrptw_inst(("VRPTW", "PSV-PDP")),
    lambda: _with(vrptw_inst(), demand={1: 1.5, 2: 1, 3: 1, 4: 1}),     # fractional demand
    lambda: _with(vrptw_inst(), demand={1: 99, 2: 1, 3: 1, 4: 1}),      # a stop larger than the vehicle
    lambda: _with(vrptw_inst(), demand={1: -1, 2: 1, 3: 1, 4: 1}),      # negative demand without PDP
    lambda: _with(pdp_inst(), pairs={}),                                 # PDP without pairs
    lambda: _with(pdp_inst(), cls={"CVRP"}),                             # pairs without PDP: pairing dropped silently
    lambda: pdp_inst(pairs={3: 1}),                                      # stops 2 and 4 are in no pair
    lambda: _with(pdp_inst(), pairs={3: 1, 4: 1}),                       # a node in two pairs
    lambda: _with(pdp_inst(), pairs={1: 1, 4: 2}),                       # pickup == delivery
    lambda: _with(pdp_inst(), pairs={3: 1, 9: 2}),                       # node outside 1..n-1
    lambda: _with(pdp_inst(), demand={1: 3, 2: 3, 3: -2, 4: -3}),        # unequal quantities on a pair
    lambda: _with(pdp_inst(), demand={1: -3, 2: -3, 3: 3, 4: 3}),        # delivery/pickup signs reversed
    lambda: _with(pdp_inst(), extra={"release": {1: 5}}, cls={"PDP", "VRPTW"}, tw={1: (0.0, 9e3)}),
], ids=["release", "depot-window", "empty-window", "unknown-node", "windows-without-class", "other-class", "fractional",
        "too-big", "negative-demand", "pdp-no-pairs", "pairs-no-pdp", "unpaired-stop", "node-in-two-pairs", "self-pair",
        "pair-outside", "unequal-quantity", "reversed-signs", "pdp-release"])
def test_unmapped_features_raise_unsupported(make):
    with pytest.raises(Unsupported):
        get_solver("ortools").solve(make(), seconds=0.5)


def test_two_fleet_entries_raise_unsupported():
    p = vrptw_inst()
    p.fleet = p.fleet + [dict(p.fleet[0], cls="ctv")]
    with pytest.raises(Unsupported):
        get_solver("ortools").solve(p, seconds=0.5)


def test_check_pdp_returns_the_pairs():
    assert check_pdp(pdp_inst()) == {3: 1, 4: 2}
    assert check_pdp(vrptw_inst()) == {}


# --- (f) determinism --------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("make", [demo_cvrp, vrptw_inst, pdp_inst], ids=["cvrp", "vrptw", "pdp"])
def test_same_input_same_plan_twice(make):
    p = make()
    a = get_solver("ortools").solve(p, seconds=1, seed=1)
    b = get_solver("ortools").solve(make(), seconds=1, seed=1)
    c = get_solver("ortools").solve(p, seconds=1, seed=99)          # OR-Tools routing has no seed: the plan does not depend on it
    assert a.routes == b.routes == c.routes and a.objective == b.objective == c.objective
    assert a.meta["first_solution"] == "PARALLEL_CHEAPEST_INSERTION" and a.meta["metaheuristic"] == "GUIDED_LOCAL_SEARCH"
    assert a.meta["seed"] == 1 and a.meta["seed_used"] is False
