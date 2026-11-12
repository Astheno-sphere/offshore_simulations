"""Raw NMEA AIS (pyais) -> offsim.traffic tables -> gate 4b, all against SYNTHETIC sentences. No network, no real AIS."""
import json
import socket

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("pyais")
from conftest import ROOT  # noqa: E402
from offsim.contract import MOVING, STATES, validate  # noqa: E402
from offsim.traffic import ais  # noqa: E402

FIX = ROOT / "tests" / "fixtures" / "ais" / "synthetic_nmea.txt"
PLACES = {"BASE": (5.30, 60.40, 1000.0)}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("AIS decode tests must not open a socket")
    monkeypatch.setattr(socket.socket, "connect", refuse)


@pytest.fixture(scope="module")
def res():
    return ais.decode_nmea(FIX)


def test_every_line_is_accounted_for(res):
    assert res.counts["lines"] == 64
    # 64 lines = 56 positions + 2 fragments of the one decoded static message + 6 rejected lines (the unavailable-position
    # line and the lone fragment are rejects; the lone fragment is one line)
    assert len(res.positions) + 2 * len(res.static) + len(res.rejects) == res.counts["lines"]
    assert res.counts["by_type"] == {1: 50, 2: 1, 3: 6, 5: 1, 18: 1}


def test_rejects_are_reported_with_reasons(res):
    reasons = dict(zip(res.rejects["line_no"], res.rejects["reason"]))
    assert len(reasons) == 6 == len(res.rejects)
    text = " ".join(reasons.values())
    for want in ("checksum", "not an AIS sentence", "position not available", "incomplete multipart", "no timestamp",
                 "unsupported type 18"):
        assert want in text
    assert list(res.rejects.columns) == ais.REJECT_COLUMNS and res.rejects["sentence"].str.len().min() > 0


def test_positions_match_what_was_encoded(res):
    p = res.positions
    assert list(p.columns) == ["mmsi", "timestamp", "lon", "lat", "sog", "cog", "ship_type"]
    assert set(p["mmsi"]) == {999000001, 999000002} and str(p["timestamp"].dt.tz) == "UTC"
    v1 = p[p["mmsi"] == 999000001].reset_index(drop=True)
    assert len(v1) == 49 and v1["timestamp"].iloc[0] == pd.Timestamp("2024-01-10T00:00:00Z")
    assert np.allclose(v1["lat"], 60.40, atol=2e-6)                        # AIS resolution is 1/600000 degree
    assert np.allclose(v1["sog"].iloc[:12], 12.0) and np.allclose(v1["cog"].iloc[:12], 270.0)
    assert (v1["sog"].iloc[12:37] < 0.2).all()                             # 2 h alongside
    assert abs(v1["lon"].iloc[12] - 5.30) < 0.001


def test_multipart_static_reassembled_across_an_interleaved_message(res):
    assert len(res.static) == 1
    s = res.static.iloc[0]
    assert (s["mmsi"], s["shipname"], s["callsign"], s["ship_type"], s["imo"]) == (999000001, "TESTVESSEL ONE", "TST1", 70, 9999999)
    assert s["draught"] == 6.5 and s["destination"] == "BASE"
    p = res.positions
    assert (p.loc[p["mmsi"] == 999000001, "ship_type"] == 70).all()       # static type propagated to positions
    assert p.loc[p["mmsi"] == 999000002, "ship_type"].isna().all()         # no type 5 seen for this one


def test_multipart_out_of_order_and_bare_lines_need_a_time():
    lines = [l for l in FIX.read_text().splitlines() if "AIVDM,2," in l][:2]      # the complete pair, not the lone fragment
    assert len(lines) == 2
    swapped = ais.decode_nmea(lines[::-1])
    assert len(swapped.static) == 1 and swapped.static.iloc[0]["shipname"] == "TESTVESSEL ONE"
    bare = [l.split(" ", 1)[1] for l in lines]
    assert len(ais.decode_nmea(bare).rejects) == 2 and ais.decode_nmea(bare).static.empty
    ok = ais.decode_nmea(bare, default_time="2024-01-10T00:00:00Z")
    assert len(ok.static) == 1 and ok.rejects.empty


def test_checksum_helper():
    good = "!AIVDM,1,1,,A,1>pf7h@01fPHCbPRSrP:S8L:0000,0*2A"
    assert ais.nmea_checksum_ok(good) and not ais.nmea_checksum_ok(good[:-2] + "00")
    assert not ais.nmea_checksum_ok("garbage") and not ais.nmea_checksum_ok("!AIVDM,1,1*ZZ")


def test_empty_and_all_bad_input_is_reported_not_raised():
    r = ais.decode_nmea(["", "   "])
    assert r.positions.empty and r.rejects.empty and r.counts["lines"] == 0
    r = ais.decode_nmea(["1704844800 hello"])
    assert r.positions.empty and len(r.rejects) == 1


def test_trajectory_has_the_contract_columns_and_passes_validate(res):
    traj = ais.to_trajectory(res.positions, anonymise=True)
    assert {"agent_id", "t", "lon", "lat", "state"} <= set(traj.columns) and set(traj["state"]) <= set(STATES)
    assert sorted(traj["agent_id"].unique()) == ["V01", "V02"] and traj["t"].min() == 0.0
    assert set(ais.to_trajectory(res.positions)["agent_id"]) == {"999000001", "999000002"}
    v1 = traj[traj["agent_id"] == "V01"]
    assert (v1["state"] == "idle").sum() >= 24 and (v1["state"].isin(MOVING)).sum() >= 24
    # a stopped real vessel is not a teleporting simulated one: the contract's own validator accepts the decoded track
    agents = pd.DataFrame({"agent_id": ["V01"], "cls": "psv", "speed_mps": 8.0, "vmax_mps": 12 * ais.KN_TO_MPS * 1.2,
                           "capacity": 1, "domain": "sea"})
    rep = validate(v1[["agent_id", "t", "lon", "lat", "state"]].reset_index(drop=True), agents)
    assert rep.ok, rep.violations


def _sim(speed_kn, dwell_s, t_in=3600.0):
    """Simulated vessel: sail in at speed_kn, dwell at BASE, sail out. Contract rows."""
    dlon = speed_kn * ais.KN_TO_MPS / (111_320 * np.cos(np.radians(60.40)))
    rows, t = [], 0.0
    for k in range(13):
        rows.append(("S", t, 5.30 + dlon * (t_in - k * t_in / 12), 60.40, "sail")); t += t_in / 12
    rows[-1] = ("S", rows[-1][1], 5.30, 60.40, "load")
    rows.append(("S", rows[-1][1] + dwell_s, 5.30, 60.40, "sail"))
    t = rows[-1][1]
    for k in range(1, 13):
        t += t_in / 12
        rows.append(("S", t, 5.30 - dlon * k * t_in / 12, 60.40, "sail"))
    return pd.DataFrame(rows, columns=["agent_id", "t", "lon", "lat", "state"])


def test_gate_4b_against_a_decoded_track(res):
    table, calib = ais.compare_decoded(_sim(12.0, 7200.0), res.positions, PLACES, {"BASE": [7200.0]}, mmsi=[999000001])
    assert calib["port_calls"] == 1 and abs(calib["port_call_all_s"]["p50"] - 7500) < 600      # 2 h + the stop detector's edges
    assert set(table["metric"]) == {"sailing_speed_kn", "port_call_s"} and table["pass"].astype(bool).all()
    assert table["n_ais"].min() >= 1


def test_gate_4b_fails_a_wrong_simulation(res):
    slow, _ = ais.compare_decoded(_sim(6.0, 7200.0), res.positions, PLACES, mmsi=[999000001])
    assert not slow["pass"].dropna().astype(bool).all() and (slow["delta"] < 0).all()
    short, _ = ais.compare_decoded(_sim(12.0, 1800.0), res.positions, PLACES, {"BASE": [1800.0]}, mmsi=[999000001])
    assert not short.loc[short["metric"] == "port_call_s", "pass"].astype(bool).any()
    assert short.loc[short["metric"] == "sailing_speed_kn", "pass"].astype(bool).all()


def test_gate_4b_window_and_tolerance_are_explicit(res):
    # a window that cuts the stop out leaves no AIS port call: not judged (NaN), never a silent pass
    w = ("2024-01-10T00:00:00Z", "2024-01-10T00:55:00Z")
    table, calib = ais.compare_decoded(_sim(12.0, 7200.0), res.positions, PLACES, {"BASE": [7200.0]}, window=w, mmsi=[999000001])
    assert calib["port_calls"] == 0 and "port_call_s" not in set(table["metric"])
    with pytest.raises(ValueError):
        ais.compare_decoded(_sim(12.0, 7200.0), res.positions, PLACES, window=("2030-01-01", "2030-01-02"))
    assert ais.GATE_4B_TOLERANCE["assumption"] is True
    tight, _ = ais.compare_decoded(_sim(12.5, 7200.0), res.positions, PLACES, mmsi=[999000001], tolerance={"tol_rel": 0.0, "tol_abs_kn": 0.1})
    assert not tight["pass"].dropna().astype(bool).all()


def test_process_nmea_writes_calibration_and_the_reject_file(tmp_path):
    calib = ais.process_nmea(FIX, tmp_path, places=PLACES, area="synthetic", dates="2024-01-10")
    assert calib["port_calls"] == 1 and (tmp_path / "calibration.json").exists()
    assert json.loads((tmp_path / "calibration.json").read_text())["src"].startswith("AIS HAIS synthetic")
    assert len(pd.read_csv(tmp_path / "ais_rejects.csv")) == 6


def test_existing_entry_points_still_take_the_decoded_table(res):
    df = ais.load_ais(res.positions)
    assert len(df) == len(res.positions)
    tracks = ais.build_tracks(df)
    assert len(tracks.trajectories) >= 2
