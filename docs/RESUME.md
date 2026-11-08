# Resume log

Hand-written state for the next session (human or Claude). `python -m offsim resume` prints this file's
**Next** section together with git state, open roadmap rows and open risks. Update it at the end of every
session and whenever work is interrupted. Newest first.

## 2026-11-08 (night) — audit-5 fixes wired (done)
`offsim run` drives every registered solver/engine (pyvrp, pyomo, ampl; replay, road, openclsim, wombat, orbit, gtfs)
via scenario `solver:`/`engine:`; gates 0, 1, 1b_exact (`certify:`), 2, 3, 3e_ensemble (`ensemble:`), 4, 4b (AIS),
4c_entur. `offsim paper <pdf>` drafts with page evidence (pdfplumber). One CLI: paper, run, experiment, story, film,
world, layer, timetable, feed, tag, gaps, entur, tools, catalog, resume. Story shot types `section`, `findings`
(fan/paired/state_gantt), narration rules (`offsim/motion/narrate.py`, safe evaluator). Visual lib: skia Canvas
(`cinema/draw.py`), Inter font (OFL), `look.sun()`, terrain hillshade. Skills rewritten to the current system. 363 tests.
Open: section/map panels still PIL (switch to draw.py), ensemble report has quantiles only (no per-run tracks for
ghost_tracks), gate 4 compares the single run not ensemble medians, all external data still unverified live.

## 2026-11-08 (late) — Norway-wide worlds + road/bus + AIS gate (done)
Any place in Norway: `python -m offsim.worlds.fetch_world --place Molde --modes sea,road,bus` (Actions: fetch-world
inputs place/modes/radius_km) -> world spec v2 (`offsim/worlds/place.py`; v1 worlds still load as [sea]). Modes imply
layers: road/walk -> OSM roads, bus -> + Entur GTFS (`offsim/transit/gtfs.py` clip/trajectories), air -> helipads +
aerodromes. Engines `road` (networkx RoadGraph, oneway, maxspeed; pipeline `domain: land`) and `gtfs` (timetable replay,
bus/ferry/rail/tram agents). Gate 4b AIS calibration in `offsim run` (opt-in `validate: {ais: true}`). 265 tests pass.
Not yet live: stedsnavn API, Entur zip, real OSM roads. Installed for next phase: skia-python, datashader, xarray-spatial.
Added: user GeoJSON layers (`offsim/worlds/user_layers.py`), paper timetables -> GTFS (`offsim/transit/from_paper.py`),
Entur realtime client + gate 4c (`offsim/transit/entur.py`, `observed.py`, workflow `entur-realtime`), data-intake rules
(ARCHITECTURE), transit rules in research-scout/paper-extract skills, level-up rules 9-17 (STYLE_REFERENCE).

## 2026-11-08 — engine layer built (done)
Architecture (`docs/ARCHITECTURE.md`, 7 layers + import rule enforced by `tests/test_architecture.py`), definitions
(`docs/ENGINES.md`), interfaces (`offsim/engines/base.py`). Built and tested here: solvers pyvrp, pyomo; engines replay,
openclsim (weather windows), wombat, orbit; `offsim/montecarlo` (CRN ensemble, bootstrap CI); `offsim/weather/years.py`;
`offsim/research` (experiment spec + runner, tags, gaps); `offsim/feed` (OpenAlex/Crossref/arXiv/NVA, fixtures);
`offsim/traffic` (AIS port calls, calibration, gate 4b spec; BarentsWatch client); `offsim/worlds/osm.py`; fetch-world
`--osm/--ais`. Wired, not run: AMPL (`solve.yml`, `tools/ampl_mcp`), `papers.yml`. Specs only: `offsim/emissions`,
`offsim/motion/findings.py`. 205 tests pass, 2 skip (AMPL solve needs a licence).
Not yet live-checked: NORA3 variable names, NVA fields, BarentsWatch endpoints, pyrosm on a real pbf, every AMPL call.

## 2026-11-07 — four visual layers built and integrated

Done: camera (per-frame track, centripetal spline, van Wijk fly, follow/orbit, `shot_plan` inspector — demo passes);
depth (datum-first merge, pydelatin mesh, baked hillshade, isobaths, EMODnet/Geonorge fetchers); weather (NORA3/NorKyst
subsetting, seeded particle trails, Hs texture, PSV weather effects); vessel (display-only fillets, speed ramps, DP
jitter, bob, Kelvin wake, heli profile; toy max offset 12 m, demo 16 m). Renderer: Python precomputes camera track,
display tracks, terrain and weather blocks; line art and wakes drawn at fixed screen size (cartographic symbols);
horizon haze hides the data edge. One command: `python -m offsim film <storyboard> [--muse unlisted]`; Actions
workflow `film`; Dockerfile; muse.ai upload (hosting only).

Interrupted and recovered: the depth builder hit the sub-agent rate limit; its uncommitted work in
/home/claude/wt/depth was finished by hand (terrain.js, requirements, catalog) and merged.

## Next
000. Next build: skia-python stroke renderer + open font (rule 12, 17), terrain hillshade under maps (rule 13).
00. You: Actions -> fetch-world with place `Molde`, modes `sea,road,bus` -> first live run of stedsnavn + OSM + Entur;
    then `--pull molde` here and run the road template / a GTFS replay on real data; fix what the log shows.
0. Wire engines into `offsim run`: scenario `engine:` / `ensemble:` blocks, `pipeline.build_variant` for
   `research/run_experiment.py`, WIND-OM / WIND-INST past gate 0; wind adapters onto `world.legs`.
0b. You: secret `AMPL_LICENSE_UUID` → Actions **solve** on the demo; allow Actions to create PRs (Settings → Actions) for **papers**.
0c. Build `offsim/emissions` and `offsim/motion/findings.py` to their specs.
0d. Section physics BUILT (display grade): `offsim/physics` fluid2d (consistent projection), ocean (JONSWAP), streaks;
    tests/test_physics.py; draft still `tools/section_still.py` (PSV in a gale, plume over the cargo deck; inputs assumed).
    DONE 5 s film `tools/section_film.py` (moving sea, heave/pitch, detailed line art `cinema/vessel_lineart.py`,
    narration chosen from measured values) + map panel (`motion/mappanel.py`: OSM coast, gated demo route, eased zoom).
    Next: NORA3 Hs/wind on the map (fetch-world --metocean), real PSV class geometry, cavity validation (Ghia 1982)
    before any section number is reported, real vessel geometry and exhaust data.
1. Actions → **fetch-world** `oslofjord` with `depth: true` and `metocean_start` (e.g. 2024-01-10T00:00, 48 h) — first live
   run of the DEM and MET Norway fetchers; fix whatever the log shows; flip `live_checked` in weather/fetch.py.
2. `python -m offsim.worlds.depth --world oslofjord --tier fjord` on the pulled DEM → terrain in the demo map shot.
3. Add `weather: {wind: nora3_wind, wave: nora3_wave, particles: 2500}` to the demo map shot; dry-run; review a still.
4. Actions → **film** on the demo storyboard (add secret `MUSE_AI_KEY` to upload) → review the MP4.
5. First paper (PSV supply routing) via `paper-extract` → `offsim run`.
