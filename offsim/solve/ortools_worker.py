"""OR-Tools routing model, run as a SEPARATE PROCESS by `offsim.solve.ortools_solver` (JSON on stdin, JSON on stdout).

Why a process: `ortools` and `highspy` (used by the pyomo and whelp solvers) each ship their own HiGHS symbols, and
whichever is imported second in one interpreter fails with `undefined symbol`. A subprocess keeps both usable in the
same run (gate 1b certifies a heuristic plan with pyomo after solving with another solver). This file imports nothing
from `offsim`, so it also runs under `python -I`.

Input  : {"dist": NxN int metres, "n_veh", "cap", "load": [delta per node, int], "seconds",
          "tt": NxN int seconds | null, "svc": [int s] | null, "tw": {node: [lo, hi]} | null, "horizon": int | null,
          "pairs": {pickup: delivery} | null, "first": str, "meta": str}
Output : {"ok": true, "routes": [[node, ...] per vehicle, depot excluded]} or {"ok": false, "error": str}
"""
from __future__ import annotations

import json
import sys


def build_and_solve(req: dict) -> dict:
    from ortools.constraint_solver import pywrapcp, routing_enums_pb2

    D, n, n_veh, cap = req["dist"], len(req["dist"]), int(req["n_veh"]), int(req["cap"])
    manager = pywrapcp.RoutingIndexManager(n, n_veh, 0)
    routing = pywrapcp.RoutingModel(manager)
    node_of = manager.IndexToNode

    dist_cb = routing.RegisterTransitCallback(lambda a, b: D[node_of(a)][node_of(b)])
    routing.SetArcCostEvaluatorOfAllVehicles(dist_cb)

    delta = req["load"]
    load_cb = routing.RegisterUnaryTransitCallback(lambda a: delta[node_of(a)])
    routing.AddDimensionWithVehicleCapacity(load_cb, 0, [cap] * n_veh, True, "Load")

    if req.get("tt") is not None:                      # VRPTW: service-start times, waiting allowed (slack)
        tt, svc, horizon = req["tt"], req["svc"], int(req["horizon"])
        time_cb = routing.RegisterTransitCallback(lambda a, b: svc[node_of(a)] + tt[node_of(a)][node_of(b)])
        routing.AddDimension(time_cb, horizon, horizon, True, "Time")
        time = routing.GetDimensionOrDie("Time")
        for node, (lo, hi) in (req.get("tw") or {}).items():
            if lo > hi:
                return {"ok": False, "error": f"window of node {node} holds no whole second: [{lo}, {hi}]"}
            time.CumulVar(manager.NodeToIndex(int(node))).SetRange(int(lo), int(hi))

    if req.get("pairs"):                               # PDP: same vehicle, pickup strictly before delivery
        order_cb = routing.RegisterUnaryTransitCallback(lambda a: 1)
        routing.AddDimension(order_cb, 0, n + 1, True, "Order")
        order = routing.GetDimensionOrDie("Order")
        solver = routing.solver()
        for p, d in req["pairs"].items():
            ip, idx_d = manager.NodeToIndex(int(p)), manager.NodeToIndex(int(d))
            routing.AddPickupAndDelivery(ip, idx_d)
            solver.Add(routing.VehicleVar(ip) == routing.VehicleVar(idx_d))
            solver.Add(order.CumulVar(ip) < order.CumulVar(idx_d))

    sp = pywrapcp.DefaultRoutingSearchParameters()
    sp.first_solution_strategy = getattr(routing_enums_pb2.FirstSolutionStrategy, req["first"])
    sp.local_search_metaheuristic = getattr(routing_enums_pb2.LocalSearchMetaheuristic, req["meta"])
    sp.time_limit.FromMilliseconds(max(1, int(round(float(req["seconds"]) * 1000))))
    sol = routing.SolveWithParameters(sp)
    if sol is None:
        return {"ok": False, "error": "no feasible plan"}
    routes = []
    for v in range(n_veh):
        idx, r = routing.Start(v), []
        while not routing.IsEnd(idx):
            if node_of(idx):
                r.append(node_of(idx))
            idx = sol.Value(routing.NextVar(idx))
        routes.append(r)
    return {"ok": True, "routes": routes}


if __name__ == "__main__":
    try:
        out = build_and_solve(json.load(sys.stdin))
    except Exception as exc:                           # noqa: BLE001 - reported to the parent, which raises
        out = {"ok": False, "error": f"{type(exc).__name__}: {exc}", "crash": True}
    json.dump(out, sys.stdout)
