"""Blender bridge: bpy runs only in a subprocess (tools/blender_shot.py); offsim.blender must not import it."""
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HAS_BPY = importlib.util.find_spec("bpy") is not None
needs_bpy = pytest.mark.skipif(not HAS_BPY, reason="bpy not installed")


def test_importing_offsim_blender_does_not_import_bpy():
    code = ("import sys, offsim.blender, offsim.blender.export, offsim.blender.shot; "
            "assert 'bpy' not in sys.modules, 'bpy leaked into the offsim process'")
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-500:]


@needs_bpy
def test_s92_glb_bbox_matches_sourced_dimensions(tmp_path):
    from offsim.blender.export import export_s92
    e = export_s92(tmp_path)
    dx, dy, dz = e["size_m"]
    d = e["dims"]
    for got, key in ((dx, "length_m"), (dy, "rotor_diameter_m"), (dz, "height_m")):
        want = d[key]["value"]
        assert abs(got - want) / want < 0.01, f"{key}: {got:.3f} vs sourced {want}"
    assert Path(e["glb"]).stat().st_size > 10_000 and not e["skipped"]


@needs_bpy
def test_draft_render_of_s92_on_helideck(tmp_path):
    from PIL import Image
    from offsim.blender.shot import helideck_spec, render_shot
    r = render_shot(helideck_spec(tmp_path, resolution=(320, 180), samples=4), tmp_path / "d.png", timeout=120)
    assert r["seconds"] < 120
    for c in r["bbox_check"]:  # the GLB round-trip through Blender keeps the CAD size
        assert c["max_rel_err"] < 0.01, c
    im = Image.open(r["png"]).convert("RGB")
    assert im.size == (320, 180)
    assert len(im.getcolors(maxcolors=1_000_000)) > 8, "render is a flat colour"
