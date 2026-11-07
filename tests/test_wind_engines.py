"""WOMBAT (O&M) and ORBIT (installation) adapters: tiny cases, contract validity, weather monotonicity.

All weather here is SYNTHETIC and test-only: constant calm vs a wave field that oscillates above the vessels' limits.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from offsim import contract
from offsim.engines import Plan, Problem, Unsupported, WeatherSeries, World, get_engine

PORT = {"lon": 5.30, "lat": 60.40}


def _wx(days: int, calm: bool, year: int = 2011) -> WeatherSeries:
    """TEST-ONLY synthetic hourly series. calm: Hs 0.8 m, 6 m/s. stormy: Hs 1.0-3.5 m (slow swell), 12 m/s."""
    n = 24 * days
    t = np.arange(n) * 3600.0
    if calm:
        hs, wind = np.full(n, 0.8), np.full(n, 6.0)
    else:
        hs, wind = 1.0 + 2.5 * np.abs(np.sin(np.arange(n) / 150.0)), np.full(n, 12.0)
    return WeatherSeries(pd.DataFrame({"t": t, "hs_m": hs, "wind_mps": wind}), "synthetic (test only)", year)


def _finite(kpis: dict, keys):
    for k in keys:
        assert k in kpis, f"missing KPI {k}"
        assert math.isfinite(kpis[k]), f"KPI {k} not finite: {kpis[k]}"


# ------------------------------------------------------------------------------------------- wombat
@pytest.fixture(scope="module")
def wombat_problem():
    pytest.importorskip("wombat")
    lay = [{"id": f"T{i + 1}", "lon": 4.80 + 0.01 * i, "lat": 60.90 + 0.005 * i} for i in range(5)]
    extra = {"wombat": {"layout": lay, "port": PORT, "vessels": ["ctv.yaml", "hlv.yaml"],
                        "failure_rate_factor": 4.0, "horizon_days": 150}}
    return Problem(cls={"WIND-OM"}, nodes=[(PORT["lon"], PORT["lat"])], dist_m=None, demand={}, fleet=[], extra=extra)


@pytest.fixture(scope="module")
def wombat_runs(wombat_problem):
    eng = get_engine("wombat")
    return {name: eng.simulate(wombat_problem, Plan({}, 0.0), World("open-sea"), _wx(150, calm), seed=7)
            for name, calm in (("calm", True), ("storm", False))}


def test_wombat_contract_and_kpis(wombat_runs):
    for r in wombat_runs.values():
        assert r.engine == "wombat" and r.seed == 7
        rep = contract.validate(r.traj, r.agents)
        assert rep.ok, str(rep)
        _finite(r.kpis, ["availability", "availability_energy", "om_cost_usd", "vessel_hours", "weather_wait_s",
                         "distance_km", "makespan_s", "wait_s"])
        assert 0.0 < r.kpis["availability"] <= 1.0
        assert r.kpis["om_cost_usd"] > 0
        assert set(r.agents["agent_id"]) == set(r.traj["agent_id"])
        assert {"sail", "dp"} <= set(r.traj["state"])
        assert "WOMBAT default library" in r.meta["sources"]["turbine"]


def test_wombat_calm_not_worse_than_stormy(wombat_runs):
    c, s = wombat_runs["calm"].kpis, wombat_runs["storm"].kpis
    assert c["availability"] >= s["availability"]
    assert c["weather_wait_s"] <= s["weather_wait_s"]
    assert s["weather_wait_s"] > 0


def test_wombat_deterministic_per_seed(wombat_problem):
    eng = get_engine("wombat")
    a = eng.simulate(wombat_problem, Plan({}, 0.0), World("x"), _wx(60, False), seed=3).kpis
    b = eng.simulate(wombat_problem, Plan({}, 0.0), World("x"), _wx(60, False), seed=3).kpis
    assert a == b


def test_wombat_refuses_instead_of_approximating(wombat_problem):
    eng = get_engine("wombat")
    with pytest.raises(Unsupported):                        # non-trivial plan
        eng.simulate(wombat_problem, Plan({"v": [1]}, 0.0), World("x"), _wx(30, True))
    with pytest.raises(Unsupported):                        # no weather
        eng.simulate(wombat_problem, Plan({}, 0.0), World("x"), None)
    w = _wx(30, True)
    w.df = w.df.iloc[::2].reset_index(drop=True)            # 2-hourly
    with pytest.raises(Unsupported):
        eng.simulate(wombat_problem, Plan({}, 0.0), World("x"), w)
    bad = Problem(cls={"WIND-OM"}, nodes=[], dist_m=None, demand={}, fleet=[],
                  extra={"wombat": {**wombat_problem.extra["wombat"],
                                    "vessels": [{"file": "ctv.yaml", "overrides": {"port_distance": 1.0}}]}})
    with pytest.raises(Unsupported):                        # port_distance shorter than the layout geometry
        eng.simulate(bad, Plan({}, 0.0), World("x"), _wx(30, True))


# ------------------------------------------------------------------------------------------- orbit
@pytest.fixture(scope="module")
def orbit_problem():
    pytest.importorskip("ORBIT")
    cfg = {"wtiv": "example_wtiv", "feeder": "example_feeder", "num_feeders": 2,
           "site": {"depth": 50}, "plant": {"num_turbines": 6},
           "port": {"num_cranes": 2, "monthly_rate": 2e5, "name": "TestPort"},
           "turbine": "12MW_generic", "install_phases": {"TurbineInstallation": "01/05"}}
    geo = {"port": PORT, "site": {"lon": 4.90, "lat": 60.90}}
    return Problem(cls={"WIND-INST"}, nodes=[], dist_m=None, demand={}, fleet=[],
                   extra={"orbit": cfg, "orbit_geo": geo})


@pytest.fixture(scope="module")
def orbit_runs(orbit_problem):
    eng = get_engine("orbit")
    return {name: eng.simulate(orbit_problem, Plan({}, 0.0), World("open-sea"), _wx(200, calm))
            for name, calm in (("calm", True), ("storm", False))}


def test_orbit_contract_and_kpis(orbit_runs):
    for r in orbit_runs.values():
        assert r.engine == "orbit"
        rep = contract.validate(r.traj, r.agents)
        assert rep.ok, str(rep)
        _finite(r.kpis, ["install_days", "installation_capex_usd", "weather_wait_s", "vessel_hours",
                         "distance_km", "makespan_s", "wait_s"])
        assert r.kpis["install_days"] > 0 and r.kpis["installation_capex_usd"] > 0
        assert {"sail", "dp", "load"} <= set(r.traj["state"])
        assert {"WTIV", "Feeder 0", "Feeder 1"} <= set(r.agents["agent_id"])
        assert r.meta["sources"]["wtiv"].startswith("ORBIT default")


def test_orbit_calm_not_slower_than_stormy(orbit_runs):
    c, s = orbit_runs["calm"].kpis, orbit_runs["storm"].kpis
    assert c["install_days"] <= s["install_days"]
    assert c["weather_wait_s"] <= s["weather_wait_s"]
    assert s["weather_wait_s"] > 0


def test_orbit_refuses_instead_of_approximating(orbit_problem):
    eng = get_engine("orbit")
    with pytest.raises(Unsupported):                        # weather far too short for the installation
        eng.simulate(orbit_problem, Plan({}, 0.0), World("x"), _wx(3, False))
    with pytest.raises(Unsupported):
        eng.simulate(orbit_problem, Plan({"v": [1]}, 0.0), World("x"), _wx(200, True))
    cfg = dict(orbit_problem.extra["orbit"], install_phases=["ArrayCableInstallation"])
    p = Problem(cls={"WIND-INST"}, nodes=[], dist_m=None, demand={}, fleet=[],
                extra={"orbit": cfg, "orbit_geo": orbit_problem.extra["orbit_geo"]})
    with pytest.raises(Unsupported):                        # phase without a trajectory mapping
        eng.simulate(p, Plan({}, 0.0), World("x"), _wx(200, True))
    cfg = dict(orbit_problem.extra["orbit"], site={"depth": 50, "distance": 1.0})
    p = Problem(cls={"WIND-INST"}, nodes=[], dist_m=None, demand={}, fleet=[],
                extra={"orbit": cfg, "orbit_geo": orbit_problem.extra["orbit_geo"]})
    with pytest.raises(Unsupported):                        # site.distance below the great-circle distance
        eng.simulate(p, Plan({}, 0.0), World("x"), _wx(200, True))
