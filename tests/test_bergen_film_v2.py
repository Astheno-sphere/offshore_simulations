"""Tests for the Bergen pilot film v2 rebuild (tools/bergen_film_v2.py).

The rebuild's three faults each get a guard that fails if the fault returns:
1. the sea is LIVE (surface changes with film time at fixed Hs, std stays Hs/4);
2. the section helicopter is the real CAD S-92 (HLR prims, bounds, edge length) with a
   turning tail rotor and a bounded bob -- not the hand-drawn sticker;
3. the map draws ONLY the story's route (map_route_agents), never the week fan.
Plus the v1 camera pattern ported to the v2 camera (findings beat now advances 18:00-18:30),
the contract gates, and the narration honesty lines (interpolated 7.24, never 7.26;
"SEA FROZEN" nowhere in the v2 module).
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bergen_film as B
import bergen_film_v2 as B2

ROOT = Path(__file__).resolve().parents[1]
RUN = Path("/home/hatch/workspace/docs/linkedin/07-gribkovskaia/run")
LAND_WIDE = ROOT / "data/worlds/bergen/land.geojson"
PLACES = ROOT / "data/worlds/bergen/osm/places_bergen.json"


@pytest.fixture(autouse=True)
def _patch_map_time():
    """v2's map time (findings advances 18:00-18:30) must be what bergen_film.focus_of
    and measure_envelope see; the charcoal + orange palette must be what every v2
    drawing call sees. Restore both afterwards so the v1 tests are untouched."""
    orig = B.map_run_t_of
    orig_palette = dict(B.P)
    B.map_run_t_of = B2.v2_map_run_t_of
    B2.apply_palette()
    yield
    B.map_run_t_of = orig
    B.P.clear()
    B.P.update(orig_palette)


def _lum(hexs):
    r, g, b = (int(hexs[i:i + 2], 16) / 255 for i in (1, 3, 5))
    f = lambda c: c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = f(r), f(g), f(b)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _ratio(a, b):
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def test_v2_palette_charcoal_orange():
    # the look direction, measured (anchors from Abhinav's AC reel, VIDEO-RE.md):
    # charcoal ground + orange glow, sea kept. The sea is MORE legible on charcoal
    # than it was on v1's maroon (ratio 1.45 vs 1.17), so keeping the flat teal is a
    # measurement, not a default. Heat red is a cue, never small text (2.57:1).
    assert B.P["ground"] == "#0B0B0B" and B.P["accent"] == "#D69E43"
    assert B2.HEAT == "#893C2A" and B2.AMBER == "#AE7C59" and B2.GLOW == "#C58934"
    assert B.P["sea"] == "#16323a", "sea keeps v1's flat teal"
    assert _ratio(B.P["sea"], B.P["ground"]) >= 1.4
    assert _ratio(B.P["sea"], "#331c22") < _ratio(B.P["sea"], B.P["ground"])
    assert _ratio(B.P["accent"], B.P["ground"]) >= 8.0
    assert _ratio(B.P["ink"], B.P["ground"]) >= 16.0
    assert _ratio(B.P["muted"], B.P["ground"]) >= 5.0
    assert _ratio(B2.HEAT, B.P["ground"]) < 3.0
    # the old maroon/gold must not leak back through v2's own drawing
    src = Path(B2.__file__).read_text()
    assert "#331c22" not in src and "#e5a028" not in src
    # heat red is a marker, never text: the only hs-conditional HEAT use is the gauge
    # tick (the clock-row number stays orange -- the first charcoal stills showed the
    # red number going dim)
    assert src.count("HEAT if hs > 6.0") == 1


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


def test_v2_sea_is_live():
    # the v1 fault: the surface was frozen at T_CANCEL in the section beat. At fixed
    # Hs the surface must CHANGE with film time (phase on f/FPS), stay deterministic,
    # and keep the measured significant height (std Hs/4 within 5%).
    xs0, e0 = B2.sea_surface(0, 7.24)
    xs1, e1 = B2.sea_surface(30, 7.24)
    xs0b, e0b = B2.sea_surface(0, 7.24)
    assert np.array_equal(e0, e0b), "sea surface must be deterministic per frame"
    assert not np.allclose(e0, e1), "sea surface must move with film time at fixed Hs"
    assert abs(float(np.std(e0)) - 7.24 / 4) / (7.24 / 4) < 0.05
    assert abs(float(np.std(e1)) - 7.24 / 4) / (7.24 / 4) < 0.05
    # one swell period later the swell repeats but the chop does not fully: the surface
    # is close, not identical -- the sea is alive, not a looped still
    _, e335 = B2.sea_surface(335, 7.24)
    assert not np.allclose(e0, e335)


def test_v2_cad_heli():
    prims, bounds = B2.heli_prims()
    assert len(prims) > 300, f"CAD heli must carry real HLR linework, got {len(prims)} prims"
    umin, umax, vmin, vmax = bounds
    assert 20.0 < umax - umin < 23.0, f"heli length {umax - umin:.2f} m (solid: 22.3 m incl. rotors)"
    assert -0.01 < vmin < 0.01 and 5.0 < vmax < 5.3, f"heli height {vmax:.2f} m (solid: 5.15 m)"
    # the tail rotor turns: 0.5 rev/s on screen, so 15 frames = 90 degrees
    assert B2.tail_rotor_angle(0) == 0.0
    assert abs(B2.tail_rotor_angle(15) - math.pi / 2) < 1e-9
    assert abs(B2.tail_rotor_angle(15) - B2.tail_rotor_angle(0)) > 1.0
    # the bob is bounded and tied to the swell period
    assert B2.heli_bob(0) == 0.0
    assert max(abs(B2.heli_bob(f)) for f in range(0, 336)) <= 0.13
    assert 0.35 <= B2.disc_alpha(0) <= 0.65


def test_v2_map_only_story_routes():
    assert B2.map_route_agents("hook", "H3-10h") == ["H3-10h"]
    assert B2.map_route_agents("map", "H3-10h") == ["H3-10h"]
    assert B2.map_route_agents("section", "H3-10h") == []
    assert B2.map_route_agents("findings", "H2-14h") == []
    # no other agent ever draws a route, in any beat
    for beat in ("hook", "map", "section", "findings"):
        assert all(a in ("H3-10h", "H2-14h") for a in B2.map_route_agents(beat, "H3-10h"))


def test_v2_story_route_starts_at_0945():
    # the map beat's headline is 09:45-12:30, but the first version drew from midnight --
    # and H3 flew a southern round trip 07:00-08:40 that made the map read as two routes
    # crossing at Flesland (whipster FAIL). The drawn window must start at the B17
    # departure and stay north of lat 60.2 (the southern leg dipped to 59.74).
    _, _, heli, _, _, w11r, w11t, _ = _ctx()
    t0k, t1k = B2.story_route_window(w11t["H3-10h"])
    window = w11r["H3-10h"][::7][t0k:t1k]
    assert window and all(lat >= 60.2 for _, lat in window)
    # the window opens at the departure point (Flesland), not mid-leg: the first drawn
    # point is the last sample at or before 09:45, H3 sitting at Flesland
    lon0, lat0 = window[0]
    assert abs(lon0 - heli[0]) < 0.3 and abs(lat0 - heli[1]) < 0.3


def test_v2_rebook_is_real_trajectory():
    # the findings rebook leg must be H2's flown trajectory, not the straight chord
    # Flesland->B3 (the chord crossed the landmass and the marker flew off it --
    # whipster FAIL). The flown path deviates from the chord by far more than a
    # decimation wobble.
    _, stops, heli, _, _, w11r, w11t, _ = _ctx()
    s, d, e = B2.rebook_segment(w11t["H2-14h"], B.T_REBOOK + 1500)
    assert w11t["H2-14h"][s] >= B.T_REBOOK
    assert d > s and e > d
    import math as _m
    ax, ay = heli
    bx, by = stops["B3"]
    seg = w11r["H2-14h"][s:e]
    assert len(seg) > 3
    worst = 0.0
    for lon, lat in seg:
        # perpendicular distance from the point to the Flesland->B3 chord, in degrees
        vx, vy = bx - ax, by - ay
        wx, wy = lon - ax, lat - ay
        t = max(0.0, min(1.0, (wx * vx + wy * vy) / (vx * vx + vy * vy)))
        worst = max(worst, _m.hypot(wx - t * vx, wy - t * vy))
    # the flown path deviates from the chord by 0.018 deg (~2 km) -- small, because the
    # leg is short, but nonzero: it is the flown trajectory, not the chord (whose
    # deviation is 0 by construction). The chord also crossed the landmass; the flown
    # path does too -- a helicopter departing Flesland must cross the coast -- but the
    # marker now sits ON the drawn line, which is the fault being fixed.
    assert worst > 0.01, f"rebook segment hugs the chord (max deviation {worst:.4f} deg)"


def test_v2_disc_alpha():
    # the disc must read in a freeze-frame (whipster round 2: the 0.18-0.42 band was
    # "a single thin blade line over black") -- 0.35-0.65, centre 0.50
    assert B2.disc_alpha(0) == 0.50
    assert 0.35 <= min(B2.disc_alpha(f) for f in range(0, 60)) <= 0.65
    assert 0.35 <= max(B2.disc_alpha(f) for f in range(0, 60)) <= 0.65


def test_v2_segment_exit():
    # geometry of the B3 chevron fix (whipster round 2): a leg from in-panel Flesland
    # to a point off-panel in BOTH axes must exit mid-edge, not at the clamped corner
    ex = B2._segment_exit(800, 250, -500, -485)
    assert ex is not None
    assert abs(ex[1] - 0) < 1.5  # exits the TOP edge
    assert 300 < ex[0] < 450  # mid-edge, not the top-left corner (x=0)
    assert B2._segment_exit(100, 100, 200, 200) is None  # end in-panel: no exit


def test_v2_first_exit():
    # geometry of the B2 chevron fix (whipster re-check): the map-beat chevron must sit
    # where the DRAWN line first leaves the panel, not at the clamped far point
    W, H = B2.PANEL_W, B2.PANEL_H
    line = [(800, 250), (600, 100), (400, -100), (300, -200), (500, 50), (700, 200)]
    ex = B2._first_exit(line)
    assert ex is not None
    assert abs(ex[1] - 0) < 1.5  # first outbound exit is the TOP edge
    assert 400 < ex[0] < 600  # on the line's approach, not the far point's x (300)
    assert B2._first_exit([(100, 100), (200, 200)]) is None  # never leaves: no exit
    src = Path(B2.__file__).read_text()
    assert "SEA FROZEN" not in src, "the frozen-sea tag must never come back"
    assert "SEA LIVE" in src
    assert all("FROZEN" not in v for v in B2.WHERE2.values())


def test_v2_narration_honesty():
    rep = B.load_report()
    deck = B.narration(rep)
    joined = " ".join(" ".join(v) for v in deck.values())
    assert "56 h" in B2.DRAFT and "50 h" in B2.DRAFT
    assert "29.5" in joined and "0.0" in joined
    assert "7.24" in joined and "6.0" in joined
    assert "7.26" not in joined and "21.58" not in joined
    assert "21.49" in joined
    assert "[draft" not in joined and "Equinor's own optimiser" not in joined


def test_v2_gates_contract_ok():
    B.gates()  # raises unless contract.validate passes on BOTH trajectories


def test_v2_camera_envelope_marker_pan():
    if not (LAND_WIDE.exists() and PLACES.exists()):
        pytest.skip("Bergen places not fetched yet (world-fetch/fetch_bergen_places.py)")
    import geopandas as gpd
    land = gpd.read_file(LAND_WIDE).geometry.union_all()
    lb = land.bounds
    fetch_log = json.loads((ROOT / "data/worlds/bergen/osm/fetch_bergen_places.json").read_text())
    assert fetch_log["steps"]["west_sea"]["coastline_ways_west_of_4.30"] == 0
    _, _, _, _, _, w11r, w11t, bbox = _ctx()
    g = B.Glide(bbox)
    centres, views = [], []
    for f in range(B.N):
        _, focus, _, _ = B.focus_of(f, w11r, w11t)
        cx, cy, span = g.view((f + 1) / B.N, focus, f)
        centres.append((cx, cy))
        views.append((cx - (B.PANEL_W / 2) * span / g.k, cy - (B.PANEL_H / 2) * span,
                      cx + (B.PANEL_W / 2) * span / g.k, cy + (B.PANEL_H / 2) * span))
    for vx0, vy0, vx1, vy1 in views:
        assert vy0 >= lb[1] - 1e-9 and vy1 <= lb[3] + 1e-9, \
            f"view lat {vy0:.3f}-{vy1:.3f} outside land {lb[1]:.3f}-{lb[3]:.3f}"
        assert vx1 <= lb[2] + 1e-9, f"view east {vx1:.3f} past land east {lb[2]:.3f}"
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
    g2 = B.Glide(bbox)
    centres2 = []
    for f in range(B.N):
        _, focus, _, _ = B.focus_of(f, w11r, w11t)
        cx, cy, span = g2.view((f + 1) / B.N, focus, f)
        if f >= 510:
            centres2.append((cx, cy))
    for c1, c2 in zip(centres[510:], centres2):
        assert abs(c1[0] - c2[0]) < 1e-9 and abs(c1[1] - c2[1]) < 1e-9


def test_v2_renders_section_frame_sea_moves():
    """End-to-end pixel proof: two consecutive section frames differ in the sea region
    (the living sea), while the frame is the right size and non-blank."""
    _, stops, heli, _, _, w11r, w11t, bbox = _ctx()
    strip = B.Strip(B.Glide(bbox), stops, heli)
    deck = B.narration(B._CTX[0])
    g = B.Glide(bbox)
    imgs = {}
    for f in (600, 601):
        gg = B.Glide(bbox)
        for ff in range(f):
            _, foc, _, _ = B.focus_of(ff, w11r, w11t)
            gg.view((ff + 1) / B.N, foc, ff)
        imgs[f] = B2.render_frame_v2(f, strip, gg, deck)
    for f, img in imgs.items():
        assert img.size == (B.W, B.H)
        assert np.asarray(img.convert("L")).std() > 10, f"frame {f} is blank"
    a = np.asarray(imgs[600].convert("RGB"), dtype=float)
    b = np.asarray(imgs[601].convert("RGB"), dtype=float)
    # section sea region: y 236..579, x 56..700 (left of the deck)
    sea = np.abs(a[250:550, 60:600] - b[250:550, 60:600]).mean()
    assert sea > 0.3, f"sea must move between consecutive frames (mean abs diff {sea:.3f})"
    # the helicopter must be visibly present: the deck region is not uniform
    deck_reg = np.asarray(imgs[600].convert("L"))[300:550, 650:1050]
    assert deck_reg.std() > 15, "deck/heli region reads as blank"
    # findings frame (f=750): the rebook map must render -- the real H2 trajectory,
    # not the straight chord -- and the map band must not be uniform
    gg = B.Glide(bbox)
    for ff in range(750):
        _, foc, _, _ = B.focus_of(ff, w11r, w11t)
        gg.view((ff + 1) / B.N, foc, ff)
    find_img = B2.render_frame_v2(750, strip, gg, deck)
    assert find_img.size == (B.W, B.H)
    map_band = np.asarray(find_img.convert("L"))[850:1150, 56:1024]
    assert map_band.std() > 10, "findings map band reads as blank"
