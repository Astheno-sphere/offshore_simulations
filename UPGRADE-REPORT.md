# Upgrade report — absorb, skia, Molde live run, Ghia validation

Date: 2026-11-09. Local work only; nothing posted, nobody contacted, nothing committed
(`gh` is not logged in on this VM). Local main is **ahead 2 of origin/main**
(`f02203a`); the two commits are the rebased fixes `8054eee` + `fbe57e3`.
Full suite on the final tree: **369 passed, 3 skipped, 0 failed** (110 s).
The repo's stated 363 is stale — the tree now holds more tests than that count.

## 1. Absorb — DONE

- Stash `v6-work-20261108` saved the uncommitted v6 work; fetch; rebase of the
  2 local commits onto origin/main `f02203a` was **clean**.
- Stash pop conflicted on `docs/RESUME.md` and `tools/section_film.py` only.
  `tools/section_film.py` was reconciled by script (`/tmp/reconcile_film.py`):
  upstream `gale_shot()` thin-wrapper path for `--mode section` + v6 demo
  machinery (`run_context`, `route_at`, demo-extended `narration`, demo-capable
  `render`, bifurcated `main`); `Scene`/`Streaks` dropped as duplicates
  (verified identical to `offsim/motion/section.py` by diff). `docs/RESUME.md`:
  both "night" entries kept, audit-5 first. Stash dropped after staging.
- Untracked dirs survived untouched: `offsim/papers/nafstad2021/`, `proof/`,
  `world-fetch/`.
- Deps installed into `venv-studio`: skia-python==144.1, pdfplumber 0.11.10,
  pypdf, reportlab, pyrosm 0.29.0, movingpandas 0.23.0, wombat 0.13.5,
  orbit-nrel 1.3.1, mcp, rasterio 1.5.2, pydelatin, osmium (pyosmium),
  scikit-image 0.26.0 (the last one unblocks `tests/test_depth.py`: 12 passed).
  amplpy NOT installed (AMPL needs a licence; 2 tests skip by design).
- Suite at absorb time: 352 passed, 4 skipped; after the skia work + Ghia
  tests + scikit-image: **369 passed, 3 skipped** (2× AMPL, 1× node/renderer).

## 2. Skia renderer (RESUME 000) — DONE

- `offsim/motion/section.py::render()`, `offsim/motion/mappanel.py::MapPanel.frame()`,
  and `tools/section_film.py::render()` (demo mode) moved from PIL to
  `offsim/cinema/draw.py` skia `Canvas` (Inter via `look.FONTS`, `look.sun()`,
  terrain hillshade per STYLE_REFERENCE rules 12–13). `tests/test_draw.py`
  extended; `tools/reproduce_film.sh` gained `-r requirements-graphics.txt`.
  Narration, gates, and data untouched — renderer only.
- Blocker found and cleared during the work: the VM restarted mid-task,
  wiping libEGL/libGL; `import skia` then failed with
  `libEGL.so.1: cannot open shared object file` even though `dpkg -l` listed
  libegl1 installed. The skia work restored libegl1/libgl1 from the apt
  archive cache (`dpkg -i`); `import skia` now succeeds. (An earlier draft
  of this report said only that the `.so` "reappeared" — the restart +
  restore is the actual cause.)
- `requirements-graphics.txt`: `gtfs-kit==14.1.1` commented out — it needs
  pandas>=3 vs the pinned pandas==2.3.3, so the pip step failed; no repo
  code imports it.
- One deliberate colour change: the sea polygon default is now `P["sea"]`
  #16323a, not `ground_deep` — the library PIL version carried the v5
  round-1 "sea invisible" bug; the teal sea is the v5 film's reference look.
  `findings.py` is still PIL (out of scope; it imports `section.font`,
  restored as a shim).
- Verification (by me, from the tree): `tools/reproduce_film.sh` reproduces
  the v5 film — `out/film/psv_section.mp4`, 5.0 s, 1080×1350, 30 fps, h264,
  3,375,516 B (v5: 3,370,762 B), exit 0 in 6 m 05 s, gates 0–3 pass, 113.3 km,
  5.56 h. Frame f0075 compared by eye against the PIL v5 still
  (`docs/linkedin/04-v5/still_f0075.png`): same composition, same numbers,
  same wording; only sub-pixel differences (Inter vs DejaVu metrics, skia
  antialiasing). Child's measured diffs: f0075 mean abs 9.97 excl. map,
  4.53 map panel; demo f0360 8.68 / 4.04; sea mean RGB 42.5,47.4,52.9 vs
  42.1,46.2,52.9; hillshade under the map (Oslofjord DEM ok, alpha mean
  44/255). No content drift. Child's stills: `workspace/skia-check/frames/
  f0075.png`, `f0360.png`.
- Note: `tests/fixtures/intake/synthetic_paper.pdf` shows as modified in the
  working tree; I did not touch it and did not investigate the diff (binary).

## 3. Molde live run (RESUME 00) — DONE, two live legs

Fetch ran locally (this VM reaches Overpass POST, Geofabrik, Entur):
`python -m offsim.worlds.fetch_world --place Molde --modes sea,road,bus`,
16 m 54 s, exit 0. World `data/worlds/molde/`, bbox 6.8655–7.4545 /
62.6051–62.8749.

What landed from the fetch:
- Coastline (Overpass POST): **1,396 ways** → `land.geojson`.
- Entur GTFS (national zip, clipped): **41 routes, 2,323 trips, 57,918
  stop_times, 422,517 shape points, 1,025 stops in bbox** (1,855 with whole
  trips), 150 services. NLOD 2.0.
- OSM Geofabrik layers: **all 0** in the fetch (roads/buildings/ferry/quays/
  landuse/helipads/aerodromes). Cause found and fixed (below); layers rebuilt
  afterwards — the top-level `data/worlds/molde/manifest.json` still records
  the fetch-time 0s (stale for the OSM entry); the current record is
  `data/worlds/molde/osm/manifest.json`.

### 3a. Why the OSM layers were 0 — pyrosm needs >512 MB of temp space

- The PBF is intact: pyosmium scan reads 209,744,821 nodes, 12,190,708 ways,
  1,968,438 highway ways, 581,123 nodes in the Molde bbox. Bbox order is
  correct (tiny-PBF test: as-is `[W,S,E,N]` returns the Molde ways; swapped
  returns 0).
- Re-running `extract_layers` on the complete PBF failed per layer with
  `OSError: 336000 requested and 0 written` — pyrosm 0.29 shards the whole
  1.38 GB PBF out-of-core (`pyrosm_ooc_*`) under `tempfile.gettempdir()`,
  which here is `/tmp`, a **512 MB tmpfs**. The shard write fills it and
  dies. Proof: with `TMPDIR=~/workspace/tmp-pyrosm` (127 GB disk) the same
  call returns roads 2,036, buildings 26,483, ferry 6, quays 100; the
  scratch peaked at 4.7 GB during the run and cleaned itself to 4.1 MB.
- **Lesson for the repo:** any `fetch_world --modes road` (or any pyrosm
  run on a country PBF) on this VM needs `TMPDIR` on the big disk, or a
  pre-filtered PBF. `fetch_world` does not set it today.
- Layers rebuilt with `build_osm_layers` under that TMPDIR:
  **roads 2,036, buildings 26,483, ferry 6, quays 100, landuse 19,
  helipads 1, aerodromes 1**. One warning: 1 relation extends beyond the
  bbox with incomplete geometry (`complete_relations=True` would fetch the
  full member set).

### 3b. GTFS replay — first live run, gates 0–3 pass

Scenario `offsim/papers/molde-gtfs-replay/scenario.yaml`, engine `gtfs`,
Mon 2026-11-09 06:00–10:00, `out/molde-gtfs-replay/`:
**289 trips (231 bus + 58 ferry), 5,962.7 vehicle-km, makespan 4.00 h,
peak 67 vehicles, mean headway 168.1 s, wait 19,860 s**, 26,102 trajectory
rows. Gates 0–3 pass; gate 4 false (no reported KPIs — expected for a
replay); status "not comparable"; zero assumptions. Caveat: gate 3 passed
but the replay's `World` carries no land polygon (non-routing problem), so
ferry legs were **not** land-checked in this run.

### 3c. Road template — first live run, gates 0–3 pass (after two real findings)

Scenario `offsim/papers/molde-road-cvrp/scenario.yaml` (template copy,
world molde, 2 trucks, 4 placeholder stops), `out/molde-road-cvrp/`:
**87.59 km, makespan 7,359.8 s (2.04 h), 2 vehicles used**, wait 0 s,
2,567 trajectory rows. Gates 0–3 pass; gate 4 false (no reported KPIs);
15 assumptions, all labelled. Routes: truck 1 → [C2], truck 2 →
[C4, C1, C3]; snap_m all 0.0.
- Finding 1: the template's placeholder points are off-network (depot
  555 m, C4 ~800 m from any road). Moved onto real named Molde roads.
- Finding 2 (the substantive one): `RoadGraph` snaps and routes **only on
  the largest strongly connected component** and builds graph nodes **only
  at way endpoints** — it never nodes ways at interior shared vertices.
  The Molde graph has **1,085 strongly connected components and 911 weakly
  connected components** (core 202 of 2,872 nodes); a real city network
  should be ~1 weak component. Off-core roads (Hatlehaugvegen, Sagsletta,
  Julsundvegen, …) cannot be served. The run's stops were placed on the
  core instead (W/E/N/S spread: Fannefjordsvegen, secondary west,
  Nedre Julsvang, Skålavegen; depot Moldelivegen). **Fixing the noding
  (split edges at shared interior vertices) is a repo design change, not
  done here** — it changes every road route and needs its own verification.

## 4. Ghia 1982 cavity validation (RESUME 0d) — RUN, and it does NOT validate

Harness: `offsim/physics/ghia1982.py` (Ghia Tables I–II, Re 100/400/1000,
17 u / 17 v points; the known misprint v = −0.23827 at x = 0.9063, Re 400
is stored as None, not zeroed) + `tools/ghia_cavity.py` (`CavitySection`:
base `Section2D` + explicit FTCS viscosity + no-slip walls + lid u = 1,
Neumann pressure; steady when centreline profiles move < 1e-4 over 5 time
units; errors on the 15 interior points only). No pass threshold exists in
the repo — errors are reported, not judged. Fast mechanics test added to
`tests/test_physics.py` (2 new tests; no error threshold asserted).

Results (`proof/ghia-cavity.json`, `proof/ghia-cavity-n129-re1000.json`):

| Re | n | steady at | u rms / max | v rms / max | u_min (Ghia) |
|----|---|-----------|-------------|-------------|--------------|
| 100 | 65 | t=20.0 | 0.031 / 0.047 | 0.027 / 0.059 | −0.184 @ y=0.52 (−0.211 @ 0.45) |
| 400 | 65 | t=35.1 | 0.134 / 0.278 | 0.198 / 0.359 | −0.118 @ y=0.55 (−0.327 @ 0.28) |
| 1000 | 65 | t=25.1 | 0.214 / 0.376 | 0.319 / 0.521 | −0.035 @ y=0.79 (−0.383 @ 0.17) |
| 1000 | 129 | t=95.0 | 0.157 / 0.319 | 0.215 / 0.320 | −0.192 @ y=0.38 (−0.383 @ 0.17) |

Interpretation (measured, not tuned): the solver's semi-Lagrangian
advection is first-order diffusive — numerical diffusion dominates the
explicit viscosity at low ν, so the vortex is too weak and sits too high,
worse at higher Re. Refinement helps in the right direction (n=65 → 129 at
Re 1000: u_min −0.035 → −0.192, rms 0.214 → 0.157) but is far from Ghia.
Jacobi 200 vs 60 changes nothing (projection is not the limiter).
**Consequence: the section numbers in v5/v6 stay display-grade (DRAFT),
exactly as labelled. The repo's precondition (0d) is now measured, not
assumed — no section number may be reported as validated until this
validation passes at the resolution the films use (the film section runs
400×125 cells at DX = 0.4 m; the cavity was run at n = 65/129 on a unit
square).** The solver was not tuned to pass; a failed validation is a result.

## Still open / not done in this round

- House-rules notes (repo `AGENTS.md`/`CLAUDE.md`, read at the end of this
  round): the local fetch overrode rule 4 ("data hosts only via Actions") —
  that override came from the parent task's explicit instruction to try
  locally first, and is recorded here, not hidden. Not done, per those same
  rules: no catalog entry for the new Ghia harness (`catalog/tools.yaml` +
  `docs/TOOLS.md` rebuild), no `docs/TESTLOG.md` entry for the manual runs,
  and `docs/RESUME.md` not updated (those go with a commit; none was made).
- Push: local main ahead 2 (8054eee, fbe57e3) + uncommitted work (absorb
  resolutions, skia conversion, Ghia harness + tests, Molde scenarios +
  runs, `data/worlds/molde/`). Unblock: `gh auth login` on this VM.
- No v7 film built (per the brief — the film comes after this upgrade lands
  and the user sees the report).
- RoadGraph endpoint-only noding (911 weak components) needs a design fix
  before road runs can serve off-core points; `fetch_world` needs TMPDIR
  handling for pyrosm on a country PBF.
- Ghia validation fails at Re ≥ 400 on the tested grids; the section solver
  needs a less diffusive advection scheme (or much finer grids) before any
  section number is reportable.
- `tests/fixtures/intake/synthetic_paper.pdf` modified in the working tree
  (not by me; binary, diff not inspected).
- `data/worlds/molde/manifest.json` OSM entry is stale (fetch-time 0s);
  current counts live in `data/worlds/molde/osm/manifest.json`.
- Actions fetch-world inputs if the local route ever blocks: place Molde,
  modes sea,road,bus, radius 15 km (gazetteer key; no stedsnavn call needed).
