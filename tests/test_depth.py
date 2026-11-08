"""Depth chain on a SYNTHETIC fjord (no network): merge priority + mask, mesh budget + exaggeration, texture limit,
isobaths, build_world_depth outputs. Real Kartverket/EMODnet data only ever arrives via the fetch-world workflow."""
import json

import numpy as np
import pytest

rasterio = pytest.importorskip("rasterio")
pytest.importorskip("pydelatin")
pytest.importorskip("skimage")

from pyproj import Transformer  # noqa: E402
from rasterio.transform import from_origin  # noqa: E402
from shapely.geometry import box, mapping  # noqa: E402
from shapely.ops import transform as sh_transform  # noqa: E402

from offsim.worlds import depth  # noqa: E402

CRS = "EPSG:25832"
X0, Y1, RES = 580_000.0, 6_600_000.0, 100.0        # NW corner (near Oslo), 100 m cells
W, H = 240, 320
XM = X0 + W * RES / 2                              # fjord axis
HALF = 4_000.0                                     # fjord half width (m)
TO_LL = Transformer.from_crs(CRS, 4326, always_xy=True).transform


def _xy():
    xs = X0 + (np.arange(W) + 0.5) * RES
    ys = Y1 - (np.arange(H) + 0.5) * RES
    return np.meshgrid(xs, ys)


def _write(path, arr, transform, nodata=-9999.0, crs=CRS):
    arr = np.where(np.isfinite(arr), arr, nodata).astype("float32")
    with rasterio.open(path, "w", driver="GTiff", height=arr.shape[0], width=arr.shape[1], count=1, dtype="float32",
                       crs=crs, transform=transform, nodata=nodata) as dst:
        dst.write(arr, 1)


@pytest.fixture(scope="module")
def fjord(tmp_path_factory):
    d = tmp_path_factory.mktemp("fjord")
    X, Y = _xy()
    tf = from_origin(X0, Y1, RES, RES)
    dx = X - XM
    # sea: shallow shelf + gaussian trench along the axis, deepest to the south
    trench = 20 + 330 * np.exp(-(dx / 1200.0) ** 2 / 2) * (0.4 + 0.6 * (Y1 - Y) / (H * RES))
    sea_lat = -(trench)                                            # EMODnet-like, LAT
    land = 15 + 0.03 * (np.abs(dx) - HALF) + 120 * np.sin((Y - 6.55e6) / 3000.0) ** 2   # hills, NN2000
    land = np.where(np.abs(dx) >= HALF, land, np.nan)               # DTM has no value at sea
    # high-resolution survey on a sub-box, 10 m "deeper" than the broad model so the winner is identifiable
    ngu_box = (slice(100, 220), slice(60, 180))                    # rows, cols
    ngu = np.full((H, W), np.nan)
    ngu[ngu_box] = sea_lat[ngu_box] - 10.0
    # ngu written on its own sub-grid (different extent, same cell size)
    r0, r1, c0, c1 = 100, 220, 60, 180
    p_ngu, p_emo, p_land = d / "ngu.tif", d / "emodnet.tif", d / "dtm.tif"
    _write(p_ngu, ngu[r0:r1, c0:c1], from_origin(X0 + c0 * RES, Y1 - r0 * RES, RES, RES))
    _write(p_emo, sea_lat, tf)
    _write(p_land, land, tf)
    land_poly = sh_transform(TO_LL, box(X0, Y1 - H * RES, XM - HALF, Y1).union(box(XM + HALF, Y1 - H * RES, X0 + W * RES, Y1)))
    geo = d / "land.geojson"
    geo.write_text(json.dumps({"type": "Feature", "properties": {}, "geometry": mapping(land_poly)}))
    srcs = [
        {"name": "NGU synthetic", "path": str(p_ngu), "priority": 0, "datum": "chart_datum", "licence": "synthetic", "credit": "SYNTHETIC"},
        {"name": "DTM synthetic", "path": str(p_land), "priority": 1, "datum": "NN2000", "licence": "synthetic", "credit": "SYNTHETIC"},
        {"name": "EMODnet synthetic", "path": str(p_emo), "priority": 3, "datum": "LAT", "licence": "synthetic", "credit": "SYNTHETIC"},
    ]
    w, s, e, n = sh_transform(TO_LL, box(X0 + 5 * RES, Y1 - (H - 5) * RES, X0 + (W - 5) * RES, Y1 - 5 * RES)).bounds
    bbox = (w, s, e, n)
    cog = d / "merged.tif"
    man = depth.merge_dem(srcs, bbox, CRS, str(cog), res=RES, land=str(geo))
    return {"dir": d, "srcs": srcs, "bbox": bbox, "cog": str(cog), "man": man, "geo": str(geo), "sea_lat": sea_lat}


def _sample(cog, band, lon, lat):
    with rasterio.open(cog) as ds:
        x, y = Transformer.from_crs(4326, ds.crs, always_xy=True).transform(lon, lat)
        r, c = ds.index(x, y)
        return float(ds.read(band)[r, c])


def _at(cog, band, x, y):
    lon, lat = TO_LL(x, y)
    return _sample(cog, band, lon, lat)


def test_merge_priority_datum_and_mask(fjord):
    cog = fjord["cog"]
    with rasterio.open(cog) as ds:
        assert ds.count == 3 and [ds.descriptions[i] for i in range(3)] == ["elevation", "bathy_mask", "source_id"]
    X, Y = _xy()
    # centre of the survey patch: highest priority (source 1) wins, datum shift of chart_datum applied (-0.3 m)
    cx, cy = X0 + 120 * RES, Y1 - 160 * RES
    r, c = int((Y1 - cy) / RES), int((cx - X0) / RES)
    exp = fjord["sea_lat"][r, c] - 10.0 - 0.3
    assert _at(cog, 3, cx, cy) == 1
    assert _at(cog, 1, cx, cy) == pytest.approx(exp, abs=1.0)    # bilinear regrid of a smooth field
    # outside the patch the broad model (source 3) wins, LAT -> NN2000 shift applied
    ox, oy = X0 + 40 * RES, Y1 - 40 * RES
    assert _at(cog, 3, XM, oy) == 3
    assert _at(cog, 1, XM, oy) == pytest.approx(fjord["sea_lat"][int((Y1 - oy) / RES), W // 2] - 0.3, abs=1.0)
    # land source owns the hills
    assert _at(cog, 3, X0 + 20 * RES, oy) == 2
    # feathering: a blended seam exists between survey and broad model (value between -10 m and 0 offset of source 1)
    col = W // 2                                       # survey patch spans rows 100-219: seam at its northern edge
    rows = range(92, 108)
    seam = [_at(cog, 1, X0 + (col + 0.5) * RES, Y1 - (r_ + 0.5) * RES) for r_ in rows]
    broad = np.array([fjord["sea_lat"][r_, col] for r_ in rows]) - 0.3
    diff = np.array(seam) - broad                      # ramps 0 -> -10 across the seam, never a 10 m step in one cell
    assert diff[0] > -2.0 and diff[-1] < -8.0
    assert np.abs(np.diff(diff)).max() < 5.0
    # mask burn: fjord axis = sea (<= 0 m), hills = land (>= 0 m)
    assert _at(cog, 2, XM, oy) == 1 and _at(cog, 1, XM, oy) <= 0
    assert _at(cog, 2, X0 + 20 * RES, oy) == 0 and _at(cog, 1, X0 + 20 * RES, oy) >= 0
    # manifest carries every licence and the datum assumption
    m = fjord["man"]
    assert {s["licence"] for s in m["sources"]} == {"synthetic"}
    lat = [s for s in m["sources"] if s["datum"] == "LAT"][0]
    assert lat["datum_offset_m"] == -0.3 and lat["assumption"] is True


def test_merge_rejects_source_without_licence(fjord, tmp_path):
    bad = [dict(fjord["srcs"][0])]
    bad[0].pop("licence")
    with pytest.raises(ValueError, match="licence"):
        depth.merge_dem(bad, fjord["bbox"], CRS, str(tmp_path / "x.tif"), res=RES)


def test_mesh_budget_and_exaggeration(fjord):
    cog = fjord["cog"]
    for tier in ("fjord", "port", "shelf"):
        m = depth.terrain_mesh(cog, tier)
        assert 0 < m["triangles"] <= depth.MAX_TRIANGLES
        assert m["indices"].dtype == np.uint32 and len(m["indices"]) == 3 * m["triangles"]
        assert m["indices"].max() < len(m["positions"]) and m["positions"].shape == m["normals"].shape
        assert np.allclose(np.linalg.norm(m["normals"], axis=1), 1.0, atol=1e-6)
        assert (m["normals"][:, 2] >= 0).mean() > 0.99                       # faces up (CCW from above)
    # per-domain exaggeration: sea z = elevation * sea_x, land z = elevation * land_x (vertices lie on the grid)
    tier = "fjord"
    _, land_x, sea_x, _ = depth.TIERS[tier]
    m = depth.terrain_mesh(cog, tier)
    with rasterio.open(cog) as ds:
        elev, sea = ds.read(1), ds.read(2) > 0.5
        from pyproj import Transformer as T
        to = T.from_crs(4326, ds.crs, always_xy=True).transform
        checked = {"sea": 0, "land": 0}
        for lon, lat, z in m["positions"][:: max(1, len(m["positions"]) // 400)]:
            x, y = to(lon, lat)
            r, c = ds.index(x, y)
            want = elev[r, c] * (sea_x if sea[r, c] else land_x)
            want = float(want)
            assert float(z) == pytest.approx(want, abs=1e-2 * max(1.0, abs(want)) + 0.5)
            checked["sea" if sea[r, c] else "land"] += 1
    assert checked["sea"] > 10 and checked["land"] > 10
    e0, e1 = elev[sea].min(), elev[~sea].max()
    assert m["bounds"][4] == pytest.approx(e0 * sea_x, rel=1e-3) and m["bounds"][5] == pytest.approx(e1 * land_x, rel=1e-3)
    assert depth.terrain_mesh(cog, "shelf")["exaggeration"] == {"land": 4.0, "sea": 30.0}


def test_mesh_triangle_cap(fjord, monkeypatch):
    monkeypatch.setattr(depth, "MAX_TRIANGLES", 5_000)
    m = depth.terrain_mesh(fjord["cog"], "fjord")
    assert m["triangles"] <= 5_000


def test_hillshade_texture_limit_and_palette(fjord, tmp_path, monkeypatch):
    from PIL import Image
    t = depth.hillshade_texture(fjord["cog"], "fjord", out_png=str(tmp_path / "hs.png"))
    img = Image.open(t["path"])
    with rasterio.open(fjord["cog"]) as ds:
        cw, ch = ds.width, ds.height
    assert img.size == (cw, ch) == (t["width"], t["height"]) and max(img.size) <= depth.TEXTURE_MAX_PX
    a = np.asarray(img.convert("RGB")).astype(float)
    with rasterio.open(fjord["cog"]) as ds:
        sea = ds.read(2) > 0.5
    # sea reads darker than land; deeper sea darker than shallow
    assert a[sea].mean() < a[~sea].mean()
    with rasterio.open(fjord["cog"]) as ds:
        z = ds.read(1)
    deep, shallow = sea & (z < -200), sea & (z > -40)
    assert deep.any() and shallow.any() and a[deep].mean() < a[shallow].mean()
    assert len(t["corners"]) == 4 and t["bounds"][0] < t["bounds"][2]
    assert depth.png_data_url(t["path"]).startswith("data:image/png;base64,")
    # oversize rasters are downscaled to the limit
    monkeypatch.setattr(depth, "TEXTURE_MAX_PX", 128)
    t2 = depth.hillshade_texture(fjord["cog"], "fjord", out_png=str(tmp_path / "hs2.png"))
    assert max(t2["width"], t2["height"]) <= 128 and t2["height"] > t2["width"]


def test_isobaths_levels_bold_and_drop_short(fjord, tmp_path):
    levels = [10, 20, 40, 60, 80, 100, 120, 140, 160, 180]
    fc = depth.isobaths(fjord["cog"], "fjord", levels=levels, out_geojson=str(tmp_path / "iso.geojson"))
    assert json.loads((tmp_path / "iso.geojson").read_text())["type"] == "FeatureCollection"
    got = {f["properties"]["depth"] for f in fc["features"]}
    assert got <= set(levels) and {10, 20, 100} <= got
    for f in fc["features"]:
        p = f["properties"]
        assert f["geometry"]["type"] == "LineString" and len(f["geometry"]["coordinates"]) >= 2
        assert p["length_m"] >= depth.MIN_ISOBATH_LEN_M
        assert p["bold"] == (levels.index(p["depth"]) + 1 in (5, 10))      # every 5th level
        assert p["label"] == f"{p['depth']:g} m"
    # defaults come from the tier
    dflt = {f["properties"]["depth"] for f in depth.isobaths(fjord["cog"], "fjord")["features"]}
    assert dflt <= set(depth.ISOBATHS_M["fjord"]) and {10, 20, 50} <= dflt
    # contour at depth d sits where the smoothed DEM is ~d (check a vertex)
    f = next(f for f in fc["features"] if f["properties"]["depth"] == 100)
    lon, lat = f["geometry"]["coordinates"][len(f["geometry"]["coordinates"]) // 2]
    assert -_sample(fjord["cog"], 1, lon, lat) == pytest.approx(100, abs=25)


def test_build_world_depth_writes_all_files(fjord, tmp_path):
    out = tmp_path / "depth" / "fjord"
    man = depth.build_world_depth("synthetic-fjord", "fjord", fjord["cog"], fjord["geo"], out_dir=out)
    for f in ("terrain.json", "hillshade.png", "isobaths.geojson", "depth_manifest.json"):
        assert (out / f).stat().st_size > 0, f
    t = json.loads((out / "terrain.json").read_text())
    n = len(t["positions"]) // 3
    assert t["triangles"] * 3 == len(t["indices"]) and len(t["normals"]) == 3 * n and len(t["texcoords"]) == 2 * n
    assert t["texture"]["file"] == "hillshade.png" and len(t["texture"]["corners"]) == 4 and len(t["bounds"]) == 6
    assert set(t["exaggeration"]) == {"land", "sea"} and t["version"] == 1
    saved = json.loads((out / "depth_manifest.json").read_text())
    assert saved["triangles"] == man["triangles"] <= depth.MAX_TRIANGLES
    assert saved["notice"].startswith("illustrative bathymetry") and saved["credits"] == ["SYNTHETIC"]
    assert len(saved["dem"]["sources"]) == 3


def test_build_world_depth_merges_from_source_list(fjord, tmp_path):
    out = tmp_path / "d2"
    man = depth.build_world_depth("synthetic-fjord", "fjord", fjord["srcs"], fjord["geo"], out_dir=out,
                                  bbox=fjord["bbox"], crs=CRS)
    assert (out / "dem.tif").exists() and (out / "terrain.json").exists()
    assert man["dem"]["land_polygon"] is True


def test_unknown_tier_and_datum():
    with pytest.raises(ValueError):
        depth.terrain_mesh("nope.tif", "ocean")
    with pytest.raises(ValueError):
        depth.datum_offset("EGM96")


def test_hillshade_light_direction():
    """Key light from the NW: a slope facing west or north is lit, one facing east or south is dark."""
    x = np.tile(np.arange(50.0), (50, 1)) * 10.0                    # z rises to the east -> faces west
    ones = np.ones(50)
    face_w = depth._hillshade(x, 10 * ones, 10.0, 315, 35).mean()
    face_e = depth._hillshade(-x, 10 * ones, 10.0, 315, 35).mean()
    y = np.tile(np.arange(50.0)[:, None], (1, 50)) * 10.0           # rows go south: z rises to the south -> faces north
    face_n = depth._hillshade(y, 10 * ones, 10.0, 315, 35).mean()
    face_s = depth._hillshade(-y, 10 * ones, 10.0, 315, 35).mean()
    assert face_w > face_e and face_n > face_s
    assert depth._hillshade(np.zeros((9, 9)), np.ones(9), 1.0, 315, 35).mean() == pytest.approx(np.sin(np.radians(35)))


# ---- fetchers: logic only, network mocked (live endpoints are unverified from this sandbox) ----------------------
def test_emodnet_coverage_choice_and_getcoverage(monkeypatch, tmp_path):
    from offsim.worlds import fetch_world as fw
    caps = ("<wcs:Capabilities xmlns:wcs='x'><wcs:Contents>"
            "<wcs:CoverageSummary><wcs:CoverageId>emodnet__mean_2020</wcs:CoverageId></wcs:CoverageSummary>"
            "<wcs:CoverageSummary><wcs:CoverageId>emodnet__mean_2022</wcs:CoverageId></wcs:CoverageSummary>"
            "<wcs:CoverageSummary><wcs:CoverageId>emodnet__source_quality_rank</wcs:CoverageId></wcs:CoverageSummary>"
            "</wcs:Contents></wcs:Capabilities>")
    desc = '<wcs:CoverageDescriptions><gml:Envelope axisLabels="Lat Long" srsDimension="2"/></wcs:CoverageDescriptions>'
    calls = []

    def fake_get(url, data=None, timeout=300):
        calls.append(url)
        if "GetCapabilities" in url:
            return caps.encode()
        if "DescribeCoverage" in url:
            return desc.encode()
        return b"II*\x00" + b"\x00" * 16

    monkeypatch.setattr(fw, "get", fake_get)
    assert fw.emodnet_pick_coverage(fw.emodnet_coverage_ids()) == "emodnet__mean_2022"
    r = fw.emodnet_bathymetry((1.5, 57.8, 6.2, 60.2), tmp_path)
    q = calls[-1]
    assert "coverageId=emodnet__mean_2022" in q and "Lat%2857.8%2C60.2%29" in q and "Long%281.5%2C6.2%29" in q
    assert (tmp_path / "dem_raw/emodnet.tif").exists() and r["datum"] == "LAT" and r["priority"] == 3
    with pytest.raises(NotImplementedError, match="endpoint unverified"):
        fw.emodnet_pick_coverage(["emodnet__other"])
    monkeypatch.setattr(fw, "get", lambda url, data=None, timeout=300: b"<ExceptionReport/>" if "GetCoverage" in url else fake_get(url))
    with pytest.raises(RuntimeError, match="did not return a TIFF"):
        fw.emodnet_bathymetry((1, 2, 3, 4), tmp_path)


def test_geonorge_order_polls_and_kartverket_unverified_paths(monkeypatch, tmp_path):
    import io
    import zipfile
    from offsim.worlds import fetch_world as fw
    monkeypatch.setattr(fw.time, "sleep", lambda s: None)
    seq = iter([
        {"referenceNumber": "r1", "files": [{"status": "WaitingForProcessing", "downloadUrl": None}]},
        {"referenceNumber": "r1", "files": [{"status": "ReadyForDownload", "downloadUrl": "https://dl/x", "fileId": "f"}]},
    ])
    posted = {}

    def fake_json(path, payload=None, method=None, timeout=120):
        if path.startswith("/capabilities"):
            return {"supportsPolygonSelection": True}
        if path.startswith("/codelists/format"):
            return [{"name": "DEM"}, {"name": "GeoTIFF"}]
        if path == "/order":
            posted.update(payload)
        return next(seq)

    z = io.BytesIO()
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("tile.tif", b"II*\x00" + b"\x00" * 8)
    monkeypatch.setattr(fw, "_geonorge_json", fake_json)
    monkeypatch.setattr(fw, "get", lambda url, data=None, timeout=300: z.getvalue())
    r = fw.kartverket_dtm((10.2, 58.95, 11.05, 59.95), tmp_path, {"metadata_uuid": "u", "projection_code": "25832"},
                          wait_s=60, poll_s=0)
    line = posted["orderLines"][0]
    assert line["formats"] == [{"name": "GeoTIFF"}] and line["coordinatesystem"] == "25832" and line["metadataUuid"] == "u"
    assert len(line["coordinates"].split()) == 10                       # closed 5-point ring, x y pairs
    assert r["files"] == ["kartverket_dtm_0.tif"] and (tmp_path / "dem_raw/kartverket_dtm_0.tif").exists()
    with pytest.raises(NotImplementedError, match="endpoint unverified"):
        fw.kartverket_dtm((1, 2, 3, 4), tmp_path, {})
    with pytest.raises(NotImplementedError, match="endpoint unverified"):
        fw.kartverket_seabed((1, 2, 3, 4), tmp_path)
    monkeypatch.setattr(fw, "_geonorge_json", lambda *a, **k: {"referenceNumber": "r", "files": [{"status": "Failed"}]})
    with pytest.raises(RuntimeError, match="failed"):
        fw.geonorge_order_files("u", {})
