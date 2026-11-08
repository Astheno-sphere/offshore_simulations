"""User-supplied data: GeoJSON world layers and paper timetables -> GTFS -> gtfs engine."""
import json

import geopandas as gpd
import pytest
import yaml
from shapely.geometry import LineString, Point

from offsim.worlds import user_layers


@pytest.fixture
def world(tmp_path):
    d = tmp_path / "data/worlds/testw"
    d.mkdir(parents=True)
    (d / "world.yaml").write_text(yaml.safe_dump({"name": "testw", "bbox": [7.0, 62.6, 7.4, 62.8], "modes": ["road"]}))
    return tmp_path


def test_roads_layer_installed_with_provenance(world, tmp_path):
    f = tmp_path / "r.geojson"
    gpd.GeoDataFrame({"highway": ["primary", "residential"]},
                     geometry=[LineString([(7.1, 62.7), (7.2, 62.7)]), LineString([(7.2, 62.7), (7.9, 62.7)])],
                     crs=4326).to_file(f, driver="GeoJSON")
    e = user_layers.add_layer("testw", "roads", f, "test fixture", "CC0", data_root=world)
    out = gpd.read_file(world / "data/worlds/testw/osm/roads.geojson")
    assert e["features_kept"] == 2 and out.total_bounds[2] <= 7.4 + 1e-9          # clipped to the bbox
    man = json.loads((world / "data/worlds/testw/manifest.json").read_text())
    assert man["user_layers"]["roads"]["src"] == "test fixture"


def test_refuses_utm_without_crs_and_missing_tags(world, tmp_path):
    f = tmp_path / "utm.geojson"
    f.write_text(json.dumps({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"highway": "primary"},
                 "geometry": {"type": "LineString", "coordinates": [[400000, 6950000], [401000, 6950000]]}}]}))
    g = gpd.read_file(f).set_crs(None, allow_override=True)
    assert any("UTM" in p for p in user_layers.check(g, "roads"))
    g2 = gpd.GeoDataFrame({"foo": [1]}, geometry=[LineString([(7.1, 62.7), (7.2, 62.7)])], crs=4326)
    assert any("needs one of" in p for p in user_layers.check(g2, "roads"))
    with pytest.raises(ValueError):
        user_layers.add_layer("testw", "roads", f, "", "CC0", data_root=world)          # provenance required


def test_paper_timetable_runs_through_gtfs_engine(tmp_path):
    from offsim.contract import validate
    from offsim.engines import Plan, Problem, World, get_engine
    from offsim.transit.from_paper import to_gtfs
    tt = {"source": {"paper": "test", "doi": "10.0/x"},
          "service": {"days": ["mon", "tue", "wed", "thu", "fri"], "start_date": 20260105, "end_date": 20261231},
          "lines": [{"id": "1", "mode": "bus",
                     "stops": [{"id": "A", "name": "A", "lon": 7.16, "lat": 62.737, "src": "p.1"},
                               {"id": "B", "name": "B", "lon": 7.20, "lat": 62.745, "assumption": True},
                               {"id": "C", "name": "C", "lon": 7.26, "lat": 62.756, "src": "p.1"}],
                     "run_time_min": {"value": [6, 7], "src": "p.2"}, "dwell_s": {"value": 30, "assumption": True},
                     "headway_min": {"value": 30, "src": "p.2"}, "first": "07:00", "last": "08:00", "both_directions": True}]}
    p = tmp_path / "timetable.yaml"
    p.write_text(yaml.safe_dump(tt))
    man = to_gtfs(p, tmp_path / "gtfs")
    assert man["trips"] == 6 and "lines[0].stops[1]" in man["assumptions"]
    eng = get_engine("gtfs")
    prob = Problem({"TRANSIT-REPLAY"}, [], None, {}, [],
                   extra={"gtfs": {"dir": str(tmp_path / "gtfs"), "date": "2026-01-07", "t0": 6 * 3600, "t1": 10 * 3600}})
    res = eng.simulate(prob, Plan({}, 0.0), World("testw"))
    assert res.kpis["trips"] == 6 and validate(res.traj, res.agents).ok


def test_paper_timetable_refuses_unsourced(tmp_path):
    from offsim.transit.from_paper import to_gtfs
    tt = {"source": {"paper": "x"}, "service": {"days": ["mon"], "start_date": 20260105, "end_date": 20260110},
          "lines": [{"id": "1", "stops": [{"id": "A", "name": "A", "lon": 7, "lat": 62}, {"id": "B", "name": "B", "lon": 7.1, "lat": 62}],
                     "run_time_min": {"value": [5], "src": "p"}, "headway_min": {"value": 10, "src": "p"}, "first": "07:00", "last": "07:30"}]}
    p = tmp_path / "t.yaml"
    p.write_text(yaml.safe_dump(tt))
    with pytest.raises(ValueError, match="needs src"):
        to_gtfs(p, tmp_path / "g")
