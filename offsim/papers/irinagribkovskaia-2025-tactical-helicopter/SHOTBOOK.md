# Shot book: "Does the lean fleet survive winter?" (about 70 s, 4:5, silent-first)

Companion to SCRIPT.md (what is said and proven). This file says how each frame is made. Numbers and rules come from
`offsim/cinema/rules.py` and `docs/VISUAL_DEFINITIONS.md` (section numbers in brackets); colour tokens come from `style.json`
(never hex typed here). Every on-screen number is a `report:` ref. Status: DRAFT until the validated report exists.

## Story form
- Device: one question, one proof. The question is asked in the first 5 s and answered by a single drawn object (the 24 x 65 winter grid). [1]
- One world: the North Sea from Bergen. We enter it through objects already on screen: helideck, helicopter, helipad on the map. [1: one world]
- Order: hook 7 %, setup 13 %, plan 17 %, gap 8 %, proof 20 %, payoff 14 %, cause 8 %, direction 7 %, end card 6 % (holds 3 s). [1: shares bent for a proof film]
- Silent-first: LinkedIn autoplays muted. Every line is burned-in text, one line at a time, at most 10 words, no trailing period. No audio is required; if added, a low sea bed only, no music hits. [3]
- Frame 0 is the thumbnail: a working sea with the S-92 on the deck, never black, never a logo. First 0.4 s static. [rules: film_hold_in_s] 

## Studied rules now in force (docs/VISUAL_DEFINITIONS.md section 16; supersede the grammar below where they conflict)
- Ground near-black, one amber accent carries data, cream line, one steel blue for the comparison (limit set B or the paper). Tokens in `style.json`.
- Every simulated frame has the real map of the same window above (Flesland inset, Bergen service area) and the result below, labelled `REPLAY / <one-line finding>`.
- The frame says what it is not: "replay on assumed positions, one weather point". Method on the frame as refs: NORA3 DJF, 24 winters, limit and source, 125 kn.
- One template for shots 4 to 8 (kicker, headline with accent, body, source line, handle); locked camera on every map shot.
- Open with a human anchor: Flesland, a winter morning, passengers waiting (cabin section with lit windows and figures; see studies AB2).
- Numbers: largest type, unit small, qualifier line below; before-to-after with an arrow for "3.6 % to 11 %".

## Frame grammar (all shots)
- Aspect 4:5. Safe margin 6 % sides, 8 % top and bottom. Hero on a thirds point, one focal point per frame. [5]
- Three depth layers: ground (map or sea) ambient, mid (routes, rings, grid) secondary, fore (the one number or line) primary. [5]
- Type: Montserrat. Title 4-9 % of height; quiet line 2.5-4 %; floor 2.6 % of short side (lint). Tabular figures, one formatter, one accent word per line. [3]
- Colour roles: ground dark (oxblood family) or paper (owner picks; both presets). Gold = the plan and the fleet. Orange = weather harm (cancelled flight, infeasible day). Charcoal = structure (coast, rings, grid lines). One accent per frame. Subject and ground separate in value. [4]
- Linework: weights fixed per role (coast heavy, rings hairline, plan legs medium, grid cell borders hairline); no glow, no particles, no gradient washes. [9]
- Banned tells: dark void with floating things, everything fading up, three cards in a row, docked logo, side-by-side panels instead of a scene. [9]

## Camera and motion defaults
- One move per shot, named with from-to values, duration, easing. Eases: arrivals easeOutQuint, camera moves easeInOutCubic, exits easeInCubic and 40-50 % shorter than the entrance. Springs critically damped (1.0). [2, 8]
- Camera limits: zoom at most 0.35 levels/s (target 0.15-0.25), pitch 10 deg/s, orbit 6 deg/s, pan 0.6 widths/s, shot at least 2.5 s. [rules.py CAMERA]
- Cuts: change bearing by 0 or at least 30 deg; keep the helicopter's screen direction (Bergen to offshore is screen-left); cut at the fastest frame of a move. [8, rules.py]
- At most 3 whole-frame beat hits in the film. This film uses 1 (the grid reveal in beat 6). [8]

## Shots
| # | Time | Frame and subject | Engine | Camera | Motion graphics and timing | Data (report ref) |
|---|---|---|---|---|---|---|
| 1 Hook | 0-5 s | S-92 on a platform helideck, North Sea swell beyond, heading screen-left. Hero on the lower-left third; deck horizon in the upper third | blender (`helideck_spec`, `Sea` from `jonswap`, Hs of a real winter hour) | Static 0.4 s, then dolly push 38 m to 30 m over 3.6 s easeInOutCubic, 40 mm lens | Line 1 at 1.2 s: "One helicopter fewer." (easeOutQuint, 0.5 s). Swell animates throughout, rotor idle | Hs of the hour shown on a small tag only if it is a ref |
| 2 Setup | 5-13 s | Bergen service area, north up: coast, relief, three hairline rings 50/80/120 nm, 20 installation dots (gold), Flesland as a larger dot | blender map render (no ink; colour boundaries carry it), land/relief/bathymetry from the world on disk | Descend: pitch 0 to 35 deg, zoom 0.2 levels/s, 8 s, easeInOutCubic; 6 deg/s orbit cap | Rings draw outward 0.8 s each, staggered 30-50 % overlap; dots land with a settle (no bounce); one line: "Paper: 4 helicopters, not 5" | rings from `plan` distances; fleet 4 vs 5 and cost -15 % from Table 4 refs |
| 3 Plan | 13-26 s | Opens on a Flesland massing inset (buildings extruded to height_m; assumed heights tinted and tagged), push to a helipad, match cut to the same pad on the map, then the plan's real legs light one by one with an S-92 following one leg at 125 kn | blender (massing + routes) then 2D strip | Follow shot: look-ahead 4-6 s, lead space 30-35 %, critically damped follow | Legs draw in schedule order, 12 flights per second then settle to real time on the one followed; a week strip (5 days x 93 flights) fills under it, gold; building count shown equals buildings drawn | legs from `plan.routes`; 93 flights/week, 125 kn, 10 min deck, 1 h turnaround (p.25) |
| 4 Gap | 26-32 s | Plain ground, the paper's sentence fragment set large, accent on the word "weather" | 2D type | Static, 6 s hold | Fragment types in over 0.6 s easeOutQuint, holds 3 s (0.5 s + 0.3 s a word, last line 2 s), source "Gribkovskaia and Slettemark 2025, p.35" in quiet line | quote "operational needs and weather conditions" (5 words) |
| 5 Test | 32-46 s | THE GRID: 24 rows (winters 2000/01 to 2023/24) by 65 columns (days); empty at start, gold-outlined | 2D drawing (skia/panel), vector | Static camera, a slow 1.5 % creep over the hold | Rows fill one at a time, 0.5 s each, with a 3-frame stagger across columns; a cell turns orange when a flight was cancelled that day; counter in the corner increments with easeOutCubic. Beat hit 1: when row 2011/12 completes, a single 6 % scale pump on that row only | 1,560 cells from `per_winter[].infeasible_day_list`; counter = infeasible days of the shown limit set |
| 6 Finding | 46-56 s | Three grids at equal scale, B, original, A left to right of density | 2D | Static; the camera does not move, the grids do | Grids slide in on a 0.4 s stagger from the right; labels carry limit and source; 2011/12 row outlined in all three; headline: "3.6 % to 11 % of days" with the accent on the range | 56/1560, 121/1560, 172/1560; wind and Hs limits and sources as written in SCRIPT.md |
| 7 Cause | 56-62 s | One horizontal bar for set A, 210 events, split sea 185, wind 22, both 3; the grid dims behind | 2D | Static | Bar draws left to right 1.0 s easeOutCubic, segments labelled on the mark; line: "Mostly sea, not wind" | cause counts from the report |
| 8 Direction | 62-67 s | Five numbered lines appear one at a time over the dimmed map | 2D type over blender still | Slow parallax drift 3 deg/s on the ground only | Each line holds 0.9 s, 30-50 % overlap on entrances; last line holds 2 s; lines from SCRIPT.md beat 9 | P90 values 1.0 / 1.0 / 0.0 as refs |
| 9 End card | 67-70 s | Caveats in two lines, paper, DOI, data credits | 2D type | Static, holds 3 s | none | credits from the world manifest; caveats from SCRIPT.md |

## Simulation accuracy required behind the pictures
- Sea in shot 1 is `jonswap.Sea` seeded from the real Hs and Tp of a stored NORA3 hour; the seed and the hour go in the shot spec.
- Routes in shot 3 are `plan.routes` from a run that passed gates 0-4; leg times use 125 kn; flights the replay cancelled are drawn orange in shot 5, not in shot 3.
- The grid in shots 5-7 uses the replay's own day lists; nothing is recomputed in the renderer.
- Rotor wash and deck wind are not shown (the film argues sea state). Rotor idle is shown only as geometry.

## QA gates before any render
1. `offsim.contract.validate` and the corrector pass on the experiment report; `story --dry-run` clean.
2. Stills at 4:5 for start, middle and end of each shot; lints: text below floor, overflow, two focal points, number not a ref, shot under 2.5 s, cut under 30 deg, constant speed, more than 3 beat hits.
3. Building count and leg count shown equal the drawn count (Nordlys's counting rule).
4. Heavy renders go to the `render` workflow; stills and drafts here.
