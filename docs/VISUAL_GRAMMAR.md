# Visual grammar: how a finding becomes a film

`docs/STYLE_REFERENCE.md` records what the reference grade *looks* like. This file records how it *argues*,
which is the part we kept missing. It was derived on 2026-11-15 from a second @abhinavbwj piece (a 20 s, 4:5,
"last tree" film: two places, one tree each, the day before and the day after it is cut down) measured frame by
frame, then set against our own golden frame `tests/golden/section.png`. Nothing of his is copied or stored in
this repo; only the grammar is.

The numbers this file quotes live in `offsim/cinema/rules.py` (`INTERVENTION`, `FRAME_BUDGET`). Change them there.

## 1. The one idea

**A film is one counterfactual, shown, not told.** Hold the whole world still, remove or change exactly one
thing, and let the physics show what that thing was doing. The viewer is never informed of the finding; they
watch it happen and reach it themselves. Everything else in this file follows from that sentence.

The reference film has no chart, no map, no camera move, no cut, no voice, and no number on screen except in
the kicker. It still lands, because the only thing that changes in 20 seconds is the thing the film is about.

## 2. What was measured

| Property | Reference | Our golden `section.png` |
|---|---|---|
| Shots / cuts | 1 shot, 0 cuts, fixed camera | 1 shot, fixed |
| Share of frame that is scene | about 74 % (two panels) | about 20 % (one strip) |
| Share that is text | about 22 %, in one block at the bottom | spread over the whole frame |
| Distinct text roles | 4 (kicker, headline, body, handle) plus one state chip per panel | 12 or more, including a footnote paragraph |
| Charts, colour bars, readout rows | none | chart, readout row, map, scale, north arrow, method lines |
| Things that change during the film | 1 (the subject), plus the field's response to it | time only; nothing is intervened on |
| Field | fills each panel edge to edge, wraps the subject, sheds vortices | horizontal streaks, barely deflected |
| Cases | 2, same treatment, stacked | 1 |
| Scale figures | people, vehicles, lit rooms in every panel | none |
| Saturated colour | the subject only | accent used on several unrelated elements |
| Time structure | before 40 % / event 15 % / after 45 % | none |

The verdict is in the second and sixth rows. Our frame is a dashboard with a small animation in it. His is an
experiment with a caption. Our linework, palette and type are already close; the *argument* is what is missing.

## 3. The intervention form

One shot kind, `intervention`, carries the grammar. Its parts:

1. **Subject.** The single thing the finding is about (a tree; for us a vessel, a helicopter, a weather window,
   a ferry departure, a time window, a second train on a single track). Drawn as the only saturated element.
2. **World.** Everything else, drawn in thin cream line on the dark ground, at true scale, with scale figures
   (people, a vehicle, a lit room). The world does not change during the film. That is what makes the change
   legible.
3. **Field.** A physical field that fills the panel and is advected every frame: wind, waves, current, heat,
   passenger flow, queue density. It must be *coupled* to the subject, so that when the subject changes the
   field visibly reorganises. The field is the animation. Nothing is keyframed.
4. **Acts.** `before` (the field in equilibrium with the subject present), `event` (the panel dims, the state
   chip changes, the subject changes), `after` (the field finds its new equilibrium). Fractions in
   `INTERVENTION["acts"]`. The after act is the longest because it is the finding.
5. **Cases.** Two panels, two instances of the same intervention (two places, two fleets, two winters), same
   clock, same treatment. One case is an anecdote; two under the same treatment is a pattern. The cases must
   differ in a way the viewer can see (open hillside against street canyon; calm January against storm January).
6. **Chips.** Each panel carries a place-and-year chip and a state chip. The state chip is the only text that
   changes. It is the clock.
7. **Caption block.** Kicker (count, range, the word SIMULATED), headline (the finding as a plain sentence,
   one accent phrase), body (two lines: what was held fixed and what was varied), handle. Static for the whole
   film.

## 4. Frame budget (enforced, not advised)

`FRAME_BUDGET` in `offsim/cinema/rules.py`; the visual gate reads it for `intervention` shots.

- Scene panels take at least 65 % of the frame height; the caption block at most 28 %.
- At most 5 text roles. No footnote paragraph, no chart, no colour bar, no readout row inside this shot kind.
  If a number is the point, it goes in the headline or the kicker, once.
- Method and provenance still have to be honest: they move to the last frame hold or to the post text, never
  into the scene. `synthetic` or `assumption` inputs put the word DRAFT in the kicker, where it cannot be missed.
- One saturated hue, on the subject. The accent amber is for the headline phrase and the place chip only.
- Each panel holds at least two scale figures.
- The field covers at least 85 % of each panel's free area, and its mean displacement between consecutive frames
  is above zero everywhere it is drawn: no frozen texture.
- Camera rates are zero. The form forbids camera moves; movement belongs to the field and the subject.

## 5. Field rules (why his eddies look real and ours do not)

1. **Solve on the whole panel, with the world as boundary.** Buildings, terrain, hull and deck are solid cells
   in the grid (no-slip), not pictures drawn over a free stream. Our exhaust section solved a small plume box and
   painted streaks elsewhere; that is why the streaks never bend.
2. **Give the flow something to shed from.** Inflow with a boundary-layer profile and a small unsteady
   perturbation, at a Reynolds number high enough for the obstacle to shed. Vortices are then physical.
3. **The subject is a body force or a porous region, and it is switchable.** A tree is drag plus shade plus
   transpiration; a vessel is a hull obstacle plus a heat source; a helicopter is a downwash momentum source.
   Switching it off at the event is the intervention. The solver keeps running through the event; the "after"
   state is computed, never cross-faded.
4. **Draw the field as advected streaks seeded everywhere,** length proportional to speed, re-seeded where they
   die, coloured by one scalar (temperature, wave height, load). Use the existing streak renderer in
   `offsim/motion/section.py`; extend it to the full panel and to obstacle masks.
5. **A second scalar may appear only under the subject** (rain or shade under the tree; spray under the
   helideck). It disappears with the subject, which is half of what makes the after act read.
6. **Forcing comes from the run.** Inflow speed, direction, wave height and period come from the scenario's
   weather series at the simulated hour, through `report:` refs. A field with invented forcing is decoration and
   the gate refuses it.

## 6. From a result to a script

A script is derived, not written freely. Given a validated `report.json`:

1. **Name the counterfactual.** What single thing differs between the two runs being compared? If more than one
   thing differs, it is two films. (`offsim experiment` already pairs runs under common random numbers.)
2. **Choose the subject and the field** from the table in section 7.
3. **Choose two cases** that differ visibly and are both in the report.
4. **Write the headline as the finding**, in at most 7 words, as a sentence a planner would say aloud. It has to
   be true of both cases. One accent phrase, the noun the film is about.
5. **Kicker:** count, range, SIMULATED (or DRAFT). **Body:** at most 40 words: what stands where it really
   stands, what was run, and which variables were watched.
6. **State chips:** three plain phrases for before, event, after.
7. Refuse when: the report failed a gate; the two runs differ in more than the declared variable; the headline
   holds for only one case; the weather is synthetic and the kicker does not say DRAFT.

## 7. Our subjects

| Domain | Subject (switchable) | World and scale figures | Coupled field | Two cases |
|---|---|---|---|---|
| Offshore helicopter (WFPPP) | the flight window, or one helicopter | heliport apron, helideck in section, deck crew, S-92 line art | wind and gust over the deck; operability limit as the event | calm winter week against storm week; Florø against Bergen |
| PSV supply (VRPTW) | one vessel removed from the fleet | quay section, cranes, deck cargo, crew | wave field and vessel motion; backlog on the quay as the second scalar | lean fleet against full fleet; same week, two winters |
| Ferry scheduling | one departure | ferry quay, queueing cars and foot passengers | queue density on the quay and the approach road | summer Friday against winter Tuesday |
| Bus (GTFS) | one route or one stop | street section, shelter, waiting passengers | passenger accumulation at stops; headway | before and after a timetable change, two corridors |
| Rail | a passing loop, or one train path | station section, platform, single track | train spacing and platform dwell | with and without the loop; two lines |
| Port call | a berth | quay wall, bollards, crane, pilot boat | current and wash in the basin | high and low water |

The second column is the test of whether a result is filmable in this form: if nothing can be switched, there is
no counterfactual, and the result needs a different form (a map film or a findings card).

## 8. What a second and third reference would add

This file holds one grammar. The first reference (section plus map, one clock) is a *where and how much* film;
this one is a *what did it do* film. Each further reference should be measured the same way (section 2's table)
and added as a named form with its own budget, not blended into these rules.

## 9. Build order

1. `INTERVENTION` and `FRAME_BUDGET` in `offsim/cinema/rules.py` (done with this file).
2. The `intervention` shot kind: panel solver with obstacle and switchable subject, full-panel streaks, chips,
   caption block, two cases on one clock; frame-budget checks in `offsim/cinema/visual_gate.py`; a golden.
3. Script derivation (section 6) in `offsim/motion/narrate.py`, refusing as listed.
4. One still triptych (before, event, after) from a validated run, judged against section 2's table.
5. Only then a 1080p render, on the VM or the `render` workflow.
