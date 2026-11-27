"""Stress-test pair: the (winter, seed) where two variants' validated trajectories diverge most.

An experiment's ensemble keeps KPI floats only (`montecarlo.ensemble._execute` drops `res.traj` after validating it), so a
trajectory pair cannot be read back from `Ensemble.to_report()`. This module re-simulates the two compared variants for
every (weather year, seed) where BOTH rows were valid, scores each pair, and keeps only the running maximum, so memory is
one pair and the extra compute is about the cost of the two compared variants again. It is opt-in per experiment:

    stress: {metric: max_divergence}        # experiment.yaml; `Experiment.extra['stress']`

and called from `run_experiment.run()` only when the ensemble is ok and a decision exists. Result, under
`report['decision']['pair']['stress']` (so `report:decision.pair.stress.max_divergence_m` resolves):

    {selection, selected_on, compare, year, wx, seed, max_divergence_m, agent_id, t_star_s, pos_a, pos_b, coverage,
     distribution: {n_pairs, n_skipped, skip_reasons, p50, p90, max}, traj_sha256: {variant: sha256}, note}

SELECTION, stated plainly: this picks the pair with the largest spatial divergence, NOT the pair with the worst decision
KPI and not the median. It is a worst case by one rule chosen for how it looks on a map. The frame that draws it must say
so (the evidence form's `limits` line) and must cite `report:decision.effect` (with `ci95`) for the statistical result;
`distribution` is there so the frame can say "worst of N pairs, median X m" instead of implying the extreme is typical.

Guards (a failed guard makes the stress block absent and sets `report['stress_blocked']`; nothing is narrated from it):
- determinism: each re-run's numeric KPIs must equal that run's ensemble row EXACTLY, and its trajectory must pass
  `offsim.contract.validate` again; otherwise the pair that would be persisted may not be the run that was counted.
- agents: the two variants' `agents` tables must name the same (agent_id, cls) set; "route 0" of one solver is not
  "route 0" of another unless the ids name the same vessel. A pair that fails this is skipped and counted.

Sidecars (trajectories as CSV, next to `out` only, never in git; `traj_sha256` pins them, and (year, seed) plus the
determinism guard reproduce them): `<out stem>.stress.<variant>.csv`.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

from offsim.contract import haversine_m
from offsim.contract import validate as validate_contract

METRICS = ("max_divergence",)


def _tracks(traj: pd.DataFrame) -> dict:
    """{agent_id: (t, lon, lat)} with strictly increasing t, exactly as `cinema.vessel.display_offset_check` prepares them."""
    out = {}
    for aid, g in traj.groupby("agent_id", sort=False):
        g = g.sort_values("t", kind="stable")
        t, lo, la = g["t"].to_numpy(float), g["lon"].to_numpy(float), g["lat"].to_numpy(float)
        keep = np.r_[t[1:] > t[:-1], True]
        out[aid] = (t[keep], lo[keep], la[keep])
    return out


def _fleet(agents: pd.DataFrame) -> set:
    return set(zip(agents["agent_id"].astype(str), agents["cls"].astype(str)))


def divergence(traj_a: pd.DataFrame, agents_a: pd.DataFrame, traj_b: pd.DataFrame, agents_b: pd.DataFrame) -> dict:
    """Max great-circle distance (m) between the same agent's position in two validated trajectories, and where.

    Both tracks are linearly interpolated in lon/lat the way the renderer and `display_offset_check` do; the difference of
    two piecewise-linear tracks is piecewise linear, so its maximum lies on the union of both time grids, which is what is
    evaluated, over the time window both tracks cover. Unlike `display_offset_check` this returns the argmax (agent, t*, both
    positions) and the coverage, and REFUSES (ValueError) when the two fleets differ, instead of skipping unmatched agents.
    """
    fa, fb = _fleet(agents_a), _fleet(agents_b)
    if fa != fb:
        raise ValueError(f"agents tables differ: only in a {sorted(fa - fb)}, only in b {sorted(fb - fa)}")
    ta, tb = _tracks(traj_a), _tracks(traj_b)
    best, matched, unmatched, overlaps = None, 0, [], []
    for aid in sorted(ta, key=str):
        if aid not in tb:
            unmatched.append(str(aid))
            continue
        (t1, lo1, la1), (t2, lo2, la2) = ta[aid], tb[aid]
        lo_t, hi_t = max(t1[0], t2[0]), min(t1[-1], t2[-1])
        span = max(t1[-1], t2[-1]) - min(t1[0], t2[0])
        if hi_t < lo_t:
            unmatched.append(str(aid))
            continue
        tt = np.union1d(t1, t2)
        tt = tt[(tt >= lo_t) & (tt <= hi_t)]
        if len(tt) == 0:
            unmatched.append(str(aid))
            continue
        pa = (np.interp(tt, t1, lo1), np.interp(tt, t1, la1))
        pb = (np.interp(tt, t2, lo2), np.interp(tt, t2, la2))
        d = haversine_m(pa[0], pa[1], pb[0], pb[1])
        i = int(np.argmax(d))
        matched += 1
        overlaps.append(float((hi_t - lo_t) / span) if span > 0 else 1.0)
        if best is None or float(d[i]) > best["max_divergence_m"]:
            best = {"max_divergence_m": float(d[i]), "agent_id": str(aid), "t_star_s": float(tt[i]),
                    "pos_a": [float(pa[0][i]), float(pa[1][i])], "pos_b": [float(pb[0][i]), float(pb[1][i])]}
    if best is None:
        raise ValueError(f"no agent has a time window in both trajectories (unmatched: {unmatched})")
    best["coverage"] = {"matched_agents": matched, "unmatched_agents": unmatched,
                        "time_overlap_min": float(min(overlaps))}
    return best


def _year(y):
    """JSON-safe year label: an int when it is whole, None when the ensemble had no weather year."""
    if y is None or (isinstance(y, float) and np.isnan(y)):
        return None
    return int(y) if float(y) == int(y) else y


def _sha(traj: pd.DataFrame) -> str:
    return hashlib.sha256(traj.to_csv(index=False).encode()).hexdigest()


def _same_kpis(res, row) -> str | None:
    """None when every numeric KPI of `res` equals the ensemble row exactly; else what differs."""
    for k, v in (res.kpis or {}).items():
        if isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, bool):
            r = row.get(k)
            if r is None or not (float(v) == float(r) or (np.isnan(float(v)) and np.isnan(float(r)))):
                return f"kpi {k!r}: re-run {float(v)!r} vs ensemble {r!r}"
    return None


def find_stress(ex, built: dict, weather: list, ens, metric: str = "max_divergence"):
    """-> (stress_block | None, {variant: trajectory DataFrame} | {}, blocked_reason | None). See the module docstring.

    `built` is {variant: (problem, plan, world, engine)} EXACTLY as the ensemble ran them. It is never rebuilt here: a builder
    that solves (offsim.pipeline.build_variant calls a time-limited solver) can return a different plan the second time, and the
    pair persisted would then not be the run that was counted."""
    if metric not in METRICS:
        raise ValueError(f"stress.metric must be one of {METRICS}, got {metric!r}")
    a, b = ex.decision["compare"][:2]
    wxs = list(weather) or [None]
    runs = ens.runs
    ra = runs[(runs["variant"] == a) & runs["valid"]].set_index(["wx", "seed"])
    rb = runs[(runs["variant"] == b) & runs["valid"]].set_index(["wx", "seed"])
    keys = sorted(set(ra.index) & set(rb.index))
    every = {(int(w), int(s)) for w, s in zip(runs[runs["variant"].isin([a, b])]["wx"], runs[runs["variant"].isin([a, b])]["seed"])}
    n_excluded = len(every) - len(keys)
    if not keys:
        return None, {}, "stress: no (year, seed) where both compared variants have a valid run"
    best, best_traj = None, {}
    scored, skipped = [], {}
    for wx, seed in keys:
        res = {}
        for v, rows in ((a, ra), (b, rb)):
            problem, plan, world, engine = built[v]
            r = engine.simulate(problem, plan, world, wxs[wx], int(seed))
            diff = _same_kpis(r, rows.loc[(wx, seed)])
            if diff:
                return None, {}, f"stress refused: engine is not deterministic for variant {v!r}, year index {wx}, seed {seed} ({diff})"
            rep = validate_contract(r.traj, r.agents, land=world.land)
            if not rep.ok:
                return None, {}, f"stress refused: variant {v!r} year index {wx}, seed {seed} passed the ensemble but fails the contract on re-run"
            res[v] = r
        try:
            d = divergence(res[a].traj, res[a].agents, res[b].traj, res[b].agents)
        except ValueError as e:
            skipped[str(e)[:120]] = skipped.get(str(e)[:120], 0) + 1
            continue
        scored.append(d["max_divergence_m"])
        if best is None or d["max_divergence_m"] > best["max_divergence_m"]:
            best = {**d, "wx": int(wx), "seed": int(seed), "year": ens.runs.loc[(runs["wx"] == wx), "year"].iloc[0]}
            best_traj = {a: res[a].traj.copy(), b: res[b].traj.copy()}
    if best is None:
        return None, {}, f"stress: no scorable pair ({sum(skipped.values())} skipped: {sorted(skipped)})"
    block = {
        "selection": metric,
        "selected_on": "spatial divergence between the two validated trajectories, not the decision KPI and not the median",
        "compare": [a, b], "year": _year(best["year"]),
        "wx": best["wx"], "seed": best["seed"],
        "max_divergence_m": best["max_divergence_m"], "agent_id": best["agent_id"], "t_star_s": best["t_star_s"],
        "pos_a": best["pos_a"], "pos_b": best["pos_b"], "coverage": best["coverage"],
        "distribution": {"n_pairs": len(scored), "n_skipped": int(sum(skipped.values())), "skip_reasons": skipped,
                         "n_excluded_invalid": int(n_excluded),
                         "p50": float(np.percentile(scored, 50)), "p90": float(np.percentile(scored, 90)),
                         "max": float(max(scored))},
        "traj_sha256": {a: _sha(best_traj[a]), b: _sha(best_traj[b])},
        "note": "worst case of the pairs by spatial divergence, not the ensemble median; the statistical result is report:decision.effect",
    }
    return block, best_traj, None


def write_sidecars(block: dict, trajs: dict, out) -> list[str]:
    """Write the persisted pair's trajectories next to `out` (never into the repo tree unless `out` is there). -> file names."""
    out = Path(out)
    names = []
    for v, traj in trajs.items():
        p = out.with_name(f"{out.stem}.stress.{v}.csv")
        traj.to_csv(p, index=False)
        names.append(p.name)
    return names
