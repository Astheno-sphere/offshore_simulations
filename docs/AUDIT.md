# Framework audit

Running record of weaknesses found in the flow and what was done. Newest first.

## 2026-11-07 — audit 4 (first integrated still)

| # | Finding | Fix |
|---|---|---|
| 1 | True-scale line art (~600 m) was 4–5 px at fjord zoom: vessels invisible | cartographic symbols: fixed screen size from the current zoom; wakes scale with them |
| 2 | Pitched cameras showed the world's data edge as slabs at the horizon | horizon haze overlay (style colours) |
| 3 | Demo sites had no `kind`, so they drew as columns | kinds on scenario stops; line-art platforms/turbines |
| 4 | Sub-agent rate limit stopped one builder mid-task with uncommitted work | `python -m offsim resume` + `docs/RESUME.md`; worktree state shown on every resume |

## 2026-11-06 — audit 3 (depth, weather, cinema; pulled vs listed)

Four research agents (weather, map depth, cinematic, repo audit) → specs and interfaces, nothing rendered.

| # | Finding | Fix |
|---|---|---|
| 1 | Catalog `tested` had no proof for remotion, pyvista, manim; test only checked status strings | `evidence:` paths required for tested/wired/installed and checked; manual runs recorded in `docs/TESTLOG.md` |
| 2 | 7 entries `installed` but in no manifest (ortools, movingpandas, salabim, roughjs, searoute, lottie-web, vivus) | demoted to `candidate`; `installed` now means "in a manifest" |
| 3 | sodir-factmaps called by code but never run on real data | new status `wired` |
| 4 | trimesh, playwright imported but not in requirements | `requirements-render.txt`, `requirements-motion.txt`; CI uses them |
| 5 | Gate 0 ignored `sim:` settings (bare literals passed) | gate 0 walks `sim`; demo values now `{value, assumption}` |
| 6 | No map depth: flat extruded land | `offsim/worlds/depth.py` defined: 3 tiers (fjord 50 m, port 10/5/1 m, shelf ~115 m), datum-first merge, pydelatin mesh, baked hillshade, CAD isobaths |
| 7 | No weather | `offsim/weather/` defined: NORA3 + NorKyst v3 subsetting (Actions), sourced PSV Hs bands (built), seeded particle trails (frame-exact) |
| 8 | Camera eased per segment (stops at every key); vessels snap heading | `offsim/cinema/` rules as data + defined camera spline/fly/follow/orbit, `shot_plan` inspector, heading smoothing, wake, bob, DP jitter, heli profile, display-offset inspector |
| 9 | No look discipline | one sun, one grade (ffmpeg presets), ≤ 2 luma.gl passes; no bloom/LUT in luma.gl → ffmpeg |
| 10 | 17 of 123 tools pulled; weather, energy, AIS layers all listed-only | visible in `docs/TOOLS.md` matrix and `docs/OPS_MAP.md` |

Open from audit 3: helicopter/crane limits unsourced (CAP 437, DNV-ST-N001, NORSOK R-003); NORA3 variable names and
wave grid unverified; GEBCO/EMODnet/rio-rgbify licences "check"; TerrainLayer offline worker untested; sound licences
per clip.

## 2026-11-06 — audit 2 (flow, motion, vectors)

| # | Finding | Risk | Fix |
|---|---|---|---|
| 1 | `scenario.yaml` had a template but nothing consumed it; each stage was run by hand | steps skipped, gates forgotten | `python -m offsim run <scenario>`: gates 0–4 in order (later also the opt-in 1b, 3e, 4b, 4c), stops at the first failure, writes `report.json` (`offsim/pipeline.py`) |
| 2 | No provenance on results | a number cannot be traced to code, data or inputs | `report.json.provenance`: scenario SHA-256, git commit + dirty flag, package versions, world manifest, run time |
| 3 | Gate 0 did not exist: unsourced parameters and unsupported problem classes went straight to the solver | silent approximation of a paper | gate 0 refuses values without `src`/`assumption` and classes outside `SUPPORTED` |
| 4 | Status word ("reproduced") was the narrator's judgement | over-claiming | computed by the runner: assumptions present → at best "re-run under assumptions" |
| 5 | Motion graphics had no structure: one map clip, static camera | no story, no reuse | `storyboard.yaml` + `python -m offsim story`: Manim equation → deck.gl map with eased camera keyframes → HyperFrames KPI card → ffmpeg crossfades |
| 6 | Numbers on screen could be typed by hand | narration drifting from results | card values must be `report:` refs; literals are refused; storyboard refused if gates 0–3 failed |
| 7 | Renderer was only checked by looking at images | slow, subjective, not in CI | `render.py --check` draws headlessly and reports layer health + page errors, writes nothing; CI job `render-check` |
| 8 | Agents drawn as sprites/models only; no CAD-style vectors | not the engineering look wanted | `lineart` mode: feature edges of our glTF models (trimesh) as metric plan-view lines rotated by heading (`offsim/assets/lineart/`) |
| 9 | Models too coarse for line art | sparse drawings | PSV/ferry detail pass (cargo, crane, pipes, railings, lifeboats, windows): 210 / 132 plan lines |
| 10 | HyperFrames template fetched GSAP from a CDN | fails offline and here | GSAP vendored from npm into each card project |

## 2026-11-06 — audit 1 (first real world)

| # | Finding | Fix |
|---|---|---|
| 1 | Straight legs crossed real land (contract caught it) | `offsim/worlds/sealanes.py`, solver distances on the same lanes |
| 2 | `--pull` pointed at the old repo and used blocked GraphQL | REST API, correct repo |
| 3 | Sprites/models missed in frames (async load) | warm-up before capture |

## Open risks (next audits)

- Quay positions are approximate: Moss snaps ~585 m, S6 ~203 m. Need real quay coordinates (Kystverket port data) and a finer local grid near ports.
- Runner supports CVRP/VRPTW only. Helicopter papers (synchronisation, multi-trip, PDP) need an OR-Tools CP-SAT or MIP path before gate 0 can pass.
- Weather is absent: no metocean windows (catalog: metocean-api / NORA3) — offshore operations results will be optimistic.
- Speed in replay is constant; no acceleration, DP time or port manoeuvring (catalog: fossen-pvs).
- GSAP licence is not OSI; if the brand becomes a company product, re-check GreenSock's standard licence terms.
- Video assembly (`story` without `--dry-run`) is implemented but its full render runs only on demand (by design: no images in audits).

## Audit 5 — 2026-11-08: what a paper actually triggers
Method: static import graph from the CLI entry points (`python -m offsim run|story|film|resume`) + skills + gates.
`python -m offsim` reaches 28 modules; **49 modules are built and tested but unreachable from the CLI.**

### When a paper is fed today
| Step | What runs | Notes |
|---|---|---|
| Intake | `paper-extract` skill: Claude reads the PDF by hand -> scenario.yaml | no PDF/table extraction tool; template is CVRP/VRPTW only |
| Gate 0 | provenance + class in `SUPPORTED = {CVRP, VRPTW}` | WIND-OM, WIND-INST, TRANSIT-REPLAY, PDP stop here |
| Solve | `solve_cvrp` (PyVRP) called directly | solver registry, Pyomo, AMPL not used; no exact bound |
| Simulate | SimPy replay (sea lanes) or road engine (land) | OpenCLSim/WOMBAT/ORBIT/gtfs engines not reachable |
| Gates 1-4 | plan check, replay=plan, contract, paper KPIs; 4b AIS opt-in | no ensemble, no exact-gap gate, 4c not wired |
| Present | `story`: map / equation / card shots from `report:` refs | section film, map panel, findings shots outside story |

### Built but not triggered
engines registry + openclsim/wombat/orbit/gtfs; montecarlo + experiment/decide; feed/tags/gaps (only via papers.yml);
transit (gtfs, from_paper, entur, observed/gate 4c); physics + section film + mappanel (tool script only); findings,
diptych, emissions (specs); place/user_layers/fetch_world (standalone CLIs, fine as data tools).

### Not verified live (workspace cannot reach the hosts)
NORA3, Kartverket DTM + stedsnavn, OSM pbf, Entur GTFS + realtime, BarentsWatch, OpenAlex/Crossref/arXiv/NVA, AMPL.
Only the Overpass coastline has run live. Expect field-name fixes on first runs.

### Drift
Skills: `offsim-foundations` router, `sim-corrector`, `sim-narrator`, `paper-extract` do not know engines, ensembles,
gates 4b/4c, transit. Catalog 150 tools; motion/video watch/candidate entries never pruned.

### Visuals vs the reference (honest, /10, ours -> reference)
data density 3->9 · physics texture 7->9 · line art 6->9 · typography 5->9 (DejaVu) · real-data maps 5->9 ·
light/time of day 2->8 · narration from data 8->8 · provenance/validation 9->(not shown). We can beat it on
validated numbers, uncertainty bands and real-vs-simulated ghost tracks; we lose on density, type, light, terrain.

### Fix order (architecture first)
1. Pipeline through the registry: scenario `solver:` / `engine:` (default pyvrp / replay); SUPPORTED = union of
   registered classes. Makes openclsim, road, gtfs, wombat, orbit reachable from `offsim run`.
2. Scenario `ensemble:` -> montecarlo -> `report["ensemble"]`; `offsim experiment <experiment.yaml>`.
3. `offsim paper <pdf>`: local text + table extraction with page numbers (pdfplumber/pypdf, MIT/BSD) -> draft
   scenario for paper-extract to confirm. GROBID (Apache) on Actions later.
4. One CLI: `offsim feed | gaps | world | layer | timetable` wrappers.
5. Story shot kinds `section`, `findings`, `diptych`; two-pass narration in story, not only in the film script.
6. Gate 1b exact certification (Pyomo/AMPL bound on small instances); gate 4c for gtfs scenarios.
7. Update skills router + corrector/narrator for engines, ensembles, gates 4b/4c.
8. Visual: skia strokes, open font, hillshade, light by clock (rules 11-13, 17).
9. One Actions batch to live-check every data source; record in TESTLOG.
