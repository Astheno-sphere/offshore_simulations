"""Timetable replay: Entur GTFS trips (bus, ferry, tram, rail) as contract trajectories (offsim.transit.gtfs).

Scenario side: `problem.extra["gtfs"]` = {
    "dir": path to a GTFS folder (as written by `offsim.transit.gtfs.clip` / `fetch_world --gtfs`),
    "date": "YYYY-MM-DD" | "YYYYMMDD",
    "t0", "t1": window in seconds on the service-day clock or "HH:MM:SS" (24+ hours allowed),
    "route_types": optional list of route_type codes or classes ("bus", "ferry", "rail", "tram"),
    "sample_s": optional trajectory sampling step, default 30 }.
`problem.cls` must be {"TRANSIT-REPLAY"}.

Mapping
- Plan: empty. The published timetable *is* the plan; a non-empty Plan.routes raises `Unsupported` (this engine cannot
  re-route or re-time trips). `problem.nodes/fleet/dist_m` are ignored.
- Agents: one per trip (agent_id = trip_id; "~prev" suffix for previous-day trips running past midnight), cls
  bus|ferry|rail|tram, domain land (sea for ferries), vmax = 1.1 x observed speed. States: drive / sail, wait (dwell, terminus).
- Events: one "dwell" event per stop with arrival != departure (node = stop_id).
- KPIs: trips, vehicle_km, peak_vehicles, mean_headway_s (mean gap between trip starts, whole network), plus
  distance_km = vehicle_km, makespan_s, wait_s (contract-style) and weather_wait_s = 0.
- meta: gtfs (the request), manifest (clip manifest incl. licence), dropped/repaired trip counts.

No weather (`needs_weather = False`): a WeatherSeries is accepted and ignored, noted in meta. World is not used; pass
`World.land` to `offsim.contract.validate` to check ferry legs against land. Deterministic; `seed` unused.
"""
from __future__ import annotations

from offsim.contract import kpis as contract_kpis
from offsim.engines.base import Plan, Problem, SimResult, Unsupported, WeatherSeries, World, register_engine
from offsim.transit import gtfs


def _seconds(v, name: str) -> float:
    if isinstance(v, str):
        return gtfs.parse_time(v)
    if v is None:
        raise Unsupported(f"problem.extra['gtfs'][{name!r}] is missing")
    return float(v)


@register_engine("gtfs")
class GtfsEngine:
    name = "gtfs"
    classes = {"TRANSIT-REPLAY"}
    needs_weather = False

    def simulate(self, problem: Problem, plan: Plan, world: World,
                 weather: WeatherSeries | None = None, seed: int = 0) -> SimResult:
        extra_cls = set(problem.cls) - self.classes
        if extra_cls:
            raise Unsupported(f"gtfs engine handles {sorted(self.classes)}; problem also needs {sorted(extra_cls)}")
        if plan is not None and plan.routes:
            raise Unsupported("gtfs engine replays the published timetable; Plan.routes must be empty")
        spec = problem.extra.get("gtfs")
        if not isinstance(spec, dict):
            raise Unsupported("problem.extra['gtfs'] (dict with dir, date, t0, t1) is missing")
        for key in ("dir", "date"):
            if key not in spec:
                raise Unsupported(f"problem.extra['gtfs'] needs {key!r}")
        t0, t1 = _seconds(spec.get("t0", 0), "t0"), _seconds(spec.get("t1"), "t1")
        feed = gtfs.load(spec["dir"])
        traj, agents, events, stats = gtfs.build(feed, spec["date"], t0, t1, float(spec.get("sample_s", 30.0)),
                                                 spec.get("route_types"))
        k = gtfs.kpis(traj, agents)
        flat = {"trips": k["trips"], "vehicle_km": k["vehicle_km"], "peak_vehicles": k["peak_vehicles"],
                "mean_headway_s": k["mean_headway_s"], "weather_wait_s": 0.0}
        if len(traj):
            c = contract_kpis(traj)
            flat.update(distance_km=c["distance_km"], makespan_s=c["makespan_s"], wait_s=c["wait_s"])
        else:
            flat.update(distance_km=0.0, makespan_s=0.0, wait_s=0.0)
        meta = {"deterministic": True, "gtfs": {k_: spec[k_] for k_ in spec}, "manifest": feed.manifest,
                "dropped": stats}
        if weather is not None:
            meta["weather_note"] = (f"weather series {weather.source!r} ignored: the gtfs engine models no weather; "
                                    "no weather effect is applied")
        return SimResult(traj=traj, agents=agents, events=events, kpis=flat, engine=self.name, seed=seed,
                         weather=None, meta=meta)
