"""One command from scenario.yaml to a gated report (and a scene only if the gates allow it).

    python -m offsim run offsim/papers/<id>/scenario.yaml [--out out/<id>] [--seconds 5]

Gates, in order; a failure stops everything after it and is written to report.json:
  0 provenance   every fleet/instance/reported value has `src` or `assumption: true`
  1 plan         solver plan re-checked outside the solver (served once, capacity)
  2 replay=plan  simulated distance equals the solver objective (1%)
  3 contract     offsim.contract.validate (time, speed, teleport, state, capacity, land)
  4 paper        measured KPIs vs `reported:` -> status word for the narrator
  4b ais         opt-in (`validate: {ais: true}`): simulated speeds / port-call dwell vs data/worlds/<w>/ais/calibration.json
                 (offsim.traffic.ais.compare_to_sim); a failure stops the run ("stopped at gate 4b_ais"). Recorded as
                 {"pass": true, "detail": "not requested"} for road runs and for any scenario that has a `validate:` block;
                 other scenarios (the sea demo) carry no 4b entry so their report is unchanged.
Land logistics: a fleet with `domain: land` (or scenario `world_mode: road`) routes on OSM roads from
data/worlds/<world>/osm/roads.geojson (offsim.worlds.roads.RoadGraph) and replays through offsim.engines.road_engine, state
"drive"; a missing file stops at gate 0 with the fetch command. report["provenance"]["graph"] says which graph was used:
sealanes | roads | none. `run(..., data_root=)` points the data directory elsewhere (tests); default <repo>/data.
Status words: reproduced | re-run under assumptions | did not reproduce | not comparable (no reported KPIs).
"""
from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import time
from importlib import metadata
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from offsim.contract import compare_to_paper, kpis, validate
from offsim.sim.replay import replay
from offsim.solve.pyvrp_adapter import matrix, solve_cvrp

ROOT = Path(__file__).resolve().parents[1]
SUPPORTED = {"CVRP", "VRPTW"}     # extend per paper; never silently approximate an unsupported class


def v(x):
    """Value of a sourced field: {value: .., src: ..} or a bare literal."""
    return x["value"] if isinstance(x, dict) and "value" in x else x


def provenance_gaps(sc):
    """Leaves that carry a value but neither a source nor an explicit assumption."""
    gaps = []

    def walk(node, path):
        if isinstance(node, dict):
            if "value" in node and not (node.get("src") or node.get("assumption")):
                gaps.append(path)
            for k, x in node.items():
                walk(x, f"{path}.{k}")
        elif isinstance(node, list):
            for i, x in enumerate(node):
                walk(x, f"{path}[{i}]")

    for key in ("fleet", "instance", "reported", "sim"):
        walk(sc.get(key), key)
    for k, x in (sc.get("sim") or {}).items():          # sim settings are parameters too: no bare literals
        if isinstance(x, (int, float)) and not isinstance(x, bool):
            gaps.append(f"sim.{k} (bare literal: use {{value, src|assumption}})")
    for i, s in enumerate(sc.get("instance", {}).get("stops", [])):
        if not (s.get("src") or s.get("assumption")):
            gaps.append(f"instance.stops[{i}] ({s.get('name')})")
    return gaps


def assumptions_used(sc):
    hits = []

    def walk(node, path):
        if isinstance(node, dict):
            if node.get("assumption"):
                hits.append(path)
            for k, x in node.items():
                walk(x, f"{path}.{k}")
        elif isinstance(node, list):
            for i, x in enumerate(node):
                walk(x, f"{path}[{i}]")
    walk(sc, "")
    return hits


def provenance_record(scenario_path, world_dir):
    def ver(p):
        try:
            return metadata.version(p)
        except metadata.PackageNotFoundError:
            return None
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout.strip())
    except FileNotFoundError:
        sha, dirty = None, None
    man = Path(world_dir) / "manifest.json" if world_dir else None
    return {"scenario_sha256": hashlib.sha256(Path(scenario_path).read_bytes()).hexdigest(),
            "git_commit": sha, "git_dirty": dirty, "run_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "python": platform.python_version(),
            "packages": {p: ver(p) for p in ("pyvrp", "simpy", "shapely", "numpy", "pandas")},
            "world_manifest": json.loads(man.read_text()) if man and man.exists() else None}


DWELL = ("load", "unload", "wait", "dp")


def dwell_durations(traj, names_by_xy):
    """{place: [seconds, ...]}: simulated dwell (state load/unload/wait/dp, consecutive rows at one node) per visit.
    names_by_xy: {(lon, lat): place name}. The replay emits stationary rows at the exact node coordinates."""
    out = {}
    for _, g in traj.sort_values(["agent_id", "t"], kind="stable").groupby("agent_id", sort=False):
        t, st = g["t"].to_numpy(dtype=float), g["state"].to_numpy()
        xy = list(zip(g["lon"].to_numpy(dtype=float), g["lat"].to_numpy(dtype=float)))
        block = None                                                   # [place, t_start, t_end]
        for i in range(len(g) - 1):
            place = names_by_xy.get(xy[i]) if st[i] in DWELL else None
            if place is not None and block is not None and block[0] == place:
                block[2] = t[i + 1]
            else:
                if block is not None:
                    out.setdefault(block[0], []).append(block[2] - block[1])
                block = [place, t[i], t[i + 1]] if place is not None else None
        if block is not None:
            out.setdefault(block[0], []).append(block[2] - block[1])
    return out


def ais_gate(traj, calib, names_by_xy):
    """Gate 4b: offsim.traffic.ais.compare_to_sim on the simulated trajectory. Returns (ok, detail).
    Port-call dwell is compared only for places the calibration lists (`port_call_s`); sailing/driving speeds against
    `sailing_speed_kn` (knots). Fails when any judged row fails, or when nothing could be compared (an opted-in gate that
    judges nothing is not a pass)."""
    from offsim.traffic.ais import compare_to_sim

    durs = {p: d for p, d in dwell_durations(traj, names_by_xy).items() if p in (calib.get("port_call_s") or {})}
    table = compare_to_sim(traj, calib, durs or None)
    judged = table["pass"].dropna()
    rows = json.loads(table.to_json(orient="records"))
    if judged.empty:
        return False, {"reason": "calibration has no metric comparable with this run", "src": calib.get("src"), "table": rows}
    bad = [r for r in rows if r["pass"] is False]
    return not bad, {"src": calib.get("src"), "failed": bad, "table": rows}


def run(scenario_path, out=None, seconds=2.0, seed=1, data_root=None):
    scenario_path = Path(scenario_path)
    sc = yaml.safe_load(scenario_path.read_text())
    pid = sc["paper"]["id"]
    out = Path(out or ROOT / "out" / pid)
    out.mkdir(parents=True, exist_ok=True)
    world = sc.get("world")
    worlds_dir = (Path(data_root) / "worlds") if data_root else ROOT / "data/worlds"
    world_dir = worlds_dir / world if world and world != "none" else None
    report = {"paper": sc["paper"], "gates": {}, "status": None, "provenance": provenance_record(scenario_path, world_dir)}
    report["provenance"]["graph"] = "none"
    fleet0 = sc["fleet"][0]
    road_mode = sc.get("world_mode") == "road" or (sc.get("world_mode") is None and fleet0.get("domain") == "land")
    ais_on = bool((sc.get("validate") or {}).get("ais"))

    def stop(gate, ok, detail):
        report["gates"][gate] = {"pass": bool(ok), "detail": detail}
        if not ok:
            report["status"] = f"stopped at gate {gate}"
            (out / "report.json").write_text(json.dumps(report, indent=1, default=float))
            print(f"[{pid}] STOP at {gate}: {detail}")
        return ok

    # gate 0: provenance and supported problem class
    gaps = provenance_gaps(sc)
    classes = set(sc["problem"]["class"])
    if not stop("0_provenance", not gaps and classes <= SUPPORTED,
                {"unsourced": gaps, "unsupported_classes": sorted(classes - SUPPORTED)}):
        return report

    # world: land + sea lanes when the world is present
    inst, fleet = sc["instance"], fleet0
    base = inst["base"]
    stops = inst["stops"]
    nodes = [(base["lon"], base["lat"])] + [(s["lon"], s["lat"]) for s in stops]
    land, legs, dist, snap = None, None, None, None
    road = None
    if ais_on:                                   # fail early, with the fix, before any solving
        calib_path = world_dir / "ais" / "calibration.json" if world_dir else None
        if not (calib_path and calib_path.exists()):
            stop("0_provenance", False, {"missing_ais_calibration": str(calib_path) if calib_path else "world is none",
                                         "fix": f"python -m offsim.worlds.fetch_world --pull {world}   "
                                                f"(or: --world {world} --out data/worlds/{world} --ais <HAIS file>)"})
            return report
    if road_mode:
        roads_path = world_dir / "osm" / "roads.geojson" if world_dir else None
        if not (roads_path and roads_path.exists()):
            stop("0_provenance", False, {"missing_roads": str(roads_path) if roads_path else "world is none: road runs need a world",
                                         "fix": f"python -m offsim.worlds.fetch_world --place {world} --modes road"})
            return report
        from offsim.worlds.roads import RoadGraph
        simc = sc.get("sim", {})
        try:
            rg = RoadGraph(roads_path, speed_kph_by_highway=v(simc.get("road_speeds_kph")),
                           max_snap_m=float(v(simc.get("max_snap_m", 2000))))
            nodes = rg.snap(nodes)
            snap = dict(zip([base.get("name", "base")] + [s["name"] for s in stops], rg.snap_m))
            legs, dist, road_time = rg.legs(nodes)
        except ValueError as exc:
            stop("0_provenance", False, {"road_graph_error": str(exc), "roads": str(roads_path)})
            return report
        road = {"graph": rg.describe(), "time_s": road_time.tolist(), "profile": rg.leg_profile}
        report["provenance"]["graph"] = "roads"
    elif world_dir:
        if not (world_dir / "land.geojson").exists():
            stop("0_provenance", False, {"missing_world": str(world_dir), "fix": f"python -m offsim.worlds.fetch_world --pull {world}"})
            return report
        import geopandas as gpd
        from offsim.worlds.sealanes import SeaGraph
        land = gpd.read_file(world_dir / "land.geojson").geometry.union_all()
        lon, lat = np.array(nodes).T
        pad = 0.08
        sea = SeaGraph(land, bbox=(lon.min() - pad, lat.min() - pad, lon.max() + pad, lat.max() + pad),
                       spacing_m=v(sc.get("sim", {}).get("lane_spacing_m", 300)), clearance_m=v(sc.get("sim", {}).get("clearance_m", 60)))
        nodes = sea.snap(nodes)
        snap = dict(zip([base.get("name", "base")] + [s["name"] for s in stops], sea.snap_m))
        legs, dist = sea.legs(nodes)
        report["provenance"]["graph"] = "sealanes"
    D = matrix(nodes) if dist is None else dist
    demand = {i: int(v(s["demand"])) for i, s in enumerate(stops, 1)}
    n_veh, cap, speed = int(v(fleet["count"])), int(v(fleet["capacity"])), float(v(fleet["speed_mps"]))
    routes, cost = solve_cvrp(nodes, demand, n_veh, cap, speed, seconds=seconds, dist=D, seed=seed)

    # gate 1: plan re-checked outside the solver
    served = sorted(c for r in routes for c in r)
    loads = [sum(demand[c] for c in r) for r in routes]
    if not stop("1_plan", served == sorted(demand) and max(loads, default=0) <= cap and len(routes) <= n_veh,
                {"routes": routes, "loads": loads, "capacity": cap, "objective_m": cost}):
        return report

    # replay in time
    ids = [f"{fleet['cls'].upper()}-{k + 1}" for k in range(n_veh)]
    agents = pd.DataFrame({"agent_id": ids, "cls": fleet["cls"], "speed_mps": speed,
                           "vmax_mps": speed * 1.0, "capacity": cap,
                           "domain": "land" if road_mode else fleet.get("domain", "sea")})
    service = {i: float(v(s.get("service_s", inst.get("service_s", 0))) or 0) for i, s in enumerate(stops, 1)}
    tw = {i: tuple(v(s["tw"])) for i, s in enumerate(stops, 1) if s.get("tw")}
    plan = dict(zip(ids, routes + [[]] * (n_veh - len(routes))))
    if road_mode:
        from offsim.engines.road_engine import simulate_road
        try:
            traj, events, road_info = simulate_road(nodes, plan, agents, legs, extra={"road_leg_profile": road["profile"]},
                                                    service_s=service, tw=tw, demand=demand)
        except Exception as exc:                 # Unsupported or a bad route: report it, never approximate
            stop("2_replay_equals_plan", False, {"road_engine": f"{type(exc).__name__}: {exc}"})
            return report
        road.update(road_info)
    else:
        traj, events = replay(nodes, plan, agents, service_s=service, tw=tw, legs=legs, demand=demand)
    k = kpis(traj)

    # gate 2: replay = plan
    g2 = compare_to_paper({"distance_km": k["distance_km"]}, {"distance_km": {"value": cost / 1000, "rel_tol": 0.01}})
    if not stop("2_replay_equals_plan", bool(g2["pass"].all()), g2.to_dict("records")):
        return report

    # gate 3: contract
    rep = validate(traj, agents, land=land)
    if not stop("3_contract", rep.ok, str(rep)):
        return report

    # gate 4: paper
    reported = sc.get("reported") or {}
    measured = {"distance_km": k["distance_km"], "makespan_s": k["makespan_s"], "wait_s": k["wait_s"],
                "vehicles_used": sum(1 for r in routes if r)}
    cmp = compare_to_paper(measured, reported) if reported else pd.DataFrame()
    assumed = assumptions_used(sc)
    if not reported:
        status = "not comparable (no reported KPIs)"
    elif cmp["pass"].all():
        status = "re-run under assumptions" if assumed else "reproduced"
    else:
        status = "did not reproduce"
    report["gates"]["4_paper"] = {"pass": status in ("reproduced", "re-run under assumptions"), "detail": cmp.to_dict("records")}
    report.update(status=status, assumptions=assumed, quay_snap_m=snap, kpis=k, measured=measured,
                  plan={"routes": routes, "objective_m": cost}, events=events.to_dict("records"))
    if road_mode:
        report.update(snap_m=snap, road={a: b for a, b in road.items() if a != "profile"})
    if ais_on:
        calib = json.loads((world_dir / "ais" / "calibration.json").read_text())
        names = [base.get("name", "base")] + [s["name"] for s in stops]
        ok, detail = ais_gate(traj, calib, {nodes[i]: names[i] for i in range(len(nodes))})
        report["paper_status"] = status
        if not stop("4b_ais", ok, detail):
            return report
    elif road_mode or "validate" in sc:
        report["gates"]["4b_ais"] = {"pass": True, "detail": "not requested"}
    traj.to_csv(out / "trajectory.csv", index=False)
    agents.to_csv(out / "agents.csv", index=False)
    (out / "report.json").write_text(json.dumps(report, indent=1, default=float))
    print(f"[{pid}] gates 0-3 pass · status: {status} · {k['distance_km']:.1f} km · makespan {k['makespan_s'] / 3600:.2f} h")
    return report
