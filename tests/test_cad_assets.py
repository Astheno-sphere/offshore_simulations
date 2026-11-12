"""CAD asset contract tests (offsim/assets/cad/base.py): the PSV is an exact solid at real scale,
its dims measure within 1 %, its HLR projection is real linework, and the section adapter keeps the
v7 physics (solids + exhaust) identical — only the drawing changes."""
import math

import pytest

cq = pytest.importorskip("cadquery", reason="cadquery not installed (requirements-cad.txt)")


def _edge_len(prims):
    t = 0.0
    for _, pts, _, _, _ in prims:
        for (x0, z0), (x1, z1) in zip(pts, pts[1:]):
            t += math.hypot(x1 - x0, z1 - z0)
    return t


def test_psv_asset_dims_and_qa():
    from offsim.assets.cad.base import build
    from offsim.assets.cad.qa import check

    a = build("psv_v10")
    assert a.meta["class"] == "vessel" and a.meta["lod"] == 2
    assert a.shape.isValid()
    assert {"hull", "superstructure", "funnel", "mast", "cargo"} <= set(a.parts)
    rep = check(a)
    assert rep["ok"], rep["dims"]
    assert sorted(rep["assumptions"]) == sorted(a.dims), "every PSV dim is assumed (no class drawing sourced)"
    assert rep["edge_density"]["n_polylines"] > 50


def test_psv_projection_is_real_linework():
    from offsim.assets.cad.base import build
    from offsim.assets.cad.drawing import project_classes as project

    a = build("psv_v10")
    classes = project(a.shape)
    assert classes["visible"], "no visible HLR edges"
    for key in ("silhouette", "visible", "hidden"):
        for pts in classes[key]:
            assert all(math.isfinite(x) and math.isfinite(z) for x, z in pts)
            assert -42.6 <= min(x for x, _ in pts) and max(x for x, _ in pts) <= 42.6
            assert -0.2 <= min(z for _, z in pts) and max(z for _, z in pts) <= 34.9
    zs = [z for pts in classes["visible"] for _, z in pts]
    assert max(zs) > 30.0, "the mast must appear in the projection"


def test_psv_profile_cad_parity_with_v7():
    """CAD drawing, v7 physics: solids and exhaust identical; linework denser than hand-drawn."""
    from offsim.assets.cad.drawing import psv_profile_cad
    from offsim.cinema.vessel_lineart import psv_profile

    p_old, s_old, e_old = psv_profile(28.0, 10.0)
    p_new, s_new, e_new = psv_profile_cad(28.0, 10.0)
    assert s_new == s_old, "the fluid obstacle mask must not change"
    assert e_new == e_old, "the exhaust point must not change"
    assert len(p_new) > len(p_old)
    assert _edge_len(p_new) > _edge_len(p_old)
    us = [x for _, pts, _, _, _ in p_new for x, _ in pts]
    ws = [z for _, pts, _, _, _ in p_new for _, z in pts]
    assert min(us) >= 28.0 and max(us) <= 113.0 and min(ws) >= 3.7 and max(ws) <= 38.7


def test_psv_profile_cad_pitch_matches_v7():
    from offsim.assets.cad.drawing import psv_profile_cad
    from offsim.cinema.vessel_lineart import psv_profile

    _, s_old, e_old = psv_profile(28.0, 10.0, pitch_rad=0.05, pivot=(70.5, 10.0))
    _, s_new, e_new = psv_profile_cad(28.0, 10.0, pitch_rad=0.05, pivot=(70.5, 10.0))
    assert s_new == s_old and e_new == e_old


def test_psv_v10_working_ship_shading():
    """v10 (his verdict on v9: "the ship looks cartoony" — correct): shading over outline, dark
    glass, no stick-men, funnel with a band. The cartoon recipe was one flat hull fill inside a
    bright outline + identical white window squares + stick-men + a plain-rectangle funnel.
    Asserts the drawing properties, not the look: the whipster judges the look on the stills."""
    from offsim.assets.cad.base import build
    from offsim.assets.cad.drawing import psv_profile_cad

    a = build("psv_v10")
    assert "windows" not in a.parts, "window boxes are gone from the solid (glazing is 2D now)"
    p_new, _, _ = psv_profile_cad(28.0, 10.0)
    fills = {f for _, _, _, f, _ in p_new if f}
    outlines = {o for _, _, _, _, o in p_new if o}
    # hull: three value bands, not one flat fill; superstructure: one value per tier
    assert {"hull_top", "hull", "hull_low"} <= fills, "hull value gradient missing"
    assert {"house", "house_mid", "house_top", "bridge"} <= fills, "tier value steps missing"
    # windows: dark glass with variation, never the white-square fill, never a bright outline
    assert "window" not in fills, "the white-square window fill is gone"
    assert "glass_dim" in fills, "glass variation missing"
    assert not any(f == "ink" for _, _, _, f, _ in p_new), "no fill may be the bright ink (crew heads)"
    assert not any(f in ("glass", "glass_dim") and o == "ink"
                   for _, _, _, f, o in p_new), "glass must not carry a bright outline"
    # funnel: colour band present
    assert "funnel_band" in fills, "funnel band missing"
    # outline down: no prim heavier than the reduced silhouette weight
    assert max(w for _, _, w, _, _ in p_new) <= 2.2, "outline weight must be down from v9's 3.0"
    # fills carry no outline at all except the boot-top stripe (a painted line, it keeps its edge)
    assert {f for _, _, _, f, o in p_new if f and o == "ink"} <= {"boot"}, \
        "only the boot-top stripe may keep a bright outline on a fill"
    # linework still denser than v8 (440 prims, 1,935 m) — detail was never the problem
    assert len(p_new) > 440
    assert _edge_len(p_new) > 1935.0


def test_psv_v9_detail_parts_and_denser_linework():
    """v9 de-kiddify: portholes, crane, davits, anchor and bridge mullions are real solids, and the
    profile linework is denser than v8's (440 prims, 1,935 m edge length) — a working ship, not a toy.
    The v7 physics parity (solids + exhaust) is still asserted by the tests above."""
    from offsim.assets.cad.base import build
    from offsim.assets.cad.drawing import project_classes as project, psv_profile_cad

    a = build("psv_v10")
    assert {"portholes", "crane", "davits", "anchor", "mullions"} <= set(a.parts)
    for name in ("portholes", "crane", "davits", "anchor", "mullions"):
        assert a.parts[name].isValid(), name
    classes = project(a.shape)
    assert sum(len(v) for v in classes.values()) > 256, "HLR linework must be denser than v8"
    p_new, _, _ = psv_profile_cad(28.0, 10.0)
    assert len(p_new) > 440, "profile prims must exceed v8's 440"
    assert _edge_len(p_new) > 1935.0, "profile edge length must exceed v8's 1,935 m"
