"""AIS traffic layer: a deterministic subsample of a fetched clip; nothing fetched -> nothing drawn, and world_stack says so.
The clip is synthetic and lives in tmp_path only (data is never committed)."""
import numpy as np
import pandas as pd
import pytest

from offsim.traffic.positions import load_traffic, load_traffic_world


def _clip(path, n_vessels=30, per=40):
    rng = np.random.default_rng(1)
    rows = [(1000 + v, pd.Timestamp("2025-01-01", tz="UTC") + pd.Timedelta(minutes=i), 10.5 + rng.random() * .2, 59.3 + rng.random() * .1, 8.0, 90.0, 70)
            for v in range(n_vessels) for i in range(per)]
    rows += [(9999, pd.Timestamp("2025-01-01", tz="UTC"), 0.0, 0.0, 5.0, 0.0, 70)]            # outside the bbox
    pd.DataFrame(rows, columns=["mmsi", "timestamp", "lon", "lat", "sog", "cog", "ship_type"]).to_csv(path, index=False)
    return path


BBOX = (10.4, 59.2, 10.8, 59.5)


def test_subsample_is_deterministic_capped_and_inside_the_bbox(tmp_path):
    f = _clip(tmp_path / "c.csv")
    a = load_traffic(f, bbox=BBOX, max_vessels=10, max_points=100)
    b = load_traffic(f, bbox=BBOX, max_vessels=10, max_points=100)
    assert a == b                                                         # fixed seed: same bytes
    assert a["n_vessels"] == 10 and len(a["points"]) == 100 and a["caps_assumption"] is True
    assert all(BBOX[0] <= x <= BBOX[2] and BBOX[1] <= y <= BBOX[3] for x, y in a["points"])
    assert a["time_synchronised"] is False and "c.csv" in a["source"] and a["epoch_utc"].startswith("2025-01-01")
    assert load_traffic(f, bbox=BBOX, max_vessels=10, max_points=100, seed=8) != a      # the seed is the only freedom


def test_no_clip_means_none_and_the_scene_names_the_absence(tmp_path):
    assert load_traffic_world("nowhere", root=tmp_path) is None
    (tmp_path / "data/worlds/w/ais").mkdir(parents=True)
    assert load_traffic_world("w", root=tmp_path) is None                 # directory exists, no clip in it
    assert load_traffic(_clip(tmp_path / "e.csv"), bbox=(20, 70, 21, 71)) is None   # nothing in the box
    _clip(tmp_path / "data/worlds/w/ais/clip.csv")
    assert load_traffic_world("w", root=tmp_path, bbox=BBOX)["n_vessels"] == 30


def test_the_traffic_block_reaches_the_scene_and_flips_only_the_ais_layer(tmp_path):
    from offsim.contract import validate
    from offsim.scene import build_scene
    tr = pd.DataFrame({"agent_id": "a", "t": [0.0, 3600.0], "lon": [10.5, 10.51], "lat": [59.3, 59.3], "state": ["sail", "sail"]})
    ag = pd.DataFrame([{"agent_id": "a", "cls": "psv", "vmax_mps": 8.0, "capacity": 1.0, "domain": "sea"}])
    cam = {"longitude": 10.5, "latitude": 59.3, "zoom": 9, "pitch": 0, "bearing": 0}
    ov = {"kicker": "k", "title": "t", "legend": [], "source": "s", "watermark": "w"}
    blk = load_traffic(_clip(tmp_path / "c.csv"), bbox=BBOX, max_points=50)
    on = build_scene(tr, ag, validate(tr, ag), camera=cam, overlay=ov, traffic=blk)
    off = build_scene(tr, ag, validate(tr, ag), camera=cam, overlay=ov, absent_reasons={"ais": "no HAIS clip under data/worlds/w/ais"})
    assert on["world_stack"]["ais"]["present"] and on["traffic"] is blk
    assert not off["world_stack"]["ais"]["present"] and "no HAIS clip" in off["world_stack"]["ais"]["reason"] and "traffic" not in off
