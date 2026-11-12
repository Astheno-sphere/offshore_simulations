"""PyVRP (HGS) behind the Solver protocol: Problem -> Plan.

Spec
- Registered as `pyvrp`; handles problem classes {"CVRP", "VRPTW"}. Anything else in `Problem.cls` raises `Unsupported`.
- CVRP: unchanged. `service_s` does not enter a distance objective and is ignored by definition, not by approximation.
  A Problem that carries time windows but whose `cls` lacks "VRPTW" raises `Unsupported` (windows would be dropped).
- VRPTW: `Problem.tw` {node: (earliest_s, latest_s)} and `Problem.service_s` map to PyVRP clients (`tw_early`,
  `tw_late`, `service_duration`); the duration matrix is `dist_m / fleet speed_mps`. Semantics are the replay's
  (offsim/sim/replay.py): vehicles leave the depot at t = 0, arrive early -> wait until the window opens (state `wait`),
  service must START by `latest`. The objective is still total distance (metres). Rounding is conservative (durations
  up, opens up, closes down), so a PyVRP plan is feasible in the continuous-time replay. The returned plan is
  re-checked in continuous time (`pyvrp_adapter.windows_violations`) before it is passed on.
- Still `Unsupported`, loudly: more than one fleet entry (vehicle types), release times (`extra` carries `release`,
  `release_s` or `release_times`), a window on the depot (node 0: the replay does not model one), a window with
  earliest > latest or a node outside 1..n-1, fractional demand, capacity, count, and a stop whose demand exceeds capacity.
- One vehicle type (`problem.fleet` has a single entry), integer demands and capacity (PyVRP is integral;
  fractional values would be truncated by `solve_cvrp`, so they are refused instead).
- Agent ids follow the pipeline convention `f"{fleet.cls.upper()}-{k}"`, k = 1..count (e.g. PSV-1). Unused
  vehicles appear in `Plan.routes` with an empty route.
- Objective = total distance in metres on `problem.dist_m` (rounded to integers by the adapter, as PyVRP
  requires).
- All index traps live in `offsim/solve/pyvrp_adapter.py`; this module only maps types.
"""
from __future__ import annotations

import numpy as np

from offsim.engines.base import Plan, Problem, Unsupported, register_solver
from offsim.solve.pyvrp_adapter import matrix, solve_cvrp, solve_vrptw, windows_violations


def agent_ids(fleet_entry: dict) -> list[str]:
    """Pipeline convention for agent ids of one fleet entry."""
    return [f"{str(fleet_entry.get('cls', 'agent')).upper()}-{k + 1}" for k in range(int(fleet_entry["count"]))]


def _integral(x, what: str) -> int:
    if float(x) != int(round(float(x))):
        raise Unsupported(f"pyvrp needs integer {what}, got {x}")
    return int(round(float(x)))


RELEASE_KEYS = ("release", "release_s", "release_times")


def check_vrptw_features(problem: Problem, who: str) -> dict:
    """Refuse every VRPTW feature the solvers and the replay do not map; return the normalised windows {node: (e, l)}.
    Shared by the pyvrp and pyomo solvers so both refuse and accept the same instances."""
    if problem.tw and "VRPTW" not in problem.cls:
        raise Unsupported(f"{who}: the problem has time windows but cls={sorted(problem.cls)} lacks 'VRPTW'; "
                          "windows would be dropped silently")
    hit = [k for k in RELEASE_KEYS if (problem.extra or {}).get(k)]
    if hit:
        raise Unsupported(f"{who}: release times ({hit[0]}) are not mapped (the replay engine does not hold vehicles for them)")
    n = len(problem.nodes)
    tw = {}
    for node, win in problem.tw.items():
        if int(node) == 0:
            raise Unsupported(f"{who}: a time window on the depot (node 0) is not modelled")
        if not 1 <= int(node) < n:
            raise Unsupported(f"{who}: time window for node {node} outside 1..{n - 1}")
        e, l = float(win[0]), float(win[1])
        if e > l:
            raise Unsupported(f"{who}: empty time window at node {node}: earliest {e} > latest {l}")
        tw[int(node)] = (e, l)
    return tw


@register_solver("pyvrp")
class PyVRPSolver:
    name = "pyvrp"
    classes = {"CVRP", "VRPTW"}

    def solve(self, problem: Problem, seconds: float = 2.0, seed: int = 1) -> Plan:
        extra_cls = set(problem.cls) - self.classes
        if extra_cls:
            raise Unsupported(f"pyvrp solver handles {sorted(self.classes)}; problem also needs {sorted(extra_cls)}")
        tw = check_vrptw_features(problem, "pyvrp solver")
        vrptw = "VRPTW" in problem.cls
        if len(problem.fleet) != 1:
            raise Unsupported(f"pyvrp solver: exactly one fleet entry supported, got {len(problem.fleet)}")
        fleet = problem.fleet[0]
        n_veh = _integral(fleet["count"], "vehicle count")
        cap = _integral(fleet["capacity"], "capacity")
        speed = float(fleet["speed_mps"])
        demand = {int(i): _integral(q, f"demand at node {i}") for i, q in problem.demand.items()}
        n = len(problem.nodes)
        missing = [i for i in range(1, n) if i not in demand]
        if missing:
            raise Unsupported(f"pyvrp solver: no demand for nodes {missing} (use 0 explicitly)")
        if any(q > cap for q in demand.values()):
            raise Unsupported("pyvrp solver: a single stop's demand exceeds vehicle capacity (split deliveries)")
        dist = matrix(problem.nodes) if problem.dist_m is None else np.asarray(problem.dist_m, dtype=float)
        if vrptw:
            service = {int(i): float(t) for i, t in (problem.service_s or {}).items() if float(t)}
            routes, cost = solve_vrptw(problem.nodes, demand, n_veh, cap, speed, service=service, tw=tw,
                                       seconds=seconds, dist=dist, seed=seed)
            bad = windows_violations(dist, speed, routes, service, tw)
            if bad:                     # cannot happen with conservative rounding; never pass on an infeasible plan
                raise RuntimeError(f"PyVRP plan misses time windows in continuous time: {bad}")
        else:
            routes, cost = solve_cvrp(problem.nodes, demand, n_veh, cap, speed, seconds=seconds, dist=dist, seed=seed)
        ids = agent_ids(fleet)
        plan = dict(zip(ids, routes + [[]] * (n_veh - len(routes))))
        return Plan(routes=plan, objective=float(cost), objective_unit="m", solver=self.name, bound=None,
                    status="feasible", meta={"seed": seed, "seconds": seconds,
                                             "vehicles_used": sum(1 for r in routes if r),
                                             **({"time_windows": len(tw)} if vrptw else {})})
