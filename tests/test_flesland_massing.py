"""Flesland massing: extrusion, tint-by-source, inset counts."""
import json

from tools.flesland_massing import _extrude, build_scene


def _fixture(tmp_path):
    data = [
        {"id": 1, "name": "Terminal", "coords": [[5.224, 60.297], [5.226, 60.297],
         [5.226, 60.298], [5.224, 60.298], [5.224, 60.297]],
         "height_m": 12.0, "height_src": "tag", "height_assumption": False},
        {"id": 2, "name": "Hotel", "coords": [[5.227, 60.297], [5.228, 60.297],
         [5.228, 60.298], [5.227, 60.298], [5.227, 60.297]],
         "height_m": 15.0, "height_src": "levels", "height_assumption": True},
        {"id": 3, "name": None, "coords": [[5.220, 60.295], [5.221, 60.295],
         [5.221, 60.296], [5.220, 60.296], [5.220, 60.295]],
         "height_m": None, "height_src": "none", "height_assumption": False},
        {"id": 4, "name": "Far", "coords": [[5.300, 60.350], [5.301, 60.350],
         [5.301, 60.351], [5.300, 60.351], [5.300, 60.350]],
         "height_m": 20.0, "height_src": "tag", "height_assumption": False},
    ]
    p = tmp_path / "buildings.json"
    p.write_text(json.dumps(data))
    return p


def test_extrude_makes_prism():
    verts, faces = [], []
    n = _extrude([(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)], 5.0,
                 12.0, verts, faces)
    assert n > 0
    zs = [v[2] for v in verts]
    assert min(zs) == 5.0 and max(zs) == 17.0


def test_scene_counts_and_tints(tmp_path):
    res = build_scene(tmp_path / "scene", _fixture(tmp_path))
    assert res["counts"] == {"measured": 1, "assumed_levels": 1, "flat": 1,
                             "total": 3}  # the far building is outside 1.5 km
    names = [a["name"] for a in res["spec"]["assets"]]
    assert names == ["ground", "measured", "assumed", "flat", "pad_halo", "pad"]
    colours = {a["name"]: a["colours"] for a in res["spec"]["assets"]}
    assert colours["measured"]["measured"] == "#e8dfd0"  # cream
    assert colours["assumed"]["assumed"] == "#c4b8a8"  # tinted tan
    assert colours["flat"]["flat"] == "#6e4a3c"
    assert res["pad"] == (5.2247, 60.2973)  # mapped pad, not the assumed heliport
    assert (tmp_path / "scene" / "scene.json").exists()
