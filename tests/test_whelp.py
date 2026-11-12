"""WFPPP: flight generation, the whelp solver (decomposition + flight-based model), the AMPL twin, the air engine, the pipeline.

Paper: Gribkovskaia & Slettemark (2025), Logistics 9(2):73. Installation positions are masked in the paper: the instances use assumed
positions calibrated to Table 4 (instances.yaml), so the reproduction is `re-run under assumptions`. All weather here is SYNTHETIC.
Set OFFSIM_SLOW=1 to also run the Bergen instance (about 1.5 min) and the Florø flight-based model (about 40 s).
"""
from __future__ import annotations

import math
import os
import time

import numpy as np
import pandas as pd
import pytest
import yaml

from conftest import ROOT
from offsim import contract, pipeline
from offsim.engines import Plan, Problem, Unsupported, WeatherSeries, World, available, get_engine, get_solver
from offsim.solve import whelp as W

SCEN = ROOT / "offsim/papers/irinagribkovskaia-2025-tactical-helicopter/scenario.yaml"
MOD = ROOT / "offsim/solve/ampl/whelp.mod"
SLOW = pytest.mark.skipif(not os.environ.get("OFFSIM_SLOW"), reason="slow (set OFFSIM_SLOW=1)")
HP = (5.0, 60.0)


def wx(hours=168, wind=8.0, hs=1.5, storm=None, hs_storm=None) -> WeatherSeries:
    """TEST-ONLY hourly series. storm = (hour_from, hour_to, wind_mps); hs_storm = (hour_from, hour_to, hs_m)."""
    w, h = np.full(hours, wind, float), np.full(hours, hs, float)
    if storm:
        w[storm[0]:storm[1]] = storm[2]
    if hs_storm:
        h[hs_storm[0]:hs_storm[1]] = hs_storm[2]
    return WeatherSeries(pd.DataFrame({"t": np.arange(hours) * 3600.0, "hs_m": h, "wind_mps": w}), "SYNTHETIC (test only)", None)


def toy(radii=(60.0, 100.0), brgs=(270.0, 300.0), demand=(1.5, 2.0), open_=("07:00-18:00", "07:00-22:00"), days=5,
        windows=((10, 5968), (12, 6625), (16, 7000)), max_helis=2) -> Problem:
    pts = [W.destination(HP[0], HP[1], b, r) for r, b in zip(radii, brgs)]
    ins = [{"name": f"X{i + 1}", "demand_flights": d, "open": o, "mobile": o.endswith("22:00")} for i, (d, o) in enumerate(zip(demand, open_))]
    w = {"windows": [{"hours": h, "cost": c} for h, c in windows], "max_helicopters": max_helis, "installations": ins, "days": days}
    return Problem(cls={"WFPPP"}, nodes=[HP] + pts, dist_m=None, demand={}, fleet=[],
                   extra={"wfppp": w, "limits": {"wind_mps": 20.0, "hs_m": 5.0}})


# ------------------------------------------------------------------------------------------------- registry
def test_registry_has_whelp_and_air():
    av = available()
    assert av["solvers"]["whelp"] == "ok" and av["engines"]["air"] == "ok"
    assert get_solver("whelp").classes == {"WFPPP"} and get_engine("air").classes == {"WFPPP"}
    assert get_engine("air").needs_weather is True


# ------------------------------------------------------------------------------------------------- flight generation (Sec 4.2)
def test_direct_flight_duration_slots_and_cost_by_hand():
    p = toy(radii=(60.0, 100.0), brgs=(270.0, 300.0))          # 60 nm and 100 nm, far apart (> 15 min between them)
    spec = W.parse_spec(p)
    fl = W.generate_flights(spec)
    assert [f.kind for f in fl] == ["direct", "direct"]
    for f, r in zip(fl, (60.0, 100.0)):
        air = 2 * r / 125.0 * 60.0                             # minutes at 125 kn
        dur = air + 10.0                                       # one deck stop
        assert f.fly_min == pytest.approx(air, rel=2e-3)
        assert f.dur_min == pytest.approx(dur, rel=2e-3)
        assert f.n == math.ceil((f.dur_min + 60.0) / 15.0 - 1e-9)       # slots incl. 1 h turnaround, rounded up
        assert f.n_fly == f.n - 4
        assert f.cost == pytest.approx(140.0 * f.dur_min / 60.0)         # turnaround and rounding are not costed
    assert fl[0].n == 9 and fl[1].n == 12                      # 67.6 + 60 = 127.6 -> 9 ; 170 + 60 -> 12 (hand values)


def test_split_flights_only_below_the_15_minute_threshold():
    a = W.destination(HP[0], HP[1], 270.0, 90.0)
    near = W.destination(*a, 0.0, 31.0)                         # 31 nm = 14.9 min
    far = W.destination(*a, 0.0, 33.0)                          # 33 nm = 15.8 min
    for second, expect in ((near, 1), (far, 0)):
        p = toy()
        p.nodes[1], p.nodes[2] = a, second
        spec = W.parse_spec(p)
        fl = W.generate_flights(spec)
        splits = [f for f in fl if f.kind == "split"]
        assert len(splits) == expect
        if expect:
            t_h, t_ij = W.leg_minutes(spec)
            f = splits[0]
            assert f.dur_min == pytest.approx(t_h[0] + t_ij[0][1] + t_h[1] + 2 * 10.0)    # two deck stops
            assert f.n == math.ceil((f.dur_min + 60.0) / 15.0 - 1e-9)


def test_floro_flight_set_and_fleet_bound():
    spec = W.parse_spec(W.problem_for("floro"))
    fl = W.generate_flights(spec)
    assert sum(f.kind == "direct" for f in fl) == 4 and sum(f.kind == "split" for f in fl) == 1
    assert [i.demand_half for i in spec.inst] == [13, 9, 8, 8]            # Table A1 x 2
    assert sum(i.demand_half for i in spec.inst) == 38                    # 19 flights per week (p.25-26)
    assert [(i.lo, i.hi) for i in spec.inst] == [(0, 44), (0, 44), (0, 44), (0, 60)]    # 07-18 h and 07-22 h departures
    assert W.fleet_upper_bound(spec, fl) == 1
    assert spec.windows == ((10.0, 5968.0), (12.0, 6625.0), (16.0, 7000.0)) and spec.l == 4


def test_instances_match_the_appendix_tables():
    for name, n, total in (("floro", 4, 19.0), ("bergen", 20, 93.0)):
        spec = W.parse_spec(W.problem_for(name))
        assert len(spec.inst) == n and sum(i.demand_half for i in spec.inst) / 2 == total
    st = W.parse_spec(W.problem_for("stavanger"))
    assert len(st.inst) == 12 and sum(i.mobile for i in st.inst) == 4
    # Table A2 sums to 48.5 flights although the text and Table 2 say 46.5 (paper inconsistency, documented in docs/ENGINES.md)
    assert sum(i.demand_half for i in st.inst) / 2 == 48.5


def test_assumed_positions_stay_within_the_paper_ranges():
    for name in ("floro", "stavanger", "bergen"):
        q = W.quay_stats(W.problem_for(name))
        assert 48.0 <= min(q["radius_nm"]) and max(q["radius_nm"]) <= 125.0, (name, q)     # "ca 50 to 120 nm" (p.25)
        assert 0.95 <= min(q["direct_h"]) and max(q["direct_h"]) <= 2.6, (name, q)         # "approximately 1 to 2.5 h"


# ------------------------------------------------------------------------------------------------- solver
def test_floro_reproduces_one_helicopter_10h_and_the_cost():
    p = W.problem_for("floro")
    t0 = time.perf_counter()
    plan = get_solver("whelp").solve(p, seconds=2.0)
    assert time.perf_counter() - t0 < 30
    assert plan.status == "optimal" and plan.solver == "whelp" and plan.objective_unit == "masked cost units"
    assert [h["label"] for h in plan.meta["helicopters"]] == ["H1-10h"]
    assert abs(plan.objective / 9980.0 - 1.0) < 0.05                            # Table 4 (positions calibrated)
    assert plan.meta["flights_total"] == 19 and plan.meta["fixed_cost"] == 5968
    assert plan.objective == pytest.approx(plan.meta["fixed_cost"] + plan.meta["variable_cost"])
    assert plan.bound is not None and plan.bound <= plan.objective + 1e-6
    ok, d = W.check_program(p, plan)
    assert ok, d
    # held-out check, not used in the calibration: Table 4's utilisation 86.82 % = 191 / 220 slots
    assert abs(plan.meta["slots_total"] - 191) <= 10
    prog = plan.meta["program"]
    assert all({"heli", "day", "start_slot", "installations", "duration_slots", "cost"} <= set(r) for r in prog)
    assert plan.routes == {"H1-10h": [n for r in prog for n in r["node_idx"]]}
    assert plan.meta["shift_gap_days"] == 0


def test_policies_hold_in_the_floro_program():
    p = W.problem_for("floro")
    plan = get_solver("whelp").solve(p)
    prog = plan.meta["program"]
    per = {}
    for r in prog:
        for n in r["installations"]:
            per.setdefault(n, [0] * 5)[r["day"]] += 1
    assert all(max(v) - min(v) <= 1 for v in per.values())                      # eq (10): spread
    for d in range(5):                                                          # eq (11): no idle slot between flights
        day = sorted((r["start_slot"], r["duration_slots"]) for r in prog if r["day"] == d)
        t = 0
        for s, n in day:
            assert s == t
            t = s + n
    mobile = [r for r in prog if "F4" in r["installations"]]
    assert mobile and all(r["start_slot"] < 60 for r in prog)


def test_decomposition_equals_the_flight_based_model_on_a_small_instance():
    p = toy(radii=(60.0, 80.0), brgs=(270.0, 280.0), demand=(1.5, 1.0), days=3, windows=((10, 5968), (12, 6625)), max_helis=2)
    p.extra["wfppp"]["method"] = "decomposition"
    dec = get_solver("whelp").solve(p)
    p.extra["wfppp"]["method"] = "full"
    full = get_solver("whelp").solve(p)
    assert dec.status == "optimal" and full.status == "optimal"
    assert dec.objective == pytest.approx(full.objective, rel=1e-9)
    assert W.check_program(p, dec)[0] and W.check_program(p, full)[0]


@SLOW
def test_floro_decomposition_equals_the_flight_based_model():
    p = W.problem_for("floro")
    dec = get_solver("whelp").solve(p)
    p.extra["wfppp"]["method"] = "full"
    full = get_solver("whelp").solve(p, seconds=300)
    assert dec.objective == pytest.approx(full.objective, rel=1e-6)


@SLOW
def test_stavanger_structure_two_helicopters_16_and_12():
    p = W.problem_for("stavanger")
    t0 = time.perf_counter()
    plan = get_solver("whelp").solve(p, seconds=2.0)
    wall = time.perf_counter() - t0
    if wall > 60:
        pytest.skip(f"Stavanger took {wall:.0f} s here (> 60 s): covered by OFFSIM_SLOW runs")
    assert sorted(h["hours"] for h in plan.meta["helicopters"]) == [12.0, 16.0]
    assert abs(plan.objective / 26642.0 - 1.0) < 0.05
    ok, d = W.check_program(p, plan)
    assert ok, d


@SLOW
def test_bergen_structure_four_helicopters():
    p = W.problem_for("bergen")
    plan = get_solver("whelp").solve(p, seconds=2.0)
    assert sorted(h["hours"] for h in plan.meta["helicopters"]) == [10.0, 10.0, 14.0, 16.0]
    assert abs(plan.objective / 47582.0 - 1.0) < 0.05
    assert W.check_program(p, plan)[0]


def test_decomposition_iterates_when_stage_two_is_infeasible():
    # many installations at the same distance, tight 10 h window, 2 helicopters allowed: Stage 1 may cram a day that Stage 2 cannot place
    p = toy(radii=(100.0, 100.0), brgs=(270.0, 290.0), demand=(3.0, 3.0), windows=((10, 5968), (12, 6625), (16, 7000)), max_helis=3)
    plan = get_solver("whelp").solve(p)
    assert W.check_program(p, plan)[0]
    assert len(plan.meta["iterations"]) >= 1


def test_solver_refuses_what_it_cannot_do():
    s = get_solver("whelp")
    with pytest.raises(Unsupported):
        s.solve(Problem(cls={"CVRP"}, nodes=[HP], dist_m=None, demand={}, fleet=[]))
    with pytest.raises(Unsupported):
        s.solve(Problem(cls={"WFPPP"}, nodes=[HP], dist_m=None, demand={}, fleet=[]))           # no wfppp block
    p = toy()
    p.extra["wfppp"]["method"] = "nope"
    with pytest.raises(Unsupported):
        s.solve(p)
    p = toy(demand=(1.25, 2.0))
    with pytest.raises(Unsupported):                                                            # not a multiple of a half-flight
        s.solve(p)


def test_infeasible_when_a_flight_cannot_fit_any_window():
    # a 120 nm direct flight is 125 min = 9 fly slots: it FITS a 4 h window (16 slots), so a 4 h window is
    # feasible and the solver correctly returns a plan. A 2 h window (8 slots) genuinely cannot hold it.
    p = toy(radii=(120.0, 120.0), brgs=(270.0, 300.0), windows=((2, 1000),), max_helis=1)
    with pytest.raises(RuntimeError):
        get_solver("whelp").solve(p)


def test_check_program_catches_a_broken_plan():
    p = W.problem_for("floro")
    plan = get_solver("whelp").solve(p)
    bad = Plan(routes=plan.routes, objective=plan.objective, meta={**plan.meta, "program": [dict(r) for r in plan.meta["program"]]})
    bad.meta["program"][1]["start_slot"] = bad.meta["program"][0]["start_slot"]
    bad.meta["program"][1]["day"] = bad.meta["program"][0]["day"]
    ok, d = W.check_program(p, bad)
    assert not ok and d["errors"]
    short = Plan(routes=plan.routes, objective=plan.objective, meta={**plan.meta, "program": plan.meta["program"][:-1]})
    assert not W.check_program(p, short)[0]


# ------------------------------------------------------------------------------------------------- AMPL twin
def test_write_dat_and_mod_declarations(tmp_path):
    p = W.problem_for("floro")
    dat = W.write_dat(p, tmp_path / "whelp.dat")
    text = dat.read_text()
    for needle in ("set I := 1 2 3 4;", "set H := 1;", "set W := 1 2 3;", "set F1 := 1 2 3 4;", "set F2 := 5;", "set D := 1 2 3 4 5;",
                   "param l := 4;", "param b :=", "1 13 2 9 3 8 4 8;", "param k :=", "1 5968.000000",
                   "param s :=", "param c :=", "param n :=", "param a :=", "param pdep :="):
        assert needle in text, needle
    assert "set T := 0 1 2" in text and text.count(" 63") >= 1                  # slots 0..63 (16 h window)
    mod = MOD.read_text()
    for needle in ("set VALID", "var x {VALID} binary;", "var y {H, W} binary;", "minimize total_cost", "subject to demand",
                   "subject to one_landing", "subject to occupancy", "subject to shift", "subject to spread_up", "(1)", "(11)"):
        assert needle in mod, needle


def test_whelp_mod_passes_the_text_screen():
    import importlib.util
    pytest.importorskip("mcp")
    spec = importlib.util.spec_from_file_location("ampl_mcp_server", ROOT / "tools/ampl_mcp/server.py")
    server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server)
    server.screen(MOD.read_text(), model_file=True)


def _ampl_ok():
    from offsim.solve.ampl_adapter import ampl_status
    return ampl_status()


AMPL_OK, AMPL_WHY = _ampl_ok()


@pytest.mark.skipif(not AMPL_OK, reason=f"AMPL cannot start here: {AMPL_WHY}")
def test_whelp_mod_parses_and_reads_data(tmp_path):
    from offsim.solve import ampl_adapter as A
    p = W.problem_for("floro")
    dat = W.write_dat(p, tmp_path / "whelp.dat")
    ampl = A._start_ampl()
    ampl.read(str(MOD))
    ampl.read_data(str(dat))
    assert ampl.get_objective("total_cost") is not None


# ------------------------------------------------------------------------------------------------- air engine
@pytest.fixture(scope="module")
def floro_plan():
    p = W.problem_for("floro")
    return p, get_solver("whelp").solve(p)


def test_air_calm_week_has_no_cancellations(floro_plan):
    p, plan = floro_plan
    r = get_engine("air").simulate(p, plan, World("none"), wx())
    k = r.kpis
    assert k["flights_planned"] == 19 and k["flights_flown"] == 19
    assert k["flights_cancelled"] == 0 and k["flights_rebooked"] == 0 and k["unmet_half_flights"] == 0
    assert k["delay_h_mean"] == 0.0 and r.events.empty
    assert k["utilisation"] == pytest.approx(plan.meta["utilisation"])
    assert k["planned_variable_cost"] == pytest.approx(plan.meta["variable_cost"], rel=1e-6)    # independent recomputation
    assert k["plan_cost"] == pytest.approx(plan.objective) and k["helicopters"] == 1 and k["window_hours"] == 10
    rep = contract.validate(r.traj, r.agents)
    assert rep.ok, str(rep)
    assert set(r.traj["state"]) == {"fly", "unload", "load", "idle"}
    assert (r.agents["domain"] == "air").all() and list(r.agents["agent_id"]) == ["H1-10h"]
    assert r.traj[["lon", "lat"]].min().min() > 0 and r.weather == "SYNTHETIC (test only)"


def test_air_storm_day_cancels_and_rebooks(floro_plan):
    p, plan = floro_plan
    # Monday 07:00-12:00. The storm must fall on a day with slack AFTER it: the solved Florø program is packed
    # back-to-back (eq 11) with no free slot on days 1-4, and Monday's tail (slots 32-39) is the week's only slack,
    # so a Tuesday storm (the original setup) legitimately rebooks nothing. See test_air_tuesday_storm_has_no_slack.
    series = wx(storm=(7, 12, 30.0))
    r = get_engine("air").simulate(p, plan, World("none"), series)
    k = r.kpis
    assert k["flights_cancelled"] > 0
    assert k["flights_rebooked"] > 0                            # the 07:00 departure rebooks into Monday's tail
    assert k["flights_rebooked"] + k["flights_unmet"] == k["flights_cancelled"]
    assert k["flights_flown"] == k["flights_planned"] - k["flights_unmet"]
    assert k["unmet_half_flights"] == 2 * k["flights_unmet"]
    assert k["delay_h_mean"] > 0 and k["delay_h_max"] >= k["delay_h_mean"]
    assert set(r.events["event"]) >= {"cancel", "rebook"}
    assert "wait" in set(r.traj["state"])
    rep = contract.validate(r.traj, r.agents)
    assert rep.ok, str(rep)
    # every flown departure is clear of the storm: no fly row inside the stormy hours (Monday 07:00-12:00)
    fly = r.traj[(r.traj["state"] == "fly")]
    assert not ((fly["t"] > (7 * 3600)) & (fly["t"] < (12 * 3600))).any()


def test_air_tuesday_storm_has_no_slack_so_flights_go_unmet(floro_plan):
    """Regression for the original storm setup: a Tuesday 07:00-12:00 storm cancels three flights and the engine
    correctly reports them unmet instead of inventing slack. The solved program has no free slot on days 1-4
    (verified: days 1-4 use slots 0-40/41; only Monday's tail is free, and it lies before the storm)."""
    p, plan = floro_plan
    r = get_engine("air").simulate(p, plan, World("none"), wx(storm=(31, 36, 30.0)))
    k = r.kpis
    assert k["flights_cancelled"] == 3
    assert k["flights_rebooked"] == 0 and k["flights_unmet"] == 3
    assert k["flights_flown"] == k["flights_planned"] - 3
    assert set(r.events["event"]) == {"cancel", "unmet"}
    assert contract.validate(r.traj, r.agents).ok


def test_air_rebooked_flights_respect_the_rules(floro_plan):
    p, plan = floro_plan
    spec = W.parse_spec(p)
    storm = (0, 10)                                             # Monday 00:00-10:00 (same reason as above: slack is Monday's tail)
    r = get_engine("air").simulate(p, plan, World("none"), wx(storm=(storm[0], storm[1], 30.0)))
    reb = r.events[r.events["event"] == "rebook"]
    assert len(reb)
    slot = 15 * 60.0
    for _, e in reb.iterrows():
        t_new = e["new_departure_t"] - 7 * 3600.0
        d, rem = divmod(t_new, 86400.0)
        assert 0 <= d < 5 and rem % slot == 0                   # a slot start on a weekday
        assert e["new_departure_t"] >= e["t"]                   # never earlier than the cancelled departure
        assert not (storm[0] * 3600 <= e["new_departure_t"] < storm[1] * 3600)   # never inside the storm
    fly = r.traj[r.traj["state"] == "fly"]["t"].to_numpy()
    assert (fly < 5 * 86400).all()


def test_air_is_deterministic_and_seed_free(floro_plan):
    p, plan = floro_plan
    s = wx(storm=(24, 40, 30.0))
    a = get_engine("air").simulate(p, plan, World("none"), s, seed=1)
    b = get_engine("air").simulate(p, plan, World("none"), s, seed=99)
    assert a.kpis == b.kpis
    pd.testing.assert_frame_equal(a.traj, b.traj)


def test_air_wave_limit_hits_only_flights_to_mobile_installations(floro_plan):
    p, plan = floro_plan
    r = get_engine("air").simulate(p, plan, World("none"), wx(hs_storm=(0, 168, 9.0)))
    n_mobile = sum("F4" in f["installations"] for f in plan.meta["program"])
    assert r.kpis["flights_cancelled"] == n_mobile > 0
    calm = get_engine("air").simulate(p, plan, World("none"), wx(wind=26.0))                  # wind limit 25 m/s applies to every flight
    assert calm.kpis["flights_cancelled"] == 19 and calm.kpis["flights_flown"] == 0
    assert calm.kpis["flights_unmet"] == 19 and calm.kpis["unmet_half_flights"] == 38
    assert contract.validate(calm.traj, calm.agents).ok


def test_air_multi_week_replay(floro_plan):
    p, plan = floro_plan
    p2 = Problem(**{**p.__dict__, "extra": {**p.extra, "wfppp": {**p.extra["wfppp"], "replay": {"weeks": "all"}}}})
    series = wx(hours=3 * 168, storm=(168 + 30, 168 + 40, 30.0))
    r = get_engine("air").simulate(p2, plan, World("none"), series)
    assert r.kpis["weeks"] == 3 and r.kpis["flights_planned"] == 57
    pw = r.meta["per_week"]
    assert pw[0]["cancelled"] == 0 and pw[1]["cancelled"] > 0 and pw[2]["cancelled"] == 0
    assert contract.validate(r.traj, r.agents).ok


def test_air_refuses_instead_of_approximating(floro_plan):
    p, plan = floro_plan
    eng = get_engine("air")
    with pytest.raises(Unsupported):
        eng.simulate(p, plan, World("none"), None)                                              # needs weather
    with pytest.raises(Unsupported):
        eng.simulate(p, Plan({}, 0.0), World("none"), wx())                                     # no program
    noli = Problem(**{**p.__dict__, "extra": {k: v for k, v in p.extra.items() if k != "limits"}})
    with pytest.raises(Unsupported):
        eng.simulate(noli, plan, World("none"), wx())
    s = wx()
    s.df = s.df.iloc[::2].reset_index(drop=True)
    with pytest.raises(Unsupported):
        eng.simulate(p, plan, World("none"), s)                                                 # 2-hourly
    with pytest.raises(Unsupported):
        eng.simulate(p, plan, World("none"), wx(hours=48))                                      # too short for the week


# ------------------------------------------------------------------------------------------------- scenario + pipeline
def test_scenario_is_sourced_and_in_sync_with_the_instance_data():
    sc = yaml.safe_load(SCEN.read_text())
    assert pipeline.provenance_gaps(sc) == []
    assert sc["problem"]["class"] == ["WFPPP"] and pipeline.select_tools(sc) == ("whelp", "air")
    assert sc["param"]["instance"] == "floro" and sc["paper"]["licence"] == "CC BY 3.0"
    assert yaml.safe_load(yaml.safe_dump(W.build_scenario("floro"))) == sc
    assumed = pipeline.assumptions_used(sc)
    assert any("limits" in a for a in assumed) and any("stops" in a for a in assumed)           # limits and positions are flagged
    prob, _, meta = pipeline.build_problem(sc)
    ref = W.problem_for("floro")
    assert prob.nodes == ref.nodes and prob.extra["wfppp"] == ref.extra["wfppp"] and prob.extra["limits"] == ref.extra["limits"]


@pytest.mark.parametrize("name", ["stavanger", "bergen"])
def test_other_instance_scenarios_are_written_and_sourced(name):
    p = SCEN.with_name(f"scenario.{name}.yaml")
    sc = yaml.safe_load(p.read_text())
    assert pipeline.provenance_gaps(sc) == [] and sc["param"]["instance"] == name
    assert yaml.safe_load(yaml.safe_dump(W.build_scenario(name))) == sc


def test_offsim_run_on_floro_reaches_the_gates_with_synthetic_weather(tmp_path):
    sc = yaml.safe_load(SCEN.read_text())
    sc["weather"] = {"synthetic": {"n": 1, "hours": 168}}
    p = tmp_path / "scenario.yaml"
    p.write_text(yaml.safe_dump(sc))
    rep = pipeline.run(p, tmp_path / "out", seconds=2)
    g = rep["gates"]
    assert all(g[k]["pass"] for k in ("0_provenance", "1_plan", "2_replay_equals_plan", "3_contract")), g
    assert g["2_replay_equals_plan"]["detail"][0]["kpi"] == "planned_variable_cost"
    assert g["4_paper"]["pass"], g["4_paper"]
    assert rep["status"] == "re-run under assumptions (synthetic weather, not reportable)"
    assert rep["reportable"] is False
    assert rep["tools"]["solver"] == "whelp" and rep["tools"]["engine"] == "air"
    assert {r["kpi"] for r in g["4_paper"]["detail"]} == {"plan_cost", "helicopters", "window_hours"}


def test_offsim_run_stops_at_gate_0_without_weather(tmp_path):
    rep = pipeline.run(SCEN, tmp_path / "out", seconds=2)
    assert rep["status"] == "stopped at gate 0_provenance" and "missing_weather" in rep["gates"]["0_provenance"]["detail"]
