"""offsim command line: one entry point for every capability. A paper flows top to bottom.

Paper
    python -m offsim paper <paper.pdf> [--out DIR]                        # PDF -> paper extract with page sources
Run
    python -m offsim run <scenario.yaml> [--out DIR] [--seconds S]       # gated pipeline -> report.json
Experiment
    python -m offsim experiment <experiment.yaml> [--engine NAME] [--workers N]   # pre-registered comparison -> decision JSON
Film
    python -m offsim story <storyboard.yaml> [--dry-run]                 # motion: shots -> final video
    python -m offsim film <storyboard.yaml> [--muse unlisted]            # run -> check -> render -> grade -> upload
Data
    python -m offsim world --place NAME [--modes sea,road] [...]         # fetch a world (its own --help)
    python -m offsim layer --world W --kind K --file F --src S --licence L   # your own GeoJSON as a world layer
    python -m offsim timetable <timetable.yaml> --out DIR                # paper timetable -> GTFS
    python -m offsim entur collect|departures [...]                      # Entur realtime
Research
    python -m offsim feed [--queries Q --out O --since D]                # literature feed -> papers/feed.jsonl
    python -m offsim tag [--feed F --out O]                              # rule-tag the feed -> papers/tags.jsonl
    python -m offsim gaps [--tags T --out O --min-support N]             # gap table and gap list
Publish
    python -m offsim article <paper_id|report.json> [--template linkedin|thought|readme_entry] [--out FILE] [--figure PNG ...]
                                                                         # report refs -> markdown article (every number a ref)
    python -m offsim publish <paper_id> [--muse] [--video FILE]          # article + figures + manifest.json -> out/<id>/publish/
Studio
    python -m offsim status                                              # board of all papers: stage, blockers, next action
    python -m offsim next <id>                                           # the next command for one paper, and why
    python -m offsim advance <id> [--run] [--max-steps N]                # run auto stages (dry-run unless --run)
    python -m offsim decide <id> <stage> --note TEXT                     # record a human decision at a decide stage
    python -m offsim doctor|learn [...]                                  # diagnose a failed run; capture a lesson (offsim.doctor)
    python -m offsim live [...]                                          # probe the outside world (offsim.live)
Inspect
    python -m offsim tools                                               # solver and engine import status
    python -m offsim catalog --find X                                    # search the tool catalog
    python -m offsim resume [--tests]                                    # after any interruption: state + next step

Commands with their own argparse (world, layer, feed, tag, gaps, entur, catalog, doctor, learn, live) pass their remaining arguments
through unchanged, so `python -m offsim world --help` shows the target's help.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _with_root_on_path():
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(p for p in (str(ROOT), env.get("PYTHONPATH", "")) if p)
    return env


def _subprocess_cli(module):
    """For targets whose argparse runs at import time under __main__ (no main(argv))."""
    def run(args):
        return subprocess.call([sys.executable, "-m", module, *args], env=_with_root_on_path())
    return run


def _feed(args):
    from offsim.feed.run import main
    return main(args)


def _tag(args):
    from offsim.research.tags import main
    return main(args)


def _gaps(args):
    from offsim.research.gaps import main
    return main(args)


def _entur(args):
    from offsim.transit.entur import main
    return main(args)


def _catalog(args):
    return subprocess.call([sys.executable, str(ROOT / "tools/catalog_build.py"), *args], cwd=ROOT,
                           env=_with_root_on_path())


def _lazy(module, label, prefix=()):
    """Passthrough to <module>.main(argv); exit 2 with a clear message when the module is not in this checkout."""
    def run(args):
        import importlib
        try:
            mod = importlib.import_module(module)
        except ImportError as exc:
            if not (exc.name and (module == exc.name or module.startswith(exc.name + "."))):
                raise                       # the module exists but one of its own imports is broken
            print(f"offsim {label}: {module} is not available in this checkout; nothing was run.", file=sys.stderr)
            return 2
        return mod.main([*prefix, *args])
    return run


# name -> (handler(args) -> int, one-line help). Dispatched before argparse so their flags and --help pass through.
PASSTHROUGH = {
    "world": (_subprocess_cli("offsim.worlds.fetch_world"), "fetch a world: place, modes, OSM, GTFS, metocean"),
    "layer": (_subprocess_cli("offsim.worlds.user_layers"), "your own GeoJSON as a world layer, with provenance"),
    "feed": (_feed, "literature feed -> papers/feed.jsonl"),
    "tag": (_tag, "rule-tag papers/feed.jsonl -> papers/tags.jsonl"),
    "gaps": (_gaps, "gap table and gap list from papers/tags.jsonl"),
    "entur": (_entur, "Entur realtime: collect | departures"),
    "catalog": (_catalog, "search the tool catalog (tools/catalog_build.py --find X)"),
}

# Optional modules owned by other packages: dispatched like PASSTHROUGH, but absent modules give exit 2 and a message.
LAZY = {
    "doctor": (_lazy("offsim.doctor.cli", "doctor"), "diagnose a failed gate or report: code, checks, repairs, question"),
    "learn": (_lazy("offsim.doctor.cli", "learn", prefix=("learn",)), "record a resolved failure as a lesson with its guard test"),
    "live": (_lazy("offsim.live.cli", "live"), "probe the outside world (data hosts, APIs, runners)"),
}


def build_parser():
    ap = argparse.ArgumentParser(prog="offsim", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("paper", help="PDF -> paper extract with page sources (offsim.intake.paper)")
    p.add_argument("pdf")
    p.add_argument("--out", metavar="DIR")
    r = sub.add_parser("run", help="scenario.yaml -> gates -> report.json")
    r.add_argument("scenario")
    r.add_argument("--out")
    r.add_argument("--seconds", type=float, default=2.0)
    e = sub.add_parser("experiment", help="experiment.yaml -> ensemble -> decision JSON")
    e.add_argument("experiment")
    e.add_argument("--engine", metavar="NAME", help="run every variant on this engine")
    e.add_argument("--workers", type=int, default=1)
    e.add_argument("--out", metavar="FILE", help="also write the decision JSON to this file")
    s = sub.add_parser("story", help="storyboard.yaml -> shots -> final video")
    s.add_argument("storyboard")
    s.add_argument("--dry-run", action="store_true")
    f = sub.add_parser("film", help="scenario -> gates -> storyboard -> MP4 [-> muse.ai]: the whole brain in one command")
    f.add_argument("storyboard")
    f.add_argument("--seconds", type=float, default=2.0, help="solver time")
    f.add_argument("--muse", choices=["public", "unlisted", "private"], help="upload to muse.ai (needs MUSE_AI_KEY)")
    ar = sub.add_parser("article", help="report.json -> markdown article from refs only (offsim.publish.article)")
    ar.add_argument("target", help="paper id or path to report.json")
    ar.add_argument("--template", default="linkedin", choices=["linkedin", "thought", "readme_entry"])
    ar.add_argument("--out", metavar="FILE", help="default: offsim/papers/<id>/article.md (or beside report.json)")
    ar.add_argument("--figure", action="append", default=[], metavar="PNG", help="a still or frame the film produced (repeatable)")
    ar.add_argument("--lang", default="en")
    pu = sub.add_parser("publish", help="article + figures + manifest.json -> out/<id>/publish/; --muse uploads the video")
    pu.add_argument("paper_id")
    pu.add_argument("--muse", action="store_true", help="upload the film to muse.ai (needs MUSE_AI_KEY; otherwise skipped)")
    pu.add_argument("--video", metavar="FILE", help="default: the film path from the storyboard, if it exists")
    pu.add_argument("--article", metavar="FILE", help="default: offsim/papers/<id>/article.md")
    t = sub.add_parser("timetable", help="timetable.yaml from a paper -> GTFS folder")
    t.add_argument("timetable")
    t.add_argument("--out", metavar="DIR", required=True)
    for name, (_, text) in {**PASSTHROUGH, **LAZY}.items():
        sub.add_parser(name, help=text, add_help=False)
    sub.add_parser("status", help="board of all papers: stage, blockers, next action, stale data branches")
    nx = sub.add_parser("next", help="the next command for one paper, and why")
    nx.add_argument("paper_id")
    ad = sub.add_parser("advance", help="run auto stages for a paper until a decision, failure or blocker (dry-run unless --run)")
    ad.add_argument("paper_id")
    ad.add_argument("--run", action="store_true", help="execute the commands (default: only show them)")
    ad.add_argument("--max-steps", type=int, default=5)
    dc = sub.add_parser("decide", help="record a human decision at a funnel stage")
    dc.add_argument("paper_id")
    dc.add_argument("stage")
    dc.add_argument("--note", required=True)
    dc.add_argument("--by", default="human")
    sub.add_parser("tools", help="solver and engine import status (offsim.engines.available)")
    rs = sub.add_parser("resume", help="where are we: branch, unpushed, worktrees, open roadmap, risks, next command")
    rs.add_argument("--tests", action="store_true", help="also run the test suite")
    return ap


def _studio(a):
    from offsim.studio import conductor, ledger
    if a.cmd == "status":
        print(conductor.format_status(conductor.status()))
        return 0
    if a.cmd == "next":
        n = conductor.next_step(a.paper_id)
        print(f"{n['paper_id']}: stage {n['stage']} ({n['kind']})")
        print(f"command: {n['command'] or '(none)'}")
        print(f"why: {n['why']}")
        for k in ("missing_inputs", "blocked", "stale"):
            if n.get(k):
                print(f"{k}: {n[k]}")
        return 0
    if a.cmd == "decide":
        try:
            ledger.decide(a.paper_id, a.stage, a.note, by=a.by)
        except ValueError as exc:
            print(f"offsim decide: {exc}", file=sys.stderr)
            return 2
        print(f"decision recorded for {a.paper_id} at {a.stage}")
        return 0
    res = conductor.advance(a.paper_id, dry_run=not a.run, max_steps=a.max_steps)
    tag = "would run" if res["dry_run"] else "ran"
    for s in res["steps"]:
        if not s["commands"]:
            print(f"[{s['stage']}] {s['status']}")
            continue
        print(f"[{s['stage']}] {tag}: " + " && ".join(s["commands"]) + (f"  -> {s['status']}" if not res["dry_run"] else ""))
    sp = res["stopped"]
    print(f"stopped: {sp['reason']}" + (f" at {sp['stage']}" if sp["stage"] else "") + f" - {sp['detail']}")
    return 1 if sp["reason"] in ("failed", "exit-check", "missing-input") and not res["dry_run"] else 0


def _publish_cmds(a):
    from offsim.publish import article
    try:
        if a.cmd == "article":
            p = article.build(a.target, a.template, a.out, a.figure or None, a.lang)
            print(f"article written: {p}")
            return 0
        from offsim.studio import context
        ctx = context(a.paper_id)
        art = Path(a.article) if a.article else ROOT / ctx["paper_dir"] / "article.md"
        film = Path(a.video) if a.video else ROOT / ctx["film"]
        man = article.publish(art, video=film if film.is_file() else None, muse=a.muse)
        print(f"publish bundle: {man['bundle']} (muse: {man['muse']['result']})")
        return 0
    except article.ArticleError as exc:
        print(f"offsim {a.cmd}: {exc}", file=sys.stderr)
        return 2


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv and argv[0] in PASSTHROUGH:
        return PASSTHROUGH[argv[0]][0](argv[1:])
    if argv and argv[0] in LAZY:
        return LAZY[argv[0]][0](argv[1:])
    a = build_parser().parse_args(argv)
    if a.cmd == "run":
        from offsim.pipeline import run
        rep = run(a.scenario, a.out, a.seconds)
        return 0 if all(g["pass"] for k, g in rep["gates"].items() if k != "4_paper") else 1
    if a.cmd in ("article", "publish"):
        return _publish_cmds(a)
    if a.cmd in ("status", "next", "advance", "decide"):
        return _studio(a)
    if a.cmd == "resume":
        from offsim.resume import main as resume
        return resume(a.tests)
    if a.cmd == "film":
        import yaml
        from pathlib import Path
        from offsim.motion.story import ROOT, build
        from offsim.pipeline import run
        sb = yaml.safe_load(Path(a.storyboard).read_text())
        rep = run(ROOT / sb["scenario"], ROOT / sb["run"], a.seconds)
        if not all(g["pass"] for k, g in rep["gates"].items() if k != "4_paper"):
            return 1
        if build(a.storyboard, dry_run=True) or build(a.storyboard):
            return 1
        film = ROOT / sb["run"] / f"{sb['id']}_{sb.get('format', 'square')}.mp4"
        if a.muse:
            from offsim.publish.muse import upload
            print("muse.ai:", upload(film, title=sb.get("title", sb["id"]), visibility=a.muse))
        return 0
    if a.cmd == "story":
        from offsim.motion.story import build
        return build(a.storyboard, dry_run=a.dry_run)
    if a.cmd == "paper":
        try:
            from offsim.intake.paper import main as paper_main
        except ImportError as exc:
            if not (exc.name or "").startswith("offsim.intake"):
                raise
            print("offsim paper: offsim.intake.paper is not available in this checkout; nothing was run.", file=sys.stderr)
            return 2
        return paper_main([a.pdf] + (["--out", a.out] if a.out else []))
    if a.cmd == "experiment":
        from offsim.research.run_experiment import run as run_experiment
        try:
            res = run_experiment(a.experiment, a.engine, workers=a.workers, out=a.out)
        except NotImplementedError as exc:
            print(f"offsim experiment: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(res, indent=2, default=str))
        return 0 if res["blocked"] is None else 1
    if a.cmd == "timetable":
        from offsim.transit.from_paper import to_gtfs
        try:
            man = to_gtfs(a.timetable, a.out)
        except ValueError as exc:
            print(f"offsim timetable: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(man, indent=1))
        return 0
    if a.cmd == "tools":
        from offsim.engines import available
        table = available()
        width = max(len(n) for rows in table.values() for n in rows)
        print(f"{'kind':8} {'name':{width}}  status")
        for kind, rows in table.items():
            for name, status in rows.items():
                print(f"{kind.rstrip('s'):8} {name:{width}}  {status}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
