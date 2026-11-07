"""WOMBAT adapter: offshore-wind O&M (NREL WOMBAT 0.13.x) behind the `Engine` interface.

Engine name  `wombat`, classes {"WIND-OM"}, needs_weather True.

What this engine means
    WOMBAT is a discrete-event simulation of a wind farm's O&M: turbines fail (Weibull), scheduled maintenance
    comes due, repair requests queue, and service vessels (CTV, SOV, jack-up, cable vessel, ...) are dispatched
    by WOMBAT's own strategies ("scheduled", "requests", threshold, charter windows, shifts) under hourly
    wind/wave limits. **The solver Plan is therefore trivial** (`routes` empty, e.g. from a no-op solver):
    WOMBAT dispatches itself, so there is nothing for a solver to decide. A non-empty Plan is rejected with
    `Unsupported` rather than ignored.

Scenario side: `problem.extra["wombat"]`  (every value needs a source or `assumption: true` in scenario.yaml)

    layout:      [{id, lon, lat, string?, order?}, ...]   turbines; string/order default to one string 0..n-1
    port:        {lon, lat}                               O&M base (quay)
    substation:  {lon, lat, id?}                          optional; default = centroid of the turbines (assumption)
    library:     "DEFAULT" | "COREWIND" | "DINWOODIE" | "IEA_26" | "<path to a WOMBAT library dir>"
                 (default "DEFAULT" = WOMBAT's bundled COWER-2024 library; reported as "WOMBAT default library")
    turbine:     "<file.yaml in library/turbines>" | inline WOMBAT turbine dict      (default DEFAULT 12MW_osw_fixed)
    array_cable / export_cable / substation_file / fixed_costs:  file names in the library (inline dict allowed
                 for fixed_costs); DEFAULT library defaults are used only for library "DEFAULT"
    failure_rate_factor: x   multiplies every turbine failure rate (Weibull scale / x); a scenario knob, not a default
    vessels:     [ "ctv.yaml" | {file|inline, count?, overrides?: {...WOMBAT vessel keys...}} ]
    route_factor: >=1        sea-lane / straight-line ratio applied to the port distance (default 1.0, assumption)
    horizon_days: n          optional: truncate the weather to its first n days
    workday_start, workday_end, inflation_rate: WOMBAT project settings (defaults 7, 19, 0)
    sample_s:    int         spacing of interpolated positions on sailing legs (default 900 s)

Weather: `WeatherSeries.df` columns t (s), hs_m, wind_mps -> WOMBAT columns datetime, waveheight, windspeed.
    Hourly spacing is required (WOMBAT is hourly; anything else raises Unsupported, never resampled silently).
    NaN raises Unsupported (WOMBAT would silently fill zeros). The wall-clock origin is Jan 1 of `weather.year`
    (2001 if unknown, reported in meta); the simulation runs for exactly the weather's length.

Results
    kpis: availability (time-based, windfarm), availability_energy (production-based), om_cost_usd (WOMBAT OpEx incl.
    fixed costs), equipment_cost_usd, materials_cost_usd, labor_cost_usd, vessel_hours (sail + on-turbine + weather
    wait, all vessels), weather_wait_s (sum of WOMBAT delays whose reason is weather), plus the engine-common
    distance_km, makespan_s, wait_s. fuel_t / co2_t are omitted (no fuel model mapped; never guessed).

Trajectory (offsim.contract): one agent per vessel.
    traveling -> state `sail`, positions interpolated on the great circle between port / turbine / substation;
    transferring crew and repair/maintenance -> `dp` at the turbine; delays: weather -> `wait`, everything else
    (no requests, next shift, charter gap, mobilization) -> `idle`.
    Honest limits: positions are straight great-circle legs, NOT sea lanes (real routing via `world.legs` is a
    later step). To keep sailing speeds physical, WOMBAT's `port_distance` is set from the geometry as
    max great-circle distance from the port to any turbine or the substation, times `route_factor` (one value for
    all turbines, so near turbines are reached "slower" than a straight sail; reported in meta).
    Vessel mobilization (e.g. jack-up, `mobilization_days`) is shown as idle at the port; the last
    `port_distance / speed` of it is drawn as the sailing leg to site (WOMBAT does not log the transit).

Unsupported (raises): non-empty Plan routes, tow-to-port / port / tugboat configs, towing or mooring actions in
the log, non-hourly weather, a user `port_distance` shorter than the layout geometry, unknown vessel actions.
"""
from __future__ import annotations

import copy
import re
import shutil
import tempfile
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from offsim import contract
from offsim.engines.base import (Plan, Problem, SimResult, Unsupported, WeatherSeries, World,
                                 register_engine)

DEFAULT_YEAR = 2001
_DEFAULT_FILES = {   # used only for the bundled DEFAULT library
    "turbine": "12MW_osw_fixed.yaml", "array_cable": "osw_array.yaml", "export_cable": "osw_export.yaml",
    "substation_file": "osw_substation.yaml", "fixed_costs": "fixed_costs_osw_fixed.yaml",
}
_CLS_BY_CAPABILITY = {"CTV": "crew_boat", "SOV": "sov", "LCN": "jackup", "CAB": "cable_vessel", "DSV": "dsv",
                      "TUG": "tug", "AHV": "ahv"}
_TRAVEL = re.compile(r"traveling from (\S+) to (\S+)")
_DP_ACTIONS = {"transferring crew", "repair", "maintenance"}
_ZERO_OK = {"complete travel", "complete transfer", "repair complete", "maintenance complete", "repair request",
            "maintenance request", "leaving site", "monthly lease fee", "daily use fee", "requests being moved",
            "requests moved to port"}


# ------------------------------------------------------------------ geometry
def _unit(lon, lat):
    lo, la = np.radians(lon), np.radians(lat)
    return np.array([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)])


def gc_interp(p0: tuple[float, float], p1: tuple[float, float], f: float) -> tuple[float, float]:
    """Point at fraction f along the great circle p0 -> p1 (lon, lat degrees)."""
    a, b = _unit(*p0), _unit(*p1)
    w = np.arccos(np.clip(a @ b, -1.0, 1.0))
    if w < 1e-12:
        return p0
    v = (np.sin((1 - f) * w) * a + np.sin(f * w) * b) / np.sin(w)
    return float(np.degrees(np.arctan2(v[1], v[0]))), float(np.degrees(np.arcsin(np.clip(v[2], -1, 1))))


def _dist_m(p, q) -> float:
    return float(contract.haversine_m(p[0], p[1], q[0], q[1]))


# ------------------------------------------------------------------ spec parsing
def _library_dir(name) -> Path:
    from wombat.core.library import library_map
    if name is None:
        name = "DEFAULT"
    path = Path(library_map.get(str(name), name))
    if not path.is_dir():
        raise Unsupported(f"wombat: library {name!r} is not a WOMBAT library directory")
    return path


def _pick(spec: dict, key: str, is_default_lib: bool):
    val = spec.get(key)
    if val is None and is_default_lib:
        val = _DEFAULT_FILES.get(key)
    if val is None:
        raise Unsupported(f"wombat: extra['wombat'] needs {key!r} when the library is not DEFAULT")
    return val


def _copy_component(src_lib: Path, dst_lib: Path, sub: str, item, tag: str) -> str:
    """Put a library file (name) or an inline dict into dst_lib/<sub>; returns the file name."""
    if isinstance(item, dict):
        fname = f"{tag}.yaml"
        (dst_lib / sub / fname).write_text(yaml.safe_dump(item, sort_keys=False))
        return fname
    src = src_lib / sub / str(item)
    if not src.is_file():
        raise Unsupported(f"wombat: {sub}/{item} not found in library {src_lib}")
    shutil.copy(src, dst_lib / sub / src.name)
    return src.name


def _copy_power_curve(src_lib: Path, dst_lib: Path, turbine_file: str) -> dict:
    tdict = yaml.safe_load((dst_lib / "turbines" / turbine_file).read_text())
    pc = (tdict.get("power_curve") or {}).get("file")
    if pc:
        src = src_lib / "turbines" / pc
        if not src.is_file():
            raise Unsupported(f"wombat: power curve turbines/{pc} not found in library {src_lib}")
        shutil.copy(src, dst_lib / "turbines" / src.name)
    return tdict


def _great_circle_max(port, points) -> float:
    return max(_dist_m(port, p) for p in points)


# ------------------------------------------------------------------ the engine
@register_engine("wombat")
class WombatEngine:
    name = "wombat"
    classes = {"WIND-OM"}
    needs_weather = True

    # -- public ---------------------------------------------------------------------------------------
    def simulate(self, problem: Problem, plan: Plan, world: World,
                 weather: WeatherSeries | None = None, seed: int = 0) -> SimResult:
        try:
            from wombat import Simulation
            import wombat
        except ImportError as e:                       # pragma: no cover
            raise Unsupported(f"wombat is not installed: {e}") from e
        if not (problem.cls & self.classes):
            raise Unsupported(f"wombat handles {sorted(self.classes)}, got {sorted(problem.cls)}")
        if plan is not None and any(plan.routes.values()):
            raise Unsupported("wombat dispatches vessels itself; pass a Plan with empty routes")
        if weather is None:
            raise Unsupported("wombat needs a WeatherSeries (hourly hs_m, wind_mps)")
        spec = problem.extra.get("wombat")
        if not isinstance(spec, dict):
            raise Unsupported("problem.extra['wombat'] (dict) is missing")
        for k in ("tow_to_port", "port_config", "tugboats"):
            if spec.get(k):
                raise Unsupported(f"wombat adapter: {k!r} (tow-to-port repairs) is not mapped")

        layout, port, sub_pos, sub_note = self._geometry(problem, spec)
        wdf, t0, year, year_note = self._weather(weather, spec)
        sample_s = float(spec.get("sample_s", 900.0))

        with tempfile.TemporaryDirectory(prefix="offsim_wombat_") as tmp:
            lib = Path(tmp)
            cfg, vessel_info, notes = self._build(lib, spec, layout, port, sub_pos, wdf, year, seed)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                sim = Simulation.from_config(lib, cfg)
                sim.run(save_metrics_inputs=False)
            events = sim.env.load_events_log_dataframe()
            kp = self._kpis(sim)
            names = list(sim.service_equipment)
            speeds = {n: float(sim.service_equipment[n].settings.speed) for n in names}
            onsite = {n: bool(sim.service_equipment[n].settings.onsite) for n in names}
            caps = {n: str(getattr(sim.service_equipment[n].settings.capability[0], "value",
                                   sim.service_equipment[n].settings.capability[0])) for n in names}

        traj, ev_tab, wx = self._to_contract(events, names, speeds, onsite, layout, port, sub_pos, t0, sample_s)
        agents = pd.DataFrame([{
            "agent_id": n, "cls": _CLS_BY_CAPABILITY.get(caps[n], caps[n].lower()),
            "vmax_mps": speeds[n] / 3.6, "capacity": np.nan, "domain": "sea"} for n in names])
        base = contract.kpis(traj)
        k = {"distance_km": base["distance_km"], "makespan_s": base["makespan_s"], "wait_s": base["wait_s"]}
        k.update(kp)
        k["weather_wait_s"] = wx["weather_wait_s"]
        k["vessel_hours"] = wx["vessel_hours"]
        k = {a: float(b) for a, b in k.items()}
        meta = {"wombat_version": getattr(wombat, "__version__", "?"), "library": str(spec.get("library", "DEFAULT")),
                "sources": notes, "substation": sub_note, "weather_origin": year_note,
                "routing": "great-circle straight legs (not sea lanes; see world.legs, later step)",
                "vessels": vessel_info, "position_notes": wx["notes"], "n_turbines": len(layout),
                "sim_days": len(wdf) / 24.0}
        return SimResult(traj=traj, agents=agents, events=ev_tab, kpis=k, engine=self.name, seed=seed,
                         weather=weather.source, meta=meta)

    # -- inputs -----------------------------------------------------------------------------------------
    @staticmethod
    def _geometry(problem: Problem, spec: dict):
        lay = spec.get("layout")
        port = spec.get("port")
        if not lay and len(problem.nodes) > 1:
            lay = [{"id": f"T{i}", "lon": n[0], "lat": n[1]} for i, n in enumerate(problem.nodes[1:], 1)]
        if port is None and problem.nodes:
            port = {"lon": problem.nodes[0][0], "lat": problem.nodes[0][1]}
        if not lay:
            raise Unsupported("wombat: extra['wombat']['layout'] (turbines with id, lon, lat) is missing")
        if not port:
            raise Unsupported("wombat: extra['wombat']['port'] {lon, lat} is missing")
        ids = [str(t["id"]) for t in lay]
        if len(set(ids)) != len(ids):
            raise Unsupported("wombat: duplicate turbine ids in layout")
        layout = [{"id": str(t["id"]), "lon": float(t["lon"]), "lat": float(t["lat"]),
                   "string": int(t.get("string", 0)), "order": t.get("order")} for t in lay]
        cnt: dict[int, int] = {}
        for t in layout:
            if t["order"] is None:
                t["order"] = cnt.get(t["string"], 0)
            cnt[t["string"]] = cnt.get(t["string"], 0) + 1
        port_xy = (float(port["lon"]), float(port["lat"]))
        sub = spec.get("substation")
        if sub:
            sub_xy, note = (float(sub["lon"]), float(sub["lat"])), "given"
        else:
            sub_xy = (float(np.mean([t["lon"] for t in layout])), float(np.mean([t["lat"] for t in layout])))
            note = "centroid of turbines (assumption)"
        return layout, port_xy, sub_xy, note

    @staticmethod
    def _weather(weather: WeatherSeries, spec: dict):
        df = weather.df
        for c in ("t", "hs_m", "wind_mps"):
            if c not in df.columns:
                raise Unsupported(f"wombat: weather column {c!r} missing")
        df = df.sort_values("t").reset_index(drop=True)
        if spec.get("horizon_days"):
            df = df[df["t"] < df["t"].iloc[0] + float(spec["horizon_days"]) * 86400.0].reset_index(drop=True)
        if len(df) < 24:
            raise Unsupported("wombat: need at least 24 hourly weather rows")
        if df[["hs_m", "wind_mps"]].isna().any().any():
            raise Unsupported("wombat: NaN in hs_m / wind_mps (WOMBAT would silently fill zeros)")
        step = np.diff(df["t"].to_numpy())
        if not np.allclose(step, 3600.0):
            raise Unsupported("wombat: weather must be strictly hourly (t step 3600 s); resample upstream")
        year = int(weather.year) if weather.year else DEFAULT_YEAR
        note = f"Jan 1 {year}" + ("" if weather.year else " (weather.year unknown, default)")
        t0 = float(df["t"].iloc[0])
        origin = pd.Timestamp(year=year, month=1, day=1) + pd.to_timedelta(t0, unit="s")
        wdf = pd.DataFrame({"datetime": origin + pd.to_timedelta(df["t"] - t0, unit="s"),
                            "windspeed": df["wind_mps"].astype(float).to_numpy(),
                            "waveheight": df["hs_m"].astype(float).to_numpy()})
        return wdf, t0, year, note

    def _build(self, lib: Path, spec: dict, layout, port, sub_pos, wdf, year, seed):
        from wombat.core.library import create_library_structure
        create_library_structure(lib)
        src_name = spec.get("library") or "DEFAULT"
        src = _library_dir(src_name)
        is_def = str(src_name).upper() == "DEFAULT"
        notes: dict[str, str] = {}
        tag = "WOMBAT default library" if is_def else f"library {src_name}"

        t_item = _pick(spec, "turbine", is_def)
        t_file = _copy_component(src, lib, "turbines", t_item, "offsim_turbine")
        tdict = _copy_power_curve(src, lib, t_file)
        if spec.get("failure_rate_factor") is not None:
            fac = float(spec["failure_rate_factor"])
            if fac <= 0:
                raise Unsupported("wombat: failure_rate_factor must be > 0")
            tdict = copy.deepcopy(tdict)
            for comp in tdict.values():
                if isinstance(comp, dict):
                    for f in comp.get("failures", []) or []:
                        f["scale"] = float(f["scale"]) / fac
            (lib / "turbines" / t_file).write_text(yaml.safe_dump(tdict, sort_keys=False))
            notes["failure_rate_factor"] = f"x{fac} (scenario value)"
        cap_kw = float(tdict["capacity_kw"])
        notes["turbine"] = f"{t_file} ({tag if not isinstance(t_item, dict) else 'inline'})"

        a_file = _copy_component(src, lib, "cables", _pick(spec, "array_cable", is_def), "offsim_array")
        e_file = _copy_component(src, lib, "cables", _pick(spec, "export_cable", is_def), "offsim_export")
        s_file = _copy_component(src, lib, "substations", _pick(spec, "substation_file", is_def), "offsim_oss")
        notes["cables_substation"] = f"{a_file}, {e_file}, {s_file} ({tag})"
        fc = _pick(spec, "fixed_costs", is_def)
        if isinstance(fc, dict):
            fixed = fc
            notes["fixed_costs"] = "inline"
        else:
            fixed = yaml.safe_load((src / "project" / "config" / str(fc)).read_text())
            notes["fixed_costs"] = f"{fc} ({tag})"

        oss_id = str(spec.get("substation", {}).get("id", "OSS")) if spec.get("substation") else "OSS"
        rows = [dict(id=oss_id, substation_id=oss_id, name=oss_id, type="substation", longitude=sub_pos[0],
                     latitude=sub_pos[1], string="", order="", distance="", subassembly=s_file, upstream_cable=e_file)]
        for t in layout:
            rows.append(dict(id=t["id"], substation_id=oss_id, name=t["id"], type="turbine", longitude=t["lon"],
                             latitude=t["lat"], string=t["string"], order=t["order"], distance=0,
                             subassembly=t_file, upstream_cable=a_file))
        df_layout = pd.DataFrame(rows)

        # port distance from geometry (one WOMBAT value for all turbines)
        pts = [(t["lon"], t["lat"]) for t in layout] + [sub_pos]
        route_factor = float(spec.get("route_factor", 1.0))
        if route_factor < 1.0:
            raise Unsupported("wombat: route_factor must be >= 1")
        port_km = _great_circle_max(port, pts) / 1000.0 * route_factor
        notes["port_distance_km"] = f"{port_km:.2f} (max great-circle port->turbine/substation x route_factor {route_factor})"

        y0, y1 = int(wdf["datetime"].dt.year.min()), int(wdf["datetime"].dt.year.max())
        vessels_cfg: list = []
        info = []
        raw = spec.get("vessels")
        if not raw:
            raise Unsupported("wombat: extra['wombat']['vessels'] is empty")
        for i, item in enumerate(raw):
            if isinstance(item, str):
                item = {"file": item}
            count = int(item.get("count", 1))
            body = item["inline"] if "inline" in item else None
            if body is None:
                f = src / "vessels" / str(item["file"])
                if not f.is_file():
                    raise Unsupported(f"wombat: vessels/{item['file']} not found in library {src}")
                body = yaml.safe_load(f.read_text())
            body = copy.deepcopy(body)
            ov = dict(item.get("overrides") or {})
            if "port_distance" in ov and float(ov["port_distance"]) < port_km - 1e-6:
                raise Unsupported(f"wombat: vessel port_distance {ov['port_distance']} km is shorter than the layout "
                                  f"geometry ({port_km:.2f} km); sailing speeds would be unphysical")
            body.update(ov)
            body.setdefault("port_distance", port_km)
            if "port_distance" not in ov:
                body["port_distance"] = port_km
            body["start_year"], body["end_year"] = y0, y1          # charter window must cover the weather
            if body.get("capability") in ("TUG", "AHV") or "tug" in str(body.get("name", "")).lower():
                raise Unsupported("wombat: tugboats / tow-to-port are not mapped")
            fname = _copy_component(src, lib, "vessels", body, f"offsim_vessel_{i}")
            vessels_cfg.append([fname, count] if count > 1 else fname)
            info.append({"file": item.get("file", "inline"), "name": body.get("name"), "count": count,
                         "speed_kmh": body.get("speed"), "port_distance_km": body["port_distance"],
                         "overrides": ov, "source": tag if "inline" not in item else "inline"})
        notes["vessel_years"] = f"start/end_year forced to weather span {y0}-{y1}"

        cfg = dict(name="offsim_wombat", layout=df_layout, service_equipment=vessels_cfg, weather=wdf,
                   workday_start=int(spec.get("workday_start", 7)), workday_end=int(spec.get("workday_end", 19)),
                   inflation_rate=float(spec.get("inflation_rate", 0.0)),
                   project_capacity=cap_kw * len(layout) / 1000.0, port_distance=port_km,
                   start_year=y0, end_year=y1, random_seed=int(seed), fixed_costs=fixed)
        return cfg, info, notes

    # -- outputs ------------------------------------------------------------------------------------------
    @staticmethod
    def _kpis(sim) -> dict:
        m = sim.metrics

        def cell(df):
            return float(np.asarray(df.to_numpy(dtype=float)).ravel()[-1])
        opex = m.opex("project", by_category=True)
        o = opex.iloc[:, 0] if opex.shape[1] == 1 else opex.iloc[0]
        get = lambda k: float(o[k]) if k in o.index else 0.0           # noqa: E731
        return {
            "availability": cell(m.time_based_availability("project", "windfarm")),
            "availability_energy": cell(m.production_based_availability("project", "windfarm")),
            "om_cost_usd": get("OpEx"), "equipment_cost_usd": get("equipment_cost"),
            "materials_cost_usd": get("materials_cost"), "labor_cost_usd": get("total_labor_cost"),
        }

    @staticmethod
    def _to_contract(events: pd.DataFrame, names, speeds, onsite, layout, port, sub_pos, t0, sample_s):
        pos = {"port": port, "site": sub_pos}
        pos.update({t["id"]: (t["lon"], t["lat"]) for t in layout})
        tur = {t["id"] for t in layout}
        rows, evrows = [], []
        weather_wait = 0.0
        vessel_h = 0.0
        notes: list[str] = []
        ev = events.loc[events["agent"].isin(names)].copy()
        ev["env_time"] = ev["env_time"].astype(float)
        ev["duration"] = ev["duration"].astype(float)
        ev = ev.sort_values("env_time", kind="stable")
        bad = sorted({a for a in ev["action"].astype(str) if a in ("towing", "complete towing", "unmooring",
                                                                      "mooring reconnection")})
        if bad:
            raise Unsupported(f"wombat: log contains tow/mooring actions {bad}; not mapped")

        for name in names:
            g = ev[ev["agent"] == name]
            # an on-site vessel starts "somewhere on site": position unresolved (None) until WOMBAT names a turbine
            # (it charges no time for that first hop), then the earlier idle rows are placed there too
            cur = None if onsite.get(name) else port
            tl: list[list] = []                                         # [t_s, lon/lat | None, state]
            last_end = None
            mob_start = None
            pend = None          # (t_arrival_h, t_floor_h): off-site vessel that WOMBAT says has arrived on site

            def put(t, p, st):
                tl.append([t0 + t * 3600.0, p, st])

            def resolve(p):
                nonlocal cur
                for row in reversed(tl):
                    if row[1] is not None:
                        break
                    row[1] = p
                cur = p

            def transit(dst, t_arr, floor):
                """Draw port->dst sailing that ends at t_arr, carved out of the mobilization window."""
                nonlocal cur
                d = _dist_m(cur, dst)
                if d <= 25.0:
                    cur = dst
                    return
                tr_h = d / (speeds[name] / 3.6) / 3600.0
                t_start = max(t_arr - tr_h, floor)
                if t_start > t_arr - tr_h + 1e-9:
                    notes.append(f"{name}: mobilization shorter than transit; sailing faster than nominal speed")
                put(t_start, cur, "sail")
                cur = dst
                put(t_arr, cur, "idle")

            for r in g.itertuples(index=False):
                act, dur, ts = str(r.action), float(r.duration), float(r.env_time)
                add, sid = str(r.additional), (None if pd.isna(r.system_id) else str(r.system_id))
                reason = str(r.reason)
                if dur > 0 or act in ("traveling", "mobilization"):
                    evrows.append({"t": t0 + ts * 3600.0, "agent_id": name, "action": act, "reason": reason,
                                   "detail": add, "system_id": sid, "duration_s": dur * 3600.0,
                                   "cost_usd": float(r.total_cost) if not pd.isna(r.total_cost) else 0.0})
                if act == "mobilization" and "arrived on site" in reason:
                    if not onsite.get(name):
                        pend = (ts, mob_start if mob_start is not None else (last_end or 0.0))
                    continue
                if pend is not None and (act in _DP_ACTIONS or act == "traveling"):
                    dst0 = pos[sid] if sid in tur else pos["site"]
                    transit(dst0, pend[0], pend[1])
                    pend = None
                if dur <= 0:
                    if act not in _ZERO_OK and act not in ("mobilization", "traveling", "delay") \
                            and act not in _DP_ACTIONS:
                        raise Unsupported(f"wombat: unmapped vessel action {act!r}")
                    continue
                if act == "traveling":
                    m = _TRAVEL.match(add)
                    dst = None
                    if m:
                        frm, to = m.group(1), m.group(2)
                        dst = (pos["port"] if to == "port" else
                               pos[sid] if (to == "site" and sid in tur) else
                               pos["site"] if to == "site" else pos.get(to))
                    if dst is None:
                        raise Unsupported(f"wombat: cannot place travel destination from {add!r}")
                    if cur is None:
                        resolve(pos["site"])
                    put(ts, cur, "sail")
                    n = max(int(dur * 3600.0 // sample_s), 0)
                    for j in range(1, n + 1):
                        f = (j * sample_s) / (dur * 3600.0)
                        if f < 1.0:
                            put(ts + f * dur, gc_interp(cur, dst, f), "sail")
                    cur = dst
                    put(ts + dur, cur, "idle")
                    vessel_h += dur
                elif act in _DP_ACTIONS:
                    if sid in tur and cur is None:
                        resolve(pos[sid])
                    if sid in tur:
                        if _dist_m(cur, pos[sid]) > 25.0:
                            notes.append(f"{name}: snapped to {sid} at t={ts:.2f} h")
                        cur = pos[sid]
                    put(ts, cur, "dp")
                    put(ts + dur, cur, "idle")
                    vessel_h += dur
                elif act == "delay":
                    wx = "weather" in add.lower() or "weather" in reason.lower()
                    put(ts, cur, "wait" if wx else "idle")
                    put(ts + dur, cur, "idle")
                    if wx:
                        weather_wait += dur * 3600.0
                        vessel_h += dur
                elif act == "mobilization":
                    mob_start = ts
                    put(ts, cur, "idle")
                    put(ts + dur, cur, "idle")
                else:
                    raise Unsupported(f"wombat: unmapped vessel action {act!r} with duration")
                last_end = ts + dur
            if cur is None:
                resolve(pos["site"])
            if not tl:
                tl = [[t0, cur, "idle"]]
            df = pd.DataFrame(tl, columns=["t", "pos", "state"])
            df["lon"] = [p[0] for p in df["pos"]]
            df["lat"] = [p[1] for p in df["pos"]]
            df = df.drop(columns="pos")
            df["agent_id"] = name
            rows.append(df)
        traj = pd.concat(rows, ignore_index=True)
        # one row per (agent, t): the later entry is the state that begins there
        traj["t"] = traj["t"].round(3)          # float noise between an action's end and the next one's start
        traj = traj.drop_duplicates(["agent_id", "t"], keep="last")
        traj = traj.sort_values(["agent_id", "t"], kind="stable").reset_index(drop=True)
        traj["alt_m"] = 0.0
        traj = traj[["agent_id", "t", "lon", "lat", "alt_m", "state"]]
        ev_tab = pd.DataFrame(evrows, columns=["t", "agent_id", "action", "reason", "detail", "system_id",
                                               "duration_s", "cost_usd"])
        return traj, ev_tab, {"weather_wait_s": weather_wait, "vessel_hours": vessel_h, "notes": notes}

