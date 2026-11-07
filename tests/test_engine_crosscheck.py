"""Two engines, one plan: deterministic KPIs must agree (docs/ENGINES.md, "Choosing"), and OpenCLSim's weather
plugin must delay unloads in a storm.

Service-time convention: both engines apply Problem.service_s as a FIXED duration per stop (replay: timeout;
OpenCLSim: ShiftAmountActivity(duration=service_s)), so there is no convention gap to explain. The only expected
differences are (a) OpenCLSim sails the WGS84 geodesic, replay and the contract use the sphere (<0.5 % on
distance, hence on sailing time) and (b) log timestamps are rounded to microseconds.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from offsim.contract import validate
from offsim.engines import Plan, Problem, WeatherSeries, World, get_engine, get_solver
from offsim.solve.pyvrp_adapter import matrix

SERVICE = 1800.0


def instance(n=6, service=SERVICE, extra=None):
    rng = np.random.default_rng(11)
    nodes = [(5.0, 60.0)] + [(5.0 + x, 60.0 + y) for x, y in rng.random((n, 2)) * 0.3]
    return Problem(cls={"CVRP"}, nodes=nodes, dist_m=matrix(nodes), demand={i: 3 for i in range(1, n + 1)},
                   fleet=[{"cls": "psv", "count": 3, "capacity": 9, "speed_mps": 6.0}],
                   service_s={i: service for i in range(1, n + 1)}, extra=extra or {})


def storm(hours=120, start_h=1, end_h=8, hs_storm=4.5):
    t = np.arange(hours + 1) * 3600.0
    hs = np.where((t >= start_h * 3600) & (t < end_h * 3600), hs_storm, 1.0)
    return WeatherSeries(df=pd.DataFrame({"t": t, "hs_m": hs, "wind_mps": 8.0}), source="synthetic storm", year=2000)


@pytest.fixture(scope="module")
def plan():
    return get_solver("pyvrp").solve(instance(), seconds=0.5, seed=1)


def run(engine, problem, plan, world=None, weather=None):
    return get_engine(engine).simulate(problem, plan, world or World(name="open"), weather=weather)


def test_replay_and_openclsim_agree_without_weather(plan):
    p = instance()
    a, b = run("replay", p, plan), run("openclsim", p, plan)
    assert validate(b.traj, b.agents).ok
    assert b.kpis["distance_km"] == pytest.approx(a.kpis["distance_km"], rel=0.01)
    assert b.kpis["makespan_s"] == pytest.approx(a.kpis["makespan_s"], rel=0.02)
    assert a.kpis["wait_s"] == b.kpis["wait_s"] == 0.0
    # per-agent too, and the unload happens at the same stops in the same order
    for aid, ka in a.meta["agents"].items():
        assert b.meta["agents"][aid]["distance_km"] == pytest.approx(ka["distance_km"], rel=0.01, abs=1e-9)
        assert b.meta["agents"][aid]["time_by_state_s"].get("unload", 0.0) == pytest.approx(
            ka["time_by_state_s"].get("unload", 0.0), rel=1e-6)
    seq = lambda r: r.traj[r.traj.state == "unload"].sort_values(["t", "agent_id"])[["agent_id", "lon", "lat"]].reset_index(drop=True)
    pd.testing.assert_frame_equal(seq(a), seq(b))


def test_sea_lane_legs_are_followed_by_both_engines(plan):
    p = instance()
    legs = {}
    for r in filter(None, plan.routes.values()):
        path = [0] + r + [0]
        for u, v in zip(path, path[1:]):
            (x0, y0), (x1, y1) = p.nodes[u], p.nodes[v]
            legs[(u, v)] = [(x0, y0), ((x0 + x1) / 2, (y0 + y1) / 2 + 0.05), (x1, y1)]      # detour around "land"
    w = World(name="lanes", legs=legs)
    a, b = run("replay", p, plan, w), run("openclsim", p, plan, w)
    straight = run("replay", p, plan)
    assert a.kpis["distance_km"] > 1.05 * straight.kpis["distance_km"]
    assert b.kpis["distance_km"] == pytest.approx(a.kpis["distance_km"], rel=0.01)
    assert b.kpis["makespan_s"] == pytest.approx(a.kpis["makespan_s"], rel=0.02)
    assert validate(b.traj, b.agents).ok


def test_berth_queue_matches_between_engines():
    p = instance(service=600.0, extra={"berths": {1: 1}})
    p.service_s[1] = 20000.0                       # node 1 is slow, so the second visitor queues
    plan = Plan(routes={"PSV-1": [1], "PSV-2": [2, 1], "PSV-3": []}, objective=0.0)
    a, b = run("replay", p, plan), run("openclsim", p, plan)
    assert a.kpis["wait_s"] > 3600 and (a.events.event == "queue").any()
    assert b.kpis["wait_s"] == pytest.approx(a.kpis["wait_s"], rel=0.02)
    assert b.kpis["weather_wait_s"] == 0.0 and b.meta["wait_breakdown_s"]["queue"] == pytest.approx(b.kpis["wait_s"], abs=1e-3)
    assert b.kpis["makespan_s"] == pytest.approx(a.kpis["makespan_s"], rel=0.02)
    assert validate(b.traj, b.agents).ok


def test_storm_makes_openclsim_wait_for_a_window(plan):
    limit = 2.5
    p0 = instance()
    p = instance(extra={"limits": {"hs_m": limit}})
    wx = storm()
    calm = run("openclsim", p0, plan)
    rough = run("openclsim", p, plan, weather=wx)
    assert rough.weather == "synthetic storm"
    assert rough.kpis["weather_wait_s"] > 0
    assert rough.kpis["makespan_s"] > calm.kpis["makespan_s"]
    assert rough.kpis["wait_s"] == pytest.approx(rough.kpis["weather_wait_s"], abs=1e-3)   # no berth queue here
    assert rough.kpis["distance_km"] == pytest.approx(calm.kpis["distance_km"], rel=1e-9)  # weather only delays
    assert validate(rough.traj, rough.agents).ok
    assert (rough.events.event == "weather_wait").any()
    # no unload starts or runs inside the storm: Hs <= limit over [start, start + service]
    hs = lambda t: float(np.interp(np.floor(t / 3600) * 3600, wx.df.t, wx.df.hs_m))
    for _, r in rough.traj[rough.traj.state == "unload"].iterrows():
        assert max(hs(r.t), hs(r.t + SERVICE - 1)) <= limit, f"unload at t={r.t} in a storm"
    # vessels held back until the storm ends (08:00), so the last unload finishes after it
    assert rough.traj.t.max() >= 8 * 3600 + SERVICE
    # replay ignores the same series: same plan, no delay, and it says so
    ign = run("replay", p, plan, weather=wx)
    assert ign.kpis["makespan_s"] == pytest.approx(calm.kpis["makespan_s"], rel=0.02) and "ignored" in ign.meta["weather_note"]


def test_weather_edge_cases_are_explicit(plan):
    from offsim.engines import Unsupported
    p = instance(extra={"limits": {"hs_m": 0.5}})
    with pytest.raises(Unsupported):                             # series never <= 0.5 m
        run("openclsim", p, plan, weather=storm())
    p = instance(extra={"limits": {"hs_m": 2.5}})
    short = storm(hours=3, start_h=1, end_h=3)                   # storm runs to the end of the data: no window
    with pytest.raises(Unsupported):
        run("openclsim", p, plan, weather=short)
    mild = run("openclsim", p, plan, weather=storm(hs_storm=2.0))   # limit never exceeded: no plugin, no wait
    assert mild.kpis["weather_wait_s"] == 0.0 and "never exceeds" in mild.meta["weather_note"]
    note = run("openclsim", instance(), plan, weather=storm())
    assert "no 'limits'" in note.meta["weather_note"] and note.kpis["weather_wait_s"] == 0.0
    two = instance(extra={"limits": {"hs_m": 2.5, "wind_mps": 5.0}})
    with pytest.raises(Unsupported):
        run("openclsim", two, plan, weather=storm())
