"""Asset QA gate: scale and detail are measured, not claimed.

    r = qa(model, drawn_height_px=240, name="psv")   # dict report
    ok, why = passes(r, min_density=10)
    problems = gate("psv", params, drawn_height_px=240)   # build + qa + passes -> [] or a list of refusals (story.check)

What is measured
* dims      each model.dims entry that can be measured is compared with the solid's bounding box; |measured - value| /
            value must be <= tol (1 %). Default measurement per dim name (override per dim with `"measure": {"axis": ...,
            "part": ...}` in the dim dict, or per asset in registry.yaml `measure:`):
              loa_m, length_m                      x extent of the whole shape
              fuselage_length_m                    x extent of the part whose name contains "fuselage" (else whole)
              beam_m, width_m                      y extent (beam_m: part "hull" if present)
              depth_m                              z extent (part "hull" if present)
              height_m, stature_m                  z extent of the whole shape
              rotor_diameter_m                     max(x extent, y extent) of the part containing "rotor"
              base_width_m, deck_width_m, crown_diameter_m   y extent (whole)
            Others (draught_m, ...) are "unchecked" (they need a waterline), listed, and do not fail the gate.
* sourced   dims with "src" vs {"assumption": True}. principal = registry required_dims (all dims if the asset is not
            in the registry). Gate: >= 1 principal dim sourced, every required dim present.
* lod, edge density (projected visible+detail polylines per 100 px of drawn height; needs drawn_height_px), the
  smallest feature the screen can show (0.75 px / px-per-metre) and how many polylines vanish at that scale.
"""
from __future__ import annotations

import math
from pathlib import Path

import yaml

REGISTRY_PATH = Path(__file__).with_name("registry.yaml")
TOL = 0.01
DEFAULT_MIN_DENSITY = 10.0           # polylines per 100 px of drawn height; starting value, tune against the reference film

# dim name -> (axis, part substring | None, part_required)
_DEFAULT_MEASURE = {
    "loa_m": ("x", None), "length_m": ("x", None), "fuselage_length_m": ("x", "fuselage"),
    "beam_m": ("y", "hull"), "width_m": ("y", None), "depth_m": ("z", "hull"),
    "height_m": ("z", None), "stature_m": ("z", None), "rotor_diameter_m": ("xy", "rotor"),
    "base_width_m": ("y", None), "deck_width_m": ("y", None), "crown_diameter_m": ("y", None),
}


def registry() -> dict:
    return yaml.safe_load(REGISTRY_PATH.read_text()) or {}


def _bbox(shape):
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    b = Bnd_Box()
    BRepBndLib.AddOptimal_s(getattr(shape, "wrapped", shape), b, False, False)
    return b.Get()                                  # xmin, ymin, zmin, xmax, ymax, zmax


def _extent(model, axis, part):
    """(extent_m, part_used). Part = substring match over model.parts; whole shape if none match."""
    names = [k for k in (model.parts or {}) if part and part in k]
    boxes = [_bbox(model.parts[k]) for k in names] or [_bbox(model.shape)]
    x0, y0, z0 = (min(b[i] for b in boxes) for i in (0, 1, 2))
    x1, y1, z1 = (max(b[i] for b in boxes) for i in (3, 4, 5))
    ext = {"x": x1 - x0, "y": y1 - y0, "z": z1 - z0}
    val = max(ext["x"], ext["y"]) if axis == "xy" else ext[axis]
    return val, (",".join(names) if names else "*")


def measured_bbox(model) -> dict:
    x0, y0, z0, x1, y1, z1 = _bbox(model.shape)
    return {"x": x1 - x0, "y": y1 - y0, "z": z1 - z0, "min": (x0, y0, z0), "max": (x1, y1, z1)}


def qa(model, drawn_height_px=None, name=None, tol=TOL, view="side") -> dict:
    reg = registry()
    name = name or (model.meta or {}).get("asset") or (model.meta or {}).get("name")
    entry = reg.get(name, {}) if name else {}
    overrides = entry.get("measure", {})
    required = list(entry.get("required_dims", []))
    dims = model.dims or {}
    rows = []
    for k, d in dims.items():
        sourced = bool(d.get("src")) and not d.get("assumption")
        row = {"name": k, "value": d.get("value"), "sourced": sourced, "measured": None, "rel_err": None, "pass": None,
               "measure": None}
        m = {**({"axis": _DEFAULT_MEASURE[k][0], "part": _DEFAULT_MEASURE[k][1]} if k in _DEFAULT_MEASURE else {}),
             **overrides.get(k, {}), **(d.get("measure") or {})}
        if m.get("axis") and d.get("value"):
            val, used = _extent(model, m["axis"], m.get("part"))
            row.update(measured=val, rel_err=abs(val - d["value"]) / abs(d["value"]), measure=f"{m['axis']}:{used}")
            row["pass"] = row["rel_err"] <= tol
        rows.append(row)
    principal = [r for r in rows if (r["name"] in required if required else True)]
    rep = {
        "name": name, "dims": rows, "tol": tol,
        "dims_checked": sum(r["pass"] is not None for r in rows),
        "dims_failed": [r["name"] for r in rows if r["pass"] is False],
        "dims_unchecked": [r["name"] for r in rows if r["pass"] is None],
        "missing_required": [k for k in required if k not in dims],
        "sourced": sum(r["sourced"] for r in rows), "assumed": sum(not r["sourced"] for r in rows),
        "principal_sourced": [r["name"] for r in principal if r["sourced"]],
        "principal_assumed": [r["name"] for r in principal if not r["sourced"]],
        "bbox_m": {k: round(v, 4) for k, v in measured_bbox(model).items() if k in "xyz"},
        "parts": sorted(model.parts or {}), "lod": (model.meta or {}).get("lod"),
        "min_lod": entry.get("min_lod", 2), "class": (model.meta or {}).get("class"),
        "licence": (model.meta or {}).get("licence"),
        "drawn_height_px": drawn_height_px, "density_per_100px": None, "min_feature_m": None, "dropped_at_scale": None,
    }
    if drawn_height_px:
        from offsim.assets.cad.drawing import MIN_PX, project
        d = project(model, view, silhouette=False)
        H = max(d.height, 1e-9)
        s = float(drawn_height_px) / H                                    # px per metre
        n = sum(1 for l in d.lines if l["cls"] in ("visible", "detail"))
        rep["density_per_100px"] = n * 100.0 / float(drawn_height_px)
        rep["edges"] = n
        rep["min_feature_m"] = MIN_PX / s
        rep["dropped_at_scale"] = sum(1 for l in d.lines if l["cls"] != "hidden" and
                                      sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(l["pts"], l["pts"][1:])) * s < MIN_PX)
        rep["px_per_m"] = s
    return rep


def passes(report, min_density=None) -> tuple:
    """(ok, reasons). Gate: no measurable dim off by more than tol, >= 1 measurable dim, all registry dims present, >= 1
    principal dim sourced; if the report was made with drawn_height_px: LOD >= min_lod and density >= min_density."""
    why = []
    if report["dims_failed"]:
        bad = {r["name"]: f"{r['rel_err']:.1%}" for r in report["dims"] if r["pass"] is False}
        why.append(f"dims off by more than {report['tol']:.0%}: {bad}")
    if not report["dims_checked"]:
        why.append("no principal dimension could be measured against the solid")
    if report["missing_required"]:
        why.append(f"missing required dims {report['missing_required']}")
    if not report["principal_sourced"]:
        why.append("all principal dimensions are assumptions (need at least one with src)")
    if report.get("drawn_height_px"):
        md = DEFAULT_MIN_DENSITY if min_density is None else min_density
        if report["lod"] is not None and report["lod"] < report["min_lod"]:
            why.append(f"LOD {report['lod']} < {report['min_lod']} required at drawn size")
        if report["density_per_100px"] is not None and report["density_per_100px"] < md:
            why.append(f"edge density {report['density_per_100px']:.1f}/100px < {md:g} at {report['drawn_height_px']} px")
    return (not why), why


def gate(name, params=None, drawn_height_px=None, min_density=None) -> list:
    """Build the registered asset and run the gate; returns refusal messages (empty = go). Never raises."""
    try:
        from offsim.assets.cad import base
        model = base.build(name, **(params or {}))
    except Exception as e:                       # import errors from a not-yet-written module, bad params, OCC errors
        return [f"asset {name!r} cannot be built ({type(e).__name__}: {e})"]
    try:
        ok, why = passes(qa(model, drawn_height_px, name=name), min_density)
    except Exception as e:
        return [f"asset {name!r} QA failed to run ({type(e).__name__}: {e})"]
    return [f"asset {name!r}: {w}" for w in why]


if __name__ == "__main__":                       # python -m offsim.assets.cad.qa psv [drawn_height_px]
    import json
    import sys
    from offsim.assets.cad import base
    nm = sys.argv[1]
    hp = float(sys.argv[2]) if len(sys.argv) > 2 else None
    r = qa(base.build(nm), hp, name=nm)
    print(json.dumps(r, indent=1, default=str))
    print(passes(r))
