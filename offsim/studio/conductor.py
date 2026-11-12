"""Conductor: status of every paper, the next step of one, and advance (run auto stages until something needs a human).

    status(root)                      -> {"papers": [row, ...], "stale_branches": [...]}
    next_step(id, root)               -> {"stage", "kind", "command", "why", "blocked", ...}
    advance(id, dry_run=True, ...)    -> {"steps": [...], "stopped": {...}}

Nothing is executed unless advance(dry_run=False). A failed `run` stage is handed to offsim.doctor.diagnose
(if that module exists) and its code is recorded as a blocker.
"""
import importlib
import os
import shlex
import subprocess
import sys
from pathlib import Path

from . import ROOT, check_exit, context, derive_stage, load_funnel, paper_ids, render, stage_done
from . import ledger


def _exec(argv, root):
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(p for p in (str(root), env.get("PYTHONPATH", "")) if p)
    return subprocess.run(argv, cwd=root, env=env).returncode


def _argv(command, ctx):
    argv = shlex.split(render(command, ctx))
    if argv and argv[0] in ("python", "python3"):
        argv[0] = sys.executable
    return argv


def _stage(stage_id, stages):
    return next(s for s in stages if s["id"] == stage_id)


def _missing_inputs(stage, ctx, root):
    return [render(i, ctx) for i in stage["inputs"] if not (Path(root) / render(i, ctx)).exists()]


def _stale(st, root):
    """Artefacts whose recorded hash no longer matches the file on disk."""
    return [p for p, h in st["artefacts"].items()
            if (Path(root) / p).is_file() and ledger.sha256(Path(root) / p) != h]


def stale_branches(root=None):
    """Data branches (origin/papers/*) ahead of main, via git. [] when git or the refs are unavailable."""
    root = Path(root or ROOT)

    def git(*a):
        r = subprocess.run(["git", "-C", str(root), *a], capture_output=True, text=True)
        return r.stdout.strip() if r.returncode == 0 else ""
    base = next((b for b in ("origin/main", "main") if git("rev-parse", "--verify", "-q", b)), None)
    if not base:
        return []
    out = []
    for ref in git("for-each-ref", "--format=%(refname:short)", "refs/remotes/origin/papers",
                   "refs/heads/papers").splitlines():
        n = git("rev-list", "--count", f"{base}..{ref}")
        if n.isdigit() and int(n) > 0:
            out.append({"branch": ref, "ahead": int(n), "base": base})
    return out


def next_step(paper_id, root=None):
    root = Path(root or ROOT)
    stages = load_funnel()
    st = ledger.load(paper_id, root)
    stage_id, marks = derive_stage(paper_id, root, st["decisions"], stages)
    if stage_id is None:
        return {"paper_id": paper_id, "stage": "done", "kind": None, "command": None, "why": "all stages complete",
                "blocked": [], "planned": False}
    s = _stage(stage_id, stages)
    ctx = context(paper_id, root)
    cmd = render(s.get("command"), ctx)
    missing = _missing_inputs(s, ctx, root)
    why = s["why"]
    if s["kind"] == "decide":
        why = f"{s['question']} ({'decision recorded, ' if any(d['stage'] == stage_id for d in st['decisions']) else ''}"\
              f"record with: python -m offsim decide {paper_id} {stage_id} --note ...)"
    elif not cmd:
        why += f" Owner skill: skills/{s['owner']} (no CLI; it must produce {', '.join(render(o, ctx) for o in s['outputs'])})."
    elif s.get("planned"):
        why += " Command is planned, not implemented yet."
    if not marks[stage_id][0] and stage_id == "run":
        rep = Path(root) / ctx["report"]
        if rep.is_file():
            why += f" Last report: {marks[stage_id][1]}."
    return {"paper_id": paper_id, "stage": stage_id, "kind": s["kind"], "command": cmd,
            "precheck": render(s.get("precheck"), ctx), "why": why, "owner": s["owner"], "model": s["model"],
            "missing_inputs": missing, "blocked": st["blockers"], "planned": bool(s.get("planned")),
            "stale": _stale(st, root)}


def status(root=None):
    root = Path(root or ROOT)
    rows = []
    for pid in paper_ids(root):
        st = ledger.load(pid, root)
        nx = next_step(pid, root)
        rows.append({"paper_id": pid, "stage": st["stage"], "kind": nx["kind"],
                     "blockers": [b["code"] for b in st["blockers"]], "next": nx["command"] or nx["why"],
                     "stale": nx.get("stale", []), "state_file": not st["derived"], "events": len(st["history"])})
    return {"papers": rows, "stale_branches": stale_branches(root)}


def format_status(res):
    rows = res["papers"]
    lines = []
    if rows:
        w = max(len(r["paper_id"]) for r in rows)
        lines.append(f"{'paper':{w}}  {'stage':10} {'kind':6} {'blockers':24} next")
        for r in rows:
            blk = ",".join(r["blockers"]) or "-"
            lines.append(f"{r['paper_id']:{w}}  {r['stage']:10} {(r['kind'] or '-'):6} {blk:24} {r['next']}")
            if r["stale"]:
                lines.append(f"{'':{w}}  stale artefacts (changed since last record): {', '.join(r['stale'])}")
    else:
        lines.append("no papers under offsim/papers")
    for b in res["stale_branches"]:
        lines.append(f"STALE data branch: {b['branch']} is {b['ahead']} commit(s) ahead of {b['base']} (merge it)")
    return "\n".join(lines)


def _diagnose(report_path):
    """offsim.doctor.diagnose(report) if the module exists, else None."""
    try:
        doctor = importlib.import_module("offsim.doctor")
    except ImportError as exc:
        if not (exc.name or "").startswith("offsim.doctor"):
            raise
        return None
    fn = getattr(doctor, "diagnose", None)
    if fn is None:
        return None
    try:
        return fn(str(report_path))
    except Exception as exc:                      # a broken doctor must not hide the original failure
        return {"code": "DOCTOR-ERROR", "question": f"{type(exc).__name__}: {exc}"}


def advance(paper_id, dry_run=True, max_steps=5, root=None):
    """Run auto stages in order. Stops at a decide stage, a stage without a CLI, a planned command, a missing
    input, a failed command or a failed exit check. dry_run=True simulates, assuming each step succeeds."""
    root = Path(root or ROOT)
    stages = load_funnel()
    steps, stopped = [], None
    assumed, skipped, produced = set(), set(), set()   # dry run: stages assumed done / optional stages skipped
    for _ in range(max_steps):
        st = ledger.load(paper_id, root)
        stage_id, _ = derive_stage(paper_id, root, st["decisions"], stages)
        ids = [s["id"] for s in stages]
        while stage_id in assumed or stage_id in skipped:
            i = ids.index(stage_id) + 1
            stage_id = ids[i] if i < len(ids) else None
        if stage_id is None:
            stopped = {"reason": "complete", "stage": None, "detail": "all stages done"}
            break
        s = _stage(stage_id, stages)
        ctx = context(paper_id, root)
        cmd = render(s.get("command"), ctx)
        if s["kind"] == "decide":
            stopped = {"reason": "decision", "stage": stage_id, "detail": s["question"]}
            if any(d["stage"] == stage_id for d in st["decisions"]) and cmd and not s.get("planned"):
                stopped = None                     # approved; fall through and run the command
            else:
                if any(d["stage"] == stage_id for d in st["decisions"]) and s.get("planned"):
                    stopped = {"reason": "planned", "stage": stage_id, "detail": f"approved, but `{cmd}` is not implemented yet"}
                break
        if not cmd:
            stopped = {"reason": "needs-owner", "stage": stage_id,
                       "detail": f"no CLI; skills/{s['owner']} must produce {', '.join(render(o, ctx) for o in s['outputs'])}"}
            break
        missing = [m for m in _missing_inputs(s, ctx, root) if m not in produced]
        if missing and s.get("optional"):
            skipped.add(stage_id)                  # an optional stage without its inputs is not part of this paper's journey
            steps.append({"stage": stage_id, "commands": [], "status": "skipped (optional, missing " + ", ".join(missing) + ")"})
            continue
        if missing:
            stopped = {"reason": "missing-input", "stage": stage_id, "detail": "missing " + ", ".join(missing)}
            if not dry_run:
                ledger.block(paper_id, "INPUT-MISSING", stopped["detail"], stage=stage_id, root=root)
            break
        if s.get("planned"):
            stopped = {"reason": "planned", "stage": stage_id, "detail": f"`{cmd}` is planned, not implemented yet"}
            break
        cmds = [c for c in (s.get("precheck"), s.get("command")) if c]
        if dry_run:
            steps.append({"stage": stage_id, "commands": [render(c, ctx) for c in cmds], "status": "would-run"})
            assumed.add(stage_id)
            produced.update(render(o, ctx) for o in s["outputs"])
            continue
        ledger.record(paper_id, stage_id, "start", " && ".join(render(c, ctx) for c in cmds), root=root)
        rc = 0
        for c in cmds:
            rc = _exec(_argv(c, ctx), root)
            if rc:
                break
        steps.append({"stage": stage_id, "commands": [render(c, ctx) for c in cmds], "status": "ok" if not rc else "failed",
                      "rc": rc})
        if rc:
            code, detail = f"{stage_id.upper()}-FAILED", f"exit code {rc}"
            if stage_id == "run":
                diag = _diagnose(root / ctx["report"])
                if diag:
                    code, detail = diag.get("code") or code, diag.get("question") or str(diag.get("checks", detail))
                elif (root / ctx["report"]).is_file():
                    ok, why = check_exit(s["exit"], ctx, root)
                    code, detail = "RUN-GATE-FAILED", why
            ledger.block(paper_id, code, detail, stage=stage_id, root=root)
            ledger.record(paper_id, stage_id, "failed", f"{code}: {detail}", root=root)
            stopped = {"reason": "failed", "stage": stage_id, "detail": f"{code}: {detail}"}
            break
        st = ledger.load(paper_id, root)
        ok, why = stage_done(s, ctx, root, st["decisions"])
        if not ok:
            ledger.block(paper_id, "EXIT-CHECK-FAILED", f"{stage_id}: {why}", stage=stage_id, root=root)
            ledger.record(paper_id, stage_id, "exit-check-failed", why, root=root)
            steps[-1]["status"] = "exit-check-failed"
            stopped = {"reason": "exit-check", "stage": stage_id, "detail": why}
            break
        for b in st["blockers"]:
            if b.get("stage") == stage_id:
                ledger.unblock(paper_id, b["code"], root=root)
        ledger.record(paper_id, stage_id, "done", why, root=root)
    else:
        stopped = {"reason": "max-steps", "stage": None, "detail": f"stopped after {max_steps} step(s)"}
    return {"paper_id": paper_id, "dry_run": dry_run, "steps": steps, "stopped": stopped}
