"""Hidden-line projection of CAD assets into classed 2D polylines (the Rhino Make2D / CAD drafting look).

    classes = project(shape)          # {"silhouette": [...], "visible": [...], "smooth": [...], "hidden": [...]}
    prims, solids, exhaust = psv_profile_cad(x0, z0)   # section-frame adapter for the gale film

Projection: OpenCASCADE HLR (HLRBRep_Algo) looking along +y (port side), so the projection plane is
(x, z) — asset x forward maps to the section's u = 42.5 - x (bow at u=0). Edge classes follow the
contract (offsim/assets/cad/base.py): silhouette / visible / hidden (+ smooth edges as their own class).
The fluid obstacle mask and the exhaust point are NOT recomputed from the CAD solid: they are the v7
psv_profile values, unchanged, so the section physics and every measured number are identical — only
the drawing is CAD. Fills come from the construction profiles (analytic rectangles + the stitched hull
silhouette), so fill edges and HLR edges agree by construction.
"""
from __future__ import annotations

import math

import numpy as np

from offsim.assets.cad.base import build as _build_asset

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


def project(shape, view="side", deflection=_DEFLECTION):
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
    from offsim.assets.cad import marine

    asset = _build_asset("psv")
    classes = project(asset.shape)
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
