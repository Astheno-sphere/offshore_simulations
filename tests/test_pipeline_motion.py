"""Gated runner, narration gate in the storyboard, and line-art geometry."""
import json
from pathlib import Path

import pytest
import yaml

from conftest import ROOT
from offsim.motion import story
from offsim.pipeline import provenance_gaps, run

DEMO = ROOT / "offsim/papers/demo-oslofjord-supply/scenario.yaml"


def scenario(tmp_path, **edit):
    sc = yaml.safe_load(DEMO.read_text())
    sc["world"] = "none"                       # CI has no fetched world: straight legs, no land check
    for k, v in edit.items():
        sc[k] = v
    p = tmp_path / "scenario.yaml"
    p.write_text(yaml.safe_dump(sc))
    return p, sc


def test_runner_passes_gates_and_records_provenance(tmp_path):
    p, _ = scenario(tmp_path)
    rep = run(p, tmp_path / "out", seconds=1)
    assert [g["pass"] for k, g in rep["gates"].items() if k != "4_paper"] == [True, True, True, True]
    assert rep["status"] == "not comparable (no reported KPIs)"
    assert rep["provenance"]["scenario_sha256"] and rep["provenance"]["packages"]["pyvrp"]
    assert (tmp_path / "out/trajectory.csv").exists()


def test_reported_kpis_decide_the_status_word(tmp_path):
    p, _ = scenario(tmp_path)
    first = run(p, tmp_path / "a", seconds=1)
    km = first["kpis"]["distance_km"]
    p2, _ = scenario(tmp_path, reported={"distance_km": {"value": km, "rel_tol": 0.01, "src": "test"}})
    assert run(p2, tmp_path / "b", seconds=1)["status"] == "re-run under assumptions"   # demo is all assumptions
    p3, _ = scenario(tmp_path, reported={"distance_km": {"value": km * 0.5, "rel_tol": 0.01, "src": "test"}})
    assert run(p3, tmp_path / "c", seconds=1)["status"] == "did not reproduce"


def test_unsourced_values_and_unsupported_classes_stop_at_gate_0(tmp_path):
    _, sc = scenario(tmp_path)
    sc["fleet"][0]["capacity"] = {"value": 12}                       # no src, no assumption
    assert "fleet[0].capacity" in provenance_gaps(sc)
    p, _ = scenario(tmp_path, problem={**sc["problem"], "class": ["PDP", "synchronisation"]})
    rep = run(p, tmp_path / "d", seconds=1)
    assert rep["status"] == "stopped at gate 0_provenance"
    assert rep["gates"]["0_provenance"]["detail"]["unsupported_classes"] == ["PDP", "synchronisation"]


def test_storyboard_refuses_literals_and_failed_runs():
    with pytest.raises(ValueError):
        story.resolve(42, {"kpis": {}})
    assert story.resolve("report:kpis.distance_km", {"kpis": {"distance_km": 113.3}}) == 113.3
    bad = {"gates": {"3_contract": {"pass": False}}, "status": "stopped at gate 3_contract"}
    probs = story.check({"shots": []}, bad)
    assert any("did not pass gates" in p for p in probs)


def test_lineart_is_metric_plan_view_with_forward_y():
    for name, (w, l) in {"psv": (16, 76), "ferry": (20, 90)}.items():
        art = json.loads((ROOT / f"offsim/assets/lineart/{name}.json").read_text())
        x0, y0, x1, y1 = art["bbox_plan"]
        assert abs((x1 - x0) - w) < 5 and abs((y1 - y0) - l) < 10, name     # beam across x, length along y
        assert len(art["plan"]) > 50 and all(len(s) == 2 for s in art["plan"])
