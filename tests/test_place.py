"""offsim.worlds.place + fetch_world place/mode plumbing, offline (fixtures, injected fetch)."""
import json
import math
import subprocess
import sys

import pytest
import yaml

from conftest import ROOT
from offsim.worlds import fetch_world, place

FIX = ROOT / "tests/fixtures/place/stedsnavn.json"


def test_bbox_parsing():
    p = place.resolve("10.2,58.95,11.05,59.95")
    assert p.bbox == (10.2, 58.95, 11.05, 59.95) and p.name == "bbox" and p.source == "explicit bbox"
    assert p.lon == pytest.approx(10.625) and p.lat == pytest.approx(59.45)
    assert place.resolve(" 10.2 , 58.95 , 11.05 , 59.95 ").bbox == p.bbox
    with pytest.raises(place.PlaceError):
        place.resolve("11,58,10,59")                       # west > east


@pytest.mark.parametrize("q", ["Ålesund", "ålesund", "alesund", "ALESUND", " Alesund "])
def test_gazetteer_case_and_diacritics_insensitive(q):
    p = place.resolve(q, fetch=lambda u: pytest.fail("gazetteer hit must not call the network"))
    assert p.name == "Ålesund" and p.lon == pytest.approx(6.15, abs=0.1) and "unverified" in p.source
    assert p.bbox[0] < p.lon < p.bbox[2] and p.bbox[1] < p.lat < p.bbox[3]


def test_gazetteer_content():
    assert len(place.GAZETTEER) >= 20
    for k, g in place.GAZETTEER.items():
        assert 4 < g["lon"] < 32 and 57 < g["lat"] < 72 and g["radius_km"] > 0, k
        assert g["source"] == "approx centre (Claude, unverified); refine via stedsnavn", k
    assert place.resolve("tromso").name == "Tromsø" and place.resolve("Agotnes").name == "Ågotnes"


def test_stedsnavn_parse_from_fixture_and_resolve():
    hits = place.parse_stedsnavn(FIX.read_bytes(), "Namsos")
    assert [h["name"] for h in hits] == ["Namsos", "Namsosvegen"]
    assert hits[0]["lat"] == pytest.approx(64.46667) and hits[0]["lon"] == 11.5 and hits[0]["municipality"] == "Namsos"
    seen = []
    p = place.resolve("Namsos", fetch=lambda u: seen.append(u) or FIX.read_bytes())
    assert "sok=Namsos" in seen[0] and "utkoordsys=4258" in seen[0] and "fuzzy=false" in seen[0] and "treffPerSide=5" in seen[0]
    assert (p.name, p.lon, p.lat) == ("Namsos", 11.5, pytest.approx(64.46667)) and "stedsnavn" in p.source
    assert p.bbox == place.bbox_for(11.5, 64.46667, place.DEFAULT_RADIUS_KM)


def test_stedsnavn_defensive():
    assert place.parse_stedsnavn(json.dumps({"navn": [{"representasjonspunkt": {"lat": 60, "lon": 5}}]}), "X")[0]["name"] == "X"
    assert place.parse_stedsnavn({"navn": [{"noe": 1}, "junk"]}) == []
    with pytest.raises(place.PlaceError):
        place.parse_stedsnavn(b"<html>")
    with pytest.raises(place.PlaceError):
        place.resolve("Nowhereville", fetch=lambda u: b'{"navn": []}')


def test_bbox_for_math():
    w, s, e, n = place.bbox_for(10.0, 60.0, 10)
    assert (n - s) / 2 * place.KM_PER_DEG == pytest.approx(10, rel=1e-3)
    assert (e - w) / (n - s) == pytest.approx(1 / math.cos(math.radians(60)), rel=1e-3)   # lon span wider at 60 N
    assert (w + e) / 2 == pytest.approx(10.0) and (s + n) / 2 == pytest.approx(60.0)
    with pytest.raises(place.PlaceError):
        place.bbox_for(10, 60, 0)


def test_slugify():
    assert place.slugify("Ålesund") == "alesund" and place.slugify("Halten/Kristiansund offshore") == "halten-kristiansund-offshore"


def test_layers_for_modes():
    assert place.layers_for(["sea"]) == ["land", "coast", "sealanes", "quays", "ferry"]
    assert "depth" in place.layers_for("sea", depth=True)
    assert place.layers_for(["road"]) == ["land", "roads"] and place.layers_for(["walk"]) == ["land", "roads"]
    assert place.layers_for(["bus"]) == ["land", "roads", "gtfs"] and place.layers_for(["air"]) == ["land", "helipads", "aerodromes"]
    with pytest.raises(place.PlaceError):
        place.layers_for(["rail"])
    with pytest.raises(place.PlaceError):
        place.layers_for([])


def test_world_spec_v2_write_and_load(tmp_path):
    p = place.resolve("Molde")
    path = tmp_path / "sub" / "molde.yaml"
    written = place.write_world_spec(p, "sea,road,bus", path)
    assert yaml.safe_load(path.read_text()) == written
    spec = place.load_world_spec(path)
    assert spec["version"] == 2 and spec["name"] == "molde" and spec["modes"] == ["sea", "road", "bus"]
    assert spec["bbox"] == list(p.bbox) and spec["place"]["name"] == "Molde" and "unverified" in spec["place"]["source"]
    assert {"coast", "sealanes", "roads", "gtfs", "land"} <= set(spec["layers"])
    assert place.load_world_spec(path) == spec


def test_v1_backcompat_on_existing_yaml():
    for name in ("oslofjord", "north-sea-stavanger"):
        raw = yaml.safe_load((ROOT / f"offsim/worlds/{name}.yaml").read_text())
        spec = place.load_world_spec(ROOT / f"offsim/worlds/{name}.yaml")
        assert spec["version"] == 2 and spec["modes"] == ["sea"] and spec["name"] == name
        assert spec["bbox"] == raw["bbox"] and spec["place"]["source"].startswith("bbox centre")
        assert spec["depth"] == raw["depth"] and spec["osm_land"] is True       # v1 keys pass through
        assert "sealanes" in spec["layers"] and "depth" in spec["layers"]


def test_plan_layers_modes_imply_flags():
    assert fetch_world.plan_layers("sea") == {"modes": ["sea"], "osm": False, "gtfs": False, "sea": True,
                                              "layers": place.layers_for(["sea"])}
    for m in ("road", "walk", "air"):
        assert fetch_world.plan_layers([m])["osm"] is True and fetch_world.plan_layers([m])["gtfs"] is False
    bus = fetch_world.plan_layers("bus")
    assert bus["osm"] and bus["gtfs"] and not bus["sea"]
    assert fetch_world.plan_layers("sea,bus")["sea"] and fetch_world.plan_layers("sea,bus")["gtfs"]


def test_fetch_world_cli_flags_present():
    out = subprocess.run([sys.executable, "-m", "offsim.worlds.fetch_world", "--help"], cwd=ROOT, capture_output=True,
                         text=True, check=True).stdout
    for flag in ("--place", "--modes", "--radius-km", "--gtfs", "--world", "--out", "--pull", "--metocean", "--depth",
                 "--depth-only", "--osm", "--osm-pbf", "--ais"):
        assert flag in out, flag


def test_fetch_gtfs_fails_clearly_without_transit_module(monkeypatch, tmp_path):
    import offsim.transit
    monkeypatch.setitem(sys.modules, "offsim.transit.gtfs", None)      # simulate the module missing; no download attempted
    monkeypatch.delattr(offsim.transit, "gtfs", raising=False)        # and drop a cached attribute from earlier imports
    monkeypatch.setattr(fetch_world, "download", lambda *a, **k: pytest.fail("must not download before the module check"))
    with pytest.raises(RuntimeError, match="offsim/transit/gtfs.py"):
        fetch_world.fetch_gtfs({"bbox": [5, 60, 6, 61]}, tmp_path / "w")


def test_workflow_has_place_inputs():
    wf = yaml.safe_load((ROOT / ".github/workflows/fetch-world.yml").read_text())
    ins = (wf.get("on") or wf.get(True))["workflow_dispatch"]["inputs"]
    assert {"world", "place", "modes", "radius_km", "osm", "depth", "metocean_start", "ais_url"} <= set(ins)
    assert ins["modes"]["default"] == "sea" and ins["place"]["required"] is False
