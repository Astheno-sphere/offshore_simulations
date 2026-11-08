# Architecture

One loop: **papers in → gap found → experiment run under real weather → validated against real traffic → visualised.**
Everything is a module behind an interface; tools are swappable, numbers are not.

```
 L6 RESEARCH   offsim.research  feed ─► tags ─► gaps.yaml ─► experiment.yaml
                    │                                             │
 L0 DATA       offsim.feed  offsim.worlds (OSM, depth, coast, Overture)  offsim.weather (NORA3, NorKyst)
               offsim.traffic (AIS: HAIS, BarentsWatch)          ◄── all fetched on Actions, pulled here
                    │                                             │
 L1 SOLVE      offsim.solve   pyvrp │ pyomo+HiGHS │ ampl (Actions/laptop) │ ortools (later)   Problem ─► Plan
                    │
 L2 SIMULATE   offsim.engines replay (SimPy) │ openclsim │ wombat │ orbit                  Plan ─► SimResult
                    │                                              (trajectory contract)
 L3 ENSEMBLE   offsim.montecarlo  N weather years × seeds × variants (common random numbers) ─► distributions
                    │
 L4 VALIDATE   gates 0–4 (offsim.pipeline, offsim.contract) + AIS calibration (offsim.traffic) ─► report.json
                    │                                   scene.py refuses anything that failed
 L5 PRESENT    offsim.scene ─► render_deck (deck.gl)  │  motion (Manim, HyperFrames)  │  cinema (camera, vessel)
               offsim.physics (section fluid, ocean surface, streaks) + motion/mappanel ─► section + map film (tools/section_film.py)
               offsim.publish (muse.ai)
```

**Dependency rule:** a layer calls only layers below it. L5 reads `report.json` and trajectory files, never a
solver or engine. L2 never fetches data. Breaking the rule is a bug: `tests/test_architecture.py` checks imports.

## Interfaces (code: `offsim/engines/base.py`)

| Object | Produced by | Holds |
|---|---|---|
| `Problem` | pipeline, from scenario.yaml | class, nodes, sea-lane distance matrix, demand, fleet, windows, class extras |
| `Plan` | any `Solver` | routes per agent, objective + unit, bound (exact), status |
| `World` | `offsim.worlds` | land geometry, sea-lane legs, ports, data manifest |
| `WeatherSeries` | `offsim.weather` | hourly `t, hs_m, wind_mps, …`, dataset + year |
| `SimResult` | any `Engine` | trajectory contract, agents, events, KPIs, seed, weather source |
| `Ensemble` | `offsim.montecarlo` | runs table, quantiles, paired comparisons → `report["ensemble"]` |

Tools register by name (`register_solver`, `register_engine`) and are imported lazily, so a missing optional
tool breaks only itself. `python -c "from offsim.engines import available; print(available())"` shows what runs here.

## Where each piece runs

| Piece | Here (Claude workspace) | GitHub Actions | Your laptop |
|---|---|---|---|
| PyVRP, Pyomo+HiGHS, OpenCLSim, WOMBAT, ORBIT, SimPy, Monte Carlo | ✔ | ✔ | ✔ |
| AMPL (academic licence) | ✘ binary download blocked | ✔ `solve.yml`, secret `AMPL_LICENSE_UUID` | ✔ via `tools/ampl_mcp` |
| OSM / Overture / Kartverket / NORA3 / AIS download | ✘ | ✔ `fetch-world.yml` → release → `--pull` | ✔ |
| Paper feed (OpenAlex, Crossref, arXiv, NVA, Brage) | read-only via WebFetch | ✔ `papers.yml` weekly | ✔ |
| Draft stills, dry runs | ✔ | ✔ | ✔ |
| 1080p / Blender renders | ✘ | ✔ `render.yml`, `film.yml` | ✔ |

## Research loop (L6 → L5)

1. **Feed** (`offsim.feed`, weekly `papers.yml`): new papers on offshore/maritime/transport OR → `papers/feed.jsonl`.
2. **Tag** (`offsim.research.tags`): rules first (keywords → class/mode/region), LLM second with a confidence;
   tags only route work, they are never a reported value.
3. **Gap table** (`offsim.research.gaps`): count papers per (class × mode × region × uncertainty). Empty or thin
   cells next to well-covered ones are gaps: *no-norway, no-uncertainty, no-code, no-validation, contradiction*.
4. **Reproduce first**: `paper-extract` writes scenario.yaml from the base paper; `offsim run` must reach
   `reproduced` or `re-run under assumptions` before any gap experiment uses it.
5. **Experiment** (`offsim.research.experiment`): variants × NORA3 years × seeds, decided by a pre-registered rule
   (`supported | not supported | inconclusive`). The decision rule is written before the run.
6. **Visualise** what passed: map shot (deck.gl) for the operation, distribution shot (fan chart / P10-P90 band)
   for the finding, card shot for the headline number. Numbers only from `report:` refs.

## Agents (skills/) mapped to layers

| Skill | Layer | Job |
|---|---|---|
| `research-scout` | L6 | run the feed, tag, update gaps.yaml, propose experiments |
| `paper-extract` | L6→L1 | paper → scenario.yaml with page/table sources |
| `opt-model` | L1 | exact model (Pyomo, or AMPL `.mod` for Actions/laptop) |
| `sim-engineer` | L2–L3 | choose engine, build the experiment, run the ensemble |
| `sim-corrector` | L4 | gates, AIS calibration, paper comparison; can stop anything |
| `visual-director` | L5 | storyboard + style; refuses unvalidated reports |
| `sim-narrator` | L5 | captions/post from report refs only |
| `tool-scout` | all | keeps `catalog/tools.yaml` honest (evidence or demote) |

## Worlds v2

A world is no longer a hand-written sea bbox: any place in Norway, for any mix of modes. Code: `offsim/worlds/place.py`
(resolve, spec I/O) and `offsim/worlds/fetch_world.py` (fetch). Data comes in through the `fetch-world` workflow
(inputs `place`, `modes`, `radius_km`) or on a laptop; this workspace cannot reach the hosts.

```yaml
version: 2
name: alesund                          # slug = offsim/worlds/<name>.yaml = release world-<name>
place: {name: Ålesund, lon: 6.15, lat: 62.47, source: "approx centre (Claude, unverified); refine via stedsnavn"}
bbox: [west, south, east, north]       # WGS84; from the centre and radius with a cos(lat) correction
modes: [sea, road, bus]                # any non-empty subset of sea | road | bus | walk | air
layers: [land, coast, sealanes, quays, ferry, roads, gtfs]   # derived from modes (place.layers_for)
osm_land: true                         # v1 keys (sodir_keywords, depth, manual, ais_*, osm_pbf_url) pass through
```

| Mode | Layers | Source |
|---|---|---|
| (always) | `land` | OSM coastline (Overpass) |
| sea | `coast`, `sealanes`, `quays`, `ferry` (+ `depth` on request) | OSM, `offsim.worlds.sealanes`, EMODnet / Kartverket DTM |
| road, walk | `roads` | OSM via Geofabrik extract (`--osm`) |
| bus | `roads` + `gtfs` | OSM + Entur national aggregated GTFS (NLOD), clipped by `offsim.transit.gtfs.clip` (`--gtfs`) |
| air | `helipads` | OSM `aeroway=helipad|heliport` (aerodromes are not an OSM layer yet) |

Resolution (`place.resolve`): `"lon0,lat0,lon1,lat1"` bbox, else a built-in gazetteer key (about 20 logistics places,
case- and diacritics-insensitive, centres flagged *approx, unverified*), else the Kartverket stedsnavn API
(CC BY 4.0, unverified live). Clients take an injectable `fetch(url) -> bytes` and are tested against fixtures.

`load_world_spec(path)` returns a v2-normalised dict for any YAML: a v1 file (no `version`) becomes `modes: [sea]`
with `place` taken from the bbox centre, so existing worlds keep working unchanged.

CLI: `python -m offsim.worlds.fetch_world --place Ålesund --modes sea,road,bus --radius-km 20`. Modes imply flags
(`plan_layers`): road/walk/bus/air => `--osm`; bus => `--gtfs`. `--place` writes `data/worlds/<slug>/world.yaml` and
`offsim/worlds/<slug>.yaml` if absent; the spec is not data and may be committed, the fetched package is never committed.

## Visual grade
See `docs/STYLE_REFERENCE.md`: the section + map diptych, physics-driven texture, real-data map, editorial frame,
method line from provenance. Palette data in `offsim/cinema/look.py` (`PALETTES`).

## What is deliberately not here
Hand-tuned "looks plausible" motion with no source number; any tool nobody calls (catalog demotes it to `watch`);
LLM-generated values in a scenario; renders of results that failed a gate.

## Data intake rules (OSM, your GeoJSON, papers, Entur)
Smallest correct source wins; every layer carries `src` + licence in `<layer>.source.json` / the world manifest.
1. **Your GeoJSON first** when you have it (municipality roads, NVDB exports, port layouts, digitised stops, QGIS files):
   `python -m offsim.worlds.user_layers --world <w> --kind roads|quays|stops|sites|buildings|... --file f.geojson
   --src "..." --licence ...`. Validated (WGS84, geometry, required tags), clipped, optionally simplified; engines read
   it unchanged. A few MB instead of the 1.3 GB national OSM extract.
2. **OSM** for what you don't have: fetch-world on Actions downloads the extract once, cuts it to the world bbox and
   publishes only the clipped layers in the release (`osm_pbf_url` in the world YAML for a smaller regional extract).
3. **Paper data** (timetables, headways, stop lists, site coordinates): `timetable.yaml` -> `offsim.transit.from_paper.to_gtfs`
   (every value `{value, src: "p.X Table Y"}` or `assumption: true`); sites/customers via a `sites` user layer.
4. **Entur** (NLOD / open, credit "Source: Entur AS"): national GTFS for schedules (fetch-world `--gtfs`), Vehicle
   Positions for observed runs (`entur-realtime` workflow -> gate 4c), Journey Planner for departures. Header
   `ET-Client-Name` always. Entur's Journey Planner MCP and Transit Data MCP can be added as Claude connectors.
5. Real data beats paper data for *validation*; paper data defines the *reproduction*. Never mix silently: the
   report says which layer came from where.
