"""CAD sprite sheets: orthographic views of registered assets, drawn with the same HLR + skia
line renderer as the PSV (offsim/assets/cad/drawing.py, offsim/cinema/draw.py).

A sprite sheet is a drafting document, not a film frame, so the polarity flips: light paper
(#E8E1CF, the films' PAPER tone) with dark ink, instead of light ink on dark ground. The
line-weight hierarchy is four tiers (silhouette 2.6 / structure 1.5 / smooth 0.9 / detail 0.5),
the fills are the same maroon family in pale tints, and every number on the sheet comes from QA
(offsim/assets/cad/qa.py) or from the measured projections — never typed by hand.

Layout (3000x2120, A4 landscape): three rows — the S-92's four orthographic views + a
dimension callout on each measured view; a detail row (rotor-head, landing-gear and tail-rotor
close-ups at ~8x the sheet scale, each with part labels); the bus's five orthographic views
(SIDE, FRONT, REAR, TOP, THREE-QUARTER). One scale per asset across its views (a sprite
sheet keeps scale within an asset; the scale bar states it). Glazing and panel lines are the
asset's 2D details (air.s92_sprite_details, land.bus_sprite_details); the three-quarter view
carries projected 3D glass (air.s92_glass_3d, land.bus_glass_3d), not flat rects.
Part labels with leaders name the parts on the side views; dimension callouts (length,
height, rotor diameter, width) are drawn from QA-measured values with extension lines.
"""
from __future__ import annotations

import math

from offsim.assets.cad import drawing as D
from offsim.assets.cad.base import build as _base_build

# The sheet's logical asset names (rows, QA manifest keys) -> the registered Nordlys sprite builders. They are
# separate registered assets from the repo's s92/bus (different parts, all-assumed dims): see R1 report.
SPRITE_BUILDERS = {"s92": "s92_sprite", "bus": "bus_sprite"}


def _build_asset(name):
    return _base_build(SPRITE_BUILDERS.get(name, name))
from offsim.cinema.draw import Canvas
from offsim.cinema.vessel_lineart import FILLS as _FILLS

VIEWS = ("side", "front", "rear", "top", "three-quarter")
VIEW_TITLES = {"side": "SIDE", "front": "FRONT", "rear": "REAR", "top": "TOP",
               "three-quarter": "THREE-QUARTER"}

# Light-paper palette: same warm family as the films, pale tints for fills, dark ink.
PAPER = "#E8E1CF"
INK = "#2a161a"
INK_FAINT = "#8a6f68"
SHEET_FILLS = dict(_FILLS)
SHEET_FILLS.update({
    "house": "#c9a98c", "house_mid": "#b99a88", "house_top": "#cbb59f",
    "house_faint": "#ddd2bd",  # faint solid for the fin in the tail-rotor zoom
    "hull": "#b99a88", "hull_top": "#cbb59f", "hull_low": "#a98878",
    "glass": "#26333a", "glass_dim": "#3a4a52", "wheel": "#241a1c",
    "accent": "#8a5a2a", "funnel_band": "#7a4038", "boot": "#5c3532",
})
SHEET_STROKES = {"ink": INK, "line_faint": INK_FAINT, "accent_dim": "#b07a2a"}

W1, W2, W3, W4 = 2.6, 1.5, 0.9, 0.5   # silhouette / structure / smooth / detail
SHEET_DEFLECTION = 0.005               # HLR edge sampling (m); the film default is 0.05 —
                                       # at 0.005 a 0.50 m wheel circle draws with ~22 segments
                                       # instead of ~7 (round-1 nit: wheel octagons at full size)
ZOOM_DEFLECTION = 0.001                # finer sampling for the detail zooms: at ~200 px/m a
                                       # 0.005 m wheel circle still shows its flats (round-2
                                       # whipster catch — the gear zoom wheel was a polygon)

# --- sheet layout: one row per entry -------------------------------------------------------------
ROWS = [
    {"asset": "s92", "title": "S-92 — OFFSHORE HELICOPTER",
     "subtitle": "Gribkovskaia fleet · Bergen program", "kind": "views",
     "cells": [{"view": v} for v in ("side", "front", "top", "three-quarter")]},
    {"asset": "s92", "title": "S-92 — DETAILS",
     "subtitle": "Close-ups at larger scale",
     "kind": "zooms",
     "cells": [{"zoom": z} for z in ("rotor_head", "gear", "tail_rotor")]},
    {"asset": "bus", "title": "FRAM 701 — CITY BUS",
     "subtitle": "Kvam–Molde–Årølia · Molde film", "kind": "views",
     "cells": [{"view": v} for v in ("side", "front", "rear", "top", "three-quarter")]},
]

# Zoom-only 2D details (source-view (u, v) metres): mechanism too small to model as a
# part, but visible at zoom scale. Rotor head: pitch-link rods as FILLED BARS, 0.06 m
# wide (u 1.07..1.13 and 1.87..1.93), from inside the swashplate (z 4.75) to the grips
# (z 5.02), each with a filled crossbar reaching IN to the grip's inner end (aft grip
# u 0.55..0.95, fore grip u 2.05..2.45). The round-4 W2 line rods read as 1–2 px
# hairlines, the same weight as the leaders (round-5 whipster catch); at 242 px/m a
# real pitch link (~0.05 m) is ~12 px wide and filled, so the rods are bars now.
# Plus a filled mast-nut band at the mast top (the solid's collar reads as just
# another rectangle in linework-only zooms; round-3 whipster catch — the head was
# three stacked empty rectangles on an empty mast column). Landing gear: a panel seam
# across the sponson (the zoom's top half was three parallel lines over empty paper).
ZOOM_DETAILS = {
    "rotor_head": [("poly", [(1.07, 4.75), (1.13, 4.75), (1.13, 5.02), (1.07, 5.02)],
                    W3, "wheel", None),
                   ("poly", [(1.87, 4.75), (1.93, 4.75), (1.93, 5.02), (1.87, 5.02)],
                    W3, "wheel", None),
                   ("poly", [(0.95, 4.99), (1.18, 4.99), (1.18, 5.05), (0.95, 5.05)],
                    W3, "wheel", None),
                   ("poly", [(1.82, 4.99), (2.05, 4.99), (2.05, 5.05), (1.82, 5.05)],
                    W3, "wheel", None),
                   ("poly", [(1.30, 4.82), (1.70, 4.82), (1.70, 4.92), (1.30, 4.92)],
                    W3, "wheel", None)],
    "gear": [("line", [(-0.2, 1.70), (3.2, 1.70)], W4, None, "line_faint")],
    "tail_rotor": [],
}

# Detail zooms: (source view, region in view metres (umin, umax, vmin, vmax), corner labels).
# Corner labels: (text, anchor (u, v) in view metres, corner tl/tr/bl/br).
ZOOMS = {
    "rotor_head": {"title": "ROTOR HEAD", "source": "side",
                   "region": (0.2, 3.0, 3.5, 5.4),
                   "fill_parts": [],
                   "labels": [("ROTOR HEAD", (1.5, 5.08), "tr"),
                              ("AFT BLADE", (0.35, 5.05), "tl"),
                              ("MAST", (1.5, 4.25), "bl"),
                              ("SWASHPLATE", (1.90, 4.75), "br")]},
    "gear": {"title": "LANDING GEAR", "source": "side",
             "region": (-0.2, 3.2, 0.0, 2.2),
             "fill_parts": [],
             "labels": [("SPONSON", (0.6, 1.70), "tl"),
                        ("STRUT", (1.20, 1.05), "tr"),
                        ("MAIN WHEEL", (0.78, 0.45), "bl"),
                        ("HUB DISC", (1.35, 0.60), "br")]},
    "tail_rotor": {"title": "TAIL ROTOR", "source": "side",
                   "region": (-11.4, -8.2, 1.9, 5.3),
                   # fill order is back-to-front in the side view: the fin sits
                   # on the centreline (y +/-0.15) behind the blades and the
                   # stabiliser (y +/-2.00), so it is drawn FIRST — drawing it
                   # last (v10 as first built) covered the bar's fill where they
                   # overlap, leaving the bar paper inside its own outline.
                   "fill_parts": ["fin", "tail_rotor_blades", "stabilizer"],
                   "fill_tones": {"fin": "house_faint"},
                   "labels": [("TAIL ROTOR", (-9.8, 4.90), "tl"),
                              ("HUB", (-9.8, 3.60), "tr"),
                              ("FIN", (-9.2, 3.80), "br")]},
}

# Part labels on the main views: (text, anchor (u, v) in view metres, "above" | "below").
# Above/below labels are laid out by measured text width so same-height texts never overlap.
LABELS = {
    ("s92", "side"): [("ROTOR HEAD", (1.5, 5.08), "above"),
                      ("MAIN ROTOR BLADE", (6.0, 5.05), "above"),
                      ("ENGINE DECK", (-2.0, 4.10), "above"),
                      ("TAIL ROTOR", (-9.8, 4.60), "above"),
                      ("PITOT TUBE", (10.40, 2.20), "above")],
    ("bus", "side"): [("ROOF AC POD", (-0.5, 3.15), "above"),
                      ("REAR DOOR", (-0.05, 2.75), "above"),
                      ("FRONT DOOR", (4.95, 2.75), "above"),
                      ("DESTINATION DISPLAY", (5.30, 2.88), "above"),
                      ("MIRROR", (6.00, 2.55), "above"),
                      ("FRONT WHEEL", (4.0, 0.50), "below"),
                      ("REAR WHEEL", (-3.6, 0.50), "below")],
}
# Corner labels on the three-quarter view: (text, 3D anchor (x, y, z), corner).
LABELS_3D = {
    ("s92", "three-quarter"): [("RESCUE HOIST", (3.0, -1.56, 3.10), "br")],
}


def _loops(polys, tol=1e-3, jump=False):
    """Closed loops from projected polylines: already-closed polylines pass through as their
    own loop (wheel circles); the rest are stitched into one silhouette loop."""
    closed, open_segs = [], []
    for p in polys:
        if len(p) >= 3 and abs(p[0][0] - p[-1][0]) + abs(p[0][1] - p[-1][1]) <= tol:
            closed.append(p)
        elif len(p) >= 2:
            open_segs.append(list(p))
    stitched = D._stitch_loop(open_segs, jump=jump)
    if stitched:
        closed.append(stitched)
    return closed


def _mesh_fill_loops(shape, view, tol=0.05):
    """A part's projected silhouette(s) as closed polygons, from the solid's own mesh.

    Tessellate the solid, project every triangle into the view, and union them with
    shapely: the union of all projected faces is the silhouette by definition, so
    interior edges (section seams, profile kinks, arch rims) drop out and the fill
    can never be a self-intersecting zigzag. Replaces the endpoint-stitching fill,
    which silently produced invalid loops in most views (the bus top view filled as
    a diagonal triangle; the s92 3/4 fills were all invalid — measured 2026-11-11).
    Returns a LIST of loops: a part with disjoint components (the twin engine boxes,
    the two exhaust cylinders, the two gear sides) unions to a MultiPolygon, and
    every component gets its own fill. The old singular version kept only the
    largest component, so the S-92 front view filled one engine box and left the
    other paper-white (round-4 whipster catch — the two deck boxes read asymmetric,
    a pair of mismatched eyes). Each exterior ring is simplified to 1 cm so the fill
    stays a light polygon, not a 600-point mesh rim. Returns [] when the mesh is
    empty."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    # tessellate a COPY, never the part itself: tessellation stores a triangulation on
    # the shape's faces, and OpenCASCADE then computes BoundingBox() from that mesh —
    # the mesh (0.05 m deflection) overshoots the true surface by ~0.01 m per side, so
    # the fuselage bbox inflated 20.90 -> 20.92 m and the sheet printed "LENGTH 20.92 m"
    # (caught 2026-11-11 reading the v4 sheet: the QA value is right, the bbox was not).
    # The copy's tessellation leaves the asset's own bbox exact.
    try:
        verts, tris = shape.copy().tessellate(tol)
    except Exception:
        return []
    pts = [tuple(v) for v in verts]
    polys = []
    for a, b, c in tris:
        poly = Polygon([D.project_point(pts[a], view), D.project_point(pts[b], view),
                        D.project_point(pts[c], view)])
        if poly.is_valid and poly.area > 1e-12:
            polys.append(poly)
    if not polys:
        return []
    u = unary_union(polys)
    if u.is_empty:
        return []
    geoms = list(u.geoms) if u.geom_type == "MultiPolygon" else [u]
    loops = []
    for g in geoms:
        if g.geom_type != "Polygon" or g.is_empty:
            continue
        ring = g.exterior.simplify(0.01, preserve_topology=True)
        if ring.geom_type not in ("LineString", "LinearRing") or len(ring.coords) < 3:
            continue
        coords = list(ring.coords)
        if coords[0] != coords[-1]:
            coords.append(coords[0])
        loops.append(coords)
    return loops


def _valid_loop(loop):
    """A fill loop is shippable only if it is a valid (non-self-intersecting) polygon
    covering most of its own bounding box. Guards the stitch fallback below."""
    from shapely.geometry import Polygon
    if len(loop) < 3:
        return False
    poly = Polygon(loop)
    if not poly.is_valid or poly.area <= 0:
        return False
    us = [p[0] for p in loop]
    vs = [p[1] for p in loop]
    bb = (max(us) - min(us)) * (max(vs) - min(vs))
    return bb <= 0 or poly.area / bb > 0.5


def _drop_front_rings(classes, view, ref_bbox=None):
    """Front-view only: drop the loft section rings that read as ghost circles.
    A ruled-loft fuselage carries a ring at every section station; in the front view
    the rings project as concentric ellipses around the fuselage axis, and the inner
    ones read as a target/face inside the outer silhouette (round-5 whipster catch,
    finding 2 — the top view was fixed by the hidden-first draw order, but these
    rings are VISIBLE HLR edges on the nose-facing surface, so no draw order hides
    them). The v6 filter dropped only rings centred on the axis, so the quadrant arcs
    survived (round-6 whipster catch: an r 1.05 arc in the upper-right quadrant, an
    r 1.45 double rim, the equator seam chained in short segments, and a 5-pt dot).
    The reference is the fuselage part's own front-view bbox (u = y-range,
    v = z-range); the rule is RADIAL, not positional: a curved segment is dropped
    outright if its farthest point from the axis never reaches the outer rim
    (r_max < r_outer - 0.10), clipped to its lower half if it sits just inside the
    rim (r_outer - 0.10 <= r_max < r_outer - 0.02) — the upper half is a double rim
    where the outer silhouette already runs, but the lower half IS the outline there
    (no outer arc exists below the axis: the sponsons and gear hide it) — and kept
    if it reaches the rim. The dot is a tiny polyline at the axis just below the
    windshield; the equator seam is a near-horizontal line at the axis height running
    past the windshield's edge to the rim (the v6 filter needed one segment spanning
    >1.5 m; the seam is chained in short segments, so the rule is per-segment).
    The outer silhouette itself reaches the rim, so it is never dropped; straight
    panel lines and part outlines are not at the axis height, so they survive.
    Assets without a fuselage part (the bus) pass through unchanged."""
    if view != "front" or ref_bbox is None:
        return classes
    ru0, ru1, rv0, rv1 = ref_bbox
    cu, cv = (ru0 + ru1) / 2, (rv0 + rv1) / 2
    r_outer = max((ru1 - ru0) / 2, (rv1 - rv0) / 2)
    out = dict(classes)
    for cls in ("visible", "smooth"):
        kept = []
        for pts in classes.get(cls, []):
            if len(pts) < 2:
                kept.append(pts)
                continue
            us = [u for u, _ in pts]
            vs = [v for _, v in pts]
            u0, u1, v0, v1 = min(us), max(us), min(vs), max(vs)
            import math
            (x0, y0), (x1, y1) = pts[0], pts[-1]
            L = math.hypot(x1 - x0, y1 - y0) or 1.0
            dev = max(abs((y1 - y0) * x - (x1 - x0) * y + x1 * y0 - y1 * x0) / L
                      for x, y in pts) if len(pts) >= 3 else 0.0
            r_max = max(math.hypot(u - cu, v - cv) for u, v in pts)
            if len(pts) >= 8 and dev > 0.08:
                # (a) curved interior ring: never reaches the outer rim
                if r_max < r_outer - 0.10:
                    continue
                # (b) near-rim ring: keep only its lower half. BUT a short duplicate
                # ring (n=9, v-span 0.62, r 1.47) sits just outside the main lower
                # arc (r 1.45, n=17, v 0.96..2.30) — two parallel arcs in the lower
                # half read as a double outline (round-7 whipster catch: the lower
                # half does NOT have a single outline, it has two). Drop the short
                # duplicate; the longer arc is the single lower outline (0.05 m
                # inside the rim, ~1 px at sheet scale, invisible).
                if r_max < r_outer - 0.02:
                    if len(pts) < 12 and (v1 - v0) < 0.80:
                        continue
                    clipped = [(u, v) for u, v in pts if v <= cv + 0.02]
                    if len(clipped) >= 2:
                        kept.append(clipped)
                    continue
                kept.append(pts)
                continue
            # (c) the dot: a tiny polyline at the axis, just below the windshield
            if (len(pts) >= 3 and (u1 - u0) < 0.30 and (v1 - v0) < 0.30
                    and u0 > cu - 0.30 and u1 < cu + 0.30
                    and v0 > cv - 0.05 and v1 < cv + 0.20):
                continue
            # (e) short near-rim fragment in the lower half: the HLR splits the
            # outer loft ring into fragments, and a 3-pt fragment at r 1.50
            # (v 2.05..2.30, both sides) survives the len>=8 curved rules and
            # sits ~0.05 m outside the long r 1.45 lower outline — two parallel
            # arcs at 4-5 o'clock, a double rim (round-8 whipster catch, finding
            # 1, half-fixed: the v8 drop of the r 1.47 n=9 ring was not the only
            # duplicate). The long r 1.45 arc provides the lower-half outline,
            # so any short fragment wholly inside the near-rim band in the lower
            # half goes. The sponson top edge is a 2-pt line whose far point is
            # outside the band (r 1.97), so it survives; the equator seam and
            # the dot are not in the band, so (c)/(d) still own them.
            if len(pts) < 8:
                rs = [math.hypot(u - cu, v - cv) for u, v in pts]
                if (all(r_outer - 0.10 <= r <= r_outer + 0.02 for r in rs)
                        and v1 <= cv + 0.02):
                    continue
            # (d) the equator seam: near-horizontal at the axis height, past the
            # windshield's edge (the glass spans u +/-0.7, so anything past +/-0.8
            # at this height is seam, not glass)
            if (len(pts) == 2 and abs(v1 - v0) < 0.06
                    and abs((v0 + v1) / 2 - cv) < 0.08
                    and (u1 > cu + 0.80 or u0 < cu - 0.80)):
                continue
            kept.append(pts)
        out[cls] = kept
    return out


def view_prims(asset, view, fills_map, details_fn, glass3d_fn=None,
               deflection=SHEET_DEFLECTION):
    """Prims (kind, points, weight, fill, outline) in view metres for one view, plus the
    (u, v) bounds. Draw order: hidden lines first (an opaque fill must cover a hidden
    edge that falls under it — the old fills-first order made the rotor blades
    translucent in the top view, 415 hidden segments showing through, round-4
    whipster catch), then the fills, then silhouette / visible / smooth HLR edges,
    then the asset's 2D details. Fills: each part in fills_map contributes its
    silhouette loop(s) from the mesh union (see _mesh_fill_loops); the stitch path is
    only a fallback, and a stitched loop ships only if it validates. In the
    three-quarter view the 2D details are replaced by projected 3D glass (honest
    glass in 3/4 — flat rects would be a lie there). The three-quarter view carries
    no hidden lines: far-side parts drawn faint through the body read as transparency,
    not as a drawing convention (round-2 whipster catch). `deflection` is the HLR edge
    sampling; the detail zooms use a finer one (ZOOM_DEFLECTION) so wheel circles stay
    round at zoom scale."""
    P = []
    classes = D.project_classes(asset.shape, view, deflection)
    # front-view ring filter: the fuselage's own bbox is the reference (u = y-range,
    # v = z-range in the front view). Assets without a fuselage part pass through.
    ref_bbox = None
    if view == "front" and "fuselage" in asset.parts:
        bb = asset.parts["fuselage"].BoundingBox()
        ref_bbox = (bb.ymin, bb.ymax, bb.zmin, bb.zmax)
    classes = _drop_front_rings(classes, view, ref_bbox)
    # hidden lines FIRST, before the fills: a hidden edge is behind the body, so where
    # an opaque fill covers it the fill must win. Drawing them after the fills (the old
    # order) made every filled part translucent — in the S-92 top view 415 hidden
    # segments showed through the rotor blades (round-4 whipster catch). Hidden lines
    # that no fill covers (the far-side gear, the tail boom under the blades) still
    # read faint, which is the convention. The 3/4 view carries no hidden lines at
    # all (round-2 whipster catch).
    if view != "three-quarter":
        for pts in classes["hidden"]:
            P.append(("line", pts, W4, None, "line_faint"))
    # front-view occlusion: the fuselage is the foremost body, so its fill is drawn
    # LAST — parts behind it (the stabiliser at the tail, the fin, the tail rotor)
    # must not paint over the disc. The stabiliser's house_mid fill (u +/-2.00,
    # v 2.85..2.97) drew across the disc as a darker band at windshield height,
    # with its tips as side bars (round-7 whipster catch, finding 1 — the "seam"
    # was a fill, not a line, so the radial ring filter could not touch it).
    # Drawing the fuselage last covers the band where it overlaps the disc and
    # leaves only the stabiliser's tips (outside the disc) visible, which is the
    # honest occlusion. Other views keep fills_map order.
    fill_items = list(fills_map.items())
    if view == "front" and "fuselage" in fills_map:
        fill_items = [(p, f) for p, f in fill_items if p != "fuselage"]
        fill_items.append(("fuselage", fills_map["fuselage"]))
    # far-side parts must not paint over the near-side body in the port-side view:
    # the rescue hoist is starboard (y -1.62..-1.50) and the side view is port, so
    # its house_mid fill is a far-side patch bleeding through the opaque fuselage
    # (round-7 whipster catch, finding 3). Its HLR edges are hidden behind the
    # fuselage and covered by the fuselage fill, so dropping the fill hides it.
    # The 3/4 view shows the starboard side, so the hoist still fills there.
    if view == "side":
        fill_items = [(p, f) for p, f in fill_items if p != "hoist"]
    for part, fill in fill_items:
        shape = asset.parts[part]
        # the three-quarter view is oblique: a part's silhouette shears over the body
        # behind it, so a lighter "house_mid" fill reads as a translucent ghost patch
        # on the flank (the rear bumper's band, the engine deck over the windows —
        # round-3 whipster catch). In 3/4 every part takes the body tone: one opaque
        # material, parts distinguished by their HLR outlines. The orthographic views
        # keep the tonal variation (there the fills sit adjacent, not overlapping).
        if view == "three-quarter":
            fill = "house"
        mesh_loops = _mesh_fill_loops(shape, view)
        for loop in mesh_loops:
            P.append(("poly", loop, W3, fill, None))
        if mesh_loops:
            continue
        # fallback: the stitch path (outline, then visible, then combined+jump). A
        # loft's silhouette splits into an outline chain and a visible chain, which
        # the combined+jump path closes with the end-cap lines (multi-point arcs are
        # section seams, interior). Only validated loops ship.
        out = D.project_outline(shape, view, deflection)
        vis = D.project_classes(shape, view, deflection)["visible"]
        loops = _loops([p for p in vis])
        if not loops:
            loops = _loops(out)
        if not loops:
            loops = _loops(out + [p for p in vis if len(p) == 2], jump=True)
        for loop in loops:
            if _valid_loop(loop):
                P.append(("poly", loop, W3, fill, None))
    for pts in classes["silhouette"]:
        P.append(("line", pts, W1, None, "ink"))
    for pts in classes["visible"]:
        P.append(("line", pts, W2, None, "ink"))
    for pts in classes["smooth"]:
        P.append(("line", pts, W3, None, "ink"))
    if view == "three-quarter" and glass3d_fn is not None:
        n = D.view_direction(view)
        for quad, normal, fill in glass3d_fn():
            # keep only the quads facing the viewer (dot(normal, N) > 0)
            if sum(a * b for a, b in zip(normal, n)) <= 0.05:
                continue
            P.append(("poly", [D.project_point(p, view) for p in quad], W3, fill,
                     "line_faint"))
    else:
        P.extend(details_fn(view))
    us = [u for _, pts, _, _, _ in P for u, _ in pts]
    vs = [v for _, pts, _, _, _ in P for _, v in pts]
    bounds = (min(us), max(us), min(vs), max(vs)) if us else (0.0, 1.0, 0.0, 1.0)
    return P, bounds


def edge_length(prims):
    t = 0.0
    for _, pts, _, _, _ in prims:
        for (x0, z0), (x1, z1) in zip(pts, pts[1:]):
            t += math.hypot(x1 - x0, z1 - z0)
    return t


def _draw_prims(cv, prims, to_px):
    """Render prims on a skia Canvas with the sheet palette (draw_prims with overrides)."""
    from offsim.cinema.draw import draw_prims
    draw_prims(cv, prims, to_px, fills=SHEET_FILLS, strokes=SHEET_STROKES)


def render_view(cv, prims, bounds, box, label=None):
    """Draw one view into the pixel box (x0, y0, x1, y1), scaled to fit, centred; returns the
    px-per-metre scale. v is up in view metres, down in pixels."""
    x0, y0, x1, y1 = box
    umin, umax, vmin, vmax = bounds
    w_m, h_m = max(umax - umin, 1e-6), max(vmax - vmin, 1e-6)
    s = min((x1 - x0) / w_m, (y1 - y0) / h_m)
    ox = x0 + ((x1 - x0) - s * w_m) / 2 - s * umin
    pad_y = ((y1 - y0) - s * h_m) / 2
    to_px = lambda u, v: (ox + s * u, y1 - pad_y - s * (v - vmin))
    _draw_prims(cv, prims, to_px)
    return s


def _asset_scale(asset, views_data, cell_w, cell_h, reserve_l=0, reserve_r=0, reserve_b=0):
    """One scale per asset: the largest view must fit its cell, after reserving the margins
    the dimension callouts need (left/right/bottom, px)."""
    s = math.inf
    for view in VIEWS:
        _, (umin, umax, vmin, vmax) = views_data[view]
        s = min(s, (cell_w - reserve_l - reserve_r) / max(umax - umin, 1e-6),
                (cell_h - reserve_b) / max(vmax - vmin, 1e-6))
    return s


def _view_box(cv, prims, bounds, box, scale, clip=None):
    """Draw prims at a FIXED scale into a pixel box, centred. Returns (to_px, px_bounds)
    where px_bounds = (left, top, right, bottom) of the drawn content in px. If `clip` is
    given (a pixel rect (x, y, w, h)), drawing is clipped to it. If clip is "content",
    drawing is clipped to the content's own px_bounds — the detail zooms use this: they
    are windows onto the source view, and the full source view drawn through the cell
    (the old cell clip) let the main rotor blade cut across the tail-rotor cell at the
    HUB label's height, and the sponson lines run through the gear cell's margins
    (round-3 whipster catch — the blade read as a dash after "HUB", "FIN –")."""
    import skia

    x0, y0, x1, y1 = box
    umin, umax, vmin, vmax = bounds
    w_m, h_m = max(umax - umin, 1e-6), max(vmax - vmin, 1e-6)
    s = scale
    ox = x0 + ((x1 - x0) - s * w_m) / 2 - s * umin
    pad_y = ((y1 - y0) - s * h_m) / 2
    to_px = lambda u, v: (ox + s * u, y1 - pad_y - s * (v - vmin))
    px_bounds = (ox + s * umin, y1 - pad_y - s * h_m, ox + s * umax, y1 - pad_y)
    if clip is not None:
        if clip == "content":
            clip = (px_bounds[0], px_bounds[1], px_bounds[2] - px_bounds[0],
                    px_bounds[3] - px_bounds[1])
        cv.cv.save()
        cv.cv.clipRect(skia.Rect.MakeXYWH(clip[0], clip[1], clip[2], clip[3]))
    _draw_prims(cv, prims, to_px)
    if clip is not None:
        cv.cv.restore()
    return to_px, px_bounds


def _text(cv, x, y, s, size, color=INK, font=("Inter", "Bold"), tracking=0.0, anchor="l"):
    cv.text(x, y, s, font=font, size=size, color=color, tracking=tracking, anchor=anchor)


def _dim_specs(asset, name):
    """Dimension callouts for the measured views: (view, axis, a, b, feature, label, side,
    offset_px). Extents are measured from the asset bboxes, labels from QA measured values
    — never typed by hand. axis 'h': a..b in u, dim line below; 'v': a..b in v, dim line to
    the side. `feature` is the fixed coordinate the extension lines run from; `offset_px`
    is the dim line's distance from the drawing (the bus side view's length dim sits below
    its below-labels, so it needs 100 px, not 30)."""
    from offsim.assets.cad.qa import check as _qa

    rep = _qa(asset)
    m = {d["name"]: d["measured"] for d in rep["dims"]}
    bb = asset.shape.BoundingBox()
    if name == "s92":
        from offsim.assets.cad.air_sprite import MAST_X
        fus = asset.parts["fuselage"].BoundingBox()
        return [
            {"view": "side", "axis": "h", "a": fus.xmin, "b": fus.xmax, "feature": 0.0,
             "label": f"{m['length_m']:.2f} m", "side": "below", "offset": 30},
            {"view": "side", "axis": "v", "a": 0.0, "b": bb.zmax, "feature": MAST_X,
             "label": f"{m['height_m']:.2f} m", "side": "left", "offset": 30},
            {"view": "top", "axis": "v", "a": bb.ymin, "b": bb.ymax, "feature": MAST_X,
             "label": f"Ø {m['rotor_diameter_m']:.2f} m", "side": "left", "offset": 30},
        ]
    body = asset.parts["body"].BoundingBox()
    return [
        {"view": "side", "axis": "h", "a": bb.xmin, "b": bb.xmax, "feature": 0.0,
         "label": f"{m['length_m']:.2f} m", "side": "below", "offset": 100},
        {"view": "side", "axis": "v", "a": 0.0, "b": bb.zmax, "feature": bb.xmax,
         "label": f"{m['height_m']:.2f} m", "side": "right", "offset": 30},
        {"view": "top", "axis": "v", "a": body.ymin, "b": body.ymax, "feature": 0.0,
         "label": f"{m['width_m']:.2f} m", "side": "left", "offset": 30},
    ]


def _draw_dim(cv, spec, to_px, px_bounds, cell_box=None):
    """One dimension callout: faint extension lines from the measured points, a thin dim
    line with end ticks, and the measured value. A vertical dim's label sits BELOW the dim
    line, centred on it (round-2 whipster catch — the chip beside the line sat on the
    drawing: "Ø 17.20 m" overlapped the tail rotor, "3.15 m" sat on the bus nose)."""
    a, b, feature = spec["a"], spec["b"], spec["feature"]
    off = spec["offset"]
    if spec["axis"] == "h":
        y = px_bounds[3] + off
        x0, x1 = to_px(a, feature)[0], to_px(b, feature)[0]
        y0 = to_px(a, feature)[1]
        for x in (x0, x1):  # extension lines, with a 4 px gap at the measured point
            cv.line([(x, y0 + 4), (x, y)], INK_FAINT, 0.5)
            cv.line([(x - 4, y), (x + 4, y)], INK, 1.0)  # end tick
        cv.line([(x0, y), (x1, y)], INK, 1.0)
        _text(cv, (x0 + x1) / 2, y - 8, spec["label"], 17, color=INK,
              font=("Inter", "SemiBold"), anchor="m")
    else:
        x = px_bounds[0] - off if spec["side"] == "left" else px_bounds[2] + off
        y0, y1 = to_px(feature, a)[1], to_px(feature, b)[1]
        x0 = to_px(feature, a)[0]
        for y in (y0, y1):  # extension lines, with a 4 px gap at the measured point
            if spec["side"] == "left":
                cv.line([(x0 - 4, y), (x, y)], INK_FAINT, 0.5)
            else:
                cv.line([(x0 + 4, y), (x, y)], INK_FAINT, 0.5)
            cv.line([(x, y - 4), (x, y + 4)], INK, 1.0)  # end tick
        cv.line([(x, y0), (x, y1)], INK, 1.0)
        # label below the dim line (y0 is the lower measured point's px y), centred on
        # the dim line, clamped inside the cell
        w = cv.measure(spec["label"], ("Inter", "SemiBold"), 17, 0.0)
        tx = x
        if cell_box is not None:
            tx = min(max(tx, cell_box[0] + w / 2 + 4), cell_box[2] - w / 2 - 4)
        _text(cv, tx, y0 + 20, spec["label"], 17, color=INK, font=("Inter", "SemiBold"),
              anchor="m")


def _draw_labels(cv, labels, to_px, px_bounds, cell_box, size=17):
    """Part labels with leaders on a main view. labels: [(text, (u, v), 'above'|'below')].
    Levels are assigned greedily by measured text width: same-height texts never overlap
    (a 16 px minimum gap — round-2 whipster catch: MAIN ROTOR BLADE and PITOT TUBE sat
    11 px apart and read as one phrase). All texts extend left of their leader (the old
    alternating left/right pushed a far-right label off the cell edge). Labels are clamped
    inside the cell; the leader tick still bridges to the text."""
    if not labels:
        return
    items = sorted(labels, key=lambda t: t[1][0])
    placed = []  # (text, side, level, ax, ay, x0, x1, ly)
    for text, (u, v), side in items:
        ax, ay = to_px(u, v)
        w = cv.measure(text, ("Inter", "SemiBold"), size, 0.5)
        level = 0
        while True:
            ly = (px_bounds[1] - 30 - level * 26) if side == "above" \
                else (px_bounds[3] + 30 + level * 26)
            x1 = ax - 8
            x0 = x1 - w
            x0 = max(x0, cell_box[0] + 4)
            x1 = min(x1, cell_box[2] - 4)
            clash = any(s2 == side and lv == level and not (x1 + 16 < a0 or x0 > a1 + 16)
                        for (_, s2, lv, _, _, a0, a1, _) in placed)
            if not clash:
                break
            level += 1
        placed.append((text, side, level, ax, ay, x0, x1, ly))
    for text, side, level, ax, ay, x0, x1, ly in placed:
        tx = x1
        cv.line([(ax, ay), (ax, ly - 4)], INK_FAINT, 0.7)
        cv.line([(ax, ly - 4), (tx, ly - 4)], INK_FAINT, 0.7)
        cv.circle(ax, ay, 2.0, fill=INK)
        _text(cv, tx, ly, text, size, color=INK, font=("Inter", "SemiBold"), tracking=0.5,
              anchor="r")


def _draw_corner_label(cv, text, anchor_px, cell_box, corner, size=16):
    """A label in a cell corner (zoom cells, 3/4 hoist): paper chip behind the text, a
    leader from the chip to the anchor point. corner: tl | tr | bl | br."""
    x0, y0, x1, y1 = cell_box
    w = cv.measure(text, ("Inter", "SemiBold"), size, 0.5)
    if corner == "tl":
        tx, ty, anchor = x0 + 14, y0 + 26, "l"
    elif corner == "tr":
        tx, ty, anchor = x1 - 14, y0 + 26, "r"
    elif corner == "bl":
        tx, ty, anchor = x0 + 14, y1 - 10, "l"
    else:
        tx, ty, anchor = x1 - 14, y1 - 10, "r"
    tx0 = tx if anchor == "l" else tx - w
    tx1 = tx0 + w
    cx, cy = (tx0 + tx1) / 2, ty - 7
    cv.line([(cx, cy), anchor_px], INK_FAINT, 0.7)
    cv.circle(anchor_px[0], anchor_px[1], 2.0, fill=INK)
    cv.polygon([(tx0 - 6, ty - 20), (tx1 + 6, ty - 20), (tx1 + 6, ty + 6),
                (tx0 - 6, ty + 6)], fill=PAPER, stroke=None)
    _text(cv, tx, ty, text, size, color=INK, font=("Inter", "SemiBold"), tracking=0.5,
          anchor=anchor)


def _zoom_prims(asset, zoom_name, prims, deflection=ZOOM_DEFLECTION):
    """Prims for one detail-zoom cell, from the source view's prims (already computed
    once per source view and cached by the caller). Linework (+ glass) only, except
    the parts the zoom is ABOUT (ZOOMS[zoom_name]["fill_parts"]), whose mesh fills
    are included so an opaque tone covers hidden edges behind them — the tail-rotor
    blades fill, or the hidden hub/fin arc shows through the lower blade (round-4
    whipster catch; the blades fill in the main views, but this filter stripped them
    here, so the arc survived the main-view fix). The fin and fuselage stay unfilled
    here or they would swamp the cell (round-1 brown-sail problem). Draw order
    mirrors view_prims: hidden lines, fills, visible lines, glass, zoom-only details.
    """
    zoom = ZOOMS[zoom_name]
    out = [p for p in prims if p[0] == "line"
           or (p[0] == "poly" and p[3] in ("glass", "glass_dim"))]
    if zoom_name == "tail_rotor":
        # the fuselage's tail-boom top edge is a 5-point near-horizontal segment
        # (u -10.45..-8.53, v 3.29..3.47) that runs UNDER the fore blade
        # (bottom edge u -9.55..-8.30, v 3.46..3.52) with a hairline paper gap
        # between them — the gap reads as a thin white strip below the blade,
        # stepping down at the tip and continuing past it as the boom edge
        # (round-7 whipster catch, finding 2). The blades and hub fairing define
        # the top of the boom where they sit, so the boom edge under the rotor
        # goes (both its visible version and its hidden twin). The 2-point
        # blade/hub edges are untouched (they have < 3 points), and the boom
        # edge past the fore tip (u -8.54..-8.00, a 2-point segment) is kept.
        kept = []
        for p in out:
            if p[0] == "line" and len(p[1]) >= 3:
                us = [u for u, _ in p[1]]
                vs = [v for _, v in p[1]]
                if (max(vs) - min(vs) < 0.25 and min(us) < -10.0
                        and max(us) > -9.0 and max(us) < -8.0
                        and min(vs) > 3.2 and max(vs) < 3.5):
                    continue
            # round-8: the boom edge past the fore tip is a 2-pt segment
            # (u -8.54..-8.00, v 3.49..3.50) with a tiny 2-pt diagonal tick at
            # its left end (u -8.55..-8.53, v 3.47..3.51) — it survives as a
            # stray thin line below the tip, its right end in mid-air at the
            # zoom region's edge (round-8 whipster catch, finding 2). Drop any
            # 2-pt line wholly inside u -8.7..-7.9, v 3.40..3.55. The fore
            # blade's bottom edge (u -9.55..-8.30) starts outside the box, and
            # its tip edge (v to 3.68) runs out of it, so both survive; the
            # hidden twins are covered by the blade fill.
            if p[0] == "line" and len(p[1]) == 2:
                (u0, v0), (u1, v1) = p[1]
                if (-8.7 <= u0 <= -7.9 and -8.7 <= u1 <= -7.9
                        and 3.40 <= v0 <= 3.55 and 3.40 <= v1 <= 3.55):
                    continue
            kept.append(p)
        out = kept
    if zoom_name == "rotor_head":
        # the fuselage's loft section seam at x=2.00 is a vertical line
        # (z 2.30..3.70); in this zoom (z 3.5..5.4) only its top 0.20 m shows,
        # as a short tick hanging below the roofline (z 3.70) with nothing
        # attached (round-7 whipster nit). The seam is a fuselage feature, not
        # a rotor-head one, so it goes here (both visible and hidden versions).
        # The mast is at x 1.50, so x 1.95..2.05 is safe.
        kept = []
        for p in out:
            if p[0] == "line":
                us = [u for u, _ in p[1]]
                vs = [v for _, v in p[1]]
                if (max(us) - min(us) < 0.05 and 1.95 < min(us) < 2.05
                        and max(vs) <= 3.71):
                    continue
            kept.append(p)
        out = kept
    if zoom_name == "gear":
        # the fuselage's loft section seam at x=2.00 is a real edge, but in this zoom
        # it is a 0.25 m vertical tick standing on the sponson top (z 2.05) and ending
        # in mid-air (z 2.30) — it reads as a stray mark, not a panel line (round-6
        # whipster catch, new defect ii). The zoom is about the gear, not the loft
        # seams, so short vertical segments standing on the sponson top go. The
        # strut's edges are below z 2.05, so they are untouched.
        kept = []
        for p in out:
            if p[0] == "line":
                us = [u for u, _ in p[1]]
                vs = [v for _, v in p[1]]
                # the seam has two versions: a visible one (z 2.05..2.30) and a
                # hidden one (z 2.05..3.70, faint). The gear zoom carries no fills,
                # so the hidden one shows through as the same tick — drop both.
                # No height cap: the hidden twin is tall in the source view and
                # only reads short because the zoom clips it.
                if (max(us) - min(us) < 0.05 and max(vs) - min(vs) > 0.05
                        and abs(min(vs) - 2.05) < 0.03):
                    continue
            kept.append(p)
        out = kept
    fill_prims = []
    for part in zoom.get("fill_parts", []):
        tone = zoom.get("fill_tones", {}).get(part, "house")
        for loop in _mesh_fill_loops(asset.parts[part], zoom["source"], deflection):
            fill_prims.append(("poly", loop, W3, tone, None))
    first_vis = next((i for i, p in enumerate(out)
                      if p[0] == "line" and p[4] != "line_faint"), len(out))
    return out[:first_vis] + fill_prims + out[first_vis:] + ZOOM_DETAILS[zoom_name]


def render_sheet(path, assets, out_stills_dir=None):
    """Assemble the sheet: three rows (S-92 views, S-92 detail zooms, bus views). `assets` is
    a list of (name, title, subtitle, fills_map, details_fn, glass3d_fn). Returns a manifest
    of measured numbers."""
    W, H = 3000, 2120
    cv = Canvas(W, H, bg=PAPER, ss=2)
    m = 60
    # header: kicker + title (one word in accent) + deck
    _text(cv, m, m + 34, "OFFSHORE_SIMULATIONS  ·  CAD ASSET SHEET", 22, color=INK_FAINT,
          font=("Inter", "SemiBold"), tracking=2.0)
    _text(cv, m, m + 104, "HELICOPTER", 64, color=INK, tracking=0.5)
    _text(cv, m + cv.measure("HELICOPTER", ("Inter", "Bold"), 64, 0.5) + 18, m + 104, "+ BUS",
          64, color="#b07a2a", tracking=0.5)
    _text(cv, m, m + 150, "Two working assets, drawn from the same solids as the films — orthographic views, one scale per asset, plus detail close-ups.",
          24, color=INK_FAINT, font=("Inter", "Regular"))
    cv.line([(m, m + 172), (W - m, m + 172)], INK_FAINT, 1.0)

    rows_y0 = m + 200
    row_h = (H - rows_y0 - 150) // len(ROWS)
    label_w = 300
    gap = 24
    manifest = {}
    built = {}
    views_cache = {}
    zoom_cache = {}   # (asset, source view) -> prims at ZOOM_DEFLECTION (finer sampling)
    main_scale = {}   # asset -> its view-row scale (the zoom row quotes multiples of it)
    for i, row in enumerate(ROWS):
        name = row["asset"]
        if name not in built:
            from offsim.assets.cad.qa import check as _qa
            asset = _build_asset(name)
            built[name] = asset
            spec = next(a for a in assets if a[0] == name)
            views_cache[name] = {v: view_prims(asset, v, spec[3], spec[4], spec[5])
                                 for v in VIEWS}
            manifest[name] = {"qa": _qa(asset), "views": {}, "details": {}}
        asset = built[name]
        views_data = views_cache[name]
        y0 = rows_y0 + i * row_h
        # row label: title, subtitle, dims from QA (measured, never typed)
        _text(cv, m, y0 + 44, row["title"], 30, color=INK, tracking=0.5)
        _text(cv, m, y0 + 78, row["subtitle"], 20, color=INK_FAINT, font=("Inter", "Regular"))
        if row["kind"] == "views":
            from offsim.assets.cad.qa import check as _qa
            rep = _qa(asset)
            # one dim per line: the label column is 300 px and two dims on one line
            # overflow into the first cell, where the side view's above-labels sit
            # (round-2 whipster catch — TAIL ROTOR struck through "ROTOR Ø 17.20 m").
            _DIM_NAMES = {"length_m": "LENGTH", "rotor_diameter_m": "ROTOR Ø",
                          "height_m": "HEIGHT", "fuselage_width_m": "WIDTH",
                          "width_m": "WIDTH"}
            dim_lines = [f"{_DIM_NAMES.get(d['name'], d['name'].upper())} "
                         f"{d['measured']:.2f} m"
                         for d in rep["dims"] if d["measured"] is not None]
            for k, ln in enumerate(dim_lines):
                _text(cv, m, y0 + 106 + k * 24, ln, 18, color=INK,
                      font=("Inter", "Regular"))
            _text(cv, m, y0 + 106 + len(dim_lines) * 24 + 4, "ALL DIMS ASSUMED", 18,
                  color="#b07a2a", font=("Inter", "SemiBold"), tracking=1.0)
        else:
            # the per-cell scale is under each zoom title; nothing more is needed here
            pass
        # cells
        n_cells = len(row["cells"])
        cell_w = (W - 2 * m - label_w - gap - (n_cells - 1) * gap) // n_cells
        cell_h = row_h - 110
        if row["kind"] == "views":
            # reserves for the dimension callouts: left (s92 height dim), right (bus height
            # dim), bottom (length dims). The scale is computed on the reserved box.
            dims = _dim_specs(asset, name)
            reserve_l = 44 if any(d["side"] == "left" for d in dims) else 0
            reserve_r = 44 if any(d["side"] == "right" for d in dims) else 0
            reserve_b = 44 if any(d["side"] == "below" for d in dims) else 0
            scale = _asset_scale(asset, views_data, cell_w, cell_h,
                                 reserve_l, reserve_r, reserve_b)
            main_scale[name] = scale
            # scale bar: a round length that draws 60-120 px
            bar_m = 1.0
            while bar_m * scale < 60:
                bar_m *= 2
            bx, by = m, y0 + row_h - 66
            cv.line([(bx, by), (bx + bar_m * scale, by)], INK, 2.0)
            cv.line([(bx, by - 6), (bx, by + 6)], INK, 2.0)
            cv.line([(bx + bar_m * scale, by - 6), (bx + bar_m * scale, by + 6)], INK, 2.0)
            _text(cv, bx, by + 26, f"{bar_m:g} m", 18, color=INK, font=("Inter", "Regular"))
            _text(cv, bx, by + 52, f"scale {scale:.1f} px/m", 16, color=INK_FAINT,
                  font=("Inter", "Regular"))
            for j, cell in enumerate(row["cells"]):
                view = cell["view"]
                prims, bounds = views_data[view]
                cx0 = m + label_w + gap + j * (cell_w + gap)
                box = (cx0 + reserve_l, y0, cx0 + cell_w - reserve_r, y0 + cell_h - reserve_b)
                full_box = (cx0, y0, cx0 + cell_w, y0 + cell_h)
                to_px, px_bounds = _view_box(cv, prims, bounds, box, scale)
                for d in dims:
                    if d["view"] == view:
                        _draw_dim(cv, d, to_px, px_bounds, full_box)
                _draw_labels(cv, LABELS.get((name, view), []), to_px, px_bounds, full_box)
                for text, anchor3d, corner in LABELS_3D.get((name, view), []):
                    anchor = to_px(*D.project_point(anchor3d, view))
                    _draw_corner_label(cv, text, anchor, full_box, corner)
                _text(cv, cx0 + cell_w / 2, y0 + cell_h + 34, VIEW_TITLES[view], 20, color=INK,
                      tracking=1.5, anchor="m")
                manifest[name]["views"][view] = {
                    "prims": len(prims), "edge_m": round(edge_length(prims), 1),
                    "bounds_m": [round(b, 2) for b in bounds]}
                if out_stills_dir is not None:
                    _render_still(out_stills_dir, name, view, prims, bounds,
                                  row["title"])
        else:
            for j, cell in enumerate(row["cells"]):
                zoom = ZOOMS[cell["zoom"]]
                # zoom prims at the finer sampling (ZOOM_DEFLECTION), computed once per
                # source view — the sheet-scale prims would show their flats at zoom scale
                if (name, zoom["source"]) not in zoom_cache:
                    zoom_cache[(name, zoom["source"])] = view_prims(
                        asset, zoom["source"], spec[3], spec[4], spec[5],
                        deflection=ZOOM_DEFLECTION)
                prims, bounds = zoom_cache[(name, zoom["source"])]
                zoom_prims = _zoom_prims(asset, cell["zoom"], prims)
                cx0 = m + label_w + gap + j * (cell_w + gap)
                box = (cx0, y0, cx0 + cell_w, y0 + cell_h)
                region = zoom["region"]
                rw, rh = region[1] - region[0], region[3] - region[2]
                zscale = min(cell_w / rw, cell_h / rh)
                to_px, _ = _view_box(cv, zoom_prims, region, box, zscale,
                                     clip="content")
                for text, anchor_uv, corner in zoom["labels"]:
                    _draw_corner_label(cv, text, to_px(*anchor_uv), box, corner)
                _text(cv, cx0 + cell_w / 2, y0 + cell_h + 34, zoom["title"], 20, color=INK,
                      tracking=1.5, anchor="m")
                mult = zscale / main_scale[name] if name in main_scale else 0.0
                _text(cv, cx0 + cell_w / 2, y0 + cell_h + 58,
                      f"{zscale:.0f} px/m · {mult:.1f}× sheet scale", 16, color=INK_FAINT,
                      font=("Inter", "Regular"), anchor="m")
                manifest[name]["details"][cell["zoom"]] = {
                    "scale_px_per_m": round(zscale, 1), "prims": len(zoom_prims),
                    "edge_m": round(edge_length(zoom_prims), 1),
                    "region_m": [round(r, 2) for r in region]}
                if out_stills_dir is not None:
                    _render_still_zoom(out_stills_dir, name, cell["zoom"], zoom_prims,
                                       region, zoom, row["title"])
        if i < len(ROWS) - 1:
            cv.line([(m, y0 + row_h - 8), (W - m, y0 + row_h - 8)], INK_FAINT, 1.0)
    # footer: assumption note + method line
    fy = H - 96
    cv.line([(m, fy - 22), (W - m, fy - 22)], INK_FAINT, 1.0)
    _text(cv, m, fy + 8, "STYLISED — dimensions assumed, not manufacturer drawings. S-92-like helicopter (Gribkovskaia fleet) · FRAM 701 city bus (Kvam–Molde–Årølia).",
          20, color=INK, font=("Inter", "Regular"))
    _text(cv, m, fy + 36, "Solids: offsim/assets/cad/air_sprite.py + land_sprite.py  ·  Projection: OpenCASCADE HLR (0.005 m sampling; 0.001 m in the detail zooms)  ·  Drawn: skia  ·  Dims from QA (offsim/assets/cad/qa.py)  ·  Detail zooms: rotor head, landing gear, tail rotor.",
          20, color=INK_FAINT, font=("Inter", "Regular"))
    cv.save(path)
    return manifest


def _render_still(out_dir, name, view, prims, bounds, title):
    """One view as a standalone still: the view, its label, the asset name, a 1 m scale bar."""
    from pathlib import Path
    W, H = 1200, 900
    cv = Canvas(W, H, bg=PAPER, ss=2)
    _text(cv, 40, 56, f"{title}  ·  {VIEW_TITLES[view]}", 26, color=INK, tracking=1.0)
    s = render_view(cv, prims, bounds, (60, 90, W - 60, H - 110))
    bar_m = 1.0
    while bar_m * s < 60:
        bar_m *= 2
    bx, by = 60, H - 60
    cv.line([(bx, by), (bx + bar_m * s, by)], INK, 2.0)
    cv.line([(bx, by - 6), (bx, by + 6)], INK, 2.0)
    cv.line([(bx + bar_m * s, by - 6), (bx + bar_m * s, by + 6)], INK, 2.0)
    _text(cv, bx, by + 26, f"{bar_m:g} m", 18, color=INK, font=("Inter", "Regular"))
    out = Path(out_dir) / f"{name}-{view}.png"
    cv.save(str(out))
    return str(out)


def _render_still_zoom(out_dir, name, zoom_name, prims, region, zoom, title):
    """One detail zoom as a standalone still: the clipped region, its labels, a scale bar."""
    from pathlib import Path
    W, H = 1200, 900
    cv = Canvas(W, H, bg=PAPER, ss=2)
    _text(cv, 40, 56, f"{title}  ·  {zoom['title']}", 26, color=INK, tracking=1.0)
    box = (60, 90, W - 60, H - 110)
    rw, rh = region[1] - region[0], region[3] - region[2]
    s = min((box[2] - box[0]) / rw, (box[3] - box[1]) / rh)
    to_px, _ = _view_box(cv, prims, region, box, s, clip="content")
    for text, anchor_uv, corner in zoom["labels"]:
        _draw_corner_label(cv, text, to_px(*anchor_uv), box, corner)
    bar_m = 0.5
    while bar_m * s < 60:
        bar_m *= 2
    bx, by = 60, H - 60
    cv.line([(bx, by), (bx + bar_m * s, by)], INK, 2.0)
    cv.line([(bx, by - 6), (bx, by + 6)], INK, 2.0)
    cv.line([(bx + bar_m * s, by - 6), (bx + bar_m * s, by + 6)], INK, 2.0)
    _text(cv, bx, by + 26, f"{bar_m:g} m", 18, color=INK, font=("Inter", "Regular"))
    out = Path(out_dir) / f"{name}-{zoom_name}.png"
    cv.save(str(out))
    return str(out)
