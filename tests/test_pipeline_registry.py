"""offsim run through the solver/engine registry: solver/engine keys, certify (1b), ensemble (3e), gtfs + entur (4c),
wombat self-dispatch, build_variant + run_experiment. All weather here is SYNTHETIC (test only); no network."""
import copy
import json

import numpy as np
import pandas as pd
import pytest
import yaml

from conftest import ROOT
from offsim import pipeline
from offsim.engines import Plan
from offsim.pipeline import build_problem, build_variant, run
from offsim.research import experiment as exp_mod, run_experiment
from offsim.transit import gtfs
from offsim.weather.years import synthetic_years

DEMO = ROOT / "offsim/papers/demo-oslofjord-supply/scenario.yaml"
WOMBAT_T = ROOT / "offsim/papers/_templates/wind_om/scenario.yaml"
GTFS_FIX = ROOT / "tests/fixtures/gtfs_mini"
DEMO_KEYS = {"paper", "gates", "status", "provenance", "assumptions", "quay_snap_m", "kpis", "measured", "plan", "events"}


def demo(tmp_path, name="scenario.yaml", **edit):
    sc = yaml.safe_load(DEMO.read_text())
    sc["world"] = "none"                       # CI has no fetched world: straight legs, no land check
    sc.update(edit)
    p = tmp_path / name
    p.write_text(yaml.safe_dump(sc))
    return p


def write(tmp_path, sc, name="s.yaml"):
    p = tmp_path / name
    p.write_text(yaml.safe_dump(sc))
    return p


# ------------------------------------------------------------------------------------------- sea demo unchanged
def test_sea_demo_report_keeps_its_keys_and_defaults(tmp_path):
    rep = run(demo(tmp_path), tmp_path / "o", seconds=1)
    assert set(rep) == DEMO_KEYS
    assert list(rep["gates"]) == ["0_provenance", "1_plan", "2_replay_equals_plan", "3_contract", "4_paper"]
    assert rep["gates"]["0_provenance"] == {"pass": True, "detail": {"unsourced": [], "unsupported_classes": []}}
    assert set(rep["gates"]["1_plan"]["detail"]) == {"routes", "loads", "capacity", "objective_m"}
    assert rep["status"] == "not comparable (no reported KPIs)"
    assert set(rep["measured"]) == {"distance_km", "makespan_s", "wait_s", "vehicles_used"}
    prov = rep["provenance"]
    assert prov["solver"] == "pyvrp" and prov["engine"] == "replay" and prov["graph"] == "none"
    assert prov["packages"]["pyvrp"] and prov["packages"]["simpy"]
    # replay distance equals the PyVRP objective, as gate 2 demands
    assert rep["kpis"]["distance_km"] == pytest.approx(rep["plan"]["objective_m"] / 1000, rel=0.01)


def test_unsupported_class_and_unavailable_tool_stop_at_gate_0(tmp_path):
    rep = run(demo(tmp_path, problem={**yaml.safe_load(DEMO.read_text())["problem"], "class": ["PDP"]}), tmp_path / "a", seconds=1)
    d = rep["gates"]["0_provenance"]["detail"]
    assert rep["status"] == "stopped at gate 0_provenance" and d["unsupported_classes"] == ["PDP"]
    rep = run(demo(tmp_path, name="b.yaml", engine="nope"), tmp_path / "b", seconds=1)
    d = rep["gates"]["0_provenance"]["detail"]
    assert rep["status"] == "stopped at gate 0_provenance" and "unknown engine" in d["unavailable"]["engine:nope"]
    # a class some tool supports, but not the chosen one: the mismatch is named
    rep = run(demo(tmp_path, name="c.yaml", engine="gtfs"), tmp_path / "c", seconds=1)
    d = rep["gates"]["0_provenance"]["detail"]
    assert d["unsupported_classes"] == [] and "engine gtfs" in d["tool_mismatch"][0]


def test_openclsim_engine_reaches_the_same_status_and_distance(tmp_path):
    base = run(demo(tmp_path), tmp_path / "r", seconds=1)
    rep = run(demo(tmp_path, name="o.yaml", engine="openclsim"), tmp_path / "o", seconds=1)
    assert rep["status"] == base["status"]
    assert all(g["pass"] for k, g in rep["gates"].items() if k != "4_paper")
    assert rep["provenance"]["engine"] == "openclsim" and rep["provenance"]["packages"]["openclsim"]
    assert rep["kpis"]["distance_km"] == pytest.approx(base["kpis"]["distance_km"], rel=0.01)
    assert rep["tools"]["engine"] == "openclsim"


# ------------------------------------------------------------------------------------------- gate 1b
def test_certify_gate_passes_against_the_exact_optimum(tmp_path):
    cert = {"max_clients": 12, "gap_tol": {"value": 0.02, "assumption": True}}
    rep = run(demo(tmp_path, certify=cert), tmp_path / "c", seconds=1)
    g = rep["gates"]["1b_exact"]
    assert g["pass"] is True and g["detail"]["solver"] == "pyomo" and g["detail"]["exact_status"] == "optimal"
    assert g["detail"]["gap"] <= 0.02 and rep["provenance"]["packages"]["pyomo"]
    assert list(rep["gates"]).index("1b_exact") == list(rep["gates"]).index("1_plan") + 1


def test_certify_gate_fails_on_gap_and_skips_big_instances(tmp_path):
    neg = {"max_clients": 12, "gap_tol": {"value": -0.5, "assumption": True}}
    rep = run(demo(tmp_path, certify=neg), tmp_path / "n", seconds=1)
    assert rep["status"] == "stopped at gate 1b_exact" and rep["gates"]["1b_exact"]["detail"]["gap"] > -0.5
    assert "2_replay_equals_plan" not in rep["gates"]
    skip = run(demo(tmp_path, name="k.yaml", certify={"max_clients": 3, "gap_tol": {"value": 0.02, "assumption": True}}),
               tmp_path / "k", seconds=1)
    d = skip["gates"]["1b_exact"]
    assert d["pass"] is True and "6 clients > max_clients 3" in d["detail"]["skipped"]


def test_certify_gate_fails_for_a_bad_heuristic_plan(tmp_path, monkeypatch):
    from offsim.solve.pyvrp_solver import PyVRPSolver
    real = PyVRPSolver.solve

    def worse(self, problem, seconds=2.0, seed=1):          # a heuristic that reports a 50% longer plan than the optimum
        pl = real(self, problem, seconds, seed)
        return Plan(pl.routes, pl.objective * 1.5, pl.objective_unit, pl.solver)

    monkeypatch.setattr(PyVRPSolver, "solve", worse)
    cert = {"max_clients": 12, "gap_tol": {"value": 0.02, "assumption": True}}
    rep = run(demo(tmp_path, certify=cert), tmp_path / "bad", seconds=1)
    assert rep["status"] == "stopped at gate 1b_exact"
    assert rep["gates"]["1b_exact"]["detail"]["gap"] == pytest.approx(0.5, abs=0.02)


def test_certify_with_unsourced_tolerance_stops_at_gate_0(tmp_path):
    rep = run(demo(tmp_path, certify={"gap_tol": {"value": 0.02}}), tmp_path / "u", seconds=1)
    assert "certify.gap_tol" in rep["gates"]["0_provenance"]["detail"]["unsourced"]


# ------------------------------------------------------------------------------------------- ensemble (3e)
def test_ensemble_with_synthetic_weather_is_not_reportable(tmp_path):
    ens = {"seeds": 2, "weather": {"synthetic": {"n": 2, "hours": 48}}}
    rep = run(demo(tmp_path, ensemble=ens), tmp_path / "e", seconds=1)
    assert rep["ensemble"]["ok"] and rep["ensemble"]["n_runs"] == 4 and rep["ensemble"]["synthetic_weather"]
    assert rep["gates"]["3e_ensemble"]["pass"] is True
    assert rep["reportable"] is False and rep["status"].endswith("(synthetic weather, not reportable)")
    assert rep["status"].startswith("not comparable")
    assert "distance_km" in rep["ensemble"]["quantiles"]
    gates = list(rep["gates"])
    assert gates.index("3_contract") < gates.index("3e_ensemble") < gates.index("4_paper")


def test_failed_ensemble_stops_at_3e(tmp_path, monkeypatch):
    import offsim.montecarlo.ensemble as em
    real = em._execute

    def bad(ctx, task):
        out = real(ctx, task)
        if "row" in out:
            out["row"]["valid"] = False
            out["failure"] = {"variant": task[0], "year": None, "seed": task[2], "kind": "contract", "detail": ["forced"]}
        return out

    monkeypatch.setattr(em, "_execute", bad)
    rep = run(demo(tmp_path, ensemble={"seeds": 1, "weather": {"synthetic": {"n": 1, "hours": 24}}}), tmp_path / "f", seconds=1)
    assert rep["status"] == "stopped at gate 3e_ensemble" and rep["ensemble"]["ok"] is False
    assert not (tmp_path / "f/trajectory.csv").exists()


def test_missing_metocean_stops_at_gate_0_with_the_fetch_hint(tmp_path):
    ens = {"seeds": 1, "weather": {"dir": "data/worlds/x/metocean", "point": [10.6, 59.3], "years": [2011, 2012], "season": "DJF"}}
    rep = run(demo(tmp_path, ensemble=ens), tmp_path / "m", seconds=1, data_root=tmp_path / "data")
    d = rep["gates"]["0_provenance"]["detail"]
    assert rep["status"] == "stopped at gate 0_provenance"
    assert d["missing_metocean"].endswith("data/worlds/x/metocean") and "fetch_world" in d["fix"] and "--metocean" in d["fix"]


# ------------------------------------------------------------------------------------------- wombat (self-dispatching)
def wombat_scenario(tmp_path):
    sc = yaml.safe_load(WOMBAT_T.read_text())
    sc["paper"]["id"] = "t-wind-om"
    sc["world"] = "none"
    sc["sim"]["wombat"]["horizon_days"] = {"value": 45, "assumption": True, "why": "test"}
    sc["sim"]["wombat"]["failure_rate_factor"] = {"value": 4.0, "assumption": True, "why": "test: make failures happen in 45 days"}
    sc["weather"] = {"synthetic": {"n": 1, "hours": 24 * 45}}
    return write(tmp_path, sc, "wom.yaml")


def test_wind_om_template_runs_through_wombat_with_self_dispatch_gate_2(tmp_path):
    pytest.importorskip("wombat")
    rep = run(wombat_scenario(tmp_path), tmp_path / "w", seconds=1)
    assert rep["provenance"]["solver"] == "none" and rep["provenance"]["engine"] == "wombat"
    assert rep["provenance"]["packages"]["wombat"]
    g = rep["gates"]
    assert g["1_plan"]["pass"] and "no routes" in g["1_plan"]["detail"]
    assert g["2_replay_equals_plan"] == {"pass": True, "detail": "engine dispatches itself (no plan to compare)"}
    assert g["3_contract"]["pass"] and g["0_provenance"]["pass"]
    assert 0.0 < rep["measured"]["availability"] <= 1.0 and "om_cost_usd" in rep["measured"]
    assert rep["reportable"] is False and rep["status"].endswith("(synthetic weather, not reportable)")
    assert (tmp_path / "w/trajectory.csv").exists()


def test_wombat_without_weather_stops_at_gate_0(tmp_path):
    pytest.importorskip("wombat")
    sc = yaml.safe_load(wombat_scenario(tmp_path).read_text())
    sc.pop("weather")
    rep = run(write(tmp_path, sc, "nw.yaml"), tmp_path / "nw", seconds=1)
    assert rep["status"] == "stopped at gate 0_provenance" and "needs weather" in rep["gates"]["0_provenance"]["detail"]["missing_weather"]


def test_build_problem_unwraps_template_blocks():
    sc = yaml.safe_load(WOMBAT_T.read_text())
    prob, world, meta = build_problem(sc)
    w = prob.extra["wombat"]
    assert prob.cls == {"WIND-OM"} and w["layout"][0]["lon"] == 2.27 and w["vessels"][0]["file"] == "ctv.yaml"
    assert w["substation"] is None and meta["graph"] == "none" and world.land is None
    assert pipeline.select_tools(sc) == ("none", "wombat")


# ------------------------------------------------------------------------------------------- gtfs + gate 4c
T0_UTC = pd.Timestamp("2026-03-03T06:00:00Z")          # 07:00 Europe/Oslo (CET) on the service day = trajectory t = 0


def gtfs_world(tmp_path, delay_s=0.0, with_vehicles=True):
    data = tmp_path / "data"
    clip = tmp_path / "gtfs_clip"
    if not clip.exists():
        gtfs.clip(GTFS_FIX, (7.0, 62.6, 7.5, 62.9), clip)
    wd = data / "worlds" / "mini"
    (wd / "entur").mkdir(parents=True, exist_ok=True)
    if with_vehicles:
        stops = {"A": (7.10, 62.73), "B": (7.15, 62.735), "C": (7.20, 62.74)}
        sched = {"T1": [("A", 8 * 60), ("B", 8 * 60 + 5), ("B", 8 * 60 + 6), ("C", 8 * 60 + 11)],
                 "T3": [("A", 9 * 60), ("B", 9 * 60 + 6), ("C", 9 * 60 + 12)]}
        rows = []
        for sj, pts in sched.items():
            for (a, ta), (b, tb) in zip(pts, pts[1:]):
                for f in (0.0, 0.5):
                    lon = stops[a][0] + f * (stops[b][0] - stops[a][0])
                    lat = stops[a][1] + f * (stops[b][1] - stops[a][1])
                    t = (ta + f * (tb - ta)) * 60 + delay_s
                    rows.append({"vehicle_id": f"V-{sj}", "line_ref": "L1", "service_journey_id": sj,
                                 "t_utc": T0_UTC + pd.Timedelta(seconds=t - 7 * 3600), "lon": lon, "lat": lat,
                                 "delay_s": delay_s, "bearing": 90.0, "speed_mps": 8.0})
            lon, lat = stops[pts[-1][0]]
            rows.append({"vehicle_id": f"V-{sj}", "line_ref": "L1", "service_journey_id": sj,
                         "t_utc": T0_UTC + pd.Timedelta(seconds=pts[-1][1] * 60 + delay_s - 7 * 3600), "lon": lon, "lat": lat,
                         "delay_s": delay_s, "bearing": 90.0, "speed_mps": 8.0})
        pd.DataFrame(rows).to_csv(wd / "entur" / "vehicles.csv", index=False)
    return data, clip


def gtfs_scenario(tmp_path, clip, **edit):
    a = lambda x, why="test": {"value": x, "assumption": True, "why": why}
    sc = {"paper": {"id": "t-gtfs", "title": "t", "authors": [], "year": 2026, "doi": "", "licence": "MIT"},
          "problem": {"class": ["TRANSIT-REPLAY"], "objective": "timetable", "constraints": []},
          "world": "mini", "solver": "none", "engine": "gtfs",
          "sim": {"gtfs": {"dir": a(str(clip)), "date": a("2026-03-03"), "t0": a("07:00:00"), "t1": a("11:00:00"),
                           "sample_s": a(60)}},
          "validate": {"entur": True}, "reported": {}}
    sc.update(edit)
    return write(tmp_path, sc, "gtfs.yaml")


def test_gtfs_scenario_reaches_gate_4c(tmp_path):
    data, clip = gtfs_world(tmp_path)
    rep = run(gtfs_scenario(tmp_path, clip), tmp_path / "g", seconds=1, data_root=data)
    g = rep["gates"]
    assert rep["provenance"]["engine"] == "gtfs" and g["2_replay_equals_plan"]["detail"].startswith("engine dispatches itself")
    assert g["3_contract"]["pass"] and g["4b_ais"] == {"pass": True, "detail": "not requested"}
    assert g["4c_entur"]["pass"] is True and g["4c_entur"]["detail"]["n_judged"] == 2
    assert g["4c_entur"]["detail"]["median_abs_delay_s"] < 60 and rep["measured"]["trips"] == 3
    assert not rep["status"].startswith("stopped") and (tmp_path / "g/trajectory.csv").exists()


def test_gate_4c_fails_for_late_vehicles_and_missing_file_stops_at_gate_0(tmp_path):
    data, clip = gtfs_world(tmp_path, delay_s=900.0)
    rep = run(gtfs_scenario(tmp_path, clip), tmp_path / "late", seconds=1, data_root=data)
    assert rep["status"] == "stopped at gate 4c_entur" and "delay" in rep["gates"]["4c_entur"]["detail"]["reason"]
    assert rep["paper_status"].startswith("not comparable")
    data2, clip2 = gtfs_world(tmp_path / "x", with_vehicles=False)
    rep = run(gtfs_scenario(tmp_path / "x", clip2), tmp_path / "nofile", seconds=1, data_root=data2)
    d = rep["gates"]["0_provenance"]["detail"]
    assert rep["status"] == "stopped at gate 0_provenance" and d["missing_entur_vehicles"].endswith("entur/vehicles.csv")
    assert "entur-realtime" in d["fix"]


# ------------------------------------------------------------------------------------------- experiments
def write_experiment(tmp_path):
    sc = yaml.safe_load(DEMO.read_text())
    sc["world"] = "none"
    write(tmp_path, sc, "scenario.yaml")
    ex = {"gap_id": "t-gap", "base": "scenario.yaml", "hypothesis": "faster vessels cut the makespan by >= 5%",
          "variants": {"paper": {"solver": "pyvrp", "engine": "replay"},
                       "fast": {"solver": "pyvrp", "engine": "openclsim",
                                "overrides": {"fleet.0.speed_mps": {"value": 8.0, "assumption": True, "why": "test"}}}},
          "ensemble": {"weather": {"years": [2000, 2001]}, "seeds": 2, "solve_seconds": 1},
          "kpis": ["makespan_s", "distance_km"],
          "decision": {"kpi": "makespan_s", "compare": ["fast", "paper"], "better": "lower", "min_effect": 0.05}}
    p = tmp_path / "experiment.yaml"
    p.write_text(yaml.safe_dump(ex))
    return p


def test_build_variant_applies_overrides_and_picks_the_variant_tools(tmp_path):
    ex = exp_mod.load(write_experiment(tmp_path))
    prob, plan, world, eng = build_variant(ex, "fast")
    assert prob.fleet[0]["speed_mps"] == 8.0 and eng.name == "openclsim" and plan.solver == "pyvrp" and plan.routes
    prob0, _, _, eng0 = build_variant(ex, "paper")
    assert prob0.fleet[0]["speed_mps"] == 5.66 and eng0.name == "replay"
    ex.variants["fast"]["overrides"]["fleet.0.capacity"] = {"value": 12}       # no src, no assumption
    with pytest.raises(ValueError, match="capacity"):
        build_variant(ex, "fast")


def test_run_experiment_end_to_end_with_the_pipeline_builder(tmp_path):
    p = write_experiment(tmp_path)
    res = run_experiment.run(p, load_weather=lambda ex: synthetic_years(2, 24, 1), out=tmp_path / "res.json")
    assert res["blocked"] is None and res["ensemble"]["ok"] and set(res["ensemble"]["variants"]) == {"paper", "fast"}
    assert res["ensemble"]["n_runs"] == 2 * 2 * 2
    assert res["decision"]["kpi"] == "makespan_s" and res["decision"]["status"] in ("supported", "not supported", "inconclusive")
    assert res["reportable"] is False                                           # synthetic weather
    assert json.loads((tmp_path / "res.json").read_text())["gap_id"] == "t-gap"
