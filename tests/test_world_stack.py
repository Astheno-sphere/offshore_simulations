"""Phase 8: the delta block in scene.json and `world_stack` (every world layer present, or absent with a named reason).

The pair is the real `run_experiment.run` result of tests/test_stress.py (genuine, hash-verified sidecars). The scene's trajectory is one of the
pair's own tracks, so `belongs_to` is true; a different run must be refused, and the JS layer must draw what Python derives."""
import json
import shutil
import subprocess

import numpy as np
import pandas as pd
import pytest

from offsim.contract import validate
from offsim.motion.delta import belongs_to, delta_block, delta_geometry
from offsim.research import run_experiment, stress
from offsim.scene import WORLD_STACK_LAYERS, build_scene, diagnose_world, world_stack
from test_stress import T_MID, _build, _exp, _wx

CAM = {"longitude": 5.25, "latitude": 60.0, "zoom": 8, "pitch": 0, "bearing": 0}
OV = {"kicker": "k", "title": "t", "legend": [], "source": "s", "watermark": "w"}


@pytest.fixture(scope="module")
def pair(tmp_path_factory):
    d = tmp_path_factory.mktemp("ws")
    r = run_experiment.run(_exp(d), build=_build(), load_weather=_wx, out=d / "r.json")
    return stress.load_stress_pair(r, d, draft=True)


def _traj(pair, name):
    t, lo, la = pair["tracks"][name]
    n = len(t)
    return pd.DataFrame({"agent_id": pair["agent_id"], "t": t, "lon": lo, "lat": la,
                         "state": ["sail"] * n})


AG = pd.DataFrame([{"agent_id": "psv1", "cls": "psv", "vmax_mps": 8.0, "capacity": 10.0, "domain": "sea"}])


def _scene(pair, which, **kw):
    tr = _traj(pair, which)
    return build_scene(tr, AG, validate(tr, AG), camera=CAM, overlay=dict(OV), **kw)


def test_the_delta_block_is_the_pairs_geometry_and_stamps_a_draft(pair):
    s = _scene(pair, "paper", delta_pair=pair)
    d = s["delta"]
    assert d["variant_names"] == pair["compare"] and d["max_divergence_m"] > 0 and d["t_star_s"] == T_MID
    g = delta_geometry(pair, 1e12)
    assert np.allclose(d["pa"], g["pa"]) and np.allclose(d["pb"], g["pb"])
    assert s["overlay"]["stamp"] == "DRAFT, NOT REPORTABLE"
    assert {nm for _, nm in s["overlay"]["legend"]} >= set(pair["compare"])
    json.dumps(s)                                                        # the whole scene stays serialisable


def test_a_pair_for_another_run_is_refused(pair):
    other = _traj(pair, "paper").assign(lon=lambda x: x["lon"] + 0.5)   # a different simulation, same agent
    assert belongs_to(pair, other) is None
    with pytest.raises(ValueError, match="does not belong"):
        delta_block(pair, other)
    with pytest.raises(ValueError, match="does not belong"):
        build_scene(other, AG, validate(other, AG), camera=CAM, overlay=dict(OV), delta_pair=pair)


def test_world_stack_names_every_layer_and_every_absence(pair):
    s = _scene(pair, "paper")
    ws = s["world_stack"]
    assert list(ws) == list(WORLD_STACK_LAYERS)
    for k, v in ws.items():
        assert v["present"] is False and len(v["reason"]) > 10, k       # a bare scene: all absent, none silent
    s2 = _scene(pair, "paper", absent_reasons={"ais": "no clip pulled"})
    assert s2["world_stack"]["ais"]["reason"] == "no clip pulled"
    # presence is read from content: a traffic block and a weather block flip exactly their layers
    s3 = _scene(pair, "paper", traffic={"points": [[5.0, 60.0]], "n_vessels": 1, "source": "HAIS"},
                weather={"particles": {"trips": [{}]}, "credit": "NORA3"})
    assert s3["world_stack"]["ais"]["present"] and s3["world_stack"]["metocean"]["present"]
    assert not s3["world_stack"]["isobaths"]["present"]


def test_diagnose_world_says_what_to_run(tmp_path):
    w = tmp_path / "data/worlds/x"
    w.mkdir(parents=True)
    why = diagnose_world("x", root=tmp_path)
    assert "land.geojson" in why["coast"] and "--pull x" in why["coast"]
    assert "--depth" in why["dem_hillshade"] and why["dem_hillshade"] == why["isobaths"]
    (w / "dem_raw").mkdir()
    assert "build_world_depth" in diagnose_world("x", root=tmp_path)["dem_hillshade"]


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_js_and_python_draw_the_same_ribbon(pair, tmp_path):
    """layers/delta.js `deltaGeometryAt` must give Python's rungs at the same clock (it re-derives the front rung in JS)."""
    s = _scene(pair, "paper", delta_pair=pair)
    ts = np.union1d(*[pair["tracks"][v][0] for v in pair["compare"]])
    probes = [float(ts[2]) + 100.0, T_MID, float(ts[-1]) + 5.0]
    js = tmp_path / "p.mjs"
    src = (__import__("pathlib").Path(__file__).resolve().parent.parent / "offsim/render_deck/src/layers/delta.js").as_uri()
    js.write_text(f"import {{deltaGeometryAt}} from '{src}';\nconst d=JSON.parse(process.argv[2]);\n"
                  f"console.log(JSON.stringify(JSON.parse(process.argv[3]).map(t=>deltaGeometryAt(d,t))));")
    r = subprocess.run(["node", str(js), json.dumps(s["delta"]), json.dumps(probes)], capture_output=True, text=True)
    if "Cannot find package" in r.stderr or "ERR_MODULE" in r.stderr:
        pytest.skip("delta.js imports deck.gl; run through the bundle check instead")
    assert r.returncode == 0, r.stderr[-400:]
    for t, got in zip(probes, json.loads(r.stdout)):
        want = delta_geometry(pair, t)
        assert np.allclose(got["pa"], want["pa"]) and np.allclose(got["pb"], want["pb"]), t
        assert np.allclose(got["trackA"], want["track_a"]) and np.allclose(got["trackB"], want["track_b"]), t
        assert (got["connector"] is not None) == (want["connector"] is not None), t
