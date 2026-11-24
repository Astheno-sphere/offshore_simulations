"""Bergen service-area map (Irina beat 2): Flesland, 20 assumed installations,
three distance rings, flight arcs — one Blender still, top-down oblique.

Data: local Bergen world (data/worlds/bergen/land.geojson) + the 20 assumed
installation positions from instances.yaml (assumption: true — the paper masks
the real ones). Rings 50/80/120 nm from Flesland. Arcs are straight lines,
stated as such. Half-res verdict format (the Molde cost lesson: a full-res
map still is ~90 min on this VM).
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import yaml
from shapely.geometry import LineString, shape as shp

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.molde_peak_shot import (  # noqa: E402
    _add_poly, _add_poly_m, _write_glb, build_disc_glb, project,
)

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path.home() / "workspace" / "offshore_simulations"
LON0, LAT0 = 3.55, 60.50  # Bergen world bbox centre
LAND_HEX = "#331c22"
SEA_HEX = "#14424f"
GOLD_HEX = "#e5a028"
ARC_HEX = "#4f8f9c"
RING_HEX = "#e8dfd0"
LABEL_HEX = "#d8cbb8"
NM_M = 1852.0
RINGS_NM = (50, 80, 120)


def load_positions(instances_yaml=None):
    inst = yaml.safe_load(open(instances_yaml or
        ROOT / "offsim" / "papers" /
        "irinagribkovskaia-2025-tactical-helicopter" / "instances.yaml"))
    b = inst["instances"]["bergen"]
    heli = (b["heliport"]["lon"], b["heliport"]["lat"])
    pos = {k: tuple(v) for k, v in b["positions"].items()}
    return heli, pos


def ring_polys(cx, cy, radius_m, width_m=2500.0, segments=96):
    ang = np.linspace(0, 2 * np.pi, segments, endpoint=False)
    pts = [(cx + radius_m * math.cos(a), cy + radius_m * math.sin(a))
           for a in ang]
    line = LineString(pts + [pts[0]])
    return line.buffer(width_m / 2, join_style=1, cap_style=1)


def build_scene(out_dir, instances_yaml=None, world_dir=None,
                resolution=(540, 675), samples=8):
    out_dir = Path(out_dir)
    heli, pos = load_positions(instances_yaml)
    world_dir = Path(world_dir) if world_dir else (
        DATA_ROOT / "data" / "worlds" / "bergen")
    hx, hy = project([heli[0]], [heli[1]], LON0, LAT0)
    hx, hy = float(hx[0]), float(hy[0])

    land_path = world_dir / "land.geojson"
    verts, faces = [], []
    for feat in json.loads(land_path.read_text())["features"]:
        geom = shp(feat["geometry"])
        polys = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
        for poly in polys:
            _add_poly(poly, 5.0, verts, faces, LON0, LAT0)
    land = _write_glb(verts, faces, out_dir / "land.glb", "land")

    dot = build_disc_glb(3000.0, 12.0, out_dir / "inst_dot.glb", "inst_dot")
    fles_dot = build_disc_glb(5000.0, 12.0, out_dir / "fles_dot.glb", "fles_dot")
    fles_halo = build_disc_glb(10000.0, 11.0, out_dir / "fles_halo.glb",
                               "fles_halo")

    assets = [{"name": "land", "glb": land["glb"], "position": [0, 0, 0],
               "heading_deg": 0, "scale": 1.0, "colours": {"land": LAND_HEX}},
              {"name": "fles_halo", "glb": fles_halo["glb"],
               "position": [hx, hy, 0], "heading_deg": 0, "scale": 1.0,
               "colours": {"fles_halo": GOLD_HEX}},
              {"name": "fles_dot", "glb": fles_dot["glb"],
               "position": [hx, hy, 0], "heading_deg": 0, "scale": 1.0,
               "colours": {"fles_dot": GOLD_HEX}}]
    for nm in RINGS_NM:
        r = nm * NM_M
        buf = ring_polys(hx, hy, r)
        v2, f2 = [], []
        polys = list(buf.geoms) if buf.geom_type == "MultiPolygon" else [buf]
        for poly in polys:
            _add_poly_m(poly, 7.0, v2, f2)
        info = _write_glb(v2, f2, out_dir / f"ring_{nm}.glb", f"ring_{nm}")
        assets.append({"name": f"ring_{nm}", "glb": info["glb"],
                       "position": [0, 0, 0], "heading_deg": 0, "scale": 1.0,
                       "colours": {f"ring_{nm}": RING_HEX}})
    for name, (lon, lat) in sorted(pos.items()):
        x, y = project([lon], [lat], LON0, LAT0)
        x, y = float(x[0]), float(y[0])
        # straight flight arc, heliport -> installation, ribbon 3000 m wide
        line = LineString([(hx, hy), (x, y)])
        buf = line.buffer(1500.0, join_style=1, cap_style=1)
        v2, f2 = [], []
        polys = list(buf.geoms) if buf.geom_type == "MultiPolygon" else [buf]
        for poly in polys:
            _add_poly_m(poly, 7.0, v2, f2)
        info = _write_glb(v2, f2, out_dir / f"arc_{name}.glb", f"arc_{name}")
        assets.append({"name": f"arc_{name}", "glb": info["glb"],
                       "position": [0, 0, 0], "heading_deg": 0, "scale": 1.0,
                       "colours": {f"arc_{name}": ARC_HEX}})
        assets.append({"name": f"inst_{name}", "glb": dot["glb"],
                       "position": [x, y, 0], "heading_deg": 0, "scale": 1.0,
                       "colours": {"inst_dot": GOLD_HEX}})
    texts = [{"text": "FLESLAND", "position": [hx, hy + 18000, 20.0],
              "size_m": 12000, "heading_deg": 0, "colour": GOLD_HEX}]
    for nm in RINGS_NM:
        r = nm * NM_M
        # label at the top of the ring (north, over the sea, in frame)
        texts.append({"text": f"{nm} NM",
                      "position": [hx, hy + r + 9000, 20.0],
                      "size_m": 12000, "heading_deg": 0, "colour": LABEL_HEX})
    spec = {
        "assets": assets,
        "texts": texts,
        "sea": {"level_m": 0.0, "size_m": 600000, "colour": "sea"},
        "camera": {"position": [0, -342000, 456000], "look_at": [0, 10000, 0],
                   "lens_mm": 35},
        "lights": {"key": {"dir": [-0.4, -0.7, 0.6], "kelvin": 5600},
                   "fill": {"dir": [0.7, 0.2, 0.3], "kelvin": 8000},
                   "rim": {"dir": [0.3, 0.9, 0.4], "kelvin": 4000}},
        "sky": {"top": "sky_top", "bottom": "sky_bottom"},
        "palette": {"sea": SEA_HEX},
        "shading": {"mode": "flat", "line_px": 0},
        "resolution": list(resolution), "samples": samples, "seed": 7,
    }
    (out_dir / "scene.json").write_text(json.dumps(spec, indent=2))
    return {"spec": spec, "land_triangles": land["triangles"],
            "installations": len(pos), "heliport": heli}


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "out" / "bergen-service-map"
    res = build_scene(out)
    print(f"land: {res['land_triangles']} triangles; "
          f"{res['installations']} installations; heliport {res['heliport']}")
    print("scene.json:", out / "scene.json")
