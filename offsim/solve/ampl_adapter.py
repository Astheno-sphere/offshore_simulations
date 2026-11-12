"""AMPL route solver (CVRP and VRPTW) behind the Solver protocol: Problem in, Plan out.

Runs where the AMPL binary and a solver module are installed and activated:
- GitHub Actions: .github/workflows/solve.yml (secret AMPL_LICENSE_UUID)
- the laptop: through tools/ampl_mcp, or the CLI below

Here (Claude workspace) the AMPL binary cannot be downloaded, so `ampl_status()` reports that and the
solve test is skipped. Everything else in this module (data writing, route extraction, plan checks) runs.

    python -m offsim.solve.ampl_adapter --scenario offsim/papers/<id>/scenario.yaml --out out/solve/ \
        [--solver highs|cbc] [--seconds 60] [--seed 1] [--great-circle]

Distances: the CLI uses great-circle metres (same as offsim/solve/pyvrp_adapter.py). A scenario with a
world (sea lanes) is refused unless --great-circle is given, because vessels must route on lanes
(CLAUDE.md). The plan records which distance basis it used.

AMPL licence UUIDs never appear in this file, in logs or in plan.json: the activation happens in CI or
in the user's shell.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

from offsim.engines.base import Plan, Problem, Unsupported, register_solver

MODEL = Path(__file__).resolve().parent / "ampl" / "cvrp.mod"
MODEL_VRPTW = Path(__file__).resolve().parent / "ampl" / "vrptw.mod"      # VRPTW: parse-checked by text only in the Claude workspace
CLASSES = {"CVRP", "VRPTW"}
SOLVERS = ("highs", "cbc")
HELP = ("AMPL is not usable here: amplpy could not start the AMPL binary or its solver module. "
        "Run the solve on GitHub Actions (.github/workflows/solve.yml, needs the secret AMPL_LICENSE_UUID) "
        "or on your laptop through tools/ampl_mcp/README.md (install the modules, then activate the licence).")


# --- pure functions: no AMPL needed --------------------------------------------------------------------------
def routes_from_arcs(arcs, depot: int = 0) -> list[list[int]]:
    """Routes from the arcs with x = 1. `arcs` is an iterable of (i, j) pairs.

    Returns one list per vehicle, the clients in visiting order, depot excluded at both ends. Raises ValueError
    for a node with two successors, a cycle that misses the depot, or a client that is not served.
    """
    out: dict[int, list[int]] = {}
    for i, j in arcs:
        out.setdefault(int(i), []).append(int(j))
    for i, js in out.items():
        if i != depot and len(js) > 1:
            raise ValueError(f"client {i} has two successors {js}")
    routes, seen = [], set()
    for start in sorted(out.get(depot, [])):
        route, node = [], start
        while node != depot:
            if node in seen:
                raise ValueError(f"client {node} is on two routes or in a subtour")
            if node not in out:
                raise ValueError(f"client {node} has no successor")
            seen.add(node)
            route.append(node)
            node = out[node][0]
        routes.append(route)
    nodes_in_arcs = set(out) | {j for js in out.values() for j in js}
    unserved = sorted(nodes_in_arcs - {depot} - seen)
    if unserved:
        raise ValueError(f"clients on a cycle without the depot: {unserved}")
    return routes


def route_distance(dist, routes, depot: int = 0) -> float:
    """Metres driven by the routes, depot to first client, between clients, last client to depot."""
    D = np.asarray(dist, dtype=float)
    total = 0.0
    for r in routes:
        path = [depot, *r, depot]
        total += sum(D[a, b] for a, b in zip(path, path[1:]))
    return float(total)


def check_plan(problem: Problem, routes: list[list[int]]) -> dict:
    """Gate-1 style check outside the solver: every client once, loads within capacity, fleet size respected.
    For a VRPTW problem also `windows_ok`: every service starts by its window's close (replay semantics)."""
    fleet = problem.fleet[0]
    cap, veh = float(fleet["capacity"]), int(fleet["count"])
    clients = sorted(range(1, len(problem.nodes)))
    served = sorted(c for r in routes for c in r)
    loads = [sum(problem.demand[c] for c in r) for r in routes]
    out = {"served_once": served == clients,
           "capacity_ok": all(load <= cap + 1e-9 for load in loads),
           "fleet_ok": len(routes) <= veh,
           "loads": loads, "capacity": cap, "vehicles_allowed": veh}
    if "VRPTW" in problem.cls:
        from offsim.solve.pyvrp_adapter import windows_violations
        bad = windows_violations(problem.dist_m, float(fleet["speed_mps"]), routes, problem.service_s, problem.tw)
        out["windows_ok"] = not bad
        out["window_violations"] = bad
    return out


def write_dat(problem: Problem, path) -> Path:
    """Write the AMPL data file for cvrp.mod (class CVRP) or vrptw.mod (class VRPTW: adds tt, svc, early, late).
    Raises Unsupported for other classes and for VRPTW features the solvers do not map, ValueError for bad data."""
    if not set(problem.cls) <= CLASSES:
        raise Unsupported(f"AMPL adapter maps {sorted(CLASSES)} only; got {sorted(problem.cls)}")
    n = len(problem.nodes)
    D = np.asarray(problem.dist_m, dtype=float)
    if D.shape != (n, n):
        raise ValueError(f"dist_m shape {D.shape} does not match {n} nodes")
    vrptw = "VRPTW" in problem.cls
    tw = {}
    if vrptw:
        from offsim.solve.pyvrp_solver import check_vrptw_features
        tw = check_vrptw_features(problem, "AMPL adapter")
    elif problem.tw:
        raise Unsupported("AMPL adapter: the problem has time windows but cls lacks 'VRPTW'; windows would be dropped")
    if len(problem.fleet) != 1:
        raise Unsupported(f"AMPL adapter: exactly one fleet entry supported, got {len(problem.fleet)}")
    fleet = problem.fleet[0]
    veh, cap = int(fleet["count"]), float(fleet["capacity"])
    if veh < 1:
        raise ValueError("fleet count must be at least 1")
    clients = list(range(1, n))
    missing = [c for c in clients if c not in problem.demand]
    if missing:
        raise ValueError(f"no demand for clients {missing}")
    too_big = {c: problem.demand[c] for c in clients if problem.demand[c] > cap}
    if too_big:
        raise ValueError(f"demand above vehicle capacity {cap}: {too_big} (infeasible; fix the scenario)")

    def num(x):
        return f"{float(x):.6f}"

    lines = ["# written by offsim.solve.ampl_adapter.write_dat; do not edit",
             "set NODES := " + " ".join(str(i) for i in range(n)) + ";",
             "set CLIENTS := " + " ".join(str(c) for c in clients) + ";",
             f"param VEH := {veh};",
             f"param cap := {num(cap)};",
             "param demand :=",
             " ".join(f"{c} {num(problem.demand[c])}" for c in clients) + ";",
             "param dist : " + " ".join(str(j) for j in range(n)) + " :="]
    for i in range(n):
        lines.append(f"{i} " + " ".join(num(D[i, j]) for j in range(n)))
    lines.append(";")
    if vrptw:
        speed = float(fleet["speed_mps"])
        horizon = 1e7                                   # seconds: "no window" means open-ended
        lines.append("param tt : " + " ".join(str(j) for j in range(n)) + " :=")
        for i in range(n):
            lines.append(f"{i} " + " ".join(num(D[i, j] / speed) for j in range(n)))
        lines.append(";")
        lines.append("param svc :=")
        lines.append(" ".join(f"{c} {num((problem.service_s or {}).get(c, 0.0))}" for c in clients) + ";")
        lines.append("param early :=")
        lines.append(" ".join(f"{c} {num(tw.get(c, (0.0, horizon))[0])}" for c in clients) + ";")
        lines.append("param late :=")
        lines.append(" ".join(f"{c} {num(tw.get(c, (0.0, horizon))[1])}" for c in clients) + ";")
    path = Path(path)
    path.write_text("\n".join(lines) + "\n")
    return path


def problem_from_scenario(sc: dict) -> Problem:
    """Problem from scenario.yaml, mirroring offsim/pipeline.py node and demand extraction, without sea lanes."""
    from offsim.pipeline import v
    from offsim.solve.pyvrp_adapter import matrix

    classes = set(sc["problem"]["class"])
    if not classes <= CLASSES:
        raise Unsupported(f"AMPL adapter maps {sorted(CLASSES)} only; scenario has {sorted(classes)}")
    inst = sc["instance"]
    base, stops = inst["base"], inst["stops"]
    nodes = [(base["lon"], base["lat"])] + [(s["lon"], s["lat"]) for s in stops]
    demand = {i: float(v(s["demand"])) for i, s in enumerate(stops, 1)}
    f = sc["fleet"][0]
    fleet = [{"cls": f["cls"], "count": int(v(f["count"])), "capacity": float(v(f["capacity"])),
              "speed_mps": float(v(f["speed_mps"])), "domain": f.get("domain", "sea")}]
    service, tw = {}, {}
    if "VRPTW" in classes:                              # same extraction as offsim.pipeline.build_problem
        service = {i: float(v(s.get("service_s", inst.get("service_s", 0))) or 0) for i, s in enumerate(stops, 1)}
        tw = {i: tuple(v(s["tw"])) for i, s in enumerate(stops, 1) if s.get("tw")}
    return Problem(cls=classes, nodes=nodes, dist_m=matrix(nodes), demand=demand, fleet=fleet, service_s=service, tw=tw)


# --- AMPL: everything below imports amplpy lazily, so the module always imports ----------------------------
def ampl_status(timeout: float = 90.0) -> tuple[bool, str]:
    """Probe in a subprocess: can AMPL start here? A failed start must not take this process down."""
    try:
        r = subprocess.run([sys.executable, "-I", "-c", "from amplpy import AMPL; AMPL()"],
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, "AMPL start timed out"
    if r.returncode == 0:
        return True, "ok"
    last = (r.stderr.strip().splitlines() or ["AMPL could not start"])[-1]
    return False, last[:200]


def _start_ampl():
    try:
        from amplpy import AMPL
        return AMPL()
    except Exception as e:  # amplpy raises RuntimeError when the binary is missing
        raise RuntimeError(HELP) from e


def _records(obj) -> list:
    """amplpy DataFrame or pandas DataFrame -> pandas DataFrame."""
    return obj.to_pandas() if hasattr(obj, "to_pandas") else obj


def _arcs_with_value(ampl) -> list[tuple[int, int]]:
    df = _records(ampl.get_variable("x").get_values())
    arcs = []
    for _, row in df.iterrows():
        if float(row.iloc[-1]) > 0.5:
            arcs.append((int(round(float(row.iloc[0]))), int(round(float(row.iloc[1])))))
    return arcs


@register_solver("ampl")
def _factory():
    return AMPLSolver()


class AMPLSolver:
    name = "ampl"
    classes = CLASSES

    def __init__(self, model: str | Path | None = None, solver: str = "highs"):
        if solver not in SOLVERS:
            raise ValueError(f"solver must be one of {SOLVERS}")
        self.model = Path(model or MODEL)
        self._model_given = model is not None
        self.solver = solver

    def solve(self, problem: Problem, seconds: float = 2.0, seed: int = 1) -> Plan:
        if not set(problem.cls) <= CLASSES:
            raise Unsupported(f"AMPL adapter maps {sorted(CLASSES)} only; got {sorted(problem.cls)}")
        model = self.model if self._model_given or "VRPTW" not in problem.cls else MODEL_VRPTW
        ampl = _start_ampl()
        with tempfile.TemporaryDirectory() as tmp:
            dat = write_dat(problem, Path(tmp) / "cvrp.dat")
            ampl.read(str(model))
            ampl.read_data(str(dat))
            ampl.set_option("solver", self.solver)
            if self.solver == "highs":
                ampl.set_option("highs_options", f"time_limit={float(seconds)} random_seed={int(seed)}")
            else:
                # CBC time-limit option name not verified in this workspace (see README risks)
                ampl.set_option("cbc_options", f"seconds={float(seconds)}")
            t0 = time.perf_counter()
            ampl.solve(verbose=False)
            wall = time.perf_counter() - t0
            result = ampl.solve_result
            if result not in ("solved", "limit", "solved?"):
                raise RuntimeError(f"AMPL solve_result={result!r}; no plan to return")
            arcs = _arcs_with_value(ampl)
            objective = float(ampl.get_objective("total_distance").value())

        routes = routes_from_arcs(arcs, depot=0)
        fleet = problem.fleet[0]
        check = check_plan(problem, routes)
        if not (check["served_once"] and check["capacity_ok"] and check["fleet_ok"] and check.get("windows_ok", True)):
            raise RuntimeError(f"AMPL plan fails the plan check: {check}")
        recomputed = route_distance(problem.dist_m, routes)
        if abs(recomputed - objective) > 1e-3 * max(1.0, objective):
            raise RuntimeError(f"objective {objective:.3f} m does not match the arcs {recomputed:.3f} m")

        ids = [f"{fleet['cls'].upper()}-{k + 1}" for k in range(int(fleet["count"]))]
        padded = routes + [[] for _ in range(len(ids) - len(routes))]
        proven = result == "solved"
        return Plan(routes=dict(zip(ids, padded)), objective=objective, objective_unit="m",
                    solver=f"ampl/{self.solver}", bound=objective if proven else None,
                    status="optimal" if proven else "time_limit",
                    meta={"solve_result": result, "wall_s": round(wall, 3), "seconds_limit": float(seconds),
                          "seed": int(seed), "model": model.name, "plan_check": check})


def solve(problem: Problem, seconds: float = 2.0, seed: int = 1, model=None, solver: str = "highs") -> Plan:
    """Module-level form: solve(problem, seconds, seed, model=None, solver='highs')."""
    return AMPLSolver(model=model, solver=solver).solve(problem, seconds=seconds, seed=seed)


# --- CLI: scenario -> plan.json (used by .github/workflows/solve.yml) ---------------------------------------
def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv=None) -> int:
    import yaml
    from offsim.pipeline import provenance_gaps

    ap = argparse.ArgumentParser(prog="python -m offsim.solve.ampl_adapter", description=__doc__.split("\n")[0])
    ap.add_argument("--scenario", required=True, help="path to scenario.yaml (class CVRP or VRPTW)")
    ap.add_argument("--out", default="out/solve", help="directory for plan.json")
    ap.add_argument("--solver", default="highs", choices=SOLVERS)
    ap.add_argument("--seconds", type=float, default=60.0)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--model", default=None, help="AMPL model (default: ampl/cvrp.mod, ampl/vrptw.mod for VRPTW)")
    ap.add_argument("--great-circle", action="store_true",
                    help="allow a scenario with a world, using great-circle distances (no sea lanes)")
    a = ap.parse_args(argv)

    scenario = Path(a.scenario)
    sc = yaml.safe_load(scenario.read_text())
    gaps = provenance_gaps(sc)
    if gaps:
        print(f"refusing: unsourced values {gaps}", file=sys.stderr)
        return 2
    world = sc.get("world")
    has_world = bool(world) and world != "none"
    if has_world and not a.great_circle:
        print(f"refusing: scenario uses world {world!r} (sea lanes). Vessels route on lanes; "
              "use `python -m offsim run`, or pass --great-circle to solve on straight-line distances.",
              file=sys.stderr)
        return 2

    problem = problem_from_scenario(sc)
    try:
        plan = AMPLSolver(model=a.model, solver=a.solver).solve(problem, seconds=a.seconds, seed=a.seed)
    except (RuntimeError, ValueError, Unsupported) as e:
        print(f"solve failed: {e}", file=sys.stderr)
        return 3
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    model_path = Path(a.model) if a.model else (MODEL_VRPTW if "VRPTW" in problem.cls else MODEL)
    record = {"paper": sc["paper"]["id"], "scenario_sha256": _sha256(scenario), "model_sha256": _sha256(model_path),
              "solver": plan.solver, "status": plan.status, "objective_m": plan.objective,
              "bound_m": plan.bound, "routes": plan.routes,
              "distance_basis": "great-circle (no sea lanes)" if has_world else "great-circle",
              "world": world if has_world else None, "run_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "meta": plan.meta}
    (out / "plan.json").write_text(json.dumps(record, indent=1, default=float))
    print(f"[{record['paper']}] {plan.solver} {plan.status} · {plan.objective / 1000:.2f} km · "
          f"{sum(1 for r in plan.routes.values() if r)} route(s) -> {out / 'plan.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
