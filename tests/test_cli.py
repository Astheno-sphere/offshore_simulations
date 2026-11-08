"""One CLI: `python -m offsim <cmd>` reaches every capability; existing commands still parse."""
import json
import re
import subprocess
import sys
import types
from pathlib import Path

import pytest
import yaml

from offsim.__main__ import PASSTHROUGH, build_parser, main

ROOT = Path(__file__).resolve().parents[1]

COMMANDS = ["paper", "run", "experiment", "story", "film", "world", "layer", "timetable", "entur",
            "feed", "tag", "gaps", "tools", "catalog", "resume"]
GROUPS = ["Paper", "Run", "Experiment", "Film", "Data", "Research", "Inspect"]


def test_help_lists_all_commands_and_groups():
    r = subprocess.run([sys.executable, "-m", "offsim", "--help"], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    for name in COMMANDS:
        assert re.search(rf"\b{name}\b", r.stdout), f"{name} missing from --help"
    for group in GROUPS:
        assert re.search(rf"^{group}$", r.stdout, re.M), f"group {group} missing from --help"


def test_every_subcommand_has_a_one_line_help():
    ap = build_parser()
    sub = next(a for a in ap._actions if a.__class__.__name__ == "_SubParsersAction")
    helps = {c.dest: c.help for c in sub._choices_actions}
    for name in COMMANDS:
        assert helps.get(name), f"{name} has no help text"
        assert "\n" not in helps[name]


def test_tools_prints_replay_ok(capsys):
    assert main(["tools"]) == 0
    out = capsys.readouterr().out
    assert re.search(r"^engine\s+replay\s+ok$", out, re.M), out


def test_timetable_writes_gtfs(tmp_path, capsys):
    tt = {"source": {"paper": "test", "doi": "10.0/x"},
          "service": {"days": ["mon", "tue", "wed", "thu", "fri"], "start_date": 20260105, "end_date": 20261231},
          "lines": [{"id": "1", "mode": "bus",
                     "stops": [{"id": "A", "name": "A", "lon": 7.16, "lat": 62.737, "src": "p.1"},
                               {"id": "B", "name": "B", "lon": 7.20, "lat": 62.745, "assumption": True},
                               {"id": "C", "name": "C", "lon": 7.26, "lat": 62.756, "src": "p.1"}],
                     "run_time_min": {"value": [6, 7], "src": "p.2"}, "dwell_s": {"value": 30, "assumption": True},
                     "headway_min": {"value": 30, "src": "p.2"}, "first": "07:00", "last": "08:00",
                     "both_directions": True}]}
    src = tmp_path / "timetable.yaml"
    src.write_text(yaml.safe_dump(tt))
    out = tmp_path / "gtfs"
    assert main(["timetable", str(src), "--out", str(out)]) == 0
    for name in ("stops.txt", "routes.txt", "trips.txt", "stop_times.txt", "calendar.txt", "manifest.json"):
        assert (out / name).exists(), name
    man = json.loads((out / "manifest.json").read_text())
    assert man["trips"] == 6 and "lines[0].stops[1]" in man["assumptions"]


def test_timetable_refuses_unsourced_with_exit_2(tmp_path, capsys):
    tt = {"source": {"paper": "x"}, "service": {"days": ["mon"], "start_date": 20260105, "end_date": 20260110},
          "lines": [{"id": "1", "stops": [{"id": "A", "name": "A", "lon": 7, "lat": 62},
                                          {"id": "B", "name": "B", "lon": 7.1, "lat": 62}],
                     "run_time_min": {"value": [5], "src": "p"}, "headway_min": {"value": 10, "src": "p"},
                     "first": "07:00", "last": "07:30"}]}
    src = tmp_path / "t.yaml"
    src.write_text(yaml.safe_dump(tt))
    assert main(["timetable", str(src), "--out", str(tmp_path / "g")]) == 2
    assert "needs src" in capsys.readouterr().err


def test_paper_missing_module_is_a_clear_error_not_a_traceback(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "offsim.intake", None)
    monkeypatch.setitem(sys.modules, "offsim.intake.paper", None)
    assert main(["paper", "some.pdf"]) == 2
    err = capsys.readouterr().err
    assert "offsim.intake.paper is not available" in err and "Traceback" not in err


def test_paper_forwards_to_intake_main(monkeypatch, tmp_path):
    seen = {}
    fake = types.ModuleType("offsim.intake.paper")
    fake.main = lambda argv: seen.setdefault("argv", argv) and 0
    monkeypatch.setitem(sys.modules, "offsim.intake", types.ModuleType("offsim.intake"))
    monkeypatch.setitem(sys.modules, "offsim.intake.paper", fake)
    assert main(["paper", "p.pdf", "--out", str(tmp_path)]) == 0
    assert seen["argv"] == ["p.pdf", "--out", str(tmp_path)]


def test_experiment_prints_decision_json(monkeypatch, capsys):
    import offsim.research.run_experiment as re_mod
    calls = {}

    def fake_run(path, engine=None, *, workers=1, **kw):
        calls.update(path=path, engine=engine, workers=workers)
        return {"gap_id": "g1", "decision": {"status": "inconclusive"}, "blocked": None, "reportable": False}

    monkeypatch.setattr(re_mod, "run", fake_run)
    assert main(["experiment", "exp.yaml", "--engine", "replay", "--workers", "3"]) == 0
    assert calls == {"path": "exp.yaml", "engine": "replay", "workers": 3}
    assert json.loads(capsys.readouterr().out)["decision"]["status"] == "inconclusive"


def test_passthrough_catalog_find_reaches_catalog_build(capsys):
    r = subprocess.run([sys.executable, "-m", "offsim", "catalog", "--find", "zzz-no-such-tool-zzz"],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_passthrough_names_are_registered():
    assert set(PASSTHROUGH) == {"world", "layer", "feed", "tag", "gaps", "entur", "catalog"}


def test_existing_commands_still_parse():
    ap = build_parser()
    a = ap.parse_args(["run", "s.yaml", "--out", "o", "--seconds", "3"])
    assert (a.cmd, a.scenario, a.out, a.seconds) == ("run", "s.yaml", "o", 3.0)
    a = ap.parse_args(["story", "b.yaml", "--dry-run"])
    assert (a.cmd, a.storyboard, a.dry_run) == ("story", "b.yaml", True)
    a = ap.parse_args(["resume", "--tests"])
    assert (a.cmd, a.tests) == ("resume", True)
    a = ap.parse_args(["film", "b.yaml", "--muse", "unlisted"])
    assert (a.cmd, a.storyboard, a.muse, a.seconds) == ("film", "b.yaml", "unlisted", 2.0)


def test_new_commands_parse():
    ap = build_parser()
    a = ap.parse_args(["experiment", "e.yaml", "--engine", "wombat", "--workers", "2"])
    assert (a.cmd, a.experiment, a.engine, a.workers) == ("experiment", "e.yaml", "wombat", 2)
    a = ap.parse_args(["timetable", "t.yaml", "--out", "d"])
    assert (a.cmd, a.timetable, a.out) == ("timetable", "t.yaml", "d")
    with pytest.raises(SystemExit):
        ap.parse_args(["timetable", "t.yaml"])          # --out is required
