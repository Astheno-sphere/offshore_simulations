"""Molde peak shot builder: counts and scene structure, no Blender needed."""
import json

import pandas as pd
import pytest

from tools.molde_peak_shot import (BBOX, build_roads_glb, build_scene,
                                    peak_positions, project, street_anchors)


@pytest.fixture
def tiny(tmp_path):
    traj = pd.DataFrame([
        # three buses + one ferry inside the bbox at t=5700, one bus outside
        {"agent_id": "b1", "t": 5670.0, "lon": 7.10, "lat": 62.70, "alt_m": 0, "state": "drive"},
        {"agent_id": "b1", "t": 5700.0, "lon": 7.11, "lat": 62.70, "alt_m": 0, "state": "drive"},
        {"agent_id": "b2", "t": 5700.0, "lon": 7.20, "lat": 62.75, "alt_m": 0, "state": "wait"},
        {"agent_id": "b3", "t": 5700.0, "lon": 7.00, "lat": 62.65, "alt_m": 0, "state": "drive"},
        {"agent_id": "f1", "t": 5700.0, "lon": 7.15, "lat": 62.68, "alt_m": 0, "state": "sail"},
        {"agent_id": "far", "t": 5700.0, "lon": 5.44, "lat": 62.29, "alt_m": 0, "state": "sail"},
    ])
    agents = pd.DataFrame([
        {"agent_id": "b1", "cls": "bus"}, {"agent_id": "b2", "cls": "bus"},
        {"agent_id": "b3", "cls": "bus"}, {"agent_id": "f1", "cls": "ferry"},
        {"agent_id": "far", "cls": "ferry"},
    ])
    traj_p, agents_p = tmp_path / "traj.csv", tmp_path / "agents.csv"
    traj.to_csv(traj_p, index=False)
    agents.to_csv(agents_p, index=False)
    land = {"type": "FeatureCollection", "features": [{
        "type": "Feature", "properties": {},
        "geometry": {"type": "Polygon", "coordinates": [[
            [7.05, 62.62], [7.25, 62.62], [7.25, 62.78], [7.05, 62.78],
            [7.05, 62.62]]]},
    }]}
    land_p = tmp_path / "land.geojson"
    land_p.write_text(json.dumps(land))
    osm_dir = tmp_path / "osm"
    osm_dir.mkdir()
    roads = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"highway": "trunk", "ref": "E 39"},
         "geometry": {"type": "LineString", "coordinates": [
             [7.06, 62.63], [7.15, 62.70], [7.24, 62.77]]}},
        {"type": "Feature", "properties": {"highway": "residential",
                                           "name": "Storgata"},
         "geometry": {"type": "LineString", "coordinates": [
             [7.10, 62.73], [7.18, 62.74]]}},
    ]}
    (osm_dir / "roads.geojson").write_text(json.dumps(roads))
    buildings = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"building": "house"},
         "geometry": {"type": "Polygon", "coordinates": [[
             [7.12, 62.735], [7.13, 62.735], [7.13, 62.74], [7.12, 62.74],
             [7.12, 62.735]]]}},
    ]}
    (osm_dir / "buildings.geojson").write_text(json.dumps(buildings))
    quays = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {},
         "geometry": {"type": "LineString", "coordinates": [
             [7.16, 62.735], [7.17, 62.735]]}},
    ]}
    (osm_dir / "quays.geojson").write_text(json.dumps(quays))
    landuse = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"landuse": "industrial"},
         "geometry": {"type": "Polygon", "coordinates": [[
             [7.20, 62.66], [7.22, 62.66], [7.22, 62.68], [7.20, 62.68],
             [7.20, 62.66]]]}},
    ]}
    (osm_dir / "landuse.geojson").write_text(json.dumps(landuse))
    return traj_p, agents_p, land_p, osm_dir


def test_peak_counts_in_frame_only(tiny):
    traj_p, agents_p, _, _ = tiny
    pos = peak_positions(traj_p, agents_p)
    by_cls = [p["cls"] for p in pos]
    assert sorted(by_cls) == ["bus", "bus", "bus", "ferry"]
    # the far ferry is outside the bbox and must not be counted
    assert all(p["agent_id"] != "far" for p in pos)


def test_heading_from_previous_step(tiny):
    traj_p, agents_p, _, _ = tiny
    pos = {p["agent_id"]: p for p in peak_positions(traj_p, agents_p)}
    # b1 moved east: heading ~0 deg from +x
    assert pos["b1"]["heading_deg"] == pytest.approx(0.0, abs=1.0)
    # b2 did not move: heading 0
    assert pos["b2"]["heading_deg"] == 0.0


def test_street_anchor_is_longest_way_midpoint(tiny):
    _, _, _, osm_dir = tiny
    anchors = {a["label"]: a for a in street_anchors(osm_dir / "roads.geojson")}
    assert set(anchors) == {"E39", "Storgata"}  # only these match the fixture
    e39 = anchors["E39"]
    x, y = project([7.15], [62.70])
    assert e39["x"] == pytest.approx(float(x[0]), abs=1.0)
    assert e39["y"] == pytest.approx(float(y[0]), abs=1.0)


def test_road_mesh_stays_inside_the_scene(tiny, tmp_path):
    """Regression: buffering in degrees made every road a continent and the
    first layered still came back 97.5% road-coloured. Ribbons must stay
    within the scene's projected extent."""
    import trimesh

    _, _, _, osm_dir = tiny
    roads = build_roads_glb(osm_dir / "roads.geojson", tmp_path / "roads")
    for half, info in roads.items():
        scene = trimesh.load(info["glb"], force="scene")
        bounds = scene.bounds
        assert abs(bounds).max() < 50000, (half, bounds)


def test_centre_place_labels_staggered(tiny, tmp_path):
    """The three centre places sit ~700 m apart but each label is ~4 km wide;
    the first layered still showed them colliding. They must be staggered in
    x and shown without the MOLDE prefix."""
    traj_p, agents_p, land_p, osm_dir = tiny
    res = build_scene(tmp_path / "scene", traj_p, agents_p, land_p, osm_dir)
    texts = {t["text"]: t["position"] for t in res["spec"]["texts"]}
    assert "SENTRUM" in texts and "MOLDE SENTRUM" not in texts
    assert "TRAFIKKTERMINAL" in texts and "FERJEKAI" in texts
    assert "LUFTHAVN, ÅRØ" in texts
    xs = [texts[k][0] for k in ("SENTRUM", "TRAFIKKTERMINAL", "FERJEKAI")]
    assert len(set(round(x) for x in xs)) == 3
    assert max(xs) - min(xs) >= 3000


def test_scene_structure(tiny, tmp_path):
    traj_p, agents_p, land_p, osm_dir = tiny
    res = build_scene(tmp_path / "scene", traj_p, agents_p, land_p, osm_dir)
    assert res["counts"] == {"bus": 3, "ferry": 1}
    assert res["total"] == 4
    spec = res["spec"]
    assert len(spec["assets"]) == 4 + 2 + 12 + 4  # base, roads, places, markers
    assert spec["assets"][0]["name"] == "land"
    assert spec["resolution"] == [1080, 1350]
    assert spec["camera"]["lens_mm"] == 35
    assert res["layers"]["buildings"] == 2  # one quad = two triangles
    assert res["layers"]["places"] == 6
    assert res["layers"]["texts"] == 8  # 6 places + E39 + Storgata
    assert (tmp_path / "scene" / "scene.json").exists()
    assert (tmp_path / "scene" / "land.glb").exists()
    assert (tmp_path / "scene" / "buildings.glb").exists()
    assert res["land"]["triangles"] == 2  # one quad = two triangles


def test_project_centre_is_origin():
    x, y = project([(BBOX[0] + BBOX[2]) / 2], [(BBOX[1] + BBOX[3]) / 2])
    assert float(x[0]) == pytest.approx(0.0, abs=1.0)
    assert float(y[0]) == pytest.approx(0.0, abs=1.0)
