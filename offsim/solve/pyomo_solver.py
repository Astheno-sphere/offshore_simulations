"""Pyomo + HiGHS exact CVRP / VRPTW behind the Solver protocol: Problem -> Plan with a dual bound.

Spec
- Registered as `pyomo`; classes {"CVRP", "VRPTW"}. Wraps `cvrp_exact` (two-index MTZ model) from
  skills/opt-model/scripts/models.py, loaded by file path with importlib so the skill stays the single
  source of the model (nothing is copied).
- Exact methods do not scale: more than MAX_CLIENTS (12) clients raises `Unsupported`; use `pyvrp` there and
  certify on a small instance.
- VRPTW (`"VRPTW" in problem.cls`): `vrptw_exact` below, a two-index MTZ load model plus a time-flow (big-M) model on
  service start times t_i in [early_i, late_i]: x_ij = 1 -> t_j >= t_i + service_i + dist_ij / speed (vehicles leave
  the depot at t = 0, as in the replay, and wait for a window to open). Arcs that cannot meet the windows are removed
  before solving. Times are continuous, durations are NOT rounded, while PyVRP rounds durations up: the exact optimum is
  therefore <= the PyVRP objective, and is the gate 1b certifier. Same refusals as the pyvrp solver
  (`check_vrptw_features`): release times, a depot window, several fleet entries, windows without cls VRPTW.
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
from offsim.solve.pyvrp_solver import check_vrptw_features

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


def vrptw_exact(dist, tt, demand, capacity, service, tw, max_vehicles=None):
    """Exact VRPTW, node 0 = depot. dist: metres, tt: travel seconds (same shape), demand[0] = 0, service[i] seconds,
    tw[i] = (early, late) for every client (use a large `late` for none). Binary x on the arcs that can meet the
    windows, load u (MTZ) and service-start time t (big-M time flow). Objective: total distance."""
    import pyomo.environ as pyo
    n = len(dist)
    N, C = range(n), range(1, n)
    arcs = [(0, j) for j in C if tt[0][j] <= tw[j][1]]
    arcs += [(j, 0) for j in C]
    arcs += [(i, j) for i in C for j in C if i != j and tw[i][0] + service[i] + tt[i][j] <= tw[j][1]]
    m = pyo.ConcreteModel("vrptw_exact")
    m.A = pyo.Set(initialize=arcs, dimen=2)
    m.x = pyo.Var(m.A, within=pyo.Binary)
    m.u = pyo.Var(C, bounds=lambda m, i: (demand[i], capacity))
    m.t = pyo.Var(C, bounds=lambda m, i: (tw[i][0], tw[i][1]))      # service start time
    out_arcs = {i: [a for a in arcs if a[0] == i] for i in N}
    in_arcs = {j: [a for a in arcs if a[1] == j] for j in N}
    m.into = pyo.Constraint(C, rule=lambda m, j: sum(m.x[a] for a in in_arcs[j]) == 1)
    m.out = pyo.Constraint(C, rule=lambda m, i: sum(m.x[a] for a in out_arcs[i]) == 1)
    m.depot = pyo.Constraint(expr=sum(m.x[a] for a in out_arcs[0]) == sum(m.x[a] for a in in_arcs[0]))
    if max_vehicles:
        m.fleet = pyo.Constraint(expr=sum(m.x[a] for a in out_arcs[0]) <= max_vehicles)
    m.start = pyo.Constraint([a for a in arcs if a[0] == 0], rule=lambda m, i, j: m.t[j] >= tt[0][j] * m.x[0, j])
    cc = [(i, j) for (i, j) in arcs if i and j]
    m.mtz = pyo.Constraint(cc, rule=lambda m, i, j: m.u[j] >= m.u[i] + demand[j] - capacity * (1 - m.x[i, j]))

    def time_rule(m, i, j):                      # big-M: tight per arc (latest start at i + service + travel - earliest at j)
        big = max(0.0, tw[i][1] + service[i] + tt[i][j] - tw[j][0])
        return m.t[j] >= m.t[i] + service[i] + tt[i][j] - big * (1 - m.x[i, j])
    m.time = pyo.Constraint(cc, rule=time_rule)
    m.cost = pyo.Objective(expr=sum(dist[i][j] * m.x[i, j] for (i, j) in arcs))
    return m


def extract_vrptw(m, n):
    """{'routes': [[node, ...]], 'cost'}; raises RuntimeError when a client is not on a route from the depot (subtour)."""
    import pyomo.environ as pyo
    on = [a for a in m.A if pyo.value(m.x[a]) > 0.5]
    succ = {i: j for (i, j) in on}
    routes = []
    for start in sorted(j for (i, j) in on if i == 0):
        r, k = [], start
        while k != 0:
            r.append(k)
            k = succ[k]
        routes.append(r)
    if sorted(c for r in routes for c in r) != list(range(1, n)):
        raise RuntimeError("exact VRPTW solution has a subtour or an unserved client")
    return {"routes": routes, "cost": pyo.value(m.cost)}


@register_solver("pyomo")
class PyomoSolver:
    name = "pyomo"
    classes = {"CVRP", "VRPTW"}

    def solve(self, problem: Problem, seconds: float = 2.0, seed: int = 1) -> Plan:
        import pyomo.environ as pyo
        from offsim.solve.pyvrp_solver import agent_ids

        extra_cls = set(problem.cls) - self.classes
        if extra_cls:
            raise Unsupported(f"pyomo solver handles {sorted(self.classes)}; problem also needs {sorted(extra_cls)}")
        tw = check_vrptw_features(problem, "pyomo solver")
        vrptw = "VRPTW" in problem.cls
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

        if vrptw:
            speed = float(fleet["speed_mps"])
            Df = np.asarray(problem.dist_m, dtype=float)
            tt = (Df / speed).tolist()
            big = 1e7                                                       # no window: effectively open-ended (s)
            win = {i: tw.get(i, (0.0, big)) for i in range(1, n_clients + 1)}
            svc = {i: float((problem.service_s or {}).get(i, 0.0)) for i in range(1, n_clients + 1)}
            m = vrptw_exact(D, tt, demand, cap, svc, win, max_vehicles=n_veh)
        else:
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
            sol = extract_vrptw(m, n_clients + 1) if vrptw else models.extract_cvrp(m)
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
                    meta={"termination": tc, "seconds": seconds, "seed": seed, "model": "vrptw_exact (MTZ + time flow)" if vrptw else "cvrp_exact (MTZ)",
                          "vehicles_used": len(routes)})
