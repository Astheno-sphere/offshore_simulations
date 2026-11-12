"""searoute-py (Apache-2.0, imported) behind the same `(legs, dist_m, time_s)` contract as the other graphs.

searoute routes on a global shipping-lane network (Eurostat MARNET, ~20 km mesh). Its own README calls the output
visualisation, not navigation. It is therefore a COARSE reference for long legs and a cross-check on our own
`offsim.worlds.sealanes.SeaGraph`; it never replaces SeaGraph. It knows nothing of our quays, clearance or
bbox, and it has no land input: it cannot be told to avoid anything.

    g = SearouteGraph(speed_mps=7.0)
    legs, dist_m, time_s = g.legs([(5.30, 60.40), (5.60, 58.97)])      # {(i, j): [(lon, lat), ...]} ordered pairs
    out = compare_with_seagraph(sea, a, b)                              # the disagreement as numbers, no tuning

Distance is recomputed here from the returned polyline with `contract.haversine_m` (endpoints included), so it is
measured the same way as every other leg; searoute's own `length` is kept in `last_props` for the record.
`time_s = dist_m / speed_mps` with OUR speed (searoute's `duration_hours` uses its own 24 kn default and is ignored).
"""
from __future__ import annotations

import numpy as np

from offsim.contract import haversine_m

KN_TO_MPS = 1852.0 / 3600.0


def _polyline_m(pts) -> float:
    a = np.asarray(pts, dtype=float)
    return float(haversine_m(a[:-1, 0], a[:-1, 1], a[1:, 0], a[1:, 1]).sum()) if len(a) > 1 else 0.0


class SearouteGraph:
    def __init__(self, speed_mps: float = 12.0 * KN_TO_MPS, restrictions=None):
        if speed_mps <= 0:
            raise ValueError("speed_mps must be positive")
        self.speed_mps = float(speed_mps)
        self.restrictions = [] if restrictions is None else list(restrictions)   # searoute default blocks the NW passage
        self.last_props: dict = {}

    def path(self, a_lonlat, b_lonlat):
        """[(lon, lat), ...] from a to b along shipping lanes, endpoints included exactly as given."""
        from searoute import searoute

        feat = searoute(list(map(float, a_lonlat)), list(map(float, b_lonlat)), units="m",
                        restrictions=self.restrictions)
        self.last_props = dict(feat.properties or {})
        pts = [tuple(map(float, p[:2])) for p in feat.geometry.coordinates]
        if not pts:
            raise ValueError(f"searoute returned no geometry for {a_lonlat} -> {b_lonlat}")
        a, b = tuple(map(float, a_lonlat)), tuple(map(float, b_lonlat))
        lane = list(pts)                                     # searoute snaps both ends to its nearest lane node
        self.last_props["lane_m"] = _polyline_m(lane)
        self.last_props["stub_m"] = (float(haversine_m(*a, *lane[0])) + float(haversine_m(*lane[-1][:2], *b)))
        if pts[0] != a:
            pts.insert(0, a)
        if pts[-1] != b:
            pts.append(b)
        return pts

    def legs(self, nodes_lonlat):
        """All ordered-pair routes. Returns (legs, dist_m, time_s): legs {(i, j): [(lon, lat), ...]} for i != j,
        dist_m and time_s NxN float arrays with a zero diagonal (same shape as RoadGraph.legs)."""
        n = len(nodes_lonlat)
        legs, dist, time = {}, np.zeros((n, n)), np.zeros((n, n))
        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                if j < i:                                    # the lane network is undirected: reuse, reversed
                    legs[(i, j)] = legs[(j, i)][::-1]
                    dist[i, j], time[i, j] = dist[j, i], time[j, i]
                    continue
                p = self.path(nodes_lonlat[i], nodes_lonlat[j])
                legs[(i, j)] = p
                dist[i, j] = _polyline_m(p)
                time[i, j] = dist[i, j] / self.speed_mps
        return legs, dist, time


def compare_with_seagraph(sea, a_lonlat, b_lonlat, speed_mps: float = 12.0 * KN_TO_MPS) -> dict:
    """Both routers on one pair; the disagreement as numbers. Neither side is tuned to the other.

    `sea` is a built `SeaGraph` (the caller supplies land). Both endpoints are first snapped by `sea.snap` (that is how
    we use it for quays); searoute gets the SNAPPED points too, so the pair is the same. Returns
    {seagraph_m, searoute_m (lane + straight stubs to our endpoints), searoute_lane_m (lane node to lane node, what
    searoute reports natively), stub_m (the two straight stubs, which ignore land), great_circle_m, diff_m, ratio
    (searoute / seagraph), rel_diff ((searoute - seagraph) / seagraph), lane_rel_diff (lane only vs seagraph),
    seagraph_detour (seagraph / great circle), searoute_detour, snap_m}."""
    a, b = sea.snap([tuple(a_lonlat), tuple(b_lonlat)])
    _, d = sea.legs([a, b])
    sg = float(d[0, 1])
    g = SearouteGraph(speed_mps)
    sr = _polyline_m(g.path(a, b))
    gc = float(haversine_m(a[0], a[1], b[0], b[1]))
    return {"seagraph_m": sg, "searoute_m": sr, "searoute_lane_m": float(g.last_props["lane_m"]), "searoute_native_m": float(g.last_props.get("length", float("nan"))),
            "stub_m": float(g.last_props["stub_m"]), "lane_rel_diff": (g.last_props["lane_m"] - sg) / sg,
            "great_circle_m": gc, "diff_m": sr - sg, "ratio": sr / sg, "rel_diff": (sr - sg) / sg,
            "seagraph_detour": sg / gc, "searoute_detour": sr / gc, "snap_m": list(sea.snap_m)}
