"""Studio: the conductor that carries one paper from feed to publish.

    funnel.yaml   the stages as data
    ledger.py     offsim/papers/<id>/state.json (append-only history, blockers, decisions)
    conductor.py  status / next_step / advance

This module holds what both share: loading the funnel, template context, exit checks and stage derivation from
the artefacts on disk (so a paper without a state file still gets a correct stage).
"""
import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
FUNNEL = Path(__file__).with_name("funnel.yaml")
KINDS = ("auto", "decide")
TIERS = ("haiku", "sonnet", "opus")
REQUIRED = ("id", "kind", "command", "inputs", "outputs", "exit", "owner", "model")


def load_funnel(path=None):
    stages = yaml.safe_load(Path(path or FUNNEL).read_text())["stages"]
    seen = set()
    for s in stages:
        missing = [k for k in REQUIRED if k not in s]
        if missing:
            raise ValueError(f"funnel stage {s.get('id')}: missing {missing}")
        if s["id"] in seen:
            raise ValueError(f"funnel: duplicate stage {s['id']}")
        seen.add(s["id"])
        if s["kind"] not in KINDS or s["model"] not in TIERS:
            raise ValueError(f"funnel stage {s['id']}: bad kind/model")
    return stages


def stage_ids(stages=None):
    return [s["id"] for s in (stages or load_funnel())]


def papers_dir(root=None):
    return Path(root or ROOT) / "offsim" / "papers"


def paper_ids(root=None):
    """Paper folders: not templates (leading underscore), holding at least one file."""
    d = papers_dir(root)
    if not d.is_dir():
        return []
    return sorted(p.name for p in d.iterdir() if p.is_dir() and not p.name.startswith(("_", "."))
                  and any(f.is_file() for f in p.iterdir()))


def _yaml(path):
    try:
        return yaml.safe_load(Path(path).read_text()) or {}
    except Exception:
        return {}


def context(paper_id, root=None):
    """Template variables for one paper; every value is a repo-relative string."""
    root = Path(root or ROOT)
    pd = f"offsim/papers/{paper_id}"
    sb_path = root / pd / "storyboard.yaml"
    sb = _yaml(sb_path) if sb_path.is_file() else {}
    own_out = f"out/{paper_id}"
    sb_run = str(sb.get("run") or own_out).rstrip("/")
    report = f"{own_out}/report.json"
    if not (root / report).is_file() and (root / sb_run / "report.json").is_file():
        report = f"{sb_run}/report.json"
    pdfs = sorted((root / pd).glob("*.pdf")) if (root / pd).is_dir() else []
    pdf = str(pdfs[0].relative_to(root)) if pdfs else f"{pd}/paper.pdf"
    return {"id": paper_id, "paper_dir": pd, "out": own_out, "scenario": f"{pd}/scenario.yaml",
            "storyboard": f"{pd}/storyboard.yaml", "experiment": f"{pd}/experiment.yaml", "pdf": pdf,
            "report": report, "film": f"{sb_run}/{sb.get('id', paper_id)}_{sb.get('format', 'square')}.mp4"}


class _Safe(dict):
    def __missing__(self, k):
        return "{" + k + "}"


def render(template, ctx):
    return str(template).format_map(_Safe(ctx)) if template is not None else None


def gates_pass(report_path):
    """True when the report exists, did not stop at a gate, and every gate except 4_paper passed."""
    try:
        rep = json.loads(Path(report_path).read_text())
    except Exception:
        return False, "no readable report"
    gates = rep.get("gates") or {}
    bad = [g for g, v in gates.items() if g != "4_paper" and not v.get("pass")]
    if not gates:
        return False, "report has no gates"
    if bad:
        return False, "gate failed: " + ", ".join(bad)
    if str(rep.get("status") or "").startswith("stopped"):
        return False, str(rep["status"])
    return True, str(rep.get("status"))


def check_exit(spec, ctx, root=None, decisions=(), stage_id=None):
    """Evaluate an exit spec -> (ok, why). `decisions` is the ledger's decision list."""
    root = Path(root or ROOT)
    if "any" in spec:
        res = [check_exit(s, ctx, root, decisions, stage_id) for s in spec["any"]]
        return any(r[0] for r in res), " or ".join(r[1] for r in res)
    if "all" in spec:
        res = [check_exit(s, ctx, root, decisions, stage_id) for s in spec["all"]]
        return all(r[0] for r in res), "; ".join(r[1] for r in res)
    if "file" in spec:
        files = [render(f, ctx) for f in spec["file"]]
        miss = [f for f in files if not (root / f).is_file()]
        return not miss, ("missing " + ", ".join(miss)) if miss else "files present"
    if "report" in spec:
        ok, why = gates_pass(root / ctx["report"])
        return ok, why
    if spec.get("decision"):
        ok = any(d.get("stage") == stage_id for d in decisions)
        return ok, "decision recorded" if ok else "no decision recorded"
    return False, "unknown exit spec"


def stage_done(stage, ctx, root=None, decisions=()):
    spec = stage["exit"]
    if stage["kind"] == "decide" and not stage.get("decision_completes", True) and "decision" in spec:
        spec = {"file": []}
    return check_exit(spec, ctx, root, decisions, stage["id"])


def derive_stage(paper_id, root=None, decisions=(), stages=None):
    """-> (current stage id or None when everything is done, {stage_id: (done, why)}).

    Current = the stage after the furthest stage whose exit check passes, so papers that skipped optional
    stages (demo papers have no gap or experiment) still land on the right step.
    """
    stages = stages or load_funnel()
    ctx = context(paper_id, root)
    marks = {s["id"]: stage_done(s, ctx, root, decisions) for s in stages}
    last = max((i for i, s in enumerate(stages) if marks[s["id"]][0]), default=-1)
    cur = stages[last + 1]["id"] if last + 1 < len(stages) else None
    return cur, marks
