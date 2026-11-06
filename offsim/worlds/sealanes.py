"""Sea lanes from a coastline: vessels go around land, not through it.

A grid graph over open water (in UTM metres), shortest paths with a clearance from the shore,
then "string pulling" so paths are straight wherever the water allows. Distances from the same
paths feed the solver, so the replay sails exactly what was optimised (corrector gate 2 holds).

    sea = SeaGraph(land_lonlat, bbox=(w, s, e, n), spacing_m=300, clearance_m=80)
    ports = sea.snap(nodes)                 # move quays onto the nearest navigable water
    legs, dist = sea.legs(ports)            # {(i, j): [(lon, lat), ...]}, metres matrix

Replace or refine with Kystverket reference routes when that data is fetched (catalog: kystverket-routes).
"""
from __future__ import annotations

import networkx as nx
import numpy as np
from pyproj import Transformer
from scipy.spatial import cKDTree
from shapely.geometry import LineString, Point, box
from shapely.ops import nearest_points, transform
from shapely.prepared import prep

UTM = "EPSG:32632"


class SeaGraph:
    def __init__(self, land, bbox, spacing_m=300.0, clearance_m=80.0):
        self.fwd = Transformer.from_crs(4326, UTM, always_xy=True).transform
        self.inv = Transformer.from_crs(UTM, 4326, always_xy=True).transform
        frame = transform(self.fwd, box(*bbox))
        self.land = transform(self.fwd, land).intersection(frame.buffer(5 * spacing_m))
        self.block = self.land.buffer(clearance_m)          # stay this far off the shore
        self._pb = prep(self.block)
        self.clearance = clearance_m
        x0, y0, x1, y1 = frame.bounds
        xs, ys = np.arange(x0, x1, spacing_m), np.arange(y0, y1, spacing_m)
        pts = [(x, y) for x in xs for y in ys if not self._pb.contains(Point(x, y))]
        self.xy = np.array(pts)
        self.tree = cKDTree(self.xy)
        G = nx.Graph()
        idx = {p: i for i, p in enumerate(pts)}
        steps = [(1, 0), (0, 1), (1, 1), (1, -1), (2, 1), (1, 2), (2, -1), (1, -2)]
        for (x, y), i in idx.items():
            for dx, dy in steps:
                q = (x + dx * spacing_m, y + dy * spacing_m)
                j = idx.get(q)
                if j is not None and not self._pb.intersects(LineString([(x, y), q])):
                    G.add_edge(i, j, w=float(np.hypot(dx, dy) * spacing_m))
        main = max(nx.connected_components(G), key=len)       # drop isolated ponds and harbour pockets
        self.G = G.subgraph(main).copy()
        keep = np.array(sorted(main))
        self._ids = keep
        self.tree = cKDTree(self.xy[keep])
        self.snap_m = []

    def _clear(self, a, b):
        return not self._pb.intersects(LineString([a, b]))

    def snap(self, nodes_lonlat):
        """Move each point that lies on land or within the clearance onto the nearest navigable water."""
        out = []
        for lon, lat in nodes_lonlat:
            p = Point(self.fwd(lon, lat))
            if self._pb.contains(p) or self.block.boundary.distance(p) < 1:
                q = nearest_points(self.block.boundary, p)[0]
                v = np.array(q.coords[0]) - np.array(p.coords[0])
                n = np.linalg.norm(v) or 1.0
                q = Point(np.array(q.coords[0]) + v / n * 15.0)   # 15 m past the clearance line
                p0, p = p, q
            else:
                p0 = p
            if not self._attach((p.x, p.y)):                    # a pocket cut off from the open fjord
                _, i = self.tree.query((p.x, p.y))
                p = Point(self.xy[self._ids[i]])
            self.snap_m.append(round(float(p.distance(Point(self.fwd(lon, lat)))), 1))
            out.append(self.inv(p.x, p.y))
        return out

    def _attach(self, p):
        """Graph nodes visible from p (straight line clear of the blocked zone); widen the search for
        quays in narrow harbours where the grid is far away."""
        for k in (12, 60, 300):
            d, ii = self.tree.query(p, k=min(k, len(self._ids)))
            vis = [(int(self._ids[i]), float(di)) for di, i in zip(np.atleast_1d(d), np.atleast_1d(ii))
                   if self._clear(p, tuple(self.xy[self._ids[i]]))]
            if vis:
                return vis[:12]
        return []

    def path(self, a_lonlat, b_lonlat):
        a, b = self.fwd(*a_lonlat), self.fwd(*b_lonlat)
        if self._clear(a, b):
            route = [a, b]
        else:
            G = self.G.copy()
            for name, p in (("A", a), ("B", b)):
                vis = self._attach(p)
                if not vis:
                    raise ValueError(f"{name} {p} cannot see open water; snap() it first or lower clearance")
                for i, di in vis:
                    G.add_edge(name, i, w=di)
            nodes = nx.shortest_path(G, "A", "B", weight="w")
            route = [a] + [tuple(self.xy[n]) for n in nodes[1:-1]] + [b]
            route = self._pull(route)
        return [self.inv(x, y) for x, y in route]

    def _pull(self, route):
        """Greedy string pulling: from each kept point jump to the farthest point still in clear water."""
        out, i = [route[0]], 0
        while i < len(route) - 1:
            j = len(route) - 1
            while j > i + 1 and not self._clear(route[i], route[j]):
                j -= 1
            out.append(route[j])
            i = j
        return out

    def legs(self, nodes_lonlat):
        """All-pairs sea paths and their lengths in metres (feed `dist` to the solver, `legs` to replay)."""
        n = len(nodes_lonlat)
        legs, dist = {}, np.zeros((n, n))
        for i in range(n):
            for j in range(i + 1, n):
                p = self.path(nodes_lonlat[i], nodes_lonlat[j])
                xy = [self.fwd(*q) for q in p]
                d = float(sum(np.hypot(x1 - x0, y1 - y0) for (x0, y0), (x1, y1) in zip(xy, xy[1:])))
                legs[(i, j)] = p
                dist[i, j] = dist[j, i] = d
        return legs, dist
