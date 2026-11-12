"""Our SimPy replay (offsim/sim/replay.py) behind the Engine protocol: Problem + Plan + World -> SimResult.

Mapping
- Plan.routes {agent_id: [node, ...]} -> replay routes (depot = node 0 added at both ends by the replay).
- Problem.fleet entries -> agents table; agent ids are expanded as `f"{cls.upper()}-{k}"` (the convention of
  `offsim.solve.pyvrp_solver.agent_ids`). A plan id that is not in the fleet raises `Unsupported`.
- Problem.service_s / tw / demand -> replay service_s / tw / demand. `problem.extra["berths"]` = {node: n}
  -> replay `shared` (agents queue for a berth, state `wait`, event `queue`).
- World.legs -> sea-lane geometry (a missing leg while `legs` is given raises Unsupported: no silent straight
  line across land). Without legs the legs are straight lines. World.land is not used by the engine; the
  contract validates it.
- KPIs: offsim.contract.kpis flattened to distance_km, makespan_s, wait_s, plus weather_wait_s = 0.0.
  Per-agent detail is in `meta["agents"]`.

Weather: this engine models none (`needs_weather = False`). A WeatherSeries is accepted and IGNORED, and the
result says so in `meta["weather_note"]` with `SimResult.weather = None`. Use the `openclsim` engine for
weather windows or `offsim.weather.effects` for the sourced PSV bands. Deterministic: `seed` is unused.
"""
from __future__ import annotations

import pandas as pd

from offsim.contract import kpis
from offsim.engines.base import Plan, Problem, SimResult, Unsupported, WeatherSeries, World, register_engine
from offsim.sim.replay import replay

_MOVE_STATE = {"sea": "sail", "air": "fly", "land": "drive"}


def fleet_agents(problem: Problem, plan: Plan) -> pd.DataFrame:
    """Agents table for the agents named in the plan. Raises Unsupported on unknown ids or mixed domains."""
    rows = {}
    for entry in problem.fleet:
        cls = str(entry.get("cls", "agent"))
        for k in range(int(entry["count"])):
            rows[f"{cls.upper()}-{k + 1}"] = {
                "agent_id": f"{cls.upper()}-{k + 1}", "cls": cls, "speed_mps": float(entry["speed_mps"]),
                "vmax_mps": float(entry.get("vmax_mps", entry["speed_mps"])), "capacity": float(entry["capacity"]),
                "domain": entry.get("domain", "sea")}
    unknown = sorted(set(plan.routes) - set(rows))
    if unknown:
        raise Unsupported(f"plan agents {unknown} are not in problem.fleet (expected ids like {sorted(rows)[:2]})")
    df = pd.DataFrame([rows[a] for a in plan.routes])
    return df


def move_state(agents: pd.DataFrame) -> str:
    domains = set(agents["domain"])
    if len(domains) > 1:
        raise Unsupported(f"mixed agent domains {sorted(domains)} in one run")
    return _MOVE_STATE[domains.pop() if domains else "sea"]


def check_plan(problem: Problem, plan: Plan, world: World) -> None:
    n = len(problem.nodes)
    for aid, r in plan.routes.items():
        bad = [s for s in r if not (1 <= int(s) < n)]
        if bad:
            raise ValueError(f"{aid}: route nodes {bad} outside 1..{n - 1} (depot is node 0 and is implicit)")
    if world.legs:
        for aid, r in plan.routes.items():
            path = [0] + list(r) + [0]
            for a, b in zip(path, path[1:]):
                if a != b and (a, b) not in world.legs and (b, a) not in world.legs:
                    raise Unsupported(f"world.legs has no sea-lane leg {a}->{b} (agent {aid})")


@register_engine("replay")
class ReplayEngine:
    name = "replay"
    classes = {"CVRP", "VRPTW", "PDP"}
    needs_weather = False

    def simulate(self, problem: Problem, plan: Plan, world: World,
                 weather: WeatherSeries | None = None, seed: int = 0) -> SimResult:
        extra_cls = set(problem.cls) - self.classes
        if extra_cls:
            raise Unsupported(f"replay engine handles {sorted(self.classes)}; problem also needs {sorted(extra_cls)}")
        check_plan(problem, plan, world)
        agents = fleet_agents(problem, plan)
        state = move_state(agents)
        berths = {int(n): int(c) for n, c in (problem.extra.get("berths") or {}).items()} or None
        traj, events = replay(problem.nodes, plan.routes, agents, service_s=problem.service_s or None,
                              tw=problem.tw or None, legs=world.legs, shared=berths, move_state=state,
                              demand=problem.demand or None)
        k = kpis(traj)
        flat = {"distance_km": k["distance_km"], "makespan_s": k["makespan_s"], "wait_s": k["wait_s"],
                "weather_wait_s": 0.0}
        meta = {"agents": k["agents"], "deterministic": True}
        if weather is not None:
            meta["weather_note"] = (f"weather series {weather.source!r} ignored: the replay engine models no weather; "
                                    "no weather effect is applied")
        return SimResult(traj=traj, agents=agents, events=events, kpis=flat, engine=self.name, seed=seed,
                         weather=None, meta=meta)
