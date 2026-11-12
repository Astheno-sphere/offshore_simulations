"""Land CAD assets (offsim/assets/cad/land.py): valid solids, dims within 1 % of the sourced values, determinism, timing."""
import json
import math
import os
import time

import pytest

cq = pytest.importorskip("cadquery")

from offsim.assets.cad.base import build as cad_build  # noqa: E402
from offsim.assets.cad import land  # noqa: E402
from offsim.assets.cad.land import bbox_dims  # noqa: E402

LAT0, LON0 = 62.7375, 7.1600          # Molde


def close(a, b, tol=0.01):
    return abs(a - b) <= tol * abs(b)


def check_dims(m):
    assert m.dims, "no dims"
    for k, d in m.dims.items():
        assert "value" in d, k
        assert d.get("src") or d.get("assumption") is True, f"{k}: neither sourced nor flagged"


def check_valid(m):
    assert m.shape.isValid()
    assert m.shape.Volume() > 0
    for n, p in m.parts.items():
        assert p.isValid(), n
        assert len(p.Solids()) >= 1, n
    assert m.meta["class"] in ("vehicle", "person", "tree", "building")
    assert m.meta["generator"] == "offsim.assets.cad.land"


def timed(fn, limit, **kw):
    """Wall-clock budget. why: these guard against a pathological regression (a boolean storm, an unbounded loop),
    not against a loaded machine. A 2 s budget on a CAD boolean failed at 2.19 s under parallel load (2026-11-12),
    so every budget is now the same order as the others (10 s): a real regression is 5-10x, never 10 %.
    Set OFFSIM_PERF_SCALE to stretch every budget on a slow runner."""
    limit *= float(os.environ.get("OFFSIM_PERF_SCALE", "1"))
    t = time.perf_counter()
    m = fn(**kw)
    dt = time.perf_counter() - t
    assert dt < limit, f"{fn.__name__}{kw} took {dt:.2f}s (limit {limit}s)"
    return m


# ------------------------------------------------------------------------------------------------ registry
def test_registry_builds_all_five():
    for name in ("bus", "train", "person", "tree", "building"):
        m = cad_build(name)
        check_valid(m)
        check_dims(m)


# ------------------------------------------------------------------------------------------------- bus
@pytest.mark.parametrize("length", [12.0, 18.0])
def test_bus_dims_and_parts(length):
    m = timed(land.build_bus, 10, length_m=length)
    check_valid(m)
    check_dims(m)
    b = bbox_dims(m.shape)
    assert close(b["x"], m.dims["length_m"]["value"])
    assert close(b["y"], m.dims["width_m"]["value"])
    assert close(b["z"], m.dims["height_m"]["value"])
    assert abs(b["zmin"]) < 1e-6 and abs((b["xmax"] + b["xmin"]) / 2) < 0.05
    assert m.dims["width_m"]["value"] == 2.55 and m.dims["height_m"]["value"] == 3.3 and "src" in m.dims["length_m"]
    for part in ("body", "windows", "doors", "glazing_ends", "wheels", "mirrors", "roof_equipment"):
        assert part in m.parts
    assert len(m.parts["wheels"].Solids()) >= (8 if length < 13 else 12)          # tyres + hubs, 2 or 3 axles
    # doors on the right (-y) side only
    assert m.parts["doors"].BoundingBox().ymax < 0
    # wheels sit on the road: tyre bottom at z=0
    assert abs(m.parts["wheels"].BoundingBox().zmin) < 1e-6
    if length > 13:
        assert "articulation" in m.parts and len(m.meta["axles_x"]) == 3
        assert close(m.dims["wheelbase_1_2_m"]["value"], 5.9) and close(m.dims["wheelbase_2_3_m"]["value"], 6.0)
    else:
        axles = m.meta["axles_x"]
        assert close(axles[0] - axles[1], m.dims["wheelbase_m"]["value"])


def test_bus_electric_flag_roof_pods():
    assert "roof_equipment" not in land.build_bus(electric=False).parts


# ----------------------------------------------------------------------------------------------- train
@pytest.mark.parametrize("n", [1, 3, 4])
def test_train_dims(n):
    m = timed(land.build_train, 10, n_cars=n)
    check_valid(m)
    check_dims(m)
    b = bbox_dims(m.shape)
    assert close(b["x"], m.dims["length_m"]["value"])
    assert close(b["y"], 3.2)
    assert close(b["z"], 4.38)
    assert close(m.dims["length_m"]["value"], n * 127.7 / 6)
    assert abs(b["zmin"]) < 1e-6
    for part in ("body", "windows", "doors", "bogies", "pantograph", "windscreen"):
        assert part in m.parts
    assert len(m.parts["body"].Solids()) == n
    assert len(m.meta["bogie_x"]) == n + 1
    pv = m.meta["pivots"]["pantograph"]
    assert pv["axis"] == (0, 1, 0) and 4.0 < pv["origin"][2] < 4.38
    # pantograph folded top is the sourced overall height
    assert close(m.parts["pantograph"].BoundingBox().zmax, 4.38, 0.002)


def test_train_pantograph_raised_reaches_wire_height():
    m = land.build_train(n_cars=2, pantograph_raised_m=1.6)
    assert m.parts["pantograph"].BoundingBox().zmax > 5.5


# ---------------------------------------------------------------------------------------------- person
@pytest.mark.parametrize("H", [1.50, 1.75, 1.95])
def test_person_stature_exact(H):
    m = timed(land.build_person, 10, stature_m=H)
    check_valid(m)
    check_dims(m)
    b = bbox_dims(m.shape)
    assert abs(b["zmax"] - H) < 1e-3 and abs(b["zmin"]) < 1e-3
    assert m.dims["stature_m"]["value"] == H
    seg = m.meta["segments_m"]
    assert close(seg["thigh"]["value"], 0.245 * H, 1e-9) and close(seg["shank"]["value"], 0.246 * H, 1e-9)
    # ratio consistency (Winter): hip height = thigh + shank + ankle height
    assert abs(seg["hip_height"]["value"] - (seg["thigh"]["value"] + seg["shank"]["value"] + seg["ankle_height"]["value"])) < 1e-9
    for part in ("head", "torso", "arm_l", "arm_r", "leg_l", "leg_r"):
        assert part in m.parts


def test_person_leg_and_arm_geometry_from_ratios():
    H = 1.8
    m = land.build_person(stature_m=H)
    leg = m.parts["leg_l"].BoundingBox()
    assert leg.zmin < 1e-6 and leg.zmax > 0.53 * H                    # hip joint at 0.530 H (thigh sphere above it)
    arm = m.parts["arm_l"].BoundingBox()
    hang = 0.818 * H - 0.010 * H - (0.186 + 0.146 + 0.108) * H         # fingertip height of a hanging arm
    assert abs(arm.zmin - (hang - 0.010 * H * 1.0)) < 0.03 * H
    shoulder_span = 2 * (0.259 * H / 2)
    assert abs(m.parts["arm_l"].BoundingBox().center.y - 0) < shoulder_span


def test_person_walking_phase_and_options():
    H = 1.75
    a = land.build_person(stature_m=H, pose="walking", phase=0.0)
    b = land.build_person(stature_m=H, pose="walking", phase=0.25)
    check_valid(a)
    check_valid(b)
    for m in (a, b):
        bb = bbox_dims(m.shape)
        assert abs(bb["zmin"]) < 1e-3
        assert close(bb["zmax"], m.dims["height_m"]["value"], 0.002)
        assert m.dims["height_m"]["value"] <= H + 1e-9                  # gait dip only lowers the figure
    assert bbox_dims(b.shape)["x"] > bbox_dims(land.build_person(stature_m=H).shape)["x"] * 2   # stride opens the legs
    for ph in [i / 10 for i in range(10)]:
        w = land.build_person(stature_m=H, pose="walking", phase=ph)
        assert w.dims["height_m"]["value"] <= H + 1e-9 and close(bbox_dims(w.shape)["zmax"], w.dims["height_m"]["value"], 0.003)
        assert abs(bbox_dims(w.shape)["zmin"]) < 1e-3
    hat = land.build_person(stature_m=H, hard_hat=True)
    assert "hard_hat" in hat.parts and hat.dims["height_m"]["value"] > H
    assert close(bbox_dims(hat.shape)["zmax"], hat.dims["height_m"]["value"], 0.002)
    suit = land.build_person(stature_m=H, survival_suit=True)
    assert suit.shape.Volume() > 1.5 * land.build_person(stature_m=H).shape.Volume()
    assert abs(bbox_dims(suit.shape)["zmax"] - H) < 1e-3
    with pytest.raises(ValueError):
        land.build_person(pose="running")


# ------------------------------------------------------------------------------------------------- tree
@pytest.mark.parametrize("sp", ["birch", "spruce", "pine"])
def test_tree_dims_and_lod(sp):
    m2 = timed(land.build_tree, 10, species=sp, seed=3, lod=2)
    m3 = timed(land.build_tree, 10, species=sp, seed=3, lod=3)
    for m in (m2, m3):
        check_valid(m)
        check_dims(m)
        b = bbox_dims(m.shape)
        assert close(b["z"], m.dims["height_m"]["value"], 0.005)
        assert close(b["x"], m.dims["crown_width_m"]["value"], 0.01) and close(b["y"], m.dims["crown_width_m"]["value"], 0.01)
        assert abs(b["zmin"]) < 1e-6
    assert "twigs" not in m2.parts and len(m3.parts["twigs"].Solids()) > 50
    assert len(m3.shape.Solids()) > len(m2.shape.Solids())
    assert m2.meta["n_primary_branches"] >= 15


def test_tree_params_override_and_ranges():
    m = land.build_tree("spruce", seed=1, height_m=30.0, crown_width_m=8.0)
    b = bbox_dims(m.shape)
    assert close(b["z"], 30.0, 0.005) and close(b["x"], 8.0, 0.01)
    assert m.dims["height_m"].get("src") and m.dims["crown_width_m"].get("src")
    # why (N3): the spruce default moved to 30 m — the low end of the cited 30-46 m mature range, crown 8.4 m inside
    # the cited 7.6-13.7 m spread — so the spruce defaults are sourced, not assumptions; pine/birch defaults (inside
    # a cited maximum only, no cited spread) stay assumed.
    d = land.build_tree("spruce")
    assert d.dims["height_m"].get("src") and d.dims["crown_diameter_m"].get("src")
    assert d.dims["height_m"]["value"] == 30.0 and d.dims["crown_diameter_m"]["value"] == d.dims["crown_width_m"]["value"] == 8.4
    for sp in ("pine", "birch"):
        dd = land.build_tree(sp)
        assert dd.dims["height_m"].get("assumption") is True and dd.dims["crown_diameter_m"].get("assumption") is True
    with pytest.raises(ValueError):
        land.build_tree("oak")


def test_tree_branches_inside_crown_width():
    m = land.build_tree("birch", seed=7, lod=3)
    w = m.dims["crown_width_m"]["value"]
    for part in ("trunk", "branches", "twigs"):
        bb = m.parts[part].BoundingBox()
        assert max(abs(bb.xmin), abs(bb.xmax), abs(bb.ymin), abs(bb.ymax)) <= w / 2 + 1e-6


def sig(m):
    bb = m.shape.BoundingBox()
    return (round(m.shape.Volume(), 6), round(bb.xmin, 6), round(bb.xmax, 6), round(bb.ymin, 6), round(bb.ymax, 6),
            round(bb.zmax, 6), len(m.shape.Solids()), m.meta["n_segments"])


@pytest.mark.parametrize("sp", ["birch", "spruce", "pine"])
def test_tree_deterministic_per_seed(sp):
    a, b = land.build_tree(sp, seed=11, lod=3), land.build_tree(sp, seed=11, lod=3)
    assert sig(a) == sig(b)
    c = land.build_tree(sp, seed=12, lod=3)
    assert sig(a) != sig(c)


# --------------------------------------------------------------------------------------------- building
def lonlat_rect(w_m, d_m, lon=LON0, lat=LAT0):
    ph = math.radians(lat)                                              # WGS84 metres per degree
    dlon = w_m / (111412.84 * math.cos(ph) - 93.5 * math.cos(3 * ph))
    dlat = d_m / (111132.95 - 559.82 * math.cos(2 * ph) + 1.175 * math.cos(4 * ph))
    return [(lon, lat), (lon + dlon, lat), (lon + dlon, lat + dlat), (lon, lat + dlat), (lon, lat)]


def test_building_from_lonlat_footprint_area_and_height():
    from shapely.geometry import Polygon
    fp = Polygon(lonlat_rect(30, 20))
    m = timed(land.build_building, 10, footprint=fp, height_m=15.0, crs="lonlat", lod=1)
    check_valid(m)
    check_dims(m)
    area = m.dims["footprint_area_m2"]["value"]
    assert close(area, 600.0, 0.005)
    assert close(m.shape.Volume(), area * 15.0, 1e-6)
    b = bbox_dims(m.shape)
    assert close(b["z"], 15.0) and abs(b["zmin"]) < 1e-9
    assert close(b["x"], 30.0, 0.005) and close(b["y"], 20.0, 0.005)
    assert m.dims["height_m"].get("src") and m.dims["floors"].get("assumption") is True


def test_building_metres_flat_and_gable_lods():
    ring = [(0, 0), (24, 0), (24, 14), (10, 14), (10, 9), (0, 9)]                # L-shape, 24*9 + 14*5 = 286 m2
    for roof in ("flat", "gable"):
        for lod in (2, 3):
            m = timed(land.build_building, 10, footprint=ring, height_m=13.0, roof=roof, lod=lod)
            check_valid(m)
            b = bbox_dims(m.shape)
            assert close(b["z"], 13.0, 1e-3) and abs(b["zmin"]) < 1e-9
            assert close(m.meta["footprint_area_m2"], 286.0, 1e-6)
            vol = m.shape.Volume()
            if roof == "flat":
                assert close(vol, 286.0 * 13.0, 0.01)          # recesses remove < 1 %
            else:
                assert 286.0 * 8.0 < vol < 286.0 * 13.0
            assert m.meta["floors"] >= 3 and m.meta.get("windows", 0) > 10
            base = m.parts["walls"].BoundingBox()
            assert abs(base.zmin) < 1e-9
    g = land.build_building(footprint=ring, height_m=13.0, roof="gable", lod=2)
    assert g.meta["roof_rise_m"] > 1.0 and abs(g.meta["wall_height_m"] + g.meta["roof_rise_m"] - 13.0) < 1e-9
    assert "windows" in land.build_building(footprint=ring, height_m=13.0, lod=3).parts


def test_building_lod1_is_plain_extrusion_and_holes():
    from shapely.geometry import Polygon
    p = Polygon([(0, 0), (20, 0), (20, 20), (0, 20)], [[(8, 8), (12, 8), (12, 12), (8, 12)]])        # courtyard
    m = land.build_building(footprint=p, height_m=10.0, lod=1)
    assert close(m.shape.Volume(), (400 - 16) * 10.0, 1e-6)
    m2 = land.build_building(footprint=p, height_m=10.0, lod=2)
    assert close(m2.shape.Volume(), (400 - 16) * 10.0, 0.01)


def test_building_timing_complex_footprint():
    import numpy as np
    from shapely.geometry import Polygon
    ang = np.linspace(0, 2 * math.pi, 41)[:-1]
    r = 22 + 4 * np.sign(np.sin(6 * ang))
    poly = Polygon([(float(a * math.cos(t)), float(a * 0.7 * math.sin(t))) for a, t in zip(r, ang)])      # 40 vertices
    for lod in (2, 3):
        m = timed(land.build_building, 10, footprint=poly, height_m=24.0, roof="gable", lod=lod)
        check_valid(m)


def write_city(tmp_path, n=300):
    feats = []
    for i in range(n):
        gx, gy = i % 20, i // 20
        ring = lonlat_rect(14, 10, LON0 + gx * 0.0003, LAT0 + gy * 0.0002)
        props = {"building": "yes"}
        if i % 3 == 0:
            props["height_m"] = 12.0
        elif i % 3 == 1:
            props["building:levels"] = "4"
        feats.append({"type": "Feature", "properties": props, "geometry": {"type": "Polygon", "coordinates": [ring]}})
    far = lonlat_rect(14, 10, LON0 + 1.0, LAT0 + 1.0)
    feats.append({"type": "Feature", "properties": {"height_m": 50}, "geometry": {"type": "Polygon", "coordinates": [far]}})
    feats.append({"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": [LON0, LAT0]}})
    path = tmp_path / "buildings.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    return path


def test_buildings_from_geojson_batch(tmp_path):
    path = write_city(tmp_path)
    bbox = (LON0 - 0.001, LAT0 - 0.001, LON0 + 0.01, LAT0 + 0.01)
    t = time.perf_counter()
    m = land.buildings_from_geojson(path, bbox=bbox, max_n=1000, lod=1)
    dt = time.perf_counter() - t
    assert dt < 5.0, dt
    assert m.meta["n_buildings"] == 300                                   # far building and the point are excluded
    assert len(m.shape.Solids()) == 300 and m.shape.isValid()
    assert m.meta["n_default_height"] == 100 and m.meta["n_height_from_levels"] == 100   # flagged assumptions
    b = bbox_dims(m.shape)
    assert close(b["z"], 12.0) and m.dims["height_max_m"]["value"] == 12.0
    # areas: 300 x ~140 m2 footprints
    assert close(m.shape.Volume(), sum(s.Volume() for s in m.shape.Solids()), 1e-9)
    per = [s.Volume() for s in m.shape.Solids()]
    assert close(sum(per) / 300, 140 * (100 * 12 + 100 * 12 + 100 * 6) / 300, 0.02)
    m5 = land.buildings_from_geojson(path, bbox=bbox, max_n=25, lod=1)
    assert m5.meta["n_buildings"] == 25
    assert m5.meta["origin"]["lonlat"] == ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)
    with pytest.raises(ValueError):
        land.buildings_from_geojson(path, bbox=(0, 0, 0.1, 0.1))


def test_buildings_from_geojson_lod2_small(tmp_path):
    path = write_city(tmp_path, n=6)
    m = timed(land.buildings_from_geojson, 10, path=path, bbox=(LON0 - 0.001, LAT0 - 0.001, LON0 + 0.01, LAT0 + 0.01),
              max_n=6, lod=2)
    assert m.meta["n_buildings"] == 6 and m.shape.isValid()
