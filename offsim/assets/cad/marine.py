"""Marine CAD assets: platform supply vessel (`psv`) and fixed jacket platform with helideck (`platform_jacket`).

Exact solids at real scale (metres; x forward, y to port, z up). Geometry is built with CadQuery/OpenCASCADE:
hulls are lofted from station sections, tubular members are cylinders between nodes, everything is a named part.

Dimension sources (every principal dimension carries `src` or `assumption`):
  PSV   loa 85 m / depth 8 m / draught 6.5 m : class of the 85 m PSV listed at shipselector.com
        (LOA 85.5 m, depth 7.8 m moulded, design draught 6.5 m, beam 18 m, deck ~800 m2):
        https://shipselector.com/offers/design/towingworkboatfishing-vessel/fire-fightingsupply-vessel/20595-85-meter-platform-supply-vessel
        cross-check UT 717 CD "Island Duchess" LOA 84.5 m, B 17 m, T 6.1 m: https://www.vard.com/shipbuilding/references/island-duchess
        Beam 20 m is a wide-body PSV assumption (the cited 85 m designs are 17-18 m).
  ISO 668 20 ft container 6.058 x 2.438 x 2.591 m (ISO 668:2020 series 1 freight containers, standard 8 ft 6 in high).
  Jacket helideck D 20.88 m: CAP 437 D-value of the Sikorsky S-92 (UK CAA CAP 437, helicopter data table; quoted at
        https://www.pprune.org/rotorheads/395350-s-92-landing-specification.html). Safety net >= 1.5 m wide and
        helideck minimum size 1.0 D: CAP 437 / Offshore Norge 074 helideck manual.
  Jacket geometry (leg batter 1:12, leg OD 1.2 m, bay count, deck heights) is generic North Sea practice: assumptions.
"""
from __future__ import annotations

import math

import numpy as np
import cadquery as cq
from cadquery import Vector as V

from .base import AssetModel, register

# --------------------------------------------------------------------------------------------- helpers
ISO_20FT = (6.058, 2.438, 2.591)  # ISO 668 length, width, height (m)


def _box(x0, x1, y0, y1, z0, z1):
    return cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))


def _cyl(r, p0, p1):
    p0, p1 = V(*p0), V(*p1)
    d = p1 - p0
    return cq.Solid.makeCylinder(r, d.Length, p0, d.normalized())


def _comp(items):
    items = [i for i in items if i is not None]
    return cq.Compound.makeCompound(items)


def _fuse(items):
    items = [i for i in items if i is not None]
    out = items[0]
    if len(items) > 1:
        out = out.fuse(*items[1:]).clean()
    return out


def _loft(sections, ruled=False):
    wires = [cq.Wire.makePolygon([V(*p) for p in s], close=True) for s in sections]
    return cq.Solid.makeLoft(wires, ruled)


def _prism_xy(pts, z0, z1):
    w = cq.Wire.makePolygon([V(x, y, z0) for x, y in pts], close=True)
    return cq.Solid.extrudeLinear(cq.Face.makeFromWires(w), V(0, 0, z1 - z0))


def _prism_xz(pts, y0, y1):
    w = cq.Wire.makePolygon([V(x, y0, z) for x, z in pts], close=True)
    return cq.Solid.extrudeLinear(cq.Face.makeFromWires(w), V(0, y1 - y0, 0))


def bbox(shape):
    """Tight bounding box (OCC AddOptimal) as (xmin, xmax, ymin, ymax, zmin, zmax)."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    b = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape.wrapped, b, False, False)
    x0, y0, z0, x1, y1, z1 = b.Get()
    return x0, x1, y0, y1, z0, z1


def _truss(p0, p1, r_chord, width, nseg, r_lace=None, dirs_up=(0, 0, 1)):
    """Lattice beam of triangular section between p0 and p1: 3 chords + zig-zag laces (list of solids)."""
    p0, p1 = np.array(p0, float), np.array(p1, float)
    ax = (p1 - p0) / np.linalg.norm(p1 - p0)
    up = np.array(dirs_up, float)
    side = np.cross(ax, up)
    side = side / np.linalg.norm(side)
    up2 = np.cross(side, ax)
    h = width * math.sqrt(3) / 2
    offs = [side * width / 2 - up2 * h / 3, -side * width / 2 - up2 * h / 3, up2 * 2 * h / 3]
    r_lace = r_lace or r_chord * 0.5
    out = []
    for o in offs:
        out.append(_cyl(r_chord, p0 + o, p1 + o))
    L = np.linalg.norm(p1 - p0)
    for i in range(nseg):
        a = p0 + ax * L * i / nseg
        b = p0 + ax * L * (i + 1) / nseg
        k = i % 3
        out.append(_cyl(r_lace, a + offs[k], b + offs[(k + 1) % 3]))
        out.append(_cyl(r_lace, a + offs[(k + 1) % 3], b + offs[(k + 2) % 3]))
    return out


def _dim(value, src=None, assumption=False):
    d = {"value": float(value)}
    if assumption:
        d["assumption"] = True
    else:
        d["src"] = src
    return d


# ------------------------------------------------------------------------------------------------ PSV
_PSV_XF = [-0.5, -0.47, -0.42, -0.30, -0.10, 0.10, 0.22, 0.32, 0.38, 0.43, 0.47, 0.50, 0.506]
_PSV_BF = [0.90, 0.96, 1.00, 1.00, 1.00, 1.00, 0.97, 0.88, 0.74, 0.54, 0.30, 0.10, 0.05]
_PSV_Z0 = [0.30, 0.10, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.15, 0.7, 1.7, 3.2, 3.6]  # keel rise aft counter / forefoot
_PSV_FL = [0, 0, 0, 0, 0, 0, 2, 7, 13, 18, 22, 25, 25]  # deck-edge flare angle above waterline (deg)


def _psv_section(xf, L, B, D, T):
    bf = float(np.interp(xf, _PSV_XF, _PSV_BF))
    z0 = float(np.interp(xf, _PSV_XF, _PSV_Z0))
    fl = math.radians(float(np.interp(xf, _PSV_XF, _PSV_FL)))
    hb = B / 2 * bf
    rb = min(2.0, 0.7 * hb, 0.7 * (T - z0))
    cx, cz = hb - rb, z0 + rb
    hbd = min(B / 2, hb + (D - T) * math.tan(fl))
    right = [(cx, z0)]
    for th in (-60, -30):
        t = math.radians(th)
        right.append((cx + rb * math.cos(t), cz + rb * math.sin(t)))
    right += [(hb, cz), (hb, T), (hbd, D)]
    left = [(-y, z) for y, z in reversed(right)]
    return right + left, hbd


def _stem_cut(L, ztop, rake_deg):
    t = math.tan(math.radians(rake_deg))
    z0, z1 = -2.0, ztop + 3.0
    xf = lambda z: L / 2 - (ztop - z) * t
    big = L / 2 + 20
    return _prism_xz([(xf(z0), z0), (big, z0), (big, z1), (xf(z1), z1)], -30, 30)


@register("psv")
def build_psv(loa_m=85.0, beam_m=20.0, depth_m=8.0, draught_m=6.5, deck_length_frac=0.55, n_tiers=3,
              rake_deg=12.0, containers=True, seed=7):
    L, B, D, T = float(loa_m), float(beam_m), float(depth_m), float(draught_m)
    tier_h, fc_h = 2.8, 2.6
    ztop_fc = D + fc_h + 0.5
    cut = _stem_cut(L, ztop_fc, rake_deg)

    # --- hull: smooth loft through station sections (flat bottom, bilge radius, bow flare, forefoot, transom)
    xs = [f * L for f in _PSV_XF]
    secs = []
    for xf, x in zip(_PSV_XF, xs):
        pts, _ = _psv_section(xf, L, B, D, T)
        secs.append([(x, y, z) for y, z in pts])
    hull_body = _loft(secs, ruled=False).cut(cut)
    hull_body = hull_body.cut(_box(-L, L, -B, B, -5.0, 0.0)).cut(_box(-L, L, B / 2, B, -1, D + 1)).cut(_box(-L, L, -B, -B / 2, -1, D + 1)).cut(_box(-L, L, -B, B, D, D + 3.0))

    # --- forecastle with sheer: trapezoid stations lofted from xf 0.30 to bow
    fxf = [0.30, 0.36, 0.42, 0.47, 0.50, 0.506]
    fsec = []
    for xf in fxf:
        _, hbd = _psv_section(xf, L, B, D, T)
        fl = math.radians(float(np.interp(xf, _PSV_XF, _PSV_FL)) + 6)
        sh = 0.5 * max(0.0, (xf - 0.30) / 0.206) ** 2
        zt = D + fc_h + sh
        h1 = min(B / 2, hbd + fc_h * math.tan(fl))
        x = xf * L
        fsec.append([(x, -hbd, D), (x, hbd, D), (x, h1, zt), (x, -h1, zt)])
    forecastle = _loft(fsec, ruled=True).cut(cut)

    # --- bulwark on the working deck: shell between outer and inset loft, open at the stern
    bw_h = 1.4
    outer_s, inner_s = [], []
    for xf in [-0.5, -0.47, -0.42, -0.30, -0.10, 0.10, 0.22, 0.30]:
        _, hbd = _psv_section(xf, L, B, D, T)
        x = xf * L
        outer_s.append([(x, -hbd, D), (x, hbd, D), (x, hbd, D + bw_h), (x, -hbd, D + bw_h)])
        hi = hbd - 0.18
        inner_s.append([(x - (1.0 if xf == -0.5 else 0), -hi, D - 0.01), (x - (1.0 if xf == -0.5 else 0), hi, D - 0.01),
                        (x - (1.0 if xf == -0.5 else 0), hi, D + bw_h + 0.1), (x - (1.0 if xf == -0.5 else 0), -hi, D + bw_h + 0.1)])
    bulwark = _loft(outer_s, ruled=True).cut(_loft(inner_s, ruled=True))
    # stern notch for the roller (open bulwark across the transom, 5 m wide)
    bulwark = bulwark.cut(_box(-L / 2 - 0.1, -L / 2 + 0.3, -2.5, 2.5, D - 0.1, D + bw_h + 0.2))
    roller = _cyl(0.55, (-L / 2 + 0.6, -2.4, D - 0.55), (-L / 2 + 0.6, 2.4, D - 0.55))

    hull = hull_body
    hull_part = _comp([hull, roller])

    # --- deckhouse tiers
    x_cargo_end = -L / 2 + deck_length_frac * L
    x_barrier = x_cargo_end - 0.4
    xh0, xh1 = x_cargo_end + 1.6, 0.30 * L - 0.5
    ch = 1.6
    tiers, win_cuts = [], []
    w = B / 2 - 0.9
    zt0 = D
    last_xy = None
    for i in range(n_tiers):
        a, b = xh0 + 0.6 * i, xh1 - 0.8 * i
        wi = w - 0.7 * i
        plan = [(a, -wi), (b - ch, -wi), (b, -wi + ch), (b, wi - ch), (b - ch, wi), (a, wi)]
        # plan above is open on aft side: make aft face square
        plan = [(a, -wi), (b - ch, -wi), (b, -wi + ch), (b, wi - ch), (b - ch, wi), (a, wi)]
        tiers.append(_prism_xy(plan, zt0, zt0 + tier_h))
        zw0 = zt0 + 0.8
        n = int((b - a - 2 * ch) // 1.9)
        for k in range(n):
            xc = a + 1.2 + 1.9 * k
            for s in (-1, 1):
                win_cuts.append(_box(xc, xc + 1.1, (wi - 0.05) if s > 0 else (-wi - 0.3), (wi + 0.3) if s > 0 else (-wi + 0.05),
                                     zw0, zw0 + 1.1))
        # forward-facing windows (between chamfers)
        nf = int((2 * (wi - ch) - 0.8) // 1.7)
        y0 = -(nf * 1.7 - 0.6) / 2
        for k in range(nf):
            yc = y0 + 1.7 * k
            win_cuts.append(_box(b - 0.05, b + 0.3, yc, yc + 1.1, zw0, zw0 + 1.1))
        # doors on the aft face
        win_cuts.append(_box(a - 0.3, a + 0.05, -0.5 - 2.6, 0.5 - 2.6, zt0 + 0.05, zt0 + 2.0))
        win_cuts.append(_box(a - 0.3, a + 0.05, -0.5 + 2.6, 0.5 + 2.6, zt0 + 0.05, zt0 + 2.0))
        last_xy = (a, b, wi)
        zt0 += tier_h
    house = _fuse(tiers)
    house = house.cut(_comp(win_cuts))
    z_bridge = zt0

    # --- bridge: raked front, wraparound glazing band with mullions
    a1, b1, w1 = last_xy
    bw = B / 2 - 1.8
    xb0, xb1 = b1 - 5.2, b1 + 0.8
    bh = 2.6
    plan_b = [(xb0, -bw + 1.0), (xb0 + 1.0, -bw), (xb1 - 1.4, -bw), (xb1, -bw + 1.8), (xb1, bw - 1.8), (xb1 - 1.4, bw),
              (xb0 + 1.0, bw), (xb0, bw - 1.0)]
    bridge_pl = _prism_xy(plan_b, z_bridge, z_bridge + bh)
    prof = _prism_xz([(xb0 - 1, z_bridge), (xb1 + 1.5, z_bridge), (xb1 - 0.55, z_bridge + bh), (xb0 - 1, z_bridge + bh)], -30, 30)
    # rake: front leans forward (top aft of base) -> use inverse so top overhangs: window slope outward
    prof = _prism_xz([(xb0 - 1, z_bridge), (xb1 - 0.5, z_bridge), (xb1 + 0.2, z_bridge + bh), (xb0 - 1, z_bridge + bh)], -30, 30)
    bridge_body = bridge_pl.intersect(prof)
    zg0, zg1 = z_bridge + 0.75, z_bridge + bh - 0.35
    band_full = bridge_body.intersect(_box(xb0 - 2, xb1 + 3, -30, 30, zg0, zg1))
    inner_w = cq.Workplane("XY").workplane(offset=zg0 - 0.1).polyline(plan_b).close().offset2D(-0.07).extrude(zg1 - zg0 + 0.2)
    ring = band_full.cut(inner_w.val())
    mull = []
    for xm in np.arange(xb0 + 0.9, xb1, 1.5):
        mull.append(_box(xm, xm + 0.12, -30, 30, zg0 - 0.1, zg1 + 0.1))
    for ym in np.arange(-bw + 0.9, bw, 1.5):
        mull.append(_box(xb0 - 2, xb1 + 3, ym, ym + 0.12, zg0 - 0.1, zg1 + 0.1))
    ring_cut = ring.cut(_comp(mull))
    bridge_core = bridge_body.cut(ring_cut)
    # wings: floor plate + low bulwark, full width within the beam
    wing_y = B / 2 - 0.15
    wings = []
    for s in (-1, 1):
        wings.append(_box(xb0 + 1.6, xb0 + 4.2, min(s * (bw - 0.1), s * wing_y), max(s * (bw - 0.1), s * wing_y), z_bridge - 0.25, z_bridge))
        yy0, yy1 = sorted((s * bw, s * wing_y))
        wings.append(_box(xb0 + 1.6, xb0 + 4.2, s * wing_y - (0.06 if s > 0 else 0), s * wing_y + (0.0 if s > 0 else 0.06),
                          z_bridge, z_bridge + 1.1))
        wings.append(_box(xb0 + 4.14, xb0 + 4.2, yy0, yy1, z_bridge, z_bridge + 1.1))
        # support brackets
        wings.append(_box(xb0 + 2.2, xb0 + 2.4, min(s * bw, s * wing_y), max(s * bw, s * wing_y), z_bridge - 0.9, z_bridge - 0.25))
    roof = _box(xb0 + 0.3, xb1 - 0.2, -bw + 0.6, bw - 0.6, z_bridge + bh, z_bridge + bh + 0.25)
    bridge = _comp([bridge_core, roof] + wings)
    z_roof = z_bridge + bh + 0.25

    # --- mast with radar bars
    xm = xb0 + 2.4
    mast = [_cyl(0.20, (xm, 0, z_roof), (xm, 0, z_roof + 6.8)),
            _cyl(0.9, (xm, 0, z_roof + 3.0), (xm, 0, z_roof + 3.1)),
            _box(xm - 0.8, xm + 0.8, -0.05, 0.05, z_roof + 3.1, z_roof + 3.7),
            _cyl(0.15, (xm, 0.0, z_roof + 6.8), (xm, 0.0, z_roof + 7.5)),
            _box(xm - 1.8, xm + 1.8, -0.15, 0.15, z_roof + 7.5, z_roof + 7.8),   # X-band radar bar
            _cyl(0.18, (xm + 1.0, 1.4, z_roof), (xm + 1.0, 1.4, z_roof + 1.2)),
            _box(xm + 1.0 - 1.1, xm + 1.0 + 1.1, 1.4 - 0.12, 1.4 + 0.12, z_roof + 1.2, z_roof + 1.45),  # S-band bar
            _cyl(0.03, (xm - 0.6, 0.7, z_roof + 3.1), (xm - 0.6, 0.7, z_roof + 6.0)),
            _cyl(0.03, (xm + 0.6, -0.7, z_roof + 3.1), (xm + 0.6, -0.7, z_roof + 5.2)),
            _cyl(0.25, (xm - 1.6, -2.0, z_roof), (xm - 1.6, -2.0, z_roof + 0.5)),
            cq.Solid.makeSphere(0.45, V(xm - 1.6, -2.0, z_roof + 0.95)),  # satcom dome
            ]
    mast = _comp(mast)

    # --- exhaust stacks on the top tier roof, aft
    ztier_top = D + n_tiers * tier_h
    fx = a1 + 2.2
    funnels = []
    for s in (-1, 1):
        fy = s * (w1 - 1.5)
        funnels.append(_cyl(0.55, (fx, fy, ztier_top), (fx, fy, ztier_top + 3.2)))
        funnels.append(_cyl(0.65, (fx, fy, ztier_top + 3.2), (fx, fy, ztier_top + 3.35)))
        funnels.append(_box(fx - 0.8, fx + 0.8, fy - 0.8, fy + 0.8, ztier_top, ztier_top + 0.4))
    funnel = _comp(funnels)

    # --- rescue boat (rigid, loft) on a davit, starboard of the upper tier roof
    bx, by, bz = a1 + 5.5, -(w1 - 1.1), ztier_top + 0.9
    bl = 7.0
    bsec = []
    for f, wb, hb_ in [(0.0, 1.10, 0.55), (0.25, 1.20, 0.60), (0.6, 1.10, 0.62), (0.85, 0.65, 0.66), (1.0, 0.08, 0.7)]:
        x = bx - bl / 2 + f * bl
        bsec.append([(x, by - wb, bz + 0.3), (x, by + wb, bz + 0.3), (x, by + wb * 1.05, bz + 0.3 + hb_), (x, by - wb * 1.05, bz + 0.3 + hb_)])
    boat_h = _loft(bsec, ruled=True)
    cabin = _box(bx - 1.0, bx + 0.6, by - 0.6, by + 0.6, bz + 0.3 + 0.6, bz + 0.3 + 1.3)
    boat = [boat_h, cabin,
            _cyl(0.22, (bx - 0.3, by, ztier_top), (bx - 0.3, by, bz - 0.2)),
            _cyl(0.12, (bx - 0.3, by, bz - 0.2), (bx - 0.3, by + 1.9, bz + 2.3)),
            _cyl(0.04, (bx - 0.3, by + 1.9, bz + 2.3), (bx - 2.2, by, bz + 1.6)),
            _cyl(0.04, (bx - 0.3, by + 1.9, bz + 2.3), (bx + 1.6, by, bz + 1.6)),
            _box(bx - 3.9, bx + 3.9, by - 1.25, by + 1.25, ztier_top, ztier_top + 0.1)]
    boat = _comp(boat)

    # --- cargo: crash barrier + cargo rails (rail part)
    rails = []
    hw = B / 2 - 1.0
    # transverse crash barrier: posts + 3 beams, 2.8 m high, just aft of the house
    xb = x_barrier
    for yy in np.arange(-hw, hw + 0.1, 2.0):
        rails.append(_box(xb - 0.15, xb + 0.15, yy - 0.15, yy + 0.15, D, D + 2.8))
    for zz in (D + 0.6, D + 1.6, D + 2.6):
        rails.append(_box(xb - 0.12, xb + 0.12, -hw, hw, zz, zz + 0.25))
    # side cargo rails: stanchions every 3 m + 3 rods
    x_s0, x_s1 = -L / 2 + 3.0, xb
    for s in (-1, 1):
        ys = s * (hw + 0.1)
        for xx in np.arange(x_s0, x_s1, 3.0):
            rails.append(_cyl(0.07, (xx, ys, D), (xx, ys, D + 3.0)))
        for zz in (D + 1.2, D + 2.1, D + 3.0):
            rails.append(_cyl(0.045, (x_s0, ys, zz), (x_s1, ys, zz)))
    # stern: chain / rail posts
    for yy in (-hw, hw):
        rails.append(_cyl(0.07, (-L / 2 + 0.4, yy, D), (-L / 2 + 0.4, yy, D + 1.2)))
    rail = _comp(rails)

    # --- deck cargo: ISO 668 20 ft containers (deterministic pattern), pipe racks
    cl, cw, ch_ = ISO_20FT
    cargo = []
    if containers:
        rng = np.random.default_rng(seed)
        x_c0, x_c1 = -L / 2 + 3.4, xb - 0.8
        ncol = int((x_c1 - x_c0) // (cl + 0.25))
        nrow = int((2 * hw - 0.4) // (cw + 0.12))
        y_start = -(nrow * (cw + 0.12) - 0.12) / 2
        for r in range(nrow):
            for c in range(ncol):
                if r in (nrow - 1,) and c < 3:
                    continue  # leave room for the pipe stack
                hgt = int(rng.choice([0, 1, 1, 2, 2, 1]))
                if hgt == 0:
                    continue
                x0 = x_c0 + c * (cl + 0.25)
                y0 = y_start + r * (cw + 0.12)
                for k in range(hgt):
                    cargo.append(_box(x0, x0 + cl, y0, y0 + cw, D + 0.15 + k * ch_, D + 0.15 + (k + 1) * ch_))
    # pipes: pyramid stack of 12 m pipes, OD 0.5 m
    pr, plen = 0.25, 12.0
    px0 = -L / 2 + 4.0
    ybase = y_start + 0.6 if containers else -2.0
    for row, n in enumerate((4, 3, 2, 1)):
        for k in range(n):
            yy = ybase + pr + (k + 0.5 * row) * 2 * pr * 1.02 + 0.0
            cargo.append(_cyl(pr, (px0, yy + (nrow - 1) * (cw + 0.12) - 4 * 2 * pr if containers else yy, D + 0.2 + pr + row * 2 * pr * 0.88),
                              (px0 + plen, yy + (nrow - 1) * (cw + 0.12) - 4 * 2 * pr if containers else yy, D + 0.2 + pr + row * 2 * pr * 0.88)))
    n_cont = sum(1 for c in cargo if c.ShapeType() == 'Solid' and abs(c.BoundingBox().xlen - cl) < 1e-6)
    cargo = _comp(cargo)

    parts = {"hull": hull_part, "bulwark": bulwark, "forecastle": forecastle, "house": house, "bridge": bridge, "mast": mast,
             "funnel": funnel, "cargo": cargo, "rail": rail, "boat": boat}
    shape = _comp(list(parts.values()))
    src_cls = "85 m PSV class, https://shipselector.com/offers/design/towingworkboatfishing-vessel/fire-fightingsupply-vessel/20595-85-meter-platform-supply-vessel (LOA 85.5, depth 7.8, T 6.5)"
    dims = {
        "loa_m": _dim(L, src_cls) if abs(L - 85.0) < 1.0 else _dim(L, assumption=True),
        "beam_m": _dim(B, assumption=True),
        "depth_m": _dim(D, src_cls) if abs(D - 8.0) < 0.3 else _dim(D, assumption=True),
        "draught_m": _dim(T, src_cls) if abs(T - 6.5) < 0.1 else _dim(T, assumption=True),
        "container_length_m": _dim(cl, "ISO 668 20 ft container 6.058 m"),
        "container_width_m": _dim(cw, "ISO 668 20 ft container 2.438 m"),
        "container_height_m": _dim(ch_, "ISO 668 20 ft container 2.591 m (8 ft 6 in)"),
    }
    meta = {"class": "vessel", "licence": "generated (CC0)", "generator": "offsim.assets.cad.marine.psv", "lod": 3,
            "waterline_z": T, "cargo_deck_x": [-L / 2, x_cargo_end], "n_containers": n_cont,
            "bow_rake_deg": rake_deg,
            "notes": "hull lofted from 13 station sections with flat bottom, bilge radius, bow flare, forefoot rise and a raked "
                     "stem cut; sheer is carried by the forecastle top. 'hull' bbox top equals depth_m. Main-deck beam equals beam_m."}
    return AssetModel(shape=shape, parts=parts, dims=dims, meta=meta)


# --------------------------------------------------------------------------------------------- jacket
CAP437_D_S92 = 20.88


@register("platform_jacket")
def build_platform_jacket(water_depth_m=80.0, deck_elev_m=22.0, helideck_d_m=CAP437_D_S92, legs=4, bays=4,
                          top_spacing_m=26.0, batter=1 / 12, leg_od_m=1.4, deck_height_m=6.0):
    """Fixed steel jacket. Origin: z=0 on the seabed, x=y=0 at the plan centre of the legs. MSL at z=water_depth_m.
    Cellar-deck plate underside at z = water_depth_m + deck_elev_m. Helideck cantilevers off the +x (forward) edge."""
    Wd, E = float(water_depth_m), float(deck_elev_m)
    zdeck = Wd + E
    zleg_top = zdeck
    leg_r, br_r = leg_od_m / 2, leg_od_m / 2 * 0.42
    s_top = float(top_spacing_m)
    # plan: 4 legs -> 2x2 ; 8 legs -> 2 x 4 (long in x)
    if legs == 4:
        nx, ny = 2, 2
        sx_top, sy_top = s_top, s_top * 0.8
    elif legs == 8:
        nx, ny = 4, 2
        sx_top, sy_top = s_top * 1.5, s_top * 0.8
    else:
        raise ValueError("legs must be 4 or 8")

    def leg_xy(ix, iy, z):
        """Plan position of leg (ix, iy) at elevation z with batter outward going down."""
        grow = (zleg_top - z) * batter
        xs_ = (-0.5 + ix / (nx - 1)) * (sx_top + 2 * grow)
        ys_ = (-0.5 + iy / (ny - 1)) * (sy_top + 2 * grow)
        return xs_, ys_

    # bay elevations: seabed (0), bays-1 intermediate frames, top frame at zleg_top
    z_levels = [0.0] + [zleg_top * (0.14 + 0.86 * (i / bays) ** 0.9) for i in range(1, bays)] + [zleg_top]
    z_levels = sorted(set(round(z, 3) for z in z_levels))
    members_leg, members_br, members_hz = [], [], []
    # legs (continuous tubes between frame levels, so node lengths are bounded)
    for ix in range(nx):
        for iy in range(ny):
            for a, b in zip(z_levels[:-1], z_levels[1:]):
                a = max(a, 0.5)  # leg tube starts inside the 1 m foot so no tilted end cap dips below the seabed
                xa, ya = leg_xy(ix, iy, a)
                xb_, yb = leg_xy(ix, iy, b)
                members_leg.append(_cyl(leg_r, (xa, ya, a), (xb_, yb, b)))
            xa, ya = leg_xy(ix, iy, 0)
            members_leg.append(_cyl(leg_r * 1.25, (xa, ya, 0), (xa, ya, 1.0)))
    # vertical X-bracing on the four faces, per bay; plus horizontal frame members at every level
    nodes = lambda ix, iy, z: (*leg_xy(ix, iy, z), z)
    faces = []
    for iy in (0, ny - 1):
        for ix in range(nx - 1):
            faces.append(((ix, iy), (ix + 1, iy)))
    for ix in (0, nx - 1):
        for iy in range(ny - 1):
            faces.append(((ix, iy), (ix, iy + 1)))
    for (i0, j0), (i1, j1) in faces:
        for a, b in zip(z_levels[:-1], z_levels[1:]):
            a = max(a, 0.9)  # lowest brace nodes sit just above the mudline
            p00, p10 = nodes(i0, j0, a), nodes(i1, j1, a)
            p01, p11 = nodes(i0, j0, b), nodes(i1, j1, b)
            members_br.append(_cyl(br_r, p00, p11))
            members_br.append(_cyl(br_r, p10, p01))
    for z in z_levels[1:]:
        z = max(z, 0.9)
        corners = [nodes(i, j, z) for (i, j) in [(0, 0), (nx - 1, 0), (nx - 1, ny - 1), (0, ny - 1)]]
        for k in range(4):
            members_hz.append(_cyl(br_r, corners[k], corners[(k + 1) % 4]))
        if nx == 4:
            for i in (1, 2):
                members_hz.append(_cyl(br_r, nodes(i, 0, z), nodes(i, ny - 1, z)))
        # horizontal diagonals at the lowest and top frame levels (plan bracing)
        if z in (z_levels[1], z_levels[-1]):
            members_hz.append(_cyl(br_r * 0.8, corners[0], corners[2]))
            members_hz.append(_cyl(br_r * 0.8, corners[1], corners[3]))
    # boat landing + riser guard on the -x face, conductor guide frame
    xl, yl = leg_xy(0, 0, Wd)
    landing = [_box(xl - 3.0, xl - 0.9, -4.0, 4.0, Wd - 2.0, Wd - 1.8),
               _cyl(0.2, (xl - 3.0, -4.0, Wd - 2.0), (xl - 0.9, -4.0, Wd + 4.0)),
               _cyl(0.2, (xl - 3.0, 4.0, Wd - 2.0), (xl - 0.9, 4.0, Wd + 4.0)),
               _cyl(0.15, (xl - 3.0, -4.0, Wd + 2.0), (xl - 3.0, 4.0, Wd + 2.0)),
               _cyl(0.2, (xl - 3.0, -4.0, Wd - 2.0), (xl - 3.0, 4.0, Wd - 2.0))]
    jacket_parts = _comp(members_leg + members_br + members_hz + landing)

    # --- topsides: deck legs, three deck levels, modules
    xt, yt = sx_top / 2 + 3.0, sy_top / 2 + 3.0  # deck plan half sizes (overhang 3 m)
    dh = float(deck_height_m)
    z_c, z_m, z_w = zdeck, zdeck + dh, zdeck + 2 * dh
    t = 0.45
    decks = [_box(-xt, xt, -yt, yt, z_c, z_c + t), _box(-xt, xt, -yt, yt, z_m, z_m + t),
             _box(-xt + 4, xt - 4, -yt + 2, yt - 2, z_w, z_w + t)]
    dleg = []
    for ix in range(nx):
        for iy in range(ny):
            x, y = leg_xy(ix, iy, zleg_top)
            dleg.append(_cyl(leg_r * 1.05, (x, y, z_c), (x, y, z_w)))
    # deck girders (bottom of each deck)
    for z in (z_c, z_m):
        for yy in np.linspace(-yt + 1, yt - 1, 5):
            dleg.append(_box(-xt, xt, yy - 0.2, yy + 0.2, z - 1.0, z))
    # modules: living quarters (3 tiers, windows), process, utility, switchgear, derrick-free
    mods = []
    lq_x0, lq_x1 = -xt + 1.0, -xt + 14.0
    lq = _box(lq_x0, lq_x1, -yt + 1.5, -yt + 14.0, z_m + t, z_m + t + 3.0 * 3)
    lq_win = []
    for tier in range(3):
        for k in range(5):
            x0 = lq_x0 + 1.2 + k * 2.4
            lq_win.append(_box(x0, x0 + 1.2, -yt + 1.5 - 0.3, -yt + 1.5 + 0.05, z_m + t + tier * 3.0 + 1.0, z_m + t + tier * 3.0 + 2.0))
            lq_win.append(_box(x0, x0 + 1.2, -yt + 14.0 - 0.05, -yt + 14.0 + 0.3, z_m + t + tier * 3.0 + 1.0, z_m + t + tier * 3.0 + 2.0))
    lq = lq.cut(_comp(lq_win))
    mods.append(lq)
    mods.append(_box(lq_x1 + 1.5, lq_x1 + 15, -yt + 2, yt - 2, z_m + t, z_m + t + 6.0))  # process module
    mods.append(_box(xt - 12, xt - 2, -yt + 2, 0, z_m + t, z_m + t + 4.5))  # utilities
    mods.append(_box(-xt + 2, -xt + 12, yt - 9, yt - 2, z_c + t, z_c + t + 4.0))  # switchgear / cellar-deck pad
    # pipes/vessels on the weather deck, vent stack
    mods.append(_cyl(1.6, (xt - 8, yt - 5, z_m + t), (xt - 8, yt - 5, z_m + t + 7.0)))
    mods.append(_cyl(0.5, (-xt + 18, yt - 4, z_w + t), (-xt + 18, yt - 4, z_w + t + 9.0)))
    modules = _comp(mods)
    # handrails around the weather deck
    hr = []
    xw0, xw1, yw0, yw1 = -xt + 4, xt - 4, -yt + 2, yt - 2
    for (ax, ay), (bx, by) in [((xw0, yw0), (xw1, yw0)), ((xw1, yw0), (xw1, yw1)), ((xw1, yw1), (xw0, yw1)), ((xw0, yw1), (xw0, yw0))]:
        hr.append(_cyl(0.04, (ax, ay, z_w + t + 1.1), (bx, by, z_w + t + 1.1)))
        hr.append(_cyl(0.04, (ax, ay, z_w + t + 0.55), (bx, by, z_w + t + 0.55)))
        n = int(max(abs(bx - ax), abs(by - ay)) // 2.0)
        for k in range(n + 1):
            f = k / max(n, 1)
            hr.append(_cyl(0.04, (ax + (bx - ax) * f, ay + (by - ay) * f, z_w + t), (ax + (bx - ax) * f, ay + (by - ay) * f, z_w + t + 1.1)))
    handrails = _comp(hr)

    # --- stairs between deck levels (stringer + treads), on the +y side
    stairs = []
    for z0, z1 in ((z_c + t, z_m), (z_m + t, z_w)):
        xs0 = xt - 14.0
        ys = yt - 1.0
        run = 6.6
        n = 16
        for k in range(n):
            stairs.append(_box(xs0 + run * k / n, xs0 + run * (k + 1) / n, ys - 1.0, ys, z0 + (z1 - z0) * k / n, z0 + (z1 - z0) * k / n + 0.05))
        for yy in (ys - 1.0, ys):
            stairs.append(_cyl(0.06, (xs0, yy, z0), (xs0 + run, yy, z1)))
    stairs = _comp(stairs)

    # --- crane: pedestal + lattice boom + cab, on a corner of the main deck
    cx, cy, cz = -xt + 3.0, yt - 3.0, z_m + t
    crane = [_cyl(1.1, (cx, cy, cz), (cx, cy, cz + 4.5)), _box(cx - 1.6, cx + 1.6, cy - 1.3, cy + 1.3, cz + 4.5, cz + 6.3)]
    boom_len, elev = 34.0, math.radians(50)
    bx0, bz0 = cx + 1.0, cz + 6.3
    tip = (bx0 + boom_len * math.cos(elev) * -1.0, cy, bz0 + boom_len * math.sin(elev))
    # boom points back over the deck edge (-x direction), heel pin at cab
    crane += _truss((bx0, cy, bz0), tip, 0.12, 1.4, 12, dirs_up=(0, 1, 0))
    crane.append(_cyl(0.05, tip, (tip[0] + 2.0 * math.cos(elev) * 1.0, tip[1], tip[2] - 6.0)))
    crane.append(_box(cx - 2.2, cx - 0.6, cy - 1.0, cy + 1.0, cz + 6.3, cz + 8.0))  # operator cab
    crane = _comp(crane)

    # --- flare boom: lattice cantilever off the -x weather-deck edge, inclined 25 deg
    fa = math.radians(25)
    f0 = (-xt + 4, -yt + 6.0, z_w + t)
    f1 = (f0[0] - 32 * math.cos(fa), f0[1], f0[2] + 32 * math.sin(fa))
    flare = _truss(f0, f1, 0.15, 2.0, 16, dirs_up=(0, 1, 0))
    flare.append(_cyl(0.35, f1, (f1[0] - 1.5 * math.cos(fa), f1[1], f1[2] + 1.5 * math.sin(fa))))
    flare = _comp(flare)

    # --- lifeboat stations: two enclosed lifeboats on davits at the main-deck edge
    lifeboats = []
    for yy in (-yt + 4.0, -yt + 12.0):
        xx = -xt + 0.6
        body = cq.Workplane("XY").box(7.2, 2.6, 2.6).edges().fillet(0.9).val().translate(V(xx - 1.5, yy, z_m + t + 3.3))
        lifeboats.append(body)
        lifeboats.append(_cyl(0.25, (xx - 0.5, yy - 1.8, z_m + t), (xx - 0.5, yy - 1.8, z_m + t + 6.2)))
        lifeboats.append(_cyl(0.25, (xx - 0.5, yy + 1.8, z_m + t), (xx - 0.5, yy + 1.8, z_m + t + 6.2)))
        lifeboats.append(_cyl(0.2, (xx - 0.5, yy - 1.8, z_m + t + 6.2), (xx - 3.0, yy - 1.8, z_m + t + 5.4)))
        lifeboats.append(_cyl(0.2, (xx - 0.5, yy + 1.8, z_m + t + 6.2), (xx - 3.0, yy + 1.8, z_m + t + 5.4)))
    lifeboats = _comp(lifeboats)

    # --- helideck, cantilevered off the +x edge of the weather deck on a truss, with perimeter safety net
    Dh = float(helideck_d_m)
    rh = Dh / 2
    z_h = z_w + t + 2.0  # helideck surface above the weather deck (clear of the vent stack)
    hx = xw1 + rh - 3.0  # centre: cantilevered so that ~3 m of the disc overlaps the deck edge
    hy = 0.0
    th = 0.35
    plate = cq.Solid.makeCylinder(rh, th, V(hx, hy, z_h - th), V(0, 0, 1))
    net_w = 1.5
    net = cq.Workplane("XY").workplane(offset=z_h - 0.55).center(hx, hy).circle(rh + net_w).circle(rh - 0.01).extrude(0.05).val()
    net_rods = []
    for k in range(48):  # radial net rods (as drawn in plan)
        a = 2 * math.pi * k / 48
        net_rods.append(_cyl(0.015, (hx + (rh) * math.cos(a), hy + rh * math.sin(a), z_h - 0.52),
                             (hx + (rh + net_w) * math.cos(a), hy + (rh + net_w) * math.sin(a), z_h - 0.52)))
    ring = cq.Workplane("XY").workplane(offset=z_h - 0.55).center(hx, hy).circle(rh + net_w).circle(rh + net_w - 0.06).extrude(0.06).val()
    # support: ring beam + radial beams + two inclined trusses back to the platform + diagonal struts to the legs
    sup = []
    for k in range(8):
        a = 2 * math.pi * k / 8
        sup.append(_cyl(0.18, (hx, hy, z_h - th - 0.2), (hx + (rh - 0.3) * math.cos(a), hy + (rh - 0.3) * math.sin(a), z_h - th - 0.2)))
    sup.append(cq.Workplane("XY").workplane(offset=z_h - th - 0.45).center(hx, hy).circle(rh - 0.3).circle(rh - 0.5).extrude(0.25).val())
    for ysd in (-rh * 0.45, rh * 0.45):
        # truss: horizontal cantilever girder from deck edge to far rim, plus lower inclined chord back to the module deck
        p_top0 = (xw1 - 1.0, ysd, z_h - th - 0.2)
        p_top1 = (hx + rh * 0.8, ysd, z_h - th - 0.2)
        sup += _truss(p_top0, p_top1, 0.18, 1.2, 10, dirs_up=(0, 1, 0))
        sup.append(_cyl(0.2, (hx + rh * 0.8, ysd, z_h - th - 0.2), (xw1 - 1.0, ysd * 0.9, z_w + t)))
        sup.append(_cyl(0.2, (hx + rh * 0.4, ysd, z_h - th - 0.2), (xw1 - 1.0, ysd * 0.9, z_w + t)))
    # columns up from the weather deck to the helideck spans
    for ysd in (-rh * 0.45, rh * 0.45):
        sup.append(_cyl(0.3, (xw1 - 1.0, ysd, z_w + t), (xw1 - 1.0, ysd, z_h - th - 0.2)))
    # markings: perimeter line (annulus) + H, thin raised, and floodlight posts
    mark = [cq.Workplane("XY").workplane(offset=z_h).center(hx, hy).circle(rh - 0.4).circle(rh - 0.7).extrude(0.01).val()]
    hh = 0.12 * Dh
    # H marking (two verticals + crossbar), with the crossbar along y
    mark += [_box(hx - 0.8 * hh - 0.18, hx - 0.8 * hh + 0.18, hy - 0.5 * hh, hy + 0.5 * hh, z_h, z_h + 0.01),
             _box(hx + 0.8 * hh - 0.18, hx + 0.8 * hh + 0.18, hy - 0.5 * hh, hy + 0.5 * hh, z_h, z_h + 0.01),
             _box(hx - 0.8 * hh, hx + 0.8 * hh, hy - 0.18, hy + 0.18, z_h, z_h + 0.01)]
    posts = []
    for k in range(8):
        a = 2 * math.pi * (k + 0.5) / 8
        posts.append(_cyl(0.05, (hx + (rh + 0.4) * math.cos(a), hy + (rh + 0.4) * math.sin(a), z_h - 0.5),
                          (hx + (rh + 0.4) * math.cos(a), hy + (rh + 0.4) * math.sin(a), z_h + 0.25)))
    # access stair/hangar-free: helideck fire monitor posts + windsock mast
    posts.append(_cyl(0.06, (hx - rh - 1.0, hy - rh * 0.5, z_h - 0.5), (hx - rh - 1.0, hy - rh * 0.5, z_h + 4.0)))
    helideck = _comp([plate, net, ring] + net_rods + sup + mark + posts)
    helideck_plate = plate

    parts = {"jacket": jacket_parts, "topsides_legs": _comp(dleg), "decks": _comp(decks), "modules": modules,
             "handrails": handrails, "stairs": stairs, "crane": crane, "flare": flare, "lifeboats": lifeboats,
             "helideck": helideck, "helideck_plate": helideck_plate}
    shape = _comp([p for k, p in parts.items() if k != "helideck_plate"])
    src_d = ("CAP 437 (UK CAA) D-value of the Sikorsky S-92 = 20.88 m, quoted at "
             "https://www.pprune.org/rotorheads/395350-s-92-landing-specification.html; helideck diameter >= 1.0 D")
    dims = {
        "water_depth_m": _dim(Wd, assumption=True),
        "deck_elev_m": _dim(E, assumption=True),
        "helideck_d_m": _dim(Dh, src_d) if abs(Dh - CAP437_D_S92) < 1e-6 else _dim(Dh, assumption=True),
        "leg_od_m": _dim(leg_od_m, assumption=True),
        "leg_batter": _dim(batter, assumption=True),
        "top_spacing_m": _dim(top_spacing_m, assumption=True),
    }
    meta = {"class": "structure", "licence": "generated (CC0)", "generator": "offsim.assets.cad.marine.platform_jacket", "lod": 3,
            "msl_z": Wd, "cellar_deck_z": zdeck, "helideck_z": z_h, "helideck_centre": (hx, hy), "legs": legs, "bays": bays,
            "pivots": {"crane": (cx, cy, cz + 6.3)},
            "notes": "z=0 is the seabed; 'decks' bottom equals water_depth_m + deck_elev_m (cellar deck underside). "
                     "'helideck_plate' is the landing disc of diameter helideck_d_m (not included in `shape` twice)."}
    return AssetModel(shape=shape, parts=parts, dims=dims, meta=meta)
