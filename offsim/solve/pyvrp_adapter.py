"""PyVRP behind one small, tested interface: nodes in lon/lat, metres and seconds out.

Every trap we have hit with PyVRP lives here, once, so scenarios never touch its index conventions:
- `ScheduledActivity.is_client` is a method in 0.14 (an attribute read is always truthy).
- a client's `idx` counts clients only: node = idx + number_of_depots.
"""
from __future__ import annotations

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
