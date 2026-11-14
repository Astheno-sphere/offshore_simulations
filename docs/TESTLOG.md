# Test log (manual runs that are not automated tests)

Evidence for catalog entries whose status is `tested` but which no automated test exercises. Each line: date ·
catalog id · environment · what ran · result. Automated evidence lives in `tests/` and CI instead.

| Date | Catalog id | Environment | What ran | Result |
|---|---|---|---|---|
| 2026-11-06 | blender-bpy | Claude workspace, bpy 5.2, 2 CPU, no GPU | 640×360 test scene, three engines | Workbench 1.4 s, Cycles CPU 16 spp 4 s, EEVEE 47 s per frame |
| 2026-11-06 | blender-bpy | same | `offsim/assets/models/make_models.py` | 4 glTF models written (psv, ferry, platform, wind_turbine) |
| 2026-11-06 | remotion | Remotion 4, system Chrome | 60-frame composition via `npx remotion render --browser-executable` | MP4 written |
| 2026-11-06 | manim | Manim 0.22.1 + apt libpango1.0-dev, dvisvgm, LaTeX | MathTex objective scene `-ql` | MP4 written; fails without dvisvgm |
| 2026-11-06 | pyvista | PyVista off-screen (VTK) | read `platform.glb`, screenshot | PNG written, no display needed |
| 2026-11-06 | hyperframes | HyperFrames 0.9.19, `HYPERFRAMES_BROWSER_PATH=/usr/bin/google-chrome` | blank example, `render -q draft` | 10 s 1920×1080 MP4; first attempt failed on GSAP CDN (blocked) → vendored GSAP fixed it |
| 2026-11-06 | gsap | GSAP 3.15 from npm inside HyperFrames card | `hyperframes lint` on `kpi_card` | 0 errors |
| 2026-11-06 | deckgl | deck.gl 9, Chrome + SwiftShader | TripsLayer/IconLayer/ScenegraphLayer/PathLayer frames; `render.py --check` in CI | ~8 fps at 640×360; all layers load |
| 2026-11-06 | fluentui-emoji | raw.githubusercontent download | 18 PNGs + MIT licence vendored | rendered in sprite mode |
| 2026-11-06 | osm-coastline | GitHub Actions `fetch-world` (oslofjord) | Overpass coastline → land polygons → release `world-oslofjord` | 4,753 ways; pulled and used by the demo |
| 2026-11-06 | trimesh | trimesh 5.2 | `python -m offsim.assets.lineart` | plan lines: psv 210, ferry 132, platform 66, turbine 61 |
| 2026-11-06 | ffmpeg | system ffmpeg | frames → H.264 veryfast; xfade chain defined | MP4 written |
| 2026-11-07 | deckgl | Chrome + SwiftShader | demo map still at t=9000 with camera track, display tracks, line-art symbols, wake, haze | vessels and platforms legible at 1080²; world edge hidden; reviewed by eye |

## 2026-11-08 — section physics, first still
`PYTHONPATH=. python tools/section_still.py` → `out/stills/psv_section.png` (not committed; data/out ignored).
400×130 grid at 0.4 m, 420 steps of 0.015 s, ~7 s CPU. Plume (520 K exhaust, assumed) rises ~16 m above the funnel,
rolls into lee eddies over the aft deck. Display grade: no validated number on screen except inputs.

## 2026-11-08 — 5 s section film
`PYTHONPATH=. python tools/section_film.py` → `out/film/psv_section.mp4` (1080×1350, 150 frames, 95 s CPU). Measured:
plume's lowest edge ≥ 4 m above the aft deck, crew-zone excess ≤ +3 °C (Hs 3.5 m, Tp 9 s, U10 15 m/s, 520 K exhaust;
all assumed). Narration selected automatically ("crew zone stays clear"); first hand-written caption was contradicted.

## 2026-11-08 — section + map film
`PYTHONPATH=. python tools/section_film.py` → 1080×1350, 150 frames, ~105 s CPU. Map: Oslofjord OSM coast + PSV-1 route
from `offsim run demo-oslofjord-supply` (gates 0–3 pass), marker 2 h 31 min in. Outer-fjord sea Hs 2.0 m / Tp 6.5 s,
U10 15 m/s (assumed): plume lowest edge ≥ 4 m over the aft deck, crew zone ≤ +1 °C → narration "crew zone stays clear".
Tuning found: full-fit overview showed beyond the pulled data; zoom 0.30 levels/s ended in empty water → 1.8× width fit, 0.16.

## 2026-11-09 — first live fetch-world (bergen-ncs, metocean 2024-01-01 +744 h): FAILED, timeout
The Fetch step ran 30 min with no output (Python buffered stdout) and was cancelled; which source hung is unknown.
Fixes: PYTHONUNBUFFERED, per-stage log + wall budget (`fetch_world.stage`; a timed-out stage is recorded in
manifest.errors and the fetch continues), `--metocean-datasets` (default for the workflow nora3_wind,nora3_wave;
NorKyst currents at 800 m over a 4.4 x 2.1 degree box is the likely heavy part), job timeout 150 min.

## 2026-11-11 — self-learning loops verified live (wip branch continuation, venv-studio)

Paper intake: `python -m offsim paper tests/fixtures/intake/synthetic_paper.pdf --out /tmp/intake-test` → 3 pages,
15 evidence rows with page refs (12 knots → 6.17 m/s, 4 h service, 90 nm), extract.json (metadata, rule tags
PSV-PDP/VRPTW, confidence 0.7), scenario.draft.yaml (values null + candidates with page refs). Works end to end.
Feed: `python -m offsim feed --queries papers/queries.yaml --sources openalex --since 2025-01-01` → 13 queries, 0 new:
OpenAlex returns HTTP 429 (Too Many Requests) from this VM; the feed degrades gracefully (warnings, continues).
Crossref works live: one query ("offshore supply vessel planning", since 2024-01-01) → 49 records in ~6 s.
arXiv: 0 hits for the same query (no error). Tag: 49 records → tags.jsonl (rule tags). Gaps: 49 tagged papers → 2 gaps
(no-norway PSV-PDP/psv, support 12; no-code PSV-PDP/psv, support 12, with DOIs).
Experiment runner: unit-verified by tests/test_montecarlo.py (fake builder + fake weather: supported / not supported /
blocked-on-contract-failure). Real end-to-end (whelp + air + NORA3 weather) NOT run — that is the Gribkovskaia
experiment, deliberately not started. `pipeline.build_variant` exists and enforces provenance on overrides.
CAD QA gates (all 9 assets, `python -m offsim.assets.cad.qa <name>`): pass — psv, bus, train, person; fail —
platform_jacket (no measurable dim, required dims missing, all assumed), s92 (rotor 21.2%, fuselage 28.0%, width
341.4% off), aw189 (rotor 20.2%, fuselage 30.0%, width 366.3% off), tree (crown_diameter_m missing, all assumed),
building (length_m/width_m missing, all assumed). Registry statuses updated to match.
Monday storm on the solved Florø program (air engine, synthetic weather): storm 07:00-12:00 → 2 cancelled, 1 rebooked
(F4 → Monday 15:00, +8 h), 1 unmet. Tuesday storm 07:00-12:00 → 3 cancelled, 0 rebooked, 3 unmet (no slack days 1-4).
Full suite (venv-studio): before 443 pass / 5 fail / 7 skip; after 449 pass / 0 fail / 7 skip (346 s).
Quirk: tests/test_intake.py's module fixture regenerates the committed tests/fixtures/intake/synthetic_paper.pdf with
fresh CreationDate/ModDate on every run (timestamp-only diff, content identical) — revert it after suite runs.

## 2026-11-12 — first machine-image build: FAILED, fixed
Build pushed an image without the Python extras: `-c constraints.txt` was not copied into the build context and a
trailing `|| true` hid the pip error; the smoke test caught it (`No module named 'skia'`). Fix: no constraint file in
the image install, failure no longer masked, import check inside the build. Lesson logged via `offsim learn` next.

## 2026-11-12 — N2 live-check, first live run: 14 ok / 1 failed / 2 skipped
`python -m offsim.live.cli` run locally (the workflow was never dispatched — no dispatch tool in the GitHub
connector, `gh` not logged in, dispatch PAT unfilled). Overpass 502'd twice in full runs (<1 s) and passed
standalone twice (57 ways, ~30-40 s): transient gateway error, not a dead host. Fix: `probe_overpass` retries
once on 502/503 (5 s); a persistent 502/503 still fails. Runner probe failed on libegl1 (VM wipe; apt cache
empty, lists stale) — fixed by installing `libegl-mesa0_25.2.8-0ubuntu0.24.04.4` + `dpkg --configure libegl1`
(the installed mesa is 25.2.8, not 24.2.8). OpenAlex still 429s with Retry-After ~13,400 s on the polite pool
(OFFSIM_MAILTO set) — shared egress IP credit exhausted; the mailto does not help here. barentswatch/ampl skipped
(no secrets). Lesson L13 recorded (DATA-HOST-TIMEOUT). Full suite 727 passed, 9 skipped, 0 failed.

## 2026-11-12 — N2 papers feed, OpenAlex 429s: retried, marked degraded
`_retry_429` in `offsim/feed/sources.py` (2 retries, backoff 1 s/2 s, honours a short Retry-After, fails at once
above the 60 s cap); `offsim/feed/run.py` writes `<out>.status.json` and reports a 429-only source once as
degraded instead of once per query. Verified live on one query: "feed degraded: openalex returned 0 records, 1x
429 after retries (Retry-After 13266s)"; crossref 50 records, nva 6, arxiv empty — 54 records. Open gap: the
papers workflow commits only feed.jsonl/tags.jsonl/gaps.yaml, so `papers/feed.status.json` is never persisted to
papers/auto — the workflow needs `papers/feed.status.json` added to its commit list (workflow-file change; the
App cannot push it).

## 2026-11-12 — N2 fetch-world bergen-ncs, coast stage: FAILED twice, now completes
Run 1: coast timed out after 900 s (`sea_polygons` O(segments × faces)); run 2: coast failed in 2 s on HTTP 502.
Fixes: `sea_polygons` vectorised (STRtree + prepared-geometry vote; synthetic split/island cases byte-identical
areas to the old scan) and `fetch_world.get()` retries once on 502/503. Verified live:
`land_from_osm` on bbox [1.40, 59.70, 5.80, 61.80] finished in 193.7 s, 33,976 coastline ways, land.geojson
5,458 km². Sodir keyword fix (`facility` → `facilities`) lands 331 facilities (run 1 had only 47 fields).
World complete on disk at `~/workspace/tmp-n2-fetch/world/` (land + sodir + metocean 744 h + osm 7 layers); no
release `world-bergen-ncs` exists yet, so `--pull` was not run.
## 2026-11-13 — loop proof rehearsed end to end (synthetic weather, Florø instance)
`python -m offsim run` on the helicopter scenario with `weather: {synthetic: {n: 1, hours: 336}}` attached at run time
(the sanctioned path; the committed scenario stays pinned to the generator): gates 0, 1, 2, 3, 4 all pass.
Gate 4 reproduces the paper's Florø instance: plan cost 9980.50 vs Table 4's 9980 (rel gap 5e-5, tol 5 %), 1 helicopter,
10 h window, both exact. Status "re-run under assumptions (synthetic weather, not reportable)", reportable False.
`python -m offsim article <id>` then REFUSED the run for exactly that reason. The chain works; only the data is fake.
Without a weather block the same scenario stops at gate 0 with the fix message, which is the behaviour Nordlys first
read as "weather has no home" and has since withdrawn.
Next: swap the synthetic block for `weather: {dir: data/worlds/bergen-ncs/metocean, point: [...], years: [...], season: DJF}`
when the 24 winters land; that run is the real loop proof and the article will build from it.
