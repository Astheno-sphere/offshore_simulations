"""Engine and solver interfaces: the seams every tool plugs into.

Layering (docs/ARCHITECTURE.md). A layer may call only the layers below it:

    L6 research   offsim.research   feed -> gaps -> experiment.yaml
    L5 present    offsim.scene / motion / render_deck     (reads report.json + trajectories only)
    L4 validate   offsim.contract + offsim.traffic        (gates, AIS calibration)
    L3 ensemble   offsim.montecarlo                       (N weather years x seeds -> distributions)
    L2 simulate   offsim.engines.*                        (Plan + world + weather -> SimResult)
    L1 solve      offsim.solve.*                          (Problem -> Plan)
    L0 data       offsim.worlds / weather / traffic / feed (fetched on Actions, pulled here)

Rules
- Every engine and solver returns the same objects (Plan, SimResult). Nothing above L2 knows which
  tool produced them; swapping OpenCLSim for the SimPy replay changes no line above L2.
- Every engine emits the trajectory contract (offsim.contract), so gate 3 and the renderer work unchanged.
- Engines never fetch data. They get a World and a WeatherSeries; data arrives via L0.
- An engine that cannot represent part of the scenario raises Unsupported; it never approximates silently.
- Randomness only through the `seed` argument (common random numbers across variants in L3).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

import pandas as pd


class Unsupported(Exception):
    """The tool cannot represent this scenario feature. Gate 0 reports it; never approximated."""


@dataclass
class Problem:
    """What a solver sees: the scenario reduced to numbers. Built by offsim.pipeline from scenario.yaml."""
    cls: set[str]                       # e.g. {"CVRP"}, {"VRPTW"}, {"PSV-PDP"}, {"WIND-OM"}
    nodes: list[tuple[float, float]]    # (lon, lat); nodes[0] is the depot / base / port
    dist_m: Any                         # NxN metres (sea-lane matrix when a world is present)
    demand: dict[int, float]            # node -> units
    fleet: list[dict]                   # [{cls, count, capacity, speed_mps, ...}] values already unwrapped
    service_s: dict[int, float] = field(default_factory=dict)
    tw: dict[int, tuple[float, float]] = field(default_factory=dict)
    extra: dict = field(default_factory=dict)   # class-specific data (e.g. PSV departure days, turbine list)


@dataclass
class Plan:
    """What a solver returns. routes: {agent_id: [node, ...]} without the depot at either end."""
    routes: dict[str, list[int]]
    objective: float
    objective_unit: str = "m"
    solver: str = ""
    bound: float | None = None          # dual bound when the solver proves one (exact models)
    status: str = "feasible"            # feasible | optimal | time_limit
    meta: dict = field(default_factory=dict)


@dataclass
class World:
    """Geography an engine runs in. Built once per scenario by offsim.worlds; read-only for engines."""
    name: str
    land: Any = None                    # shapely geometry, or None for an open-sea test world
    legs: dict | None = None            # {(a, b): [(lon, lat), ...]} sea-lane geometry
    ports: dict = field(default_factory=dict)
    manifest: dict | None = None


@dataclass
class WeatherSeries:
    """Hourly metocean at the operation's reference point(s). Columns at least: t (s), hs_m, wind_mps.
    Optional: tp_s, dir_deg, current_mps. `source` names the dataset and year, e.g. "NORA3 2011"."""
    df: pd.DataFrame
    source: str
    year: int | None = None


@dataclass
class SimResult:
    """What every engine returns. traj/agents follow offsim.contract; kpis are plain floats."""
    traj: pd.DataFrame
    agents: pd.DataFrame
    events: pd.DataFrame
    kpis: dict[str, float]
    engine: str
    seed: int
    weather: str | None = None
    meta: dict = field(default_factory=dict)


class Solver(Protocol):
    name: str
    classes: set[str]                   # problem classes this solver handles

    def solve(self, problem: Problem, seconds: float = 2.0, seed: int = 1) -> Plan: ...


class Engine(Protocol):
    name: str
    classes: set[str]                   # problem classes this engine can simulate
    needs_weather: bool

    def simulate(self, problem: Problem, plan: Plan, world: World,
                 weather: WeatherSeries | None = None, seed: int = 0) -> SimResult: ...


# --- registries: tools register themselves on import; the pipeline looks them up by name ---------------
_SOLVERS: dict[str, Callable[[], Solver]] = {}
_ENGINES: dict[str, Callable[[], Engine]] = {}


def register_solver(name: str):
    def deco(factory):
        _SOLVERS[name] = factory
        return factory
    return deco


def register_engine(name: str):
    def deco(factory):
        _ENGINES[name] = factory
        return factory
    return deco


# module that registers each name; imported lazily so a missing optional dependency only breaks its own tool
SOLVER_MODULES = {"pyvrp": "offsim.solve.pyvrp_solver", "pyomo": "offsim.solve.pyomo_solver",
                  "ampl": "offsim.solve.ampl_adapter"}
ENGINE_MODULES = {"replay": "offsim.engines.replay_engine", "openclsim": "offsim.engines.openclsim_adapter",
                  "wombat": "offsim.engines.wombat_adapter", "orbit": "offsim.engines.orbit_adapter",
                  "road": "offsim.engines.road_engine", "gtfs": "offsim.engines.gtfs_engine"}


def _load(name, registry, modules, kind):
    if name not in registry:
        if name not in modules:
            raise KeyError(f"unknown {kind} {name!r}; known: {sorted(modules)}")
        import importlib
        importlib.import_module(modules[name])
    return registry[name]()


def get_solver(name: str) -> Solver:
    return _load(name, _SOLVERS, SOLVER_MODULES, "solver")


def get_engine(name: str) -> Engine:
    return _load(name, _ENGINES, ENGINE_MODULES, "engine")


def available() -> dict[str, dict[str, str]]:
    """{'solvers': {name: 'ok'|error}, 'engines': {...}}: what imports in this environment."""
    out = {}
    for kind, mods, get in (("solvers", SOLVER_MODULES, get_solver), ("engines", ENGINE_MODULES, get_engine)):
        out[kind] = {}
        for n in mods:
            try:
                get(n)
                out[kind][n] = "ok"
            except Exception as e:      # noqa: BLE001 - report, don't crash, on optional tools
                out[kind][n] = f"{type(e).__name__}: {e}"[:120]
    return out
