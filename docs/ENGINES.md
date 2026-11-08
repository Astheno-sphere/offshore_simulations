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
| `road` | our SimPy replay on OSM roads (networkx graph) | land legs: trucks, vans, workers driving to a depot, quay or heliport | none | ours (networkx BSD-3, OSM ODbL data) |
| `gtfs` | `offsim.transit.gtfs` (Entur national GTFS) | replaying bus / ferry / tram / rail timetables as agents (Molde/FRAM, Oslo/Ruter) | none | ours; data NLOD 2.0 |

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

### gtfs
- **Mapping:** `extra["gtfs"]` = {dir (GTFS folder from `offsim.transit.gtfs.clip`), date, t0, t1 (seconds on the service-day clock or
  "HH:MM:SS", 24+ allowed), route_types?, sample_s?}; `problem.cls = {"TRANSIT-REPLAY"}`. The Plan is empty: the timetable *is* the plan
  (non-empty routes raise `Unsupported`). One agent per trip (`agent_id = trip_id`; `~prev` suffix for previous-day trips running past midnight);
  `cls` bus | ferry | rail | tram from `route_type` (basic and extended codes, e.g. 700, 1000, 1200; unknown types such as air or cable car are dropped
  and counted); domain land, sea for ferry; `vmax` = 1.1 x observed stop-to-stop speed.
- **Positions:** along the trip's shape (`shape_dist_traveled` when complete, else stops projected forward onto the polyline); no shape = straight between stops.
- **Contract:** `drive` (`sail` for ferry) when moving, `wait` while dwelling (arrival != departure) and at the terminus; a row at every stop arrival
  and departure plus a `sample_s` grid; `idle` never. Events: one `dwell` per stop with dwell.
- **KPIs:** `trips, vehicle_km, peak_vehicles, mean_headway_s` (gap between trip starts, whole network; per-stop headway: `gtfs.headways`), plus
  `distance_km, makespan_s, wait_s`, `weather_wait_s = 0`.
- **Limits:** scheduled times only (no delays, real-time or cancellations); `frequencies.txt` not expanded; missing stop times are interpolated by distance and
  zero-time hops floored at 1 s (counted in `meta["dropped"]`); ferries without a shape run straight and may cross land, so give `World.land` to `validate`;
  no weather. `clip` keeps whole trips with >= 2 in-bbox stops, so long-distance trips pull in stops outside the box.

### road
- **Mapping:** same as `replay` (Plan.routes, fleet, `service_s`/`tw`/`demand`, `extra["berths"]`), with agents of domain `land`
  and moving state `drive`. `World.legs` = `offsim.worlds.roads.RoadGraph.legs` (fastest route on the OSM `roads` layer,
  snapped to the nearest road, one-way streets respected, DIRECTED legs: a missing used leg raises `Unsupported`, the reverse
  leg is never a stand-in). Time comes from `extra["road_leg_profile"]` (seconds at every vertex) or, coarser, `extra["road_time_s"]`;
  with neither the engine raises `Unsupported`. The pipeline switches to this graph/engine when a fleet has `domain: land` or the
  scenario sets `world_mode: road`, reading `data/worlds/<world>/osm/roads.geojson` (missing: stop at gate 0 with
  `python -m offsim.worlds.fetch_world --place <world> --modes road`).
- **Speeds:** OSM `maxspeed` where tagged, else a class default (50 residential, 80 rural classes, 90 motorway, 30 service/track;
  the Statens vegvesen general limits 50/80/90/110 km/h, Vegtrafikkloven / skiltforskriften, "general limits, not verified per
  road"), all listed as assumptions with the share of edges that used them. Fleet `speed_mps` is a top speed: the vehicle drives at
  min(road speed, fleet speed) on every hop; `meta["speed_cap_applied"]` says when that lengthened a leg beyond the solver's time matrix.
- **How:** `offsim/sim/replay.py` is unchanged (one speed per agent). Each used leg is replayed in time-equivalent space (hop
  length = hop seconds x 25 m/s) and the moving rows are mapped back onto the road polyline, so waits, time windows and berth queues run
  on the real-seconds clock and every road vertex appears in the trajectory.
- **KPIs:** `distance_km, makespan_s, wait_s, weather_wait_s = 0`; `meta["drive_s"]`. Distances are sphere-based (contract), the graph
  uses WGS84: about 0.3 % apart at 62 N, inside gate 2's 1 %.
- **Gate 4b (AIS):** a scenario with `validate: {ais: true}` runs `offsim.traffic.ais.compare_to_sim` against
  `data/worlds/<world>/ais/calibration.json` (simulated speeds in knots, port-call dwell for places the calibration lists); a failure, or a
  calibration that judges nothing, stops the run at `4b_ais`; no calibration file stops at gate 0 with the fetch hint. AIS describes
  ships: use it on road runs only for a calibration you built for that purpose.
- **Limits:** free-flow speed at the limit; no congestion, signals, turn restrictions or penalties, access=private, vehicle weight/height,
  ferries; the roads layer must be noded at junctions (pyrosm/osmnx output is). Snapping uses the largest strongly connected component
  and refuses points farther than `max_snap_m` (default 2000 m) from it. Two parallel roads between the same junctions: the faster one routes.
  No weather (a series is ignored and noted). One `speed_mps` per run (mixed speeds raise). CVRP, VRPTW.

## Choosing
PSV supply / ferry / crew boat with a routing plan → `replay` for gate 2, `openclsim` for the ensemble.
Land legs on roads (trucks, vans, workers) → `road`. Wind O&M → `wombat`. Wind installation → `orbit`. Two engines on the same small instance must agree on
deterministic KPIs within 1% (`tests/test_engine_crosscheck.py`) before either is trusted on a large one.

### Entur realtime (validation, gate 4c)
- **What:** not an engine. `offsim.transit.entur` polls Entur's Vehicle Positions GraphQL API (stdlib, no websockets; header `ET-Client-Name` from env
  `ENTUR_CLIENT_NAME`, default `astheno-offshoresimulations`; 429 honours Retry-After; at most one snapshot per 2 s) into `vehicles.csv`; run it through the
  `entur-realtime` workflow (api.entur.io is unreachable from the Claude workspace). Credit "Source: Entur AS". GraphQL field names and the units of
  `delay` / `speed` are **unverified live**.
- **Mapping:** `offsim.transit.observed.observed_trajectories(vehicles_df, t0_utc)` gives contract trajectories, one agent per service journey (cls bus, domain
  land, `drive`/`wait` from the position change between samples). `t0_utc` must be the UTC instant of the scheduled trajectory's t = 0.
- **Gate 4c (opt-in, by hand; not in `offsim run`):** `compare_to_schedule(sched_traj, observed_traj)` projects each observed point onto the GTFS path and reports per
  journey the delay quantiles and the observed/scheduled travel-time ratio; `gate_4c(cmp)` passes when the median |median delay| <= 180 s and the median ratio
  <= 1.25 (both **assumptions**, unsourced), and fails when nothing could be judged. Record runs in `docs/TESTLOG.md`.
- **Limits:** sampled positions only (30 s polls, vehicles report at their own rate); loop routes can project to the wrong lap; a dwell counts from its first
  arrival; trips are matched by id (Entur GTFS `trip_id` = ServiceJourney id), so a feed from another date or a re-planned journey simply does not match.
