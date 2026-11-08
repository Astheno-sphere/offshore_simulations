"""Plan-map panel for the section + map diptych (docs/STYLE_REFERENCE.md), drawn in PIL, supersampled.

Real layers only, each with its source: coastline (world land.geojson, OSM/ODbL), the vessel's route and position
(trajectory contract from a gated `offsim run`), wind streaks (a field: NORA3 when pulled, else a uniform wind that
the caller must label as assumed). Camera: eased zoom from the route overview toward the vessel, limited by the
cinema rule (offsim/cinema/rules.py zoom rate; 0.3 zoom levels/s used here).

    mp = MapPanel(land, bbox, size=(W, H), ss=2)
    img = mp.frame(u, route_xy, done_k, marker, wind=(u_mps, v_mps), seed=0)   # u in 0..1 over the shot
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw

from offsim.cinema.look import PALETTES

P = PALETTES["section-plan"]
ZOOM_RATE = 0.16                      # zoom levels per second (cap 0.35 in cinema/rules.py); 0.8 levels over 5 s keeps coast in view


def smooth(u):
    u = min(max(u, 0.0), 1.0)
    return u * u * (3 - 2 * u)


class MapPanel:
    def __init__(self, land, bbox, size=(1080, 300), ss=2, seconds=5.0, n_streaks=2400, seed=0):
        self.land, self.bbox, self.size, self.ss, self.seconds = land, bbox, size, ss, seconds
        self.k = math.cos(math.radians((bbox[1] + bbox[3]) / 2))
        self.rng = np.random.default_rng(seed)
        self.p = None
        self.n = n_streaks
        self.tail = []

    def _view(self, u, focus):
        """Centre and metres-per-pixel at shot fraction u: overview of bbox -> zoomed on focus."""
        W, H = self.size
        x0, y0, x1, y1 = self.bbox
        # wide panels: the width fit crops too much and the full fit shows beyond the data; 1.8x the width fit keeps
        # coast in frame at the end of the zoom (tuned on the Oslofjord world, 968x300 panel)
        span = 1.8 * min((x1 - x0) * self.k / W, (y1 - y0) / H)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        e = smooth(u)
        zoom = 2 ** (ZOOM_RATE * self.seconds * e)
        return cx + (focus[0] - cx) * e, cy + (focus[1] - cy) * e, span / zoom

    def _proj(self, view):
        cx, cy, dpp = view
        W, H = self.size
        s = self.ss
        return lambda lon, lat: (((lon - cx) * self.k / dpp + W / 2) * s, (H / 2 - (lat - cy) / dpp) * s)

    def frame(self, u, route, done_k, marker, wind=(8.0, 0.0), label_km=None):
        W, H = self.size
        s = self.ss
        view = self._view(u, marker)
        pj = self._proj(view)
        img = Image.new("RGBA", (W * s, H * s), P["ground_deep"])
        landmask = Image.new("L", (W * s, H * s), 0)
        d, dm = ImageDraw.Draw(img), ImageDraw.Draw(landmask)
        geoms = getattr(self.land, "geoms", [self.land])
        for g in geoms:
            ext = [pj(x, y) for x, y in g.exterior.coords]
            if len(ext) < 3:
                continue
            d.polygon(ext, fill="#432629")
            dm.polygon(ext, fill=255)
            for hole in g.interiors:
                hp = [pj(x, y) for x, y in hole.coords]
                d.polygon(hp, fill=P["ground_deep"])
                dm.polygon(hp, fill=0)
            d.line(ext + [ext[0]], fill=P["streak_hi"], width=max(1, s))
        lm = np.array(landmask) > 0
        # wind streaks in screen space (field is uniform here: caller labels it); respawn on land
        if self.p is None:
            self.p = np.c_[self.rng.uniform(0, W * s, self.n), self.rng.uniform(0, H * s, self.n)]
            self.tail = [self.p.copy()]
        vel = np.array([wind[0], -wind[1]]) / max(np.hypot(*wind), 1e-6) * 3.0 * s
        wob = np.sin(self.p[:, 1] / (37 * s) + u * 6) * 0.6 * s
        q = self.p + vel + np.c_[np.zeros(self.n), wob]
        out = (q[:, 0] < 0) | (q[:, 0] >= W * s) | (q[:, 1] < 0) | (q[:, 1] >= H * s)
        qi = np.clip(q.astype(int), 0, [W * s - 1, H * s - 1])
        out |= lm[qi[:, 1], qi[:, 0]] | (self.rng.random(self.n) < 0.01)
        q[out] = np.c_[self.rng.uniform(0, W * s, out.sum()), self.rng.uniform(0, H * s, out.sum())]
        self.tail = ([q.copy()] + self.tail)[:10]
        for k in range(len(self.tail) - 1):
            a, b = self.tail[k], self.tail[k + 1]
            jump = np.hypot(*(a - b).T) > 12 * s
            for (x0, y0), (x1, y1), j in zip(a, b, jump):
                if not j:
                    d.line([(x0, y0), (x1, y1)], fill=(170, 140, 120, int(210 * (1 - k / 10))), width=max(1, s // 2 + 1))
        # route: done part solid accent, rest dashed muted
        pts = [pj(x, y) for x, y in route]
        if done_k > 1:
            d.line(pts[:done_k], fill=P["accent"], width=2 * s, joint="curve")
        for i in range(done_k, len(pts) - 1, 2):
            d.line([pts[i], pts[i + 1]], fill=P["muted"], width=s)
        mx, my = pj(*marker)
        r = 7 * s
        d.ellipse([mx - 2.4 * r, my - 2.4 * r, mx + 2.4 * r, my + 2.4 * r], outline=P["accent"], width=s)
        d.ellipse([mx - r * 0.6, my - r * 0.6, mx + r * 0.6, my + r * 0.6], fill=P["accent"])
        # scale bar (km) and north
        km_px = 1000 / (view[2] * 111_320) * s
        bar_km = label_km or max(1, int(round(W * s * 0.18 / km_px)))
        bx, by = 24 * s, H * s - 22 * s
        d.line([(bx, by), (bx + bar_km * km_px, by)], fill=P["ink"], width=2 * s)
        d.text((bx, by - 22 * s), f"{bar_km} km", fill=P["ink"], font_size=13 * s)
        d.text((W * s - 30 * s, 14 * s), "N", fill=P["ink"], font_size=15 * s)
        d.line([(W * s - 24 * s, 36 * s), (W * s - 24 * s, 52 * s)], fill=P["ink"], width=s)
        return img.resize(self.size, Image.LANCZOS)
