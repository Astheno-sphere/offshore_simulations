"""Doctor: classify a failed gate, run read-only checks, offer repairs, ask the one question, remember the lesson.

    from offsim.doctor import diagnose, repair
    d = diagnose("out/<paper>/report.json")      # or a report dict, or a paper id (out/<id>/report.json)
    d["code"], d["gate"], d["checks"], d["repairs"], d["question"]
    repair("out/<paper>/report.json", max_attempts=2, run=False)   # run=True executes AUTO repairs only

Rules (docs/SYSTEM_PLAN.md 3.2): auto repairs are deterministic and value-preserving (re-pull released data, clear partial
downloads, rerun with another solver seed, report a command). Anything touching a sourced value, an assumption or a tolerance
is `human` and only ever asked about. Every repair attempt writes `diagnosis.json` next to the report.
CLI: `python -m offsim doctor <report.json|paper_id> [--repair]` / `learn ...` (offsim.doctor.cli.main).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

from offsim.doctor.codes import CODES, classify, code_for_gate, first_failure, meaning

ROOT = Path(__file__).resolve().parents[2]
PLAYBOOKS = Path(__file__).with_name("playbooks")
AUTO_OPS = {"report_command", "pull_world", "rerun_gate", "rerun_seed", "clear_partial_downloads"}   # the whole auto vocabulary

__all__ = ["diagnose", "repair", "load_playbook", "build_ctx", "CODES", "classify", "AUTO_OPS"]


def load_playbook(code):
    return yaml.safe_load((PLAYBOOKS / f"{code}.yaml").read_text())


def load_report(x, root=ROOT):
    """(report | text | qa-dict, path | None) from a dict, a report.json path, a paper id (out/<id>/report.json) or text."""
    if isinstance(x, dict):
        return x, None
    p = Path(str(x))
    if not p.exists() and re.fullmatch(r"[\w.\-]+", str(x)):
        p = Path(root) / "out" / str(x) / "report.json"
    if p.exists() and p.is_file():
        return json.loads(p.read_text()), p
    return str(x), None


def build_ctx(report, path=None, root=ROOT, data_root=None):
    """Everything a check may read. `report` may be a full report, a bare gate entry/detail, a QA report or text."""
    rep = report if isinstance(report, dict) else {}
    gate, entry = first_failure(rep) if "gates" in rep else (None, None)
    if entry is not None:
        detail = entry.get("detail")
    elif "pass" in rep and "detail" in rep:
        detail = rep["detail"]
    else:
        detail = report
    pid = (rep.get("paper") or {}).get("id") if isinstance(rep.get("paper"), dict) else None
    spath = next((c for c in (Path(root) / "offsim/papers" / str(pid) / "scenario.yaml",) if pid and c.exists()), None)
    scenario = yaml.safe_load(spath.read_text()) if spath else None
    world = (scenario or {}).get("world")
    droot = Path(data_root) if data_root else Path(root) / "data"
    return {"report": rep, "gate": gate, "entry": entry, "detail": detail, "code": classify(report), "root": Path(root),
            "data_root": droot, "world": world, "scenario_path": spath, "scenario": scenario,
            "world_dir": (droot / "worlds" / world) if world and world != "none" else None,
            "report_dir": Path(path).parent if path else None}


def _fix_command(ctx):
    d = ctx.get("detail")
    if isinstance(d, dict) and d.get("fix"):
        return d["fix"]
    w = ctx.get("world")
    return f"python -m offsim.worlds.fetch_world --pull {w}" if w and w != "none" else None


def diagnose(report_or_path, root=ROOT, data_root=None):
    """-> {code, gate, meaning, detail, checks: [{name, ok, evidence}], repairs: [...], question, ok}.
    ok=True and code=None for a report whose gates all pass. A check that raises is reported as ok=None with the error."""
    from offsim.doctor import checks as C
    report, path = load_report(report_or_path, root)
    ctx = build_ctx(report, path, root, data_root)
    code = ctx["code"]
    if code is None:
        return {"code": None, "gate": None, "meaning": None, "detail": None, "checks": [], "repairs": [], "question": None, "ok": True,
                "status": report.get("status") if isinstance(report, dict) else None}
    pb = load_playbook(code)
    out = []
    for name in pb.get("checks") or []:
        try:
            res = getattr(C, name)(ctx)
        except Exception as exc:                                              # noqa: BLE001 - a crashing check is evidence too
            res = {"ok": None, "evidence": {"check_error": f"{type(exc).__name__}: {exc}"[:300]}}
        out.append({"name": name, **res})
    return {"code": code, "gate": ctx["gate"] or pb["gate"], "meaning": meaning(code), "detail": ctx["detail"], "checks": out,
            "repairs": pb.get("repairs") or [], "question": pb.get("question"), "ok": False,
            "fix_command": _fix_command(ctx), "report_path": str(path) if path else None}


# ------------------------------------------------------------------------------------------------ repair
def _run_cmd(cmd, timeout):
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    return {"cmd": " ".join(cmd), "returncode": p.returncode, "tail": (p.stdout + p.stderr)[-400:]}


def clear_partial_downloads(root=ROOT, data_root=None):
    base = (Path(data_root) if data_root else Path(root) / "data") / "worlds"
    gone = []
    for cache in ("_osm_cache", "_gtfs_cache"):
        for f in (base / cache).glob("*") if (base / cache).exists() else []:
            if f.is_file() and (f.stat().st_size == 0 or f.suffix == ".part"):
                f.unlink()
                gone.append(str(f))
    return gone


def _default_runner(scenario_path, out, seed, data_root=None):
    from offsim import pipeline
    return pipeline.run(scenario_path, out=out, seconds=2.0, seed=seed, data_root=data_root)


def repair(report_path, max_attempts=2, run=False, runner=None, root=ROOT, data_root=None):
    """Plan (run=False) or execute (run=True) the AUTO repairs of a failing report, at most `max_attempts` that rerun the gate.

    Each executed repair is followed by a rerun of the same scenario file into <report dir>/repair-<n>/ (the failing report is
    kept); the new report is diagnosed again and the loop stops when it passes. Human repairs are never executed: they stay
    in the result with the question. diagnosis.json is written next to the report either way. `runner(scenario, out, seed)`
    is injectable for tests."""
    path = Path(report_path)
    if not path.exists():
        path = Path(root) / "out" / str(report_path) / "report.json"
    d = diagnose(path, root, data_root)
    result = {**d, "run": bool(run), "max_attempts": max_attempts, "attempts": [], "resolved": d["ok"], "planned": []}
    ctx = build_ctx(json.loads(path.read_text()), path, root, data_root)
    auto = [r for r in d["repairs"] if r.get("kind") == "auto"]
    assert all(r.get("op") in AUTO_OPS for r in auto), "auto repair with an op outside the allowed vocabulary"
    result["planned"] = [{"id": r["id"], "op": r["op"], "action": r["action"]} for r in auto]
    seed_base = 1
    n_reruns = 0
    for r in auto if run and not d["ok"] else []:
        op, att = r["op"], {"id": r["id"], "op": r["op"]}
        if op == "report_command":
            att["result"] = _fix_command(ctx) or "no fetch command recorded for this failure"
            result["attempts"].append(att)
            continue
        if n_reruns >= max_attempts:
            att["skipped"] = f"max_attempts={max_attempts} reached"
            result["attempts"].append(att)
            continue
        seed = seed_base + (n_reruns + 1 if op == "rerun_seed" else 0)
        try:
            if op == "pull_world":
                if not ctx["world"] or ctx["world"] == "none":
                    att["skipped"] = "scenario has no world"
                    result["attempts"].append(att)
                    continue
                att["result"] = _run_cmd([sys.executable, "-m", "offsim.worlds.fetch_world", "--pull", str(ctx["world"])], 900)
            elif op == "clear_partial_downloads":
                att["result"] = {"removed": clear_partial_downloads(root, data_root)}
            if ctx["scenario_path"] is None:
                att["skipped"] = "scenario file not found (offsim/papers/<paper id>/scenario.yaml): cannot rerun the gate"
                result["attempts"].append(att)
                continue
            n_reruns += 1
            out = path.parent / f"repair-{n_reruns}"
            rep2 = (runner or (lambda s, o, sd: _default_runner(s, o, sd, data_root)))(ctx["scenario_path"], out, seed)
            d2 = diagnose(rep2, root, data_root)
            att.update(seed=seed, rerun_dir=str(out), code_after=d2["code"], passed=d2["ok"])
            result["attempts"].append(att)
            if d2["ok"]:
                result["resolved"] = True
                break
        except Exception as exc:                                              # noqa: BLE001
            att["error"] = f"{type(exc).__name__}: {exc}"[:300]
            result["attempts"].append(att)
    (path.parent / "diagnosis.json").write_text(json.dumps(result, indent=1, default=str))
    return result
