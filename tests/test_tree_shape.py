"""T3: declared tree shape of the ensemble (docs/DATA_TREES.md). The quiet failure: nothing raised, branches missing.

Seeded faults on a tiny fake engine (no real engine, no world): (a) a variant on other seeds, (b) a weather year with no
valid runs, (c) a comparison with one missing pair is refused and names the key, (d) a complete ensemble passes and its
compare output is byte-identical to the pre-T3 implementation."""
import json

import numpy as np
import pandas as pd
import pytest

from offsim.engines.base import Plan, Problem, SimResult, World
from offsim.montecarlo import Ensemble, run_ensemble
from offsim.montecarlo.ensemble import N_BOOT
from offsim.montecarlo.shape import TreeShape, TreeShapeError
from offsim.doctor.codes import classify, code_for_gate
from offsim.weather.years import synthetic_years

A, B = (5.0, 60.0), (5.5, 60.0)


class TinyEngine:
    name = "tiny"
    classes = {"CVRP"}
    needs_weather = True

    def simulate(self, problem, plan, world, weather=None, seed=0):
        rng = np.random.default_rng(seed)
        wait = float((weather.df["hs_m"].to_numpy()[:48] > 2.5).sum()) * 3600.0 * plan.meta.get("wait_factor", 1.0)
        wait += float(rng.uniform(0, 900.0))
        t1, t2 = 3600.0, 3600.0 + 5560.0
        t3 = t2 + wait
        rows = [("p", 0.0, *A, "load"), ("p", t1, *A, "sail"), ("p", t2, *B, "wait"), ("p", t3, *B, "unload"),
                ("p", t3 + 600.0, *B, "idle")]
        traj = pd.DataFrame(rows, columns=["agent_id", "t", "lon", "lat", "state"])
        agents = pd.DataFrame([{"agent_id": "p", "cls": "psv", "vmax_mps": 8.0, "capacity": 10.0, "domain": "sea"}])
        return SimResult(traj, agents, pd.DataFrame(), {"wait_s": wait}, self.name, seed, weather.source if weather else None)


def ensemble(seeds=(0, 1, 2), years=3):
    prob = Problem({"CVRP"}, [A, B], None, {1: 1.0}, [{"cls": "psv", "count": 1}])
    plans = {"base": Plan({"p": [1]}, 1.0, meta={"wait_factor": 1.0}),
             "better": Plan({"p": [1]}, 1.0, meta={"wait_factor": 0.5})}
    return run_ensemble(prob, None, World("open-sea"), TinyEngine(), synthetic_years(years, 48, seed=3), list(seeds), variants=plans)


def legacy_compare(ens, kpi, a, b, n_boot=N_BOOT, seed=0):
    """The pre-T3 body of Ensemble.compare, verbatim (no shape check): the reference for the byte-identity proof."""
    vr = ens.valid_runs
    cols = ["year", "wx", "seed", kpi]
    pa = vr.loc[vr["variant"] == a, cols].rename(columns={kpi: "a"})
    pb = vr.loc[vr["variant"] == b, cols].rename(columns={kpi: "b"})
    d = pa.merge(pb, on=["year", "wx", "seed"], how="inner").dropna(subset=["a", "b"])
    d = d.sort_values(["wx", "seed"]).reset_index(drop=True)
    d["diff"] = d["a"] - d["b"]
    diff, base = d["diff"].to_numpy(float), d["b"].to_numpy(float)
    n = len(d)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(n_boot, n))
    bm = diff[idx].mean(axis=1)
    den = base[idx].mean(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        br = np.where(den != 0, bm / den, np.nan)
    ci = (float(np.percentile(bm, 2.5)), float(np.percentile(bm, 97.5)))
    rci = (float(np.nanpercentile(br, 2.5)), float(np.nanpercentile(br, 97.5)))
    mb = float(base.mean())
    return {"n": n, "mean": float(diff.mean()), "ci": ci, "rel": float(diff.mean() / mb), "rci": rci,
            "diffs": d.to_dict("records")}


def new_compare(ens, kpi, a, b):
    c = ens.compare(kpi, a, b)
    return {"n": c.n, "mean": c.mean, "ci": c.ci, "rel": c.rel_mean, "rci": c.rel_ci, "diffs": c.diffs.to_dict("records")}


# -------------------------------------------------------------------------------------------- the pure shape
def test_treeshape_expected_observed_and_diff_name_the_paths():
    ts = TreeShape.expected(["a", "b"], [2000, 2001], [0, 1])
    assert ts.describe() == {"levels": ["variant", "year", "seed"], "sizes": {"variant": 2, "year": 2, "seed": 2},
                             "branches": 4, "items_per_branch": 2, "paths": 8}
    runs = pd.DataFrame([(v, y, s, True) for v in "ab" for y in (2000, 2001) for s in (0, 1)],
                        columns=["variant", "year", "seed", "valid"])
    assert ts.diff(ts.observed(runs)).ok
    extra = pd.DataFrame([{"variant": "b", "year": 2001, "seed": 9, "valid": True}])
    cut = pd.concat([runs.drop(index=[0, 5]), extra], ignore_index=True)
    d = ts.diff(ts.observed(cut))
    assert d.missing == (("a", 2000, 0), ("b", 2000, 1)) and d.extra == (("b", 2001, 9),) and not d.ok
    assert {(b, h, w) for b, h, w in d.short} == {(("a", 2000), 1, 2), (("b", 2000), 1, 2)}
    assert d.summary()["missing"] == ["{a; 2000; 0}", "{b; 2000; 1}"]


# -------------------------------------------------------------------------------------------- (d) complete passes
def test_complete_ensemble_passes_and_compare_is_byte_identical():
    ens = ensemble()
    assert ens.ok and ens.shape_ok and ens.shape().ok
    sh = ens.shape_report()
    assert sh["ok"] and sh["expected"]["paths"] == sh["observed_paths"] == 2 * 3 * 3 and sh["missing"] == []
    new, old = new_compare(ens, "wait_s", "better", "base"), legacy_compare(ens, "wait_s", "better", "base")
    assert new["n"] == 9
    assert json.dumps(new, sort_keys=True, default=float) == json.dumps(old, sort_keys=True, default=float)
    assert ens.to_report()["shape"]["ok"] is True


# -------------------------------------------------------------------------------------------- (a) other seeds
def test_variant_on_other_seeds_is_a_shape_error_and_compare_refuses():
    ens = ensemble()
    runs = ens.runs.copy()
    runs.loc[(runs["variant"] == "better") & (runs["seed"] == 2), "seed"] = 7        # `better` ran on [0, 1, 7]
    bad = Ensemble(runs, [], ens.meta)
    assert bad.ok and not bad.shape_ok                                                # nothing failed: the quiet case
    d = bad.shape()
    assert ("better", 0, 2) in d.missing and ("better", 0, 7) in d.extra
    with pytest.raises(TreeShapeError, match=r"\{0; 2\}"):
        bad.compare("wait_s", "better", "base")


# -------------------------------------------------------------------------------------------- (b) empty year
def test_weather_year_with_no_valid_runs_is_a_missing_branch():
    ens = ensemble()
    y = ens.meta["years"][1]
    runs = ens.runs.copy()
    runs.loc[runs["year"] == y, "valid"] = False                                      # silent: no failure was recorded
    bad = Ensemble(runs, [], ens.meta)
    d = bad.shape()
    assert not d.ok and len(d.missing) == 2 * 3 and {p[1] for p in d.missing} == {y}
    assert {b for b, h, w in d.short} == {(v, y) for v in ("base", "better")}
    s = bad.shape_report()
    assert s["n_missing"] == 6 and len(s["missing"]) == 5                             # compact: up to 5 example paths
    with pytest.raises(TreeShapeError, match=f"missing 3"):
        bad.compare("wait_s", "better", "base")


# -------------------------------------------------------------------------------------------- (c) one pair missing
def test_compare_with_one_missing_pair_is_refused_and_names_the_key():
    ens = ensemble()
    y = ens.meta["years"][2]
    runs = ens.runs[~((ens.runs["variant"] == "base") & (ens.runs["year"] == y) & (ens.runs["seed"] == 1))]
    short = Ensemble(runs.reset_index(drop=True), [], ens.meta)
    with pytest.raises(TreeShapeError) as e:
        short.compare("wait_s", "better", "base")
    msg = str(e.value)
    assert f"{{{y}; 1}}" in msg and "8 of 9" in msg and "missing 1" in msg
    assert short.compare is not None and not short.shape_ok
    assert not short._comparisons                                                      # nothing was recorded


# -------------------------------------------------------------------------------------------- gate 3e code
def test_doctor_code_for_a_shape_mismatch_and_precedence_of_run_failures():
    d = {"shape": {"ok": False}, "failures": []}
    assert code_for_gate("3e_ensemble", d) == "ENS-SHAPE"
    assert code_for_gate("3e_ensemble", {**d, "failures": [{"kind": "contract"}]}) == "G3E-ENSEMBLE"     # the loud case first
    assert code_for_gate("3e_ensemble", {"shape": {"ok": True}}) == "G3E-ENSEMBLE"
    assert classify({"gates": {"3e_ensemble": {"pass": False, "detail": d}}, "status": "stopped at gate 3e_ensemble"}) == "ENS-SHAPE"


def test_pipeline_gate_3e_fails_with_ens_shape_on_a_silently_empty_year(tmp_path, monkeypatch):
    import offsim.montecarlo.ensemble as em
    from offsim.pipeline import run
    from test_pipeline_registry import demo
    real = em._execute

    def quiet(ctx, task):
        out = real(ctx, task)
        if "row" in out and task[1] == 1:               # year index 1 yields no valid run, and no failure is recorded
            out["row"]["valid"] = False
        return out

    monkeypatch.setattr(em, "_execute", quiet)
    rep = run(demo(tmp_path, ensemble={"seeds": 2, "weather": {"synthetic": {"n": 2, "hours": 24}}}), tmp_path / "q", seconds=1)
    g = rep["gates"]["3e_ensemble"]
    assert rep["status"] == "stopped at gate 3e_ensemble" and rep["ensemble"]["ok"] is True and rep["reportable"] is False
    assert g["code"] == rep["code"] == "ENS-SHAPE" and not g["pass"]
    sh = g["detail"]["shape"]
    assert sh["ok"] is False and sh["n_missing"] == 2 and sh["expected"]["paths"] == 4 and sh["observed_paths"] == 2
    assert len(sh["missing"]) <= 5 and sh["missing"][0].startswith("{base; ")


def test_pipeline_gate_3e_passes_a_complete_tree(tmp_path):
    from offsim.pipeline import run
    from test_pipeline_registry import demo
    rep = run(demo(tmp_path, ensemble={"seeds": 2, "weather": {"synthetic": {"n": 2, "hours": 24}}}), tmp_path / "c", seconds=1)
    g = rep["gates"]["3e_ensemble"]
    assert g["pass"] and g["detail"]["shape"]["ok"] and g["detail"]["shape"]["observed_paths"] == 4
