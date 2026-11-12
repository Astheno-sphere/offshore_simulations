"""Molde Monday morning — the first film on live data.

A MAP film (no section physics: the Ghia 1982 cavity validation does NOT pass, so no
section number may be presented as validated). The Entur GTFS replay for Monday
2026-11-09 06:00-10:00 on the real Molde coast, real roads, real timetables.

    PYTHONPATH=. python tools/molde_film.py --out <molde-morning.mp4>   # 24 s, 720 frames
    PYTHONPATH=. python tools/molde_film.py --only 360                  # single-frame still check

Two-pass, as the repo's films: pass 1 measures (measure.json, already computed from the
gated replay report + trajectory), the deck sentences are chosen by narrate rules over
those measured values, pass 2 renders the same morning. Numbers on screen come from
measure.json / report.json, never typed by hand. Static camera throughout (Abhinav DNA):
one fixed view of the Molde bbox; only the content animates. The static base
(coastline, roads, buildings, GTFS shapes) is rendered once and blitted per frame.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import skia

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from offsim.cinema.draw import Canvas  # noqa: E402
from offsim.cinema.look import PALETTES, font_path  # noqa: E402
from offsim.motion import narrate  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
P = PALETTES["section-plan"]
W, H, SS = 1080, 1350, 2
FPS = 30
SECONDS = 24.0
NFRAMES = int(SECONDS * FPS)          # 720
WINDOW_S = 14400.0                    # 06:00-10:00

FILM_DIR = Path("/home/hatch/workspace/docs/linkedin/05-molde")
MEASURE = json.loads((FILM_DIR / "measure.json").read_text())
REPORT = json.loads((ROOT / "out/molde-gtfs-replay/report.json").read_text())
BBOX = REPORT["provenance"]["world_manifest"]["bbox"]  # lon_min, lat_min, lon_max, lat_max

KICKER = "MOLDE · MONDAY 06:00–10:00 · AS TIMETABLED"
HEADLINE = [[("HOW BUSY IS A MONDAY", False)], [("MORNING", True), (" IN MOLDE?", False)]]
HANDLE = "offshore_simulations"

DRAFT = ("DRAFT: ferry legs are NOT land-checked (no land polygon in the replay World); "
         "gate 4 not comparable — no reported KPIs.")
METHODS = ("Map: coastline, roads, buildings © OpenStreetMap (ODbL 1.0); "
           "timetable: Entur GTFS (NLOD 2.0); replay gates 0–3 passed.")

# --- narration rules (narrate.choose over measured values; first match wins) ---------------
DECK1_RULES = [
    {"when": "peak_vehicles >= 50",
     "text": "{trips} trips, {vehicle_km:,.0f} km in {makespan_h} hours — peak {peak_vehicles} vehicles at {peak_clock}."},
    {"text": "{trips} trips, {vehicle_km:,.0f} km in {makespan_h} hours."},
]
DECK2_RULES = [
    # the surprise: ferries are 1 in 5 trips but only 8% of the distance. The "23 sailings"
    # anchor lives on the map as the MOLDE–VESTNES ×23 label (beats 3-4), not in this line:
    # the full sentence does not fit 968 px at 22 pt (v6 deck-width lesson).
    {"when": "ferry_trips * 5 >= trips and ferry_km * 10 <= vehicle_km",
     "text": "But 1 in 5 trips is a ferry, and the sea carries only {ferry_share_pct:.0f}% of the distance."},
    {"text": "Ferries run {ferry_trips} of the {trips} trips."},
]


def narration_values():
    m, t = MEASURE["totals"], MEASURE
    return {
        "trips": m["trips"],
        "vehicle_km": m["vehicle_km"],
        "makespan_h": int(m["makespan_h"]),
        "peak_vehicles": m["peak_vehicles"],
        "peak_clock": t["peak"]["at_clock"],
        "ferry_trips": t["ferry"]["trips"],
        "ferry_km": t["ferry"]["vehicle_km"],
        "ferry_share_pct": round(100 * t["ferry"]["vehicle_km"] / m["vehicle_km"], 1),
        "ferry_1070_trips": next(r["trips"] for r in t["ferry_routes"] if r["route"] == "1070"),
    }


def deck_lines():
    v = narration_values()
    return [narrate.choose(DECK1_RULES, v), narrate.choose(DECK2_RULES, v)]


# --- text helpers (PIL-style top anchoring, as in section.py) --------------------------------
_ASCENT = {}


def _ascent(size, weight):
    key = (size, weight)
    if key not in _ASCENT:
        f = skia.Font(skia.Typeface.MakeFromFile(font_path(weight)), float(size))
        _ASCENT[key] = -f.getMetrics().fAscent
    return _ASCENT[key]


def _text(cv, x, top, s, size, weight="Regular", color="#ffffff", anchor="l"):
    cv.text(x, top + _ascent(size, weight), s, font=("Inter", weight), size=size,
            color=color, anchor=anchor)


def _skia_image_rgba(arr):
    a = arr[..., 3:4].astype(np.float32) / 255.0
    pm = np.concatenate([(arr[..., :3].astype(np.float32) * a + 0.5).astype(np.uint8),
                         arr[..., 3:4]], axis=-1)
    return skia.Image.fromarray(np.ascontiguousarray(pm),
                                colorType=skia.kRGBA_8888_ColorType,
                                alphaType=skia.kPremul_AlphaType)


# --- geometry --------------------------------------------------------------------------------
LAT0 = (BBOX[1] + BBOX[3]) / 2
KX = 111.32 * np.cos(np.radians(LAT0))   # km per degree lon
KY = 110.99                               # km per degree lat
MAP = {"x": 56, "y": 250, "w": 968, "h": 800}   # map panel, 1x coords
BW_KM = (BBOX[2] - BBOX[0]) * KX
BH_KM = (BBOX[3] - BBOX[1]) * KY


def _fit():
    s = min(MAP["w"] / BW_KM, MAP["h"] / BH_KM)   # px per km
    ox = MAP["x"] + (MAP["w"] - BW_KM * s) / 2
    oy = MAP["y"] + (MAP["h"] - BH_KM * s) / 2
    return s, ox, oy


SCALE, OX, OY = _fit()


def to_px(lon, lat):
    return (OX + (lon - BBOX[0]) * KX * SCALE, OY + (BBOX[3] - lat) * KY * SCALE)


def to_local(lon, lat):
    """Map-panel-local coords (the static base canvas is MAP-sized, not full-frame)."""
    x, y = to_px(lon, lat)
    return (x - MAP["x"], y - MAP["y"])


def load_geo():
    def gj(p):
        return json.loads(Path(p).read_text())["features"]
    land = gj(ROOT / "data/worlds/molde/land.geojson")
    roads = gj(ROOT / "data/worlds/molde/osm/roads.geojson")
    buildings = gj(ROOT / "data/worlds/molde/osm/buildings.geojson")
    quays = gj(ROOT / "data/worlds/molde/osm/quays.geojson")
    return land, roads, buildings, quays


def load_shapes():
    """GTFS shape polylines for the trips in the window, subsampled — the real network."""
    trips = pd.read_csv(ROOT / "data/worlds/molde/gtfs/trips.txt", low_memory=False)
    agents = pd.read_csv(ROOT / "out/molde-gtfs-replay/agents.csv")
    want = set(trips[trips.trip_id.isin(set(agents.trip_id))].shape_id.dropna())
    shapes = pd.read_csv(ROOT / "data/worlds/molde/gtfs/shapes.txt", low_memory=False)
    shapes = shapes[shapes.shape_id.isin(want)].sort_values(["shape_id", "shape_pt_sequence"])
    ferry_shapes, bus_shapes = [], []
    fids = set(trips[trips.route_id.str.contains("1050|1058|1059|1070|HUR")].shape_id.dropna())
    for sid, g in shapes.groupby("shape_id"):
        pts = [to_local(lon, lat) for lon, lat in
               zip(g.shape_pt_lon.values[::4], g.shape_pt_lat.values[::4])]
        (ferry_shapes if sid in fids else bus_shapes).append(pts)
    return bus_shapes, ferry_shapes


def build_base():
    """Static map base, rendered once at ss=2: sea, land, landuse tint, buildings, roads,
    GTFS shapes (bus faint, ferry accent), quays. Returns a skia image + the ferry label anchors."""
    land, roads, buildings, quays = load_geo()
    bus_shapes, ferry_shapes = load_shapes()
    cv = Canvas(MAP["w"], MAP["h"], bg=P["sea"], ss=SS)
    # land (MultiPolygon, may have several rings)
    for feat in land:
        for poly in feat["geometry"]["coordinates"]:
            for ring in poly:
                cv.polygon([to_local(lon, lat) for lon, lat in ring], fill=P["ground"])
    # coastline stroke: outer rings only
    for feat in land:
        for poly in feat["geometry"]["coordinates"]:
            cv.line([to_local(lon, lat) for lon, lat in poly[0]], P["streak_hi"], 1.5)
    # buildings: one path, tonal fill (Polygon or MultiPolygon — yield rings either way)
    def rings(geom):
        if geom["type"] == "Polygon":
            yield from geom["coordinates"]
        elif geom["type"] == "MultiPolygon":
            for poly in geom["coordinates"]:
                yield from poly

    path = skia.Path()
    for feat in buildings:
        for ring in rings(feat["geometry"]):
            pts = [to_local(lon, lat) for lon, lat in ring]
            if len(pts) < 3:
                continue
            path.moveTo(float(pts[0][0]), float(pts[0][1]))
            for x, y in pts[1:]:
                path.lineTo(float(x), float(y))
            path.close()
    paint = skia.Paint(AntiAlias=True, Color=skia.Color(0x46, 0x2B, 0x30, 255))
    paint.setStyle(skia.Paint.kFill_Style)
    cv.cv.drawPath(path, paint)
    # roads: one path, hairlines
    path = skia.Path()
    for feat in roads:
        pts = [to_local(lon, lat) for lon, lat in feat["geometry"]["coordinates"]]
        path.moveTo(float(pts[0][0]), float(pts[0][1]))
        for x, y in pts[1:]:
            path.lineTo(float(x), float(y))
    paint = skia.Paint(AntiAlias=True, Color=skia.Color(0x6B, 0x5A, 0x52, 200))
    paint.setStyle(skia.Paint.kStroke_Style)
    paint.setStrokeWidth(0.75)
    cv.cv.drawPath(path, paint)
    # GTFS shapes: bus faint, ferry accent
    for shapes, color, width, alpha in ((bus_shapes, "#9c8a80", 1.0, 0.45),
                                        (ferry_shapes, P["accent"], 1.5, 0.6)):
        path = skia.Path()
        for pts in shapes:
            if len(pts) < 2:
                continue
            path.moveTo(float(pts[0][0]), float(pts[0][1]))
            for x, y in pts[1:]:
                path.lineTo(float(x), float(y))
        r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
        paint = skia.Paint(AntiAlias=True, Color=skia.Color(r, g, b, int(255 * alpha)))
        paint.setStyle(skia.Paint.kStroke_Style)
        paint.setStrokeWidth(width)
        paint.setStrokeCap(skia.Paint.kRound_Cap)
        paint.setStrokeJoin(skia.Paint.kRound_Join)
        cv.cv.drawPath(path, paint)
    # quays: mixed geometry in the layer (86 LineString, 13 Polygon, 1 Point) — piers as
    # strokes, harbour areas as fills, the one point as a dot
    for feat in quays:
        g = feat["geometry"]
        if g["type"] == "Point":
            x, y = to_local(*g["coordinates"][:2])
            cv.circle(x, y, 1.6, fill=P["muted"], alpha=0.8)
        elif g["type"] == "LineString":
            pts = [to_local(lon, lat) for lon, lat in g["coordinates"]]
            if len(pts) >= 2:
                cv.line(pts, P["muted"], 1.2, alpha=0.8)
        elif g["type"] == "Polygon":
            for ring in rings(g):
                pts = [to_local(lon, lat) for lon, lat in ring]
                if len(pts) >= 3:
                    cv.polygon(pts, fill="#40262c")
    arr = np.asarray(cv.to_pil().convert("RGBA"))
    return _skia_image_rgba(arr)


def ferry_label_anchors(traj, agents):
    """Midpoint of each ferry line's sailed positions (measured, from the trajectory)."""
    out = {}
    names = {"1070": "MOLDE–VESTNES", "1058": "SOLHOLMEN–MORDALSVÅGEN",
             "1059": "AUKRA–HOLLINGSHOLMEN", "1050": "MOLDE–SEKKEN"}
    amap = agents.set_index("agent_id")
    for route, name in names.items():
        ids = [a for a in amap.index if str(amap.loc[a, "route_short_name"]) == route]
        sub = traj[traj.agent_id.isin(ids)]
        if len(sub) == 0:
            continue
        mid = sub.iloc[len(sub) // 2]
        out[route] = (name, to_px(mid.lon, mid.lat))
    return out


# --- per-frame state (precomputed once) ------------------------------------------------------
class Morning:
    def __init__(self):
        self.traj = pd.read_csv(ROOT / "out/molde-gtfs-replay/trajectory.csv")
        self.agents = pd.read_csv(ROOT / "out/molde-gtfs-replay/agents.csv")
        self.ids = list(self.agents.agent_id)
        self.cls = dict(zip(self.agents.agent_id, self.agents.cls))
        self.t_start = dict(zip(self.agents.agent_id, self.agents.t_start))
        self.state_at = {}   # agent -> (t array, state array)
        for aid, g in self.traj.groupby("agent_id"):
            self.state_at[aid] = (g.t.values, g.state.values)
        # positions at frame times: (nframes, nagents) lon/lat, NaN when inactive
        self.ft = np.linspace(0, WINDOW_S, NFRAMES)
        self.lon = np.full((NFRAMES, len(self.ids)), np.nan)
        self.lat = np.full((NFRAMES, len(self.ids)), np.nan)
        grouped = {aid: g for aid, g in self.traj.groupby("agent_id")}
        for j, aid in enumerate(self.ids):
            g = grouped.get(aid)
            if g is None:
                continue
            t = g.t.values
            self.lon[:, j] = np.interp(self.ft, t, g.lon.values, left=np.nan, right=np.nan)
            self.lat[:, j] = np.interp(self.ft, t, g.lat.values, left=np.nan, right=np.nan)
        self.in_bbox = (
            (self.lon >= BBOX[0]) & (self.lon <= BBOX[2])
            & (self.lat >= BBOX[1]) & (self.lat <= BBOX[3])
        )
        self.active = ~np.isnan(self.lon)
        # ferry sailing now (state == 'sail' at the last sample <= frame t)
        self.ferry_sailing = np.zeros(NFRAMES, dtype=int)
        for j, aid in enumerate(self.ids):
            if self.cls[aid] != "ferry":
                continue
            t, s = self.state_at[aid]
            idx = np.searchsorted(t, self.ft, side="right") - 1
            ok = (idx >= 0) & (s[np.clip(idx, 0, len(s) - 1)] == "sail") & self.active[:, j]
            self.ferry_sailing[ok] += 1

    def clock(self, f):
        s = self.ft[f]
        return f"{6 + int(s) // 3600:02d}:{int(s) % 3600 // 60:02d}"

    def on_road(self, f):
        return int((self.active[f] & self.in_bbox[f]).sum())

    def trips_so_far(self, f):
        return int(sum(1 for aid in self.ids if self.t_start[aid] <= self.ft[f]))


# --- frame render ----------------------------------------------------------------------------
CHART = {"x": 56, "y": 1108, "w": 968, "h": 118, "ymax": 70}


def render_frame(m, base_img, labels, deck, f):
    cv = Canvas(W, H, bg=P["ground"], ss=SS)
    # header
    _text(cv, 56, 44, KICKER, 17, "Bold", P["accent"])
    _text(cv, W - 56, 46, HANDLE, 15, "Bold", P["muted"], anchor="r")
    for y, line in zip((76, 136), HEADLINE):
        x = 56
        for text, accent in line:
            _text(cv, x, y, text, 52, "Bold", P["accent"] if accent else P["ink"])
            x += cv.measure(text, ("Inter", "Bold"), 52)
    # readouts: clock, on the road now, trips so far
    y = 212
    x = 56
    for lab, val, hot in (("CLOCK", m.clock(f), False),
                          ("ON THE ROAD NOW", str(m.on_road(f)), True),
                          ("TRIPS SO FAR", str(m.trips_so_far(f)), False),
                          ("FERRIES SAILING", str(int(m.ferry_sailing[f])), False)):
        _text(cv, x, y, lab, 15, "Bold", P["muted"])
        x += cv.measure(lab + " ", ("Inter", "Bold"), 15)
        _text(cv, x, y, val, 19, "Bold", P["accent"] if hot else P["ink"])
        x += cv.measure(val, ("Inter", "Bold"), 19) + 40
    # map base (blit at 1x coords; the surface is ss-scaled, as in section.py's heat raster)
    cv.cv.drawImage(base_img, float(MAP["x"]), float(MAP["y"]))
    # vehicles
    beat_ferry = 420 <= f < 570
    for j, aid in enumerate(m.ids):
        if not (m.active[f, j] and m.in_bbox[f, j]):
            continue
        x, y = to_px(m.lon[f, j], m.lat[f, j])
        if x < MAP["x"] or x > MAP["x"] + MAP["w"] or y < MAP["y"] or y > MAP["y"] + MAP["h"]:
            continue
        is_ferry = m.cls[aid] == "ferry"
        if beat_ferry and not is_ferry:
            cv.circle(x, y, 3.0, fill=P["ink"], alpha=0.30)
        elif is_ferry:
            if beat_ferry:
                cv.circle(x, y, 9, stroke=P["accent"], width=1.5, alpha=0.85)
            hx, hy = x, y
            cv.polygon([(hx, hy - 5), (hx + 5, hy), (hx, hy + 5), (hx - 5, hy)], fill=P["accent"])
        else:
            cv.circle(x, y, 3.5, fill=P["ink"], alpha=0.9)
    # ferry labels from the ferry beat through the answer (the ×23 anchor stays on screen
    # while the deck surprise lands in beat 4). Each label sits on a small ground chip
    # (whipster round 1: the bare labels were shredded by the route lines underneath).
    if f >= 420:
        for route, (name, (lx, ly)) in labels.items():
            n = next(r["trips"] for r in MEASURE["ferry_routes"] if r["route"] == route)
            s = f"{name} ×{n}"
            w = cv.measure(s, ("Inter", "Bold"), 14)
            cv.polygon([(lx - w / 2 - 6, ly - 4), (lx + w / 2 + 6, ly - 4),
                        (lx + w / 2 + 6, ly + 18), (lx - w / 2 - 6, ly + 18)],
                       fill=P["ground"], alpha=0.88)
            _text(cv, lx, ly, s, 14, "Bold", P["accent"], anchor="m")
    # scale bar + north arrow on the map (bar on a small ground chip so it never sits on the coast)
    bx, by = MAP["x"] + 16, MAP["y"] + MAP["h"] - 34
    bar_px = 5 * SCALE
    cv.polygon([(bx - 8, by - 10), (bx + bar_px + 8, by - 10), (bx + bar_px + 8, by + 16),
                (bx - 8, by + 16)], fill=P["ground"], alpha=0.85)
    cv.line([(bx, by), (bx + bar_px, by)], P["ink"], 2.0)
    _text(cv, bx + bar_px + 8, by - 8, "5 km", 13, "Regular", P["ink"])
    _text(cv, MAP["x"] + MAP["w"] - 16, MAP["y"] + 18, "N", 15, "Bold", P["muted"], anchor="r")
    cv.line([(MAP["x"] + MAP["w"] - 22, MAP["y"] + 36), (MAP["x"] + MAP["w"] - 22, MAP["y"] + 56)],
            P["muted"], 1.5)
    # chart: vehicles on the road, 06:00-10:00
    cx, cy, cw, chh = CHART["x"], CHART["y"], CHART["w"], CHART["h"]
    _text(cv, cx, cy - 4, "VEHICLES ON THE ROAD, MONDAY 06:00–10:00", 14, "Bold", P["muted"])
    gy0, gy1 = cy + 26, cy + chh
    for v in (0, 25, 50):
        yy = gy1 - (gy1 - gy0) * v / CHART["ymax"]
        cv.line([(cx, yy), (cx + cw, yy)], "#4a3236", 1.0)
        _text(cv, cx + cw - 24, yy - 16, f"{v}", 13, "Regular", P["muted"])
    series = MEASURE["active_series_30s"]["all"]
    pts = [(cx + cw * i / (len(series) - 1), gy1 - (gy1 - gy0) * v / CHART["ymax"])
           for i, v in enumerate(series)]
    cv.line(pts, P["accent"], 2.5)
    peak_i = int(np.argmax(series))
    px = cx + cw * peak_i / (len(series) - 1)
    py = gy1 - (gy1 - gy0) * series[peak_i] / CHART["ymax"]
    cv.circle(px, py, 4.5, fill=P["accent"])
    _text(cv, px, py - 26, f"PEAK {series[peak_i]} · {MEASURE['peak']['at_clock']}", 13, "Bold",
          P["accent"], anchor="m")
    now_x = cx + cw * f / (NFRAMES - 1)
    now_v = series[min(int(m.ft[f] / 30), len(series) - 1)]
    now_y = gy1 - (gy1 - gy0) * now_v / CHART["ymax"]
    cv.line([(now_x, gy0), (now_x, gy1)], P["muted"], 1.0, alpha=0.6)
    cv.circle(now_x, now_y, 4, fill=P["ink"])
    # deck (deck 1 from the start; the surprise lands in the final beat)
    yb = 1252
    _text(cv, 56, yb, deck[0], 22, "Regular", P["ink"])
    if f >= 570:
        _text(cv, 56, yb + 30, deck[1], 22, "Regular", P["ink"])
    # methods footer
    _text(cv, 56, 1308, METHODS, 13, "Regular", P["muted"])
    _text(cv, 56, 1326, DRAFT, 13, "Regular", P["muted"])
    return cv


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(FILM_DIR / "molde-morning.mp4"))
    ap.add_argument("--fps", type=int, default=FPS)
    ap.add_argument("--only", type=int, default=None, help="render a single frame index (still check)")
    a = ap.parse_args()
    out = Path(a.out)
    frames = out.parent / "frames"
    frames.mkdir(parents=True, exist_ok=True)
    # headline + deck fit assertions (v6 lesson: deck text must fit 968 px at its size)
    probe = Canvas(W, H, bg=P["ground"], ss=1)
    for line in HEADLINE:
        wsum = sum(probe.measure(t, ("Inter", "Bold"), 52) for t, _ in line)
        assert wsum <= 968, f"headline too wide: {wsum:.0f}px"
    deck = deck_lines()
    print("deck 1:", deck[0])
    print("deck 2:", deck[1])
    for d in deck:
        assert probe.measure(d, ("Inter", "Regular"), 22) <= 968, f"deck too wide: {d}"
    for s in (METHODS, DRAFT):
        assert probe.measure(s, ("Inter", "Regular"), 13) <= 968, f"footer too wide: {s}"
    m = Morning()
    base_img = build_base()
    labels = ferry_label_anchors(m.traj, m.agents)
    only = [a.only] if a.only is not None else range(NFRAMES)
    for f in only:
        cv = render_frame(m, base_img, labels, deck, f)
        cv.save(str(frames / f"f{f:04d}.png"))
        if a.only is not None:
            print(frames / f"f{f:04d}.png")
            return
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(a.fps), "-i",
                    str(frames / "f%04d.png"), "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "18", "-pix_fmt", "yuv420p", str(out)], check=True)
    print(out, f"{NFRAMES} frames")


if __name__ == "__main__":
    main()
