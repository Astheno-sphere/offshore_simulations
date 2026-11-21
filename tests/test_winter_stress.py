"""Tests for tools/winter_stress.py (N4.3).

The full run (Bergen, 24 winters) is far too slow for the suite, so the tests
cover the mechanics on Florø (solve ~2 s) with synthetic weather: the locked
paper-window program, one winter's replay counts, and the summary distribution.
Synthetic weather is TEST-ONLY here, as everywhere; reported results use NORA3.
"""
import winter_stress
from offsim.engines.base import World
from offsim.solve import whelp
from offsim.weather.years import synthetic_years


def _floro():
    data = whelp.load_instances()
    prob = whelp.problem_for("floro", scale=1.03438, data=data)
    spec = whelp.parse_spec(prob)
    return prob, spec, whelp.generate_flights(spec)


def test_locked_program_reproduces_paper_windows_floro():
    prob, spec, flights = _floro()
    plan, detail = winter_stress.build_locked_program(
        prob, spec, flights, [10], limit=120.0)
    assert plan is not None, detail
    assert [h["hours"] for h in plan.meta["helicopters"]] == [10]
    assert detail["check_program_ok"] is True
    assert abs(plan.objective - 9980.5) < 1.0


def test_run_winter_counts_are_consistent():
    prob, spec, _flights = _floro()
    plan, _ = whelp.evaluate_scale("floro", 1.03438, whelp.load_instances(), limit=120.0)
    prob.extra["wfppp"]["replay"] = {"weeks": "all"}
    series = synthetic_years(n=1, hours=336, seed=7)
    by_key = {(r["heli"], r["day"], r["start_slot"]):
              next(f for f in whelp.generate_flights(spec) if f.fid == r["fid"])
              for r in plan.meta["program"]}
    row = winter_stress.run_winter(prob, plan, World(name="test"), series[0], spec, by_key)
    assert row["weeks"] == 2
    assert row["operating_days"] == 10
    assert 0 <= row["infeasible_days"] <= row["operating_days"]
    assert row["flights_cancelled"] == row["flights_rebooked"] + row["flights_unmet"]
    assert row["flights_planned"] == 2 * len(plan.meta["program"])
    assert set(row["cancel_causes"]) <= {"wind", "hs", "both", "unknown"}


def test_limit_overrides_replace_scenario_defaults():
    prob, _, _ = _floro()
    assert prob.extra["limits"] == {"wind_mps": 25.0, "hs_m": 6.0}
    winter_stress.apply_limit_overrides(prob, wind_mps=30.87, hs_m=7.0)
    assert prob.extra["limits"] == {"wind_mps": 30.87, "hs_m": 7.0}
    winter_stress.apply_limit_overrides(prob)
    assert prob.extra["limits"] == {"wind_mps": 30.87, "hs_m": 7.0}


def test_summarise_reports_distribution_not_mean():
    rows = [{"infeasible_days": d, "flights_unmet": u, "operating_days": 65}
            for d, u in [(0, 0), (3, 1), (5, 0), (9, 2), (12, 4)]]
    s = winter_stress.summarise(rows)
    assert s["winters"] == 5
    assert s["infeasible_days_total"] == 29
    assert s["infeasible_days_per_winter"] == [0, 3, 5, 9, 12]
    assert s["infeasible_days_min"] == 0
    assert s["infeasible_days_max"] == 12
    assert s["infeasible_days_median"] == 5.0
    assert s["winters_with_zero_infeasible"] == 1
    assert s["unmet_flights_total"] == 7
