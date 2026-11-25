"""Draft evidence frame for the Irina film from the three stress-test files. NOT REPORTABLE: the files are unvalidated results, so the
frame is stamped DRAFT. Reference panel stays a visible placeholder until the Bergen world is pulled.
Run: python tools/evidence_still.py [--palette amber-black] [--set A|B|orig] [--out out/evidence_demo.png]"""
import argparse
import json
from pathlib import Path

from PIL import Image

from offsim.cinema import look
from offsim.cinema.draw import Canvas
from offsim.motion.evidence import render_evidence

P = Path("offsim/papers/irinagribkovskaia-2025-tactical-helicopter")
FILES = {"orig": "stress-test.json", "A": "stress-test-A.json", "B": "stress-test-B.json"}


def grid_panel(winters, pal, size):
    """24 rows (winters) x 65 columns (days); a cell is lit when a flight was cancelled that day. Drawn from the file, nothing typed."""
    w, h = size
    cv = Canvas(w, h, pal["ground_deep"], ss=2)
    rows, cols = len(winters), 65
    gx, gy = 70, 14
    cw, ch = (w - gx - 20) / cols, (h - gy - 12) / rows
    worst = max(range(rows), key=lambda i: winters[i]["infeasible_days"])
    for r, wt in enumerate(winters):
        bad = {int(d[1:].split("d")[0]) * 5 + int(d.split("d")[1]) for d in wt["infeasible_day_list"]}
        for c in range(cols):
            x0, y0 = gx + c * cw, gy + r * ch
            cv.polygon([(x0 + .5, y0 + .5), (x0 + cw - .5, y0 + .5), (x0 + cw - .5, y0 + ch - .5), (x0 + .5, y0 + ch - .5)],
                       fill=pal["accent"] if c in bad else pal["ground"], alpha=1.0 if c in bad else 0.55)
        if r == worst:
            cv.polygon([(gx, gy + r * ch), (gx + cols * cw, gy + r * ch), (gx + cols * cw, gy + (r + 1) * ch), (gx, gy + (r + 1) * ch)],
                       stroke=pal["ink"], width=1.4)
        if r == worst or (r % 4 == 0 and abs(r - worst) > 1):
            cv.text(gx - 8, y0 + ch * 0.85, f"{wt['year']}/{str(wt['year'] + 1)[2:]}", ("Inter", "Medium"), 11,
                    pal["accent"] if r == worst else pal["muted"], anchor="r")
    return cv.to_pil(), worst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--palette", default="amber-black")
    ap.add_argument("--set", default="A", choices=list(FILES))
    ap.add_argument("--out", default="out/evidence_demo.png")
    a = ap.parse_args()
    d = json.load(open(P / FILES[a.set]))
    wins = d["results"]["solver"]["per_winter"]
    inf, od = sum(x["infeasible_days"] for x in wins), sum(x["operating_days"] for x in wins)
    pal = look.PALETTES[a.palette]
    panel, worst = grid_panel(wins, pal, (950, 324))
    shot = {
        "type": "map", "form": "evidence", "seconds": 6, "template": "ev1", "kicker": "Bergen, 24 winters",
        "headline": "Sea state cancels the flights", "accent": "Sea state",
        "body": "One weekly plan, replayed through every NORA3 winter. A lit cell is a day with a cancelled flight.",
        "finding": f"limit set {a.set}: wind {d['limits']['wind_mps']} m/s, Hs {d['limits']['hs_m']} m",
        "reference": {"kind": "map", "source": "Bergen service area (not pulled)"},
        "limits": ["The paper's plan: our solved plan on assumed positions, one weather point, our fleet windows. P90 <= 1 is an assumption."],
        "method": [{"label": "NORA3 DJF 2000-2023, 24 winters", "ref": "report:draft.winters"},
                   ({"label": "limit: " + d.get("limits_src", "assumed")[:40], "ref": "report:draft.limits_src"} if not d.get("limits_assumption", True)
                    else {"label": "limit assumed", "assumption": True})],
        "counters": [{"label": "infeasible days", "ref": "report:draft.infeasible"}, {"label": "of operating days", "ref": "report:draft.share"}],
        "palette": {"ground": 1, "accent": 2, "comparison": 3},
        "source": "Gribkovskaia and Slettemark 2025, Logistics 9(2):73; NORA3 hindcast", "handle": "@offshore_simulations",
    }
    img = render_evidence(shot, {"report:draft.infeasible": str(inf), "report:draft.share": f"{100 * inf / od:.1f} %"},
                          {"result": panel}, a.palette, draft="Draft, not reportable")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    img.save(a.out)
    print(a.out, img.size, "worst winter", wins[worst]["year"], "infeasible", inf, "of", od)


if __name__ == "__main__":
    main()
