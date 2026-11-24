"""Bergen service map: rings, arcs and dots from the assumed positions."""
import json

import yaml

from tools.bergen_service_map import build_scene, load_positions, ring_polys


def _fixture(tmp_path):
    root = tmp_path / "root"
    paper = root / "offsim" / "papers" / "irinagribkovskaia-2025-tactical-helicopter"
    paper.mkdir(parents=True)
    inst = {"instances": {"bergen": {
        "heliport": {"name": "Bergen", "lon": 5.2181, "lat": 60.2934,
                     "assumption": True},
        "positions": {"B1": [3.0, 60.6], "B2": [4.0, 61.0]}}}}
    (paper / "instances.yaml").write_text(yaml.safe_dump(inst))
    world = root / "data" / "worlds" / "bergen"
    world.mkdir(parents=True)
    land = {"type": "FeatureCollection", "features": [{
        "type": "Feature", "properties": {},
        "geometry": {"type": "Polygon", "coordinates": [[
            [1.5, 59.2], [5.6, 59.2], [5.6, 61.8], [1.5, 61.8],
            [1.5, 59.2]]]},
    }]}
    (world / "land.geojson").write_text(json.dumps(land))
    return root


def test_load_positions(tmp_path):
    root = _fixture(tmp_path)
    heli, pos = load_positions(
        root / "offsim" / "papers" /
        "irinagribkovskaia-2025-tactical-helicopter" / "instances.yaml")
    assert heli == (5.2181, 60.2934)
    assert sorted(pos) == ["B1", "B2"]


def test_ring_is_annulus():
    buf = ring_polys(0.0, 0.0, 100000.0)
    assert buf.geom_type == "Polygon"
    assert len(buf.interiors) == 1  # the hole: a ring, not a disc


def test_scene_structure(tmp_path):
    root = _fixture(tmp_path)
    res = build_scene(tmp_path / "scene",
                      root / "offsim" / "papers" /
                      "irinagribkovskaia-2025-tactical-helicopter" /
                      "instances.yaml",
                      root / "data" / "worlds" / "bergen")
    assert res["installations"] == 2
    assert res["land_triangles"] == 2
    spec = res["spec"]
    names = [a["name"] for a in spec["assets"]]
    assert names.count("inst_B1") == 1 and names.count("inst_B2") == 1
    assert "ring_50" in names and "ring_120" in names
    assert "arc_B1" in names and "arc_B2" in names
    assert len(spec["texts"]) == 4  # FLESLAND + 3 rings
    assert spec["sea"]["size_m"] == 600000
    assert spec["shading"]["line_px"] == 0
    assert (tmp_path / "scene" / "scene.json").exists()
