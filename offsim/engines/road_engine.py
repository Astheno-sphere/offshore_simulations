"""Land logistics on real roads: our SimPy replay with road legs and per-road-class speeds (state `drive`).

Mapping
- Plan.routes / Problem.fleet / service_s / tw / demand / extra["berths"] -> exactly as the `replay` engine
  (`offsim.engines.replay_engine`); every agent must have domain `land`, the moving state is `drive`.
- World.legs -> road geometry from `offsim.worlds.roads.RoadGraph.legs`. Legs are DIRECTED (one-way streets): leg (a, b) must
  be present for every used a -> b; the reverse leg (b, a) is NOT used as a stand-in. A missing used leg raises `Unsupported`.
- Travel time. `problem.extra["road_leg_profile"]` = {(a, b): [cumulative seconds at each vertex of legs[(a, b)]]}
  (RoadGraph.leg_profile) gives the time at every vertex, so a leg over a motorway then a village street takes the right
  time on each part. Without a profile, `problem.extra["road_time_s"]` (the RoadGraph time matrix) gives each leg one
  average speed. With neither the engine raises `Unsupported`: it will not fall back to a made-up speed.
- Speed cap. The fleet `speed_mps` is the vehicle's top speed: on every polyline hop the vehicle drives at
  min(road speed, fleet speed). If the cap lowers any leg, `meta["speed_cap_applied"]` is True and the time matrix the
  solver saw (uncapped) is shorter than the simulated drive time. All agents of one run must share one `speed_mps`
  (otherwise `Unsupported`: run the fleets separately).
- KPIs like replay: `distance_km, makespan_s, wait_s, weather_wait_s = 0.0`; per-agent detail in `meta["agents"]`;
  `meta["drive_s"]` is the summed time in state `drive`.

How a varying speed runs on a constant-speed replay (offsim/sim/replay.py is unchanged)
`replay` moves an agent at one speed along a polyline. Each used leg is therefore replayed in TIME-EQUIVALENT space: its
polyline is laid out on the equator with hop lengths = hop seconds x REF_SPEED_MPS, replayed at REF_SPEED_MPS (so
elapsed time = real seconds, time windows and berth queues see the right clock), and every moving row is mapped back to
the real road position by its elapsed seconds. Stationary rows (idle, wait, unload) already carry real coordinates and
are untouched. Rows keep every road vertex, so the trajectory follows the road polylines exactly.

Limits: free-flow speed at the limit (no congestion, signals, turn penalties or time-of-day); no weather (a WeatherSeries
is accepted, ignored and noted in `meta["weather_note"]`); CVRP and VRPTW only; one `speed_mps` per run.
Deterministic: `seed` is unused.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from offsim.contract import EARTH_R, MOVING, haversine_m, kpis
from offsim.engines.base import Plan, Problem, SimResult, Unsupported, WeatherSeries, World, register_engine
from offsim.engines.replay_engine import fleet_agents
from offsim.sim.replay import replay

REF_SPEED_MPS = 25.0          # replay speed in time-equivalent space; 1 s of travel = 25 equivalent metres (500 m sample = 20 s)
_GAP_DEG = 0.01               # empty longitude between two legs in time-equivalent space
_M_PER_DEG = EARTH_R * np.pi / 180.0


def _hop_m(pts):
    a = np.asarray(pts, dtype=float)
    if len(a) < 2:
        return np.zeros(0)
    return np.asarray(haversine_m(a[:-1, 0], a[:-1, 1], a[1:, 0], a[1:, 1]), dtype=float)


def leg_time_profile(key, pts, extra, cap_mps):
    """Cumulative seconds at each vertex of leg `key` with the speed cap applied. Raises Unsupported without time data.
    Returns (cum_seconds ndarray, capped: bool)."""
    hop = _hop_m(pts)
    prof = (extra.get("road_leg_profile") or {}).get(key)
    if prof is not None:
        cum = np.asarray(prof, dtype=float)
        if len(cum) != len(pts):
            raise Unsupported(f"road_leg_profile for leg {key} has {len(cum)} values for {len(pts)} vertices")
        dt = np.diff(cum)
    else:
        tm = extra.get("road_time_s")
        if tm is None:
            raise Unsupported(f"road engine has no travel time for leg {key}: pass problem.extra['road_leg_profile'] "
                              "or ['road_time_s'] from RoadGraph.legs (it does not guess a speed)")
        total = float(np.asarray(tm)[key[0], key[1]])
        if not np.isfinite(total) or (total <= 0 < hop.sum()):
            raise Unsupported(f"road_time_s[{key[0]}][{key[1]}] = {total}: not a usable travel time")
        dt = hop / hop.sum() * total if hop.sum() > 0 else np.zeros_like(hop)
    if (dt < 0).any():
        raise Unsupported(f"leg {key}: profile time goes backwards")
    capped = False
    if cap_mps:
        floor = hop / float(cap_mps)
        capped = bool((dt < floor - 1e-9).any())
        dt = np.maximum(dt, floor)
    return np.r_[0.0, np.cumsum(dt)], capped


def used_legs(routes, depot=0):
    out = []
    for r in routes.values():
        path = [depot] + [int(x) for x in r] + [depot]
        out += [(a, b) for a, b in zip(path, path[1:]) if a != b]
    return sorted(set(out))


def simulate_road(nodes, routes, agents, legs, extra=None, service_s=None, tw=None, shared=None, demand=None):
    """Replay `routes` on road legs. Returns (traj, events, info) with the contract's `drive` state.
    agents: DataFrame(agent_id, cls, speed_mps, vmax_mps, capacity, domain='land'). `legs` must hold every used ordered leg.
    info = {"speed_cap_mps", "speed_cap_applied", "time_basis", "legs"}. Raises Unsupported as described in the module doc."""
    extra = extra or {}
    if agents.empty:
        raise Unsupported("no agents")
    if set(agents["domain"]) != {"land"}:
        raise Unsupported(f"road engine runs land agents only; got domains {sorted(set(agents['domain']))}")
    speeds = sorted({float(s) for s in agents["speed_mps"]})
    if len(speeds) > 1:
        raise Unsupported(f"agents have different speed_mps {speeds}: the road engine applies one speed cap per run")
    cap = speeds[0]
    n = len(nodes)
    for aid, r in routes.items():
        bad = [s for s in r if not (1 <= int(s) < n)]
        if bad:
            raise ValueError(f"{aid}: route nodes {bad} outside 1..{n - 1} (depot is node 0 and is implicit)")
    need = used_legs(routes)
    missing = [k for k in need if not legs or k not in legs]
    if missing:
        raise Unsupported(f"world.legs has no road leg for {missing[:5]}{' ...' if len(missing) > 5 else ''} "
                          "(legs are directed; the reverse leg is not substituted)")

    warped, layout, any_cap, offset = {}, {}, False, 0.0
    for key in need:
        pts = [tuple(map(float, p)) for p in legs[key]]
        cum, capped = leg_time_profile(key, pts, extra, cap)
        any_cap |= capped
        total = float(cum[-1])
        if total <= 0:                                    # zero-length leg: replay it as it is, no time
            warped[key] = pts
            continue
        eq = cum * REF_SPEED_MPS / _M_PER_DEG             # equivalent metres -> degrees of longitude on the equator
        warped[key] = [(offset + float(x), 0.0) for x in eq]
        layout[key] = (offset, total, np.asarray(pts, dtype=float), cum)
        offset += float(eq[-1]) + _GAP_DEG
    ref_agents = agents.copy()
    ref_agents["speed_mps"] = REF_SPEED_MPS               # replay clock = real seconds in time-equivalent space
    ref_agents["vmax_mps"] = np.maximum(ref_agents["vmax_mps"], REF_SPEED_MPS)
    traj, events = replay(nodes, routes, ref_agents, service_s=service_s or None, tw=tw or None, legs=warped,
                          shared=shared or None, move_state="drive", demand=demand or None)

    fict = (traj["lat"].to_numpy() == 0.0) & traj["state"].isin(list(MOVING)).to_numpy()
    if fict.any() and layout:
        keys = list(layout)
        starts = np.array([layout[k][0] for k in keys])
        lon = traj["lon"].to_numpy(copy=True)
        lat = traj["lat"].to_numpy(copy=True)
        idx = np.where(fict)[0]
        which = np.searchsorted(starts, lon[idx] + 1e-9, side="right") - 1
        for w in np.unique(which):
            rows = idx[which == w]
            off, total, real, cum = layout[keys[w]]
            tau = np.clip((lon[rows] - off) * _M_PER_DEG / REF_SPEED_MPS, 0.0, total)
            lon[rows] = np.interp(tau, cum, real[:, 0])
            lat[rows] = np.interp(tau, cum, real[:, 1])
        traj = traj.assign(lon=lon, lat=lat)
    traj = traj.assign(alt_m=0.0)
    info = {"speed_cap_mps": cap, "speed_cap_applied": bool(any_cap), "legs": len(need),
            "time_basis": "road_leg_profile" if extra.get("road_leg_profile") else "road_time_s"}
    return traj, events, info


@register_engine("road")
class RoadEngine:
    name = "road"
    classes = {"CVRP", "VRPTW"}
    needs_weather = False

    def simulate(self, problem: Problem, plan: Plan, world: World,
                 weather: WeatherSeries | None = None, seed: int = 0) -> SimResult:
        extra_cls = set(problem.cls) - self.classes
        if extra_cls:
            raise Unsupported(f"road engine handles {sorted(self.classes)}; problem also needs {sorted(extra_cls)}")
        if not world.legs:
            raise Unsupported("road engine needs world.legs from RoadGraph.legs (no straight lines across country)")
        problem_fleet = [{**f, "domain": f.get("domain", "land")} for f in problem.fleet]
        agents = fleet_agents(Problem(**{**problem.__dict__, "fleet": problem_fleet}), plan)
        berths = {int(k): int(c) for k, c in (problem.extra.get("berths") or {}).items()} or None
        traj, events, info = simulate_road(problem.nodes, plan.routes, agents, world.legs, extra=problem.extra,
                                           service_s=problem.service_s, tw=problem.tw, shared=berths, demand=problem.demand)
        k = kpis(traj)
        drive_s = float(sum(a["time_by_state_s"].get("drive", 0.0) for a in k["agents"].values()))
        flat = {"distance_km": k["distance_km"], "makespan_s": k["makespan_s"], "wait_s": k["wait_s"], "weather_wait_s": 0.0}
        meta = {"agents": k["agents"], "deterministic": True, "drive_s": drive_s, **info}
        if weather is not None:
            meta["weather_note"] = (f"weather series {weather.source!r} ignored: the road engine models no weather; "
                                    "no weather effect is applied")
        return SimResult(traj=traj, agents=agents, events=events, kpis=flat, engine=self.name, seed=seed, weather=None, meta=meta)
