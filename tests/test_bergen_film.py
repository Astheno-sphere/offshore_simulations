"""Tests for the Bergen one-winter pilot film (tools/bergen_film.py).

The clamp-guard test is the v10 pattern ported: the film's own glide camera is
stepped over all 900 frames on BOTH the clean path and a resumed-from-510 path,
and every view must stay inside the display land (lat within the strip bounds,
east edge <= land east bound -- the west overhang is verified open sea, see the
fetch log), the focus marker must stay in frame, and the peak pan rate must stay
under the 0.25 widths/s cinema cap. Tests that need the fetched places skip
with a reason when it is absent (like the v10 coverage test).
"""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bergen_film as B

ROOT = Path(__file__).resolve().parents[1]
RUN = Path("/home/hatch/workspace/docs/linkedin/07-gribkovskaia/run")
LAND_WIDE = ROOT / "data/worlds/bergen/land.geojson"  # contract land covers the envelope; see film docstring
PLACES = ROOT / "data/worlds/bergen/osm/places_bergen.json"


def _ctx():
    rep = B.load_report()
    stops, heli, tr, routes, times, w11r, w11t = B.load_traj()
    weather = B.load_weather()
    B._CTX = (rep, stops, heli, routes, times, w11r, w11t, weather)
    bbox = (min(min(lon for lon, _ in routes[a]) for a in routes) - 0.06,
            min(min(lat for _, lat in routes[a]) for a in routes) - 0.06,
            max(max(lon for lon, _ in routes[a]) for a in routes) + 0.06,
            max(max(lat for _, lat in routes[a]) for a in routes) + 0.06)
    return rep, stops, heli, routes, times, w11r, w11t, bbox


def _run_glide(bbox, w11r, w11t, start=0):
    g = B.Glide(bbox)
    centres, views = [], []
    for f in range(B.N):
        _, focus, _, _ = B.focus_of(f, w11r, w11t)
        cx, cy, span = g.view((f + 1) / B.N, focus, f)
        if f >= start:
            centres.append((cx, cy))
            views.append((cx - (B.PANEL_W / 2) * span / g.k, cy - (B.PANEL_H / 2) * span,
                          cx + (B.PANEL_W / 2) * span / g.k, cy + (B.PANEL_H / 2) * span))
    return g, centres, views


def test_bergen_gates_contract_ok():
    B.gates()  # raises unless contract.validate passes on BOTH trajectories


def test_bergen_narration_from_measured_report():
    rep = B.load_report()
    deck = B.narration(rep)
    joined = " ".join(" ".join(v) for v in deck.values())
    # the lean-windows honesty line lives in the DRAFT footer (every frame), not the deck
    assert "56 h" in B.DRAFT and "50 h" in B.DRAFT
    assert "29.5" in joined and "0.0" in joined  # featured delay, P90 unmet
    # featured Hs/wind are the INTERPOLATED 12:30 values (7.24 / 21.49); the 12:00
    # hourly values (7.26 / 21.58) must not appear anywhere on screen
    assert "7.24" in joined and "6.0" in joined
    assert "7.26" not in joined and "21.58" not in joined
    assert "21.49" in joined
    assert "[draft" not in joined and "Equinor's own optimiser" not in joined
    assert "The paper's optimiser" in joined
    assert "1,209" in joined or "1209" in joined
    assert "24-winter" in joined or "one winter only" in joined
    # the section headline carries the same interpolated Hs as the deck
    hl = B.headlines(rep)["section"]
    assert "7.24" in "".join(t for line in hl for t, _ in line)
    assert "7.26" not in "".join(t for line in hl for t, _ in line)


def test_bergen_off_frame_callout_collapses():
    # four helicopters parked at the heliport clamp to one edge spot: one callout,
    # not four stacked labels (f0300). A lone off-frame heli keeps its own id.
    heli = (900.0, 290.0)
    off4 = [("H1-16h", 905.0, 310.0), ("H2-14h", 898.0, 312.0),
            ("H4-10h", 902.0, 308.0), ("H5-10h", 900.0, 311.0)]
    co = B._off_frame_callouts(off4, heli)
    assert len(co) == 1
    assert co[0][0] == ["H1-16h", "H2-14h", "H4-10h", "H5-10h"]
    assert co[0][3] == "4 HELIS AT FLESLAND"
    # the f0300 case: two parked at the heliport, two on final approach ~40 px
    # out -- still one "AT FLESLAND" callout, not four labels
    off_mixed = [("H1-16h", 893.0, 415.0), ("H2-14h", 861.0, 391.0),
                 ("H4-10h", 893.0, 415.0), ("H5-10h", 860.0, 434.0)]
    co_m = B._off_frame_callouts(off_mixed, (893.4, 414.9))
    assert len(co_m) == 1 and co_m[0][3] == "4 HELIS AT FLESLAND"
    co1 = B._off_frame_callouts([("H1-16h", 100.0, -30.0)], heli)
    assert len(co1) == 1 and co1[0][3] == "H1-16h"
    # same spot but far from the heliport: generic label, no Flesland claim
    co2 = B._off_frame_callouts([("H1-16h", 100.0, -30.0), ("H2-14h", 105.0, -28.0)], heli)
    assert len(co2) == 1 and co2[0][3] == "2 HELIS"


def test_bergen_static_wide_rejected():
    _, _, _, routes, _, _, _, bbox = _ctx()
    import math
    fw = (bbox[2] - bbox[0]) * 111.32 * math.cos(math.radians(60.2))
    fh = (bbox[3] - bbox[1]) * 111.32
    fit_px = B.PANEL_H * fw / fh
    assert fit_px < 0.30 * B.PANEL_W, f"static wide would fit {fit_px:.0f}px, not rejected"


def test_bergen_camera_envelope_marker_pan():
    if not (LAND_WIDE.exists() and PLACES.exists()):
        pytest.skip("Bergen places not fetched yet (world-fetch/fetch_bergen_places.py)")
    import geopandas as gpd
    land = gpd.read_file(LAND_WIDE).geometry.union_all()
    lb = land.bounds  # (lon0, lat0, lon1, lat1)
    fetch_log = json.loads((ROOT / "data/worlds/bergen/osm/fetch_bergen_places.json").read_text())
    assert fetch_log["steps"]["west_sea"]["coastline_ways_west_of_4.30"] == 0, \
        "west overhang is only valid if no coastline exists west of lon 4.30"
    _, _, _, _, _, w11r, w11t, bbox = _ctx()
    g, centres, views = _run_glide(bbox, w11r, w11t)
    # every view inside the land in lat, and east edge inside the land east bound
    for vx0, vy0, vx1, vy1 in views:
        assert vy0 >= lb[1] - 1e-9 and vy1 <= lb[3] + 1e-9, f"view lat {vy0:.3f}-{vy1:.3f} outside land {lb[1]:.3f}-{lb[3]:.3f}"
        assert vx1 <= lb[2] + 1e-9, f"view east {vx1:.3f} past land east {lb[2]:.3f}"
    # focus marker in frame on every frame; peak pan under the 0.25 widths/s cap
    worst = 0.0
    for f in range(B.N):
        focus_ag, _, markers, _ = B.focus_of(f, w11r, w11t)
        cx, cy = centres[f]
        _, mk = markers[focus_ag]
        mx = (mk[0] - cx) * g.k / g.span + B.PANEL_W / 2
        my = B.PANEL_H / 2 - (mk[1] - cy) / g.span
        assert 0 <= mx < B.PANEL_W and 0 <= my < B.PANEL_H, \
            f"focus {focus_ag} off frame at f{f}: ({mx:.0f}, {my:.0f})"
        worst = max(worst, max(abs(mx - B.PANEL_W / 2) / (B.PANEL_W / 2),
                               abs(my - B.PANEL_H / 2) / (B.PANEL_H / 2)))
    assert worst < 1.0
    assert g._pan_max <= 0.25, f"peak pan {g._pan_max:.3f} widths/s over the 0.25 cap"
    # resumed path (stepped silently from 0) must reproduce the clean centres
    g2, centres2, _ = _run_glide(bbox, w11r, w11t, start=510)
    for (c1, c2) in zip(centres[510:], centres2):
        assert abs(c1[0] - c2[0]) < 1e-9 and abs(c1[1] - c2[1]) < 1e-9


def test_bergen_strip_covers_envelope():
    if not (LAND_WIDE.exists() and PLACES.exists()):
        pytest.skip("Bergen places not fetched yet (world-fetch/fetch_bergen_places.py)")
    _, stops, heli, _, _, w11r, w11t, bbox = _ctx()
    strip = B.Strip(B.Glide(bbox), stops, heli)
    env, _, _ = B.measure_envelope(B.Glide(bbox))
    assert strip.lon0 <= env[0] and strip.lon1 >= env[2]
    assert strip.lat0 <= env[1] and strip.lat1 >= env[3]
    names = {t for t, *_ in strip.label_items}
    assert {"BERGEN", "FLORØ", "FLESLAND", "NORTH SEA"} <= names
    assert len([t for t in names if t.startswith("B") and t[1:].isdigit()]) == 20
