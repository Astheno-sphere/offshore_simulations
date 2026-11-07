"""L3 ensemble: CRN pairing, quantiles, contract enforcement, JSON-safe report, weather years, experiment decision.

Uses a small fake Engine (honours the Engine protocol, emits valid contract rows) so no real engine is needed."""
import json

import numpy as np
import pandas as pd
import pytest

from offsim.engines.base import Plan, Problem, SimResult, Unsupported, WeatherSeries, World
from offsim.montecarlo import Ensemble, run_ensemble
from offsim.research import run_experiment
from offsim.weather.years import SYNTHETIC_SOURCE, load_years, season_months, synthetic_years

A, B = (5.0, 60.0), (5.5, 60.0)     # ~27.8 km apart


class FakeEngine:
    """One PSV: load, sail A->B, wait on weather (hours with Hs above limit in the first 100 h), unload.
    plan.meta: wait_factor scales the wait; violate=True sails impossibly fast (contract speed violation)."""
    name = "fake"
    classes = {"CVRP"}
    needs_weather = True
    HS_LIMIT = 2.5

    def simulate(self, problem, plan, world, weather=None, seed=0):
        rng = np.random.default_rng(seed)
        hs = weather.df["hs_m"].to_numpy()[:100]
        wait = float((hs > self.HS_LIMIT).sum()) * 3600.0 * plan.meta.get("wait_factor", 1.0)
        wait += float(rng.uniform(0, 900.0))        # seed noise: identical across variants (CRN)
        sail = 10.0 if plan.meta.get("violate") else 5560.0
        t1 = 3600.0
        t2 = t1 + sail
        t3 = t2 + wait
        rows = [("psv1", 0.0, *A, "load"), ("psv1", t1, *A, "sail"), ("psv1", t2, *B, "wait"),
                ("psv1", t3, *B, "unload"), ("psv1", t3 + 1800.0, *B, "idle")]
        traj = pd.DataFrame(rows, columns=["agent_id", "t", "lon", "lat", "state"])
        agents = pd.DataFrame([{"agent_id": "psv1", "cls": "psv", "vmax_mps": 8.0, "capacity": 10.0, "domain": "sea"}])
        k = {"wait_s": wait, "makespan_s": t3 + 1800.0}
        return SimResult(traj, agents, pd.DataFrame(), k, self.name, seed, weather.source if weather else None)


def setup(n_years=6, hours=120):
    prob = Problem({"CVRP"}, [A, B], None, {1: 1.0}, [{"cls": "psv", "count": 1}])
    return prob, World("open-sea"), synthetic_years(n_years, hours, seed=3)


def plans(**extra):
    d = {"base": Plan({"psv1": [1]}, 1.0, meta={"wait_factor": 1.0}),
         "better": Plan({"psv1": [1]}, 1.0, meta={"wait_factor": 0.5}),
         "twin": Plan({"psv1": [1]}, 1.0, meta={"wait_factor": 1.0})}
    d.update(extra)
    return d


def test_runs_table_and_quantiles_monotone():
    prob, world, wx = setup()
    ens = run_ensemble(prob, None, world, FakeEngine(), wx, [0, 1, 2], variants=plans())
    assert ens.ok and len(ens.runs) == 3 * 6 * 3
    assert {"variant", "year", "seed", "wait_s", "makespan_s"} <= set(ens.runs.columns)
    q = ens.quantiles("wait_s", q=(0.1, 0.5, 0.9))
    assert (q["p10"] <= q["p50"]).all() and (q["p50"] <= q["p90"]).all()
    assert (q["n"] == 18).all()
    assert q.loc["better", "p50"] < q.loc["base", "p50"]
    with pytest.raises(KeyError):
        ens.quantiles("nope")


def test_single_plan_defaults_to_base():
    prob, world, wx = setup(2)
    ens = run_ensemble(prob, plans()["base"], world, FakeEngine(), wx, [7])
    assert ens.variants == ["base"] and len(ens.runs) == 2


def test_common_random_numbers_identical_variants_compare_to_exact_zero():
    prob, world, wx = setup()
    ens = run_ensemble(prob, None, world, FakeEngine(), wx, [0, 1, 2, 3], variants=plans())
    c = ens.compare("wait_s", "twin", "base")
    assert c.mean == 0.0 and c.ci == (0.0, 0.0) and c.n == 24
    assert (c.diffs["diff"] == 0.0).all()
    assert c.rel_mean == 0.0 and c.rel_ci == (0.0, 0.0)


def test_better_variant_is_negative_with_ci_excluding_zero_and_deterministic():
    prob, world, wx = setup()
    ens = run_ensemble(prob, None, world, FakeEngine(), wx, list(range(5)), variants=plans())
    c1, c2 = ens.compare("wait_s", "better", "base"), ens.compare("wait_s", "better", "base")
    assert c1.ci == c2.ci and c1.n_boot == 2000                      # seeded bootstrap
    assert c1.ci[1] < 0 and c1.rel_ci[1] < 0 and -0.6 < c1.rel_mean < -0.3
    assert c1.ci[0] <= c1.mean <= c1.ci[1]


def test_deterministic_with_workers():
    prob, world, wx = setup(3, 60)
    serial = run_ensemble(prob, None, world, FakeEngine(), wx, [0, 1], variants=plans())
    par = run_ensemble(prob, None, world, FakeEngine(), wx, [0, 1], variants=plans(), workers=2)
    pd.testing.assert_frame_equal(serial.runs, par.runs)


def test_contract_violation_is_caught_and_reported():
    prob, world, wx = setup(3, 60)
    ps = plans(fast=Plan({"psv1": [1]}, 1.0, meta={"violate": True}))
    ens = run_ensemble(prob, None, world, FakeEngine(), wx, [4, 5], variants=ps)
    assert not ens.ok
    assert len(ens.failures) == 3 * 2
    f = ens.failures[0]
    assert f["variant"] == "fast" and f["seed"] in (4, 5) and f["kind"] == "contract"
    assert any("[speed]" in d for d in f["detail"])
    assert not ens.runs.loc[ens.runs.variant == "fast", "valid"].any()
    assert ens.runs.loc[ens.runs.variant != "fast", "valid"].all()
    assert ens.quantiles("wait_s").loc["fast", "n"] == 0              # invalid runs never feed statistics
    rep = ens.to_report()
    assert rep["ok"] is False and rep["failures"][0]["variant"] == "fast"
    # validate=False is allowed but is recorded
    off = run_ensemble(prob, None, world, FakeEngine(), wx, [4], variants=ps, validate=False)
    assert off.ok and off.to_report()["validated"] is False


def test_engine_error_is_a_failure_but_unsupported_propagates():
    prob, world, wx = setup(1, 30)

    class Boom(FakeEngine):
        def simulate(self, *a, **k):
            raise RuntimeError("kaput")

    ens = run_ensemble(prob, plans()["base"], world, Boom(), wx, [1])
    assert not ens.ok and ens.failures[0]["kind"] == "engine_error" and "kaput" in ens.failures[0]["detail"]

    class Nope(FakeEngine):
        def simulate(self, *a, **k):
            raise Unsupported("no cranes")

    with pytest.raises(Unsupported):
        run_ensemble(prob, plans()["base"], world, Nope(), wx, [1])


def test_report_is_json_safe_and_flags_synthetic_weather():
    prob, world, wx = setup(3, 60)
    ens = run_ensemble(prob, None, world, FakeEngine(), wx, [0, 1], variants=plans())
    ens.compare("wait_s", "better", "base")
    rep = ens.to_report()
    text = json.dumps(rep, allow_nan=False)                           # no NaN/inf, no numpy types
    back = json.loads(text)
    assert back["ok"] and back["synthetic_weather"] and back["weather_sources"] == [SYNTHETIC_SOURCE]
    assert back["quantiles"]["wait_s"]["base"]["p50"] >= 0
    assert back["comparisons"][0]["a"] == "better" and len(back["comparisons"][0]["ci95"]) == 2


def test_merge_requires_same_seeds_and_years():
    prob, world, wx = setup(2, 40)
    p = plans()
    a = run_ensemble(prob, None, world, FakeEngine(), wx, [0, 1], variants={"base": p["base"]})
    b = run_ensemble(prob, None, world, FakeEngine(), wx, [0, 1], variants={"better": p["better"]})
    m = Ensemble.merge(a, b)
    assert m.variants == ["base", "better"] and m.compare("wait_s", "better", "base").n == 4
    c = run_ensemble(prob, None, world, FakeEngine(), wx, [0, 2], variants={"x": p["twin"]})
    with pytest.raises(ValueError):
        Ensemble.merge(a, c)


# --- weather years ------------------------------------------------------------------------------------
def test_season_months():
    assert season_months("DJF") == [12, 1, 2] and season_months("jja") == [6, 7, 8]
    assert season_months(None) == list(range(1, 13)) and season_months([11, 12, 1]) == [11, 12, 1]
    with pytest.raises(ValueError):
        season_months("J")
    with pytest.raises(ValueError):
        season_months("XYZ")


def test_synthetic_years_is_deterministic_and_marked():
    a, b = synthetic_years(2, 200, seed=1), synthetic_years(2, 200, seed=1)
    assert all(w.source == "SYNTHETIC (test only)" for w in a)
    pd.testing.assert_frame_equal(a[0].df, b[0].df)
    assert not a[0].df["hs_m"].equals(a[1].df["hs_m"])
    assert list(a[0].df.columns) == ["t", "hs_m", "wind_mps", "tp_s"] and a[0].df["t"].iloc[1] == 3600.0
    assert a[0].df["hs_m"].between(0.1, 14).all()


def _write_nc(path, names, nlat=3, nlon=3):
    xr = pytest.importorskip("xarray")
    time = pd.date_range("2010-11-01", "2012-03-31 23:00", freq="h")
    lat, lon = np.linspace(59.0, 61.0, nlat), np.linspace(4.0, 6.0, nlon)
    LA, LO = np.meshgrid(lat, lon, indexing="ij")
    cell = (np.arange(nlat)[:, None] * 10 + np.arange(nlon)[None, :]).astype(float)   # reveals the grid cell
    hrs = np.arange(len(time), dtype=float)
    data = {n: (("time", "lat", "lon"), np.broadcast_to(f(cell, hrs), (len(time), nlat, nlon)).copy())
            for n, f in names.items()}
    xr.Dataset(data, coords={"time": time, "lat": lat, "lon": lon}).to_netcdf(path, engine="scipy")


def test_load_years_from_wave_and_wind_files(tmp_path):
    _write_nc(tmp_path / "wave.nc", {"hs": lambda c, h: c[None] + 1.0 + (h[:, None, None] % 24) / 100.0,
                                      "tp": lambda c, h: c[None] * 0 + 8.0})
    _write_nc(tmp_path / "wind.nc", {"u10": lambda c, h: c[None] * 0 + 3.0, "v10": lambda c, h: c[None] * 0 + 4.0})
    ws = load_years(tmp_path, point=(5.1, 60.1), years=[2010, 2011], season="DJF")   # nearest cell (row 1, col 1)
    assert [w.year for w in ws] == [2010, 2011]
    assert ws[0].source == "NORA3 DJF 2010/11"
    d = ws[0].df
    assert list(d.columns) == ["t", "hs_m", "wind_mps", "tp_s"]
    assert len(d) == (31 + 31 + 28) * 24                                  # 1 Dec 2010 .. 28 Feb 2011
    assert d["t"].iloc[0] == 0.0 and d["t"].iloc[-1] == (len(d) - 1) * 3600.0
    assert np.allclose(d["wind_mps"], 5.0) and np.allclose(d["tp_s"], 8.0)
    assert d["hs_m"].min() == pytest.approx(12.0, abs=1e-6)               # cell 11 + 1.0
    assert len(ws[1].df) == (31 + 31 + 29) * 24                           # Dec 2011 .. Feb 2012 (leap)
    with pytest.raises(ValueError):                                       # 2012 DJF has no December in the data
        load_years(tmp_path, (5.0, 60.0), [2012], "DJF")
    with pytest.raises(ValueError):                                       # too far from every grid cell
        load_years(tmp_path, (20.0, 70.0), [2010], "DJF")


def test_load_years_requires_wind_and_wave(tmp_path):
    _write_nc(tmp_path / "wave.nc", {"hs": lambda c, h: c[None] + 1.0 + 0 * h[:, None, None]})
    with pytest.raises(ValueError, match="wind_mps"):
        load_years(tmp_path / "wave.nc", (5.0, 60.0), [2011])


# --- experiment decision ------------------------------------------------------------------------------
YAML = """
gap_id: fake-01
base: scenario.yaml
hypothesis: "half the wait cuts wait by >= 20%"
variants:
  paper:  {solver: pyvrp, engine: fake}
  robust: {solver: pyvrp, engine: fake}
ensemble: {weather: {dataset: NORA3, years: [2000, 2005], season: DJF}, seeds: 5}
kpis: [wait_s, makespan_s]
decision: {kpi: wait_s, compare: [robust, paper], better: lower, min_effect: 0.2}
"""


def _build_factory(factor, violate=False):
    prob, world, _ = setup()

    def build(ex, name):
        meta = {"wait_factor": factor if name == "robust" else 1.0, "violate": violate and name == "robust"}
        return prob, Plan({"psv1": [1]}, 1.0, meta=meta), world, FakeEngine()
    return build


def test_run_experiment_supported_and_not_supported(tmp_path):
    p = tmp_path / "experiment.yaml"
    p.write_text(YAML)
    wx = lambda ex: synthetic_years(8, 120, seed=11)                      # noqa: E731
    r = run_experiment.run(p, build=_build_factory(0.5), load_weather=wx, out=tmp_path / "r.json")
    assert r["decision"]["status"] == "supported" and r["decision"]["effect"] > 0.3
    assert r["reportable"] is False                                       # synthetic weather is never reportable
    assert json.loads((tmp_path / "r.json").read_text())["gap_id"] == "fake-01"
    same = run_experiment.run(p, build=_build_factory(1.0), load_weather=wx)
    assert same["decision"]["status"] == "not supported" and same["decision"]["effect"] == 0.0
    weak = run_experiment.run(p, build=_build_factory(0.95), load_weather=wx)
    assert weak["decision"]["status"] == "not supported"                  # CI top (<5% effect) below 20%


def test_run_experiment_blocks_on_contract_failure_and_needs_builder(tmp_path):
    p = tmp_path / "experiment.yaml"
    p.write_text(YAML)
    r = run_experiment.run(p, build=_build_factory(0.5, violate=True),
                           load_weather=lambda ex: synthetic_years(2, 60, seed=1))
    assert r["decision"] is None and "failed" in r["blocked"] and r["reportable"] is False
    with pytest.raises(NotImplementedError):
        run_experiment.run(p, load_weather=lambda ex: [])


def test_oriented_effect():
    assert run_experiment.oriented_effect(-0.3, (-0.4, -0.2), "lower") == (0.3, (0.2, 0.4))
    assert run_experiment.oriented_effect(0.3, (0.2, 0.4), "higher") == (0.3, (0.2, 0.4))
