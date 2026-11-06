---
name: offsim-foundations
description: Entry point for offshore_simulations - reproduce offshore and maritime logistics papers (PSV supply, ferries, helicopters, crew/worker routing, offshore wind installation and O&M) on real Norwegian geography, validate them, and turn them into 2.5D videos and posts. Routes each request to the right skill and states the shared conventions (WGS84 in, metres, seconds, contract before pictures).
---

# offshore_simulations: router and conventions

| Request is about | Use |
|---|---|
| A paper to reproduce, simulate or visualise | `paper-extract` → `python -m offsim run <scenario.yaml>` → `sim-corrector` reads the report |
| Routing/scheduling solve (VRP, PDP, multi-depot) | `offsim/solve/pyvrp_adapter.py`; exact check on small cases with `opt-model` |
| An LP/MIP from a paper; proving a plan optimal | `opt-model` |
| "Results look wrong", any check before showing | `sim-corrector` |
| A video, still or LinkedIn format of a validated result | `visual-director` → `storyboard.yaml` → `python -m offsim story` (`--dry-run` first) |
| Motion graphics: equation intro, KPI count-up card, camera moves, line-art drawing | `visual-director` (Motion section); engines: Manim, HyperFrames + GSAP, deck.gl |
| Caption, post, README entry for a result | `sim-narrator` |
| Which tool, dataset, MCP server or skill exists for X; add a new one | `tool-scout` (catalog: `catalog/tools.yaml`, `docs/TOOLS.md`) |
| Map data for a study area | `offsim/worlds/` (fetch on Actions, `--pull` here) |
| Terrain, bathymetry, hillshade, isobaths (map depth) | `offsim/worlds/depth.py` (defined) · spec `docs/VISUAL_SPEC.md` §2 |
| Wind, waves, currents: data, operability, on-screen | `offsim/weather/` (fetch, operability, visual) · spec §3 |
| Cinematic camera, vessel motion, look | `offsim/cinema/` (rules, camera, vessel, look) · spec §4–6 |
| What is pulled vs listed; where each stage lives | `docs/OPS_MAP.md`, `docs/TOOLS.md` matrix |

## The flow (never skip a step)
paper → `scenario.yaml` → **`offsim run`** (gate 0 provenance → solve → gate 1 plan → replay → gate 2 replay=plan →
gate 3 contract → gate 4 paper → `report.json`) → `storyboard.yaml` → **`offsim story`** (refs into the report only) → video → post.
`offsim.scene.build_scene` refuses a trajectory that failed `validate`; nothing reaches a video unchecked.

## Conventions
- Coordinates in: WGS84 lon/lat. Distances: metres (haversine for checks). Time: seconds from scenario start.
- Every parameter has a source (page/table) or an explicit `assumption: true`.
- Status words for results: **reproduced**, **re-run under assumptions**, **did not reproduce**.
- Data is fetched, never committed; credits travel in each world's `manifest.json` and on screen.
- GPL tools (Blender, VISIR-2, SIMROUTE) run as separate processes; never import them into MIT code.
- Where things run: solve, simulate, validate, drafts here; data fetch and 1080p renders on GitHub Actions.
