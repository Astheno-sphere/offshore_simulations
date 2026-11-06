"""offsim command line.

    python -m offsim run <scenario.yaml> [--out DIR] [--seconds S]     # gated pipeline -> report.json
    python -m offsim story <storyboard.yaml> [--dry-run]               # motion: shots -> final video
"""
import argparse
import sys


def main(argv=None):
    ap = argparse.ArgumentParser(prog="offsim")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="scenario.yaml -> gates -> report.json")
    r.add_argument("scenario")
    r.add_argument("--out")
    r.add_argument("--seconds", type=float, default=2.0)
    s = sub.add_parser("story", help="storyboard.yaml -> shots -> final video")
    s.add_argument("storyboard")
    s.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "run":
        from offsim.pipeline import run
        rep = run(a.scenario, a.out, a.seconds)
        return 0 if all(g["pass"] for k, g in rep["gates"].items() if k != "4_paper") else 1
    if a.cmd == "story":
        from offsim.motion.story import build
        return build(a.storyboard, dry_run=a.dry_run)


if __name__ == "__main__":
    sys.exit(main())
