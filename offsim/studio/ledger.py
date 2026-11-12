"""Per-paper ledger: offsim/papers/<id>/state.json.

    {paper_id, stage, history:[{t_utc, stage, event, detail, by}], artefacts:{path: sha256},
     blockers:[{code, detail, since, stage}], decisions:[{t_utc, stage, note, by}], next}

History and decisions are append-only (save() refuses a state that drops or edits earlier entries). Writes are
atomic (temp file + os.replace). When no state file exists, load() derives the stage from the artefacts on disk,
so existing papers get a correct state without setup; nothing is written until the first record/block/decide.
"""
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import ROOT, context, derive_stage, load_funnel, render


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def state_path(paper_id, root=None):
    return Path(root or ROOT) / "offsim" / "papers" / paper_id / "state.json"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _empty(paper_id):
    return {"paper_id": paper_id, "stage": None, "history": [], "artefacts": {}, "blockers": [],
            "decisions": [], "next": None}


def _read(paper_id, root):
    p = state_path(paper_id, root)
    if p.is_file():
        st = json.loads(p.read_text())
        for k, v in _empty(paper_id).items():
            st.setdefault(k, v)
        return st
    return None


def next_action(stage_id, paper_id, root=None, stages=None):
    stages = stages or load_funnel()
    s = next((x for x in stages if x["id"] == stage_id), None)
    if s is None:
        return None
    ctx = context(paper_id, root)
    if s["kind"] == "decide":
        return f"decide: python -m offsim decide {paper_id} {s['id']} --note ..."
    if s.get("command"):
        return render(s["command"], ctx)
    return f"[{s['owner']}] produce " + ", ".join(render(o, ctx) for o in s["outputs"])


def load(paper_id, root=None):
    """Stored state if present, else a derived one. `stage` and `next` are always recomputed from disk."""
    root = Path(root or ROOT)
    st = _read(paper_id, root)
    derived = st is None
    st = st or _empty(paper_id)
    stage, _ = derive_stage(paper_id, root, st["decisions"])
    st["stage"] = stage or "done"
    st["next"] = next_action(stage, paper_id, root) if stage else None
    st["derived"] = derived
    return st


def save(st, root=None):
    """Atomic write; refuses to shorten or alter history/decisions already on disk."""
    root = Path(root or ROOT)
    st = {k: v for k, v in st.items() if k != "derived"}
    p = state_path(st["paper_id"], root)
    old = _read(st["paper_id"], root)
    if old:
        for key in ("history", "decisions"):
            if st[key][:len(old[key])] != old[key]:
                raise ValueError(f"ledger {key} is append-only: refusing to rewrite earlier entries")
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".state.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(st, f, indent=2, sort_keys=False)
            f.write("\n")
        os.replace(tmp, p)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return p


def _hash_outputs(st, stage_id, root, stages=None):
    ctx = context(st["paper_id"], root)
    for s in (stages or load_funnel()):
        if s["id"] == stage_id:
            for o in s["outputs"]:
                rel = render(o, ctx)
                if (Path(root) / rel).is_file():
                    st["artefacts"][rel] = sha256(Path(root) / rel)


def _commit(st, root):
    stage, _ = derive_stage(st["paper_id"], root, st["decisions"])
    st["stage"] = stage or "done"
    st["next"] = next_action(stage, st["paper_id"], root) if stage else None
    save(st, root)
    st["derived"] = False
    return st


def record(paper_id, stage, event, detail="", by="conductor", root=None):
    """Append a history entry and refresh artefact hashes for the stage's outputs."""
    root = Path(root or ROOT)
    st = _read(paper_id, root) or _empty(paper_id)
    st["history"].append({"t_utc": now(), "stage": stage, "event": event, "detail": str(detail), "by": by})
    _hash_outputs(st, stage, root)
    return _commit(st, root)


def block(paper_id, code, detail="", stage=None, root=None, by="conductor"):
    root = Path(root or ROOT)
    st = _read(paper_id, root) or _empty(paper_id)
    st["blockers"] = [b for b in st["blockers"] if b["code"] != code]
    st["blockers"].append({"code": code, "detail": str(detail), "since": now(), "stage": stage})
    st["history"].append({"t_utc": now(), "stage": stage, "event": "blocked", "detail": f"{code}: {detail}", "by": by})
    return _commit(st, root)


def unblock(paper_id, code=None, root=None, by="conductor"):
    """Clear one blocker by code, or all when code is None."""
    root = Path(root or ROOT)
    st = _read(paper_id, root) or _empty(paper_id)
    gone = [b for b in st["blockers"] if code is None or b["code"] == code]
    if not gone:
        return st
    st["blockers"] = [b for b in st["blockers"] if b not in gone]
    st["history"].append({"t_utc": now(), "stage": gone[0].get("stage"), "event": "unblocked",
                          "detail": ",".join(b["code"] for b in gone), "by": by})
    return _commit(st, root)


def decide(paper_id, stage, note, by="human", root=None):
    root = Path(root or ROOT)
    if stage not in [s["id"] for s in load_funnel()]:
        raise ValueError(f"unknown stage {stage!r}")
    st = _read(paper_id, root) or _empty(paper_id)
    st["decisions"].append({"t_utc": now(), "stage": stage, "note": note, "by": by})
    st["history"].append({"t_utc": now(), "stage": stage, "event": "decided", "detail": note, "by": by})
    return _commit(st, root)
