"""Plan-map panel for the section + map diptych (docs/STYLE_REFERENCE.md), drawn on the skia Canvas (rule 12),
supersampled. Terrain hillshade (rule 13) sits under the map when the world has a DEM.

Real layers only, each with its source: coastline (world land.geojson, OSM/ODbL), the vessel's route and position
(trajectory contract from a gated `offsim run`), wind streaks (a field: NORA3 when pulled, else a uniform wind that
the caller must label as assumed). Camera: eased zoom from the route overview toward the vessel, limited by the
cinema rule (offsim/cinema/rules.py zoom rate; 0.3 zoom levels/s used here).

    mp = MapPanel(land, bbox, size=(W, H), ss=2, world_dir=Path("data/worlds/oslofjord"))
    img = mp.frame(u, route_xy, done_k, marker, wind=(u_mps, v_mps), seed=0)   # u in 0..1 over the shot

v9 (2026-11-09, the user's verdict on v8): the panel background and the sea holes were P["ground_deep"]
#2a161a — land #432629 and sea nearly the same dark maroon value, separated only by a coastline hairline,
and the 50 m EMODnet hillshade rendered as mottled speckle. The v9 fix: the panel background and sea are
P["sea"] #16323a (the Molde v2 pattern — sea one flat teal, land a different dark plum), the hillshade is
smoothed (Gaussian sigma 2 cells) and its alpha capped (0.05..0.45) at a higher sun (55 deg) so relief reads
as texture, and OSM roads + named places are drawn. The map wind streaks are off in the demo film
(wind_streaks=False): with the follow-cam they were a second motion competing with the section streaks; the
airflow lives in the section panel only. The camera is a dead-zone glide (camera="smooth"): the centre stays
put while the vessel is inside the central 60% of the view and glides (capped at pan_cap panel-widths
per film, 1.8 = 0.075 widths/s at 24 s in the demo film) to keep it there. A static wide map cannot work here: the route is 9 km wide x
31 km tall in a 3.2:1 panel, so the route would shrink to ~7% of the panel width.
"""
from __future__ import annotations

import math

import numpy as np
import skia
from PIL import Image, ImageDraw

from offsim.cinema.draw import Canvas
from offsim.cinema.look import PALETTES, font_path

P = PALETTES["section-plan"]
ZOOM_RATE = 0.16                      # zoom levels per second (cap 0.35 in cinema/rules.py); 0.8 levels over 5 s keeps coast in view


def smooth(u):
    u = min(max(u, 0.0), 1.0)
    return u * u * (3 - 2 * u)


_ASCENT = {}


def _ascent(size, weight):
    """Baseline offset (px) so skia text sits where PIL's top-anchored text sat: baseline = top + ascent."""
    key = (size, weight)
    if key not in _ASCENT:
        f = skia.Font(skia.Typeface.MakeFromFile(font_path(weight)), float(size))
        _ASCENT[key] = -f.getMetrics().fAscent
    return _ASCENT[key]


def _text(cv, x, top, s, size, weight="Regular", color="#ffffff", anchor="l"):
    """Canvas.text with PIL-style top anchoring (the old renderer passed top-left y)."""
    cv.text(x, top + _ascent(size, weight), s, font=("Inter", weight), size=size, color=color, anchor=anchor)


def _skia_image_rgba(arr):
    """skia.Image from a straight-alpha RGBA uint8 array (premultiplied for skia)."""
    a = arr[..., 3:4].astype(np.float32) / 255.0
    pm = np.concatenate([(arr[..., :3].astype(np.float32) * a + 0.5).astype(np.uint8), arr[..., 3:4]], axis=-1)
    return skia.Image.fromarray(np.ascontiguousarray(pm), colorType=skia.kRGBA_8888_ColorType,
                                alphaType=skia.kPremul_AlphaType)


def _overlaps(box, boxes, margin=4):
    x0, y0, x1, y1 = box
    for bx0, by0, bx1, by1 in boxes:
        if not (x1 + margin < bx0 or bx1 + margin < x0 or y1 + margin < by0 or by1 + margin < y0):
            return True
    return False


def _draw_hillshade(mp, cv, view, pj):
    """Draw the panel's hillshade image (geographic extent mp._hill_bbox, image size mp.size) clipped
    to the current view, so the terrain stays aligned with the coastline. The image is row 0 = north;
    where the view runs past the DEM there is simply no hillshade."""
    W, H = mp.size
    cx, cy, dpp = view
    hx0, hy0, hx1, hy1 = mp._hill_bbox
    vx0 = cx - (W / 2) * dpp / mp.k
    vx1 = cx + (W / 2) * dpp / mp.k
    vy0 = cy - (H / 2) * dpp
    vy1 = cy + (H / 2) * dpp
    ix0, ix1 = max(vx0, hx0), min(vx1, hx1)
    iy0, iy1 = max(vy0, hy0), min(vy1, hy1)
    if ix1 <= ix0 or iy1 <= iy0:
        return
    sx0 = (ix0 - hx0) / (hx1 - hx0) * W
    sx1 = (ix1 - hx0) / (hx1 - hx0) * W
    sy0 = (hy1 - iy1) / (hy1 - hy0) * H
    sy1 = (hy1 - iy0) / (hy1 - hy0) * H
    dx0, _ = pj(ix0, iy1)
    dx1, _ = pj(ix1, iy1)
    _, dy0 = pj(ix0, iy1)
    _, dy1 = pj(ix0, iy0)
    cv.cv.drawImageRect(mp._hill, skia.Rect.MakeXYWH(sx0, sy0, sx1 - sx0, sy1 - sy0),
                        skia.Rect.MakeXYWH(dx0, dy0, dx1 - dx0, dy1 - dy0))


class MapPanel:
    def __init__(self, land, bbox, size=(1080, 300), ss=2, seconds=5.0, n_streaks=900, seed=0, span_mult=1.8,
                 world_dir=None, camera="ease", wind_streaks=True, roads=None, places=None, pan_cap=1.2):
        self.land, self.bbox, self.size, self.ss, self.seconds = land, bbox, size, ss, seconds
        self.span_mult = span_mult    # overview width as a multiple of the width fit (1.8 tuned on Oslofjord)
        self.k = math.cos(math.radians((bbox[1] + bbox[3]) / 2))
        self.rng = np.random.default_rng(seed)
        self.p = None
        self.n = n_streaks
        self.tail = []
        self.camera, self.wind_streaks = camera, wind_streaks
        self.pan_cap = pan_cap        # smooth camera: max glide, panel-widths per film (1.8 = 0.075 widths/s at 24 s)
        # v9 dead-zone glide camera state: centre (lon, lat), last u, peak pan (panel-widths per film)
        self._cam, self._last_u, self._pan_max = None, 0.0, 0.0
        # v9 OSM roads, bucketed by class (each a list of [(lon, lat), ...] ways); places are
        # {text, lat, lon, kind} dicts — kind place/site/fjord; names verified against the OSM
        # fetch (places_demo.json), never guessed.
        # v10 guard: the land bounds the camera may never leave. The v9 blue cuts were the view
        # overhanging the land box (right 0.082 deg at f0000, left 0.022 deg at f0719) with the
        # flat sea-teal background showing as a straight vertical strip through land. The clamp
        # (in _view_smooth / _view) bounds the glide centre so the whole view stays inside these
        # bounds; when the land is narrower than the view the clamp cannot help (the fetch is the
        # fix) and the glide is left alone. GeoSeries/GeoDataFrame have total_bounds; a shapely
        # geometry has bounds; anything else leaves the guard off (None).
        if hasattr(land, "total_bounds"):
            self._land_bounds = tuple(float(v) for v in land.total_bounds)
        elif hasattr(land, "bounds"):
            self._land_bounds = tuple(float(v) for v in land.bounds)
        else:
            self._land_bounds = None
        self.roads = {"major": [], "secondary": [], "tertiary": []}
        _roads = roads.get("features", []) if isinstance(roads, dict) else (roads or [])
        for f in _roads:
            hw = f["properties"].get("highway", "")
            coords = f["geometry"]["coordinates"]
            if len(coords) < 2:
                continue
            if hw in ("motorway", "trunk", "primary", "primary_link", "trunk_link"):
                self.roads["major"].append(coords)
            elif hw == "secondary":
                self.roads["secondary"].append(coords)
            elif hw == "tertiary":
                self.roads["tertiary"].append(coords)
        self.places = list(places or [])
        # terrain hillshade (rule 13), read once: under the land fill, over the flat ground. None + a reason
        # when the world has no DEM — the map then stays flat, exactly as before. v9 tuning: the 50 m
        # EMODnet grid is smoothed (sigma 2 cells) and the slope alpha capped (0.05..0.45) at a higher
        # sun (55 deg) — unsmoothed it read as dirt, not relief.
        self._hill, self.hill_why = None, None
        self._hill_bbox = bbox
        if world_dir is not None:
            from offsim.worlds.terrain_tint import for_bbox
            rgba, why = for_bbox(world_dir, bbox, size, azimuth=315.0, altitude=55.0,
                                 smooth_sigma=2.0, alpha_range=(0.05, 0.45))
            self.hill_why = why
            if rgba is not None:
                self._hill = _skia_image_rgba(rgba)

    def _clamp_to_land(self, cx, cy, span):
        """v10 guard: keep the whole view inside the land data, so the sea-teal panel background
        can never show as a straight strip through land (the v9 blue cuts). The clamp binds only
        when the glide would leave the data; with the v10 fetch (envelope + ~0.1 deg margin) it
        never binds on the demo run — it is a safety net for resumed renders and future routes.
        When the land is narrower than the view the clamp cannot help and the centre is left
        alone (the fetch, not the camera, is the fix there)."""
        if self._land_bounds is None:
            return cx, cy
        W, H = self.size
        hw = (W / 2) * span / self.k
        hh = (H / 2) * span
        lx0, ly0, lx1, ly1 = self._land_bounds
        if lx1 - lx0 > 2 * hw:
            cx = min(max(cx, lx0 + hw), lx1 - hw)
        if ly1 - ly0 > 2 * hh:
            cy = min(max(cy, ly0 + hh), ly1 - hh)
        return cx, cy

    def _view(self, u, focus, follow=False):
        """Centre and metres-per-pixel at shot fraction u: overview of bbox -> zoomed on focus. follow=True
        locks the centre on the (moving) focus — a follow-cam; without it the centre eases from the bbox
        centre toward a fixed focus, which leaves a moving vessel outside the thin panel's lat window.
        camera="smooth" (v9 demo film) replaces the lock with a dead-zone glide: the centre stays put
        while the focus is inside the central 60% of the view and glides (capped at pan_cap panel-widths per
        film) to keep it there — one slow motion, not a camera glued to a fast vessel."""
        if self.camera == "smooth":
            return self._view_smooth(u, focus)
        W, H = self.size
        x0, y0, x1, y1 = self.bbox
        # wide panels: the width fit crops too much and the full fit shows beyond the data; span_mult x the
        # width fit keeps coast in frame at the end of the zoom (tuned on the Oslofjord world, 968x300 panel)
        span = self.span_mult * min((x1 - x0) * self.k / W, (y1 - y0) / H)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        e = 1.0 if follow else smooth(u)
        zoom = 2 ** (ZOOM_RATE * self.seconds * smooth(u))
        cx, cy = self._clamp_to_land(cx + (focus[0] - cx) * e, cy + (focus[1] - cy) * e, span / zoom)
        return cx, cy, span / zoom

    def _view_smooth(self, u, focus):
        """Dead-zone glide camera. The view span is fixed (no zoom); the centre opens on the focus
        (the vessel at its base) and then moves only to keep the focus inside the central 60% rect,
        gliding with a u 0.02 time constant and a hard cap of pan_cap panel-widths per film
        (1.8 = 0.075 widths/s over 24 s in the demo film). self._pan_max records the peak rate
        (widths per film) for the report/tests. The cap is binding: at span 3.2 / cap 1.2 the marker
        leaves the frame on the 193-frame southward run; span 4.0 / cap 1.8 holds it with worst
        centre-distance 0.41 of the half-frame (test_draw)."""
        W, H = self.size
        x0, y0, x1, y1 = self.bbox
        span = self.span_mult * min((x1 - x0) * self.k / W, (y1 - y0) / H)
        lon, lat = focus
        if self._cam is None:
            # v10: clamp the opening too — a resumed render opens on the focus at the resume
            # frame, and the v9 f0719 left strip was exactly a resumed opening outside the data.
            self._cam = self._clamp_to_land(lon, lat, span)
            self._last_u = u
            return self._cam[0], self._cam[1], span
        du = max(u - self._last_u, 0.0)
        self._last_u = u
        cx, cy = self._cam
        mx = (lon - cx) * self.k / span + W / 2
        my = H / 2 - (lat - cy) / span
        tx, ty = cx, cy
        if mx < 0.2 * W:
            tx = cx - (0.2 * W - mx) * span / self.k
        elif mx > 0.8 * W:
            tx = cx + (mx - 0.8 * W) * span / self.k
        if my < 0.2 * H:
            ty = cy + (0.2 * H - my) * span
        elif my > 0.8 * H:
            ty = cy - (my - 0.8 * H) * span
        a = 1.0 - math.exp(-du / 0.02) if du > 0 else 0.0
        dlon, dlat = (tx - cx) * a, (ty - cy) * a
        px = math.hypot(dlon * self.k / span, dlat / span)
        cap = du * self.pan_cap * W
        if px > cap > 0:
            f = cap / px
            dlon, dlat = dlon * f, dlat * f
        self._cam = self._clamp_to_land(cx + dlon, cy + dlat, span)
        # pan rate from the ACTUAL centre change (after the clamp), not the requested glide
        moved = math.hypot((self._cam[0] - cx) * self.k / span, (self._cam[1] - cy) / span)
        if du > 0:
            self._pan_max = max(self._pan_max, moved / W / du)
        return self._cam[0], self._cam[1], span

    def _proj(self, view):
        cx, cy, dpp = view
        W, H = self.size
        return lambda lon, lat: ((lon - cx) * self.k / dpp + W / 2, H / 2 - (lat - cy) / dpp)

    def _route_and_marker(self, cv, pj, route, done_k, marker):
        """One vessel's route: done part solid accent, rest dashed muted, ring + dot at the marker."""
        pts = [pj(x, y) for x, y in route]
        if done_k > 1:
            cv.line(pts[:done_k], P["accent"], 2.0)
        for i in range(done_k, len(pts) - 1, 2):
            cv.line([pts[i], pts[i + 1]], P["muted"], 1.0)
        mx, my = pj(*marker)
        cv.circle(mx, my, 16.8, stroke=P["accent"], width=1.0)
        cv.circle(mx, my, 4.2, fill=P["accent"])

    def frame(self, u, route, done_k, marker, wind=(8.0, 0.0), label_km=None, others=None, follow=False):
        """others: extra vessels as [(name, route, done_k, marker), ...], drawn like the main one (same
        accent: they are one plan, not competing series). A vessel whose marker is outside the frame gets
        an edge indicator (chevron + name) instead of vanishing silently. follow: lock the camera centre
        on the moving marker."""
        W, H = self.size
        view = self._view(u, marker, follow=follow)
        pj = self._proj(view)
        cv = Canvas(W, H, bg=P["sea"], ss=self.ss)   # v9: the sea is P["sea"], not ground_deep — land and sea must read as two different things
        geoms = getattr(self.land, "geoms", [self.land])
        exts = []
        landmask = Image.new("L", (W, H), 0)          # internal raster only: where streaks must respawn
        dm = ImageDraw.Draw(landmask)
        for g in geoms:
            ext = [pj(x, y) for x, y in g.exterior.coords]
            if len(ext) < 3:
                continue
            holes = [[pj(x, y) for x, y in hole.coords] for hole in g.interiors]
            exts.append((ext, holes))
            cv.polygon(ext, fill="#432629")
            dm.polygon(ext, fill=255)
            for hp in holes:
                cv.polygon(hp, fill=P["sea"])   # v9: holes are sea, not ground_deep
                dm.polygon(hp, fill=0)
        if self._hill is not None:
            # v9: the hillshade is a geographic layer for the world bbox, not a screen fill — draw
            # only the part overlapping the current view, so it stays aligned with the coastline.
            # (Drawing it stretched over the whole panel misaligned it with the coast: the v8
            # "mottled speckle". Where the view runs past the DEM there is simply no hillshade.)
            _draw_hillshade(self, cv, view, pj)
        # v9: OSM roads, one batched path per class (major / secondary / tertiary) — the land's
        # internal structure, without which the coast is a bare outline
        if self.roads["major"]:
            cv.lines([[pj(lon, lat) for lon, lat in way] for way in self.roads["major"]],
                     (138, 122, 110), 1.6, alpha=0.55)
        if self.roads["secondary"]:
            cv.lines([[pj(lon, lat) for lon, lat in way] for way in self.roads["secondary"]],
                     (120, 106, 96), 1.1, alpha=0.45)
        if self.roads["tertiary"]:
            cv.lines([[pj(lon, lat) for lon, lat in way] for way in self.roads["tertiary"]],
                     (110, 96, 88), 0.8, alpha=0.35)
        for ext, _holes in exts:
            cv.line(ext + [ext[0]], P["streak_hi"], 1.0)
        lm = np.array(landmask) > 0
        # wind streaks in screen space (field is uniform here: caller labels it); respawn on land.
        # v9: off in the demo film (wind_streaks=False) — streaks over the sea + a moving camera were
        # two competing motions; the airflow lives in the section panel only.
        if self.wind_streaks:
            if self.p is None:
                self.p = np.c_[self.rng.uniform(0, W, self.n), self.rng.uniform(0, H, self.n)]
                self.tail = [self.p.copy()]
            vel = np.array([wind[0], -wind[1]]) / max(np.hypot(*wind), 1e-6) * 5.0
            wob = np.sin(self.p[:, 1] / 37 + u * 6) * 0.6
            q = self.p + vel + np.c_[np.zeros(self.n), wob]
            out = (q[:, 0] < 0) | (q[:, 0] >= W) | (q[:, 1] < 0) | (q[:, 1] >= H)
            qi = np.clip(q.astype(int), 0, [W - 1, H - 1])
            out |= lm[qi[:, 1], qi[:, 0]] | (self.rng.random(self.n) < 0.01)
            q[out] = np.c_[self.rng.uniform(0, W, out.sum()), self.rng.uniform(0, H, out.sum())]
            self.tail = ([q.copy()] + self.tail)[:10]
            for k in range(len(self.tail) - 1):
                a, b = self.tail[k], self.tail[k + 1]
                jump = np.hypot(*(a - b).T) > 12
                for (x0, y0), (x1, y1), j in zip(a, b, jump):
                    if not j:
                        cv.line([(x0, y0), (x1, y1)], (170, 140, 120, int(120 * (1 - k / 10))), 1.0)
        self._route_and_marker(cv, pj, route, done_k, marker)
        for name_o, route_o, done_o, marker_o in others or []:
            self._route_and_marker(cv, pj, route_o, done_o, marker_o)
            mx, my = pj(*marker_o)
            if not (0 <= mx < W and 0 <= my < H):
                # off-frame vessel: chevron + name at the clamped edge, pointing at the true position
                cx_, cy_ = min(max(mx, 14), W - 14), min(max(my, 14), H - 14)
                dx, dy = mx - cx_, my - cy_
                L = max((dx * dx + dy * dy) ** 0.5, 1e-6)
                ux, uy = dx / L, dy / L
                cv.polygon([(cx_ + ux * 10, cy_ + uy * 10),
                            (cx_ - uy * 6 - ux * 4, cy_ + ux * 6 - uy * 4),
                            (cx_ + uy * 6 - ux * 4, cy_ - ux * 6 - uy * 4)], fill=P["accent"])
                lab_w = cv.measure(name_o, ("Inter", "Bold"), 13)
                lx = cx_ + 14 if cx_ + 14 + lab_w < W - 8 else cx_ - 14 - lab_w
                _text(cv, lx, cy_ - 7, name_o, 13, "Bold", P["accent"])
        # scale bar (km) and north; the label sits on a ground chip so it never reads half on the coastline
        km_px = 1000 / (view[2] * 111_320)
        bar_km = label_km or max(1, int(round(W * 0.18 / km_px)))
        bx, by = 24, H - 22
        cv.line([(bx, by), (bx + bar_km * km_px, by)], P["ink"], 2.0)
        _label = f"{bar_km} km"
        _w = cv.measure(_label, ("Inter", "Regular"), 13)
        cv.polygon([(bx - 5, by - 26), (bx + _w + 5, by - 26), (bx + _w + 5, by - 6), (bx - 5, by - 6)],
                   fill=P["ground_deep"])
        _text(cv, bx, by - 22, _label, 13, "Regular", P["ink"])
        _text(cv, W - 30, 14, "N", 15, "Bold", P["ink"])
        cv.line([(W - 24, 36), (W - 24, 52)], P["ink"], 1.0)
        # v9: named places (OSM-verified) — drawn last, on top of the route; the scale-bar chip
        # and the north arrow are reserved so no label sits under them.
        if self.places:
            occupied = [(bx - 5, by - 26, bx + _w + 5, by - 6), (W - 44, 8, W - 8, 56)]
            self._place_labels(cv, pj, occupied)
        return cv.to_pil()

    def _place_labels(self, cv, pj, occupied):
        """Deterministic place labels (the Molde v2 placer, ported): each label tries above / below /
        left / right (then far above / far below) of its anchor and takes the first chip that does not
        overlap an already-placed box and stays inside the panel. Anchors outside the view are skipped,
        not drawn off-panel. kinds: 'place' — gold dot + halo + ground chip; 'site' — small gold dot +
        bare text (no chip); 'fjord' — bare text on the water, no dot. Returns (placed, fell_back) —
        fell-back labels are drawn at the first candidate and reported, not hidden."""
        W, H = self.size
        items = []
        for p in self.places:
            ax, ay = pj(p["lon"], p["lat"])
            if not (-30 <= ax <= W + 30 and -30 <= ay <= H + 30):
                continue
            items.append((p["text"], ax, ay, p.get("size", 13), p.get("color", P["accent"]),
                          p.get("kind", "place")))
        placed, fell_back = {}, []
        boxes = list(occupied)
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
                if b[0] < 8 or b[1] < 8 or b[2] > W - 8 or b[3] > H - 8:
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
        place_anchors = [(ax, ay) for _t, ax, ay, _s, _c, k, _b in chosen if k == "place"]
        for text, ax, ay, size, color, kind, box in chosen:
            if kind == "place":
                crowded = any((ax - ox) ** 2 + (ay - oy) ** 2 < 20 ** 2
                              for ox, oy in place_anchors if (ox, oy) != (ax, ay))
                if not crowded:
                    cv.circle(ax, ay, 10, fill=color, alpha=0.22)
                cv.circle(ax, ay, 3.0 if crowded else 4, fill=color)
            elif kind == "site":
                cv.circle(ax, ay, 2.5, fill=color)
            cx = (box[0] + box[2]) / 2
            cy = (box[1] + box[3]) / 2
            if abs(cx - ax) > 14 or abs(cy - ay) > 14:
                ex = min(max(ax, box[0]), box[2])
                ey = min(max(ay, box[1]), box[3])
                cv.line([(ax, ay), (ex, ey)], P["muted"] if kind == "fjord" else color, 1.0, alpha=0.7)
        # pass 2: chips + text (on top of every leader)
        for text, ax, ay, size, color, kind, box in chosen:
            cx = (box[0] + box[2]) / 2
            if kind == "place":
                cv.polygon([(box[0], box[1]), (box[2], box[1]), (box[2], box[3]), (box[0], box[3])],
                           fill=P["ground"], alpha=0.92)
            _text(cv, cx, box[1] + 5, text, size, "Bold", color, anchor="m")
        self._placed, self._fell_back = placed, fell_back
        return placed, fell_back
