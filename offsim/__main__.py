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
Inspect
    python -m offsim tools                                               # solver and engine import status
    python -m offsim catalog --find X                                    # search the tool catalog
    python -m offsim resume [--tests]                                    # after any interruption: state + next step

Commands with their own argparse (world, layer, feed, tag, gaps, entur, catalog) pass their remaining arguments
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
    s = sub.add_parser("story", help="storyboard.yaml -> shots -> final video")
    s.add_argument("storyboard")
    s.add_argument("--dry-run", action="store_true")
    f = sub.add_parser("film", help="scenario -> gates -> storyboard -> MP4 [-> muse.ai]: the whole brain in one command")
    f.add_argument("storyboard")
    f.add_argument("--seconds", type=float, default=2.0, help="solver time")
    f.add_argument("--muse", choices=["public", "unlisted", "private"], help="upload to muse.ai (needs MUSE_AI_KEY)")
    t = sub.add_parser("timetable", help="timetable.yaml from a paper -> GTFS folder")
    t.add_argument("timetable")
    t.add_argument("--out", metavar="DIR", required=True)
    for name, (_, text) in PASSTHROUGH.items():
        sub.add_parser(name, help=text, add_help=False)
    sub.add_parser("tools", help="solver and engine import status (offsim.engines.available)")
    rs = sub.add_parser("resume", help="where are we: branch, unpushed, worktrees, open roadmap, risks, next command")
    rs.add_argument("--tests", action="store_true", help="also run the test suite")
    return ap


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv and argv[0] in PASSTHROUGH:
        return PASSTHROUGH[argv[0]][0](argv[1:])
    a = build_parser().parse_args(argv)
    if a.cmd == "run":
        from offsim.pipeline import run
        rep = run(a.scenario, a.out, a.seconds)
        return 0 if all(g["pass"] for k, g in rep["gates"].items() if k != "4_paper") else 1
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
            res = run_experiment(a.experiment, a.engine, workers=a.workers)
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
