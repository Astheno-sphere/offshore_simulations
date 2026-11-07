# Engines and solvers: definitions, assumptions, limits

Each tool sits behind `offsim/engines/base.py`. This page says what each one *means*, so a scenario picks the
engine whose assumptions match the paper, not the one that looks best. Adapters fill their own section with
the exact mapping they implement; anything not mapped raises `Unsupported`.

## Solvers (L1: Problem → Plan)

| Name | Tool | Classes | Exact? | Runs | Notes |
|---|---|---|---|---|---|
| `pyvrp` | PyVRP 0.14 (HGS) | CVRP, VRPTW | heuristic | here | index traps handled in `pyvrp_adapter.py` |
| `pyomo` | Pyomo + HiGHS | any MIP we write | exact (bound) | here | certifies heuristics on small instances |
| `ampl` | AMPL academic + HiGHS/CBC | any `.mod` | exact (bound) | Actions, laptop | `.mod/.dat` live in the paper folder; Pyomo twin for cross-check |

## Engines (L2: Plan → SimResult)

| Name | Tool | Best for | Weather | Licence |
|---|---|---|---|---|
| `replay` | our SimPy replay | checking a plan in time on sea lanes; berth/helideck queues | via `offsim.weather.effects` | ours |
| `openclsim` | OpenCLSim (TU Delft, Deltares, Van Oord) | cyclic vessel logistics: load, sail, unload under weather windows | native (`HasWeatherPluginActivity`) | MIT |
| `wombat` | WOMBAT (NREL) | offshore-wind O&M: failures, CTV/SOV/jack-up dispatch, availability | native (hourly series) | Apache-2.0 |
| `orbit` | ORBIT (NREL) | offshore-wind installation: WTIV, feeders, port, weather delays | native (hourly series) | Apache-2.0 |

### Common definitions
- **Weather window**: an activity of duration *d* with limit *L* (e.g. Hs ≤ 2.5 m) starts only when the series
  stays ≤ *L* for *d* hours from the start. Waiting time is state `wait` in the contract.
- **Operability limits** come from `offsim/weather/operability.py` with sources; unsourced limits are
  `assumption: true` and listed in the report.
- **Seed**: the only source of randomness (failures, service-time noise). Same seed across variants.
- **KPIs every engine reports**: `distance_km, makespan_s, wait_s, weather_wait_s, fuel_t, co2_t`
  (fuel/CO₂ from `offsim.emissions` once built, else omitted, never guessed), plus engine-specific
  (`availability`, `install_days`, `service_level`).

### replay
- **Mapping:** `Plan.routes` → `offsim.sim.replay` routes (depot node 0 implicit at both ends); fleet → agents `<CLS>-k`;
  `service_s`/`tw`/`demand` pass through; `extra["berths"]={node: n}` → shared berths (state `wait`); `World.legs` → lane geometry.
- **KPIs:** `distance_km, makespan_s, wait_s`; `weather_wait_s = 0`.
- **Limits:** no weather — a WeatherSeries is accepted, ignored and noted in `meta["weather_note"]`, never faked. A used leg
  missing from `World.legs` raises `Unsupported` (no silent straight line across land). Mixed domains in one run raise. CVRP, VRPTW.

### openclsim
- **Mapping:** depot → Site; each stop → Site with container capacity = demand × visits; berths → site resource; each route →
  one vessel (ContainerDependentMovable + Processor) running Move → ShiftAmount(unload, duration = service_s) → … → Move home.
  Lane paths enter as `MoveActivity(duration = path length / speed)`; straight legs use OpenCLSim's WGS84 geodesic (< 0.5 % from the contract sphere).
- **Weather:** `extra["limits"]={"hs_m": L}` + WeatherSeries → `HasWeatherPluginActivity`/`WeatherCriterion(maximum=L,
  window_length=service_s)` on each unload; the wait is logged by OpenCLSim → contract `wait`, KPI `weather_wait_s`.
- **Guards (1.6.3 quirks):** the plugin raises IndexError when no window exists and silently releases after the series ends —
  the adapter pre-checks and raises `Unsupported` instead, and verifies every unload start against the plugin's windows.
- **Limits:** CVRP only; no time windows; one weather limit; sailing not weather-limited; no fuel/CO₂ yet; berth waits
  inferred from log gaps (agrees with replay within 2 %).
- **Cross-check (tests/test_engine_crosscheck.py):** vs replay, distance identical, makespan within 0.15 %; synthetic storm
  adds weather wait and lengthens makespan.

### wombat
- **Mapping:** `extra["wombat"]` = layout (id, lon, lat), port, vessels, library (bundled DEFAULT/COWER 2024 or a path), cables,
  costs, `failure_rate_factor`. The Plan is empty: WOMBAT dispatches itself (non-empty routes raise `Unsupported`).
- **Weather:** hourly `hs_m, wind_mps` → `waveheight, windspeed`; the run lasts as long as the series (Jan 1 of its year = t0).
- **KPIs:** `availability, availability_energy, om_cost_usd, vessel_hours, weather_wait_s, distance_km, makespan_s, wait_s`.
- **Contract:** one agent per vessel; travel `sail` (great circle port↔turbine↔substation), transfer/repair `dp`,
  weather delay `wait`, other delays/mobilisation `idle`.
- **Limits:** straight great-circle legs (no `world.legs` yet); one `port_distance` = farthest asset × `route_factor`;
  tow-to-port, tugs, mooring unsupported; vessel charter years forced to the weather span (noted in meta).

### orbit
- **Mapping:** `extra["orbit"]` = an ORBIT ProjectManager config; `extra["orbit_geo"]` = port/site lon/lat + `route_factor`
  (`site.distance` ≥ great circle). Library defaults are recorded in `meta.sources` as "ORBIT default". Plan is empty.
- **Weather:** hourly `hs_m, wind_mps` → `waveheight, windspeed`; series too short for the project → `Unsupported`.
- **KPIs:** `install_days` (parallel phases not double counted), `install_days_sum, installation_capex_usd, weather_wait_s,
  queue_wait_s, vessel_hours, distance_km, makespan_s, wait_s`.
- **Contract:** transit `sail`, weather delay `wait`, queue/other waits `idle`, port actions `load`, site actions `dp`.
- **Limits:** phases with trajectories: Turbine, Monopile, Jacket, OffshoreSubstation installation; cables, scour, tow,
  mooring raise `Unsupported` — so floating wind (Utsira Nord, Hywind Tampen) is not yet representable; one straight leg.

## Choosing
PSV supply / ferry / crew boat with a routing plan → `replay` for gate 2, `openclsim` for the ensemble.
Wind O&M → `wombat`. Wind installation → `orbit`. Two engines on the same small instance must agree on
deterministic KPIs within 1% (`tests/test_engine_crosscheck.py`) before either is trusted on a large one.
