"""Sea lanes go around land and keep the contract; every mapped sprite and model exists with its licence."""
import json

import pandas as pd
from shapely.geometry import LineString, Polygon

from conftest import ROOT
from offsim.contract import validate
from offsim.sim.replay import replay
from offsim.worlds.sealanes import SeaGraph

# an island between two harbours, plus a quay that sits slightly on land
ISLAND = Polygon([(10.10, 59.00), (10.20, 59.00), (10.20, 59.10), (10.10, 59.10)])
SHORE = Polygon([(9.90, 58.90), (9.96, 58.90), (9.96, 59.20), (9.90, 59.20)])
LAND = ISLAND.union(SHORE)


def test_lane_goes_around_the_island_and_passes_the_contract():
    sea = SeaGraph(LAND, bbox=(9.92, 58.92, 10.40, 59.18), spacing_m=500, clearance_m=100)
    nodes = sea.snap([(9.955, 59.05), (10.30, 59.05)])          # first quay is 250 m inside SHORE
    assert sea.snap_m[0] > 0 and not SHORE.contains(LineString(nodes).interpolate(0))
    legs, dist = sea.legs(nodes)
    path = legs[(0, 1)]
    assert len(path) > 2                                         # had to turn
    assert not LineString(path).intersects(ISLAND)
    straight = LineString(nodes).length
    assert LineString(path).length > straight                    # detour is longer than the cut
    agents = pd.DataFrame({"agent_id": ["F"], "cls": "ferry", "speed_mps": 7.0, "vmax_mps": 7.0, "capacity": 1, "domain": "sea"})
    traj, _ = replay(nodes, {"F": [1]}, agents, legs=legs)
    assert validate(traj, agents, land=LAND).ok
    straight_traj, _ = replay(nodes, {"F": [1]}, agents)          # same trip without lanes
    assert "land" in {c for c, _, _ in validate(straight_traj, agents, land=LAND).violations}


def test_mapped_sprites_and_models_exist_with_licences():
    style = json.loads((ROOT / "offsim/style.json").read_text())
    assets = ROOT / "offsim/assets"
    for cls, key in style["sprites"].items():
        assert (assets / "sprites" / f"{key}.png").exists(), cls
    for kind, f in style["models"].items():
        assert (assets / "models" / f"{f}.glb").exists(), kind
    assert "MIT" in (assets / "sprites/LICENSE-fluentui-emoji.txt").read_text()
    assert style["agent_mode"] in ("sprite", "model", "dot")
