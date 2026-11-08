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
