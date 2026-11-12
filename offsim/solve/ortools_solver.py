"""Google OR-Tools routing behind the Solver protocol: Problem -> Plan. The second, independent routing solver.

Spec
- Registered as `ortools`; handles problem classes {"CVRP", "VRPTW", "PDP"}. PDP may be combined with VRPTW
  (`cls = {"PDP", "VRPTW"}`: paired stops with windows). Anything else in `Problem.cls` raises `Unsupported`.
- CVRP: one capacity dimension (cumulative demand <= capacity, vehicles start empty of "delivered" units).
- VRPTW: a "Time" dimension, `Problem.tw` {node: (earliest_s, latest_s)} and `Problem.service_s` mapped with the
  semantics of the replay (offsim/sim/replay.py) and of the pyvrp solver: vehicles leave the depot at t = 0, arrive
  early -> wait (slack) until the window opens, service must START by `latest`. Travel time = `dist_m / speed_mps`.
  Rounding is conservative exactly as in `pyvrp_adapter` (travel and service up, window opens up, closes down), so an
  OR-Tools plan is feasible in the continuous-time replay. The plan is re-checked in continuous time
  (`pyvrp_adapter.windows_violations`) before it is returned.
- PDP: `Problem.pairs` {pickup_node: delivery_node}. Sign convention of `Problem.demand` (shared with the replay, which
  "unloads" `demand[b]` at b and starts a route carrying `sum(demand)`): a delivery has demand +q, its pickup -q, so
  every route starts and ends empty and the on-board load rises by q at the pickup and falls by q at the delivery.
  Constraints: `AddPickupAndDelivery`, same vehicle for both stops, pickup strictly before delivery (a unit-step
  "Order" dimension, so precedence also holds when both stops are at the same position), load in [0, capacity].
  Every stop 1..n-1 must belong to exactly one pair; |demand| equal on both ends, delivery > 0.
- Objective: total distance in metres on `problem.dist_m`, rounded to integer metres per arc exactly like the PyVRP
  adapter and the Pyomo solver, so objectives of the three solvers are comparable.
- Process: the model runs in a subprocess (`ortools_worker.py`, `python -I`). `ortools` and `highspy` (pyomo, whelp) ship
  clashing HiGHS symbols, so they cannot share an interpreter; the worker keeps both usable in one run.
- Determinism: first-solution strategy PARALLEL_CHEAPEST_INSERTION, metaheuristic GUIDED_LOCAL_SEARCH, search stops at
  `seconds` of wall clock. OR-Tools' routing search has no random seed, so `seed` is accepted, recorded in
  `Plan.meta["seed"]` and unused; the same input gives the same plan whenever the search is not cut off in the middle
  of an improvement (small instances converge long before the limit; large ones can differ run to run by timing).
- Still `Unsupported`, loudly: more than one fleet entry, release times, a depot window, empty or out-of-range windows,
  fractional demand/capacity/count, a stop larger than the vehicle, windows without cls VRPTW, pairs without cls PDP,
  cls PDP without pairs or with an unpaired stop. No feasible plan (windows or capacity cannot be met) -> RuntimeError.
- Agent ids as in `pyvrp_solver.agent_ids` (PSV-1, ...); unused vehicles appear with an empty route.
"""
from __future__ import annotations

import importlib.util
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np

from offsim.engines.base import Plan, Problem, Unsupported, register_solver
from offsim.solve.pyvrp_adapter import matrix, windows_violations
from offsim.solve.pyvrp_solver import _integral, agent_ids, check_vrptw_features

FIRST_SOLUTION = "PARALLEL_CHEAPEST_INSERTION"
METAHEURISTIC = "GUIDED_LOCAL_SEARCH"


def check_pdp(problem: Problem, who: str = "ortools solver") -> dict[int, int]:
    """Validate the PDP part of a Problem and return {pickup: delivery}. Refuses every case it does not model."""
    pairs = {int(p): int(d) for p, d in (getattr(problem, "pairs", None) or {}).items()}
    pdp = "PDP" in problem.cls
    if pairs and not pdp:
        raise Unsupported(f"{who}: the problem has pickup-delivery pairs but cls={sorted(problem.cls)} lacks 'PDP'; "
                          "the pairing would be dropped silently")
    if not pdp:
        return {}
    if not pairs:
        raise Unsupported(f"{who}: cls PDP needs Problem.pairs {{pickup: delivery}}")
    n = len(problem.nodes)
    seen: list[int] = []
    for p, d in pairs.items():
        for node in (p, d):
            if not 1 <= node < n:
                raise Unsupported(f"{who}: pair ({p}, {d}) uses node {node} outside 1..{n - 1}")
        if p == d:
            raise Unsupported(f"{who}: pair ({p}, {d}) has the same pickup and delivery node")
        seen += [p, d]
    if len(seen) != len(set(seen)):
        raise Unsupported(f"{who}: a node appears in more than one pair")
    if set(seen) != set(range(1, n)):
        raise Unsupported(f"{who}: nodes {sorted(set(range(1, n)) - set(seen))} are in no pair (mixing PDP with plain "
                          "deliveries is not mapped)")
    for p, d in pairs.items():
        qp, qd = problem.demand.get(p), problem.demand.get(d)
        if qp is None or qd is None or float(qd) <= 0 or float(qp) != -float(qd):
            raise Unsupported(f"{who}: pair ({p}, {d}) needs demand[delivery] = q > 0 and demand[pickup] = -q "
                              f"(got {qp}, {qd})")
    return pairs


def pdp_violations(problem: Problem, routes: list[list[int]] | dict, capacity: float | None = None) -> list[str]:
    """Independent check of a plan against the PDP constraints. [] = feasible. Each message names the broken rule:
    a pair split over vehicles, a delivery before its pickup, a stop served twice or never, load outside [0, capacity]."""
    pairs = check_pdp(problem)
    routes = list(routes.values()) if isinstance(routes, dict) else list(routes)
    cap = capacity if capacity is not None else (problem.fleet[0]["capacity"] if problem.fleet else None)
    where = {}
    bad = []
    for k, r in enumerate(routes):
        for pos, node in enumerate(r):
            if node in where:
                bad.append(f"node {node} served twice")
            where[node] = (k, pos)
        load = 0.0
        for node in r:
            load -= float(problem.demand[node])
            if load < -1e-9 or (cap is not None and load > cap + 1e-9):
                bad.append(f"vehicle {k}: load {load:g} outside [0, {cap}] after node {node}")
    for node in range(1, len(problem.nodes)):
        if node not in where:
            bad.append(f"node {node} not served")
    for p, d in pairs.items():
        if p in where and d in where:
            if where[p][0] != where[d][0]:
                bad.append(f"pair ({p}, {d}) split over vehicles {where[p][0]} and {where[d][0]}")
            elif where[p][1] > where[d][1]:
                bad.append(f"pair ({p}, {d}): delivery before pickup")
    return bad


WORKER = Path(__file__).with_name("ortools_worker.py")


def _run_worker(req: dict, seconds: float) -> list[list[int]]:
    """Run the OR-Tools model in a separate interpreter (see ortools_worker.py: symbol clash with highspy)."""
    done = subprocess.run([sys.executable, "-I", str(WORKER)], input=json.dumps(req), capture_output=True, text=True,
                          timeout=float(seconds) + 120.0)
    try:
        out = json.loads(done.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"OR-Tools worker failed (exit {done.returncode}): {done.stderr.strip()[-300:]}") from None
    if not out["ok"]:
        if out.get("crash"):
            raise RuntimeError(f"OR-Tools worker crashed: {out['error']}")
        raise RuntimeError(f"OR-Tools found no plan that meets the capacity and the other constraints ({out['error']})")
    return out["routes"]


@register_solver("ortools")
class ORToolsSolver:
    name = "ortools"
    classes = {"CVRP", "VRPTW", "PDP"}

    def __init__(self):
        if importlib.util.find_spec("ortools") is None:         # not imported here: see ortools_worker.py
            raise ImportError("ortools is not installed (pip install ortools)")

    def solve(self, problem: Problem, seconds: float = 2.0, seed: int = 1) -> Plan:
        extra_cls = set(problem.cls) - self.classes
        if extra_cls:
            raise Unsupported(f"ortools solver handles {sorted(self.classes)}; problem also needs {sorted(extra_cls)}")
        tw = check_vrptw_features(problem, "ortools solver")
        pairs = check_pdp(problem)
        pdp = bool(pairs)
        timed = "VRPTW" in problem.cls
        if len(problem.fleet) != 1:
            raise Unsupported(f"ortools solver: exactly one fleet entry supported, got {len(problem.fleet)}")
        fleet = problem.fleet[0]
        n_veh = _integral(fleet["count"], "vehicle count")
        cap = _integral(fleet["capacity"], "capacity")
        speed = float(fleet["speed_mps"])
        n = len(problem.nodes)
        demand = {int(i): _integral(q, f"demand at node {i}") for i, q in problem.demand.items()}
        missing = [i for i in range(1, n) if i not in demand]
        if missing:
            raise Unsupported(f"ortools solver: no demand for nodes {missing} (use 0 explicitly)")
        if any(abs(q) > cap for q in demand.values()):
            raise Unsupported("ortools solver: a single stop's demand exceeds vehicle capacity (split deliveries)")
        if not pdp and any(q < 0 for q in demand.values()):
            raise Unsupported("ortools solver: negative demand needs cls PDP with pairs")
        dist = matrix(problem.nodes) if problem.dist_m is None else np.asarray(problem.dist_m, dtype=float)
        D = np.rint(dist).astype(np.int64).tolist()
        service = {int(i): float(t) for i, t in (problem.service_s or {}).items() if float(t)}
        if service and not timed:
            service = {}                   # service time does not enter a distance-only objective (as in pyvrp)

        # capacity: CVRP accumulates demand (units delivered from the depot); PDP tracks on-board load (+q at pickup)
        delta = [0] + [(-1 if pdp else 1) * demand[i] for i in range(1, n)]
        req = {"dist": D, "n_veh": n_veh, "cap": cap, "load": delta, "seconds": float(seconds), "tt": None,
               "svc": None, "tw": None, "horizon": None, "pairs": {str(p): d for p, d in pairs.items()} or None,
               "first": FIRST_SOLUTION, "meta": METAHEURISTIC}
        if timed:
            tt = [[int(math.ceil(dist[i][j] / speed - 1e-9)) for j in range(n)] for i in range(n)]
            svc = [0] + [int(math.ceil(service.get(i, 0.0))) for i in range(1, n)]
            late_max = max([int(math.floor(w[1])) for w in tw.values()] + [0])
            req.update(tt=tt, svc=svc, horizon=late_max + sum(svc) + n * max(max(r) for r in tt) + 1,
                       tw={str(i): [int(math.ceil(e)), int(math.floor(l))] for i, (e, l) in tw.items()})
        routes = _run_worker(req, seconds)
        if timed:
            bad = windows_violations(dist, speed, routes, service, tw)
            if bad:                        # cannot happen with conservative rounding; never pass on an infeasible plan
                raise RuntimeError(f"OR-Tools plan misses time windows in continuous time: {bad}")
        if pdp:
            bad = pdp_violations(problem, routes, cap)
            if bad:
                raise RuntimeError(f"OR-Tools plan breaks the pickup-delivery constraints: {bad}")
        cost = sum(D[a][b] for r in routes for a, b in zip([0] + r, r + [0]))
        ids = agent_ids(fleet)
        meta = {"seed": seed, "seed_used": False, "seconds": seconds, "first_solution": FIRST_SOLUTION,
                "metaheuristic": METAHEURISTIC, "vehicles_used": sum(1 for r in routes if r)}
        if timed:
            meta["time_windows"] = len(tw)
        if pdp:
            meta["pairs"] = len(pairs)
        return Plan(routes=dict(zip(ids, routes)), objective=float(cost), objective_unit="m", solver=self.name,
                    bound=None, status="feasible", meta=meta)
