"""Concept frame for the helicopter film (Gribkovskaia & Slettemark 2025 gap: lean fleet vs winter).

    PYTHONPATH=. python tools/concept_heli.py --out out/stills/heli_concept.png

Airflow over the platform is solved (Section2D); numbers on screen are only the paper's (Tables 3-4, A3, p.25).
Results panels show "?" because nothing has been simulated yet. Installation positions are schematic (paper masks
them). Labelled CONCEPT FRAME on screen.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from PIL import Image, ImageDraw, ImageFont

from offsim.cinema.look import PALETTES, font_path
from offsim.physics.fluid2d import Section2D, obstacle_mask, wind_profile
from offsim.physics.streaks import trace

P = PALETTES["section-plan"]
W, H, SS = 1080, 1350, 2
L_M, H_M, DX, SEA = 170.0, 78.0, 0.5, 8.0
F = lambda s, w="Regular": ImageFont.truetype(font_path(w), s)
INK, MUTED, ACC = P["ink"], P["muted"], P["accent"]
BERGEN_DEMAND = [4, 5, 3, 6.5, 5, 6.5, 3, 4, 4, 4.5, 10, 2, 3.5, 7, 6.5, 6.5, 3, 3.5, 2.5, 3]   # Table A3


def platform(x0=70.0):
    """Stylised fixed platform: jacket legs, two decks, modules, helideck cantilevered upwind, crane, flare boom."""
    deck1, deck2, top = 30.0, 38.0, 47.0
    solids = [[(x0, deck1), (x0 + 46, deck1), (x0 + 46, top), (x0, top)],            # topside block (wind obstacle)
              [(x0 - 14, top + 1.0), (x0 + 6, top + 1.0), (x0 + 6, top + 2.2), (x0 - 14, top + 2.2)]]   # helideck
    lines = []
    for lx in (x0 + 4, x0 + 18, x0 + 30, x0 + 42):                                     # jacket legs + bracing
        lines.append(([(lx, SEA - 6), (lx, deck1)], 2.2))
    for z0, z1 in ((SEA - 4, 14), (14, 22), (22, deck1)):
        lines += [([(x0 + 4, z0), (x0 + 18, z1)], 1.0), ([(x0 + 18, z0), (x0 + 4, z1)], 1.0),
                  ([(x0 + 30, z0), (x0 + 42, z1)], 1.0), ([(x0 + 42, z0), (x0 + 30, z1)], 1.0)]
    boxes = [(x0, deck1, x0 + 46, deck2, "house"), (x0 + 2, deck2, x0 + 22, top, "module"),
             (x0 + 24, deck2, x0 + 44, top - 2, "module"), (x0 + 26, top - 2, x0 + 36, top + 4, "house")]
    helideck = [(x0 - 14, top + 1.0), (x0 + 6, top + 2.2)]
    crane = [(x0 + 38, top + 4), (x0 + 38, top + 12), (x0 + 58, top + 6)]
    flare = [(x0 + 46, deck2 + 2), (x0 + 66, deck2 + 18)]
    return solids, lines, boxes, helideck, crane, flare, (x0, deck1, deck2, top)


def s92(cx, cz, scale=1.0):
    """Side-profile S-92 (~17.1 m fuselage, 17.2 m rotor) as polylines; returns list of (points, weight)."""
    s = scale
    body = [(-8.5, 0.6), (-7.6, 2.4), (-4.5, 3.3), (3.5, 3.3), (5.2, 2.4), (6.0, 1.0), (5.0, -0.2), (-7.8, -0.2)]
    tail = [(5.0, 2.6), (13.0, 3.0), (14.2, 5.2), (14.8, 5.2), (14.2, 2.2), (5.6, 0.8)]
    rotor = [(-8.6, 4.4), (8.6, 4.1)]
    mast = [(0.0, 3.3), (0.0, 4.3)]
    gear = [[(-5.5, -0.2), (-5.5, -1.2)], [(1.5, -0.2), (1.5, -1.2)]]
    win = [[(-7.3, 2.1), (-5.6, 2.9)], [(-5.0, 1.5), (-5.0, 2.7)]] + [[(x, 1.4), (x + 0.9, 1.4), (x + 0.9, 2.2), (x, 2.2), (x, 1.4)] for x in np.arange(-3.6, 3.2, 1.3)]
    tf = lambda pts: [(cx + x * s, cz + z * s) for x, z in pts]
    out = [(tf(body + body[:1]), 2.2), (tf(tail + tail[:1]), 1.8), (tf(rotor), 2.0), (tf(mast), 1.6),
           (tf([(13.6, 6.6), (14.6, 3.8)]), 1.2)]
    out += [(tf(g), 1.2) for g in gear] + [(tf(w), 0.9) for w in win]
    return out


def solve(u10=22.0, steps=420, dt=0.012):
    nx, nz = int(L_M / DX), int(H_M / DX)
    zs = (np.arange(nz) + 0.5) * DX
    solids, *_ = platform()
    sea = np.zeros((nx, nz), bool)
    sea[:, : int(SEA / DX)] = True
    sec = Section2D(nx, nz, DX, sea | obstacle_mask(solids, nx, nz, DX), jacobi=40)
    sec.set_inflow(wind_profile(np.maximum(zs - SEA, 0.5), u10))
    for _ in range(steps):
        sec.step(dt)
    return sec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out/stills/heli_concept.png")
    a = ap.parse_args()
    sec = solve()
    img = Image.new("RGB", (W, H), P["ground"])
    d = ImageDraw.Draw(img)
    # header
    d.text((56, 44), "BERGEN HELIPORT  ·  20 INSTALLATIONS  ·  NORTH SEA WINTER", font=F(17, "Bold"), fill=ACC)
    d.text((W - 56 - d.textlength("offshore_simulations", font=F(15, "SemiBold")), 46), "offshore_simulations", font=F(15, "SemiBold"), fill=MUTED)
    d.text((56, 78), "EQUINOR'S OPTIMISER SAYS", font=F(46, "Bold"), fill=INK)
    d.text((56, 130), "4", font=F(46, "Bold"), fill=ACC)
    d.text((56 + d.textlength("4 ", font=F(46, "Bold")), 130), "HELICOPTERS, NOT 5.", font=F(46, "Bold"), fill=INK)
    d.text((56, 190), "Does the lean fleet survive January?", font=F(24), fill=MUTED)
    # section panel (supersampled)
    top, ph = 240, int(W * H_M / L_M)
    pw, phs = W * SS, ph * SS
    s = W / L_M * SS
    px = lambda x, z: (x * s, phs - z * s)
    pan = Image.new("RGBA", (pw, phs), P["ground"])
    lay = Image.new("RGBA", (pw, phs), (0, 0, 0, 0))
    dl = ImageDraw.Draw(lay)
    tails = trace(sec.mask, sec.u, sec.w, DX, 0.07, n=11000, tail=16, seed_=5)
    sp = np.hypot(sec.u, sec.w)
    ix = np.clip(np.nan_to_num(tails[:, 0, 0]).astype(int), 0, sec.nx - 1)
    iz = np.clip(np.nan_to_num(tails[:, 0, 1]).astype(int), 0, sec.nz - 1)
    vort = np.abs(np.gradient(sec.w, axis=0) - np.gradient(sec.u, axis=1)) / DX
    hv = np.clip(vort[ix, iz] / 2.5, 0, 1)                      # turbulence colours the streaks (amber = eddies)
    cmap = LinearSegmentedColormap.from_list("st", [P["streak_lo"], P["streak_hi"], ACC])
    for tl, v in zip(tails, hv):
        pts = [px(x * DX, z * DX) for x, z in tl if np.isfinite(x)]
        if len(pts) < 2:
            continue
        r, g, b = (np.array(cmap(v)[:3]) * 255).astype(int)
        for i in range(len(pts) - 1):
            dl.line([pts[i], pts[i + 1]], fill=(r, g, b, int(150 * (1 - i / len(pts)))), width=SS)
    pan.alpha_composite(lay)
    dp = ImageDraw.Draw(pan)
    xs = np.linspace(0, L_M, 400)
    surf = [px(x, SEA + 0.8 * math.sin(x / 9.0) + 0.4 * math.sin(x / 3.7)) for x in xs]
    dp.polygon(surf + [(pw, phs), (0, phs)], fill=P["ground_deep"])
    dp.line(surf, fill=P["streak_hi"], width=2 * SS)
    solids, lines, boxes, helideck, crane, flare, (x0, d1, d2, tp) = platform()
    for pts, w in lines:
        dp.line([px(*p) for p in pts], fill=INK, width=max(1, int(w * SS)))
    fills = {"house": "#4a2b2d", "module": "#432729"}
    for xa, za, xb, zb, kind in boxes:
        dp.rectangle([px(xa, zb), px(xb, za)], fill=fills[kind], outline=INK, width=2 * SS)
        for xw in np.arange(xa + 1.5, xb - 1, 2.2):
            dp.line([px(xw, za + 1), px(xw, zb - 1)], fill="#6b4f4a", width=1)
    dp.rectangle([px(helideck[0][0], helideck[1][1]), px(helideck[1][0], helideck[0][1])], fill="#53302f", outline=INK, width=2 * SS)
    for xn in np.arange(helideck[0][0], helideck[1][0], 1.2):          # perimeter net posts
        dp.line([px(xn, tp + 2.2), px(xn, tp + 3.0)], fill=INK, width=1)
    dp.line([px(helideck[0][0] + 9, tp + 1.0), px(helideck[0][0] + 9, d2)], fill=INK, width=SS)   # deck support
    dp.line([px(*p) for p in crane], fill=INK, width=2 * SS)
    dp.line([px(*p) for p in flare], fill=INK, width=2 * SS)
    dp.ellipse([px(flare[1][0] - 1.4, flare[1][1] + 3), px(flare[1][0] + 1.4, flare[1][1])], fill=ACC)
    for pts, w in s92(36.0, 53.0, 1.7):
        dp.line([px(*p) for p in pts], fill=INK, width=max(1, int(w * SS)), joint="curve")
    for u in (52.0,):                                                   # crew on the deck for scale (1.8 m)
        dp.line([px(x0 + 10, d2), px(x0 + 10, d2 + 1.8)], fill=INK, width=SS)
    img.paste(pan.resize((W, ph), Image.LANCZOS).convert("RGB"), (0, top))
    d.text((56, top + 14), "14:15  ·  WIND 22 m/s (ILLUSTRATIVE)", font=F(18, "SemiBold"), fill=INK)
    d.text((56, top + 40), "flow over the helideck solved, not drawn: amber = eddies", font=F(14), fill=MUTED)
    d.text((W - 56 - d.textlength("SECTION · 2D AIRFLOW", font=F(14, "SemiBold")), top + 14), "SECTION · 2D AIRFLOW", font=F(14, "SemiBold"), fill=MUTED)
    st = "FLIGHT B11  CANCELLED?"
    bx = 610
    d.rounded_rectangle([bx, top + 70, bx + 20 + d.textlength(st, font=F(18, "Bold")), top + 104], 6, outline=ACC, width=2)
    d.text((bx + 10, top + 76), st, font=F(18, "Bold"), fill=ACC)
    # readouts (paper values only)
    y = top + ph + 26
    for i, (lab, val, hot) in enumerate([("OPTIMAL FLEET", "4 S-92", True), ("ACTUAL", "5 S-92", False), ("FLIGHTS / WEEK", "93", False)]):
        xx = 56 + i * 330
        d.text((xx, y), lab, font=F(16, "SemiBold"), fill=MUTED)
        d.text((xx, y + 22), val, font=F(30, "Bold"), fill=ACC if hot else INK)
    # schematic flight map (positions assumed: the paper masks them)
    my = y + 92
    mw, mh = 470, 330
    cx, cy = 56 + 70, my + mh // 2 + 10
    d.text((56, my - 4), "WEEKLY PROGRAMME FROM BERGEN (SCHEMATIC)", font=F(14, "SemiBold"), fill=MUTED)
    # true orientation: the fields lie west of Flesland, so the heliport sits at the right and flights fan out left
    cx, cy = 56 + mw - 30, my + mh // 2 + 30
    nm = (mw - 60) / 125.0
    for r in (50, 100):
        d.arc([cx - r * nm, cy - r * nm, cx + r * nm, cy + r * nm], 135, 225, fill="#5a3e3e", width=1)
        d.text((cx - r * nm + 4, cy + 4), f"{r} nm", font=F(12), fill=MUTED)
    rng = np.random.default_rng(3)
    for k, dem in enumerate(BERGEN_DEMAND):
        ang = math.radians(140 + 80 * (k + 0.5) / 20)
        rr = (55 + 60 * rng.random()) * nm                          # paper: 50-120 nm; positions schematic
        ix_, iy_ = cx + rr * math.cos(ang), cy - rr * math.sin(ang)
        d.line([(cx, cy), (ix_, iy_)], fill=(229, 160, 40), width=max(1, round(dem / 2.5)))
        rad = 3 + dem * 0.6
        d.ellipse([ix_ - rad, iy_ - rad, ix_ + rad, iy_ + rad], outline=INK, width=1, fill=P["ground_deep"])
    d.ellipse([cx - 7, cy - 7, cx + 7, cy + 7], fill=ACC)
    d.text((cx - 62, cy + 14), "Flesland", font=F(13, "SemiBold"), fill=INK)
    d.text((56 + 4, my + 22), "W  ←", font=F(12, "SemiBold"), fill=MUTED)
    d.text((56, my + mh + 4), "line width = weekly flights (Table A3) · positions schematic", font=F(12), fill=MUTED)
    # result panel: what we will measure (no numbers until simulated)
    rx, rw = 600, 424
    d.text((rx, my - 4), "UNMET FLIGHTS / WEEK, 24 WINTERS", font=F(14, "SemiBold"), fill=MUTED)
    for j, (lab, col) in enumerate([("4 helicopters (optimal)", ACC), ("5 helicopters (actual)", P["streak_hi"])]):
        yy = my + 60 + j * 120
        d.text((rx, yy), lab, font=F(16, "SemiBold"), fill=INK)
        d.rounded_rectangle([rx, yy + 30, rx + rw, yy + 62], 8, outline="#5a3e3e", width=1)
        d.rectangle([rx + 60, yy + 38, rx + 260, yy + 54], fill=None, outline=col, width=2)
        d.text((rx + rw - 22, yy + 33), "?", font=F(22, "Bold"), fill=col)
        d.text((rx, yy + 68), "P10 – P90 band   ·   to be simulated on NORA3", font=F(12), fill=MUTED)
    d.text((rx, my + 300), "Decision rule set before the run:", font=F(14), fill=MUTED)
    d.text((rx, my + 320), "lean fleet robust if P90 ≤ 1 unmet flight/week", font=F(14, "SemiBold"), fill=INK)
    # methods
    yb = H - 108
    d.text((56, yb), "Paper: Gribkovskaia & Slettemark (2025), Logistics 9(2):73, CC BY 3.0. Fleet, flights, demand: Tables 4, A3.",
           font=F(13), fill=MUTED)
    d.text((56, yb + 20), "Airflow: 2D Boussinesq stable fluids (Stam 1999), 0.5 m grid. Wind, positions and cancellation are illustrative.",
           font=F(13), fill=MUTED)
    d.text((56, yb + 52), "CONCEPT FRAME  ·  NO RESULTS YET", font=F(15, "Bold"), fill=ACC)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    print(out)


if __name__ == "__main__":
    main()
