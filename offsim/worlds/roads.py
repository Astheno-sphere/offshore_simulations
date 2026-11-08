"""Road network for land logistics: trucks, vans and workers drive on real roads, not straight lines.

A directed graph (networkx, BSD) built from OSM road LineStrings (the `roads` layer written by
`offsim.worlds.osm`, i.e. `data/worlds/<world>/osm/roads.geojson`). Same call shape as `offsim.worlds.sealanes.SeaGraph`
so the pipeline can swap graphs, with one addition: a time matrix and a per-vertex time profile.

    rg = RoadGraph("data/worlds/molde/osm/roads.geojson")        # or a GeoDataFrame
    nodes = rg.snap(nodes_lonlat)                                  # onto the nearest road; rg.snap_m = metres moved
    legs, dist_m, time_s = rg.legs(nodes)                          # {(i, j): [(lon, lat), ...]} for every ordered pair i != j
    rg.leg_profile[(i, j)]                                         # cumulative seconds at each vertex of legs[(i, j)]

SPEC (what this module promises; tests/test_road.py checks each line)
- Input: LineString/MultiLineString features with a `highway` tag; optional `maxspeed`, `oneway`, `junction`. The network
  must be NODED at junctions (pyrosm / osmnx output is: ways are split where they meet). Two roads that merely cross
  (bridge, tunnel) share no endpoint and therefore no junction.
- Edge length: geodesic metres on WGS84 (pyproj.Geod), summed over the polyline. Edge time = length / speed. The contract's
  KPIs use a sphere (haversine), which reads about 0.3 % shorter than WGS84 at 62 N: well inside the 1 % of gate 2.
- Speed per edge: the `maxspeed` tag when it parses ("50", "50 mph", "30;50" -> the smallest number), else the default
  for the `highway` class (DEFAULT_SPEED_KPH). A highway class with no default raises ValueError (add it to
  `speed_kph_by_highway`); classes that cannot carry a car (footway, path, cycleway, steps, ...) are dropped and counted
  in `rg.stats["dropped_non_driving"]`. `rg.stats["default_speed_share"]` says how much of the network ran on defaults.
- Direction: oneway = yes/true/1 (forward) or -1/reverse (backward); roundabouts (`junction` = roundabout|circular)
  are forward-only. Everything else is two-way. The graph is a DiGraph; parallel roads between the same two junctions
  keep the faster one for routing (all of them stay available for snapping).
- snap(nodes): each point moves to the nearest point ON a road (not just the nearest junction), restricted to the largest
  strongly connected component so a depot is never stranded on an island or a one-way dead end. A point farther than
  `max_snap_m` (default 2000 m) from such a road raises ValueError instead of teleporting silently.
- legs(nodes): fastest route (Dijkstra on time; `weight="length"` for shortest) between every ordered pair, as geometry that
  follows the road polylines exactly, with distance (m) and time (s) matrices. The matrices are NOT symmetric when
  one-way streets matter. An unreachable pair raises ValueError. Two points on the same road segment travel directly along
  it when its direction allows.

NOT modelled (the engine and docs say so): turn restrictions and turn penalties, traffic lights, congestion, time-of-day,
access=private/no tags, vehicle height/weight limits, ferries. Times are free-flow at the limit.

Speed defaults are ASSUMPTIONS. Basis: the Norwegian general speed limits (Statens vegvesen: 50 km/h built-up, 80 km/h
outside built-up areas, 90 and 110 km/h only on signed motorway/expressway stretches; Vegtrafikkloven / skiltforskriften).
They are general limits, not verified per road: a class default replaces the real posted limit only where OSM has no
`maxspeed`. Classes the general limits do not cover (service, track, living_street) are plain assumptions.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import networkx as nx
import numpy as np
from pyproj import Geod

from offsim.contract import haversine_m

GEOD = Geod(ellps="WGS84")
MPH_TO_KPH = 1.609344

DEFAULT_SPEED_SRC = ("Statens vegvesen general speed limits 50/80/90/110 km/h (Vegtrafikkloven, skiltforskriften); "
                     "general limits, not verified per road")
DEFAULT_SPEED_KPH = {
    # signed motorway stretches are 90-110; 90 is the conservative general value
    "motorway": 90.0, "motorway_link": 50.0,
    "trunk": 80.0, "trunk_link": 50.0,
    "primary": 80.0, "primary_link": 50.0,
    "secondary": 80.0, "secondary_link": 50.0,
    "tertiary": 80.0, "tertiary_link": 50.0,
    "unclassified": 80.0,          # rural general limit; built-up streets are usually tagged with maxspeed
    "residential": 50.0,           # built-up general limit
    "road": 50.0,
    # not covered by the general limits: plain assumptions
    "service": 30.0, "track": 30.0, "living_street": 20.0,
}
NON_DRIVING = {"footway", "path", "cycleway", "pedestrian", "steps", "bridleway", "corridor", "platform", "proposed",
               "construction", "elevator", "bus_guideway", "raceway", "escape", "via_ferrata", "razed", "abandoned"}
FORWARD = {"yes", "true", "1"}
BACKWARD = {"-1", "reverse"}
_KEY_DEC = 7                       # junction key = coordinate rounded to 1e-7 degrees (about 1 cm)


def parse_maxspeed_kph(value) -> float:
    """OSM maxspeed -> km/h, NaN when absent or not a number ("signals", "none", "NO:urban"). "50", "50 km/h", "30 mph",
    "30;50" (smallest) are understood."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return float("nan")
    best = []
    for part in str(value).replace(",", ".").split(";"):
        s = part.strip().lower()
        num = ""
        for ch in s:
            if ch.isdigit() or ch == ".":
                num += ch
            else:
                break
        if not num:
            continue
        try:
            x = float(num)
        except ValueError:
            continue
        if "mph" in s:
            x *= MPH_TO_KPH
        if x > 0:
            best.append(x)
    return min(best) if best else float("nan")


def _first_tag(value):
    """pyrosm/GeoJSON may hold a list as a JSON string: '["residential", "service"]' -> 'residential'."""
    if isinstance(value, (list, tuple)):
        return str(value[0]) if value else ""
    s = "" if value is None or (isinstance(value, float) and math.isnan(value)) else str(value).strip()
    if s.startswith("["):
        try:
            arr = json.loads(s)
            return str(arr[0]) if arr else ""
        except ValueError:
            pass
    return s


def _directions(oneway, junction) -> tuple[bool, bool]:
    ow = _first_tag(oneway).lower()
    if ow in FORWARD:
        return True, False
    if ow in BACKWARD:
        return False, True
    if _first_tag(junction).lower() in ("roundabout", "circular"):
        return True, False
    return True, True


class _Edge:
    __slots__ = ("eid", "coords", "cum", "length", "speed_mps", "fwd", "bwd", "u", "v", "from_default")

    def __init__(self, eid, coords, cum, speed_mps, fwd, bwd, u, v, from_default):
        self.eid, self.coords, self.cum, self.length = eid, coords, cum, float(cum[-1])
        self.speed_mps, self.fwd, self.bwd, self.u, self.v, self.from_default = speed_mps, fwd, bwd, u, v, from_default

    def point_at(self, s):
        """(lon, lat) at distance s metres from the u end along the polyline."""
        s = min(max(float(s), 0.0), self.length)
        k = int(np.searchsorted(self.cum, s, side="right") - 1)
        k = min(max(k, 0), len(self.cum) - 2)
        seg = self.cum[k + 1] - self.cum[k]
        f = 0.0 if seg <= 0 else (s - self.cum[k]) / seg
        (x0, y0), (x1, y1) = self.coords[k], self.coords[k + 1]
        return (float(x0 + (x1 - x0) * f), float(y0 + (y1 - y0) * f))

    def sub(self, s0, s1):
        """Polyline from s0 to s1 (either order) with interpolated end points: [(lon, lat), ...] and the cumulative
        distance (m) of each vertex from the start of the sub-line."""
        a, b = (s0, s1) if s0 <= s1 else (s1, s0)
        inner = [i for i in range(len(self.coords)) if a < self.cum[i] < b]
        pts = [self.point_at(a)] + [tuple(map(float, self.coords[i])) for i in inner] + [self.point_at(b)]
        ds = [0.0] + [float(self.cum[i]) - a for i in inner] + [float(b) - a]
        if s0 > s1:
            pts, ds = pts[::-1], [(b - a) - d for d in ds[::-1]]
        return pts, ds


class RoadGraph:
    """Directed road graph with snapping and Dijkstra legs. See the module docstring for the spec."""

    def __init__(self, roads, speed_kph_by_highway: dict | None = None, weight: str = "time", max_snap_m: float = 2000.0):
        if weight not in ("time", "length"):
            raise ValueError("weight must be 'time' (fastest) or 'length' (shortest)")
        import geopandas as gpd

        self.weight = weight
        self.max_snap_m = float(max_snap_m)
        self.speed_kph = {**DEFAULT_SPEED_KPH, **(speed_kph_by_highway or {})}
        self.speed_src = DEFAULT_SPEED_SRC
        gdf = roads if hasattr(roads, "geometry") else gpd.read_file(Path(roads))
        if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(4326)
        gdf = gdf.explode(index_parts=False, ignore_index=True) if len(gdf) else gdf
        self.stats = {"features": int(len(gdf)), "dropped_non_driving": 0, "dropped_degenerate": 0, "edges": 0,
                      "default_speed_edges": 0, "default_speed_share": 0.0, "classes": {}}
        self.edges: list[_Edge] = []
        self._build(gdf)
        if not self.edges:
            raise ValueError("road layer has no drivable LineString features (check data/worlds/<world>/osm/roads.geojson)")
        self.leg_profile: dict = {}
        self.snap_m: list = []
        self._place: dict = {}
        self._make_snap_index()

    # ----------------------------------------------------------------------------------------------- build
    def _build(self, gdf):
        keys, G = {}, nx.DiGraph()

        def junction(xy):
            k = (round(float(xy[0]), _KEY_DEC), round(float(xy[1]), _KEY_DEC))
            return keys.setdefault(k, len(keys))

        cols = set(gdf.columns)
        for _, row in gdf.iterrows():
            geom = row.geometry
            if geom is None or geom.is_empty or geom.geom_type != "LineString":
                self.stats["dropped_degenerate"] += 1
                continue
            hw = _first_tag(row["highway"]) if "highway" in cols else ""
            if hw in NON_DRIVING:
                self.stats["dropped_non_driving"] += 1
                continue
            if hw not in self.speed_kph:
                raise ValueError(f"highway class {hw!r} has no speed: pass speed_kph_by_highway={{{hw!r}: kph}} "
                                 f"(known: {sorted(self.speed_kph)})")
            xy = np.asarray(geom.coords, dtype=float)[:, :2]
            keep = np.r_[True, np.any(np.diff(xy, axis=0) != 0, axis=1)]      # drop repeated vertices
            xy = xy[keep]
            if len(xy) < 2:
                self.stats["dropped_degenerate"] += 1
                continue
            _, _, d = GEOD.inv(xy[:-1, 0], xy[:-1, 1], xy[1:, 0], xy[1:, 1])
            cum = np.r_[0.0, np.cumsum(d)]
            kph = parse_maxspeed_kph(row["maxspeed"]) if "maxspeed" in cols else float("nan")
            from_default = not math.isfinite(kph)
            if from_default:
                kph = self.speed_kph[hw]
            fwd, bwd = _directions(row["oneway"] if "oneway" in cols else None, row["junction"] if "junction" in cols else None)
            e = _Edge(len(self.edges), xy, cum, kph / 3.6, fwd, bwd, junction(xy[0]), junction(xy[-1]), from_default)
            self.edges.append(e)
            self.stats["classes"][hw] = self.stats["classes"].get(hw, 0) + 1
            self.stats["default_speed_edges"] += int(from_default)
            if e.u == e.v or e.length <= 0:
                continue                                        # loops snap but do not connect anything
            t = e.length / e.speed_mps
            for a, b, ok, rev in ((e.u, e.v, e.fwd, False), (e.v, e.u, e.bwd, True)):
                if not ok:
                    continue
                cur = G.get_edge_data(a, b)
                if cur is None or t < cur["t"]:
                    G.add_edge(a, b, t=t, l=e.length, g=(e.eid, e.length, 0.0) if rev else (e.eid, 0.0, e.length))
        self.stats["edges"] = len(self.edges)
        self.stats["default_speed_share"] = self.stats["default_speed_edges"] / max(len(self.edges), 1)
        self.G = G
        self._junction_xy = {i: k for k, i in keys.items()}

    def _make_snap_index(self):
        from shapely.geometry import LineString
        from shapely.strtree import STRtree

        comps = list(nx.strongly_connected_components(self.G)) if self.G.number_of_nodes() else []
        self.core = max(comps, key=len) if comps else set()
        cand = [e for e in self.edges if e.u in self.core and e.v in self.core]
        if not cand:
            raise ValueError("road graph has no strongly connected core (one-way tags may all point one way)")
        self._cand = cand
        allxy = np.vstack([e.coords for e in cand])
        self._lon0, self._lat0 = float(allxy[:, 0].mean()), float(allxy[:, 1].mean())
        self._kx = 111_320.0 * math.cos(math.radians(self._lat0))
        self._ky = 110_574.0
        self._tree = STRtree([LineString(self._local(e.coords)) for e in cand])
        self.stats["core_nodes"] = len(self.core)
        self.stats["total_nodes"] = self.G.number_of_nodes()

    def _local(self, lonlat):
        a = np.asarray(lonlat, dtype=float)
        return np.column_stack([(a[:, 0] - self._lon0) * self._kx, (a[:, 1] - self._lat0) * self._ky])

    # ----------------------------------------------------------------------------------------------- snap
    def _project(self, lon, lat):
        """Nearest point on the core network: (edge, s along edge in m, (lon, lat), snap distance in m)."""
        from shapely.geometry import Point

        p = self._local([(lon, lat)])[0]
        e = self._cand[int(self._tree.nearest(Point(p[0], p[1])))]
        c = self._local(e.coords)
        a, b = c[:-1], c[1:]
        ab = b - a
        L2 = np.maximum((ab ** 2).sum(axis=1), 1e-12)
        t = np.clip(((p - a) * ab).sum(axis=1) / L2, 0.0, 1.0)
        proj = a + ab * t[:, None]
        k = int(np.argmin(((proj - p) ** 2).sum(axis=1)))
        x0, y0 = e.coords[k]
        x1, y1 = e.coords[k + 1]
        q = (float(x0 + (x1 - x0) * t[k]), float(y0 + (y1 - y0) * t[k]))
        s = float(e.cum[k] + (e.cum[k + 1] - e.cum[k]) * t[k])
        return e, s, q, float(haversine_m(lon, lat, q[0], q[1]))

    def snap(self, nodes_lonlat):
        """Move each (lon, lat) onto the nearest road point of the largest strongly connected component.
        Returns the snapped list of (lon, lat); `self.snap_m` holds the distance moved per point (metres, rounded 0.1).
        Raises ValueError when a point is farther than `max_snap_m` from the network."""
        out, moved = [], []
        for lon, lat in nodes_lonlat:
            e, s, q, d = self._project(float(lon), float(lat))
            if d > self.max_snap_m:
                raise ValueError(f"({lon:.5f}, {lat:.5f}) is {d:.0f} m from the nearest road (max_snap_m={self.max_snap_m:.0f}); "
                                 "wrong coordinates, or the roads layer does not cover it")
            self._place[q] = (e.eid, s)
            out.append(q)
            moved.append(round(d, 1))
        self.snap_m = moved
        return out

    def _placement(self, lonlat):
        key = (float(lonlat[0]), float(lonlat[1]))
        if key not in self._place:
            self.snap([key])
            if key not in self._place:                       # the point was not exactly on the network: use its snap
                e, s, q, _ = self._project(*key)
                self._place[key] = (e.eid, s)
        eid, s = self._place[key]
        return self.edges[eid], s

    # ----------------------------------------------------------------------------------------------- legs
    def legs(self, nodes_lonlat):
        """All ordered-pair routes. Returns (legs, dist_m, time_s):
        legs[(i, j)] = [(lon, lat), ...] for i != j (both directions: one-way streets differ);
        dist_m, time_s = NxN float arrays (zero diagonal). `self.leg_profile[(i, j)]` = cumulative seconds at each
        vertex of legs[(i, j)] (free-flow at the edge speeds). Raises ValueError if any pair is unreachable."""
        n = len(nodes_lonlat)
        place = [self._placement(p) for p in nodes_lonlat]
        wkey = "t" if self.weight == "time" else "l"
        G = self.G
        names = [("snap", i) for i in range(n)]
        legs, profile = {}, {}
        dist, time = np.zeros((n, n)), np.zeros((n, n))
        try:
            for i, (e, s) in enumerate(place):
                X = names[i]
                G.add_node(X)
                for rev, (src, dst, ok) in enumerate(((e.u, e.v, e.fwd), (e.v, e.u, e.bwd))):
                    if not ok:
                        continue
                    # travelling u->v: u->X over [0, s], X->v over [s, L]; v->u: v->X over [L, s], X->u over [s, 0]
                    if not rev:
                        self._temp_arc(G, e, src, X, 0.0, s)
                        self._temp_arc(G, e, X, dst, s, e.length)
                    else:
                        self._temp_arc(G, e, src, X, e.length, s)
                        self._temp_arc(G, e, X, dst, s, 0.0)
            for i in range(n):
                pred, d = nx.dijkstra_predecessor_and_distance(G, names[i], weight=wkey)
                for j in range(n):
                    if i == j:
                        continue
                    direct = self._direct(place[i], place[j])
                    if direct is not None:
                        arcs = [direct]
                    else:
                        if names[j] not in d:
                            raise ValueError(f"no drivable route from node {i} to node {j} "
                                             f"({nodes_lonlat[i]} -> {nodes_lonlat[j]}): one-way streets or a gap in the roads layer")
                        path, cur = [names[j]], names[j]
                        while cur != names[i]:
                            cur = pred[cur][0]
                            path.append(cur)
                        path.reverse()
                        arcs = [G.edges[a, b]["g"] for a, b in zip(path, path[1:])]
                    pts, cum_t, cum_l = self._assemble(arcs)
                    legs[(i, j)] = pts
                    profile[(i, j)] = cum_t
                    dist[i, j], time[i, j] = cum_l[-1], cum_t[-1]
        finally:
            G.remove_nodes_from(names)
        self.leg_profile = profile
        return legs, dist, time

    @staticmethod
    def _temp_arc(G, e, a, b, s0, s1):
        ln = abs(s1 - s0)
        G.add_edge(a, b, t=ln / e.speed_mps, l=ln, g=(e.eid, float(s0), float(s1)))

    @staticmethod
    def _direct(pa, pb):
        (ea, sa), (eb, sb) = pa, pb
        if ea.eid != eb.eid:
            return None
        if sb >= sa and ea.fwd:
            return (ea.eid, sa, sb)
        if sb <= sa and ea.bwd:
            return (ea.eid, sa, sb)
        return None

    def _assemble(self, arcs):
        pts, cum_t, cum_l = [], [], []
        t0 = l0 = 0.0
        for eid, s0, s1 in arcs:
            e = self.edges[eid]
            p, ds = e.sub(s0, s1)
            for q, d in zip(p, ds):
                if pts and q == pts[-1]:
                    continue
                pts.append(q)
                cum_l.append(l0 + d)
                cum_t.append(t0 + d / e.speed_mps)
            l0 += ds[-1]
            t0 += ds[-1] / e.speed_mps
        if len(pts) == 1:                                    # zero-length leg: two identical points, zero time
            pts, cum_t, cum_l = pts * 2, [cum_t[0], cum_t[0]], [cum_l[0], cum_l[0]]
        # the last cumulative value must be the true total even when the last arc repeated a vertex
        cum_t[-1], cum_l[-1] = max(cum_t[-1], t0), max(cum_l[-1], l0)
        return pts, cum_t, cum_l

    # ----------------------------------------------------------------------------------------------- info
    def describe(self) -> dict:
        """What a report records about this graph (JSON-safe)."""
        return {"graph": "roads", "weight": self.weight, "speed_basis": self.speed_src,
                "speed_defaults_are_assumptions": True, "max_snap_m": self.max_snap_m,
                **{k: v for k, v in self.stats.items()}}
