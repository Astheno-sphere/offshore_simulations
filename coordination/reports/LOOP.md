# LOOP — loop proof on Gribkovskaia & Slettemark 2025 (Florø), still sprites only

Branch: `agent/nordlys/loop-proof` (created from `origin/main` 11a0439 — main moved
from adfd5f9 during the task when Claude pushed the loop-proof fixture; explicit
refspec `git fetch origin +refs/heads/main:refs/remotes/origin/main`). No video.
No article run in this task; the real run is article-ready (see Part A).
Note: `scenario.synth.yaml` landed on main as 11a0439 (Claude) while this task ran.
My copy differed only in YAML escaping (`Florø` vs `"Flor\xF8"`); parsed dicts are
identical, so the Part B run stands and main's version is the one on the branch.
Claude's 11a0439 message says to use the "real bergen-ncs metocean dir" for the
reportable run — that path is stale: bergen-ncs holds only Jan 2024. Part A used
`data/worlds/bergen/metocean` (the winters), as corrected in the brief.

## Part B — machine test, synthetic weather (DONE)

Scenario: `offsim/papers/irinagribkovskaia-2025-tactical-helicopter/scenario.synth.yaml`
— a copy of the committed `scenario.yaml` with ONLY
`weather: {synthetic: {n: 1, hours: 336}}` added. Committed scenario untouched.
Report: `out/irinagribkovskaia-2025-tactical-helicopter-synth/report.json`
(trajectory.csv 384 rows). Re-run reproduced byte-identically after the real run
overwrote the first out dir; both runs now live in separate out dirs.

| Gate | Pass | Detail |
|---|---|---|
| 0_provenance | true | unsourced [], unsupported_classes [] |
| 1_plan | true | 19 flights, 1 helicopter (H1-10h), objective 9980.4986, recomputed identical |
| 2_replay_equals_plan | true | planned_variable_cost 4012.4986 = plan, flights_planned_per_week 19 = 19 |
| 3_contract | true | contract: OK |
| 4_paper | true | plan_cost 9980.4986 vs 9980 (gap 4.996e-05, tol 0.05), helicopters 1 = 1, window_hours 10 = 10 |

Status: `re-run under assumptions (synthetic weather, not reportable)`, reportable False.
Also measured: 5,863.3 km, makespan 106.31 h, 19/19 flights flown, 0 cancelled,
0 rebooked, 0 unmet, 28.7 flying hours, utilisation 0.90.
`offsim article` / `offsim publish` NOT run (synthetic weather is not reportable).

Still: `out/irinagribkovskaia-2025-tactical-helicopter-synth/loop-proof-still-synth.png`
(130,660 B). Storyboard `storyboard.synth.yaml` (one findings shot, kind
`state_gantt`, square 1080×1080, `visual: {strict: true}`).
`story.check`: **0 problems, 0 warnings**.

## Part A — real weather, NORA3 winter 2001–02 (DONE)

Fetch finished 2026-11-12T23:22:26Z, driver exit 0: 48 .nc files in
`data/worlds/bergen/metocean/` — 24 winters (Dec 2001–Dec 2023 + Dec 2024), ~2.1 GB.
Scenario: `scenario.real.yaml` — the committed scenario with ONLY
`weather: {dir: data/worlds/bergen/metocean, point: [2.7194, 60.276],
years: [2001, 2023], season: DJF}` added.
Note the correction: the dir is `data/worlds/bergen/metocean` (the winters), not
`data/worlds/bergen-ncs/metocean` (Jan 2024 only). The pipeline passes
`weather_years[0]` to the engine, so this run is ONE week under the FIRST year:
DJF 2001–02, week starting 2001-12-01, at grid cell (2.704, 60.278).
The 2024 pair sits outside years [2001, 2023] and was not used.
Report: `out/irinagribkovskaia-2025-tactical-helicopter/report.json`
(trajectory.csv 369 rows).

| Gate | Pass | Detail |
|---|---|---|
| 0_provenance | true | unsourced [], unsupported_classes [] |
| 1_plan | true | 19 flights, 1 helicopter, objective 9980.4986, recomputed identical |
| 2_replay_equals_plan | true | planned_variable_cost 4012.4986 = plan, flights_planned_per_week 19 = 19 |
| 3_contract | true | contract: OK |
| 4_paper | true | plan_cost 9980.4986 vs 9980 (gap 4.996e-05, tol 0.05), helicopters 1 = 1, window_hours 10 = 10 |

Status: `re-run under assumptions`, reportable None (no synthetic flag).
**Table 4 reproduces under real weather too.** The plan is unchanged (the
solver sees no weather); the weather acts on the replay only.

### The one cancellation (measured, not assumed)

19 planned, **18 flown, 1 cancelled, 0 rebooked, 1 unmet**. Distance 5,607.8 km
(vs 5,863.3 synthetic), utilisation 0.85, 27.4 flying hours.
Event: day 3 (Tue 2001-12-04, t = 292,500 s), flight to F4, `cancel` + `unmet`.
Cause measured at the grid cell: wind 19.3 m/s (assumed limit 25.0 — OK),
**Hs 6.53 m (assumed limit 6.0 — breach)**. Week Dec 1–8: wind max 20.6 m/s
(0 h over limit), Hs max 6.76 m, 13 h over 6.0 m. The cancellation was a sea-state
breach, not wind — same signature as the one-winter Bergen pilot.
Limits are assumptions (`sim.limits.wind_mps` 25.0, `hs_m` 6.0, both
`assumption: true`, unsourced — CAP 437 sourcing still open) and so are the
installation positions (`instance.base`, `stops[0..3]`).

Still: `out/irinagribkovskaia-2025-tactical-helicopter/loop-proof-still-real.png`
(134,440 B). Storyboard `storyboard.real.yaml` (same shot, strict).
`story.check`: **0 problems, 0 warnings**. The frame shows the WAIT state
(amber, 1.3 h) where the helicopter was held for the cancelled flight.
Article: NOT run here — the report is ready for `offsim article` (no synthetic
refusal applies: status has no "not reportable", reportable is None, not False).

## Fixes made during this task (mine, not the repo's)

- Narration template conflated planned with flown (`{measured.flights_planned} flights
  flown`). Fixed in both storyboards to
  `{measured.flights_flown} of {measured.flights_planned} flights flown`; both
  stills re-rendered and re-checked. The synth still was correct by accident
  (19 = 19); the real one would have overstated flown by 1.

## Not done / open

- No Actions workflow has ever been dispatched from this VM (no dispatch tool,
  no PAT). The hosted-runner path is still unproven. No workaround attempted.
- The still PNGs are binary and live in `out/` (gitignored); they cannot be pushed
  via the connector. The scenarios, storyboards and this report are on the branch.
- Known audit-7 defects, not touched here: gate 1 does not check time windows;
  `replay.py` `tw_late` (service end) disagrees with the solvers (service start).
- Nit, not a gate failure: the single-lane gantt leaves a wide empty band between
  the lane and the state-share bar. Left as rendered.

## Tests

Full suite before commit: **777 passed, 9 skipped, 0 failed** in 446.54 s
(Actions baseline 779/7 — same 786 collected, 2 environment skips on this VM).
No test was edited. No tolerance was changed. No gate failed, so no doctor run.
