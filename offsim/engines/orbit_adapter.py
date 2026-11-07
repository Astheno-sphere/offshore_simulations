"""ORBIT adapter: offshore-wind installation (NREL ORBIT 1.3.x) behind the `Engine` interface.

Engine name  `orbit`, classes {"WIND-INST"}, needs_weather True.

What this engine means
    ORBIT is a discrete-event model of installation phases (monopile, jacket, turbine, offshore substation, cables,
    scour protection, mooring, ...) with a port, WTIV / feeder / support vessels, and wind/wave limits per task.
    The vessels follow ORBIT's own logic, so **the solver Plan is trivial** (`routes` empty); a non-empty Plan is
    rejected with `Unsupported` rather than ignored.

Scenario side
    problem.extra["orbit"]      an ORBIT `ProjectManager` config dict, exactly as ORBIT documents it (bundled example
                                pattern: {"wtiv": "example_wtiv", "feeder": "example_feeder", "num_feeders": 2,
                                "site": {"depth": .., "distance": ..}, "plant": {"num_turbines": ..},
                                "port": {...}, "turbine": "12MW_generic", "install_phases": {...}}).
                                String items are ORBIT library names; those found in ORBIT's bundled library are
                                reported in `meta["sources"]` as "ORBIT default" (so a scenario can say which values
                                are ORBIT defaults and which carry a paper source).
    problem.extra["orbit_geo"]  {"port": {lon, lat}, "site": {lon, lat}, "route_factor": 1.0, "sample_s": 900}
                                (fallback: problem.nodes[0] = port, nodes[1] = site). If `site.distance` is absent in
                                the ORBIT config it is set to great-circle(port, site) x route_factor (assumption);
                                if present it must be >= the great-circle distance (else Unsupported), so sailing speeds
                                stay physical. Routing on sea lanes (world.legs) is a later step.
    install_phases (dict form) start values: a full "MM/DD/YYYY", "MM/DD" (year taken from the weather), "start"
                                (first weather timestamp) or an int hour index. ORBIT needs the date to exist in the
                                weather, so a year-agnostic scenario uses "MM/DD" / "start".
    The `WeatherSeries` must be long enough for the installation; if ORBIT runs out of weather this raises Unsupported
    ("weather series too short"), never a truncated result.

Weather: `WeatherSeries.df` columns t (s), hs_m, wind_mps -> ORBIT DataFrame datetime / waveheight / windspeed
    (the columns ORBIT's `max_waveheight` / `max_windspeed` constraints read). Hourly, no NaN (else Unsupported);
    the wall-clock origin is Jan 1 of `weather.year` (2001 if unknown, reported in meta).

Results
    kpis: install_days (span from earliest phase start to latest phase end, parallel phases not double counted),
    install_days_sum (ORBIT `installation_time`, sum of phase times), installation_capex_usd (ORBIT
    `installation_capex`), weather_wait_s (sum over vessels of ORBIT "Delay" actions, the weather-window waits),
    queue_wait_s (resource waits: Queue, Wait for .., "Delay: ..."), vessel_hours (non-idle vessel time), plus engine-common
    distance_km, makespan_s, wait_s. fuel_t / co2_t omitted (not mapped).

Trajectory (offsim.contract): one agent per vessel (prefixed `<phase>:` when several install phases run).
    ORBIT logs the *end* time of each action; start = time - duration. `Mobilize` advances no clock (cost only) and is
    drawn as idle at the port (its hours are in meta). A leg is port <-> site; a "Transit" action may be split by
    weather delays, so legs are tracked by accumulated transit hours against site.distance / transit_speed.
    States: Transit -> `sail` (great-circle interpolation port/site); weather "Delay" -> `wait` (where the vessel is);
    Queue / Wait for / "Delay: ..." -> `idle`; any other action -> `load` at the port, `dp` at the site.
    Phases mapped to a trajectory (port <-> site transits only): TurbineInstallation, MonopileInstallation,
    JacketInstallation, OffshoreSubstationInstallation. Others (cable, scour, tow, mooring) raise `Unsupported`.
"""
from __future__ import annotations

import contextlib
import io
import warnings
from copy import deepcopy

import numpy as np
import pandas as pd

from offsim import contract
from offsim.engines.base import (Plan, Problem, SimResult, Unsupported, WeatherSeries, World,
                                 register_engine)
from offsim.engines.wombat_adapter import DEFAULT_YEAR, gc_interp, _dist_m

SUPPORTED_PHASES = {
    "TurbineInstallation": ("wtiv", "WTIV"),
    "MonopileInstallation": ("wtiv", "WTIV"),
    "JacketInstallation": ("wtiv", "WTIV"),
    "OffshoreSubstationInstallation": ("oss_install_vessel", "Heavy Lift Vessel"),
}
_RESOURCE_WAIT = ("Queue", "Wait for", "Delay:")
_EPS = 1e-6


@register_engine("orbit")
class OrbitEngine:
    name = "orbit"
    classes = {"WIND-INST"}
    needs_weather = True

    # -- public ---------------------------------------------------------------------------------------
    def simulate(self, problem: Problem, plan: Plan, world: World,
                 weather: WeatherSeries | None = None, seed: int = 0) -> SimResult:
        try:
            import ORBIT
            from ORBIT import ProjectManager
            from ORBIT.core.library import default_library
        except ImportError as e:                        # pragma: no cover
            raise Unsupported(f"orbit-nrel is not installed: {e}") from e
        if not (problem.cls & self.classes):
            raise Unsupported(f"orbit handles {sorted(self.classes)}, got {sorted(problem.cls)}")
        if plan is not None and any(plan.routes.values()):
            raise Unsupported("orbit simulates installation itself; pass a Plan with empty routes")
        if weather is None:
            raise Unsupported("orbit needs a WeatherSeries (hourly hs_m, wind_mps)")
        cfg = problem.extra.get("orbit")
        if not isinstance(cfg, dict):
            raise Unsupported("problem.extra['orbit'] (ProjectManager config dict) is missing")
        geo = dict(problem.extra.get("orbit_geo") or {})
        port, site, dist_note = self._geometry(problem, geo)
        route_factor = float(geo.get("route_factor", 1.0))
        if route_factor < 1.0:
            raise Unsupported("orbit: route_factor must be >= 1")
        sample_s = float(geo.get("sample_s", 900.0))

        cfg = deepcopy(cfg)
        phases = cfg.get("install_phases")
        names = list(phases) if isinstance(phases, (list, set, tuple, dict)) else [phases]
        if not phases:
            raise Unsupported("orbit: config has no install_phases")
        bad = [p for p in names if p not in SUPPORTED_PHASES]
        if bad:
            raise Unsupported(f"orbit: no trajectory mapping for phases {bad}; mapped: {sorted(SUPPORTED_PHASES)}")

        geo_m = _dist_m(port, site) / 1000.0
        site_cfg = cfg.setdefault("site", {})
        if site_cfg.get("distance") is None:
            site_cfg["distance"] = geo_m * route_factor
            dist_note = f"site.distance = great-circle {geo_m:.2f} km x route_factor {route_factor} (assumption)"
        elif float(site_cfg["distance"]) < geo_m * (1 - 1e-3):
            raise Unsupported(f"orbit: site.distance {site_cfg['distance']} km is shorter than the port-site "
                              f"great-circle distance {geo_m:.2f} km")
        else:
            dist_note = f"site.distance {site_cfg['distance']} km from config (>= great-circle {geo_m:.2f} km)"

        wdf, t0, year, year_note = self._weather(weather)
        cfg = self._resolve_starts(cfg, wdf)
        sources = self._sources(cfg, default_library)

        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out), warnings.catch_warnings():
                warnings.simplefilter("ignore")
                pm = ProjectManager(cfg, weather=wdf)
                pm.run()
        except Exception as e:                           # noqa: BLE001
            tname = type(e).__name__
            if tname in ("StateExhausted", "WeatherProfileError", "WindowNotFound"):
                raise Unsupported(f"orbit: weather series too short or window never found ({tname}: {e})") from e
            raise

        starts = pm.phase_starts
        zero = min(starts.values()) if starts else 0
        speeds = self._vessel_speeds(pm, list(starts))
        traj, agents, acc = self._to_contract(pm, zero, speeds, port, site, float(site_cfg["distance"]), t0, sample_s)
        base = contract.kpis(traj)

        spans = [(starts[p], starts[p] + pm.phase_times[p]) for p in starts if p in pm.phase_times]
        install_h = (max(e for _, e in spans) - min(s for s, _ in spans)) if spans else 0.0
        k = {"distance_km": base["distance_km"], "makespan_s": base["makespan_s"], "wait_s": base["wait_s"],
             "install_days": install_h / 24.0,
             "install_days_sum": float(pm.installation_time) / 24.0,
             "installation_capex_usd": float(pm.installation_capex),
             "weather_wait_s": acc["weather_wait_h"] * 3600.0,
             "queue_wait_s": acc["queue_wait_h"] * 3600.0,
             "vessel_hours": acc["vessel_h"]}
        k = {a: float(b) for a, b in k.items()}
        events = pd.DataFrame(acc["events"], columns=["t", "agent_id", "phase", "action", "duration_s", "cost_usd"])
        meta = {"orbit_version": getattr(ORBIT, "__version__", "?"), "sources": sources, "site_distance": dist_note,
                "weather_origin": year_note, "routing": "great-circle straight legs (not sea lanes; later step)",
                "mobilization_h": acc["mobilize"], "phase_starts_h": dict(starts),
                "phase_times_h": {p: float(v) for p, v in pm.phase_times.items()},
                "process_times": "ORBIT default (ORBIT/core/defaults/process_times.yaml) unless overridden in config",
                "notes": acc["notes"]}
        return SimResult(traj=traj, agents=agents, events=events, kpis=k, engine=self.name, seed=seed,
                         weather=weather.source, meta=meta)

    # -- inputs -----------------------------------------------------------------------------------------
    @staticmethod
    def _geometry(problem: Problem, geo: dict):
        port = geo.get("port") or ({"lon": problem.nodes[0][0], "lat": problem.nodes[0][1]} if problem.nodes else None)
        site = geo.get("site") or ({"lon": problem.nodes[1][0], "lat": problem.nodes[1][1]}
                                   if len(problem.nodes) > 1 else None)
        if not port or not site:
            raise Unsupported("orbit: extra['orbit_geo'] needs port and site {lon, lat}")
        return (float(port["lon"]), float(port["lat"])), (float(site["lon"]), float(site["lat"])), ""

    @staticmethod
    def _weather(weather: WeatherSeries):
        df = weather.df
        for c in ("t", "hs_m", "wind_mps"):
            if c not in df.columns:
                raise Unsupported(f"orbit: weather column {c!r} missing")
        df = df.sort_values("t").reset_index(drop=True)
        if len(df) < 24:
            raise Unsupported("orbit: need at least 24 hourly weather rows")
        if df[["hs_m", "wind_mps"]].isna().any().any():
            raise Unsupported("orbit: NaN in hs_m / wind_mps")
        if not np.allclose(np.diff(df["t"].to_numpy()), 3600.0):
            raise Unsupported("orbit: weather must be strictly hourly (t step 3600 s); resample upstream")
        year = int(weather.year) if weather.year else DEFAULT_YEAR
        note = f"Jan 1 {year}" + ("" if weather.year else " (weather.year unknown, default)")
        t0 = float(df["t"].iloc[0])
        origin = pd.Timestamp(year=year, month=1, day=1) + pd.to_timedelta(t0, unit="s")
        wdf = pd.DataFrame({"datetime": origin + pd.to_timedelta(df["t"] - t0, unit="s"),
                            "windspeed": df["wind_mps"].astype(float).to_numpy(),
                            "waveheight": df["hs_m"].astype(float).to_numpy()})
        return wdf, t0, year, note

    @staticmethod
    def _resolve_starts(cfg: dict, wdf: pd.DataFrame) -> dict:
        ph = cfg.get("install_phases")
        if not isinstance(ph, dict):
            return cfg
        first = wdf["datetime"].iloc[0]
        out = {}
        for name, v in ph.items():
            if isinstance(v, str):
                s = v.strip()
                if s.lower() == "start":
                    v = first.strftime("%m/%d/%Y")
                    if first != first.normalize():
                        raise Unsupported("orbit: weather must start at 00:00 for 'start'")
                elif len(s) == 5 and s[2] == "/":
                    v = f"{s}/{first.year}"
            out[name] = v
        cfg["install_phases"] = out
        return cfg

    @staticmethod
    def _sources(cfg: dict, default_library) -> dict:
        found = {}
        for key, val in cfg.items():
            if isinstance(val, str):
                for sub in ("vessels", "turbines", "cables", "substructures", "ports"):
                    if (default_library / sub / f"{val}.yaml").is_file():
                        found[key] = f"ORBIT default (library/{sub}/{val}.yaml)"
                        break
        return found

    @staticmethod
    def _vessel_speeds(pm, phases) -> dict[str, float]:
        """{agent_id: transit_speed km/h} from the resolved vessel specs of each phase."""
        out = {}
        multi = len(phases) > 1
        for ph in phases:
            key, default = SUPPORTED_PHASES[ph]
            conf = pm._phases[ph].config
            vspec = conf.get(key)
            if not isinstance(vspec, dict):
                raise Unsupported(f"orbit: vessel spec {key!r} of {ph} did not resolve to a dict")
            tag = f"{ph}:" if multi else ""
            out[tag + vspec.get("name", default)] = float(vspec["transport_specs"]["transit_speed"])
            if conf.get("num_feeders") and conf.get("feeder"):
                fs = float(conf["feeder"]["transport_specs"]["transit_speed"])
                for n in range(int(conf["num_feeders"])):
                    out[f"{tag}Feeder {n}"] = fs
        return out

    # -- outputs ------------------------------------------------------------------------------------------
    @staticmethod
    def _to_contract(pm, zero, speeds, port, site, dist_km, t0, sample_s):
        multi = len(pm.phase_starts) > 1
        acts = pm.actions
        by_agent: dict[str, list[dict]] = {}
        for a in acts:
            if a["phase"] not in SUPPORTED_PHASES:
                continue
            aid = f"{a['phase']}:{a['agent']}" if multi else a["agent"]
            by_agent.setdefault(aid, []).append(a)
        unknown = sorted(set(by_agent) - set(speeds))
        if unknown:
            raise Unsupported(f"orbit: no transit speed for agents {unknown}")

        rows, evrows, notes = [], [], []
        weather_wait = queue_wait = vessel_h = mobilize_h = 0.0
        for aid, lst in by_agent.items():
            v_ms = speeds[aid] / 3.6
            leg_h = dist_km / speeds[aid]
            lst = sorted(lst, key=lambda a: a["time"] - a["duration"] if a["action"] != "Mobilize" else -1.0)
            loc = "port"
            prog = 0.0
            tl: list[tuple[float, tuple[float, float], str]] = []
            clock = None

            def pos_at(frac, here):
                a, b = (port, site) if here == "port" else (site, port)
                return gc_interp(a, b, min(max(frac, 0.0), 1.0))

            def put(t_h, p, st):
                tl.append((t0 + (zero + t_h) * 3600.0, p, st))

            for a in lst:
                act, dur = str(a["action"]), float(a["duration"])
                t_start_ev = zero if act == "Mobilize" else zero + a["time"] - dur      # logs carry end times
                evrows.append((t0 + t_start_ev * 3600.0, aid, a["phase"], act, dur * 3600.0,
                               float(a.get("cost", 0.0))))
                if act == "Mobilize":
                    mobilize_h += dur
                    continue
                end = float(a["time"])
                start = end - dur
                if clock is not None and start < clock - 1e-6:
                    notes.append(f"{aid}: {act} starts {clock - start:.3f} h before previous action ended; clamped")
                    start = clock
                if clock is not None and start > clock + 1e-6:
                    put(clock, pos_at(prog / leg_h, loc) if prog > _EPS else (port if loc == "port" else site), "idle")
                if act == "Transit":
                    f0 = prog / leg_h
                    f1 = (prog + dur) / leg_h
                    if f1 > 1.0 + 1e-4:
                        raise Unsupported(f"orbit: {aid} transit exceeds site.distance/speed (another distance used "
                                          f"in the phase?)")
                    put(start, pos_at(f0, loc), "sail")
                    n = int(dur * 3600.0 // sample_s)
                    for j in range(1, n + 1):
                        frac = j * sample_s / (dur * 3600.0)
                        if frac < 1.0 - 1e-9:
                            put(start + frac * dur, pos_at(f0 + (f1 - f0) * frac, loc), "sail")
                    prog += dur
                    vessel_h += dur
                    if prog >= leg_h * (1 - 1e-4):
                        loc = "site" if loc == "port" else "port"
                        prog = 0.0
                        put(end, port if loc == "port" else site, "idle")
                    else:
                        put(end, pos_at(prog / leg_h, loc), "idle")
                else:
                    here = pos_at(prog / leg_h, loc) if prog > _EPS else (port if loc == "port" else site)
                    if act == "Delay":
                        st = "wait"
                        weather_wait += dur
                    elif act.startswith(_RESOURCE_WAIT):
                        st = "idle"
                        queue_wait += dur
                    else:
                        st = "load" if loc == "port" else "dp"
                        vessel_h += dur
                    put(start, here, st)
                    put(end, here, "idle")
                clock = end
            if not tl:
                tl = [(t0 + zero * 3600.0, port, "idle")]
            df = pd.DataFrame(tl, columns=["t", "pos", "state"])
            df["lon"] = [p[0] for p in df["pos"]]
            df["lat"] = [p[1] for p in df["pos"]]
            df["agent_id"] = aid
            rows.append(df.drop(columns="pos"))
        traj = pd.concat(rows, ignore_index=True)
        traj["t"] = traj["t"].round(3)          # float noise between an action's end and the next one's start
        traj = traj.drop_duplicates(["agent_id", "t"], keep="last")
        traj = traj.sort_values(["agent_id", "t"], kind="stable").reset_index(drop=True)
        traj["alt_m"] = 0.0
        traj = traj[["agent_id", "t", "lon", "lat", "alt_m", "state"]]
        agents = pd.DataFrame([{
            "agent_id": aid, "cls": ("feeder" if "Feeder" in aid else "wtiv" if "WTIV" in aid else "vessel"),
            "vmax_mps": speeds[aid] / 3.6, "capacity": np.nan, "domain": "sea"} for aid in by_agent])
        return traj, agents, {"weather_wait_h": weather_wait, "queue_wait_h": queue_wait, "vessel_h": vessel_h,
                              "mobilize": mobilize_h, "events": evrows, "notes": notes}
