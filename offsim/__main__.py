"""offsim command line.

    python -m offsim run <scenario.yaml> [--out DIR] [--seconds S]     # gated pipeline -> report.json
    python -m offsim story <storyboard.yaml> [--dry-run]               # motion: shots -> final video
    python -m offsim resume [--tests]                                  # after any interruption: state + next step
    python -m offsim film <storyboard.yaml> [--muse unlisted]          # everything: run -> check -> render -> grade -> upload
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
    rs = sub.add_parser("resume", help="where are we: branch, unpushed, worktrees, open roadmap, risks, next command")
    rs.add_argument("--tests", action="store_true", help="also run the test suite")
    f = sub.add_parser("film", help="scenario -> gates -> storyboard -> MP4 [-> muse.ai]: the whole brain in one command")
    f.add_argument("storyboard")
    f.add_argument("--seconds", type=float, default=2.0, help="solver time")
    f.add_argument("--muse", choices=["public", "unlisted", "private"], help="upload to muse.ai (needs MUSE_AI_KEY)")
    a = ap.parse_args(argv)
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


if __name__ == "__main__":
    sys.exit(main())
