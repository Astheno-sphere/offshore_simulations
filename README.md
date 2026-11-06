# Offshore Simulations

**Reproduce offshore logistics research on real Norwegian geography, check every number, then show it.**

[![tests](https://github.com/Astheno-sphere/offshore_simulations/actions/workflows/tests.yml/badge.svg)](https://github.com/Astheno-sphere/offshore_simulations/actions/workflows/tests.yml)
· MIT · Python 3.12+ · Node 22 · by [Arshad Akhtar Abbasia](https://www.linkedin.com/in/arshad-abbasiaa/) (MSc Sustainable Energy Logistics, Molde University College)

Operations-research papers on offshore supply vessels (PSV), ferries, helicopter crew transport, worker
routing and offshore wind installation and maintenance report results as tables. This repository turns a
paper into a running simulation on a real map (the Oslofjord, the fields west of Stavanger), checks the
simulation against physics and against the paper's own numbers, and only then renders it as a short 2.5D
video. Reproduction comes first, pictures come last.

## How it works

```
 paper ──► paper-extract ──► scenario.yaml ──► SOLVE (PyVRP · OR-Tools · Pyomo/HiGHS)
                                                   │ plan
 world (OSM coast · Sodir · Kartverket · AIS) ────►│
                                                   ▼
                                     SIMULATE in time (SimPy: sailing, queues, time windows)
                                                   │ trajectory  ◄── the one table everything shares
                                                   ▼
                                     sim-corrector: 4 gates ── fail ──► stop, report why
                                                   │ pass
                                                   ▼
                    visual-director ──► scene ──► render (deck.gl draft here, 1080p on Actions)
                                                   ▼
                                     sim-narrator ──► caption + post (numbers from the report only)
```

**The trajectory contract** ([`offsim/contract.py`](offsim/contract.py)): one row per vessel per moment:
where, when, doing what, how much on board. Solvers and simulators write it, renderers only read it.
`validate` rejects time running backwards, impossible speeds, teleports, moving while loading, overloads and
sea legs that cross land. A rendering bug cannot change a result; a result bug cannot reach a video.

**The four corrector gates:** (1) the plan is feasible when re-checked outside the solver, (2) the
replayed simulation equals the solver's own objective, (3) the trajectory passes the contract, (4) our KPIs
match the paper's reported values within a stated tolerance. On its first run this caught a PyVRP index
change that produced a plan 35% longer than the solver's objective and an overloaded vessel, plus an
unfair baseline. Both would have looked fine on screen.

## Skills (Claude Code)

| Skill | What it does |
|---|---|
| [`offsim-foundations`](skills/offsim-foundations/SKILL.md) | Router and conventions: which skill for which request |
| [`paper-extract`](skills/paper-extract/SKILL.md) | Paper → `scenario.yaml`; every value has a page source or an explicit assumption flag |
| [`sim-corrector`](skills/sim-corrector/SKILL.md) | The four gates; refuses to pass anything unchecked |
| [`visual-director`](skills/visual-director/SKILL.md) | Motion grammar: one accent, live clock, measured KPIs, house palette, LinkedIn formats |
| [`sim-narrator`](skills/sim-narrator/SKILL.md) | Captions and posts from the corrector's report only: *reproduced*, *re-run under assumptions*, or *did not reproduce* |
| [`opt-model`](skills/opt-model/SKILL.md) | Exact LP/MIP models (Pyomo, HiGHS); certifies heuristic plans on small instances |
| [`tool-scout`](skills/tool-scout/SKILL.md) | Finds, vets and records tools in the catalog |

## What the videos look like

Agents are characters, not blocks: cartoony ships, ferries, helicopters, boats and workers (Fluent Emoji,
MIT) that turn to face their heading, or our own low-poly 3D models (PSV, ferry, platform, wind turbine,
made with Blender in this repo). Vessels follow sea lanes computed from the real coastline, so the land
check passes on real geography. First real world fetched: the Oslofjord (4,753 coastline ways).

```bash
python -m offsim.worlds.fetch_world --pull oslofjord
python -m offsim.examples.oslofjord_demo --out out/oslofjord     # synthetic timetable, real coastline
python offsim/render_deck/render.py --scene out/oslofjord/scene.json --out out/oslofjord/still.png --format square --still --at 5400
```

## Tool catalog

[`docs/TOOLS.md`](docs/TOOLS.md) lists 70+ open-source tools, datasets, MCP servers and skills across 15
layers: world data, AIS traffic, metocean (MET Norway NORA3), solvers, weather routing, simulation,
offshore wind models (NREL WOMBAT, ORBIT), emissions, rendering, video, CC0 3D assets, maritime UI design,
MCP connectors, Claude skills and benchmark papers. Each entry has its licence, whether it was tested here,
where it runs and when we need it. Search it:

```bash
python tools/catalog_build.py --find helicopter
python tools/catalog_build.py --now
```

## Quick start

```bash
pip install -r requirements.txt
python -m pytest -q tests                                   # contract, replay, exact-vs-heuristic, catalog
python -m offsim.examples.toy_fjord --out out/toy           # synthetic fjord: solve → simulate → validate → scene
pip install playwright                                      # renderer needs Node 22, ffmpeg, Chrome
python offsim/render_deck/render.py --scene out/toy/scene.json --out out/toy/draft.mp4
```

Real worlds are fetched by GitHub Actions (workflow **fetch-world**) and published as releases, then pulled:
`python -m offsim.worlds.fetch_world --pull oslofjord`. Final videos: workflow **render**.

## Status

| Part | State |
|---|---|
| Trajectory contract, SimPy replay, PyVRP adapter, exact MIP check | runs, tested (CI) |
| Four agent skills + router + tool scout | written |
| Worlds | Oslofjord fetched and used; North Sea off Stavanger configured |
| Sea lanes from the coastline | runs, tested (real Oslofjord demo passes the land check) |
| Renderer (deck.gl, headless) | sprites, glTF models, trails, overlays tested; style v0 |
| Intro animation (Manim), 3D inspection (PyVista) | run here |
| First reproduced paper | next ([roadmap](docs/ROADMAP.md)) |

## Repository map

| Path | Contents |
|---|---|
| `offsim/` | the package: `contract`, `sim/replay`, `solve/pyvrp_adapter`, `scene`, `worlds/`, `render_deck/`, `papers/`, `examples/` |
| `skills/` | Claude Code skills (also a plugin: `.claude-plugin/plugin.json`) |
| `catalog/tools.yaml` | tool catalog source; `docs/TOOLS.md` is generated |
| `docs/` | [framework](docs/FRAMEWORK.md), [roadmap](docs/ROADMAP.md), [tools](docs/TOOLS.md) |
| `.github/workflows/` | tests, fetch-world, render |

## Data credits

© OpenStreetMap contributors (ODbL) · Source: Norwegian Offshore Directorate (NLOD) · Kartverket ·
Kystverket (NLOD) · MET Norway. Data is fetched at use and never committed.

Sister repository: [computational_Logistics](https://github.com/Astheno-sphere/computational_Logistics)
(transport planning under deep uncertainty; source of the house style, `opt-model` and the coastline code).

**Keywords:** offshore logistics, platform supply vessel, PSV routing, offshore helicopter routing, crew
change, ferry scheduling, offshore wind installation, operations and maintenance, vehicle routing problem,
maritime simulation, discrete-event simulation, AIS, Norway, Norwegian continental shelf, Oslofjord, Stavanger,
reproducible operations research, logistics visualisation.
