"""Entur GTFS -> trajectory contract (offsim.transit.gtfs, engine "gtfs"), on a tiny hand-written feed."""
from __future__ import annotations

import datetime as dt
import json
import shutil
from pathlib import Path

import numpy as np
import pytest

from offsim.contract import validate
from offsim.engines import Plan, Problem, Unsupported, World, get_engine
from offsim.transit import gtfs

FIX = Path(__file__).parent / "fixtures" / "gtfs_mini"
BBOX = (7.0, 62.6, 7.5, 62.9)     # Molde-ish; excludes X, Y (10E, 60N)
WED = "2026-03-04"                # weekday; SPECIAL runs by calendar_dates only


@pytest.fixture(scope="module")
def clipped(tmp_path_factory):
    d = tmp_path_factory.mktemp("gtfs_clip")
    gtfs.clip(FIX, BBOX, d)
    return d


@pytest.fixture(scope="module")
def feed():
    return gtfs.load(FIX)


@pytest.fixture(scope="module")
def cfeed(clipped):
    return gtfs.load(clipped)


def test_parse_time_past_midnight():
    assert gtfs.parse_time("08:00:00") == 28800
    assert gtfs.parse_time("24:00:00") == 86400
    assert gtfs.parse_time("25:10:00") == 90600
    assert np.isnan(gtfs.parse_time("")) and np.isnan(gtfs.parse_time(None))


def test_route_class_extended_types():
    assert [gtfs.route_class(x) for x in (3, 700, 704, 200, 4, 1000, 1200, 2, 101, 401, 0, 900)] == \
        ["bus", "bus", "bus", "bus", "ferry", "ferry", "ferry", "rail", "rail", "rail", "tram", "tram"]
    assert gtfs.route_class(1100) is None and gtfs.route_class("x") is None


def test_calendar_and_exceptions(feed):
    assert gtfs.service_ids_on(feed, "2026-03-03") == {"WD"}                    # Tuesday
    assert gtfs.service_ids_on(feed, "20260302") == set()                       # Monday, removed
    assert gtfs.service_ids_on(feed, dt.date(2026, 3, 7)) == {"WD"}             # Saturday, added
    assert gtfs.service_ids_on(feed, "2026-03-08") == set()                     # Sunday
    assert gtfs.service_ids_on(feed, WED) == {"WD", "SPECIAL"}                  # calendar_dates only service
    assert gtfs.service_ids_on(feed, "2026-04-01") == set()                     # outside range


def test_trips_on_window_and_types(feed):
    tr = gtfs.trips_on(feed, "2026-03-03")
    assert {"T1", "T2", "T3", "F1"} <= set(tr["agent_id"])
    # T2 runs 23:50 -> 25:10; on Wednesday it shows up as a previous-day carry-over
    wed = gtfs.trips_on(feed, WED, 0, 3600)
    assert "T2~prev" in set(wed["agent_id"]) and wed.set_index("agent_id").loc["T2~prev", "end_s"] == 4200
    assert set(gtfs.trips_on(feed, "2026-03-03", route_types=["ferry"])["trip_id"]) == {"F1"}
    assert set(gtfs.trips_on(feed, "2026-03-03", route_types=[700])["trip_id"]) >= {"OUT1"}


def test_clip_bbox(tmp_path):
    m = gtfs.clip(FIX, BBOX, tmp_path / "c")
    feed = gtfs.load(tmp_path / "c")
    assert set(feed.stops["stop_id"]) == {"A", "B", "C", "D", "E"}              # X, Y dropped
    assert "OUT1" not in set(feed.trips["trip_id"])                             # no stop inside
    assert "ONE1" not in set(feed.trips["trip_id"])                             # only 1 stop inside
    assert {"T1", "T2", "T3", "F1", "SP1"} == set(feed.trips["trip_id"])
    assert "R3" not in set(feed.routes["route_id"])
    assert set(feed.shapes["shape_id"]) == {"S1", "SF"}
    assert m["source"] == "Entur national GTFS" and m["licence"] == "NLOD 2.0"
    assert m["counts"]["trips"] == 5 and m["counts"]["stops_in_bbox"] == 5
    assert json.loads((tmp_path / "c" / "manifest.json").read_text())["bbox"] == list(BBOX)


def test_clip_zip_date_and_partial(tmp_path):
    z = shutil.make_archive(str(tmp_path / "gtfs"), "zip", FIX)
    m = gtfs.clip(z, BBOX, tmp_path / "d", date="2026-03-03")
    feed = gtfs.load(tmp_path / "d")
    assert "SP1" not in set(feed.trips["trip_id"]) and m["date"] == "2026-03-03"
    assert "SPECIAL" not in set(feed.calendar["service_id"])
    # whole_trips=False keeps only the in-bbox stop_times
    gtfs.clip(z, (7.05, 62.7, 7.17, 62.8), tmp_path / "p", whole_trips=False)
    p = gtfs.load(tmp_path / "p")
    assert set(p.stop_times["stop_id"]) <= {"A", "B"}


def test_trajectories_pass_contract(cfeed):
    traj, agents = gtfs.trajectories(cfeed, "2026-03-03", 7 * 3600, 11 * 3600, sample_s=30)
    rep = validate(traj, agents)
    assert rep.ok, str(rep)
    assert set(agents["agent_id"]) == {"T1", "T3", "F1"}
    a = agents.set_index("agent_id")
    assert a.loc["F1", "domain"] == "sea" and a.loc["F1", "cls"] == "ferry"
    assert a.loc["T1", "domain"] == "land" and a.loc["T1", "cls"] == "bus"
    assert a["capacity"].isna().all()
    assert not a.loc["T3", "has_shape"] and a.loc["T1", "has_shape"]
    f = traj[traj["agent_id"] == "F1"]
    assert set(f["state"]) == {"sail", "wait"} and not (traj["state"] == "idle").any()
    t1 = traj[traj["agent_id"] == "T1"]
    assert t1["t"].iloc[0] == 3600 and t1["t"].iloc[-1] == 3600 + 660           # t from t0
    assert t1.iloc[-1]["state"] == "wait"
    # speed within the 1.1x observed vmax, and well above zero
    assert 3 < a.loc["T1", "vmax_mps"] < 15


def test_dwell_rows_are_wait_and_positions_on_shape(cfeed):
    traj, _ = gtfs.trajectories(cfeed, "2026-03-03", 8 * 3600, 10 * 3600, sample_s=30)
    t1 = traj[traj["agent_id"] == "T1"].set_index("t")
    # B: arrival 08:05 (t=300) departure 08:06 (t=360): wait at 300 and 330, drive from 360
    assert t1.loc[300, "state"] == "wait" and t1.loc[330, "state"] == "wait" and t1.loc[360, "state"] == "drive"
    assert t1.loc[300, "lon"] == pytest.approx(7.15, abs=1e-6) == t1.loc[360, "lon"]
    # follows the (kinked) shape: halfway A->B in time is on the shape, not necessarily the straight chord
    assert 62.73 <= t1.loc[150, "lat"] <= 62.735
    # no-shape trip T3 is a straight line: lat linear in lon
    t3 = traj[traj["agent_id"] == "T3"]
    assert t3["lat"].iloc[1] == pytest.approx(62.73 + (t3["lon"].iloc[1] - 7.1) / 0.05 * 0.005, abs=1e-4)


def test_past_midnight_trip(cfeed):
    # Wednesday 00:00-02:00: previous-day T2 (23:50 -> 25:10) still running
    traj, agents = gtfs.trajectories(cfeed, WED, 0, 2 * 3600, sample_s=60)
    assert validate(traj, agents).ok
    assert list(agents["agent_id"]) == ["T2~prev"]
    g = traj[traj["agent_id"] == "T2~prev"]
    assert g["t"].min() == 0 and g["t"].max() == 4200
    # its own day: 23:30-26:00 window sees it with offset 0
    traj2, ag2 = gtfs.trajectories(cfeed, "2026-03-03", 23 * 3600 + 1800, 26 * 3600)
    assert "T2" in set(ag2["agent_id"]) and validate(traj2, ag2).ok


def test_headways_and_kpis(cfeed):
    h = gtfs.headways(cfeed, "2026-03-03", "A")
    assert list(h["trip_id"]) == ["T1", "T3", "T2"] and h["headway_s"].iloc[1] == 3600
    traj, agents = gtfs.trajectories(cfeed, "2026-03-03", 8 * 3600, 11 * 3600, sample_s=60)
    k = gtfs.kpis(traj, agents)
    assert k["trips"] == 3 and k["vehicle_km"] > 5
    assert k["peak_vehicles"] == 1                                              # trips do not overlap
    assert k["mean_headway_s"] == pytest.approx(((9 - 8) * 3600 + (10 - 9) * 3600) / 2)
    ins = gtfs.in_service(traj, 60)
    assert ins.max() == 1 and ins.min() == 0


def test_engine_gtfs(clipped):
    eng = get_engine("gtfs")
    assert eng.name == "gtfs" and eng.classes == {"TRANSIT-REPLAY"} and eng.needs_weather is False
    p = Problem(cls={"TRANSIT-REPLAY"}, nodes=[(7.1, 62.7)], dist_m=None, demand={}, fleet=[],
                extra={"gtfs": {"dir": str(clipped), "date": "2026-03-03", "t0": "07:00:00", "t1": "11:00:00",
                                "sample_s": 60}})
    res = eng.simulate(p, Plan(routes={}, objective=0.0), World(name="mini"))
    assert validate(res.traj, res.agents).ok
    assert res.engine == "gtfs" and res.weather is None
    for key in ("trips", "vehicle_km", "peak_vehicles", "mean_headway_s"):
        assert key in res.kpis
    assert res.kpis["trips"] == 3 and res.kpis["distance_km"] == pytest.approx(res.kpis["vehicle_km"], rel=1e-6)
    assert res.kpis["wait_s"] > 0
    assert set(res.events["event"]) == {"dwell"}
    # filter by class
    p.extra["gtfs"]["route_types"] = ["ferry"]
    assert get_engine("gtfs").simulate(p, Plan(routes={}, objective=0.0), World(name="mini")).kpis["trips"] == 1
    with pytest.raises(Unsupported):
        eng.simulate(p, Plan(routes={"BUS-1": [1]}, objective=0.0), World(name="mini"))
    with pytest.raises(Unsupported):
        eng.simulate(Problem(cls={"CVRP"}, nodes=[], dist_m=None, demand={}, fleet=[]), Plan({}, 0.0), World(name="m"))
