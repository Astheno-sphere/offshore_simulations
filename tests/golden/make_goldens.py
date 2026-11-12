"""Regenerate the visual-gate reference frames from the repo's own renderers (small, deterministic, synthetic data).

    PYTHONPATH=. python tests/golden/make_goldens.py            # rewrite tests/golden/{section,map,findings}.png + .text.json
    PYTHONPATH=. python tests/golden/make_goldens.py --table    # print the measurements the GATE_SPEC thresholds come from

section   section.run_section with a synthetic coast + route standing in for the world data (the film's full layout, map panel on)
map       mappanel.MapPanel on the same synthetic coast (panel only)
findings  findings fan from the synthetic ensemble of tests/test_story_shots.py
Sizes are 1/3 of the canonical 1080 x 1350 (section, findings) and 0.5 x the 968 x 300 panel (map). Never regenerate to make a
failing gate pass: a changed golden is a reviewed visual change (commit it with the reason).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SIZE = (360, 450)
MAP_SIZE = (484, 150)
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]


def synthetic_ctx():
    """A fjord: jagged west and east coasts (seeded noise), two islands, a route down the middle channel."""
    from shapely.geometry import Polygon
    rng = np.random.default_rng(3)
    y = np.linspace(58.9, 59.85, 40)
    west = 10.55 + 0.10 * np.sin(y * 9) + rng.normal(0, 0.018, y.size)
    east = 11.12 + 0.08 * np.sin(y * 7 + 1) + rng.normal(0, 0.018, y.size)
    land = Polygon([(10.0, 58.9)] + list(zip(west, y)) + [(10.0, 59.85)])
    land = land.union(Polygon(list(zip(east, y)) + [(11.6, 59.85), (11.6, 58.9)]))
    land = land.union(Polygon([(10.83, 59.30), (10.90, 59.27), (10.93, 59.34), (10.86, 59.38)]))
    land = land.union(Polygon([(10.80, 59.52), (10.87, 59.50), (10.89, 59.56), (10.81, 59.58)]))
    t = np.linspace(0, 1, 60)
    route = list(zip(10.86 + 0.05 * np.sin(5 * t) + 0.03 * t, 58.98 + 0.7 * t))
    k = 14
    bbox = (10.45, 58.95, 11.2, 59.75)
    return {"land": land, "bbox": bbox, "route": route, "k": k, "marker": route[k], "t_h": 1.5, "agent": "PSV-1",
            "paper": "synthetic-fjord", "status": "re-run under assumptions"}


def section_frame(tmp: Path):
    from test_story_shots import sec_shot

    from offsim.cinema.visual_gate import capture_text
    from offsim.motion import section
    shot = sec_shot(seconds=0.2, map={"world": "x", "run": "y", "agent": "PSV-1", "label": "SYNTHETIC FJORD ROUTE"})
    real = section.map_context
    section.map_context = lambda *a, **k: synthetic_ctx()
    try:
        with capture_text(canvas=(section.W, section.H)) as texts:
            res = section.run_section(shot, None, tmp, 30, None, SIZE, 0, strict_map=True, spinup_steps=40, log=lambda *_: None)
    finally:
        section.map_context = real
    from PIL import Image
    return Image.open(res["frames"][0]).convert("RGB"), texts


def map_frame():
    from offsim.cinema.visual_gate import capture_text
    from offsim.motion.mappanel import MapPanel
    c = synthetic_ctx()
    mp = MapPanel(c["land"], c["bbox"], size=MAP_SIZE, ss=2, seconds=5.0, n_streaks=900, seed=0)
    for u in (0.2, 0.5, 0.8):                               # let the streak tails build up like the film does
        mp.frame(u, c["route"], c["k"] + 1, c["marker"], wind=(8.0, 0.0))
    with capture_text() as texts:
        img = mp.frame(1.0, c["route"], c["k"] + 1, c["marker"], wind=(8.0, 0.0))
    return img.convert("RGB"), texts


def findings_frame(tmp: Path):
    from test_story_shots import FAN, make_report

    from offsim.cinema.visual_gate import capture_text
    from offsim.motion import findings
    rep, _, _ = make_report()
    with capture_text(canvas=(1080, 1350)) as texts:
        res = findings.run_findings(FAN, rep, tmp, 30, size=SIZE, only=-1, log=lambda *_: None)
    from PIL import Image
    return Image.open(res["frames"][0]).convert("RGB"), texts


def all_frames(tmp: Path):
    return {"section": section_frame(tmp / "s") + ("section",), "map": map_frame() + ("map",), "findings": findings_frame(tmp / "f") + ("findings",)}


def write(tmp: Path):
    for name, (img, texts, _kind) in all_frames(tmp).items():
        img.save(HERE / f"{name}.png", optimize=True)
        (HERE / f"{name}.text.json").write_text(json.dumps(texts))
        print("wrote", name, img.size)


def table(tmp: Path):
    from offsim.cinema import visual_gate as vg
    for name, (img, texts, kind) in all_frames(tmp).items():
        r = vg.inspect(img, {"kind": kind, "text": texts or None, "strokes": {"preview_of": 1080 if kind != "map" else 968}})
        print(name, img.size)
        for k in ("edges", "strokes", "balance"):
            print("  ", k, {a: b for a, b in r[k].items() if a != "cells"})
        print("   palette", {k: v for k, v in r["palette"].items() if k != "off_colors"}, r["palette"]["off_colors"])
        print("   contrast", {k: v for k, v in r["contrast"].items() if k != "items"})
        print("   type", r["type_scale"], "margins", r["margins"])


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as t:
        (table if "--table" in sys.argv else write)(Path(t))
