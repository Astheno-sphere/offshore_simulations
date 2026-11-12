"""offsim.worlds.osm post-processing on synthetic GeoDataFrames (no pbf, no network)."""
import json

import numpy as np
import pytest

gpd = pytest.importorskip("geopandas")
pytest.importorskip("pyrosm")
from shapely.geometry import LineString, Point, box  # noqa: E402

from offsim.worlds import osm  # noqa: E402

BBOX = (10.0, 59.0, 11.0, 60.0)


def _buildings():
    return gpd.GeoDataFrame({
        "height": ["12", "40 ft", None, "garbage", None, "3,5 m"],
        "building:levels": [None, None, "4", "2", None, "9"],
        "geometry": [box(10.1 + i * 0.01, 59.5, 10.105 + i * 0.01, 59.505) for i in range(6)]}, crs=4326)


def test_parse_height():
    assert osm.parse_height_m("12") == 12 and osm.parse_height_m("12.5 m") == 12.5 and osm.parse_height_m("3,5 m") == 3.5
    assert osm.parse_height_m("40 ft") == pytest.approx(12.192) and osm.parse_height_m("40'") == pytest.approx(12.192)
    assert np.isnan(osm.parse_height_m("tall")) and np.isnan(osm.parse_height_m(None)) and np.isnan(osm.parse_height_m("-3"))


def test_height_m_logic_and_assumption_flag():
    b = osm.add_height_m(_buildings())
    assert b["height_m"].iloc[0] == 12 and b["height_src"].iloc[0] == "height_tag" and not b["height_assumption"].iloc[0]
    assert b["height_m"].iloc[1] == pytest.approx(12.192)
    assert b["height_m"].iloc[2] == 12.0 and b["height_src"].iloc[2] == "levels_x3_assumption" and b["height_assumption"].iloc[2]
    assert b["height_m"].iloc[3] == 6.0 and b["height_assumption"].iloc[3]          # unparseable height falls back to levels
    assert np.isnan(b["height_m"].iloc[4]) and b["height_src"].iloc[4] == "none" and not b["height_assumption"].iloc[4]
    assert b["height_m"].iloc[5] == 3.5                                             # tag beats levels
    assert "height_m" not in _buildings().columns                                   # input untouched


def test_levels_column_alias():
    g = gpd.GeoDataFrame({"building_levels": ["3"], "geometry": [Point(10.5, 59.5)]}, crs=4326)
    assert osm.add_height_m(g)["height_m"].iloc[0] == 9.0


def test_clip_and_postprocess():
    far = gpd.GeoDataFrame({"height": ["5"], "geometry": [Point(20, 60)]}, crs=4326)
    layers = osm.postprocess({"buildings": _buildings(), "quays": gpd.GeoDataFrame(
        {"man_made": ["pier", "quay"], "geometry": [LineString([(10.2, 59.5), (10.21, 59.5)]), LineString([(30, 60), (30.1, 60)])]}, crs=4326),
        "far": far}, BBOX)
    assert len(layers["quays"]) == 1 and layers["far"].empty and "height_m" in layers["buildings"]


def test_write_layers_and_manifest(tmp_path):
    q = gpd.GeoDataFrame({"man_made": ["pier"], "tags": [{"a": "b"}], "nodes": [[1, 2]], "geometry": [LineString([(10.2, 59.5), (10.21, 59.5)])]}, crs=4326)
    counts = {"quays": osm.write_layer(q, tmp_path, "quays"), "helipads": osm.write_layer(gpd.GeoDataFrame(geometry=[], crs=4326), tmp_path, "helipads"),
              "buildings": osm.write_layer(osm.add_height_m(_buildings()), tmp_path, "buildings")}
    assert counts == {"quays": 1, "helipads": 0, "buildings": 6}
    fc = json.loads((tmp_path / "quays.geojson").read_text())
    assert fc["type"] == "FeatureCollection" and fc["features"][0]["properties"]["man_made"] == "pier"
    assert json.loads((tmp_path / "helipads.geojson").read_text())["features"] == []
    b = json.loads((tmp_path / "buildings.geojson").read_text())["features"]
    assert b[2]["properties"]["height_assumption"] is True and b[2]["properties"]["height_m"] == 12.0
    man = osm.write_manifest(tmp_path, counts, BBOX, source="norway-latest.osm.pbf", source_date="2026-11-01")
    on_disk = json.loads((tmp_path / "manifest.json").read_text())
    assert on_disk == man and man["licence"] == "ODbL 1.0" and "OpenStreetMap contributors" in man["credit"]
    assert "ODbL" in man["attribution"] and man["layers"]["buildings"]["features"] == 6 and man["source_date"] == "2026-11-01"
    assert any("3 m" in a for a in man["assumptions"])


def test_overture_is_a_spec(tmp_path):
    with pytest.raises(NotImplementedError):
        osm.overture_buildings_spec(BBOX, tmp_path)


def test_fetch_world_flags_exist():
    import inspect

    from offsim.worlds import fetch_world
    src = inspect.getsource(fetch_world)
    for flag in ("--world", "--out", "--pull", "--metocean", "--depth", "--depth-only", "--osm", "--ais"):
        assert f'"{flag}"' in src, flag
    assert "osm" in inspect.signature(fetch_world.fetch).parameters and "ais_path" in inspect.signature(fetch_world.fetch).parameters


def test_fetch_world_get_retries_once_on_gateway_error(monkeypatch):
    # why: the bergen-ncs coast stage failed in 2 s on a transient Overpass 502;
    # get() must retry once on 502/503, and the test must prove the retry without waiting.
    import urllib.error

    from offsim.worlds import fetch_world
    monkeypatch.setattr(fetch_world, "GET_RETRY_S", 0)

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"ok"

    calls = {"n": 0}

    def flaky(req, timeout=300):
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.HTTPError(req.full_url, 502, "Bad Gateway", {}, None)
        return Resp()

    monkeypatch.setattr(urllib.request, "urlopen", flaky)
    assert fetch_world.get("https://example.invalid/x") == b"ok" and calls["n"] == 2


def test_fetch_world_get_raises_other_http_errors_at_once(monkeypatch):
    import urllib.error

    from offsim.worlds import fetch_world
    calls = {"n": 0}

    def flaky(req, timeout=300):
        calls["n"] += 1
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", flaky)
    with pytest.raises(urllib.error.HTTPError):
        fetch_world.get("https://example.invalid/x")
    assert calls["n"] == 1
