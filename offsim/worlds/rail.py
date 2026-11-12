"""Rail network for train and tram modelling: a graph over the OSM `rail` layer, with station snapping.

Same call shape as `offsim.worlds.roads.RoadGraph` (it IS a RoadGraph subclass: snapping, Dijkstra legs and geometry
assembly are shared; only the build rules differ), so the pipeline can swap graphs.

    rg = RailGraph("data/worlds/molde/osm/rail.geojson")          # or a GeoDataFrame
    nodes = rg.snap(nodes_lonlat)                                  # onto the nearest track; rg.snap_m = metres moved
    legs, dist_m, time_s = rg.legs(nodes)                          # {(i, j): [(lon, lat), ...]} for every ordered pair i != j
    st = rg.snap_stations(stations_gdf)                            # DataFrame: station, node_lon/lat, snap_m, snapped
    pts, node_idx, dist_m, time_s = rg.chain(nodes)                # consecutive stops only (what a GTFS trip needs)
    rg = load_world_rail("data/worlds/molde")                      # RailGraph, or None when osm/rail.geojson is absent

SPEC (tests/test_rail.py checks each line)
- Input: LineString/MultiLineString features with a `railway` tag in rail | light_rail | subway | tram. Other `railway`
  values (abandoned, disused, construction, proposed, preserved, narrow_gauge, funicular, miniature, monorail, platform,
  ...) are dropped and counted in `stats["dropped_other_railway"]`. The layer is NOT assumed noded: lines are split at
  every vertex that two different lines share (switches, crossings of mapped junction nodes), so a branch leaves a
  main line at the node where OSM puts the switch. Lines that merely cross without a shared vertex (a bridge over a
  track) stay unconnected.
- Edge length: geodesic metres on WGS84. Edge time = length / speed. Rail is bidirectional (no oneway tags are read;
  signalled single-direction running on double track is not modelled).
- Service tracks: `service` in yard | siding | spur is EXCLUDED unless `include_service=True` (counted in
  `stats["excluded_service"]`). `service=crossover` stays (it joins the main tracks).
  Tunnels and bridges are kept and carried in `edge_attrs` (and counted in stats).
- Speed per edge: the `maxspeed` tag when it parses (km/h; `roads.parse_maxspeed_kph`), else DEFAULT_SPEED_KPH by
  `railway`/`usage`. `stats["default_speed_share"]` says how much of the network ran on defaults.
- snap(nodes): nearest point ON a track (not just a junction), over every included edge (rail networks inside one bbox
  are often disconnected, e.g. a tram next to a main line, so there is no "core" restriction: an unreachable pair is
  reported by `legs`). Farther than `max_snap_m` (default 500 m) raises ValueError.
- legs(nodes): fastest route between every ordered pair, geometry along the track polylines. Unreachable pair raises
  ValueError (never a straight line). The matrices are symmetric.
- snap_stations(stations): station points (or polygon centroids) -> nearest track point with the distance REPORTED
  (the rail twin of vessel quay snaps). A station beyond `max_snap_m` gets snapped=False and NaN node (strict=True raises).

NOT modelled: electrification as a constraint (the tag is kept, never used to route or to power anything), gauge
(kept; all of Norway is 1435 mm), gradients and curve speed, signalling, block sections, single-track conflicts,
platform occupancy, dwell models, switch speeds, speed profiles (acceleration), freight paths. Times are free-flow at the limit.

Speed defaults are ASSUMPTIONS (`assumption: true` in any scenario that relies on them). Reference points: Norwegian
mainline passenger services run mostly 100-130 km/h with 160 km/h on the newest double-track sections and 210 km/h
on Gardermobanen/Norske tog class 71-74 rolling stock limits (Bane NOR network statement and Norske tog fleet data;
figures recalled, NOT verified in this workspace: no access to banenor.no). Oslo T-bane is signalled for 70-80 km/h and
the Oslo tram runs 40-60 km/h (Ruter; not verified). The class defaults below are conservative single numbers,
not per-line values: where a scenario needs the real line speed, tag `maxspeed` in the data or pass
`speed_kph_by_class`.
"""
from __future__ import annotations

import math
from pathlib import Path

import networkx as nx
import numpy as np

from offsim.worlds.roads import GEOD, RoadGraph, _Edge, _first_tag, parse_maxspeed_kph

DEFAULT_SPEED_SRC = ("ASSUMPTION (assumption: true): conservative class defaults; Norwegian mainline 100-130 km/h "
                     "(Bane NOR / Norske tog, unverified here), T-bane 70, tram 40; real limits only where OSM has maxspeed")
RAILWAYS = ("rail", "light_rail", "subway", "tram")
EXCLUDED_SERVICE = {"yard", "siding", "spur"}
DEFAULT_SPEED_KPH = {
    "rail:main": 120.0,        # usage=main (inter-city, regional)
    "rail:branch": 80.0,       # usage=branch
    "rail:industrial": 40.0,   # usage=industrial / military / tourism
    "rail": 80.0,              # untagged usage
    "light_rail": 70.0,        # Oslo T-bane class (Ruter), assumption
    "subway": 70.0,
    "tram": 40.0,              # urban tram, assumption
}
_USAGE_KEY = {"main": "rail:main", "branch": "rail:branch", "industrial": "rail:industrial",
              "military": "rail:industrial", "tourism": "rail:industrial", "test": "rail:industrial"}
_KEY_DEC = 7


def speed_class(railway: str, usage: str) -> str:
    """Key into DEFAULT_SPEED_KPH for a `railway`/`usage` pair (usage matters for `rail` only)."""
    if railway == "rail":
        return _USAGE_KEY.get(usage, "rail")
    return railway


def _yes(v) -> bool:
    return _first_tag(v).lower() in ("yes", "true", "1", "viaduct", "culvert", "building_passage", "covered")


def _split_at_shared(lines):
    """[(row_index, xy ndarray)] -> list of (row_index, xy) split at interior vertices that another line also has."""
    seen = {}
    for ri, xy in lines:
        for k in {(round(float(x), _KEY_DEC), round(float(y), _KEY_DEC)) for x, y in xy}:
            seen.setdefault(k, set()).add(ri)
    out = []
    for ri, xy in lines:
        cut = [0]
        for i in range(1, len(xy) - 1):
            if len(seen[(round(float(xy[i][0]), _KEY_DEC), round(float(xy[i][1]), _KEY_DEC))]) > 1:
                cut.append(i)
        cut.append(len(xy) - 1)
        for a, b in zip(cut, cut[1:]):
            out.append((ri, xy[a:b + 1]))
    return out


class RailGraph(RoadGraph):
    """Undirected-in-effect (both directions) rail graph with snapping, legs, chains and station snapping."""

    def __init__(self, rail, speed_kph_by_class: dict | None = None, weight: str = "time", max_snap_m: float = 500.0,
                 include_service: bool = False):
        if weight not in ("time", "length"):
            raise ValueError("weight must be 'time' (fastest) or 'length' (shortest)")
        import geopandas as gpd

        self.weight = weight
        self.max_snap_m = float(max_snap_m)
        self.include_service = bool(include_service)
        self.speed_kph = {**DEFAULT_SPEED_KPH, **(speed_kph_by_class or {})}
        self.speed_src = DEFAULT_SPEED_SRC
        gdf = rail if hasattr(rail, "geometry") else gpd.read_file(Path(rail))
        if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(4326)
        gdf = gdf.explode(index_parts=False, ignore_index=True) if len(gdf) else gdf
        self.stats = {"features": int(len(gdf)), "dropped_other_railway": 0, "dropped_degenerate": 0,
                      "excluded_service": 0, "edges": 0, "default_speed_edges": 0, "default_speed_share": 0.0,
                      "classes": {}, "tunnel_edges": 0, "bridge_edges": 0, "electrified_edges": 0,
                      "length_km": 0.0, "electrified_km": 0.0}
        self.edges: list[_Edge] = []
        self.edge_attrs: list[dict] = []
        self._build(gdf)
        if not self.edges:
            raise ValueError("rail layer has no usable LineString features (check data/worlds/<world>/osm/rail.geojson; "
                             "service=yard|siding|spur are excluded unless include_service=True)")
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

        def tag(row, c):
            return _first_tag(row[c]) if c in cols else ""

        rows, lines = {}, []
        for ri, row in gdf.iterrows():
            geom = row.geometry
            if geom is None or geom.is_empty or geom.geom_type != "LineString":
                self.stats["dropped_degenerate"] += 1
                continue
            rw = tag(row, "railway").lower()
            if rw not in RAILWAYS:
                self.stats["dropped_other_railway"] += 1
                continue
            if tag(row, "service").lower() in EXCLUDED_SERVICE and not self.include_service:
                self.stats["excluded_service"] += 1
                continue
            xy = np.asarray(geom.coords, dtype=float)[:, :2]
            xy = xy[np.r_[True, np.any(np.diff(xy, axis=0) != 0, axis=1)]]
            if len(xy) < 2:
                self.stats["dropped_degenerate"] += 1
                continue
            rows[ri] = row
            lines.append((ri, xy))

        for ri, xy in _split_at_shared(lines):
            row = rows[ri]
            rw, usage = tag(row, "railway").lower(), tag(row, "usage").lower()
            cls = speed_class(rw, usage)
            if cls not in self.speed_kph:
                raise ValueError(f"rail class {cls!r} has no speed: pass speed_kph_by_class={{{cls!r}: kph}}")
            _, _, d = GEOD.inv(xy[:-1, 0], xy[:-1, 1], xy[1:, 0], xy[1:, 1])
            cum = np.r_[0.0, np.cumsum(d)]
            kph = parse_maxspeed_kph(row["maxspeed"]) if "maxspeed" in cols else float("nan")
            from_default = not math.isfinite(kph)
            if from_default:
                kph = self.speed_kph[cls]
            elec = tag(row, "electrified").lower() not in ("", "no")
            attrs = {"railway": rw, "usage": usage, "service": tag(row, "service").lower(), "gauge": tag(row, "gauge"),
                     "voltage": tag(row, "voltage"), "electrified": elec, "tunnel": _yes(row["tunnel"]) if "tunnel" in cols else False,
                     "bridge": _yes(row["bridge"]) if "bridge" in cols else False, "speed_kph": float(kph),
                     "speed_from_default": from_default, "speed_class": cls, "name": tag(row, "name")}
            e = _Edge(len(self.edges), xy, cum, kph / 3.6, True, True, junction(xy[0]), junction(xy[-1]), from_default)
            self.edges.append(e)
            self.edge_attrs.append(attrs)
            st = self.stats
            st["classes"][cls] = st["classes"].get(cls, 0) + 1
            st["default_speed_edges"] += int(from_default)
            st["tunnel_edges"] += int(attrs["tunnel"])
            st["bridge_edges"] += int(attrs["bridge"])
            st["electrified_edges"] += int(elec)
            st["length_km"] += e.length / 1000.0
            st["electrified_km"] += e.length / 1000.0 * elec
            if e.u == e.v or e.length <= 0:
                continue
            t = e.length / e.speed_mps
            for a, b, rev in ((e.u, e.v, False), (e.v, e.u, True)):
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

        comps = list(nx.connected_components(self.G.to_undirected())) if self.G.number_of_nodes() else []
        self.core = set().union(*comps) if comps else set()          # no core restriction: every included edge snaps
        self._cand = list(self.edges)
        allxy = np.vstack([e.coords for e in self._cand])
        self._lon0, self._lat0 = float(allxy[:, 0].mean()), float(allxy[:, 1].mean())
        self._kx = 111_320.0 * math.cos(math.radians(self._lat0))
        self._ky = 110_574.0
        self._tree = STRtree([LineString(self._local(e.coords)) for e in self._cand])
        self.stats["components"] = len(comps)
        self.stats["total_nodes"] = self.G.number_of_nodes()

    # ----------------------------------------------------------------------------------------------- routes
    def legs(self, nodes_lonlat):
        """See RoadGraph.legs. Unreachable pair -> ValueError naming the nodes (a rail gap or a different network)."""
        try:
            return super().legs(nodes_lonlat)
        except ValueError as ex:
            if "no drivable route" in str(ex):
                msg = str(ex).replace("no drivable route", "no rail route").split(":")[0]
                raise ValueError(f"{msg}: the stops are on disconnected track (gap in the rail layer, a service track "
                                 "excluded, or a different network such as tram vs main line)") from None
            raise

    def chain(self, nodes_lonlat):
        """Route through the nodes IN ORDER (consecutive pairs only; cheaper than `legs` for a trip).
        Returns (points, node_idx, dist_m, time_s): `points` the polyline, `node_idx[k]` the vertex index of node k in it,
        `dist_m[k]`, `time_s[k]` the cumulative geodesic distance and free-flow time at node k. The nodes must be on
        the graph (call `snap` first). Raises ValueError for an unreachable consecutive pair."""
        n = len(nodes_lonlat)
        if n < 2:
            raise ValueError("chain needs at least two nodes")
        place = [self._placement(p) for p in nodes_lonlat]
        wkey = "t" if self.weight == "time" else "l"
        G = self.G
        names = [("snap", i) for i in range(n)]
        pts, idx, cum_l, cum_t = [], [0], [0.0], [0.0]
        try:
            for i, (e, s) in enumerate(place):
                G.add_node(names[i])
                for src, dst, rev in ((e.u, e.v, False), (e.v, e.u, True)):
                    if not rev:
                        self._temp_arc(G, e, src, names[i], 0.0, s)
                        self._temp_arc(G, e, names[i], dst, s, e.length)
                    else:
                        self._temp_arc(G, e, src, names[i], e.length, s)
                        self._temp_arc(G, e, names[i], dst, s, 0.0)
            for i in range(n - 1):
                direct = self._direct(place[i], place[i + 1])
                if direct is not None:
                    arcs = [direct]
                else:
                    try:
                        path = nx.dijkstra_path(G, names[i], names[i + 1], weight=wkey)
                    except nx.NetworkXNoPath:
                        raise ValueError(f"no rail route from node {i} to node {i + 1} "
                                         f"({nodes_lonlat[i]} -> {nodes_lonlat[i + 1]}): disconnected track") from None
                    arcs = [G.edges[a, b]["g"] for a, b in zip(path, path[1:])]
                p, ct, cl = self._assemble(arcs)
                if pts and p[0] == pts[-1]:
                    p = p[1:]
                pts.extend(p)
                idx.append(len(pts) - 1)
                cum_l.append(cum_l[-1] + cl[-1])
                cum_t.append(cum_t[-1] + ct[-1])
        finally:
            G.remove_nodes_from(names)
        return pts, idx, cum_l, cum_t

    # ----------------------------------------------------------------------------------------------- stations
    def snap_stations(self, stations, strict: bool = False, name_cols=("name", "ref")):
        """Snap station features onto the track and REPORT the distance (as quay snaps are reported for vessels).
        `stations`: GeoDataFrame / path (Point; Polygon and Line use the centroid). Returns a DataFrame, one row per
        station, columns: station, ref, railway, lon, lat, node_lon, node_lat, snap_m, snapped (bool).
        A station farther than `max_snap_m` has snapped=False and NaN node coordinates; strict=True raises instead."""
        import geopandas as gpd
        import pandas as pd

        g = stations if hasattr(stations, "geometry") else gpd.read_file(Path(stations))
        if g.crs is not None and g.crs.to_epsg() != 4326:
            g = g.to_crs(4326)
        rows = []
        for i, r in enumerate(g.itertuples(index=False)):
            geom = r.geometry
            if geom is None or geom.is_empty:
                continue
            c = geom if geom.geom_type == "Point" else geom.centroid
            d = r._asdict()
            e, s, q, dist = self._project(float(c.x), float(c.y))
            ok = dist <= self.max_snap_m
            if not ok and strict:
                raise ValueError(f"station {d.get('name') or i!r} is {dist:.0f} m from the nearest track (max_snap_m={self.max_snap_m:.0f})")
            if ok:
                self._place[q] = (e.eid, s)
            rows.append({"station": d.get(name_cols[0]) or "", "ref": d.get(name_cols[1]) or "", "railway": d.get("railway") or "",
                         "lon": float(c.x), "lat": float(c.y), "node_lon": q[0] if ok else float("nan"),
                         "node_lat": q[1] if ok else float("nan"), "snap_m": round(dist, 1), "snapped": bool(ok)})
        return pd.DataFrame(rows, columns=["station", "ref", "railway", "lon", "lat", "node_lon", "node_lat", "snap_m", "snapped"])

    # ----------------------------------------------------------------------------------------------- info
    def describe(self) -> dict:
        """What a report records about this graph (JSON-safe)."""
        return {"graph": "rail", "weight": self.weight, "speed_basis": self.speed_src, "speed_defaults_are_assumptions": True,
                "max_snap_m": self.max_snap_m, "include_service": self.include_service,
                **{k: (round(v, 3) if isinstance(v, float) else v) for k, v in self.stats.items()}}


def load_world_rail(world_dir, **kw):
    """RailGraph from <world_dir>/osm/rail.geojson, or None when the file is absent, empty, or has no usable line.
    Never raises for a missing layer (a world without rail is normal); a corrupt file still raises."""
    p = Path(world_dir) / "osm" / "rail.geojson"
    if not p.exists():
        return None
    try:
        return RailGraph(p, **kw)
    except ValueError as ex:
        if "no usable LineString" in str(ex):
            return None
        raise
