# Engines and solvers: definitions, assumptions, limits

Each tool sits behind `offsim/engines/base.py`. This page says what each one *means*, so a scenario picks the
engine whose assumptions match the paper, not the one that looks best. Adapters fill their own section with
the exact mapping they implement; anything not mapped raises `Unsupported`.

## Solvers (L1: Problem → Plan)

| Name | Tool | Classes | Exact? | Runs | Notes |
|---|---|---|---|---|---|
| `pyvrp` | PyVRP 0.14 (HGS) | CVRP, VRPTW | heuristic | here | index traps handled in `pyvrp_adapter.py`; VRPTW: `Problem.tw` + `service_s` -> `tw_early/tw_late/service_duration`, durations = `dist_m / speed_mps` rounded up (a PyVRP plan is feasible in the continuous replay); one fleet entry; refuses release times, a depot window, empty windows, windows without cls VRPTW |
| `pyomo` | Pyomo + HiGHS | CVRP, VRPTW (exact, <= 12 clients) | exact (bound) | here | certifies heuristics on small instances (gate 1b); VRPTW = MTZ load + big-M time flow (`vrptw_exact`), continuous times so exact <= PyVRP objective; same refusals as `pyvrp` |
| `ampl` | AMPL academic + HiGHS/CBC | CVRP (`cvrp.mod`), VRPTW (`vrptw.mod`) | exact (bound) | Actions, laptop | `write_dat` picks the model from `Problem.cls`; Pyomo twin for cross-check; `vrptw.mod` is text-checked only in the Claude workspace (no AMPL binary), its solve runs on Actions |
| `whelp` | Pyomo + HiGHS (decomposition) | WFPPP | exact (Stage 1 bound) | here | weekly helicopter flight program, Gribkovskaia & Slettemark 2025; AMPL twin `solve/ampl/whelp.mod` |

## Engines (L2: Plan → SimResult)

| Name | Tool | Best for | Weather | Licence |
|---|---|---|---|---|
| `replay` | our SimPy replay | checking a plan in time on sea lanes; berth/helideck queues | via `offsim.weather.effects` | ours |
| `openclsim` | OpenCLSim (TU Delft, Deltares, Van Oord) | cyclic vessel logistics: load, sail, unload under weather windows | native (`HasWeatherPluginActivity`) | MIT |
| `wombat` | WOMBAT (NREL) | offshore-wind O&M: failures, CTV/SOV/jack-up dispatch, availability | native (hourly series) | Apache-2.0 |
| `orbit` | ORBIT (NREL) | offshore-wind installation: WTIV, feeders, port, weather delays | native (hourly series) | Apache-2.0 |
| `road` | our SimPy replay on OSM roads (networkx graph) | land legs: trucks, vans, workers driving to a depot, quay or heliport | none | ours (networkx BSD-3, OSM ODbL data) |
| `gtfs` | `offsim.transit.gtfs` (Entur national GTFS) | replaying bus / ferry / tram / rail timetables as agents (Molde/FRAM, Oslo/Ruter) | none | ours; data NLOD 2.0 |
| `air` | our replay of a weekly helicopter program | cancellation and rebooking of flights under hourly wind / Hs limits (lean-fleet-vs-winter) | hourly `wind_mps`, `hs_m`, required | ours |

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

### rail (network layer for `gtfs`, not an engine)
- **What:** `offsim.worlds.rail.RailGraph` over the OSM `rail` layer (`railway=rail|light_rail|subway|tram`; `stations` layer for `station|halt|tram_stop`).
  Same contract as `RoadGraph` (`snap`, `legs`, plus `chain` for consecutive stops and `snap_stations` with the snap distance reported). Fetch with
  `fetch_world --modes rail` (implies `--osm`; add `--gtfs` for timetables).
- **Build rules:** lines split at shared vertices (switches); both directions; `service=yard|siding|spur` excluded unless `include_service=True`; tunnels, bridges,
  `electrified`, `voltage`, `gauge` kept as edge attributes; speed = `maxspeed` else a class default (main 120, branch 80, industrial 40, light_rail/subway 70, tram 40 km/h),
  **all defaults are assumptions** (`assumption: true`; Bane NOR / Norske tog figures not verified in this workspace). Unreachable pair or a station beyond
  `max_snap_m` (500 m) raises or is reported (`snapped=False`); never a silent straight line.
- **Hook in `gtfs`:** a rail or tram trip without a `shapes.txt` shape follows the rail graph between its stops (`build(rail="auto")` reads `<world>/osm/rail.geojson`
  next to the GTFS folder; `rail=False` disables). Order: shapes.txt, rail graph, straight. `meta["geometry_by_trip"]`, `meta["geometry"]`, `meta["rail_fallback"]`,
  `meta["rail_snap_m_max"]` record what was used. Timetable times are unchanged; only geometry and along-track distance change (so `vehicle_km` and `vmax` follow the track).
- **Not modelled:** single-track capacity and crossing logic, signalling and block sections, platform occupancy, dwell models, electrification as a constraint or
  energy, gradients and curve speeds, acceleration profiles, freight paths, Bane NOR network statements (slots, capacity), delays and real-time.

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

### whelp (solver, WFPPP)
- **Problem:** the Weekly Flight Program Planning Problem of Gribkovskaia & Slettemark (2025, Logistics 9(2):73, CC BY 3.0): one heliport, installations with weekly demand in
  half-flights, helicopters with daily operating windows (fixed weekly cost), minimise fixed + flight-hour cost. Code `offsim/solve/whelp.py`; the module docstring
  carries the equation map. `problem.extra["wfppp"]` (scenario `sim.wfppp`, passed by `pipeline.EXTRA_KEYS`): `slot_min, speed_kn, deck_min, turnaround_min,
  split_threshold_min, flight_hour_cost, days, day_start, max_helicopters, windows [{hours, cost}], installations [{name, demand_flights, open "07:00-18:00", mobile}]`,
  plus optional `method` (`decomposition` default | `full`), `time_limit_s` (default 120 per MIP) and, for the engine, `replay: {weeks}`. `nodes[0]` = heliport, `nodes[1:]` =
  installations in that order. The instances live in `offsim/papers/irinagribkovskaia-2025-tactical-helicopter/instances.yaml`; `scenario.yaml` (Florø, default),
  `scenario.stavanger.yaml`, `scenario.bergen.yaml` are generated from it (`python -m offsim.solve.whelp --instance bergen --write-scenario PATH`).
- **Methods:** `decomposition` = Sec 5 (Stage 1 resources + flights per day without slots, Stage 2 start slots per day by min sum of starts, loop that upgrades the helicopter
  with the cheapest next window or adds one); `full` = Sec 4.3 eqs (1)-(12) as one MIP (small instances; Florø about 40 s). Both on Pyomo + HiGHS; `ampl/whelp.mod` is the
  same flight-based model for AMPL (`write_dat`; not runnable here).
- **How the text was read** (each moves numbers; full list in the module docstring): cost = 140 x air time + deck stops in hours, turnaround NOT costed and times NOT rounded to slots
  (Table 4 costs are not multiples of a slot); slots n_f = ceil((duration + 60 min) / 15 min) with the turnaround inside; opening hours constrain the DEPARTURE slot; at most one
  flight to an installation STARTS per slot; the flight without its turnaround must fit the window (so a 10 h window holds 40 + 4 slots, as in the paper's fleet bound 220 = 44 x 5);
  utilisation = flown slots incl. turnaround / window slots + 4 per day (Florø 191 / 220 = 86.82 %, Bergen 1036 / 1080 = 95.93 %: Table 4's Stavanger 86.82 % repeats Florø's and does
  not fit this formula). Non-overlap is written as slot occupancy (equivalent to eqs 7 + 9).
- **Plan:** `routes {"H1-16h": [node, ...]}` installations in program order; `objective` total cost (masked units); `meta["program"]` = flights `{heli, day (0 = Monday), start_slot (0 = 07:00),
  installations, node_idx, duration_slots (turnaround included), fly_slots, duration_min, cost, kind, fid, window_h}`; `bound` = Stage 1 optimum of the first iteration (a valid lower bound);
  `meta` also `iterations`, `utilisation`, `shift_gap_days` (days with an idle gap that opening hours forced), `direct_only_slots`, `wall_s`.
- **Gate 1** for WFPPP is `whelp.check_program`: demand, windows, opening hours, overlap with turnaround, one start per installation and slot, spread, fleet size and cost, recomputed from the flight
  records and the geometry. Gate 2 compares the replay's own recomputation of the program's flight-hour cost (haversine, 1e-6) and flight count with the plan.
- **Positions are an assumption.** The paper masks them (p.25: 50-120 nm, direct flights 1-2.5 h). `design_layout` builds clusters (members 8-14 nm apart so splits exist) at seeded bearings
  and radii; `calibrate` multiplies all cluster radii by one scale s: grid scan of s, then step halving around the best, objective |cost - Table 4| / Table 4 plus 1 when the window set differs
  from Table 4 (cost is a step function of s: slots round up, windows jump). The record sits in `instances.yaml` under `calibration`. Florø is continuous in s, so its cost is matched by
  construction; the checks that are NOT fitted are the fleet, the window, the 191 slots, the flight counts. Stavanger / Bergen are limited by the window steps. Re-run: `python -m offsim.solve.whelp --instance X --calibrate`.
- **Paper inconsistency:** Table A2 (Stavanger) sums to 48.5 flights; the text (p.26) and Table 2 say 46.5. The tables are used as printed.
- **Limits:** one heliport, homogeneous fleet, windows start together, five identical weekdays, demand in half-flights; the decomposition's optimality claim is the paper's (Stage 2 minimises start times
  instead of enforcing eq 11). Stage 1 / 2 MIPs stop at `time_limit_s`; a time-limit result is reported as `status: time_limit`.

### air (engine, WFPPP)
- **Mapping:** the `whelp` program is replayed over an hourly `WeatherSeries`; the week starts at `extra["weather_t0_s"]` (default: first sample), five weekday blocks of 24 h, slot t departs at day start + t x 15 min.
  `wfppp.replay.weeks` (default 1, `"all"` = every full 7-day block of the series) replays the same program in consecutive weeks.
- **Departure rule:** every hourly sample from the departure hour to the hour of the flight's last minute (air time + deck stops) must have `wind_mps <= limits.wind_mps` and, for a flight to a mobile installation,
  `hs_m <= limits.hs_m`. The limits are `extra["limits"]` (scenario `sim.limits`) and are `assumption: true` placeholders (25 m/s, 6 m) until sourced from CAP 437 / the helicopter flight manual / operator minima; missing limits raise `Unsupported`.
- **Cancellation and rebooking:** a cancelled flight frees its slot and goes to the earliest free slot at or after its planned departure (weekday, slot, helicopter order) in any helicopter window of the same week such that the flight fits the
  window, the departure slot is inside every installation's opening hours, no slot of [t, t + n_f) is used by that helicopter, no other flight to the same installation starts in that slot, and the weather rule holds there (perfect forecast: an optimistic
  bound on recovery). Nothing already planned is moved. No slot by Friday: the flight is unmet. Deterministic for a given series.
- **Contract:** agent per helicopter (cls helicopter, domain air); `fly` (great circle, 5 min samples), `unload` (deck stop; the contract has no `deck` state), `load` (turnaround at the heliport), `wait` (held for weather), `idle`.
- **KPIs:** `flights_planned, flights_flown, flights_cancelled, flights_rebooked, flights_unmet, unmet_half_flights (2 per unrebookable flight), unmet_half_flights_net (shortfall against demand, spare half-flights netted),
  delay_h_mean (rebooked flights, hours), delay_h_max, utilisation, plan_cost, planned_variable_cost, helicopters, window_hours, flown_hours, weeks`; plus the usual `distance_km, makespan_s, wait_s` from the contract.
- **Limits:** one reference point for wind and Hs (no per-installation weather); no delays of departing flights, only cancel / rebook; no passenger bookkeeping; wind and Hs thresholds are the only operability rules (no visibility, ceiling, icing).

## Choosing
`offsim run` looks both tools up in the registry (`offsim.engines.base`): scenario `solver:` (default `pyvrp`; `none` when the engine dispatches itself) and
`engine:` (default `replay` for sea, `road` for land; `wombat` / `orbit` / `gtfs` for WIND-OM / WIND-INST / TRANSIT-REPLAY). Gate 0 accepts the classes of
the registered tools and names an unsupported class, a solver/engine that does not cover the class, or a tool that does not import (with the error).

| Problem | `solver:` | `engine:` | Gate 2 |
|---|---|---|---|
| PSV supply / ferry / crew boat with a routing plan | `pyvrp` (`pyomo`/`ampl` to certify) | `replay`; `openclsim` for weather windows and the ensemble | simulated km = plan objective (1 %) |
| Routing with time windows (VRPTW: windows per stop, service times, early arrival waits) | `pyvrp` (`pyomo` certifies up to 12 clients with `certify:`; `ampl` on Actions) | `replay` (state `wait`, events `tw_wait` / `tw_late`; `openclsim` has no windows); template `offsim/papers/_templates/vrptw/scenario.yaml` | same; the replay logs `tw_late` when service ENDS after `late`, the solvers require service to START by `late` (so with `service_s > 0` a feasible plan can still log `tw_late`) |
| Land legs on roads (trucks, vans, workers) | `pyvrp` | `road` | same |
| Wind O&M | `none` | `wombat` (needs hourly weather) | "engine dispatches itself" |
| Wind installation | `none` | `orbit` (needs hourly weather) | "engine dispatches itself" |
| Timetable replay (bus, ferry, rail) | `none` | `gtfs` | "engine dispatches itself" |
| Weekly helicopter flight program (WFPPP) | `whelp` | `air` (needs weather) | flight-hour cost and flight count of the plan, recomputed by the replay |

Opt-in blocks in scenario.yaml (all other gates are unchanged):
- `certify: {max_clients: 12, gap_tol: {value: 0.02, assumption: true}, solver: pyomo|ampl}` -> gate `1b_exact`: heuristic objective vs the exact optimum (or its
  proven bound); fails above `gap_tol`, skipped (recorded) above `max_clients`.
- `ensemble: {seeds: N, weather: {dir, point: [lon, lat], years: [y0, y1], season: DJF}}` -> `report["ensemble"]` (gate `3e_ensemble`; a failed ensemble stops the run).
  `weather: {synthetic: {n, hours}}` is TEST-ONLY: it sets `report["reportable"] = False` and ends the status with "(synthetic weather, not reportable)". A top-level
  `weather:` block (same format) feeds the single run of engines that need weather. A missing metocean directory stops at gate 0 with the `fetch_world --metocean` command.
- `validate: {entur: true}` (engine `gtfs`) -> gate `4c_entur` from `data/worlds/<w>/entur/vehicles.csv` (workflow `entur-realtime`).
Experiments use the same construction: `offsim.pipeline.build_variant(experiment, variant)` (overrides applied to the base scenario, then solve and engine of the variant).
Two engines on the same small instance must agree on deterministic KPIs within 1% (`tests/test_engine_crosscheck.py`) before either is trusted on a large one.

### Entur realtime (validation, gate 4c)
- **What:** not an engine. `offsim.transit.entur` polls Entur's Vehicle Positions GraphQL API (stdlib, no websockets; header `ET-Client-Name` from env
  `ENTUR_CLIENT_NAME`, default `astheno-offshoresimulations`; 429 honours Retry-After; at most one snapshot per 2 s) into `vehicles.csv`; run it through the
  `entur-realtime` workflow (api.entur.io is unreachable from the Claude workspace). Credit "Source: Entur AS". GraphQL field names and the units of
  `delay` / `speed` are **unverified live**.
- **Mapping:** `offsim.transit.observed.observed_trajectories(vehicles_df, t0_utc)` gives contract trajectories, one agent per service journey (cls bus, domain
  land, `drive`/`wait` from the position change between samples). `t0_utc` must be the UTC instant of the scheduled trajectory's t = 0.
Wired into `offsim run` as gate 4c_entur (scenario `validate: {entur: true}`, engine gtfs; data: workflow entur-realtime).
  journey the delay quantiles and the observed/scheduled travel-time ratio; `gate_4c(cmp)` passes when the median |median delay| <= 180 s and the median ratio
  <= 1.25 (both **assumptions**, unsourced), and fails when nothing could be judged. Record runs in `docs/TESTLOG.md`.
- **Limits:** sampled positions only (30 s polls, vehicles report at their own rate); loop routes can project to the wrong lap; a dwell counts from its first
  arrival; trips are matched by id (Entur GTFS `trip_id` = ServiceJourney id), so a feed from another date or a re-planned journey simply does not match.

## Weather data: two backends
Engines read an hourly series per weather year (`offsim.weather.years.load_years`: `hs_m`, `wind_mps`, optional `tp_s`, `dir_deg`). Two fetchers
produce the files it reads. Both write MET Norway NORA3 data (CC BY 4.0, credit "MET Norway (CC BY 4.0)"); neither runs in the Claude workspace
(thredds.met.no is blocked), so both run on a VM or Actions and come back as files or a release.

| | `legacy` (default) | `metocean-api` |
|---|---|---|
| Code | `offsim.weather.fetch.subset`, called by `fetch_world --metocean START HOURS` | `offsim.worlds.metocean_api` (`fetch_world --metocean-backend metocean-api`, or its own CLI) |
| Output | a gridded box, regular lon/lat, int16: `metocean/<stamp>_<h>h_<dataset>.nc` | one cell per file: `metocean_point/pt_<product>_<YYYYMM>.nc` (dims time, lat 1, lon 1) + `manifest.json` |
| Good for | maps, particles, currents (the visual layer); one period | many winters at one site (ensembles, `weather: {dir, point, years, season}`) |
| Unit of work | one stage per dataset, one wall budget | one request per product-month; 24 winters of DJF = 144 |
| Timeout | SIGALRM stage budget (cannot interrupt a blocked netCDF read) | each unit in a subprocess killed after `--unit-timeout` (default 600 s) |
| Resume | none: a killed run starts over | files are written atomically and re-validated on start; only missing or invalid units are fetched |
| Failures | `manifest.errors`, one entry per stage | per unit in `manifest.json` (status, attempts, error, permanent) and mirrored into `errors` |
| Currents | yes (`norkyst_v3`) | no (not read by `load_years`) |
| Status | `verified_source` only, never opened live | catalog `wired`: proven offline on fixtures, not live |

### Variable mapping (metocean-api 1.1.14 -> stored name -> what `load_years` builds)
| Product (`TimeSeries(product=...)`) | Library column | Stored as | Unit | Becomes | Direction convention (library) |
|---|---|---|---|---|---|
| `NORA3_wave_sub` | `hs` | `hs` | m | `hs_m` | n/a |
| `NORA3_wave_sub` | `tp` | `tp` | s | `tp_s` | n/a |
| `NORA3_wave_sub` | `thq` | `thq` | degrees | `dir_deg` | OCEANIC (towards), as the library declares it; the file's own `standard_name` was not seen live |
| `NORA3_wind_sub`, `height=[10]` | `wind_speed_10m` | `wind_speed` | m/s | `wind_mps` | n/a |
| `NORA3_wind_sub`, `height=[10]` | `wind_direction_10m` | `wind_direction` | degrees | not read | METEOROLOGICAL (from) |
| `NORKYST800_V3` (not fetched here) | `u_eastward`, `v_northward` | `u`, `v` (legacy names) | m/s | not read | n/a |

The wind request pins `height=[10]`: without it the library returns `wind_speed_10.0m`, `wind_speed_20.0m`, ... (all heights), and it refuses
`start_time` / `end_time` with a time part for these products (`'YYYY-MM-DD'` only). Any column not in this table raises `VariableMappingError`;
nothing is renamed by guess. The library rounds values to 0.01.

### Fetch 24 Bergen winters (resumable)
```
pip install metocean-api
python -m offsim.worlds.metocean_api fetch --world bergen-ncs --point 3.0,60.6 --years 2000-2023 --season DJF
```
- Writes `data/worlds/bergen-ncs/metocean_point/` (override with `--out`). Winter Y is Dec Y .. Feb Y+1, so this is Dec 2000 .. Feb 2024; 144 units.
  The point 3.0 E, 60.6 N is an open-sea cell inside the `bergen-ncs` box near the Oseberg and Troll fields: an **assumption** (any cell inside the
  box and over water works; the loader refuses land cells and cells more than 30 km away). A directory holds one point: another point needs another `--out`.
- Time: **unmeasured**. Each unit costs about 4 s of Python start-up plus one monthly point read over OPeNDAP, expected 10 to 60 s, so roughly 1 to 2.5
  hours in total. The line `[k/144] nora3_wave:200012: ok (N s ...)` gives N for the first unit; multiply by 144. `--max-runtime-min 100` stops cleanly
  inside a job time limit.
- Resuming looks like this, and a first run says `STARTING: 0/144 units on disk` instead:
  `RESUMING: 37/144 units already on disk and valid (skipped); 107 to fetch`. Run the same command again after a kill, a timeout or a stop; valid
  files are never fetched twice. `python -m offsim.worlds.metocean_api status --world bergen-ncs` shows what is on disk without fetching.
- Exit code 0 only when all 144 are valid; 2 when some are missing (the failures are in `manifest.json`, `units`). Six failures in a row stop the run.
- Use it: `weather: {dir: data/worlds/bergen-ncs/metocean_point, point: [3.0, 60.6], years: [2000, 2023], season: DJF}`. A run is reportable only if
  the series are real, so check the manifest says 144 ok before dropping the synthetic block.
- Inside a world fetch: `python -m offsim.worlds.fetch_world --world bergen-ncs --out world --metocean-backend metocean-api --metocean-point 3.0,60.6 --metocean-years 2000-2023`.
  The fetch-world workflow does not expose these flags yet (a workflow change, not made in this package) and an Actions runner starts empty each time,
  so on Actions the whole fetch must fit one job: use `--max-runtime-min`, and carry `metocean_point/` forward between runs (cache or release) to resume.
- Cross-check windows with `python -m offsim.worlds.metocean_api stats --world bergen-ncs --point 3.0,60.6 --years 2000-2023`: metocean-stats runs in a
  **child process** (it requires `lmoments3`, GPL-3.0, so it is never imported here). Do not install metocean-stats in the fetch environment: it pulls
  `pydap`, which can change which backend xarray picks for OPeNDAP URLs.

Not proven offline (first live run must check, then log it in `docs/TESTLOG.md` and promote the catalog entries to `tested`): that the live monthly files
have the structure the fixtures assume (rotated grid `rlat`/`rlon` for waves, `height`/`y`/`x` for wind, 2D `longitude`/`latitude`); that they are hourly
and whole-month (otherwise every unit fails loudly with the missing-hours count); that the 2000 to 2024 months exist on the server; the time per unit; the
`HTTP.TIMEOUT` lines in the child's `.dodsrc` (the subprocess kill is the guarantee, not these); direction conventions of `thq`.
