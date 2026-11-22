"""render_shot(spec, out_png): write scene.json, run tools/blender_shot.py as a separate process, return timing."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "blender_shot.py"


def render_shot(spec: dict, out_png, timeout: float = 600.0, python: str | None = None) -> dict:
    """Render `spec` (the scene.json schema in docs/BLENDER.md) to `out_png`. Raises RuntimeError on failure.

    Returns {"png", "seconds", "scene_json", "resolution", "samples", "bbox_check"}; bbox_check is what the
    script measured on the imported objects (world-space metres) against the bbox the spec declared, if any.
    """
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    scene_json = out_png.with_suffix(".scene.json")
    scene_json.write_text(json.dumps(spec, indent=2))
    report = out_png.with_suffix(".report.json")
    report.unlink(missing_ok=True)
    t0 = time.time()
    try:
        r = subprocess.run([python or sys.executable, str(SCRIPT), str(scene_json), str(out_png)],
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"blender_shot timed out after {timeout:.0f} s") from e
    secs = time.time() - t0
    if r.returncode != 0 or not out_png.exists():
        raise RuntimeError(f"blender_shot failed ({r.returncode}): {(r.stderr or r.stdout)[-800:]}")
    rep = json.loads(report.read_text()) if report.exists() else {}
    return {"png": str(out_png), "seconds": round(secs, 2), "scene_json": str(scene_json),
            "resolution": rep.get("resolution"), "samples": rep.get("samples"), "bbox_check": rep.get("bbox_check", [])}


def helideck_spec(out_dir=None, resolution=(960, 540), samples=16, heading_deg=200.0) -> dict:
    """Scene spec: Sikorsky S-92 parked on the platform_jacket helideck. Exports both GLBs; z=0 is mean sea level."""
    from offsim.blender.export import export_platform, export_s92
    s92, plat = export_s92(out_dir), export_platform(out_dir)
    msl = plat["meta"]["msl_z"]
    hx, hy = plat["meta"]["helideck_centre"]
    zh = plat["meta"]["helideck_z"] - msl
    # S-92 origin is at the nose-side of the rotor axis box; centre its footprint on the helideck centre
    x0, x1, y0, y1, _, _ = s92["bbox_m"]
    return {
        "assets": [
            {"name": "platform_jacket", "glb": plat["glb"], "position": [0, 0, -msl], "heading_deg": 0, "scale": 1.0,
             "colours": {"default": "steel", "deck": "deck", "helideck": "deck", "crane": "accent", "flare": "accent", "lifeboat": "accent"},
             "expect_size_m": [round(v, 4) for v in plat["size_m"]]},
            {"name": "s92", "glb": s92["glb"], "position": [hx, hy, zh], "heading_deg": heading_deg, "scale": 1.0,
             "colours": {"default": "hull", "rotor": "steel", "tail_rotor": "steel", "gear": "steel", "glazing": "ink", "sponsons": "accent"},
             "expect_size_m": [round(v, 4) for v in s92["size_m"]]},
        ],
        "sea": {"level_m": 0.0, "size_m": 6000, "colour": "sea"},
        "camera": {"position": [hx + 38, hy - 52, zh + 11], "look_at": [hx, hy, zh + 2.2], "lens_mm": 40},
        "lights": {"key": {"dir": [-0.4, -0.7, 0.6], "kelvin": 5600}, "fill": {"dir": [0.7, 0.2, 0.3], "kelvin": 8000},
                   "rim": {"dir": [0.3, 0.9, 0.4], "kelvin": 4000}},
        "sky": {"top": "sky_top", "bottom": "sky_bottom"},
        "palette": {},
        "shading": {"mode": "flat", "line_px": 1.2},
        "resolution": list(resolution), "samples": samples, "seed": 7,
    }
