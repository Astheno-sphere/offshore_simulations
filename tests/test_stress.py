"""Stress-test pair (offsim/research/stress.py): the (year, seed) where two compared variants diverge most.

Fake engine, no real solver. The `robust` variant deflects its mid-route waypoint north by (dy_per_hs x that winter's mean
Hs) degrees, `paper` sails straight, so the expected worst winter and the exact metres are known without the code under
test: haversine between two points on one meridian is EARTH_R x delta-latitude."""
import copy
import itertools
import json
import math

import numpy as np
import pandas as pd
import pytest

from offsim.cinema.vessel import display_offset_check
from offsim.contract import EARTH_R
from offsim.engines.base import Plan, Problem, SimResult, World
from offsim.motion.story import resolve
from offsim.research import run_experiment, stress
from offsim.weather.years import synthetic_years

A, B = (5.0, 60.0), (5.5, 60.0)
DY_PER_HS = 0.004                      # degrees of latitude per metre of mean Hs
T_MID = 3600.0 + 2780.0                # the deflected waypoint is reached at this time whatever the seed


class DeflectEngine:
    name = "fake"
    classes = {"CVRP"}
    needs_weather = True

    def simulate(self, problem, plan, world, weather=None, seed=0):
        rng = np.random.default_rng(seed)
        hs = weather.df["hs_m"].to_numpy()[:100]
        dy = plan.meta.get("dy_per_hs", 0.0) * float(hs.mean())
        wait = float((hs > 2.5).sum()) * 3600.0 * plan.meta.get("wait_factor", 1.0) + float(rng.uniform(0, 900.0))
        t1, tm, t2 = 3600.0, T_MID, 3600.0 + 5560.0
        t3 = t2 + wait
        rows = [("psv1", 0.0, *A, "load"), ("psv1", t1, *A, "sail"), ("psv1", tm, 5.25, 60.0 + dy, "sail"),
                ("psv1", t2, *B, "wait"), ("psv1", t3, *B, "unload"), ("psv1", t3 + 1800.0, *B, "idle")]
        traj = pd.DataFrame(rows, columns=["agent_id", "t", "lon", "lat", "state"])
        agents = pd.DataFrame([{"agent_id": "psv1", "cls": plan.meta.get("cls", "psv"), "vmax_mps": 8.0,
                                "capacity": 10.0, "domain": "sea"}])
        k = {"wait_s": wait, "makespan_s": t3 + 1800.0}
        k.update(self.extra_kpis())
        return SimResult(traj, agents, pd.DataFrame(), k, self.name, seed, weather.source if weather else None)

    def extra_kpis(self):
        return {}


class JitterEngine(DeflectEngine):
    """Not deterministic: a KPI changes on every call, so a re-run can never reproduce its ensemble row."""
    _n = itertools.count()

    def extra_kpis(self):
        return {"jitter": float(next(self._n))}


YAML = """
gap_id: fake-stress-01
base: scenario.yaml
hypothesis: "half the wait cuts wait by >= 20%"
variants:
  paper:  {solver: pyvrp, engine: fake}
  robust: {solver: pyvrp, engine: fake}
ensemble: {weather: {dataset: NORA3, years: [2000, 2005], season: DJF}, seeds: 3}
kpis: [wait_s, makespan_s]
decision: {kpi: wait_s, compare: [robust, paper], better: lower, min_effect: 0.2}
"""
N_YEARS, N_SEEDS = 6, 3


def _wx(ex=None):
    return synthetic_years(N_YEARS, 120, seed=11)


def _build(engine_cls=DeflectEngine, robust_meta=None):
    prob = Problem({"CVRP"}, [A, B], None, {1: 1.0}, [{"cls": "psv", "count": 1}])
    world = World("open-sea")

    def build(ex, name):
        meta = {"wait_factor": 0.5, "dy_per_hs": DY_PER_HS, **(robust_meta or {})} if name == "robust" else {"wait_factor": 1.0}
        return prob, Plan({"psv1": [1]}, 1.0, meta=meta), world, engine_cls()
    return build


def _exp(tmp_path, stress_line="stress: {metric: max_divergence}\n"):
    p = tmp_path / "experiment.yaml"
    p.write_text(YAML + stress_line)
    return p


def _traj(rows):
    return pd.DataFrame(rows, columns=["agent_id", "t", "lon", "lat", "state"])


def _agents(cls="psv"):
    return pd.DataFrame([{"agent_id": "psv1", "cls": cls, "vmax_mps": 8.0, "capacity": 10.0, "domain": "sea"}])


# --- the metric ---------------------------------------------------------------------------------------
def test_divergence_known_offset_and_argmax_time():
    a = _traj([("psv1", 0.0, 5.0, 60.0, "sail"), ("psv1", 1000.0, 5.1, 60.0, "sail")])
    b = _traj([("psv1", 0.0, 5.0, 60.0, "sail"), ("psv1", 500.0, 5.05, 60.02, "sail"), ("psv1", 1000.0, 5.1, 60.0, "sail")])
    d = stress.divergence(a, _agents(), b, _agents())
    # on the union grid {0, 500, 1000}: at t=500 a is at (5.05, 60.0), b at (5.05, 60.02): same meridian, 0.02 deg of latitude
    assert d["max_divergence_m"] == pytest.approx(EARTH_R * math.radians(0.02), rel=1e-9)
    assert d["t_star_s"] == 500.0 and d["agent_id"] == "psv1"
    assert d["pos_a"] == pytest.approx([5.05, 60.0]) and d["pos_b"] == pytest.approx([5.05, 60.02])
    assert d["coverage"] == {"matched_agents": 1, "unmatched_agents": [], "time_overlap_min": 1.0}


def test_divergence_refuses_when_the_fleets_differ():
    t = _traj([("psv1", 0.0, 5.0, 60.0, "sail"), ("psv1", 10.0, 5.0, 60.0, "sail")])
    with pytest.raises(ValueError, match="agents tables differ"):
        stress.divergence(t, _agents("psv"), t, _agents("crew_boat"))
    other = _agents().assign(agent_id="psv2")
    with pytest.raises(ValueError, match="agents tables differ"):
        stress.divergence(t, _agents(), t, other)


def test_divergence_agrees_with_display_offset_check_on_the_same_inputs():
    a = _traj([("psv1", 0.0, 5.0, 60.0, "sail"), ("psv1", 700.0, 5.3, 60.01, "sail"), ("psv1", 1000.0, 5.5, 60.0, "sail")])
    b = _traj([("psv1", 0.0, 5.0, 60.0, "sail"), ("psv1", 300.0, 5.1, 60.03, "sail"), ("psv1", 1000.0, 5.5, 60.0, "sail")])
    assert stress.divergence(a, _agents(), b, _agents())["max_divergence_m"] == pytest.approx(display_offset_check(a, b), rel=1e-12)


def test_divergence_reports_a_partial_time_overlap():
    a = _traj([("psv1", 0.0, 5.0, 60.0, "sail"), ("psv1", 1000.0, 5.1, 60.0, "sail")])
    b = _traj([("psv1", 500.0, 5.0, 60.0, "sail"), ("psv1", 1500.0, 5.1, 60.0, "sail")])
    d = stress.divergence(a, _agents(), b, _agents())
    assert d["coverage"]["time_overlap_min"] == pytest.approx(500.0 / 1500.0)


# --- the runner ---------------------------------------------------------------------------------------
def _expected_worst_year():
    wx = _wx()
    means = [float(w.df["hs_m"].to_numpy()[:100].mean()) for w in wx]
    i = int(np.argmax(means))
    return i, EARTH_R * math.radians(DY_PER_HS * means[i]), means


def test_run_persists_the_worst_pair_beside_the_statistical_effect(tmp_path):
    r = run_experiment.run(_exp(tmp_path), build=_build(), load_weather=_wx, out=tmp_path / "r.json")
    st = r["decision"]["pair"]["stress"]
    i, metres, means = _expected_worst_year()
    assert st["wx"] == i and st["seed"] == 0                     # ties across seeds go to the first (wx, seed)
    assert st["max_divergence_m"] == pytest.approx(metres, rel=1e-9) and st["t_star_s"] == T_MID
    assert st["compare"] == ["robust", "paper"] and st["agent_id"] == "psv1"
    assert st["selection"] == "max_divergence" and "not the decision KPI" in st["selected_on"]
    d = st["distribution"]
    assert d["n_pairs"] == N_YEARS * N_SEEDS and d["n_skipped"] == 0 and d["n_excluded_invalid"] == 0
    assert d["max"] == st["max_divergence_m"] and d["p50"] <= d["p90"] <= d["max"]
    assert d["p50"] < d["max"]                                  # the extreme is not typical, and the frame can say so
    assert "assumption" not in st                               # a measured value is not an unsourced parameter
    assert r["decision"]["effect"] > 0 and r["decision"]["ci95"]  # the statistical result is still there, with its interval
    assert resolve("report:decision.pair.stress.max_divergence_m", r) == st["max_divergence_m"]
    assert resolve("report:decision.effect", r) == r["decision"]["effect"]


def test_sidecars_sit_beside_out_and_match_the_hash(tmp_path):
    import hashlib
    r = run_experiment.run(_exp(tmp_path), build=_build(), load_weather=_wx, out=tmp_path / "r.json")
    st = r["decision"]["pair"]["stress"]
    assert sorted(st["sidecars"]) == ["r.stress.paper.csv", "r.stress.robust.csv"]
    for v in ("paper", "robust"):
        assert hashlib.sha256((tmp_path / f"r.stress.{v}.csv").read_bytes()).hexdigest() == st["traj_sha256"][v]
    on_disk = json.loads((tmp_path / "r.json").read_text())
    assert on_disk["decision"]["pair"]["stress"]["max_divergence_m"] == st["max_divergence_m"]


def test_no_stress_key_leaves_the_result_exactly_as_it_was(tmp_path):
    plain = run_experiment.run(_exp(tmp_path, ""), build=_build(), load_weather=_wx)
    with_stress = run_experiment.run(_exp(tmp_path), build=_build(), load_weather=_wx)
    assert "pair" not in plain["decision"] and "stress_blocked" not in plain
    trimmed = copy.deepcopy(with_stress)
    del trimmed["decision"]["pair"]
    assert json.dumps(trimmed, sort_keys=True, default=str) == json.dumps(plain, sort_keys=True, default=str)


def test_unknown_metric_fails_before_any_compute(tmp_path):
    def build(ex, name):
        raise AssertionError("build must not be called")
    with pytest.raises(ValueError, match="stress must be"):
        run_experiment.run(_exp(tmp_path, "stress: {metric: worst_kpi}\n"), build=build, load_weather=_wx)


def test_a_non_deterministic_engine_is_refused_not_persisted(tmp_path):
    r = run_experiment.run(_exp(tmp_path), build=_build(JitterEngine), load_weather=_wx)
    assert r["decision"] is not None and "pair" not in r["decision"]
    assert "not deterministic" in r["stress_blocked"]


def test_different_fleets_are_skipped_and_counted_then_blocked(tmp_path):
    r = run_experiment.run(_exp(tmp_path), build=_build(robust_meta={"cls": "crew_boat"}), load_weather=_wx)
    assert "pair" not in r["decision"] and "no scorable pair" in r["stress_blocked"]
    assert f"{N_YEARS * N_SEEDS} skipped" in r["stress_blocked"] and "agents tables differ" in r["stress_blocked"]


def test_pairs_invalid_in_the_ensemble_are_excluded_and_counted(tmp_path):
    from offsim.montecarlo import run_ensemble
    import offsim.research.experiment as exp_mod
    ex = exp_mod.load(_exp(tmp_path))
    build = _build()
    parts = []
    for v in ("paper", "robust"):
        prob, plan, world, eng = build(ex, v)
        parts.append(run_ensemble(prob, None, world, eng, _wx(), [0, 1, 2], variants={v: plan}))
    from offsim.montecarlo import Ensemble
    ens = Ensemble.merge(*parts)
    hit = ens.runs.index[(ens.runs["variant"] == "robust") & (ens.runs["wx"] == 0) & (ens.runs["seed"] == 1)][0]
    ens.runs.loc[hit, "valid"] = False
    block, trajs, why = stress.find_stress(ex, {v: build(ex, v) for v in ("paper", "robust")}, _wx(), ens)
    assert why is None and block["distribution"]["n_pairs"] == N_YEARS * N_SEEDS - 1
    assert block["distribution"]["n_excluded_invalid"] == 1
    assert set(trajs) == {"paper", "robust"}


def test_the_stress_pass_reuses_the_ensembles_plan_and_never_rebuilds(tmp_path):
    """offsim.pipeline.build_variant calls a time-limited solver, so a second build can return a different plan. Here the
    second build of `robust` would deflect twice as far; the persisted pair must still be the plan the ensemble ran."""
    calls = {}
    inner = _build()

    def build(ex, name):
        calls[name] = calls.get(name, 0) + 1
        prob, plan, world, eng = inner(ex, name)
        if name == "robust" and calls[name] > 1:
            plan = Plan(plan.routes, plan.objective, meta={**plan.meta, "dy_per_hs": 2 * DY_PER_HS})
        return prob, plan, world, eng

    r = run_experiment.run(_exp(tmp_path), build=build, load_weather=_wx)
    assert calls == {"paper": 1, "robust": 1}                       # built once each, by run(), and reused
    assert "stress_blocked" not in r
    assert r["decision"]["pair"]["stress"]["max_divergence_m"] == pytest.approx(_expected_worst_year()[1], rel=1e-9)
