"""Visual quality levers: skia Canvas, bundled Inter font, sun()/ground_tint(), terrain hillshade (audit 5 fix 8)."""
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

pytest.importorskip("skia")
from offsim.cinema import look
from offsim.cinema.draw import Canvas, draw_prims
from offsim.cinema.vessel_lineart import psv_profile
from offsim.worlds.terrain_tint import for_bbox, hillshade_rgba

BG = (51, 28, 34)


def test_canvas_line_polygon_text():
    cv = Canvas(300, 200, bg="#331c22", ss=2)
    cv.polygon([(20, 20), (120, 30), (90, 100)], fill="#4a2b2d", stroke="#f2e9df", width=2.4)
    cv.line([(10, 150), (290, 190)], "#e5a028", 1.0, dash=(6, 4))
    cv.circle(220, 60, 20, fill="#c8442f", alpha=0.5)
    cv.text(140, 120, "SECTION", font=("Inter", "Bold"), size=24, color="#f2e9df", tracking=1.5)
    im = cv.to_pil()
    assert im.size == (300, 200) and im.mode == "RGB"
    a = np.asarray(im).astype(int)
    assert (np.abs(a - np.array(BG)).sum(-1) > 30).sum() > 1500
    assert cv.measure("SECTION", ("Inter", "Bold"), 24, 1.5) > cv.measure("SECTION", ("Inter", "Bold"), 24)
    assert (np.abs(a[100:125, 140:260] - np.array(BG)).sum(-1) > 60).sum() > 100     # text pixels exist


def test_antialiasing_intermediate_values():
    cv = Canvas(100, 100, bg="#000000", ss=1)
    cv.line([(5, 5), (95, 60)], "#ffffff", 1.5)
    g = np.asarray(cv.to_pil())[..., 0]
    mid = ((g > 20) & (g < 235)).sum()
    assert mid > 40, f"expected intermediate grey values on a diagonal, got {mid}"
    cv2 = Canvas(100, 100, bg=None, ss=2)
    cv2.line([(5, 5), (95, 60)], "#ffffff", 1.5)
    im = cv2.to_pil()
    assert im.mode == "RGBA"
    al = np.asarray(im)[..., 3]
    assert ((al > 10) & (al < 245)).sum() > 40


def test_dash_leaves_gaps():
    cv = Canvas(120, 20, bg="#000000")
    cv.line([(0, 10), (120, 10)], "#ffffff", 2, dash=(8, 8))
    row = np.asarray(cv.to_pil())[10, :, 0]
    assert (row < 20).sum() > 20 and (row > 200).sum() > 20


def test_draw_prims_psv_profile():
    prims, solids, _ = psv_profile(0.0, 0.0)
    s = 3.0
    cv = Canvas(400, 150, bg="#331c22", ss=2)
    draw_prims(cv, prims, lambda x, z: (20 + s * x, 110 - s * z))
    a = np.asarray(cv.to_pil()).astype(int)
    assert (np.abs(a - np.array(BG)).sum(-1) > 40).sum() > 4000


def test_fonts_and_licence():
    d = Path(look.FONTS["Regular"]).parent
    assert (d / "OFL.txt").exists() and "Open Font License" in (d / "OFL.txt").read_text()
    for w in ("Regular", "Medium", "SemiBold", "Bold"):
        p = Path(look.font_path(w))
        assert p.exists() and p.stat().st_size > 100_000, w
    with pytest.raises(KeyError):
        look.font_path("Black")


def test_sun_solstice_and_winter():
    s = look.sun(12.0, lat=60.0, doy=172)
    assert s["elevation_deg"] == pytest.approx(53.4, abs=0.3)
    assert abs(s["solar_azimuth_deg"] - 180) < 1.0
    assert s["azimuth_deg"] == 220.0
    assert look.sun(0.0, lat=60.0, doy=355)["elevation_deg"] < 0
    assert look.sun(12.0, lat=60.0, doy=355)["elevation_deg"] == pytest.approx(6.6, abs=0.5)
    assert look.sun(0.0, doy=355)["ambient"] < look.sun(12.0)["ambient"]
    assert look.sun(12.0)["key_color"] != look.sun(0.0, doy=355)["key_color"]
    # morning is east of south, afternoon west
    assert look.sun(9.0)["solar_azimuth_deg"] < 180 < look.sun(15.0)["solar_azimuth_deg"]


def test_ground_tint_night_and_low_sun():
    P = look.PALETTES["section-plan"]
    lum = lambda h: sum(int(h[i:i + 2], 16) for i in (1, 3, 5))
    day, night, low = look.ground_tint(P, 45), look.ground_tint(P, -10), look.ground_tint(P, 4)
    assert day == P["ground"]
    assert lum(night) < lum(day)
    r = lambda h: int(h[1:3], 16)
    b = lambda h: int(h[5:7], 16)
    assert r(low) > r(day) and b(low) / r(low) < b(day) / r(day)       # warmer at low sun


def _cone(n=81, h=100.0):
    y, x = np.mgrid[0:n, 0:n]
    r = np.hypot(x - n // 2, y - n // 2)
    return np.clip(h - 2.0 * r, 0, None)


def test_hillshade_cone_nw_brighter_than_se():
    dem = _cone()
    rgba = hillshade_rgba(dem, 10.0, look.PALETTES["section-plan"], azimuth=315, altitude=45)
    assert rgba.shape == (81, 81, 4) and rgba.dtype == np.uint8
    nw, se = rgba[20:30, 20:30, :3].astype(float).mean(), rgba[52:62, 52:62, :3].astype(float).mean()
    assert nw > se + 10
    assert rgba[20:30, 20:30, 3].mean() > rgba[0:5, 0:5, 3].mean()         # slope raises alpha over flat ground
    dem[0, 0] = np.nan
    assert hillshade_rgba(dem, 10.0, look.PALETTES["section-plan"])[0, 0, 3] == 0


def test_for_bbox_without_dem_is_honest(tmp_path):
    rgba, why = for_bbox(tmp_path, (10.0, 59.0, 10.5, 59.5), (64, 64))
    assert rgba is None and "no DEM" in why


def test_for_bbox_reads_world_dem(tmp_path):
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin
    d = tmp_path / "depth" / "t1"
    d.mkdir(parents=True)
    dem = _cone(60, 300.0).astype("float32")
    sea = np.zeros_like(dem)
    tf = from_origin(10.0, 60.0, 0.001, 0.001)
    with rasterio.open(d / "dem.tif", "w", driver="GTiff", height=60, width=60, count=3, dtype="float32",
                       crs="EPSG:4326", transform=tf) as ds:
        ds.write(dem, 1), ds.write(sea, 2), ds.write(sea, 3)
    rgba, why = for_bbox(tmp_path, (10.005, 59.945, 10.055, 59.995), (50, 50))
    assert rgba is not None and rgba.shape == (50, 50, 4) and why.startswith("ok")
    rgba2, why2 = for_bbox(tmp_path, (20.0, 40.0, 20.1, 40.1), (10, 10))
    assert rgba2 is None and "outside" in why2


# ---------------------------------------------------------------------------------- skia renderers
def _section_shot():
    from offsim.motion import section as S
    return {"type": "section", "seconds": 0.1, "vessel": "psv",
            "hs": {"value": 2.0, "assumption": True}, "tp": {"value": 6.5, "assumption": True},
            "u10": {"value": 15.0, "assumption": True}, "t_exh": {"value": 520.0, "assumption": True},
            "kicker": "OUTER OSLOFJORD GALE  ·  SIMULATED",
            "headline": {"top": "WHERE DOES THE", "accent": "EXHAUST", "rest": "GO IN A GALE?"},
            "map": None, "narration": S.PSV_GALE_NARRATION}


def test_section_frame_renders_via_skia(tmp_path):
    """The section renderer runs on the skia Canvas: canonical size, heat + streaks + vessel in the panel,
    header text present. No map panel here (that needs gated run data); the map path is covered below."""
    from offsim.motion import section as S
    sc = S.Scene(2.0, 6.5, 15.0)
    st = S.Streaks(sc)
    series = []
    for _ in range(2):
        sc.step(0.015)
        st.advance(0.015)
        series.append((sc.t, sc.deck_air_excess(), sc.plume_height()))
    out = tmp_path / "f0000.png"
    S.render(sc, st, series, 0, 2, out, ("deck line one", "deck line two"), None, None, _section_shot())
    im = Image.open(out)
    assert im.size == (1080, 1350) and im.mode == "RGB"
    a = np.asarray(im).astype(int)
    panel = a[236:573, :, :]                                  # the section panel: heat, streaks, sea, vessel
    assert (np.abs(panel - np.array(BG)).sum(-1) > 30).sum() > 5000
    assert (a[40:200, 56:600, 0] > 150).sum() > 100            # kicker + headline accent pixels exist
    assert (np.abs(a[573:900, :, :] - np.array(BG)).sum(-1) > 30).sum() > 500  # readouts + chart drawn


def test_canvas_lines_batches_polylines():
    """Canvas.lines draws many polylines as one path — no connecting segment between them."""
    from offsim.cinema.draw import Canvas
    cv = Canvas(40, 20, bg="#000000", ss=1)
    cv.lines([[(5, 10), (15, 10)], [(25, 10), (35, 10)]], "#ffffff", 2.0)
    a = np.asarray(cv.to_pil()).astype(int)
    assert a[10, 10].sum() > 600 and a[10, 30].sum() > 600   # both segments drawn
    assert a[10, 20].sum() < 100                              # no bridge between them


def test_hillshade_smoothing_and_alpha_cap():
    """v9 terrain fix: Gaussian smoothing tames the noisy 50 m grid (lower alpha scatter) and the
    alpha_range cap is honoured — relief as texture, not speckle."""
    from offsim.worlds.terrain_tint import hillshade_rgba
    rng = np.random.default_rng(0)
    dem = _cone(81, 300.0) + rng.normal(0, 25.0, (81, 81))
    pal = look.PALETTES["section-plan"]
    raw = hillshade_rgba(dem, 10.0, pal)
    sm = hillshade_rgba(dem, 10.0, pal, smooth_sigma=2.0, alpha_range=(0.05, 0.45))
    assert sm[..., 3].std() < raw[..., 3].std()
    assert sm[..., 3].max() <= int(0.45 * 255) + 1


def test_map_panel_smooth_camera_keeps_vessel_in_frame():
    """v9 dead-zone glide camera, driven over the real demo trajectory at the film's own frame times
    (route_at, 720 frames, span 4.0, cap 1.8): the marker stays in frame, and the peak pan rate stays
    under the 1.8 panel-widths-per-film cap (0.074 widths/s at 24 s, 36% under v6's follow-cam 0.116)
    — one slow motion, not a camera glued to a fast vessel. The span + cap were measured: at span 3.2 /
    cap 1.2 the marker leaves the frame on the 193-frame southward run, because the camera cap cannot
    keep up with a 2.8 px/frame marker; span 4.0 / cap 1.8 holds it with margin."""
    import pandas as pd
    from shapely.geometry import Polygon
    from offsim.motion.mappanel import MapPanel
    from offsim.motion.section import route_at
    tr = pd.read_csv("out/demo-oslofjord-supply/trajectory.csv")
    makespan_s = float(max(tr[tr.agent_id == a].t.max() for a in tr.agent_id.unique()))
    g = tr[tr.agent_id == "PSV-1"].sort_values("t")
    route, times = list(zip(g.lon, g.lat)), g.t.to_numpy()
    land = Polygon([(10.44, 59.11), (10.72, 59.11), (10.72, 59.47), (10.44, 59.47)])
    mp = MapPanel(land, (10.44, 59.11, 10.72, 59.47), size=(968, 300), seconds=0.0, span_mult=4.0,
                  camera="smooth", wind_streaks=False, pan_cap=1.8)
    W, H = 968, 300
    worst = 0.0
    for f in range(720):
        u = (f + 1) / 720
        _, mk = route_at(route, times, u * makespan_s)
        cx, cy, dpp = mp._view(u, mk)
        mx = (mk[0] - cx) * mp.k / dpp + W / 2
        my = H / 2 - (mk[1] - cy) / dpp
        assert 0 <= mx < W and 0 <= my < H, f"marker out of frame at f{f}"
        worst = max(worst, abs(mx - W / 2) / W, abs(my - H / 2) / H)
    assert worst < 0.5, f"marker reaches {worst:.2f} of the half-frame (edge is 0.50)"
    assert mp._pan_max <= 1.8, f"peak pan {mp._pan_max:.2f} widths/film exceeds the 1.8 cap"
    assert mp._pan_max / 24.0 < 0.08, "peak pan must be under 0.08 widths/s at 24 s"
    assert mp._cam != (route[0][0], route[0][1]), "the camera must move over the run"


def test_map_panel_view_inside_land_coverage():
    """v10 blue-cuts guard: every frame's view must sit inside the land coverage, on the clean
    720-frame path AND on the f239-resumed path that produced the v9 frames on disk (the v9
    f0719 left strip was a resumed opening outside the old box). The v9 land (lon 10.00-11.10)
    fails this test — the clean view overhangs its right edge by 0.082 deg (72 px); the v10
    fetch (lon 9.85-11.30) passes with ~0.1 deg margin. The clamp must also never bind on the
    demo run: the clamped and unclamped views are identical, so the guard is a safety net, not
    a second camera. Skips when the fetched land or the demo trajectory is absent (data/ and
    out/ are gitignored; the fetch script verifies coverage separately)."""
    import math

    import geopandas as gpd
    import pandas as pd
    from offsim.motion.mappanel import MapPanel
    from offsim.motion.section import route_at
    land_p = Path("data/worlds/oslofjord/osm/land_wide.geojson")
    tr_p = Path("out/demo-oslofjord-supply/trajectory.csv")
    if not land_p.exists() or not tr_p.exists():
        pytest.skip("v10 land / demo trajectory not fetched on this machine")
    land = gpd.read_file(land_p).geometry.union_all()
    lb = land.bounds
    tr = pd.read_csv(tr_p)
    makespan_s = float(max(tr[tr.agent_id == a].t.max() for a in tr.agent_id.unique()))
    g = tr[tr.agent_id == "PSV-1"].sort_values("t")
    route, times = list(zip(g.lon, g.lat)), g.t.to_numpy()
    W, H = 968, 300
    k = math.cos(math.radians((59.11 + 59.47) / 2))

    def _views(start, use_land):
        mp = MapPanel(use_land, (10.44, 59.11, 10.72, 59.47), size=(W, H), seconds=0.0,
                      span_mult=4.0, camera="smooth", wind_streaks=False, pan_cap=1.8)
        out = []
        for f in range(start, 720):
            u = (f + 1) / 720
            _, mk = route_at(route, times, u * makespan_s)
            cx, cy, dpp = mp._view(u, mk)
            out.append((f, cx, cy, dpp, mk))
        return out

    for start in (0, 239):
        clamped = _views(start, land)
        unclamped = _views(start, None)
        for (f, cx, cy, dpp, mk), (_, ux, uy, _, _) in zip(clamped, unclamped):
            assert (cx, cy) == (ux, uy), f"clamp binds at f{f} on the {start}-path (fetch too narrow)"
            vx0, vx1 = cx - (W / 2) * dpp / k, cx + (W / 2) * dpp / k
            vy0, vy1 = cy - (H / 2) * dpp, cy + (H / 2) * dpp
            assert vx0 >= lb[0] - 1e-9 and vx1 <= lb[2] + 1e-9, \
                f"view leaves the land lon range at f{f}: {vx0:.4f}..{vx1:.4f} vs {lb[0]:.4f}..{lb[2]:.4f}"
            assert vy0 >= lb[1] - 1e-9 and vy1 <= lb[3] + 1e-9, \
                f"view leaves the land lat range at f{f}: {vy0:.4f}..{vy1:.4f} vs {lb[1]:.4f}..{lb[3]:.4f}"
            mx = (mk[0] - cx) * k / dpp + W / 2
            my = H / 2 - (mk[1] - cy) / dpp
            assert 0 <= mx < W and 0 <= my < H, f"marker out of frame at f{f} on the {start}-path"


def test_map_panel_place_labels_do_not_overlap():
    """v9 named map: the deterministic placer puts every non-crowded label in a non-overlapping chip
    inside the panel, and reports (not hides) any label it could not place."""
    from shapely.geometry import Polygon
    from offsim.motion.mappanel import MapPanel
    land = Polygon([(10.0, 59.0), (10.5, 59.0), (10.5, 59.5), (10.0, 59.5)])
    places = [
        {"text": "MOSS · FERRY", "lat": 59.24, "lon": 10.40, "kind": "place"},
        {"text": "HORTEN · FERRY", "lat": 59.22, "lon": 10.05, "kind": "place"},
        {"text": "OSLOFJORDEN", "lat": 59.15, "lon": 10.22, "kind": "fjord", "color": "#7ba3ad"},
        {"text": "S1", "lat": 59.18, "lon": 10.30, "kind": "site", "size": 11},
        {"text": "S2", "lat": 59.25, "lon": 10.15, "kind": "site", "size": 11},
    ]
    mp = MapPanel(land, (10.0, 59.0, 10.5, 59.5), size=(968, 300), places=places)
    route = [(10.1 + 0.01 * i, 59.1 + 0.005 * i) for i in range(20)]
    img = mp.frame(0.5, route, 10, route[9], wind=(8.0, 0.0))
    assert img.size == (968, 300)
    assert mp._fell_back == [], f"labels fell back: {mp._fell_back}"
    boxes = list(mp._placed.values())
    for i, b in enumerate(boxes):
        assert 8 <= b[0] and b[2] <= 968 - 8 and 8 <= b[1] and b[3] <= 300 - 8, f"box {b} out of panel"
        for c in boxes[i + 1:]:
            assert b[2] + 4 < c[0] or c[2] + 4 < b[0] or b[3] + 4 < c[1] or c[3] + 4 < b[1], \
                f"labels overlap: {b} vs {c}"


def test_map_panel_hillshade_clipped_to_view(tmp_path):
    """v9: the hillshade is a geographic layer for the world bbox, drawn only where it overlaps the
    current view — a follow-cam view that runs past the DEM must render (not crash, not stretch the
    texture over the whole panel)."""
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin
    from shapely.geometry import Polygon
    from offsim.motion.mappanel import MapPanel
    d = tmp_path / "depth" / "t1"
    d.mkdir(parents=True)
    dem = _cone(60, 300.0).astype("float32")
    sea = np.zeros_like(dem)
    tf = from_origin(10.0, 60.0, 0.001, 0.001)
    with rasterio.open(d / "dem.tif", "w", driver="GTiff", height=60, width=60, count=3, dtype="float32",
                       crs="EPSG:4326", transform=tf) as ds:
        ds.write(dem, 1), ds.write(sea, 2), ds.write(sea, 3)
    land = Polygon([(10.0, 59.94), (10.06, 59.94), (10.06, 60.0), (10.0, 60.0)])
    bbox = (10.005, 59.945, 10.055, 59.995)
    route = [(10.01 + 0.002 * i, 59.95 + 0.001 * i) for i in range(10)]
    mp = MapPanel(land, bbox, size=(50, 50), world_dir=tmp_path)
    assert mp._hill is not None
    # follow-cam locked on the route's north end, view running past the DEM: must render, hillshade clipped
    img = mp.frame(0.0, route, 9, route[-1], follow=True)
    assert img.size == (50, 50) and img.mode == "RGB"
    flat = MapPanel(land, bbox, size=(50, 50), world_dir=tmp_path / "no-dem")
    assert not np.array_equal(np.asarray(img), np.asarray(flat.frame(0.0, route, 9, route[-1], follow=True)))


def test_map_panel_renders_via_skia():
    """MapPanel.frame() on the skia Canvas: canonical size, land fill + route + marker + scale bar present."""
    from shapely.geometry import Polygon
    from offsim.motion.mappanel import MapPanel
    land = Polygon([(10.0, 59.0), (10.5, 59.0), (10.5, 59.5), (10.0, 59.5)])
    mp = MapPanel(land, (10.0, 59.0, 10.5, 59.5), size=(480, 150))
    route = [(10.1 + 0.01 * i, 59.1 + 0.005 * i) for i in range(20)]
    img = mp.frame(0.5, route, 10, route[9], wind=(8.0, 0.0))
    assert img.size == (480, 150) and img.mode == "RGB"
    a = np.asarray(img).astype(int)
    deep = np.array([42, 22, 26])                             # ground_deep
    assert (np.abs(a - deep).sum(-1) > 30).sum() > 1000        # land + route + streaks + furniture
    img2 = mp.frame(0.9, route, 18, route[17], wind=(8.0, 0.0))
    assert not np.array_equal(np.asarray(img), np.asarray(img2))   # camera + route advance


def test_map_panel_hillshade_under_map(tmp_path):
    """With a world DEM the hillshade loads once (hill_why 'ok: ...') and the frame still renders; without
    one the panel stays flat and says why."""
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin
    from shapely.geometry import Polygon
    from offsim.motion.mappanel import MapPanel
    d = tmp_path / "depth" / "t1"
    d.mkdir(parents=True)
    dem = _cone(60, 300.0).astype("float32")
    sea = np.zeros_like(dem)
    tf = from_origin(10.0, 60.0, 0.001, 0.001)
    with rasterio.open(d / "dem.tif", "w", driver="GTiff", height=60, width=60, count=3, dtype="float32",
                       crs="EPSG:4326", transform=tf) as ds:
        ds.write(dem, 1), ds.write(sea, 2), ds.write(sea, 3)
    land = Polygon([(10.0, 59.94), (10.06, 59.94), (10.06, 60.0), (10.0, 60.0)])
    bbox = (10.005, 59.945, 10.055, 59.995)
    route = [(10.01 + 0.002 * i, 59.95 + 0.001 * i) for i in range(10)]
    mp = MapPanel(land, bbox, size=(50, 50), world_dir=tmp_path)
    assert mp.hill_why.startswith("ok:") and mp._hill is not None
    img = mp.frame(0.0, route, 1, route[0])
    assert img.size == (50, 50) and img.mode == "RGB"
    flat = MapPanel(land, bbox, size=(50, 50), world_dir=tmp_path / "no-dem")
    assert flat._hill is None and "no DEM" in flat.hill_why
    assert flat.frame(0.0, route, 1, route[0]).size == (50, 50)
