"""CAD solids: PSV, jacket platform, S-92, AW189 (offsim.assets.cad.marine / air).

Every asset must build in < 10 s, be a valid OCC solid, carry its named parts, source every principal dimension and
measure within 1 % of its stated dimensions (scale is provable).
"""
import math
import time

import numpy as np
import pytest

from offsim.assets.cad import base
from offsim.assets.cad.air import bbox as air_bbox
from offsim.assets.cad.marine import bbox

TOL = 0.01
ASSETS = {
    "psv": {"parts": {"hull", "house", "bridge", "mast", "funnel", "cargo", "rail", "boat"}},
    "platform_jacket": {"parts": {"jacket", "decks", "modules", "crane", "flare", "lifeboats", "helideck", "stairs"}},
    "s92": {"parts": {"fuselage", "tailboom", "rotor", "tail_rotor", "gear", "nacelles", "tailfin", "sponsons"}},
    "aw189": {"parts": {"fuselage", "tailboom", "rotor", "tail_rotor", "gear", "nacelles", "tailfin", "sponsons"}},
}
_CACHE = {}


def _get(name, **kw):
    key = (name, tuple(sorted(kw.items())))
    if key not in _CACHE:
        t = time.perf_counter()
        m = base.build(name, **kw)
        _CACHE[key] = (m, time.perf_counter() - t)
    return _CACHE[key]


def _ext(shape, axis):
    b = bbox(shape)
    return b[2 * axis + 1] - b[2 * axis]


def _close(measured, stated, what):
    assert abs(measured - stated) <= TOL * stated, f"{what}: measured {measured:.3f} vs stated {stated:.3f}"


def _max_radius(part, pivot):
    v, _ = part.tessellate(0.02, 0.3)
    p = np.array([[a.x, a.y] for a in v]) - np.array(pivot[:2])
    return float(np.hypot(p[:, 0], p[:, 1]).max())


@pytest.mark.parametrize("name", list(ASSETS))
def test_builds_valid_fast_named(name):
    base.build(name) if name not in _CACHE else None  # warm imports outside the timing
    m, dt = _get(name)
    assert dt < 10.0, f"{name} took {dt:.1f}s"
    assert m.shape.isValid()
    assert ASSETS[name]["parts"] <= set(m.parts), set(ASSETS[name]["parts"]) - set(m.parts)
    for k, p in m.parts.items():
        assert p.isValid(), f"{name}.{k} invalid"
        assert p.Volume() > 0, f"{name}.{k} empty"
    assert m.meta["class"] in ("vessel", "structure", "aircraft") and m.meta["lod"] >= 2


@pytest.mark.parametrize("name", list(ASSETS))
def test_every_dim_is_sourced(name):
    m, _ = _get(name)
    assert m.dims
    for k, d in m.dims.items():
        assert "value" in d, k
        assert d.get("assumption") is True or (isinstance(d.get("src"), str) and d["src"].strip()), f"{name}.{k} unsourced"
    # a film may not use an asset whose principal dimensions are all assumptions
    assert any("src" in d for d in m.dims.values())


def test_psv_scale():
    m, _ = _get("psv")
    d = m.dims
    _close(_ext(m.shape, 0), d["loa_m"]["value"], "loa")
    _close(_ext(m.shape, 1), d["beam_m"]["value"], "beam")
    b = bbox(m.parts["hull"])
    _close(b[5], d["depth_m"]["value"], "depth (hull top)")
    assert abs(b[4]) < 1e-6, "keel at z=0"
    assert d["draught_m"]["value"] < d["depth_m"]["value"]
    # ISO 668 container dims and a real number of boxes on deck
    assert (d["container_length_m"]["value"], d["container_width_m"]["value"], d["container_height_m"]["value"]) == (6.058, 2.438, 2.591)
    assert m.meta["n_containers"] >= 10
    # bridge is forward of the cargo deck and above the house
    assert bbox(m.parts["bridge"])[0] > bbox(m.parts["cargo"])[1]
    assert bbox(m.parts["bridge"])[4] > bbox(m.parts["house"])[4]


def test_psv_params_scale():
    m, _ = _get("psv", loa_m=70.0, beam_m=16.0, depth_m=7.0, draught_m=5.5)
    _close(_ext(m.shape, 0), 70.0, "loa")
    _close(_ext(m.shape, 1), 16.0, "beam")
    _close(bbox(m.parts["hull"])[5], 7.0, "depth")
    assert m.dims["beam_m"].get("assumption") and m.dims["draught_m"].get("assumption")


def test_jacket_scale():
    m, _ = _get("platform_jacket")
    d = m.dims
    Wd, E = d["water_depth_m"]["value"], d["deck_elev_m"]["value"]
    assert abs(bbox(m.parts["jacket"])[4]) < 1e-6  # legs land on the seabed
    _close(bbox(m.parts["decks"])[4], Wd + E, "cellar deck underside")
    plate = m.parts["helideck_plate"]
    D = d["helideck_d_m"]["value"]
    assert abs(D - 20.88) < 1e-9 and "CAP 437" in d["helideck_d_m"]["src"]
    _close(_ext(plate, 0), D, "helideck dia x")
    _close(_ext(plate, 1), D, "helideck dia y")
    # helideck is cantilevered: its centre is outside the weather-deck footprint and above all decks
    hx, _ = m.meta["helideck_centre"]
    assert hx > bbox(m.parts["decks"])[1] - 4.0 and bbox(plate)[4] > bbox(m.parts["decks"])[4]
    # safety net ring is wider than the landing disc by >= 1.5 m each side
    assert _ext(m.parts["helideck"], 1) >= D + 2 * 1.5 - 1e-6


@pytest.mark.parametrize("legs,bays", [(4, 3), (8, 4)])
def test_jacket_variants(legs, bays):
    m, dt = _get("platform_jacket", legs=legs, bays=bays, water_depth_m=120.0, deck_elev_m=20.0, helideck_d_m=17.6)
    assert dt < 10 and m.shape.isValid()
    _close(_ext(m.parts["helideck_plate"], 0), 17.6, "helideck dia")
    _close(bbox(m.parts["decks"])[4], 140.0, "deck elev")
    assert m.dims["helideck_d_m"].get("assumption")  # not the CAP 437 S-92 value


@pytest.mark.parametrize("name", ["s92", "aw189"])
def test_helicopter_scale(name):
    m, _ = _get(name)
    d = m.dims
    _close(_ext(m.shape, 0), d["length_m"]["value"], "overall length")
    _close(bbox(m.shape)[5] - bbox(m.shape)[4], d["height_m"]["value"], "overall height")
    assert abs(bbox(m.shape)[4]) < 1e-6, "wheels on z=0"
    piv = m.meta["pivots"]["rotor"]
    R = d["rotor_diameter_m"]["value"] / 2
    _close(2 * _max_radius(m.parts["rotor"], piv["point"]), 2 * R, "rotor diameter")
    if m.meta["pivots"]["rotor"]["blades"] % 2 == 0:  # blades 0 and 180 deg lie on the x axis
        _close(_ext(m.parts["rotor"], 0), 2 * R, "rotor bbox x (azimuth 0)")
    assert m.meta["pivots"]["rotor"]["blades"] == d["main_rotor_blades"]["value"]
    tr = m.parts["tail_rotor"]
    _close(_ext(tr, 2), d["tail_rotor_diameter_m"]["value"], "tail rotor diameter")
    # main rotor hub above the roof, tail rotor behind the fuselage tail
    assert bbox(m.parts["rotor"])[4] > bbox(m.parts["fuselage"])[5]
    assert bbox(tr)[0] < bbox(m.parts["tailboom"])[0]


def test_s92_specific():
    m, _ = _get("s92")
    d = m.dims
    assert d["length_m"]["value"] == 20.88 and d["rotor_diameter_m"]["value"] == 17.17 and d["d_value_m"]["value"] == 20.88
    body = bbox(__import__("cadquery").Compound.makeCompound([m.parts["fuselage"], m.parts["sponsons"]]))
    _close(body[3] - body[2], d["width_m"]["value"], "hull width")
    _close(bbox(m.parts["rotor"])[5], d["rotor_head_height_m"]["value"], "rotor head height")
    assert m.meta["pivots"]["rotor"]["blades"] == 4


def test_aw189_specific():
    m, _ = _get("aw189")
    assert m.dims["rotor_diameter_m"]["value"] == 14.60 and m.meta["pivots"]["rotor"]["blades"] == 5


@pytest.mark.parametrize("name", ["s92", "aw189"])
def test_rotor_azimuth_rotates_rotor_only(name):
    m0, _ = _get(name, rotor_azimuth_deg=0.0)
    m1, _ = _get(name, rotor_azimuth_deg=37.0)
    R = m1.dims["rotor_diameter_m"]["value"] / 2
    _close(2 * _max_radius(m1.parts["rotor"], m1.meta["pivots"]["rotor"]["point"]), 2 * R, "rotor diameter at 37 deg")
    for k in m0.parts:
        if k != "rotor":
            a, b = bbox(m0.parts[k]), bbox(m1.parts[k])
            assert max(abs(x - y) for x, y in zip(a, b)) < 1e-6, k
    assert max(abs(x - y) for x, y in zip(bbox(m0.parts["rotor"]), bbox(m1.parts["rotor"]))) > 0.05
    assert m1.meta["pivots"]["rotor"]["azimuth_deg"] == 37.0
