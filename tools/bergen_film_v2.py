"""Bergen lean pilot film v2 — REBUILD (Arshad's verdict on v1, 2026-11-12: "the animation
is soo terrible that i will puke, the sea feels horrible, the helicopter feels terrible,
the bottom map is soo confusing").

Same numbers, same honesty, different film. The experiment is FROZEN (run/run-report.json:
lean 4 helis 3 cancelled / 3 rebooked / 0 unmet of 1,209, P90 unmet 0.0 vs threshold <= 1,
one winter only; gate 4 FAILED on window_hours 56 h vs the paper's 50 h -- the film states
56 h and never claims the paper's windows). v1's tool (tools/bergen_film.py) is untouched;
this module imports it and overrides the three faults:

1. SEA — v1 froze the JONSWAP surface at T_CANCEL in the section beat (the frozen-sea
   tag): a cartoon sine, not water. v2 runs the surface on FILM time (t = f/FPS, real-time waves);
   the AMPLITUDE follows the narrative weather at the beat's moment, so the sea is alive at
   the measured Hs of the moment shown. The chop is time-dependent too (deep-water
   dispersion). Wind streaks advect continuously (no f%90 wrap jump). The frozen-sea tag
   is gone; the tag reads "SEA LIVE · Hs X.XX m" with the measured Hs of the frame.
2. HELICOPTER — v1's hand-drawn S-92 was a tiny white sticker. v2 draws the REAL CAD S-92
   (offsim/assets/cad/air.py, HLR linework through sheet.view_prims, the same asset as the
   sprite sheet), at a 110 m section width so it reads as a machine (~205 px long). The main
   rotor blades are excluded from the HLR (they are stopped in the solid) and drawn as a
   shimmering blur band; the tail rotor is drawn as a rotating X (0.5 rev/s on screen -- a
   real tail rotor spins far faster, but at 30 fps that aliases into a backward crawl; the
   disc reads as turning at 0.5 rev/s; display choice, noted in the report). Deck + heli
   heave +/-0.12 m at the swell period (display-grade; the wheels stay on the deck because
   deck and heli bob together). All dims assumption:true ("S-92 STYLISED — ALL DIMS ASSUMED");
   the asset's declared dims FAIL QA (rotor ~21%, width ~340% off) -- never hidden.
3. MAP — v1 drew all five helicopters' week-11 routes: the Flesland fan. v2 draws ONLY the
   story's helicopter's TODAY legs (done solid gold, to-come-today faint dashed). Other
   helicopters are markers only, never lines, never callouts. Live labels are filtered to
   OSM-verified places + the story sites B3/B17. The aircraft FLIES the route (moving marker
   along the real trajectory, as in v1) and in the findings beat H2 flies the rebook leg
   (map + clock advance 18:00->18:30 in sync -- one clock, not the v1 freeze-frame).

Layout: same 30 s / 1080x1350 / 30 fps / 900 frames, same beats (hook/map/section/findings),
same two-pass narration and DRAFT footer. Section 110 m x 35 m (v1: 160 x 50) so the heli
reads at 9.8 px/m; the chart/map/deck layout below it is unchanged (the section panel is
6 px taller, the gap to the chart shrinks by 6 px).

Look (2026-11-12, his direction: 'use charcoal grey and orange glow theme from abhinav on
this one'): v2 drops v1's dark-maroon/gold for charcoal ground #0B0B0B + orange glow
#D69E43/#C58934 + heat red #893C2A + amber #AE7C59 (all measured from Abhinav's AC reel,
~/workspace/abhinav-video/re/VIDEO-RE.md). Orange is the glow and the accent (cancelled
flight, over-limit line, focus route, titles); the glow reads as orange light on charcoal
-- soft halos under the focus route/marker, never flat orange fills. The sea keeps v1's
flat teal #16323a: luminance ratio vs charcoal 1.45 (better than vs v1's maroon 1.17);
land stays the Strip's hardcoded maroon #432629, so sea/land/ground stay three distinct
values. Heat red #893C2A is 2.57:1 on charcoal -- used only as the Hs gauge tick (a
colour patch), never for text: the first charcoal stills showed the clock-row number
going dim in red, so the over-limit number stays orange (8.28:1).

    PYTHONPATH=. venv-studio/bin/python tools/bergen_film_v2.py --out <mp4> [--only N] [--resume-from N]
"""
from __future__ import annotations

import argparse
import math
import subprocess
import sys
import time
from datetime import timedelta
from pathlib import Path

import numpy as np
import skia

import bergen_film as B
from offsim.cinema.draw import Canvas, draw_prims
from offsim.cinema.vessel_lineart import STROKES as SECTION_STROKES
from offsim.assets.cad.sheet import SHEET_FILLS
from offsim.physics import ocean

ROOT, RUN, OUTDIR = B.ROOT, B.RUN, B.OUTDIR
P = B.P
W, H, SS, FPS, N = B.W, B.H, B.SS, B.FPS, B.N
PANEL_W, PANEL_H = B.PANEL_W, B.PANEL_H
HOOK, MAPB, SECB, FIND = B.HOOK, B.MAPB, B.SECB, B.FIND
T_MON11, T_MAP_START, T_CANCEL, T_REBOOK, T0 = B.T_MON11, B.T_MAP_START, B.T_CANCEL, B.T_REBOOK, B.T0
TP_FEATURED = B.TP_FEATURED
HELI_NOTE = B.HELI_NOTE
DRAFT = B.DRAFT
SPAN_MULT, PAN_CAP = B.SPAN_MULT, B.PAN_CAP

# ---------------------------------------------------------------- charcoal + orange glow (look direction)
# His words 2026-11-12: 'use charcoal grey and orange glow theme from abhinav on this
# one'. Anchors measured from Abhinav's AC reel (VIDEO-RE.md): ground #0B0B0B, title/glow
# orange #D69E43, interior/glow orange #C58934, heat red #893C2A, amber #AE7C59. v2's P
# IS bergen_film's P (same dict object), so apply_palette() recolours v1's Strip,
# draw_chart, live labels and findings table in this process only -- v1's file and its
# rendered mp4 are untouched. The sea keeps v1's flat teal #16323a: relative luminance
# 0.0276 vs charcoal 0.0033 (ratio 1.45, BETTER than vs v1's maroon ground 1.17), and the
# land is the Strip's hardcoded maroon #432629 (L 0.0274, same value as the sea but a
# different hue -- the v9 fix, which works because the tan coastline hairline separates
# them); sea/land/ground stay three distinct values, not one dark mass.
V2_PALETTE = {
    "ground": "#0B0B0B", "ground_deep": "#141414", "sea": "#16323a",
    "streak_lo": "#846a5d", "streak_hi": "#c9a98c", "accent": "#D69E43",
    "ink": "#f2e9df", "muted": "#9c8a80",
}
HEAT = "#893C2A"   # over-limit / heat red: the Hs gauge tick ONLY, a colour patch.
                  # Never text: 2.57:1 on charcoal, and the clock-row number went dim
                  # in the first charcoal stills -- the palette breaks the reading
                  # there, so the over-limit number stays orange (8.28:1).
AMBER = "#AE7C59"  # amber heat, secondary: the wind streaks over the living sea.
GLOW = "#C58934"   # interior/glow orange: soft halos under the focus route + marker.
SEA_MID = "#2a5f6e"  # lighter tint of the sea #16323a (RGB x1.9): internal wave structure
                     # (the sea's own contour, offset down -- not a new colour family).
HELI_FILLS = {k: (v + "cc" if isinstance(v, str) and len(v.lstrip("#")) == 6 else v)
              for k, v in SHEET_FILLS.items()}  # sheet fills muted to 0.8 alpha
                     # (8-digit hex -- parse_color takes #rrggbbaa): opaque tan read as a
                     # flat paper cutout, not linework (whipster FAIL).


def apply_palette():
    """Recolour the shared palette dict to charcoal + orange glow (see V2_PALETTE).
    Call before any drawing (Strip, chart, labels all read P at call time)."""
    P.update(V2_PALETTE)

# section geometry: 110 m wide x 35 m tall (v1: 160 x 50). The heli (22.3 m overall) is
# ~205 px long at 9.82 px/m; deck 26 m still fits under the 35 m top (heli top 31.2 m).
L_M, H_M, SEA_Z = 110.0, 35.0, 10.0
SEC_PH2 = int(W * H_M / L_M)  # 343
DECK_X0, DECK_X1, DECK_Z = 66.0, 101.75, 26.0
HELI_CX = 84.0  # section metres of the asset origin (mast station)
MAST_X, ROTOR_Z, ROTOR_R = 1.5, 5.05, 8.6  # mast station, rotor plane height, blade radius
TAIL_X, TAIL_Z, TAIL_R = -9.80, 3.60, 1.50
FIND_MAP_SPAN_S = 1800.0  # findings map+clock advance 30 min over the beat (one clock)


def v2_run_t_of(f):
    """One clock for the chart and readouts. v1 froze the findings beat at T_REBOOK; v2
    advances 18:00 -> 18:30 there, in sync with the map marker flying the rebook leg."""
    if f < MAPB[0]:
        return T_CANCEL
    if f < SECB[0]:
        return T_MAP_START + (f - MAPB[0]) / (MAPB[1] - MAPB[0]) * (T_CANCEL - T_MAP_START)
    if f < FIND[0]:
        return T_CANCEL + (f - SECB[0]) / (SECB[1] - SECB[0]) * (T_REBOOK - T_CANCEL)
    return T_REBOOK + (f - FIND[0]) / (FIND[1] - FIND[0]) * FIND_MAP_SPAN_S


def v2_map_run_t_of(f):
    """The map's moment. Hook/section frozen at the cancellation (the section beat's WHERE
    line says the moment; the sea, rotor and chart move there, the map does not). Map beat
    runs Thu 09:45-12:30; findings advances 18:00 -> 18:30 with H2 flying the rebook."""
    if f < MAPB[0] or SECB[0] <= f < FIND[0]:
        return T_CANCEL
    if f < SECB[0]:
        return v2_run_t_of(f)
    return T_REBOOK + (f - FIND[0]) / (FIND[1] - FIND[0]) * FIND_MAP_SPAN_S


# ---------------------------------------------------------------- living sea
def sea_surface(f, hs):
    """Live JONSWAP surface at the measured Hs of the narrative moment. The PHASE runs on
    film time (t = f/FPS: real-time waves, one swell period = 11.17 s = 335 frames); the
    AMPLITUDE follows the narrative weather, so the sea is alive at the Hs of the moment
    shown -- v1 froze the phase at T_CANCEL, which is the fault being fixed. Chop is
    time-dependent (deep-water dispersion w = sqrt(g k)); the sum is renormalised to
    std Hs/4, so the drawn significant height stays measured (the v1 convention)."""
    xs = np.linspace(0, L_M, 320)
    t_sea = f / FPS
    eta = ocean.surface(xs, t_sea, hs, TP_FEATURED, seed=7)
    rng = np.random.default_rng(7)
    chop = np.zeros_like(xs)
    # irregular chop: varied amplitudes + a longer 25 m component, so the surface is not
    # a regular train of uniform bumps (whipster FAIL: "cartoon sine"). The sum is still
    # renormalised to std Hs/4 below, so the drawn height stays measured.
    for lam in (6.0, 9.0, 13.0, 18.0, 25.0):
        w = math.sqrt(9.81 * 2 * math.pi / lam)
        chop += rng.uniform(0.15, 0.65) * np.sin(2 * np.pi * xs / lam - w * t_sea
                                                 + rng.uniform(0, 2 * np.pi))
    eta = eta + chop
    eta *= (hs / 4.0) / max(float(np.std(eta)), 1e-9)
    return xs, eta


# ---------------------------------------------------------------- CAD helicopter
_HELI_CACHE = {}


def heli_prims():
    """The real CAD S-92, side view, WITHOUT the rotor blades (they are stopped in the
    solid -- fore/aft + athwart -- so they would read as a frozen disc). The blades are
    drawn animated by draw_section_v2 (blur band + turning tail rotor). Cached: the build
    + fuse + HLR costs ~16 s once per process. Fills are the sheet's (tan house, dark
    glass); strokes are the section's (near-white ink on the dark ground -- the sheet's
    near-black ink would vanish on the charcoal ground)."""
    if "prims" in _HELI_CACHE:
        return _HELI_CACHE["prims"]
    from offsim.assets.cad.base import build, AssetModel
    from offsim.assets.cad import sheet as _S
    from offsim.assets.cad import air as _A
    asset = build("s92")
    exclude = {"blade_fore", "blade_aft", "blade_port", "blade_stbd", "tail_rotor_blades"}
    shape = None
    for name, part in asset.parts.items():
        if name in exclude:
            continue
        shape = part if shape is None else shape.fuse(part)
    norotor = AssetModel(shape=shape, parts=asset.parts, dims=asset.dims, meta=asset.meta)
    fills = {k: v for k, v in _A.SPRITE_FILLS.items() if k not in exclude}
    prims, bounds = _S.view_prims(norotor, "side", fills, _A.s92_sprite_details,
                                  deflection=0.005)
    _HELI_CACHE["prims"] = (prims, bounds)
    print(f"heli CAD prims: {len(prims)}, bounds {[round(v, 2) for v in bounds]}, "
          f"edge {round(_S.edge_length(prims), 1)} m (no-rotor HLR, blades animated separately)")
    return _HELI_CACHE["prims"]


def tail_rotor_angle(f):
    """Tail-rotor blade angle (rad): 0.5 rev/s on screen. A real tail rotor spins far
    faster, but at 30 fps that aliases into a backward crawl; 0.5 rev/s reads as turning.
    Display choice, noted in the report."""
    return math.pi * f / FPS


def heli_bob(f):
    """Deck + heli heave (m): +/-0.12 m at the swell period, tied to the sea state.
    Display-grade (the deck height is schematic); the wheels stay on the deck because
    deck and heli bob together, and the legs stretch invisibly (1.2 px)."""
    return 0.12 * math.sin(2 * math.pi * (f / FPS) / TP_FEATURED)


def disc_alpha(f):
    """Main-rotor blur-band alpha: a slow shimmer at 1.5 Hz (the blade-pass frequency is
    far above the frame rate, so the disc reads as a blur, not as stopped blades).
    Range 0.35-0.65: the 0.18-0.42 band was still invisible in a still -- "a single thin
    blade line over black" (whipster round 2). The disc must read in a freeze-frame,
    which is what LinkedIn shows first."""
    return 0.50 + 0.15 * math.sin(2 * math.pi * 1.5 * f / FPS)


# ---------------------------------------------------------------- section (living sea + CAD heli)
def draw_section_v2(cv, f, run_t, hs, wind, beat):
    """Helideck in a gale, v2: the sea is LIVE (phase on film time, Hs the narrative
    moment's measured value), the CAD S-92 sits on the deck with a turning rotor, the
    deck + heli heave at the swell period. Findings beat replaces the sea with the KPI
    table (v1's, unchanged)."""
    s = W / L_M
    top, ph = B.SEC_TOP, SEC_PH2
    to_px = lambda x, z: (x * s, top + ph - z * s)
    if beat == "findings":
        B._draw_findings_section(cv, top, ph)
        return
    xs, eta = sea_surface(f, hs)
    surf = [to_px(x, SEA_Z + e) for x, e in zip(xs, eta)]
    cv.polygon(surf + [(W, top + ph), (0, top + ph)], fill=P["sea"])
    # internal wave structure: the surface's own contour, offset down in a lighter tint
    # of the same sea (SEA_MID), so the sea has depth instead of one flat band with a
    # wavy edge (whipster FAIL: "cartoon sine"). The old whitecaps are gone: small white
    # ticks on the crests read as stray marks, not wave tops.
    for dy, al in ((8, 0.8), (17, 0.55)):
        cv.line([(x, y + dy) for x, y in surf], SEA_MID, 1.0, alpha=al)
    cv.line(surf, P["streak_hi"], 2.0)
    # Hs gauge (left): Hs is a significant height, not a crest line -- the v1 fix stands
    gx = 92.0
    gz = lambda z: top + ph - z * s
    cv.line([(gx, gz(SEA_Z)), (gx, gz(SEA_Z + 8.0))], P["ink"], 1.5)
    for v in (0.0, 6.0):
        cv.line([(gx - 8, gz(SEA_Z + v)), (gx + 8, gz(SEA_Z + v))], P["ink"], 1.5)
    B._text(cv, gx + 14, gz(SEA_Z + 6.0) + 4, "LIMIT 6.0 m — ASSUMED", 12, "Bold", P["accent"])
    hy = gz(SEA_Z + hs)
    # the Hs marker reads hot when it is over the limit (HEAT is a colour patch here,
    # not text); the value itself stays orange so the number stays legible (8.28:1)
    cv.line([(gx - 8, hy), (gx + 8, hy)], HEAT if hs > 6.0 else P["accent"], 2.5)
    B._text(cv, gx + 14, hy - 22, f"Hs {hs:.2f} m", 13, "Bold", P["accent"])
    # the label sits in the wave band, so a wave crest struck through it ("TILL WATER",
    # whipster FAIL). A ground chip behind the text keeps it readable (the map labels
    # use the same chip mechanism).
    _sw = cv.measure("STILL WATER", ("Inter", "Regular"), 11)
    cv.polygon([(gx + 8, gz(SEA_Z) - 2), (gx + 8 + _sw + 8, gz(SEA_Z) - 2),
                (gx + 8 + _sw + 8, gz(SEA_Z) + 18), (gx + 8, gz(SEA_Z) + 18)],
               fill=P["ground"], alpha=0.92)
    B._text(cv, gx + 14, gz(SEA_Z) + 4, "STILL WATER", 11, "Regular", P["muted"])
    # wind streaks: continuous advection (v1's f%90 wrapped every 3 s -- a visible jump).
    # Fewer, and confined to the open sky between the gauge and the deck: 90 streaks
    # across the whole width read as scratches over the helicopter and the annotation
    # (whipster FAIL). They advect in the film; in a still they are dashes, so they
    # stay out of the way of the machine and the numbers.
    rng = np.random.default_rng(11)
    base = rng.uniform(18, 62, 40)
    ys = rng.uniform(SEA_Z + 3.0, SEA_Z + 20.0, 40)
    for x0, z in zip(base, ys):
        # advect inside the [18, 62] m band: a streak leaving at 62 re-enters at 18
        x = 18 + ((x0 - 18 + wind * 2.7 * (f / FPS)) % 44)
        fade = min(1.0, (z - (SEA_Z + 3.0)) / 4.0)
        x0p, y0p = to_px(x, z)
        x1p, _ = to_px(x + 6.0, z)
        cv.line([(x0p, y0p), (x1p, y0p)], (174, 124, 89, int(80 * fade)), 1.0)  # AMBER #AE7C59
    # jacket + helideck (deck height schematic: legs carry the drafting break), bobbed
    bob = heli_bob(f)
    dz = DECK_Z + bob
    # the legs end at still water: running them 4 m under the surface read as
    # scaffolding left in the drawing (whipster FAIL). One diagonal brace per leg,
    # not an X -- the X read as a mark, not as structure.
    for lx in (DECK_X0 + 4, DECK_X1 - 4):
        x0p, y0p = to_px(lx, SEA_Z)
        x1p, y1p = to_px(lx, 20.0)
        cv.line([(x0p, y0p), (x1p, y1p)], P["ink"], 2.0)
        bx, by = to_px(lx, 20.0)
        cv.line([(bx - 5, by - 4), (bx + 5, by + 4)], P["ink"], 1.5)
        x2p, y2p = to_px(lx, dz)
        cv.line([(bx, by), (x2p, y2p)], P["ink"], 2.0)
    x0p, y0p = to_px(DECK_X0, dz)
    x1p, y1p = to_px(DECK_X1, dz)
    cv.line([(x0p, y0p), (x1p, y1p)], P["ink"], 3.0)
    B._text(cv, to_px(DECK_X0 + 6, dz)[0], to_px(0, dz)[1] - 24, "H", 20, "Bold", P["accent"],
            anchor="m")
    # the real CAD S-92 (HLR linework + sheet fills + 2D glass), on the deck, bobbing with it.
    # The fills are muted to 0.8 (HELI_FILLS): opaque tan read as a flat paper cutout,
    # not linework (whipster FAIL).
    prims, _bounds = heli_prims()
    to_heli = lambda u, v: ((HELI_CX + u) * s, top + ph - (dz + v) * s)
    draw_prims(cv, prims, to_heli, fills=HELI_FILLS, strokes=SECTION_STROKES)
    # main rotor: blur band, not stopped blades. The band spans the disc (mast +/- 8.6 m)
    # at the rotor plane. Two passes: a wide faint disc plus a solid shimmering band at
    # 1.5 Hz, and a blade line at its centre. The 0.10/0.18-0.42 version was still
    # invisible in a still -- "a single thin blade line over black" (whipster round 2) --
    # so the band is taller (0.30 m) and the alpha is 0.35-0.65: it must read in a
    # freeze-frame, which is what LinkedIn shows first.
    u0, u1 = MAST_X - ROTOR_R, MAST_X + ROTOR_R
    disc = [(u0, ROTOR_Z - 0.55), (u1, ROTOR_Z - 0.55), (u1, ROTOR_Z + 0.55), (u0, ROTOR_Z + 0.55)]
    cv.polygon([to_heli(u, v) for u, v in disc], fill=P["ink"], alpha=0.20)
    band = [(u0, ROTOR_Z - 0.30), (u1, ROTOR_Z - 0.30), (u1, ROTOR_Z + 0.30), (u0, ROTOR_Z + 0.30)]
    cv.polygon([to_heli(u, v) for u, v in band], fill=P["ink"], alpha=disc_alpha(f))
    cv.line([to_heli(u0, ROTOR_Z), to_heli(u1, ROTOR_Z)], P["ink"], 2.5, alpha=0.85)
    # tail rotor: the disc circle + 4 blades turning at 0.5 rev/s (the hub is in the HLR)
    tcx, tcy = to_heli(TAIL_X, TAIL_Z)
    tr = TAIL_R * s
    cv.circle(tcx, tcy, tr, stroke=P["ink"], width=1.0, alpha=0.7)
    th = tail_rotor_angle(f)
    for k in range(2):
        a = th + k * math.pi / 2
        cv.line([(tcx - tr * math.cos(a), tcy - tr * math.sin(a)),
                 (tcx + tr * math.cos(a), tcy + tr * math.sin(a))], P["ink"], 2.5)
    cv.circle(tcx, tcy, 2.0, fill=P["ink"])
    B._text(cv, 56, top + 14, "SECTION — HELIDECK IN A GALE", 14, "Bold", P["muted"])
    B._text(cv, W - 56, top + 14, HELI_NOTE, 13, "Bold", P["muted"], anchor="r")
    # the "DECK HEIGHT SCHEMATIC — NOT MEASURED" note lived here in v1 at top+40, but the
    # rotor disc (deck + 5.05 m) crosses exactly that line -- text struck through by the
    # disc. It now lives in the footer source line instead (render_frame_v2).
    # the sea is LIVE, at the measured Hs of this frame's moment -- never frozen
    B._text(cv, W - 56, top + ph - 14, f"SEA LIVE · Hs {hs:.2f} m", 12, "Bold", P["muted"],
            anchor="r")
    if beat == "section":
        if f < (SECB[0] + SECB[1]) // 2:
            B._text(cv, 56, top + 44, "CANCELLED — Hs OVER THE LIMIT", 20, "Bold", P["accent"])
        else:
            B._text(cv, 56, top + 44, "REBOOKED TO H2-14h · FRI 18:00 · 29.5 H LATE", 20, "Bold",
                    P["accent"])
    elif beat == "map" and run_t >= T_CANCEL:
        B._text(cv, 56, top + 44, "CANCELLED — Hs OVER THE LIMIT", 20, "Bold", P["accent"])


# ---------------------------------------------------------------- map (story routes only)
def map_route_agents(beat, focus_ag):
    """Which agents draw a route on the map, per beat. v1 drew all five helicopters'
    week-11 routes -- the Flesland fan. v2 draws only the story's helicopter, only
    today's legs; other helicopters are markers, never lines. Section/findings beats
    draw no routes at all: the two story legs carry the geography there."""
    if beat in ("hook", "map"):
        return [focus_ag]
    return []


def story_route_window(times_ag):
    """Decimated index window of the featured morning's route (09:45-12:30 story):
    (start_k, end_k) in the [::7] sampling. The start is the B17 departure, not
    midnight -- see draw_map_v2. FLOOR division: the first drawn point is the last
    sample at or before 09:45, which is H3 sitting at Flesland (the departure point)
    -- ceiling division skips it, and the leg's first drawn point is then already en
    route and off-panel, so the hook map shows no route at all."""
    t0k = max(1, int(np.searchsorted(times_ag, T_MAP_START)) // 7)
    t1k = max(t0k + 1, int(np.searchsorted(times_ag, 6912000 + 86400)) // 7)
    return t0k, t1k


def rebook_segment(times_ag, map_run_t):
    """RAW index window of the rebook leg (H2's real Fri 18:00 round trip):
    (start_k, done_k, end_k). The rebook is a flown trajectory, so it is drawn as one
    -- the straight chord from Flesland to B3 crossed the landmass and the marker flew
    off it (whipster FAIL). RAW, not decimated: the round trip is ~1.93 h with ~4 raw
    points, so the [::7] sampling would leave the solid line empty for the whole
    30-minute findings beat. The round trip is ~1.93 h; the window covers 2 h."""
    start_k = max(1, int(np.searchsorted(times_ag, T_REBOOK)))
    done_k = max(start_k, int(np.searchsorted(times_ag, map_run_t)))
    end_k = max(done_k + 1, int(np.searchsorted(times_ag, T_REBOOK + 7200)))
    return start_k, done_k, end_k


def _segment_exit(x0, y0, x1, y1):
    """Where the segment (x0,y0)->(x1,y1) first leaves the map panel, or None if the end
    is in-panel. B._chevron clamps x and y INDEPENDENTLY, so for a point off-panel in
    both axes (B3 is far north-west) it lands in the corner -- while the leg exits
    mid-edge, ~350 px away (whipster round 2: the map told two stories about where B3
    is). Passing the exit point puts the chevron where the leg leaves the frame."""
    if 0 <= x1 < PANEL_W and 0 <= y1 < PANEL_H:
        return None
    best = None
    for t in [ (0 - x0) / (x1 - x0) if x1 != x0 else None,
               (PANEL_W - x0) / (x1 - x0) if x1 != x0 else None,
               (0 - y0) / (y1 - y0) if y1 != y0 else None,
               (PANEL_H - y0) / (y1 - y0) if y1 != y0 else None ]:
        if t is None or not (0 < t <= 1):
            continue
        x, y = x0 + t * (x1 - x0), y0 + t * (y1 - y0)
        if -1 <= x <= PANEL_W + 1 and -1 <= y <= PANEL_H + 1 and (best is None or t < best[0]):
            best = (t, x, y)
    return (best[1], best[2]) if best else None


def _first_exit(pts):
    """First point where the drawn polyline leaves the map panel, or None. Walk in time
    order; the first segment whose start is in-panel and end is off-panel gives the
    outbound exit. (The segment into the northernmost point is not robust: decimation
    can put its start off-panel too, so the exit must be found by walking the line.)"""
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if 0 <= x0 < PANEL_W and 0 <= y0 < PANEL_H and not (0 <= x1 < PANEL_W and 0 <= y1 < PANEL_H):
            return _segment_exit(x0, y0, x1, y1)
    return None


def _chip_label(cv, x, y, text, size=12, color=None):
    """Text on a ground chip (the map-label mechanism), clamped inside the panel with a
    12 px margin. For labels that sit over busy ground (coastline/roads) instead of open
    sea -- the REBOOKED label lay chipless over the maroon coast and the coast lines
    struck through the letters (whipster round 2)."""
    color = color or P["accent"]
    w = cv.measure(text, ("Inter", "Bold"), size)
    x = min(max(x, 12), PANEL_W - 12 - w)
    y = min(max(y, 12), PANEL_H - 12 - size)
    cv.polygon([(x - 4, y - 7), (x + w + 4, y - 7), (x + w + 4, y + size + 2),
                (x - 4, y + size + 2)], fill=P["ground"], alpha=0.92)
    B._text(cv, x, y, text, size, "Bold", color)


def _clamp_label(cv, x, y, text, size=12):
    """Label position clamped inside the panel: a label on a leg that leaves the frame
    must stay readable -- the CANCELLED label sat on the off-panel midpoint and vanished
    (whipster FAIL: three route styles, no reason given)."""
    w = cv.measure(text, ("Inter", "Bold"), size)
    x = min(max(x, 8), PANEL_W - 8 - w)
    y = min(max(y, 8), PANEL_H - 8 - size)
    return x, y


def draw_map_v2(strip, glide, cx, cy, focus_ag, markers, routes, times, run_t, beat, f,
                stops, heliport):
    """The map panel, v2: the strip + live overlays, but only the story's route is drawn.
    Otherwise the v1 panel (own canvas, live labels, chevrons, scale bar, north) stands:
    the v1 fixes for label collisions, chevron stacking and the scale-bar chip are kept.
    Live labels are filtered to OSM-verified places + the story sites B3/B17 -- the other
    B dots stay on the strip, but their labels added clutter without story."""
    span, k = glide.span, glide.k
    cv = Canvas(PANEL_W, PANEL_H, bg=P["sea"], ss=SS)
    src_x = (cx - strip.lon0) * k / span - PANEL_W / 2
    src_y = (strip.lat1 - cy) / span - PANEL_H / 2
    cv.cv.drawImageRect(strip.skia_img,
                        skia.Rect.MakeXYWH(float(src_x), float(src_y),
                                           float(PANEL_W), float(PANEL_H)),
                        skia.Rect.MakeXYWH(0, 0, float(PANEL_W), float(PANEL_H)))
    pj = lambda lon, lat: ((lon - cx) * k / span + PANEL_W / 2,
                           PANEL_H / 2 - (lat - cy) / span)
    reserved = []
    _fmx, _fmy = pj(*markers[focus_ag][1])
    _flw = cv.measure(focus_ag, ("Inter", "Bold"), 13) + 12
    _flh = 23
    if _fmx > PANEL_W / 2:
        _flbox = [_fmx - 24 - _flw, _fmy - _flh / 2, _fmx - 24, _fmy + _flh / 2]
    else:
        _flbox = [_fmx + 24, _fmy - _flh / 2, _fmx + 24 + _flw, _fmy + _flh / 2]
    _flbox[0] = min(max(_flbox[0], 8), PANEL_W - 8 - _flw)
    _flbox[2] = _flbox[0] + _flw
    _flbox[1] = min(max(_flbox[1], 8), PANEL_H - 8 - _flh)
    _flbox[3] = _flbox[1] + _flh
    reserved.append(tuple(_flbox))
    # the other B sites are the field (the hook names B1-B20), but baked in accent orange
    # they read as unexplained markers competing with the story (whipster FAIL). Quiet
    # them to muted -- still present, no longer shouting.
    for text, lon, lat, _size, _col, kind in strip.label_items:
        if kind == "site" and text not in ("B3", "B17"):
            dx, dy = pj(lon, lat)
            if 0 <= dx < PANEL_W and 0 <= dy < PANEL_H:
                cv.circle(dx, dy, 2.5, fill=P["muted"])
    # THE story's route, and nothing else: the focus helicopter's featured-morning legs,
    # decimated (straight legs collapse). Done = solid orange; to-come = faint dashed
    # (the day's plan, not the week's -- the week fan is the fault being fixed). Other
    # helicopters draw no route at any time. The window starts at the B17 departure
    # (09:45), not midnight: H3 also flew a southern round trip 07:00-08:40, and drawing
    # the whole day made the map read as two routes crossing at Flesland (whipster FAIL).
    for ag in map_route_agents(beat, focus_ag):
        route = routes[ag]
        done_k, marker = markers[ag]
        pts = [pj(*p) for p in route[::7]]
        dk = max(1, done_k // 7)
        t0k, t1k = story_route_window(times[ag])
        if dk > t0k:
            # orange glow, two passes: a wide faint halo plus the solid route (light on
            # charcoal, never a flat orange fill). The first version's single halo did
            # not read as glow (whipster FAIL).
            cv.line(pts[t0k:dk], GLOW, 11.0, alpha=0.15)
            cv.line(pts[t0k:dk], GLOW, 5.0, alpha=0.40)
            cv.line(pts[t0k:dk], P["accent"], 2.0)
        if t1k > dk:
            cv.line(pts[dk:t1k], P["muted"], 1.0, dash=(4, 4))
    # focus-route exit (map beat only): if the flown route's farthest point is off-panel,
    # mark where it leaves the frame with the nearest site name (v1's B17 fix stands)
    if beat == "map" and focus_ag in routes:
        done_k, _ = markers[focus_ag]
        t0k = story_route_window(times[focus_ag])[0]
        done_pts = routes[focus_ag][t0k:max(t0k + 1, done_k)]
        if done_pts:
            far = max(done_pts, key=lambda p: p[1])
            fx_, fy_ = pj(*far)
            if not (0 <= fy_ < PANEL_H):
                near = min(stops, key=lambda n: (stops[n][0] - far[0]) ** 2 +
                           (stops[n][1] - far[1]) ** 2)
                # chevron ON the route line, at the point the flown leg leaves the panel:
                # _chevron clamps x and y independently, which put B2 ~100-150 px from
                # the line in f0300/f0450, on opposite sides as the camera glided
                # (whipster re-check FAIL -- same genus as the B3 fault). The drawn line
                # is the decimated pts; its first outbound exit is where the leg leaves
                # toward the far point.
                pts = [pj(*p) for p in routes[focus_ag][::7]]
                dk = max(1, done_k // 7)
                ex = _first_exit(pts[t0k:dk])
                box = B._chevron(cv, ex[0], ex[1], near) if ex else B._chevron(cv, fx_, fy_, near)
                if box:
                    reserved.append(box)
    # the two legs of the story (scenario positions, assumed). The CANCELLED leg is a
    # straight dashed line because the flight never flew -- there is no trajectory to
    # draw -- and its label is clamped inside the panel so it stays readable. The
    # REBOOKED leg is the real flown trajectory (rebook_segment), not the straight
    # chord: the chord crossed the landmass and the marker flew off it (whipster FAIL).
    if beat in ("section", "findings"):
        fx, fy = pj(*heliport)
        bx, by = pj(*stops["B3"])
        cv.line([(fx, fy), (bx, by)], P["accent"], 2.0, dash=(6, 5))
        lx, ly = _clamp_label(cv, (fx + bx) / 2 + 8, (fy + by) / 2 - 8, "CANCELLED")
        B._text(cv, lx, ly, "CANCELLED", 12, "Bold", P["accent"])
        if beat == "findings":
            rpts = [pj(*p) for p in routes[focus_ag]]  # RAW points, not decimated (see rebook_segment)
            rs, rd, re_ = rebook_segment(times[focus_ag], run_t)
            if rd > rs:
                cv.line(rpts[rs:rd], P["ink"], 2.5)
            if re_ > rd:
                cv.line(rpts[rd:re_], P["muted"], 1.0, dash=(4, 4))
            mx_, my_ = rpts[min(rd, len(rpts) - 1)] if rpts else (fx, fy)
            # label to the LEFT of the marker, over the open sea west of Flesland, on a
            # ground chip: the previous version sat above the marker on the maroon
            # coast, chipless, its top touching the panel edge (whipster round 2)
            rw = cv.measure("REBOOKED FRI 18:00", ("Inter", "Bold"), 12)
            _chip_label(cv, mx_ - rw - 16, my_ - 6, "REBOOKED FRI 18:00", 12, P["ink"])
        if not (0 <= bx < PANEL_W and 0 <= by < PANEL_H):
            # chevron at the point the leg LEAVES the panel (not the clamped corner:
            # _chevron clamps x and y independently, which put B3 in the top-left
            # corner ~350 px from where the dashed leg exits -- whipster round 2)
            ex = _segment_exit(fx, fy, bx, by)
            box = B._chevron(cv, ex[0], ex[1], "B3") if ex else B._chevron(cv, bx, by, "B3")
            if box:
                reserved.append(box)
    # markers: the focus helicopter with its reserved label box; the others as small dots
    # only (no routes, no chevrons, no callouts -- they are not the story; an off-frame
    # other is skipped silently instead of collapsing into a callout at the edge)
    for ag in sorted(routes):
        _, marker = markers[ag]
        mx, my = pj(*marker)
        if ag == focus_ag:
            cv.circle(mx, my, 34.0, fill=GLOW, alpha=0.12)
            cv.circle(mx, my, 24.0, fill=GLOW, alpha=0.25)
            cv.circle(mx, my, 16.8, stroke=P["accent"], width=1.0)
            cv.circle(mx, my, 4.2, fill=P["accent"])
            bx0, by0, bx1, by1 = _flbox
            cv.polygon([(bx0, by0), (bx1, by0), (bx1, by1), (bx0, by1)],
                       fill=P["ground"], alpha=0.92)
            ex = bx0 if bx0 > mx else bx1
            cv.line([(ex, (by0 + by1) / 2), (mx, my)], P["accent"], 1.0, alpha=0.7)
            B._text(cv, (bx0 + bx1) / 2, by0 + 5, ag, 13, "Bold", P["accent"], anchor="m")
        # the other helicopters are small MUTED dots, and only in the hook/map beats:
        # in the section/findings beats the story legs are the geography, and an
        # unlabelled bright dot (H2 mid-sea at T_CANCEL) read as a stray mark
        # (whipster round 2)
        elif beat in ("hook", "map") and 0 <= mx < PANEL_W and 0 <= my < PANEL_H:
            cv.circle(mx, my, 2.5, fill=P["muted"])
    # live labels, filtered: places + story sites only (the other B labels added clutter)
    # In the findings beat the camera sits on Flesland, so BERGEN + FLESLAND + the H2
    # label pile up on one patch of coast (whipster FAIL): there, only the rebook's
    # endpoints (FLESLAND, B3) are labelled.
    import copy as _copy
    strip_f = _copy.copy(strip)
    if beat == "findings":
        keep = lambda it: it[0] in ("B3", "FLESLAND") or it[5] == "fjord"
    else:
        keep = lambda it: it[5] in ("place", "fjord") or it[0] in ("B3", "B17")
    strip_f.label_items = [it for it in strip.label_items if keep(it)]
    placed, fell = B._live_labels(cv, strip_f, pj, reserved)
    # scale bar (km) on a ground chip matching the charcoal place-label chips
    km_px = 1000 / (span * 111320)
    bar_km = max(1, int(round(PANEL_W * 0.18 / km_px)))
    bx, by = 24, PANEL_H - 22
    cv.line([(bx, by), (bx + bar_km * km_px, by)], P["ink"], 2.0)
    lab = f"{bar_km} km"
    lw = cv.measure(lab, ("Inter", "Regular"), 13)
    cv.polygon([(bx - 5, by - 26), (bx + lw + 5, by - 26), (bx + lw + 5, by - 6), (bx - 5, by - 6)],
               fill=P["ground"], alpha=0.92)
    B._text(cv, bx, by - 22, lab, 13, "Regular", P["ink"])
    B._text(cv, PANEL_W - 30, 14, "N", 15, "Bold", P["ink"])
    cv.line([(PANEL_W - 24, 36), (PANEL_W - 24, 52)], P["ink"], 1.0)
    return cv.to_pil(), fell


WHERE2 = dict(B.WHERE)
WHERE2["section"] = "WHERE: THE CANCELLATION MOMENT — THU 12:30 UTC"
WHERE2["findings"] = "WHERE: FRI 18:00–18:30 — H2-14h FLIES THE REBOOK TO B3"


# ---------------------------------------------------------------- frame + main
def render_frame_v2(f, strip, glide, deck):
    rep, stops, heliport, routes, times, w11_routes, w11_times, (wt, wwind, whs) = B._CTX
    beat = B.beat_of(f)
    focus_ag, focus, markers, map_run_t = B.focus_of(f, w11_routes, w11_times)
    run_t = v2_run_t_of(f)
    u = (f + 1) / N
    cx, cy, span = glide.view(u, focus, f)
    sec_t = T_CANCEL if beat == "section" else run_t
    wind, hs = B.weather_at(wt, wwind, whs, sec_t)
    cv = Canvas(W, H, bg=P["ground"], ss=SS)
    B._text(cv, 56, 44, B.KICKERS[beat], 17, "Bold", P["accent"])
    hl = B.headlines(rep)[beat]
    for y, line in zip((76, 136), hl):
        x = 56
        for text, accent in line:
            B._text(cv, x, y, text, 52, "Bold", P["accent"] if accent else P["ink"])
            x += cv.measure(text, ("Inter", "Bold"), 52)
    draw_section_v2(cv, f, sec_t, hs, wind, beat)
    y = B.SEC_TOP + SEC_PH2 + 30
    B._text(cv, 56, y, "CLOCK", 19, "Bold", P["ink"])
    x = 56 + cv.measure("CLOCK ", ("Inter", "Bold"), 19)
    B._text(cv, x, y, B.clock_str(sec_t), 19, "Bold", P["accent"])
    x += cv.measure(B.clock_str(sec_t), ("Inter", "Bold"), 19) + 34
    B._text(cv, x, y, "WIND", 19, "Bold", P["ink"])
    x += cv.measure("WIND ", ("Inter", "Bold"), 19)
    B._text(cv, x, y, f"{wind:.1f} m/s", 19, "Bold", P["muted"])
    x += cv.measure(f"{wind:.1f} m/s", ("Inter", "Bold"), 19) + 34
    B._text(cv, x, y, "Hs", 19, "Bold", P["ink"])
    x += cv.measure("Hs ", ("Inter", "Bold"), 19)
    # the over-limit Hs stays orange, not heat red: HEAT measures 2.57:1 on charcoal
    # and the clock-row number went dim -- the charcoal fights the red where it breaks
    # the reading, so the red keeps only the gauge tick (a colour patch, never text)
    B._text(cv, x, y, f"{hs:.2f} m", 19, "Bold", P["accent"] if hs > 6.0 else P["muted"])
    gy1 = B.draw_chart(cv, f, beat, run_t)
    my0 = gy1 + 36
    B._text(cv, 56, my0, WHERE2[beat], 14, "Bold", P["muted"])
    panel, _fell = draw_map_v2(strip, glide, cx, cy, focus_ag, markers, w11_routes, w11_times,
                               map_run_t, beat, f, stops, heliport)
    my1 = my0 + 24 + PANEL_H
    yb = my1 + 28
    B._text(cv, 56, yb, deck[beat][0], 22, "Regular", P["ink"])
    B._text(cv, 56, yb + 30, deck[beat][1], 22, "Regular", P["ink"])
    B._text(cv, 56, yb + 70, "Map: coastline OpenStreetMap (ODbL); B positions + heliport from the "
            "scenario (assumed); only the featured flight + the rebook leg are drawn.", 13,
            "Regular", P["muted"])
    B._text(cv, 56, yb + 88, "Sea: NORA3 wind/wave at the centroid (MET Norway, CC BY 4.0); "
            "Tp 11.2 s. Section sea: JONSWAP live, display-grade; deck height schematic.",
            13, "Regular", P["muted"])
    B._text(cv, 56, yb + 106, "DRAFT — ONE-WINTER PILOT · 1 OF 24 WINTERS · B POSITIONS ASSUMED · "
            "HELIDECK LIMITS ASSUMED (25 m/s, 6 m)", 13, "Regular", P["muted"])
    B._text(cv, 56, yb + 124, "RECOVERY = REBOOK INTO WEEKLY SLACK ONLY · "
            "LEAN WINDOWS 56 h, NOT THE PAPER'S 50 h", 13, "Regular", P["muted"])
    B._text(cv, W - 56, 46, "offshore_simulations", 15, "Bold", P["muted"], anchor="r")
    img = cv.to_pil()
    img.paste(panel, (56, my0 + 24))
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUTDIR / "bergen-lean-pilot-v2.mp4"))
    ap.add_argument("--seconds", type=float, default=30.0)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--only", type=int, default=None, help="render a single frame index (still check)")
    ap.add_argument("--resume-from", type=int, default=None,
                    help="resume a killed render: skip frames < N (already on disk)")
    a = ap.parse_args()
    assert a.seconds * a.fps == N, "this film is 30 s at 30 fps = 900 frames"
    rep = B.load_report()
    stops, heliport, tr, routes, times, w11_routes, w11_times = B.load_traj()
    weather = B.load_weather()
    B._CTX = (rep, stops, heliport, routes, times, w11_routes, w11_times, weather)
    # the v2 camera: bergen_film.focus_of / measure_envelope resolve map_run_t_of in
    # bergen_film's globals, so patch it to the v2 version before any camera step.
    B.map_run_t_of = v2_map_run_t_of
    # the look: charcoal + orange glow, applied to the shared palette before any drawing
    apply_palette()
    print(f"look: charcoal {P['ground']} + orange glow {P['accent']} / {GLOW}, heat {HEAT}, "
          f"sea kept {P['sea']} (ratio vs charcoal 1.45)")
    print("gates first:")
    B.gates()
    bbox = (min(min(lon for lon, _ in routes[ag]) for ag in routes) - 0.06,
            min(min(lat for _, lat in routes[ag]) for ag in routes) - 0.06,
            max(max(lon for lon, _ in routes[ag]) for ag in routes) + 0.06,
            max(max(lat for _, lat in routes[ag]) for ag in routes) + 0.06)
    import math as _m
    fw = (bbox[2] - bbox[0]) * 111.32 * _m.cos(_m.radians(60.2))
    fh = (bbox[3] - bbox[1]) * 111.32
    print(f"field {fw:.1f} km x {fh:.1f} km; static-wide fit = "
          f"{PANEL_H * fw / fh:.0f}px = {PANEL_H * fw / fh / PANEL_W * 100:.0f}% of panel width -> REJECTED")
    deck = B.narration(rep)
    print("narration (pass 1, from the measured report):")
    for b, lines in deck.items():
        print(f"  {b}: {' '.join(lines)}")
    env, centres, g0 = B.measure_envelope(B.Glide(bbox))
    print(f"camera envelope lon {env[0]:.3f}-{env[2]:.3f} lat {env[1]:.3f}-{env[3]:.3f}; "
          f"view {g0.view_lon:.2f} deg lon x {g0.view_lat:.2f} deg lat; "
          f"peak pan {g0._pan_max:.3f} widths/s at f{g0._pan_max_f} (cap 0.25)")
    strip = B.Strip(B.Glide(bbox), stops, heliport)
    out = Path(a.out)
    frames = out.parent / "frames_v2"
    frames.mkdir(parents=True, exist_ok=True)
    glide = B.Glide(bbox)
    if a.resume_from is not None:
        missing = [f for f in range(a.resume_from) if not (frames / f"f{f:04d}.png").exists()]
        if missing:
            raise SystemExit(f"--resume-from {a.resume_from}: {len(missing)} earlier frames missing "
                             f"(first f{missing[0]:04d}.png); refusing to encode a gapped film")
        print(f"resuming from f{a.resume_from:04d}")
        for ff in range(a.resume_from):
            _, foc, _, _ = B.focus_of(ff, w11_routes, w11_times)
            glide.view((ff + 1) / N, foc, ff)
    start = a.resume_from or 0
    if a.only is not None:
        for ff in range(a.only):
            _, foc, _, _ = B.focus_of(ff, w11_routes, w11_times)
            glide.view((ff + 1) / N, foc, ff)
        img = render_frame_v2(a.only, strip, glide, deck)
        p = frames / f"f{a.only:04d}.png"
        img.save(p)
        print(p)
        return
    t0 = time.time()
    for f in range(start, N):
        img = render_frame_v2(f, strip, glide, deck)
        img.save(frames / f"f{f:04d}.png")
        if f % 100 == 0:
            print(f"f{f:04d} {time.time() - t0:.0f}s", flush=True)
    print(f"rendered {N - start} frames in {time.time() - t0:.0f}s; "
          f"peak pan {glide._pan_max:.3f} widths/s at f{glide._pan_max_f}")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(a.fps), "-i",
                    str(frames / "f%04d.png"), "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                    "-pix_fmt", "yuv420p", str(out)], check=True)
    print(out, f"{N} frames")


if __name__ == "__main__":
    main()
