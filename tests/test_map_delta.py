"""Stress-pair delta layer: research.stress.load_stress_pair (verified sidecars) -> mappanel.delta_geometry / MapPanel.frame(delta=).

The report is a real `run_experiment.run` result from the fake engine in tests/test_stress.py, so the sidecars and their hashes are
genuine. The claims under test: the picture is drawn from the verified files; its widest rung IS the report's number; the layer obeys
the simulation clock; a tampered or missing sidecar is refused before anything is drawn."""
import copy
import shutil

import numpy as np
import pytest
from PIL import ImageChops
from shapely.geometry import Polygon

from offsim.contract import haversine_m
from offsim.motion import mappanel
from offsim.motion.mappanel import MapPanel, delta_geometry
from offsim.research import run_experiment, stress
from test_stress import T_MID, _build, _exp, _wx

BBOX = (4.9, 59.9, 5.6, 60.4)


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    d = tmp_path_factory.mktemp("delta")
    r = run_experiment.run(_exp(d), build=_build(), load_weather=_wx, out=d / "r.json")
    return r, d


@pytest.fixture
def pair(run):
    r, d = run
    return stress.load_stress_pair(r, d, draft=True)


def _panel(**kw):
    land = Polygon([(4.9, 60.25), (5.6, 60.25), (5.6, 60.4), (4.9, 60.4)])
    return MapPanel(land, BBOX, size=(960, 320), seconds=0.0, wind_streaks=False, **kw)


def _widest_m(g):
    return float(np.max(haversine_m(g["pa"][:, 0], g["pa"][:, 1], g["pb"][:, 0], g["pb"][:, 1])))


# --- loading and refusing -------------------------------------------------------------------------------
def test_loads_the_verified_pair_and_stamps_it_draft_because_the_fixture_weather_is_synthetic(run):
    r, d = run
    p = stress.load_stress_pair(r, d, draft=True)
    assert p["draft"] is True and p["compare"] == ["robust", "paper"] and p["agent_id"] == "psv1"
    assert set(p["tracks"]) == {"robust", "paper"}
    with pytest.raises(ValueError, match="not reportable"):
        stress.load_stress_pair(r, d)                                   # unreportable: never silently drawn as if real


@pytest.mark.parametrize("change", ["digit", "format_only"])
def test_a_tampered_sidecar_is_refused_before_any_drawing(run, tmp_path, change):
    r, d = run
    for f in d.glob("r.stress.*.csv"):
        shutil.copy(f, tmp_path / f.name)
    f = tmp_path / "r.stress.robust.csv"
    raw = f.read_bytes()
    # `format_only` parses to the SAME table (a blank line is skipped), so only a hash over the file bytes catches it; a hash of a
    # re-serialised table would pass it. `digit` changes a number.
    f.write_bytes(raw + b"\n" if change == "format_only" else raw.replace(b"60.0", b"60.1", 1))
    with pytest.raises(ValueError, match="sha256"):
        stress.load_stress_pair(r, tmp_path, draft=True)


def test_refusals_blocked_missing_block_missing_file_wrong_agent_and_a_lying_block(run, tmp_path):
    r, d = run
    with pytest.raises(ValueError, match="no stress pair to draw: why"):
        stress.load_stress_pair({**r, "stress_blocked": "why"}, d, draft=True)
    with pytest.raises(ValueError, match="no decision.pair.stress"):
        stress.load_stress_pair({"decision": {}}, d, draft=True)
    with pytest.raises(ValueError, match="is not in"):
        stress.load_stress_pair(r, tmp_path, draft=True)                # sidecars not there
    wrong = copy.deepcopy(r)
    wrong["decision"]["pair"]["stress"]["agent_id"] = "nobody"
    with pytest.raises(ValueError, match="'nobody' is not in sidecar"):
        stress.load_stress_pair(wrong, d, draft=True)
    lie = copy.deepcopy(r)
    lie["decision"]["pair"]["stress"]["pos_a"] = [9.0, 9.0]
    with pytest.raises(ValueError, match="disagrees with its sidecar"):
        stress.load_stress_pair(lie, d, draft=True)
    odd = copy.deepcopy(r)
    odd["decision"]["pair"]["stress"]["sidecars"] = ["../r.stress.robust.csv", "r.stress.paper.csv"]
    with pytest.raises(ValueError, match="no single plain sidecar name"):
        stress.load_stress_pair(odd, d, draft=True)


# --- the picture is the number ---------------------------------------------------------------------------
def test_the_widest_rung_is_the_reports_max_divergence(run, pair):
    r, _ = run
    st = r["decision"]["pair"]["stress"]
    g = delta_geometry(pair, 1e12)                                       # the whole shared window
    assert _widest_m(g) == pytest.approx(st["max_divergence_m"], rel=1e-9)
    assert g["rung_t"][int(np.argmax(haversine_m(g["pa"][:, 0], g["pa"][:, 1], g["pb"][:, 0], g["pb"][:, 1])))] == st["t_star_s"] == T_MID
    (la, lb) = g["connector"]
    assert float(haversine_m(la[0], la[1], lb[0], lb[1])) == pytest.approx(st["max_divergence_m"], rel=1e-9)


def test_the_ribbon_pinches_to_nothing_where_the_tracks_agree_and_peaks_in_between(run, pair):
    r, _ = run
    g = delta_geometry(pair, 1e12)
    w = haversine_m(g["pa"][:, 0], g["pa"][:, 1], g["pb"][:, 0], g["pb"][:, 1])
    assert w[0] == pytest.approx(0.0, abs=1e-6) and w[-1] == pytest.approx(0.0, abs=1e-6)   # both start at A and end at B
    assert 0 < int(np.argmax(w)) < len(w) - 1
    assert w.max() == pytest.approx(r["decision"]["pair"]["stress"]["max_divergence_m"], rel=1e-9)   # its height is the report's number


# --- the clock is simulation time ------------------------------------------------------------------------
def test_the_layer_follows_the_simulation_clock(pair):
    ts = [pair["tracks"][v][0] for v in pair["compare"]]
    grid = np.union1d(ts[0], ts[1])
    lo = max(t[0] for t in ts)
    assert len(delta_geometry(pair, lo - 1.0)["rung_t"]) == 0 and not len(delta_geometry(pair, lo - 1.0)["track_a"])
    t = float(grid[2]) + 100.0                                           # between two samples: grid points <= t, plus the front rung
    g = delta_geometry(pair, t)
    assert len(g["rung_t"]) == int((grid <= t).sum()) + 1 and g["rung_t"][-1] == t
    on = delta_geometry(pair, float(grid[2]))                            # exactly on a sample: no duplicate front rung
    assert len(on["rung_t"]) == int((grid <= grid[2]).sum())
    assert delta_geometry(pair, T_MID - 1.0)["connector"] is None
    assert delta_geometry(pair, T_MID)["connector"] is not None
    assert delta_geometry(pair, T_MID + 10.0)["connector"] is not None
    assert np.allclose(g["track_a"][-1], g["pa"][-1])                    # the track ends where the ribbon's front is


# --- drawing -----------------------------------------------------------------------------------------------
def test_delta_with_wind_streaks_is_refused_by_the_v9_verdict(pair):
    land = Polygon([(4.9, 60.25), (5.6, 60.25), (5.6, 60.4), (4.9, 60.4)])
    mp = MapPanel(land, BBOX, size=(960, 320), seconds=0.0, wind_streaks=True)
    with pytest.raises(ValueError, match="wind_streaks=False"):
        mp.frame(0.5, None, 0, (5.25, 60.0), delta={"pair": pair, "t": T_MID})


def test_the_layer_paints_the_ribbon_and_connector_and_leaves_the_rest_alone(pair):
    route = [(5.0, 60.0), (5.5, 60.0)]
    base = _panel().frame(0.5, route, 1, (5.25, 60.0))
    mp = _panel()
    img = mp.frame(0.5, None, 0, (5.25, 60.0), delta={"pair": pair, "t": T_MID})
    diff = ImageChops.difference(base.convert("RGB"), img.convert("RGB")).getbbox()
    assert diff is not None
    # the connector's midpoint is inside the changed region
    view = mp._view(0.5, (5.25, 60.0))
    px = mp._proj(view)
    g = delta_geometry(pair, T_MID)
    mx, my = (np.mean([px(*g["connector"][0])[i], px(*g["connector"][1])[i]]) for i in (0, 1))
    assert diff[0] <= mx <= diff[2] and diff[1] <= my <= diff[3]
    # frames are a pure function of their arguments: same pair, same t, same bytes
    again = _panel().frame(0.5, None, 0, (5.25, 60.0), delta={"pair": pair, "t": T_MID})
    assert ImageChops.difference(img.convert("RGB"), again.convert("RGB")).getbbox() is None


def test_delta_none_is_the_unchanged_panel(pair):
    route = [(5.0, 60.0), (5.5, 60.0)]
    a = _panel().frame(0.5, route, 1, (5.25, 60.0))
    b = _panel().frame(0.5, route, 1, (5.25, 60.0), delta=None)
    assert ImageChops.difference(a.convert("RGB"), b.convert("RGB")).getbbox() is None


def test_the_legend_names_the_experiments_variants_and_stamps_a_draft(pair, monkeypatch):
    from offsim.cinema.draw import Canvas
    seen = []
    real = Canvas.text
    monkeypatch.setattr(Canvas, "text", lambda self, x, y, s, *a, **k: (seen.append(s), real(self, x, y, s, *a, **k))[1])
    _panel().frame(0.5, None, 0, (5.25, 60.0), delta={"pair": pair, "t": T_MID})
    assert {"robust", "paper", "DRAFT, NOT REPORTABLE"} <= set(seen)
    assert not any(w in " ".join(seen).lower() for w in ("exact", "heuristic"))      # names come from the experiment, never hardcoded
    assert not any(any(ch.isdigit() for ch in t) for t in seen if t not in ("N",) and "km" not in t)   # no number is printed by the layer
    assert mappanel.DELTA_LAYER["assumption"] is True                    # its three readability numbers are flagged as set by eye
