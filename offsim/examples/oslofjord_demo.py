"""Renderer and contract demo on the REAL Oslofjord coastline (world release `world-oslofjord`).

Timetable, demand and site placement are SYNTHETIC (labelled on screen): two ferries shuttle
Moss–Horten, a crew boat and a supply vessel serve two invented offshore sites in the outer fjord.
What is real: the coastline every sea leg is checked against.

    python -m offsim.worlds.fetch_world --pull oslofjord
    python -m offsim.examples.oslofjord_demo --out out/oslofjord
    python offsim/render_deck/render.py --scene out/oslofjord/scene.json --out out/oslofjord/still.png --format square --still --at 5400
"""
import argparse
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd

from offsim.contract import kpis, validate
from offsim.scene import build_scene, diagnose_world, write
from offsim.sim.replay import replay
from offsim.worlds.sealanes import SeaGraph

ROOT = Path(__file__).resolve().parents[2]
KN = 0.514444
# lon, lat (approximate terminal positions; synthetic sites in open water)
NODES = [(10.6540, 59.4330),   # 0 Moss ferry terminal
         (10.4930, 59.4180),   # 1 Horten ferry terminal
         (10.5700, 59.2400),   # 2 site A (synthetic wind turbine)
         (10.6200, 59.1500),   # 3 site B (synthetic platform)
         (10.5650, 59.4280)]   # 4 mid-fjord waypoint


def load_weather(world, traj, land):
    """The scene's `weather` block from the world's fetched NORA3 files (data/worlds/<w>/metocean/*nora3_wind*.nc, *nora3_wave*.nc), tagged
    provenance "nora3"; None when the folder or the files are not there (world_stack then names the absence). Never invents weather: a
    synthetic stand-in must be built by the caller and tagged "synthetic", which stamps the frame DRAFT."""
    mdir = Path(world) / "metocean"
    if not mdir.is_dir():
        return None
    import xarray as xr
    from offsim.weather.visual import weather_scene
    ds = {}
    for kind in ("wind", "wave"):
        f = sorted(mdir.glob(f"*nora3_{kind}*.nc"))
        if f:
            ds[f"ds_{kind}"] = xr.open_dataset(f[0])
    if not ds:
        return None
    bbox = [float(traj["lon"].min()) - 0.1, float(traj["lat"].min()) - 0.1, float(traj["lon"].max()) + 0.1, float(traj["lat"].max()) + 0.1]
    wx = weather_scene(bbox, float(traj["t"].min()), float(traj["t"].max()), land=land, seed=0, n_particles=2500, **ds)
    wx["provenance"] = "nora3"
    return wx


def run(out, world=ROOT / "data/worlds/oslofjord"):
    land = gpd.read_file(Path(world) / "land.geojson").geometry.union_all()
    sea = SeaGraph(land, bbox=(10.40, 59.10, 10.75, 59.47), spacing_m=300, clearance_m=60)
    nodes = sea.snap(NODES)                       # quays onto navigable water
    legs, dist = sea.legs(nodes)                  # sea lanes, not straight lines
    print('quays moved to water (m):', sea.snap_m)
    agents = pd.DataFrame([
        {"agent_id": "MF Bastø-1", "cls": "ferry", "speed_mps": 14 * KN, "vmax_mps": 15 * KN, "capacity": 200, "domain": "sea"},
        {"agent_id": "MF Bastø-2", "cls": "ferry", "speed_mps": 14 * KN, "vmax_mps": 15 * KN, "capacity": 200, "domain": "sea"},
        {"agent_id": "CTV-1", "cls": "crew_boat", "speed_mps": 22 * KN, "vmax_mps": 25 * KN, "capacity": 12, "domain": "sea"},
        {"agent_id": "PSV-1", "cls": "psv", "speed_mps": 11 * KN, "vmax_mps": 13 * KN, "capacity": 10, "domain": "sea"},
    ])
    frames = []
    # ferries: depot = their home terminal; three round trips each, offset by half a crossing
    for aid, home, other in (("MF Bastø-1", 0, 1), ("MF Bastø-2", 1, 0)):
        tr, _ = replay(nodes, {aid: [other, home, other, home, other]}, agents, depot=home, legs=legs,
                       service_s={0: 600, 1: 600})
        frames.append(tr)
    tr, _ = replay(nodes, {"CTV-1": [2, 3]}, agents, depot=0, legs=legs, service_s={2: 2400, 3: 1800}, demand={2: 6, 3: 6})
    frames.append(tr)
    tr, _ = replay(nodes, {"PSV-1": [3]}, agents, depot=1, legs=legs, service_s={3: 5400}, demand={3: 8})
    frames.append(tr)
    traj = pd.concat(frames, ignore_index=True)
    rep = validate(traj, agents, land=land)
    print(rep)
    k = kpis(traj)
    sites = [{"pos": list(nodes[2]), "kind": "wind_turbine", "label": "site A (synthetic)"},
             {"pos": list(nodes[3]), "kind": "platform", "label": "site B (synthetic)"},
             {"pos": list(NODES[0]), "label": "Moss", "height_m": 300},
             {"pos": list(NODES[1]), "label": "Horten", "height_m": 300}]
    terrain = None                                # the demo used to skip bathymetry even when it was pulled: load it when it is there
    tdir = Path(world) / "depth" / "fjord"
    if (tdir / "terrain.json").exists():
        from offsim.scene import load_terrain
        terrain = load_terrain(tdir)
    weather = load_weather(Path(world), traj, land)
    scene = build_scene(
        traj, agents, rep, land=land, sites=sites, lanes=[[list(p) for p in legs[(0, 1)]]], accent=("CTV-1",), seconds=16, trail_s=1800, land_relief_m=60,
        camera={"fit": [[10.42, 59.12], [10.72, 59.46]], "pitch": 50, "bearing": -15},
        overlay={"kicker": "one fjord, four schedules: who waits, who sails?",
                 "title": "Oslofjord — renderer demo",
                 "legend": [["#FF5B3A", "crew transfer vessel"], ["#E8E1CF", "ferries · supply vessel"]],
                 "source": "Coastline © OpenStreetMap contributors (ODbL) · timetable, sites and demand SYNTHETIC · vessels and sites: offsim CAD linework",
                 "watermark": "OFFSHORE SIMULATIONS"},
        kpi_track=[["km sailed, all vessels", [[0, f"{k['distance_km']:.0f}"]]]],
        terrain=terrain, weather=weather, absent_reasons=diagnose_world(Path(world).name))
    # lineart_px / site_lineart_px are existing style knobs raised for this demo scene only: at fjord zoom the CAD symbols (34 / 30 px) read as
    # specks. 60 / 54 px are set by eye (assumption, not sourced, not measured); the global style.json values are unchanged.
    scene["style"] = {"agent_mode": "lineart", "site_mode": "lineart", "lineart_px": 60, "site_lineart_px": 54}    # engineering linework, not emoji billboards; the global style.json default is unchanged
    out = Path(out)
    write(scene, out / "scene.json")
    (out / "report.json").write_text(json.dumps({"contract": str(rep), "kpis": k}, indent=1))
    return traj, rep, k


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out/oslofjord")
    run(ap.parse_args().out)
