"""Registry, solvers and engines behave as the interfaces in offsim/engines/base.py promise.

Small synthetic instances in open sea (World.land = None); each file runs in a few seconds.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from offsim.contract import validate
from offsim.engines import (Plan, Problem, Unsupported, WeatherSeries, World, available, get_engine, get_solver)
from offsim.solve.pyvrp_adapter import matrix


def instance(n_clients=6, seed=3, cap=9, count=3, demand=3, service=900.0, spread=0.25):
    rng = np.random.default_rng(seed)
    nodes = [(5.0, 60.0)] + [(5.0 + x, 60.0 + y) for x, y in rng.random((n_clients, 2)) * spread]
    return Problem(cls={"CVRP"}, nodes=nodes, dist_m=matrix(nodes), demand={i: demand for i in range(1, n_clients + 1)},
                   fleet=[{"cls": "psv", "count": count, "capacity": cap, "speed_mps": 6.0}],
                   service_s={i: service for i in range(1, n_clients + 1)})


def test_registry_lists_every_tool_we_ship():
    av = available()
    assert av["solvers"]["pyvrp"] == "ok" and av["solvers"]["pyomo"] == "ok"
    assert av["engines"]["replay"] == "ok" and av["engines"]["openclsim"] == "ok"
    assert set(av["engines"]) == {"replay", "openclsim", "wombat", "orbit", "road", "gtfs"}    # unbuilt ones report an error string
    assert set(av["solvers"]) == {"pyvrp", "pyomo", "ampl"}
    for name, cls in (("pyvrp", {"CVRP"}), ("pyomo", {"CVRP"})):
        assert get_solver(name).classes == cls and get_solver(name).name == name
    assert get_engine("replay").needs_weather is False and get_engine("openclsim").needs_weather is False
    with pytest.raises(KeyError):
        get_engine("nope")


def test_pyvrp_plan_shape_and_unsupported():
    p = instance()
    plan = get_solver("pyvrp").solve(p, seconds=0.5, seed=1)
    assert set(plan.routes) == {"PSV-1", "PSV-2", "PSV-3"}
    assert sorted(c for r in plan.routes.values() for c in r) == [1, 2, 3, 4, 5, 6]
    assert all(sum(p.demand[c] for c in r) <= 9 for r in plan.routes.values())
    assert plan.solver == "pyvrp" and plan.objective_unit == "m" and plan.bound is None
    for bad in (Problem(**{**p.__dict__, "cls": {"VRPTW"}}), Problem(**{**p.__dict__, "tw": {1: (0.0, 100.0)}}),
                Problem(**{**p.__dict__, "demand": {**p.demand, 1: 2.5}})):
        with pytest.raises(Unsupported):
            get_solver("pyvrp").solve(bad, seconds=0.2)


def test_pyomo_certifies_pyvrp_on_six_clients():
    p = instance()
    heur = get_solver("pyvrp").solve(p, seconds=1.0, seed=1)
    exact = get_solver("pyomo").solve(p, seconds=15.0)
    assert exact.status == "optimal" and exact.solver == "pyomo"
    assert exact.objective <= heur.objective + 1e-6
    assert exact.bound is not None and exact.bound <= exact.objective + 1e-6   # a valid lower bound
    assert exact.bound <= heur.objective + 1e-6
    assert sorted(c for r in exact.routes.values() for c in r) == [1, 2, 3, 4, 5, 6]
    assert set(exact.routes) == set(heur.routes)


def test_pyomo_refuses_large_instances():
    with pytest.raises(Unsupported):
        get_solver("pyomo").solve(instance(n_clients=13, count=5), seconds=1)


@pytest.mark.parametrize("engine", ["replay", "openclsim"])
def test_engines_pass_the_contract(engine):
    p = instance()
    plan = get_solver("pyvrp").solve(p, seconds=0.5, seed=1)
    res = get_engine(engine).simulate(p, plan, World(name="open"), weather=None, seed=0)
    rep = validate(res.traj, res.agents, land=None)
    assert rep.ok, str(rep)
    assert res.engine == engine and res.weather is None
    assert set(res.traj["agent_id"]) == set(plan.routes)
    for k in ("distance_km", "makespan_s", "wait_s", "weather_wait_s"):
        assert isinstance(res.kpis[k], float)
    assert res.kpis["distance_km"] == pytest.approx(plan.objective / 1000, rel=0.01)
    assert res.kpis["weather_wait_s"] == 0.0
    # every unit was unloaded: last load of each agent is 0
    assert res.traj.groupby("agent_id")["load"].last().eq(0).all()


def test_replay_ignores_weather_and_says_so():
    p = instance()
    plan = get_solver("pyvrp").solve(p, seconds=0.5)
    wx = WeatherSeries(df=pd.DataFrame({"t": [0.0, 3600.0], "hs_m": [9.0, 9.0], "wind_mps": [1.0, 1.0]}), source="test")
    res = get_engine("replay").simulate(p, plan, World(name="open"), weather=wx)
    assert res.weather is None and "ignored" in res.meta["weather_note"] and res.kpis["weather_wait_s"] == 0.0


def test_engines_refuse_unknown_agents_and_missing_lanes():
    p = instance()
    bad = Plan(routes={"TUG-1": [1]}, objective=0.0)
    legs = {(0, 1): [p.nodes[0], p.nodes[1]]}
    plan = Plan(routes={"PSV-1": [1, 2]}, objective=0.0)
    for eng in ("replay", "openclsim"):
        with pytest.raises(Unsupported):
            get_engine(eng).simulate(p, bad, World(name="w"))
        with pytest.raises(Unsupported):                       # leg 1->2 / 2->0 absent while legs are given
            get_engine(eng).simulate(p, plan, World(name="w", legs=legs))
    with pytest.raises(Unsupported):
        get_engine("openclsim").simulate(Problem(**{**p.__dict__, "tw": {1: (0.0, 5.0)}}), plan, World(name="w"))
