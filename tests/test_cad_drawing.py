"""CAD drawing engine: exact HLR projection, section, cache, skia rendering, QA gate, story hook."""
import math

import pytest

cq = pytest.importorskip("cadquery")
pytest.importorskip("skia")

from offsim.assets.cad import base, drawing as D, qa as Q                      # noqa: E402
from offsim.assets.cad.base import AssetModel                                  # noqa: E402

L, B, H, HOUSE = 40.0, 8.0, 5.0, 3.0          # hull length / beam / depth, deckhouse height (m)


def ship_model(loa=L, beam=B, src=True):
    """Ship-like test asset: lofted hull (bow forward +x, keel at z=0) + deckhouse + funnel cylinder with a bore."""
    half = beam / 2
    hull = (cq.Workplane("YZ").workplane(offset=-L / 2).rect(beam, H, centered=(True, False))
            .workplane(offset=L * 0.75).rect(beam, H, centered=(True, False))
            .workplane(offset=L * 0.25).rect(0.4, H, centered=(True, False)).loft(combine=True, ruled=True))
    house = cq.Workplane("XY").box(10, beam * 0.6, HOUSE, centered=(True, True, False)).translate((-8, 0, H))
    funnel = cq.Workplane("XY").circle(1.0).extrude(4).faces(">Z").workplane().hole(1.2).translate((-8, 0, H + HOUSE))
    shape = cq.Workplane("XY").add(hull.val()).add(house.val()).add(funnel.val())
    whole = cq.Compound.makeCompound([hull.val(), house.val(), funnel.val()])
    dim = (lambda v: {"value": v, "src": "test data sheet"}) if src else (lambda v: {"value": v, "assumption": True})
    return AssetModel(shape=whole, parts={"hull": hull.val(), "house": house.val(), "funnel": funnel.val()},
                      dims={"loa_m": dim(loa), "beam_m": dim(beam), "depth_m": dim(H)},
                      meta={"class": "vessel", "lod": 2, "generator": "test"})


@pytest.fixture(scope="module")
def ship():
    return ship_model()


def test_side_projection_bbox_equals_solid_extent(ship):
    d = D.project(ship, "side")
    x0, y0, x1, y1 = d.bbox
    assert (x1 - x0) == pytest.approx(L, abs=1e-3)           # loa along x, in metres
    assert (y1 - y0) == pytest.approx(H + HOUSE + 4, abs=1e-3)  # keel to funnel top
    assert y0 == pytest.approx(0.0, abs=1e-3)
    # bow to the right: the bow tip (x = +L/2) is the right-hand extent
    assert x1 == pytest.approx(L / 2, abs=1e-3)
    top = D.project(ship, "top")
    assert (top.bbox[2] - top.bbox[0]) == pytest.approx(B, abs=1e-3)   # top view: right = -y, so width = beam
    assert (top.bbox[3] - top.bbox[1]) == pytest.approx(L, abs=1e-3)


def test_hidden_lines_only_with_flag_and_outline_class(ship):
    plain = D.project(ship, "iso")
    assert not plain.by_class("hidden")
    withh = D.project(ship, "iso", hidden=True)
    assert withh.by_class("hidden")
    assert plain.by_class("outline") and plain.by_class("visible")
    assert {l["part"] for l in plain.by_class("visible")} <= {"hull", "house", "funnel"}
    assert {l["part"] for l in plain.by_class("visible")} >= {"hull", "house"}
    # the deckhouse hides hull lines behind it: hidden set is non-trivial and bbox ignores hidden lines
    assert withh.bbox == pytest.approx(plain.bbox, abs=1e-6)


def test_section_contour(ship):
    s = D.section(ship, "yz", offset=L / 4)                  # hull-only cross-section (house spans x = -13..-3)
    pts = [p for l in s.lines for p in l["pts"]]
    assert s.lines and all(l["cls"] == "section" for l in s.lines)
    assert max(p[0] for p in pts) - min(p[0] for p in pts) == pytest.approx(B, abs=1e-3)
    assert max(p[1] for p in pts) - min(p[1] for p in pts) == pytest.approx(H, abs=1e-3)


def test_cache_round_trip(ship, tmp_path):
    d = D.project(ship, "side")
    back = D.Drawing.from_dict(__import__("json").loads(__import__("json").dumps(d.to_dict())))
    assert back.counts() == d.counts() and back.bbox == pytest.approx(d.bbox, abs=1e-4)

    @base.register("_cache_test")
    def build(**p):
        build.calls += 1
        return ship_model()
    build.calls = 0
    a = D.project_cached("_cache_test", {"k": 1}, "side", cache_dir=tmp_path)
    b = D.project_cached("_cache_test", {"k": 1}, "side", cache_dir=tmp_path)
    assert build.calls == 1 and a.counts() == b.counts()                 # second call = JSON only
    D.project_cached("_cache_test", {"k": 2}, "side", cache_dir=tmp_path)
    assert build.calls == 2 and len(list(tmp_path.glob("*.json"))) == 2   # params are part of the key
    assert D.cache_path("x", {"a": 1}, "side") != D.cache_path("x", {"a": 1}, "top")


def test_transform_pitch_and_heave(ship):
    d = D.project(ship, "side")
    m = d.transformed(angle=math.radians(3), dy=0.5, pivot=(0, 0))
    assert m.bbox != d.bbox and len(m.lines) == len(d.lines)
    same = d.transformed()
    assert same.bbox == pytest.approx(d.bbox)


def _canvas_px(d, w=480, h=160, **style):
    from offsim.cinema.draw import Canvas
    cv = Canvas(w, h, bg="#331c22", ss=2)
    s = (w - 20) / d.width
    stats = D.draw(cv, d, lambda x, y: (10 + s * (x - d.bbox[0]), h - 10 - s * (y - d.bbox[1])), style)
    return cv.to_pil(), stats


def test_draw_produces_antialiased_pixels(ship):
    import numpy as np
    img, stats = _canvas_px(D.project(ship, "side"))
    a = np.asarray(img).astype(int)
    bg = np.array([0x33, 0x1c, 0x22])
    diff = np.abs(a - bg).sum(axis=2)
    assert stats["drawn"] > 10 and stats["by_class"].get("outline")
    assert (diff > 0).sum() > 500
    ink = np.array([0xf2, 0xe9, 0xdf])
    full = (np.abs(a - ink).sum(axis=2) < 6).sum()
    partial = ((diff > 20) & (np.abs(a - ink).sum(axis=2) > 60)).sum()
    assert full > 0 and partial > 0                                         # solid ink and intermediate (AA) values


def test_scale_aware_dropping_and_hidden_style(ship):
    d = D.project(ship, "iso", hidden=True)
    from offsim.cinema.draw import Canvas
    cv = Canvas(40, 20, bg="#000000")
    tiny = D.draw(cv, d, lambda x, y: (20 + 0.005 * x, 10 - 0.005 * y), {"show_hidden": True})   # 0.005 px per metre
    assert tiny["dropped"] > 0 and tiny["drawn"] == 0
    _, no_h = _canvas_px(d)
    _, with_h = _canvas_px(d, show_hidden=True)
    assert "hidden" not in no_h["by_class"] and with_h["by_class"].get("hidden")


def test_svg(ship, tmp_path):
    p = D.to_svg(D.project(ship, "side"), tmp_path / "s.svg")
    txt = open(p).read()
    assert txt.startswith("<svg") and 'class="outline"' in txt and "polyline" in txt


def test_qa_passes_on_matching_dims_and_fails_on_5pct_wrong(ship):
    r = Q.qa(ship, drawn_height_px=200)
    ok, why = Q.passes(r, min_density=1)
    assert ok, why
    assert all(row["rel_err"] < 0.01 for row in r["dims"]) and r["sourced"] == 3 and r["assumed"] == 0
    assert r["density_per_100px"] > 0 and r["min_feature_m"] > 0 and r["parts"] == ["funnel", "house", "hull"]
    bad = Q.qa(ship_model(loa=L * 1.05))
    ok2, why2 = Q.passes(bad)
    assert not ok2 and "loa_m" in bad["dims_failed"] and "loa_m" in why2[0]
    ok3, why3 = Q.passes(Q.qa(ship, drawn_height_px=200), min_density=1e6)
    assert not ok3 and "density" in why3[0]


def test_qa_refuses_all_assumed():
    r = Q.qa(ship_model(src=False))
    ok, why = Q.passes(r)
    assert not ok and any("assumption" in w for w in why) and r["assumed"] == 3 and not r["dims_failed"]


def test_registry_gate_passes_all_nine_main_assets():
    # why (N3): locks in the CAD QA work — every film-eligible asset passes qa.gate with no drawn size. The N1 sprite
    # assets (psv_v10, s92_sprite, bus_sprite) are all-assumed by design and stay out of this list.
    for name in ("psv", "s92", "bus", "train", "person", "tree", "building", "aw189", "platform_jacket"):
        assert Q.gate(name) == [], name


def _storyboard(asset):
    return {"id": "t", "format": "square", "shots": [{"type": "card", "seconds": 1, "kpis": [], "asset": asset}]}


def _asset_probs(asset):
    from offsim.motion import story
    rep = {"gates": {"0": {"pass": True}}, "status": "ok"}
    return [p for p in story.check(_storyboard(asset), rep) if "asset" in p]


def test_story_check_gates_asset_shots():
    base.register("_assumed_tiny")(lambda **p: ship_model(src=False))
    base.register("_sourced_tiny")(lambda **p: ship_model(src=True))
    base.register("_wrong_tiny")(lambda **p: ship_model(loa=L * 1.05))
    assert any("assumption" in p for p in _asset_probs({"name": "_assumed_tiny"}))
    assert any("loa_m" in p for p in _asset_probs({"name": "_wrong_tiny"}))
    assert _asset_probs({"name": "_sourced_tiny", "view": "side"}) == []
    missing = _asset_probs({"name": "psv"})                       # psv is built and passes QA now (marine.py, shipselector class)
    assert missing == []
    assert any("cannot be built" in p for p in _asset_probs({"name": "psv", "params": {"loa_m": "not-a-number"}}))
    assert any("unknown asset" in p for p in _asset_probs({"name": "nope"}))
