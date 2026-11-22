"""Export CadQuery assets to GLB (glTF 2.0, Y-up as the spec requires; Blender's importer returns it to Z-up).

Units are metres. Bounding boxes are returned in the CAD frame (x forward, z up), tight (OCC AddOptimal), so they
compare directly with the sourced `dims` of the asset.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "out" / "blender"


def _bbox(shape):
    from offsim.assets.cad.air import bbox  # tight OCC box; same function for every asset module
    return tuple(float(v) for v in bbox(shape))


def export_asset(name: str, out_dir: Path | None = None, tol: float = 0.05, angular: float = 0.2, skip_parts=(), **params) -> dict:
    """Build asset `name` (offsim.assets.cad registry), write <out_dir>/<name>.glb with one node per part.

    Returns {"glb": path, "bbox_m": (xmin, xmax, ymin, ymax, zmin, zmax), "size_m": (dx, dy, dz), "parts": [...],
    "meta": asset meta, "dims": asset dims}. Parts that fail to tessellate are skipped and listed under "skipped".
    """
    import trimesh
    from offsim.assets.cad import base

    out_dir = Path(out_dir or OUT)
    out_dir.mkdir(parents=True, exist_ok=True)
    model = base.build(name, **params)
    parts = model.parts or {name: model.shape}
    scene = trimesh.Scene()
    done, skipped = [], []
    for pname, shp in parts.items():
        if pname in skip_parts:
            continue
        try:
            v, f = shp.tessellate(tol, angular)
        except Exception:  # noqa: BLE001 - a bad part must not lose the asset; reported to the caller
            skipped.append(pname)
            continue
        if not len(f):
            skipped.append(pname)
            continue
        v = np.array([(p.x, p.y, p.z) for p in v], dtype=float)
        v = v[:, [0, 2, 1]] * np.array([1.0, 1.0, -1.0])  # CAD (x,y,z up) -> glTF (x, z, -y)
        scene.add_geometry(trimesh.Trimesh(v, np.array(f), process=False), node_name=pname, geom_name=pname)
        done.append(pname)
    glb = out_dir / f"{name}.glb"
    glb.write_bytes(scene.export(file_type="glb"))
    bb = _bbox(model.shape)
    return {"glb": str(glb), "bbox_m": bb, "size_m": (bb[1] - bb[0], bb[3] - bb[2], bb[5] - bb[4]),
            "parts": done, "skipped": skipped, "meta": model.meta, "dims": model.dims}


def export_s92(out_dir=None) -> dict:
    return export_asset("s92", out_dir)


def export_platform(out_dir=None) -> dict:
    return export_asset("platform_jacket", out_dir, tol=0.1, angular=0.3, skip_parts=("helideck_plate",))  # the plate is already inside "helideck"
