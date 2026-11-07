"""PyVRP (HGS) behind the Solver protocol: Problem -> Plan.

Spec
- Registered as `pyvrp`; handles problem class {"CVRP"} only. A Problem that carries time windows, or whose
  `cls` names anything else (e.g. "VRPTW"), raises `Unsupported`: we do not model windows here, and a CVRP
  plan that ignores windows would be an unmarked approximation.
- One vehicle type (`problem.fleet` has a single entry), integer demands and capacity (PyVRP is integral;
  fractional values would be truncated by `solve_cvrp`, so they are refused instead).
- Agent ids follow the pipeline convention `f"{fleet.cls.upper()}-{k}"`, k = 1..count (e.g. PSV-1). Unused
  vehicles appear in `Plan.routes` with an empty route.
- Objective = total distance in metres on `problem.dist_m` (rounded to integers by the adapter, as PyVRP
  requires). `service_s` does not enter a distance objective and is ignored by definition, not by approximation.
- All index traps live in `offsim/solve/pyvrp_adapter.py`; this module only maps types.
"""
from __future__ import annotations

import numpy as np

from offsim.engines.base import Plan, Problem, Unsupported, register_solver
from offsim.solve.pyvrp_adapter import matrix, solve_cvrp


def agent_ids(fleet_entry: dict) -> list[str]:
    """Pipeline convention for agent ids of one fleet entry."""
    return [f"{str(fleet_entry.get('cls', 'agent')).upper()}-{k + 1}" for k in range(int(fleet_entry["count"]))]


def _integral(x, what: str) -> int:
    if float(x) != int(round(float(x))):
        raise Unsupported(f"pyvrp needs integer {what}, got {x}")
    return int(round(float(x)))


@register_solver("pyvrp")
class PyVRPSolver:
    name = "pyvrp"
    classes = {"CVRP"}

    def solve(self, problem: Problem, seconds: float = 2.0, seed: int = 1) -> Plan:
        extra_cls = set(problem.cls) - self.classes
        if extra_cls:
            raise Unsupported(f"pyvrp solver handles {sorted(self.classes)}; problem also needs {sorted(extra_cls)}")
        if problem.tw:
            raise Unsupported("pyvrp solver: time windows (VRPTW) are not implemented here")
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
        routes, cost = solve_cvrp(problem.nodes, demand, n_veh, cap, speed, seconds=seconds, dist=dist, seed=seed)
        ids = agent_ids(fleet)
        plan = dict(zip(ids, routes + [[]] * (n_veh - len(routes))))
        return Plan(routes=plan, objective=float(cost), objective_unit="m", solver=self.name, bound=None,
                    status="feasible", meta={"seed": seed, "seconds": seconds,
                                             "vehicles_used": sum(1 for r in routes if r)})
