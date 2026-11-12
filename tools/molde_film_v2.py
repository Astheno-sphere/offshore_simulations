"""Molde Monday morning v2 — same film, richer map.

v1's verdict (the user): the map has no houses, no fine details, no major street
names, no lit places in gold/orange. v2 fixes exactly that, on the same measured
morning (289 trips, 5,963 km, peak 67 at 07:35; same question/answer/surprise,
re-measured in v2/measure.py — same values, plus the per-mode series the
two-colour chart needs). Same gates (re-run before any frame renders).

    PYTHONPATH=. python tools/molde_film_v2.py --out <molde-morning-v2.mp4>
    PYTHONPATH=. python tools/molde_film_v2.py --only 360

Changes vs v1 (all on the map):
1. HOUSES: buildings are filled footprints in a warm tone with an edge, not faint
   hairlines — the built fabric reads at film scale.
2. ROAD HIERARCHY + STREET NAMES: four road weights by OSM highway class, quays
   drawn light, and the major streets named from OSM name tags (E39, Fv 64,
   Storgata, Julsundvegen · Fv 662, Frænavegen · Fv 538).
3. LIT PLACES IN GOLD: six key places in gold with a halo — Molde sentrum
   (domkirke), trafikkterminal, ferjekai, lufthavn Årø, Furneset ferjekai,
   Sekken kai — each named. INTERPRETATION (flagged in the report): "lit" =
   the important places glowing gold, not street-light data.
4. FERRY VS FRAM, TWO COLOURS, NO LEGEND: ferry = gold (accent), FRAM bus =
   #4f8f9c (palette field_diverging[0]); the meaning is carried by direct
   labels — "FERRY · MOLDE–VESTNES ×23" on the routes, "FRAM 701" on the
   busiest bus route, and the chart's two lines named at their peaks.
5. CREDIT: "Film by Arshad Abbasia — Python · skia · pandas · OpenStreetMap ·
   Entur GTFS · ffmpeg" in the footer.
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

FILM_DIR = Path("/home/hatch/workspace/docs/linkedin/05-molde/v2")
MEASURE = json.loads((FILM_DIR / "measure.json").read_text())
REPORT = json.loads((ROOT / "out/molde-gtfs-replay/report.json").read_text())
BBOX = REPORT["provenance"]["world_manifest"]["bbox"]  # lon_min, lat_min, lon_max, lat_max

# two modes, two colours, no legend: ferry = gold accent, FRAM bus = palette teal-blue
FRAM = "#4f8f9c"   # PALETTES["section-plan"]["field_diverging"][0]
FERRY = P["accent"]  # gold #e5a028
CREDIT = ("Film by Arshad Abbasia — Python · skia · pandas · OpenStreetMap · "
          "Entur GTFS · ffmpeg")

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
    landuse = gj(ROOT / "data/worlds/molde/osm/landuse.geojson")
    return land, roads, buildings, quays, landuse


# --- v2 map content: street names and lit places, all from OSM / GTFS tags ------------------
# Street anchors are computed from the road data (midpoint of the longest matching way),
# never hand-placed coordinates. Lit-place anchors are verified OSM building / GTFS stop /
# OSM aerodrome coordinates (see V2-REPORT.md for the sources).
LIT_PLACES = [
    # (label, lon, lat, source)
    ("MOLDE SENTRUM", 7.1605, 62.7383, "OSM building Molde domkirke (centre anchor)"),
    ("MOLDE TRAFIKKTERMINAL", 7.1616, 62.7374, "GTFS stop NSR:Quay:100017"),
    ("MOLDE FERJEKAI", 7.1691, 62.7369, "GTFS stop NSR:Quay:69465"),
    ("MOLDE LUFTHAVN, ÅRØ", 7.2676, 62.7450, "OSM aerodrome Molde lufthavn ENML/MOL, centroid"),
    ("FURNESET FERJEKAI", 7.0851, 62.6511, "GTFS stop NSR:Quay:116010 (route 1070 Vestnes side)"),
    ("SEKKEN KAI", 7.3030, 62.6753, "GTFS stop NSR:Quay:65841 (route 1050)"),
]
STREET_LABELS = [
    # (label, ref, name) — the anchor is the longest matching OSM way's midpoint
    ("E39", "E 39", None),
    ("Fv 64", "64", None),
    ("Storgata", "537", "Storgata"),
    ("Julsundvegen · Fv 662", "662", "Julsundvegen"),
    ("Frænavegen · Fv 538", "538", "Frænavegen"),
]


def road_anchor(roads, ref=None, name=None):
    """Midpoint of the longest OSM way matching ref/name (measured, from the extract)."""
    best, best_n = None, -1
    for f in roads:
        p = f["properties"]
        if ref is not None and p.get("ref") != ref:
            continue
        if name is not None and p.get("name") != name:
            continue
        coords = f["geometry"]["coordinates"]
        if len(coords) > best_n:
            best, best_n = coords, len(coords)
    mid = best[len(best) // 2]
    return mid[0], mid[1]


def _rings(geom):
    if geom["type"] == "Polygon":
        yield from geom["coordinates"]
    elif geom["type"] == "MultiPolygon":
        for poly in geom["coordinates"]:
            yield from poly


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


def _paint_path(cv, pts_list, color, width, alpha=1.0, fill=False):
    """One skia path for many polylines/polygons (stroke or fill)."""
    path = skia.Path()
    for pts in pts_list:
        if len(pts) < (3 if fill else 2):
            continue
        path.moveTo(float(pts[0][0]), float(pts[0][1]))
        for x, y in pts[1:]:
            path.lineTo(float(x), float(y))
        if fill:
            path.close()
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    paint = skia.Paint(AntiAlias=True, Color=skia.Color(r, g, b, int(255 * alpha)))
    paint.setStyle(skia.Paint.kFill_Style if fill else skia.Paint.kStroke_Style)
    if not fill:
        paint.setStrokeWidth(width)
        paint.setStrokeCap(skia.Paint.kRound_Cap)
        paint.setStrokeJoin(skia.Paint.kRound_Join)
    cv.cv.drawPath(path, paint)


def _overlaps(box, boxes, margin=4):
    x0, y0, x1, y1 = box
    for bx0, by0, bx1, by1 in boxes:
        if not (x1 + margin < bx0 or bx1 + margin < x0 or y1 + margin < by0 or by1 + margin < y0):
            return True
    return False


def _chip_box(cv, text, cx, cy, size, weight="Bold"):
    w = cv.measure(text, ("Inter", weight), size) + 12
    h = size + 10
    return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


def place_labels(cv, items, occupied):
    """Deterministic label placement: each label tries above / below / left / right
    (then far above / far below) of its anchor and takes the first chip that does not
    overlap an already-placed box and stays inside the panel. Returns {text: box}
    plus a list of labels that fell back to an overlapping slot (reported, not hidden).
    Draws the chip, the leader from the anchor dot, and the text. `items` is a list of
    (text, ax, ay, size, color, kind) in priority order; kind 'place' gets a gold dot
    and halo, 'fram' a blue dot, 'street' no dot. Two passes: dots and leaders first,
    chips and text second — so a long leader never crosses another label's chip.
    Places clustered within 20 px of another place get a small dot and no halo, so
    the centre's three dots read as three places instead of one gold smear."""
    placed, fell_back = {}, []
    boxes = list(occupied)
    # pass 0: choose every chip first (placement is order-dependent, drawing is not)
    chosen = []
    for text, ax, ay, size, color, kind in items:
        w = cv.measure(text, ("Inter", "Bold"), size) + 12
        h = size + 10
        cands = [
            (ax, ay - h / 2 - 14), (ax, ay + h / 2 + 14),
            (ax - w / 2 - 16, ay), (ax + w / 2 + 16, ay),
            (ax, ay - h / 2 - 40), (ax, ay + h / 2 + 40),
            (ax, ay - h / 2 - 80), (ax, ay + h / 2 + 80),
        ]
        box = None
        for cx, cy in cands:
            b = (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
            if b[0] < 8 or b[1] < 8 or b[2] > MAP["w"] - 8 or b[3] > MAP["h"] - 8:
                continue
            if not _overlaps(b, boxes):
                box = b
                break
        if box is None:
            cx, cy = cands[0]
            box = (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
            fell_back.append(text)
        boxes.append(box)
        placed[text] = box
        chosen.append((text, ax, ay, size, color, kind, box))
    # pass 1: dots + leaders (under the chips)
    place_anchors = [(ax, ay) for _t, ax, ay, _s, _c, k in items if k == "place"]
    for text, ax, ay, size, color, kind, box in chosen:
        if kind == "place":
            crowded = any((ax - ox) ** 2 + (ay - oy) ** 2 < 20 ** 2
                          for ox, oy in place_anchors if (ox, oy) != (ax, ay))
            if not crowded:
                cv.circle(ax, ay, 10, fill=FERRY, alpha=0.22)
            cv.circle(ax, ay, 3.0 if crowded else 4, fill=FERRY)
        elif kind == "fram":
            cv.circle(ax, ay, 9, fill=FRAM, alpha=0.25)
            cv.circle(ax, ay, 3.5, fill=FRAM)
        cx = (box[0] + box[2]) / 2
        cy = (box[1] + box[3]) / 2
        if abs(cx - ax) > 14 or abs(cy - ay) > 14:
            ex = min(max(ax, box[0]), box[2])
            ey = min(max(ay, box[1]), box[3])
            cv.line([(ax, ay), (ex, ey)], FERRY if kind == "place" else
                    (FRAM if kind == "fram" else P["muted"]), 1.0, alpha=0.7)
    # pass 2: chips + text (on top of every leader)
    for text, ax, ay, size, color, kind, box in chosen:
        cx = (box[0] + box[2]) / 2
        cv.polygon([(box[0], box[1]), (box[2], box[1]), (box[2], box[3]), (box[0], box[3])],
                   fill=P["ground"], alpha=0.92)
        _text(cv, cx, box[1] + 5, text, size, "Bold", color, anchor="m")
    return placed, fell_back


def build_base(ferry_boxes, fram_anchor):
    """Static map base, rendered once at ss=2: sea, land, landuse tint, filled buildings,
    road hierarchy, two-colour GTFS shapes (FRAM blue / ferry gold), light quays, then
    the named map: street names, lit places in gold, the FRAM 701 route label.
    `ferry_boxes` are the per-frame ferry-label chips (reserved so static labels never
    sit under them). Returns the skia image + the placed-label boxes (for the report)."""
    land, roads, buildings, quays, landuse = load_geo()
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
    # landuse (industrial areas): a faint tint above the ground, below the buildings
    _paint_path(cv, [[to_local(lon, lat) for lon, lat in ring]
                     for feat in landuse for ring in _rings(feat["geometry"])],
                "#3d232a", 0, fill=True)
    # HOUSES: filled footprints in a warm tone with an edge — the built fabric reads,
    # where v1's #462b30 fill on #331c22 ground was invisible. The stroke fattens the
    # smallest footprints a touch so individual houses read at film scale.
    _paint_path(cv, [[to_local(lon, lat) for lon, lat in ring]
                     for feat in buildings for ring in _rings(feat["geometry"])],
                "#6e4a3c", 0.75, fill=True)
    _paint_path(cv, [[to_local(lon, lat) for lon, lat in ring]
                     for feat in buildings for ring in _rings(feat["geometry"])],
                "#8a6a58", 0.5)
    # ROAD HIERARCHY: four weights by OSM highway class (v1 drew all roads as one hairline)
    by_class = {"major": [], "secondary": [], "tertiary": [], "minor": []}
    for feat in roads:
        hw = feat["properties"].get("highway", "")
        pts = [to_local(lon, lat) for lon, lat in feat["geometry"]["coordinates"]]
        if hw in ("motorway", "trunk", "primary", "primary_link", "trunk_link"):
            by_class["major"].append(pts)
        elif hw == "secondary":
            by_class["secondary"].append(pts)
        elif hw in ("tertiary", "tertiary_link"):
            by_class["tertiary"].append(pts)
        else:
            by_class["minor"].append(pts)
    _paint_path(cv, by_class["major"], "#8a7364", 2.0)
    _paint_path(cv, by_class["secondary"], "#6b5a52", 1.25)
    _paint_path(cv, by_class["tertiary"], "#5d4c44", 1.0)
    _paint_path(cv, by_class["minor"], "#4e3f38", 0.6, alpha=0.8)
    # GTFS shapes: two colours, no legend — FRAM bus blue, ferry gold
    _paint_path(cv, bus_shapes, FRAM, 1.0, alpha=0.65)
    _paint_path(cv, ferry_shapes, FERRY, 1.5, alpha=0.7)
    # quays: piers and harbour areas drawn light, so the terminals read
    for feat in quays:
        g = feat["geometry"]
        if g["type"] == "Point":
            x, y = to_local(*g["coordinates"][:2])
            cv.circle(x, y, 2.0, fill=P["streak_hi"], alpha=0.9)
        elif g["type"] == "LineString":
            pts = [to_local(lon, lat) for lon, lat in g["coordinates"]]
            if len(pts) >= 2:
                cv.line(pts, P["streak_hi"], 1.5, alpha=0.9)
        elif g["type"] == "Polygon":
            for ring in _rings(g):
                pts = [to_local(lon, lat) for lon, lat in ring]
                if len(pts) >= 3:
                    cv.polygon(pts, fill="#4a3236")
    # --- the named map: lit places, the FRAM route label, street names ------------------
    occupied = list(ferry_boxes)
    # scale bar (bottom-left) and north arrow (top-right) keep their corners
    occupied.append((8, MAP["h"] - 46, 250, MAP["h"] - 14))
    occupied.append((MAP["w"] - 44, 8, MAP["w"] - 8, 66))
    items = []
    for label, lon, lat, _src in LIT_PLACES:
        x, y = to_local(lon, lat)
        items.append((label, x, y, 13, FERRY, "place"))
    fx, fy = to_local(*fram_anchor)
    items.append(("FRAM 701 · Kvam–Molde–Årølia", fx, fy, 13, FRAM, "fram"))
    for label, ref, name in STREET_LABELS:
        lon, lat = road_anchor(roads, ref=ref, name=name)
        x, y = to_local(lon, lat)
        items.append((label, x, y, 12, P["ink"], "street"))
    placed, fell_back = place_labels(cv, items, occupied)
    arr = np.asarray(cv.to_pil().convert("RGBA"))
    return _skia_image_rgba(arr), placed, fell_back


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
    # 1050's trajectory median lands at Molde ferjekai (the ferry dwells there between
    # its 6 sailings) — the label would sit on the terminal, on top of the centre
    # cluster, instead of on the route. Use the median of its SAILED positions.
    ids = [a for a in amap.index if str(amap.loc[a, "route_short_name"]) == "1050"]
    sail = traj[traj.agent_id.isin(ids) & (traj.state == "sail")]
    out["1050"] = (names["1050"], to_px(float(sail.lon.median()), float(sail.lat.median())))
    return out


def shape_midpoint(route_short_name):
    """Geometric midpoint of the longest GTFS shape for a route — the mid-route point
    a label sits on (used where the trajectory median is degenerate: route 1050's
    median sailed position lands at Molde ferjekai because the ferry dwells there
    between its 6 sailings, so the label would sit on the terminal, not the route)."""
    trips = pd.read_csv(ROOT / "data/worlds/molde/gtfs/trips.txt", low_memory=False)
    routes = pd.read_csv(ROOT / "data/worlds/molde/gtfs/routes.txt", low_memory=False)
    rid = set(routes[routes.route_short_name.astype(str) == route_short_name].route_id)
    sids = set(trips[trips.route_id.isin(rid)].shape_id.dropna())
    shapes = pd.read_csv(ROOT / "data/worlds/molde/gtfs/shapes.txt", low_memory=False)
    shapes = shapes[shapes.shape_id.isin(sids)]
    best, best_n = None, -1
    for _sid, g in shapes.groupby("shape_id"):
        if len(g) > best_n:
            best, best_n = g, len(g)
    mid = best.iloc[len(best) // 2]
    return float(mid.shape_pt_lon), float(mid.shape_pt_lat)


def fram_label_anchor():
    """Geometric midpoint of the longest route-701 (Kvam–Molde–Årølia) GTFS shape —
    the real route line the FRAM 701 label sits on."""
    return shape_midpoint("701")


def ferry_label_boxes(probe, labels):
    """The per-frame ferry-label chips, in map-panel-local coords — reserved in the
    static base so no street or place label ever sits under them."""
    boxes = []
    for route, (name, (lx, ly)) in labels.items():
        n = next(r["trips"] for r in MEASURE["ferry_routes"] if r["route"] == route)
        s = f"FERRY · {name} ×{n}"
        w = probe.measure(s, ("Inter", "Bold"), 14) + 12
        cx, cy = lx - MAP["x"], ly - MAP["y"]
        boxes.append((cx - w / 2, cy - 11, cx + w / 2, cy + 11))
    return boxes


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
    # readouts: clock, on the road now, trips so far — the two mode values carry
    # their mode colours (FRAM blue for the buses on the road, gold for the ferries)
    y = 212
    x = 56
    for lab, val, color in (("CLOCK", m.clock(f), P["ink"]),
                            ("ON THE ROAD NOW", str(m.on_road(f)), FRAM),
                            ("TRIPS SO FAR", str(m.trips_so_far(f)), P["ink"]),
                            ("FERRIES SAILING", str(int(m.ferry_sailing[f])), FERRY)):
        _text(cv, x, y, lab, 15, "Bold", P["muted"])
        x += cv.measure(lab + " ", ("Inter", "Bold"), 15)
        _text(cv, x, y, val, 19, "Bold", color)
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
            cv.circle(x, y, 3.5, fill=FRAM, alpha=0.30)
        elif is_ferry:
            if beat_ferry:
                cv.circle(x, y, 9, stroke=FERRY, width=1.5, alpha=0.85)
            hx, hy = x, y
            cv.polygon([(hx, hy - 5), (hx + 5, hy), (hx, hy + 5), (hx - 5, hy)], fill=FERRY)
        else:
            cv.circle(x, y, 4.0, fill=FRAM, alpha=0.95)
    # ferry labels from the ferry beat through the answer (the ×23 anchor stays on screen
    # while the deck surprise lands in beat 4). Each label sits on a small ground chip
    # (whipster round 1: the bare labels were shredded by the route lines underneath).
    # The labels name the mode themselves — "FERRY · …" — so no legend is needed.
    if f >= 420:
        for route, (name, (lx, ly)) in labels.items():
            n = next(r["trips"] for r in MEASURE["ferry_routes"] if r["route"] == route)
            s = f"FERRY · {name} ×{n}"
            w = cv.measure(s, ("Inter", "Bold"), 14)
            cv.polygon([(lx - w / 2 - 6, ly - 4), (lx + w / 2 + 6, ly - 4),
                        (lx + w / 2 + 6, ly + 18), (lx - w / 2 - 6, ly + 18)],
                       fill=P["ground"], alpha=0.88)
            _text(cv, lx, ly, s, 14, "Bold", FERRY, anchor="m")
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
    # chart: vehicles on the road, 06:00-10:00 — two lines, one per mode, each named
    # at its own peak (no legend): FRAM buses in blue, ferries in gold. The total
    # peak (67 at 07:35) stays in the deck sentence, not on the chart.
    cx, cy, cw, chh = CHART["x"], CHART["y"], CHART["w"], CHART["h"]
    _text(cv, cx, cy - 4, "VEHICLES ON THE ROAD, MONDAY 06:00–10:00", 14, "Bold", P["muted"])
    gy0, gy1 = cy + 26, cy + chh
    for v in (0, 25, 50):
        yy = gy1 - (gy1 - gy0) * v / CHART["ymax"]
        cv.line([(cx, yy), (cx + cw, yy)], "#4a3236", 1.0)
        _text(cv, cx + cw - 24, yy - 16, f"{v}", 13, "Regular", P["muted"])
    for mode, color in (("ferry", FERRY), ("bus", FRAM)):
        series = MEASURE["active_series_30s"][mode]
        pts = [(cx + cw * i / (len(series) - 1), gy1 - (gy1 - gy0) * v / CHART["ymax"])
               for i, v in enumerate(series)]
        cv.line(pts, color, 2.5)
        peak_i = int(np.argmax(series))
        px = cx + cw * peak_i / (len(series) - 1)
        py = gy1 - (gy1 - gy0) * series[peak_i] / CHART["ymax"]
        cv.circle(px, py, 4.5, fill=color)
        tag = f"{'FERRY' if mode == 'ferry' else 'FRAM'} · PEAK {series[peak_i]} · {MEASURE['peak_by_mode'][mode]['at_clock']}"
        _text(cv, px, py - 26, tag, 13, "Bold", color, anchor="m")
    series = MEASURE["active_series_30s"]["all"]
    now_x = cx + cw * f / (NFRAMES - 1)
    now_v = series[min(int(m.ft[f] / 30), len(series) - 1)]
    now_y = gy1 - (gy1 - gy0) * now_v / CHART["ymax"]
    cv.line([(now_x, gy0), (now_x, gy1)], P["muted"], 1.0, alpha=0.6)
    cv.circle(now_x, now_y, 4, fill=P["ink"])
    # deck (deck 1 from the start; the surprise lands in the final beat)
    yb = 1240
    _text(cv, 56, yb, deck[0], 22, "Regular", P["ink"])
    if f >= 570:
        _text(cv, 56, yb + 28, deck[1], 22, "Regular", P["ink"])
    # methods footer + credit
    _text(cv, 56, 1294, METHODS, 13, "Regular", P["muted"])
    _text(cv, 56, 1311, DRAFT, 13, "Regular", P["muted"])
    _text(cv, 56, 1328, CREDIT, 13, "Bold", P["ink"])
    return cv


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(FILM_DIR / "molde-morning-v2.mp4"))
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
    for s in (METHODS, DRAFT, CREDIT):
        assert probe.measure(s, ("Inter", "Regular" if s != CREDIT else "Bold"), 13) <= 968, \
            f"footer too wide: {s}"
    m = Morning()
    labels = ferry_label_anchors(m.traj, m.agents)
    fboxes = ferry_label_boxes(probe, labels)
    fram = fram_label_anchor()
    print("FRAM 701 label anchor (lon, lat):", fram)
    base_img, placed, fell_back = build_base(fboxes, fram)
    print("placed labels:", {k: [round(v) for v in box] for k, box in placed.items()})
    print("fell back (overlapping slot):", fell_back)
    (FILM_DIR / "placed.json").write_text(json.dumps(
        {"placed": {k: [round(v, 1) for v in box] for k, box in placed.items()},
         "fell_back": fell_back,
         "fram_anchor_lon_lat": list(fram)}, indent=1))
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
