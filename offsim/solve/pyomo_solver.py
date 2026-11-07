"""Pyomo + HiGHS exact CVRP behind the Solver protocol: Problem -> Plan with a dual bound.

Spec
- Registered as `pyomo`; class {"CVRP"}. Wraps `cvrp_exact` (two-index MTZ model) from
  skills/opt-model/scripts/models.py, loaded by file path with importlib so the skill stays the single
  source of the model (nothing is copied).
- Exact methods do not scale: more than MAX_CLIENTS (12) clients raises `Unsupported`; use `pyvrp` there and
  certify on a small instance. Time windows are not modelled and raise `Unsupported`.
- Distances are rounded to integer metres exactly like the PyVRP adapter, so both solvers optimise the same
  numbers and `pyomo.objective <= pyvrp.objective` is a meaningful certificate.
- `max_vehicles` = fleet count. Agent ids as in `pyvrp_solver.agent_ids` (PSV-1, ...).
- Plan.status: "optimal" when HiGHS proves it, "time_limit" when it stops at `seconds` with an incumbent
  (then `bound` is the proven dual bound and `objective` the incumbent). No incumbent -> RuntimeError.
- Plan.bound is HiGHS' proven lower bound (minimisation) in the same unit as the objective.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np

from offsim.engines.base import Plan, Problem, Unsupported, register_solver

MAX_CLIENTS = 12
_SKILL_MODELS = Path(__file__).resolve().parents[2] / "skills" / "opt-model" / "scripts" / "models.py"


def _load_models():
    """Import skills/opt-model/scripts/models.py by path (it is a skill script, not a package module)."""
    name = "offsim_skill_opt_models"
    if name in sys.modules:
        return sys.modules[name]
    if not _SKILL_MODELS.exists():
        raise Unsupported(f"pyomo solver: model file missing: {_SKILL_MODELS}")
    spec = importlib.util.spec_from_file_location(name, _SKILL_MODELS)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@register_solver("pyomo")
class PyomoSolver:
    name = "pyomo"
    classes = {"CVRP"}

    def solve(self, problem: Problem, seconds: float = 2.0, seed: int = 1) -> Plan:
        import pyomo.environ as pyo
        from offsim.solve.pyvrp_solver import agent_ids

        extra_cls = set(problem.cls) - self.classes
        if extra_cls:
            raise Unsupported(f"pyomo solver handles {sorted(self.classes)}; problem also needs {sorted(extra_cls)}")
        if problem.tw:
            raise Unsupported("pyomo solver: time windows are not modelled")
        if len(problem.fleet) != 1:
            raise Unsupported(f"pyomo solver: exactly one fleet entry supported, got {len(problem.fleet)}")
        n_clients = len(problem.nodes) - 1
        if n_clients > MAX_CLIENTS:
            raise Unsupported(f"pyomo exact CVRP supports at most {MAX_CLIENTS} clients, got {n_clients}; use pyvrp")
        fleet = problem.fleet[0]
        n_veh, cap = int(fleet["count"]), float(fleet["capacity"])
        demand = [0.0] + [float(problem.demand[i]) for i in range(1, n_clients + 1)]
        if max(demand) > cap:
            raise Unsupported("pyomo solver: a single stop's demand exceeds vehicle capacity")
        D = np.rint(np.asarray(problem.dist_m, dtype=float)).astype(int).tolist()

        models = _load_models()
        m = models.cvrp_exact(D, demand, cap, max_vehicles=n_veh)
        opt = pyo.SolverFactory("appsi_highs")
        if not opt.available(exception_flag=False):
            raise Unsupported("HiGHS (appsi_highs) is not available in this environment")
        opt.config.time_limit = float(seconds)
        opt.highs_options["mip_rel_gap"] = 0.0      # default 1e-4 would make 'optimal' a 0.01% claim
        opt.highs_options["mip_abs_gap"] = 1e-6
        opt.highs_options["random_seed"] = int(seed)
        res = opt.solve(m)
        tc = str(res.solver.termination_condition)
        try:
            obj = float(pyo.value(m.cost))
            sol = models.extract_cvrp(m)
        except Exception as e:            # noqa: BLE001 - no incumbent loaded
            raise RuntimeError(f"HiGHS returned no solution (termination: {tc})") from e
        if tc == "optimal":
            status = "optimal"
        elif tc in ("maxTimeLimit", "maxIterations"):
            status = "time_limit"
        else:
            raise RuntimeError(f"unexpected HiGHS termination: {tc}")
        lb = res.problem.lower_bound
        bound = None if lb is None or not np.isfinite(lb) else float(lb)
        if bound is not None:
            bound = min(bound, obj)
        if status == "optimal":
            obj = round(obj, 6)            # integer metres: strip LP round-off (35508.99999999997 -> 35509)
            bound = obj if bound is None else min(round(bound, 6), obj)
        ids = agent_ids(fleet)
        routes = sol["routes"]
        if len(routes) > n_veh:
            raise RuntimeError("model used more vehicles than the fleet")
        plan = dict(zip(ids, routes + [[]] * (n_veh - len(routes))))
        return Plan(routes=plan, objective=obj, objective_unit="m", solver=self.name, bound=bound, status=status,
                    meta={"termination": tc, "seconds": seconds, "seed": seed, "model": "cvrp_exact (MTZ)",
                          "vehicles_used": len(routes)})
