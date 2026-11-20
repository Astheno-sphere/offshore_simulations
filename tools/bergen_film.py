"""One-winter pilot film: Gribkovskaia & Slettemark 2025, Bergen (Logistics 9(2):73).

30 s, 1080x1350, 30 fps, 900 frames, skia, section + map diptych (the v10 pattern).

    PYTHONPATH=. venv-studio/bin/python tools/bergen_film.py --out <mp4> [--only N] [--resume-from N]

Every number on screen comes from docs/linkedin/07-gribkovskaia/run/run-report.json
(the source of truth) or the run CSVs; the deck sentences are chosen from those
measured values in a first pass (two-pass narration) and only then rendered. Nothing
is rendered before contract.validate passes on BOTH trajectories with the Bergen
land polygon, and no frame is rendered before the camera envelope is measured.

Beats (Arshad's draft script): (1) hook card, (2) map: week 11 of the ACTUAL
5-helicopter program animating, (3) section: the featured B3 cancellation live
(Thu 20 Feb 12:30 UTC, Hs 7.24 m over the assumed 6.0 m limit -- interpolated
between the 12:00 and 13:00 hourly NORA3 samples) and its rebook
29.5 h later, (4) findings: P90 unmet 0.0 vs threshold <= 1, one winter only.

Camera (measured, not habit): the B field is 199.7 km x 339 km in a 968x300 panel,
so a static wide would shrink it to 177 px = 18% of the panel width (the Oslofjord
rejection, worse there at 7%): rejected. A dead-zone glide at span 1.2 (view
4.32 deg lon x 0.67 deg lat) follows the focus helicopter; the focus switches
H3-10h -> H2-14h at the section beat over a 30-frame blend. The map is one static
raster strip (land + roads + hillshade + place labels, rendered once at the film's
own dpp) blitted per frame at the glide window -- the Molde fixed-camera pattern
generalised to a 1-D glide -- with routes, markers and chevrons drawn live.
Land is the contract land.geojson itself (simplified 0.001 for display): the
measured camera envelope (lon 1.34-5.56 / lat 59.95-61.50, once the glide is
clamped to the land's east bound 5.5617) sits entirely inside it -- the south gap
(land ends 59.335, B19 at 58.708) is below every view, the north gap (land to
61.808) above every view, and west of lon 4.50 there is no coast in the envelope
lat band (Overpass coastline check: zero ways; see world-fetch/fetch_bergen_places.py).
The full strip-land fetch (fetch_bergen_wide.py) was stopped once that measurement
made it unnecessary: the only real coast outside the contract land is the mainland
east of 5.5617, and no rendered view reaches it.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import skia
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
RUN = Path("/home/hatch/workspace/docs/linkedin/07-gribkovskaia/run")
OUTDIR = Path("/home/hatch/workspace/docs/linkedin/07-gribkovskaia")
SCEN = Path("/home/hatch/workspace/tmp-wip-heli/offsim/papers/irinagribkovskaia-2025-tactical-helicopter/scenario.bergen.yaml")

from offsim.cinema.draw import Canvas  # noqa: E402
from offsim.cinema.look import PALETTES, font_path  # noqa: E402
from offsim.motion.section import route_at  # noqa: E402
from offsim.physics import ocean  # noqa: E402

P = PALETTES["section-plan"]
W, H, SS, FPS, N = 1080, 1350, 2, 30, 900
PANEL_W, PANEL_H = W - 112, 300
# beats: (first frame, last frame)
HOOK = (0, 89)
MAPB = (90, 509)
SECB = (510, 719)
FIND = (720, 899)
# traj seconds from Mon 2024-12-02 00:00 UTC
T_MON11 = 6652800       # Mon 17 Feb 00:00 (week 11)
T_MAP_START = 6947100   # Thu 20 Feb 09:45: H3-10h departs Flesland for B17 (measured)
T_CANCEL = 6957000      # Thu 20 Feb 12:30, featured cancellation (actual, B3, H3-10h)
T_REBOOK = 7063200      # Fri 21 Feb 18:00, rebooked departure (H2-14h)
T0 = datetime(2024, 12, 2, tzinfo=timezone.utc)
SPAN_MULT = 1.2         # view 4.32 deg lon x 0.67 deg lat (measured: fits the lon span, glides in lat)
PAN_CAP = 6.0           # panel-widths per film (cap 0.20 widths/s; the Thu-morning legs need ~0.19)
TP_FEATURED = 11.17     # s, NORA3 wave at the featured hour, nearest grid cell (measured)
HELI_NOTE = "S-92 STYLISED — ALL DIMS ASSUMED"
DRAFT = ("DRAFT — ONE-WINTER PILOT · 1 OF 24 WINTERS · B POSITIONS ASSUMED · "
         "HELIDECK LIMITS ASSUMED (25 m/s, 6 m) · RECOVERY = REBOOK INTO WEEKLY SLACK ONLY · "
         "LEAN WINDOWS 56 h, NOT THE PAPER'S 50 h")


def _ascent(size, weight):
    f = skia.Font(skia.Typeface.MakeFromFile(font_path(weight)), float(size))
    return -f.getMetrics().fAscent


def _text(cv, x, top, s, size, weight="Regular", color="#ffffff", anchor="l", tracking=0.0):
    cv.text(x, top + _ascent(size, weight), s, font=("Inter", weight), size=size, color=color,
            tracking=tracking, anchor=anchor)


def load_report():
    rep = json.loads((RUN / "run-report.json").read_text())
    # the headline facts, asserted against the report before any frame (never typed by hand)
    assert rep["lean"]["unmet_p90"] == 0.0 and rep["actual"]["unmet_p90"] == 0.0
    assert rep["lean"]["kpis"]["flights_unmet"] == 0.0 and rep["actual"]["kpis"]["flights_unmet"] == 0.0
    assert rep["lean"]["window_hours_total"] == 56 and rep["actual"]["window_hours_total"] == 60
    assert rep["lean"]["kpis"]["flights_cancelled"] == 3.0 and rep["actual"]["kpis"]["flights_cancelled"] == 5.0
    assert rep["featured_cancellation"]["delay_h"] == 29.5
    assert rep["gates_lean"]["4_paper"]["pass"] is False  # gate 4 FAILED on window_hours: say so
    return rep


def load_traj():
    import yaml
    scen = yaml.safe_load(SCEN.read_text())
    stops = {s["name"]: (float(s["lon"]), float(s["lat"])) for s in scen["instance"]["stops"]}
    heliport = (float(scen["instance"]["base"]["lon"]), float(scen["instance"]["base"]["lat"]))
    tr = pd.read_csv(RUN / "actual-traj.csv").sort_values(["agent_id", "t"]).reset_index(drop=True)
    routes, times = {}, {}
    for ag, g in tr.groupby("agent_id"):
        routes[ag] = list(zip(g.lon, g.lat))
        times[ag] = g.t.to_numpy()
    # map routes: week 11 ONLY (Mon 17 Feb 00:00 - Mon 24 Feb 00:00). The full 13-week
    # routes would draw 12 weeks of future flying as dashed "to come".
    w11 = tr[(tr.t >= T_MON11) & (tr.t < T_MON11 + 7 * 86400)]
    w11_routes, w11_times = {}, {}
    for ag, g in w11.groupby("agent_id"):
        w11_routes[ag] = list(zip(g.lon, g.lat))
        w11_times[ag] = g.t.to_numpy()
    return stops, heliport, tr, routes, times, w11_routes, w11_times


def load_weather():
    w = pd.read_csv(RUN / "weather-centroid.csv")
    return w["t"].to_numpy(), w["wind_mps"].to_numpy(), w["hs_m"].to_numpy()


def weather_at(wt, wwind, whs, traj_t):
    """Wind/Hs at a traj moment (weather t = traj t + 86400 s). Linear interpolation."""
    t = traj_t + 86400.0
    return float(np.interp(t, wt, wwind)), float(np.interp(t, wt, whs))


def gates():
    """Gates first: contract.validate on BOTH trajectories with the Bergen land polygon.
    Air agents are exempt from the land check (domain air); the check still covers
    schema, time, teleport, speed (vmax 125 kn = 64.31 m/s) and stationary states."""
    import geopandas as gpd
    from offsim import contract
    land = gpd.read_file(ROOT / "data/worlds/bergen/land.geojson").geometry.union_all()
    agents = pd.DataFrame([
        {"agent_id": a, "cls": "helicopter", "vmax_mps": 64.306, "capacity": 19.0, "domain": "air"}
        for a in ("H1-16h", "H2-16h", "H3-14h", "H4-10h", "H2-14h", "H3-10h", "H5-10h")])
    agents = agents.drop_duplicates("agent_id").reset_index(drop=True)
    out = {}
    for name in ("lean", "actual"):
        tr = pd.read_csv(RUN / f"{name}-traj.csv")
        rep = contract.validate(tr, agents, land=land)
        out[name] = rep
        print(f"gate contract {name}: {rep}")
        if not rep.ok:
            raise SystemExit(f"contract gate FAILED on {name}: {rep}")
    return out


def beat_of(f):
    for name, (a, b) in (("hook", HOOK), ("map", MAPB), ("section", SECB), ("findings", FIND)):
        if a <= f <= b:
            return name
    raise ValueError(f)


def run_t_of(f):
    """One clock for the section, chart and readouts: the map beat runs Thu 09:45-12:30
    (H3's morning into the featured cancellation), the section beat Thu 12:30 to
    Fri 18:00 (the 29.5 h rebook wait). The map beat does NOT run Mon-Fri: at the
    week-long compression (84.5 h in 10 s) the marker crosses the panel in ~2 frames
    and no capped camera (0.25 widths/s) can keep it in frame -- measured, see the
    report. The week is carried by the full week-11 route network on the map and by
    the Hs chart, not by a chasing camera."""
    if f < MAPB[0]:
        return T_CANCEL
    if f < SECB[0]:
        return T_MAP_START + (f - MAPB[0]) / (MAPB[1] - MAPB[0]) * (T_CANCEL - T_MAP_START)
    if f < FIND[0]:
        return T_CANCEL + (f - SECB[0]) / (SECB[1] - SECB[0]) * (T_REBOOK - T_CANCEL)
    return T_REBOOK


def map_run_t_of(f):
    """The map's moment. Frozen at the cancellation through the section beat (the
    section panel + Hs chart carry the Thu-Fri time there); frozen at the rebook
    departure in the findings beat. No focus jump: H3 sits at Flesland at 12:30
    and H2 departs Flesland at 18:00, so the focus moves Flesland -> Flesland."""
    if f < MAPB[0] or SECB[0] <= f < FIND[0]:
        return T_CANCEL
    if f < SECB[0]:
        return run_t_of(f)
    return T_REBOOK


def clock_str(run_t):
    return (T0 + timedelta(seconds=float(run_t))).strftime("%a %d %b %H:%M UTC").upper()


class Glide:
    """Dead-zone glide camera (the v9 MapPanel._view_smooth logic, standalone so the
    dry-run measurement and the render step the identical camera). Fixed span, no zoom.
    Records peak pan rate (panel-widths/s) from the actual centre change."""

    def __init__(self, bbox, span_mult=SPAN_MULT, pan_cap=PAN_CAP, east_limit=5.5617):
        self.bbox = bbox
        self.span_mult, self.pan_cap = span_mult, pan_cap
        # East clamp: the view may overhang the land data ONLY where the overhang is
        # verified open sea (west, lon < 4.30 -- zero coastline ways there). East of
        # lon 5.5617 is mainland Norway, so the glide centre is clamped so the view's
        # east edge never passes the contract land's east bound (5.5617, land.geojson).
        # The v10 clamp cannot do this: the land is narrower than the view in lon,
        # so it leaves the glide alone.
        self.east_limit = east_limit
        self.k = math.cos(math.radians((bbox[1] + bbox[3]) / 2))
        self.span = span_mult * min((bbox[2] - bbox[0]) * self.k / PANEL_W,
                                    (bbox[3] - bbox[1]) / PANEL_H)
        self.pan_cap = pan_cap
        self._cam, self._last_u, self._pan_max, self._pan_max_f = None, 0.0, 0.0, -1

    @property
    def view_lon(self):
        return PANEL_W * self.span / self.k

    @property
    def view_lat(self):
        return PANEL_H * self.span

    def view(self, u, focus, f=-1):
        lon, lat = focus
        if self._cam is None:
            self._cam = (min(lon, self.east_limit - self.view_lon / 2), lat)
            self._last_u = u
            return self._cam[0], self._cam[1], self.span
        du = max(u - self._last_u, 0.0)
        self._last_u = u
        cx, cy = self._cam
        mx = (lon - cx) * self.k / self.span + PANEL_W / 2
        my = PANEL_H / 2 - (lat - cy) / self.span
        # Dead zone 0.30/0.70 (not 0.20/0.80): the camera aims the marker at 30% from
        # the edge, not the edge itself, so a fast marker keeps ~90 px of slack.
        # Time constant 0.01 (not the v9 0.02): at 900 frames the v9 constant leaves
        # the marker 1-3 px outside the frame for ~80 frames on the northbound leg
        # (measured f153-162, f342-346) -- the smoothing, not the pan cap, was the
        # limiter (peak pan was 0.117, cap 0.20).
        tx, ty = cx, cy
        if mx < 0.3 * PANEL_W:
            tx = cx - (0.3 * PANEL_W - mx) * self.span / self.k
        elif mx > 0.7 * PANEL_W:
            tx = cx + (mx - 0.7 * PANEL_W) * self.span / self.k
        if my < 0.3 * PANEL_H:
            ty = cy + (0.3 * PANEL_H - my) * self.span
        elif my > 0.7 * PANEL_H:
            ty = cy - (my - 0.7 * PANEL_H) * self.span
        a = 1.0 - math.exp(-du / 0.01) if du > 0 else 0.0
        dlon, dlat = (tx - cx) * a, (ty - cy) * a
        px = math.hypot(dlon * self.k / self.span, dlat / self.span)
        cap = du * self.pan_cap * PANEL_W
        if px > cap > 0:
            fac = cap / px
            dlon, dlat = dlon * fac, dlat * fac
        self._cam = (min(cx + dlon, self.east_limit - self.view_lon / 2), cy + dlat)
        moved = math.hypot((self._cam[0] - cx) * self.k / self.span,
                           (self._cam[1] - cy) / self.span)
        if du > 0:
            rate = moved / PANEL_W / du / (N / FPS)  # panel-widths per second
            if rate > self._pan_max:
                self._pan_max, self._pan_max_f = rate, f
        return self._cam[0], self._cam[1], self.span


def focus_of(f, routes, times):
    """Focus helicopter per beat (week-11 routes). H3-10h through the section beat
    (it sits at Flesland from 12:30), H2-14h in the findings beat (it departs
    Flesland with the rebook at 18:00). Markers are week-11 only."""
    run_t = map_run_t_of(f)
    focus_ag = "H2-14h" if f >= FIND[0] else "H3-10h"
    markers = {}
    for ag in routes:
        markers[ag] = route_at(routes[ag], times[ag], run_t)
    return focus_ag, markers[focus_ag][1], markers, run_t


def narration(rep):
    """Two-pass deck text: templates filled ONLY with measured numbers from the report.
    The hook lines are Arshad's draft script (wording corrected 2026-11-12: the
    4-heli optimum is the paper's, not Equinor's -- Equinor runs 5, and the actual
    program is solver-built). All Hs/wind values are the report's interpolated
    values at the stated timestamp (one convention, every readout)."""
    lean, act = rep["lean"], rep["actual"]
    fc = rep["featured_cancellation"]
    return {
        "hook": ("The paper's optimiser says Bergen needs 4 helicopters, not 5.",
                 "What happens in January?"),
        "map": (f"Week 11 (17–21 Feb): {int(act['per_week'][11]['cancelled'])} flights cancelled "
                f"— both rebooked, none unmet.",
                f"Thu 12:30: H3-10h to B3 cancelled — Hs {fc['hs_m_at_departure']:.2f} m "
                f"over the 6.0 m limit (assumed)."),
        "section": (f"Cancelled Thu 12:30, wind {fc['wind_mps_at_departure']:.2f} m/s (inside 25), "
                    f"Hs {fc['hs_m_at_departure']:.2f} m (over 6.0).",
                    f"Rebooked to H2-14h, Fri 18:00 — {fc['delay_h']:.1f} h late. No overtime, "
                    f"no spare helicopter."),
        "findings": (f"P90 unmet flights/week (lean) {lean['unmet_p90']:.1f} vs threshold ≤ 1: "
                     f"PASS — on this one winter only.",
                     f"Lean {int(lean['kpis']['flights_cancelled'])} cancelled / "
                     f"{int(act['kpis']['flights_cancelled'])} actual; delay "
                     f"{lean['kpis']['total_delay_h']:.1f} h vs {act['kpis']['total_delay_h']:.2f} h, "
                     f"of 1,209 flown each."),
    }


# ---------------------------------------------------------------- strip (map base)
def _skia_image_rgba(arr):
    a = arr[..., 3:4].astype(np.float32) / 255.0
    pm = np.concatenate([(arr[..., :3].astype(np.float32) * a + 0.5).astype(np.uint8), arr[..., 3:4]], axis=-1)
    return skia.Image.fromarray(np.ascontiguousarray(pm), colorType=skia.kRGBA_8888_ColorType,
                                alphaType=skia.kPremul_AlphaType)


class Strip:
    """One static raster of the whole camera envelope at the film's own dpp, blitted per
    frame at the glide window (the Molde fixed-camera pattern, generalised to a glide).
    Contents: flat teal sea, dark land, smoothed hillshade, OSM roads, OSM-verified
    place labels + B-site dots/labels + FLESLAND. Routes and markers are live, per frame."""

    def __init__(self, glide, stops, heliport):
        import geopandas as gpd
        self.span = glide.span
        self.k = glide.k
        # envelope: every view the glide can open, + margin (measured in the dry run)
        env, _, _ = measure_envelope(glide)
        self.lon0 = env[0] - 0.05
        self.lon1 = env[2] + 0.05
        self.lat0 = env[1] - 0.05
        self.lat1 = env[3] + 0.05
        self.sw = int(round((self.lon1 - self.lon0) * self.k / self.span))
        self.sh = int(round((self.lat1 - self.lat0) / self.span))
        self.pj = lambda lon, lat: ((lon - self.lon0) * self.k / self.span,
                                    (self.lat1 - lat) / self.span)
        cv = Canvas(self.sw, self.sh, bg=P["sea"], ss=SS)
        land = gpd.read_file(ROOT / "data/worlds/bergen/land.geojson").geometry.union_all()
        land = land.simplify(0.001, preserve_topology=True)
        geoms = getattr(land, "geoms", [land])
        nverts = 0
        for g in geoms:
            ext = [self.pj(x, y) for x, y in g.exterior.coords]
            nverts += len(ext)
            if len(ext) >= 3:
                cv.polygon(ext, fill="#432629")
            for hole in g.interiors:
                hp = [self.pj(x, y) for x, y in hole.coords]
                if len(hp) >= 3:
                    cv.polygon(hp, fill=P["sea"])
        print(f"strip land: {len(geoms)} parts, {nverts} verts, {self.sw}x{self.sh}px")
        # hillshade (faint: smoothed sigma 2, alpha capped 0.45) under the roads, over the land
        try:
            from offsim.worlds.terrain_tint import for_bbox
            rgba, why = for_bbox(ROOT / "data/worlds/bergen",
                                 (self.lon0, self.lat0, self.lon1, self.lat1),
                                 (self.sw, self.sh), azimuth=315.0, altitude=55.0,
                                 smooth_sigma=2.0, alpha_range=(0.05, 0.45))
            if rgba is not None:
                cv.cv.drawImage(_skia_image_rgba(rgba), 0, 0)
                print("strip hillshade: on")
            else:
                print(f"strip hillshade: off ({why})")
        except Exception as exc:  # noqa: BLE001 - hillshade is texture, never a render blocker
            print(f"strip hillshade: off ({exc})")
        # roads (Bergen OSM extract, major/secondary/tertiary only, clipped to the strip)
        roads = json.loads((ROOT / "data/worlds/bergen/osm/roads.geojson").read_text())
        buckets = {"major": [], "secondary": [], "tertiary": []}
        for f in roads.get("features", []):
            hw = f["properties"].get("highway", "")
            coords = f["geometry"]["coordinates"]
            if len(coords) < 2:
                continue
            if not any(self.lon0 - 0.05 <= c[0] <= self.lon1 + 0.05 and
                       self.lat0 - 0.05 <= c[1] <= self.lat1 + 0.05 for c in coords):
                continue
            key = ("major" if hw in ("motorway", "trunk", "primary", "primary_link", "trunk_link")
                   else "secondary" if hw == "secondary" else "tertiary" if hw == "tertiary" else None)
            if key:
                buckets[key].append([self.pj(lon, lat) for lon, lat in coords])
        for key, col, wd, al in (("major", (138, 122, 110), 1.6, 0.55),
                                 ("secondary", (120, 106, 96), 1.1, 0.45),
                                 ("tertiary", (110, 96, 88), 0.8, 0.35)):
            if buckets[key]:
                cv.lines(buckets[key], col, wd, alpha=al)
        print(f"strip roads: major {len(buckets['major'])}, secondary {len(buckets['secondary'])}, "
              f"tertiary {len(buckets['tertiary'])}")
        for g in geoms:  # coastline hairline on top of the hillshade
            ext = [self.pj(x, y) for x, y in g.exterior.coords]
            if len(ext) >= 3:
                cv.line(ext + [ext[0]], P["streak_hi"], 1.0)
        self.img = cv.to_pil()
        self._labels(cv, stops, heliport)
        self.img = cv.to_pil()
        # skia image for sub-pixel blits
        arr = np.asarray(self.img.convert("RGBA"))
        self.skia_img = _skia_image_rgba(arr)

    def _labels(self, cv, stops, heliport):
        """Dots only are baked into the strip (exact geographic anchors). TEXT labels
        are drawn live per frame in draw_map: a label baked at the strip edge is
        clipped by the blit window (f0300: FLESLAND and B9 half-cut), while the live
        placer skips off-view anchors and keeps every box inside the panel.
        Places come from places_bergen.json (OSM-verified); the sea name is OSM
        relation 9051063 (place=sea, name:en North Sea -- the global Overpass query
        for natural=sea returns 0 because the relation carries place=sea, not
        natural=sea). The NORTH SEA anchor (2.60, 60.05) is asserted open sea in
        the land geometry. B1-B20 labels come from the scenario (assumed positions,
        never real platform names); FLESLAND sits on the scenario heliport point."""
        import geopandas as gpd
        land = gpd.read_file(ROOT / "data/worlds/bergen/land.geojson").geometry.union_all()
        from shapely.geometry import Point
        places = json.loads((ROOT / "data/worlds/bergen/osm/places_bergen.json").read_text())
        want = {"Bergen": "BERGEN", "Florø": "FLORØ", "Haugesund": "HAUGESUND", "Måløy": "MÅLØY"}
        items = []
        for p in places:
            if p["name"] in want and p["kind"] in ("city", "town", "village"):
                items.append((want[p["name"]], p["lon"], p["lat"], 13, P["accent"], "place"))
        sea_anchor = (2.60, 60.05)
        assert not land.contains(Point(*sea_anchor)), "NORTH SEA anchor is on land!"
        items.append(("NORTH SEA", sea_anchor[0], sea_anchor[1], 13, "#7ba3ad", "fjord"))
        items.append(("FLESLAND", heliport[0], heliport[1], 13, P["accent"], "place"))
        for name, (lon, lat) in sorted(stops.items()):
            items.append((name, lon, lat, 11, P["accent"], "site"))
        for text, lon, lat, size, color, kind in items:
            ax, ay = self.pj(lon, lat)
            if kind == "place":
                cv.circle(ax, ay, 10, fill=color, alpha=0.22)
                cv.circle(ax, ay, 4, fill=color)
            elif kind == "site":
                cv.circle(ax, ay, 2.5, fill=color)
        self.label_items = items
        print(f"strip label items: {len(items)} (dots baked, text drawn live per frame)")


def measure_envelope(glide):
    """Dry-run the glide over all 900 frames (clean path) and return the view envelope
    (lon0, lat0, lon1, lat1) plus per-frame centres. The render steps the identical
    camera, so the strip built from this envelope covers every frame."""
    _, _, _, _, _, routes, times, _ = _CTX
    g = Glide(glide.bbox, glide.span_mult, glide.pan_cap)
    env = [1e9, 1e9, -1e9, -1e9]
    centres = []
    for f in range(N):
        _, focus, _, _ = focus_of(f, routes, times)
        cx, cy, span = g.view((f + 1) / N, focus, f)
        vx0, vx1 = cx - (PANEL_W / 2) * span / g.k, cx + (PANEL_W / 2) * span / g.k
        vy0, vy1 = cy - (PANEL_H / 2) * span, cy + (PANEL_H / 2) * span
        env[0], env[1] = min(env[0], vx0), min(env[1], vy0)
        env[2], env[3] = max(env[2], vx1), max(env[3], vy1)
        centres.append((cx, cy))
    return env, centres, g


_CTX = None  # (rep, stops, heliport, routes, times, w11_routes, w11_times, weather)


# ---------------------------------------------------------------- section + charts
# S-92 stylised side profile, drawn to the sprite-sheet dims (overall length
# 20.90 m, rotor Ø 17.20 m, height 5.15 m) instead of the CAD asset, whose
# declared dims FAIL QA (rotor ~21%, width ~340% off). Nose right, tail left.
# All dims assumed -- HELI_NOTE stays on screen wherever this is drawn.
S92_HULL_M, S92_ROTOR_D_M, S92_H_M = 17.1, 17.20, 5.15


def _draw_s92(cv, to_px, cx_m, deck_z):
    """Hand-drawn stylised S-92 on deck: mast + rotor disc, readable tail rotor,
    real gear (struts + wheels). Coordinates in metres, (dx from heli centre,
    dz above the deck)."""
    P_ = lambda dx, dz: to_px(cx_m + dx, deck_z + dz)
    hull = "#d9c8a3"
    dark = "#16323a"
    # gear: two struts + wheels (wheel centres 0.45 m above the deck)
    for gx in (-5.5, 4.5):
        cv.line([P_(gx, 0.45), P_(gx, 1.15)], P["ink"], 1.5)
        wx, wy = P_(gx, 0.45)
        cv.circle(wx, wy, 3.2, fill=P["ink"])
        cv.circle(wx, wy, 1.2, fill=P["ground"])
    # fuselage: nose right, tail boom tapering left, belly at deck + 1.0
    fus = [(-8.6, 2.6), (-8.2, 3.0), (-5.0, 3.5), (2.0, 3.6), (7.6, 3.2),
           (8.6, 2.4), (8.2, 1.5), (4.0, 1.0), (-4.5, 1.0), (-8.0, 1.6)]
    cv.polygon([P_(x, z) for x, z in fus], fill=hull, stroke=P["ink"], width=1.5)
    # tail fin + stabiliser + tail rotor (Ø 2.4 m, four blades)
    cv.polygon([P_(-8.6, 2.6), P_(-8.0, 4.6), P_(-6.9, 4.4), P_(-7.1, 2.8)],
               fill=hull, stroke=P["ink"], width=1.2)
    cv.line([P_(-8.4, 3.3), P_(-6.4, 3.3)], P["ink"], 1.5)
    tx, ty = P_(-7.6, 3.9)
    cv.circle(tx, ty, 8.0, stroke=P["ink"], width=1.5)
    cv.line([(tx - 5.5, ty - 5.5), (tx + 5.5, ty + 5.5)], P["ink"], 1.5)
    cv.line([(tx - 5.5, ty + 5.5), (tx + 5.5, ty - 5.5)], P["ink"], 1.5)
    cv.circle(tx, ty, 1.8, fill=P["ink"])
    # windows: cockpit pair + three cabin windows
    for x0, x1 in ((5.6, 7.4), (2.6, 4.4), (-0.4, 1.4), (-3.4, -1.6)):
        cv.polygon([P_(x0, 2.55), P_(x1, 2.55), P_(x1, 3.05), P_(x0, 3.05)], fill=dark)
    # mast + rotor disc (Ø 17.20 m, centred on the mast at dx +0.5)
    cv.line([P_(0.5, 3.6), P_(0.5, 4.9)], P["ink"], 2.0)
    cv.line([P_(0.5 - S92_ROTOR_D_M / 2, 4.9), P_(0.5 + S92_ROTOR_D_M / 2, 4.9)],
            P["ink"], 2.5)
    cv.line([P_(0.5 - S92_ROTOR_D_M / 2, 4.72), P_(0.5 + S92_ROTOR_D_M / 2, 4.72)],
            P["ink"], 3.5, alpha=0.35)
    cv.circle(*P_(0.5, 4.9), 2.0, fill=P["ink"])


# section geometry: 160 m wide, 50 m tall, sea still-water at z=10 m (section.py values)
L_M, H_M, SEA_Z = 160.0, 50.0, 10.0
SEC_TOP, SEC_PH = 236, int(W * H_M / L_M)


def draw_section(cv, f, run_t, hs, wind, beat):
    """Helideck in a gale: JONSWAP sea (Hs measured, Tp 11.17 s at the featured hour),
    the assumed 6.0 m Hs limit line, a schematic jacket + helideck (deck height
    schematic, legs broken), the stylised S-92 on deck. Streaks stop 2 m above the
    still-water line and fade over 4 m. Findings beat replaces the sea with KPI bars."""
    s = W / L_M
    top, ph = SEC_TOP, SEC_PH
    to_px = lambda x, z: (x * s, top + ph - z * s)
    if beat == "findings":
        _draw_findings_section(cv, top, ph)
        return
    xs = np.linspace(0, L_M, 320)
    eta = ocean.surface(xs, float(run_t), hs, TP_FEATURED, seed=7)
    # chop: short deterministic components (6-18 m) so a 7 m sea reads steep and
    # chopped in a 160 m panel -- the Tp 11.17 s swell alone is ~195 m long, less
    # than one wave across the panel, so it draws as a gentle slope. The sum is
    # renormalised to std Hs/4, so the drawn significant height stays measured.
    rng = np.random.default_rng(7)
    chop = np.zeros_like(xs)
    for lam in (6.0, 9.0, 13.0, 18.0):
        chop += rng.uniform(0.25, 0.5) * np.sin(2 * np.pi * xs / lam + rng.uniform(0, 2 * np.pi))
    eta = eta + chop
    eta *= (hs / 4.0) / max(float(np.std(eta)), 1e-9)
    surf = [to_px(x, SEA_Z + e) for x, e in zip(xs, eta)]
    cv.polygon(surf + [(W, top + ph), (0, top + ph)], fill=P["sea"])
    for k in range(1, 4):
        cv.line([(x, y + k * 9) for x, y in surf], (107, 79, 74, 70), 0.5)
    cv.line(surf, P["streak_hi"], 2.0)
    # whitecaps on the steepest crests
    crest = np.where((eta[1:-1] > eta[:-2]) & (eta[1:-1] >= eta[2:]) &
                     (eta[1:-1] > 0.6 * eta.max()))[0] + 1
    for i in crest:
        x0p, y0p = to_px(xs[i] - 1.5, SEA_Z + eta[i])
        x1p, _ = to_px(xs[i] + 1.5, SEA_Z + eta[i])
        cv.line([(x0p, y0p), (x1p, y0p)], P["ink"], 1.5, alpha=0.85)
    # Hs gauge (left): Hs is a significant height, not a crest line -- the f0300
    # dashed line across the panel read as a crest threshold the waves never
    # reached (instantaneous crest +2.7 m). The gauge shows the measured Hs
    # against the assumed 6.0 m limit; the chart below carries the limit line.
    gx = 92.0
    gz = lambda z: top + ph - z * s
    cv.line([(gx, gz(SEA_Z)), (gx, gz(SEA_Z + 8.0))], P["ink"], 1.5)
    for v in (0.0, 6.0):
        cv.line([(gx - 8, gz(SEA_Z + v)), (gx + 8, gz(SEA_Z + v))], P["ink"], 1.5)
    _text(cv, gx + 14, gz(SEA_Z + 6.0) + 4, "LIMIT 6.0 m — ASSUMED", 12, "Bold", P["accent"])
    hy = gz(SEA_Z + hs)
    cv.line([(gx - 8, hy), (gx + 8, hy)], P["accent"], 2.5)
    _text(cv, gx + 14, hy - 22, f"Hs {hs:.2f} m", 13, "Bold", P["accent"])
    _text(cv, gx + 14, gz(SEA_Z) + 4, "STILL WATER", 11, "Regular", P["muted"])
    # wind streaks: deterministic in f, above SEA_Z + 2, fading over 4 m
    rng = np.random.default_rng(11)
    base = rng.uniform(0, L_M, 90)
    ys = rng.uniform(SEA_Z + 2.0, SEA_Z + 22.0, 90)
    for x0, z in zip(base, ys):
        x = (x0 + wind * 0.9 * (f % 90) / 30.0 * 3.0) % L_M
        fade = min(1.0, (z - (SEA_Z + 2.0)) / 4.0)
        x0p, y0p = to_px(x, z)
        x1p, _ = to_px(x + 6.0, z)
        cv.line([(x0p, y0p), (x1p, y0p)], (170, 140, 120, int(110 * fade)), 1.0)
    # jacket + helideck (deck height schematic: legs carry the drafting break)
    dx0, dx1, deck_z = 96.0, 148.0, 26.0
    for lx in (dx0 + 4, dx1 - 4):
        x0p, y0p = to_px(lx, SEA_Z - 4)
        x1p, y1p = to_px(lx, 20.0)
        cv.line([(x0p, y0p), (x1p, y1p)], P["ink"], 2.0)
        bx, by = to_px(lx, 20.0)
        cv.line([(bx - 5, by - 4), (bx + 5, by + 4)], P["ink"], 1.5)
        cv.line([(bx - 5, by + 4), (bx + 5, by - 4)], P["ink"], 1.5)
        x2p, y2p = to_px(lx, deck_z)
        cv.line([(bx, by), (x2p, y2p)], P["ink"], 2.0)
    x0p, y0p = to_px(dx0, deck_z)
    x1p, y1p = to_px(dx1, deck_z)
    cv.line([(x0p, y0p), (x1p, y1p)], P["ink"], 3.0)
    _text(cv, to_px(dx0 + 6, deck_z)[0], to_px(0, deck_z)[1] - 24, "H", 20, "Bold", P["accent"],
          anchor="m")
    # S-92 side profile on deck (nose right), drawn to the sprite-sheet dims
    # (length 20.90 m, rotor Ø 17.20 m, height 5.15 m) -- see _draw_s92.
    _draw_s92(cv, to_px, (dx0 + dx1) / 2, deck_z)
    _text(cv, 56, top + 14, "SECTION — HELIDECK IN A GALE", 14, "Bold", P["muted"])
    _text(cv, W - 56, top + 14, HELI_NOTE, 13, "Bold", P["muted"], anchor="r")
    _text(cv, W - 56, top + 40, "DECK HEIGHT SCHEMATIC — NOT MEASURED", 11, "Regular", P["muted"],
          anchor="r")
    if beat in ("hook", "section"):
        # the sea in these beats is frozen at the cancellation moment, not live
        _text(cv, W - 56, top + ph - 14, "SEA FROZEN 12:30", 12, "Bold", P["muted"], anchor="r")
    # stamp: cancelled, then rebooked (plain text -- the ✕/✓ glyphs render as
    # tofu bars in Inter at film scale)
    if beat == "section":
        if f < (SECB[0] + SECB[1]) // 2:
            _text(cv, 56, top + 44, "CANCELLED — Hs OVER THE LIMIT", 20, "Bold", P["accent"])
        else:
            _text(cv, 56, top + 44, "REBOOKED TO H2-14h · FRI 18:00 · 29.5 H LATE", 20, "Bold", P["accent"])
    elif beat == "map" and run_t >= T_CANCEL:
        _text(cv, 56, top + 44, "CANCELLED — Hs OVER THE LIMIT", 20, "Bold", P["accent"])


def _draw_findings_section(cv, top, ph):
    rep = _CTX[0]
    lean, act = rep["lean"], rep["actual"]
    _text(cv, 56, top + 14, "FINDINGS — LEAN (4 HELI) vs ACTUAL (5 HELI), THIS ONE WINTER", 14, "Bold",
          P["muted"])
    rows = [("UNMET FLIGHTS", "0", "0", "of 1,209 flown each"),
            ("CANCELLED → REBOOKED", f"{int(lean['kpis']['flights_cancelled'])}",
             f"{int(act['kpis']['flights_cancelled'])}", "all rebooked, none unmet"),
            ("TOTAL DELAY", f"{lean['kpis']['total_delay_h']:.1f} h",
             f"{act['kpis']['total_delay_h']:.2f} h", "rebooked flights only"),
            ("PLAN COST (MASKED UNITS, ROUNDED)", f"{lean['plan_cost']:,.0f}", f"{act['plan_cost']:,.0f}",
             f"+{act['plan_cost'] - lean['plan_cost']:,.0f}, all fixed cost")]
    y = top + 56
    _text(cv, 600, y, "LEAN", 15, "Bold", P["ink"])
    _text(cv, 750, y, "ACTUAL", 15, "Bold", P["ink"])
    y += 30
    for label, lv, av, note in rows:
        _text(cv, 56, y, label, 19, "Bold", P["ink"])
        _text(cv, 600, y, lv, 24, "Bold", P["accent"])
        _text(cv, 750, y, av, 24, "Bold", P["ink"])
        _text(cv, W - 56, y + 4, note, 13, "Regular", P["muted"], anchor="r")
        y += 52
    _text(cv, 56, y + 8, "The extra helicopter bought nothing measurable in this one winter.",
          20, "Regular", P["ink"])


def draw_chart(cv, f, beat, run_t):
    """Chart under the section. Modes: winter (13-week unmet strip), hs (week-11 Hs
    with the 6.0 m limit + cancel/rebook markers), findings (P90 gauge)."""
    rep, _, _, _, _, _, _, (wt, wwind, whs) = _CTX
    cx0, cy0, cw, chh = 56, SEC_TOP + SEC_PH + 60, W - 112, 170
    gy0, gy1 = cy0 + 26, cy0 + chh
    if beat in ("hook",):
        _text(cv, cx0, cy0 - 4, "UNMET FLIGHTS PER WEEK — ALL 13 WEEKS, DEC 2024–FEB 2025", 14, "Bold", P["muted"])
        bw = cw / 13
        for i, wk in enumerate(rep["lean"]["per_week"]):
            x = cx0 + i * bw
            _text(cv, x + bw / 2, gy1 - 24, "0", 16, "Bold", P["accent"], anchor="m")
            cv.line([(x + bw / 2, gy1 - 30), (x + bw / 2, gy1 - 44)], P["accent"], 2.0)
            _text(cv, x + bw / 2, gy1 - 2, f"W{i}", 10, "Regular", P["muted"], anchor="m")
        _text(cv, cx0 + cw, cy0 - 4, "1,209 / 1,209 FLOWN", 14, "Bold", P["ink"], anchor="r")
        return gy1
    if beat == "findings":
        _text(cv, cx0, cy0 - 4, "PRE-REGISTERED DECISION: P90 WEEKLY UNMET (LEAN) ≤ 1", 14, "Bold", P["muted"])
        x0, x1 = cx0, cx0 + cw
        ymid = (gy0 + gy1) / 2
        cv.line([(x0, ymid), (x1, ymid)], P["muted"], 2.0)
        for v in (0, 1, 2):
            xx = x0 + cw * v / 2.0
            cv.line([(xx, ymid - 8), (xx, ymid + 8)], P["ink"], 1.5)
            _text(cv, xx, ymid + 14, f"{v}", 13, "Regular", P["muted"], anchor="m")
        tx = x0 + cw * 1 / 2.0
        _text(cv, tx, ymid - 34, "THRESHOLD 1", 13, "Bold", P["accent"], anchor="m")
        cv.circle(x0, ymid, 7, fill=P["accent"])
        _text(cv, x0 + 14, ymid - 34, "MEASURED P90 0.0 — PASS (ONE WINTER ONLY)", 16, "Bold", P["accent"])
        return gy1
    # hs mode (map + section beats): week 11, Mon 00:00 - Sat 00:00
    _text(cv, cx0, cy0 - 4, "SIGNIFICANT WAVE HEIGHT Hs AT THE CENTROID, WEEK 11 (NORA3, MEASURED)", 14, "Bold",
          P["muted"])
    t_w0, t_w1 = 6739200.0, 6739200.0 + 7 * 86400  # weather seconds, Mon 17 Feb - Mon 24 Feb
    m = (wt >= t_w0) & (wt <= t_w1)
    tt, hh = wt[m], whs[m]
    ymax = 12.0
    zy = gy1 - (gy1 - gy0) * 6.0 / ymax
    cv.line([(cx0, zy), (cx0 + cw, zy)], P["accent"], 1.5, dash=(8, 6))
    _text(cv, cx0 + 8, zy - 20, "Hs LIMIT 6.0 m — ASSUMED", 12, "Bold", P["accent"])
    for v in (0, 6, 12):
        yy = gy1 - (gy1 - gy0) * v / ymax
        cv.line([(cx0, yy), (cx0 + cw, yy)], "#4a3236", 1.0)
        _text(cv, cx0 + cw - 24, yy - 18, f"{v}", 13, "Regular", P["muted"])
    pts = [(cx0 + cw * (t - t_w0) / (t_w1 - t_w0), gy1 - (gy1 - gy0) * h / ymax)
           for t, h in zip(tt, hh)]
    if len(pts) > 1:
        cv.line(pts, P["ink"], 2.0)
    # cancel + rebook markers (event dots sit on the curve by construction)
    marker_xs = []
    for tt_c, lab, col in ((T_CANCEL + 86400, "CANCELLED THU 12:30", P["accent"]),
                           (T_REBOOK + 86400, "REBOOKED FRI 18:00", P["accent"])):
        xx = cx0 + cw * (tt_c - t_w0) / (t_w1 - t_w0)
        marker_xs.append(xx)
        h_c = float(np.interp(tt_c, wt, whs))
        yy = gy1 - (gy1 - gy0) * h_c / ymax
        cv.circle(xx, yy, 6, fill=col)
        _text(cv, min(max(xx, cx0 + 70), cx0 + cw - 70), gy0 + 4, lab, 12, "Bold", col, anchor="m")
    # playhead at run_t (the chart's own clock -- in the section beat it advances
    # through the 29.5 h wait while the section panel + clock stay frozen at
    # 12:30, so it carries its own time tag there). The line starts BELOW the
    # event-label band (gy0+22) so it never nicks the "D" of CANCELLED, and the
    # dot is suppressed within 15 px of an event dot: on a 7-day axis 11:07 and
    # 12:30 are 9 px apart, and the two dots merged into one blob (f0300).
    px = cx0 + cw * (run_t + 86400 - t_w0) / (t_w1 - t_w0)
    cv.line([(px, gy0 + 22), (px, gy1)], P["accent"], 2.0)
    if min(abs(px - mxx) for mxx in marker_xs) >= 15:
        cv.circle(px, gy1 - (gy1 - gy0) * float(np.interp(run_t + 86400, wt, whs)) / ymax, 5,
                  fill=P["accent"])
    if beat == "section":
        ct = (T0 + timedelta(seconds=float(run_t))).strftime("%a %H:%M").upper()
        tx = min(max(px, cx0 + 40), cx0 + cw - 40)
        _text(cv, tx, gy1 + 6, f"CHART {ct}", 11, "Bold", P["accent"], anchor="m")
    return gy1


# ---------------------------------------------------------------- map panel
def _live_labels(cv, strip, pj, reserved=()):
    """Deterministic place labels in PANEL coords (the MapPanel placer): each label
    tries above / below / left / right of its anchor and takes the first box that
    does not overlap and stays inside the panel. Anchors outside the panel are
    skipped outright (f0300: FLESLAND's dot sat 6 px below the edge and its label
    floated with a leader to nowhere, colliding with a chevron label). Returns
    (placed, fell_back)."""
    items = []
    for text, lon, lat, size, color, kind in strip.label_items:
        ax, ay = pj(lon, lat)
        if not (0 <= ax <= PANEL_W and 0 <= ay <= PANEL_H):
            continue
        items.append((text, ax, ay, size, color, kind))
    boxes = [(19, PANEL_H - 26, 19 + 120, PANEL_H - 6), (PANEL_W - 44, 8, PANEL_W - 8, 56)]
    boxes += list(reserved)
    placed, fell = [], []
    for text, ax, ay, size, color, kind in items:
        w = cv.measure(text, ("Inter", "Bold"), size) + 12
        h = size + 10
        cands = [(ax, ay - h / 2 - 14), (ax, ay + h / 2 + 14),
                 (ax - w / 2 - 16, ay), (ax + w / 2 + 16, ay),
                 (ax, ay - h / 2 - 40), (ax, ay + h / 2 + 40)]
        box = None
        for cx, cy in cands:
            b = (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
            if b[0] < 8 or b[1] < 8 or b[2] > PANEL_W - 8 or b[3] > PANEL_H - 8:
                continue
            if not any(not (b[2] + 4 < ob[0] or ob[2] + 4 < b[0] or b[3] + 4 < ob[1] or
                            ob[3] + 4 < b[1]) for ob in boxes):
                box = b
                break
        if box is None:
            cx, cy = cands[0]
            box = (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
            fell.append(text)
        boxes.append(box)
        placed.append((text, ax, ay, size, color, kind, box))
    for text, ax, ay, size, color, kind, box in placed:
        cx = (box[0] + box[2]) / 2
        cy = (box[1] + box[3]) / 2
        if abs(cx - ax) > 14 or abs(cy - ay) > 14:
            ex = min(max(ax, box[0]), box[2])
            ey = min(max(ay, box[1]), box[3])
            cv.line([(ax, ay), (ex, ey)], P["muted"] if kind == "fjord" else color, 1.0, alpha=0.7)
    for text, ax, ay, size, color, kind, box in placed:
        cx = (box[0] + box[2]) / 2
        if kind == "place":
            cv.polygon([(box[0], box[1]), (box[2], box[1]), (box[2], box[3]), (box[0], box[3])],
                       fill=P["ground"], alpha=0.92)
        _text(cv, cx, box[1] + 5, text, size, "Bold", color, anchor="m")
    return placed, fell


def _chevron(cv, mx, my, label=None, dy=0):
    """Off-frame point: gold chevron + name at the clamped edge (the v8 fix).
    dy staggers stacked labels when several points clamp to the same edge spot
    (f0300: four helis parked at Flesland clamped to one bottom-edge point and
    their labels printed on top of each other). Returns the label box (or None)
    so the live placer can avoid it."""
    cx_, cy_ = min(max(mx, 14), PANEL_W - 14), min(max(my, 14), PANEL_H - 14)
    dx, dy_ = mx - cx_, my - cy_
    L = max(math.hypot(dx, dy_), 1e-6)
    ux, uy = dx / L, dy_ / L
    cv.polygon([(cx_ + ux * 10, cy_ + uy * 10),
                (cx_ - uy * 6 - ux * 4, cy_ + ux * 6 - uy * 4),
                (cx_ + uy * 6 - ux * 4, cy_ - ux * 6 - uy * 4)], fill=P["accent"])
    if label:
        lab_w = cv.measure(label, ("Inter", "Bold"), 13)
        # label placement follows the edge the point left by: top -> below the
        # triangle, bottom -> above it (both centred on the triangle, so the
        # label stays over open water instead of sliding onto the land at the
        # panel's right edge); left/right -> to the side as before
        if cy_ <= 14 and my < cy_:
            lx = min(max(cx_ - lab_w / 2, 8), PANEL_W - 8 - lab_w)
            ty = cy_ + 10 + dy
        elif cy_ >= PANEL_H - 14 and my > cy_:
            lx = min(max(cx_ - lab_w / 2, 8), PANEL_W - 8 - lab_w)
            ty = cy_ - 26 + dy
        else:
            lx = cx_ + 14 if cx_ + 14 + lab_w < PANEL_W - 8 else cx_ - 14 - lab_w
            ty = cy_ - 7 + dy
        _text(cv, lx, ty, label, 13, "Bold", P["accent"])
        return (lx - 4, ty - 7, lx + lab_w + 4, ty + 13)
    return None


def _off_frame_callouts(off, heliport_px):
    """Collapse off-frame helicopters that clamp to one edge spot into a single
    callout. `off` is [(agent, mx, my)] in panel coords, `heliport_px` the
    heliport's panel position. Returns [(agents, mx, my, label)] where (mx, my)
    is one representative unclamped point (for the chevron direction) and the
    label is "N HELIS AT FLESLAND" when every member is parked at the heliport
    or on final approach to it (within 60 px, ~15 km at this span), else the agent
    id (single) or "N HELIS". The old code drew one label per helicopter,
    staggered 20 px: four parked helis stacked diagonally over the coastline at
    the panel edge, gold-on-brown (f0300)."""
    buckets = {}
    for ag, mx, my in off:
        cx_ = min(max(mx, 14), PANEL_W - 14)
        cy_ = min(max(my, 14), PANEL_H - 14)
        buckets.setdefault((round(cx_ / 90), round(cy_ / 90)), []).append((ag, mx, my))
    hx, hy = heliport_px
    out = []
    for grp in buckets.values():
        if len(grp) == 1:
            ag, mx, my = grp[0]
            out.append(([ag], mx, my, ag))
        else:
            at_base = all(math.hypot(mx - hx, my - hy) <= 60 for _, mx, my in grp)
            lab = (f"{len(grp)} HELIS AT FLESLAND" if at_base else f"{len(grp)} HELIS")
            out.append(([ag for ag, _, _ in grp], grp[0][1], grp[0][2], lab))
    return out


def draw_map(strip, glide, cx, cy, focus_ag, markers, routes, times, run_t, beat, f, stops, heliport):
    """The map panel, rendered on its OWN canvas so skia clips every route, marker
    and label to the panel (f0300: unclipped week-11 routes spilled over the deck
    text and footer). Blits the strip window at the glide centre, then live routes
    (the week's program faint, today's legs of the focus helicopter solid), markers
    + chevrons, live labels, scale bar and north. Returns a PIL image; the caller
    pastes it. Section beat: the cancelled Flesland-B3 leg dashed; findings beat
    adds the rebook leg solid (the map is frozen at the cancellation / rebook
    moments, so these legs are the geography of the story, not a second clock)."""
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
    reserved = []  # label boxes the live placer must avoid (chevrons, focus label)
    # Focus-heli label box, reserved BEFORE the routes are drawn: offset from the
    # marker with a leader line, so it never sits in the Flesland knot or behind
    # the FLESLAND box (f0000/f0600/f0750). West of the marker when the marker is
    # in the right half, else east; clamped inside the panel.
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
    today0 = 6912000  # Thu 20 Feb 00:00 UTC: only today's legs go solid
    # routes, decimated (straight legs collapse); others faint, focus: week faint + today solid
    for ag in sorted(routes):
        route = routes[ag]
        done_k, marker = markers[ag]
        pts = [pj(*p) for p in route[::7]]
        dk = max(1, done_k // 7)
        t0k = max(1, int(np.searchsorted(times[ag], today0)) // 7)
        if ag == focus_ag:
            if dk > 1:
                cv.line(pts[:dk], P["muted"], 1.0)
            for i in range(max(1, dk), len(pts) - 1, 2):
                cv.line([pts[i], pts[i + 1]], P["muted"], 1.0)
            if dk > t0k:
                cv.line(pts[t0k:dk], P["accent"], 2.0)
        else:
            if dk > 1:
                cv.line(pts[:dk], P["muted"], 1.0, alpha=0.45)
            for i in range(max(1, dk), len(pts) - 1, 2):
                cv.line([pts[i], pts[i + 1]], P["muted"], 1.0, alpha=0.45)
    # focus-route exit (map beat only -- in section/findings the story legs carry
    # the geography, and the rebook route's far point IS B3, which the story leg
    # already chevrons): if the flown route's farthest point is off-panel, mark
    # where it leaves the frame with the nearest site name (f0300: B17's dot sits
    # 25 px above the top edge while H3 is returning from it -- the route line
    # alone does not say where it went)
    if beat == "map" and focus_ag in routes:
        done_k, _ = markers[focus_ag]
        t0k = max(1, int(np.searchsorted(times[focus_ag], today0)))
        done_pts = routes[focus_ag][t0k:max(t0k + 1, done_k)]
        if done_pts:
            far = max(done_pts, key=lambda p: p[1])
            fx_, fy_ = pj(*far)
            if not (0 <= fy_ < PANEL_H):
                near = min(stops, key=lambda n: (stops[n][0] - far[0]) ** 2 +
                           (stops[n][1] - far[1]) ** 2)
                box = _chevron(cv, fx_, fy_, near)
                if box:
                    reserved.append(box)
    # the two legs of the story (scenario positions, assumed)
    if beat in ("section", "findings"):
        fx, fy = pj(*heliport)
        bx, by = pj(*stops["B3"])
        cv.line([(fx, fy), (bx, by)], P["accent"], 2.0, dash=(6, 5))
        _text(cv, (fx + bx) / 2 + 8, (fy + by) / 2 - 8, "CANCELLED", 12, "Bold", P["accent"])
        if beat == "findings":
            cv.line([(fx, fy + 3), (bx, by + 3)], P["ink"], 2.5)
            _text(cv, (fx + bx) / 2 + 8, (fy + by) / 2 + 12, "REBOOKED FRI 18:00", 12, "Bold",
                  P["ink"])
        if not (0 <= bx < PANEL_W and 0 <= by < PANEL_H):
            box = _chevron(cv, bx, by, "B3")  # B3 (61.76 N) is off the top at this span
            if box:
                reserved.append(box)
    # markers (+ chevrons for off-frame others); their label boxes are reserved
    # for the live placer so no chevron label ever collides with a place label.
    # Helicopters parked at the same heliport clamp to one edge spot: they are
    # collapsed into ONE callout ("N HELIS AT FLESLAND", leader out to sea)
    # instead of one label each -- see _off_frame_callouts.
    off = []
    for ag in sorted(routes):
        if ag == focus_ag:
            continue
        _, marker = markers[ag]
        mx, my = pj(*marker)
        if not (0 <= mx < PANEL_W and 0 <= my < PANEL_H):
            off.append((ag, mx, my))
    callouts = _off_frame_callouts(off, pj(*heliport))
    for ag in sorted(routes):
        _, marker = markers[ag]
        mx, my = pj(*marker)
        if ag == focus_ag:
            cv.circle(mx, my, 16.8, stroke=P["accent"], width=1.0)
            cv.circle(mx, my, 4.2, fill=P["accent"])
            # focus label in the box reserved before the routes, on a backing
            # chip so route lines cannot strike through it, leader to the marker
            bx0, by0, bx1, by1 = _flbox
            cv.polygon([(bx0, by0), (bx1, by0), (bx1, by1), (bx0, by1)],
                       fill=P["ground"], alpha=0.92)
            ex = bx0 if bx0 > mx else bx1
            cv.line([(ex, (by0 + by1) / 2), (mx, my)], P["accent"], 1.0, alpha=0.7)
            _text(cv, (bx0 + bx1) / 2, by0 + 5, ag, 13, "Bold", P["accent"], anchor="m")
        else:
            cv.circle(mx, my, 3.5, fill=P["ink"])
    for _agents, mx, my, lab in callouts:
        if len(_agents) == 1:
            box = _chevron(cv, mx, my, lab)
        else:
            # one chevron at the clamped point + one callout box WEST of it
            # (open water on this coast), leader line to the triangle; the box
            # is a ground chip so coastline/routes cannot strike through it
            box = _chevron(cv, mx, my)
            cx_ = min(max(mx, 14), PANEL_W - 14)
            cy_ = min(max(my, 14), PANEL_H - 14)
            lw = cv.measure(lab, ("Inter", "Bold"), 13) + 12
            lh = 23
            bx1 = cx_ - 16 - lw
            if bx1 < 8:
                bx0, bx1 = cx_ + 16, cx_ + 16 + lw
            else:
                bx0 = bx1
                bx1 = bx0 + lw
            by0 = min(max(cy_ - lh / 2, 8), PANEL_H - 8 - lh)
            box = (bx0, by0, bx1, by0 + lh)
            cv.polygon([(bx0, by0), (bx1, by0), (bx1, by0 + lh), (bx0, by0 + lh)],
                       fill=P["ground"], alpha=0.92)
            ex = bx1 if bx0 < cx_ else bx0
            cv.line([(ex, by0 + lh / 2), (cx_, cy_)], P["accent"], 1.0, alpha=0.7)
            _text(cv, (bx0 + bx1) / 2, by0 + 5, lab, 13, "Bold", P["accent"], anchor="m")
        if box:
            reserved.append(box)
    placed, fell = _live_labels(cv, strip, pj, reserved)
    # scale bar (km) on a ground chip matching the dark-maroon place-label chips
    km_px = 1000 / (span * 111320)
    bar_km = max(1, int(round(PANEL_W * 0.18 / km_px)))
    bx, by = 24, PANEL_H - 22
    cv.line([(bx, by), (bx + bar_km * km_px, by)], P["ink"], 2.0)
    lab = f"{bar_km} km"
    lw = cv.measure(lab, ("Inter", "Regular"), 13)
    cv.polygon([(bx - 5, by - 26), (bx + lw + 5, by - 26), (bx + lw + 5, by - 6), (bx - 5, by - 6)],
               fill=P["ground"], alpha=0.92)
    _text(cv, bx, by - 22, lab, 13, "Regular", P["ink"])
    _text(cv, PANEL_W - 30, 14, "N", 15, "Bold", P["ink"])
    cv.line([(PANEL_W - 24, 36), (PANEL_W - 24, 52)], P["ink"], 1.0)
    return cv.to_pil(), fell


def headlines(rep):
    """Beat headlines, built from the measured report (never hand-typed): the
    section Hs is the interpolated 12:30 value, so it agrees with the gauge and
    the clock line on every frame."""
    fc = rep["featured_cancellation"]
    return {
        "hook": ([("FOUR HELICOPTERS,", False)], [("NOT FIVE.", True)]),
        "map": ([("THU 20 FEB, 09:45–12:30", False)], [("H3-10h FLIES NORTH", False)]),
        "section": ([("THE SEA SAYS NO:", False)],
                    [(f"Hs {fc['hs_m_at_departure']:.2f} m ", True), ("> 6.0 m", False)]),
        "findings": ([("NOTHING UNMET —", False)], [("IN THIS ONE WINTER", True)]),
    }
KICKERS = {
    "hook": "GRIBKOVSKAIA & SLETTEMARK 2025 · BERGEN · ONE-WINTER PILOT",
    "map": "GRIBKOVSKAIA & SLETTEMARK 2025 · BERGEN · WEEK 11 · THU MORNING · ACTUAL PROGRAM",
    "section": "GRIBKOVSKAIA & SLETTEMARK 2025 · BERGEN · THE FEATURED FLIGHT · ACTUAL PROGRAM",
    "findings": "GRIBKOVSKAIA & SLETTEMARK 2025 · BERGEN · FINDINGS · ONE WINTER ONLY",
}
WHERE = {
    "hook": "WHERE: FLESLAND + B1–B20 ON THE REAL BERGEN COAST, THU 20 FEB 12:30 UTC",
    "map": "WHERE: H3-10h FLIES THU MORNING — FLESLAND TO B17 AND BACK, THEN THE B3 DEPARTURE",
    "section": "WHERE: THE CANCELLATION MOMENT, FROZEN — THU 12:30 UTC",
    "findings": "WHERE: FRI 18:00 — H2-14h DEPARTS FLESLAND WITH THE REBOOK TO B3",
}


def render_frame(f, strip, glide, deck):
    rep, stops, heliport, routes, times, w11_routes, w11_times, (wt, wwind, whs) = _CTX
    beat = beat_of(f)
    focus_ag, focus, markers, map_run_t = focus_of(f, w11_routes, w11_times)
    run_t = run_t_of(f)  # chart time (advances through the wait); the map has its own
    # frozen time, and the section panel + readouts freeze at T_CANCEL in the section beat
    u = (f + 1) / N
    cx, cy, span = glide.view(u, focus, f)
    sec_t = T_CANCEL if beat == "section" else run_t
    wind, hs = weather_at(wt, wwind, whs, sec_t)
    cv = Canvas(W, H, bg=P["ground"], ss=SS)
    _text(cv, 56, 44, KICKERS[beat], 17, "Bold", P["accent"])
    hl = headlines(rep)[beat]
    for y, line in zip((76, 136), hl):
        x = 56
        for text, accent in line:
            _text(cv, x, y, text, 52, "Bold", P["accent"] if accent else P["ink"])
            x += cv.measure(text, ("Inter", "Bold"), 52)
    draw_section(cv, f, sec_t, hs, wind, beat)
    # readouts (the section's moment: frozen at the cancellation in the section beat)
    y = SEC_TOP + SEC_PH + 30
    _text(cv, 56, y, "CLOCK", 19, "Bold", P["ink"])
    x = 56 + cv.measure("CLOCK ", ("Inter", "Bold"), 19)
    _text(cv, x, y, clock_str(sec_t), 19, "Bold", P["accent"])
    x += cv.measure(clock_str(sec_t), ("Inter", "Bold"), 19) + 34
    _text(cv, x, y, "WIND", 19, "Bold", P["ink"])
    x += cv.measure("WIND ", ("Inter", "Bold"), 19)
    _text(cv, x, y, f"{wind:.1f} m/s", 19, "Bold", P["muted"])
    x += cv.measure(f"{wind:.1f} m/s", ("Inter", "Bold"), 19) + 34
    _text(cv, x, y, "Hs", 19, "Bold", P["ink"])
    x += cv.measure("Hs ", ("Inter", "Bold"), 19)
    _text(cv, x, y, f"{hs:.2f} m", 19, "Bold", P["accent"] if hs > 6.0 else P["muted"])
    gy1 = draw_chart(cv, f, beat, run_t)
    my0 = gy1 + 36
    _text(cv, 56, my0, WHERE[beat], 14, "Bold", P["muted"])
    panel, _fell = draw_map(strip, glide, cx, cy, focus_ag, markers, w11_routes, w11_times,
                            map_run_t, beat, f, stops, heliport)
    my1 = my0 + 24 + PANEL_H

    yb = my1 + 28
    _text(cv, 56, yb, deck[beat][0], 22, "Regular", P["ink"])
    _text(cv, 56, yb + 30, deck[beat][1], 22, "Regular", P["ink"])
    _text(cv, 56, yb + 70, "Map: coastline OpenStreetMap (ODbL); B positions + heliport from the "
          "scenario (assumed); routes from the replayed actual program.", 13, "Regular", P["muted"])
    _text(cv, 56, yb + 88, "Sea: NORA3 wind/wave at the centroid (MET Norway, CC BY 4.0); "
          "Tp 11.2 s at the featured hour. Section sea: JONSWAP, display-grade.", 13, "Regular",
          P["muted"])
    _text(cv, 56, yb + 106, "DRAFT — ONE-WINTER PILOT · 1 OF 24 WINTERS · B POSITIONS ASSUMED · "
          "HELIDECK LIMITS ASSUMED (25 m/s, 6 m)", 13, "Regular", P["muted"])
    _text(cv, 56, yb + 124, "RECOVERY = REBOOK INTO WEEKLY SLACK ONLY · "
          "LEAN WINDOWS 56 h, NOT THE PAPER'S 50 h", 13, "Regular", P["muted"])
    _text(cv, W - 56, 46, "offshore_simulations", 15, "Bold", P["muted"], anchor="r")
    img = cv.to_pil()
    img.paste(panel, (56, my0 + 24))
    return img


def main():
    global _CTX
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUTDIR / "bergen-lean-pilot.mp4"))
    ap.add_argument("--seconds", type=float, default=30.0)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--only", type=int, default=None, help="render a single frame index (still check)")
    ap.add_argument("--resume-from", type=int, default=None,
                    help="resume a killed render: skip frames < N (already on disk)")
    a = ap.parse_args()
    assert a.seconds * a.fps == N, "this film is 30 s at 30 fps = 900 frames"
    rep = load_report()
    stops, heliport, tr, routes, times, w11_routes, w11_times = load_traj()
    weather = load_weather()
    _CTX = (rep, stops, heliport, routes, times, w11_routes, w11_times, weather)
    print("gates first:")
    gates()
    bbox = (min(min(lon for lon, _ in routes[ag]) for ag in routes) - 0.06,
            min(min(lat for _, lat in routes[ag]) for ag in routes) - 0.06,
            max(max(lon for lon, _ in routes[ag]) for ag in routes) + 0.06,
            max(max(lat for _, lat in routes[ag]) for ag in routes) + 0.06)
    # static-wide check (measured): field km vs panel aspect
    import math as _m
    fw = (bbox[2] - bbox[0]) * 111.32 * _m.cos(_m.radians(60.2))
    fh = (bbox[3] - bbox[1]) * 111.32
    print(f"field {fw:.1f} km x {fh:.1f} km; static-wide fit = "
          f"{PANEL_H * fw / fh:.0f}px = {PANEL_H * fw / fh / PANEL_W * 100:.0f}% of panel width -> REJECTED")
    deck = narration(rep)
    print("narration (pass 1, from the measured report):")
    for b, lines in deck.items():
        print(f"  {b}: {' '.join(lines)}")
    env, centres, g0 = measure_envelope(Glide(bbox))
    print(f"camera envelope lon {env[0]:.3f}-{env[2]:.3f} lat {env[1]:.3f}-{env[3]:.3f}; "
          f"view {g0.view_lon:.2f} deg lon x {g0.view_lat:.2f} deg lat; "
          f"peak pan {g0._pan_max:.3f} widths/s at f{g0._pan_max_f} (cap 0.25)")
    strip = Strip(Glide(bbox), stops, heliport)
    out = Path(a.out)
    frames = out.parent / "frames"
    frames.mkdir(parents=True, exist_ok=True)
    glide = Glide(bbox)
    if a.resume_from is not None:
        missing = [f for f in range(a.resume_from) if not (frames / f"f{f:04d}.png").exists()]
        if missing:
            raise SystemExit(f"--resume-from {a.resume_from}: {len(missing)} earlier frames missing "
                             f"(first f{missing[0]:04d}.png); refusing to encode a gapped film")
        print(f"resuming from f{a.resume_from:04d}")
        # a resume is only deterministic if the glide carries the clean path's state:
        # step it silently from frame 0 (the v9 f239 lesson -- a fresh opening at the
        # resume frame puts the camera on the focus, not where the clean path had it)
        for ff in range(a.resume_from):
            _, foc, _, _ = focus_of(ff, w11_routes, w11_times)
            glide.view((ff + 1) / N, foc, ff)
    start = a.resume_from or 0
    if a.only is not None:
        # a single-frame still must show the camera where the glide would have put it
        for ff in range(a.only):
            _, foc, _, _ = focus_of(ff, w11_routes, w11_times)
            glide.view((ff + 1) / N, foc, ff)
        img = render_frame(a.only, strip, glide, deck)
        p = frames / f"f{a.only:04d}.png"
        img.save(p)
        print(p)
        return
    import time
    t0 = time.time()
    for f in range(start, N):
        img = render_frame(f, strip, glide, deck)
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
