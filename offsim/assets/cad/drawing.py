"""Drawing engine: exact CAD solids -> CAD-grade line art (the Rhino Make2D / drafting look).

    d = project(model, view="side")                  # exact hidden-line removal (OpenCASCADE HLR), metres in the view plane
    d = project_cached("psv", {"loa_m": 85}, "side") # same, cached to out/cache/cad/*.json (films never run HLR per frame)
    s = section(model, plane="xz", offset=0.0)       # cut contour (hull cross-section etc.) as a Drawing of cls "section"
    n = draw(canvas, d.transformed(angle=pitch, dy=heave), to_px, style)   # offsim.cinema.draw.Canvas
    to_svg(d, "out.svg")

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
