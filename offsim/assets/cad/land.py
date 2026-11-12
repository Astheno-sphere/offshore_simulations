"""Land assets as exact solids at real scale: bus, train, person, tree, building (contract: offsim/assets/cad/base.py).

    bus(length_m=12|18)   Solaris Urbino 12/18 electric class city bus (right-hand traffic: doors on -y)
    train(n_cars=4)       Stadler FLIRT regional EMU (Norske tog class 76 dimensions), pantograph with pivot
    person(stature_m, pose, phase, hard_hat, survival_suit)  anthropometric figure, Winter/Drillis-Contini ratios
    tree(species, seed, height_m, crown_width_m, lod)        deterministic recursive-branching tree
    building(footprint, height_m, roof, lod)                 extrusion of a real footprint (+ buildings_from_geojson);
                                                              default footprint is Molde Mølle, OSM way 1355114723

Axes: x forward, y left, z up, metres, origin on the ground at the plan centre (see base.py).  Everything is built
from OpenCASCADE primitives, booleans on single parts only; the whole-object `shape` is a Compound of the parts
(parts overlap only where they physically touch), so building one asset takes well under a second to a few seconds.

SOURCES (also repeated in each dims entry):
  EU Directive 96/53/EC Annex I: max width 2.55 m (point 1.2a), max height 4.00 m (1.3), articulated bus 18.75 m (1.1)
      https://www.legislation.gov.uk/eudr/1996/53/data.html
  Solaris Urbino 12 electric (12 000 x 2 550 x 3 300 mm, wheelbase 5 900, doors 2-2-2)
      https://www.solarisbus.com/public/assets/Biuro_prasowe/2022_10_12_Transexpo/Technical_Details_Urbino_12_electric_Transexpo_EN.pdf
  Solaris Urbino 18 electric (18 000 x 2 550 x 3 300 mm, wheelbases 5 900 + 6 000, doors 2-2-2-2)
      https://www.solarisbus.com/public/assets/Biuro_prasowe/2023_10_06_BUSWORLD/Technical_details_Solaris_Urbino_18_electric.pdf
  Stadler FLIRT class 76 (Norske tog): 127 700 mm over couplers, 6 cars, 3 200 mm wide, 4 380 mm above rail
      https://www.railvolution.net/news/first-class-76-flirt-on-test
  Stadler FLIRT Nordic (Norske tog): bogie wheelbase 2 700 mm motor / 2 500 mm trailer, entrance width 1 100 mm
      https://stadlerrail.com/api/docs/x/fd4e7b7bbc/flirt-200-nordic_norske-tog-sa.pdf
  Body segment ratios of stature: Drillis & Contini (1966) as tabulated in Winter, Biomechanics and Motor Control of
      Human Movement, 3rd ed. (2005), Fig. 4.1 (also cited as "Drillis and Contini 1966; cited in Winter 2005").
      The figure itself could not be opened from this workspace: the ratios are the standard published values.
  Tree size ranges: Norway spruce 30-46 m tall, crown spread 7.6-13.7 m (https://dimensions.com/element/norway-spruce-picea-abies);
      Scots pine "to 25 m" (https://www.rhs.org.uk/plants/13141/i-Pinus-sylvestris-i/Details);
      silver birch "up to 24 m" (https://www.forestryandland.gov.scot/learn/trees/silver-birch).
  Building floors: OSM building:levels x 3.0 m = offsim.worlds.osm.LEVEL_HEIGHT_M (an assumption, flagged).
  Default building (Molde Mølle, Molde): OSM way 1355114723, height=19, building:levels=5, building=office
      (Overpass 2026-11-12; © OpenStreetMap contributors, ODbL 1.0); footprint 17.88 x 12.76 m minimum rotated
      rectangle, area 221.8 m2 (UTM 32N).
"""
from __future__ import annotations

import functools
import json
import math
import random
from pathlib import Path

import cadquery as cq
import numpy as np

from .base import AssetModel, register

V = cq.Vector
GEN = "offsim.assets.cad.land"
LICENCE = "generated (original geometry, no external meshes)"

URL_EU = "https://www.legislation.gov.uk/eudr/1996/53/data.html"
URL_U12 = ("https://www.solarisbus.com/public/assets/Biuro_prasowe/2022_10_12_Transexpo/"
           "Technical_Details_Urbino_12_electric_Transexpo_EN.pdf")
URL_U18 = ("https://www.solarisbus.com/public/assets/Biuro_prasowe/2023_10_06_BUSWORLD/"
           "Technical_details_Solaris_Urbino_18_electric.pdf")
URL_F76 = "https://www.railvolution.net/news/first-class-76-flirt-on-test"
URL_FNORD = "https://stadlerrail.com/api/docs/x/fd4e7b7bbc/flirt-200-nordic_norske-tog-sa.pdf"
URL_WINTER = "Winter 2005 Biomechanics and Motor Control of Human Movement 3rd ed. Fig 4.1 (after Drillis & Contini 1966)"


def _src(value, src):
    return {"value": float(value), "src": src}


def _asm(value, note=""):
    d = {"value": float(value), "assumption": True}
    if note:
        d["note"] = note
    return d


# ----------------------------------------------------------------------------------------------- shape helpers
def _vals(x):
    if x is None:
        return []
    if isinstance(x, cq.Workplane):
        return list(x.vals())
    if isinstance(x, (list, tuple)):
        out = []
        for i in x:
            out += _vals(i)
        return out
    return [x]


def _comp(*items):
    shapes = []
    for it in items:
        shapes += _vals(it)
    return cq.Compound.makeCompound(shapes)


def _box(x0, x1, y0, y1, z0, z1):
    return cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))


def _cyl(r, p0, p1):
    d = V(*p1) - V(*p0)
    return cq.Solid.makeCylinder(r, d.Length, V(*p0), d)


def _cone(p0, p1, r0, r1):
    d = V(*p1) - V(*p0)
    if d.Length < 1e-6:
        return None
    return cq.Solid.makeCone(r0, r1, d.Length, V(*p0), d)


def _cyl_y(r, y0, y1, x, z):
    return cq.Solid.makeCylinder(r, y1 - y0, V(x, y0, z), V(0, 1, 0))


def _free(a, b, excl, pad=0.0):
    """Intervals of [a, b] left after removing the (lo, hi) intervals in `excl` (each padded by `pad`)."""
    iv = [(a, b)]
    for lo, hi in sorted(excl):
        lo, hi = lo - pad, hi + pad
        nxt = []
        for s, e in iv:
            if hi <= s or lo >= e:
                nxt.append((s, e))
                continue
            if lo > s:
                nxt.append((s, lo))
            if hi < e:
                nxt.append((hi, e))
        iv = nxt
    return [(s, e) for s, e in iv if e - s > 1e-6]


def _bays(a, b, maxw, pillar, minw=0.45):
    """Split [a, b] into equal window bays separated by pillars -> [(lo, hi)]."""
    L = b - a
    if L < minw + 2 * pillar:
        return []
    n = max(1, math.ceil((L - pillar) / (maxw + pillar)))
    w = (L - (n + 1) * pillar) / n
    while w < minw and n > 1:
        n -= 1
        w = (L - (n + 1) * pillar) / n
    if w < minw:
        return []
    return [(a + pillar + i * (w + pillar), a + pillar + i * (w + pillar) + w) for i in range(n)]


def _spheroid(a, b, cx, cy, cz):
    """Ellipsoid with horizontal semi-axis a and vertical semi-axis b (revolved half-ellipse, exact extents)."""
    prof = (cq.Workplane("XZ").moveTo(0, -b).ellipseArc(a, b, -90, 90, sense=1, startAtCurrent=True)
            .close().revolve(360, (0, 0, 0), (0, 1, 0)))
    return prof.val().translate(V(cx, cy, cz))


def _fuse(*shapes):
    s = shapes[0]
    if len(shapes) > 1:
        s = s.fuse(*shapes[1:]).clean()
    return s


def bbox_dims(shape):
    bb = shape.BoundingBox()
    return {"x": bb.xlen, "y": bb.ylen, "z": bb.zlen, "xmin": bb.xmin, "xmax": bb.xmax, "ymin": bb.ymin,
            "ymax": bb.ymax, "zmin": bb.zmin, "zmax": bb.zmax}


# ================================================================================================== BUS
BUS_HW = 2.55 / 2           # EU 96/53/EC point 1.2(a); Urbino width 2 550
BUS_H = 3.3                 # Urbino height 3 300 (incl. roof equipment)
BUS_ROOF_Z = 3.0            # body roofline; roof pods bring it to 3.3 (assumption)
BUS_Z0 = 0.30               # underside of body above road (assumption)
WHEEL_R = 0.48              # 275/70 R22.5 class tyre (assumption)


def _bus_section(x0, x1, rf, rr):
    L = x1 - x0
    mk = lambda: cq.Workplane("XY").box(L, 2 * BUS_HW, BUS_ROOF_Z - BUS_Z0, centered=(False, True, False)).translate((x0, 0, BUS_Z0))
    sect = mk().edges("|X and >Z").fillet(0.28).edges("|X and <Z").fillet(0.06)
    plan = mk()
    if rf:
        plan = plan.edges("|Z and >X").fillet(rf)
    if rr:
        plan = plan.edges("|Z and <X").fillet(rr)
    return sect.intersect(plan).val()


@register("bus")
def build_bus(length_m: float = 12.0, electric: bool = True, lod: int = 2, **_):
    """City bus. length_m 12 -> Urbino 12 (3 axles-free 2-axle, doors 2-2-2); 18 -> articulated Urbino 18 (3 axles, 2-2-2-2)."""
    art = length_m > 13.0
    L = 18.0 if art else 12.0
    x_front, x_rear = L / 2, -L / 2
    rf, rr = 0.45, 0.40
    if not art:
        sections = [(x_rear, x_front, rf, rr)]
        axles = [x_front - 2.7, x_front - 2.7 - 5.9]
        door_x = [4.7, 0.3, -4.5]
        track = [2.12, 1.90]                       # wheel track front/rear (assumption)
    else:
        sections = [(-1.0, x_front, rf, 0.0), (x_rear, -2.6, 0.0, rr)]
        a1 = x_front - 2.7
        axles = [a1, a1 - 5.9, a1 - 5.9 - 6.0]
        door_x = [7.75, 3.3, -3.9, -7.6]
        track = [2.12, 1.90, 1.90]
    bodies, win_cut, win_pane, door_cut, door_leaf = [], [], [], [], []
    d_win, d_door, w_door = 0.04, 0.05, 1.25
    excl_doors = [(x - w_door / 2, x + w_door / 2) for x in door_x]
    for (x0, x1, f, r) in sections:
        bodies.append(_bus_section(x0, x1, f, r))
        lo = x0 + (f + 0.25 if f else 0.45)
        hi = x1 - (r + 0.25 if r else 0.45)
        for s in (+1, -1):
            for a, b in _free(lo, hi, excl_doors if s < 0 else [], pad=0.2):
                for (c, d) in _bays(a, b, 1.45, 0.14):
                    cy0, cy1 = (BUS_HW - d_win, BUS_HW + 0.1) if s > 0 else (-BUS_HW - 0.1, -BUS_HW + d_win)
                    win_cut.append(_box(c, d, cy0, cy1, 1.10, 2.55))
                    y0 = BUS_HW - d_win if s > 0 else -BUS_HW + d_win - 0.015
                    win_pane.append(_box(c, d, y0, y0 + 0.015, 1.10, 2.55))
    # windscreen and rear window (flat part of the rounded ends)
    glass_ends, end_cut = [], []
    fx = x_front
    end_cut.append(_box(fx - 0.05, fx + 0.1, -0.78, 0.78, 1.00, 2.70))
    glass_ends.append(_box(fx - 0.05, fx - 0.035, -0.78, 0.78, 1.00, 2.70))
    rx = x_rear
    end_cut.append(_box(rx - 0.1, rx + 0.05, -0.65, 0.65, 1.60, 2.60))
    glass_ends.append(_box(rx + 0.035, rx + 0.05, -0.65, 0.65, 1.60, 2.60))
    for x in door_x:                                            # doors on the right (-y) side
        door_cut.append(_box(x - w_door / 2, x + w_door / 2, -BUS_HW - 0.1, -BUS_HW + d_door, 0.36, 2.30))
        for k in (-1, +1):
            xa = x - 0.0155 if k < 0 else x + 0.0155
            xb = x - w_door / 2 + 0.02 if k < 0 else x + w_door / 2 - 0.02
            lo_, hi_ = min(xa, xb), max(xa, xb)
            door_leaf.append(_box(lo_, hi_, -BUS_HW + d_door - 0.03, -BUS_HW + d_door, 0.36, 2.30))
    # wheel arches (outer side of each wheel only)
    arch = []
    for ax in axles:
        for s in (+1, -1):
            y0, y1 = (0.88, 1.40) if s > 0 else (-1.40, -0.88)
            arch.append(_cyl_y(0.58, y0, y1, ax, WHEEL_R))
    body_cuts = win_cut + end_cut + door_cut + arch
    bodies2 = []
    for b in bodies:
        bodies2.append(b.cut(*body_cuts) if body_cuts else b)
    wheels = []
    for ax, tr in zip(axles, track):
        for s in (+1, -1):
            yc = s * (1.20 - 0.1375)
            wheels.append(_cyl_y(WHEEL_R, yc - 0.1375, yc + 0.1375, ax, WHEEL_R))
            ho = 0.03
            ya, yb = sorted((yc + s * 0.1375, yc + s * (0.1375 + ho)))
            wheels.append(_cyl_y(0.17, ya, yb, ax, WHEEL_R))
    mirrors = []
    for s in (+1, -1):
        y0, y1 = (1.05, 1.27) if s > 0 else (-1.27, -1.05)
        mirrors.append(_box(x_front - 0.34, x_front - 0.08, y0, y1, 2.15, 2.78))
        ya, yb = (0.90, 1.05) if s > 0 else (-1.05, -0.90)
        mirrors.append(_box(x_front - 0.30, x_front - 0.12, ya, yb, 2.62, 2.70))
    roof = []
    if electric and lod >= 2:
        def pod(xa, xb, hw, h0=BUS_ROOF_Z, h1=BUS_H):
            p = cq.Workplane("XY").box(xb - xa, 2 * hw, h1 - h0, centered=(False, True, False)).translate((xa, 0, h0))
            return p.edges("|Z").fillet(min(0.2, hw * 0.5)).faces(">Z").edges().fillet(0.06).val()
        if not art:
            roof += [pod(2.2, 4.2, 0.80), pod(-5.0, 1.6, 0.95)]            # HVAC + battery pods
        else:
            roof += [pod(5.4, 7.4, 0.80), pod(-0.7, 4.6, 0.95), pod(-8.0, -3.0, 0.95)]
    bellows = None
    if art:
        bellows = _box(-2.6, -1.0, -1.10, 1.10, 0.55, 2.85)
    parts = {"body": _comp(bodies2), "windows": _comp(win_pane), "doors": _comp(door_leaf),
             "glazing_ends": _comp(glass_ends), "wheels": _comp(wheels), "mirrors": _comp(mirrors)}
    if roof:
        parts["roof_equipment"] = _comp(roof)
    if bellows is not None:
        parts["articulation"] = _comp(bellows)
    shape = _comp(*parts.values())
    url = URL_U18 if art else URL_U12
    dims = {"length_m": _src(L, url), "width_m": _src(2.55, f"{url}; EU 96/53/EC Annex I 1.2(a) {URL_EU}"),
            "height_m": _src(BUS_H, url),
            "body_roof_height_m": _asm(BUS_ROOF_Z, "roofline below roof pods; pods bring the total to the sourced 3.3 m"),
            "wheel_diameter_m": _asm(2 * WHEEL_R, "275/70R22.5 class; Solaris sheets give no tyre size"),
            "door_width_m": _asm(w_door, "doors counted 2-2-2(-2) in the source; widths not given")}
    if art:
        dims["wheelbase_1_2_m"] = _src(5.9, url)
        dims["wheelbase_2_3_m"] = _src(6.0, url)
    else:
        dims["wheelbase_m"] = _src(5.9, url)
    dims["front_overhang_m"] = _asm(2.7, "axle positions along the body not in the source sheet")
    meta = {"class": "vehicle", "licence": LICENCE, "generator": GEN, "lod": lod,
            "notes": ("doors on -y (right-hand traffic); mirror heads kept inside the 2.55 m x 12 m envelope so the "
                      "bbox equals the sourced principal dimensions (real mirrors protrude, excluded from width by 96/53/EC); "
                      "axle x positions and section split (articulated) are assumptions"),
            "axles_x": axles, "articulated": art, "door_x": door_x,
            "pivots": {"articulation": {"origin": (-1.8, 0.0, 0.0), "axis": (0, 0, 1)}} if art else {}}
    return AssetModel(shape=shape, parts=parts, dims=dims, meta=meta)


# ================================================================================================= TRAIN
TR_W = 3.2
TR_H = 4.38
TR_ROOF = 4.0
TR_Z0 = 0.60
TR_CAR_L = 127.7 / 6                      # 21.283 m per car, derived from the class 76 set
RAIL_GAUGE = 1.435
TR_WHEEL_R = 0.46


def _pantograph(xb, zb, folded_top, raised_h=None, L1=1.15, L2=1.15, head_len=1.95, r=0.025, roof_z=TR_ROOF):
    head = (xb, folded_top - r) if raised_h is None else (xb, zb + raised_h)
    dx, dz = head[0] - xb, head[1] - zb
    d = math.hypot(dx, dz)
    hh = math.sqrt(max(L1 ** 2 - (d / 2) ** 2, 0.0))
    nx, nz = dz / d, -dx / d
    el = (xb + dx / 2 + hh * nx, zb + dz / 2 + hh * nz)
    items = [_box(xb - 0.6, xb + 0.6, -0.45, 0.45, zb - 0.03, zb),
             _box(xb - 0.45, xb - 0.33, -0.3, -0.18, roof_z, zb - 0.03), _box(xb - 0.45, xb - 0.33, 0.18, 0.3, roof_z, zb - 0.03),
             _box(xb + 0.33, xb + 0.45, -0.3, -0.18, roof_z, zb - 0.03), _box(xb + 0.33, xb + 0.45, 0.18, 0.3, roof_z, zb - 0.03)]
    for y in (-0.3, 0.3):
        items.append(_cyl(r, (xb, y, zb), (el[0], y, el[1])))
        items.append(_cyl(r, (el[0], y, el[1]), (head[0], y, head[1])))
    items.append(_cyl(r, (el[0], -0.3, el[1]), (el[0], 0.3, el[1])))
    items.append(_cyl(r, (head[0], -head_len / 2, head[1]), (head[0], head_len / 2, head[1])))
    meta = {"origin": (xb, 0.0, zb), "axis": (0, 1, 0), "elbow": (el[0], el[1]), "head": head,
            "note": "two-link arm; rotate about origin/axis, or pass raised_h to re-solve the pose"}
    return _comp(items), meta


@register("train")
def build_train(n_cars: int = 4, pantograph_raised_m: float | None = None, lod: int = 2, **_):
    """Regional EMU: n_cars FLIRT-type cars coupled end to end, cab at both ends, Jakobs bogies at the joints."""
    n = max(1, int(n_cars))
    Lc = TR_CAR_L
    total = n * Lc
    x_start = -total / 2
    rc = 0.9                                              # plan radius of cab corners
    cuts_cab_rear, cars, wins, win_cuts, doors, panes = [], [], [], [], [], []
    bogie_x = [x_start + 3.4] + [x_start + k * Lc for k in range(1, n)] + [x_start + total - 3.4]
    bogie_wb = [2.7] + [2.5] * (n - 1) + [2.7]
    rake = 0.95
    door_w, d_win, d_door = 1.1, 0.05, 0.05
    wheel_wells_all = [(bx - 1.9, bx + 1.9) for bx in bogie_x]
    for i in range(n):
        xa, xb = x_start + i * Lc, x_start + (i + 1) * Lc
        front, rear = i == n - 1, i == 0
        cx = (xa + xb) / 2
        sect = (cq.Workplane("XY").box(Lc, TR_W, TR_ROOF - TR_Z0, centered=(False, True, False)).translate((xa, 0, TR_Z0))
                .edges("|X and >Z").fillet(0.9).edges("|X and <Z").fillet(0.15))
        plan = cq.Workplane("XY").box(Lc, TR_W, TR_ROOF - TR_Z0, centered=(False, True, False)).translate((xa, 0, TR_Z0))
        if front:
            plan = plan.edges("|Z and >X").fillet(rc)
        if rear:
            plan = plan.edges("|Z and <X").fillet(rc)
        body = sect.intersect(plan).val()
        cut_list = []
        for sgn, is_cab in ((+1, front), (-1, rear)):
            if not is_cab:
                continue
            xe = xb if sgn > 0 else xa
            pts = [(xe, 2.2), (xe - sgn * rake, TR_ROOF), (xe - sgn * rake, 4.7), (xe + sgn * 1.0, 4.7), (xe + sgn * 1.0, 2.2)]
            cut_list.append(cq.Workplane("XZ").polyline(pts).close().extrude(2.2, both=True).val())
            # windscreen pocket + pane on the raked plane
            t = math.hypot(rake, TR_ROOF - 2.2)
            ux, uz = -sgn * rake / t, (TR_ROOF - 2.2) / t               # along the rake, upward
            nx_, nz_ = -sgn * (TR_ROOF - 2.2) / t * -1.0, 0.0
            # inward normal (into the body): perpendicular to (ux,uz), pointing -x*sgn and -z
            inx, inz = -sgn * (TR_ROOF - 2.2) / t, -rake / t
            s0, s1 = 0.30, 1.62                                             # extent along the rake from its lower end
            def quad(off0, off1):
                p = [(xe + ux * s0 + inx * off0, 2.2 + uz * s0 + inz * off0), (xe + ux * s1 + inx * off0, 2.2 + uz * s1 + inz * off0),
                     (xe + ux * s1 + inx * off1, 2.2 + uz * s1 + inz * off1), (xe + ux * s0 + inx * off1, 2.2 + uz * s0 + inz * off1)]
                return cq.Workplane("XZ").polyline(p).close().extrude(0.65, both=True).val()
            cut_list.append(quad(-0.05, 0.05))
            panes.append(quad(0.05 - 0.015, 0.05))
        # doors, windows (both sides)
        loc = lambda x: x
        door_c = []
        for sgn in (+1, -1):
            end_is_cab = (sgn > 0 and front) or (sgn < 0 and rear)
            door_c.append(cx + sgn * (Lc / 2 - (4.6 if end_is_cab else 2.5)))
        excl = [(c - door_w / 2, c + door_w / 2) for c in door_c]
        if front:
            excl.append((xb - 3.2, xb))
        if rear:
            excl.append((xa, xa + 3.2))
        for s in (+1, -1):
            for c in door_c:
                y0, y1 = (TR_W / 2 - d_door, TR_W / 2 + 0.1) if s > 0 else (-TR_W / 2 - 0.1, -TR_W / 2 + d_door)
                cut_list.append(_box(c - door_w / 2, c + door_w / 2, y0, y1, 0.75, 2.75))
                for k in (-1, +1):
                    lo_ = c - door_w / 2 + 0.02 if k < 0 else c + 0.0155
                    hi_ = c - 0.0155 if k < 0 else c + door_w / 2 - 0.02
                    yy = (TR_W / 2 - d_door, TR_W / 2 - d_door + 0.03) if s > 0 else (-TR_W / 2 + d_door - 0.03, -TR_W / 2 + d_door)
                    doors.append(_box(lo_, hi_, yy[0], yy[1], 0.75, 2.75))
            for a, b in _free(xa + 0.8, xb - 0.8, excl, pad=0.3):
                for (c, d) in _bays(a, b, 1.6, 0.3):
                    y0, y1 = (TR_W / 2 - d_win, TR_W / 2 + 0.1) if s > 0 else (-TR_W / 2 - 0.1, -TR_W / 2 + d_win)
                    cut_list.append(_box(c, d, y0, y1, 1.55, 2.90))
                    yy = (TR_W / 2 - d_win, TR_W / 2 - d_win + 0.015) if s > 0 else (-TR_W / 2 + d_win - 0.015, -TR_W / 2 + d_win)
                    wins.append(_box(c, d, yy[0], yy[1], 1.55, 2.90))
        for (lo, hi) in wheel_wells_all:
            if hi > xa and lo < xb:
                cut_list.append(_box(max(lo, xa - 0.1), min(hi, xb + 0.1), -0.97, 0.97, 0.5, 1.0))
        cars.append(body.cut(*cut_list))
    # bogies
    bog = []
    for bx, wb in zip(bogie_x, bogie_wb):
        for s in (+1, -1):
            bog.append(_box(bx - wb / 2 - 0.1, bx + wb / 2 + 0.1, s * 0.95 - 0.1, s * 0.95 + 0.1, 0.36, 0.58))
        bog.append(_box(bx - 0.15, bx + 0.15, -0.95, 0.95, 0.38, 0.58))
        for ax in (-wb / 2, wb / 2):
            bog.append(_cyl_y(0.06, -0.80, 0.80, bx + ax, TR_WHEEL_R))
            for s in (+1, -1):
                y0 = s * (RAIL_GAUGE / 2 - 0.06) if s > 0 else -(RAIL_GAUGE / 2 + 0.07)
                bog.append(_cyl_y(TR_WHEEL_R, y0, y0 + 0.13, bx + ax, TR_WHEEL_R))
    # underfloor equipment, roof equipment, pantograph
    under = []
    for i in range(n):
        xa = x_start + i * Lc
        for a, b in _free(xa + 0.2, xa + Lc - 0.2, wheel_wells_all, pad=0.25):
            if b - a > 1.2:
                under.append(_box(a, b, -1.15, 1.15, 0.40, TR_Z0))
    pant_car = 1 if n > 1 else 0
    pcx = x_start + (pant_car + 0.5) * Lc
    pg, pmeta = _pantograph(pcx, TR_ROOF + 0.2, TR_H, raised_h=pantograph_raised_m)
    roof_eq = []
    for i in range(n):
        cx = x_start + (i + 0.5) * Lc
        off = 4.5 if i == pant_car else 0.0
        roof_eq.append(_box(cx + off - 1.5, cx + off + 1.5, -0.6, 0.6, TR_ROOF - 0.02, TR_ROOF + 0.2))
    parts = {"body": _comp(cars), "windows": _comp(wins), "doors": _comp(doors), "windscreen": _comp(panes),
             "bogies": _comp(bog), "underfloor": _comp(under), "roof_equipment": _comp(roof_eq), "pantograph": pg}
    shape = _comp(*parts.values())
    dims = {"length_m": _src(total, f"{n} x car {Lc:.3f} m = 127.7 m / 6 cars (class 76 over couplers) {URL_F76}"),
            "width_m": _src(TR_W, URL_F76), "height_m": _src(TR_H, f"{URL_F76} (above rail top, pantograph folded)"),
            "car_length_m": _src(Lc, f"derived: 127.7 m over couplers / 6 cars, {URL_F76}"),
            "motor_bogie_wheelbase_m": _src(2.7, URL_FNORD), "trailer_bogie_wheelbase_m": _src(2.5, URL_FNORD),
            "door_clear_width_m": _src(door_w, URL_FNORD),
            "track_gauge_m": _src(RAIL_GAUGE, "standard gauge, UIC / Bane NOR network"),
            "wheel_diameter_m": _asm(2 * TR_WHEEL_R, "new-wheel diameter not in the cited sheets"),
            "roof_height_m": _asm(TR_ROOF, "roofline below the folded pantograph"),
            "floor_height_m": _asm(0.95, "FLIRT Nordic high-floor 1.2 m cited by Stadler; regional low-floor entrance differs")}
    meta = {"class": "vehicle", "licence": LICENCE, "generator": GEN, "lod": lod, "n_cars": n,
            "notes": ("origin = rail top at the train centre; car lengths equal (derived average, real cab cars are longer); "
                      "Jakobs bogies at car joints, cab bogies 3.4 m from the ends (assumption); pantograph folded unless "
                      "pantograph_raised_m given"),
            "bogie_x": bogie_x, "pivots": {"pantograph": pmeta}}
    return AssetModel(shape=shape, parts=parts, dims=dims, meta=meta)


# ================================================================================================ PERSON
# fractions of stature H: Winter 2005 Fig. 4.1 (Drillis & Contini 1966)
SEG = {"head_neck": 0.182, "shoulder_height": 0.818, "hip_height": 0.530, "knee_height": 0.285, "ankle_height": 0.039,
       "upper_arm": 0.186, "forearm": 0.146, "hand": 0.108, "thigh": 0.245, "shank": 0.246, "foot_length": 0.152,
       "shoulder_width": 0.259, "hip_width": 0.191, "head_height": 0.130}


def _limb(p0, p1, r0, r1):
    c = _cone(p0, p1, r0, r1)
    return _fuse(c, cq.Solid.makeSphere(r0, V(*p0)), cq.Solid.makeSphere(r1, V(*p1)))


@register("person")
def build_person(stature_m: float = 1.75, pose: str = "standing", phase: float = 0.0, hard_hat: bool = False,
                 survival_suit: bool = False, lod: int = 2, **_):
    """Anthropometric figure. pose 'standing' | 'walking' (phase 0..1 = gait cycle, 0 = left leg mid-swing)."""
    H = float(stature_m)
    k_l, k_t = (1.28, 1.20) if survival_suit else (1.0, 1.0)
    hipy = SEG["hip_width"] * H / 2
    shy = SEG["shoulder_width"] * H / 2
    th = {}
    if pose == "walking":
        w = 2 * math.pi * phase
        for side, ph in (("l", w), ("r", w + math.pi)):
            hip = math.radians(26) * math.sin(ph)
            knee = math.radians(4 + 52 * max(0.0, math.cos(ph)))
            th[side] = (hip, knee)
    elif pose != "standing":
        raise ValueError("pose must be 'standing' or 'walking'")
    else:
        th = {"l": (0.0, 0.0), "r": (0.0, 0.0)}
    # leg kinematics (hip at z=0 first), find the lowest sole point to put the figure on the ground
    kin = {}
    zmin = 1e9
    for side, ys in (("l", +1), ("r", -1)):
        hip, knee = th[side]
        kx = SEG["thigh"] * H * math.sin(hip)
        kz = -SEG["thigh"] * H * math.cos(hip)
        sh = hip - knee
        ax_ = kx + SEG["shank"] * H * math.sin(sh)
        az_ = kz - SEG["shank"] * H * math.cos(sh)
        pitch = 0.5 * sh * min(1.0, max(0.0, (abs(sh) - 0.12) / 0.12)) if pose == "walking" else 0.0   # stance foot stays flat
        fw = 0.058 * H * (1.25 if survival_suit else 1.0)
        foot = (cq.Workplane("XY").box(0.152 * H, fw, 0.059 * H, centered=False)
                .translate((-0.045 * H, -fw / 2, -SEG["ankle_height"] * H)).edges("|Y").fillet(0.012 * H).val())
        foot = foot.rotate(V(0, 0, 0), V(0, 1, 0), -math.degrees(pitch)).translate(V(ax_, ys * hipy, az_))
        zmin = min(zmin, foot.BoundingBox().zmin)
        kin[side] = (kx, kz, ax_, az_, foot)
    hip_z = -zmin                                   # hip joint height so that the lowest sole is at z=0
    drop = hip_z - SEG["hip_height"] * H            # <= 0 in gait (centre of mass dips)
    zs = lambda z: z + drop                         # shift standing-height z to the posed height
    parts = {}
    # --- legs and feet
    for side, ys in (("l", +1), ("r", -1)):
        kx, kz, ax_, az_, foot = kin[side]
        hip_p = (0.0, ys * hipy, hip_z)
        knee_p = (kx, ys * hipy, hip_z + kz)
        ank_p = (ax_, ys * hipy, hip_z + az_)
        thigh = _limb(hip_p, knee_p, 0.050 * H * k_l, 0.036 * H * k_l)
        shank = _limb(knee_p, ank_p, 0.035 * H * k_l, 0.021 * H * k_l)
        foot = foot.translate(V(0, 0, hip_z))
        parts[f"leg_{side}"] = _comp(thigh, shank, foot)
    # --- torso (loft of ellipses; ellipse(a=depth along x, b=width along y))
    secs = [(0.50, 0.062, 0.092), (0.58, 0.058, 0.084), (0.64, 0.056, 0.078), (0.72, 0.066, 0.090), (0.79, 0.060, 0.104),
            (0.835, 0.040, 0.066)]
    wp = cq.Workplane("XY").workplane(offset=zs(secs[0][0] * H))
    wp = wp.ellipse(secs[0][1] * H * k_t, secs[0][2] * H * k_t)
    for (z_prev, _, _), (z, a, b) in zip(secs, secs[1:]):
        wp = wp.workplane(offset=(z - z_prev) * H).ellipse(a * H * k_t, b * H * k_t)
    torso = wp.loft(combine=True).val()
    # --- arms
    for side, ys in (("l", +1), ("r", -1)):
        opp = th["r" if side == "l" else "l"][0]
        al = 0.85 * opp
        el = math.radians(8) + (math.radians(22) * max(0.0, math.sin(al)) if pose == "walking" else 0.0)
        ab = 0.07
        sh_p = (0.0, ys * shy, zs(SEG["shoulder_height"] * H) - 0.010 * H)
        d1 = (math.sin(al), ys * ab, -math.cos(al))
        n1 = math.sqrt(sum(c * c for c in d1))
        el_p = tuple(sh_p[i] + SEG["upper_arm"] * H * d1[i] / n1 for i in range(3))
        d2 = (math.sin(al + el), ys * ab, -math.cos(al + el))
        n2 = math.sqrt(sum(c * c for c in d2))
        wr_p = tuple(el_p[i] + SEG["forearm"] * H * d2[i] / n2 for i in range(3))
        hd_p = tuple(wr_p[i] + SEG["hand"] * H * d2[i] / n2 for i in range(3))
        ua = _limb(sh_p, el_p, 0.030 * H * k_l, 0.023 * H * k_l)
        fa = _limb(el_p, wr_p, 0.023 * H * k_l, 0.016 * H * k_l)
        hd = _limb(wr_p, hd_p, 0.016 * H * k_l, 0.010 * H * (1.4 if survival_suit else 1.0))
        parts[f"arm_{side}"] = _comp(ua, fa, hd)
    # --- neck and head: head spheroid top exactly at stature
    head_c = zs(H - 0.065 * H)
    head = _spheroid(0.050 * H, 0.065 * H, 0.008 * H, 0.0, head_c)
    neck = _cyl(0.035 * H * (1.4 if survival_suit else 1.0), (0, 0, zs(0.815 * H)), (0, 0, zs(H - 0.110 * H)))
    parts["torso"] = _comp(torso)
    parts["head"] = _comp(head, neck)
    top = H + drop
    if hard_hat:
        zc = head_c + 0.025 * H
        dome = _spheroid(0.058 * H, 0.065 * H, 0.008 * H, 0.0, zc)
        dome = dome.intersect(_box(-1, 1, -1, 1, zc, zc + 1))
        brim = _cyl(0.072 * H, (0.008 * H, 0, zc - 0.006 * H), (0.008 * H, 0, zc))
        parts["hard_hat"] = _comp(dome, brim)
        top = zc + 0.065 * H
    shape = _comp(*parts.values())
    dims = {"stature_m": _src(H, "caller parameter (standing stature); segment ratios " + URL_WINTER),
            "height_m": {"value": top, "src": "stature (+ hard-hat crown, - gait dip when walking); " + URL_WINTER}}
    seg = {k: _src(v * H, URL_WINTER) for k, v in SEG.items()}
    seg["body_cross_sections"] = {"assumption": True, "note": "segment radii/torso ellipses are typical adult values, not from the cited table"}
    meta = {"class": "person", "licence": LICENCE, "generator": GEN, "lod": lod, "pose": pose, "phase": phase,
            "hard_hat": hard_hat, "survival_suit": survival_suit, "segments_m": seg, "gait_dip_m": drop,
            "notes": "capsule limbs, lofted torso, spheroid head; walking = sagittal gait with arm counter-swing (assumption)"}
    return AssetModel(shape=shape, parts=parts, dims=dims, meta=meta)


# ================================================================================================== TREE
SPECIES = {
    # height, crown_w/H, slenderness H/dbh, crown base fraction. The spruce default (30 m, crown 8.4 m) is the LOW END
    # of the cited mature range (30-46 m, spread 7.6-13.7 m), so it is sourced, not assumed; pine/birch defaults sit
    # inside a cited maximum only ("to 25 m" / "up to 24 m") with no cited spread, so they stay assumptions.
    "spruce": dict(h=30.0, cw=0.28, slender=60.0, base=0.10),
    "pine": dict(h=22.0, cw=0.30, slender=55.0, base=0.50),
    "birch": dict(h=16.0, cw=0.40, slender=70.0, base=0.25),
}
TREE_SRC = ("Norway spruce 30-46 m, spread 7.6-13.7 m https://dimensions.com/element/norway-spruce-picea-abies ; Scots pine to 25 m "
            "https://www.rhs.org.uk/plants/13141/i-Pinus-sylvestris-i/Details ; silver birch to 24 m "
            "https://www.forestryandland.gov.scot/learn/trees/silver-birch")


def _envelope(sp, H, W, zb):
    R = W / 2
    if sp == "spruce":
        prof = [(0, zb), (R, zb), (R * 0.78, zb + 0.28 * (H - zb)), (R * 0.46, zb + 0.6 * (H - zb)), (0, H)]
        return cq.Workplane("XZ").polyline(prof).close().revolve(360, (0, 0, 0), (0, 1, 0)).val()
    if sp == "pine":
        zc, b = zb + 0.55 * (H - zb), 0.45 * (H - zb)
        return _spheroid(R, b, 0, 0, zc)
    zc, b = zb + 0.52 * (H - zb), 0.48 * (H - zb)
    return _spheroid(R, b, 0, 0, zc)


def _inside(sp, H, W, zb):
    R = W / 2
    if sp == "spruce":
        def f(x, y, z):
            if z < zb or z > H:
                return False
            return math.hypot(x, y) <= R * ((H - z) / (H - zb)) ** 0.95 + 1e-9
    else:
        frac, hh = (0.55, 0.45) if sp == "pine" else (0.52, 0.48)
        zc, b = zb + frac * (H - zb), hh * (H - zb)
        def f(x, y, z):
            return (x * x + y * y) / (R * R) + (z - zc) ** 2 / (b * b) <= 1.0
    return f


def _unit(v):
    n = math.sqrt(sum(c * c for c in v)) or 1.0
    return tuple(c / n for c in v)


def _perp(d, ang):
    ref = (0, 0, 1) if abs(d[2]) < 0.9 else (1, 0, 0)
    a = _unit((d[1] * ref[2] - d[2] * ref[1], d[2] * ref[0] - d[0] * ref[2], d[0] * ref[1] - d[1] * ref[0]))
    b = (d[1] * a[2] - d[2] * a[1], d[2] * a[0] - d[0] * a[2], d[0] * a[1] - d[1] * a[0])
    return tuple(math.cos(ang) * a[i] + math.sin(ang) * b[i] for i in range(3))


@register("tree")
def build_tree(species: str = "spruce", seed: int = 0, height_m: float | None = None, crown_width_m: float | None = None,
               lod: int = 2, **_):
    """Procedural tree. LOD 2: trunk + primary branches + crown envelope solid; LOD 3 adds twigs. Same seed -> same tree."""
    if species not in SPECIES:
        raise ValueError(f"species must be one of {sorted(SPECIES)}")
    sp = SPECIES[species]
    H = float(height_m or sp["h"])
    W = float(crown_width_m or sp["cw"] * H)
    rng = random.Random(f"{species}:{seed}")
    zb = sp["base"] * H
    inside = _inside(species, H, W, zb)
    r0 = H / sp["slender"] / 2 * 1.05
    # trunk centre line
    n_t = 12
    amp = {"spruce": 0.0, "pine": 0.018 * H, "birch": 0.014 * H}[species]
    ph, az = rng.uniform(0, 6.28), rng.uniform(0, 6.28)
    tp = []
    for i in range(n_t + 1):
        t = i / n_t
        o = amp * math.sin(math.pi * t) * (math.sin(3 * t + ph) * 0.6 + 0.4) if i > 1 else 0.0     # vertical base: sole at z=0
        tp.append((o * math.cos(az), o * math.sin(az), H * t))
    taper = lambda t: max(r0 * (1 - t) ** 0.9 * (1 + 0.15 * (1 - t) ** 6), 0.0)
    trunk = [_cone(tp[i], tp[i + 1], taper(i / n_t), taper((i + 1) / n_t)) for i in range(n_t)]
    zt = lambda z: tp[min(n_t, int(z / H * n_t + 0.5))]
    segs = []                       # (p0, p1, r0, r1, level)

    def add_branch(p0, d, length, rb, level, droop):
        """two-segment curved branch; tip kept inside the crown envelope."""
        for _ in range(24):
            mid = (p0[0] + d[0] * length * 0.5, p0[1] + d[1] * length * 0.5, p0[2] + d[2] * length * 0.5 - droop * length * 0.05)
            tip = (p0[0] + d[0] * length, p0[1] + d[1] * length, p0[2] + d[2] * length - droop * length * 0.12 + (0.10 * length if droop > 0 else 0))
            if inside(*tip) and tip[2] < H - 0.02 and tip[2] > 0.1:
                break
            length *= 0.9
        else:
            return None
        rt = max(rb * 0.12, 0.003)
        segs.append((p0, mid, rb, rb * 0.55, level))
        segs.append((mid, tip, rb * 0.55, rt, level))
        return p0, mid, tip, length

    prim = []
    if species == "spruce":
        z = zb
        while z < H * 0.97:
            nb = rng.choice((4, 5, 5, 6))
            a0 = rng.uniform(0, 2 * math.pi)
            R = W / 2 * ((H - z) / (H - zb)) ** 0.95
            base_t = zt(z)
            for k in range(nb):
                a = a0 + 2 * math.pi * k / nb + rng.uniform(-0.2, 0.2)
                el = rng.uniform(-0.05, 0.10) - 0.10 * (H - z) / (H - zb) * 0 + (-0.22 * (1 - (z - zb) / (H - zb)))
                d = _unit((math.cos(a) * math.cos(el), math.sin(a) * math.cos(el), math.sin(el)))
                rb = max(0.012, 0.28 * taper(z / H) * rng.uniform(0.8, 1.1))
                p0 = (base_t[0], base_t[1], z)
                b = add_branch(p0, d, max(R, 0.3) * rng.uniform(0.82, 1.0), rb, 1, 1.0)
                if b:
                    prim.append(b)
            z += H * 0.035 * rng.uniform(0.9, 1.1)
    elif species == "pine":
        z = 0.22 * H
        while z < zb:                                         # dead stubs on the lower trunk
            a0 = rng.uniform(0, 6.28)
            for k in range(3):
                a = a0 + 2.09 * k
                d = _unit((math.cos(a), math.sin(a), rng.uniform(-0.1, 0.15)))
                b = add_branch(zt(z)[:2] + (z,), d, rng.uniform(0.3, 0.8), 0.015, 1, 0.0)
                if b:
                    prim.append(b)
            z += 0.09 * H
        z = zb
        while z < H * 0.97:
            nb = rng.choice((3, 4, 4, 5))
            a0 = rng.uniform(0, 6.28)
            for k in range(nb):
                a = a0 + 2 * math.pi * k / nb + rng.uniform(-0.3, 0.3)
                el = rng.uniform(0.0, 0.45)
                d = _unit((math.cos(a) * math.cos(el), math.sin(a) * math.cos(el), math.sin(el)))
                rb = max(0.012, 0.30 * taper(z / H) * rng.uniform(0.8, 1.1))
                b = add_branch(zt(z)[:2] + (z,), d, W / 2 * rng.uniform(0.7, 1.0), rb, 1, 0.0)
                if b:
                    prim.append(b)
            z += H * 0.05 * rng.uniform(0.9, 1.1)
    else:                                                      # birch: ascending, then drooping twigs
        n_b = int(H * 1.3)
        for k in range(n_b):
            z = zb + (0.95 * H - zb) * (k + rng.uniform(0, 1)) / n_b
            a = rng.uniform(0, 2 * math.pi)
            el = math.radians(rng.uniform(25, 60))
            d = _unit((math.cos(a) * math.cos(el), math.sin(a) * math.cos(el), math.sin(el)))
            rb = max(0.012, 0.30 * taper(z / H))
            b = add_branch(zt(z)[:2] + (z,), d, W / 2 * rng.uniform(0.6, 1.0), rb, 1, 0.6)
            if b:
                prim.append(b)
    if lod >= 3:
        for (p0, mid, tip, length) in prim:
            n_tw = {"spruce": 7, "pine": 4, "birch": 5}[species]
            for j in range(n_tw):
                u = rng.uniform(0.25, 0.95)
                src_p = (p0[0] + (tip[0] - p0[0]) * u, p0[1] + (tip[1] - p0[1]) * u, p0[2] + (tip[2] - p0[2]) * u)
                bd = _unit((tip[0] - p0[0], tip[1] - p0[1], tip[2] - p0[2]))
                ang = rng.uniform(0, 6.28)
                spread = {"spruce": 0.9, "pine": 0.7, "birch": 0.8}[species]
                pd = _perp(bd, ang)
                d = _unit(tuple(bd[i] * (1 - spread * 0.5) + pd[i] * spread for i in range(3)))
                if species in ("birch", "spruce"):
                    d = _unit((d[0], d[1], d[2] - 0.35))
                tl = length * rng.uniform(0.10, 0.25)
                for _ in range(10):
                    t_ = (src_p[0] + d[0] * tl, src_p[1] + d[1] * tl, src_p[2] + d[2] * tl)
                    if inside(*t_) and 0.1 < t_[2] < H - 0.02:
                        segs.append((src_p, t_, 0.008, 0.0015, 2))
                        break
                    tl *= 0.8
    # keep everything inside the crown width (scale horizontally about the axis if a trunk lean pushed it out)
    items = [s for s in trunk if s is not None]
    branches = [_cone(a, b, r0_, r1_) for (a, b, r0_, r1_, lv) in segs]
    twigs = [c for c, s in zip(branches, segs) if s[4] == 2]
    prim_c = [c for c, s in zip(branches, segs) if s[4] == 1]
    env = _envelope(species, H, W, zb)
    parts = {"trunk": _comp(items), "branches": _comp([c for c in prim_c if c is not None]), "crown": _comp(env)}
    if twigs:
        parts["twigs"] = _comp([c for c in twigs if c is not None])
    shape = _comp(*parts.values())
    if height_m is not None:
        h_dim = _src(H, "caller parameter")
    elif species == "spruce":
        h_dim = _src(H, "default = low end of the cited mature range 30-46 m: " + TREE_SRC)
    else:
        h_dim = _asm(H, f"species default inside cited range: {TREE_SRC}")
    if crown_width_m is not None:
        crown = _src(W, "caller parameter")
    elif species == "spruce":
        crown = _src(W, "default 0.28 x height = 8.4 m, inside the cited spread 7.6-13.7 m: " + TREE_SRC)
    else:
        crown = _asm(W, f"default {sp['cw']:.2f} x height; spruce spread/height ~0.25-0.30 (dimensions.com 7.6-13.7 m for 30-46 m)")
    dims = {"height_m": h_dim,
            "crown_width_m": crown,
            "crown_diameter_m": dict(crown),  # same physical quantity under the registry's required-dim name
            "dbh_m": _asm(H / sp["slender"], "slenderness ratio H/DBH assumed per species")}
    meta = {"class": "tree", "licence": LICENCE, "generator": GEN, "lod": lod, "species": species, "seed": seed,
            "n_primary_branches": len(prim), "n_segments": len(segs), "crown_base_m": zb,
            "notes": "foliage is the 'crown' envelope solid; branch tips are constrained inside it; deterministic per (species, seed)"}
    return AssetModel(shape=shape, parts=parts, dims=dims, meta=meta)


# ============================================================================================== BUILDING
FLOOR_H = 3.0                    # offsim.worlds.osm.LEVEL_HEIGHT_M (assumption)

# Default building: Molde Mølle, Molde — a real OSM footprint with a height tag, so the default asset's principal
# dims are sourced, not assumed. Footprint corners (lon/lat, closed ring implied) and height=19 / building:levels=5
# read from OSM way 1355114723 (Overpass 2026-11-12; © OpenStreetMap contributors, ODbL 1.0). Projected to local
# metres by build_building (azimuthal equidistant about the footprint centroid); length/width are the projected
# footprint bounds, so they measure exactly what the solid is.
_MOLDE_MOLLE = {
    "way": 1355114723, "name": "Molde Mølle",
    "footprint_lonlat": [(7.182409, 62.736456), (7.182733, 62.736514), (7.182828, 62.736412),
                         (7.182513, 62.736352), (7.182492, 62.736372)],
    "height_m": 19.0, "levels": 5,
}
_MOLDE_MOLLE_SRC = (f"OSM way {_MOLDE_MOLLE['way']} ({_MOLDE_MOLLE['name']}, Molde; "
                    "© OpenStreetMap contributors, ODbL 1.0)")


@functools.lru_cache(maxsize=8)
def _aeqd(lon0, lat0):
    import pyproj
    return pyproj.Transformer.from_crs("EPSG:4326", f"+proj=aeqd +lat_0={lat0} +lon_0={lon0} +datum=WGS84 +units=m +no_defs",
                                       always_xy=True)


def _project(geom, origin_lonlat):
    t = _aeqd(round(origin_lonlat[0], 7), round(origin_lonlat[1], 7))
    import shapely
    return shapely.transform(geom, lambda c: np.column_stack(t.transform(c[:, 0], c[:, 1])))


def _as_polygon(footprint):
    from shapely.geometry import Polygon, shape
    if isinstance(footprint, dict):
        return shape(footprint)
    if isinstance(footprint, (list, tuple)):
        return Polygon(footprint)
    return footprint


def _face(poly, z0=0.0):
    ext = cq.Wire.makePolygon([V(x, y, z0) for x, y in poly.exterior.coords[:-1]], close=True)
    holes = [cq.Wire.makePolygon([V(x, y, z0) for x, y in r.coords[:-1]], close=True) for r in poly.interiors]
    return cq.Face.makeFromWires(ext, holes)


def _extrude(poly, h, z0=0.0):
    return cq.Solid.extrudeLinear(_face(poly, z0), V(0, 0, h))


def _clean_poly(poly):
    from shapely.geometry.polygon import orient
    p = poly.buffer(0)
    if p.geom_type == "MultiPolygon":
        p = max(p.geoms, key=lambda g: g.area)
    p = p.simplify(0.02, preserve_topology=True)
    return orient(p, 1.0)


def _build_one(poly, height, roof, lod, pitch_deg=30.0, max_windows=100):
    """poly in metres (CCW). Returns (parts dict, info dict)."""
    info = {"floors": None}
    walls_h, roof_part = height, None
    rise = 0.0
    if lod <= 1:
        return {"walls": _extrude(poly, height)}, {"floors": max(1, round(height / FLOOR_H)), "wall_height_m": height}
    if roof == "gable":
        mrr = poly.minimum_rotated_rectangle
        c = list(mrr.exterior.coords)
        e0 = (c[1][0] - c[0][0], c[1][1] - c[0][1])
        e1 = (c[2][0] - c[1][0], c[2][1] - c[1][1])
        l0, l1 = math.hypot(*e0), math.hypot(*e1)
        (lx, ly), long_, short_ = (e0, l0, l1) if l0 >= l1 else (e1, l1, l0)
        ang = math.degrees(math.atan2(ly, lx))
        rise = min(0.5 * short_ * math.tan(math.radians(pitch_deg)), 0.35 * height)
        walls_h = height - rise
        cx, cy = mrr.centroid.x, mrr.centroid.y
        prof = [(-short_ / 2 - 0.01, walls_h), (short_ / 2 + 0.01, walls_h), (0, height)]
        prism = (cq.Workplane("YZ").polyline(prof).close().extrude((long_ + 2.0) / 2, both=True).val()
                 .rotate(V(0, 0, 0), V(0, 0, 1), ang).translate(V(cx, cy, 0)))
        roof_part = _extrude(poly, height).intersect(prism)
        walls = _extrude(poly, walls_h)
    else:
        slab = min(0.3, height * 0.1)
        walls_h = height - slab
        walls = _extrude(poly, walls_h)
        roof_part = _extrude(poly, slab, walls_h)
    n_fl = max(1, round(walls_h / FLOOR_H))
    fh = walls_h / n_fl
    info.update(floors=n_fl, floor_height_m=fh, wall_height_m=walls_h, roof_rise_m=rise)
    inner = poly.buffer(-0.03, join_style=2)
    tools, panes = [], []
    if n_fl > 1 and not inner.is_empty and inner.geom_type == "Polygon":
        ring = _extrude(poly, 0.06).cut(_extrude(inner, 0.06))
        for k in range(1, n_fl):
            tools.append(ring.translate(V(0, 0, k * fh - 0.03)))
    win_w, win_h, sill, pitch, dep = 1.2, 1.4, 0.9, 3.0, 0.05
    if fh >= 2.4:
        def layout(pt):
            out = []
            for ring_ in [poly.exterior] + list(poly.interiors):
                cs = list(ring_.coords)
                for (x0, y0), (x1, y1) in zip(cs, cs[1:]):
                    el = math.hypot(x1 - x0, y1 - y0)
                    if el < 2.4:
                        continue
                    ux, uy = (x1 - x0) / el, (y1 - y0) / el          # outward normal is (uy, -ux): CCW exterior, CW holes
                    nw = max(1, int((el - 1.2) // pt))
                    ang = math.degrees(math.atan2(uy, ux))
                    step = (el - 1.2) / nw if nw > 1 else 0.0
                    for j in range(nw):
                        s_ = el / 2 + (j - (nw - 1) / 2) * step
                        for k in range(n_fl):
                            out.append((x0 + ux * s_, y0 + uy * s_, k * fh + sill, ang))
            return out
        lay = layout(pitch)
        while len(lay) > max_windows and pitch < 60:                  # booleans cost ~7 ms per window: thin out big facades
            pitch *= 1.25
            lay = layout(pitch)
        if len(lay) > max_windows:                                    # still too many (one per edge per floor): stride
            k_ = math.ceil(len(lay) / max_windows)
            lay = [w for i, w in enumerate(lay) if i % k_ == 0]
        wbox = _box(-win_w / 2, win_w / 2, -dep, 0.2, 0, win_h)
        pbox = _box(-win_w / 2, win_w / 2, -dep, -dep + 0.015, 0, win_h)
        for (px, py, pz, ang) in lay:
            loc = cq.Location(V(px, py, pz), V(0, 0, 1), ang)
            tools.append(wbox.moved(loc))
            if lod >= 3:
                panes.append(pbox.moved(loc))
        info["windows"] = len(lay)
        info["window_pitch_m"] = pitch
    if tools:
        walls = walls.cut(*tools)
    parts = {"walls": walls}
    if roof_part is not None:
        parts["roof"] = roof_part
    if panes:
        parts["windows"] = _comp(panes)
    return parts, info


@register("building")
def build_building(footprint=None, height_m: float | None = None, roof: str = "flat", lod: int = 2, crs: str = "metres",
                   origin=None, levels: float | None = None, pitch_deg: float = 30.0, max_windows: int = 100, **_):
    """Extruded real footprint. footprint: shapely Polygon / coordinate list / GeoJSON geometry; crs 'metres' or 'lonlat'.
    height_m = total height to the top (OSM `height`); gable roofs take their rise out of it. Origin of the model = the
    footprint centroid (returned in meta['origin']) unless `origin` is given (same crs as the footprint). No footprint
    given: the default is Molde Mølle (OSM way 1355114723, height 19 m) — see _MOLDE_MOLLE."""
    default_fp = footprint is None
    if default_fp:
        footprint = _MOLDE_MOLLE["footprint_lonlat"]
        crs = "lonlat"
    poly = _as_polygon(footprint)
    if poly.geom_type == "MultiPolygon":
        poly = max(poly.geoms, key=lambda g: g.area)
    if crs == "lonlat":
        o = origin or (poly.centroid.x, poly.centroid.y)
        poly = _project(poly, o)
        origin_out = {"lonlat": tuple(o)}
    else:
        o = origin or (poly.centroid.x, poly.centroid.y)
        from shapely import affinity
        poly = affinity.translate(poly, -o[0], -o[1])
        origin_out = {"metres": tuple(o)}
    poly = _clean_poly(poly)
    h_given = height_m is not None
    if height_m is None:
        height_m = (levels * FLOOR_H) if levels else (_MOLDE_MOLLE["height_m"] if default_fp else 9.0)
    parts, info = _build_one(poly, float(height_m), roof, lod, pitch_deg, max_windows)
    shape = _comp(*parts.values())
    # length/width are the projected footprint bounds, so they measure exactly what the solid is (walls and roof are
    # extrusions of the same polygon; window recesses never extend the bbox)
    L = poly.bounds[2] - poly.bounds[0]
    W = poly.bounds[3] - poly.bounds[1]
    lw_src = (_MOLDE_MOLLE_SRC + " footprint, projected to local metres" if default_fp
              else "caller footprint polygon (projected to local metres)")
    if default_fp and not h_given and levels is None:
        h_dim = _src(height_m, _MOLDE_MOLLE_SRC + f" height={height_m:g} tag")
    elif h_given:
        h_dim = _src(height_m, "caller (OSM height_m / paper)")
    else:
        h_dim = _asm(height_m, "default / levels x 3.0 m")
    dims = {"length_m": _src(L, lw_src), "width_m": _src(W, lw_src), "height_m": h_dim,
            "footprint_area_m2": _src(poly.area, lw_src),
            "floors": _asm(info["floors"], f"round(wall height / {FLOOR_H} m): offsim.worlds.osm.LEVEL_HEIGHT_M")}
    meta = {"class": "building", "licence": LICENCE, "generator": GEN, "lod": lod, "roof": roof, "origin": origin_out,
            "footprint_area_m2": poly.area, **info,
            "notes": ("default footprint is Molde Mølle (OSM way 1355114723); " if default_fp else "")
                     + "floor lines and windows are shallow recesses (lod>=2), glass panes lod 3; floors are an assumption"}
    return AssetModel(shape=shape, parts=parts, dims=dims, meta=meta)


def buildings_from_geojson(path, bbox=None, max_n: int = 500, lod: int = 1, default_height_m: float = 6.0,
                           roof: str = "flat", min_area_m2: float = 4.0) -> AssetModel:
    """One compound for a city block from a buildings GeoJSON (offsim.worlds.osm / user_layers: lon/lat, `height_m`).
    bbox = (minlon, minlat, maxlon, maxlat) filter; features are taken in file order up to max_n. Heights: `height_m`,
    else `height`, else building:levels x 3 m, else default_height_m (counted in meta['n_assumed_height']).
    lod 1 = plain extrusions (fast path, ~1 ms each); lod >= 2 builds each with floor lines/windows (slow, use small max_n).
    All buildings share one local origin (bbox centre, azimuthal-equidistant metres)."""
    from shapely.geometry import box as sbox, shape as sshape
    from offsim.worlds.osm import FT_TO_M, parse_height_m, parse_levels  # noqa: F401  (same parsing rules as the world layer)
    data = json.loads(Path(path).read_text())
    feats = data["features"] if data.get("type") == "FeatureCollection" else [data]
    clip = sbox(*bbox) if bbox else None
    picked = []
    for f in feats:
        g = f.get("geometry")
        if not g or g.get("type") not in ("Polygon", "MultiPolygon"):
            continue
        geom = sshape(g)
        if clip is not None and not geom.intersects(clip):
            continue
        picked.append((geom, f.get("properties") or {}))
        if len(picked) >= max_n:
            break
    if not picked:
        raise ValueError("no building features in bbox")
    if bbox:
        o = ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)
    else:
        b = [g.bounds for g, _ in picked]
        o = ((min(x[0] for x in b) + max(x[2] for x in b)) / 2, (min(x[1] for x in b) + max(x[3] for x in b)) / 2)
    solids, heights, n_default, n_levels, skipped = [], [], 0, 0, 0
    detail_parts = []
    for geom, props in picked:
        h = float("nan")
        for key in ("height_m", "height"):
            if key in props and props[key] is not None:
                h = parse_height_m(props[key])
                if h == h:
                    break
        if h != h:
            lv = parse_levels(props.get("building:levels", props.get("building_levels")))
            h = lv * FLOOR_H if lv == lv else float("nan")
            if h != h:
                h = default_height_m
                n_default += 1
            else:
                n_levels += 1
        pm = _project(geom, o)
        polys = list(pm.geoms) if pm.geom_type == "MultiPolygon" else [pm]
        for p in polys:
            p = _clean_poly(p)
            if p.is_empty or p.area < min_area_m2 or p.geom_type != "Polygon":
                skipped += 1
                continue
            if lod <= 1:
                solids.append(_extrude(p, h))
            else:
                prt, _ = _build_one(p, h, roof, lod)
                solids += list(prt.values())
            heights.append(h)
    comp = _comp(solids)
    dims = {"count": {"value": len(heights), "src": f"{path}"},
            "height_max_m": {"value": max(heights), "src": "GeoJSON height_m / height / levels x 3 m / default (assumption)"}}
    meta = {"class": "building", "licence": LICENCE, "generator": GEN, "lod": lod, "origin": {"lonlat": o},
            "n_buildings": len(heights), "n_assumed_height": n_default + n_levels, "n_default_height": n_default,
            "n_height_from_levels": n_levels, "n_skipped": skipped, "default_height_m": default_height_m,
            "notes": "city block compound in local metres around origin lon/lat; heights without a tag use default_height_m (assumption)"}
    return AssetModel(shape=comp, parts={"buildings": comp}, dims=dims, meta=meta)
