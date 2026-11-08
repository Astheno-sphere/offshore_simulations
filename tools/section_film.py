"""5 s section film in the section-plan grade: PSV heading into a gale, exhaust over the aft deck.

    PYTHONPATH=. python tools/section_film.py --out out/film/psv_section.mp4 [--seconds 5 --fps 30]

Every moving element is a simulation variable: air (Section2D), sea (JONSWAP surface, moving boundary), ship heave
and pitch (from the sea surface under the hull, display-grade), the chart (air temperature over the aft deck,
measured in the solver each frame). Inputs are ASSUMED (vessel geometry, exhaust temperature, weather); labelled DRAFT.
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from PIL import Image, ImageDraw, ImageFont

from offsim.cinema.look import PALETTES
from offsim.cinema.vessel_lineart import draw as draw_vessel, psv_profile
from offsim.physics import ocean
from offsim.physics.fluid2d import Section2D, obstacle_mask, wind_profile

P = PALETTES["section-plan"]
L_M, H_M, DX, SEA_Z, BOW_X, SHIP_L = 160.0, 60.0, 0.4, 10.0, 28.0, 85.0
W, H, SS = 1080, 1350, 2
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans{}.ttf"


def font(s, b=False):
    return ImageFont.truetype(FONT.format("-Bold" if b else ""), s)


class Scene:
    def __init__(self, hs, tp, u10, t_exh=520.0, seed=7):
        self.hs, self.tp, self.u10, self.t_exh, self.seed = hs, tp, u10, t_exh, seed
        self.nx, self.nz = int(L_M / DX), int(H_M / DX)
        self.xs = (np.arange(self.nx) + 0.5) * DX
        self.zs = (np.arange(self.nz) + 0.5) * DX
        self.sec = Section2D(self.nx, self.nz, DX, jacobi=40)
        self.sec.set_inflow(wind_profile(np.maximum(self.zs - SEA_Z, 0.5), u10))
        self.t = 0.0
        self.update_geometry()

    def ship_pose(self, t):
        xb, xs_ = BOW_X, BOW_X + SHIP_L
        e = ocean.surface(np.array([xb + 10, BOW_X + SHIP_L / 2, xs_ - 10]), t, self.hs, self.tp, seed=self.seed)
        heave = 0.7 * e[1]                                    # ship filters short waves (display-grade factor)
        pitch = 0.5 * np.arctan2(e[0] - e[2], SHIP_L - 20)    # bow up when bow sea is higher
        return heave, pitch

    def update_geometry(self):
        self.eta = ocean.surface(self.xs, self.t, self.hs, self.tp, seed=self.seed)
        self.heave, self.pitch = self.ship_pose(self.t)
        z0 = SEA_Z + self.heave
        self.prims, solids, self.exhaust = psv_profile(BOW_X, z0, SHIP_L, pitch_rad=self.pitch,
                                                       pivot=(BOW_X + SHIP_L / 2, z0))
        self.deck_z = z0 + 4.5
        sea = self.zs[None, :] < (SEA_Z + self.eta)[:, None]
        self.sec.mask = sea | obstacle_mask(solids, self.nx, self.nz, DX)
        hot = np.zeros((self.nx, self.nz), bool)
        i, k = int(self.exhaust[0] / DX), int(self.exhaust[1] / DX)
        hot[i - 3:i + 4, k:k + 3] = True
        hot &= ~self.sec.mask
        self.sec.add_heat(hot, self.t_exh)

    def step(self, dt):
        self.sec.step(dt)
        self.t += dt
        self.update_geometry()

    def deck_air_excess(self):
        """Max air temperature excess (K) 0.5-2.5 m above the aft cargo deck: a measured solver value."""
        i0, i1 = int((BOW_X + 28) / DX), int((BOW_X + 82) / DX)
        k0, k1 = int((self.deck_z + 0.5) / DX), int((self.deck_z + 2.5) / DX)
        cells = self.sec.T[i0:i1, k0:k1][~self.sec.mask[i0:i1, k0:k1]]
        return float(cells.max() - self.sec.t_ref) if cells.size else 0.0

    def plume_height(self):
        """Lowest height (m above the deck) of air >20 K over ambient above the aft deck; NaN if none there."""
        i0, i1 = int((BOW_X + 28) / DX), int((BOW_X + 82) / DX)
        hot = (self.sec.T[i0:i1] - self.sec.t_ref) > 20
        ks = np.where(hot.any(0))[0]
        return float(ks.min() * DX - self.deck_z) if ks.size else float("nan")


class Streaks:
    def __init__(self, sc, n=7000, tail=12, seed=3):
        self.rng = np.random.default_rng(seed)
        self.sc, self.n, self.tail = sc, n, tail
        self.p = np.c_[self.rng.uniform(0, sc.nx - 1, n), self.rng.uniform(0, sc.nz - 1, n)]
        self.hist = np.full((n, tail, 2), np.nan)

    def advance(self, dt):
        from scipy.ndimage import map_coordinates
        u, w, m = self.sc.sec.u, self.sc.sec.w, self.sc.sec.mask
        v = lambda q: np.c_[map_coordinates(u, q.T, order=1, mode="nearest"), map_coordinates(w, q.T, order=1, mode="nearest")]
        q = self.p + v(self.p + 0.5 * v(self.p) * dt / DX) * dt / DX
        nx, nz = u.shape
        bad = (q[:, 0] < 0) | (q[:, 0] > nx - 1) | (q[:, 1] < 0) | (q[:, 1] > nz - 1)
        bad |= m[np.clip(q[:, 0].astype(int), 0, nx - 1), np.clip(q[:, 1].astype(int), 0, nz - 1)]
        bad |= self.rng.random(self.n) < 0.004                 # age-out keeps density even
        q[bad] = np.c_[self.rng.uniform(0, nx - 1, bad.sum()), self.rng.uniform(0, nz - 1, bad.sum())]
        self.hist = np.roll(self.hist, 1, axis=1)
        self.hist[:, 0] = q
        self.hist[bad, 1:] = np.nan
        self.p = q


def narration(series):
    """Deck text chosen from what the run measured (never written before the run)."""
    deck = max(v for _, v, _ in series)
    hs = [h for _, _, h in series if np.isfinite(h)]
    low = min(hs) if hs else float("nan")
    if deck >= 5:
        return ("Bow into the wind, the funnel's hot gas is caught in the lee of the bridge",
                f"and reaches the cargo deck: up to +{deck:.0f} °C in the crew's breathing zone.")
    return ("Bow into the wind, the funnel's hot gas rolls into eddies behind the bridge",
            f"but never comes lower than {low:.0f} m above the cargo deck: the crew zone stays clear.")


def render(sc, st, series, frame, nframes, out_path, deck_text):
    s = W / L_M
    top, ph = 236, int(W * H_M / L_M)
    img = Image.new("RGB", (W, H), P["ground"])
    d = ImageDraw.Draw(img)
    # header
    d.text((56, 44), "NORTH SEA GALE  ·  ONE SUPPLY VESSEL  ·  SIMULATED", font=font(17, True), fill=P["accent"])
    hf = font(52, True)
    d.text((56, 76), "WHERE DOES THE", font=hf, fill=P["ink"])
    d.text((56, 136), "EXHAUST", font=hf, fill=P["accent"])
    d.text((56 + d.textlength("EXHAUST ", font=hf), 136), "GO IN A GALE?", font=hf, fill=P["ink"])
    # section panel, supersampled
    pw, phs = W * SS, ph * SS
    to_px = lambda x, z: (x * s * SS, phs - z * s * SS)
    pan = Image.new("RGBA", (pw, phs), P["ground"])
    dT = np.clip((sc.sec.T - sc.sec.t_ref) / 80.0, 0, 1).T[::-1]
    acc = np.array(Image.new("RGB", (1, 1), P["accent"]).getpixel((0, 0)))
    g = np.zeros((*dT.shape, 4), np.uint8)
    g[..., :3] = acc
    g[..., 3] = (dT ** 0.6 * 160).astype(np.uint8)
    pan.alpha_composite(Image.fromarray(g, "RGBA").resize((pw, phs), Image.BILINEAR))
    lay = Image.new("RGBA", (pw, phs), (0, 0, 0, 0))
    dl = ImageDraw.Draw(lay)
    cmap = LinearSegmentedColormap.from_list("st", [P["streak_lo"], P["streak_hi"], P["accent"]])
    h0 = st.hist[:, 0]
    ok = np.isfinite(h0[:, 0])
    ix = np.clip(np.nan_to_num(h0[:, 0]).astype(int), 0, sc.nx - 1)
    iz = np.clip(np.nan_to_num(h0[:, 1]).astype(int), 0, sc.nz - 1)
    heat = np.clip((sc.sec.T[ix, iz] - sc.sec.t_ref) / 60.0, 0, 1)
    for tl, hv, good in zip(st.hist, heat, ok):
        if not good:
            continue
        pts = [(x * DX * s * SS, phs - z * DX * s * SS) for x, z in tl if np.isfinite(x)]
        if len(pts) < 2:
            continue
        r, gg, b = (np.array(cmap(hv)[:3]) * 255).astype(int)
        n = len(pts)
        for i in range(n - 1):
            dl.line([pts[i], pts[i + 1]], fill=(r, gg, b, int(150 * (1 - i / n))), width=SS)
    pan.alpha_composite(lay)
    dp = ImageDraw.Draw(pan)
    surf = [to_px(x, SEA_Z + e) for x, e in zip(sc.xs, sc.eta)]
    dp.polygon(surf + [(pw, phs), (0, phs)], fill=P["ground_deep"])
    for k in range(1, 4):                                       # faint sub-surface swell lines
        dp.line([(x, y + k * 9 * SS) for x, y in surf], fill=(107, 79, 74, 70), width=1)
    dp.line(surf, fill=P["streak_hi"], width=2 * SS)
    draw_vessel(dp, sc.prims, to_px, ss=SS)
    img.paste(pan.resize((W, ph), Image.LANCZOS).convert("RGB"), (0, top))
    # clock + conditions on the panel
    d.text((56, top + 14), f"t +{sc.t - series[0][0]:4.1f} s", font=font(20, True), fill=P["ink"])
    d.text((56, top + 40), f"WIND {sc.u10:.0f} m/s  ·  Hs {sc.hs:.1f} m  ·  Tp {sc.tp:.0f} s", font=font(15), fill=P["muted"])
    d.text((W - 56 - d.textlength("SECTION, 2D AIRFLOW", font=font(14, True)), top + 14), "SECTION, 2D AIRFLOW",
           font=font(14, True), fill=P["muted"])
    # readouts (measured this frame)
    y = top + ph + 30
    plume = np.where(((sc.sec.T - sc.sec.t_ref) > 20).any(0))[0]
    vals = [("CREW ZONE AIR", f"+{series[-1][1]:.0f} °C", True), ("HEAVE", f"{sc.heave:+.1f} m", False),
            ("PITCH", f"{np.degrees(sc.pitch):+.1f}°", False)]
    x = 56
    for lab, val, hot in vals:
        d.text((x, y), lab, font=font(19, True), fill=P["ink"])
        x += d.textlength(lab + " ", font=font(19, True))
        d.text((x, y), val, font=font(19, True), fill=P["accent"] if hot else P["muted"])
        x += d.textlength(val, font=font(19, True)) + 34
    # chart: air temperature over the aft deck, drawn as time advances
    cx0, cy0, cw, chh = 56, y + 56, W - 112, 250
    d.text((cx0, cy0 - 4), "LOWEST EDGE OF THE HOT PLUME (>20 °C) ABOVE THE AFT DECK, m", font=font(14, True), fill=P["muted"])
    gy0, gy1 = cy0 + 26, cy0 + chh
    ymax = 30.0
    d.rectangle([cx0, gy1 - (gy1 - gy0) * 2.5 / ymax, cx0 + cw, gy1], fill="#4a2a2a")   # crew breathing zone
    d.text((cx0 + 8, gy1 - (gy1 - gy0) * 2.5 / ymax - 2), "crew zone 0–2.5 m", font=font(12), fill=P["accent"])
    for v in (0, 10, 20, 30):
        yy = gy1 - (gy1 - gy0) * v / ymax
        d.line([(cx0, yy), (cx0 + cw, yy)], fill="#4a3236", width=1)
        d.text((cx0 + cw - 30, yy - 18), f"{v}", font=font(13), fill=P["muted"])
    t0, t1 = series[0][0], series[0][0] + nframes * (series[1][0] - series[0][0] if len(series) > 1 else 1)
    pts = [(cx0 + cw * (t - t0) / (t1 - t0), gy1 - (gy1 - gy0) * min(max(h, 0), ymax) / ymax)
           for t, _, h in series if np.isfinite(h)]
    if len(pts) > 1:
        d.line(pts, fill=P["accent"], width=3)
    if pts:
        d.ellipse([pts[-1][0] - 5, pts[-1][1] - 5, pts[-1][0] + 5, pts[-1][1] + 5], fill=P["accent"])
    # deck + method
    yb = gy1 + 34
    d.text((56, yb), deck_text[0], font=font(22), fill=P["ink"])
    d.text((56, yb + 30), deck_text[1], font=font(22), fill=P["ink"])
    d.text((56, yb + 74), "Air: 2D Boussinesq stable fluids (Stam 1999), 0.4 m grid, IEC 61400-3 wind profile. Sea: JONSWAP.",
           font=font(14), fill=P["muted"])
    d.text((56, yb + 94), "DRAFT: vessel geometry, exhaust temperature (520 K) and weather are assumptions; ship motion display-grade.",
           font=font(14), fill=P["muted"])
    d.text((56, H - 52), "offshore_simulations", font=font(15, True), fill=P["muted"])
    img.save(out_path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out/film/psv_section.mp4")
    ap.add_argument("--seconds", type=float, default=5.0)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--hs", type=float, default=3.5)
    ap.add_argument("--tp", type=float, default=9.0)
    ap.add_argument("--u10", type=float, default=15.0)
    ap.add_argument("--only", type=int, default=None, help="render a single frame index (still check)")
    a = ap.parse_args()
    out = Path(a.out)
    frames = out.parent / "frames"
    frames.mkdir(parents=True, exist_ok=True)
    dt, sub, n = 0.015, 3, int(a.seconds * a.fps)

    def simulate(render_frames, deck_text=None):
        sc = Scene(a.hs, a.tp, a.u10)
        st = Streaks(sc)
        for _ in range(360):                                  # spin-up: let the wake and plume develop
            sc.step(dt)
            st.advance(dt)
        series = []
        for f in range(n):
            for _ in range(sub):
                sc.step(dt)
                if render_frames:
                    st.advance(dt)
            series.append((sc.t, sc.deck_air_excess(), sc.plume_height()))
            if render_frames and (a.only is None or f == a.only):
                render(sc, st, series, f, n, frames / f"f{f:04d}.png", deck_text)
                if a.only is not None:
                    return series, sc
        return series, sc

    series, _ = simulate(False)                               # pass 1: measure (deterministic)
    text = narration(series)
    print("narration:", " ".join(text))
    series, sc = simulate(True, text)                         # pass 2: render the same run
    if a.only is not None:
        print(frames / f"f{a.only:04d}.png")
        return
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(a.fps), "-i", str(frames / "f%04d.png"),
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", str(out)], check=True)
    print(out, f"{n} frames, sim {sc.t:.1f} s")


if __name__ == "__main__":
    main()
