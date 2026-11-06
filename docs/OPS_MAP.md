# Ops map — the grand view

Every stage of the flow: what code does it, which tools are **pulled** (in the repo, with evidence) vs only
**listed** (catalog), which **inspector** guards it, and which **rules** apply. Live counts per layer:
`docs/TOOLS.md` → "Pulled vs listed". Audit history and open risks: `docs/AUDIT.md`.
Legend: ✅ built and tested · 🟨 defined (interface in code, not built) · ⬜ planned · 🔒 inspector.

```
 paper ─► scenario.yaml ─► offsim run ──────────────────────────────────────────► report.json
            │                 G0 provenance ─ solve ─ G1 plan ─ replay ─ G2 replay=plan ─ G3 contract ─ G4 paper
 world ─────┘   (fetch-world on Actions → release → --pull)                                │
 weather ───────(fetch-world metocean, 🟨)──────────────────────────────────────────────────┤
                                                                                           ▼
 storyboard.yaml ─► offsim story --dry-run (🔒 refs, tools, render --check, lint, shot_plan 🟨) ─► offsim story ─► MP4 ─► post
```

| Stage | Code | Pulled tools | Listed next (catalog id) | Inspector 🔒 | Rules |
|---|---|---|---|---|---|
| Paper → scenario | `skills/paper-extract`, `offsim/papers/_template` ✅ | — | nafstad-2020, vrplib | G0 `provenance_gaps` (incl. `sim`), `SUPPORTED` classes ✅ | every value `src` or `assumption`; never invent |
| World: land | `worlds/fetch_world.py`, `coast.py` ✅ | osm-coastline (tested), sodir-factmaps (wired) | — | land check in `validate` ✅ | fetched not committed; credits in manifest |
| World: depth | `worlds/depth.py` 🟨 | — | kartverket-dtm10, kartverket-seabed-dtm, emodnet-bathymetry, gdal-tools, pydelatin, deckgl-terrainlayer | ⬜ datum check, mesh budget | VISUAL_SPEC §2 tiers; datum before merge |
| World: lanes | `worlds/sealanes.py` ✅ | (ours) | kystverket-routes | quay snap report, G2 ✅ | never straight across land; report snaps |
| Traffic (AIS) | — ⬜ | — | kystverket-hais, movingpandas, pyais | ⬜ sim-vs-AIS speed/port-time check | validate speeds against real traffic |
| Weather data | `weather/fetch.py` 🟨 | — | nora3-wind-wave, norkyst-v3-800m, xarray-netcdf4, metocean-api | ⬜ manifest + licence | CC BY 4.0 credit MET Norway |
| Weather in sim | `weather/operability.py` (PSV bands ✅, rest 🟨) | — | metocean-stats | G0 (`assumption` for heli/crane) | only sourced thresholds without `assumption` |
| Solve | `solve/pyvrp_adapter.py` ✅, `skills/opt-model` ✅ | pyvrp, opt-model (tested) | ortools (PDP/sync), alns | G1 ✅, exact-vs-heuristic test ✅ | adapter only; OR-Tools in a subprocess |
| Simulate | `sim/replay.py` ✅ | simpy (tested) | fossen-pvs, wombat, orbit | G2, G3 ✅ | event-driven; ≤ 500 m sampling |
| Report | `pipeline.py` ✅ | — | — | G4 status word ✅, provenance ✅ | status computed, never judged |
| Scene | `scene.py` ✅ | — | — | `build_scene` refuses invalid ✅ | display never edits truth |
| Render: map | `render_deck/` ✅ | deckgl, ffmpeg (tested) | deckgl-flyto, deckgl-postprocess, lumagl-effects, seeded-particles | `render.py --check` (CI) ✅ | frame-exact; offline; SwiftShader budget |
| Render: agents | `assets/` sprites ✅, models ✅, lineart ✅ | fluentui-emoji, offsim-models, trimesh, blender-bpy (tested) | kenney-watercraft | assets+licence test ✅ | characters, not blocks |
| Cinema: camera | `cinema/camera.py` 🟨, `rules.py` (data ✅) | — | deckgl-flyto | `shot_plan` 🟨 | VISUAL_SPEC §4 rate limits, grammar |
| Cinema: vessel | `cinema/vessel.py` 🟨 | — | — | `display_offset_check` 🟨 | ≤ 25 m display offset; seeded closed form |
| Cinema: look | `cinema/look.py` (grades ✅ data) | ffmpeg | lumagl-effects | ⬜ pass budget check | one sun, one grade per film |
| Weather visuals | `weather/visual.py` 🟨 | — | seeded-particles, mpl-streamplot-textures, weatherlayers-gl (drafts) | ⬜ byte-identical re-render test | frame-exact particles only in finals |
| Motion | `motion/story.py` ✅, `templates/kpi_card` ✅ | hyperframes, gsap, manim (tested) | vivus, motion-canvas, lottie-web, gsap-skills | `story --dry-run` ✅, `hyperframes lint` ✅ | numbers only from `report:` refs |
| Sound | — ⬜ | — | pixabay-audio, freesound-cc0 | ⬜ licence per clip | CC0 / Pixabay only; −24 LUFS beds |
| Publish | `render` workflow ✅ | — | — | — | credits + status word on screen |
| Tools | `tools/catalog_build.py` ✅, `skills/tool-scout` | — | — | catalog validity, **evidence paths**, TOOLS.md freshness ✅ | tested/wired/installed need evidence |

## Entry points

| Command | Purpose |
|---|---|
| `python -m offsim run <scenario.yaml> [--out] [--seconds]` | gated pipeline → `report.json` |
| `python -m offsim story <storyboard.yaml> [--dry-run]` | shots → film |
| `python offsim/render_deck/render.py --scene … [--check] [--still --at T] [--agents sprite\|model\|lineart] [--sites model\|lineart] [--format …]` | map renderer |
| `python -m offsim.worlds.fetch_world --world <w>` (Actions) / `--pull <w>` (here) | world data |
| `python -m offsim.assets.lineart`; Blender `make_models.py` | asset builds |
| `python tools/catalog_build.py [--find X] [--now] [--check]` | catalog |
| workflows: `tests` (pytest + render-check), `fetch-world`, `render` | CI / data / finals |

## Manifests (what "pulled" means)

| File | Holds |
|---|---|
| `requirements.txt` | core: solve, simulate, validate, exact models |
| `requirements-render.txt` | + playwright, trimesh |
| `requirements-motion.txt` | + manim, pyvista (needs apt libpango1.0-dev, dvisvgm, LaTeX) |
| `offsim/render_deck/package.json` | deck.gl layers, loaders.gl, esbuild |
| `offsim/motion/package.json` | hyperframes, gsap |
| `offsim/assets/` | Fluent sprites (MIT, licence file), our glTF models, line art |
