"""PyVRP behind one small, tested interface: nodes in lon/lat, metres and seconds out.

Every trap we have hit with PyVRP lives here, once, so scenarios never touch its index conventions:
- `ScheduledActivity.is_client` is a method in 0.14 (an attribute read is always truthy).
- a client's `idx` counts clients only: node = idx + number_of_depots.
- time windows (VRPTW): integer seconds. Durations are rounded UP, window opens rounded up, window closes rounded down,
  so a PyVRP-feasible plan is also feasible in the continuous-time replay (never the other way round).
"""
from __future__ import annotations

import math

import numpy as np
from pyvrp import Model
from pyvrp.stop import MaxRuntime

from offsim.contract import haversine_m


def matrix(nodes):
    """Great-circle metres between all (lon, lat) nodes. Swap for a sea-lane matrix when lanes exist."""
    lon, lat = np.array(nodes).T
    return haversine_m(lon[:, None], lat[:, None], lon[None, :], lat[None, :])


def solve_cvrp(nodes, demand, n_vehicles, capacity, speed_mps, seconds=2.0, dist=None, seed=1):
    """nodes[0] is the depot; demand: {node: units}. Returns (routes as node lists without depot,
    objective in metres). Raises if PyVRP's best plan is infeasible: never pass on an infeasible plan."""
    D = matrix(nodes) if dist is None else np.asarray(dist)
    m = Model()
    m.add_vehicle_type(num_available=n_vehicles, capacity=capacity)
    locs = [m.add_location(x=int(x * 1e5), y=int(y * 1e5)) for x, y in nodes]
    m.add_depot(locs[0])
    for i, loc in enumerate(locs[1:], 1):
        m.add_client(loc, delivery=int(demand[i]))
    for i, a in enumerate(locs):
        for j, b in enumerate(locs):
            m.add_edge(a, b, distance=int(round(D[i, j])), duration=int(round(D[i, j] / speed_mps)))
    res = m.solve(stop=MaxRuntime(seconds), seed=seed, display=False)
    if not res.is_feasible():
        raise RuntimeError("PyVRP returned an infeasible plan")
    routes = [[a.idx + 1 for a in r if a.is_client()] for r in res.best.routes()]
    return routes, float(res.cost())


def route_times(dist, speed_mps, route, service=None, tw=None, depot=0):
    """Continuous-time schedule of one route as the replay engine runs it (offsim/sim/replay.py): leave the depot at
    t = 0, drive d / speed, wait until the window opens, serve, drive on. Returns [(node, arrival_s, start_s, end_s)].
    Service starts at max(arrival, early); the window is met when start <= late."""
    service, tw = service or {}, tw or {}
    t, here, out = 0.0, depot, []
    for b in route:
        arr = t + float(dist[here][b]) / speed_mps
        start = max(arr, float(tw.get(b, (0.0, None))[0]))
        end = start + float(service.get(b, 0.0))
        out.append((b, arr, start, end))
        t, here = end, b
    return out


def windows_violations(dist, speed_mps, routes, service=None, tw=None, depot=0, tol_s=1e-6):
    """[(node, start_s, late_s)] for every stop whose service starts after its window closes. Empty = feasible."""
    tw = tw or {}
    bad = []
    for r in routes:
        for b, _, start, _ in route_times(dist, speed_mps, r, service, tw, depot):
            late = tw.get(b, (0.0, None))[1]
            if late is not None and start > late + tol_s:
                bad.append((b, start, float(late)))
    return bad


def solve_vrptw(nodes, demand, n_vehicles, capacity, speed_mps, service=None, tw=None, seconds=2.0, dist=None, seed=1):
    """CVRP plus time windows. nodes[0] is the depot (no window, vehicles leave at t = 0). service: {node: s};
    tw: {node: (early_s, late_s)}; both in seconds. Objective: total distance (metres), as in solve_cvrp.
    Returns (routes as node lists without depot, objective in metres). Raises RuntimeError when PyVRP's best plan is
    infeasible (windows cannot be met with this fleet): never pass on an infeasible plan."""
    service, tw = service or {}, tw or {}
    D = matrix(nodes) if dist is None else np.asarray(dist)
    m = Model()
    m.add_vehicle_type(num_available=n_vehicles, capacity=capacity)
    locs = [m.add_location(x=int(x * 1e5), y=int(y * 1e5)) for x, y in nodes]
    m.add_depot(locs[0])
    for i, loc in enumerate(locs[1:], 1):
        early, late = tw.get(i, (0, None))
        kw = {"tw_early": int(math.ceil(early))}
        if late is not None:
            kw["tw_late"] = int(math.floor(late))
        m.add_client(loc, delivery=int(demand[i]), service_duration=int(math.ceil(service.get(i, 0.0))), **kw)
    for i, a in enumerate(locs):
        for j, b in enumerate(locs):
            m.add_edge(a, b, distance=int(round(D[i, j])), duration=int(math.ceil(D[i, j] / speed_mps - 1e-9)))
    res = m.solve(stop=MaxRuntime(seconds), seed=seed, display=False)
    if not res.is_feasible():
        raise RuntimeError("PyVRP found no plan that meets the capacity and the time windows")
    routes = [[a.idx + 1 for a in r if a.is_client()] for r in res.best.routes()]
    return routes, float(res.cost())
