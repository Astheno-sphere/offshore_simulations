"""Command line for the doctor. `main(argv) -> int` (offsim.__main__ routes `doctor` and `learn` here).

    doctor <report.json | paper_id | text> [--repair [--dry-run]] [--json]
    learn --code C --symptom S --cause X --fix F --guard tests/test_x.py::test_y [--open]

argv may start with the sub-command (`["doctor", "out/p/report.json"]`) or omit it: arguments with --code/--symptom mean
`learn`, anything else means `doctor`. Exit codes: 0 report passes or the repair resolved it, 1 a failure remains (diagnosed),
2 refused (learn without a guard) or input not found.
`--repair` executes the AUTO repairs (at most --max-attempts gate reruns, default 2); `--repair --dry-run` only plans them.
Both write diagnosis.json next to the report. Human repairs are only ever printed, with the one question.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _print_diag(d, out):
    if d["ok"]:
        print("doctor: all gates pass, nothing to diagnose", file=out)
        return
    print(f"{d['code']}  ({d['gate']})  {d['meaning']}", file=out)
    for c in d["checks"]:
        mark = {True: "ok ", False: "BAD", None: "?  "}[c["ok"]]
        ev = json.dumps(c["evidence"], default=str)
        print(f"  [{mark}] {c['name']}: {ev[:260]}", file=out)
    for r in d["repairs"]:
        print(f"  ({r['kind']:5}) {r['id']}: {r['action']}", file=out)
    if d.get("fix_command"):
        print(f"  fetch: {d['fix_command']}", file=out)
    print(f"  ask: {d['question']}", file=out)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv and argv[0] in ("doctor", "learn") else ("learn" if any(a.startswith(("--code", "--symptom")) for a in argv) else "doctor")
    if argv and argv[0] in ("doctor", "learn"):
        argv = argv[1:]
    out = sys.stdout
    if cmd == "learn":
        from offsim.doctor import lessons
        ap = argparse.ArgumentParser(prog="offsim learn")
        ap.add_argument("--code", required=True)
        ap.add_argument("--symptom", required=True)
        ap.add_argument("--cause", required=True)
        ap.add_argument("--fix", required=True)
        ap.add_argument("--guard", default=None, help="tests/test_x.py::test_name or playbook:CODE::check_name")
        ap.add_argument("--open", action="store_true", help="record without a guard; listed as open in docs/LESSONS.md")
        a = ap.parse_args(argv)
        try:
            rec = lessons.add(a.code, a.symptom, a.cause, a.fix, a.guard, open_=a.open)
        except lessons.LessonRefused as exc:
            print(f"learn: refused: {exc}", file=sys.stderr)
            return 2
        print(f"learn: L{rec['id']} {rec['code']} recorded ({'open' if rec['open'] else 'guard: ' + rec['guard']}); docs/LESSONS.md updated", file=out)
        return 0
    from offsim import doctor
    ap = argparse.ArgumentParser(prog="offsim doctor")
    ap.add_argument("target", help="report.json, a paper id (out/<id>/report.json) or an error text")
    ap.add_argument("--repair", action="store_true", help="execute the auto repairs (at most 2 gate reruns), write diagnosis.json")
    ap.add_argument("--dry-run", action="store_true", help="with --repair: only plan the auto repairs")
    ap.add_argument("--max-attempts", type=int, default=2)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    report, path = doctor.load_report(a.target)
    if path is None and isinstance(report, str) and Path(a.target).suffix == ".json":
        print(f"doctor: {a.target} not found", file=sys.stderr)
        return 2
    if a.repair:
        if path is None:
            print("doctor: --repair needs a report.json or paper id", file=sys.stderr)
            return 2
        d = doctor.repair(path, max_attempts=a.max_attempts, run=not a.dry_run)
        if a.json:
            print(json.dumps(d, indent=1, default=str), file=out)
        else:
            _print_diag(d, out)
            for r in d["planned"] if a.dry_run else []:
                print(f"  would run: {r['id']} ({r['op']})", file=out)
            for t in d["attempts"]:
                print(f"  ran: {json.dumps(t, default=str)[:300]}", file=out)
            print(f"  resolved: {d['resolved']}  (diagnosis.json written)", file=out)
        return 0 if d["resolved"] else 1
    d = doctor.diagnose(report if path is None else path)
    if path is not None:
        (path.parent / "diagnosis.json").write_text(json.dumps(d, indent=1, default=str))
    if a.json:
        print(json.dumps(d, indent=1, default=str), file=out)
    else:
        _print_diag(d, out)
    return 0 if d["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
