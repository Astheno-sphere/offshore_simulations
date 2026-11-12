# Style reference: the "section + map" grade (reverse-engineered from @abhinavbwj)

Source: two reference clips supplied by Arshad (NYC street trees / heat; NYC air-conditioner heat), 720×900, 30 fps,
20–30 s. His GitHub is `Abhinavbwj` (not reachable from the Claude workspace; nothing copied). This page records
*what makes the look work* as rules we can implement and check. We take ideas, not code or assets.

## What he does (observed)
His own method line, printed on the frame: *"Map: 30 m surface simulation anchored to the Landsat 8/9 mean at 11:30,
heated air carried on a south-west wind… Section: surface energy balance and 2D buoyant Navier-Stokes."*

1. **Two coupled views, one clock.** Top: a vertical *section* (street canyon cut through two buildings). Bottom: a
   *plan map* of the same phenomenon at city scale. A clock (`13:59`, air temperature) drives both; a 24 h day loops.
2. **Real physics in the section.** 2D buoyant incompressible Navier-Stokes (Boussinesq), heat sources from a
   surface energy balance. The flow is drawn as thousands of short advected streaks (the "brushed silk" texture),
   coloured by temperature; vortices and plumes are physical, not keyframed.
3. **Real data on the map.** A 30 m raster anchored to satellite land-surface temperature, advected by wind; a diverging
   colour map (teal = cooler than air → cream → orange/red = hotter). The map changes extent between shots (borough → street).
4. **Line-art architecture with life.** Building sections drawn as thin lines on flat warm fills; furniture, people,
   AC units, fire escapes as silhouettes. Scale cues everywhere (people, cars).
5. **Live readouts tied to the sim.** Labels under the section (`UNDER TREE 37°C · ASPHALT 49°C · NO TREE 52°C`) with the
   hot value in the accent colour; colour bars with units on both views; scale bar; "SIMULATED" tag.
6. **Editorial frame.** Kicker in small spaced caps (`HEAT, TREES AND PEOPLE ON 83,597 NEW YORK STREETS`), a bold
   geometric-sans headline with **one word in the accent colour**, a two-line plain-language deck, then a small
   grey methods line. Handle bottom-left. Portrait 4:5 for the feed.
7. **Palette** (sampled): ground `#331c22` / `#2a161a` (plum-brown, never pure black), streak greys `#846a5d` `#c9a98c`,
   accent amber `#e5a028`, diverging teal ↔ red for the field. Few colours, warm dark ground, one hot accent.

## Why it reads as "god tier"
Physics you can *see* (eddies, plumes) + real data you can *trust* (satellite-anchored, method line printed) + one
question in the headline + numbers that move with the picture. Every visual element is a variable of the simulation.
That is our rule already ("numbers only from report refs"); he applies it to the *texture* too.

## Our offshore translation
| His | Ours |
|---|---|
| Street-canyon section, 2D buoyant N-S | **Vertical sea section**: hull/platform line art; wind field over the helideck and superstructure (2D N-S with buoyant turbine-exhaust plume); wave surface from a JONSWAP spectrum at the hour's Hs/Tp |
| Plan map, Landsat-anchored temperature | **Plan map**: NORA3 Hs/wind field (`offsim/weather`), sea lanes, vessel tracks from the trajectory contract, ensemble ghost tracks |
| Clock + air temperature | Clock + Hs / wind speed; operability band (`weather/operability.py`) |
| `UNDER TREE / ASPHALT / NO TREE` readouts | `ON DECK GUST · HS · WAITING VESSELS · P90 DELAY` from `report:` refs |
| Headline question | "Which supply runs does the North Sea cancel first?" / "When can a helicopter land on Troll?" |
| Methods line | Generated from `report.provenance` (dataset, engine, ensemble size, gates passed) |

## Implementation map (specs; build to the docstrings)
- `offsim/physics/fluid2d.py` — 2D Boussinesq stable-fluids solver (Stam 1999 semi-Lagrangian + pressure projection)
  in numpy, Taichi backend optional; inputs: obstacle mask from section line art, inflow wind profile, heat sources.
- `offsim/physics/ocean.py` — wave surface elevation along a section from a JONSWAP spectrum (Hs, Tp from NORA3),
  random phases from the scenario seed.
- `offsim/physics/streaks.py` — advect N tracer particles through a velocity field, keep short tails, render as
  alpha-blended polylines coloured by a scalar (the brushed texture); same function draws wind over the plan map.
- `offsim/motion/diptych.py` — section (top) + map (bottom) layout, one clock, readout slots bound to `report:` refs,
  editorial header/footer from the storyboard; 1080×1350 (4:5) and 1080×1920 (9:16).
- `offsim/cinema/look.py` — preset `section-plan` with the palette above (ours, adjustable).
Rule: the section and the map are both *simulations or data*, never decoration; each carries a method line.

## Craft rules learned (2026-11-08, from our first attempts)
Why our first vessel looked childish next to the reference, and the fix now in code (`offsim/cinema/vessel_lineart.py`):
1. **Detail density at real proportions**: 4 polygons → ~170 primitives (bulwark posts, portholes, tiered house,
   wraparound bridge glass, mast and radar, rescue boat, cargo with corrugation, crew for scale).
2. **Line-weight hierarchy**: one stroke → three (outline 2.4, structure 1.3, detail 0.8 px).
3. **Anti-aliasing**: draw the section at 2× and downscale (Lanczos); thin lines stay crisp.
4. **Tonal fills**: hull, house, funnel, glass, cargo each a different value of the ground colour.
5. **Narration from measurement**: the film runs the simulation twice (deterministic); pass 1 measures, the deck text
   is chosen from the numbers, pass 2 renders. Our first caption ("rolled down over the cargo deck") was contradicted by
   the solver (crew zone +0 °C) and was replaced automatically. Every sentence on screen must survive this check.
6. **Every region earns its space**: header asks the question, section shows the mechanism, readouts give the live
   values, the chart answers the question over time (crew zone band marked), the methods line says how and what is assumed.
Reproduce: `PYTHONPATH=. python tools/section_film.py` (5 s, 150 frames, ~95 s CPU) or `--only N` for one frame.
7. **Map panel = real layers only** (`offsim/motion/mappanel.py`): OSM coastline, the vessel's route from a gated
   `offsim run` (the film refuses a run that failed gates 0–3), marker at the moment the section shows (southernmost
   sailing point = most exposed). Camera eases in at 0.16 zoom levels/s (cap 0.35); the overview is 1.8× the width fit
   so the frame never shows past the pulled data and the coast stays in view at the end. Map wind is uniform and
   labelled so until NORA3 is pulled. Sea state matched to place (outer fjord: Hs 2.0 m, Tp 6.5 s; open North Sea 3.5 m).
8. **Frame furniture**: handle top-right with the kicker; methods block names every source and every assumption.

## Level-up rules: from good to the reference grade (2026-11-08)
What still separates us from the reference, as rules with the tool that delivers each:
9.  **Density of real things**: every building footprint, every stop, every street tree-equivalent (every quay,
    every bus) drawn, not a sample. Tools: user/OSM layers, Overture buildings, datashader for >100k points.
10. **Two scales always**: a mechanism (section, street, deck) and its consequence at city/region scale, one clock.
11. **Light and time of day**: the frame's mood follows the simulated clock (sun elevation -> ground tint, window
    glow at night). Data: `cinema/look.py sun()` (spec) driven by the scenario time.
12. **Print-grade strokes**: skia-python (installed) for anti-aliased vectors with joins, caps and dashes; hairlines
    at 0.6 px for detail, 2.4 px outlines. PIL only for raster compositing.
13. **Terrain as texture**: hillshade + slope from Kartverket DTM (xarray-spatial), tinted in the palette, under every
    map; fjords read as landscape, not flat polygons.
14. **Colour scales are data**: diverging around a meaningful zero (ambient, schedule, plan), legend with units on
    every field, same scale across frames.
15. **One question, one answer, one surprise**: headline asks, chart answers, and the deck line states what the
    simulation found that a reader would not guess. Chosen from measurements (rule 5).
16. **Real vs simulated side by side** when we have it: AIS (gate 4b) or Entur Vehicle Positions (gate 4c) as faint
    ghost tracks under the simulated run.
17. **Typography**: one geometric sans (bold caps headline, regular deck, small caps kicker); no more than 3 sizes per
    frame plus the methods line. Install an open font (e.g. Montserrat or Inter, OFL) instead of DejaVu.

## CAD assets (2026-11-09)
Vessels, aircraft, vehicles, people, trees and buildings are exact solids at real scale, drawn as hidden-line projections
(Rhino Make2D look), not hand-placed primitives. Code: `offsim/assets/cad/` (contract `base.py`, engine `drawing.py`,
gate `qa.py`, status `registry.yaml`).
1. **Exact solids, real scale**: one CadQuery/build123d solid per asset in metres, axes per `base.py` (x forward, y port,
   z up, origin at keel/ground), named parts (hull, house, rotor, ...). Never scale a drawing to "look right".
2. **Projection**: `drawing.project(model, view)` runs OpenCASCADE HLR (exact visibility, parts occlude each other).
   Views: side (bow right), front, top, iso, or any vector. Cache per (asset, params, view) in `out/cache/cad/`
   (`project_cached`); films never run HLR per frame. Pitch/heave/roll = 2D transform of the cached drawing
   (`Drawing.transformed`), valid to ~5 degrees about non-view axes; re-project beyond that.
3. **Line classes and weights** (px at 1x, same hierarchy as rule 2): outline 2.4 (silhouette), visible 1.3 (sharp and
   turning edges per part), detail 0.8 (smooth/seam edges, muted), hidden 0.6 dashed (only with `show_hidden`), section 2.8
   (cut contours from `drawing.section`). Colours from `look.PALETTES` (ink, muted); per-part colour/weight via style.
4. **LOD by drawn size**: lines shorter than 0.75 px on screen are dropped and counted (`draw()` returns the stats);
   a film uses an asset only at a size where `qa` reports LOD >= 2 and edge density >= the gate (starting value 10
   polylines per 100 px of drawn height; tune against the reference). Far away = silhouette + outline only.
5. **QA gate** (`qa.qa`, `qa.passes`, enforced by `story.check` on any shot with `asset: {name, params, view,
   drawn_height_px}`): every measurable principal dim within 1 % of the solid's bounding box, all registry-required dims
   present, at least one principal dim sourced. An asset whose principal dims are all `assumption: true` is refused.
6. **Sources**: each principal dim carries `src` (class drawing, manufacturer data sheet, paper table, standard) with
   page/table; unsourced = `assumption: true` and listed in the QA report and on screen. External meshes need licence +
   source in `meta`. No hand-drawn outlines next to CAD assets in the same frame.

## Visual gate (2026-11-12): the machine judges its own frames
Rules 1-17 above were checked by eye in chat. `offsim/cinema/visual_gate.py` measures them on a rendered frame, and
`story.check` refuses a storyboard whose section or findings frame fails. A failing frame is a finding about the frame, never a
reason to retune the gate (a threshold changes only with a golden-frame measurement or a rule number to cite).

    r = inspect(img, {"kind": "findings", "text": texts})   # texts from `with capture_text(canvas=(1080, 1350)) as texts:`
    ok, reasons = passes(r, strict=False)                    # reasons: ["margins: ink clipped at the frame edge: right (51 px)"]
    ok, why = compare(frame, "tests/golden/findings.png")    # structural regression, not pixel noise

| Rule id | Severity | What is measured | Limit | Source |
|---|---|---|---|---|
| edges | hard | Sobel edge pixels (step >= 3 L*), whole frame and main panel (frame y 17 % to 75 %), on a 480 px wide copy | overall 0.050 to 0.374, panel 0.043 to 0.374: below = empty, above = mush | goldens: 0.5 x lowest (findings 0.0997 / 0.0870), 2 x highest (map 0.1871) |
| strokes | hard | median equivalent width of strong linework and type (coverage-weighted: a 0.6 px hairline reads 0.6 whatever its pixel phase) | >= 0.75 px at the delivered size (x w / preview width for a reduced preview) | CAD rule 4 (0.75 px visibility floor); goldens measure 0.90 to 1.45 px at 1080 wide (the brief's 1 px fails muted type at 0.90 to 0.98) |
| palette | hard | share of pixels farther than a tolerance from the palette gamut (declared colours, vessel fills and strokes, finding states, and every blend of two of them) | <= 5 %; tolerance = 0.5 x the palette's median nearest-neighbour Lab distance (4.9 Delta E, floor 3) | brief V1 (tolerance from the palette's own spread); goldens measure 0.5 to 0.8 % |
| accent | hard / soft | share of accent-dominant pixels | hard above 8 %; soft below 0.1 % | rule 6 (one accent) and brief V1; floor = half the lowest golden (0.21 %): the brief's 1 % floor holds for no reference frame (0.2 to 0.4 %) |
| contrast | hard / soft | WCAG ratio of every recorded text box against the ring of pixels around it | hard < 4.5:1 on a flat background; soft on a textured field (ring spread > 3 L*, streaks and maps have no single background) | WCAG 2.x AA; without text metadata only per-region luminance range, soft |
| type_scale | soft | distinct text sizes in the renderer's canvas px, the methods line (smallest group in the lower 45 %) not counted | <= 4 (rule 17 says 3) | rule 17, brief V1 |
| margins | hard | text boxes inside the safe area; ink in the safe band outside bleed boxes; ink touching the edge (clipped) | safe = 3 % of the short side, band ink <= 0.4 %, clip = any run of ink in the outer pixel row or column | findings golden sits >= 3.2 % from the edge; EBU R95 action-safe 3.5 % is the broadcast reference |
| balance | hard / soft | share of ink per half (top, bottom, left, right) and ink density per cell of a 3 x 3 grid | hard: smallest half >= 13 %; soft: <= 3 sparse cells (< 20 % of the mean) | goldens: smallest half 0.27 (findings), 0.42 (section); cells 0, 2, 0 sparse |

- **Soft** rules fail only with `strict: true`; otherwise they are returned in `report["warnings"]` and printed by `story` dry-run.
- **Kinds** (`section`, `map`, `findings`) set the main panel and bleed boxes (the sea section is full-bleed by design).
  A shot may carry `visual: {strict: true|false, kind: ..., spec: {<GATE_SPEC overrides>}}`; a typo in a spec key is a refusal.
- **Text metadata**: `capture_text()` records every `Canvas.text` and PIL `ImageDraw.text` call, so contrast, margins and type
  scale use the film's own text boxes. Draws onto other canvases (a map panel pasted into the frame) are filtered with `canvas=`.
- **Golden frames** (`tests/golden/`: section, map panel, findings fan; 1/3 scale; synthetic coast and ensemble) come from
  `PYTHONPATH=. python tests/golden/make_goldens.py` (`--table` prints the measurements the thresholds come from). `compare`
  fails on a 4 x 4 region whose ink or edge density moved more than 35 % (floors keep empty regions quiet).
- **Cannot judge**: whether the physics, the numbers or the labels are right; wrong geometry (a rotor on the ground passes);
  taste; colour-blind legibility; motion and timing; frames that render outside Python (map shots, cards, equations).
