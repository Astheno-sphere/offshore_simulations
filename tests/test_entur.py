"""Entur realtime client and observed-transit validation (gate 4c), offline with hand-written fixtures."""
from __future__ import annotations

import json
import urllib.error
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from offsim.contract import validate
from offsim.transit import entur, observed

FIX = Path(__file__).parent / "fixtures" / "entur"
BBOX = (7.0, 62.6, 7.5, 62.9)
T0 = "2026-11-08T08:00:00Z"


def fx(name):
    return (FIX / name).read_bytes()


class FakePost:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def __call__(self, url, body, headers):
        self.calls.append((url, json.loads(body), headers))
        r = self.responses[min(len(self.calls) - 1, len(self.responses) - 1)]
        if isinstance(r, Exception):
            raise r
        return r


def test_client_headers_default_and_env():
    assert entur.client_headers({})["ET-Client-Name"] == "astheno-offshoresimulations"
    assert entur.client_headers({"ENTUR_CLIENT_NAME": ""})["ET-Client-Name"] == "astheno-offshoresimulations"
    assert entur.client_headers({"ENTUR_CLIENT_NAME": "acme-app"})["ET-Client-Name"] == "acme-app"


def test_header_sent_and_bbox_variables():
    post = FakePost(fx("vehicles_1.json"))
    entur.vehicles(BBOX, post=post)
    url, body, headers = post.calls[0]
    assert url == entur.VEHICLES_URL
    assert headers["ET-Client-Name"]
    assert body["variables"] == {"minLat": 62.6, "minLon": 7.0, "maxLat": 62.9, "maxLon": 7.5}
    assert "codespace" not in body["variables"]
    entur.vehicles(BBOX, codespace="MOR", post=post)
    assert post.calls[1][1]["variables"]["codespace"] == "MOR" and "codespaceId" in post.calls[1][1]["query"]


def test_429_retry_honours_retry_after():
    post = FakePost(entur.RateLimited(7), urllib.error.HTTPError("u", 429, "Too Many", {"Retry-After": "3"}, None),
                    fx("vehicles_1.json"))
    slept = []
    df = entur.vehicles(BBOX, post=post, sleep=slept.append)
    assert len(post.calls) == 3 and slept == [7, 3] and len(df) == 2


def test_429_gives_up_and_backs_off_without_header():
    post = FakePost(entur.RateLimited(None))
    slept = []
    with pytest.raises(entur.RateLimited):
        entur.graphql(entur.VEHICLES_URL, "q", {}, post, retries=2, sleep=slept.append)
    assert len(post.calls) == 3 and slept == [2.0, 4.0]


def test_graphql_errors_raise():
    with pytest.raises(entur.EnturError):
        entur.graphql(entur.VEHICLES_URL, "q", {}, FakePost(b'{"errors": [{"message": "bad field"}]}'))


def test_parse_vehicles():
    df = entur.vehicles(BBOX, post=FakePost(fx("vehicles_1.json")))
    assert list(df.columns) == entur.COLUMNS
    assert len(df) == 2                                   # the vehicle without a location is dropped
    a = df.set_index("vehicle_id").loc["MOR:Vehicle:101"]
    assert a["service_journey_id"] == "MOR:ServiceJourney:1-0800" and a["line_ref"] == "MOR:Line:1"
    assert (a["lon"], a["lat"], a["delay_s"], a["speed_mps"]) == (7.1, 62.7, 60.0, 8.0)
    assert str(df["t_utc"].dt.tz) == "UTC" and df["t_utc"].iloc[0] == pd.Timestamp(T0)
    assert df.set_index("vehicle_id").loc["MOR:Vehicle:102", "delay_s"] == 90.0     # ISO-8601 duration


def test_unknown_shape_gives_empty_frame():
    df = entur.vehicles(BBOX, post=FakePost(b'{"data": {"vehicles": null}}'))
    assert df.empty and list(df.columns) == entur.COLUMNS


def test_collect_dedupes_over_two_polls_and_reruns(tmp_path):
    out = tmp_path / "w" / "entur" / "vehicles.csv"
    slept = []
    post = FakePost(fx("vehicles_1.json"), fx("vehicles_2.json"))
    n = entur.collect(BBOX, minutes=0.5, every_s=30, out_csv=out, post=post, sleep=slept.append)
    assert len(post.calls) == 2 and slept == [30.0]
    assert n == 3                                         # 2 + (101 new, 102 repeated)
    df = entur.read_csv(out)
    assert len(df) == 3 and not df.duplicated(["vehicle_id", "t_utc"]).any()
    # a second run over the same data appends nothing, and the header is not repeated
    n2 = entur.collect(BBOX, minutes=0.5, every_s=30, out_csv=out, post=FakePost(fx("vehicles_2.json")), sleep=slept.append)
    assert n2 == 0 and len(entur.read_csv(out)) == 3


def test_collect_skips_a_failed_poll_and_clamps_rate(tmp_path):
    out = tmp_path / "v.csv"
    slept = []
    post = FakePost(fx("vehicles_1.json"), RuntimeError("boom"), fx("vehicles_2.json"))
    n = entur.collect(BBOX, minutes=0.1, every_s=0.1, out_csv=out, post=post, sleep=slept.append)
    assert slept and all(s >= entur.MIN_EVERY_S for s in slept) and n == 3


def test_departures():
    js = {"data": {"stopPlace": {"id": "NSR:StopPlace:1", "name": "Molde", "estimatedCalls": [
        {"realtime": True, "aimedDepartureTime": "2026-11-08T08:00:00+01:00", "expectedDepartureTime": "2026-11-08T08:02:00+01:00",
         "destinationDisplay": {"frontText": "Kristiansund"}, "serviceJourney": {"id": "SJ1", "line": {"publicCode": "1"}}}]}}}
    post = FakePost(json.dumps(js).encode())
    df = entur.departures("NSR:StopPlace:1", 5, post=post)
    assert post.calls[0][0] == entur.JOURNEY_PLANNER_URL and post.calls[0][1]["variables"] == {"id": "NSR:StopPlace:1", "n": 5}
    assert df["delay_s"].iloc[0] == 120 and df["destination"].iloc[0] == "Kristiansund"


# --- observed trajectories and gate 4c -----------------------------------------------------------------------

def vehicles_from_fixtures():
    return pd.concat([entur.vehicles(BBOX, post=FakePost(fx(f))) for f in ("vehicles_1.json", "vehicles_2.json")],
                     ignore_index=True)


def test_observed_trajectories_pass_contract():
    tr, ag = observed.observed_trajectories(vehicles_from_fixtures(), T0)
    rep = validate(tr, ag)
    assert rep.ok, str(rep)
    assert set(ag["agent_id"]) == {"MOR:ServiceJourney:1-0800", "MOR:ServiceJourney:2-0755"}
    assert (ag["cls"] == "bus").all() and (ag["domain"] == "land").all()
    a = tr[tr["agent_id"] == "MOR:ServiceJourney:1-0800"]
    assert list(a["t"]) == [0.0, 30.0] and list(a["state"]) == ["drive", "drive"]
    b = tr[tr["agent_id"] == "MOR:ServiceJourney:2-0755"]
    assert len(b) == 1 and b["state"].iloc[0] == "wait"


def test_observed_drops_rows_before_t0_and_splits_shared_journeys():
    v = vehicles_from_fixtures()
    tr, _ = observed.observed_trajectories(v, "2026-11-08T08:00:10Z")
    assert tr["t"].min() >= 0 and len(tr) == 1
    v2 = pd.concat([v, v.assign(vehicle_id="MOR:Vehicle:999")], ignore_index=True)
    tr2, ag2 = observed.observed_trajectories(v2, T0)
    assert validate(tr2, ag2).ok and len(ag2) == 4


LON0, LAT = 7.0, 62.7
LON_STEP = 0.01         # ~510 m at 62.7 N


def sched(sj="SJ1", n=11, dt=60.0):
    t = np.arange(n) * dt
    return pd.DataFrame({"agent_id": sj, "t": t, "lon": LON0 + LON_STEP * np.arange(n), "lat": LAT, "alt_m": 0.0,
                         "state": "drive"})


def trip(sj="SJ1", delay=0.0, stretch=1.0, n=11, dt=60.0, drop_every=1):
    s = sched(sj, n, dt)
    s = s.iloc[::drop_every].copy()
    s["t"] = s["t"] * stretch + delay
    return s


def test_compare_to_schedule_delayed_trip():
    cmp = observed.compare_to_schedule(sched(), trip(delay=120.0))
    r = cmp.iloc[0]
    assert r["service_journey_id"] == "SJ1" and r["n_points"] == 11 and r["n_used"] == 11
    assert r["delay_p10"] == pytest.approx(120, abs=1) and r["delay_p50"] == pytest.approx(120, abs=1)
    assert r["tt_ratio"] == pytest.approx(1.0, abs=0.01) and r["coverage"] == pytest.approx(1.0, abs=0.01)


def test_compare_to_schedule_slow_trip_and_unmatched():
    cmp = observed.compare_to_schedule(sched(), pd.concat([trip(stretch=1.5), trip("OTHER")]))
    by = cmp.set_index("service_journey_id")
    assert by.loc["SJ1", "tt_ratio"] == pytest.approx(1.5, abs=0.01)
    assert by.loc["SJ1", "delay_p50"] == pytest.approx(150, abs=2)      # 30 s late per stop, median at stop 5
    assert by.loc["OTHER", "n_used"] == 0 and np.isnan(by.loc["OTHER", "delay_p50"])


def test_compare_drops_off_route_points_and_strips_prev_suffix():
    o = trip(delay=30.0)
    o.loc[o.index[3], "lat"] += 0.05                      # ~5.5 km off the line
    cmp = observed.compare_to_schedule(sched("SJ1~prev"), o)
    r = cmp.iloc[0]
    assert r["n_points"] == 11 and r["n_used"] == 10 and r["max_offroute_m"] > 5000
    assert observed.compare_to_schedule(sched("SJ1~prev"), o, match="agent_id").iloc[0]["n_used"] == 0


def test_gate_4c_pass_and_fail():
    ok = observed.gate_4c(observed.compare_to_schedule(sched(), trip(delay=120.0)))
    assert ok["pass"] and ok["detail"]["n_judged"] == 1
    assert ok["detail"]["tolerances"]["max_tt_ratio"]["assumption"] is True
    late = observed.gate_4c(observed.compare_to_schedule(sched(), trip(delay=400.0)))
    assert not late["pass"] and "delay" in late["detail"]["reason"]
    slow = observed.gate_4c(observed.compare_to_schedule(sched(), trip(stretch=1.6)), max_median_delay_s=1e9)
    assert not slow["pass"] and "travel-time" in slow["detail"]["reason"]
    assert observed.gate_4c(observed.compare_to_schedule(sched(), trip(delay=400.0)), max_median_delay_s=500.0)["pass"]


def test_gate_4c_nothing_judged_fails():
    res = observed.gate_4c(observed.compare_to_schedule(sched(), trip("OTHER")))
    assert not res["pass"] and res["detail"]["n_judged"] == 0
    assert not observed.gate_4c(pd.DataFrame(columns=observed._COLS))["pass"]


def test_end_to_end_vehicles_to_gate():
    n = 11
    rows = [{"vehicle_id": "V1", "line_ref": "L", "service_journey_id": "SJ1",
             "t_utc": pd.Timestamp(T0) + pd.Timedelta(seconds=60 * i + 90), "lon": LON0 + LON_STEP * i, "lat": LAT,
             "delay_s": 90.0, "bearing": 90.0, "speed_mps": 8.5} for i in range(n)]
    tr, ag = observed.observed_trajectories(pd.DataFrame(rows), T0)
    assert validate(tr, ag).ok
    res = observed.gate_4c(observed.compare_to_schedule(sched(), tr))
    assert res["pass"] and res["detail"]["median_abs_delay_s"] == pytest.approx(90, abs=1)
