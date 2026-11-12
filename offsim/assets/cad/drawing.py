"""Drawing engine: exact CAD solids -> CAD-grade line art (the Rhino Make2D / drafting look).

    d = project(model, view="side")                  # exact hidden-line removal (OpenCASCADE HLR), metres in the view plane
    d = project_cached("psv", {"loa_m": 85}, "side") # same, cached to out/cache/cad/*.json (films never run HLR per frame)
    s = section(model, plane="xz", offset=0.0)       # cut contour (hull cross-section etc.) as a Drawing of cls "section"
    n = draw(canvas, d.transformed(angle=pitch, dy=heave), to_px, style)   # offsim.cinema.draw.Canvas
    to_svg(d, "out.svg")
    classes = project_classes(shape, view)            # Nordlys sprite-sheet projection: {class: [polyline]}, views side/front/rear/top/three-quarter
    prims, solids, exhaust = psv_profile_cad(x0, z0)  # gale-film section-frame adapter (builds "psv_v10")

View frames (model axes: x forward, y port, z up; see base.py). Drawing coordinates are (right, up) in metres:
    side   camera on the starboard side (-y) looking +y   bow to the right      right = +x, up = +z
    front  camera ahead of the bow looking -x             port to the right     right = +y, up = +z
    top    camera above looking -z                        bow up the page       right = -y, up = +x
    iso    camera at (+x, -y, +z) looking at the origin   right = (y+x)/..., up = z-ish
    (dx, dy, dz)  any vector pointing from the object toward the camera; `up` is the world up hint.

Line classes (cls) and what OpenCASCADE edge class produces them:
    outline   OutLineVCompound of the WHOLE shape: the silhouette / turning edges (heaviest)
    visible   OutLine + sharp (VCompound) visible edges of each named part
    detail    smooth / sewn visible edges (Rg1Line, RgNLine): tangent seams, face splits (lightest)
    hidden    HCompound (only computed with hidden=True; drawn dashed only if style["show_hidden"])
    section   cut contours from section()

Motion: a cached drawing is moved as a 2D rigid transform (`Drawing.transformed`: rotate about a pivot, translate,
scale). That is exact for rotation about the view axis (roll in a front view, pitch in a side view) and a good
approximation for small out-of-plane rotations; beyond ~5 degrees about any other axis the silhouette changes and
the asset must be re-projected (`project` with a rotated model / different view).
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[3]
CACHE_VERSION = 1
CACHE_DIR = ROOT / "out" / "cache" / "cad"

CLASSES = ("outline", "visible", "detail", "hidden", "section")
WEIGHTS = {"outline": 2.4, "visible": 1.3, "detail": 0.8, "hidden": 0.6, "section": 2.8}   # px at 1x (STYLE_REFERENCE)
MIN_PX = 0.75                                    # polylines shorter than this on screen are dropped (no mush)
HIDDEN_DASH = (4.0, 3.0)

_NAMED_VIEWS = {"side": ((0.0, -1.0, 0.0), (0, 0, 1)), "front": ((1.0, 0.0, 0.0), (0, 0, 1)),
                "top": ((0.0, 0.0, 1.0), (1, 0, 0)), "iso": ((1.0, -1.0, 0.6), (0, 0, 1))}


# ---------------------------------------------------------------------------------------------------------------
@dataclass
class Drawing:
    lines: list = field(default_factory=list)       # [{"cls": str, "part": str, "pts": [(x, y), ...]}]  metres, (right, up)
    bbox: tuple = (0.0, 0.0, 0.0, 0.0)              # xmin, ymin, xmax, ymax over all non-hidden lines
    meta: dict = field(default_factory=dict)

    def by_class(self, cls):
        return [l for l in self.lines if l["cls"] == cls]

    def counts(self):
        out = {}
        for l in self.lines:
            out[l["cls"]] = out.get(l["cls"], 0) + 1
        return out

    @property
    def width(self):
        return self.bbox[2] - self.bbox[0]

    @property
    def height(self):
        return self.bbox[3] - self.bbox[1]

    def to_dict(self):
        return {"lines": [{"cls": l["cls"], "part": l["part"], "pts": [[round(x, 5), round(y, 5)] for x, y in l["pts"]]}
                          for l in self.lines], "bbox": list(self.bbox), "meta": self.meta}

    @classmethod
    def from_dict(cls, d):
        return cls(lines=[{"cls": l["cls"], "part": l["part"], "pts": [tuple(p) for p in l["pts"]]} for l in d["lines"]],
                   bbox=tuple(d["bbox"]), meta=dict(d.get("meta", {})))

    def transformed(self, angle=0.0, dx=0.0, dy=0.0, pivot=(0.0, 0.0), scale=1.0):
        """New Drawing: scale about the pivot, rotate by `angle` rad (counter-clockwise, y up) about the pivot, then
        translate by (dx, dy) metres. Pitch/heave of a cached side drawing: transformed(angle=pitch, dy=heave,
        pivot=(x_cg, z_cg)). Valid for small angles (see module docstring)."""
        c, s = math.cos(angle) * scale, math.sin(angle) * scale
        px, py = pivot
        def tf(p):
            x, y = p[0] - px, p[1] - py
            return (px + c * x - s * y + dx, py + s * x + c * y + dy)
        lines = [{"cls": l["cls"], "part": l["part"], "pts": [tf(p) for p in l["pts"]]} for l in self.lines]
        return Drawing(lines, _bbox(lines), dict(self.meta))


def _bbox(lines):
    xs = [p[0] for l in lines if l["cls"] != "hidden" for p in l["pts"]]
    ys = [p[1] for l in lines if l["cls"] != "hidden" for p in l["pts"]]
    if not xs:
        xs = [p[0] for l in lines for p in l["pts"]]
        ys = [p[1] for l in lines for p in l["pts"]]
    if not xs:
        return (0.0, 0.0, 0.0, 0.0)
    return (min(xs), min(ys), max(xs), max(ys))


# ---------------------------------------------------------------------------------------------------------------
def _wrapped(s):
    """TopoDS_Shape from a cadquery / build123d Shape / Workplane / Compound, or a raw TopoDS_Shape."""
    if hasattr(s, "val") and callable(s.val) and not hasattr(s, "wrapped"):     # cadquery Workplane
        s = s.val()
    return getattr(s, "wrapped", s)


def _unit(v):
    n = math.sqrt(sum(c * c for c in v))
    if n == 0:
        raise ValueError("zero-length view vector")
    return tuple(c / n for c in v)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def view_frame(view, up=(0, 0, 1)):
    """(toward_camera, right, up_vec) unit vectors for a named view or a direction vector (object -> camera)."""
    if isinstance(view, str):
        if view not in _NAMED_VIEWS:
            raise ValueError(f"unknown view {view!r}; use {sorted(_NAMED_VIEWS)} or a direction vector")
        d, upv = _NAMED_VIEWS[view]
        if up != (0, 0, 1):
            upv = up
    else:
        d, upv = tuple(view), up
    n = _unit(d)
    look = tuple(-c for c in n)
    right = _cross(look, _unit(upv))
    if sum(c * c for c in right) < 1e-12:                       # up parallel to look: pick any
        right = _cross(look, (1, 0, 0) if abs(look[0]) < 0.9 else (0, 1, 0))
    right = _unit(right)
    upv = _cross(right, look)
    return n, right, _unit(upv)


def _diag(shape):
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    b = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, b, False, False)
    x0, y0, z0, x1, y1, z1 = b.Get()
    return math.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2 + (z1 - z0) ** 2)


def _drop_collinear(pts, tol=1e-6):
    """Remove interior points that lie on the chord of their neighbours (a circle seen edge-on is a straight line)."""
    if len(pts) < 3:
        return pts
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        a, b, c = out[-1], pts[i], pts[i + 1]
        cr = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        L = math.hypot(c[0] - a[0], c[1] - a[1])
        dot = (b[0] - a[0]) * (c[0] - a[0]) + (b[1] - a[1]) * (c[1] - a[1])
        if L > 0 and abs(cr) / L < tol and 0 <= dot <= L * L:
            continue
        out.append(b)
    out.append(pts[-1])
    return out


def _polylines(compound, defl):
    """Discretise every edge of an HLR compound into 2D polylines (x, y) = view-plane coordinates."""
    if compound is None or compound.IsNull():
        return []
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GCPnts import GCPnts_QuasiUniformDeflection
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    out = []
    ex = TopExp_Explorer(compound, TopAbs_EDGE)
    while ex.More():
        edge = TopoDS.Edge_s(ex.Current())
        ex.Next()
        try:
            c = BRepAdaptor_Curve(edge)
            u0, u1 = c.FirstParameter(), c.LastParameter()
            gp = GCPnts_QuasiUniformDeflection(c, defl, u0, u1)
            if gp.IsDone() and gp.NbPoints() >= 2:
                pts = [(gp.Value(i).X(), gp.Value(i).Y()) for i in range(1, gp.NbPoints() + 1)]
            else:
                pts = [(c.Value(u0).X(), c.Value(u0).Y()), (c.Value(u1).X(), c.Value(u1).Y())]
        except Exception:
            continue
        pts = _drop_collinear([(round(x, 7), round(y, 7)) for x, y in pts])
        if len(pts) >= 2 and any(abs(pts[1][k] - pts[0][k]) > 1e-9 or abs(pts[-1][k] - pts[0][k]) > 1e-9 for k in (0, 1)):
            out.append(pts)
    return out


def _hlr(shapes: dict, ax2, silhouette_only=False, hidden=False, defl=1e-3):
    """Run exact HLR on {name: TopoDS}. Returns {name: {cls: [polyline]}} (cls keys raw: outline, sharp, smooth, hidden)."""
    from OCP.HLRAlgo import HLRAlgo_Projector
    from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape
    algo = HLRBRep_Algo()
    for s in shapes.values():
        algo.Add(s)
    algo.Projector(HLRAlgo_Projector(ax2))
    algo.Update()
    algo.Hide()
    tos = HLRBRep_HLRToShape(algo)
    res = {}
    for name, s in shapes.items():
        r = {"outline": _polylines(tos.OutLineVCompound(s), defl)}
        if not silhouette_only:
            r["sharp"] = _polylines(tos.VCompound(s), defl)
            r["smooth"] = _polylines(tos.Rg1LineVCompound(s), defl) + _polylines(tos.RgNLineVCompound(s), defl)
            if hidden:
                r["hidden"] = _polylines(tos.HCompound(s), defl)
        res[name] = r
    return res


def _on_silhouette(polys, tol):
    """The visible whole-shape edges that lie on the exterior boundary of the projected shape (the silhouette).
    Boundary = exterior ring(s) of the union of the faces closed by the visible linework (holes filled). Falls back to
    the HLR turning-edge class alone if the linework does not close."""
    try:
        from shapely.geometry import LineString
        from shapely.ops import polygonize, unary_union
        ls = [LineString(p) for p in polys if len(p) >= 2]
        faces = list(polygonize(unary_union(ls)))
        if not faces:
            raise ValueError("no closed faces")
        sil = unary_union(faces)
        rings = []
        for g in (sil.geoms if hasattr(sil, "geoms") else [sil]):
            rings.append(g.exterior)
        from shapely.geometry import MultiLineString
        boundary = MultiLineString([list(r.coords) for r in rings]).buffer(tol)
        keep = []
        for p in polys:
            if len(p) < 2:
                continue
            probe = list(p) + [((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) for a, b in zip(p, p[1:])]
            from shapely.geometry import Point
            if all(boundary.covers(Point(q)) for q in probe):
                keep.append(p)
        return keep
    except Exception:
        return []


def _model_parts(model):
    shape = getattr(model, "shape", model)
    parts = dict(getattr(model, "parts", None) or {})
    return shape, parts


def project(model_or_shape, view="side", up=(0, 0, 1), hidden=False, silhouette=True, deflection=None) -> Drawing:
    """Exact hidden-line projection of an AssetModel (or a bare shape) into a Drawing (metres in the view plane).

    Each named part is projected together with its siblings (parts occlude each other) and its lines carry the part
    name (weights/colours per part). `silhouette=True` adds a second pass on the whole shape whose visible outline
    edges are class "outline" (part "*"). `hidden=True` also computes hidden edges (class "hidden").
    deflection: chord tolerance in metres for curve discretisation (default diag/1500, min 1 mm)."""
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
    t0 = time.perf_counter()
    shape, parts = _model_parts(model_or_shape)
    whole = _wrapped(shape)
    n, right, _upv = view_frame(view, up)
    ax2 = gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(*n), gp_Dir(*right))
    defl = float(deflection) if deflection else max(_diag(whole) / 1500.0, 1e-3)
    named = {k: _wrapped(v) for k, v in parts.items()} or {"body": whole}
    lines = []
    for name, r in _hlr(named, ax2, hidden=hidden, defl=defl).items():
        for pl in r["sharp"] + r["outline"]:
            lines.append({"cls": "visible", "part": name, "pts": pl})
        for pl in r["smooth"]:
            lines.append({"cls": "detail", "part": name, "pts": pl})
        for pl in r.get("hidden", []):
            lines.append({"cls": "hidden", "part": name, "pts": pl})
    if silhouette:
        whole_r = _hlr({"*": whole}, ax2, defl=defl)["*"]
        for pl in _on_silhouette(whole_r["outline"] + whole_r["sharp"] + whole_r["smooth"], tol=max(defl * 0.5, 1e-4)):
            lines.append({"cls": "outline", "part": "*", "pts": pl})
    meta = {"view": view if isinstance(view, str) else list(view), "toward_camera": list(n), "right": list(right),
            "deflection": defl, "parts": sorted(named), "hlr_s": round(time.perf_counter() - t0, 3), "hidden": bool(hidden)}
    return Drawing(lines, _bbox(lines), meta)


# ---------------------------------------------------------------------------------------------------------------
def _chain(segs, tol=1e-6):
    """Join open polylines end-to-end into longer ones."""
    segs = [list(s) for s in segs]
    out = []
    while segs:
        cur = segs.pop()
        grew = True
        while grew:
            grew = False
            for i, s in enumerate(segs):
                for a, b, rev_s, at_end in ((cur[-1], s[0], False, True), (cur[-1], s[-1], True, True),
                                            (cur[0], s[-1], False, False), (cur[0], s[0], True, False)):
                    if abs(a[0] - b[0]) < tol and abs(a[1] - b[1]) < tol:
                        t = s[::-1] if rev_s else s
                        cur = cur + t[1:] if at_end else t[:-1] + cur
                        segs.pop(i)
                        grew = True
                        break
                if grew:
                    break
        out.append(cur)
    return out


def section(model_or_shape, plane="xz", offset=0.0, deflection=None) -> Drawing:
    """Cut the model with an axis plane and return the contour as a Drawing of cls "section" (per part).

    plane "xz" (normal y; coords (x, z) = a longitudinal section), "yz" (normal x; coords (y, z) = a cross-section,
    e.g. a hull section at x = offset), "xy" (normal z; coords (x, y) = a waterplane / deck plan at z = offset)."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
    from OCP.gp import gp_Dir, gp_Pln, gp_Pnt
    spec = {"xz": ((0, 1, 0), (0, offset, 0), (0, 2)), "yz": ((1, 0, 0), (offset, 0, 0), (1, 2)),
            "xy": ((0, 0, 1), (0, 0, offset), (0, 1))}
    if plane not in spec:
        raise ValueError(f"plane must be one of {sorted(spec)}")
    nrm, org, (ia, ib) = spec[plane]
    pln = gp_Pln(gp_Pnt(*org), gp_Dir(*nrm))
    shape, parts = _model_parts(model_or_shape)
    named = {k: _wrapped(v) for k, v in parts.items()} or {"body": _wrapped(shape)}
    defl = float(deflection) if deflection else max(_diag(_wrapped(shape)) / 1500.0, 1e-3)
    lines = []
    for name, s in named.items():
        sec = BRepAlgoAPI_Section(s, pln, True)
        sec.Build()
        if not sec.IsDone():
            continue
        from OCP.BRepAdaptor import BRepAdaptor_Curve
        from OCP.GCPnts import GCPnts_QuasiUniformDeflection
        from OCP.TopAbs import TopAbs_EDGE
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopoDS import TopoDS
        segs = []
        ex = TopExp_Explorer(sec.Shape(), TopAbs_EDGE)
        while ex.More():
            c = BRepAdaptor_Curve(TopoDS.Edge_s(ex.Current()))
            ex.Next()
            g = GCPnts_QuasiUniformDeflection(c, defl, c.FirstParameter(), c.LastParameter())
            if g.IsDone() and g.NbPoints() >= 2:
                p3 = [g.Value(i) for i in range(1, g.NbPoints() + 1)]
            else:
                p3 = [c.Value(c.FirstParameter()), c.Value(c.LastParameter())]
            segs.append([((p.X(), p.Y(), p.Z())[ia], (p.X(), p.Y(), p.Z())[ib]) for p in p3])
        for pl in _chain(segs):
            lines.append({"cls": "section", "part": name, "pts": pl})
    return Drawing(lines, _bbox(lines), {"plane": plane, "offset": offset, "parts": sorted(named)})


# ---------------------------------------------------------------------------------------------------------------
def cache_key(name, params, view, hidden=False, silhouette=True):
    blob = json.dumps({"p": params or {}, "v": view if isinstance(view, str) else list(view), "h": bool(hidden),
                       "s": bool(silhouette), "ver": CACHE_VERSION}, sort_keys=True, default=str)
    h = hashlib.sha1(blob.encode()).hexdigest()[:12]
    vtag = view if isinstance(view, str) else "v" + "_".join(f"{c:g}" for c in view)
    return f"{name}_{vtag}_{h}"


def cache_path(name, params=None, view="side", hidden=False, silhouette=True, cache_dir=None):
    return Path(cache_dir or CACHE_DIR) / (cache_key(name, params, view, hidden, silhouette) + ".json")


def project_cached(name, params=None, view="side", hidden=False, silhouette=True, cache_dir=None, refresh=False) -> Drawing:
    """project() of the registered asset `name` built with `params`, cached on disk keyed by (name, params hash, view).
    A cache hit loads JSON only (no OpenCASCADE work)."""
    path = cache_path(name, params, view, hidden, silhouette, cache_dir)
    if path.exists() and not refresh:
        return Drawing.from_dict(json.loads(path.read_text()))
    from offsim.assets.cad import base
    d = project(base.build(name, **(params or {})), view, hidden=hidden, silhouette=silhouette)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(d.to_dict()))
    tmp.replace(path)
    return d


# ---------------------------------------------------------------------------------------------------------------
def _palette(style):
    from offsim.cinema.look import PALETTES
    return PALETTES[style.get("palette", "section-plan")]


def _poly_len_px(px):
    return sum(math.hypot(px[i + 1][0] - px[i][0], px[i + 1][1] - px[i][1]) for i in range(len(px) - 1))


def draw(canvas, drawing: Drawing, to_px, style=None) -> dict:
    """Render a Drawing on an offsim.cinema.draw.Canvas. to_px(x_m, y_m) -> (px, py) in 1x pixels (y already flipped
    by the caller). style keys (all optional): palette ("section-plan"), ink, muted, weights {cls: px}, show_hidden
    (False), min_px (0.75), part_colors {part: colour}, part_weight_scale {part: factor}, alpha, hidden_dash.
    Order: hidden, detail, visible, section, outline (heavier on top). Polylines shorter than min_px on screen are
    dropped. Returns {"drawn": n, "dropped": n, "by_class": {...}, "px_per_m": s}."""
    style = style or {}
    pal = _palette(style)
    ink, muted = style.get("ink", pal["ink"]), style.get("muted", pal["muted"])
    wts = {**WEIGHTS, **style.get("weights", {})}
    min_px = float(style.get("min_px", MIN_PX))
    pc, pws = style.get("part_colors", {}), style.get("part_weight_scale", {})
    alpha = style.get("alpha")
    o, ex = to_px(0.0, 0.0), to_px(1.0, 0.0)
    scale = math.hypot(ex[0] - o[0], ex[1] - o[1])
    stats = {"drawn": 0, "dropped": 0, "by_class": {}, "px_per_m": scale}
    order = ["hidden", "detail", "visible", "section", "outline"]
    for cls in order:
        if cls == "hidden" and not style.get("show_hidden"):
            continue
        for l in drawing.lines:
            if l["cls"] != cls:
                continue
            px = [to_px(x, y) for x, y in l["pts"]]
            if _poly_len_px(px) < min_px:
                stats["dropped"] += 1
                continue
            w = wts[cls] * pws.get(l["part"], 1.0)
            if cls == "hidden":
                canvas.line(px, muted, w, dash=style.get("hidden_dash", HIDDEN_DASH), alpha=alpha)
            else:
                col = pc.get(l["part"], muted if cls == "detail" else ink)
                canvas.line(px, col, w, alpha=alpha)
            stats["drawn"] += 1
            stats["by_class"][cls] = stats["by_class"].get(cls, 0) + 1
    return stats


def to_svg(drawing: Drawing, path, weights=None, px_per_m=20.0, margin_px=12, ink="#111111", muted="#666666",
           background="#ffffff", show_hidden=False, min_px=MIN_PX):
    """Write a standalone SVG (y flipped, metres scaled by px_per_m). Stroke widths are px (WEIGHTS, overridable)."""
    wts = {**WEIGHTS, **(weights or {})}
    x0, y0, x1, y1 = drawing.bbox
    W = (x1 - x0) * px_per_m + 2 * margin_px
    H = (y1 - y0) * px_per_m + 2 * margin_px
    def P(p):
        return f"{(p[0] - x0) * px_per_m + margin_px:.2f},{(y1 - p[1]) * px_per_m + margin_px:.2f}"
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.1f}" height="{H:.1f}" viewBox="0 0 {W:.1f} {H:.1f}">',
           f'<rect width="100%" height="100%" fill="{background}"/>']
    for cls in ("hidden", "detail", "visible", "section", "outline"):
        if cls == "hidden" and not show_hidden:
            continue
        col = muted if cls in ("hidden", "detail") else ink
        dash = f' stroke-dasharray="{HIDDEN_DASH[0]:g} {HIDDEN_DASH[1]:g}"' if cls == "hidden" else ""
        for l in drawing.lines:
            if l["cls"] != cls or _poly_len_px([((a * px_per_m), (b * px_per_m)) for a, b in l["pts"]]) < min_px:
                continue
            out.append(f'<polyline class="{cls}" data-part="{l["part"]}" fill="none" stroke="{col}" stroke-width="{wts[cls]}"'
                       f' stroke-linejoin="round" stroke-linecap="round"{dash} points="{" ".join(P(p) for p in l["pts"])}"/>')
    out.append("</svg>")
    Path(path).write_text("\n".join(out))
    return str(path)


# ===============================================================================================================
# Multi-view sprite-sheet projection and the gale film's section-frame adapter (merged from Nordlys N1, R1 reconcile).
# `project_classes` is Nordlys's original `project(shape, view, deflection)`: it returns {class: [polyline]} in view
# (u, v) metres with v up, over views side/front/rear/top/three-quarter. It is renamed because `project` above (the
# repo API) returns a Drawing; the two have different signatures (3rd arg `up` vs `deflection`) and return types.
# ===============================================================================================================
import numpy as np  # noqa: E402

from offsim.assets.cad.base import build as _build_asset  # noqa: E402

try:
    import cadquery  # noqa: F401  (the kernel; its absence is handled by the caller falling back)
    _CADQUERY = True
except ImportError:
    _CADQUERY = False

_W1, _W2, _W3 = 2.2, 1.2, 0.7   # v10: silhouette 3.0 -> 2.2, structure 1.4 -> 1.2 (outline goes down)
_DEFLECTION = 0.05          # m; HLR edge sampling
_DRAUGHT = 6.2              # waterline above keel in the asset frame
_HALF_L = 42.5

# Orthographic views for sprite sheets (CAD drafting): view name -> (view direction N, horizontal
# axis Vx, v_sign). N points from the object toward the viewer; Vx is the image-right axis; the
# image-up axis is Vy = N x Vx, and v_sign flips it when Vy points down (side view: Vy = -z).
# The default view is "side", identical to the original port-side projection, so the gale film's
# psv_profile_cad is untouched. The three-quarter view looks from front-starboard-above: the nose
# reads to the right and the starboard side (rescue hoist) shows.
_VIEWS = {
    "side": ((0, 1, 0), (1, 0, 0), -1),
    "front": ((1, 0, 0), (0, 1, 0), +1),
    "rear": ((-1, 0, 0), (0, -1, 0), +1),
    "top": ((0, 0, 1), (1, 0, 0), +1),
    "three-quarter": ((1, -1, 0.7), (1, 1, 0), +1),
}


def _hlr_compounds(shape, direction=(0, 1, 0), x_dir=(1, 0, 0)):
    """Run the OCP hidden-line algorithm on a cadquery Shape; return the HLRToShape object.
    direction = view direction N (object -> viewer); x_dir = image-right axis Vx."""
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
    from OCP.HLRAlgo import HLRAlgo_Projector
    from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape

    algo = HLRBRep_Algo()
    algo.Add(shape.wrapped)
    ax = gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(*direction), gp_Dir(*x_dir))
    algo.Projector(HLRAlgo_Projector(ax))
    algo.Update()
    algo.Hide()
    return HLRBRep_HLRToShape(algo)


def _discretize_edge(edge, deflection=_DEFLECTION):
    """A TopoDS_Edge -> list of (u, v) points in the projector's local frame (raw: X along Vx,
    Y along Vy = N x Vx). The caller flips Y when the view's up axis points down."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GCPnts import GCPnts_QuasiUniformDeflection

    adaptor = BRepAdaptor_Curve(edge)
    disc = GCPnts_QuasiUniformDeflection(adaptor, deflection)
    if disc.NbPoints() < 2:
        return []
    return [(disc.Value(i).X(), disc.Value(i).Y()) for i in range(1, disc.NbPoints() + 1)]


def _edges_of(compound, deflection=_DEFLECTION):
    """All edges of a (possibly null) TopoDS_Shape -> list of discretized polylines."""
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer

    if compound is None or compound.IsNull():
        return []
    from OCP.TopoDS import TopoDS

    out = []
    exp = TopExp_Explorer(compound, TopAbs_EDGE)
    while exp.More():
        pts = _discretize_edge(TopoDS.Edge_s(exp.Current()), deflection)
        if len(pts) >= 2:
            out.append(pts)
        exp.Next()
    return out


def view_direction(view="side"):
    """The view direction N (object -> viewer) for an orthographic view."""
    if view not in _VIEWS:
        raise ValueError(f"unknown view {view!r}; known: {sorted(_VIEWS)}")
    return _VIEWS[view][0]


def project_point(p, view="side"):
    """Project one 3D point (x, y, z) into a view's (u, v) metres with v up — the same
    projection the HLR projector applies (local X along Vx, local Y along N x Vx, flipped
    by the view's v_sign). Used for honest 2D glass in the three-quarter view: a 3D quad
    on the body surface projects to the same parallelogram the HLR edges would bound."""
    import numpy as np

    if view not in _VIEWS:
        raise ValueError(f"unknown view {view!r}; known: {sorted(_VIEWS)}")
    direction, x_dir, v_sign = _VIEWS[view]
    n = np.array(direction, dtype=float)
    n /= np.linalg.norm(n)
    vx = np.array(x_dir, dtype=float)
    vx /= np.linalg.norm(vx)
    vy = np.cross(n, vx)
    p = np.array(p, dtype=float)
    return (float(np.dot(p, vx)), v_sign * float(np.dot(p, vy)))


def project_classes(shape, view="side", deflection=_DEFLECTION):
    """HLR-project a cadquery Shape from one orthographic view. Returns {class: [polyline, ...]}
    in view (u, v) metres with v up. Classes: silhouette (outline), visible (sharp), smooth
    (visible smooth edges), hidden (hidden sharp + smooth). The default view is "side" (the
    port side, x forward, z up) — identical to the original projection, so the gale film's
    psv_profile_cad is untouched. Other views: "front" (nose on, y right, z up), "rear",
    "top" (nose right, port up), "three-quarter" (front-starboard-above, nose right).
    `deflection` is the HLR edge sampling (m): the default 0.05 m is the film value; the
    sprite sheet uses 0.005 m, so wheel circles draw with ~22 segments instead of ~7
    (round-1 nit: wheel octagons visible at full size)."""
    if view not in _VIEWS:
        raise ValueError(f"unknown view {view!r}; known: {sorted(_VIEWS)}")
    direction, x_dir, v_sign = _VIEWS[view]
    hlr = _hlr_compounds(shape, direction, x_dir)
    flip = lambda pts: [(u, v_sign * v) for u, v in pts]
    return {
        "silhouette": [flip(p) for p in _edges_of(hlr.OutLineVCompound(), deflection)],
        "visible": [flip(p) for p in _edges_of(hlr.VCompound(), deflection)],
        "smooth": [flip(p) for p in _edges_of(hlr.Rg1LineVCompound(), deflection) + _edges_of(hlr.RgNLineVCompound(), deflection)],
        "hidden": [flip(p) for p in _edges_of(hlr.HCompound(), deflection) + _edges_of(hlr.Rg1LineHCompound(), deflection)
                   + _edges_of(hlr.RgNLineHCompound(), deflection)],
    }


def project_outline(shape, view="side", deflection=_DEFLECTION):
    """The silhouette outline polylines of a shape in one view, in (u, v) metres with v up.
    Used to stitch a fill loop for one part (the body silhouette fill on a sprite)."""
    direction, x_dir, v_sign = _VIEWS[view]
    hlr = _hlr_compounds(shape, direction, x_dir)
    return [[(u, v_sign * v) for u, v in p] for p in _edges_of(hlr.OutLineVCompound(), deflection)]


def _stitch_loop(polylines, tol=1e-4, jump=False):
    """Join endpoint-matching polylines into one closed polygon (for the hull silhouette fill).
    Returns the polygon points, or None if the loop does not close. With jump=True, a chain
    end with no exact match connects to the nearest remaining endpoint with a straight line
    (a loft's silhouette splits into an outline chain and a visible chain whose ends are the
    end-cap lines — the jump is the cap), and the loop is closed with a straight segment."""
    segs = [list(p) for p in polylines if len(p) >= 2]
    if not segs:
        return None
    loop = segs.pop(0)
    guard = 0
    while segs and guard < 10000:
        guard += 1
        end = loop[-1]
        best, best_d, flip = None, tol, False
        for i, s in enumerate(segs):
            for cand, fl in ((s[0], False), (s[-1], True)):
                d = abs(cand[0] - end[0]) + abs(cand[1] - end[1])
                if d < best_d:
                    best, best_d, flip = i, d, fl
        if best is None:
            if not jump:
                return None
            # nearest remaining endpoint, any distance — the jump line is the cap
            best2, best_d2, flip2 = None, math.inf, False
            for i, s in enumerate(segs):
                for cand, fl in ((s[0], False), (s[-1], True)):
                    d = abs(cand[0] - end[0]) + abs(cand[1] - end[1])
                    if d < best_d2:
                        best2, best_d2, flip2 = i, d, fl
            if best2 is None:
                return None
            s = segs.pop(best2)
            loop.extend(list(reversed(s)) if flip2 else list(s))
            continue
        s = segs.pop(best)
        loop.extend(reversed(s[:-1]) if flip else s[1:])
    if abs(loop[0][0] - loop[-1][0]) + abs(loop[0][1] - loop[-1][1]) > tol:
        if not jump:
            return None
        loop.append(loop[0])
    return loop


def _clip_band(poly, z0, z1):
    """Clip a polygon to the horizontal band z0 <= z <= z1 (Sutherland-Hodgman, two half-planes).
    Used for the boot-top stripe: the hull silhouette clipped to the waterline band."""
    def clip_half(pts, keep, z):
        if not pts:
            return []
        out = []
        n = len(pts)
        for i in range(n):
            a, b = pts[i - 1], pts[i]
            za, zb = a[1], b[1]
            ina, inb = keep(za, z), keep(zb, z)
            if inb:
                if not ina:
                    t = (z - za) / (zb - za) if zb != za else 0.0
                    out.append((a[0] + (b[0] - a[0]) * t, z))
                out.append(b)
            elif ina:
                t = (z - za) / (zb - za) if zb != za else 0.0
                out.append((a[0] + (b[0] - a[0]) * t, z))
        return out
    return clip_half(clip_half(poly, lambda zz, z: zz >= z, z0), lambda zz, z: zz <= z, z1)


def _arc(xc, zc, r, a0, a1, n=10):
    a = np.linspace(a0, a1, n)
    return list(zip(xc + r * np.cos(a), zc + r * np.sin(a)))


_CAD_CACHE = {}


def _cad_prims_local():
    """CAD linework + fills for the PSV in local section coords (u = metres from the bow,
    w = metres above the waterline), cached. Built once from the asset."""
    if "prims" in _CAD_CACHE:
        return _CAD_CACHE["prims"]
    from offsim.assets.cad import marine_film as marine

    asset = _build_asset("psv_v10")
    classes = project_classes(asset.shape)
    to_local = lambda x, z: (_HALF_L - x, z - _DRAUGHT)
    P = []

    def _poly(pts, w, fill, outline):
        P.append(("poly", [to_local(x, z) for x, z in pts], w, fill, outline))

    def _line(pts, w, outline):
        P.append(("line", [to_local(x, z) for x, z in pts], w, None, outline))

    # fills: hull silhouette (stitched loop of the hull part's own outline), then analytic part rects.
    # v10 shading over outline: the hull is NOT one flat fill inside a bright outline — that is the
    # cartoon recipe. Light from above: three value bands clipped from the silhouette (sheer
    # lightest, keel darkest), and NO outline on any fill: the HLR silhouette carries the edge,
    # at the reduced weight above. Fill edges and HLR edges agree by construction.
    hull_loop = _stitch_loop(project_outline(asset.parts["hull"], "side"))
    if hull_loop is None:                       # fallback: the construction control polygon
        hull_loop = marine._hull_profile_points()
    for z0, z1, fill in ((_DRAUGHT + 4.5, 14.3, "hull_top"), (_DRAUGHT, _DRAUGHT + 4.5, "hull"),
                         (0.0, _DRAUGHT, "hull_low")):
        band = _clip_band(hull_loop, z0, z1)
        if len(band) >= 3:
            _poly(band, _W3, fill, None)
    # v9: boot-top stripe — the hull silhouette clipped to the waterline band (z 6.2-7.8, i.e.
    # 0-1.6 m above the waterline), a muted brick tone that breaks up the hull slab. A working
    # ship's hull is not one flat colour; the stripe is the cheapest honest structure on it.
    _band = _clip_band(hull_loop, _DRAUGHT, _DRAUGHT + 1.6)
    if len(_band) >= 3:
        _poly(_band, _W3, "boot", "ink")
    # v10: superstructure steps up one value per tier (light from above); funnel is a tapered body
    # + cap with a colour band across the taper. No outlines on fills — HLR carries every edge.
    for (x0, x1, z0, z1), fill in zip(
            ((19.5, 39.5, 13.7, 16.7), (20.5, 38.5, 16.7, 19.7), (21.5, 37.5, 19.7, 22.3)),
            ("house", "house_mid", "house_top")):
        _poly([(x0, z0), (x1, z0), (x1, z1), (x0, z1)], _W2, fill, None)
    _poly([(20.0, 22.3), (38.5, 22.3), (38.5, 25.3), (21.2, 25.3)], _W1, "bridge", None)  # bridge
    _poly([(17.0, 19.7), (20.5, 19.7), (20.1, 26.5), (17.4, 26.5)], _W1, "funnel", None)  # funnel body
    _poly([(17.0, 25.5), (20.5, 25.5), (20.5, 26.5), (17.0, 26.5)], _W1, "funnel", None)  # cap
    # funnel band, z 24.3-25.3, interpolated across the taper (left edge 17.0@19.7 -> 17.4@26.5,
    # right edge 20.5@19.7 -> 20.1@26.5): the band is what stops the funnel reading as a rectangle.
    _poly([(17.27, 24.3), (20.23, 24.3), (20.17, 25.3), (17.33, 25.3)], _W3, "funnel_band", None)
    # windows: dark glass with variation, no outline. The v9 white squares were the bright ink
    # outline around each 1.1 m rect (the fill was already dark); the window boxes are gone from
    # the solid, so no HLR rectangle survives either. Bridge glazing: one dark band + mullions.
    for x0, x1, z0, z1 in ((19.5, 39.5, 13.7, 16.7), (20.5, 38.5, 16.7, 19.7), (21.5, 37.5, 19.7, 22.3)):
        for i, x in enumerate(range(int(x0) + 2, int(x1) - 1, 2)):                          # window rows
            _poly([(x, z0 + 1.1), (x + 1.1, z0 + 1.1), (x + 1.1, z0 + 2.2), (x, z0 + 2.2)],
                  _W3, "glass" if i % 2 == 0 else "glass_dim", None)
    _poly([(20.6, 23.3), (38.0, 23.3), (38.0, 24.7), (20.6, 24.7)], _W3, "glass", None)  # bridge band
    _poly([(23.0, 17.1), (28.5, 17.1), (28.5, 18.3), (23.0, 18.3)], _W3, "accent_fill", None)  # rescue boat
    for u, w, h in ((30, 6.1, 2.6), (37, 6.1, 2.6), (44, 12.2, 2.6), (58, 6.1, 5.2)):     # cargo
        x0, x1 = 42.5 - (u + w), 42.5 - u
        _poly([(x0, 10.7), (x1, 10.7), (x1, 10.7 + h), (x0, 10.7 + h)], _W2, "cargo", None)
    for k in range(4):                                                                       # pipe stack
        x = 42.5 - (68 + k * 1.1)
        _poly(_arc(x, 11.25 + (k % 2) * 0.9, 0.5, 0, 2 * np.pi), _W3, None, "ink")
    # HLR edges of the fused solid: the CAD linework itself
    for pts in classes["silhouette"]:
        _line(pts, _W1, "ink")
    for pts in classes["visible"]:
        _line(pts, _W2, "ink")
    for pts in classes["smooth"]:
        _line(pts, _W3, "ink")
    for pts in classes["hidden"]:
        _line(pts, _W3, "line_faint")
    # 2D drafting detail (construction lines, not CAD parts — the same device as the boot-top line
    # below): hull plating seams + butt joints, draft marks, rail stanchions. All in asset (x, z).
    for z in (8.2, 9.6):                                            # plating seams along the hull side
        _line([(-37.5, z), (34.5, z)], _W3, "line_faint")
    for x in (26.5, 18.5, 10.5, 2.5, -5.5, -13.5, -21.5, -29.5):  # butt joints between the seams
        _line([(x, 8.2), (x, 9.6)], _W3, "line_faint")
    _line([(-42.0, 6.2), (-42.0, 10.7)], _W3, "ink")               # stern draft rule (transom is vertical)
    for z in (6.2, 7.2, 8.2, 9.2, 10.2):
        _line([(-42.0, z), (-40.8, z)], _W3, "ink")
    def _stem_x(z):                                                 # stem curve, linear on the spline legs
        if z <= 7.2:
            return 36.5 + 3.5 * (z - 0.8) / 6.4
        return 40.0 + 2.5 * (z - 7.2) / 7.1
    for z in (6.2, 7.2, 8.2, 9.2, 10.2):                           # bow draft ticks across the stem
        sx = _stem_x(z)
        _line([(sx - 0.8, z), (sx + 0.8, z)], _W3, "ink")
    for u in range(2, 24, 2):                                       # forecastle-deck rail stanchions
        _line([(42.5 - u, 13.7), (42.5 - u, 14.8)], _W3, "ink")
    _line([(42.5 - 2, 14.8), (42.5 - 22, 14.8)], _W3, "ink")
    for u in range(4, 22, 2):                                       # bridge-top rail stanchions
        _line([(42.5 - u, 25.3), (42.5 - u, 26.4)], _W3, "ink")
    _line([(42.5 - 4, 26.4), (42.5 - 20, 26.4)], _W3, "ink")
    # v10: NO crew. The v7-v9 scale figures were stick-men (circle head + three lines); a ship with
    # no crew reads more technical than a ship with stick-men. Proper scale figures are a separate
    # piece of work, not a two-line annotation.
    # boot-top line (waterline detail, as in v7): asset coords, z = waterline + 0.35
    _line([(39.3, 6.55), (-42.0, 6.55)], _W3, "accent_dim")
    _CAD_CACHE["prims"] = P
    _CAD_CACHE["classes"] = classes
    return P


def psv_profile_cad(x0, z0, length=85.0, pitch_rad=0.0, pivot=None):
    """Drop-in for vessel_lineart.psv_profile: (prims, solids, exhaust) in section coords.
    The prims are the CAD HLR linework; the solids and the exhaust point are the v7 values,
    unchanged, so the fluid mask and every measured number are identical."""
    from offsim.cinema.vessel_lineart import psv_profile

    if not _CADQUERY:
        raise ImportError("cadquery is not installed; the CAD profile needs the OpenCASCADE kernel")
    if abs(length - 85.0) > 1e-9:
        raise ValueError(f"CAD PSV is built at LOA 85 m; got length={length}")
    _, solids, exhaust = psv_profile(x0, z0, length, pitch_rad, pivot)
    prims = [(k, [(x0 + u, z0 + w) for u, w in pts], wt, f, o)
             for k, pts, wt, f, o in _cad_prims_local()]
    if pitch_rad and pivot is not None:
        c, s = np.cos(pitch_rad), np.sin(pitch_rad)
        rot = lambda pts: [(pivot[0] + (x - pivot[0]) * c - (z - pivot[1]) * s,
                            pivot[1] + (x - pivot[0]) * s + (z - pivot[1]) * c) for x, z in pts]
        prims = [(k, rot(p), w, f, o) for k, p, w, f, o in prims]
    return prims, solids, exhaust
