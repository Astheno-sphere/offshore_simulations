# Resume log

Hand-written state for the next session (human or Claude). `python -m offsim resume` prints this file's
**Next** section together with git state, open roadmap rows and open risks. Update it at the end of every
session and whenever work is interrupted. Newest first.

## 2026-11-12 (evening) — main is the machine: P1 + Nordlys's film path merged. 670 pass, 6 skip.
main = W0 + W1-W5 (conductor, doctor, concordance, live-check, agents+MCP) + R1 (Nordlys's N1 reconciled:
section.py skia+CAD-HLR, mappanel, sheet.py, cad_sprites, ghia1982 harness, linkedin reports; drawing.py merged;
S-92 now QA pass). CAD QA: 7 pass, aw189 fail, platform_jacket unmeasurable. Reports in coordination/reports/.
Open, in order:
  1. machine-image build (Dockerfile fixed after the first failure: constraints.txt was outside the build context).
     Then Arshad: package access + Codespaces secrets, create the Codespace (docs/MACHINE.md).
  2. CI on the hosted runner: the test step produced no output for 30 min; now `pytest -v -u` names the test live.
     Read the newest tests run on main; if it is one test, fix it, else move the test job inside the image.
  3. Arshad on Actions: live-check (first real probe of every host), papers (data branch + issue), fetch-world
     bergen-ncs; set variable OFFSIM_MAILTO and secrets AMPL_LICENSE_UUID / MUSE_AI_KEY (Actions + Codespaces).
  4. Then P2: W6 gap scout (18 of 26 gaps are no-code noise), W7 intake tables, W8 article generator.
  5. Drafter: aw189 + platform_jacket to QA pass. Director: the visual gate (density, type, contrast, goldens).

## 2026-11-12 (later) — the machine on GitHub: docs/MACHINE.md
.devcontainer/devcontainer.json (Codespaces), Dockerfile extended to every extra, machine-image.yml (GHCR image),
tools/machine_setup.sh (AMPL activation from a Codespaces secret). NOT built yet (no Docker here): Arshad runs
Actions -> machine-image, then creates a Codespace. Open: CI test job hangs on the runner (per-test timeout added,
read the durations in the last tests run); then move the test job into the image; merge PR #1.

## 2026-11-12 — W0 + P1 (W1-W5) built and merged into wip/cad-assets-heli. 607 pass, 5 skip locally.
W0: CI apt retries + requirements-cad, papers workflow -> data branch + issue, papers/auto data merged, coordination/
channel (task N1 for Nordlys: bring uncommitted CAD sources + section.py v7-v10 in on agent/nordlys/N1-cad-sources).
W1 tests/test_concordance.py (13 drift guards) + docs/GUARDS.md; gaps.py engine mapping fixed (HRP -> air).
W2 offsim/studio (funnel.yaml, ledger, conductor): `offsim status | next | advance | decide`.
W3 offsim/doctor (22 codes, playbooks, diagnose/repair, lessons): `offsim doctor | learn`; pipeline emits codes.
W4 offsim/live (17 probes) + live-check.yml: `offsim live`. Unverified live until its first Actions run.
W5 .claude/agents (9 roles), .mcp.json (ampl, Entur x2), AGENTS.md protocol.
Next: CI green on this branch -> merge PR #1 -> Arshad runs live-check + papers + fetch-world on Actions, sets
OFFSIM_MAILTO variable and AMPL_LICENSE_UUID secret -> Nordlys N1 -> then P2 (W6 gap scout, W7 intake, W8 article).

## 2026-11-11 (later) — system review, plan only: docs/SYSTEM_PLAN.md
Nothing built. Verdict, measured state, 12 named flaws, five additions (conductor, doctor, concordance, live-check,
agents+MCP), wave plan W0-W13 with models, owners, exit tests and firing commands, 6 decisions for Arshad.
Next: Arshad answers section 6, then "fire W0", then "fire W1 W2 W3 W4 W5".

## 2026-11-11 — HALTED branch continued (Nordlys, subagent): 5 failing tests fixed, suite green. Uncommitted, nothing pushed.

Key finding: the air engine was NOT broken — its `_rebook` is correct. Three of the five failures were wrong test
premises, and the other two were stale expectations. The solved Florø program is packed back-to-back (eq 11, no idle
slots): days 1-4 use slots 0-40/41, Monday's tail (slots 32-39) is the week's only slack, so a Tuesday storm
legitimately rebooks nothing (verified by trace: every candidate rejected on weather or occupancy). A 120 nm flight is
125 min = 9 fly slots and FITS a 4 h window (16 slots). psv passes QA now; whelp/air ship, so the registry test's sets
were stale.
Fixes (tests only; no solver/engine code changed):
  - tests/test_engines_core.py::test_registry_lists_every_tool_we_ship — expected engines + "air", solvers + "whelp".
  - tests/test_cad_drawing.py::test_story_check_gates_asset_shots — psv now asserts QA pass (`qa("psv") == (True, [])`);
    the "cannot be built" refusal path is now covered by a bad-params case instead.
  - tests/test_whelp.py::test_infeasible_when_a_flight_cannot_fit_any_window — window 4 h -> 2 h (8 slots < 9 fly slots).
  - tests/test_whelp.py::test_air_storm_day_cancels_and_rebooks — storm moved Tue -> Mon 07:00-12:00 (the week's only
    slack is Monday's tail): 2 cancelled, 1 rebooked (F4 -> Mon 15:00, +8 h), 1 unmet.
  - tests/test_whelp.py::test_air_rebooked_flights_respect_the_rules — storm Mon 00:00-10:00, same outcome; assertions kept strict.
  - NEW tests/test_whelp.py::test_air_tuesday_storm_has_no_slack_so_flights_go_unmet — pins the discovered fact
    (Tue storm: 3 cancelled, 0 rebooked, 3 unmet; engine reports unmet rather than inventing slack).
Suite (venv-studio, full runs): before 443 pass, 5 fail, 7 skip; after 449 pass, 0 fail, 7 skip (346 s). The HALTED
entry said 445/5/5; the 2-test difference is pass -> skip accounting, same 5 failures. The 7 skips are pre-existing
environment skips: 3 AMPL (amplpy absent), 2 SLOW (OFFSIM_SLOW unset), 1 Stavanger (solve 81 s > 60 s conditional
skip — the [12, 16] h assertion never runs on this VM), 1 vessel (deck.gl node_modules absent).
Follow-ons done: catalog entries whelp, air, cadquery, build123d, cadquery-ocp (159 tools, 54 pulled; `catalog_build.py
--check` passes); requirements-cad in CI (.github/workflows/tests.yml pytest job, + novtk-restore step — build123d pulls
cadquery-ocp-novtk, which breaks CadQuery VTK; 20-min timeout unchanged, watch the first CI run); registry.yaml
statuses from measured QA gates — qa-pass: psv, bus, train, person; built: platform_jacket, s92, aw189, tree, building.
Pipeline.py diff (WIP commit) reviewed — CORRECT: EXTRA_KEYS += wfppp, TOOL_PACKAGES += whelp (pyomo, highspy) + air (),
gate 1 WFPPP branch uses whelp.check_program, gate 2 compares planned_variable_cost (1e-6) and flights_planned_per_week
(exact) from the air engine KPIs; exercised by the passing pipeline tests. `pipeline.build_variant` exists, so the
experiment runner's default builder resolves.
Self-learning loops verified live (see docs/TESTLOG.md): paper intake on the fixture (3 pp, 15 evidence rows, draft
scenario); feed via Crossref (49 records for one query; OpenAlex 429s from this VM, degrades gracefully; arXiv 0 hits);
tag (49) -> gaps (2 gaps, support 12 each); experiment runner unit-verified (test_montecarlo, fake builder/weather) —
real end-to-end NOT run (that is the Gribkovskaia experiment, deliberately not started); `offsim resume` works.
Remains: s92/aw189 QA fail (dims off rotor ~21%, fuselage ~28-30%, width 341-366% — declared dims do not match the
built solid); platform_jacket/tree/building QA fail (missing dims, all assumed); 23 more Bergen winters to fetch; AMPL
install awaits approval + UUID via secure capture; sea_polygons + Sodir keyword bugs; CAD duplication with Nordlys's main-tree CAD sources (sprite sheet at docs/linkedin/06-cad-sprites/cad-sprites.png on
the VM, sources uncommitted): Arshad decided 2026-11-12 to bring the sources in via branch agent/nordlys/cad-sources. Quirk: test_intake.py's fixture regenerates the committed
synthetic_paper.pdf with fresh timestamps on every run (timestamp-only diff) — reverted here; it will show modified
again after any suite run.

## 2026-11-09 — HALTED by Arshad (weekly limit). Branch `wip/cad-assets-heli`, not merged to main.
State: 445 pass, 5 fail, 5 skip. Built: cad/drawing.py (HLR line classes, cache), qa.py (scale/detail gate),
registry.yaml, story `asset:` hook, land.py (bus, train, person, tree, building; 27 tests pass), marine.py (psv,
platform_jacket) + air.py (s92, aw189) (agent finished; report lost: re-check dims/sources in module docstrings),
solve/whelp.py + ampl/whelp.mod + engines/air_engine.py + paper scenarios (agent killed mid-work; pipeline.py edited).
Failing, fix first next session:
  - tests/test_engines_core.py::test_registry_lists_every_tool_we_ship (add "air" to expected engines)
  - tests/test_cad_drawing.py::test_story_check_gates_asset_shots
  - tests/test_whelp.py: infeasible-window, storm-day cancels/rebooks, rebooked-rules (air engine incomplete)
Then: catalog entries (cadquery, build123d, OCP; whelp, air), requirements-cad in CI, registry status -> built/qa-pass,
review the pipeline.py diff from the killed agent, merge to main. Goal reminder: build the machine, do not run studies.

## 2026-11-09 — CAD-grade assets + helicopter simulation (superseded by the HALTED entry above)
Contract written: `offsim/assets/cad/base.py` (exact solids, real scale, sourced dims; registry). requirements-cad.txt
(cadquery, build123d, OCP = OpenCASCADE, Apache-2.0). Agents (none commit): D drawing.py (HLR line classes) + qa.py +
registry.yaml + story `asset:` hook; M marine.py (psv, platform_jacket) + air.py (s92, aw189); L land.py (bus, train,
person, tree, building); H solve/whelp.py + ampl/whelp.mod + engines/air_engine.py + paper scenario (WFPPP).
If interrupted: git status; pytest; finish per docstrings; merge catalog/docs; commit.

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
