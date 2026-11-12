"""Land CAD assets: FRAM city bus.

A stylised ~12 m city bus at real scale, built as an exact cadquery solid — the Molde film's
FRAM 701 (Kvam–Molde–Årølia). Proportions are STYLISED: no manufacturer drawing was sourced,
so every principal dimension is `assumption: True` and appears in the asset QA report (same
honesty rule as the PSV and the S-92). Axes per the asset contract
(offsim/assets/cad/base.py): x forward (nose), y to port, z up; origin at the ground on the
centreline, mid-vehicle. Units metres.

LOD 2, 8 parts: slab-sided body from a spline side profile (sloped windshield, rounded roof
corners), two axles as separate parts (front / rear, wheels + hub discs), mirrors port +
starboard, roof AC pod, bumpers front + rear. Side windows, doors, destination display and
lights are NOT in the solid — glazing and panel lines are drawn 2D on the sprite sheet (the
v10 PSV lesson: boxes in the solid draw bright HLR rectangles and read as white squares).
No crew: a bus with stick-men reads as a toy.
"""
from __future__ import annotations

import cadquery as cq

from offsim.assets.cad.base import AssetModel, register

# --- principal dimensions (all assumed: no manufacturer drawing sourced) -----------------------
# Stylised ~12 m city bus: overall length incl. bumpers, body width, overall height incl. roof pod.
LENGTH, WIDTH, HEIGHT = 12.2, 2.55, 3.15
HALF_L, HALF_W = LENGTH / 2, WIDTH / 2

DIMS = {
    "length_m": {"value": LENGTH, "assumption": True},
    "width_m": {"value": WIDTH, "assumption": True, "part": "body"},
    "height_m": {"value": HEIGHT, "assumption": True},
}
_DIM_NOTE = "stylised ~12 m city bus (FRAM 701, Kvam–Molde–Årølia); no manufacturer drawing sourced"


def _box(x0, x1, z0, z1, y0, y1):
    return cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0, cq.Vector(x0, y0, z0))


def _body_profile_points():
    """Side-profile outline (x forward, z up from the ground), nose first, clockwise. The
    windshield slope and the roof corners are splines; the belly and the roof are straight."""
    return [(6.0, 0.55), (6.0, 1.80), (5.75, 2.95), (5.40, 3.00), (-5.40, 3.00),
            (-5.75, 2.95), (-6.0, 2.60), (-6.0, 0.55)]


def _arch_cut(x, r=0.62, z=0.55):
    """Half-cylinder wheel-arch cut-out (upper half, z >= belly) at one axle: the body's
    bottom edge follows the arch instead of slicing straight through the wheel (round-2
    whipster catch — the belly line cut both wheels in half in the side view). The arch
    clears the 0.50 m wheel by 0.12 m; the body's bbox is unchanged (the cut is inside it)."""
    cyl = cq.Solid.makeCylinder(r, 2 * HALF_W, cq.Vector(x, -HALF_W, z), cq.Vector(0, 1, 0))
    box = _box(x - r, x + r, z, z + r, -HALF_W, HALF_W)
    return cyl.intersect(box)


def _body():
    """Body solid: spline side profile extruded across the width, with a wheel-arch cut-out
    over each axle. Slab-sided (no tumblehome: invisible in a side projection, LOD-3 work)."""
    pts = _body_profile_points()
    wp = (cq.Workplane("XZ")
          .moveTo(*pts[0])
          .lineTo(*pts[1])
          .spline(pts[2:4], includeCurrent=True)   # sloped windshield up to the roof
          .lineTo(*pts[4])
          .spline(pts[5:7], includeCurrent=True)   # rounded rear roof corner down to the tail
          .lineTo(*pts[7])
          .close())
    return wp.extrude(HALF_W, both=True).val().cut(_arch_cut(4.00)).cut(_arch_cut(-3.60))


def _axle(x):
    """One axle: two wheels (cylinders athwartships) + proud hub discs, both sides."""
    out = []
    for y in (1.10, -1.10):
        out.append(cq.Solid.makeCylinder(0.50, 0.35, cq.Vector(x, y - 0.175, 0.50),
                                         cq.Vector(0, 1, 0)))
        hub_y = y + 0.175 if y > 0 else y - 0.175
        out.append(cq.Solid.makeCylinder(0.22, 0.06, cq.Vector(x, hub_y - 0.03, 0.50),
                                         cq.Vector(0, 1, 0)))
    return out[0].fuse(*out[1:])


def _mirror(port: bool):
    """One door mirror: stalk out of the front corner + mirror head (the only parts wider
    than the body, so width_m is measured on the body part, not the fused bbox). The
    stalk runs 0.12 m INTO the body (y 1.15, not 1.27): ending exactly at the body
    surface left a visible gap in the front/rear views and the mirror read as floating
    on a thin stalk (round-3 whipster catch)."""
    if port:
        y0, y1, h0, h1 = 1.15, 1.45, 1.42, 1.52
    else:
        y0, y1, h0, h1 = -1.45, -1.15, -1.52, -1.42
    return _box(5.80, 6.00, 2.45, 2.55, y0, y1).fuse(
        _box(5.80, 6.00, 2.15, 2.60, h0, h1))


def _roof_pod():
    """Roof AC pod, inside the overall height. Sits exactly on the roofline (z 3.00):
    the front-view destination display now occupies the 2.90..3.00 band below it, so
    the pod must not extend below 3.00 or its fill swallows the display (round-4
    whipster catch). The old 0.05 m embed (round-2 fix for floating) is gone — the
    pod's bottom edge coincides with the roofline, which seats it."""
    return _box(-3.00, 2.00, 3.00, 3.15, -0.80, 0.80)


def _bumper(front: bool):
    """One bumper, flush with the body end."""
    if front:
        return _box(6.00, 6.10, 0.55, 0.95, -1.20, 1.20)
    return _box(-6.10, -6.00, 0.55, 0.95, -1.20, 1.20)


@register("bus")
def build_bus(**params) -> AssetModel:
    """Build the FRAM city bus asset. No parameters yet: one stylised 12 m bus (params reserved
    for fleet variants)."""
    if params:
        raise ValueError(f"bus takes no parameters yet; got {sorted(params)}")
    parts = {"body": _body(), "wheels_front": _axle(4.00), "wheels_rear": _axle(-3.60),
             "mirrors_port": _mirror(True), "mirrors_stbd": _mirror(False),
             "roof_pod": _roof_pod(), "bumper_front": _bumper(True),
             "bumper_rear": _bumper(False)}
    shape = None
    for p in parts.values():
        shape = p if shape is None else shape.fuse(p)
    dims = {k: dict(v, note=_DIM_NOTE) for k, v in DIMS.items()}
    return AssetModel(shape=shape, parts=parts, dims=dims, meta={
        "class": "vehicle",
        "licence": "own work — generated solid, no external model",
        "generator": "offsim.assets.cad.land:build_bus",
        "lod": 2,
        "notes": ("stylised ~12 m city bus (FRAM 701, Kvam–Molde–Årølia); all dims assumed until "
                  "a manufacturer drawing is sourced; slab-sided body, sloped windshield, two "
                  "axles as separate parts, mirrors port + starboard, roof AC pod, bumpers "
                  "front + rear; side windows, doors, destination display and lights are 2D "
                  "(sprite sheet), not in the solid; no crew."),
    })


# --- sprite-sheet 2D details (view coords in metres, v up) --------------------------------------
# Glazing and panel lines drawn 2D on the sheet, like the PSV's windows: dark glass with
# variation, no outline. The 3/4 view carries projected 3D glass (bus_glass_3d) instead.
# Line weights: W_PANEL (door/panel outlines) and W_FINE (mullions, stripes, handles).

W_PANEL, W_FINE = 0.9, 0.5

# Side windows (x0, width, fill): varied widths, not four identical tiles; clear of the door
# zones (front door 4.40-5.50, rear door -0.60-0.50) and the wheel arches (x 4.0, -3.6).
# One tone (round-8 whipster nit: the alternating glass/glass_dim read as a fill
# inconsistency with no meaning).
_SIDE_WINDOWS = ((-5.50, 0.95, "glass"), (-3.00, 1.80, "glass"),
                 (0.70, 1.75, "glass"), (2.80, 0.90, "glass"))


def bus_sprite_details(view):
    """2D detail prims for one view: (kind, points, weight, fill, outline)."""
    P = []

    def poly(pts, w, fill, outline=None):
        P.append(("poly", pts, w, fill, outline))

    def line(pts, w, outline="ink"):
        P.append(("line", pts, w, None, outline))

    if view == "side":
        # side windows: dark glass, one tone (widths 0.90-1.80 m),
        # each with a faint frame — a window, not a black tile (round-2 whipster catch)
        for x0, w, fill in _SIDE_WINDOWS:
            poly([(x0, 2.05), (x0 + w, 2.05), (x0 + w, 2.70), (x0, 2.70)], W_PANEL, fill,
                 "line_faint")
        # doors: faint panel outline + centre split + glass in the upper half + handle.
        # A door that is only an outline reads as a blank panel; the glass makes it a door.
        for x0, x1 in ((4.40, 5.50), (-0.60, 0.50)):
            poly([(x0, 0.60), (x1, 0.60), (x1, 2.75), (x0, 2.75)], W_PANEL, None, "line_faint")
            line([((x0 + x1) / 2, 0.60), ((x0 + x1) / 2, 2.75)], W_FINE, "line_faint")
            poly([(x0 + 0.15, 2.05), (x1 - 0.15, 2.05), (x1 - 0.15, 2.65), (x0 + 0.15, 2.65)],
                 W_FINE, "glass_dim", "line_faint")
            line([(x1 - 0.35, 1.55), (x1 - 0.20, 1.55)], W_FINE, "line_faint")
        # the wheel arches are cut into the body solid now (the HLR draws the arch edge);
        # the 2D arc lines are gone — they doubled the solid edge
        # rub strip along the side + skirt line: the two horizontal features that stop the
        # slab reading as one flat panel. Both are BROKEN at the wheel arches (axles at
        # x 4.00 / -3.60, arch r 0.62): the unbroken skirt line at z 0.62 ran straight
        # through both wheels and across each hub (round-3 whipster catch — the arch
        # cuts were there, but the line was never broken at them).
        for x0, x1 in ((-5.90, -4.22), (-2.98, 3.38), (4.62, 5.90)):
            line([(x0, 1.00), (x1, 1.00)], W_FINE, "line_faint")
            line([(x0, 0.62), (x1, 0.62)], W_FINE, "line_faint")
        # destination display band above the windshield line, front of the side
        poly([(5.00, 2.80), (5.70, 2.80), (5.70, 2.95), (5.00, 2.95)], W_FINE, "glass_dim")
    elif view == "front":
        # windshield: narrower than round 2 (the giant black visor read as a face under the
        # two square headlight "eyes"), a stronger centre mullion, and a horizontal divider
        # so it reads as two panes, not one visor
        poly([(-0.85, 1.85), (0.85, 1.85), (0.78, 2.90), (-0.78, 2.90)], W_PANEL, "glass",
             "line_faint")
        line([(0.0, 1.85), (0.0, 2.88)], W_PANEL)
        line([(-0.83, 2.40), (0.83, 2.40)], W_FINE)
        # destination display band above the windshield (narrower than the glass, so the
        # two dark bands no longer merge into one black mass). It sits in the 2.90..3.00
        # band between the windshield top and the roofline: the old 2.95..3.08 band
        # overlapped the roof AC pod's fill (round-4 whipster catch), and the centre
        # mullion ran up into it — the mullion now stops at 2.88.
        poly([(-0.45, 2.90), (0.45, 2.90), (0.45, 3.00), (-0.45, 3.00)], W_FINE, "glass_dim")
        # headlights: smaller than round 2 (0.22 x 0.14 m, not 0.30 x 0.20)
        for y0 in (-1.01, 0.79):
            poly([(y0, 0.97), (y0 + 0.22, 0.97), (y0 + 0.22, 1.11), (y0, 1.11)], W_FINE,
                 "glass_dim", "line_faint")
        # engine-grille PANEL: a faint-outlined rect with four slats, below the
        # windshield (same treatment as the rear grille panel). The old two bare lines
        # (z 1.35/1.55) read as a ghost seam across an otherwise featureless panel
        # (round-5 whipster catch, N2) — unframed faint lines are a seam, a framed
        # panel with slats is a grille.
        poly([(-0.70, 1.10), (0.70, 1.10), (0.70, 1.80), (-0.70, 1.80)], W_FINE, None,
             "line_faint")
        for z in (1.24, 1.38, 1.52, 1.66):
            line([(-0.70, z), (0.70, z)], W_FINE, "line_faint")
        # wheels, seen from the front, are the tyre tread (a rectangle) — a faint tread
        # line across each one stops it reading as a plain rectangle (a front-view wheel
        # is a rectangle by geometry; the round view is the side)
        for y0, y1 in ((-1.25, -0.95), (0.95, 1.25)):
            line([(y0, 0.28), (y1, 0.28)], W_FINE, "line_faint")
    elif view == "rear":
        # rear window: SMALLER than the windshield and divided both ways (four panes),
        # so the rear cell cannot be mistaken for the front (round-3 whipster catch —
        # the two cells were near-identical at sheet scale: same window, same lights,
        # same bumper). The front keeps the destination display + headlights + grille;
        # the rear gets the smaller divided window, TALL vertical taillight strips
        # (the front lights are wide and short), and a solid engine-grille panel with
        # slats below the window. No destination display on the rear.
        poly([(-0.75, 1.95), (0.75, 1.95), (0.75, 2.65), (-0.75, 2.65)], W_PANEL, "glass",
             "line_faint")
        line([(0.0, 1.95), (0.0, 2.65)], W_PANEL)
        line([(-0.75, 2.30), (0.75, 2.30)], W_FINE)
        # engine-grille panel: VERTICAL louvres in a wider panel — the old
        # horizontal-slat panel was identical to the front grille, so the
        # front/rear distinction rested on window and lights only (round-7
        # whipster nit). A rear engine vent reads as vertical louvres; the front
        # keeps its horizontal slats.
        poly([(-0.85, 1.05), (0.85, 1.05), (0.85, 1.70), (-0.85, 1.70)], W_FINE, None,
             "line_faint")
        for u in (-0.60, -0.30, 0.00, 0.30, 0.60):
            line([(u, 1.05), (u, 1.70)], W_FINE, "line_faint")
        # taillights: tall vertical strips (0.15 wide x 0.45 tall), not the front's
        # wide short headlights
        for y0 in (-1.10, 0.95):
            poly([(y0, 0.95), (y0 + 0.15, 0.95), (y0 + 0.15, 1.40), (y0, 1.40)], W_FINE,
                 "glass_dim", "line_faint")
        for y0, y1 in ((-1.25, -0.95), (0.95, 1.25)):
            line([(y0, 0.28), (y1, 0.28)], W_FINE, "line_faint")
    elif view == "top":
        # roof hatch: one panel line, so the top view is not just the pod on an empty box
        poly([(-1.0, -0.50), (1.0, -0.50), (1.0, 0.50), (-1.0, 0.50)], W_FINE, None,
             "line_faint")
    return P


def bus_glass_3d():
    """Glazing as 3D quads on the body surface: (points, outward normal, fill). The sheet
    projects them into the three-quarter view and keeps only the quads facing the viewer —
    honest glass in 3/4, where flat 2D rects would be a lie. The side quads sit 0.005 m
    proud of the 1.275 m half-width."""
    quads = []
    for x0, w, fill in _SIDE_WINDOWS:
        for s in (1, -1):
            y = s * 1.28
            quads.append(([(x0, y, 2.05), (x0 + w, y, 2.05), (x0 + w, y, 2.70),
                           (x0, y, 2.70)], (0, s, 0), fill))
    # windshield: a quad on the sloped nose (profile runs (6.0, 1.80) -> (5.75, 2.95)),
    # narrowed with the 2D front glass (round 2: the wide visor read as a face)
    quads.append(([(5.97, -0.80, 1.95), (5.97, 0.80, 1.95), (5.74, 0.80, 2.85),
                   (5.74, -0.80, 2.85)], (0.35, 0, 0.94), "glass"))
    # destination display band, front face above the windshield
    quads.append(([(5.80, -0.45, 2.95), (5.80, 0.45, 2.95), (5.80, 0.45, 3.08),
                   (5.80, -0.45, 3.08)], (1, 0, 0), "glass_dim"))
    return quads


# Parts whose silhouette gets a tonal fill on the sheet (part -> fill key). Wheels are NOT
# filled (round 1: a filled wheel is a black blob); the HLR circles + hub discs carry them.
SPRITE_FILLS = {"body": "house", "roof_pod": "house_mid",
                "bumper_front": "house_mid", "bumper_rear": "house_mid"}
