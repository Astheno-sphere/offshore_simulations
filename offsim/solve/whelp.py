"""WFPPP solver: Weekly Flight Program Planning Problem (Gribkovskaia & Slettemark 2025, Logistics 9(2):73, CC BY 3.0).

Registered as `whelp`, class {"WFPPP"}. One heliport, a set of offshore installations with weekly demand in half-flights,
helicopters with daily operating windows (10/12/14/16 h, fixed weekly cost). Output: a weekly flight program (which
helicopter flies which installation(s), on which weekday, from which 15-min slot) of minimum total cost = fixed window
costs + flight-hour cost of the flights. The program repeats every week of a stable-demand period.

What is implemented, with the paper's section/equation numbers (page numbers refer to extract.json, Logistics 9, 73)
  Sec 4.2  flight generation        direct flights heliport-i-heliport and split flights heliport-i-j-heliport for pairs with
                                    inter-installation flight time <= 15 min (p.14, p.25).
  Sec 4.3  flight-based model       eqs (1)-(12), `solve_full` (Pyomo + HiGHS); the same model as AMPL text in ampl/whelp.mod
                                    (`write_dat` writes its data). Small instances only (paper: <= 7 installations to optimality).
  Sec 5    decomposition            Stage 1 (eqs 13-19: resources + flights per day, no time slots) and Stage 2 (eqs 20-27: start
                                    slots per day, minimise the sum of start times) in a loop; `solve_decomposition`.

How the text was read (decisions that move numbers)
  * Duration: direct = 2 x flight time + 10 min deck stop; split = t(H,i) + t(i,j) + t(j,H) + 2 x 10 min (one deck stop per landing).
    Slots: n_f = ceil((duration + 60 min turnaround) / 15 min); the turnaround is INSIDE n_f (p.14, "included in the flight
    duration"). Parameter l = 4 turnaround slots.
  * COST: c_f = flight-hour cost x duration in hours, WITHOUT the turnaround and NOT rounded to slots. Evidence: (i) p.15
    "variable cost depends on the flight time ... distances ... and the number of landings"; (ii) Table 4 costs are not
    multiples of 140 x 0.25 h: Stavanger (26642 - 7000 - 6625)/140 = 92.98 h = 371.9 slots; Bergen (47582 - 7000 - 6813 -
    2 x 5968)/140 = 155.95 h = 623.8 slots; (iii) Florø total slots 191 = 86.82 % x 220 (Table 4) fits 19 flights of 6.05
    flight slots + 4 turnaround slots, and its cost 4012/140 = 28.66 h = 114.6 slots matches the same flights unrounded.
  * Opening hours (eq 3): p_it = 1 iff the DEPARTURE slot t lies in [open_start, open_end) of installation i (p.14: "start and
    end time slots for allowed flight departures from the heliport"); a flight to two installations needs both. The landing
    time is not constrained by the model.
  * One landing per installation and slot (eq 4/24): at most one flight to installation i STARTS in slot t, over all helicopters.
  * Non-overlap (eqs 7 + 9) is written as slot occupancy: every slot of [t, t + n_f) of a helicopter holds at most one flight.
    The two forms are equivalent (two intervals overlap iff one contains the other's start); the occupancy form is much smaller.
  * Window (eq 8): the flight WITHOUT its turnaround must fit the window (t + n_f - l <= s_w); the turnaround may run past
    the end (Stage 1 eq 18: sum n_f x <= s_w + l, and 220 = (40 + 4) x 5 slots in the paper's fleet bound, p.26).
  * Demand (eq 2/14): direct flight = 2 half-flights to its installation; a split flight = 1 half-flight to each of its two.
  * Spread (eq 10/17): counts of flights per installation differ by at most 1 between any two weekdays.
  * Shift (eq 11): in the full model as written (no idle slot between flights, window start e_w = 0); in the decomposition it is
    replaced by Stage 2's objective (min sum of start slots), as in the paper. `meta["shift_gap_days"]` counts days where the
    result still has an idle gap (forced by opening hours); the full model is infeasible for such days.
  * Fleet bound (p.18, p.26): H = min(helicopters available, ceil(slots of all demand on direct flights / (44 x 5)));
    the loop may add helicopters beyond it, up to the available number.
  * Equality in eq (21) (flights per day) instead of >= : extra flights only cost.

Iteration (Sec 5.1): Stage 2 infeasible on a day -> the helicopter whose next larger window is the cheapest step is upgraded
(its window is then fixed through eq 19); if none can be upgraded one helicopter with the smallest window is added.

Problem contract: `problem.extra["wfppp"]` (scenario `sim.wfppp`, passed on by offsim.pipeline.build_problem), nodes[0] = heliport,
nodes[1:] = installations in the order of `wfppp.installations`. See docs/ENGINES.md (whelp) for the field list.
Plan: routes {"H1-16h": [node, ...]} (installations in program order), objective = total cost (masked units), meta["program"] =
list of flights {heli, day, start_slot, installations, node_idx, duration_slots, fly_slots, cost, ...}.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from offsim.engines.base import Plan, Problem, Unsupported, register_solver

CLASSES = {"WFPPP"}
MODEL = Path(__file__).resolve().parent / "ampl" / "whelp.mod"
EARTH_R = 6_371_008.8
NM_M = 1852.0
EPS = 1e-9


# ------------------------------------------------------------------------------------------------- spec
def hav_m(lon1, lat1, lon2, lat2) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (lon1, lat1, lon2, lat2))
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_R * math.asin(min(1.0, math.sqrt(a)))


def hhmm(s) -> float:
    """'07:00' -> 7.0 (hours); numbers pass through as hours."""
    if isinstance(s, (int, float)):
        return float(s)
    h, m = str(s).strip().split(":")[:2]
    return int(h) + int(m) / 60.0


@dataclass(frozen=True)
class Inst:
    name: str
    lon: float
    lat: float
    demand_half: int          # weekly demand in half-flights (Tables A1-A3 values x 2)
    lo: int                   # first slot (from the day start) in which a departure to it is allowed
    hi: int                   # first slot in which it is not (departures t with lo <= t < hi)
    mobile: bool


@dataclass(frozen=True)
class Spec:
    heliport: tuple
    heliport_name: str
    inst: tuple               # of Inst
    windows: tuple            # ((hours, fixed cost), ...) ascending hours
    max_helis: int
    slot_min: int = 15
    speed_kn: float = 125.0
    deck_min: float = 10.0
    turnaround_min: float = 60.0
    split_min: float = 15.0
    hour_cost: float = 140.0
    days: int = 5
    day_start_h: float = 7.0

    @property
    def l(self) -> int:
        return int(round(self.turnaround_min / self.slot_min))

    def s_w(self, w: int) -> int:
        """Slots in operating window w (excluding the closing turnaround)."""
        return int(round(self.windows[w][0] * 60 / self.slot_min))

    @property
    def names(self):
        return [i.name for i in self.inst]


def parse_spec(problem: Problem) -> Spec:
    """Problem -> Spec. Everything the model needs, validated; Unsupported when the scenario asks for more than the paper's model."""
    if not set(problem.cls) <= CLASSES:
        raise Unsupported(f"whelp handles {sorted(CLASSES)}; problem needs {sorted(set(problem.cls))}")
    w = (problem.extra or {}).get("wfppp")
    if not w:
        raise Unsupported("WFPPP needs problem.extra['wfppp'] (scenario sim.wfppp, passed through offsim.pipeline.EXTRA_KEYS)")
    nodes = problem.nodes
    insts_raw = w.get("installations") or []
    if len(nodes) != len(insts_raw) + 1:
        raise Unsupported(f"nodes ({len(nodes)}) must be heliport + {len(insts_raw)} installations")
    slot = int(w.get("slot_min", 15))
    day_start = hhmm(w.get("day_start", "07:00"))
    inst = []
    for k, r in enumerate(insts_raw, 1):
        a, b = str(r["open"]).split("-")
        lo = (hhmm(a) - day_start) * 60 / slot
        hi = (hhmm(b) - day_start) * 60 / slot
        if abs(lo - round(lo)) > EPS or abs(hi - round(hi)) > EPS or lo < 0 or hi <= lo:
            raise Unsupported(f"installation {r['name']}: opening hours {r['open']} do not fall on {slot}-min slots after {day_start:g}:00")
        dh = float(r["demand_flights"]) * 2
        if abs(dh - round(dh)) > EPS:
            raise Unsupported(f"installation {r['name']}: demand {r['demand_flights']} flights is not a multiple of a half-flight")
        inst.append(Inst(str(r["name"]), float(nodes[k][0]), float(nodes[k][1]), int(round(dh)), int(round(lo)), int(round(hi)),
                         bool(r.get("mobile", False))))
    wins = []
    for r in w["windows"]:
        if abs(hhmm(r.get("start", w.get("day_start", "07:00"))) - day_start) > EPS:
            raise Unsupported("operating windows must start at the day start (paper: all at 07:00)")
        wins.append((float(r["hours"]), float(r["cost"])))
    wins.sort()
    turn = float(w.get("turnaround_min", 60))
    if abs(turn / slot - round(turn / slot)) > EPS:
        raise Unsupported("turnaround must be a whole number of slots")
    if any(abs(h * 60 / slot - round(h * 60 / slot)) > EPS for h, _ in wins):
        raise Unsupported("operating window durations must be whole numbers of slots")
    hp_name = (w.get("heliport_name") or "heliport")
    return Spec(heliport=(float(nodes[0][0]), float(nodes[0][1])), heliport_name=str(hp_name), inst=tuple(inst), windows=tuple(wins),
                max_helis=int(w.get("max_helicopters", 1)), slot_min=slot, speed_kn=float(w.get("speed_kn", 125)),
                deck_min=float(w.get("deck_min", 10)), turnaround_min=turn, split_min=float(w.get("split_threshold_min", 15)),
                hour_cost=float(w.get("flight_hour_cost", 140)), days=int(w.get("days", 5)), day_start_h=day_start)


# ------------------------------------------------------------------------------------------------- flights (Sec 4.2)
@dataclass(frozen=True)
class Flight:
    fid: int
    kind: str                 # "direct" | "split"
    inst: tuple               # indices into Spec.inst, in visiting order
    fly_min: float            # time in the air
    dur_min: float            # air time + deck stops (what the flight-hour cost is paid on)
    cost: float
    n: int                    # slots including the turnaround
    n_fly: int                # slots without the turnaround


def leg_minutes(spec: Spec):
    """(t_hi[i] minutes heliport->i, t_ij[i][j] minutes i->j) at the cruise speed, great circle."""
    kn_mps = spec.speed_kn * NM_M / 3600.0
    h = spec.heliport
    t_h = [hav_m(h[0], h[1], p.lon, p.lat) / kn_mps / 60.0 for p in spec.inst]
    n = len(spec.inst)
    t_ij = [[0.0] * n for _ in range(n)]
    for a in range(n):
        for b in range(n):
            if a != b:
                t_ij[a][b] = hav_m(spec.inst[a].lon, spec.inst[a].lat, spec.inst[b].lon, spec.inst[b].lat) / kn_mps / 60.0
    return t_h, t_ij


def _slots(spec: Spec, dur_min: float) -> tuple[int, int]:
    n_fly = int(math.ceil(dur_min / spec.slot_min - EPS))
    return n_fly + spec.l, n_fly


def generate_flights(spec: Spec) -> list[Flight]:
    """All direct flights, then split flights of every installation pair whose flight time is <= the threshold (p.14)."""
    t_h, t_ij = leg_minutes(spec)
    out = []
    for i in range(len(spec.inst)):
        fly = 2 * t_h[i]
        dur = fly + spec.deck_min
        n, nf = _slots(spec, dur)
        out.append(Flight(len(out), "direct", (i,), fly, dur, spec.hour_cost * dur / 60.0, n, nf))
    for i, j in itertools.combinations(range(len(spec.inst)), 2):
        if t_ij[i][j] <= spec.split_min + EPS:
            fly = t_h[i] + t_ij[i][j] + t_h[j]
            dur = fly + 2 * spec.deck_min
            n, nf = _slots(spec, dur)
            out.append(Flight(len(out), "split", (i, j), fly, dur, spec.hour_cost * dur / 60.0, n, nf))
    return out


def fleet_upper_bound(spec: Spec, flights) -> int:
    """p.18 / p.26: slots of the whole demand on direct flights / slots of the smallest window (+ turnaround) per week."""
    direct = {f.inst[0]: f for f in flights if f.kind == "direct"}
    need = sum(math.ceil(p.demand_half / 2) * direct[k].n for k, p in enumerate(spec.inst))
    per_heli = (spec.s_w(0) + spec.l) * spec.days
    return max(1, min(spec.max_helis, int(math.ceil(need / per_heli - EPS))))


def direct_only_slots(spec: Spec, flights) -> int:
    direct = {f.inst[0]: f for f in flights if f.kind == "direct"}
    return sum(math.ceil(p.demand_half / 2) * direct[k].n for k, p in enumerate(spec.inst))


# ------------------------------------------------------------------------------------------------- HiGHS through Pyomo
def _solve(m, limit: float, seed: int, gap: float = 0.0):
    """Solve a Pyomo model with HiGHS. Returns (status, bound) with status optimal | feasible | infeasible; raises when inconclusive."""
    import pyomo.environ as pyo

    opt = pyo.SolverFactory("appsi_highs")
    if not opt.available(exception_flag=False):
        raise Unsupported("HiGHS (appsi_highs) is not available in this environment")
    opt.config.time_limit = float(limit)
    opt.highs_options["mip_rel_gap"] = float(gap)
    opt.highs_options["mip_abs_gap"] = 1e-6
    opt.highs_options["random_seed"] = int(seed)
    opt.highs_options["output_flag"] = False
    res = opt.solve(m, load_solutions=False)
    tc = str(res.solver.termination_condition)
    if tc == "infeasible":
        return "infeasible", None
    if tc == "optimal":
        m.solutions.load_from(res)
        lb = res.problem.lower_bound
        return "optimal", None if lb is None or not np.isfinite(lb) else float(lb)
    if tc in ("maxTimeLimit", "maxIterations") and res.problem.upper_bound is not None and np.isfinite(res.problem.upper_bound):
        m.solutions.load_from(res)
        lb = res.problem.lower_bound
        return "feasible", None if lb is None or not np.isfinite(lb) else float(lb)
    raise RuntimeError(f"HiGHS inconclusive (termination {tc}) within {limit:g} s")


# ------------------------------------------------------------------------------------------------- Stage 1 (eqs 13-19)
def stage1(spec: Spec, flights, H: int, lock: dict | None, limit: float, seed: int, level: bool = True):
    """Resources + flights per day without time slots. lock {h: w}: eq (19), those helicopters keep that window.
    Returns None when infeasible, else dict(obj, bound, status, windows {h: w}, counts {(h, f, d): n}, per_day {d: {f: n}})."""
    import pyomo.environ as pyo

    lock = lock or {}
    W, F, D = range(len(spec.windows)), range(len(flights)), range(spec.days)
    I = range(len(spec.inst))
    l = spec.l
    smax = spec.s_w(len(spec.windows) - 1)
    m = pyo.ConcreteModel()
    m.y = pyo.Var([(h, w) for h in range(H) for w in W], domain=pyo.Binary)
    ub = {f: max(1, (smax + l) // flights[f].n) for f in F}
    m.x = pyo.Var([(h, f, d) for h in range(H) for f in F for d in D], domain=pyo.NonNegativeIntegers)
    for (h, f, d), var in m.x.items():
        var.setub(ub[f])
    cap = {h: sum((spec.s_w(w) + l) * m.y[h, w] for w in W) for h in range(H)}          # (s_w + l) y
    slots = {h: sum(spec.s_w(w) * m.y[h, w] for w in W) for h in range(H)}
    m.one = pyo.ConstraintList()                                                       # (16)
    m.fix = pyo.ConstraintList()                                                       # (19)
    for h in range(H):
        m.one.add(sum(m.y[h, w] for w in W) <= 1)
        if h in lock:
            m.fix.add(m.y[h, lock[h]] >= 1)
    m.sym = pyo.ConstraintList()                                                       # unlocked helicopters sorted by window
    free = [h for h in range(H) if h not in lock]
    for a, b in zip(free, free[1:]):
        m.sym.add(slots[a] >= slots[b])
    m.dem = pyo.ConstraintList()                                                       # (14)
    for i in I:
        m.dem.add(sum((2 if flights[f].kind == "direct" else 1) * m.x[h, f, d]
                      for f in F if i in flights[f].inst for h in range(H) for d in D) >= spec.inst[i].demand_half)
    m.cap = pyo.ConstraintList()                                                       # (15) + (18)
    for h in range(H):
        for d in D:
            m.cap.add(sum(flights[f].n * m.x[h, f, d] for f in F) <= cap[h])     # forces x = 0 for an unused helicopter
    m.spread = pyo.ConstraintList()                                                    # (17)
    cnt = {(i, d): sum(m.x[h, f, d] for f in F if i in flights[f].inst for h in range(H)) for i in I for d in D}
    for i in I:
        for d, e in itertools.combinations(D, 2):
            m.spread.add(cnt[i, d] - cnt[i, e] <= 1)
            m.spread.add(cnt[i, e] - cnt[i, d] <= 1)
    fixed = sum(spec.windows[w][1] * m.y[h, w] for h in range(H) for w in W)
    var = sum(flights[f].cost * m.x[h, f, d] for (h, f, d) in m.x)
    m.obj = pyo.Objective(expr=fixed + var, sense=pyo.minimize)
    status, lb = _solve(m, limit, seed)
    if status == "infeasible":
        return None
    best = float(pyo.value(m.obj))
    if level and status == "optimal":
        # tie-break among cost-optimal solutions: level the load over the weekdays (the paper's own policy, p.10: flights per
        # day "levelled over the week"), which makes Stage 2 feasible more often. Cost is held at the optimum.
        m.obj.deactivate()
        m.cut = pyo.Constraint(expr=fixed + var <= best + 1e-4)
        m.peak = pyo.Var(domain=pyo.NonNegativeReals)
        m.lvl = pyo.ConstraintList()
        for d in D:
            m.lvl.add(sum(flights[f].n * m.x[h, f, d] for h in range(H) for f in F) <= m.peak)
        m.obj2 = pyo.Objective(expr=m.peak, sense=pyo.minimize)
        try:
            st2, _ = _solve(m, limit, seed)
        except RuntimeError:
            st2 = "infeasible"
        if st2 == "infeasible":                                   # numerical corner: redo the plain solve
            m.cut.deactivate()
            m.obj2.deactivate()
            m.obj.activate()
            status, lb = _solve(m, limit, seed)
    win = {}
    for h in range(H):
        for w in W:
            if pyo.value(m.y[h, w]) > 0.5:
                win[h] = w
    counts = {k: int(round(pyo.value(v))) for k, v in m.x.items() if pyo.value(v) > 0.5}
    per_day = {d: {} for d in D}
    for (h, f, d), n in counts.items():
        per_day[d][f] = per_day[d].get(f, 0) + n
    return {"obj": best, "bound": lb, "status": status, "windows": win, "counts": counts, "per_day": per_day}


# ------------------------------------------------------------------------------------------------- Stage 2 (eqs 20-27)
def stage2_day(spec: Spec, flights, day_counts: dict, windows: dict, limit: float, seed: int):
    """Start slots for one day. windows {h: w}; day_counts {f: g_f}. Returns None when infeasible, else
    dict(status, starts [(h, f, t)], obj)."""
    import pyomo.environ as pyo

    l = spec.l
    fl = sorted(day_counts)
    if not fl:
        return {"status": "optimal", "starts": [], "obj": 0.0}
    hs = sorted(windows)
    idx = []
    for h in hs:
        s = spec.s_w(windows[h])
        for f in fl:
            ff = flights[f]
            lo = max(spec.inst[i].lo for i in ff.inst)
            hi = min(spec.inst[i].hi for i in ff.inst)
            for t in range(lo, min(hi, s - ff.n_fly + 1)):
                idx.append((h, f, t))
    cover = {f: [k for k in idx if k[1] == f] for f in fl}
    if any(len(cover[f]) < day_counts[f] for f in fl):
        return None                                                                    # not enough placeable starts
    m = pyo.ConcreteModel()
    m.x = pyo.Var(idx, domain=pyo.Binary)
    m.cov = pyo.ConstraintList()                                                       # (21)
    for f in fl:
        m.cov.add(sum(m.x[k] for k in cover[f]) == day_counts[f])
    occ, land = {}, {}
    for (h, f, t) in idx:
        for s in range(t, t + flights[f].n):                                           # (25) + (27)
            occ.setdefault((h, s), []).append((h, f, t))
        for i in flights[f].inst:                                                      # (24)
            land.setdefault((i, t), []).append((h, f, t))
    m.occ = pyo.ConstraintList()
    for key, ks in occ.items():
        if len(ks) > 1:
            m.occ.add(sum(m.x[k] for k in ks) <= 1)
    m.land = pyo.ConstraintList()
    for key, ks in land.items():
        if len(ks) > 1:
            m.land.add(sum(m.x[k] for k in ks) <= 1)
    m.obj = pyo.Objective(expr=sum(t * m.x[(h, f, t)] for (h, f, t) in idx), sense=pyo.minimize)   # (20)
    status, _ = _solve(m, limit, seed)
    if status == "infeasible":
        return None
    starts = [k for k in idx if pyo.value(m.x[k]) > 0.5]
    return {"status": status, "starts": starts, "obj": float(pyo.value(m.obj))}


# ------------------------------------------------------------------------------------------------- decomposition (Sec 5)
def solve_decomposition(spec: Spec, flights, limit: float = 120.0, seed: int = 1, max_iter: int = 12):
    """Stage 1 -> Stage 2 per day -> upgrade/add a helicopter on infeasibility, until every day is placed."""
    H = fleet_upper_bound(spec, flights)
    lock: dict = {}
    log, t0 = [], time.perf_counter()
    first_bound = None
    for it in range(1, max_iter + 1):
        Hn = min(spec.max_helis, max(H, len(lock)))
        s1 = None
        while s1 is None:
            s1 = stage1(spec, flights, Hn, lock, limit, seed)
            if s1 is None:
                if Hn >= spec.max_helis:
                    break
                Hn += 1
        if s1 is None:
            if not lock:
                raise RuntimeError("WFPPP infeasible with the available helicopters (Stage 1)")
            # locked resources cannot even carry the flights: treat like a failed day and grow the fleet
            s1 = {"windows": dict(lock), "per_day": {}, "obj": float("nan"), "status": "infeasible", "counts": {}}
            bad_day = -1
            starts = {}
        else:
            if first_bound is None and s1["status"] == "optimal":
                first_bound = s1["obj"]
            starts, bad_day = {}, None
            for d in range(spec.days):
                s2 = stage2_day(spec, flights, s1["per_day"][d], s1["windows"], limit, seed)
                if s2 is None:
                    bad_day = d
                    break
                starts[d] = s2
        log.append({"iteration": it, "stage1_cost": s1["obj"], "stage1_status": s1["status"],
                    "windows_h": {h: spec.windows[w][0] for h, w in s1["windows"].items()},
                    "infeasible_day": bad_day, "wall_s": round(time.perf_counter() - t0, 3)})
        if bad_day is None:
            return {"stage1": s1, "starts": starts, "iterations": log, "bound": first_bound,
                    "status": "optimal" if all(s1["status"] == "optimal" and s["status"] == "optimal" for s in starts.values()) else "time_limit"}
        # revise resources
        win = dict(s1["windows"])
        best = None
        for h, w in win.items():
            if w + 1 < len(spec.windows):
                step = spec.windows[w + 1][1] - spec.windows[w][1]
                if best is None or step < best[0]:
                    best = (step, h)
        if best is not None:
            h = best[1]
            win[h] += 1
        else:
            if len(win) >= spec.max_helis:
                raise RuntimeError("WFPPP: no feasible program with the available helicopters and operating windows")
            win[max(win, default=-1) + 1] = 0
        lock = win
        H = max(H, len(lock))
    raise RuntimeError(f"WFPPP decomposition did not converge in {max_iter} iterations")


# ------------------------------------------------------------------------------------------------- full flight-based model (Sec 4.3)
def solve_full(spec: Spec, flights, limit: float = 600.0, seed: int = 1, H: int | None = None):
    """Eqs (1)-(12) as one MIP (Pyomo). Flight shift (11) included. Intended for small instances."""
    import pyomo.environ as pyo

    H = H or fleet_upper_bound(spec, flights)
    W, F, D = range(len(spec.windows)), range(len(flights)), range(spec.days)
    l = spec.l
    I = range(len(spec.inst))
    idx = []
    for h in range(H):
        for w in W:
            s = spec.s_w(w)
            for f in F:
                ff = flights[f]
                lo = max(spec.inst[i].lo for i in ff.inst)
                hi = min(spec.inst[i].hi for i in ff.inst)
                for d in D:
                    for t in range(lo, min(hi, s - ff.n_fly + 1)):
                        idx.append((h, w, f, d, t))
    m = pyo.ConcreteModel()
    m.x = pyo.Var(idx, domain=pyo.Binary)
    m.y = pyo.Var([(h, w) for h in range(H) for w in W], domain=pyo.Binary)
    by_hd, by_hwd, by_idt, by_hds, by_id = {}, {}, {}, {}, {}
    for k in idx:
        h, w, f, d, t = k
        by_hd.setdefault((h, d), []).append(k)
        by_hwd.setdefault((h, w, d), []).append(k)
        for i in flights[f].inst:
            by_idt.setdefault((i, d, t), []).append(k)
            by_id.setdefault((i, d), []).append(k)
        for s in range(t, t + flights[f].n):
            by_hds.setdefault((h, d, s), []).append(k)
    m.one = pyo.ConstraintList()
    for h in range(H):
        m.one.add(sum(m.y[h, w] for w in W) <= 1)                                      # (6)
    for k in idx:
        m.one.add(m.x[k] <= m.y[k[0], k[1]])                                           # (5)
    m.dem = pyo.ConstraintList()                                                       # (2)
    for i in I:
        terms = [(2 if flights[k[2]].kind == "direct" else 1) * m.x[k] for d in D for k in by_id.get((i, d), [])]
        m.dem.add(sum(terms) >= spec.inst[i].demand_half)
    m.land = pyo.ConstraintList()                                                      # (4)
    for key, ks in by_idt.items():
        if len(ks) > 1:
            m.land.add(sum(m.x[k] for k in ks) <= 1)
    m.occ = pyo.ConstraintList()                                                       # (7) + (9)
    for key, ks in by_hds.items():
        if len(ks) > 1:
            m.occ.add(sum(m.x[k] for k in ks) <= 1)
    m.spread = pyo.ConstraintList()                                                    # (10)
    for i in I:
        for d, e in itertools.combinations(D, 2):
            a = sum(m.x[k] for k in by_id.get((i, d), []))
            b = sum(m.x[k] for k in by_id.get((i, e), []))
            m.spread.add(a - b <= 1)
            m.spread.add(b - a <= 1)
    m.ld = pyo.Var([(h, d) for h in range(H) for d in D], domain=pyo.NonNegativeReals)   # slots used by h on day d
    m.shift = pyo.ConstraintList()                                                     # (11) with e_w = 0
    for (h, d), ks in by_hd.items():
        m.shift.add(m.ld[h, d] == sum(flights[k[2]].n * m.x[k] for k in ks))
    for k in idx:
        h, w, f, d, t = k
        m.shift.add((t + flights[f].n) * m.x[k] <= m.ld[h, d])
    for h in range(H):
        for d in D:
            if (h, d) not in by_hd:
                m.ld[h, d].fix(0.0)
    m.sym = pyo.ConstraintList()
    for h in range(H - 1):
        m.sym.add(sum(spec.s_w(w) * m.y[h, w] for w in W) >= sum(spec.s_w(w) * m.y[h + 1, w] for w in W))
    m.obj = pyo.Objective(expr=sum(spec.windows[w][1] * m.y[h, w] for h in range(H) for w in W)
                          + sum(flights[k[2]].cost * m.x[k] for k in idx), sense=pyo.minimize)
    status, lb = _solve(m, limit, seed)
    if status == "infeasible":
        raise RuntimeError("flight-based model infeasible with the available helicopters")
    win = {h: w for h in range(H) for w in W if pyo.value(m.y[h, w]) > 0.5}
    starts = {d: [] for d in D}
    for k in idx:
        if pyo.value(m.x[k]) > 0.5:
            starts[k[3]].append((k[0], k[2], k[4]))
    return {"windows": win, "starts": starts, "obj": float(pyo.value(m.obj)), "bound": lb, "status": status}


# ------------------------------------------------------------------------------------------------- program, plan, checks
def label_helis(spec: Spec, windows: dict) -> dict:
    """{h: 'H1-16h'}: helicopters numbered by window size (largest first), stable in h."""
    order = sorted(windows, key=lambda h: (-windows[h], h))
    return {h: f"H{k + 1}-{spec.windows[windows[h]][0]:g}h" for k, h in enumerate(order)}


def build_program(spec: Spec, flights, windows: dict, starts: dict) -> list[dict]:
    lab = label_helis(spec, windows)
    prog = []
    for d in sorted(starts):
        for (h, f, t) in starts[d]:
            ff = flights[f]
            prog.append({"heli": lab[h], "day": int(d), "start_slot": int(t), "fid": ff.fid, "kind": ff.kind,
                         "installations": [spec.inst[i].name for i in ff.inst], "node_idx": [i + 1 for i in ff.inst],
                         "duration_slots": ff.n, "fly_slots": ff.n_fly, "duration_min": ff.dur_min, "fly_min": ff.fly_min,
                         "cost": ff.cost, "window_h": spec.windows[windows[h]][0]})
    prog.sort(key=lambda r: (r["day"], r["heli"], r["start_slot"]))
    return prog


def utilisation(spec: Spec, program, windows: dict) -> float:
    """Paper's Table 4 measure: slots occupied by flights (turnaround included) / slots of the windows (+ turnaround), per week.
    Reverse-engineered from Florø (191 / 220 = 86.82 %) and Bergen (1036 / 1080 = 95.93 %)."""
    avail = sum((spec.s_w(w) + spec.l) * spec.days for w in windows.values())
    return sum(r["duration_slots"] for r in program) / avail if avail else 0.0


def make_plan(spec: Spec, flights, windows: dict, starts: dict, bound, status: str, meta: dict) -> Plan:
    prog = build_program(spec, flights, windows, starts)
    fixed = sum(spec.windows[w][1] for w in windows.values())
    var = sum(r["cost"] for r in prog)
    routes = {lab: [] for lab in label_helis(spec, windows).values()}
    for r in prog:
        routes[r["heli"]].extend(r["node_idx"])
    gaps = 0
    for (h, d), grp in itertools.groupby(sorted(((r["heli"], r["day"], r["start_slot"], r["duration_slots"]) for r in prog)),
                                         key=lambda z: (z[0], z[1])):
        t = 0
        for _, _, s, n in grp:
            gaps += s > t
            t = max(t, s + n)
    meta = dict(meta, program=prog, fixed_cost=fixed, variable_cost=var, helicopters=[
        {"label": lab, "hours": spec.windows[windows[h]][0], "fixed_cost": spec.windows[windows[h]][1]}
        for h, lab in label_helis(spec, windows).items()], utilisation=utilisation(spec, prog, windows),
        shift_gap_days=gaps, flights_total=len(prog), slots_total=sum(r["duration_slots"] for r in prog),
        direct_only_slots=direct_only_slots(spec, flights), n_flight_options=len(flights))
    return Plan(routes=routes, objective=fixed + var, objective_unit="masked cost units", solver="whelp", bound=bound, status=status, meta=meta)


def check_program(problem: Problem, plan: Plan) -> tuple[bool, dict]:
    """Gate 1: the program re-checked outside the solver, from the flight records and the geometry only.
    Demand, windows, opening hours, non-overlap with turnaround, one landing per installation and slot, flight spread,
    fleet size, cost. Idle gaps (flight shift) are reported, not failed (the decomposition minimises them)."""
    spec = parse_spec(problem)
    prog = plan.meta.get("program")
    if prog is None:
        return False, {"error": "plan has no meta['program']"}
    flights = {f.fid: f for f in generate_flights(spec)}
    wcost = {h: c for h, c in spec.windows}
    errs, win_h = [], {}
    served = [0] * len(spec.inst)
    per_day = {(i, d): 0 for i in range(len(spec.inst)) for d in range(spec.days)}
    starts, occ = {}, {}
    cost = 0.0
    for r in prog:
        ff = flights.get(r["fid"])
        if ff is None or [spec.inst[i].name for i in ff.inst] != r["installations"]:
            errs.append(f"unknown flight {r['fid']}")
            continue
        if win_h.setdefault(r["heli"], r["window_h"]) != r["window_h"]:
            errs.append(f"{r['heli']}: two windows")
        if r["window_h"] not in wcost:
            errs.append(f"{r['heli']}: window {r['window_h']} h is not an option")
            continue
        d, t = r["day"], r["start_slot"]
        if not 0 <= d < spec.days:
            errs.append("day outside the week")
            continue
        if t < 0 or t + ff.n_fly > int(round(r["window_h"] * 60 / spec.slot_min)):
            errs.append(f"{r['heli']} d{d} t{t}: flight leaves the window")
        for i in ff.inst:
            p = spec.inst[i]
            if not p.lo <= t < p.hi:
                errs.append(f"{p.name} d{d} t{t}: departure outside opening hours")
            served[i] += 2 if ff.kind == "direct" else 1
            per_day[i, d] += 1
            starts[i, d, t] = starts.get((i, d, t), 0) + 1
        for u in range(t, t + ff.n):
            occ[r["heli"], d, u] = occ.get((r["heli"], d, u), 0) + 1
        cost += ff.cost
    errs += [f"{spec.inst[k[0]].name} d{k[1]} t{k[2]}: {n} flights start in one slot" for k, n in starts.items() if n > 1]
    errs += [f"{k[0]} d{k[1]} slot {k[2]}: {n} flights" for k, n in occ.items() if n > 1]
    if len(win_h) > spec.max_helis:
        errs.append(f"{len(win_h)} helicopters > {spec.max_helis} available")
    short = [spec.inst[i].name for i in range(len(spec.inst)) if served[i] < spec.inst[i].demand_half]
    spread = [spec.inst[i].name for i in range(len(spec.inst))
              if max(per_day[i, d] for d in range(spec.days)) - min(per_day[i, d] for d in range(spec.days)) > 1]
    fixed = sum(wcost.get(h, 0.0) for h in win_h.values())
    ok = not errs and not short and not spread and abs(fixed + cost - plan.objective) <= 1e-6 * max(1.0, plan.objective)
    detail = {"flights": len(prog), "helicopters": dict(win_h), "demand_short": short, "spread_violations": spread,
              "errors": sorted(set(errs))[:10], "objective": plan.objective, "recomputed": fixed + cost,
              "shift_gap_days": plan.meta.get("shift_gap_days")}
    return ok, detail


# ------------------------------------------------------------------------------------------------- solver
@register_solver("whelp")
def _factory():
    return WhelpSolver()


class WhelpSolver:
    name = "whelp"
    classes = CLASSES

    def solve(self, problem: Problem, seconds: float = 2.0, seed: int = 1) -> Plan:
        """Decomposition by default; `wfppp.method: full` runs the flight-based model. `wfppp.time_limit_s` (default 120) caps each
        MIP; `seconds` raises it when larger (the pipeline default of 2 s would cut the MIPs short)."""
        spec = parse_spec(problem)
        w = problem.extra["wfppp"]
        limit = max(float(seconds), float(w.get("time_limit_s", 120)))
        method = str(w.get("method", "decomposition"))
        flights = generate_flights(spec)
        t0 = time.perf_counter()
        if method == "full":
            r = solve_full(spec, flights, limit=limit, seed=seed)
            starts = {d: r["starts"].get(d, []) for d in range(spec.days)}
            plan = make_plan(spec, flights, r["windows"], starts, r["bound"], "optimal" if r["status"] == "optimal" else "time_limit",
                             {"method": "full", "seed": seed})
        elif method == "decomposition":
            r = solve_decomposition(spec, flights, limit=limit, seed=seed)
            starts = {d: s["starts"] for d, s in r["starts"].items()}
            plan = make_plan(spec, flights, r["stage1"]["windows"], starts, r["bound"], r["status"],
                             {"method": "decomposition", "iterations": r["iterations"], "seed": seed})
        else:
            raise Unsupported(f"unknown wfppp.method {method!r} (decomposition | full)")
        plan.meta["wall_s"] = round(time.perf_counter() - t0, 3)
        plan.meta["time_limit_s"] = limit
        return plan


# ------------------------------------------------------------------------------------------------- instances (Tables 2-4, A1-A3)
PAPER_ID = "irinagribkovskaia-2025-tactical-helicopter"
PAPER_DIR = Path(__file__).resolve().parents[1] / "papers" / PAPER_ID
INSTANCES = PAPER_DIR / "instances.yaml"

# Tables A1-A3 (p.38-39): weekly flight demand and opening hours (departure window from the heliport), M = mobile installation.
TABLES = {
    "floro": {"table": "A1", "page": 38, "installations": [("F1", 6.5, "07:00-18:00"), ("F2", 4.5, "07:00-18:00"),
                                                           ("F3", 4, "07:00-18:00"), ("F4", 4, "07:00-22:00")]},
    "stavanger": {"table": "A2", "page": 39, "installations": [
        ("S1", 4, "07:00-22:00"), ("S2", 1.5, "07:00-18:00"), ("S3", 4, "07:00-22:00"), ("S4", 4, "07:00-22:00"),
        ("S5", 4, "07:00-22:00"), ("S6", 2.5, "07:00-18:00"), ("S7", 4.5, "07:00-18:00"), ("S8", 1.5, "07:00-18:00"),
        ("S9", 13, "07:00-18:00"), ("S10", 1.5, "07:00-18:00"), ("S11", 3.5, "07:00-18:00"), ("S12", 4.5, "07:00-18:00")]},
    "bergen": {"table": "A3", "page": 39, "installations": [
        ("B1", 4, "07:00-18:00"), ("B2", 5, "07:00-18:00"), ("B3", 3, "07:00-22:00"), ("B4", 6.5, "07:00-18:00"),
        ("B5", 5, "07:00-18:00"), ("B6", 6.5, "07:00-18:00"), ("B7", 3, "07:00-22:00"), ("B8", 4, "07:00-18:00"),
        ("B9", 4, "07:00-18:00"), ("B10", 4.5, "07:00-18:00"), ("B11", 10, "07:00-18:00"), ("B12", 2, "07:00-18:00"),
        ("B13", 3.5, "07:00-18:00"), ("B14", 7, "07:00-18:00"), ("B15", 6.5, "07:00-18:00"), ("B16", 6.5, "07:00-18:00"),
        ("B17", 3, "07:00-18:00"), ("B18", 3.5, "07:00-18:00"), ("B19", 2.5, "07:00-18:00"), ("B20", 3, "07:00-18:00")]},
}
# Table 2 (p.26) helicopters available and window options; Table 4 (p.29) optimal result; heliport positions are approximate
# airport reference points (assumption, unverified).
HELIPORTS = {"floro": ("Florø", 5.0247, 61.5836), "stavanger": ("Stavanger", 5.6378, 58.8767), "bergen": ("Bergen", 5.2181, 60.2934)}
MAX_HELIS = {"floro": 1, "stavanger": 3, "bergen": 5}
WINDOW_OPTIONS = {"floro": (10, 12, 16), "stavanger": (10, 12, 14, 16), "bergen": (10, 12, 14, 16)}
WINDOW_COST = {10: 5968, 12: 6625, 14: 6813, 16: 7000}                                  # Table 3 (p.26)
PAPER_RESULT = {"floro": {"cost": 9980, "windows": [10], "utilisation": 0.8682, "slots": 191},
                "stavanger": {"cost": 26642, "windows": [16, 12], "utilisation": 0.8682},
                "bergen": {"cost": 47582, "windows": [16, 14, 10, 10], "utilisation": 0.9593, "slots": 1036}}
# Clusters of installations flying close enough (<= 15 min) for split flights; the paper masks the positions (assumption).
CLUSTERS = {
    "floro": [["F1", "F2"], ["F3"], ["F4"]],
    "stavanger": [["S2", "S8"], ["S6", "S7", "S12"], ["S10", "S11"], ["S1"], ["S3"], ["S4"], ["S5"], ["S9"]],
    "bergen": [["B4", "B6"], ["B15", "B16"], ["B10", "B13"], ["B18", "B19"], ["B1", "B8"], ["B2", "B5"], ["B3"], ["B7"],
               ["B9"], ["B11"], ["B12"], ["B14"], ["B17"], ["B20"]],
}
LAYOUT_PARAMS = {  # mean / half-spread of the cluster radius (nm) before calibration, bearing sector (deg), RNG seed
    "floro": {"r_mean": 80.0, "r_half": 18.0, "sector": (235.0, 315.0), "seed": 11},
    "stavanger": {"r_mean": 100.0, "r_half": 12.0, "sector": (225.0, 335.0), "seed": 12},
    "bergen": {"r_mean": 92.0, "r_half": 20.0, "sector": (215.0, 345.0), "seed": 13},
}


def destination(lon, lat, bearing_deg, dist_nm):
    """Great-circle destination point (lon, lat) from a start, a true bearing and a distance in nautical miles."""
    d = dist_nm * NM_M / EARTH_R
    b, la, lo = math.radians(bearing_deg), math.radians(lat), math.radians(lon)
    la2 = math.asin(math.sin(la) * math.cos(d) + math.cos(la) * math.sin(d) * math.cos(b))
    lo2 = lo + math.atan2(math.sin(b) * math.sin(d) * math.cos(la), math.cos(d) - math.sin(la) * math.sin(la2))
    return math.degrees(lo2), math.degrees(la2)


def design_layout(name: str) -> list[dict]:
    """Assumed base layout of an instance: one anchor per cluster (bearing, radius from the heliport) and the other members at
    8-14 nm from the anchor (so every pair of a cluster is <= 28 nm = 13.4 min apart and may fly split). Deterministic in
    LAYOUT_PARAMS. The radii are what `calibrate` scales."""
    prm = LAYOUT_PARAMS[name]
    rng = np.random.default_rng(prm["seed"])
    cl = CLUSTERS[name]
    k = len(cl)
    lo, hi = prm["sector"]
    brg = lo + (np.arange(k) + rng.uniform(0.15, 0.85, k)) * (hi - lo) / k
    brg = rng.permutation(brg)
    rad = prm["r_mean"] + prm["r_half"] * rng.uniform(-1, 1, k)
    out = []
    for c, (members, b, r) in enumerate(zip(cl, brg, rad)):
        for m_i, mem in enumerate(members):
            if m_i == 0:
                out.append({"name": mem, "anchor": None, "bearing_deg": round(float(b), 3), "radius_nm": round(float(r), 3)})
            else:
                ang, dist = rng.uniform(0, 2 * math.pi), rng.uniform(8, 14)
                out.append({"name": mem, "anchor": members[0], "offset_nm": [round(dist * math.cos(ang), 3), round(dist * math.sin(ang), 3)]})
    order = [n for n, *_ in TABLES[name]["installations"]]
    return sorted(out, key=lambda r: order.index(r["name"]))


def layout_positions(heliport, layout, scale: float = 1.0) -> dict:
    """{name: (lon, lat)} from a base layout with cluster radii x scale; offsets (east, north in nm) are not scaled."""
    pos = {}
    for r in layout:
        if r.get("anchor") is None:
            pos[r["name"]] = destination(heliport[0], heliport[1], r["bearing_deg"], r["radius_nm"] * scale)
    for r in layout:
        if r.get("anchor") is not None:
            lon0, lat0 = pos[r["anchor"]]
            dx, dy = r["offset_nm"]
            pos[r["name"]] = (lon0 + dx / 60.0 / math.cos(math.radians(lat0)), lat0 + dy / 60.0)
    return pos


def _wfppp_block(name: str, common: dict, inst_rows: list[dict]) -> dict:
    """The sim.wfppp block (sourced leaves) of an instance."""
    tab = TABLES[name]
    src_t = f"p.{tab['page']} Table {tab['table']}"
    wins = [{"hours": {"value": h, "src": f"p.26 (options {WINDOW_OPTIONS[name]})"}, "cost": {"value": WINDOW_COST[h], "src": "p.26 Table 3"}}
            for h in WINDOW_OPTIONS[name]]
    rows = []
    for (n, dem, hrs), pos in zip(tab["installations"], inst_rows):
        rows.append({"name": n, "demand_flights": {"value": dem, "src": src_t}, "open": {"value": hrs, "src": src_t},
                     "mobile": hrs.endswith("22:00")})
    return {**common, "heliport_name": HELIPORTS[name][0], "max_helicopters": {"value": MAX_HELIS[name], "src": "p.26 Table 2"},
            "windows": wins, "installations": rows}


COMMON = {
    "slot_min": {"value": 15, "src": "p.25 Sec 6.2.1"},
    "speed_kn": {"value": 125, "src": "p.25 Sec 6.2.1 (S-92 average speed)"},
    "deck_min": {"value": 10, "src": "p.25 Sec 6.2.1 (about ten minutes per deck stop)"},
    "turnaround_min": {"value": 60, "src": "p.25 Sec 6.2.1 (one hour added to each flight)"},
    "split_threshold_min": {"value": 15, "src": "p.25 Sec 6.2.1"},
    "flight_hour_cost": {"value": 140, "src": "p.25 Sec 6.2.1 (masked units)"},
    "days": {"value": 5, "src": "p.12 Sec 3 (Monday to Friday)"},
    "day_start": {"value": "07:00", "src": "p.26 (windows start at 07:00)"},
}


def build_scenario(name: str, data: dict | None = None) -> dict:
    """scenario.yaml content for an instance from instances.yaml (positions + calibration record)."""
    data = data or load_instances()
    inst = data["instances"][name]
    pos = inst["positions"]
    hp = inst["heliport"]
    stops = [{"name": n, "lon": round(pos[n][0], 5), "lat": round(pos[n][1], 5), "assumption": True} for n, *_ in TABLES[name]["installations"]]
    rows = _wfppp_block(name, COMMON, stops)
    res = PAPER_RESULT[name]
    rep = {"plan_cost": {"value": res["cost"], "src": "p.29 Table 4", "rel_tol": 0.05},
           "helicopters": {"value": len(res["windows"]), "src": "p.29 Table 4", "rel_tol": 0.0},
           "window_hours": {"value": float(sum(res["windows"])), "src": "p.29 Table 4", "rel_tol": 0.0}}
    return {
        "paper": {"id": PAPER_ID, "title": "Tactical Helicopter Transportation Planning for Offshore Personnel on the Norwegian Continental Shelf",
                  "authors": ["Irina Gribkovskaia", "Gaute Oiestad Slettemark"], "year": 2025, "doi": "10.3390/logistics9020073",
                  "licence": "CC BY 3.0"},
        "param": {"instance": name, "choices": ["floro", "stavanger", "bergen"],
                  "how": "python -m offsim.solve.whelp --write-scenario <name> (instances.yaml is the single source)"},
        "problem": {"class": ["WFPPP"], "objective": {"value": "min fixed window costs + flight-hour costs of the weekly program",
                                                         "src": "p.15 eq (1)"}},
        "solver": "whelp",
        "engine": "air",
        "world": "none",
        "fleet": [{"cls": "helicopter", "count": {"value": MAX_HELIS[name], "src": "p.26 Table 2 (helicopters available)"},
                   "speed_mps": {"value": round(125 * NM_M / 3600, 3), "src": "p.25 Sec 6.2.1 (125 kn)"}, "domain": "air"}],
        "instance": {"source": "paper Appendix A + assumed positions",
                     "base": {"name": hp["name"], "lon": hp["lon"], "lat": hp["lat"], "assumption": True,
                              "note": "approximate airport reference point, unverified"},
                     "stops": stops},
        "sim": {"wfppp": rows,
                "limits": {"wind_mps": {"value": 25.0, "assumption": True,
                                        "note": "placeholder; source from the helicopter flight manual / CAP 437 / operator minima"},
                           "hs_m": {"value": 6.0, "assumption": True,
                                    "note": "mobile installations only; placeholder, source from CAP 437 helideck motion limits"}}},
        "reported": rep,
    }


def load_instances(path=None) -> dict:
    import yaml
    return yaml.safe_load(Path(path or INSTANCES).read_text())


def unwrap(x):
    """{value, src|assumption} leaves -> value, recursively (same rule as offsim.pipeline.unwrap)."""
    if isinstance(x, dict):
        if "value" in x:
            return unwrap(x["value"])
        return {k: unwrap(v) for k, v in x.items()}
    if isinstance(x, list):
        return [unwrap(v) for v in x]
    return x


def problem_for(name: str, scale: float | None = None, data: dict | None = None, positions: dict | None = None) -> Problem:
    """Problem of an instance without the pipeline. `scale` re-places the installations from the stored base layout (calibration);
    default: the stored calibrated positions."""
    data = data or load_instances()
    inst = data["instances"][name]
    hp = inst["heliport"]
    if positions is None:
        positions = layout_positions((hp["lon"], hp["lat"]), inst["layout"], scale) if scale is not None else inst["positions"]
    order = [n for n, *_ in TABLES[name]["installations"]]
    sc = build_scenario(name, {"instances": {name: {**inst, "positions": {n: positions[n] for n in order}}}})
    wf = unwrap(sc["sim"]["wfppp"])
    nodes = [(hp["lon"], hp["lat"])] + [(positions[n][0], positions[n][1]) for n in order]
    fleet = [unwrap(f) for f in sc["fleet"]]
    return Problem(cls={"WFPPP"}, nodes=nodes, dist_m=None, demand={}, fleet=fleet,
                   extra={"wfppp": wf, "limits": unwrap(sc["sim"]["limits"])})


def quay_stats(problem: Problem) -> dict:
    """Radii (nm) and direct-flight hours incl. one deck stop of every installation: check against p.25 (50-120 nm, 1-2.5 h)."""
    spec = parse_spec(problem)
    nm = [hav_m(*spec.heliport, p.lon, p.lat) / NM_M for p in spec.inst]
    hrs = [(2 * r / spec.speed_kn * 60 + spec.deck_min) / 60 for r in nm]
    return {"radius_nm": [round(r, 1) for r in nm], "direct_h": [round(h, 2) for h in hrs]}


# ------------------------------------------------------------------------------------------------- calibration
def evaluate_scale(name: str, scale: float, data: dict, limit: float = 120.0, seed: int = 1):
    """Optimal program of the instance with the cluster radii x scale: (Plan, Problem)."""
    prob = problem_for(name, scale=scale, data=data)
    return WhelpSolver().solve(prob, seconds=limit, seed=seed), prob


def calibrate(name: str, data: dict, lo: float = 0.75, hi: float = 1.25, grid: int = 11, refine: int = 7,
              limit: float = 120.0, log=None) -> dict:
    """Choose the radial scale s that makes the reproduced optimal cost approach Table 4.

    The paper masks the installation positions (50-120 nm, 1-2.5 h). `design_layout` gives an assumed layout; every cluster
    radius is multiplied by s (offsets inside clusters stay). cost(s) is a step function (slots round up, windows jump), so:
    scan a grid, then repeatedly halve the step around the best point. score = |cost - paper| / paper, +1 when the
    fleet (window set) differs from Table 4. Returns the record stored in instances.yaml."""
    target = PAPER_RESULT[name]["cost"]
    fleet_t = sorted(PAPER_RESULT[name]["windows"], reverse=True)
    cache = {}

    def score(s):
        s = round(float(s), 5)
        if s not in cache:
            try:
                plan, _ = evaluate_scale(name, s, data, limit)
                fleet = sorted((h["hours"] for h in plan.meta["helicopters"]), reverse=True)
                cache[s] = (abs(plan.objective - target) / target + (0.0 if fleet == [float(x) for x in fleet_t] else 1.0),
                            plan.objective, fleet, plan.meta["wall_s"])
            except RuntimeError as exc:
                cache[s] = (9.0, float("nan"), [str(exc)[:40]], 0.0)
            if log:
                log(f"  s={s:.4f} cost={cache[s][1]:.1f} fleet={cache[s][2]} score={cache[s][0]:.4f} ({cache[s][3]} s)")
        return cache[s][0]

    for s in np.linspace(lo, hi, grid):
        score(s)
    step = (hi - lo) / (grid - 1)
    for _ in range(refine):
        best = min(cache, key=lambda s: cache[s][0])
        step /= 2
        for s in (best - step, best + step):
            score(s)
    best = min(cache, key=lambda s: cache[s][0])
    return {"scale": float(best), "cost": round(float(cache[best][1]), 2), "paper_cost": target,
            "rel_gap": round(float(cache[best][1] / target - 1.0), 5), "fleet_h": [float(x) for x in cache[best][2]],
            "paper_fleet_h": [float(x) for x in fleet_t], "evaluations": len(cache)}


def build_instances(path=None, calibrate_scales: bool = True, only=None, log=print) -> dict:
    """(Re)write instances.yaml: tables, base layouts, calibrated positions. `only`: instance names to (re)do, others kept."""
    import yaml
    path = Path(path or INSTANCES)
    data = yaml.safe_load(path.read_text()) if path.exists() else {"paper": PAPER_ID, "instances": {}}
    for name in (only or TABLES):
        hp = HELIPORTS[name]
        inst = data["instances"].get(name, {})
        inst["heliport"] = {"name": hp[0], "lon": hp[1], "lat": hp[2], "assumption": True}
        inst["layout"] = inst.get("layout") or design_layout(name)
        inst["positions"] = {n: list(p) for n, p in layout_positions((hp[1], hp[2]), inst["layout"], inst.get("calibration", {}).get("scale", 1.0)).items()}
        data["instances"][name] = inst
        if calibrate_scales:
            log(f"calibrating {name} (paper {PAPER_RESULT[name]['cost']})")
            rec = calibrate(name, data, log=log)
            inst["calibration"] = rec
            inst["positions"] = {n: [round(x, 5) for x in p] for n, p in layout_positions((hp[1], hp[2]), inst["layout"], rec["scale"]).items()}
            log(f"  -> {rec}")
    data["note"] = ("Installation positions are MASKED in the paper (p.25: 50-120 nm from the heliport). Everything under `layout`, "
                    "`positions`, `calibration` is an ASSUMPTION produced by offsim.solve.whelp.build_instances; demand, "
                    "opening hours, window costs and results are sourced in offsim.solve.whelp / scenario.yaml.")
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
    return data


# ------------------------------------------------------------------------------------------------- AMPL data (cvrp style: write_dat)
def write_dat(problem: Problem, path, H: int | None = None) -> Path:
    """AMPL data file for ampl/whelp.mod (the flight-based model). Time slots 0..S-1, S = slots of the largest window."""
    spec = parse_spec(problem)
    flights = generate_flights(spec)
    H = H or fleet_upper_bound(spec, flights)
    S = spec.s_w(len(spec.windows) - 1)
    l = spec.l

    def num(x):
        return f"{float(x):.6f}"

    I = [k + 1 for k in range(len(spec.inst))]
    F1 = [f.fid + 1 for f in flights if f.kind == "direct"]
    F2 = [f.fid + 1 for f in flights if f.kind == "split"]
    lines = ["# written by offsim.solve.whelp.write_dat; do not edit",
             "set I := " + " ".join(map(str, I)) + ";",
             "set H := " + " ".join(str(h + 1) for h in range(H)) + ";",
             "set W := " + " ".join(str(w + 1) for w in range(len(spec.windows))) + ";",
             "set F1 := " + " ".join(map(str, F1)) + ";",
             "set F2 := " + " ".join(map(str, F2)) + ";",
             "set D := " + " ".join(str(d + 1) for d in range(spec.days)) + ";",
             "set T := " + " ".join(str(t) for t in range(S)) + ";",
             f"param l := {l};",
             "param b :=", " ".join(f"{k + 1} {spec.inst[k].demand_half}" for k in range(len(spec.inst))) + ";",
             "param k :=", " ".join(f"{w + 1} {num(spec.windows[w][1])}" for w in range(len(spec.windows))) + ";",
             "param s :=", " ".join(f"{w + 1} {spec.s_w(w)}" for w in range(len(spec.windows))) + ";",
             "param c :=", " ".join(f"{f.fid + 1} {num(f.cost)}" for f in flights) + ";",
             "param n :=", " ".join(f"{f.fid + 1} {f.n}" for f in flights) + ";",
             "param a :=", " ".join(f"{i + 1} {f.fid + 1} 1" for f in flights for i in f.inst) + ";",
             "param pdep :=", " ".join(f"{k + 1} {t} 1" for k, p in enumerate(spec.inst) for t in range(p.lo, min(p.hi, S))) + ";"]
    path = Path(path)
    path.write_text("\n".join(lines) + "\n")
    return path


def ampl_status() -> tuple[bool, str]:
    from offsim.solve.ampl_adapter import ampl_status as st
    return st()


# ------------------------------------------------------------------------------------------------- CLI
def main(argv=None) -> int:
    import yaml
    ap = argparse.ArgumentParser(prog="python -m offsim.solve.whelp", description="WFPPP on an instance of the paper")
    ap.add_argument("--instance", default="floro", help="floro | stavanger | bergen")
    ap.add_argument("--method", default="decomposition", choices=("decomposition", "full"))
    ap.add_argument("--limit", type=float, default=300.0)
    ap.add_argument("--dat", default=None, help="write the AMPL data file here and exit")
    ap.add_argument("--write-scenario", default=None, metavar="PATH", help="write scenario YAML of --instance to PATH and exit")
    ap.add_argument("--calibrate", action="store_true", help="re-run the radial-scale calibration of --instance and rewrite instances.yaml")
    ap.add_argument("--init-instances", action="store_true", help="write instances.yaml with uncalibrated base layouts (scale 1)")
    a = ap.parse_args(argv)
    if a.init_instances:
        build_instances(calibrate_scales=False)
        return 0
    if a.calibrate:
        build_instances(only=[a.instance], calibrate_scales=True)
        return 0
    if a.write_scenario:
        Path(a.write_scenario).write_text(yaml.safe_dump(build_scenario(a.instance), sort_keys=False, allow_unicode=True))
        return 0
    prob = problem_for(a.instance)
    if a.dat:
        print(write_dat(prob, a.dat))
        return 0
    prob.extra["wfppp"] = {**prob.extra["wfppp"], "method": a.method}
    t0 = time.perf_counter()
    plan = WhelpSolver().solve(prob, seconds=a.limit)
    print(json.dumps({"instance": a.instance, "cost": round(plan.objective, 1), "paper_cost": PAPER_RESULT[a.instance]["cost"],
                      "status": plan.status, "helicopters": [h["label"] for h in plan.meta["helicopters"]],
                      "flights": plan.meta["flights_total"], "slots": plan.meta["slots_total"],
                      "utilisation": round(plan.meta["utilisation"], 4), "wall_s": round(time.perf_counter() - t0, 1)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
