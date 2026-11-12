"""Studio conductor: funnel data, ledger, stage derivation, advance. Fast: tmp dirs, subprocess monkeypatched."""
import json
import shlex
import sys
import types
from pathlib import Path

import pytest
import yaml

from offsim.__main__ import LAZY, PASSTHROUGH, build_parser, main
from offsim.studio import conductor, ledger, context, derive_stage, load_funnel

ROOT = Path(__file__).resolve().parents[1]
PID = "fake-paper"


def sub_names():
    ap = build_parser()
    action = next(a for a in ap._actions if a.dest == "cmd")
    return set(action.choices) | set(PASSTHROUGH) | set(LAZY)


@pytest.fixture
def root(tmp_path):
    (tmp_path / "offsim/papers" / PID).mkdir(parents=True)
    return tmp_path


def touch(root, rel, text="x"):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


def good_report(root, rel=f"out/{PID}/report.json", ok=True):
    gates = {"0_provenance": {"pass": True}, "1_plan": {"pass": ok}, "4_paper": {"pass": False}}
    touch(root, rel, json.dumps({"gates": gates, "status": "reproduced" if ok else "stopped at gate 1_plan"}))


# ---- funnel ---------------------------------------------------------------------------------------------------------

def test_funnel_loads_in_order():
    ids = [s["id"] for s in load_funnel()]
    assert ids == ["feed", "triage", "gap", "intake", "extract", "scenario", "run", "experiment", "findings",
                   "storyboard", "film", "article", "publish"]
    kinds = {s["id"]: s["kind"] for s in load_funnel()}
    assert {k for k, v in kinds.items() if v == "decide"} == {"gap", "extract", "publish"}


def test_every_real_command_exists_in_the_cli():
    names = sub_names()
    for s in load_funnel():
        assert (ROOT / "skills" / s["owner"]).is_dir(), f"{s['id']}: owner skill missing"
        for key in ("command", "precheck"):
            cmd = s.get(key)
            if not cmd or s.get("planned"):
                continue
            argv = shlex.split(cmd)
            assert argv[:3] == ["python", "-m", "offsim"], cmd
            assert argv[3] in names, f"{s['id']}: `offsim {argv[3]}` is not a CLI command"
    assert all(s.get("planned") for s in load_funnel() if s["id"] in ("findings", "article", "publish"))


def test_run_command_parses_with_the_real_parser():
    s = next(x for x in load_funnel() if x["id"] == "experiment")
    cmd = conductor.render(s["command"], context(PID))
    a = build_parser().parse_args(shlex.split(cmd)[3:])
    assert a.cmd == "experiment" and a.out.endswith("experiment.json")


# ---- derivation -----------------------------------------------------------------------------------------------------

def test_state_derivation_stages(root):
    pd = f"offsim/papers/{PID}"
    stage = lambda: derive_stage(PID, root)[0]
    assert stage() == "feed"                                   # nothing at all in a bare checkout
    touch(root, "papers/feed.jsonl")
    touch(root, "papers/tags.jsonl")
    assert stage() == "gap"
    touch(root, f"{pd}/GAP.md")
    assert stage() == "intake"
    touch(root, f"{pd}/extract.json", "{}")
    assert stage() == "extract"
    touch(root, f"{pd}/scenario.yaml", "paper: {id: x}")        # scenario present implies extract was confirmed
    assert stage() == "run"
    good_report(root, ok=False)
    assert stage() == "run" and not derive_stage(PID, root)[1]["run"][0]
    good_report(root)
    assert stage() == "experiment"
    touch(root, f"{pd}/storyboard.yaml", "id: fake-paper\nrun: out/fake\n")
    assert stage() == "film"
    touch(root, "out/fake/fake-paper_square.mp4")
    assert stage() == "article"
    touch(root, f"{pd}/article.md")
    assert stage() == "publish"
    touch(root, f"{pd}/published.json", "{}")
    assert stage() is None


def test_load_derives_without_writing(root):
    touch(root, f"offsim/papers/{PID}/extract.json", "{}")
    st = ledger.load(PID, root)
    assert st["derived"] and st["stage"] == "extract" and st["history"] == []
    assert not ledger.state_path(PID, root).exists()


def test_decision_completes_decide_stage(root):
    touch(root, f"offsim/papers/{PID}/extract.json", "{}")
    ledger.decide(PID, "extract", "values confirmed against pp. 12-14", root=root)
    st = ledger.load(PID, root)
    assert st["stage"] == "scenario" and not st["derived"]
    with pytest.raises(ValueError):
        ledger.decide(PID, "nonsense", "x", root=root)


# ---- ledger ---------------------------------------------------------------------------------------------------------

def test_ledger_history_is_append_only_and_atomic(root):
    touch(root, f"offsim/papers/{PID}/scenario.yaml", "a: 1")
    ledger.record(PID, "scenario", "done", "first", root=root)
    first = json.loads(ledger.state_path(PID, root).read_text())
    ledger.block(PID, "G1-PLAN-INFEASIBLE", "capacity", stage="run", root=root)
    ledger.unblock(PID, "G1-PLAN-INFEASIBLE", root=root)
    ledger.decide(PID, "gap", "chosen", root=root)
    now = json.loads(ledger.state_path(PID, root).read_text())
    assert now["history"][:len(first["history"])] == first["history"]
    assert [h["event"] for h in now["history"]] == ["done", "blocked", "unblocked", "decided"]
    assert now["blockers"] == [] and len(now["decisions"]) == 1
    assert "offsim/papers/fake-paper/scenario.yaml" in now["artefacts"]
    assert set(now) >= {"paper_id", "stage", "history", "artefacts", "blockers", "decisions", "next"}
    assert all(set(h) == {"t_utc", "stage", "event", "detail", "by"} for h in now["history"])
    assert not list(ledger.state_path(PID, root).parent.glob(".state.*"))        # no temp files left
    tampered = dict(now, history=now["history"][1:])
    with pytest.raises(ValueError):
        ledger.save(tampered, root)
    tampered = json.loads(json.dumps(now))
    tampered["history"][0]["detail"] = "rewritten"
    with pytest.raises(ValueError):
        ledger.save(tampered, root)


# ---- advance --------------------------------------------------------------------------------------------------------

def test_advance_dry_run_executes_nothing(root, monkeypatch):
    touch(root, f"offsim/papers/{PID}/scenario.yaml", "a: 1")
    monkeypatch.setattr(conductor, "_exec", lambda *a, **k: pytest.fail("dry run executed a command"))
    res = conductor.advance(PID, dry_run=True, root=root)
    assert res["steps"][0]["stage"] == "run" and res["steps"][0]["status"] == "would-run"
    assert not ledger.state_path(PID, root).exists()
    assert res["stopped"]["reason"] == "needs-owner" and res["stopped"]["stage"] == "storyboard"


def test_advance_stops_at_decide_stage(root, monkeypatch):
    touch(root, f"offsim/papers/{PID}/extract.json", "{}")
    monkeypatch.setattr(conductor, "_exec", lambda *a, **k: pytest.fail("must not run"))
    res = conductor.advance(PID, dry_run=False, root=root)
    assert res["steps"] == [] and res["stopped"]["reason"] == "decision" and res["stopped"]["stage"] == "extract"


def test_advance_runs_auto_stages_then_stops_at_owner(root, monkeypatch):
    touch(root, f"offsim/papers/{PID}/scenario.yaml", "a: 1")
    calls = []

    def fake_exec(argv, r):
        calls.append(argv)
        good_report(root)
        return 0
    monkeypatch.setattr(conductor, "_exec", fake_exec)
    res = conductor.advance(PID, dry_run=False, root=root)
    assert len(calls) == 1 and calls[0][1:4] == ["-m", "offsim", "run"] and calls[0][0] == sys.executable
    assert [s["status"] for s in res["steps"] if s["commands"]] == ["ok"]
    assert res["stopped"]["reason"] == "needs-owner" and res["stopped"]["stage"] == "storyboard"
    events = [h["event"] for h in ledger.load(PID, root)["history"]]
    assert events == ["start", "done"]
    assert ledger.load(PID, root)["blockers"] == []


def test_advance_stops_on_failed_exit_check(root, monkeypatch):
    touch(root, f"offsim/papers/{PID}/scenario.yaml", "a: 1")
    monkeypatch.setattr(conductor, "_exec", lambda argv, r: 0)       # command "succeeds" but writes no report
    res = conductor.advance(PID, dry_run=False, root=root)
    assert res["stopped"]["reason"] == "exit-check" and res["stopped"]["stage"] == "run"
    st = ledger.load(PID, root)
    assert [b["code"] for b in st["blockers"]] == ["EXIT-CHECK-FAILED"]
    assert st["stage"] == "run"


def test_failed_run_without_doctor_records_gate_blocker(root, monkeypatch):
    touch(root, f"offsim/papers/{PID}/scenario.yaml", "a: 1")
    monkeypatch.setitem(sys.modules, "offsim.doctor", None)          # module absent
    monkeypatch.setattr(conductor, "_exec", lambda argv, r: (good_report(root, ok=False), 1)[1])
    res = conductor.advance(PID, dry_run=False, root=root)
    assert res["stopped"]["reason"] == "failed"
    assert [b["code"] for b in ledger.load(PID, root)["blockers"]] == ["RUN-GATE-FAILED"]


def test_failed_run_calls_doctor_and_records_its_code(root, monkeypatch):
    touch(root, f"offsim/papers/{PID}/scenario.yaml", "a: 1")
    seen = []

    def diagnose(path):
        seen.append(str(path))
        return {"code": "G1-PLAN-INFEASIBLE", "checks": [], "repairs": [], "question": "raise fleet capacity?"}
    monkeypatch.setitem(sys.modules, "offsim.doctor", types.SimpleNamespace(diagnose=diagnose))
    monkeypatch.setattr(conductor, "_exec", lambda argv, r: (good_report(root, ok=False), 1)[1])
    res = conductor.advance(PID, dry_run=False, root=root)
    assert seen and seen[0].endswith(f"out/{PID}/report.json")
    assert res["stopped"]["detail"].startswith("G1-PLAN-INFEASIBLE")
    st = ledger.load(PID, root)
    assert st["blockers"][0]["code"] == "G1-PLAN-INFEASIBLE" and "fleet capacity" in st["blockers"][0]["detail"]


def test_missing_required_input_blocks(root, monkeypatch):
    touch(root, "papers/feed.jsonl")
    touch(root, "papers/tags.jsonl")
    ledger.decide(PID, "gap", "go", root=root)
    monkeypatch.setattr(conductor, "_exec", lambda *a, **k: pytest.fail("no pdf, must not run"))
    res = conductor.advance(PID, dry_run=False, root=root)
    assert res["stopped"]["reason"] == "missing-input" and res["stopped"]["stage"] == "intake"
    assert ledger.load(PID, root)["blockers"][0]["code"] == "INPUT-MISSING"


# ---- status and CLI ---------------------------------------------------------------------------------------------------

def test_status_lists_the_real_papers():
    res = conductor.status()
    rows = {r["paper_id"]: r for r in res["papers"]}
    assert {"demo-oslofjord-supply", "irinagribkovskaia-2025-tactical-helicopter"} <= set(rows)
    assert rows["demo-oslofjord-supply"]["stage"] in ("film", "article", "publish", "done")
    assert rows["irinagribkovskaia-2025-tactical-helicopter"]["stage"] in ("run", "experiment", "storyboard")
    assert "demo-oslofjord-supply" in conductor.format_status(res)


def test_cli_status_next_and_missing_modules(capsys, monkeypatch):
    assert main(["status"]) == 0
    assert main(["next", "demo-oslofjord-supply"]) == 0
    out = capsys.readouterr().out
    assert "stage" in out and "command:" in out
    assert main(["advance", "demo-oslofjord-supply"]) == 0         # dry-run by default
    assert main(["decide", PID, "nonsense", "--note", "x"]) == 2   # unknown stage: refused before any write
    for mod, cmd in (("offsim.doctor.cli", "doctor"), ("offsim.live.cli", "live"), ("offsim.doctor.cli", "learn")):
        monkeypatch.setitem(sys.modules, mod, None)
        assert main([cmd]) == 2
        assert "not available" in capsys.readouterr().err


def test_experiment_accepts_out_flag():
    a = build_parser().parse_args(["experiment", "e.yaml", "--out", "x.json"])
    assert a.out == "x.json"
