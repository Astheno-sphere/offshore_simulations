"""Flesland massing inset (Irina shot 3): buildings extruded to height_m around
the mapped helipad, for the push to the pad and the match cut to the map.

Heights: `height` tag = measured (cream); `building:levels` x 3 m = assumed
(tinted tan); no height = flat footprint (no invented height). The pad is the
MAPPED OSM helipad polygon at (5.2247, 60.2973) on the Bergen airport apron —
not the instances.yaml heliport (5.2181, 60.2934, ~700 m away, assumption),
which the service-area map uses; the difference is sub-pixel on the map.
Counts are reported (QA gate: buildings shown = buildings drawn).
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
from shapely.geometry import Polygon, box, shape as shp
from shapely.ops import triangulate

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.molde_peak_shot import (  # noqa: E402
    _add_poly, _to_gltf, _write_glb, build_disc_glb, project,
)

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path.home() / "workspace" / "offshore_simulations"
LON0, LAT0 = 5.2247, 60.2973  # mapped helipad, centre of the inset
PAD_LON, PAD_LAT = 5.2247, 60.2973
INSET_RADIUS_M = 1500.0
GROUND_HEX = "#331c22"
SEA_HEX = "#14424f"
MEASURED_HEX = "#e8dfd0"
ASSUMED_HEX = "#c4b8a8"
FLAT_HEX = "#6e4a3c"
GOLD_HEX = "#e5a028"


def _extrude(coords, z0, h, verts, faces):
    """Prism: triangulated top at z0+h, side quads, bottom omitted."""
    poly = Polygon(coords)
    if not poly.is_valid or poly.area == 0:
        return 0
    n = 0
    for tri in triangulate(poly):
        if not poly.covers(tri.centroid):
            continue
        ring = list(tri.exterior.coords)[:3]
        if (ring[1][0] - ring[0][0]) * (ring[2][1] - ring[0][1]) - \
           (ring[1][1] - ring[0][1]) * (ring[2][0] - ring[0][0]) < 0:
            ring = [ring[0], ring[2], ring[1]]
        base = len(verts)
        for x, y in ring:
            verts.append([float(x), float(y), z0 + h])
        faces.append([base, base + 1, base + 2])
        n += 1
    ring = list(poly.exterior.coords)[:-1]
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        base = len(verts)
        verts.extend([[float(x1), float(y1), z0], [float(x2), float(y2), z0],
                      [float(x2), float(y2), z0 + h],
                      [float(x1), float(y1), z0 + h]])
        faces.extend([[base, base + 1, base + 2], [base, base + 2, base + 3]])
        n += 2
    return n


def build_scene(out_dir, buildings_json=None, resolution=(540, 675),
                samples=8):
    out_dir = Path(out_dir)
    buildings_json = buildings_json or (ROOT / "out" / "flesland-massing" /
                                        "buildings.json")
    data = json.loads(Path(buildings_json).read_text())
    px, py = project([PAD_LON], [PAD_LAT], LON0, LAT0)
    px, py = float(px[0]), float(py[0])

    measured, assumed, flat = [], [], []
    counts = {"measured": 0, "assumed_levels": 0, "flat": 0, "total": 0}
    for b in data:
        cx = sum(c[0] for c in b["coords"]) / len(b["coords"])
        cy = sum(c[1] for c in b["coords"]) / len(b["coords"])
        d = math.hypot((cx - PAD_LON) * 111320.0 *
                       math.cos(math.radians(PAD_LAT)),
                       (cy - PAD_LAT) * 110540.0)
        if d > INSET_RADIUS_M:
            continue
        counts["total"] += 1
        xs, ys = project([c[0] for c in b["coords"]],
                         [c[1] for c in b["coords"]], LON0, LAT0)
        coords = list(zip(xs, ys))
        if b["height_m"] is not None and b["height_m"] > 0:
            if b["height_src"] == "tag":
                counts["measured"] += 1
                measured.append((coords, b["height_m"]))
            else:
                counts["assumed_levels"] += 1
                assumed.append((coords, b["height_m"]))
        else:
            counts["flat"] += 1
            flat.append(coords)

    assets = []
    # Real ground: the Bergen coastline clipped to the inset box, not a disc
    # (a disc reads as a floating island — the banned tell).
    land_path = (DATA_ROOT / "data" / "worlds" / "bergen" / "land.geojson")
    clip = box(PAD_LON - 0.025, PAD_LAT - 0.02, PAD_LON + 0.025, PAD_LAT + 0.02)
    verts, faces = [], []
    for feat in json.loads(land_path.read_text())["features"]:
        geom = shp(feat["geometry"])
        cut = geom.intersection(clip)
        polys = list(cut.geoms) if cut.geom_type == "MultiPolygon" else [cut]
        for poly in polys:
            if poly.geom_type == "Polygon" and not poly.is_empty:
                _add_poly(poly, 5.0, verts, faces, LON0, LAT0)
    info = _write_glb(verts, faces, out_dir / "ground.glb", "ground")
    assets.append({"name": "ground", "glb": info["glb"],
                   "position": [0, 0, 0], "heading_deg": 0, "scale": 1.0,
                   "colours": {"ground": GROUND_HEX}})
    for name, group, z0 in (("measured", measured, 5.0),
                            ("assumed", assumed, 5.0)):
        verts, faces = [], []
        for coords, h in group:
            _extrude(coords, z0, h, verts, faces)
        info = _write_glb(verts, faces, out_dir / f"{name}.glb", name)
        assets.append({"name": name, "glb": info["glb"],
                       "position": [0, 0, 0], "heading_deg": 0, "scale": 1.0,
                       "colours": {name: MEASURED_HEX if name == "measured"
                                   else ASSUMED_HEX}})
    verts, faces = [], []
    for coords in flat:
        poly = Polygon(coords)
        if not poly.is_valid or poly.area == 0:
            continue
        for tri in triangulate(poly):
            if not poly.covers(tri.centroid):
                continue
            ring = list(tri.exterior.coords)[:3]
            base = len(verts)
            for x, y in ring:
                verts.append([float(x), float(y), 8.0])
            faces.append([base, base + 1, base + 2])
    info = _write_glb(verts, faces, out_dir / "flat.glb", "flat")
    assets.append({"name": "flat", "glb": info["glb"], "position": [0, 0, 0],
                   "heading_deg": 0, "scale": 1.0, "colours": {"flat": FLAT_HEX}})

    pad = build_disc_glb(30.0, 12.0, out_dir / "pad.glb", "pad")
    halo = build_disc_glb(45.0, 11.0, out_dir / "pad_halo.glb", "pad_halo")
    assets.append({"name": "pad_halo", "glb": halo["glb"],
                   "position": [px, py, 0], "heading_deg": 0, "scale": 1.0,
                   "colours": {"pad_halo": GOLD_HEX}})
    assets.append({"name": "pad", "glb": pad["glb"],
                   "position": [px, py, 0], "heading_deg": 0, "scale": 1.0,
                   "colours": {"pad": GOLD_HEX}})
    # One label only: the pad is the gold disc, it needs no name.
    texts = [{"text": "FLESLAND", "position": [px - 250, py + 80, 20.0],
              "size_m": 80, "heading_deg": 0, "colour": GOLD_HEX}]
    spec = {
        "assets": assets,
        "texts": texts,
        "sea": {"level_m": 0.0, "size_m": 20000, "colour": "sea"},
        "camera": {"position": [px + 350, py - 200, 180],
                   "look_at": [px - 250, py + 50, 0], "lens_mm": 40},
        "lights": {"key": {"dir": [-0.4, -0.7, 0.6], "kelvin": 5600},
                   "fill": {"dir": [0.7, 0.2, 0.3], "kelvin": 8000},
                   "rim": {"dir": [0.3, 0.9, 0.4], "kelvin": 4000}},
        "sky": {"top": "sky_top", "bottom": "sky_bottom"},
        "palette": {"sea": SEA_HEX},
        "shading": {"mode": "flat", "line_px": 0},
        "resolution": list(resolution), "samples": samples, "seed": 7,
    }
    (out_dir / "scene.json").write_text(json.dumps(spec, indent=2))
    return {"spec": spec, "counts": counts, "pad": (PAD_LON, PAD_LAT)}


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "out" / "flesland-massing"
    res = build_scene(out)
    print("inset:", res["counts"], "pad:", res["pad"])
    print("scene.json:", out / "scene.json")
