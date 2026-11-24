"""Molde peak shot: build the Blender scene for the 07:35 still.

Reads the gated GTFS replay (trajectory.csv) and the Molde world
(land.geojson), and writes out/molde-peak/land.glb, bus.glb, ferry.glb and
scene.json for tools/blender_shot.py. No bpy here: the render runs in the
Blender binary (see the smoke test in coordination/reports/molde-peak-shot-spec.md).

Counts are instantaneous at t = 5700 s (07:35), in the Molde world bbox,
by class from agents.csv. The headline number is the in-frame count, so the
number and the picture agree by construction.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from shapely.geometry import shape
from shapely.ops import triangulate

ROOT = Path(__file__).resolve().parents[1]
BBOX = (6.8655, 62.6051, 7.4545, 62.8749)  # lon_min, lat_min, lon_max, lat_max
LON0 = (BBOX[0] + BBOX[2]) / 2
LAT0 = (BBOX[1] + BBOX[3]) / 2
T_PEAK = 5700.0
LAND_Z = 5.0      # land sits just above the sea plane (level 0)
MARKER_Z = 12.0
BUS_R = 125.0     # disc radius, metres (~9 px at 1080 wide over 30 km)
FERRY_R = 175.0   # diamond radius, metres
FRAME = (1080, 1350)  # 4:5, to match the v2 film

# v2 palette tokens (OURS): oxblood ground, gold ferry, blue bus.
LAND_HEX = "#331c22"
BUS_HEX = "#4f8f9c"
FERRY_HEX = "#e5a028"
ROAD_HEX = "#8a7364"      # v2 road colour, all classes
BUILDING_HEX = "#6e4a3c"  # v2 building fill
QUAY_HEX = "#c9a98c"      # v2 quay colour
LANDUSE_HEX = "#3d232a"   # v2 industrial tint
PLACE_HALO_HEX = "#c9a25e"
LABEL_STREET_HEX = "#d8cbb8"
ROAD_Z = 7.0
BUILDING_Z = 8.0
QUAY_Z = 7.0
LANDUSE_Z = 6.0
PLACE_Z = 12.0
LABEL_Z = 20.0
# Road ribbon half-widths by class, metres. Symbols, not true widths: a real
# 7 m road is sub-pixel at 36 px/km; v2's 2.0 px trunk is ~75 m.
ROAD_HALF_WIDTH = {"trunk": 60.0, "primary": 60.0, "primary_link": 60.0,
                   "trunk_link": 60.0, "secondary": 45.0, "tertiary": 35.0,
                   "tertiary_link": 35.0}
ROAD_HALF_WIDTH_DEFAULT = 25.0
# The six gold places from v2 (lon, lat). Labels stack north of the true
# point where the three centre places collide (offsets in metres, see below).
PLACES = {
    "MOLDE SENTRUM": (7.1605, 62.7383),
    "MOLDE TRAFIKKTERMINAL": (7.1616, 62.7374),
    "MOLDE FERJEKAI": (7.1691, 62.7369),
    "MOLDE LUFTHAVN, ÅRØ": (7.2676, 62.7450),
    "FURNESET FERJEKAI": (7.0851, 62.6511),
    "SEKKEN KAI": (7.3030, 62.6753),
}
# Place labels: display text + (dx, dy) in metres from the dot. The three
# centre places sit within ~700 m of each other but each label is ~4 km wide
# at 600 m cap height, so they need a horizontal stagger as well as the
# vertical ladder, and the "MOLDE " prefix is dropped (the map is Molde).
PLACE_LABEL_LAYOUT = {
    "MOLDE SENTRUM": ("SENTRUM", 0.0, 900.0),
    "MOLDE TRAFIKKTERMINAL": ("TRAFIKKTERMINAL", -2200.0, 1400.0),
    "MOLDE FERJEKAI": ("FERJEKAI", 2200.0, 3600.0),
    "MOLDE LUFTHAVN, ÅRØ": ("LUFTHAVN, ÅRØ", 0.0, 900.0),
    "FURNESET FERJEKAI": ("FURNESET FERJEKAI", 0.0, 900.0),
    "SEKKEN KAI": ("SEKKEN KAI", 0.0, 900.0),
}
# Street labels: (label, match on name or ref). Anchor = middle vertex of
# the longest matching way, heading along the way (v2's rule).
STREETS = [
    ("E39", "ref", "E 39"),
    ("Fv 64", "name", "Malmefjordvegen"),
    ("Storgata", "name", "Storgata"),
    ("Julsundvegen · Fv 662", "name", "Julsundvegen"),
    ("Frænavegen · Fv 538", "name", "Frænavegen"),
]


def _add_poly(poly, z, verts, faces, lon0=LON0, lat0=LAT0):
    """Triangulate one polygon (covers-filtered) into the vertex lists."""
    for tri in triangulate(poly):
        if not poly.covers(tri.centroid):
            continue
        ring = list(tri.exterior.coords)[:3]
        base = len(verts)
        (x1, y1), (x2, y2), (x3, y3) = ring
        if (x2 - x1) * (y3 - y1) - (y2 - y1) * (x3 - x1) < 0:
            ring = [ring[0], ring[2], ring[1]]
        xs, ys = project([p[0] for p in ring], [p[1] for p in ring], lon0, lat0)
        for xi, yi in zip(xs, ys):
            verts.append([float(xi), float(yi), z])
        faces.append([base, base + 1, base + 2])


def _add_poly_m(poly, z, verts, faces):
    """Triangulate one polygon already in local metres (no projection)."""
    for tri in triangulate(poly):
        if not poly.covers(tri.centroid):
            continue
        ring = list(tri.exterior.coords)[:3]
        base = len(verts)
        (x1, y1), (x2, y2), (x3, y3) = ring
        if (x2 - x1) * (y3 - y1) - (y2 - y1) * (x3 - x1) < 0:
            ring = [ring[0], ring[2], ring[1]]
        for xi, yi in ring:
            verts.append([float(xi), float(yi), z])
        faces.append([base, base + 1, base + 2])


def _write_glb(verts, faces, out_glb, node_name):
    import trimesh

    mesh = trimesh.Trimesh(vertices=_to_gltf(verts), faces=np.array(faces),
                           process=False)
    scene = trimesh.Scene()
    scene.add_geometry(mesh, node_name=node_name, geom_name=node_name)
    Path(out_glb).parent.mkdir(parents=True, exist_ok=True)
    Path(out_glb).write_bytes(scene.export(file_type="glb"))
    return {"glb": str(out_glb), "triangles": len(faces)}


def project(lon, lat, lon0=LON0, lat0=LAT0):
    """Lon/lat to local metres about (lon0, lat0) (equirectangular)."""
    x = (np.asarray(lon) - lon0) * 111320.0 * math.cos(math.radians(lat0))
    y = (np.asarray(lat) - lat0) * 110540.0
    return x, y


def peak_positions(traj_csv, agents_csv, t=T_PEAK, bbox=BBOX):
    """Instantaneous positions at time t, inside bbox, by class.

    Returns a list of dicts: agent_id, cls, x, y (metres), heading_deg
    (about +Z from +x, from the previous 30 s step; 0 when still/unknown).
    """
    traj = pd.read_csv(traj_csv)
    agents = pd.read_csv(agents_csv)
    cls = dict(zip(agents.agent_id, agents.cls))
    now = traj[traj.t == t].copy()
    now["cls"] = now.agent_id.map(cls)
    now = now[(now.lon >= bbox[0]) & (now.lon <= bbox[2])
              & (now.lat >= bbox[1]) & (now.lat <= bbox[3])]
    prev = traj[traj.t == t - 30].set_index("agent_id")
    out = []
    for row in now.itertuples():
        x, y = project(row.lon, row.lat)
        heading = 0.0
        if row.agent_id in prev.index:
            px, py = project(prev.loc[row.agent_id].lon, prev.loc[row.agent_id].lat)
            dx, dy = float(x - px), float(y - py)
            if dx * dx + dy * dy > 1.0:
                heading = math.degrees(math.atan2(dy, dx))
        out.append({"agent_id": row.agent_id, "cls": row.cls,
                    "x": float(x), "y": float(y), "heading_deg": heading})
    return out


def _to_gltf(xyz):
    """Local (x east, y north, z up) to glTF (x, y up, z) = (x, z, -y)."""
    v = np.asarray(xyz, dtype=float)
    return v[:, [0, 2, 1]] * np.array([1.0, 1.0, -1.0])


def build_land_glb(geojson_path, out_glb):
    """Triangulate the land polygons into a flat mesh GLB (one node 'land')."""
    import trimesh

    data = json.loads(Path(geojson_path).read_text())
    polys = []
    for feat in data["features"]:
        geom = shape(feat["geometry"])
        if geom.geom_type == "MultiPolygon":
            polys.extend(geom.geoms)
        elif geom.geom_type == "Polygon":
            polys.append(geom)
    verts, faces = [], []
    for poly in polys:
        for tri in triangulate(poly):
            c = tri.centroid
            if not poly.covers(c):
                continue
            ring = list(tri.exterior.coords)[:3]
            base = len(verts)
            # CCW in (x, y) so the normal points +Z in the local frame.
            (x1, y1), (x2, y2), (x3, y3) = ring
            if (x2 - x1) * (y3 - y1) - (y2 - y1) * (x3 - x1) < 0:
                ring = [ring[0], ring[2], ring[1]]
            xs, ys = project([p[0] for p in ring], [p[1] for p in ring])
            for xi, yi in zip(xs, ys):
                verts.append([float(xi), float(yi), LAND_Z])
            faces.append([base, base + 1, base + 2])
    mesh = trimesh.Trimesh(vertices=_to_gltf(verts), faces=np.array(faces),
                           process=False)
    scene = trimesh.Scene()
    scene.add_geometry(mesh, node_name="land", geom_name="land")
    Path(out_glb).parent.mkdir(parents=True, exist_ok=True)
    Path(out_glb).write_bytes(scene.export(file_type="glb"))
    xs = [v[0] for v in verts]
    ys = [v[1] for v in verts]
    return {"glb": str(out_glb), "triangles": len(faces),
            "size_m": [max(xs) - min(xs), max(ys) - min(ys), LAND_Z]}


def build_marker_glb(kind, out_glb):
    """A flat symbol GLB: bus = disc, ferry = diamond (4-sided)."""
    import trimesh

    n = 24 if kind == "bus" else 4
    r = BUS_R if kind == "bus" else FERRY_R
    h = 8.0
    ang = np.linspace(0, 2 * np.pi, n, endpoint=False)
    if kind == "ferry":
        ang = ang + np.pi / 4
    ring = [(r * np.cos(a), r * np.sin(a)) for a in ang]
    verts, faces = [], []
    top = len(verts)
    for xi, yi in ring:
        verts.append([xi, yi, MARKER_Z])
    verts.append([0.0, 0.0, MARKER_Z])
    for i in range(n):
        faces.append([top + i, top + (i + 1) % n, top + n])
    bot = len(verts)
    for xi, yi in ring:
        verts.append([xi, yi, MARKER_Z - h])
    verts.append([0.0, 0.0, MARKER_Z - h])
    for i in range(n):
        faces.append([bot + (i + 1) % n, bot + i, bot + n])
    for i in range(n):
        j = (i + 1) % n
        faces.append([top + i, top + j, bot + j])
        faces.append([top + i, bot + j, bot + i])
    mesh = trimesh.Trimesh(vertices=_to_gltf(verts), faces=np.array(faces),
                           process=False)
    scene = trimesh.Scene()
    scene.add_geometry(mesh, node_name=kind, geom_name=kind)
    Path(out_glb).parent.mkdir(parents=True, exist_ok=True)
    Path(out_glb).write_bytes(scene.export(file_type="glb"))
    return {"glb": str(out_glb)}


def build_roads_glb(roads_path, out_dir):
    """One ribbon mesh per width class, from OSM highway ways.

    Project to local metres FIRST, then buffer: the buffer distance is in the
    geometry's units, and buffering in degrees made every road a continent.
    (That bug painted the first layered Molde still road-coloured throughout.)
    """
    from shapely.geometry import LineString, shape as shp

    feats = json.loads(Path(roads_path).read_text())["features"]
    by_class = {}
    for feat in feats:
        props = feat["properties"]
        hw = props.get("highway", "")
        half = ROAD_HALF_WIDTH.get(hw, ROAD_HALF_WIDTH_DEFAULT)
        line = shp(feat["geometry"])
        xs, ys = project(list(line.xy[0]), list(line.xy[1]))
        mline = LineString(zip(xs, ys))
        buf = mline.buffer(half, join_style=1, cap_style=1)
        polys = list(buf.geoms) if buf.geom_type == "MultiPolygon" else [buf]
        by_class.setdefault(half, []).extend(polys)
    out = {}
    for half, polys in sorted(by_class.items()):
        verts, faces = [], []
        for poly in polys:
            _add_poly_m(poly, ROAD_Z, verts, faces)
        out[half] = _write_glb(verts, faces, Path(out_dir) / f"road_{int(half)}.glb",
                               f"road_{int(half)}")
        out[half]["class"] = "road"
    return out


def build_buildings_glb(buildings_path, out_glb):
    """Flat footprints, one mesh, triangulated like the land."""
    from shapely.geometry import shape as shp

    verts, faces = [], []
    for feat in json.loads(Path(buildings_path).read_text())["features"]:
        geom = shp(feat["geometry"])
        polys = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
        for poly in polys:
            _add_poly(poly, BUILDING_Z, verts, faces)
    return _write_glb(verts, faces, out_glb, "buildings")


def build_quays_glb(quays_path, out_glb):
    """Quay lines as ribbons + quay polygons, one mesh.

    Lines are projected to metres and buffered there; polygons from the file
    stay in lon/lat and go through the projecting triangulator.
    """
    from shapely.geometry import LineString, shape as shp

    verts, faces = [], []
    for feat in json.loads(Path(quays_path).read_text())["features"]:
        geom = shp(feat["geometry"])
        if geom.geom_type == "LineString":
            xs, ys = project(list(geom.xy[0]), list(geom.xy[1]))
            mline = LineString(zip(xs, ys))
            buf = mline.buffer(25.0, join_style=1, cap_style=1)
            polys = list(buf.geoms) if buf.geom_type == "MultiPolygon" else [buf]
            for poly in polys:
                _add_poly_m(poly, QUAY_Z, verts, faces)
        elif geom.geom_type == "Polygon":
            _add_poly(geom, QUAY_Z, verts, faces)
        elif geom.geom_type == "MultiPolygon":
            for poly in geom.geoms:
                _add_poly(poly, QUAY_Z, verts, faces)
    return _write_glb(verts, faces, out_glb, "quays")


def build_landuse_glb(landuse_path, out_glb):
    """Industrial landuse tint, one mesh."""
    from shapely.geometry import shape as shp

    verts, faces = [], []
    for feat in json.loads(Path(landuse_path).read_text())["features"]:
        geom = shp(feat["geometry"])
        polys = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
        for poly in polys:
            _add_poly(poly, LANDUSE_Z, verts, faces)
    return _write_glb(verts, faces, out_glb, "landuse")


def build_disc_glb(radius, z, out_glb, node_name, segments=24):
    """A flat disc symbol (place dot / halo), one mesh."""
    import trimesh

    ang = np.linspace(0, 2 * np.pi, segments, endpoint=False)
    verts = [[float(radius * np.cos(a)), float(radius * np.sin(a)), z] for a in ang]
    verts.append([0.0, 0.0, z])
    faces = [[i, (i + 1) % segments, segments] for i in range(segments)]
    return _write_glb(verts, faces, out_glb, node_name)


def street_anchors(roads_path):
    """Midpoint + heading of the longest way per street target."""
    from shapely.geometry import shape as shp

    feats = json.loads(Path(roads_path).read_text())["features"]
    out = []
    for label, key, value in STREETS:
        best, best_len = None, -1.0
        for feat in feats:
            if feat["properties"].get(key) != value:
                continue
            line = shp(feat["geometry"])
            if line.length > best_len:
                best, best_len = line, line.length
        if best is None:
            continue
        coords = list(best.coords)
        mid = coords[len(coords) // 2]
        prev_c, next_c = coords[max(0, len(coords) // 2 - 1)], coords[min(len(coords) - 1, len(coords) // 2 + 1)]
        (x1, y1), (x2, y2) = project([prev_c[0], next_c[0]], [prev_c[1], next_c[1]])
        heading = math.degrees(math.atan2(float(y2 - y1), float(x2 - x1)))
        x, y = project([mid[0]], [mid[1]])
        out.append({"label": label, "x": float(x[0]), "y": float(y[0]),
                    "heading_deg": round(heading, 1)})
    return out


def build_scene(out_dir, traj_csv=None, agents_csv=None, geojson=None,
                osm_dir=None, resolution=FRAME, samples=16, line_px=1.2):
    """Write the GLBs and scene.json for the peak still. Returns the spec."""
    out_dir = Path(out_dir)
    traj_csv = traj_csv or ROOT / "out" / "molde-gtfs-replay" / "trajectory.csv"
    agents_csv = agents_csv or ROOT / "out" / "molde-gtfs-replay" / "agents.csv"
    geojson = geojson or ROOT / "data" / "worlds" / "molde" / "land.geojson"
    osm_dir = Path(osm_dir) if osm_dir else ROOT / "data" / "worlds" / "molde" / "osm"
    land = build_land_glb(geojson, out_dir / "land.glb")
    bus = build_marker_glb("bus", out_dir / "bus.glb")
    ferry = build_marker_glb("ferry", out_dir / "ferry.glb")
    roads = build_roads_glb(osm_dir / "roads.geojson", out_dir)
    buildings = build_buildings_glb(osm_dir / "buildings.geojson",
                                    out_dir / "buildings.glb")
    quays = build_quays_glb(osm_dir / "quays.geojson", out_dir / "quays.glb")
    landuse = build_landuse_glb(osm_dir / "landuse.geojson",
                                out_dir / "landuse.glb")
    place_dot = build_disc_glb(200.0, PLACE_Z, out_dir / "place_dot.glb", "place_dot")
    place_halo = build_disc_glb(420.0, PLACE_Z - 1.0, out_dir / "place_halo.glb",
                                "place_halo")
    positions = peak_positions(traj_csv, agents_csv)
    assets = [{"name": "land", "glb": land["glb"], "position": [0, 0, 0],
               "heading_deg": 0, "scale": 1.0, "colours": {"land": LAND_HEX}},
              {"name": "landuse", "glb": landuse["glb"], "position": [0, 0, 0],
               "heading_deg": 0, "scale": 1.0, "colours": {"landuse": LANDUSE_HEX}},
              {"name": "buildings", "glb": buildings["glb"], "position": [0, 0, 0],
               "heading_deg": 0, "scale": 1.0, "colours": {"buildings": BUILDING_HEX}},
              {"name": "quays", "glb": quays["glb"], "position": [0, 0, 0],
               "heading_deg": 0, "scale": 1.0, "colours": {"quays": QUAY_HEX}}]
    for half, info in sorted(roads.items()):
        assets.append({"name": f"road_{int(half)}", "glb": info["glb"],
                       "position": [0, 0, 0], "heading_deg": 0, "scale": 1.0,
                       "colours": {f"road_{int(half)}": ROAD_HEX}})
    for name, (lon, lat) in PLACES.items():
        x, y = project([lon], [lat])
        assets.append({"name": "place_halo_" + name[:4], "glb": place_halo["glb"],
                       "position": [float(x[0]), float(y[0]), 0],
                       "heading_deg": 0, "scale": 1.0,
                       "colours": {"place_halo": PLACE_HALO_HEX}})
        assets.append({"name": "place_dot_" + name[:4], "glb": place_dot["glb"],
                       "position": [float(x[0]), float(y[0]), 0],
                       "heading_deg": 0, "scale": 1.0,
                       "colours": {"place_dot": FERRY_HEX}})
    for i, p in enumerate(positions):
        kind = p["cls"]
        glb = bus["glb"] if kind == "bus" else ferry["glb"]
        hexcol = BUS_HEX if kind == "bus" else FERRY_HEX
        assets.append({"name": f"{kind}_{i:02d}", "glb": glb,
                       "position": [p["x"], p["y"], 0],
                       "heading_deg": round(p["heading_deg"], 1), "scale": 1.0,
                       "colours": {kind: hexcol}})
    texts = []
    for name, (lon, lat) in PLACES.items():
        x, y = project([lon], [lat])
        label, dx, dy = PLACE_LABEL_LAYOUT.get(name, (name, 0.0, 0.0))
        texts.append({"text": label,
                      "position": [float(x[0]) + dx, float(y[0]) + dy, LABEL_Z],
                      "size_m": 400, "heading_deg": 0, "colour": FERRY_HEX})
    for s in street_anchors(osm_dir / "roads.geojson"):
        texts.append({"text": s["label"], "position": [s["x"], s["y"], LABEL_Z],
                      "size_m": 500, "heading_deg": s["heading_deg"],
                      "colour": LABEL_STREET_HEX})
    spec = {
        "assets": assets,
        "texts": texts,
        "sea": {"level_m": 0.0, "size_m": 60000, "colour": "sea"},
        "camera": {"position": [0, -18000, 24000], "look_at": [0, 1000, 0],
                   "lens_mm": 35},
        "lights": {"key": {"dir": [-0.4, -0.7, 0.6], "kelvin": 5600},
                   "fill": {"dir": [0.7, 0.2, 0.3], "kelvin": 8000},
                   "rim": {"dir": [0.3, 0.9, 0.4], "kelvin": 4000}},
        "sky": {"top": "sky_top", "bottom": "sky_bottom"},
        "palette": {"sea": "#14424f"},
        "shading": {"mode": "flat", "line_px": line_px},
        "resolution": list(resolution), "samples": samples, "seed": 7,
    }
    (out_dir / "scene.json").write_text(json.dumps(spec, indent=2))
    counts = {"bus": sum(1 for p in positions if p["cls"] == "bus"),
              "ferry": sum(1 for p in positions if p["cls"] == "ferry")}
    layers = {"roads": {int(h): v["triangles"] for h, v in roads.items()},
              "buildings": buildings["triangles"],
              "quays": quays["triangles"], "landuse": landuse["triangles"],
              "places": len(PLACES), "texts": len(texts)}
    return {"spec": spec, "land": land, "counts": counts,
            "total": len(positions), "layers": layers}


if __name__ == "__main__":
    import sys

    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "out" / "molde-peak"
    # argv[2] is the checkout holding data/ and out/ (the worktree has neither)
    data_root = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT
    res = build_scene(out, data_root / "out" / "molde-gtfs-replay" / "trajectory.csv",
                      data_root / "out" / "molde-gtfs-replay" / "agents.csv",
                      data_root / "data" / "worlds" / "molde" / "land.geojson",
                      data_root / "data" / "worlds" / "molde" / "osm",
                      line_px=float(sys.argv[3]) if len(sys.argv) > 3 else 1.2)
    print(f"land: {res['land']['triangles']} triangles, "
          f"size {['%.0f' % v for v in res['land']['size_m']]} m")
    print(f"layers: {res['layers']}")
    print(f"peak t={T_PEAK}: {res['counts']['bus']} bus + "
          f"{res['counts']['ferry']} ferry = {res['total']} in frame")
    print("scene.json:", out / "scene.json")
