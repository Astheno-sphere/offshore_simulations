"""Visual quality levers: skia Canvas, bundled Inter font, sun()/ground_tint(), terrain hillshade (audit 5 fix 8)."""
from pathlib import Path

import numpy as np
import pytest

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
