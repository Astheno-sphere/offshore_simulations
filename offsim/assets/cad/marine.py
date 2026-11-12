"""Marine CAD assets: PSV (and, later, platform_jacket).

The PSV is a stylised ~85 m platform supply vessel at real scale, built as an exact cadquery solid.
Proportions follow the section film's existing profile (offsim/cinema/vessel_lineart.py, "stylised ~85 m
PSV, UT 755-like proportions; ASSUMED until a class drawing is sourced") — every principal dimension is
therefore `assumption: True` and appears in the asset QA report; the film's DRAFT line already says the
vessel geometry is an assumption. Axes per the asset contract (offsim/assets/cad/base.py): x forward (bow),
y to port, z up; origin at the keel, midships. Units metres.

LOD 2: hull with spline stem + sheer, stepped superstructure, funnel (tapered body + cap), mast + radar,
bulwark rails, cargo (containers + pipe stack), rescue boat.
LOD 3 (v9, de-kiddified): portholes, draft marks (2D, drawing.py), deck crane, lifeboat davits,
anchor, bridge-glazing mullions, rail stanchions (2D, drawing.py), hull plating seams (2D, drawing.py).
v10 (working ship, not a toy): the window boxes are GONE from the solid — HLR drew their bright
rectangles around every 1.1 m window and the superstructure read as identical white squares. Windows
are glazing, not structure: dark glass rects with variation, drawn 2D in drawing.py (same device as
the boot-top stripe). The bridge mullions stay as CAD boxes: their vertical HLR edges read as pane
dividers on the dark glass band.
"""
from __future__ import annotations

import math

import cadquery as cq

from offsim.assets.cad.base import AssetModel, register

# --- principal dimensions (all assumed: no class drawing sourced) -------------------------------
# Same key numbers as vessel_lineart.psv_profile: LOA 85, deck z0+4.5, fcsle z0+7.5, keel z0-6.2.
# Asset frame: z=0 at the keel, so waterline z=6.2, main deck z=10.7, fcsle deck z=13.7.
LOA, BEAM, DRAUGHT, DEPTH = 85.0, 17.0, 6.2, 10.7
FCSLE_Z, BRIDGE_TOP_Z, FUNNEL_TOP_Z, MAST_TOP_Z = 13.7, 25.3, 26.5, 34.8
HALF_L, HALF_B = LOA / 2, BEAM / 2

DIMS = {
    "loa_m": {"value": LOA, "assumption": True},
    "beam_m": {"value": BEAM, "assumption": True},
    "depth_m": {"value": DEPTH, "assumption": True},          # keel -> main deck
    "draught_m": {"value": DRAUGHT, "assumption": True},
    "air_draught_m": {"value": MAST_TOP_Z, "assumption": True},  # keel -> mast top
    "funnel_top_m": {"value": FUNNEL_TOP_Z, "assumption": True},
}
_DIM_NOTE = "stylised PSV, UT 755-like proportions (vessel_lineart.py); no class drawing sourced"


def _hull_profile_points():
    """Side-profile outline (x forward, z up from keel), bow tip first, clockwise. The stem and the
    forecastle edge are splines through these vertices; the keel, transom and main deck are straight."""
    return [(HALF_L, 14.3), (40.0, 7.2), (36.5, 0.8), (32.5, 0.0), (-38.5, 0.0), (-41.0, 1.8),
            (-HALF_L, 10.1), (-HALF_L, DEPTH), (18.5, DEPTH), (18.5, FCSLE_Z), (41.3, 14.3)]


def _hull():
    """Hull solid: spline-stem side profile extruded across the beam. Slab-sided (no bilge radius:
    invisible in a side projection, LOD-3 work)."""
    pts = _hull_profile_points()
    # NOTE: Workplane.spline() does NOT include the current point unless includeCurrent=True
    # (without it the wire never closes and the extrude comes back empty). The forecastle step
    # is a lineTo first: starting the sheer spline vertically overshoots the bow by ~1 m.
    wp = (cq.Workplane("XZ")
          .moveTo(*pts[0])
          .spline(pts[1:4], includeCurrent=True)  # raked, curved stem down to the keel
          .lineTo(*pts[4]).lineTo(*pts[5]).lineTo(*pts[6]).lineTo(*pts[7])
          .lineTo(*pts[8])                        # flat main deck, stern -> forecastle step
          .lineTo(*pts[9])                        # the step itself
          .spline([(30.0, 14.0), pts[10]], includeCurrent=True)  # forecastle sheer to the bow
          .close())
    # both=True extrudes `until` in EACH direction, so half the beam per side
    return wp.extrude(BEAM / 2, both=True).val()


def _box(x0, x1, z0, z1, y0, y1):
    return cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0, cq.Vector(x0, y0, z0))


def _house():
    """Stepped superstructure (forward) + bridge with a sloped front, as one fused part."""
    # tiers: (x0, x1, z0, z1) in asset coords; old profile u -> x = 42.5 - u
    tiers = [(19.5, 39.5, FCSLE_Z, 16.7), (20.5, 38.5, 16.7, 19.7), (21.5, 37.5, 19.7, 22.3)]
    solids = [_box(x0, x1, z0, z1, -7.0, 7.0) for x0, x1, z0, z1 in tiers]
    # bridge: trapezoid profile (front face slopes back), extruded across the house width
    prof = [(20.0, 22.3), (38.5, 22.3), (38.5, 25.3), (21.2, 25.3)]
    bridge = (cq.Workplane("XZ").polyline(prof).close().extrude(7.0, both=True).val())
    solids.append(bridge)
    return solids[0].fuse(*solids[1:])


def _funnel():
    """Twin exhaust uptake, aft of the house; top at (x=18.8, z=26.5) — the section's exhaust point.
    Tapered body + a slightly wider cap (z 25.5-26.5): a funnel reads by its cap, not as a plain
    rectangle. The colour band is a 2D device in drawing.py (same device as the boot-top stripe)."""
    body = cq.Workplane("XZ").polyline([(17.0, 19.7), (20.5, 19.7), (20.1, 26.5), (17.4, 26.5)]).close().extrude(2.0, both=True).val()
    cap = _box(17.0, 20.5, 25.5, 26.5, -1.0, 1.0)
    return body.fuse(cap)


def _mast():
    mast = cq.Solid.makeCylinder(0.15, MAST_TOP_Z - BRIDGE_TOP_Z, cq.Vector(29.5, 0, BRIDGE_TOP_Z),
                                 cq.Vector(0, 0, 1))
    radar = _box(27.0, 32.0, 31.4, 31.7, -0.15, 0.15)
    antenna = cq.Solid.makeCylinder(0.06, 3.5, cq.Vector(26.0, 0, BRIDGE_TOP_Z), cq.Vector(0, 0, 1))
    return mast.fuse(radar, antenna)


def _bulwark():
    """Rail/bulwark walls along both deck edges, main deck, 1.1 m high."""
    return _box(-HALF_L, 18.5, DEPTH, DEPTH + 1.1, 8.4, 8.5).fuse(
        _box(-HALF_L, 18.5, DEPTH, DEPTH + 1.1, -8.5, -8.4))


def _cargo():
    """Aft-deck cargo: containers (old profile boxes) + pipe stack (cylinders athwartships)."""
    boxes = []
    for u, w, h in ((30, 6.1, 2.6), (37, 6.1, 2.6), (44, 12.2, 2.6), (58, 6.1, 5.2)):
        boxes.append(_box(42.5 - (u + w), 42.5 - u, DEPTH, DEPTH + h, -4.0, 4.0))
    pipes = []
    for k in range(4):
        x = 42.5 - (68 + k * 1.1)
        z = DEPTH + 0.55 + (k % 2) * 0.9
        pipes.append(cq.Solid.makeCylinder(0.5, 6.0, cq.Vector(x, -3.0, z), cq.Vector(0, 1, 0)))
    out = boxes[0].fuse(*boxes[1:], *pipes)
    return out


def _rescue_boat():
    return _box(23.0, 28.5, 17.1, 18.3, 6.5, 8.5)


def _portholes():
    """LOD-3: porthole rings on the port hull side (the projected side), one row above the
    waterline. Small cylinders proud of the slab side, so HLR projects them as circles."""
    out = None
    for x in range(-36, 37, 4):
        c = cq.Solid.makeCylinder(0.32, 0.25, cq.Vector(float(x), 8.3, 8.6), cq.Vector(0, 1, 0))
        out = c if out is None else out.fuse(c)
    return out


def _beam(p0, p1, w):
    """Square-section beam from p0 to p1 (asset coords), for the crane boom."""
    p0, p1 = cq.Vector(*p0), cq.Vector(*p1)
    d = p1 - p0
    b = cq.Solid.makeBox(d.Length, w, w, cq.Vector(0, -w / 2, -w / 2))
    b = b.rotate(cq.Vector(0, 0, 0), cq.Vector(0, 1, 0), -math.degrees(math.atan2(d.z, d.x)))
    return b.translate(p0)


def _crane():
    """LOD-3: aft-deck crane — pedestal on the main deck, boom angled forward-up, hook block."""
    pedestal = cq.Solid.makeCylinder(0.9, 3.5, cq.Vector(-2.0, 0, DEPTH), cq.Vector(0, 0, 1))
    boom = _beam((-2.0, 0, 14.2), (8.7, 0, 23.2), 0.9)
    hook = _box(8.3, 9.1, 20.6, 22.0, -0.2, 0.2)
    return pedestal.fuse(boom, hook)


def _davits():
    """LOD-3: lifeboat davit frames over the rescue boat (two L-frames, port side)."""
    out = None
    for x in (24.0, 27.5):
        up = _box(x - 0.12, x + 0.12, 17.1, 18.9, 7.0, 7.25)
        arm = _box(x - 0.12, x + 0.12, 18.75, 19.0, 7.0, 8.5)   # flush with the hull side (beam stays 17.0)
        f = up.fuse(arm)
        out = f if out is None else out.fuse(f)
    return out


def _anchor():
    """LOD-3: stockless anchor on the port bow, just below the forecastle deck."""
    return _box(38.4, 39.8, 8.6, 9.6, 8.5, 8.55).fuse(_box(38.9, 39.3, 9.6, 10.6, 8.5, 8.55))


def _mullions():
    """LOD-3: bridge-glazing mullions — thin verticals across the wraparound band, so the glass
    reads as panes, not one white block."""
    out = None
    for x in range(22, 38, 3):
        m = _box(float(x), x + 0.25, 23.3, 24.7, 7.0, 7.14)
        out = m if out is None else out.fuse(m)
    return out


@register("psv")
def build_psv(**params) -> AssetModel:
    """Build the PSV asset. No parameters yet: one stylised 85 m PSV (params reserved for class variants)."""
    if params:
        raise ValueError(f"psv takes no parameters yet; got {sorted(params)}")
    hull = _hull()
    house = _house()
    funnel = _funnel()
    mast = _mast()
    bulwark = _bulwark()
    cargo = _cargo()
    boat = _rescue_boat()
    portholes = _portholes()
    crane = _crane()
    davits = _davits()
    anchor = _anchor()
    mullions = _mullions()
    parts = {"hull": hull, "superstructure": house, "funnel": funnel,
             "mast": mast, "bulwark": bulwark, "cargo": cargo, "rescue_boat": boat,
             "portholes": portholes, "crane": crane, "davits": davits, "anchor": anchor,
             "mullions": mullions}
    shape = hull.fuse(house, funnel, mast, bulwark, cargo, boat,
                      portholes, crane, davits, anchor, mullions)
    dims = {k: dict(v, note=_DIM_NOTE) for k, v in DIMS.items()}
    return AssetModel(shape=shape, parts=parts, dims=dims, meta={
        "class": "vessel",
        "licence": "own work — generated solid, no external model",
        "generator": "offsim.assets.cad.marine:build_psv",
        "lod": 2,
        "notes": ("stylised ~85 m PSV, UT 755-like proportions; all dims assumed until a class drawing is "
                  "sourced; slab-sided hull, spline stem; LOD 2 (decks, rails) + v9 working-ship "
                  "detail (portholes, deck crane, davits, anchor, glazing mullions) + v10 shading "
                  "(windows as 2D dark glass, funnel cap; no window boxes in the solid)."),
    })
