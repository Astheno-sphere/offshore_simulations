"""Camera: easing, fit_view, spline, fly, per-frame track, shot_plan inspector."""
import copy
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from offsim.cinema import camera as C

VP = (1080, 1080)
DEMO = Path(__file__).resolve().parent.parent / "offsim/papers/demo-oslofjord-supply/storyboard.yaml"


@pytest.mark.parametrize("name", ["linear", "cubic_in_out", "quint_in_out", "smoothstep"])
def test_ease_endpoints_monotonic_clamped(name):
    assert C.ease(name, 0) == 0 and C.ease(name, 1) == 1
    assert C.ease(name, -3) == 0 and C.ease(name, 7) == 1
    v = [C.ease(name, i / 200) for i in range(201)]
    assert all(b >= a - 1e-12 for a, b in zip(v, v[1:]))
    assert C.ease(name, 0.5) == pytest.approx(0.5)
    with pytest.raises(ValueError):
        C.ease("nope", 0.5)


def _project(lon, lat, v, vp):
    """Independent screen projection for pitch 0, bearing 0 (512 px tiles)."""
    s = 512 * 2 ** v["zoom"]
    f = lambda lo, la: ((lo + 180) / 360 * s, (1 - math.log(math.tan(math.pi / 4 + math.radians(la) / 2)) / math.pi) / 2 * s)  # noqa: E731
    x, y = f(lon, lat)
    cx, cy = f(v["longitude"], v["latitude"])
    return vp[0] / 2 + x - cx, vp[1] / 2 + y - cy


@pytest.mark.parametrize("bbox,vp", [([[10.40, 59.10], [10.75, 59.47]], (1080, 1080)), ([[4.0, 58.5], [6.0, 60.5]], (1080, 1920)),
                                     ([[10.0, 59.0], [11.5, 59.4]], (1920, 1080))])
def test_fit_view_contains_bbox_in_padded_viewport(bbox, vp):
    v = C.fit_view(bbox, vp, pitch=30, bearing=-10)
    assert v["pitch"] == 30 and v["bearing"] == -10
    W, H, p = vp[0], vp[1], 0.06
    (w, s), (e, n) = bbox
    xs, ys = zip(*[_project(lo, la, v, vp) for lo in (w, e) for la in (s, n)])
    tol = 1.5  # px: Math.round of the padding in app.js
    assert min(xs) >= W * p - tol and max(xs) <= W - W * (0.12 + p) + tol
    assert min(ys) >= H * (0.22 + p) - tol and max(ys) <= H - H * (0.12 + p) + tol
    # tight on the limiting axis
    assert min(min(xs) - W * p, min(ys) - H * (0.22 + p)) < 3 or max(W * (1 - 0.12 - p) - max(xs), H * (1 - 0.12 - p) - max(ys)) < 3


def test_fit_view_matches_deck_fitbounds():
    v = C.fit_view([[10.40, 59.10], [10.75, 59.47]], VP, 30, 0)  # reference from @math.gl/web-mercator fitBounds
    assert v["longitude"] == pytest.approx(10.602496954933, abs=1e-9)
    assert v["latitude"] == pytest.approx(59.319697753296, abs=1e-9)
    assert v["zoom"] == pytest.approx(9.146803841152, abs=1e-9)


KEYS = [{"t": 0.0, "longitude": 10.0, "latitude": 59.0, "zoom": 8.0, "pitch": 0, "bearing": 0},
        {"t": 2.0, "longitude": 10.4, "latitude": 59.3, "zoom": 9.5, "pitch": 30, "bearing": 20},
        {"t": 5.0, "longitude": 10.5, "latitude": 59.2, "zoom": 11.0, "pitch": 50, "bearing": 10},
        {"t": 9.0, "longitude": 10.9, "latitude": 59.4, "zoom": 10.0, "pitch": 40, "bearing": 350}]


def test_spline_interpolates_keys_and_velocity_is_continuous():
    for k in KEYS:
        v = C.camera_spline(KEYS, k["t"])
        for d in C.DIMS[:4]:
            assert v[d] == pytest.approx(k[d], abs=1e-9)
    assert C.camera_spline(KEYS, 9.0)["bearing"] == pytest.approx(-10.0)  # 350 unwrapped to -10: short way round
    h = 1e-5
    for k in KEYS[1:-1]:
        a, b = C.camera_spline(KEYS, k["t"] - 2 * h), C.camera_spline(KEYS, k["t"] - h)
        c, d = C.camera_spline(KEYS, k["t"] + h), C.camera_spline(KEYS, k["t"] + 2 * h)
        for dim in C.DIMS:
            vin, vout = (b[dim] - a[dim]) / h, (d[dim] - c[dim]) / h
            assert vin == pytest.approx(vout, abs=2e-3 * max(1.0, abs(vin))), (k["t"], dim)
        # and it does not stop at the key
        assert abs((c["zoom"] - b["zoom"]) / (2 * h)) > 1e-3
    # holds are exactly static
    hold = [{"t": 0, **{d: KEYS[0][d] for d in C.DIMS}}, {"t": 1, **{d: KEYS[0][d] for d in C.DIMS}}, {**KEYS[1], "t": 4}]
    assert all(C.camera_spline(hold, x / 10)["zoom"] == 8.0 for x in range(11))


def test_fly_endpoints_exact_and_zoom_dips_on_long_moves():
    a = {"longitude": 10.0, "latitude": 59.0, "zoom": 11.0, "pitch": 40, "bearing": 0}
    b = {"longitude": 14.0, "latitude": 61.0, "zoom": 11.0, "pitch": 60, "bearing": 90}
    assert C.camera_fly(a, b, 0) == a and C.camera_fly(a, b, 1) == b
    zs = [C.camera_fly(a, b, i / 50)["zoom"] for i in range(51)]
    assert min(zs) < 11.0 - 1.0  # zooms out for a long pan
    mid = C.camera_fly(a, b, 0.5)
    assert mid["pitch"] == pytest.approx(50) and mid["bearing"] == pytest.approx(45)
    # reference values from @math.gl/web-mercator flyToViewport (viewport 1080x1080)
    a2 = {"longitude": 10.5, "latitude": 59.2, "zoom": 8, "pitch": 0, "bearing": 0}
    b2 = {"longitude": 10.7, "latitude": 59.4, "zoom": 12.5, "pitch": 0, "bearing": 0}
    assert C.camera_fly(a2, b2, 0.6)["zoom"] == pytest.approx(10.653812169824578, abs=1e-9)
    assert C.camera_fly(a2, b2, 0.6)["longitude"] == pytest.approx(10.695702056003205, abs=1e-9)


def _shot(**cam):
    return {"type": "map", "seconds": 8, "camera": cam}


def test_camera_track_length_and_shape():
    sb = yaml.safe_load(DEMO.read_text())
    for fps in (24, 30):
        fr = C.camera_track(sb["shots"][1], 0.0, 3600.0, 14, fps, VP)
        assert len(fr) == round(14 * fps)
        assert set(fr[0]) == {"i", "s", "t", "longitude", "latitude", "zoom", "pitch", "bearing"}
        assert fr[0]["t"] == 0.0 and fr[-1]["t"] < 3600.0 and fr[5]["i"] == 5
    fly = _shot(keys=[{"at": 0, "longitude": 10.0, "latitude": 59.0, "zoom": 8, "pitch": 0},
                      {"at": 1, "longitude": 10.6, "latitude": 59.4, "zoom": 12, "pitch": 40, "move": "fly"}])
    fr = C.camera_track(fly, 0, 100, 8, 30, VP)
    assert len(fr) == 240 and fr[0]["zoom"] == 8 and min(f["zoom"] for f in fr) < 12


def test_follow_places_vessel_with_lead_space_and_orbit():
    t = np.arange(0, 600, 10.0)
    tr = pd.DataFrame({"agent_id": "a", "t": t, "lon": 10.5 + t * 2e-5, "lat": 59.2 + t * 1e-5})
    shot = {"type": "map", "seconds": 6, "camera": {"follow": {"agent_id": "a", "zoom": 13, "pitch": 40, "bearing": 0}}}
    fr = C.camera_track(shot, 200, 260, 6, 30, VP, traj=tr)
    assert len(fr) == 180
    f = fr[90]
    assert f["longitude"] > np.interp(f["t"], t, tr["lon"]) and f["latitude"] > np.interp(f["t"], t, tr["lat"])  # centre ahead of vessel
    with pytest.raises(ValueError):
        C.camera_orbit((10, 59), 1, 0, 9.0, 12, 50)
    assert C.camera_orbit((10, 59), 2, 0, 5.0, 12, 50)["bearing"] == 10.0


def test_shot_plan_flags_too_fast_zoom_and_passes_demo():
    sb = yaml.safe_load(DEMO.read_text())
    assert C.shot_plan(sb, VP) == []
    bad = copy.deepcopy(sb)
    bad["shots"][1]["camera"]["keys"][2]["fit"] = [[10.55, 59.20], [10.60, 59.25]]  # ~3 zoom levels in 4.5 s
    msgs = C.shot_plan(bad, VP)
    assert any("shot 1" in m and "zoom rate" in m and "vs max 0.35" in m for m in msgs), msgs
    short = copy.deepcopy(sb)
    short["shots"][2]["seconds"] = 2.0
    assert any("shot 2" in m and "length" in m for m in C.shot_plan(short, VP))
    nohold = copy.deepcopy(sb)
    nohold["shots"] = [nohold["shots"][1]] + nohold["shots"][2:]
    nohold["shots"][0]["camera"]["keys"] = [nohold["shots"][0]["camera"]["keys"][i] for i in (0, 2, 3)]
    assert any("film opening not static" in m for m in C.shot_plan(nohold, VP))
    # a supplied track is inspected instead of the storyboard camera
    fr = C.camera_track(sb["shots"][1], 0, 1, 14, 30, VP)
    for f in fr:
        f["pitch"] += f["i"] * 0.5
    assert any("pitch rate" in m for m in C.shot_plan(sb, VP, tracks={1: fr}))
