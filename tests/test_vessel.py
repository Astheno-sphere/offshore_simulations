"""Cosmetic vessel motion: display-only, 25 m corridor, same schedule, rate-limited heading, seeded."""
import json
import shutil
import subprocess

import numpy as np
import pandas as pd
import pytest

from conftest import ROOT
from offsim.cinema import vessel as V
from offsim.cinema.rules import HELICOPTER, VESSEL
from offsim.contract import EARTH_R, haversine_m
from offsim.examples.toy_fjord import run
from offsim.sim.replay import replay

KN = 0.514444
VMAX = 12 * KN


@pytest.fixture(scope="module")
def toy(tmp_path_factory):
    results, _, _ = run(tmp_path_factory.mktemp("toy"))
    traj = results["optimised"][0]
    agents = pd.DataFrame({"agent_id": ["PSV-A", "PSV-B"], "cls": "psv", "vmax_mps": VMAX, "domain": "sea"})
    return traj, agents


@pytest.fixture(scope="module")
def cornered():
    """One vessel sailing a lane with a 70 deg and a 20 deg corner, a 15 min stop, then back (sharp 90 deg-ish legs)."""
    nodes = [(10.60, 59.10), (10.60, 59.20), (10.66, 59.25), (10.66, 59.32)]
    legs = {(0, 1): [nodes[0], (10.60, 59.15), (10.64, 59.18), nodes[1]], (1, 2): [nodes[1], (10.63, 59.22), nodes[2]]}
    agents = pd.DataFrame({"agent_id": ["V"], "cls": "psv", "speed_mps": VMAX, "vmax_mps": VMAX, "capacity": 10, "domain": "sea"})
    traj, _ = replay(nodes, {"V": [1, 2, 3]}, agents, service_s={1: 900, 2: 600, 3: 300}, legs=legs, demand={1: 1, 2: 1, 3: 1})
    return traj, agents


def unwrap_rate_deg_s(ts, heading):
    h = np.degrees(np.unwrap(np.radians(heading)))
    return np.abs(np.diff(h)) / np.diff(ts)


def arrays(d, aid):
    a = d[aid]
    return (np.array(a["ts"]), np.array([p[0] for p in a["path"]]), np.array([p[1] for p in a["path"]]),
            np.array(a["heading"]), list(a["states"]))


def test_arrival_times_and_stop_positions_unchanged(toy, cornered):
    for traj, agents in (toy, cornered):
        d = V.display_agents(traj, agents, seed=3)
        for aid, g in traj.groupby("agent_id"):
            ts, lon, lat, _, _ = arrays(d, aid)
            gt = g.drop_duplicates("t", keep="last")
            assert set(gt["t"]) <= set(ts)                              # every validated timestamp is a display timestamp
            gl, ga = gt["lon"].to_numpy(), gt["lat"].to_numpy()
            still = haversine_m(gl[:-1], ga[:-1], gl[1:], ga[1:]) < 0.05
            stop = np.r_[True, still] | np.r_[still, True]                # rows that begin or end a dwell, plus both ends
            stop[[0, -1]] = True
            i = np.searchsorted(ts, gt["t"].to_numpy()[stop])
            err = haversine_m(lon[i], lat[i], gl[stop], ga[stop])
            assert stop.sum() > 4 and err.max() < 0.05                   # arrivals/departures happen at the same time and place
            assert ts[0] == g["t"].iloc[0] and ts[-1] == g["t"].iloc[-1]
        assert d["max_offset_m"] > 0.5                                   # and the copy is not just the validated track


def test_heading_turn_rate_within_limits(toy, cornered):
    for traj, agents in (toy, cornered):
        d = V.display_agents(traj, agents, seed=0)
        for aid in traj["agent_id"].unique():
            ts, lon, lat, hd, st = arrays(d, aid)
            rate = unwrap_rate_deg_s(ts, hd) * 60                         # deg/min
            x, y = lon * np.cos(np.radians(lat[0])) * 111_195, lat * 111_195
            speed = np.hypot(np.diff(x), np.diff(y)) / np.diff(ts)
            quiet = np.array([s not in V.JITTER_STATES and s2 not in V.JITTER_STATES for s, s2 in zip(st[:-1], st[1:])])
            assert (rate[quiet] <= VESSEL["psv_rot_manoeuvre_deg_min"] + 1e-6).all()
            assert (rate[quiet & (speed >= V.MANOEUVRE_SPEED_MPS)] <= VESSEL["psv_rot_service_deg_min"] + 1e-6).all()


def test_heading_smooth_service_rate_and_fillets(cornered):
    traj, _ = cornered
    df = V.heading_smooth(traj, rot_max_deg_min=20.0)
    ts, hd = df["t"].to_numpy(), df["heading"].to_numpy()
    assert (unwrap_rate_deg_s(ts, hd) * 60 <= 20.0 + 1e-6).all()
    assert set(traj["t"]) <= set(ts)
    assert V.display_offset_check(traj, df) <= V.FILLET_BUDGET_M + 0.05
    raw = traj.drop_duplicates("t", keep="last")                         # corners really are cut (arc differs from the vertex)
    assert V.display_offset_check(traj, df) > 1.0 and len(df) > len(raw)


def test_speed_profile_ramps_and_budget(toy):
    traj, _ = toy
    df = V.speed_profile(traj, quay_ramp_m=400.0, depart_ramp_s=20.0)
    assert V.display_offset_check(traj, df) <= V.RAMP_BUDGET_M + 0.05     # ramps are limited by the offset budget
    g, h = traj[traj.agent_id == "PSV-A"], df[df.agent_id == "PSV-A"]
    assert set(g["t"]) <= set(h["t"])
    # the display actually slows into the first stop: speed in the last 2 s before arrival is below half of cruise
    arr = g[g.state == "unload"]["t"].iloc[0]
    near = h[(h.t >= arr - 2.0) & (h.t <= arr)]
    sp = haversine_m(near.lon.iloc[0], near.lat.iloc[0], near.lon.iloc[-1], near.lat.iloc[-1]) / (near.t.iloc[-1] - near.t.iloc[0])
    assert sp < 0.5 * VMAX


def test_max_offset_within_25m_on_toy_and_cornered(toy, cornered):
    for traj, agents in (toy, cornered):
        d = V.display_agents(traj, agents, seed=1)
        assert d["max_offset_m"] <= VESSEL["display_offset_max_m"]
        assert d["max_offset_m"] == pytest.approx(V.display_offset_check(traj, d))


def test_display_never_edits_validated_trajectory(toy):
    traj, agents = toy
    before = traj.copy(deep=True)
    V.display_agents(traj, agents)
    pd.testing.assert_frame_equal(traj, before)


def test_same_seed_identical_different_seed_differs(toy):
    traj, agents = toy
    a, b, c = (V.display_agents(traj, agents, seed=s) for s in (5, 5, 6))
    assert json.dumps(a) == json.dumps(b)
    assert json.dumps(a) != json.dumps(c)
    assert V.dp_jitter(1, 12.5) == V.dp_jitter(1, 12.5) and V.dp_jitter(1, 12.5) != V.dp_jitter(2, 12.5)
    assert V.bob(1.0, 7.0, 3.3, 4) == V.bob(1.0, 7.0, 3.3, 4)


def test_display_shape(toy):
    traj, agents = toy
    d = V.display_agents(traj, agents, seed=0, hs_at=lambda lon, lat, t: (2.0, 8.0))
    assert set(d) == {"PSV-A", "PSV-B", "max_offset_m"}
    a = d["PSV-A"]
    assert set(a) == {"path", "ts", "states", "heading", "roll", "pitch", "heave"}
    n = len(a["ts"])
    assert all(len(a[k]) == n for k in a) and all(len(p) == 3 for p in a["path"])
    assert np.diff(a["ts"]).max() <= 2.0 + 1e-9                          # ~2 s sampling alongside and along arcs
    assert 0 <= min(a["heading"]) and max(a["heading"]) < 360
    assert max(map(abs, a["roll"])) <= 2.4 + 1e-6 and max(map(abs, a["pitch"])) <= 1.2 + 1e-6 and max(map(abs, a["heave"])) <= 0.5 + 1e-6
    json.dumps(d)


def test_dp_jitter_only_while_stationary_service(toy):
    traj, agents = toy
    d = V.display_agents(traj, agents)
    ts, lon, lat, _, st = arrays(d, "PSV-A")
    g = traj[traj.agent_id == "PSV-A"].drop_duplicates("t", keep="last")
    pos = np.column_stack([np.interp(ts, g.t, g.lon), np.interp(ts, g.t, g.lat)])
    off = haversine_m(pos[:, 0], pos[:, 1], lon, lat)
    mid = [i for i, s in enumerate(st) if s == "unload"]
    assert off[mid].max() > 0.5 and off[mid].max() < 6.0                 # jitter exists, peak a few metres
    wait = [i for i, s in enumerate(st) if s == "idle"]
    assert off[wait].max() < 1e-6                                        # none while idle


def test_dp_jitter_and_bob_statistics():
    t = np.arange(0, 4000, 0.5)
    dx, dy, dh = V.dp_jitter(3, t)
    assert np.sqrt(np.mean(dx ** 2 + dy ** 2)) == pytest.approx(1.5, rel=0.35)
    assert np.sqrt(np.mean(dh ** 2)) == pytest.approx(0.5, rel=0.35)
    per, _ = V._jitter_params(3)
    assert per.min() >= 7.0 and per.max() <= 40.0
    hv, rl, pt = V.bob(1.0, 7.0, t, 3)
    assert abs(hv).max() <= 0.25 + 1e-9 and abs(rl).max() <= 1.2 + 1e-9 and abs(pt).max() <= 0.6 + 1e-9
    hv, rl, pt = V.bob(9.0, 7.0, t, 3)
    assert abs(rl).max() <= 6.0 + 1e-9 and abs(pt).max() <= 3.0 + 1e-9    # roll/pitch capped
    assert not V.bob(0.0, 7.0, 3.0, 1) == (1, 1, 1) and V.bob(0.0, 7.0, 3.0, 1) == (0.0, 0.0, 0.0)


def test_display_track_passes_display_speed_check(toy, cornered):
    """Display-specific speed check (vmax*1.15). The validated contract check is never weakened or touched."""
    for traj, agents in (toy, cornered):
        d = V.display_agents(traj, agents)
        for aid in traj["agent_id"].unique():
            ts, lon, lat, _, _ = arrays(d, aid)
            v = haversine_m(lon[:-1], lat[:-1], lon[1:], lat[1:]) / np.diff(ts)
            assert v.max() <= VMAX * 1.15, (aid, v.max())


def test_wake_kelvin_angle_length_alpha():
    lat0, lon_end = 59.0, 10.6
    c = np.cos(np.radians(lat0))
    track = [[lon_end - k * 20.0 / (EARTH_R * c) * 180 / np.pi, lat0] for k in range(60, -1, -1)]    # 1200 m eastwards
    segs = V.wake(track, 0.0, 6.0, 76.0)
    assert {s["kind"] for s in segs} == {"arm_l", "arm_r", "trail"}
    for kind, sign in (("arm_l", 1), ("arm_r", -1)):
        arm = [s for s in segs if s["kind"] == kind]
        end = arm[-1]["path"][1]
        dx = (end[0] - lon_end) * np.pi / 180 * EARTH_R * c
        dy = (end[1] - lat0) * np.pi / 180 * EARTH_R
        assert np.degrees(np.arctan2(abs(dy), abs(dx))) == pytest.approx(VESSEL["kelvin_half_angle_deg"], abs=0.05)
        assert dy * sign > 0                                              # one arm each side
        assert np.hypot(dx, dy) * np.cos(np.radians(19.47)) == pytest.approx(10 * 76.0, rel=1e-3)   # 10 ship lengths behind
        al = [s["alpha"] for s in arm]
        assert all(a >= b for a, b in zip(al, al[1:])) and al[-1] < al[0]  # fades
    assert V.wake(track, 0.0, 0.0, 76.0) == []
    a_fast = max(s["alpha"] for s in V.wake(track, 6.0, 6.0, 76.0))
    a_slow = max(s["alpha"] for s in V.wake(track, 0.0, 3.0, 76.0))
    assert a_fast == pytest.approx(2 * a_slow)                            # alpha proportional to speed
    lo = V.wake(track, 0.0, 6.0, 76.0, wake_len_lengths=1.0)
    assert len(lo) == len(segs)                                           # length clamped to 8-12 ship lengths


def test_heli_phases_monotonic_climb_descent_and_30s_hover():
    route = {"path": [(10.0, 59.0), (10.5, 59.2), (11.0, 59.3)], "deck_alt_m": 25.0}
    tl = V.heli_timeline(route)
    names = [p[0] for p in tl]
    assert names == [p["name"] for p in V.HELI_PHASES]
    ph = {p[0]: p for p in tl}
    assert ph["hover"][2] - ph["hover"][1] == pytest.approx(HELICOPTER["deck_hover_s"])
    t_end = tl[-1][2]
    ts = np.arange(0, t_end + 60, 1.0)
    prof = np.array([V.heli_profile(route, t) for t in ts])
    alt = prof[:, 2]
    up = ts <= ph["climb"][2]
    assert (np.diff(alt[up]) > 0).all()                                   # climb strictly monotonic
    mx = int(np.argmax(alt))
    assert (np.diff(alt[mx:]) <= 1e-9).all()                              # then never climbs again
    desc = (ts >= ph["descent"][1]) & (ts <= ph["flare"][2])
    assert (np.diff(alt[desc]) < 0).all()
    vz = np.diff(alt)
    assert HELICOPTER["climb_mps"][0] <= vz[up[:-1]].max() <= HELICOPTER["climb_mps"][1]
    assert -HELICOPTER["descent_mps"][1] <= vz[(ts[:-1] >= ph["descent"][1]) & (ts[:-1] < ph["flare"][2] - 1)].min()
    cruise_v = haversine_m(prof[:, 0][:-1], prof[:, 1][:-1], prof[:, 0][1:], prof[:, 1][1:])
    mid = int((ph["cruise"][1] + ph["cruise"][2]) / 2)
    assert cruise_v[mid] == pytest.approx(HELICOPTER["cruise_kn"] * KN, rel=0.02)
    hov = (ts >= ph["hover"][1]) & (ts <= ph["hover"][2])
    assert hov.sum() >= 30 and np.ptp(alt[hov]) == 0 and np.ptp(prof[hov][:, 0]) == 0 and alt[hov][0] == 25.0   # still on deck
    assert V.heli_profile(route, -50.0)[2] == 25.0 and V.heli_profile(route, t_end + 999)[2] == 25.0
    d_flare = haversine_m(*V.heli_profile(route, ph["flare"][1])[:2], *V.heli_profile(route, ph["hover"][1])[:2])
    assert d_flare == pytest.approx(HELICOPTER["flare_m"], abs=1.0)


def test_non_sea_agents_keep_validated_positions():
    traj = pd.DataFrame({"agent_id": "H", "t": [0.0, 100.0, 200.0], "lon": [10.0, 10.1, 10.1], "lat": [59.0, 59.0, 59.0],
                         "alt_m": [0.0, 300.0, 0.0], "state": ["fly", "fly", "idle"], "load": 0.0})
    agents = pd.DataFrame({"agent_id": ["H"], "cls": "helicopter", "vmax_mps": 80.0, "domain": "air"})
    d = V.display_agents(traj, agents)
    assert d["max_offset_m"] < 1e-6 and d["H"]["ts"] == [0.0, 100.0, 200.0] and [p[2] for p in d["H"]["path"]] == [0.0, 300.0, 0.0]
    assert set(d["H"]["roll"]) == {0.0} and d["H"]["heading"][0] == pytest.approx(90.0, abs=0.1)


node = shutil.which("node")


@pytest.mark.skipif(not node or not (ROOT / "offsim/render_deck/node_modules/@deck.gl").exists(), reason="needs node + renderer deps")
def test_js_display_pose_and_wake(toy):
    traj, agents = toy
    d = V.display_agents(traj, agents, seed=2)
    full = d["PSV-A"]
    i0 = int(np.searchsorted(full["ts"], 9000.5)) - 5                    # a short window keeps the payload small
    a = {"id": "PSV-A", "cls": "psv", "accent": False, **{k: v[i0:i0 + 40] for k, v in full.items()}}
    seam = {"id": "s", "ts": [0, 10], "path": [[10, 59, 0], [10.001, 59, 0]], "states": ["sail", "sail"], "heading": [350, 10],
            "roll": [0, 2], "pitch": [0, 1], "heave": [0, 0.2]}
    code = f"""
import {{displayPose, wakeSegments, wakeLayers}} from 'file://{(ROOT / "offsim/render_deck/src/layers/vessel.js").as_posix()}';
const a = {json.dumps(a)}, seam = {json.dumps(seam)};
const t = 9000.5;
const p1 = displayPose(a, t), p2 = displayPose(a, t);
const s = displayPose(seam, 5);
const hist = []; for (let k = 20; k >= 0; k--) hist.push([10.6 - k * 0.0003, 59.0]);
const w = wakeSegments(hist, 6, 76);
const layers = wakeLayers([p1], t, {{wake_color: '#ffffff'}});
console.log(JSON.stringify({{same: JSON.stringify(p1) === JSON.stringify(p2), before: displayPose(a, -5), seamHeading: s.heading, seamRoll: s.roll,
  speed: p1.speed, n: w.length, kinds: [...new Set(w.map((x) => x.kind))], layer: layers[0].id, heading: p1.heading}}));
"""
    out = subprocess.run([node, "--input-type=module"], input=code, capture_output=True, text=True, cwd=ROOT / "offsim/render_deck")
    assert out.returncode == 0, out.stderr
    r = json.loads(out.stdout.strip().splitlines()[-1])
    assert r["same"] and r["before"] is None
    assert r["seamHeading"] == pytest.approx(0.0, abs=1e-9) or r["seamHeading"] == pytest.approx(360.0, abs=1e-9)   # 350 -> 10 passes through 0
    assert r["seamRoll"] == pytest.approx(1.0)
    assert r["n"] == 36 and set(r["kinds"]) == {"arm_l", "arm_r", "trail"} and r["layer"] == "vessel-wake"
    k = int(np.searchsorted(a["ts"], 9000.5, side="right")) - 1          # same interpolation in Python, seam-safe
    f = (9000.5 - a["ts"][k]) / (a["ts"][k + 1] - a["ts"][k])
    h0, h1 = a["heading"][k], a["heading"][k + 1]
    assert r["heading"] == pytest.approx((h0 + ((h1 - h0 + 540) % 360 - 180) * f) % 360, abs=1e-6)
