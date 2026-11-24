"""Irina winter grid (beats 5-6): 24 winters x 65 days, one cell per operating day.

A cell lights when a flight was cancelled that day (per_winter[].infeasible_day_list,
"w{week}d{day}" -> column week*5+day). Three limit sets, same scale, stacked:
original (assumed), A (IOGP routine), B (SPA.HOFO.135 + IOGP precautionary).
The worst row (2011/12) is outlined. All numbers come from the stress-test
JSONs; nothing is typed by hand. PIL render, 4:5.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "offsim" / "papers" / "irinagribkovskaia-2025-tactical-helicopter"
GROUND = (46, 21, 28)      # oxblood #2E151C
PANEL = (28, 18, 16)
LIT = (229, 160, 40)       # gold #e5a028
UNLIT = (60, 42, 40)
CREAM = (232, 223, 208)
MUTED = (138, 115, 100)
DAY_RE = re.compile(r"^w(\d+)d(\d+)$")


def load_sets(paper_dir=PAPER):
    """(label, source, infeasible, share, grid) per limit set, table order."""
    files = [
        ("ORIGINAL · WIND 25.0 M/S, HS 6.0 M — ASSUMED", "stress-test.json"),
        ("A · WIND 26.75 M/S, HS 5.5 M — IOGP AMG APP.6 CHART 2 P.142",
         "stress-test-A.json"),
        ("B · WIND 30.87 M/S, HS 7.0 M — SPA.HOFO.135 + IOGP PRECAUTIONARY",
         "stress-test-B.json"),
    ]
    out = []
    for label, fname in files:
        d = json.loads((Path(paper_dir) / fname).read_text())
        pw = d["results"]["solver"]["per_winter"]
        grid = [[False] * 65 for _ in range(24)]
        for i, w in enumerate(pw):
            for entry in w["infeasible_day_list"]:
                m = DAY_RE.match(entry)
                week, day = int(m.group(1)), int(m.group(2))
                grid[i][week * 5 + day] = True
        inf = sum(sum(row) for row in grid)
        od = sum(w["operating_days"] for w in pw)
        causes = {}
        for w in pw:
            for k, v in w["cancel_causes"].items():
                causes[k] = causes.get(k, 0) + v
        out.append({"label": label, "grid": grid, "infeasible": inf,
                    "share": inf / od, "years": [w["year"] for w in pw],
                    "causes": causes})
    return out


def _font(size):
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def render_grid(sets, out_png, single=None, width=1080, height=1350):
    """Render one (single=index) or all three grids stacked. Returns stats."""
    img = Image.new("RGB", (width, height), GROUND)
    dr = ImageDraw.Draw(img)
    title = _font(44)
    sub = _font(24)
    small = _font(20)
    label_f = _font(22)
    year_f = _font(18)
    x0, y = 54, 48
    dr.text((x0, y), "24 WINTERS, 65 DAYS EACH", font=title, fill=CREAM)
    y += 62
    dr.text((x0, y), "A day lights up when a flight was cancelled.",
            font=sub, fill=MUTED)
    y += 64
    show = [sets[single]] if single is not None else sets
    cell = 10 if single is None else 13
    gap = 2
    gw = 65 * (cell + gap) - gap
    for s in show:
        dr.text((x0, y), s["label"], font=label_f, fill=CREAM)
        y += 30
        dr.text((x0, y), f"{s['infeasible']} days infeasible = "
                f"{100 * s['share']:.1f}% of 1,560 operating days",
                font=label_f, fill=LIT)
        y += 36
        top = y
        for r, row in enumerate(s["grid"]):
            for c, lit in enumerate(row):
                px = x0 + c * (cell + gap)
                py = top + r * (cell + gap)
                dr.rectangle([px, py, px + cell - 1, py + cell - 1],
                             fill=LIT if lit else UNLIT)
            if s["years"][r] % 4 == 0 or r == 23:
                dr.text((x0 + gw + 10, top + r * (cell + gap) - 2),
                        str(s["years"][r]), font=year_f, fill=MUTED)
        # worst row 2011/12 outlined
        worst = max(range(24), key=lambda r: sum(s["grid"][r]))
        dr.rectangle([x0 - 4, top + worst * (cell + gap) - 4,
                      x0 + gw + 3, top + worst * (cell + gap) + cell + 3],
                     outline=CREAM, width=2)
        y = top + 24 * (cell + gap) + 18
        if single is not None:
            # Beat 7 fills the rest of the single frame: the cause split.
            c = s["causes"]
            total = sum(c.values())
            dr.text((x0, y + 30), "WHAT CANCELLED THEM", font=label_f, fill=CREAM)
            y += 30 + 36
            bx, bw = x0, gw
            x = bx
            segs = [("SEA STATE", c.get("hs", 0), LIT),
                    ("WIND", c.get("wind", 0), (79, 143, 156)),
                    ("BOTH", c.get("both", 0), MUTED)]
            for name, n, col in segs:
                if n <= 0:
                    continue
                wseg = bw * n / total
                dr.rectangle([x, y, x + wseg - 2, y + 44], fill=col)
                x += wseg
            y += 60
            parts = " · ".join(f"{n} {v}" for n, v in
                               [("SEA", c.get("hs", 0)), ("WIND", c.get("wind", 0)),
                                ("BOTH", c.get("both", 0))])
            dr.text((x0, y), f"{parts} of {total} cancellations",
                    font=label_f, fill=CREAM)
            y += 36
    dr.text((x0, height - 52),
            "One weather point (3.0E, 60.6N) for all 20 installations · Positions assumed",
            font=small, fill=MUTED)
    img.save(out_png)
    return {"sets": [(s["label"][:12], s["infeasible"],
                      round(100 * s["share"], 1)) for s in show]}


if __name__ == "__main__":
    import sys

    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "out" / "irina-winter-grid"
    out.mkdir(parents=True, exist_ok=True)
    sets = load_sets()
    print(render_grid(sets, out / "winter-grid-three.png"))
    print(render_grid(sets, out / "winter-grid-A.png", single=1))
    print("wrote", out)
