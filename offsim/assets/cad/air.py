"""Aircraft CAD assets: Sikorsky S-92A (`s92`) and Leonardo AW189 (`aw189`), the two offshore helicopters of the studies.

Exact solids at real scale (metres; x forward, y to port, z up). Origin: x = main-rotor axis, y = centreline,
z = ground under the wheels. The fuselage is lofted from superellipse cross-sections (nose, cockpit, cabin, tail cone);
rotors are separate parts (`rotor`, `tail_rotor`) with their pivots/axes in `meta["pivots"]`.
Parameter `rotor_azimuth_deg` rotates the main rotor about its axis (blade 0 points forward at 0 deg).

Dimension sources
S-92A
  main rotor diameter 17.17 m, tail rotor 3.35 m, fuselage length 17.10 m, hull (sponson) width 3.89 m, height 4.32 m
    (to the top of the rotor head): EASA TCDS R.011 S-92A, section III (https://easa.europa.eu/cs/downloads/7957/en)
  overall length rotors turning 20.88 m (68 ft 6 in) and overall height 5.47 m (17 ft 11 in, tail rotor tip):
    https://www.flugzeuginfo.net/acdata_php/acdata_s92_en.php and https://aerocorner.com/aircraft/sikorsky-s-92/
  CAP 437 D-value 20.88 m: https://www.pprune.org/rotorheads/395350-s-92-landing-specification.html
  cabin interior width 2.00 m: https://aerocorner.com/aircraft/sikorsky-s-92/ (exterior fuselage width of 3.04 m is
    taken from the hull width less the sponsons: assumption)
AW189
  main rotor diameter 14.60 m, overall length 17.57 m, overall height 5.07 m (rotors turning), cabin width 2.40 m, 5-blade
  main rotor, 4-blade tail rotor: Leonardo https://www.leonardo.com/en/-/aw189-1 and
  https://www.fairlifts.com/helicopters/specifications/leonardo-aw189-helicopter-specifications/
  (current Leonardo AW189 Energy brochure, 2025: overall length 17.57 m, overall height 5.07 m, rotor diameter 14.60 m).
  Rotor-head height 4.04 m, tail-rotor diameter 2.90 m, mast-to-tail-rotor 8.855 m, wheelbase 4.79 m: EASA OEB draft
  report 14/01/2014 §3.1/§3.2 dimensioned drawing
  (https://www.easa.europa.eu/sites/default/files/dfu/certification-experts-docs-oeb-reports-agusta-AW189-Draft-OEB-Report-10-01-14.pdf;
  the §3.1 table's "fuselage length 17.605 m" is the overall length, not the airframe — the drawing gives no airframe length).
  Fuselage length, sponson width: assumptions (no public figure found; the drawing's front view gives 2.55 / 2.80 / 3.02 m
  widths — fuselage / sponsons / max — against the model's 3.00 m fuselage+sponsons).
"""
from __future__ import annotations

import math

import numpy as np
import cadquery as cq
from cadquery import Vector as V

from .base import AssetModel, register


# --------------------------------------------------------------------------------------------- helpers
def _box(x0, x1, y0, y1, z0, z1):
    return cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))


def _cyl(r, p0, p1):
    p0, p1 = V(*p0), V(*p1)
    d = p1 - p0
    return cq.Solid.makeCylinder(r, d.Length, p0, d.normalized())


def _comp(items):
    return cq.Compound.makeCompound([i for i in items if i is not None])


def _loft(sections, ruled=False):
    wires = [cq.Wire.makePolygon([V(*p) for p in s], close=True) for s in sections]
    return cq.Solid.makeLoft(wires, ruled)


def _prism_xz(pts, y0, y1):
    w = cq.Wire.makePolygon([V(x, y0, z) for x, z in pts], close=True)
    return cq.Solid.extrudeLinear(cq.Face.makeFromWires(w), V(0, y1 - y0, 0))


def bbox(shape):
    """Tight bounding box (OCC AddOptimal): (xmin, xmax, ymin, ymax, zmin, zmax)."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    b = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape.wrapped, b, False, False)
    x0, y0, z0, x1, y1, z1 = b.Get()
    return x0, x1, y0, y1, z0, z1


def _dim(value, src=None, assumption=False):
    d = {"value": float(value)}
    if assumption:
        d["assumption"] = True
    else:
        d["src"] = src
    return d


def _superellipse(x, hw, zb, zt, ex, n=24):
    zc, hh = (zb + zt) / 2, (zt - zb) / 2
    pts = []
    for k in range(n):
        th = 2 * math.pi * k / n
        c, s = math.cos(th), math.sin(th)
        pts.append((x, hw * math.copysign(abs(c) ** (2 / ex), c), zc + hh * math.copysign(abs(s) ** (2 / ex), s)))
    return pts


def _blade(r0, R, c0, c1, t0, t1, z_c, droop=0.0):
    """One rotor blade along +x (leading edge +y, thickness z), root radius r0, tip radius R exactly."""
    secs = []
    for f in (0.0, 0.25, 0.6, 1.0):
        r = r0 + (R - r0) * f
        c = c0 + (c1 - c0) * f if f < 0.9 else c1
        t = t0 + (t1 - t0) * f
        zc = z_c - droop * f ** 2
        p = [(0.5 * c, 0.0), (0.3 * c, 0.5 * t), (-0.1 * c, 0.5 * t), (-0.5 * c, 0.06 * t), (-0.5 * c, -0.06 * t),
             (-0.1 * c, -0.5 * t), (0.3 * c, -0.5 * t)]
        secs.append([(r, y, zc + z) for y, z in p])
    return _loft(secs, ruled=True)


def _rotor(n, R, r0, c0, c1, t0, t1, z_c, az_deg, hub_r, hub_z0, hub_z1):
    """Main rotor: hub + n blades about the z axis through the origin; blade 0 at azimuth az_deg (0 = forward)."""
    items = [cq.Solid.makeCylinder(hub_r, hub_z1 - hub_z0, V(0, 0, hub_z0), V(0, 0, 1))]
    b0 = _blade(r0, R, c0, c1, t0, t1, z_c, droop=0.12)
    for k in range(n):
        a = az_deg + 360.0 * k / n
        items.append(b0.rotate(V(0, 0, 0), V(0, 0, 1), a))
        # root cuff / pitch horn
        items.append(_cyl(0.07, (0.6 * math.cos(math.radians(a)), 0.6 * math.sin(math.radians(a)), z_c),
                          (hub_r * math.cos(math.radians(a)), hub_r * math.sin(math.radians(a)), z_c)))
    return _comp(items)


def _tail_rotor(n, R, centre, y_off):
    """Tail rotor (axis y) at `centre` (x, z); blade 0 along +x. Hub + n blades."""
    cx, cz = centre
    b0 = _blade(0.15, R, 0.26, 0.20, 0.045, 0.03, 0.0).rotate(V(0, 0, 0), V(1, 0, 0), 90)
    items = [cq.Solid.makeCylinder(0.13, 0.22, V(0, -0.11, 0), V(0, 1, 0))]
    for k in range(n):
        items.append(b0.rotate(V(0, 0, 0), V(0, 1, 0), 360.0 * k / n))
    items.append(_cyl(0.05, (0, -0.2, 0), (0, 0.0, 0)))
    return _comp(items).translate(V(cx, y_off, cz))


# --------------------------------------------------------------------------------------- builder
def _heli(name, spec, rotor_azimuth_deg, tail_azimuth_deg):
    S = spec
    xn, Lf = S["x_nose"], S["fus_len"]
    stn = S["stations"]
    split = S["split"]

    def at(frac):
        return xn - frac * Lf

    def secs(sel):
        return [_superellipse(at(f), hw, zb, zt, ex) for f, hw, zb, zt, ex in sel]

    def seg(lo, hi):
        return [s for s in stn if lo - 1e-9 <= s[0] <= hi + 1e-9]

    # segments are lofted (and cut) separately: boolean cuts on one long B-spline loft are 10x slower
    c0, c1 = S["cabin_frac"]
    cockpit_f = S["cockpit_frac"]
    nose_seg = _loft(secs(seg(0.0, c0)))
    cabin_seg = _loft(secs(seg(c0, c1)))
    aft_seg = _loft(secs(seg(c1, split)))
    tailboom = _loft(secs(seg(split, 1.0)))

    # --- cabin windows (shallow recesses)
    cab = seg(c0, c1)
    hw_c, zb_c, zt_c, ex_c = cab[1][1], cab[1][2], cab[1][3], cab[1][4]
    zc, hh = (zb_c + zt_c) / 2, (zt_c - zb_c) / 2
    cuts = []
    zw0, zw1 = S["win_z"]
    f_w0, f_w1 = S["win_frac"]
    n_w = S["n_win"]
    pitch = (f_w1 - f_w0) * Lf / n_w
    zmid = (zw0 + zw1) / 2
    y_loc = hw_c * (1 - abs((zmid - zc) / hh) ** ex_c) ** (1 / ex_c)
    for k in range(n_w):
        xa = at(f_w0) - k * pitch
        for sgn in (1, -1):
            ya, yb = (y_loc - 0.05, y_loc + 0.6) if sgn > 0 else (-y_loc - 0.6, -y_loc + 0.05)
            cuts.append(_box(xa - pitch * 0.7, xa, ya, yb, zw0, zw1))
    cabin_seg = cabin_seg.cut(_comp(cuts))
    # cockpit side windows (pilot + co-pilot)
    cx0, cx1 = at(cockpit_f[0]), at(cockpit_f[1])
    f_mid = (cockpit_f[0] + cockpit_f[1]) / 2
    sec_mid = min(stn, key=lambda s: abs(s[0] - f_mid))
    ccuts = []
    for sgn in (1, -1):
        yl = sec_mid[1] * 0.93
        ya, yb = (yl - 0.06, yl + 0.6) if sgn > 0 else (-yl - 0.6, -yl + 0.06)
        ccuts.append(_box(cx1, cx0, ya, yb, S["cockpit_z"][0], S["cockpit_z"][1]))
    nose_seg = nose_seg.cut(_comp(ccuts))
    fuselage = _comp([nose_seg, cabin_seg, aft_seg])

    # --- windscreen panes (thin glazing proud of the nose roof)
    gl = []
    top_a = [s for s in stn if 0.02 <= s[0] <= 0.16]
    xa_, xb_ = at(0.03), at(0.15)
    za_, zb2 = np.interp([0.03, 0.15], [s[0] for s in stn], [s[3] for s in stn])
    ang = math.degrees(math.atan2(zb2 - za_, xa_ - xb_))
    L_ = math.hypot(xa_ - xb_, zb2 - za_)
    for yc in (-0.42, 0.42):
        pane = cq.Solid.makeBox(L_ * 0.85, 0.7, 0.04, V(-L_ * 0.425, -0.35, -0.02))
        pane = pane.rotate(V(0, 0, 0), V(0, 1, 0), -ang)
        pane = pane.translate(V((xa_ + xb_) / 2, yc, (za_ + zb2) / 2 + 0.02))
        gl.append(pane)
    glazing = _comp(gl)

    # --- sponsons + landing gear
    sx0, sx1 = sorted(S["sponson_x"])
    sw_out, sw_in = S["width_m"] / 2, hw_c * 0.78
    szb, szt = S["sponson_z"]
    spons = []
    for sgn in (1, -1):
        sp = cq.Workplane("XY").box(sx1 - sx0, sw_out - sw_in, szt - szb).edges().fillet(min(0.22, 0.4 * (sw_out - sw_in))).val()
        spons.append(sp.translate(V((sx0 + sx1) / 2, sgn * (sw_out + sw_in) / 2, (szb + szt) / 2)))
    sponsons = _comp(spons)
    wr, ww = S["wheel_r"], S["wheel_w"]
    gear = []
    gx = S["main_gear_x"]
    for sgn in (1, -1):
        gy = sgn * (sw_out - 0.25)
        gear.append(cq.Solid.makeCylinder(wr, ww, V(gx, gy - ww / 2, wr), V(0, 1, 0)))
        gear.append(_cyl(0.07, (gx, gy, szb), (gx, gy, wr)))
        gear.append(_cyl(0.04, (gx + 0.5, gy, szb), (gx, gy, wr + 0.1)))
    nx_ = S["nose_gear_x"]
    nose_zb = float(np.interp((xn - nx_) / Lf, [s[0] for s in stn], [s[2] for s in stn]))
    gear.append(cq.Solid.makeCylinder(wr * 0.75, ww * 0.8, V(nx_, -0.38, wr * 0.75), V(0, 1, 0)))
    gear.append(cq.Solid.makeCylinder(wr * 0.75, ww * 0.8, V(nx_, 0.0, wr * 0.75), V(0, 1, 0)))
    gear.append(_cyl(0.06, (nx_, 0, nose_zb + 0.1), (nx_, 0, wr * 0.75)))
    # tail bumper
    gear.append(_cyl(0.04, (at(0.93), 0, float(np.interp(0.93, [s[0] for s in stn], [s[2] for s in stn]))),
                     (at(0.93) - 0.3, 0, float(np.interp(0.93, [s[0] for s in stn], [s[2] for s in stn])) - 0.25)))
    gear = _comp(gear)

    # --- engines / main gearbox on the roof
    roof = max(s[3] for s in stn)
    hub_top = S["hub_top"]
    eng = []
    for sgn in (1, -1):
        ey = sgn * S["engine_y"]
        ez = roof + S["engine_r"] * 0.55
        e0, e1 = S["engine_x"]
        eng.append(_cyl(S["engine_r"], (e0, ey, ez), (e1, ey, ez)))
        eng.append(_cyl(S["engine_r"] * 1.08, (e0 + 0.1, ey, ez), (e0 - 0.25, ey, ez)))  # intake lip
        eng.append(_cyl(S["engine_r"] * 0.7, (e1, ey, ez), (e1 - 0.5, ey, ez - 0.25)))  # exhaust nozzle
    eng.append(_box(e1, e0, -S["engine_y"], S["engine_y"], roof, roof + 0.3))  # deck between nacelles
    eng.append(cq.Solid.makeCylinder(0.95, 0.75, V(0, 0, roof), V(0, 0, 1)))  # main gearbox fairing
    nacelles = _comp(eng)
    mast = _comp([_cyl(0.24, (0, 0, roof + 0.7), (0, 0, hub_top - 0.32)),
                  cq.Solid.makeCylinder(0.36, 0.12, V(0, 0, roof + 0.7), V(0, 0, 1)),
                  _cyl(0.3, (0, 0, hub_top - 0.62), (0, 0, hub_top - 0.32))])

    # --- fin, tail rotor pylon, stabiliser
    Rt = S["tail_R"]
    x_tr = xn - S["length_m"] + Rt
    z_tr = S["height_m"] - Rt
    fin_pts = [(p[0] if not isinstance(p[0], str) else 0, p[1]) for p in S["fin_pts"]]
    fin = _prism_xz(fin_pts, -0.14, 0.14)
    sx = S["stab"]
    stab = _prism_xz([(sx[0], sx[2]), (sx[0] - sx[3], sx[2] + 0.02), (sx[0] - sx[3] * 1.0, sx[2] - 0.05), (sx[0] + 0.1, sx[2] - 0.12)], 0.1, 0.1 + sx[1])
    tr_gb = _cyl(0.17, (x_tr, 0.0, z_tr), (x_tr, S["tr_y"] - 0.1, z_tr))
    tail_rotor = _tail_rotor(S["n_tail"], Rt, (x_tr, z_tr), S["tr_y"]).rotate(V(x_tr, S["tr_y"], z_tr), V(x_tr, S["tr_y"] + 1, z_tr), tail_azimuth_deg)
    tailfin = _comp([fin, stab, tr_gb])

    # --- main rotor
    R = S["rotor_d"] / 2
    rotor = _rotor(S["n_main"], R, 0.55, S["chord"], S["chord"] * 0.85, 0.075, 0.05, hub_top - 0.15, rotor_azimuth_deg,
                   0.5, hub_top - 0.32, hub_top).translate(V(0, 0, 0))

    parts = {"fuselage": fuselage, "tailboom": tailboom, "glazing": glazing, "sponsons": sponsons, "gear": gear,
             "nacelles": nacelles, "mast": mast, "tailfin": tailfin, "rotor": rotor, "tail_rotor": tail_rotor}
    shape = _comp(list(parts.values()))
    dims = S["dims"](spec)
    meta = {"class": "aircraft", "licence": "generated (CC0)", "generator": f"offsim.assets.cad.air.{name}", "lod": 3,
            "pivots": {"rotor": {"point": (0.0, 0.0, hub_top - 0.15), "axis": (0, 0, 1), "radius_m": R, "blades": S["n_main"],
                                 "azimuth_deg": rotor_azimuth_deg},
                       "tail_rotor": {"point": (x_tr, S["tr_y"], z_tr), "axis": (0, 1, 0), "radius_m": Rt, "blades": S["n_tail"]}},
            "main_rotor_hub_z": hub_top, "notes": S["notes"], "d_value_m": S.get("d_value")}
    return AssetModel(shape=shape, parts=parts, dims=dims, meta=meta)


# --------------------------------------------------------------------------------------------- S-92
_S92 = {
    "x_nose": 8.65, "fus_len": 17.10, "split": 0.72, "length_m": 20.88, "height_m": 5.47, "rotor_d": 17.17, "tail_R": 3.35 / 2,
    "n_main": 4, "n_tail": 4, "chord": 0.46, "hub_top": 4.32, "width_m": 3.89, "tr_y": 0.42,
    "stations": [
        (0.000, 0.06, 1.50, 1.75, 2.2), (0.020, 0.45, 1.25, 2.35, 2.2), (0.060, 0.85, 1.05, 2.85, 2.4),
        (0.120, 1.20, 0.95, 3.15, 2.8), (0.200, 1.45, 0.90, 3.30, 3.5), (0.300, 1.52, 0.85, 3.32, 4.0),
        (0.480, 1.52, 0.85, 3.32, 4.0), (0.620, 1.45, 0.90, 3.25, 3.8), (0.720, 1.05, 1.20, 3.10, 3.0),
        (0.800, 0.62, 1.55, 2.95, 2.6), (0.900, 0.32, 1.90, 2.80, 2.4), (1.000, 0.16, 2.15, 2.70, 2.2)],
    "cabin_frac": (0.20, 0.62), "win_frac": (0.27, 0.62), "n_win": 6, "win_z": (2.30, 2.95), "cockpit_frac": (0.10, 0.20), "cockpit_z": (2.05, 2.85),
    "sponson_x": (3.4, -3.0), "sponson_z": (0.80, 2.00), "wheel_r": 0.35, "wheel_w": 0.26, "main_gear_x": -1.2,
    "nose_gear_x": 5.6, "engine_y": 0.66, "engine_r": 0.48, "engine_x": (0.9, -2.9),
    "fin_pts": [(-5.0, 2.75), (-9.65, 3.95), (-11.0, 3.85), (-9.1, 2.45), (-5.4, 2.40)],
    "stab": (-6.9, 1.7, 2.45, 0.9),
    "d_value": 20.88,
    "notes": "S-92A. Overall length 20.88 m and height 5.47 m are rotors-turning / tail-rotor-tip figures; nose-to-tail-rotor "
             "bbox reproduces both. Station table, fin planform, sponson and gear layout approximate (no public drawings).",
}


def _dims_s92(S):
    t = "EASA TCDS R.011 Sikorsky S-92A sect. III, https://easa.europa.eu/cs/downloads/7957/en"
    f = "https://www.flugzeuginfo.net/acdata_php/acdata_s92_en.php; https://aerocorner.com/aircraft/sikorsky-s-92/"
    return {
        "rotor_diameter_m": _dim(S["rotor_d"], t + " (17.17 m)"),
        "tail_rotor_diameter_m": _dim(2 * S["tail_R"], t + " (3.35 m)"),
        "length_m": _dim(S["length_m"], f + " (overall length rotors turning 68 ft 6 in); CAP 437 D-value 20.88 m"),
        "fuselage_length_m": _dim(S["fus_len"], t + " (17.10 m)"),
        "width_m": _dim(S["width_m"], t + " (hull width 3.89 m, sponsons incl.)"),
        "height_m": _dim(S["height_m"], f + " (17 ft 11 in overall, tail rotor tip)"),
        "rotor_head_height_m": _dim(S["hub_top"], t + " (height 4.32 m)"),
        "d_value_m": _dim(20.88, "CAP 437 D-value for S-92, https://www.pprune.org/rotorheads/395350-s-92-landing-specification.html"),
        "main_rotor_blades": _dim(4, "Sikorsky S-92 4-blade main rotor (flugzeuginfo / aerocorner)"),
        "tail_rotor_blades": _dim(4, assumption=True),
    }


_S92["dims"] = _dims_s92


@register("s92")
def build_s92(rotor_azimuth_deg=0.0, tail_azimuth_deg=0.0):
    return _heli("s92", _S92, float(rotor_azimuth_deg), float(tail_azimuth_deg))


# -------------------------------------------------------------------------------------------- AW189
_AW189 = {
    "x_nose": 7.32, "fus_len": 15.40, "split": 0.70, "length_m": 17.57, "height_m": 5.07, "rotor_d": 14.60, "tail_R": 1.45,
    "n_main": 5, "n_tail": 4, "chord": 0.40, "hub_top": 4.04, "width_m": 3.00, "tr_y": 0.38,
    "stations": [
        (0.000, 0.06, 1.40, 1.65, 2.2), (0.020, 0.42, 1.18, 2.20, 2.2), (0.060, 0.80, 1.00, 2.70, 2.4),
        (0.120, 1.12, 0.90, 3.00, 2.8), (0.200, 1.32, 0.85, 3.12, 3.5), (0.300, 1.38, 0.82, 3.14, 4.0),
        (0.480, 1.38, 0.82, 3.14, 4.0), (0.600, 1.30, 0.88, 3.08, 3.8), (0.700, 0.98, 1.15, 2.98, 3.0),
        (0.800, 0.58, 1.50, 2.86, 2.6), (0.900, 0.30, 1.82, 2.72, 2.4), (1.000, 0.15, 2.05, 2.60, 2.2)],
    "cabin_frac": (0.20, 0.60), "win_frac": (0.27, 0.60), "n_win": 5, "win_z": (2.20, 2.80), "cockpit_frac": (0.10, 0.20), "cockpit_z": (1.95, 2.70),
    "sponson_x": (3.0, -2.6), "sponson_z": (0.78, 1.85), "wheel_r": 0.32, "wheel_w": 0.24, "main_gear_x": -1.0,
    "nose_gear_x": 4.9, "engine_y": 0.62, "engine_r": 0.44, "engine_x": (0.8, -2.5),
    "fin_pts": [(-4.4, 2.65), (-8.35, 3.75), (-9.4, 3.65), (-8.1, 2.40), (-4.8, 2.35)],
    "stab": (-6.0, 1.5, 2.40, 0.8),
    "d_value": 17.60,
    "notes": "AW189. Overall length 17.57 m, height 5.07 m (rotors turning, Leonardo). Rotor-head height 4.04 m and tail "
             "rotor diameter 2.90 m from the EASA OEB §3.2 dimensioned drawing. Fuselage length, sponson width are "
             "assumptions; station table approximate.",
}


def _dims_aw189(S):
    l = "Leonardo AW189 https://www.leonardo.com/en/-/aw189-1 ; https://www.fairlifts.com/helicopters/specifications/leonardo-aw189-helicopter-specifications/"
    e = ("EASA OEB draft report 14/01/2014 §3.2 dimensioned drawing, "
         "https://www.easa.europa.eu/sites/default/files/dfu/certification-experts-docs-oeb-reports-agusta-AW189-Draft-OEB-Report-10-01-14.pdf")
    return {
        "rotor_diameter_m": _dim(S["rotor_d"], l + " (14.60 m)"),
        "length_m": _dim(S["length_m"], l + " (17.57 m, rotors turning)"),
        "height_m": _dim(S["height_m"], l + " (5.07 m, rotors turning)"),
        "cabin_width_m": _dim(2.40, l + " (cabin width 2.40 m)"),
        "main_rotor_blades": _dim(5, l + " (5-blade main rotor)"),
        "tail_rotor_blades": _dim(4, l + " (4-blade tail rotor)"),
        "tail_rotor_diameter_m": _dim(2 * S["tail_R"], e + " (Ø2900 mm)"),
        "fuselage_length_m": _dim(S["fus_len"], assumption=True),
        "width_m": _dim(S["width_m"], assumption=True),
        "rotor_head_height_m": _dim(S["hub_top"], e + " (4040 mm rotor-head height)"),
    }


_AW189["dims"] = _dims_aw189


@register("aw189")
def build_aw189(rotor_azimuth_deg=0.0, tail_azimuth_deg=0.0):
    return _heli("aw189", _AW189, float(rotor_azimuth_deg), float(tail_azimuth_deg))
