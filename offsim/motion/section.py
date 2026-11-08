"""Section shot: the standard-pipeline home of the "section + map" film (docs/STYLE_REFERENCE.md).

A vertical sea section (2D Boussinesq air, JONSWAP sea, line-art vessel with heave and pitch), live readouts, a chart
measured in the solver, an optional real-layers map panel, and a deck sentence CHOSEN FROM MEASUREMENTS.

    render_section_shot(shot, sb, out_mp4, fps, report=None)

Storyboard shot (every physical input is `{value, src | assumption: true}`; the vessel is a profile name):
    - type: section            # alias: diptych (a section shot with a map)
      seconds: 5
      vessel: psv
      hs: {value: 2.0, assumption: true}       tp: {value: 6.5, assumption: true}
      u10: {value: 15, assumption: true}       t_exh: {value: 520, assumption: true}      # K
      kicker: "OUTER OSLOFJORD GALE  ·  SIMULATED"
      headline: {top: "WHERE DOES THE", accent: "EXHAUST", rest: "GO IN A GALE?"}
      map: {world: oslofjord, run: out/demo-oslofjord-supply, agent: PSV-1} | null
      narration:                               # offsim.motion.narrate rules over the MEASURED values below
        - {when: "deck_excess_max >= 5", text: "line one\nline two {deck_excess_max:.0f}"}
        - {text: "default"}

Two passes (the solver is deterministic): pass 1 runs the simulation and measures; the narration rules choose the deck
text from those numbers; pass 2 renders the same run. Measured names usable in narration (plus `flatten(report)`):
deck_excess_max, deck_excess_final (K = degC over ambient, 0.5-2.5 m above the aft cargo deck), plume_min_m, plume_seen
(1 if the >20 K plume reached the aft-deck columns), heave_max_m, pitch_max_deg, hs, tp, u10, t_exh.
Layout is the canonical 1080x1350 (4:5); another `size` is letterboxed with the ground colour.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from PIL import Image, ImageDraw, ImageFont

from offsim.cinema.look import PALETTES
from offsim.cinema.vessel_lineart import draw as draw_vessel, psv_profile
from offsim.motion import narrate
from offsim.physics import ocean
from offsim.physics.fluid2d import Section2D, obstacle_mask, wind_profile

ROOT = Path(__file__).resolve().parents[2]
P = PALETTES["section-plan"]
L_M, H_M, DX, SEA_Z, BOW_X, SHIP_L = 160.0, 50.0, 0.4, 10.0, 28.0, 85.0
W, H, SS = 1080, 1350, 2
from offsim.cinema.look import font_path   # Inter (SIL OFL), style rule 17
VESSELS = ("psv",)
INPUTS = ("hs", "tp", "u10", "t_exh")
MEASURED_NAMES = frozenset({"deck_excess_max", "deck_excess_final", "plume_min_m", "plume_seen", "heave_max_m",
                            "pitch_max_deg", "hs", "tp", "u10", "t_exh"})
SPINUP_STEPS = 360


def font(s, b=False):
    return ImageFont.truetype(font_path("Bold" if b else "Regular"), s)


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


def map_context(world="oslofjord", run="out/demo-oslofjord-supply", agent="PSV-1"):
    """Real layers for the map panel: coastline + the gated demo run's route for one vessel. The 'moment' shown in
    the section is the vessel's southernmost sailing point (outer fjord, most exposed). Returns None if absent."""
    import json

    import geopandas as gpd
    import pandas as pd
    land_p, traj_p, rep_p = ROOT / f"data/worlds/{world}/land.geojson", ROOT / run / "trajectory.csv", ROOT / run / "report.json"
    if not (land_p.exists() and traj_p.exists() and rep_p.exists()):
        return None
    rep = json.loads(rep_p.read_text())
    if not all(g["pass"] for k, g in rep["gates"].items() if k.startswith(("0", "1", "2", "3"))):
        return None                                           # never map a run that failed a gate
    tr = pd.read_csv(traj_p)
    tr = tr[tr.agent_id == agent].sort_values("t").reset_index(drop=True)
    sail = tr[tr.state == "sail"]
    k = int(sail.lat.idxmin())
    route = list(zip(tr.lon, tr.lat))
    lon, lat = np.array(route).T
    pad = 0.06
    bbox = (lon.min() - pad, lat.min() - pad * 0.6, lon.max() + pad, lat.max() + pad * 0.6)
    land = gpd.read_file(land_p).geometry.union_all()
    from shapely.geometry import box
    land = land.intersection(box(bbox[0] - 1.5, bbox[1] - 0.6, bbox[2] + 1.5, bbox[3] + 0.6))   # clip far outside the view
    return {"land": land, "bbox": bbox, "route": route, "k": k, "marker": route[k], "t_h": float(tr.t[k]) / 3600,
            "agent": agent, "paper": rep["paper"]["id"], "status": rep["status"]}


def measured_values(sc, series, heave_max=0.0, pitch_max=0.0):
    """Flat dict of what the solver measured over the shot (the only thing narration may talk about)."""
    deck = [v for _, v, _ in series]
    plume = [h for _, _, h in series if np.isfinite(h)]
    return {"deck_excess_max": float(max(deck)), "deck_excess_final": float(deck[-1]),
            "plume_min_m": float(min(plume)) if plume else float("nan"), "plume_seen": 1.0 if plume else 0.0,
            "heave_max_m": float(heave_max), "pitch_max_deg": float(pitch_max),
            "hs": sc.hs, "tp": sc.tp, "u10": sc.u10, "t_exh": sc.t_exh}


# the rules the original film used (kept as data so the wrapper tool and the demo storyboard share them)
PSV_GALE_NARRATION = [
    {"when": "deck_excess_max >= 5",
     "text": "Bow into the wind, the funnel's hot gas is caught in the lee of the bridge\n"
             "and reaches the cargo deck: up to +{deck_excess_max:.0f} °C in the crew's breathing zone."},
    {"when": "plume_seen > 0",
     "text": "Bow into the wind, the funnel's hot gas rolls into eddies behind the bridge\n"
             "but never comes lower than {plume_min_m:.0f} m above the cargo deck: the crew zone stays clear."},
    {"text": "Bow into the wind, the funnel's hot gas is carried away downwind\n"
             "and never reaches the cargo deck: the crew zone stays clear."},
]


def narration(series):
    """Back-compat: the original film's two deck lines for a measured series [(t, deck_excess, plume_height_m)]."""
    plume = [h for _, _, h in series if np.isfinite(h)]
    vals = {"deck_excess_max": float(max(v for _, v, _ in series)), "plume_seen": 1.0 if plume else 0.0,
            "plume_min_m": float(min(plume)) if plume else float("nan")}
    return tuple(deck_lines(PSV_GALE_NARRATION, vals))


def deck_lines(rules, values):
    """Narration text -> at most two deck lines (split on newline)."""
    lines = narrate.choose(rules, values).split("\n")
    if len(lines) > 2:
        raise narrate.NarrationError("the deck text has at most two lines")
    return lines + [""] * (2 - len(lines))


def assumption_line(shot):
    """The on-screen DRAFT / sourced line, generated from which inputs carry a src and which are assumptions."""
    def assumed(k):
        return bool(shot[k].get("assumption"))
    parts = ["vessel geometry"]
    if assumed("t_exh"):
        parts.append(f"exhaust temperature ({shot['t_exh']['value']:.0f} K)")
    if any(assumed(k) for k in ("hs", "tp", "u10")):
        parts.append("weather")
    txt = ""
    if len(parts) > 1:
        txt = "DRAFT: " + ", ".join(parts[:-1]) + f" and {parts[-1]} are assumptions; ship motion display-grade."
    else:
        txt = "DRAFT: vessel geometry is an assumption; ship motion display-grade."
    src = [f"{k} {shot[k]['src']}" for k in INPUTS if not assumed(k)]
    return txt + (("  Sourced: " + "; ".join(src) + ".") if src else "")


def render(sc, st, series, frame, nframes, out_path, deck_text, mp=None, ctx=None, shot=None, size=None):
    s = W / L_M
    top, ph = 236, int(W * H_M / L_M)
    img = Image.new("RGB", (W, H), P["ground"])
    d = ImageDraw.Draw(img)
    # header
    d.text((56, 44), shot["kicker"], font=font(17, True), fill=P["accent"])
    hf = font(52, True)
    hl = shot["headline"]
    d.text((56, 76), hl["top"], font=hf, fill=P["ink"])
    d.text((56, 136), hl["accent"], font=hf, fill=P["accent"])
    d.text((56 + d.textlength(hl["accent"] + " ", font=hf), 136), hl["rest"], font=hf, fill=P["ink"])
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
    vals = [("CREW ZONE AIR", f"+{series[-1][1]:.0f} °C", True), ("HEAVE", f"{sc.heave:+.1f} m", False),
            ("PITCH", f"{np.degrees(sc.pitch):+.1f}°", False)]
    x = 56
    for lab, val, hot in vals:
        d.text((x, y), lab, font=font(19, True), fill=P["ink"])
        x += d.textlength(lab + " ", font=font(19, True))
        d.text((x, y), val, font=font(19, True), fill=P["accent"] if hot else P["muted"])
        x += d.textlength(val, font=font(19, True)) + 34
    # chart: air temperature over the aft deck, drawn as time advances
    cx0, cy0, cw, chh = 56, y + 50, W - 112, 170
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
    # map panel: where this moment is, on the real coast (same clock: route drawn up to the moment, camera eases in)
    my0 = gy1 + 36
    if mp is not None:
        label = (shot.get("map") or {}).get("label") or ctx["paper"].upper().replace("-", " ")
        d.text((56, my0), f"WHERE: {ctx['agent']} ON THE {label}, {int(ctx['t_h'])} h {int(ctx['t_h'] % 1 * 60):02d} min IN",
               font=font(14, True), fill=P["muted"])
        panel = mp.frame((frame + 1) / nframes, ctx["route"], ctx["k"] + 1, ctx["marker"], wind=(sc.u10, 0.0))
        img.paste(panel.convert("RGB"), (56, my0 + 24))
        my1 = my0 + 24 + panel.size[1]
    else:
        my1 = my0
    # deck + method
    yb = my1 + 28
    d.text((56, yb), deck_text[0], font=font(22), fill=P["ink"])
    d.text((56, yb + 30), deck_text[1], font=font(22), fill=P["ink"])
    d.text((56, yb + 70), "Air: 2D Boussinesq stable fluids (Stam 1999), 0.4 m grid, IEC 61400-3 wind profile. Sea: JONSWAP.",
           font=font(13), fill=P["muted"])
    if ctx:
        d.text((56, yb + 88), f"Map: coastline OpenStreetMap (ODbL); route from offsim run {ctx['paper']} (gates 0-3 passed); map wind uniform.",
               font=font(13), fill=P["muted"])
    d.text((56, yb + 106), assumption_line(shot), font=font(13), fill=P["muted"])
    d.text((W - 56 - d.textlength("offshore_simulations", font=font(15, True)), 46), "offshore_simulations",
           font=font(15, True), fill=P["muted"])
    if size and tuple(size) != (W, H):
        img = fit(img, size)
    img.save(out_path)


def fit(img, size):
    """Scale the canonical frame into `size` (uniform, centred, ground-colour bars)."""
    w, h = size
    k = min(w / img.width, h / img.height)
    nw, nh = max(1, round(img.width * k)), max(1, round(img.height * k))
    small = img.resize((nw, nh), Image.LANCZOS)
    if (nw, nh) == (w, h):
        return small
    out = Image.new("RGB", (w, h), P["ground"])
    out.paste(small, ((w - nw) // 2, (h - nh) // 2))
    return out


def problems(shot, report=None):
    """Static validation of a section shot (no simulation): sourced inputs, narration rules and their names."""
    probs = []
    if str(shot.get("vessel")) not in VESSELS:
        probs.append(f"vessel {shot.get('vessel')!r} unknown; have {list(VESSELS)}")
    for k in INPUTS:
        v = shot.get(k)
        if not isinstance(v, dict) or not isinstance(v.get("value"), (int, float)) or isinstance(v.get("value"), bool):
            probs.append(f"{k}: needs {{value: <number>, src: ... | assumption: true}}")
        elif not (v.get("src") or v.get("assumption") is True):
            probs.append(f"{k}: value {v['value']} has no src and is not marked assumption: true")
    for k in ("kicker",):
        if not shot.get(k):
            probs.append(f"{k}: missing")
    hl = shot.get("headline")
    if not (isinstance(hl, dict) and all(isinstance(hl.get(x), str) and hl.get(x) for x in ("top", "accent", "rest"))):
        probs.append("headline: needs {top, accent, rest}")
    known = set(MEASURED_NAMES) | set(narrate.flatten(report or {}))
    probs += narrate.validate_rules(shot.get("narration"), known)
    m = shot.get("map")
    if m is not None and not (isinstance(m, dict) and all(m.get(x) for x in ("world", "run", "agent"))):
        probs.append("map: null or {world, run, agent}")
    if not (isinstance(shot.get("seconds"), (int, float)) and shot["seconds"] > 0):
        probs.append("seconds: needs a positive number")
    return probs


def run_section(shot, sb=None, frames_dir=".", fps=30, report=None, size=None, only=None, strict_map=True,
                spinup_steps=None, log=print):
    """Both passes. Writes PNG frames into frames_dir (all, or just frame `only`) and returns
    {"n", "frames", "measured", "deck", "map": bool}. Raises on invalid shot / missing map layers (strict_map)."""
    bad = problems(shot, report)
    if bad:
        raise ValueError("section shot refused:\n  " + "\n  ".join(bad))
    frames_dir = Path(frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)
    hs, tp, u10, t_exh = (float(shot[k]["value"]) for k in INPUTS)
    seconds = float(shot["seconds"])
    spin = SPINUP_STEPS if spinup_steps is None else int(spinup_steps)
    dt, sub, n = 0.015, 3, max(1, int(seconds * fps))

    ctx, mp = None, None
    if shot.get("map"):
        m = shot["map"]
        ctx = map_context(m["world"], m["run"], m["agent"])
        if ctx is None:
            if strict_map:
                raise FileNotFoundError(f"map layers absent or run failed a gate: world {m['world']!r}, run {m['run']!r}")
            log("map layers absent: rendering the section without the map panel")
        else:
            from offsim.motion.mappanel import MapPanel
            mp = MapPanel(ctx["land"], ctx["bbox"], size=(W - 112, 300), seconds=seconds)

    def simulate(render_frames, deck_text=None):
        sc = Scene(hs, tp, u10, t_exh)
        st = Streaks(sc) if render_frames else None
        for _ in range(spin):                                 # spin-up: let the wake and plume develop
            sc.step(dt)
            if st:
                st.advance(dt)
        series, files, hv, pv = [], [], 0.0, 0.0
        for f in range(n):
            for _ in range(sub):
                sc.step(dt)
                if st:
                    st.advance(dt)
            series.append((sc.t, sc.deck_air_excess(), sc.plume_height()))
            hv, pv = max(hv, abs(sc.heave)), max(pv, abs(float(np.degrees(sc.pitch))))
            if render_frames and (only is None or f == only):
                p = frames_dir / f"f{f:04d}.png"
                render(sc, st, series, f, n, p, deck_text, mp, ctx, shot, size)
                files.append(p)
                if only is not None:
                    break
        return series, sc, files, hv, pv

    series, sc, _, hv, pv = simulate(False)                   # pass 1: measure (deterministic)
    measured = measured_values(sc, series, hv, pv)
    deck = deck_lines(shot["narration"], {**narrate.flatten(report or {}), **measured})
    log("narration: " + " ".join(deck))
    _, sc, files, _, _ = simulate(True, deck)                 # pass 2: render the same run
    return {"n": n, "frames": files, "measured": measured, "deck": deck, "map": mp is not None, "sim_t": sc.t}


def encode(frames_dir, out, fps):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(fps), "-i", str(Path(frames_dir) / "f%04d.png"),
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", str(out)], check=True)


def render_section_shot(shot, sb, out_mp4, fps=30, report=None, size=None, frames_dir=None, keep_frames=False,
                        strict_map=True, spinup_steps=None, log=print):
    """Render a section shot to out_mp4. `size` (w, h) defaults to the canonical 1080x1350."""
    import shutil
    out = Path(out_mp4)
    out.parent.mkdir(parents=True, exist_ok=True)
    fd = Path(frames_dir) if frames_dir else out.with_suffix("").with_name(out.stem + "_frames")
    res = run_section(shot, sb, fd, fps, report, size, None, strict_map, spinup_steps, log)
    encode(fd, out, fps)
    if not keep_frames:
        shutil.rmtree(fd, ignore_errors=True)
    log(f"{out} {res['n']} frames, sim {res['sim_t']:.1f} s")
    return res
