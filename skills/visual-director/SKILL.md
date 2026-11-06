---
name: visual-director
description: Motion grammar for offshore_simulations videos - turns a validated trajectory into a 2.5D animated scene (camera fitted to the study area, one accent for the thing the paper is about, state halos for waiting and loading, live clock and measured KPIs) in the house palette, and renders drafts here and 1080p finals on GitHub Actions. Use when a corrector-approved simulation needs a video, still or LinkedIn format.
---

# visual-director

Extends the plate style of computational_Logistics (`skills/visual-narrative`) from plates to motion. Same palette and voice (`offsim/style.json`, copied
from `plate.py`): ink ground, paper linework, **one** accent.

## Pipeline
`offsim.scene.build_scene(...)` (refuses invalid trajectories) → `scene.json` →
`python offsim/render_deck/render.py --scene ... --format draft|square|vertical|wide [--still]`.
Draft (640×360) and stills render in this workspace (software WebGL, ~8 frames/s at draft).
Finals: run workflow `render` (Actions), download the MP4 from the release it creates.

## Agents and sites: characters, not blocks
`style.json` → `agent_mode`:
| Mode | Looks like | Source |
|---|---|---|
| `sprite` (default) | cartoony 3D-look billboards that flip to face their heading | `offsim/assets/sprites/` (Fluent Emoji, MIT), class → sprite in `style.sprites` |
| `model` | low-poly glTF oriented along the course | `offsim/assets/models/*.glb` (ours, `make_models.py`), class → model in `style.models` |
| `dot` | plain circles (debug) | — |
Sites with a `kind` that has a model (`platform`, `wind_turbine`) render as 3D models; others as columns.
Models are exaggerated on purpose (`site_model_scale`, `agent_model_scale`): at fjord zoom a true-scale
50 m platform is 3 px. Say "not to scale" on screen when it matters. Override per render: `--agents model`.
Assets load asynchronously; `render.py` warms up before capture (missing sprites in a frame = raise the warm-up).

## Sea lanes
Vessels must route around land: `offsim.worlds.sealanes.SeaGraph` (grid + clearance + string pulling),
feeding `legs` to replay and `dist` to the solver. Quays snapped to water are reported (`sea.snap_m`);
put moves over ~200 m in the caption or fix the quay coordinates.

## Grammar (v0, to be refined per video like plates 01-04)
1. One question as the kicker, one idea as the title; the accent is the optimised plan or the one
   agent the paper is about. Baseline in paper, never a second accent.
2. Show the cause: the coast, the field layout, the weather window. Use world data, not decoration.
3. Time is explicit: clock always on; waiting and loading are halos in their state colour.
4. Numbers on screen come only from `kpi_track`, built from `offsim.contract.kpis`.
5. Credit line always: paper DOI, data sources with licence (Sodir NLOD, Kartverket, Kystverket,
   © OpenStreetMap contributors ODbL), and "SYNTHETIC" when any geometry or demand is invented.
6. Formats: square 1080², vertical 1080×1350 for LinkedIn; wide 1920×1080 for talks.

## Not yet (deliberately)
Blender hero shots (`bpy` 5.2 works here: Workbench ~1 s/frame, Cycles CPU
~4 s/frame at 640×360; finals belong on Actions), Remotion captions (works here with system Chrome), Manim intros for the model's maths (works here).
Add each only when a paper's story needs it.
