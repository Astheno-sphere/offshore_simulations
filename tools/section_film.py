"""5 s section film in the section-plan grade: PSV heading into a gale, exhaust over the aft deck.

    PYTHONPATH=. python tools/section_film.py --out out/film/psv_section.mp4 [--seconds 5 --fps 30]

Thin wrapper: the film is the `section` shot type of the standard pipeline (offsim/motion/section.py, storyboard
`type: section`). Every moving element is a simulation variable; inputs are ASSUMED (vessel geometry, exhaust
temperature, weather) and labelled DRAFT; the deck text is chosen from measurements (offsim/motion/narrate.py).
"""
from __future__ import annotations

import argparse
from pathlib import Path

from offsim.motion import section as S
from offsim.motion.section import PSV_GALE_NARRATION, Scene, Streaks, map_context, narration, render_section_shot, run_section  # noqa: F401


def gale_shot(seconds=5.0, hs=2.0, tp=6.5, u10=15.0, t_exh=520.0):
    return {"type": "section", "seconds": seconds, "vessel": "psv",
            "hs": {"value": hs, "assumption": True}, "tp": {"value": tp, "assumption": True},
            "u10": {"value": u10, "assumption": True}, "t_exh": {"value": t_exh, "assumption": True},
            "kicker": "OUTER OSLOFJORD GALE  ·  SIMULATED",
            "headline": {"top": "WHERE DOES THE", "accent": "EXHAUST", "rest": "GO IN A GALE?"},
            "map": {"world": "oslofjord", "run": "out/demo-oslofjord-supply", "agent": "PSV-1", "label": "OSLOFJORD DEMO SUPPLY RUN"},
            "narration": PSV_GALE_NARRATION}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out/film/psv_section.mp4")
    ap.add_argument("--seconds", type=float, default=5.0)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--hs", type=float, default=2.0)     # outer-fjord gale sea (assumed); Hs 3.5 is open North Sea
    ap.add_argument("--tp", type=float, default=6.5)
    ap.add_argument("--u10", type=float, default=15.0)
    ap.add_argument("--only", type=int, default=None, help="render a single frame index (still check)")
    a = ap.parse_args()
    out = Path(a.out)
    shot = gale_shot(a.seconds, a.hs, a.tp, a.u10)
    frames = out.parent / "frames"
    if a.only is not None:
        res = run_section(shot, None, frames, a.fps, None, None, a.only, strict_map=False)
        print(res["frames"][0])
        return
    render_section_shot(shot, None, out, a.fps, frames_dir=frames, keep_frames=True, strict_map=False)


if __name__ == "__main__":
    main()
