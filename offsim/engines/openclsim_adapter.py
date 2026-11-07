"""OpenCLSim (TU Delft / Deltares / Van Oord, MIT) behind the Engine protocol: Problem + Plan + World -> SimResult.

Mapping (Problem/Plan -> OpenCLSim objects)
- depot (node 0)            -> `Site` (Locatable, no stock: it is only the start and end of every route).
- each served stop          -> `Site` whose container has capacity = demand x number of visits (each visit unloads
                               `demand[node]`, exactly as the replay engine does) and level 0; "full" = delivered.
                               Site resource capacity = `problem.extra["berths"][node]` (default: number of
                               vessels, i.e. no queue unless berths are given).
- each route in Plan.routes -> one vessel (`ContainerDependentMovable` + `Processor` + `HasResource`),
                               container capacity = fleet capacity, level = route total demand, speed constant
                               (`compute_v` returns the fleet speed). Empty routes create no vessel.
- route [s1..sk]            -> `SequentialActivity`: MoveActivity(depot->s1), ShiftAmountActivity(unload s1:
                               vessel -> site, amount = demand, duration = service_s), MoveActivity(s1->s2),
                               ..., MoveActivity(sk->depot). A stop with demand 0 uses BasicActivity(service_s).
- Problem.service_s         -> the shift `duration` (fixed, independent of amount). The replay engine uses the
                               same convention (fixed service time per stop), so there is NO service-time
                               convention difference to reconcile; OpenCLSim's loading/unloading rate
                               functions are deliberately not used.
- sailing time              -> without World.legs: OpenCLSim's own WGS84 geodesic distance / speed. With
                               World.legs: the sea-lane path length (haversine, as the contract measures) / speed
                               is passed as `MoveActivity(duration=...)`, so vessels follow lanes. A leg missing
                               from `legs` raises Unsupported. The two conventions differ by < 0.5 %
                               (geodesic vs sphere), the only expected disagreement with the replay engine.
Weather
- `problem.extra["limits"] = {"hs_m": L}` (one column of WeatherSeries.df) and a WeatherSeries -> every unload
  gets `HasWeatherPluginActivity` with `WeatherCriterion(maximum=L, window_length=service_s)`: the unload starts
  only when the series stays <= L for service_s seconds from the start (each sample is a step value from its
  timestamp, OpenCLSim's convention). The wait is logged by OpenCLSim as "waiting on weather" and becomes
  contract state `wait`; its total is KPI `weather_wait_s`. Sailing is not weather-limited.
- Series time t (s) is scenario time; `problem.extra["weather_t0_s"]` (default 0) shifts the start inside it.
- Limits without a series, or a series without limits, are ignored with a note in `meta["weather_note"]`.
- Raises Unsupported: more than one limit, unknown column, a series that never allows an unload window, an
  unload that would start beyond the series (the plugin silently releases those; we verify every start
  against the plugin's own windows afterwards), time windows (`problem.tw`), mixed agent domains. A node
  visited k times is delivered k times (no split-delivery logic).
Output
- OpenCLSim activity logs (START/STOP/WAIT_START/WAIT_STOP) -> contract rows (agent_id, t, lon, lat, state,
  load). Moving legs are sampled every 500 m along the leg geometry (straight or lane) at constant speed;
  states: sail/fly/drive while moving, `wait` (berth queue, then weather), `unload`, `idle` at the depot.
- KPIs: distance_km, makespan_s, wait_s (all `wait` rows), weather_wait_s (OpenCLSim weather log only).
  Fuel/CO2 are not reported. Deterministic: `seed` is unused.
"""
from __future__ import annotations

import datetime as _dt
import warnings
from importlib import metadata

import numpy as np
import pandas as pd
import shapely.geometry as sg
import simpy

import openclsim.core as core
import openclsim.model as model
from openclsim.plugins import HasWeatherPluginActivity, WeatherCriterion
from openclsim.plugins.weather import WeatherPluginActivity

from offsim.contract import haversine_m, kpis
from offsim.engines.base import Plan, Problem, SimResult, Unsupported, WeatherSeries, World, register_engine
from offsim.engines.replay_engine import check_plan, fleet_agents, move_state

_EPOCH = _dt.datetime(1970, 1, 1)
_WX_LABEL = "waiting on weather"
SAMPLE_M = 500.0
_EPS = 1e-6


class _Site(core.Identifiable, core.Log, core.Locatable, core.HasContainer, core.HasResource):
    """Depot or stop: a place with an optional container and a berth resource."""


class _Vessel(core.Identifiable, core.ContainerDependentMovable, core.Processor,
              core.LoadingFunction, core.UnloadingFunction, core.HasResource, core.Log):
    """One route's vessel: moves, carries a container, unloads itself into a site."""


class _Unload(HasWeatherPluginActivity, model.ShiftAmountActivity):
    """Unload shift, weather-gated when metocean_criteria is given."""


class _Service(HasWeatherPluginActivity, model.BasicActivity):
    """Zero-demand stop: service time only, weather-gated like _Unload."""


def _ts(stamp: _dt.datetime) -> float:
    return (stamp - _EPOCH).total_seconds()


def _leg_points(nodes, a, b, legs):
    if legs and (a, b) in legs:
        return [tuple(p) for p in legs[(a, b)]], True
    if legs and (b, a) in legs:
        return [tuple(p) for p in reversed(legs[(b, a)])], True
    return [tuple(nodes[a]), tuple(nodes[b])], False


def _path_m(pts) -> float:
    return float(sum(haversine_m(x0, y0, x1, y1) for (x0, y0), (x1, y1) in zip(pts, pts[1:])))


def _windows(df: pd.DataFrame, col: str, limit: float, d: float):
    crit = WeatherCriterion(name=f"{col}<={limit}", condition=col, window_length=d, maximum=limit)
    return WeatherPluginActivity(weather_criteria=crit, metocean_df=df).process_data(crit)["windows"], crit


@register_engine("openclsim")
class OpenCLSimEngine:
    name = "openclsim"
    classes = {"CVRP"}
    needs_weather = False

    def simulate(self, problem: Problem, plan: Plan, world: World,
                 weather: WeatherSeries | None = None, seed: int = 0) -> SimResult:
        extra_cls = set(problem.cls) - self.classes
        if extra_cls:
            raise Unsupported(f"openclsim engine handles {sorted(self.classes)}; problem also needs {sorted(extra_cls)}")
        if problem.tw:
            raise Unsupported("openclsim adapter: time windows are not mapped")
        check_plan(problem, plan, world)
        agents = fleet_agents(problem, plan)
        mstate = move_state(agents)
        spec = agents.set_index("agent_id")
        nodes = problem.nodes
        visited = [s for r in plan.routes.values() for s in r]
        visits = {n: visited.count(n) for n in set(visited)}
        demand = {int(k): float(v) for k, v in problem.demand.items()}
        service = {int(k): float(v) for k, v in problem.service_s.items()}
        berths = {int(n): int(c) for n, c in (problem.extra.get("berths") or {}).items()}
        meta: dict = {"openclsim_version": metadata.version("openclsim"), "deterministic": True}

        # ---- weather -> one criterion + step-function table in scenario time -----------------------------
        limits = problem.extra.get("limits") or {}
        wx_df = col = limit = None
        if limits and weather is not None:
            if len(limits) != 1:
                raise Unsupported(f"openclsim adapter maps one weather limit, got {sorted(limits)}")
            (col, limit), = limits.items()
            limit = float(limit)
            if col not in weather.df.columns or "t" not in weather.df.columns:
                raise Unsupported(f"weather series lacks column {col!r} or 't' (has {list(weather.df.columns)})")
            t0 = float(problem.extra.get("weather_t0_s", 0.0))
            wx_df = (weather.df[["t", col]].astype(float).sort_values("t").reset_index(drop=True)
                     .rename(columns={"t": "ts"}))
            wx_df["ts"] = wx_df["ts"] - t0
            if wx_df[col].min() > limit:
                raise Unsupported(f"{col} > {limit} for the whole series: no unload window exists")
            if wx_df[col].max() <= limit:
                meta["weather_note"] = f"{col} never exceeds {limit} in {weather.source!r}: no weather wait possible"
                wx_df = None
            else:
                meta["weather_limit"] = {col: limit}
        elif limits:
            meta["weather_note"] = f"limits {limits} ignored: no WeatherSeries given"
        elif weather is not None:
            meta["weather_note"] = f"weather series {weather.source!r} not used: problem.extra has no 'limits'"
        windows_by_d: dict[float, list] = {}

        def criterion_for(d: float):
            if wx_df is None:
                return None
            if d not in windows_by_d:
                try:
                    windows_by_d[d], crit = _windows(wx_df, col, limit, d)
                except IndexError as e:      # plugin cannot build windows from this series
                    raise Unsupported(f"weather windows cannot be built from this series: {e}") from e
                if not windows_by_d[d]:
                    raise Unsupported(f"no {col} <= {limit} window of {d:.0f} s exists in the series")
                windows_by_d[("crit", d)] = crit
            return windows_by_d[("crit", d)]

        # ---- build the OpenCLSim model -----------------------------------------------------------------
        env = simpy.Environment()
        registry: dict = {}
        n_routes = max(1, sum(1 for r in plan.routes.values() if r))
        site = {0: _Site(env=env, name="depot", geometry=sg.Point(nodes[0]), capacity=0, nr_resources=n_routes)}
        for n in sorted(set(visited)):
            q = demand.get(n, 0.0)
            site[n] = _Site(env=env, name=f"stop-{n}", geometry=sg.Point(nodes[n]), capacity=q * visits[n], level=0.0,
                            nr_resources=berths.get(n, n_routes))
        plans = {}          # aid -> (vessel, [step dicts], sequence)
        for aid, route in plan.routes.items():
            if not route:
                continue
            v, cap = float(spec.loc[aid, "speed_mps"]), float(spec.loc[aid, "capacity"])
            total = float(sum(demand.get(s, 0.0) for s in route))
            if cap <= 0:
                raise Unsupported(f"{aid}: capacity must be > 0 for an OpenCLSim container")
            if total > cap + _EPS:
                raise ValueError(f"{aid}: route load {total} exceeds capacity {cap}")
            vessel = _Vessel(env=env, name=aid, geometry=sg.Point(nodes[0]), capacity=cap, level=total,
                             compute_v=lambda _frac, v=v: v, loading_rate=1.0, unloading_rate=1.0, nr_resources=1)
            steps, acts = [], []
            path = [0] + list(route) + [0]
            for i, (a, b) in enumerate(zip(path, path[1:])):
                pts, lane = _leg_points(nodes, a, b, world.legs)
                dur = _path_m(pts) / v if lane else None
                mv = model.MoveActivity(env=env, registry=registry, name=f"{aid} sail {i}: {a}->{b}", mover=vessel,
                                        destination=site[b], duration=dur)
                steps.append({"kind": "move", "act": mv, "pts": pts, "a": a, "b": b})
                acts.append(mv)
                if b == 0:
                    continue
                d, q = service.get(b, 0.0), demand.get(b, 0.0)
                crit = criterion_for(d)
                kw = dict(metocean_criteria=crit, metocean_df=wx_df if crit is not None else None,
                          env=env, registry=registry, name=f"{aid} serve {i}: {b}")
                if q > 0:
                    act = _Unload(processor=vessel, origin=vessel, destination=site[b], duration=d, amount=q, **kw)
                else:
                    act = _Service(duration=d, **kw)
                steps.append({"kind": "serve", "act": act, "node": b, "q": q, "d": d, "weather": crit is not None})
                acts.append(act)
            seq = model.SequentialActivity(env=env, registry=registry, name=f"{aid} route", sub_processes=acts)
            plans[aid] = (vessel, steps, seq)

        with warnings.catch_warnings():       # OpenCLSim stamps logs with datetime.utcfromtimestamp
            warnings.simplefilter("ignore", DeprecationWarning)
            if plans:
                model.register_processes([p[2] for p in plans.values()])
                env.run()
            rows, events, per_agent = self._rows(plan, plans, nodes, mstate, spec, world, windows_by_d)

        # ---- consistency: everything delivered, vessels empty -------------------------------------------
        for n in sorted(set(visited)):
            want = demand.get(n, 0.0) * visits[n]
            if want > 0 and abs(site[n].container.get_level() - want) > 1e-6:
                raise RuntimeError(f"stop {n}: delivered {site[n].container.get_level()} of {want}")
        for aid, (vessel, _, _) in plans.items():
            if abs(vessel.container.get_level()) > 1e-6:
                raise RuntimeError(f"{aid}: {vessel.container.get_level()} units still on board after the route")

        traj = pd.DataFrame(rows, columns=["agent_id", "t", "lon", "lat", "alt_m", "state", "load"])
        traj = traj.sort_values(["agent_id", "t"], kind="stable").reset_index(drop=True)
        ev = pd.DataFrame(events, columns=["agent_id", "node", "event", "t", "duration_s"])
        k = kpis(traj)
        wx_wait = float(sum(a["weather_wait_s"] for a in per_agent.values()))
        flat = {"distance_km": k["distance_km"], "makespan_s": k["makespan_s"], "wait_s": k["wait_s"],
                "weather_wait_s": wx_wait}
        meta["agents"] = k["agents"]
        meta["wait_breakdown_s"] = {"weather": wx_wait, "queue": float(sum(a["queue_wait_s"] for a in per_agent.values()))}
        return SimResult(traj=traj, agents=agents, events=ev, kpis=flat, engine=self.name, seed=seed,
                         weather=weather.source if wx_df is not None else None, meta=meta)

    # ---- OpenCLSim logs -> contract rows -------------------------------------------------------------------
    @staticmethod
    def _rows(plan, plans, nodes, mstate, spec, world, windows_by_d):
        rows, events, per_agent = [], [], {}

        for aid, route in plan.routes.items():
            depot = nodes[0]
            load = float(sum(s["q"] for s in plans[aid][1] if s["kind"] == "serve")) if aid in plans else 0.0
            last_t = [0.0]

            def emit(t, lon, lat, state, ld):
                t = max(float(t), last_t[0])           # microsecond log stamps: never step backwards
                last_t[0] = t
                rows.append((aid, t, float(lon), float(lat), 0.0, state, float(ld)))

            emit(0.0, *depot, "idle", load)
            stats = {"weather_wait_s": 0.0, "queue_wait_s": 0.0}
            per_agent[aid] = stats
            if aid not in plans:
                continue
            _, steps, _ = plans[aid]
            prev_stop = 0.0
            for st in steps:
                lg = [(_ts(e["Timestamp"]), e["ActivityState"], e["ActivityLabel"]) for e in st["act"].logbook]
                starts = [t for t, s, _ in lg if s == "START"]
                stops = [t for t, s, _ in lg if s == "STOP"]
                if not starts or not stops:
                    raise RuntimeError(f"activity {st['act'].name!r} did not finish (log: {[s for _, s, _ in lg]})")
                if st["kind"] == "move":
                    t0, t1 = starts[0], stops[-1]
                    pts = st["pts"]
                    seg = [float(haversine_m(x0, y0, x1, y1)) for (x0, y0), (x1, y1) in zip(pts, pts[1:])]
                    total = sum(seg)
                    emit(t0, *pts[0], mstate, load)
                    cum = 0.0
                    for (x0, y0), (x1, y1), d in zip(pts, pts[1:], seg):
                        n = max(1, int(np.ceil(d / SAMPLE_M)))
                        for j in range(1, n + 1):
                            f = j / n
                            frac = (cum + d * f) / total if total > 0 else 1.0
                            emit(t0 + (t1 - t0) * frac, x0 + (x1 - x0) * f, y0 + (y1 - y0) * f, mstate, load)
                        cum += d
                    prev_stop = t1
                    if st["b"] == 0:
                        emit(t1, *nodes[0], "idle", load)
                    continue
                here = nodes[st["node"]]
                first = min(t for t, _, _ in lg)
                if first - prev_stop > _EPS:               # berth queue before the activity could begin
                    emit(prev_stop, *here, "wait", load)
                    events.append((aid, st["node"], "queue", prev_stop, first - prev_stop))
                    stats["queue_wait_s"] += first - prev_stop
                ws = [t for t, s, lab in lg if s == "WAIT_START" and lab.get("ref") == _WX_LABEL]
                we = [t for t, s, lab in lg if s == "WAIT_STOP" and lab.get("ref") == _WX_LABEL]
                for a0, a1 in zip(ws, we):
                    emit(a0, *here, "wait", load)
                    events.append((aid, st["node"], "weather_wait", a0, a1 - a0))
                    stats["weather_wait_s"] += a1 - a0
                s0 = starts[0]
                if st["weather"]:                          # verify against the plugin's own windows
                    win = windows_by_d[st["d"]]
                    if not any(w0 - _EPS <= s0 <= w1 + _EPS for w0, w1 in win):
                        raise Unsupported(f"{aid}: unload at t={s0:.0f} s starts outside every weather window "
                                          "(operation runs beyond the weather series); extend the series")
                emit(s0, *here, "unload", load)
                load -= st["q"]
        return rows, events, per_agent
