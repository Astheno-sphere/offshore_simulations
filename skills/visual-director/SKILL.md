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
| `lineart` | CAD-style vector linework (feature edges of our models), plan view, rotated by heading, crisp at any zoom | `offsim/assets/lineart/*.json` from `python -m offsim.assets.lineart` |
| `dot` | plain circles (debug) | — |
Sites with a `kind` that has a model (`platform`, `wind_turbine`) render as 3D models (`site_mode: model`) or line art (`site_mode: lineart`); others as columns.
Models are exaggerated on purpose (`site_model_scale`, `agent_model_scale`): at fjord zoom a true-scale
50 m platform is 3 px. Say "not to scale" on screen when it matters. Override per render: `--agents model`.
Assets load asynchronously; `render.py` warms up before capture (missing sprites in a frame = raise the warm-up).

## Motion: storyboard → shots → video
`offsim/papers/<id>/storyboard.yaml` lists shots; `python -m offsim story <storyboard> --dry-run` resolves every
number against `report.json`, builds each shot's source and checks it headlessly (renderer `--check`,
`hyperframes lint`) without rendering. Drop `--dry-run` to render shots and crossfade them with ffmpeg.
| Shot | Engine | Use |
|---|---|---|
| `equation` | Manim (LaTeX) | the paper's objective and key constraint, written on |
| `map` | deck.gl | the run on the real coast; `camera.keys` = eased fly-in / push / pull-back; `agents`/`sites` modes |
| `card` | HyperFrames + GSAP | KPI count-ups and the status word; template `offsim/motion/templates/kpi_card` |
Card values are `report:` refs (with `scale`, `decimals`, `unit`); literals are refused. A run that failed
gates 0–3 cannot get a storyboard. Next engines in the catalog: Vivus (line-by-line SVG drawing), Motion
Canvas (vector diagram explainers), Lottie (icon animation).

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
