"""The `intervention` shot kind (docs/VISUAL_GRAMMAR.md): one counterfactual, two stacked cases, one clock.

    A film is ONE thing switched, shown in TWO panels (two cases under the same treatment), with a physical field that fills
    each panel and visibly reorganises when the subject changes. Fixed camera, no chart, no colour bar, a static caption block.

Pipeline (everything is computed; nothing is keyframed or cross-faded):
  world     CAD solids at true scale (platform_jacket, s92, person: all registry qa-pass) -> hidden-line drawings for the
            linework, and the orthographic shadow of the same tessellated solids rasterised to the solver's obstacle mask
  forcing   inflow speed (and direction) from `report:` refs to the run's weather; literal numbers are refused
  solver    offsim.physics.panel2d.PanelSolver on the whole panel grid, subject switched at the event, run through the switch
  streaks   offsim.physics.streaks.FieldStreaks seeded over the whole panel, coloured by speed
  frame     two panels (1080 x 500 each), place + state chip per panel, static caption block; 1080 x 1350

Storyboard shot (see offsim/papers/<id>/storyboard.intervention.yaml):
    - type: intervention
      seconds: 20
      subject: s92_on_helideck
      forcing:                                  # every value is a report: ref (the run's weather), or an assumption
        direction: {value: from_left, assumption: true}
        cases:
          - {name: calm,  wind: "report:weather.hour.57.wind_mps", hs: "report:weather.hour.57.hs_m", place: FLORO}
          - {name: storm, wind: "report:weather.hour.250.wind_mps", hs: "report:weather.hour.250.hs_m", place: FLORO}
      kicker / headline / body / chips: see `problems()`; the headline is chosen by `narration:` rules over measured values

Cost (1080 x 1350, grid 300 x 139 cells of 0.4 m, ~9000 streaks per panel): see coordination/reports/V1.md.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from offsim.cinema import rules
from offsim.cinema.look import PALETTES
from offsim.motion import narrate

ROOT = Path(__file__).resolve().parents[2]
P = PALETTES["section-plan"]
W, H = 1080, 1350
INT = rules.INTERVENTION
FB = rules.FRAME_BUDGET


# ------------------------------------------------------------------------------------------------------ geometry
@dataclass(frozen=True)
class Geom:
    """Panel geometry in world metres (platform_jacket coordinates: z = height above the seabed) and pixels."""
    w_px: int = 1080
    h_px: int = 500
    px_per_m: float = 9.0
    dx_m: float = 0.4
    x0_m: float = -52.0
    z0_m: float = 134.0                    # 2 m below the 136 m still-water line (water depth 136 m, Solan)

    @property
    def nx(self):
        return int(round(self.w_px / self.px_per_m / self.dx_m))

    @property
    def nz(self):
        return int(round(self.h_px / self.px_per_m / self.dx_m))

    @property
    def sea_z(self):
        return 136.0

    def to_px(self, x, z, oy=0.0):
        return (x - self.x0_m) * self.px_per_m, oy + self.h_px - (z - self.z0_m) * self.px_per_m


G0 = Geom()
DECK_Z = 172.95                            # top of the helideck plate (platform_jacket helideck_plate)
HELIDECK_X = 16.44                         # centre of the plate (6.0 .. 26.88)
# parts of the platform that block the air. The jacket (vertical legs and braces), the topsides legs, the handrails, stairs, crane
# boom and flare boom are open lattice or slender members: air goes around and between them in 3D, but their side-view shadow is a
# wall in a 2D section (a vertical leg would seal the whole height), so they are drawn as linework and are NOT solid cells.
PLATFORM_SOLID = ("decks", "modules", "helideck", "helideck_plate", "lifeboats")
S92_SOLID = ("fuselage", "tailboom", "sponsons", "gear", "nacelles", "tailfin", "glazing")   # rotors are the momentum source
SS = 4


def _shadow_tris(shape, tf, tol=0.1):
    """Triangles of a tessellated CAD part projected to the (x, z) plane in world metres: (n, 3, 2)."""
    v, t = shape.tessellate(tol, 0.5)
    v = np.array([[p.x, p.z] for p in v], float)
    v = tf(v)
    return v[np.array(t, int)]


def raster_tris(tris, geom=G0):
    """Rasterise projected triangles to the solver grid: a cell is solid when at least half of it is covered."""
    nx, nz = geom.nx, geom.nz
    img = Image.new("L", (nx * SS, nz * SS), 0)
    d = ImageDraw.Draw(img)
    for tri in tris:
        pts = [((x - geom.x0_m) / geom.dx_m * SS, (nz * SS) - (z - geom.z0_m) / geom.dx_m * SS) for x, z in tri]
        d.polygon(pts, fill=255)
    a = np.asarray(img, float).reshape(nz, SS, nx, SS).mean(axis=(1, 3)) / 255.0
    return (a[::-1].T >= 0.5)


def _mirror(cx_model, cx_world):
    """Model x (forward) -> world x with the nose pointing LEFT (a helicopter lands into the wind, wind from the left)."""
    return lambda v: np.c_[cx_world - (v[:, 0] - cx_model), v[:, 1] + DECK_Z]


_WORLD_CACHE: dict = {}


def build_world(geom=G0):
    """Everything geometric, cached: platform + S-92 + persons as drawings (linework), triangles (fills) and solid masks."""
    key = geom
    if key in _WORLD_CACHE:
        return _WORLD_CACHE[key]
    from offsim.assets.cad import base, drawing
    plat = base.build("platform_jacket")
    tris = np.concatenate([_shadow_tris(plat.parts[k], lambda v: v, 0.1) for k in PLATFORM_SOLID])
    plat_d = drawing.project_cached("platform_jacket", None, "side")
    s92 = base.build("s92")
    s92_d = drawing.project_cached("s92", None, "side")
    x_lo, x_hi = s92_d.bbox[0], s92_d.bbox[2]
    cxm = 0.5 * (x_lo + x_hi)
    tf = _mirror(cxm, HELIDECK_X)
    s92_tris = np.concatenate([_shadow_tris(s92.parts[k], tf, 0.05) for k in S92_SOLID])
    s92_lines = [{"cls": l["cls"], "part": l["part"], "pts": [tuple(p) for p in tf(np.array(l["pts"], float))]} for l in s92_d.lines]
    sea = np.zeros((geom.nx, geom.nz), bool)
    sea[:, : int(round((geom.sea_z - geom.z0_m) / geom.dx_m))] = True
    world = raster_tris(tris, geom) | sea
    persons = build_persons(geom)
    out = {"world": world, "sea": sea, "platform_tris": tris, "platform_drawing": plat_d, "s92_tris": s92_tris,
           "s92_lines": s92_lines, "s92_solid": raster_tris(s92_tris, geom), "persons": persons,
           "rotor": rotor_geometry(s92_d, tf, geom)}
    for p in persons:
        out["world"] = out["world"] | p["solid"]
    _WORLD_CACHE[key] = out
    return out


# scale figures: stature 1.75 m (person asset, registry qa-pass, anthropometric table); standing on the main deck and the helideck apron
PERSON_SPOTS = ((-2.0, 170.95), (1.2, 170.95), (4.6, 172.95))


def build_persons(geom=G0):
    from offsim.assets.cad import base, drawing
    pm = base.build("person")
    pd_ = drawing.project_cached("person", None, "side")
    out = []
    for (x, z) in PERSON_SPOTS:
        shift = lambda v, x=x, z=z: np.c_[v[:, 0] + x, v[:, 1] + z]
        tris = np.concatenate([_shadow_tris(s, shift, 0.02) for s in pm.parts.values()])
        lines = [{"cls": l["cls"], "part": l["part"], "pts": [tuple(p) for p in shift(np.array(l["pts"], float))]} for l in pd_.lines]
        out.append({"x": x, "z": z, "lines": lines, "tris": tris, "solid": raster_tris(tris, geom), "height_m": float(pd_.bbox[3] - pd_.bbox[1])})
    return out


def rotor_geometry(s92_d, tf, geom):
    """Rotor disc in world metres: centre x, hub height, radius, from the S-92 drawing (part 'rotor')."""
    pts = np.array([p for l in s92_d.lines if l["part"] == "rotor" for p in l["pts"]], float)
    xc = 0.5 * (pts[:, 0].min() + pts[:, 0].max())
    r = 0.5 * (pts[:, 0].max() - pts[:, 0].min())
    zc = float(pts[:, 1].mean())
    c = tf(np.array([[xc, zc]]))[0]
    return {"x": float(c[0]), "z": float(c[1]), "r": float(r)}


# ------------------------------------------------------------------------------------------------------ forcing (report: refs)
REF = re.compile(r"^report:[A-Za-z_][\w.]*$")


def weather_view(report, scenario=None, data_root=None):
    """The run's weather as report-ref nodes. `report.json` does not carry the weather series, so it is re-loaded from the
    scenario's `weather:` block with the loader the run itself used (offsim.pipeline.load_weather; deterministic), the same series
    the main simulation used (weather_years[0]). Nodes: weather.hour.<h>.{wind_mps,hs_m,tp_s}; weather.min / q10 / q50 / q90 / max
    (the hour with that wind quantile, with `.hour`); weather.synthetic (1/0); weather.source. A report that already has a
    `weather` block is returned unchanged."""
    if isinstance(report.get("weather"), dict):
        return report
    from offsim import pipeline
    spec = (scenario or {}).get("weather") or ((scenario or {}).get("ensemble") or {}).get("weather")
    if not spec:
        return report
    years, synthetic = pipeline.load_weather(spec, data_root)
    df = years[0].df
    hours = {}
    for h, r in enumerate(df.itertuples()):
        hours[str(h)] = {"wind_mps": float(r.wind_mps), "hs_m": float(r.hs_m), "tp_s": float(getattr(r, "tp_s", float("nan")))}
    w = df["wind_mps"].to_numpy()
    node = {"hour": hours, "synthetic": 1 if synthetic else 0, "source": str(years[0].source), "n_hours": len(df)}
    order = np.argsort(w, kind="stable")
    for tag, q in (("min", 0.0), ("q10", 0.10), ("q50", 0.5), ("q90", 0.9), ("max", 1.0)):
        h = int(order[min(len(order) - 1, int(round(q * (len(order) - 1))))])
        node[tag] = {**hours[str(h)], "hour": h}
    return {**report, "weather": node}


def resolve_ref(ref, view):
    if not (isinstance(ref, str) and REF.match(ref)):
        raise ValueError(f"forcing values must be report refs like 'report:weather.max.wind_mps', got {ref!r}")
    node = view
    for k in ref[len("report:"):].split("."):
        node = node[k]
    return node


# ------------------------------------------------------------------------------------------------------ subject
def s92_subject(geom, world, mtow_kg=12020.0, thrust_frac=0.1, thick_cells=3, rho=1.225):
    """The S-92 on the helideck: the fuselage as solid cells and the rotor as a downward momentum source.
    Disc loading DL = thrust_frac * MTOW g / (pi R^2) is kept in the 2D section (pressure jump over the disc thickness h gives
    a body force a = DL / (rho h) per cell). The rotor radius comes from the CAD asset (s92, EASA TCDS R.011 / CAP 437); MTOW
    and thrust_frac are assumptions of the shot (a helicopter on a deck has rotors turning at low collective)."""
    from offsim.physics.panel2d import Subject
    r = world["rotor"]
    nx, nz = geom.nx, geom.nz
    xs = geom.x0_m + (np.arange(nx) + 0.5) * geom.dx_m
    zs = geom.z0_m + (np.arange(nz) + 0.5) * geom.dx_m
    disc = (np.abs(xs[:, None] - r["x"]) <= r["r"]) & (zs[None, :] >= r["z"]) & (zs[None, :] < r["z"] + thick_cells * geom.dx_m)
    disc &= ~world["s92_solid"]
    dl = thrust_frac * mtow_kg * 9.81 / (math.pi * r["r"] ** 2)
    a = dl / (rho * thick_cells * geom.dx_m)
    fz = np.where(disc, -a, 0.0)
    return Subject("S-92 on the helideck", solid=world["s92_solid"].copy(), accel=(np.zeros_like(fz), fz),
                   meta={"disc_loading_pa": dl, "accel_ms2": a, "rotor_radius_m": r["r"], "disc_cells": int(disc.sum())})


# ------------------------------------------------------------------------------------------------------ cases
FPS = 30
SUBSTEPS = 2                       # solver steps per frame (dt = 1/60 s); CFL stays < 1.5 at the downwash jet
SPINUP_S = 20.0                    # film clock offset of the pre-roll (the solver time at film t = 0)
MASTER_U, MASTER_S = 8.0, 18.0      # reference speed (m/s) and seconds of the one-off flush every case starts from
TAIL_S = 0.8                       # seconds of motion a streak remembers: length = speed x TAIL_S
STRIDE_U = 4.5                     # a panel whose wind is below this keeps its tail points 4.5 / U frames apart (1 to 3), so a calm panel still shows streaks;
                                   # colour keeps one speed scale across panels, so the comparison between panels is not lost
WINDOW_S = 2.0                     # measurement windows: the last 2 s of the before and the after act
NU, SMAG = 0.03, 0.08               # explicit viscosity m2/s and Smagorinsky coefficient: the display-grade stand-in for sub-grid turbulence
TOP = "lid"                         # free-slip lid: an open top lets the spin-up momentum persist (the inlet no longer sets the flux); the cost is blockage (reported)


def acts(seconds):
    """{act: (t0, t1)} from rules.INTERVENTION['acts'] (fractions of the film)."""
    a = INT["acts"]
    b = a["before"] * seconds
    e = a["event"] * seconds
    return {"before": (0.0, b), "event": (b, b + e), "after": (b + e, seconds)}


def dim_at(t, seconds):
    """Panel luminance multiplier (a share of the before act): dims over the first quarter of the event, holds, returns over the last."""
    lo = 0.5 * (INT["event_dim"][0] + INT["event_dim"][1])
    t0, t1 = acts(seconds)["event"]
    if t <= t0 or t >= t1:
        return 1.0
    u = (t - t0) / (t1 - t0)
    def sm(x):
        x = min(1.0, max(0.0, x))
        return x * x * (3 - 2 * x)
    k = sm(u / 0.25) if u < 0.5 else sm((1 - u) / 0.25)
    return 1.0 - (1.0 - lo) * k


def state_index(t, seconds):
    a = acts(seconds)
    return 0 if t < a["event"][0] else (1 if t < a["event"][1] else 2)


_MASTER: dict = {}


def master_field(geom, world, subject, u_master=MASTER_U, seconds=MASTER_S, seed=1):
    """The flushed before-state at a reference speed, computed once per (geometry, subject): the panel solved from rest for `seconds`
    (about one flush time at u_master) with the subject on. Returns the face arrays (u, w)."""
    from offsim.physics.fluid2d import wind_profile
    from offsim.physics.panel2d import PanelSolver
    key = (geom, id(subject), u_master, seconds, seed)
    if key not in _MASTER:
        zc = geom.z0_m + (np.arange(geom.nz) + 0.5) * geom.dx_m
        s = PanelSolver(geom.nx, geom.nz, geom.dx_m, world["world"], wind_profile(np.maximum(zc - geom.sea_z, 0.5), u_master), seed=seed,
                        nu=NU, smag=SMAG, top=TOP)
        s.set_subject(subject)
        t = 0.0
        while t < seconds:
            h = min(0.02, 1.6 * s.dx / max(float(np.abs(s.u).max()), float(np.abs(s.w).max()), 1e-6))
            s.step(h)
            t += h
        _MASTER[key] = (s.u.copy(), s.w.copy())
    return _MASTER[key]


class Case:
    """One panel: its own solver, streaks and measurements. Same geometry, same subject, same clock as the other case."""

    def __init__(self, name, u10, hs, geom, world, subject, seconds, seed, n_streaks=5500, grid_scale=1.0, label=""):
        from offsim.physics.fluid2d import wind_profile
        from offsim.physics.panel2d import PanelSolver
        from offsim.physics.streaks import FieldStreaks
        self.name, self.u10, self.hs, self.geom, self.world, self.seconds, self.label = name, float(u10), float(hs), geom, world, seconds, label
        zc = geom.z0_m + (np.arange(geom.nz) + 0.5) * geom.dx_m
        prof = wind_profile(np.maximum(zc - geom.sea_z, 0.5), self.u10)
        self.solver = PanelSolver(geom.nx, geom.nz, geom.dx_m, world["world"], prof, seed=seed, nu=NU, smag=SMAG, top=TOP)
        self.subject = subject
        self.solver.set_subject(subject)
        t_switch = SPINUP_S + 0.5 * (acts(seconds)["event"][0] + acts(seconds)["event"][1])
        self.solver.schedule(t_switch, None)
        self.t_switch = t_switch
        self.streaks = FieldStreaks(self.solver.solid, geom.dx_m, n=n_streaks, tail=int(round(TAIL_S * FPS)), seed=seed + 100,
                                    px_per_m=geom.px_per_m, stride=int(np.clip(round(STRIDE_U / max(self.u10, 1.5)), 1, 3)))
        self._solid_id = id(self.solver.solid)
        self.acc = {"before": [], "after": []}
        self.metrics = []                                # per-frame (cover, static)
        self.frame = -1
        self.spun = False

    @property
    def t(self):
        return self.solver.time - SPINUP_S

    def spin_up(self, master=None, t_hold=4.0, u_master=MASTER_U):
        """Pre-roll to the before-act equilibrium. A calm case would need minutes to flush the starting vortices out of a 120 m
        panel, so the panel is first flushed once at a reference speed (`master_field`: subject on, the same geometry), and each
        case starts from that field scaled by U / u_master (an inviscid flow is self-similar under a speed scale: the same wake,
        evolving more slowly) and then runs t_hold seconds at its own forcing, so the subject's local balance and the inflow
        perturbation are the case's own. The film clock starts at the end (t = 0)."""
        s = self.solver
        u0, w0 = master if master is not None else master_field(self.geom, self.world, self.subject, u_master=u_master)
        k = self.u10 / u_master
        s.u[:] = u0 * k
        s.w[:] = w0 * k
        s._close_faces()
        s._project()
        sw = s._switches
        s._switches = []
        t = 0.0
        while t < t_hold:
            h = min(0.02, 1.6 * s.dx / max(float(np.abs(s.u).max()), float(np.abs(s.w).max()), 1e-6))
            s.step(h)
            t += h
        s.time = SPINUP_S                                  # exact film t = 0
        s._switches = sw
        self.spin_s = t_hold
        self.spun = True
        for _ in range(int(TAIL_S * FPS) + 2):             # let the streak tails fill (no frame is drawn from these)
            self.streaks.advance(s.u, s.w, 1.0 / FPS)

    def advance_frame(self):
        """One film frame: SUBSTEPS solver steps then one streak step; records measurement windows."""
        s = self.solver
        for _ in range(SUBSTEPS):
            s.step(1.0 / (FPS * SUBSTEPS))
        if id(s.solid) != self._solid_id:                 # the subject switched: the geometry changed under the streaks
            self.streaks.set_solid(s.solid)
            self._solid_id = id(s.solid)
        self.streaks.advance(s.u, s.w, 1.0 / FPS)
        self.frame += 1
        t = self.t
        a = acts(self.seconds)
        uc, wc = s.cell_velocity()
        spd = np.hypot(uc, wc)
        if a["before"][1] - WINDOW_S <= t < a["before"][1]:
            self.acc["before"].append(spd.copy())
        if t >= a["after"][1] - WINDOW_S - 1e-9:
            self.acc["after"].append(spd.copy())
        self.metrics.append(self.streaks.measure())

    def measured(self, prefix=""):
        """Numbers the solver measured: how much the field moved between the end of the before act and the end of the after act."""
        g = self.geom
        if not self.acc["before"] or not self.acc["after"]:
            return {}
        b, a = np.mean(self.acc["before"], axis=0), np.mean(self.acc["after"], axis=0)
        free = ~(self.solver.solid | self.world["s92_solid"])          # cells fluid in both states
        free &= ~self.world["world"]
        ref = max(self.u10, 0.5)
        changed = (np.abs(a - b) > 0.15 * ref) & free
        xs = g.x0_m + (np.arange(g.nx) + 0.5) * g.dx_m
        zs = g.z0_m + (np.arange(g.nz) + 0.5) * g.dx_m
        box = (xs[:, None] >= 6.0) & (xs[:, None] <= 27.0) & (zs[None, :] > DECK_Z + 0.4) & (zs[None, :] <= DECK_Z + 7.0) & free
        lee = (xs[:, None] > 27.0) & (zs[None, :] > g.sea_z) & free
        sb, sa = (np.std(self.acc["before"], axis=0), np.std(self.acc["after"], axis=0))
        out = {"reorg_share": float(changed.sum() / max(free.sum(), 1)),
               "deck_speed_before": float(b[box].mean()), "deck_speed_after": float(a[box].mean()),
               "deck_change": float(abs(a[box].mean() - b[box].mean()) / ref),
               "deck_turb_before": float(sb[box].mean() / ref), "deck_turb_after": float(sa[box].mean() / ref),
               "lee_change": float(np.abs(a - b)[lee].mean() / ref), "u10": self.u10}
        return {f"{prefix}{k}": v for k, v in out.items()}

    def snapshot(self):
        """What a frame needs (copies): streak tails, solid mask, speed colour source, subject presence, measure."""
        s = self.solver
        uc, wc = s.cell_velocity()
        return {"hist": self.streaks.hist.copy(), "solid": s.solid.copy(), "speed": np.hypot(uc, wc), "t": self.t,
                "subject_on": s.subject is not None, "measure": dict(self.metrics[-1]) if self.metrics else {}}


# ------------------------------------------------------------------------------------------------------ frame
import skia                                                    # noqa: E402

from offsim.cinema.draw import Canvas                          # noqa: E402
from offsim.cinema.look import font_path                       # noqa: E402

SS_FRAME = 2
PANEL_H = G0.h_px
CAPTION_TOP = 2 * PANEL_H
LINE_W = {"outline": 1.5, "visible": 0.95, "detail": 0.7}      # px at 1x: 9 px per metre carries finer lines than the 2.4 / 1.3 / 0.8 set
_ASC: dict = {}


def _ascent(size, weight):
    k = (size, weight)
    if k not in _ASC:
        f = skia.Font(skia.Typeface.MakeFromFile(font_path(weight)), float(size))
        _ASC[k] = -f.getMetrics().fAscent
    return _ASC[k]


def _text(cv, x, top, s, size, weight="Regular", color="#ffffff", anchor="l", tracking=0.0):
    cv.text(x, top + _ascent(size, weight), s, font=("Inter", weight), size=size, color=color, tracking=tracking, anchor=anchor)


def _paint(color, alpha=1.0, stroke=False, width=1.0):
    from offsim.cinema.draw import _paint as dp
    return dp(color, alpha, stroke, width)


_PATHS: dict = {}


def _tri_path(tris, to_px):
    path = skia.Path()
    for t in tris:
        (x0, y0), (x1, y1), (x2, y2) = (to_px(x, z) for x, z in t)
        path.moveTo(x0, y0)
        path.lineTo(x1, y1)
        path.lineTo(x2, y2)
        path.close()
    return path


def _cached_path(key, tris, geom):
    k = (key, geom)
    if k not in _PATHS:
        _PATHS[k] = _tri_path(tris, lambda x, z: geom.to_px(x, z))
    return _PATHS[k]


def _lut():
    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list("st", [P["streak_lo"], P["streak_hi"]])       # greys only: the subject is the only saturated element
    return (np.array([cmap(i / 63)[:3] for i in range(64)]) * 255).astype(int)


STREAK = {"width": 1.9, "alpha": 160, "n": None, "tail": None}     # how the tails are drawn (the solver's streak count is separate)


def draw_streaks(cv, snap, geom, vmax, dim=1.0):
    hist, speed = snap["hist"], snap["speed"]
    if STREAK["n"]:
        hist = hist[:STREAK["n"]]
    if STREAK["tail"]:
        hist = hist[:, :STREAK["tail"]]
    h0, h1 = hist[:, 0], hist[:, 1]
    ok = np.isfinite(h0[:, 0]) & np.isfinite(h1[:, 0])
    ix = np.clip(np.nan_to_num(h0[:, 0]).astype(int), 0, geom.nx - 1)
    iz = np.clip(np.nan_to_num(h0[:, 1]).astype(int), 0, geom.nz - 1)
    ci = np.clip((speed[ix, iz] / vmax * 63).astype(int), 0, 63)
    lut = _lut()
    s = geom.px_per_m * geom.dx_m
    n = hist.shape[1]
    X = hist[:, :, 0] * s
    Y = geom.h_px - hist[:, :, 1] * s
    buckets: dict = {}
    for k in np.nonzero(ok)[0]:
        xs, ys = X[k], Y[k]
        good = np.isfinite(xs)
        m = int(good.sum())
        if m < 2:
            continue
        # one segment run per (colour, alpha-band): the tail fades towards its oldest point
        for band in range(4):
            a, b = band * n // 4, min(n - 1, (band + 1) * n // 4)
            seg = [(xs[i], ys[i]) for i in range(a, b + 1) if good[i]]
            if len(seg) >= 2:
                buckets.setdefault((int(ci[k]), band), []).append(seg)
    for (c, band), segs in buckets.items():
        r, g, b = (int(v) for v in lut[c])
        path = skia.Path()
        for seg in segs:
            path.moveTo(float(seg[0][0]), float(seg[0][1]))
            for x, y in seg[1:]:
                path.lineTo(float(x), float(y))
        paint = skia.Paint(AntiAlias=True, Color=skia.Color(r, g, b, int(STREAK["alpha"] * (1.0 - band / 4.2))))
        paint.setStyle(skia.Paint.kStroke_Style)
        paint.setStrokeWidth(STREAK["width"] / max(dim, 0.5))      # the event dim lowers contrast; widen so the tails stay legible
        paint.setStrokeCap(skia.Paint.kRound_Cap)
        paint.setStrokeJoin(skia.Paint.kRound_Join)
        cv.cv.drawPath(path, paint)


def draw_lines(cv, lines, geom, colors=None, scale=1.0):
    to_px = lambda x, z: geom.to_px(x, z)
    colors = colors or {}
    for cls in ("detail", "visible", "outline"):
        segs = [l for l in lines if l["cls"] == cls]
        for part in {l["part"] for l in segs}:
            pl = [[to_px(x, z) for x, z in l["pts"]] for l in segs if l["part"] == part]
            col = colors.get(part, colors.get("*", P["muted"] if cls == "detail" else P["ink"]))
            cv.lines(pl, col, LINE_W[cls] * scale)


def chip(cv, x, top, label, color, anchor="l", size=16):
    """A pill with a flat ground fill behind its text, so the text always has one background colour."""
    wd = cv.measure(label, ("Inter", "Bold"), size, 1.2)
    pad = 11
    x0 = x if anchor == "l" else x - wd - 2 * pad
    rect = skia.Rect.MakeXYWH(float(x0), float(top), float(wd + 2 * pad), float(size + 2 * 8))
    cv.cv.drawRoundRect(rect, 6.0, 6.0, _paint(P["ground"], 0.94))
    cv.cv.drawRoundRect(rect, 6.0, 6.0, _paint(color, 0.55, True, 0.8))
    _text(cv, x0 + pad, top + 8, label, size, "Bold", color, tracking=1.2)
    return x0, top, x0 + wd + 2 * pad, top + size + 16


def draw_panel(cv, snap, case, geom, world, vmax, oy, dim, chips):
    """One scene panel at vertical offset oy. Layers, bottom to top: ground, sea, streaks, solid fills, linework, subject, figures."""
    cv.cv.save()
    cv.cv.clipRect(skia.Rect.MakeXYWH(0.0, float(oy), float(geom.w_px), float(geom.h_px)))
    cv.cv.translate(0.0, float(oy))
    cv.cv.drawRect(skia.Rect.MakeXYWH(0.0, 0.0, float(geom.w_px), float(geom.h_px)), _paint(P["ground_deep"]))
    sea_y = geom.to_px(0, geom.sea_z)[1]
    cv.cv.drawRect(skia.Rect.MakeXYWH(0.0, float(sea_y), float(geom.w_px), float(geom.h_px - sea_y)), _paint(P["sea"]))
    draw_streaks(cv, snap, geom, vmax, dim)
    cv.line([(0, sea_y), (geom.w_px, sea_y)], P["streak_hi"], 1.2)
    cv.cv.drawPath(_cached_path("platform", world["platform_tris"], geom), _paint("#4a2b2d", 1.0))
    draw_lines(cv, world["platform_drawing"].lines, geom)
    for p in world["persons"]:
        cv.cv.drawPath(_cached_path(f"person{p['x']}", p["tris"], geom), _paint(P["ink"], 0.22))
        draw_lines(cv, p["lines"], geom, {"*": P["ink"]}, 0.9)
    if snap["subject_on"]:
        cv.cv.drawPath(_cached_path("s92", world["s92_tris"], geom), _paint(P["accent"], 0.30))
        draw_lines(cv, world["s92_lines"], geom, {"*": P["accent"], "rotor": P["accent"], "tail_rotor": P["accent"]}, 1.0)
    if dim < 1.0:
        cv.cv.drawRect(skia.Rect.MakeXYWH(0.0, 0.0, float(geom.w_px), float(geom.h_px)), _paint(P["ground_deep"], 1.0 - dim))
    cv.cv.restore()
    place, state = chips
    boxes = [chip(cv, 44, oy + 30, place, P["accent"]), chip(cv, geom.w_px - 44, oy + 30, state, P["ink"], anchor="r")]
    return boxes


def draw_caption(cv, kicker, headline, body, handle):
    cv.line([(0, CAPTION_TOP), (W, CAPTION_TOP)], P["muted"], 0.8)
    _text(cv, 56, CAPTION_TOP + 32, kicker, 16, "Bold", P["muted"], tracking=1.6)
    y = CAPTION_TOP + 66
    for line in headline:
        x = 56
        for text, accent in line:
            _text(cv, x, y, text, 48, "Bold", P["accent"] if accent else P["ink"])
            x += cv.measure(text, ("Inter", "Bold"), 48)
        y += 56
    y += 22
    for line in body:
        _text(cv, 56, y, line, 21, "Regular", P["ink"])
        y += 29
    _text(cv, 56, 1290, handle, 16, "Bold", P["muted"], tracking=1.0)


def render_frame(snaps, cases, geom, world, seconds, text, out_path=None, vmax=12.0):
    """The delivered frame (1080 x 1350) from one snapshot per case. `text` = dict(kicker, headline, body, handle, place[2], states[3]).
    Returns (PIL image, meta) where meta is what the visual gate cannot see in pixels: panels, figures, elements, field measures."""
    cv = Canvas(W, H, bg=P["ground"], ss=SS_FRAME)
    t = snaps[0]["t"]
    dim = dim_at(t, seconds)
    si = state_index(t, seconds)
    boxes = []
    for k, (sn, case) in enumerate(zip(snaps, cases)):
        boxes += draw_panel(cv, sn, case, geom, world, vmax, k * PANEL_H, dim, (text["place"][k], text["states"][si]))
    draw_caption(cv, text["kicker"], text["headline"], text["body"], text["handle"])
    cv.line([(0, PANEL_H), (W, PANEL_H)], P["muted"], 0.8)
    img = cv.to_pil()
    figs = [sum(1 for p in world["persons"] if p["height_m"] * geom.px_per_m >= 12.0) for _ in cases]
    meta = {"panels": [[k * PANEL_H / H, (k + 1) * PANEL_H / H] for k in range(len(cases))], "scale_figures": figs,
            "field": [{"cover": sn["measure"].get("cover"), "static": sn["measure"].get("static")} for sn in snaps],
            "elements": ["scene_panel", "chip", "caption"], "t": t, "act": ("before", "event", "after")[si], "dim": dim}
    if out_path:
        img.save(out_path)
    return img, meta


# ------------------------------------------------------------------------------------------------------ the shot
SUBJECTS = ("s92_on_helideck",)
SHOT_KEYS = {"type", "seconds", "subject", "subject_params", "forcing", "kicker", "kicker_values", "headline", "body", "chips", "handle",
             "visual", "seed", "streaks"}
FORBIDDEN_KEYS = ("camera", "chart", "map", "readouts", "readout", "colour_bar", "color_bar", "footnote", "methods", "inset")
MEASURED_NAMES = frozenset({"wind_lo", "wind_hi", "reorg_min", "deck_change_min"} | {f"case{i}.{k}" for i in (0, 1) for k in (
    "reorg_share", "deck_speed_before", "deck_speed_after", "deck_change", "deck_turb_before", "deck_turb_after", "lee_change", "u10")})


def _words(text):
    return len(re.findall(r"\S+", re.sub(r"\{[^{}]*\}", "X", str(text).replace("|", ""))))


def is_draft(shot, view):
    """DRAFT when the weather is synthetic or any forcing / subject input is an assumption (VISUAL_GRAMMAR section 4)."""
    wx = (view.get("weather") or {})
    if wx.get("synthetic"):
        return True
    items = [shot.get("forcing", {}).get("direction")] + list((shot.get("subject_params") or {}).values())
    return any(isinstance(v, dict) and v.get("assumption") for v in items)


def problems(shot, report_view, sb=None):
    """Static validation of an intervention shot (no simulation). Refusals, one string each."""
    probs = []
    extra = set(shot) - SHOT_KEYS
    if extra:
        probs.append(f"keys not allowed in an intervention shot: {sorted(extra)}")
    bad = [k for k in FORBIDDEN_KEYS if k in shot]
    if bad:
        probs.append(f"an intervention shot has no {', '.join(bad)} (docs/VISUAL_GRAMMAR.md section 4: fixed camera, no chart, no readout row, no footnote)")
    lo, hi = INT["film_s"]
    sec = shot.get("seconds")
    if not (isinstance(sec, (int, float)) and lo <= sec <= hi):
        probs.append(f"seconds: {sec!r} outside the film length {lo:g} to {hi:g} s (rules.INTERVENTION['film_s'])")
    if shot.get("subject") not in SUBJECTS:
        probs.append(f"subject: {shot.get('subject')!r} unknown; have {list(SUBJECTS)}")
    f = shot.get("forcing")
    if not isinstance(f, dict):
        return probs + ["forcing: needs {direction, cases: [{place, wind, hs}, ...]} with report: refs"]
    cases = f.get("cases")
    if not (isinstance(cases, list) and len(cases) == INT["cases"]):
        probs.append(f"forcing.cases: needs exactly {INT['cases']} cases (two instances under the same treatment), got {cases if not isinstance(cases, list) else len(cases)}")
        cases = []
    values = {}
    for i, c in enumerate(cases):
        for k in ("wind", "hs"):
            v = c.get(k) if isinstance(c, dict) else None
            if not (isinstance(v, str) and REF.match(v)):
                probs.append(f"forcing.cases[{i}].{k}: must be a report: ref to the run's weather, got {v!r} (literal forcing numbers are refused: a field with invented forcing is decoration)")
                continue
            try:
                val = resolve_ref(v, report_view)
                if not isinstance(val, (int, float)) or isinstance(val, bool) or not math.isfinite(val):
                    raise TypeError(f"{v} is not a finite number ({val!r})")
                values[(i, k)] = float(val)
            except Exception as e:
                probs.append(f"forcing.cases[{i}].{k}: {type(e).__name__}: {e}")
        if not (isinstance(c, dict) and c.get("place")):
            probs.append(f"forcing.cases[{i}].place: missing")
    d = f.get("direction")
    if isinstance(d, str) and REF.match(d):
        pass
    elif not (isinstance(d, dict) and d.get("value") in ("from_left",) and (d.get("src") or d.get("assumption") is True)):
        probs.append(f"forcing.direction: needs {{value: from_left, src: ... | assumption: true}} (from_right is not built) or a report: ref, got {d!r}")
    for k, v in (shot.get("subject_params") or {}).items():
        if not (isinstance(v, dict) and isinstance(v.get("value"), (int, float)) and (v.get("src") or v.get("assumption") is True)):
            probs.append(f"subject_params.{k}: needs {{value: <number>, src: ... | assumption: true}}")
    ch = (shot.get("chips") or {}).get("states")
    if not (isinstance(ch, list) and len(ch) == INT["state_chips"] and all(isinstance(x, str) and x for x in ch)):
        probs.append(f"chips.states: needs {INT['state_chips']} plain phrases (before, event, after)")
    k = shot.get("kicker")
    names = {"status", "lo", "hi"} | set((shot.get("kicker_values") or {}))
    if not (isinstance(k, str) and "{status}" in k):
        probs.append("kicker: a template containing {status} (it becomes DRAFT, SIMULATED when the weather or a forcing input is assumed)")
    else:
        used = set(re.findall(r"\{([A-Za-z_]\w*)", k))
        if used - names:
            probs.append(f"kicker: placeholders {sorted(used - names)} are not defined (have {sorted(names)})")
    for n, ref in (shot.get("kicker_values") or {}).items():
        try:
            resolve_ref(ref, report_view)
        except Exception as e:
            probs.append(f"kicker_values.{n}: {type(e).__name__}: {e}")
    known = set(MEASURED_NAMES) | set(narrate.flatten(report_view))
    hl, body = shot.get("headline"), shot.get("body")
    probs += [f"headline: {p}" for p in narrate.validate_rules(hl, known)]
    probs += [f"body: {p}" for p in narrate.validate_rules(body, known)]
    for r in hl or []:
        t = str(r.get("text", ""))
        if _words(t) > INT["headline_words_max"]:
            probs.append(f"headline: {_words(t)} words > {INT['headline_words_max']}: {t!r}")
        if t.count("|") != 2 or len(t.split("\n")) > 2:
            probs.append(f"headline: needs exactly one |accent phrase| and at most two lines: {t!r}")
    for r in body or []:
        if _words(r.get("text", "")) > INT["body_words_max"]:
            probs.append(f"body: {_words(r.get('text', ''))} words > {INT['body_words_max']}")
        if len(str(r.get("text", "")).split("\n")) > 3:
            probs.append("body: at most three lines")
    if not shot.get("handle"):
        probs.append("handle: missing")
    return probs


def _forcing(shot, view):
    cs = shot["forcing"]["cases"]
    return [{"place": c["place"], "u10": float(resolve_ref(c["wind"], view)), "hs": float(resolve_ref(c["hs"], view))} for c in cs]


def _subject_params(shot):
    sp = shot.get("subject_params") or {}
    out = {}
    if "mtow_kg" in sp:
        out["mtow_kg"] = float(sp["mtow_kg"]["value"])
    if "thrust_frac" in sp:
        out["thrust_frac"] = float(sp["thrust_frac"]["value"])
    return out


def _segments(line):
    parts = line.split("|")
    return [(p, i % 2 == 1) for i, p in enumerate(parts) if p]


def run_intervention(shot, sb=None, report=None, out_dir=".", times=None, quick=False, scenario=None, log=print, n_streaks=5500):
    """Simulate both cases through the whole film once (pass 1, with a snapshot at every requested film time), choose the headline
    and body from what the solver measured, then draw the snapshots (pass 2). `times` = film seconds to draw (default: the three
    stills, one per act). quick = a short spin-up and one frame (the dry-run check; the numbers are indicative only).
    Returns {frames, meta, texts, measured, text, timing, draft}."""
    import time as _time
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if scenario is None and sb and sb.get("scenario"):
        import yaml
        scenario = yaml.safe_load((ROOT / sb["scenario"]).read_text())
    view = weather_view(report or {}, scenario)
    bad = problems(shot, view, sb)
    if bad:
        raise ValueError("intervention shot refused:\n  " + "\n  ".join(bad))
    sec = float(shot["seconds"])
    ac = acts(sec)
    if times is None:
        times = [0.9 * ac["before"][1], 0.5 * (ac["event"][0] + ac["event"][1]), sec - 1.0 / FPS]
    if quick:
        times = [0.0]
    force = _forcing(shot, view)
    g = G0
    t0 = _time.perf_counter()
    world = build_world(g)
    subject = s92_subject(g, world, **_subject_params(shot))
    seed = int(shot.get("seed", 1))
    cases = [Case(f["place"], f["u10"], f["hs"], g, world, subject, sec, seed + 7 * i, n_streaks=n_streaks) for i, f in enumerate(force)]
    t_build = _time.perf_counter() - t0
    t0 = _time.perf_counter()
    master = master_field(g, world, subject, seconds=(4.0 if quick else MASTER_S), seed=seed)
    for c in cases:
        c.spin_up(master, t_hold=(1.0 if quick else 4.0))
    t_spin = _time.perf_counter() - t0
    want = {int(round(t * FPS)): t for t in times}
    snaps: dict = {}
    n_frames = max(want) + 1 if quick else int(round(sec * FPS))
    t0 = _time.perf_counter()
    for f in range(n_frames):
        for c in cases:
            c.advance_frame()
        if f in want:
            snaps[f] = [c.snapshot() for c in cases]
    t_run = _time.perf_counter() - t0
    measured = {}
    for i, c in enumerate(cases):
        measured.update(c.measured(prefix=f"case{i}."))
    if all(f"case{i}.deck_change" in measured for i in (0, 1)):
        measured["reorg_min"] = min(measured[f"case{i}.reorg_share"] for i in (0, 1))
        measured["deck_change_min"] = min(measured[f"case{i}.deck_change"] for i in (0, 1))
    else:                                                       # quick mode: the windows are not reached
        for k in ("reorg_min", "deck_change_min"):
            measured[k] = 0.0
        for i in (0, 1):
            for k in ("reorg_share", "deck_speed_before", "deck_speed_after", "deck_change", "deck_turb_before", "deck_turb_after", "lee_change"):
                measured.setdefault(f"case{i}.{k}", 0.0)
            measured[f"case{i}.u10"] = cases[i].u10
    winds = [f["u10"] for f in force]
    measured["wind_lo"], measured["wind_hi"] = min(winds), max(winds)
    vals = {**narrate.flatten(view), **measured}
    draft = is_draft(shot, view)
    kv = {n: resolve_ref(r, view) for n, r in (shot.get("kicker_values") or {}).items()}
    kicker = shot["kicker"].format(status="DRAFT, SIMULATED" if draft else "SIMULATED", lo=min(winds), hi=max(winds), **kv)
    headline = [_segments(l) for l in narrate.choose(shot["headline"], vals).split("\n")]
    body = narrate.choose(shot["body"], vals).split("\n")
    text = {"kicker": kicker, "headline": headline, "body": body, "handle": shot["handle"],
            "place": [f"{f['place']}  ·  {f['u10']:.1f} m/s" for f in force], "states": shot["chips"]["states"]}
    from offsim.cinema.visual_gate import capture_text
    frames, metas, texts_all = [], [], []
    t0 = _time.perf_counter()
    vmax = max(8.0, 2.0 * max(winds))
    for fidx in sorted(snaps):
        with capture_text(canvas=(W, H)) as texts:
            img, meta = render_frame(snaps[fidx], cases, g, world, sec, text, None, vmax=vmax)
        p = out_dir / f"intervention_{meta['act']}_{fidx:04d}.png"
        img.save(p)
        frames.append(p)
        metas.append(meta)
        texts_all.append(texts)
    t_draw = _time.perf_counter() - t0
    timing = {"grid": [g.nx, g.nz], "dx_m": g.dx_m, "streaks": n_streaks, "tail_frames": int(round(TAIL_S * FPS)), "build_s": round(t_build, 1),
              "spin_up_s": round(t_spin, 1), "sim_s_per_frame": round(t_run / max(n_frames, 1), 3), "draw_s_per_frame": round(t_draw / max(len(frames), 1), 3),
              "frames": n_frames, "solver_steps_per_frame": SUBSTEPS}
    return {"frames": frames, "meta": metas, "texts": texts_all, "measured": measured, "text": text, "timing": timing, "draft": draft,
            "cases": cases, "view": view}


def render_intervention_shot(shot, sb, out_mp4, fps=30, report=None, frames_dir=None, keep_frames=False,
                             quick=False, log=print):
    """Render an intervention shot to out_mp4. quick = one frame (the dry-run proof path); otherwise every
    frame of shot['seconds'] at fps. This is the film assembly V1 did not ship: story.build() had no
    shot_intervention, so `offsim film` refused an intervention storyboard with a KeyError.

    Frames are named intervention_<act>_<fidx>.png, so they cannot be fed to ffmpeg as a numbered
    sequence; they are symlinked into f%04d.png order (run_intervention's frame list is already in
    film order) and encoded with the same flags as section.encode.
    """
    import shutil

    from offsim.motion.section import encode

    out = Path(out_mp4)
    out.parent.mkdir(parents=True, exist_ok=True)
    fd = Path(frames_dir) if frames_dir else out.with_suffix("").with_name(out.stem + "_frames")
    sec = float(shot["seconds"])
    times = None if quick else [i / fps for i in range(int(round(sec * fps)))]
    res = run_intervention(shot, sb, report, fd, times=times, quick=quick, log=log)
    for i, p in enumerate(res["frames"]):
        (fd / f"f{i:04d}.png").symlink_to(Path(p).resolve())
    encode(fd, out, fps)
    if not keep_frames:
        shutil.rmtree(fd, ignore_errors=True)
    log(f"{out} {len(res['frames'])} frames, spin-up {res['timing']['spin_up_s']:.1f} s")
    return res


def gate_frame(img, texts, meta, strict=False):
    """Run the visual gate on a delivered 1080 x 1350 frame as kind `intervention`. Returns (ok, reasons, report)."""
    from offsim.cinema import visual_gate as vg
    rep = vg.inspect(img, {"kind": "intervention", "text": texts or None, "meta": meta})
    ok, reasons = vg.passes(rep, strict=strict)
    return ok, reasons, rep


def main(argv=None):
    """python -m offsim.motion.intervention <storyboard.yaml> [--out out/v1_intervention] [--quick]: the three stills (one per act),
    each judged by the visual gate; writes stills, `stills.json` (measured values, timing, gate findings)."""
    import argparse

    import yaml
    ap = argparse.ArgumentParser(prog="offsim.motion.intervention")
    ap.add_argument("storyboard")
    ap.add_argument("--out", default="out/v1_intervention")
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args(argv)
    sb = yaml.safe_load(Path(a.storyboard).read_text())
    report = json.loads((ROOT / sb["run"] / "report.json").read_text())
    shot = next(s for s in sb["shots"] if s["type"] == "intervention")
    res = run_intervention(shot, sb, report, ROOT / a.out, quick=a.quick)
    rows = []
    for p, meta, texts in zip(res["frames"], res["meta"], res["texts"]):
        ok, why, rep = gate_frame(Image.open(p).convert("RGB"), texts, meta)
        rows.append({"frame": str(p), "act": meta["act"], "t": meta["t"], "dim": meta["dim"], "gate_ok": ok, "reasons": why,
                     "findings": [{k: f[k] for k in ("rule", "ok", "msg")} for f in rep["findings"]], "frame_budget": rep["frame_budget"],
                     "edges": rep["edges"], "strokes": {k: rep["strokes"][k] for k in ("median_px", "thin_share")}})
        stem = Path(p).with_suffix("")
        stem.with_suffix(".text.json").write_text(json.dumps(texts))
        stem.with_suffix(".meta.json").write_text(json.dumps(meta, default=float))
        print(f"{meta['act']:6s} t={meta['t']:.2f}s gate {'PASS' if ok else 'FAIL'} {why}")
    (ROOT / a.out / "stills.json").write_text(json.dumps({"measured": res["measured"], "timing": res["timing"], "draft": res["draft"], "text": res["text"],
                                                          "stills": rows}, indent=1, default=float))
    print("measured:", {k: round(v, 3) for k, v in res["measured"].items()})
    print("timing:", res["timing"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
