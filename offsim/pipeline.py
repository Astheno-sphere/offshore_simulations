"""One command from scenario.yaml to a gated report (and a scene only if the gates allow it).

    python -m offsim run offsim/papers/<id>/scenario.yaml [--out out/<id>] [--seconds 5]

Gates, in order; a failure stops everything after it and is written to report.json:
  0 provenance   every fleet/instance/reported value has `src` or `assumption: true`
  1 plan         solver plan re-checked outside the solver (served once, capacity)
  2 replay=plan  simulated distance equals the solver objective (1%)
  3 contract     offsim.contract.validate (time, speed, teleport, state, capacity, land)
  4 paper        measured KPIs vs `reported:` -> status word for the narrator
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

    for key in ("fleet", "instance", "reported"):
        walk(sc.get(key), key)
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


def run(scenario_path, out=None, seconds=2.0, seed=1):
    scenario_path = Path(scenario_path)
    sc = yaml.safe_load(scenario_path.read_text())
    pid = sc["paper"]["id"]
    out = Path(out or ROOT / "out" / pid)
    out.mkdir(parents=True, exist_ok=True)
    world = sc.get("world")
    world_dir = ROOT / "data/worlds" / world if world and world != "none" else None
    report = {"paper": sc["paper"], "gates": {}, "status": None, "provenance": provenance_record(scenario_path, world_dir)}

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
    inst, fleet = sc["instance"], sc["fleet"][0]
    base = inst["base"]
    stops = inst["stops"]
    nodes = [(base["lon"], base["lat"])] + [(s["lon"], s["lat"]) for s in stops]
    land, legs, dist, snap = None, None, None, None
    if world_dir:
        if not (world_dir / "land.geojson").exists():
            stop("0_provenance", False, {"missing_world": str(world_dir), "fix": f"python -m offsim.worlds.fetch_world --pull {world}"})
            return report
        import geopandas as gpd
        from offsim.worlds.sealanes import SeaGraph
        land = gpd.read_file(world_dir / "land.geojson").geometry.union_all()
        lon, lat = np.array(nodes).T
        pad = 0.08
        sea = SeaGraph(land, bbox=(lon.min() - pad, lat.min() - pad, lon.max() + pad, lat.max() + pad),
                       spacing_m=sc.get("sim", {}).get("lane_spacing_m", 300), clearance_m=sc.get("sim", {}).get("clearance_m", 60))
        nodes = sea.snap(nodes)
        snap = dict(zip([base.get("name", "base")] + [s["name"] for s in stops], sea.snap_m))
        legs, dist = sea.legs(nodes)
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
                           "vmax_mps": speed * 1.0, "capacity": cap, "domain": fleet.get("domain", "sea")})
    service = {i: float(v(s.get("service_s", inst.get("service_s", 0))) or 0) for i, s in enumerate(stops, 1)}
    tw = {i: tuple(v(s["tw"])) for i, s in enumerate(stops, 1) if s.get("tw")}
    plan = dict(zip(ids, routes + [[]] * (n_veh - len(routes))))
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
    traj.to_csv(out / "trajectory.csv", index=False)
    agents.to_csv(out / "agents.csv", index=False)
    (out / "report.json").write_text(json.dumps(report, indent=1, default=float))
    print(f"[{pid}] gates 0-3 pass · status: {status} · {k['distance_km']:.1f} km · makespan {k['makespan_s'] / 3600:.2f} h")
    return report
