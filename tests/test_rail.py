"""Rail layers, RailGraph, station snapping and the GTFS rail hook, on a synthetic network (no pbf, no network)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

gpd = pytest.importorskip("geopandas")
pytest.importorskip("networkx")
from shapely.geometry import LineString, Point  # noqa: E402

from offsim.contract import validate  # noqa: E402
from offsim.transit import gtfs  # noqa: E402
from offsim.worlds import fetch_world, osm, place, rail  # noqa: E402
from offsim.worlds.roads import GEOD  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LAT = 62.73

# main line W->E with a vertex at the siding switch (7.15) and at the branch switch (7.10)
MAIN_A = [(7.00, LAT), (7.10, LAT), (7.15, LAT)]            # usage=main, electrified, no maxspeed (class default 120)
MAIN_B = [(7.15, LAT), (7.22, LAT), (7.30, LAT)]            # maxspeed=100, not electrified
SIDING = [(7.15, LAT), (7.15, LAT + 0.01)]                  # service=siding (excluded by default)
BRANCH = [(7.10, LAT), (7.10, LAT - 0.01)]                  # usage=branch, bridge=yes; leaves MAIN_A at an interior vertex
TRAM = [(7.20, 62.75), (7.25, 62.75)]                       # separate network
ABANDONED = [(7.0, 62.70), (7.1, 62.70)]


def _rail_gdf():
    rows = [
        ("rail", "main", None, "contract", "15000", None, None, None, MAIN_A),
        ("rail", "main", None, None, None, "100", None, "yes", MAIN_B),
        ("rail", None, "siding", None, None, None, None, None, SIDING),
        ("rail", "branch", None, None, None, None, "yes", None, BRANCH),
        ("tram", None, None, "contact_line", "750", None, None, None, TRAM),
        ("abandoned", None, None, None, None, None, None, None, ABANDONED),
    ]
    return gpd.GeoDataFrame({
        "railway": [r[0] for r in rows], "usage": [r[1] for r in rows], "service": [r[2] for r in rows],
        "electrified": [r[3] for r in rows], "voltage": [r[4] for r in rows], "maxspeed": [r[5] for r in rows],
        "bridge": [r[6] for r in rows], "tunnel": [r[7] for r in rows], "gauge": ["1435"] * len(rows),
        "geometry": [LineString(r[8]) for r in rows]}, crs=4326)


def _stations_gdf():
    return gpd.GeoDataFrame({"railway": ["station", "halt", "station"], "name": ["Alpha", "Omega", "Siding end"],
                             "ref": ["A", "O", "S"],
                             "geometry": [Point(7.02, LAT + 0.0002), Point(7.28, LAT - 0.0002), Point(7.15, LAT + 0.0099)]}, crs=4326)


def _len(pts):
    p = np.asarray(pts)
    return float(GEOD.inv(p[:-1, 0], p[:-1, 1], p[1:, 0], p[1:, 1])[2].sum())


@pytest.fixture(scope="module")
def rg():
    return rail.RailGraph(_rail_gdf())


# --- layers, modes, plumbing ----------------------------------------------------------------------------------

def test_osm_rail_layers_declared_and_written(tmp_path):
    assert "rail" in osm.LAYERS and "stations" in osm.LAYERS and "quays" in osm.LAYERS      # existing layers kept
    crit, keys = osm.FILTERS["rail"]
    assert set(crit["railway"]) == {"rail", "light_rail", "subway", "tram"}
    for k in ("usage", "electrified", "voltage", "gauge", "maxspeed", "service", "tunnel", "bridge"):
        assert k in keys
    crit, keys = osm.FILTERS["stations"]
    assert set(crit["railway"]) == {"station", "halt", "tram_stop"} and "name" in keys and "ref" in keys
    got = osm.postprocess({"rail": _rail_gdf(), "stations": _stations_gdf()}, (6.9, 62.6, 7.5, 62.9))
    counts = {k: osm.write_layer(v, tmp_path, k) for k, v in got.items()}
    man = osm.write_manifest(tmp_path, counts, (6.9, 62.6, 7.5, 62.9), source="x.osm.pbf")
    assert man["licence"] == "ODbL 1.0" and man["layers"]["rail"]["features"] == 6 and man["layers"]["stations"]["features"] == 3
    fc = json.loads((tmp_path / "rail.geojson").read_text())
    assert fc["features"][0]["properties"]["electrified"] == "contract"


def test_rail_mode_and_fetch_plumbing():
    assert "rail" in place.MODES
    assert place.layers_for(["rail"]) == ["land", "rail", "stations"]
    assert place.layers_for(["bus", "rail"]) == ["land", "roads", "gtfs", "rail", "stations"]
    p = fetch_world.plan_layers("rail")
    assert p["osm"] is True and p["gtfs"] is False and p["sea"] is False and p["layers"] == ["land", "rail", "stations"]
    out = subprocess.run([sys.executable, "-m", "offsim.worlds.fetch_world", "--help"], cwd=ROOT, capture_output=True,
                         text=True, check=True).stdout
    assert "air,rail" in out


# --- RailGraph ------------------------------------------------------------------------------------------------

def test_graph_build_stats_and_exclusions(rg):
    st = rg.stats
    assert st["dropped_other_railway"] == 1 and st["excluded_service"] == 1
    assert st["bridge_edges"] == 1 and st["tunnel_edges"] == 1 and st["electrified_edges"] >= 2       # contract + tram
    assert st["components"] == 2                                                                      # main network + tram
    # MAIN_A is split at the branch switch (interior vertex shared with BRANCH): A -> 2 edges, B 1, branch 1, tram 1
    assert st["edges"] == 5
    assert rg.describe()["speed_defaults_are_assumptions"] is True and "assumption: true" in rg.describe()["speed_basis"]
    classes = {a["speed_class"] for a in rg.edge_attrs}
    assert {"rail:main", "rail:branch", "tram"} <= classes


def test_speed_from_maxspeed_else_class_default(rg):
    by = {(a["railway"], a["usage"], a["speed_from_default"]): a["speed_kph"] for a in rg.edge_attrs}
    assert by[("rail", "main", True)] == 120.0                      # default
    assert by[("rail", "main", False)] == 100.0                     # maxspeed tag wins
    assert by[("rail", "branch", True)] == 80.0 and by[("tram", "", True)] == 40.0


def test_shortest_path_and_time(rg):
    a, o = (7.02, LAT), (7.28, LAT)
    legs, dist, time = rg.legs([a, o])
    expect_a = _len([a, (7.10, LAT), (7.15, LAT)])
    expect_b = _len([(7.15, LAT), (7.22, LAT), o])
    assert dist[0, 1] == pytest.approx(expect_a + expect_b, rel=1e-6)
    assert time[0, 1] == pytest.approx(expect_a / (120 / 3.6) + expect_b / (100 / 3.6), rel=1e-6)
    assert dist[0, 1] == pytest.approx(dist[1, 0]) and time[0, 1] == pytest.approx(time[1, 0])      # symmetric
    assert legs[(0, 1)][0] == pytest.approx(a) and legs[(0, 1)][-1] == pytest.approx(o)
    assert all(abs(y - LAT) < 1e-9 for _, y in legs[(0, 1)])                                        # stays on the track
    assert rg.leg_profile[(0, 1)][-1] == pytest.approx(time[0, 1])


def test_branch_reachable_through_split_edge(rg):
    legs, dist, _ = rg.legs([(7.02, LAT), (7.10, LAT - 0.01)])
    assert dist[0, 1] == pytest.approx(_len([(7.02, LAT), (7.10, LAT)]) + _len([(7.10, LAT), (7.10, LAT - 0.01)]), rel=1e-6)


def test_siding_excluded_then_included():
    tip = (7.15, LAT + 0.0099)
    g = rail.RailGraph(_rail_gdf())
    with pytest.raises(ValueError, match="nearest road|nearest track|from the nearest"):
        g.snap([tip])                                              # ~1.1 km from any included track, max_snap 500 m
    g2 = rail.RailGraph(_rail_gdf(), include_service=True)
    assert g2.stats["excluded_service"] == 0 and g2.stats["edges"] == 6
    legs, dist, _ = g2.legs([(7.02, LAT), tip])
    assert dist[0, 1] > _len([(7.02, LAT), (7.15, LAT)]) + 1000


def test_unreachable_pair_raises_never_straight(rg):
    with pytest.raises(ValueError, match="no rail route"):
        rg.legs([(7.02, LAT), (7.22, 62.75)])                      # main line -> tram network
    with pytest.raises(ValueError, match="no rail route"):
        rg.chain(rg.snap([(7.02, LAT), (7.22, 62.75)]))


def test_chain_matches_legs(rg):
    pts = rg.snap([(7.02, LAT), (7.10, LAT - 0.0099), (7.28, LAT)])
    path, idx, dist, time = rg.chain(pts)
    assert idx[0] == 0 and idx == sorted(idx) and path[idx[1]] == pytest.approx(pts[1])
    _, d, t = rg.legs(pts)
    assert dist[-1] == pytest.approx(d[0, 1] + d[1, 2], rel=1e-9) and time[-1] == pytest.approx(t[0, 1] + t[1, 2], rel=1e-9)


def test_station_snapping_reports_distance():
    g = rail.RailGraph(_rail_gdf())
    st = g.snap_stations(_stations_gdf())
    assert list(st["station"]) == ["Alpha", "Omega", "Siding end"]
    assert st.loc[0, "snap_m"] == pytest.approx(0.0002 * 111_195, abs=1.0) and bool(st.loc[0, "snapped"])
    assert st.loc[0, "node_lat"] == pytest.approx(LAT)
    assert not bool(st.loc[2, "snapped"]) and np.isnan(st.loc[2, "node_lon"]) and st.loc[2, "snap_m"] > 900      # siding excluded
    with pytest.raises(ValueError, match="Siding end"):
        g.snap_stations(_stations_gdf(), strict=True)
    st2 = rail.RailGraph(_rail_gdf(), include_service=True).snap_stations(_stations_gdf())
    assert st2["snapped"].all() and st2.loc[2, "snap_m"] < 15


def test_load_world_rail_absent_and_present(tmp_path):
    assert rail.load_world_rail(tmp_path) is None
    (tmp_path / "osm").mkdir()
    (tmp_path / "osm" / "rail.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": []}))
    assert rail.load_world_rail(tmp_path) is None                   # empty layer is not an error
    osm.write_layer(_rail_gdf(), tmp_path / "osm", "rail")
    assert isinstance(rail.load_world_rail(tmp_path), rail.RailGraph)


# --- GTFS hook ------------------------------------------------------------------------------------------------

STOPS = {"S1": (7.02, LAT + 0.0002), "SB": (7.10, LAT - 0.0099), "S2": (7.28, LAT - 0.0002), "FAR": (7.20, 62.80)}


def _write_world(root: Path) -> Path:
    g = root / "gtfs"
    g.mkdir(parents=True)
    pd.DataFrame([{"stop_id": k, "stop_name": k, "stop_lat": v[1], "stop_lon": v[0]} for k, v in STOPS.items()]).to_csv(g / "stops.txt", index=False)
    pd.DataFrame([{"route_id": "RR", "agency_id": "A", "route_short_name": "R1", "route_type": 2},
                  {"route_id": "RB", "agency_id": "A", "route_short_name": "B1", "route_type": 3}]).to_csv(g / "routes.txt", index=False)
    pd.DataFrame([{"route_id": "RR", "service_id": "D", "trip_id": "TRAIN", "shape_id": ""},
                  {"route_id": "RR", "service_id": "D", "trip_id": "SHAPED", "shape_id": "SH"},
                  {"route_id": "RR", "service_id": "D", "trip_id": "TOOFAR", "shape_id": ""},
                  {"route_id": "RB", "service_id": "D", "trip_id": "BUS", "shape_id": ""}]).to_csv(g / "trips.txt", index=False)
    st = []
    for trip, seq in (("TRAIN", [("S1", "08:00:00", "08:00:00"), ("SB", "08:06:00", "08:07:00"), ("S2", "08:17:00", "08:17:00")]),
                      ("SHAPED", [("S1", "09:00:00", "09:00:00"), ("S2", "09:10:00", "09:10:00")]),
                      ("TOOFAR", [("S1", "09:30:00", "09:30:00"), ("FAR", "09:50:00", "09:50:00")]),
                      ("BUS", [("S1", "10:00:00", "10:00:00"), ("S2", "10:30:00", "10:30:00")])):
        for i, (s, a, d) in enumerate(seq):
            st.append({"trip_id": trip, "stop_id": s, "arrival_time": a, "departure_time": d, "stop_sequence": i + 1})
    pd.DataFrame(st).to_csv(g / "stop_times.txt", index=False)
    pd.DataFrame([{"service_id": "D", **{d: 1 for d in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")},
                   "start_date": "20260101", "end_date": "20261231"}]).to_csv(g / "calendar.txt", index=False)
    pd.DataFrame([{"shape_id": "SH", "shape_pt_lat": LAT + 0.001, "shape_pt_lon": 7.02 + 0.13 * i, "shape_pt_sequence": i}
                  for i in range(3)] + [{"shape_id": "SH", "shape_pt_lat": LAT + 0.001, "shape_pt_lon": 7.28, "shape_pt_sequence": 3}]).to_csv(g / "shapes.txt", index=False)
    osm.write_layer(_rail_gdf(), root / "osm", "rail")
    return g


def _local_dist_m(traj, lines):
    from shapely.geometry import MultiLineString

    kx, ky = 111_320.0 * np.cos(np.radians(LAT)), 110_574.0
    net = MultiLineString([[(x * kx, y * ky) for x, y in ln] for ln in lines])
    return np.array([net.distance(Point(x * kx, y * ky)) for x, y in zip(traj["lon"], traj["lat"])])


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    root = tmp_path_factory.mktemp("railworld")
    return root, _write_world(root)


def test_rail_trip_follows_the_track(world):
    _, g = world
    feed = gtfs.load(g)
    traj, agents, events, meta = gtfs.build(feed, "2026-03-04", 7 * 3600, 11 * 3600, 30, ["rail"])        # rail="auto"
    t = traj[traj["agent_id"] == "TRAIN"]
    assert meta["geometry_by_trip"]["TRAIN"] == "rail_graph"
    assert (_local_dist_m(t, [MAIN_A, MAIN_B, BRANCH]) < 1.0).all()                                      # every point within 1 m
    assert t["lat"].min() < LAT - 0.009                                                                  # it went down the branch
    rep = validate(traj, agents)
    assert rep.ok, str(rep)
    assert meta["rail_snap_m_max"] < 25 and meta["geometry"]["rail_graph"] == 1


def test_geometry_order_shapes_then_rail_then_straight(world):
    _, g = world
    feed = gtfs.load(g)
    traj, agents, _, meta = gtfs.build(feed, "2026-03-04", 7 * 3600, 11 * 3600, 30, None)
    assert meta["geometry_by_trip"] == {"TRAIN": "rail_graph", "SHAPED": "shapes", "TOOFAR": "straight", "BUS": "straight"}
    assert meta["geometry"] == {"shapes": 1, "rail_graph": 1, "straight": 2}
    assert meta["rail_fallback"] == 1 and any("max_snap_m" in k or "nearest" in k for k in meta["rail_fallback_reasons"])
    sh = traj[traj["agent_id"] == "SHAPED"]
    assert np.allclose(sh["lat"].iloc[1:-1].mean(), LAT + 0.001, atol=1e-4)                              # followed shapes.txt, not the rail
    assert validate(traj, agents).ok


def test_rail_off_and_explicit_graph(world):
    root, g = world
    feed = gtfs.load(g)
    _, _, _, off = gtfs.build(feed, "2026-03-04", 7 * 3600, 11 * 3600, 30, ["rail"], rail=False)
    assert off["geometry_by_trip"]["TRAIN"] == "straight" and off["geometry"]["rail_graph"] == 0
    tr_off, _, _, _ = gtfs.build(feed, "2026-03-04", 7 * 3600, 11 * 3600, 30, ["rail"], rail=False)
    assert _local_dist_m(tr_off[tr_off["agent_id"] == "TRAIN"], [MAIN_A, MAIN_B, BRANCH]).max() > 100     # the old straight line
    _, _, _, on = gtfs.build(feed, "2026-03-04", 7 * 3600, 11 * 3600, 30, ["rail"], rail=rail.RailGraph(_rail_gdf()))
    assert on["geometry_by_trip"]["TRAIN"] == "rail_graph"
    _, _, _, p = gtfs.build(feed, "2026-03-04", 7 * 3600, 11 * 3600, 30, ["rail"], rail=str(root / "osm" / "rail.geojson"))
    assert p["geometry_by_trip"]["TRAIN"] == "rail_graph"


def test_no_rail_layer_means_old_behaviour(tmp_path):
    g = _write_world(tmp_path)
    (tmp_path / "osm" / "rail.geojson").unlink()
    _, _, _, meta = gtfs.build(gtfs.load(g), "2026-03-04", 7 * 3600, 11 * 3600, 30, ["rail"])
    assert meta["geometry_by_trip"]["TRAIN"] == "straight" and meta["rail_fallback"] == 0
