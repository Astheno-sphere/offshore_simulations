"""Aircraft CAD assets: S-92-like offshore helicopter.

A stylised ~21 m offshore helicopter at real scale, built as an exact cadquery solid — the
Gribkovskaia paper's fleet (S-92, 125 knots, 15-min slots; the paper's Bergen program is the
next film). Proportions are STYLISED: no manufacturer drawing was sourced, so every principal
dimension is `assumption: True` and appears in the asset QA report (same honesty rule as the
PSV). Axes per the asset contract (offsim/assets/cad/base.py): x forward (nose), y to port,
z up; origin at the ground on the centreline, under the main rotor mast. Units metres.

LOD 2, 20 parts: lofted fuselage + tail boom (elliptical sections), tail fin + stabiliser,
main rotor split into mast / head (hub + swashplate + blade grips) / 4 separate blades,
tail rotor split into hub (+ gearbox fairing) / 4 tapered blades, sponsons port + starboard,
tricycle gear split into main (raked struts + wheels + hub discs) / nose (twin wheels +
strut), twin engine deck + exhausts, rescue hoist (starboard), pitot + antenna. Cockpit
glazing is NOT in the solid — windows are glazing, not structure: dark glass drawn 2D in the
sprite sheet (the v10 PSV lesson: window boxes in the solid draw bright HLR rectangles and
read as white squares).
"""
from __future__ import annotations

import cadquery as cq

from offsim.assets.cad.base import AssetModel, register

# --- principal dimensions (all assumed: no manufacturer drawing sourced) -----------------------
# Stylised S-92-like proportions: overall length nose->tail tip, rotor diameter, overall height
# ground->rotor head, fuselage max width. Values are by construction (see the builders below).
LENGTH, ROTOR_DIA, HEIGHT, FUSELAGE_WIDTH = 20.9, 17.2, 5.15, 3.0
MAST_X = 1.5          # main rotor mast station (x)
ROTOR_Z = 5.05        # main rotor blade plane
ROTOR_HEAD_TOP_Z = 5.15
TAIL_ROTOR_X = -9.80  # tail rotor hub station (x, on the fin)
TAIL_ROTOR_Z = 3.60   # tail rotor hub height (blades 1.50 m: tips 2.10..5.10, under the head)
TAIL_ROTOR_BLADE = 1.50

DIMS = {
    # length is the airframe length nose->tail tip, measured on the fuselage part (the
    # helicopter convention): the tail rotor disc and the pitot stick out past it, and the
    # fused bbox (22.30 m) is the overall length incl. rotors — reported in the QA notes.
    "length_m": {"value": LENGTH, "assumption": True, "part": "fuselage"},
    "rotor_diameter_m": {"value": ROTOR_DIA, "assumption": True},
    "height_m": {"value": HEIGHT, "assumption": True},
    "fuselage_width_m": {"value": FUSELAGE_WIDTH, "assumption": True, "part": "fuselage"},
}
_DIM_NOTE = "stylised S-92-like offshore helicopter (Gribkovskaia fleet); no manufacturer drawing sourced"


def _box(x0, x1, z0, z1, y0, y1):
    return cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0, cq.Vector(x0, y0, z0))


def _ellipse_wire(x, y_half, zc, z_half):
    """Closed elliptical wire in the YZ plane at station x (for the fuselage loft)."""
    return cq.Wire.makeEllipse(y_half, z_half, center=(x, 0, zc), normal=(1, 0, 0),
                               xDir=(0, 1, 0))


def _fuselage():
    """One loft, nose tip to tail tip: elliptical sections, belly ~0.95 m, cabin roof ~3.7 m,
    tail boom tapering to the fin. Smooth (not ruled) so the loft seams stay quiet."""
    stations = [  # (x, y_half, z_centre, z_half)
        (10.45, 0.15, 2.30, 0.15),   # nose tip
        (9.50, 1.05, 2.35, 1.05),    # nose
        (7.00, 1.45, 2.30, 1.35),    # cockpit
        (2.00, 1.50, 2.30, 1.40),    # cabin mid (widest)
        (-3.00, 1.45, 2.35, 1.35),   # cabin aft
        (-5.50, 0.90, 2.60, 0.90),   # tail boom base
        (-8.00, 0.55, 2.90, 0.60),   # tail boom mid
        (-10.45, 0.15, 3.10, 0.35),  # tail tip
    ]
    wires = [_ellipse_wire(x, yh, zc, zh) for x, yh, zc, zh in stations]
    # Ruled (not smooth): a smooth B-spline loft overshoots the widest station by ~10%
    # (measured 3.31 m vs the 3.0 m design width), so the stated width would be a lie.
    # The ruled loft's section seams read as frame stations in the drawing — honest drafting.
    return cq.Solid.makeLoft(wires, ruled=True)


def _fin():
    """Vertical tail fin: swept side profile, 0.25 m thick on the centreline."""
    prof = [(-8.20, 2.80), (-10.45, 3.00), (-10.45, 4.60), (-9.60, 5.00), (-8.60, 3.60)]
    return cq.Workplane("XZ").polyline(prof).close().extrude(0.125, both=True).val()


def _stabilizer():
    """Horizontal stabiliser at the tail: thin box across the boom. It sits LOW
    (z 2.60..2.72), on the tail boom below the fin — the old z 3.50..3.62 put it
    straight through the tail-rotor disc (the fore blade is z 3.46..3.74 at the
    same x), so its top/bottom edges drew through the blade as a smaller second
    rectangle (round-6 whipster catch, nit b). At 2.85 it clears the fore blade
    (3.46) and the hub (3.45), and it embeds in the fin (2.80), and it still
    meets the tail boom.
    Chord 1.25 m (x -9.60..-8.35): the short 1.20 m chord (x -9.60..-8.40)
    floated in the tail-rotor zoom, its forward end in mid-air over the pale fin
    (round-7 whipster catch, finding 2). The forward end now runs to the fin's
    leading edge (x -8.20), so it meets a visible edge in the zoom. The aft end
    stays at x -9.60: the down blade hangs to z 2.10 at x -9.80 +/- 0.11, so
    extending aft past x -9.69 would put the stabiliser through the down blade
    (measured 0.00154 m^3 at x -10.00). The aft end's bottom-left corner touches
    the boom diagonal, so the bar reads attached at both ends. ROUND-8
    CORRECTION: that claim was wrong — the fin's bottom is z 2.80, so the bar
    at z 2.60..2.72 sat 0.08 m BELOW the fin with no fin edge at its height, and
    its forward end was a free edge over bare paper (round-8 whipster catch,
    finding 2, half-fixed). The bar is raised to z 2.85..2.97 so it EMBEDS in
    the fin's lower edge: the fin's bottom is a diagonal from (-8.20, 2.80) to
    (-10.45, 3.00), and the bar straddles it (at x -8.20 the fin's bottom is
    2.80, at x -9.60 it is 2.92), so the bar is inside the fin along its length
    and its forward end meets the fin's leading-edge bottom corner. It still
    clears the blades and hub (fore blade 3.46, hub 3.45) and the down blade
    (x -9.80 +/- 0.11, no x overlap with the bar's x -9.60..-8.20). ROUND-9
    CORRECTION (v10): the "forward end meets the leading edge" claim was wrong
    in projection — the fin's leading edge KINKS at (-8.60, 3.60), so at the
    bar's height its lower segment sits at x -8.225..-8.285, AFT of the bar's
    end at -8.20: the bar poked 0.025..0.085 m past the fin, a free edge over
    paper (round-9 whipster catch, the only fail). The chord is shortened to
    x -9.60..-8.35 so both ends sit inside the fin's silhouette at the bar's
    height, and the fin is filled faintly in the tail-rotor zoom so the bar
    sits on fin tone, not paper."""
    return _box(-9.60, -8.35, 2.85, 2.97, -2.00, 2.00)


def _rotor_mast():
    """Main rotor mast: the column from the roof to the head (z 3.70-4.90), at the mast
    station x=1.5 (v2 fix: the first split build left it at x=0, so the mast drew on the
    region's left edge and the MAST label pointed at empty space)."""
    return cq.Solid.makeCylinder(0.18, 4.90 - 3.70, cq.Vector(MAST_X, 0, 3.70),
                                 cq.Vector(0, 0, 1))


def _rotor_head():
    """Rotor head: hub + swashplate disc + one blade grip per blade + a mast nut (a wider
    collar where the mast meets the head — the one piece of mechanism the round-2 head zoom
    was missing: without it the mast read as a blank column). Built around the rotor axis
    at x=0, z=0, then shifted to the mast station (like the blades)."""
    hub = cq.Solid.makeCylinder(0.35, ROTOR_HEAD_TOP_Z - 4.85, cq.Vector(0, 0, 4.85),
                                cq.Vector(0, 0, 1))
    swash = cq.Solid.makeCylinder(0.45, 0.10, cq.Vector(0, 0, 4.70), cq.Vector(0, 0, 1))
    nut = cq.Solid.makeCylinder(0.28, 0.10, cq.Vector(0, 0, 4.82), cq.Vector(0, 0, 1))
    grip = _box(0.55, 0.95, 4.95, 5.08, -0.18, 0.18)
    grips = [grip]
    for ang in (90, 180, 270):
        grips.append(grip.rotate(cq.Vector(0, 0, 0), cq.Vector(0, 0, 1), ang))
    return hub.fuse(swash, nut, *grips).translate(cq.Vector(MAST_X, 0, 0))


def _one_blade():
    """One main-rotor blade: thin tapered plate, root 0.80 m from the axis, tip 8.60 m,
    chord 0.65 -> 0.40 m. Built around the rotor axis, fore (+x); the caller rotates it."""
    return (cq.Workplane("XY")
            .polyline([(0.80, -0.325), (8.60, -0.20), (8.60, 0.20), (0.80, 0.325)])
            .close().extrude(0.07).val())


def _blades():
    """4 blades as separate parts: fore / aft / port / starboard, stopped pose. Each blade is
    rotated about the rotor axis, then the whole set is shifted to the mast station and UP to
    the rotor plane (round-1 whipster: the blades were left at z=0 and drew on the ground)."""
    base = _one_blade()
    out = {}
    for name, ang in (("blade_fore", 0), ("blade_port", 90), ("blade_aft", 180),
                      ("blade_stbd", 270)):
        b = base.rotate(cq.Vector(0, 0, 0), cq.Vector(0, 0, 1), ang) if ang else base
        out[name] = b.translate(cq.Vector(MAST_X, 0, ROTOR_Z - 0.035))
    return out


def _tail_rotor_hub():
    """Tail rotor hub on the port side of the fin + the gearbox fairing it sits on. The hub
    axis is the y-axis through (TAIL_ROTOR_X, 0.275, TAIL_ROTOR_Z)."""
    hub = cq.Solid.makeCylinder(0.12, 0.30, cq.Vector(TAIL_ROTOR_X, 0.125, TAIL_ROTOR_Z),
                                cq.Vector(0, 1, 0))
    fairing = _box(TAIL_ROTOR_X - 0.25, TAIL_ROTOR_X + 0.25, TAIL_ROTOR_Z - 0.15,
                   TAIL_ROTOR_Z + 0.15, 0.10, 0.30)
    return hub.fuse(fairing)


def _tail_rotor_blades():
    """Tail rotor: 4 tapered blades in the vertical (XZ) plane, 1.50 m long — a ~3.0 m disc,
    the S-92 proportion (round 1: 0.95 m blades read as a diamond smudge on the fin). Built
    as one tapered plate in XY, rotated into the XZ plane, then fanned about the hub axis.
    Blade tips: z 2.10..5.10, x -11.30..-8.30 — inside the overall height (5.15)."""
    plate = (cq.Workplane("XY")
             .polyline([(0.25, -0.14), (TAIL_ROTOR_BLADE, -0.08),
                        (TAIL_ROTOR_BLADE, 0.08), (0.25, 0.14)])
             .close().extrude(0.06).val())
    # into the XZ plane: rotate 90 deg about the x-axis (chord y -> z, thickness z -> -y)
    plate = plate.rotate(cq.Vector(0, 0, 0), cq.Vector(1, 0, 0), 90)
    plate = plate.translate(cq.Vector(TAIL_ROTOR_X, 0.275 + 0.03, TAIL_ROTOR_Z))
    blades = [plate]
    _axis = cq.Vector(TAIL_ROTOR_X, 0.275, TAIL_ROTOR_Z)
    for ang in (90, 180, 270):
        blades.append(plate.rotate(_axis, _axis + cq.Vector(0, 1, 0), ang))
    return blades[0].fuse(*blades[1:])


def _sponson(port: bool):
    """One stub sponson (main-gear housing) on the cabin side."""
    y0, y1 = (1.25, 1.95) if port else (-1.95, -1.25)
    return _box(-1.00, 3.50, 1.35, 2.05, y0, y1)


def _gear_main():
    """Main gear, both sides: wheel + proud hub disc + a VERTICAL strut up to the sponson.
    The strut ends at the TYRE TOP (z 0.90), not at the axle — the old strut ran to the
    axle (z 0.45), so its outline continued inside the tyre down to the hub disc and
    read as a box drawn on the wheel (round-5 whipster catch). The axle is inside the
    wheel and not drawn; the strut landing on the tyre top is the honest attachment.
    Round-2 whipster catch: the raked strut's sharp bottom corner poked through the
    wheel and ended inside it, with no axle to terminate on."""
    out = []
    for y in (1.80, -1.80):
        out.append(cq.Solid.makeCylinder(0.45, 0.30, cq.Vector(1.20, y - 0.15, 0.45),
                                         cq.Vector(0, 1, 0)))
        hub_y = y + 0.175 if y > 0 else y - 0.175
        out.append(cq.Solid.makeCylinder(0.22, 0.06, cq.Vector(1.20, hub_y - 0.03, 0.45),
                                         cq.Vector(0, 1, 0)))
        y0, y1 = (1.55, 1.85) if y > 0 else (-1.85, -1.55)
        out.append(_box(1.05, 1.35, 0.90, 1.35, y0, y1))
    return out[0].fuse(*out[1:])


def _gear_nose():
    """Nose gear: twin wheels + a vertical strut up to the belly + an axle bar. The
    strut (y ±0.15) does not overlap the twin wheels (y ±0.30..0.54) in the front
    view, so without the axle the two wheels hung below the belly with a visible gap
    and no strut connecting them (round-5 whipster catch, N1). The axle bar
    (y -0.54..0.54, z 0.70..0.82) joins the wheels and overlaps the strut's foot
    (z 0.76) and the wheel tops (z 0.76), so the whole gear reads as one assembly.
    The strut ends at the tyre top (z 0.76), as the main gear does."""
    out = []
    for y in (0.42, -0.42):
        out.append(cq.Solid.makeCylinder(0.38, 0.24, cq.Vector(7.30, y - 0.12, 0.38),
                                         cq.Vector(0, 1, 0)))
    out.append(_box(7.10, 7.50, 0.76, 1.05, -0.15, 0.15))
    out.append(_box(7.22, 7.38, 0.70, 0.82, -0.54, 0.54))
    return out[0].fuse(*out[1:])


def _engines():
    """Twin engine deck on the roof aft of the mast."""
    out = []
    for y0, y1 in ((0.35, 1.05), (-1.05, -0.35)):
        out.append(_box(-2.50, -0.30, 3.65, 4.25, y0, y1))
    return out[0].fuse(*out[1:])


def _exhausts():
    """Engine exhausts pointing aft, one per deck."""
    out = []
    for y in (0.70, -0.70):
        out.append(cq.Solid.makeCylinder(0.18, 0.60, cq.Vector(-2.50, y, 3.95),
                                         cq.Vector(-1, 0, 0)))
    return out[0].fuse(*out[1:])


def _hoist():
    """Rescue hoist above the starboard cabin door: housing + cable + hook block. The
    cable is r 0.05, not a hairline — the old r 0.02 cable read as a thin tick joining
    a floating hook to the housing (round-5 whipster catch, N1, and the side-view
    hoist-tab nit)."""
    housing = _box(2.60, 3.40, 3.00, 3.35, -1.62, -1.50)
    cable = cq.Solid.makeCylinder(0.05, 0.50, cq.Vector(3.00, -1.56, 2.50), cq.Vector(0, 0, 1))
    hook = _box(2.88, 3.12, 2.30, 2.50, -1.64, -1.48)
    return housing.fuse(cable, hook)


def _pitot():
    """Pitot tube on the nose, off-centre (port). Its base sits INSIDE the nose (x 10.00,
    y 0.30, z 2.20 is inside the ruled loft: (0.30/0.58)^2 + ((2.20-2.32)/0.58)^2 < 1) and
    it emerges from the nose surface at x ~10.28 and sticks out to x 11.00 — 0.55 m past
    the nose tip (10.45), so it reads at sheet scale (round-3 whipster catch: the 0.60 m
    tube showed only 0.15 m past the tip, a ~2 px nub). Round-2 whipster catch: the old
    pitot sat at y 1.20, outside the fuselage surface (the nose half-width there is
    < 1.05), so it drew as a thick black dash floating detached off the nose. A
    forward-pointing pitot is hidden behind the nose in the front view — it reads in the
    side and top views, not the front."""
    return cq.Solid.makeCylinder(0.03, 1.00, cq.Vector(10.00, 0.30, 2.20), cq.Vector(1, 0, 0))


def _antenna():
    """Roof antenna, a blade on the centreline. Taller than the engine deck (top
    z 4.40 vs the deck's 4.25) and 0.16 m thick, with its base sunk into the roof
    (z 3.65) — the old 0.06 m hairline (z 3.70..4.10) ended below the deck tops and
    read as a thin tan rod floating beside the mast in the front view (round-5
    whipster catch, N1). It is a filled part now (SPRITE_FILLS), so it does not read
    as an unfilled white box on the roof in the side view either."""
    return _box(4.50, 5.00, 3.65, 4.40, -0.08, 0.08)


@register("s92")
def build_s92(**params) -> AssetModel:
    """Build the S-92-like helicopter asset. No parameters yet: one stylised S-92 (params
    reserved for fleet variants)."""
    if params:
        raise ValueError(f"s92 takes no parameters yet; got {sorted(params)}")
    parts = {"fuselage": _fuselage(), "fin": _fin(), "stabilizer": _stabilizer(),
             "rotor_mast": _rotor_mast(), "rotor_head": _rotor_head(),
             **_blades(),
             "tail_rotor_hub": _tail_rotor_hub(), "tail_rotor_blades": _tail_rotor_blades(),
             "sponson_port": _sponson(True), "sponson_stbd": _sponson(False),
             "gear_main": _gear_main(), "gear_nose": _gear_nose(),
             "engines": _engines(), "exhausts": _exhausts(), "hoist": _hoist(),
             "pitot": _pitot(), "antenna": _antenna()}
    shape = None
    for p in parts.values():
        shape = p if shape is None else shape.fuse(p)
    dims = {k: dict(v, note=_DIM_NOTE) for k, v in DIMS.items()}
    return AssetModel(shape=shape, parts=parts, dims=dims, meta={
        "class": "aircraft",
        "licence": "own work — generated solid, no external model",
        "generator": "offsim.assets.cad.air:build_s92",
        "lod": 2,
        "notes": ("stylised S-92-like offshore helicopter (Gribkovskaia fleet); all dims assumed "
                  "until a manufacturer drawing is sourced; lofted fuselage + tail boom, 4-blade "
                  "main rotor stopped fore/aft + athwart (mast / head / 4 separate blades), tail "
                  "rotor port (hub + 4 tapered blades, ~3.0 m disc), sponsons + tricycle gear "
                  "(vertical struts), rescue hoist starboard; cockpit glazing is 2D (sprite sheet), "
                  "not in the solid."),
    })


# --- sprite-sheet 2D details (view coords in metres, v up) --------------------------------------
# Glazing is drawn 2D on the sheet, like the PSV's windows: dark glass with variation, no outline.
# The 3/4 view carries projected 3D glass (sprite_glass_3d) instead of rects.
# Line weights: W_PANEL (door/panel outlines) and W_FINE (mullions, stripes) — the sheet's tiers.

W_PANEL, W_FINE = 0.9, 0.5


def s92_sprite_details(view):
    """2D detail prims for one view: (kind, points, weight, fill, outline)."""
    P = []

    def poly(pts, w, fill, outline=None):
        P.append(("poly", pts, w, fill, outline))

    def line(pts, w, outline="ink"):
        P.append(("line", pts, w, None, outline))

    if view == "side":
        # cockpit glazing: wraparound nose glass, one dark band with a single centre mullion.
        # Each glass pane carries a faint frame (a window, not a black tile — round-2
        # whipster catch: five identical dark rects read as tiles).
        poly([(7.35, 2.95), (8.55, 3.00), (9.05, 2.60), (8.80, 2.30), (7.50, 2.30)],
             W_PANEL, "glass", "line_faint")
        line([(8.15, 2.98), (8.05, 2.30)], W_FINE)
        # cabin windows: varied widths, not five identical tiles — one per bay, with gaps,
        # one tone (round-8 whipster nit: the alternating glass/glass_dim read as a
        # fill inconsistency with no meaning, windows 2 and 4 lighter for no reason).
        # The middle bay is the sliding door (faint outline + handle).
        # The door window is narrower than the door outline so the panel reads around it
        # (round-2 whipster catch: the window nearly filled the outline, a stray rectangle).
        for x0, w, fill in ((0.70, 0.65, "glass"), (1.90, 0.50, "glass"),
                            (3.15, 0.70, "glass"), (4.30, 0.50, "glass"),
                            (5.50, 0.65, "glass")):
            # the middle bay (3.15) is the sliding door's window: it takes NO frame of
            # its own, because the door outline below is its frame — a second faint rect
            # 0.20 m inside it read as a stray rectangle overlapping the window
            # (round-3 whipster catch)
            outline = None if x0 == 3.15 else "line_faint"
            poly([(x0, 2.60), (x0 + w, 2.60), (x0 + w, 3.20), (x0, 3.20)], W_PANEL, fill,
                 outline)
        # sliding door: a FULL panel from the sponson top (z 2.05) to near the roof
        # (z 3.50), not a small rectangle around the window — the old outline
        # (v 2.45..3.35) read as a stray rectangle overlapping the window (round-3/4
        # whipster catch). The window sits in the panel's upper half; the handle marks
        # it as a door. Drawn at panel weight (W2) with a DARK outline (ink): the
        # line_faint outline read as a pale ghost rectangle straddling the window
        # (round-7 whipster catch, finding 3 — the door is a panel, not a ghost).
        poly([(2.95, 2.05), (4.05, 2.05), (4.05, 3.50), (2.95, 3.50)], W_PANEL, None,
             "ink")
        line([(3.85, 2.90), (4.00, 2.90)], W_FINE, "line_faint")
        # tail boom stripe (a painted line, not structure) + fin leading-edge line
        line([(-5.40, 3.05), (-9.90, 3.35)], W_FINE, "line_faint")
    elif view == "front":
        # windshield: narrower than round 2 (the dark trapezoid still read as a face visor
        # under the two round exhaust "eyes") and a stronger centre pillar.
        poly([(-0.50, 2.30), (0.50, 2.30), (0.42, 3.15), (-0.42, 3.15)], W_PANEL, "glass",
             "line_faint")
        line([(0.0, 2.30), (0.0, 3.15)], W_PANEL)
        # blank the exhaust "eyes": the two exhaust cylinders (r 0.18 at y +/-0.70,
        # z 3.95) project as dark circles inside the engine-deck boxes and read as a
        # pair of eyes above the windshield (round-3 whipster catch). Cover each with a
        # 12-sided disc in the engine-deck tone, drawn after the HLR lines — the pipes
        # still read in the side and top views, where they point aft.
        import math as _math
        for _cy in (0.70, -0.70):
            _disc = [(_cy + 0.18 * _math.cos(2 * _math.pi * _k / 12),
                      3.95 + 0.18 * _math.sin(2 * _math.pi * _k / 12))
                     for _k in range(12)]
            poly(_disc, W_FINE, "house_mid")
    return P


def s92_glass_3d():
    """Glazing as 3D quads on the body surface: (points, outward normal, fill). The sheet
    projects them into the three-quarter view and keeps only the quads facing the viewer —
    honest glass in 3/4, where flat 2D rects would be a lie."""
    quads = []
    # cabin windows, both sides (y = +/-1.51, just proud of the 1.50 half-width).
    # One tone, like the 2D side windows (round-8 whipster nit).
    for x0, w, fill in ((0.70, 0.65, "glass"), (1.90, 0.50, "glass"),
                        (3.15, 0.70, "glass"), (4.30, 0.50, "glass"),
                        (5.50, 0.65, "glass")):
        for s in (1, -1):
            y = s * 1.51
            quads.append(([(x0, y, 2.60), (x0 + w, y, 2.60), (x0 + w, y, 3.20),
                           (x0, y, 3.20)], (0, s, 0), fill))
    # cockpit glass, both sides: a quad on the nose slope (the nose half-width is ~1.05-1.45
    # here, so the quad sits on the surface, slightly proud)
    for s in (1, -1):
        quads.append(([(7.40, s * 1.30, 2.30), (8.85, s * 1.05, 2.30),
                       (8.55, s * 1.00, 3.00), (7.45, s * 1.25, 3.00)],
                      (0, s, 0.25), "glass"))
    return quads


# Parts whose silhouette gets a tonal fill on the sheet (part -> fill key). The fin takes the
# fuselage tone (round 1: a darker fin read as a separate brown sail). The four main-rotor
# blades ARE filled (round 3: unfilled, the fore/aft blades read white while the
# port/starboard ones read tan over the fuselage — the disc looked half see-through, and
# the bodies were not opaque). A filled wheel is a black blob, so the gear stays linework
# + hub discs. The tail-rotor blades ARE filled too (round 4: unfilled, a hidden hub/fin
# arc showed through the lower blade — the disc is small enough that a solid fill reads
# as the disc, and it covers the hidden line behind it).
SPRITE_FILLS = {"fuselage": "house", "fin": "house", "stabilizer": "house_mid",
                "sponson_port": "house_mid", "sponson_stbd": "house_mid",
                "engines": "house_mid", "rotor_head": "house_mid", "rotor_mast": "house_mid",
                "blade_fore": "house", "blade_aft": "house",
                "blade_port": "house", "blade_stbd": "house",
                "tail_rotor_blades": "house", "antenna": "house_mid",
                "hoist": "house_mid"}
