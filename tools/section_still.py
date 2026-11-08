"""Draft still: PSV section in wind and waves (docs/STYLE_REFERENCE.md). Display-grade, all inputs ASSUMED.

    python tools/section_still.py --out out/stills/psv_section.png [--hs 3 --tp 9 --u10 15]
Freezes the wave surface at the final time (moving boundary not yet coupled). Not a validated result.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from PIL import Image, ImageDraw, ImageFont

from offsim.cinema.look import PALETTES
from offsim.physics import ocean, streaks
from offsim.physics.fluid2d import Section2D, obstacle_mask, wind_profile

P = PALETTES["section-plan"]
L_M, H_M, DX, SEA_Z = 160.0, 52.0, 0.4, 10.0


def hull_polys(x0=30.0, z0=SEA_Z):
    """Stylised 85 m PSV heading into the wind (bow left, wind from the left): hull, forward superstructure and
    bridge, funnel aft of the bridge, cargo deck aft (geometry ASSUMED)."""
    m = lambda pts: [(x0 + 85 - x, z) for x, z in pts]          # mirror: bow at x0
    hull = m([(0, z0 - 6), (78, z0 - 6), (85, z0 + 3), (82, z0 + 4.5), (0, z0 + 4.5), (-1, z0 - 1)])
    house = m([(58, z0 + 4.5), (78, z0 + 4.5), (78, z0 + 13), (60, z0 + 13)])
    bridge = m([(62, z0 + 13), (78, z0 + 13), (76, z0 + 17), (63, z0 + 17)])
    funnel = m([(53, z0 + 4.5), (57, z0 + 4.5), (57, z0 + 15), (53.5, z0 + 15)])
    return {"hull": hull, "house": house, "bridge": bridge, "funnel": funnel}


def run(hs, tp, u10, steps=420, dt=0.015, seed=7):
    nx, nz = int(L_M / DX), int(H_M / DX)
    xs = (np.arange(nx) + 0.5) * DX
    zs = (np.arange(nz) + 0.5) * DX
    t_end = steps * dt
    eta = ocean.surface(xs, t_end, hs, tp, seed=seed)
    sea = zs[None, :] < (SEA_Z + eta)[:, None]
    polys = hull_polys()
    mask = sea | obstacle_mask(list(polys.values()), nx, nz, DX)
    sec = Section2D(nx, nz, DX, mask, jacobi=40)
    sec.set_inflow(wind_profile(np.maximum(zs - SEA_Z, 0.5), u10))
    fx = polys["funnel"]
    hot = np.zeros((nx, nz), bool)
    i0, i1 = sorted((int(fx[0][0] / DX), int(fx[1][0] / DX)))
    k = int((SEA_Z + 15) / DX)
    hot[i0:i1, k:k + 3] = True
    sec.add_heat(hot, 520.0)                          # exhaust temperature ASSUMED
    for _ in range(steps):
        sec.step(dt)
    return sec, eta, polys, xs


def render(sec, eta, polys, xs, hs, tp, u10, size=(1080, 1080)):
    W, H = size
    img = Image.new("RGB", size, P["ground"])
    d = ImageDraw.Draw(img)
    font = lambda s, b=False: ImageFont.truetype(f"/usr/share/fonts/truetype/dejavu/DejaVuSans{'-Bold' if b else ''}.ttf", s)
    # header
    d.text((48, 40), "SUPPLY RUNS ON THE NORWEGIAN SHELF  ·  SECTION, SIMULATED", font=font(18, True), fill=P["accent"])
    d.text((48, 72), "WHERE DOES THE", font=font(54, True), fill=P["ink"])
    d.text((48, 132), "EXHAUST", font=font(54, True), fill=P["accent"])
    d.text((48 + d.textlength("EXHAUST ", font=font(54, True)), 132), "GO IN A GALE?", font=font(54, True), fill=P["ink"])
    # section panel
    top, ph = 230, int(W * H_M / L_M)
    s = W / L_M
    to_px = lambda x, z: (x * s, top + ph - z * s)
    panel = Image.new("RGBA", (W, ph), (0, 0, 0, 0))
    tails = streaks.trace(sec.mask, sec.u, sec.w, sec.dx, 0.06, n=9000, tail=16, seed_=3)
    ix = np.clip(np.nan_to_num(tails[:, 0, 0]).astype(int), 0, sec.nx - 1)
    iz = np.clip(np.nan_to_num(tails[:, 0, 1]).astype(int), 0, sec.nz - 1)
    heat = np.clip((sec.T[ix, iz] - sec.t_ref) / 60.0, 0, 1)
    cmap = LinearSegmentedColormap.from_list("st", [P["streak_lo"], P["streak_hi"], P["accent"]])
    panel.alpha_composite(streaks.draw(tails, heat, cmap, (W, ph), (sec.nx, sec.nz), alpha=0.55))
    # temperature glow: the plume itself, from the solver's T field
    dT = np.clip((sec.T - sec.t_ref) / 80.0, 0, 1).T[::-1]
    acc = np.array(Image.new("RGB", (1, 1), P["accent"]).getpixel((0, 0)))
    glow = np.zeros((*dT.shape, 4), np.uint8)
    glow[..., :3] = acc
    glow[..., 3] = (dT ** 0.6 * 170).astype(np.uint8)
    gimg = Image.fromarray(glow, "RGBA").resize((W, ph), Image.BILINEAR)
    panel = Image.alpha_composite(gimg, panel)
    img.paste(panel, (0, top), panel)
    # sea
    surf = [to_px(x, SEA_Z + e) for x, e in zip(xs, eta)]
    d.polygon(surf + [(W, top + ph), (0, top + ph)], fill=P["ground_deep"])
    d.line(surf, fill=P["streak_hi"], width=2)
    # vessel line art
    for name, poly in polys.items():
        pts = [to_px(x, z) for x, z in poly]
        d.polygon(pts, fill="#4a2a2c" if name != "hull" else "#3d2326", outline=P["ink"], width=2)
    hx = polys["house"]
    for row in (SEA_Z + 7, SEA_Z + 10.5):
        for xw in np.arange(min(hx[0][0], hx[1][0]) + 2, max(hx[0][0], hx[1][0]) - 1, 2.6):
            d.rectangle([to_px(xw, row + 1.2), to_px(xw + 1.4, row)], outline=P["accent"], width=1)
    d.line([to_px(62, SEA_Z + 4.5), to_px(112, SEA_Z + 4.5)], fill=P["muted"], width=1)   # cargo deck (aft)
    # readouts (from this draft run, not a report; labelled so)
    plume_top = SEA_Z + np.where(((sec.T - sec.t_ref) > 20).any(0))[0].max() * sec.dx
    y = top + ph + 34
    items = [("WIND 10 m", f"{u10:.0f} m/s", False), ("Hs", f"{hs:.1f} m", False), ("PLUME TOP", f"{plume_top - SEA_Z:.0f} m", True)]
    xpos = 48
    for lab, val, hot in items:
        d.text((xpos, y), lab, font=font(20, True), fill=P["ink"])
        xpos += d.textlength(lab + " ", font=font(20, True))
        d.text((xpos, y), val, font=font(20, True), fill=P["accent"] if hot else P["muted"])
        xpos += d.textlength(val, font=font(20, True)) + 40
    d.text((48, y + 52), "Wind over a supply vessel's deck in a North Sea gale, solved, not drawn: every streak is air", font=font(22), fill=P["ink"])
    d.text((48, y + 82), "carried by the flow, warm exhaust rising and bending downwind over the cargo deck.", font=font(22), fill=P["ink"])
    d.text((48, y + 128), "Section: 2D Boussinesq stable fluids (Stam 1999), 0.4 m grid, IEC 61400-3 offshore wind profile;",
           font=font(15), fill=P["muted"])
    d.text((48, y + 150), f"sea: JONSWAP Hs {hs} m Tp {tp} s. DRAFT: vessel geometry, exhaust temperature and weather are assumptions.",
           font=font(15), fill=P["muted"])
    d.text((48, H - 48), "offshore_simulations", font=font(16, True), fill=P["muted"])
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out/stills/psv_section.png")
    ap.add_argument("--hs", type=float, default=3.0)
    ap.add_argument("--tp", type=float, default=9.0)
    ap.add_argument("--u10", type=float, default=15.0)
    a = ap.parse_args()
    sec, eta, polys, xs = run(a.hs, a.tp, a.u10)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    render(sec, eta, polys, xs, a.hs, a.tp, a.u10).save(out)
    print(out, f"t={sec.time:.1f}s", sec.meta)


if __name__ == "__main__":
    main()
