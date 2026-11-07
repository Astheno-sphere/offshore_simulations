"""offsim.traffic: synthetic AIS (two vessels, one with a 2 h stop at a 'base') -> port calls, calibration, gate 4b."""
import json

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("movingpandas")
pytest.importorskip("geopandas")

from offsim.traffic import ais, barentswatch  # noqa: E402

BASE = (5.30, 60.40)          # lon, lat
T0 = pd.Timestamp("2024-01-10T00:00:00Z")


def _vessel(mmsi, stop_min=None):
    """Sails 1 h east->base at ~12 kn, optionally sits at base for stop_min, sails 1 h away. 5-min fixes."""
    rows, t = [], T0
    dlon_per_min = 12 * 1852 / 60 / (111_320 * np.cos(np.radians(BASE[1])))     # degrees lon per minute at 12 kn
    lon = BASE[0] + dlon_per_min * 60
    for _ in range(12):                                                         # inbound
        rows.append((mmsi, t, lon, BASE[1], 12.0, 270.0, 70)); t += pd.Timedelta(minutes=5); lon -= dlon_per_min * 5
    if stop_min:
        for k in range(stop_min // 5 + 1):                                      # jittering at the quay
            rows.append((mmsi, t, BASE[0] + 0.0002 * (k % 2), BASE[1], 0.1, 0.0, 70)); t += pd.Timedelta(minutes=5)
    for i in range(12):                                                         # outbound
        lon = BASE[0] - dlon_per_min * 5 * (i + 1)
        rows.append((mmsi, t, lon, BASE[1], 12.0, 270.0, 70)); t += pd.Timedelta(minutes=5)
    return rows


@pytest.fixture(scope="module")
def raw():
    rows = _vessel(257111000, stop_min=120) + _vessel(257222000)               # second vessel just passes
    return pd.DataFrame(rows, columns=["MMSI", "msgtime", "Longitude", "Latitude", "SpeedOverGround", "CourseOverGround", "shiptype"])


@pytest.fixture(scope="module")
def tracks(raw):
    return ais.build_tracks(ais.load_ais(raw))


def test_column_normalisation_and_cleaning(raw):
    dirty = pd.concat([raw, raw.iloc[:3], pd.DataFrame([[1, "2024-01-10T00:00:00Z", 181.0, 91.0, 1023, 0, 70]], columns=raw.columns)])
    df = ais.load_ais(dirty)
    assert list(df.columns) == ["mmsi", "timestamp", "lon", "lat", "sog", "cog", "ship_type"]
    assert len(df) == len(raw) and df["mmsi"].dtype == "int64" and str(df["timestamp"].dt.tz) == "UTC"
    with pytest.raises(ValueError):
        ais.normalise_columns(pd.DataFrame({"a": [1]}))


def test_filter_by_area_and_type(raw):
    df = ais.load_ais(raw)
    assert len(ais.filter_ais(df, bbox=(5.0, 60.0, 5.31, 61.0))) < len(df)
    assert ais.filter_ais(df, ship_types=ais.PSV_TYPES).shape == df.shape
    assert ais.filter_ais(df, ship_types=[60]).empty and ais.filter_ais(df, mmsi=[257222000])["mmsi"].nunique() == 1


def test_split_on_gap():
    df = ais.load_ais(pd.DataFrame(_vessel(1) + [(1, T0 + pd.Timedelta(hours=10), 5.0, 60.4, 10, 0, 70),
                                                 (1, T0 + pd.Timedelta(hours=10, minutes=5), 5.0, 60.41, 10, 0, 70)],
                                   columns=["mmsi", "timestamp", "lon", "lat", "sog", "cog", "ship_type"]))
    assert len(ais.build_tracks(df).trajectories) == 2


def test_port_call_found_within_five_minutes(tracks):
    calls = ais.port_calls(tracks, {"base": (*BASE, 500)})
    assert list(calls.columns) == ["mmsi", "place", "arrive", "depart", "duration_s"]
    assert len(calls) == 1 and calls.iloc[0]["mmsi"] == 257111000 and calls.iloc[0]["place"] == "base"
    assert abs(calls.iloc[0]["duration_s"] - 7200) <= 300


def test_stop_outside_radius_is_not_a_call(tracks):
    assert ais.port_calls(tracks, {"elsewhere": (6.0, 61.0, 500)}).empty


def test_calibration_quantiles(tracks):
    calls = ais.port_calls(tracks, pd.DataFrame([{"name": "base", "lon": BASE[0], "lat": BASE[1], "radius_m": 500}]))
    cal = ais.calibration(calls, tracks, area="Bergen", dates="2024-01-10")
    assert cal["src"] == "AIS HAIS Bergen 2024-01-10, offsim.traffic"
    assert cal["port_call_s"]["base"]["n"] == 1 and abs(cal["port_call_s"]["base"]["p50"] - 7200) <= 300
    sp = cal["sailing_speed_kn"]
    assert sp["p10"] <= sp["p50"] <= sp["p90"] and abs(sp["p50"] - 12.0) < 0.5      # stopped fixes (0.1 kn) excluded
    assert cal["vessels"] == 1 and cal["port_calls"] == 1


def _sim(speed_kn, dwell_s):
    dlon = speed_kn * 1852 / (111_320 * np.cos(np.radians(BASE[1])))               # degrees per hour
    rows = [("psv", i * 600.0, BASE[0] + dlon * i / 6, BASE[1], "sail") for i in range(7)]
    return pd.DataFrame(rows, columns=["agent_id", "t", "lon", "lat", "state"]), {"base": [dwell_s]}


def test_compare_to_sim_pass_and_fail(tracks):
    calls = ais.port_calls(tracks, {"base": (*BASE, 500)})
    cal = ais.calibration(calls, tracks)
    good, dur = _sim(12.0, 7000)
    t = ais.compare_to_sim(good, cal, dur)
    assert set(t["metric"]) == {"sailing_speed_kn", "port_call_s"} and t["pass"].all()
    bad, dur_bad = _sim(18.0, 1800)
    t = ais.compare_to_sim(bad, cal, dur_bad)
    assert not t[t["metric"] == "sailing_speed_kn"]["pass"].any() and not t[t["metric"] == "port_call_s"]["pass"].any()
    assert ais.compare_to_sim(None, cal, None).empty


def test_process_hais_writes_calibration(tmp_path, raw):
    src = tmp_path / "hais.csv"
    raw.to_csv(src, index=False)
    cal = ais.process_hais(src, tmp_path / "out", bbox=(5.0, 60.0, 6.0, 61.0), places=[{"name": "base", "lon": BASE[0], "lat": BASE[1], "radius_m": 500}],
                           area="test")
    assert json.loads((tmp_path / "out/calibration.json").read_text())["src"] == cal["src"]
    assert cal["src"].startswith("AIS HAIS test 2024-01-10..2024-01-10") and (tmp_path / "out/port_calls.csv").exists()


def test_barentswatch_token_and_normalisation():
    calls = []

    def fake(url, headers=None, data=None):
        calls.append((url, headers, data))
        if "connect/token" in url:
            return json.dumps({"access_token": "tok", "expires_in": 3600}).encode()
        return json.dumps([{"mmsi": 257111000, "msgtime": "2024-01-10T00:00:00Z", "latitude": 60.4, "longitude": 5.3,
                            "speedOverGround": 11.5, "courseOverGround": 90, "shipType": 70}]).encode()

    bw = barentswatch.BarentsWatch("id", "secret", fetch=fake)
    recs = bw.latest()
    assert recs[0]["lon"] == 5.3 and recs[0]["sog"] == 11.5
    assert b"scope=ais" in calls[0][2] and b"grant_type=client_credentials" in calls[0][2]
    assert calls[1][1]["Authorization"] == "Bearer tok"
    bw.latest()
    assert sum("connect/token" in c[0] for c in calls) == 1                            # token cached
    assert len(ais.load_ais(pd.DataFrame(recs))) == 1
    with pytest.raises(RuntimeError):
        barentswatch.BarentsWatch("", "", fetch=fake)
    assert not barentswatch.credentials_available({}) and barentswatch.credentials_available({"BW_CLIENT_ID": "a", "BW_CLIENT_SECRET": "b"})
