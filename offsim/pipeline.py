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
Registry (docs/ENGINES.md, "Choosing"): scenario `solver:` (default pyvrp; `none` = no routing, the engine dispatches itself) and
`engine:` (default replay for sea, road for land; wind O&M -> wombat, installation -> orbit, transit -> gtfs) are looked up in
offsim.engines.base. Gate 0 accepts the problem classes of the registered solvers and engines and reports an unsupported class or
a tool that does not import (with the import error). Further gates, all opt-in:
  1b exact       `certify: {max_clients: 12, gap_tol: {value: 0.02, assumption: true}, solver: pyomo|ampl}`: heuristic objective vs an
                 exact solve (or its proven bound); fails when the gap exceeds gap_tol
  3e ensemble    `ensemble: {seeds: N, weather: {dir, point, years, season} | {synthetic: {n, hours}}}` -> report["ensemble"]; a failed
                 ensemble stops here; synthetic weather sets report["reportable"] = False
  4c entur       `validate: {entur: true}` (engine gtfs): data/worlds/<w>/entur/vehicles.csv vs the timetable (observed.gate_4c)
Gate 2 compares simulated distance with the plan only for engines that follow a plan (replay, road, openclsim); wombat, orbit and
gtfs dispatch themselves and record {"pass": true, "detail": "engine dispatches itself (no plan to compare)"}.
`build_problem(sc)` and `build_variant(experiment, variant)` expose the same construction to offsim.research.
Land logistics: a fleet with `domain: land` (or scenario `world_mode: road`) routes on OSM roads from
data/worlds/<world>/osm/roads.geojson (offsim.worlds.roads.RoadGraph) and replays through offsim.engines.road_engine, state
"drive"; a missing file stops at gate 0 with the fetch command. report["provenance"]["graph"] says which graph was used:
sealanes | roads | none. `run(..., data_root=)` points the data directory elsewhere (tests); default <repo>/data.
Status words: reproduced | re-run under assumptions | did not reproduce | not comparable (no reported KPIs).
Failure codes: Every failing gate entry carries a stable `code` (offsim.doctor.codes, e.g. G3-LAND-CROSSING); a stopped run also has
  report["code"]. `python -m offsim doctor <report.json>` turns the code into checks, repairs and one question.
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
from offsim.doctor.codes import code_for_gate
from offsim.engines.base import (ENGINE_MODULES, SOLVER_MODULES, Plan, Problem, Unsupported, WeatherSeries, World,
                                 get_engine, get_solver)
from offsim.solve.pyvrp_adapter import matrix

ROOT = Path(__file__).resolve().parents[1]
ROUTING = {"CVRP", "VRPTW", "PDP"}   # classes that need a distance matrix / sea lanes / roads
SELF_DISPATCH = {"wombat", "orbit", "gtfs"}          # engines that decide their own moves: gate 2 has no plan to compare
DEFAULT_ENGINE = {"WIND-OM": "wombat", "WIND-INST": "orbit", "TRANSIT-REPLAY": "gtfs"}
EXTRA_KEYS = ("wombat", "orbit", "orbit_geo", "gtfs", "limits", "berths", "weather_t0_s", "wfppp")   # sim.<k> | extra.<k> -> Problem.extra
TOOL_PACKAGES = {"pyvrp": ("pyvrp",), "pyomo": ("pyomo", "highspy"), "ampl": ("amplpy",), "replay": ("simpy",),
                 "road": ("simpy",), "openclsim": ("openclsim", "simpy"), "wombat": ("wombat",),
                 "orbit": ("orbit-nrel",), "gtfs": (), "whelp": ("pyomo", "highspy"), "air": ()}


def supported_classes():
    """(classes handled by any registered solver or engine that imports, {tool: import error}). Loads every tool."""
    classes, bad = set(), {}
    for kind, mods, get in (("solver", SOLVER_MODULES, get_solver), ("engine", ENGINE_MODULES, get_engine)):
        for n in mods:
            try:
                classes |= set(get(n).classes)
            except Exception as exc:                      # noqa: BLE001 - an optional tool that does not import
                bad[f"{kind}:{n}"] = f"{type(exc).__name__}: {exc}"[:200]
    return classes, bad


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

    for key in ("fleet", "instance", "reported", "sim", "certify"):
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


def provenance_record(scenario_path, world_dir, tools=None):
    """tools: {"solver": name, "engine": name, ...}: recorded by name, with the versions of the packages behind them."""
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
    pkgs = ["pyvrp", "simpy", "shapely", "numpy", "pandas"]
    for t in (tools or {}).values():
        pkgs += [p for p in TOOL_PACKAGES.get(t, ()) if p not in pkgs]
    rec = {"scenario_sha256": hashlib.sha256(Path(scenario_path).read_bytes()).hexdigest(),
           "git_commit": sha, "git_dirty": dirty, "run_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "python": platform.python_version(),
           "packages": {p: ver(p) for p in pkgs},
           "world_manifest": json.loads(man.read_text()) if man and man.exists() else None}
    rec.update(tools or {})
    return rec


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


def unwrap(x):
    """Deep version of `v`: every {value, src|assumption, ..} leaf becomes its value, recursively."""
    if isinstance(x, dict):
        if "value" in x:
            return unwrap(x["value"])
        return {k: unwrap(y) for k, y in x.items()}
    if isinstance(x, list):
        return [unwrap(y) for y in x]
    return x


class WorldDataError(Exception):
    """Data the scenario needs is missing or unusable. `detail` is what gate 0 records (including the fix command)."""

    def __init__(self, detail):
        super().__init__(str(detail))
        self.detail = detail


def resolve_path(p, data_root=None):
    """Scenario paths are relative to the repo; `data/...` follows `data_root` (tests)."""
    p = Path(p)
    if p.is_absolute():
        return p
    if data_root is not None and p.parts[:1] == ("data",):
        return Path(data_root).joinpath(*p.parts[1:])
    return ROOT / p


def is_road_mode(sc):
    fleets = sc.get("fleet") or [{}]
    return sc.get("world_mode") == "road" or (sc.get("world_mode") is None and fleets[0].get("domain") == "land")


def select_tools(sc):
    """(solver name, engine name) from the scenario: `solver:` / `engine:` (or `problem.solver`), else the defaults."""
    classes = set(sc["problem"]["class"])
    routing = bool(classes & ROUTING)
    solver = v(sc.get("solver")) or v((sc.get("problem") or {}).get("solver")) or ("pyvrp" if routing else "none")
    engine = v(sc.get("engine"))
    if not engine:
        if routing:
            engine = "road" if is_road_mode(sc) else "replay"
        else:
            engine = next((DEFAULT_ENGINE[c] for c in sorted(classes) if c in DEFAULT_ENGINE), "replay")
    return str(solver), str(engine)


# ------------------------------------------------------------------------------------------------- problem
def build_problem(sc, data_root=None):
    """scenario dict -> (Problem, World, meta). Sea lanes or a RoadGraph for CVRP/VRPTW; classes that need no routing
    (WIND-OM, WIND-INST, TRANSIT-REPLAY) get a Problem whose `extra` holds their blocks (`sim.<k>` or `extra.<k>` for k in
    EXTRA_KEYS, {value, src} leaves unwrapped). meta: graph (sealanes|roads|none), snap_m, names, road, road_mode, world_dir.
    Raises WorldDataError (detail incl. the fix command) when a needed data file is missing."""
    classes = set(sc["problem"]["class"])
    routing = bool(classes & ROUTING)
    world = sc.get("world")
    worlds_dir = (Path(data_root) / "worlds") if data_root else ROOT / "data/worlds"
    world_dir = worlds_dir / world if world and world != "none" else None
    fleets = sc.get("fleet") or []
    fleet0 = fleets[0] if fleets else {}
    inst = sc.get("instance") or {}
    base = inst.get("base")
    stops = inst.get("stops") or []
    simc = sc.get("sim") or {}
    road_mode = routing and is_road_mode(sc)
    nodes = ([(base["lon"], base["lat"])] if base else []) + [(s["lon"], s["lat"]) for s in stops]
    names = ([base.get("name", "base")] if base else []) + [s["name"] for s in stops]
    land, legs, dist, snap, road = None, None, None, None, None
    graph = "none"
    if road_mode:
        roads_path = world_dir / "osm" / "roads.geojson" if world_dir else None
        if not (roads_path and roads_path.exists()):
            raise WorldDataError({"missing_roads": str(roads_path) if roads_path else "world is none: road runs need a world",
                                  "fix": f"python -m offsim.worlds.fetch_world --place {world} --modes road"})
        from offsim.worlds.roads import RoadGraph
        try:
            rg = RoadGraph(roads_path, speed_kph_by_highway=v(simc.get("road_speeds_kph")),
                           max_snap_m=float(v(simc.get("max_snap_m", 2000))))
            nodes = rg.snap(nodes)
            snap = dict(zip(names, rg.snap_m))
            legs, dist, road_time = rg.legs(nodes)
        except ValueError as exc:
            raise WorldDataError({"road_graph_error": str(exc), "roads": str(roads_path)}) from exc
        road = {"graph": rg.describe(), "time_s": road_time.tolist(), "profile": rg.leg_profile}
        graph = "roads"
    elif routing and world_dir:
        if not (world_dir / "land.geojson").exists():
            raise WorldDataError({"missing_world": str(world_dir), "fix": f"python -m offsim.worlds.fetch_world --pull {world}"})
        import geopandas as gpd
        from offsim.worlds.sealanes import SeaGraph
        land = gpd.read_file(world_dir / "land.geojson").geometry.union_all()
        lon, lat = np.array(nodes).T
        pad = 0.08
        sea = SeaGraph(land, bbox=(lon.min() - pad, lat.min() - pad, lon.max() + pad, lat.max() + pad),
                       spacing_m=v(simc.get("lane_spacing_m", 300)), clearance_m=v(simc.get("clearance_m", 60)))
        nodes = sea.snap(nodes)
        snap = dict(zip(names, sea.snap_m))
        legs, dist = sea.legs(nodes)
        graph = "sealanes"
    fleet, demand, service, tw = [], {}, {}, {}
    D = None
    for f in fleets:
        d = {k: unwrap(x) for k, x in f.items()}
        d["domain"] = "land" if road_mode else d.get("domain", "sea")
        if routing:
            d["count"], d["capacity"] = int(d["count"]), int(d["capacity"])
        fleet.append(d)
    if routing:
        D = matrix(nodes) if dist is None else dist
        demand = {i: int(v(s["demand"])) for i, s in enumerate(stops, 1)}
        service = {i: float(v(s.get("service_s", inst.get("service_s", 0))) or 0) for i, s in enumerate(stops, 1)}
        tw = {i: tuple(v(s["tw"])) for i, s in enumerate(stops, 1) if s.get("tw")}
        if "PDP" in classes:
            # pairing comes from the stops themselves: role pickup|delivery + a shared `pair` id. The demand the
            # solver and the replay see is signed (pickup -q, delivery +q), so load on board rises at the pickup
            # and falls at the delivery; the replay's load floor of 0 is what proves the order held.
            by_pair = {}
            for i, st in enumerate(stops, 1):
                if "pair" not in st or "role" not in st:
                    raise ValueError(f"PDP stop {st.get('name', i)!r} needs `role: pickup|delivery` and `pair: <id>`")
                by_pair.setdefault(st["pair"], {})[st["role"]] = i
            for pid, roles in by_pair.items():
                if set(roles) != {"pickup", "delivery"}:
                    raise ValueError(f"PDP pair {pid!r} needs exactly one pickup and one delivery, got {sorted(roles)}")
            pairs = {r["pickup"]: r["delivery"] for r in by_pair.values()}
            for pk, dl in pairs.items():
                if abs(demand[pk]) != abs(demand[dl]):
                    raise ValueError(f"PDP pair at nodes {pk}/{dl}: pickup and delivery demand differ")
                demand[pk] = -abs(demand[dl])
    extra = {}
    for key in EXTRA_KEYS:
        for src in (simc, sc.get("extra") or {}):
            if key in src:
                extra[key] = unwrap(src[key])
                break
    if "gtfs" in extra and isinstance(extra["gtfs"], dict) and "dir" in extra["gtfs"]:
        gdir = resolve_path(extra["gtfs"]["dir"], data_root)
        if not gdir.exists():
            raise WorldDataError({"missing_gtfs": str(gdir),
                                  "fix": f"python -m offsim.worlds.fetch_world --place {world} --modes bus   (or --pull {world})"})
        extra["gtfs"] = {**extra["gtfs"], "dir": str(gdir)}
    if road:
        extra["road_leg_profile"] = road["profile"]
    problem = Problem(cls=classes, nodes=nodes, dist_m=D, demand=demand, fleet=fleet, service_s=service, tw=tw, extra=extra)
    if "PDP" in classes:
        problem.pairs = pairs
    w = World(name=world or "none", land=land, legs=legs)
    return problem, w, {"graph": graph, "snap_m": snap, "names": names, "road": road, "road_mode": road_mode,
                        "world_dir": world_dir}


def _set_path(node, path, value):
    """Set `a.b.0.c` in nested dicts/lists, creating dicts on the way (experiment overrides)."""
    parts = str(path).split(".")
    for i, k in enumerate(parts[:-1]):
        nxt = parts[i + 1]
        if isinstance(node, list):
            node = node[int(k)]
        else:
            if k not in node or node[k] is None:
                node[k] = [] if nxt.isdigit() else {}
            node = node[k]
    if isinstance(node, list):
        node[int(parts[-1])] = value
    else:
        node[parts[-1]] = value


class BaseScenarioMissing(NotImplementedError, FileNotFoundError):
    """experiment.base does not exist, so no variant can be built (NotImplementedError keeps the contract of
    offsim.research.run_experiment: 'no builder')."""


def build_variant(experiment, variant, data_root=None, seconds=None, seed=1):
    """One experiment variant -> (problem, plan, world, engine) for offsim.research.run_experiment.

    The base scenario is loaded from experiment.base, the variant's `overrides` ({dotted.path: value}) are applied, `solver` and
    `engine` are set from the variant, and the result is built like `run` does. Overridden values must still carry a source or
    `assumption: true` (ValueError otherwise). Solver `none` gives an empty Plan (the engine dispatches itself)."""
    var = experiment.variants[variant]
    if not Path(experiment.base).exists():
        raise BaseScenarioMissing(f"experiment base scenario not found: {experiment.base}")
    sc = yaml.safe_load(Path(experiment.base).read_text())
    for path, val in (var.get("overrides") or {}).items():
        _set_path(sc, path, val)
    sc["solver"], sc["engine"] = var["solver"], var["engine"]
    gaps = provenance_gaps(sc)
    if gaps:
        raise ValueError(f"variant {variant!r}: values without src or assumption: {gaps}")
    problem, world, _ = build_problem(sc, data_root)
    if var["solver"] == "none":
        plan = Plan(routes={}, objective=0.0, solver="none")
    else:
        secs = seconds if seconds is not None else float((experiment.ensemble or {}).get("solve_seconds", 2.0))
        plan = get_solver(var["solver"]).solve(problem, seconds=secs, seed=seed)
    return problem, plan, world, get_engine(var["engine"])


# ------------------------------------------------------------------------------------------------- gates
def certify_gate(problem, plan, cert, seed=1):
    """Gate 1b: heuristic objective vs an exact solve. Returns (ok, detail). gap = (heuristic - L) / L where L is the exact
    objective when proven optimal, else the exact solver's proven bound. Fails when gap > gap_tol, when the exact solver
    errors, and when the heuristic is below the proven bound (the two models disagree)."""
    name = str(v(cert.get("solver", "pyomo")))
    tol = float(v(cert.get("gap_tol", 0.02)))
    max_clients = int(v(cert.get("max_clients", 12)))
    n_clients = len(problem.nodes) - 1
    detail = {"solver": name, "n_clients": n_clients, "max_clients": max_clients, "gap_tol": tol,
              "heuristic": plan.solver, "heuristic_m": float(plan.objective)}
    if n_clients > max_clients:
        detail["skipped"] = f"{n_clients} clients > max_clients {max_clients}: no exact certificate"
        return True, detail
    try:
        ex = get_solver(name).solve(problem, seconds=float(v(cert.get("seconds", 30))), seed=seed)
    except Exception as exc:                                                    # noqa: BLE001
        detail["error"] = f"{type(exc).__name__}: {exc}"[:300]
        return False, detail
    lower = ex.objective if ex.status == "optimal" else ex.bound
    detail.update(exact_status=ex.status, exact_m=float(ex.objective), bound_m=None if ex.bound is None else float(ex.bound))
    if lower is None:
        detail["error"] = "exact solver proved no bound"
        return False, detail
    lower = min(float(lower), float(ex.objective))
    h = float(plan.objective)
    gap = (h - lower) / lower if lower > 0 else (0.0 if h <= 0 else float("inf"))
    detail["gap"] = gap
    if h < lower - 1e-6 * max(1.0, lower):
        detail["error"] = "heuristic objective is below the exact bound: the two models do not describe the same problem"
        return False, detail
    return gap <= tol, detail


def load_weather(spec, data_root=None):
    """weather block -> (list[WeatherSeries], synthetic: bool). {synthetic: {n, hours, seed?}} is TEST-ONLY;
    {dir, point: [lon, lat], years: [y0, y1] | [y, ..], season?, dataset?} reads NORA3 files (offsim.weather.years)."""
    from offsim.weather.years import load_years, synthetic_years
    spec = unwrap(spec)
    if "synthetic" in spec:
        s = spec["synthetic"]
        return synthetic_years(int(s["n"]), int(s["hours"]), int(s.get("seed", 1))), True
    y = spec["years"]
    years = list(range(y[0], y[1] + 1)) if len(y) == 2 else list(y)
    return load_years(resolve_path(spec["dir"], data_root), tuple(spec["point"]), years, spec.get("season"),
                      dataset=spec.get("dataset", "NORA3")), False


def entur_gate(traj, vehicles_csv, gtfs_spec, opts):
    """Gate 4c: offsim.transit.observed on the simulated timetable trajectory. t = 0 of the gtfs trajectory is the service-day
    midnight (Europe/Oslo) + the window start `t0`, unless validate.entur_t0_utc overrides it."""
    from offsim.transit import entur, observed
    from offsim.transit.gtfs import parse_time
    t0 = gtfs_spec.get("t0", 0)
    t0_s = parse_time(t0) if isinstance(t0, str) else float(t0)
    if opts.get("entur_t0_utc"):
        t0_utc = pd.Timestamp(opts["entur_t0_utc"])
    else:
        day = pd.Timestamp(str(gtfs_spec["date"])).tz_localize("Europe/Oslo").tz_convert("UTC")
        t0_utc = day + pd.Timedelta(seconds=t0_s)
    o_tr, _ = observed.observed_trajectories(entur.read_csv(vehicles_csv), t0_utc)
    cmp = observed.compare_to_schedule(traj, o_tr)
    kw = {k: float(opts[f"entur_{k}"]) for k in ("max_median_delay_s", "max_tt_ratio") if f"entur_{k}" in opts}
    res = observed.gate_4c(cmp, **kw)
    res["detail"]["t0_utc"] = str(t0_utc)
    res["detail"]["journeys"] = json.loads(cmp.to_json(orient="records"))
    return res["pass"], res["detail"]


def run(scenario_path, out=None, seconds=2.0, seed=1, data_root=None):
    scenario_path = Path(scenario_path)
    sc = yaml.safe_load(scenario_path.read_text())
    pid = sc["paper"]["id"]
    out = Path(out or ROOT / "out" / pid)
    out.mkdir(parents=True, exist_ok=True)
    world = sc.get("world")
    worlds_dir = (Path(data_root) / "worlds") if data_root else ROOT / "data/worlds"
    world_dir = worlds_dir / world if world and world != "none" else None
    classes = set(sc["problem"]["class"])
    solver_name, engine_name = select_tools(sc)
    cert = sc.get("certify")
    cert_name = str(v(cert.get("solver", "pyomo"))) if cert else None
    tools = {"solver": solver_name, "engine": engine_name}
    if cert_name:
        tools["certify_solver"] = cert_name
    report = {"paper": sc["paper"], "gates": {}, "status": None,
              "provenance": provenance_record(scenario_path, world_dir, tools)}
    report["provenance"]["graph"] = "none"
    ais_on = bool((sc.get("validate") or {}).get("ais"))
    entur_on = bool((sc.get("validate") or {}).get("entur"))
    ens_cfg = sc.get("ensemble")
    ens_wx = (ens_cfg or {}).get("weather")

    def stop(gate, ok, detail):
        report["gates"][gate] = {"pass": bool(ok), "detail": detail}
        if not ok:
            code = code_for_gate(gate, detail)                  # stable failure code (offsim.doctor.codes)
            report["gates"][gate]["code"] = report["code"] = code
            report["status"] = f"stopped at gate {gate}"
            (out / "report.json").write_text(json.dumps(report, indent=1, default=float))
            print(f"[{pid}] STOP at {gate}: {detail}")
        return ok

    # gate 0: provenance, problem classes, tools that import
    gaps = provenance_gaps(sc)
    unavailable, mismatch, solver_obj, engine_obj = {}, [], None, None
    if solver_name != "none":
        try:
            solver_obj = get_solver(solver_name)
        except Exception as exc:                                                # noqa: BLE001
            unavailable[f"solver:{solver_name}"] = f"{type(exc).__name__}: {exc}"[:300]
    try:
        engine_obj = get_engine(engine_name)
    except Exception as exc:                                                    # noqa: BLE001
        unavailable[f"engine:{engine_name}"] = f"{type(exc).__name__}: {exc}"[:300]
    if cert_name:
        try:
            get_solver(cert_name)
        except Exception as exc:                                                # noqa: BLE001
            unavailable[f"solver:{cert_name}"] = f"{type(exc).__name__}: {exc}"[:300]
    if solver_obj is not None and not classes <= set(solver_obj.classes):
        mismatch.append(f"solver {solver_name} handles {sorted(solver_obj.classes)}, problem needs {sorted(classes)}")
    if engine_obj is not None and not classes <= set(engine_obj.classes):
        mismatch.append(f"engine {engine_name} handles {sorted(engine_obj.classes)}, problem needs {sorted(classes)}")
    unsupported = []
    if mismatch or unavailable:
        known, bad = supported_classes()
        unsupported = sorted(classes - known)
        unavailable = {**bad, **unavailable} if unavailable else unavailable
    detail0 = {"unsourced": gaps, "unsupported_classes": unsupported}
    if unavailable:
        detail0["unavailable"] = unavailable
    if mismatch:
        detail0["tool_mismatch"] = mismatch
    if not stop("0_provenance", not gaps and not unsupported and not unavailable and not mismatch, detail0):
        return report
    routing = bool(classes & ROUTING)
    follows_plan = solver_name != "none" and engine_name not in SELF_DISPATCH

    # inputs that must exist: fail early, with the fix, before any solving
    if ais_on:
        calib_path = world_dir / "ais" / "calibration.json" if world_dir else None
        if not (calib_path and calib_path.exists()):
            stop("0_provenance", False, {"missing_ais_calibration": str(calib_path) if calib_path else "world is none",
                                         "fix": f"python -m offsim.worlds.fetch_world --pull {world}   "
                                                f"(or: --world {world} --out data/worlds/{world} --ais <HAIS file>)"})
            return report
    vehicles_csv = world_dir / "entur" / "vehicles.csv" if world_dir else None
    if entur_on:
        if engine_name != "gtfs":
            stop("0_provenance", False, {"entur_validation": f"gate 4c compares a timetable replay; engine is {engine_name!r}, not 'gtfs'"})
            return report
        if not (vehicles_csv and vehicles_csv.exists()):
            stop("0_provenance", False, {"missing_entur_vehicles": str(vehicles_csv) if vehicles_csv else "world is none",
                                         "fix": f"run the entur-realtime workflow (offsim.transit.entur collect), then "
                                                f"python -m offsim.worlds.fetch_world --pull {world}"})
            return report
    main_wx = sc.get("weather") or ens_wx
    for spec in {id(x): x for x in (sc.get("weather"), ens_wx) if x}.values():
        spec = unwrap(spec)
        mdir = resolve_path(spec["dir"], data_root) if spec.get("dir") else None
        if "synthetic" not in spec and not (mdir and mdir.exists()):
            stop("0_provenance", False, {"missing_metocean": str(mdir) if mdir else "weather block has no dir or synthetic",
                                         "fix": f"python -m offsim.worlds.fetch_world --world {world} --out data/worlds/{world} "
                                                f"--metocean START_UTC HOURS   (or --pull {world})"})
            return report
    weather_years, synthetic_wx = [], False
    try:
        if main_wx:
            main_years, synthetic_wx = load_weather(main_wx, data_root)
            weather_years = main_years
        ens_years = load_weather(ens_wx, data_root)[0] if ens_wx and ens_wx is not main_wx else weather_years
    except (FileNotFoundError, ValueError, KeyError) as exc:
        stop("0_provenance", False, {"weather_error": f"{type(exc).__name__}: {exc}",
                                     "fix": f"python -m offsim.worlds.fetch_world --world {world} --out data/worlds/{world} "
                                            f"--metocean START_UTC HOURS   (or --pull {world})"})
        return report
    if getattr(engine_obj, "needs_weather", False) and not weather_years:
        stop("0_provenance", False, {"missing_weather": f"engine {engine_name} needs weather",
                                     "fix": "add `weather: {dir: data/worlds/<w>/metocean, point: [lon, lat], years: [y0, y1], season: DJF}` "
                                            "(or `ensemble.weather`); tests: `weather: {synthetic: {n, hours}}`"})
        return report

    # world, problem
    try:
        problem, world_obj, meta = build_problem(sc, data_root)
    except WorldDataError as exc:
        stop("0_provenance", False, exc.detail)
        return report
    report["provenance"]["graph"] = meta["graph"]
    snap, road = meta["snap_m"], meta["road"]
    nodes = problem.nodes
    demand = problem.demand
    fleet = problem.fleet[0] if problem.fleet else {}
    n_veh, cap = int(fleet.get("count", 0)), fleet.get("capacity")

    # solve (registry)
    if solver_name == "none":
        plan = Plan(routes={}, objective=0.0, solver="none")
        routes, cost = [], 0.0
        stop("1_plan", True, "no routes: solver none (the engine dispatches itself)")
    else:
        try:
            plan = solver_obj.solve(problem, seconds=seconds, seed=seed)
        except Exception as exc:                                                # noqa: BLE001 - Unsupported, infeasible, ...
            stop("1_plan", False, {"solver": solver_name, "error": f"{type(exc).__name__}: {exc}"[:300]})
            return report
        routes, cost = [r for r in plan.routes.values() if r], float(plan.objective)

        # gate 1: plan re-checked outside the solver
        if "WFPPP" in classes:                  # weekly flight program: demand, windows, opening hours, overlaps, spread (offsim.solve.whelp)
            from offsim.solve.whelp import check_program
            ok1, d1 = check_program(problem, plan)
            if not stop("1_plan", ok1, {**d1, "objective": cost}):
                return report
        else:
            served = sorted(c for r in routes for c in r)
            loads = [sum(demand[c] for c in r) for r in routes]
            if not stop("1_plan", served == sorted(demand) and max(loads, default=0) <= cap and len(routes) <= n_veh,
                        {"routes": routes, "loads": loads, "capacity": cap, "objective_m": cost}):
                return report

        # gate 1b: exact certificate (opt-in)
        if cert:
            ok, d1b = certify_gate(problem, plan, cert, seed=seed)
            if not stop("1b_exact", ok, d1b):
                return report

    # simulate (registry)
    try:
        res = engine_obj.simulate(problem, plan, world_obj, weather_years[0] if weather_years else None, seed=seed)
    except Exception as exc:                  # Unsupported or a bad route: report it, never approximate
        stop("2_replay_equals_plan", False, {f"{engine_name}_engine": f"{type(exc).__name__}: {exc}"[:300]})
        return report
    traj, events, agents = res.traj, res.events, res.agents
    k = kpis(traj)
    if road is not None:
        road.update({key: res.meta[key] for key in ("speed_cap_mps", "speed_cap_applied", "legs", "time_basis") if key in res.meta})

    # gate 2: replay = plan
    if follows_plan:
        if "WFPPP" in classes:                  # the replay recomputes the program's flight-hour cost from the geometry (1e-6) and its flight count
            g2 = compare_to_paper({a: res.kpis.get(a) for a in ("planned_variable_cost", "flights_planned_per_week")},
                                  {"planned_variable_cost": {"value": plan.meta["variable_cost"], "rel_tol": 1e-6},
                                   "flights_planned_per_week": {"value": len(plan.meta["program"]), "rel_tol": 0.0}})
        else:
            g2 = compare_to_paper({"distance_km": k["distance_km"]}, {"distance_km": {"value": cost / 1000, "rel_tol": 0.01}})
        if not stop("2_replay_equals_plan", bool(g2["pass"].all()), g2.to_dict("records")):
            return report
    else:
        stop("2_replay_equals_plan", True, "engine dispatches itself (no plan to compare)")

    # gate 3: contract
    rep = validate(traj, agents, land=world_obj.land)
    if not stop("3_contract", rep.ok, str(rep)):
        return report

    # gate 3e: ensemble (opt-in)
    if ens_cfg:
        from offsim.montecarlo import run_ensemble
        seeds_spec = ens_cfg.get("seeds", 1)
        seeds = list(range(int(seeds_spec))) if isinstance(seeds_spec, int) else [int(x) for x in seeds_spec]
        try:
            ens = run_ensemble(problem, plan, world_obj, engine_obj, ens_years, seeds, workers=int(ens_cfg.get("workers", 1)))
        except Unsupported as exc:
            stop("3e_ensemble", False, {"unsupported": str(exc)[:300]})
            return report
        rep_e = ens.to_report()
        report["ensemble"] = rep_e
        report["reportable"] = bool(ens.ok and not rep_e["synthetic_weather"] and rep_e["validated"])
        synthetic_wx = synthetic_wx or rep_e["synthetic_weather"]
        d3e = {"n_runs": rep_e["n_runs"], "n_valid": rep_e["n_valid"], "seeds": rep_e["seeds"], "years": rep_e["years"],
               "weather_sources": rep_e["weather_sources"]}
        if not ens.ok:
            d3e["failures"] = rep_e["failures"][:5]
        if not stop("3e_ensemble", ens.ok, d3e):
            return report
    elif synthetic_wx:
        report["reportable"] = False

    # gate 4: paper
    reported = sc.get("reported") or {}
    measured = {"distance_km": k["distance_km"], "makespan_s": k["makespan_s"], "wait_s": k["wait_s"]}
    if routing:
        measured["vehicles_used"] = sum(1 for r in routes if r)
    if engine_name not in ("replay", "road"):
        measured.update({a: b for a, b in res.kpis.items() if a not in measured})
    cmp = compare_to_paper(measured, reported) if reported else pd.DataFrame()
    assumed = assumptions_used(sc)
    if not reported:
        status = "not comparable (no reported KPIs)"
    elif cmp["pass"].all():
        status = "re-run under assumptions" if assumed else "reproduced"
    else:
        status = "did not reproduce"
    report["gates"]["4_paper"] = {"pass": status in ("reproduced", "re-run under assumptions"), "detail": cmp.to_dict("records")}
    if status == "did not reproduce":                       # "not comparable" has pass False too but is not a failure
        report["gates"]["4_paper"]["code"] = code_for_gate("4_paper", None)
    final_status = status + (" (synthetic weather, not reportable)" if synthetic_wx else "")
    report.update(status=final_status, assumptions=assumed, quay_snap_m=snap, kpis=k, measured=measured,
                  plan={"routes": routes, "objective_m": cost}, events=events.to_dict("records"))
    if solver_name != "pyvrp" or engine_name not in ("replay", "road"):
        report["tools"] = {"solver": solver_name, "engine": engine_name, "plan_status": plan.status,
                           "engine_kpis": res.kpis, "engine_meta_keys": sorted(res.meta)}
        if res.meta.get("weather_note"):
            report["tools"]["weather_note"] = res.meta["weather_note"]
    if meta["road_mode"]:
        report.update(snap_m=snap, road={a: b for a, b in road.items() if a != "profile"})
    if ais_on:
        calib = json.loads((world_dir / "ais" / "calibration.json").read_text())
        names = meta["names"]
        ok, detail = ais_gate(traj, calib, {nodes[i]: names[i] for i in range(len(nodes))})
        report["paper_status"] = final_status
        if not stop("4b_ais", ok, detail):
            return report
    elif meta["road_mode"] or "validate" in sc:
        report["gates"]["4b_ais"] = {"pass": True, "detail": "not requested"}
    if entur_on:
        ok, detail = entur_gate(traj, vehicles_csv, problem.extra["gtfs"], unwrap(sc["validate"]))
        report["paper_status"] = final_status
        if not stop("4c_entur", ok, detail):
            return report
    traj.to_csv(out / "trajectory.csv", index=False)
    agents.to_csv(out / "agents.csv", index=False)
    (out / "report.json").write_text(json.dumps(report, indent=1, default=float))
    print(f"[{pid}] gates 0-3 pass · status: {final_status} · {k['distance_km']:.1f} km · makespan {k['makespan_s'] / 3600:.2f} h")
    return report
