"""Winter stress test (N4.3): replay a WFPPP weekly flight program against real NORA3 winters.

Takes a weekly flight program and replays it, unchanged, against every DJF winter
in a NORA3 point series. Counts the operating days on which the program is
infeasible and reports the distribution across winters, not the mean.

Definitions (recorded, not tuned):
- An operating day is a Monday-Friday day of a replayed week (5 per week, 13 weeks
  per DJF winter, 65 operating days per winter).
- A day is INFEASIBLE when at least one flight planned that day is cancelled for
  weather (wind above the limit, or Hs above the limit on a flight serving a
  mobile installation). A cancelled flight is rebooked into the earliest free slot
  of the same week when one exists; a flight with no slot by Friday is UNMET.
- The rebooking rule is the air engine's (perfect forecast, no moves); the numbers
  are therefore an optimistic bound on recovery.

Variants (reported separately, never averaged together):
- "paper": the paper's window structure forced (Bergen [16, 14, 10, 10], Table 4),
  flight assignment optimised under the reconstructed geometry. The paper publishes
  only windows and totals, so the flight-level program is a reconstruction; the
  windows are the paper's.
- "solver": the whelp solver's free optimum at the same geometry (Bergen
  [16, 16, 12, 10] at the Florø-fitted scale, Audit 8).

Assumptions carried in the report (all assumption: true until sourced):
- Installation positions are reconstructed (paper masks them, p.25: 50-120 nm);
  geometry here uses the Florø-fitted radial scale s = 1.03438 (Audit 8).
- Operability limits wind 25 m/s and Hs 6.0 m (mobile installations only), both
  unsourced placeholders (CAP 437 / flight manual / operator minima).
- Weather is a single point series (3.0E, 60.6N); wave and wind come from cells
  ~1 km apart. Direction (thq) is not used: the go/no-go rule needs wind + Hs only.
- Demand split, opening hours and window costs are the paper's (Tables A1-A3, 2, 3).

Usage:
    python -m tools.winter_stress --instance bergen --scale 1.03438 \\
        --point-dir data/worlds/bergen-ncs/metocean_point --point 3.0,60.6 \\
        --years 2000-2023 --season DJF --limit 420 \\
        --out offsim/papers/irinagribkovskaia-2025-tactical-helicopter/stress-test.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import time
from pathlib import Path

import numpy as np

from offsim.engines.air_engine import AirEngine
from offsim.engines.base import Plan, World
from offsim.solve import whelp
from offsim.weather.years import load_years

WEEK_S = 7 * 86400.0


def paper_windows(name: str) -> list[int]:
    """The paper's Table 4 window hours for an instance (sourced, not fitted)."""
    return sorted(whelp.PAPER_RESULT[name]["windows"], reverse=True)


def build_locked_program(problem, spec, flights, windows_h: list[int],
                         limit: float, seed: int = 1):
    """A program with the given window hours forced (stage 1 lock + stage 2 days).

    Returns (plan, detail). plan is None when the locked windows cannot carry the
    flights (stage 1 infeasible) or some day cannot be placed (stage 2 fails);
    detail says which, so the failure is reported, not hidden.
    """
    win_idx = {h: i for i, (h, _c) in enumerate(spec.windows)}
    lock = {}
    for h, wh in enumerate(windows_h):
        if wh not in win_idx:
            return None, {"error": f"window {wh} h is not an option {sorted(win_idx)}"}
        lock[h] = win_idx[wh]
    s1 = whelp.stage1(spec, flights, len(windows_h), lock, limit, seed)
    if s1 is None:
        return None, {"stage1": "infeasible", "lock": lock}
    starts, bad_day = {}, None
    for d in range(spec.days):
        s2 = whelp.stage2_day(spec, flights, s1["per_day"][d], s1["windows"], limit, seed)
        if s2 is None:
            bad_day = d
            break
        starts[d] = s2["starts"]
    if bad_day is not None:
        return None, {"stage1": s1["status"], "windows": s1["windows"],
                      "stage2_infeasible_day": bad_day}
    plan = whelp.make_plan(spec, flights, s1["windows"], starts, s1.get("bound"),
                           "optimal" if s1["status"] == "optimal" else s1["status"],
                           {"method": "decomposition-locked",
                            "locked_windows_h": windows_h, "seed": seed})
    ok, det = whelp.check_program(problem, plan)
    return plan, {"check_program_ok": ok, "check": det,
                  "windows": s1["windows"], "objective": plan.objective}


def _cause(series, spec, flights_by_key, ev, limits, first_idx: int = 0) -> str:
    """Why a cancelled flight failed: 'wind', 'hs', 'both', or 'unknown'.

    Re-checks the departure rule over the flight's own window, using the same
    prefix rule as the engine (any failing hour in [departure, last minute]).
    """
    wk, day = int(ev["week"]), int(ev["day"])
    dep_s = float(ev["t"]) - wk * WEEK_S
    slot_s = spec.slot_min * 60.0
    day0_s = spec.day_start_h * 3600.0
    slot = int(round((dep_s - day * 86400.0 - day0_s) / slot_s))
    key = (str(ev["agent_id"]), day, slot)
    fl = flights_by_key.get(key)
    if fl is None:
        return "unknown"
    h0 = first_idx + wk * 168 + int(math.floor(dep_s / 3600.0 + 1e-9))
    h1 = first_idx + wk * 168 + int(math.floor((dep_s + fl.dur_min * 60.0 - 1e-6) / 3600.0))
    wind = series.df["wind_mps"].to_numpy(float)
    hs = series.df["hs_m"].to_numpy(float)
    wind_bad = bool(np.any(wind[h0:h1 + 1] > float(limits["wind_mps"]) + 1e-12))
    mobile = any(spec.inst[i].mobile for i in fl.inst)
    hs_bad = bool(mobile and "hs_m" in limits
                  and np.any(hs[h0:h1 + 1] > float(limits["hs_m"]) + 1e-12))
    if wind_bad and hs_bad:
        return "both"
    if wind_bad:
        return "wind"
    if hs_bad:
        return "hs"
    return "unknown"


def run_winter(problem, plan, world, series, spec, flights_by_key) -> dict:
    """Replay one winter's series (weeks='all') and count infeasible days."""
    eng = AirEngine()
    res = eng.simulate(problem, plan, world, series)
    ev = res.events
    weeks = int(res.meta["weeks"])
    operating_days = weeks * spec.days
    limits = problem.extra["limits"]
    if len(ev):
        cancels = ev[ev["event"] == "cancel"]
        unmets = ev[ev["event"] == "unmet"]
        infeasible = sorted({(int(w), int(d)) for w, d in zip(cancels["week"], cancels["day"])})
        unmet_days = sorted({(int(w), int(d)) for w, d in zip(unmets["week"], unmets["day"])})
        causes = {}
        for _, row in cancels.iterrows():
            c = _cause(series, spec, flights_by_key, row, limits)
            causes[c] = causes.get(c, 0) + 1
    else:
        infeasible, unmet_days, causes = [], [], {}
    per_week = res.meta["per_week"]
    return {
        "year": int(series.year) if series.year is not None else None,
        "source": str(series.source),
        "weeks": weeks,
        "operating_days": operating_days,
        "infeasible_days": len(infeasible),
        "infeasible_day_list": [f"w{w}d{d}" for w, d in infeasible],
        "days_with_unmet": len(unmet_days),
        "flights_planned": int(res.kpis["flights_planned"]),
        "flights_cancelled": int(res.kpis["flights_cancelled"]),
        "flights_rebooked": int(res.kpis["flights_rebooked"]),
        "flights_unmet": int(res.kpis["flights_unmet"]),
        "cancel_causes": causes,
        "delay_h_mean": float(res.kpis["delay_h_mean"]),
        "delay_h_max": float(res.kpis["delay_h_max"]),
        "utilisation": float(res.kpis["utilisation"]),
        "per_week": per_week,
    }


def _atomic_write(path: str, text: str) -> None:
    """Write via temp + rename, so a kill mid-write never leaves a corrupt file."""
    tmp = f"{path}.tmp"
    Path(tmp).write_text(text)
    os.replace(tmp, path)


def _plan_to_json(plan) -> dict:
    return {"routes": plan.routes, "objective": plan.objective,
            "objective_unit": plan.objective_unit, "solver": plan.solver,
            "bound": plan.bound, "status": plan.status, "meta": plan.meta}


def _plan_from_json(d: dict) -> Plan:
    return Plan(routes=d["routes"], objective=d["objective"],
                objective_unit=d.get("objective_unit", "m"),
                solver=d.get("solver", "whelp"), bound=d.get("bound"),
                status=d.get("status", "optimal"), meta=d["meta"])


def summarise(rows: list[dict]) -> dict:
    """Distribution across winters, not the mean alone."""
    days = np.array([r["infeasible_days"] for r in rows], dtype=float)
    unmet = np.array([r["flights_unmet"] for r in rows], dtype=float)
    op = int(sum(r["operating_days"] for r in rows))
    return {
        "winters": len(rows),
        "operating_days_total": op,
        "infeasible_days_total": int(days.sum()),
        "infeasible_share": float(days.sum() / op) if op else 0.0,
        "infeasible_days_per_winter": [int(d) for d in days],
        "infeasible_days_min": int(days.min()),
        "infeasible_days_p10": float(np.percentile(days, 10)),
        "infeasible_days_median": float(np.median(days)),
        "infeasible_days_p90": float(np.percentile(days, 90)),
        "infeasible_days_max": int(days.max()),
        "winters_with_zero_infeasible": int(np.sum(days == 0)),
        "unmet_flights_total": int(unmet.sum()),
        "unmet_flights_per_winter": [int(u) for u in unmet],
        "winters_with_zero_unmet": int(np.sum(unmet == 0)),
    }


def apply_limit_overrides(problem, wind_mps=None, hs_m=None):
    """Override problem.extra['limits'] (sourced limits for a sensitivity rerun).

    The scenario defaults (wind 25 m/s, Hs 6.0 m) are assumed placeholders;
    a rerun passes sourced values here instead of editing the shared
    scenario. None leaves that limit untouched.
    """
    if wind_mps is not None:
        problem.extra["limits"]["wind_mps"] = wind_mps
    if hs_m is not None:
        problem.extra["limits"]["hs_m"] = hs_m


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--instance", default="bergen")
    ap.add_argument("--scale", type=float, default=1.03438,
                    help="radial scale for the reconstructed geometry (Audit 8)")
    ap.add_argument("--point-dir", required=True)
    ap.add_argument("--point", default="3.0,60.6")
    ap.add_argument("--years", default="2000-2023")
    ap.add_argument("--season", default="DJF")
    ap.add_argument("--limit", type=float, default=420.0)
    ap.add_argument("--variants", default="paper,solver",
                    help="comma list: paper (locked Table 4 windows), solver (free optimum)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", required=True)
    ap.add_argument("--plans", default=None,
                    help="load solved plans from a checkpoint JSON instead of "
                         "re-solving (written to <out>.plans.json when solving)")
    ap.add_argument("--wind-mps", type=float, default=None,
                    help="override limits.wind_mps (sourced go/no-go wind limit)")
    ap.add_argument("--hs-m", type=float, default=None,
                    help="override limits.hs_m (mobile installations only)")
    ap.add_argument("--limits-src", default=None,
                    help="citation for overridden limits, recorded in the output")
    args = ap.parse_args()

    lon, lat = (float(x) for x in args.point.split(","))
    y0, y1 = (int(x) for x in args.years.split("-"))
    years = list(range(y0, y1 + 1))
    t_start = time.time()

    import yaml
    data = yaml.safe_load(open(
        "offsim/papers/irinagribkovskaia-2025-tactical-helicopter/instances.yaml"))
    problem = whelp.problem_for(args.instance, scale=args.scale, data=data)
    apply_limit_overrides(problem, args.wind_mps, args.hs_m)
    spec = whelp.parse_spec(problem)
    flights = whelp.generate_flights(spec)
    problem.extra["wfppp"]["replay"] = {"weeks": "all"}
    world = World(name="winter-stress")

    variants = [v.strip() for v in args.variants.split(",") if v.strip()]
    plans, plan_info = {}, {}
    plans_path = f"{args.out}.plans.json"
    if args.plans:
        ckpt = json.loads(Path(args.plans).read_text())
        for name in variants:
            if name in ckpt.get("plans", {}):
                plans[name] = _plan_from_json(ckpt["plans"][name])
                plan_info[name] = ckpt["plan_info"][name]
        print(f"loaded {list(plans)} plans from {args.plans} (no re-solve)", flush=True)
    else:
        if "solver" in variants:
            print("solving solver variant (free optimum, Bergen ~12 min)...", flush=True)
            t0 = time.time()
            plan_s, prob_s = whelp.evaluate_scale(args.instance, args.scale, data,
                                                  limit=args.limit, seed=args.seed)
            plans["solver"] = plan_s
            plan_info["solver"] = {
                "windows_h": [h["hours"] for h in plan_s.meta["helicopters"]],
                "objective": plan_s.objective,
                "flights_per_week": len(plan_s.meta["program"]),
                "wall_s": round(time.time() - t0, 1),
            }
            print(f"solver variant: windows={plan_info['solver']['windows_h']} "
                  f"objective={plan_s.objective:.1f} ({time.time()-t0:.0f}s)", flush=True)
        if "paper" in variants:
            print("solving paper variant (locked Table 4 windows)...", flush=True)
            t0 = time.time()
            pw = paper_windows(args.instance)
            plan_p, detail = build_locked_program(problem, spec, flights, pw,
                                                  args.limit, args.seed)
            if plan_p is None:
                plan_info["paper"] = {"windows_h": pw, "feasible": False, "detail": detail,
                                      "wall_s": round(time.time() - t0, 1)}
                print(f"paper variant: INFEASIBLE under this geometry: {detail}", flush=True)
            else:
                plans["paper"] = plan_p
                plan_info["paper"] = {
                    "windows_h": [h["hours"] for h in plan_p.meta["helicopters"]],
                    "objective": plan_p.objective,
                    "flights_per_week": len(plan_p.meta["program"]),
                    "check_program_ok": detail["check_program_ok"],
                    "wall_s": round(time.time() - t0, 1),
                }
                print(f"paper variant: windows={plan_info['paper']['windows_h']} "
                      f"objective={plan_p.objective:.1f} "
                      f"check={detail['check_program_ok']} ({time.time()-t0:.0f}s)", flush=True)
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        # Merge with any existing checkpoint (split-stage runs solve one
        # variant at a time; a restart must not wipe the variant already done).
        merged_plans, merged_info = {}, {}
        if Path(plans_path).exists():
            old = json.loads(Path(plans_path).read_text())
            merged_plans, merged_info = old.get("plans", {}), old.get("plan_info", {})
        merged_plans.update({n: _plan_to_json(p) for n, p in plans.items()})
        merged_info.update(plan_info)
        _atomic_write(plans_path, json.dumps(
            {"plans": merged_plans, "plan_info": merged_info},
            indent=2, default=str))
        print(f"checkpointed plans to {plans_path}", flush=True)

    series = load_years(args.point_dir, (lon, lat), years, args.season)
    print(f"loaded {len(series)} winters from {args.point_dir} "
          f"({time.time()-t_start:.0f}s)", flush=True)

    out = {
        "method": "replay the same weekly program against every DJF winter; "
                  "a day is infeasible when >=1 planned flight that day is cancelled",
        "instance": args.instance,
        "scale": args.scale,
        "point": [lon, lat],
        "point_dir": args.point_dir,
        "season": args.season,
        "years": years,
        "limits": {k: float(v) for k, v in problem.extra["limits"].items()},
        "limits_assumption": args.wind_mps is None and args.hs_m is None,
        "limits_src": args.limits_src,
        "positions_assumption": True,
        "variants": plan_info,
        "results": {},
    }
    # Merge with an existing results file (split-stage runs): a variant run
    # must not wipe the results of a variant already replayed.
    if Path(args.out).exists():
        old = json.loads(Path(args.out).read_text())
        out["variants"] = {**old.get("variants", {}), **plan_info}
        out["results"] = old.get("results", {})
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    for name, plan in plans.items():
        # flight lookup is per-variant: heli labels differ between variants.
        by_key = {}
        for r in plan.meta["program"]:
            by_key[(r["heli"], r["day"], r["start_slot"])] = \
                next(f for f in flights if f.fid == r["fid"])
        rows = []
        out["results"][name] = {"per_winter": rows, "summary": None}
        for s in series:
            t0 = time.time()
            row = run_winter(problem, plan, world, s, spec, by_key)
            row["wall_s"] = round(time.time() - t0, 1)
            rows.append(row)
            out["results"][name]["summary"] = summarise(rows)
            _atomic_write(args.out, json.dumps(out, indent=2, default=str))
            print(f"  [{name}] DJF {s.year}/{str(s.year+1)[-2:]}: "
                  f"infeasible {row['infeasible_days']}/{row['operating_days']} days, "
                  f"cancelled {row['flights_cancelled']}, "
                  f"unmet {row['flights_unmet']} ({row['wall_s']}s)", flush=True)
    out["wall_s_total"] = round(time.time() - t_start, 1)
    _atomic_write(args.out, json.dumps(out, indent=2, default=str))
    print(f"wrote {args.out} ({time.time()-t_start:.0f}s total)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
