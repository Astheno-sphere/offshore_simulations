# LESSONS

Generated from `offsim/doctor/lessons.jsonl` by `python -m offsim learn` (offsim.doctor.lessons). Do not edit by hand.
A lesson is closed only when its guard (a test or a playbook check) exists. Open lessons come first.

11 lessons, 2 open.

## Open (no guard yet)

### L10 (2026-11-11) DATA-HOST-TIMEOUT

- Symptom: OpenAlex returns HTTP 429 from GitHub Actions and from the VM: 0 records, the best feed source is dead
- Cause: No polite-pool mailto or API key; shared egress IPs are rate limited
- Fix: Add OFFSIM_MAILTO / API key secret and backoff; live-check probe (W4) will own the guard
- Guard: none yet

### L11 (2026-11-06) CI-ENV

- Symptom: HyperFrames render failed: GSAP loaded from a CDN that is blocked in the workspace
- Cause: Template fetched GSAP at render time
- Fix: GSAP vendored from npm into each card project; no automated guard yet
- Guard: none yet

## CI-ENV

### L3 (2026-11-08) CI-ENV

- Symptom: CI red: pytest rejects pytest.approx(numpy float32) in test_depth
- Cause: Newer pytest refuses numpy float32 arguments to approx
- Fix: Plain float tolerance (commit 52f190d); the playbook check flags numpy scalars passed to approx
- Guard: `playbook:CI-ENV::numpy_float_in_approx`

### L4 (2026-11-08) CI-ENV

- Symptom: skia-python import fails on the runner: libEGL.so.1 / libGL.so.1 missing
- Cause: skia-python needs the system libEGL/libGL (apt libegl1 libgl1)
- Fix: CI installs libegl1 libgl1 libfontconfig1 (commit f02203a); doctor check egl_available reports it
- Guard: `playbook:CI-ENV::egl_available`

### L5 (2026-11-12) CI-ENV

- Symptom: CI red 8 times in apt-get install libegl1 (index download), never reaching pytest
- Cause: Transient apt index failure on the new runner image
- Fix: tests.yml retries apt-get once with --fix-missing (W0)
- Guard: `playbook:CI-ENV::ci_workflow_retries_apt`

## DATA-HOST-TIMEOUT

### L6 (2026-11-09) DATA-HOST-TIMEOUT

- Symptom: First live fetch-world (bergen-ncs) ran 30 min with no output and was cancelled; which source hung was unknown
- Cause: Python buffered stdout and no per-stage wall budget; NorKyst currents over a 4.4 x 2.1 degree box is the likely heavy part
- Fix: fetch_world.stage: flushed per-stage log, wall budget, timed-out stage recorded in manifest.errors, fetch continues
- Guard: `tests/test_place.py::test_fetch_stage_records_timeout_and_continues`

## DATA-SCHEMA

### L7 (2026-11-08) DATA-SCHEMA

- Symptom: Paper intake raised KeyError on a KPI phrase of a real paper ('objective function', 'total costs')
- Cause: The KPI regex matches variants that are not literal keys of the label table
- Fix: _kpi_label matches the longest known key inside the phrase and falls back to kpi_<slug>
- Guard: `tests/test_intake.py::test_kpi_label_variants`

## G1-PLAN-INFEASIBLE

### L1 (2026-11-06) G1-PLAN-INFEASIBLE

- Symptom: PyVRP routes hold the wrong clients, or every client looks served (is_client() always truthy)
- Cause: PyVRP 0.14: ScheduledActivity.is_client is a method; a client's idx counts clients only, node = idx + number_of_depots
- Fix: All PyVRP use goes through offsim/solve/pyvrp_adapter.py, which handles is_client() and index offsets once
- Guard: `playbook:G1-PLAN-INFEASIBLE::pyvrp_only_via_adapter`

## G3-LAND-CROSSING

### L2 (2026-11-06) G3-LAND-CROSSING

- Symptom: Contract reported sea legs crossing real land in the first Oslofjord run (audit 1)
- Cause: Legs were straight lines between quays; the solver's distances ignored the coast
- Fix: Sea legs route on offsim.worlds.sealanes and solver distances use the same lanes; report quay snaps
- Guard: `tests/test_sealanes_assets.py::test_lane_goes_around_the_island_and_passes_the_contract`

## QA-ASSET-DIM

### L9 (2026-11-11) QA-ASSET-DIM

- Symptom: s92 and aw189 failed the CAD QA gate: rotor 20 %, fuselage 30 %, width 340 % off; platform_jacket, tree, building had no measurable dims
- Cause: Solids were built from guessed proportions, not from the cited dimensions
- Fix: QA gate measures the bounding box against declared dims (1 %); rebuild the solid to the dim, never the dim to the solid (W12)
- Guard: `tests/test_cad_drawing.py::test_qa_passes_on_matching_dims_and_fails_on_5pct_wrong`

## UNKNOWN

### L8 (2026-11-11) UNKNOWN

- Symptom: Five failing tests were closed by editing the tests (commits 9268d3e..996fce0); it exposed a model gap (no slack in the air engine program)
- Cause: Premises of the tests were wrong, but nobody checked them first; an edited test can hide a real defect
- Fix: Check the test's premise against the paper/engine docs before editing; an edit carries a why: line and a LESSONS entry; doctor check tests_weakened lists removed asserts
- Guard: `playbook:UNKNOWN::tests_weakened`
