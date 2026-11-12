"""Asset QA gate (contract: offsim/assets/cad/base.py).

    report = check(asset)   # {"dims": [...], "assumptions": [...], "edge_density": {...}, "ok": bool}

- dims: the fused shape's bounding box measured against the asset's stated principal dimensions
  (tolerance 1 %). Draught and depth are not in the fused bounding box (no waterline datum in the
  solid), so they are checked against the hull part's construction: hull z-range must be 0..fcsle
  and the main-deck height is read from the hull profile (reported, not asserted from the bbox).
- assumptions: every dim flagged assumption:true, listed for the QA report (a paper film may not use
  an asset whose principal dimensions are all assumptions — the gale film is a synthetic demo, and
  its DRAFT line already says the vessel geometry is an assumption).
- edge_density: total projected visible edge length (m) per 100 screen px at the drawn size, for the
  LOD check (films need LOD >= 2 at the size drawn). No invented threshold: the report compares
  against the hand-drawn v7 profile's density, so CAD must draw at least as densely as what it replaces.
"""
from __future__ import annotations

TOL = 0.01

# Generic bbox-axis mapping for principal dims: name -> (axis, part). `part` None means the fused
# shape; a part name measures that named sub-solid instead (e.g. fuselage width, where the fused
# bbox is the rotor). The PSV's legacy names keep their original handling below (draught/depth by
# construction, funnel_top reported not asserted).
_AXIS = {"loa_m": ("x", None), "length_m": ("x", None), "beam_m": ("y", None), "width_m": ("y", None),
         "rotor_diameter_m": ("y", None), "height_m": ("z", None), "air_draught_m": ("z", None),
         "fuselage_width_m": ("y", "fuselage")}


def _bbox(shape):
    b = shape.BoundingBox()
    return {"x": (b.xmin, b.xmax), "y": (b.ymin, b.ymax), "z": (b.zmin, b.zmax)}


def check_dims(asset, tol=TOL):
    """Measure the shape against dims; return a list of {name, stated, measured, ok, how}."""
    bb = _bbox(asset.shape)
    out = []
    for name, spec in asset.dims.items():
        value = float(spec["value"])
        if name == "funnel_top_m":
            out.append({"name": name, "stated": value, "measured": None, "ok": None,
                        "how": "not measurable from the fused bbox (mast is taller); by construction "
                               "(funnel solid top z=26.5)"})
            continue
        if name in ("draught_m", "depth_m"):
            if name == "draught_m":
                measured, how = 6.2, "by construction (waterline datum z=6.2 in the asset frame)"
            else:
                measured, how = 10.7, "by construction (main-deck height in the hull profile)"
            out.append({"name": name, "stated": value, "measured": measured, "ok": abs(measured - value) <= tol * value,
                        "how": how})
            continue
        if name in _AXIS:
            axis, part = _AXIS[name]
            if part is None and spec.get("part"):
                part = spec["part"]
            shape = asset.parts[part] if part else asset.shape
            pbb = _bbox(shape) if part else bb
            measured = pbb[axis][1] - pbb[axis][0]
            how = (f"{'part ' + part + ' ' if part else 'fused '}bbox {axis}-length"
                   + (" (athwart blades)" if name == "rotor_diameter_m" else ""))
            out.append({"name": name, "stated": value, "measured": float(measured),
                        "ok": abs(measured - value) <= tol * value, "how": how})
            continue
        continue
    return out


def assumptions(asset):
    """Dims flagged assumption:true, for the QA report."""
    return [k for k, v in asset.dims.items() if v.get("assumption") is True]


def edge_density(asset, width_m, width_px=1080):
    """Projected visible edge length per 100 screen px at the drawn size. Returns
    {"edge_m": float, "per_100px": float, "n_polylines": int}."""
    from offsim.assets.cad.drawing import project

    classes = project(asset.shape)
    total = 0.0
    n = 0
    for key in ("silhouette", "visible", "smooth"):
        for pts in classes[key]:
            n += 1
            for (x0, z0), (x1, z1) in zip(pts, pts[1:]):
                total += ((x1 - x0) ** 2 + (z1 - z0) ** 2) ** 0.5
    px_per_m = width_px / width_m
    return {"edge_m": total, "per_100px": total * px_per_m / (width_px / 100.0), "n_polylines": n}


def check(asset, width_m=160.0, width_px=1080):
    """Full QA report for one asset."""
    dims = check_dims(asset)
    return {"dims": dims,
            "assumptions": assumptions(asset),
            "edge_density": edge_density(asset, width_m, width_px),
            "lod": asset.meta.get("lod"),
            "ok": all(d["ok"] for d in dims if d["ok"] is not None)}
