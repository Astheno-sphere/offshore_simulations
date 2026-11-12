"""Lessons: every resolved failure is recorded once, with the guard that keeps it from coming back.

A lesson is `{id, date, code, symptom, cause, fix, guard, open}` in offsim/doctor/lessons.jsonl (append-only); docs/LESSONS.md
is regenerated from it. Rule (docs/SYSTEM_PLAN.md 3.2): a lesson is not closed until a guard exists, either
  - a test id `tests/test_x.py::test_name` (file exists and defines the function), or
  - a playbook check `playbook:<CODE>::<check_name>` (the playbook of CODE lists the check and checks.py defines it).
`add` refuses a lesson without an existing guard unless `open_=True`; open lessons are listed first in LESSONS.md.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATH = Path(__file__).with_name("lessons.jsonl")
DOC = ROOT / "docs" / "LESSONS.md"


class LessonRefused(ValueError):
    pass


def load(path=PATH):
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()]


def guard_exists(guard, root=ROOT):
    """True when the guard names a test function that exists, or a check listed in the playbook and defined in checks.py."""
    if not guard:
        return False
    g = str(guard).strip()
    root = Path(root)
    if g.startswith("playbook:"):
        m = re.fullmatch(r"playbook:([A-Z0-9-]+)::(\w+)", g)
        if not m:
            return False
        from offsim.doctor import PLAYBOOKS, checks
        pb = PLAYBOOKS / f"{m.group(1)}.yaml"
        if not pb.exists():
            return False
        import yaml
        return m.group(2) in (yaml.safe_load(pb.read_text()).get("checks") or []) and callable(getattr(checks, m.group(2), None))
    m = re.fullmatch(r"([\w./-]+\.py)::(\w+)(?:\[.*\])?", g)
    if not m:
        return False
    f = root / m.group(1)
    return f.exists() and re.search(rf"^\s*(async\s+)?def {re.escape(m.group(2))}\b", f.read_text(), re.M) is not None


def add(code, symptom, cause, fix, guard=None, open_=False, path=PATH, doc=DOC, root=ROOT, date=None):
    from offsim.doctor.codes import CODES
    if code not in CODES:
        raise LessonRefused(f"unknown code {code!r}; codes: {', '.join(CODES)}")
    for name, val in (("symptom", symptom), ("cause", cause), ("fix", fix)):
        if not str(val or "").strip():
            raise LessonRefused(f"--{name} is required")
    if not open_ and not guard_exists(guard, root):
        raise LessonRefused("a lesson needs a guard that exists: a test id 'tests/test_x.py::test_name' or a playbook check "
                            "'playbook:CODE::check_name'. Add the guard first, or record the lesson with --open "
                            "(it is listed as open until a guard exists).")
    items = load(path)
    rec = {"id": len(items) + 1, "date": date or dt.date.today().isoformat(), "code": code, "symptom": symptom.strip(),
           "cause": cause.strip(), "fix": fix.strip(), "guard": (guard or "").strip() or None, "open": bool(open_ and not guard_exists(guard, root))}
    with Path(path).open("a") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    write_doc(path, doc)
    return rec


def render(items=None):
    items = load() if items is None else items
    opn = [x for x in items if x.get("open")]
    lines = ["# LESSONS", "",
             "Generated from `offsim/doctor/lessons.jsonl` by `python -m offsim learn` (offsim.doctor.lessons). Do not edit by hand.",
             "A lesson is closed only when its guard (a test or a playbook check) exists. Open lessons come first.", ""]
    lines += [f"{len(items)} lessons, {len(opn)} open.", ""]
    if opn:
        lines += ["## Open (no guard yet)", ""]
        lines += [_entry(x) for x in opn]
    by = {}
    for x in items:
        if not x.get("open"):
            by.setdefault(x["code"], []).append(x)
    for code in sorted(by):
        lines += [f"## {code}", ""] + [_entry(x) for x in by[code]]
    return "\n".join(lines).rstrip() + "\n"


def _entry(x):
    g = f"`{x['guard']}`" if x.get("guard") else "none yet"
    return (f"### L{x['id']} ({x['date']}) {x['code']}\n\n- Symptom: {x['symptom']}\n- Cause: {x['cause']}\n- Fix: {x['fix']}\n"
            f"- Guard: {g}\n")


def write_doc(path=PATH, doc=DOC):
    Path(doc).write_text(render(load(path)))
