"""Land logistics on roads: RoadGraph, the `road` engine, the pipeline's road mode and gate 4b (AIS).

A synthetic 4 x 4 lattice (no network, no fetched world). lon = 7.00 + 0.02 i, lat = 62.700 + 0.005 j  (about 1.0 km x 0.55 km cells):
  row j=0   residential (50 km/h default), two-way          the short but slow way from A to B
  row j=1   secondary (80 km/h), ONE-WAY west -> east         the fast way A -> B, not usable B -> A
  rows 2,3  secondary, two-way; the row-3 edge between columns 1 and 2 bends north (a mid vertex) to test geometry
  columns   secondary, two-way
"""
import json
import math

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import yaml
from pyproj import Geod
from shapely.geometry import LineString, MultiLineString, Point
from shapely.ops import unary_union

from offsim.contract import validate
from offsim.engines import Plan, Problem, Unsupported, World, get_engine
from offsim.pipeline import run
from offsim.traffic import ais
from offsim.worlds.roads import DEFAULT_SPEED_KPH, RoadGraph, parse_maxspeed_kph

GEOD = Geod(ellps="WGS84")
LON0, LAT0, DLON, DLAT = 7.00, 62.700, 0.02, 0.005


def P(i, j):
    return (LON0 + DLON * i, LAT0 + DLAT * j)


def lattice_gdf():
    rows = []

    def add(coords, hw="secondary", **tags):
        rows.append({"highway": hw, "maxspeed": None, "oneway": None, **tags, "geometry": LineString(coords)})

    for j in range(4):
        for i in range(3):
            coords = [P(i, j), P(i + 1, j)]
            if j == 3 and i == 1:
                coords = [P(1, 3), (LON0 + DLON * 1.5, LAT0 + DLAT * 3 + 0.001), P(2, 3)]
            add(coords, "residential" if j == 0 else "secondary", oneway="yes" if j == 1 else None)
    for i in range(4):
        for j in range(3):
            add([P(i, j), P(i, j + 1)])
    add([(8.0, 63.5), (8.001, 63.5)], "secondary")                      # an island far away: never the snap target
    add([P(0, 0), (LON0, LAT0 - 0.0001)], "footway")                    # not drivable: dropped
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=4326)


@pytest.fixture(scope="module")
def roads_path(tmp_path_factory):
    p = tmp_path_factory.mktemp("roads") / "roads.geojson"
    lattice_gdf().to_file(p, driver="GeoJSON")
    return p


@pytest.fixture(scope="module")
def rg(roads_path):
    return RoadGraph(roads_path)


def seg_m(a, b):
    return GEOD.inv(a[0], a[1], b[0], b[1])[2]


def offroad(p, north_m=0.0, east_m=0.0):
    return (p[0] + east_m / (111_320 * math.cos(math.radians(p[1]))), p[1] + north_m / 110_574)


# ------------------------------------------------------------------------------------------------ RoadGraph
def test_maxspeed_parsing():
    assert parse_maxspeed_kph("50") == 50 and parse_maxspeed_kph("30;50") == 30
    assert parse_maxspeed_kph("30 mph") == pytest.approx(48.28, abs=0.01)
    assert all(math.isnan(parse_maxspeed_kph(x)) for x in (None, "signals", "none", "NO:urban", float("nan")))


def test_graph_stats_and_documented_defaults(rg):
    assert rg.stats["dropped_non_driving"] == 1 and rg.stats["edges"] == 4 * 3 + 4 * 3 + 1
    assert rg.stats["default_speed_share"] == 1.0                     # no maxspeed tag anywhere
    assert "Statens vegvesen" in rg.speed_src and "not verified per road" in rg.speed_src
    assert set(DEFAULT_SPEED_KPH.values()) >= {50.0, 80.0, 90.0}
    d = rg.describe()
    assert d["graph"] == "roads" and d["speed_defaults_are_assumptions"] is True
    with pytest.raises(ValueError, match="no speed"):
        RoadGraph(gpd.GeoDataFrame({"highway": ["gravity_tube"]}, geometry=[LineString([(7, 62), (7.01, 62)])], crs=4326))


def test_maxspeed_tag_beats_class_default():
    g = gpd.GeoDataFrame({"highway": ["secondary", "secondary"], "maxspeed": ["30", None], "oneway": [None, None]},
                         geometry=[LineString([(7, 62), (7.01, 62)]), LineString([(7.01, 62), (7.02, 62)])], crs=4326)
    r = RoadGraph(g)
    assert r.stats["default_speed_edges"] == 1
    _, dist, time = r.legs(r.snap([(7.0, 62.0), (7.01, 62.0), (7.02, 62.0)]))
    assert dist[0, 1] / time[0, 1] == pytest.approx(30 / 3.6, rel=1e-6)
    assert dist[1, 2] / time[1, 2] == pytest.approx(80 / 3.6, rel=1e-6)


def test_fastest_path_differs_from_shortest_and_oneway_is_asymmetric(roads_path, rg):
    A, B = P(0, 0), P(3, 0)
    nodes = rg.snap([A, B])
    legs, dist, time = rg.legs(nodes)
    row = sum(seg_m(P(i, 0), P(i + 1, 0)) for i in range(3))
    row1 = sum(seg_m(P(i, 1), P(i + 1, 1)) for i in range(3))
    up = seg_m(P(0, 0), P(0, 1))
    around = row1 + 2 * up
    # A->B: residential row 0 takes row / (50/3.6); the one-way row 1 (80 km/h) plus two verticals is faster though longer
    assert time[0, 1] == pytest.approx(around / (80 / 3.6), rel=1e-4)
    assert dist[0, 1] == pytest.approx(around, rel=1e-4) and dist[0, 1] > row
    assert time[0, 1] < row / (50 / 3.6)
    # B->A may not use the one-way row: slow row 0 is best
    assert dist[1, 0] == pytest.approx(row, rel=1e-4) and time[1, 0] == pytest.approx(row / (50 / 3.6), rel=1e-4)
    assert (0, 1) in legs and (1, 0) in legs and dist[0, 0] == 0
    short = RoadGraph(roads_path, weight="length")
    _, d2, t2 = short.legs(short.snap([A, B]))
    assert d2[0, 1] == pytest.approx(row, rel=1e-4) and t2[0, 1] > time[0, 1]       # shortest is slower than fastest


def test_profile_matches_time_matrix_and_geometry_is_on_roads(rg):
    nodes = rg.snap([P(0, 0), P(3, 3), P(2, 1)])
    legs, dist, time = rg.legs(nodes)
    for (i, j), pts in legs.items():
        prof = rg.leg_profile[(i, j)]
        assert len(prof) == len(pts) and prof[0] == 0 and prof[-1] == pytest.approx(time[i, j])
        assert np.all(np.diff(prof) >= 0)
        assert tuple(pts[0]) == pytest.approx(nodes[i]) and tuple(pts[-1]) == pytest.approx(nodes[j])
        length = sum(seg_m(a, b) for a, b in zip(pts, pts[1:]))
        assert length == pytest.approx(dist[i, j], rel=1e-6)
    bend = (LON0 + DLON * 1.5, LAT0 + DLAT * 3 + 0.001)
    nodes = rg.snap([P(1, 3), P(2, 3)])
    legs, _, _ = rg.legs(nodes)
    assert any(tuple(p) == pytest.approx(bend) for p in legs[(0, 1)]) and any(tuple(p) == pytest.approx(bend) for p in legs[(1, 0)])


def test_snap_moves_onto_the_road_and_reports_metres(rg):
    mid = ((P(0, 2)[0] + P(1, 2)[0]) / 2, P(0, 2)[1])
    p = offroad(mid, north_m=30.0)
    (q,) = rg.snap([p])
    assert rg.snap_m == [pytest.approx(30.0, abs=1.0)]
    assert q[1] == pytest.approx(P(0, 2)[1], abs=1e-9)                       # on the row-2 street
    (q2,) = rg.snap([P(2, 2)])
    assert rg.snap_m == [0.0] and q2 == pytest.approx(P(2, 2))


def test_far_point_and_island_never_teleport_silently(roads_path, rg):
    with pytest.raises(ValueError, match="nearest road"):
        rg.snap([(9.0, 62.7)])
    # the island at (8.0, 63.5) is not in the main component: a point on it is 'far from the core', not routed to the island
    with pytest.raises(ValueError, match="nearest road"):
        rg.snap([(8.0005, 63.5)])
    loose = RoadGraph(roads_path, max_snap_m=1e6)
    (q,) = loose.snap([(8.0005, 63.5)])
    assert q[1] < 63.0                                                      # moved onto the lattice (and reported by snap_m)
    assert loose.snap_m[0] > 50_000


def test_two_points_on_one_segment_travel_along_it(rg):
    a = offroad((LON0 + DLON * 0.25, LAT0 + DLAT * 2), north_m=5)
    b = offroad((LON0 + DLON * 0.75, LAT0 + DLAT * 2), north_m=5)
    nodes = rg.snap([a, b])
    legs, dist, time = rg.legs(nodes)
    assert dist[0, 1] == pytest.approx(seg_m(nodes[0], nodes[1]), rel=1e-6) and dist[1, 0] == pytest.approx(dist[0, 1], rel=1e-6)
    assert time[0, 1] == pytest.approx(dist[0, 1] / (80 / 3.6), rel=1e-6)


def test_one_way_street_in_the_wrong_direction_goes_around(rg):
    a = (LON0 + DLON * 1.25, LAT0 + DLAT * 1)
    b = (LON0 + DLON * 1.75, LAT0 + DLAT * 1)
    nodes = rg.snap([a, b])
    _, dist, _ = rg.legs(nodes)
    direct = seg_m(nodes[0], nodes[1])
    assert dist[0, 1] == pytest.approx(direct, rel=1e-6)                    # with the flow
    assert dist[1, 0] > 3 * direct                                          # against it: around the block


# ------------------------------------------------------------------------------------------------ engine
def problem_and_world(rg, tw=None, speed=22.2, domain="land"):
    pts = rg.snap([P(0, 0), P(3, 2), P(1, 3), P(3, 0)])
    legs, dist, time = rg.legs(pts)
    prob = Problem(cls={"CVRP"}, nodes=pts, dist_m=dist, demand={1: 3, 2: 2, 3: 4},
                   fleet=[{"cls": "truck", "count": 2, "capacity": 10, "speed_mps": speed, "domain": domain}],
                   service_s={1: 600, 2: 600, 3: 600}, tw=tw or {},
                   extra={"road_leg_profile": rg.leg_profile, "road_time_s": time})
    return prob, World(name="grid", legs=legs), dist, time


def test_road_engine_is_registered_and_passes_the_contract(rg):
    eng = get_engine("road")
    assert eng.name == "road" and eng.classes == {"CVRP", "VRPTW"} and eng.needs_weather is False
    prob, world, dist, time = problem_and_world(rg)
    plan = Plan(routes={"TRUCK-1": [1, 2], "TRUCK-2": [3]}, objective=0.0)
    res = eng.simulate(prob, plan, world)
    assert set(res.agents["domain"]) == {"land"} and "drive" in set(res.traj["state"]) and "sail" not in set(res.traj["state"])
    rep = validate(res.traj, res.agents)
    assert rep.ok, rep
    # driving time of TRUCK-1 = the time matrix over its legs (uncapped: truck top speed = secondary limit)
    legs_t = time[0, 1] + time[1, 2] + time[2, 0]
    k = res.meta["agents"]["TRUCK-1"]["time_by_state_s"]
    assert k["drive"] == pytest.approx(legs_t, abs=1.0) and k["unload"] == pytest.approx(1200, abs=1.0)
    legs_d = dist[0, 1] + dist[1, 2] + dist[2, 0]
    assert res.meta["agents"]["TRUCK-1"]["distance_km"] * 1000 == pytest.approx(legs_d, rel=0.005)   # sphere (contract) vs WGS84 (graph): ~0.3 % at 62.7 N
    assert res.meta["speed_cap_applied"] is False and res.meta["time_basis"] == "road_leg_profile"


def test_engine_speed_cap_lowers_speed_never_raises_it(rg):
    prob, world, _, time = problem_and_world(rg, speed=10.0)
    res = get_engine("road").simulate(prob, Plan(routes={"TRUCK-1": [1]}, objective=0.0), world)
    assert res.meta["speed_cap_applied"] is True
    assert validate(res.traj, res.agents).ok
    assert res.meta["agents"]["TRUCK-1"]["time_by_state_s"]["drive"] > 1.5 * (time[0, 1] + time[1, 0])


def test_engine_time_windows_use_the_road_clock(rg):
    prob, world, _, time = problem_and_world(rg, tw={1: (5000.0, 9000.0)})
    res = get_engine("road").simulate(prob, Plan(routes={"TRUCK-1": [1]}, objective=0.0), world)
    ev = res.events[res.events["event"] == "tw_wait"]
    assert len(ev) == 1 and ev["duration_s"].iloc[0] == pytest.approx(5000 - time[0, 1], abs=1.0)
    assert validate(res.traj, res.agents).ok


def test_engine_unsupported_instead_of_approximating(rg):
    prob, world, _, _ = problem_and_world(rg)
    eng = get_engine("road")
    plan = Plan(routes={"TRUCK-1": [1, 2]}, objective=0.0)
    gap = World(name="grid", legs={k: v for k, v in world.legs.items() if k != (1, 2)})
    with pytest.raises(Unsupported, match="no road leg"):
        eng.simulate(prob, plan, gap)
    reverse_only = World(name="grid", legs={k: v for k, v in world.legs.items() if k != (2, 0)})
    with pytest.raises(Unsupported, match="no road leg"):                      # the reverse leg is not a stand-in on a directed graph
        eng.simulate(prob, plan, reverse_only)
    with pytest.raises(Unsupported, match="no travel time"):
        eng.simulate(Problem(**{**prob.__dict__, "extra": {}}), plan, world)
    with pytest.raises(Unsupported, match="world.legs"):
        eng.simulate(prob, plan, World(name="grid"))
    with pytest.raises(Unsupported, match="land agents"):
        eng.simulate(Problem(**{**prob.__dict__, "fleet": [{**prob.fleet[0], "domain": "sea"}]}), plan, world)
    mixed = Problem(**{**prob.__dict__, "fleet": [{**prob.fleet[0]}, {"cls": "van", "count": 1, "capacity": 5, "speed_mps": 15.0}]})
    with pytest.raises(Unsupported, match="different speed"):
        eng.simulate(mixed, Plan(routes={"TRUCK-1": [1], "VAN-1": [2]}, objective=0.0), world)
    with pytest.raises(Unsupported, match="also needs"):
        eng.simulate(Problem(**{**prob.__dict__, "cls": {"PDP"}}), plan, world)


# ------------------------------------------------------------------------------------------------ pipeline
def write_world(tmp_path, with_roads=True):
    data = tmp_path / "data"
    osm = data / "worlds" / "grid" / "osm"
    osm.mkdir(parents=True)
    if with_roads:
        lattice_gdf().to_file(osm / "roads.geojson", driver="GeoJSON")
    return data


def scenario(tmp_path, validate_block=None, **edit):
    stops = [("C1", P(3, 2)), ("C2", P(1, 3)), ("C3", P(3, 0))]
    sc = {
        "paper": {"id": "road-test", "title": "t", "authors": [], "year": 2026, "doi": "", "licence": "MIT"},
        "problem": {"class": ["CVRP"], "objective": "distance", "solver": "pyvrp",
                    "constraints": [{"name": "capacity", "formula_or_text": "load <= capacity", "assumption": True}]},
        "world": "grid",
        "fleet": [{"cls": "truck", "count": {"value": 2, "assumption": True}, "capacity": {"value": 6, "assumption": True},
                   "speed_mps": {"value": 22.2, "assumption": True}, "domain": "land"}],
        "instance": {"service_s": {"value": 600, "assumption": True},
                     "base": {"name": "Depot", "lon": offroad(P(0, 0), 20, 10)[0], "lat": offroad(P(0, 0), 20, 10)[1], "assumption": True},
                     "stops": [{"name": n, "lon": offroad(p, -15)[0], "lat": offroad(p, -15)[1], "demand": {"value": d, "assumption": True},
                                "assumption": True} for (n, p), d in zip(stops, (3, 2, 4))]},
        "sim": {"max_snap_m": {"value": 500, "assumption": True}},
        "reported": {},
    }
    sc.update(edit)
    if validate_block is not None:
        sc["validate"] = validate_block
    p = tmp_path / "scenario.yaml"
    p.write_text(yaml.safe_dump(sc))
    return p


def road_union():
    g = lattice_gdf()
    g = g[g["highway"] != "footway"]
    return unary_union(list(g.geometry))


def max_offroad_m(traj):
    u = road_union()
    kx, ky = 111_320 * math.cos(math.radians(62.72)), 110_574
    from shapely import affinity
    ul = affinity.scale(u, xfact=kx, yfact=ky, origin=(0, 0))
    return max(ul.distance(Point(x * kx, y * ky)) for x, y in zip(traj["lon"], traj["lat"]))


def test_pipeline_road_mode_follows_roads_through_all_gates(tmp_path):
    data = write_world(tmp_path)
    rep = run(scenario(tmp_path), tmp_path / "out", seconds=1, data_root=data)
    assert rep["provenance"]["graph"] == "roads"
    g = rep["gates"]
    assert [g[k]["pass"] for k in ("0_provenance", "1_plan", "2_replay_equals_plan", "3_contract")] == [True] * 4
    assert g["4b_ais"] == {"pass": True, "detail": "not requested"}
    assert rep["status"] == "not comparable (no reported KPIs)"
    assert rep["snap_m"]["Depot"] == pytest.approx(10.0, abs=1.0) and rep["quay_snap_m"] == rep["snap_m"]
    assert rep["road"]["graph"]["graph"] == "roads" and np.asarray(rep["road"]["time_s"]).shape == (4, 4)
    assert rep["road"]["speed_cap_applied"] is False
    traj = pd.read_csv(tmp_path / "out/trajectory.csv")
    assert set(traj["state"]) >= {"drive", "unload", "idle"} and "sail" not in set(traj["state"])
    assert max_offroad_m(traj) < 1.0                                        # every row sits on a road line
    agents = pd.read_csv(tmp_path / "out/agents.csv")
    assert set(agents["domain"]) == {"land"} and validate(traj, agents).ok
    # the one-way street is never driven against: consecutive samples both on row 1 never move west
    for _, gg in traj.sort_values(["agent_id", "t"]).groupby("agent_id"):
        la, lo = gg["lat"].to_numpy(), gg["lon"].to_numpy()
        on1 = np.abs(la - (LAT0 + DLAT)) < 1e-9
        both = on1[:-1] & on1[1:] & (gg["state"].to_numpy()[:-1] == "drive")
        assert (np.diff(lo)[both] >= -1e-12).all()


def test_world_mode_road_overrides_domain_and_sea_default_is_unchanged(tmp_path):
    data = write_world(tmp_path)
    sc = yaml.safe_load(scenario(tmp_path).read_text())
    sc["fleet"][0].pop("domain")
    sc["world_mode"] = "road"
    p = tmp_path / "wm.yaml"
    p.write_text(yaml.safe_dump(sc))
    rep = run(p, tmp_path / "o2", seconds=1, data_root=data)
    assert rep["provenance"]["graph"] == "roads" and "road" in rep
    assert pd.read_csv(tmp_path / "o2/agents.csv")["domain"].eq("land").all()


def test_missing_roads_file_stops_at_gate_0_with_the_fetch_command(tmp_path):
    data = write_world(tmp_path, with_roads=False)
    rep = run(scenario(tmp_path), tmp_path / "o3", seconds=1, data_root=data)
    assert rep["status"] == "stopped at gate 0_provenance"
    d = rep["gates"]["0_provenance"]["detail"]
    assert d["fix"] == "python -m offsim.worlds.fetch_world --place grid --modes road" and d["missing_roads"].endswith("roads.geojson")
    rep = run(scenario(tmp_path, world="none"), tmp_path / "o3b", seconds=1, data_root=data)
    assert rep["status"] == "stopped at gate 0_provenance" and "road runs need a world" in rep["gates"]["0_provenance"]["detail"]["missing_roads"]


def test_stop_off_the_road_network_stops_at_gate_0(tmp_path):
    data = write_world(tmp_path)
    sc = yaml.safe_load(scenario(tmp_path).read_text())
    sc["instance"]["stops"][0].update(lon=9.5, lat=62.7)
    p = tmp_path / "far.yaml"
    p.write_text(yaml.safe_dump(sc))
    rep = run(p, tmp_path / "o4", seconds=1, data_root=data)
    assert rep["status"] == "stopped at gate 0_provenance" and "nearest road" in rep["gates"]["0_provenance"]["detail"]["road_graph_error"]


# ------------------------------------------------------------------------------------------------ gate 4b (AIS)
def sim_speed_quantiles(tmp_path, data):
    """Run once without the gate and read the simulated speed quantiles in knots exactly as compare_to_sim does."""
    run(scenario(tmp_path), tmp_path / "base", seconds=1, data_root=data)
    traj = pd.read_csv(tmp_path / "base/trajectory.csv")
    tab = ais.compare_to_sim(traj, {"sailing_speed_kn": {"p10": 1.0, "p50": 1.0, "p90": 1.0, "n": 50}})
    return tab.set_index("quantile")["sim"].to_dict()


def put_calibration(data, speed):
    d = data / "worlds" / "grid" / "ais"
    d.mkdir(parents=True, exist_ok=True)
    (d / "calibration.json").write_text(json.dumps({"src": "AIS HAIS synthetic test, offsim.traffic",
                                                    "sailing_speed_kn": {**speed, "n": 200}, "port_call_s": {}, "port_call_all_s": {}}))


def test_ais_gate_passes_when_the_sim_matches_the_calibration(tmp_path):
    data = write_world(tmp_path)
    q = sim_speed_quantiles(tmp_path, data)
    put_calibration(data, q)
    rep = run(scenario(tmp_path, validate_block={"ais": True}), tmp_path / "ok", seconds=1, data_root=data)
    g = rep["gates"]["4b_ais"]
    assert g["pass"] is True and g["detail"]["failed"] == [] and g["detail"]["src"].startswith("AIS HAIS")
    assert not rep["status"].startswith("stopped") and (tmp_path / "ok/trajectory.csv").exists()


def test_ais_gate_failure_stops_like_other_gates(tmp_path):
    data = write_world(tmp_path)
    q = sim_speed_quantiles(tmp_path, data)
    put_calibration(data, {k: v * 2.5 for k, v in q.items()})
    rep = run(scenario(tmp_path, validate_block={"ais": True}), tmp_path / "bad", seconds=1, data_root=data)
    assert rep["status"] == "stopped at gate 4b_ais" and rep["gates"]["4b_ais"]["pass"] is False
    assert rep["gates"]["4b_ais"]["detail"]["failed"] and rep["paper_status"] == "not comparable (no reported KPIs)"
    assert (tmp_path / "bad/report.json").exists() and not (tmp_path / "bad/trajectory.csv").exists()


def test_ais_gate_that_judges_nothing_is_not_a_pass(tmp_path):
    data = write_world(tmp_path)
    put_calibration(data, {})
    rep = run(scenario(tmp_path, validate_block={"ais": True}), tmp_path / "none", seconds=1, data_root=data)
    assert rep["status"] == "stopped at gate 4b_ais" and "no metric comparable" in rep["gates"]["4b_ais"]["detail"]["reason"]


def test_ais_opt_in_without_calibration_stops_with_the_fetch_hint(tmp_path):
    data = write_world(tmp_path)
    rep = run(scenario(tmp_path, validate_block={"ais": True}), tmp_path / "nofile", seconds=1, data_root=data)
    assert rep["status"] == "stopped at gate 0_provenance"
    d = rep["gates"]["0_provenance"]["detail"]
    assert d["missing_ais_calibration"].endswith("ais/calibration.json") and "fetch_world" in d["fix"] and "--ais" in d["fix"]


def test_calibration_file_present_but_not_opted_in_is_ignored(tmp_path):
    data = write_world(tmp_path)
    put_calibration(data, {"p10": 0.1, "p50": 0.1, "p90": 0.1})      # would fail if consulted
    rep = run(scenario(tmp_path, validate_block={"ais": False}), tmp_path / "off", seconds=1, data_root=data)
    assert rep["gates"]["4b_ais"] == {"pass": True, "detail": "not requested"} and not rep["status"].startswith("stopped")


def test_dwell_durations_group_consecutive_rows_per_visit():
    from offsim.pipeline import dwell_durations
    t = pd.DataFrame({"agent_id": "A", "t": [0, 10, 20, 50, 60], "lon": [1, 2, 2, 2, 3], "lat": [0.5] * 5,
                      "state": ["drive", "wait", "unload", "drive", "idle"]})
    assert dwell_durations(t, {(2.0, 0.5): "X"}) == {"X": [40.0]}
