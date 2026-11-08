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
               offsim.physics (section fluid, ocean surface, streaks) ─► motion/diptych (section + map, one clock)
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

## Visual grade
See `docs/STYLE_REFERENCE.md`: the section + map diptych, physics-driven texture, real-data map, editorial frame,
method line from provenance. Palette data in `offsim/cinema/look.py` (`PALETTES`).

## What is deliberately not here
Hand-tuned "looks plausible" motion with no source number; any tool nobody calls (catalog demotes it to `watch`);
LLM-generated values in a scenario; renders of results that failed a gate.
