---
name: offsim-foundations
description: Entry point for offshore_simulations - reproduce offshore and maritime logistics papers (PSV supply, ferries, helicopters, crew and worker routing, offshore wind installation and O&M, bus and transit timetables) on real Norwegian geography, test them under real weather, validate them, and turn validated results into videos and posts. Routes each request to the right skill and states the shared conventions.
---

# offshore_simulations: router and conventions

## Request routing
| Request is about | Use |
|---|---|
| A paper PDF to reproduce, simulate or visualise | `python -m offsim paper <pdf>` (draft), then `paper-extract` |
| Scenario values, timetable, page sources | `paper-extract` |
| Running the pipeline, reading gates, "results look wrong" | `sim-corrector` (reads `report.json`) |
| Gap, experiment, weather years, variants, decision | `research-scout` (gap), `sim-engineer` (experiment, ensemble) |
| Exact LP/MIP, bound on a heuristic plan | `opt-model` (Pyomo here; AMPL on Actions or laptop) |
| Storyboard, map / section / findings / card / equation shots, film | `visual-director`, then `python -m offsim story` |
| Caption, post, README entry for a result | `sim-narrator` (from `report:` refs only) |
| Tool, dataset, MCP server, skill: does it exist, add it | `tool-scout` (`catalog/tools.yaml`, `docs/TOOLS.md`) |
| Your GeoJSON, OSM, Entur, weather data | Data intake below; CLI `offsim world`, `layer`, `timetable`, `entur` |
| Literature feed, tags, gaps | `research-scout` (CLI `offsim feed`, `tag`, `gaps`) |

## The flow (never skip a step)
1. **Paper PDF** -> `python -m offsim paper <pdf>` writes a DRAFT with page evidence. Drafts never run.
2. **`paper-extract`** confirms every candidate value with its page, chooses solver and engine keys, writes
   `scenario.yaml` (+ `timetable.yaml` for networks).
3. **`python -m offsim run <scenario.yaml>`**: gates 0, 1, 1b, 2, 3, 3e, 4, 4b, 4c, stop at the first failure, write
   `report.json`. Gate 0 always runs; 1b, 3e, 4b, 4c run when the scenario sets `certify:`, `ensemble:`,
   `validate: {ais: true}` or `validate: {entur: true}`. Read by **`sim-corrector`**.
4. **Gap or question** -> `experiment.yaml`, decision written before the run, `python -m offsim experiment <yaml>` ->
   `report["ensemble"]`. Owner: **`sim-engineer`** (gap confirmed by `research-scout`).
5. **Storyboard**: `storyboard.yaml` with shots map, section, findings, card, equation. Owner: **`visual-director`**.
   Every number is a `report:` ref.
6. **`python -m offsim story <storyboard> --dry-run`** checks every ref and shot headlessly, then
   `python -m offsim story` renders the film. Caption and post: **`sim-narrator`**.

`offsim.scene.build_scene` and `offsim story` refuse any run whose report failed a gate.

## Engine per problem class (`docs/ENGINES.md`)
| Problem | Solver (plan) | Engine (simulate) | Runs |
|---|---|---|---|
| CVRP / VRPTW heuristic plan | `pyvrp` (default) | `replay` (gate 2) | here |
| Exact bound, small instance | `pyomo` (HiGHS) | none | here |
| Exact bound, `.mod` paper or large instance | `ampl` | none | Actions (`solve.yml`), laptop (`tools/ampl_mcp`) |
| PSV, ferry, crew boat with weather windows, ensemble | `pyvrp` | `openclsim` | here |
| Land legs on roads: trucks, vans, workers | `pyvrp` | `road` (OSM roads, fetched) | here, after fetch |
| Bus, ferry, rail timetable | none (timetable is the plan) | `gtfs` | here, Entur GTFS |
| Offshore-wind O&M | none | `wombat` | here |
| Offshore-wind installation | none | `orbit` | here |

Pick the engine whose assumptions match the paper, not the one that looks best. An engine that cannot represent a
feature raises `Unsupported`: report it at gate 0, never approximate.

## Data intake (smallest correct source wins)
1. **Your GeoJSON first**: `offsim.worlds.user_layers` (`--kind roads|quays|stops|sites|...`, with `--src` and `--licence`).
2. **OSM** for what you lack: `fetch-world` on Actions -> release -> `python -m offsim.worlds.fetch_world --pull <world>`.
3. **Paper data** (timetables, headways, stops, site coordinates): `timetable.yaml`, each value with a page source.
4. **Entur**: schedules via fetch-world `--gtfs`; observed runs via the `entur-realtime` workflow for gate 4c.

Paper data defines the reproduction; real data validates it. Each layer carries `src` and licence. Never mix silently:
the report says which layer came from where.

## Where things run
- **Here** (Claude workspace): PyVRP, Pyomo + HiGHS, OpenCLSim, WOMBAT, ORBIT, SimPy, Monte Carlo, drafts, dry runs,
  stills. Cannot reach Kartverket, Kystverket, Sodir, Overpass, MET Norway, Entur or the AMPL download.
- **GitHub Actions**: `fetch-world`, `solve` (AMPL, secret `AMPL_LICENSE_UUID`), `papers` (weekly feed),
  `entur-realtime`, `render` and `film` (1080p).
- **Laptop**: AMPL through `tools/ampl_mcp`, any data fetch, anything Actions can do.

Results come back as releases or artifacts; pull them here with the `--pull` commands.

## Conventions
- Coordinates in WGS84 lon/lat. Distances in metres. Time in seconds from scenario start.
- Every scenario value has a `src` (page or table) or `assumption: true`; assumptions are printed on screen.
- Run status: **reproduced**, **re-run under assumptions**, **did not reproduce**.
- Experiment decision: **supported**, **not supported**, **inconclusive**.
- Synthetic weather (`synthetic_years`) is test-only and never reportable: it is labelled **(synthetic weather, not reportable)**.
- Numbers on screen come only from `report:` refs.
- Data is fetched, never committed. GPL tools run as separate processes.
- CLI overview: `offsim resume` shows state; `offsim tools` lists the catalog.
