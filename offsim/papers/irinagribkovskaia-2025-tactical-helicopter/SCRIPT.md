# Film script: does the lean Bergen fleet survive 24 winters?

Status: DRAFT for owner review. Numbers below come from the three stress-test files in this folder; they are NOT yet a
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
