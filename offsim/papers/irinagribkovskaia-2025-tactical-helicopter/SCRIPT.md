# Film script: does the lean Bergen fleet survive 24 winters?

Status: APPROVED by owner 2026-11-25, conditional on the acceptance criteria in the next section. Numbers below come from the three stress-test files in this folder; they are NOT yet a
validated report, so none may appear on screen until the experiment passes `offsim.contract.validate` and the corrector
(see "Gates before any frame"). Format: 4:5, about 60 s, one through-line, one form (small multiples).

## The argument in one line
The paper's weekly plan needs one helicopter fewer than Equinor's actual resources, but it never tests weather
(Gribkovskaia & Slettemark 2025, p.35). Replaying the Bergen plan through 24 real NORA3 winters shows weather cancels flights,
and the sea state, not the wind, does most of it.

## What the data says (stress-test.json, -A, -B; Bergen instance, 93 flights a week, 24 winters x 13 weeks x 5 days = 1,560 days)
| Limit set | Source of the limit | Infeasible days | Flights cancelled (of 29,016) | Left unmet | Cause of cancellations |
|---|---|---|---|---|---|
| Original assumed: wind 25.0 m/s, Hs 6.0 m | assumption (flagged) | 121 = 7.8 % | 199 | 107 | Hs 123, wind 71, both 5 |
| A: wind 26.75 m/s, Hs 5.5 m | IOGP AMG App.6 Chart 2 p.142 (consult thresholds used as hard cancel) | 172 = 11.0 % | 210 | 74 | Hs 185, wind 22, both 3 |
| B: wind 30.87 m/s, Hs 7.0 m | SPA.HOFO.135 wind 60 kt incl. gusts (Reg (EU) 2016/1199); IOGP precautionary Hs 7.0 m | 56 = 3.6 % | 65 | 20 | Hs 60, wind 5 |
Worst winter in all three: 2011/12 (10, 14 and 6 infeasible days). Finding for the film: the answer swings from 3.6 % to
11.0 % of days depending on a limit the paper never states, and Hs is the dominant cause (A: 185 of 210 events).

Caveats that must be on the closing card (all true today):
1. Offshore installation positions are masked in the paper; ours are assumed and calibrated to reproduce Table 4 costs (a fitted choice).
2. One weather point (3.0 E, 60.6 N) stands in for all 20 installations.
3. Our solved Bergen fleet windows are [16,16,12,10] h, the paper's are [16,14,10,10] h: gate 4 flags the mismatch, so this is a replay of OUR plan, not the paper's exact one.
4. The decision rule "winter-robust if P90 unmet flights per week is at most 1" is an assumption and has not been computed from these files.

## Beats (about 60 s)
| # | s | On screen (picture first) | Words (at most 10 a line) | Data and engine | Needs |
|---|---|---|---|---|---|
| 1 Hook | 0-4 | Frame 0 already a working sea: a swell under a helideck with the S-92 waiting; the swell builds | "One helicopter fewer. Same people offshore." | Blender still-to-move, sea from `jonswap.Sea` driven by a real Hs hour | sea module (built), S-92 + platform (built) |
| 2 Claim | 4-12 | Map of the Bergen service area: Flesland, three distance rings 50 / 80 / 120 nm, 20 installation dots | "Paper: the lean plan flies 20 platforms from Bergen" | top-down map, land from OSM, rings from the 125 kn / distance data in the paper | bergen-ncs world on disk (NOT yet) |
| 3 Plan | 12-22 | The week as a flight schedule: 93 flights across 5 days, the fleet of 4 vs 5 as bars | "Table 4: 4 helicopters, not 5. Cost down 15 %" | plan trajectory from the run report | validated run (done: gates 0-4 with the fleet caveat) |
| 4 Gap | 22-28 | The same schedule, one sentence from p.35 stays on screen, nothing moves | "The paper does not model weather" | text only, quote under 15 words | exact wording from p.35 |
| 5 Test | 28-42 | THE FORM: a grid, 24 rows (winters) by 65 columns (days); each cell lights if a flight was cancelled that day; rows fill in one at a time under a slow sea | "Replay it through every winter since 2000" | 1,560 cells from `per_winter[].infeasible_day_list`; renders as 2D drawing | stress-test turned into a report |
| 6 Finding | 42-52 | Three grids side by side, one per limit set, same scale; the worst row (2011/12) outlined | "3.6 % to 11 % of days. It depends on the limit." | counts from the three result files | limits with sources on the frame |
| 7 Cause | 52-58 | One number change: the cause bar splits into Hs vs wind for set A | "Mostly sea, not wind" | A: Hs 185, wind 22, both 3 | same report |
| 8 Close | 58-62 | End card: the four caveats in two lines, paper, DOI, data credits | "Replay of our plan on assumed positions" | text | credits from world manifest |

The earlier shot "deck wind falls as the S-92 leaves" is NOT in this film: the cancellations are 88 % sea state in set A, so
wind at the deck is the wrong subject. It can live in a separate post about rotor wash.

## Presentation choices (open for the owner)
- One idea per frame, no chart chrome: the grid is the only data graphic, with a one-line legend.
- Number counted in the frame shown: the counts on screen are the ones drawn in that frame.
- Title length: lines of at most about 10 words (docs/VISUAL_DEFINITIONS.md section 3 for the rule and the conflict with our headline rule).
- Ground: dark maroon (our working default) or paper white: owner to choose; both are presets.
- The article carries the table above and the four caveats in full; the film shows only what the grid proves.

## Gates before any frame
1. Experiment passes the contract and the corrector (not yet; the three JSON files are results, not a validated report).
2. Every on-screen number is a `report:` ref into that report; limits carry their source lines as written in the table.
3. `story --dry-run` clean; lints from docs/VISUAL_DEFINITIONS.md section 10 clean on stills at 4:5.
4. Bergen world pulled (`python -m offsim.worlds.fetch_world --pull bergen-ncs`) for beat 2; until then beat 2 is a placeholder.

## Data and component checklist
| Component | State |
|---|---|
| Paper gap and pre-registered question | done (GAP.md) |
| Run of the paper's Bergen instance, gates 0-4 | done, gate 4 flags fleet windows (by design) |
| 24 winters of NORA3 weather, replay | results exist (three JSON files, unreviewed) |
| Limits with sources | A and B sourced; original assumed |
| Experiment report with `report:` refs | MISSING: build from the three files |
| Land, coast, depth, installations for the map | MISSING on disk: needs the `fetch-world` run for bergen-ncs |
| Heliport massing (Flesland buildings with heights) | MISSING: world `flesland-heliport` added; needs a fetch run |
| Sea surface from Hs | built (jonswap, branch agent/claude/visual-engine) |
| S-92 and platform solids | built, draft quality |
| Grid shot (24 x 65) | MISSING: to build (2D, new shot kind) |
| Script review by owner | this file |

## Owner approval (2026-11-25) and acceptance criteria
Approved on condition that the film is a simulated map with good massing, correct routes, academically accurate simulation, data
from the paper and its model file, and the gaps turned into research direction. Each condition becomes a check:

| Condition | Check before the frame ships | Source in repo |
|---|---|---|
| Simulated map, real geography | land, coast, relief, bathymetry from the pulled world; no hand-drawn coast | `offsim/worlds/bergen-ncs.yaml` (on disk); Flesland inset from `flesland-heliport` |
| Good massing | Flesland buildings extruded to `height_m`; `levels x 3 m` cells flagged as assumption on the frame; count of buildings shown is the count drawn | OSM `height_src`/`height_assumption` |
| Right routes | every drawn leg is a leg of `plan.routes` in the validated run report, great-circle at 125 kn, from the run's heliport to the installation; none drawn by eye | `report.json` `plan.routes`, `trajectory.csv` |
| Academically accurate | paper's Table 4 reproduced (gate 4), Tables A1-A3 demand and windows, p.25 constants; deviations (fleet windows [16,16,12,10] vs [16,14,10,10], masked positions) on the closing card | gates 0-4, `scenario.yaml` |
| Paper's data and model file | parameters come from `scenario.yaml` / `instances.yaml` with page refs; positions marked fitted | `instances.yaml` calibration block |
| Gaps become direction | closing beat 9 below | GAP.md |

Edits to the beat table above:
- Beat 2 draws the 20 installation dots from `instances.yaml` (assumed, fitted to Table 4), labelled as such.
- Beat 3 draws the plan's actual legs from `plan.routes`, not a schematic; a Flesland massing inset opens the beat.
- Beat 4 quotes p.35 verbatim: "operational needs and weather conditions" (5 words); the sentence it ends is the gap.
- Caveat 4 is closed by Nordlys's weekly-series check: P90 unmet flights per week is 1.0 (original), 1.0 (A), 0.0 (B), against the assumed rule P90 <= 1. State it as: survives under the regulatory limits (B), sits on the boundary under the IOGP limits (A). The rule itself stays flagged as an assumption.

## Beat 9: research direction (new, 58-70 s; film becomes about 70 s)
Words come from the gap, one line each, nothing numeric beyond the report refs:
1. Plan for weather: size the fleet and slack against winter replays, not a deterministic week (the paper's own p.35 omission).
2. Name the limit: the answer swings 3.6 % to 11 % on the helideck and sea-state limit; the limit is a decision variable, not a constant.
3. Unmask the positions: the replay used one weather point and assumed positions; per-installation NORA3 points are the next test.
4. Test the rule: P90 <= 1 unmet flights per week is ours; the operator's tolerance should set it.
5. Test the other bases: Stavanger and Florø through the same winters (instances exist, replays not run).
Each line maps to a pre-registered follow-up in GAP.md before it is shown.

## Work split
| Piece | Owner | State |
|---|---|---|
| Validated experiment report with `report:` refs from the three stress-test files and the P90 check | Claude (integrator) | next; needs Nordlys's weekly series pushed (waiting on owner's push go) |
| Grid stills (beats 5-7) | Nordlys | built from files; re-render after the report exists so numbers come from `report:` refs |
| Map, massing, route shots (beats 2-3) | Nordlys (Blender, bergen-ncs on his disk) | next, after the Molde re-render |
| Closing beat 9, caveat card, credits | Claude | to write after the report |
