# N6 exam — the "last tree" film, answered from the sheet alone

Examiner: nordlys. Date: 2026-11-15. Film: the 20 s reference Arshad uploaded
(`22555a142611870473831b911582c60bd98266c54aa523fa522c7202864c9a94.mp4`).
Method: `docs/REFERENCE_STUDY.md`. The eleven answers below were written from the tool
output and the two sheets only, before opening `docs/VISUAL_GRAMMAR.md`. The comparison
with the grammar is the last section, written after.

## Step 1. Tool confirmation

`python tools/reference_study.py <file> --out out/reference/last-tree` returns exactly the
worked-example numbers in `docs/REFERENCE_STUDY.md`:

- 20.0 s, 720 x 900, 30 fps, 600 frames, 0 cuts, 2 panels
- scene share 0.738, static share 0.262, saturated share 0.0352
- scene bands [0.022-0.391] (upper panel) and [0.400-0.769] (lower panel)
- palette: #352021 37.1%, #4b3b34 22.7%, #65594b 16.2%, #2b1816 11.8%, #23110f 7.8%, #ba9a74 4.4%
- acts (tool): before 0-9 s, event 9-11 s, after 11-20 s
- luminance per s: 60.7, 62.1, 65.2, 68.5, 68.4, 66.4, 62.6, 59.0, 49.0, 38.6, 36.9,
  54.3, 56.2, 57.3, 61.1, 64.0, 63.2, 60.8, 57.9, 55.3
- motion per s peaks at s10 (22.3), the felling moment

## Step 2. The eleven answers

- **Question.** What does a tree do for its place, and what is lost the day after it is felled?
- **Changing things.** (a) The wind/heat field intensifies and reorganises, fastest at the
  felling (motion 22.3 at s10). Strike: the field responding. (b) The tree itself: standing,
  then falling through the night, then lying on the ground. Keep. (c) The light: luminance
  68.5 at s3 down to 36.9 at s10, back to 64.0 at s15 — day dims to night during the felling
  and returns the day after. Strike: the clock. (d) The state chips: "the day before" to
  "felled in the night" to "the day after". Strike: the clock. (e) The people: by eye the
  small figures seem to shift slightly, but I cannot confirm movement at sheet resolution;
  they read as scale figures, not a change. Left after striking: **1 — the tree is felled.**
- **Subject.** The last tree in each place, one per panel. Marked out as the only saturated
  green in a near-monochrome brown/charcoal frame (saturated share 0.035, essentially all of
  it the canopy), the only large living form, centred in its panel.
- **World.** Two sites that never move: Hadrian's Wall ridge with the Sycamore Gap hollow
  above; a Hanoi street of row houses with balconies and lit ground floors below. Scale comes
  from tiny walking people on the wall path and the street, the houses' storeys and lit
  windows, and the wall itself. The Hanoi tree stands about three storeys tall.
- **Field.** Fine streaks and vortices filling the whole panel — wind and heat (the body names
  sun, shade, wind, rain, heat). It reacts to the subject: streaks bend around the canopy,
  shed vortices downstream of it, and after the felling the flow streams through the gap
  where the tree stood, faster and more chaotic. By eye it speeds up over the ridge crest
  and through the gap, curls into vortices behind the canopy and along the wall, and stalls
  in the lee of the buildings — which is where a flow would separate and accelerate, so it
  reads as physically placed rather than decorative. I cannot verify a solver from the sheet;
  that is a by-eye judgement.
- **Cases.** Two, under the same treatment: Sycamore Gap 2021 (a sycamore in a hollow on the
  Wall) and Hanoi 2016 (a street tree between row houses). Same acts, same field, same text
  roles, same clock chips. They differ in setting (rural ridge vs dense urban street), tree,
  and what the tree shades (open hollow vs street and shopfronts).
- **Clock.** The state chips in each panel's top-left: "the day before", "felled in the
  night", "the day after", beside the case label. Plus the light cycle (day to night to day).
  No running clock, no timeline, no dates beyond the case years.
- **Text.** Six roles, sizes by eye as % of the 900 px frame height: case chip
  "SYCAMORE GAP · 2021" / "HANOI · 2016" ~1.6%, never changes; state chip ~1.6%, changes
  twice; kicker "15 TREES THAT WERE CUT DOWN · 1775 TO 2024 · SIMULATED" ~1.6%, never
  changes; headline "That was the last tree" ~4.5%, never changes, **5 words**; body (two
  lines) ~1.6%, never changes, **34 words** ("Fifteen trees felled, poisoned or cleared,
  each standing at its site in its real place, run through its last day and the day after:
  sun, shade, wind, rain, heat and who could see it."); credit "@abhinavbw" ~1.2%, never
  changes. Only the state chip ever changes.
- **Absent.** No charts, legends, colour bars, axes, footnotes, logos (only the @ handle),
  maps, scale bars, data tables, lists of the 15 trees, before/after sliders, or numbers for
  wind, temperature or shade. The only numbers on screen are "15 TREES ... 1775 TO 2024" in
  the kicker.
- **Camera.** Static. No cuts, no pan, no zoom, no camera move of any kind for the whole
  20 s. All motion is the field and the subject.
- **Sound and loop.** Does not loop cleanly: frame 0 shows the tree standing, frame 19 shows
  it fallen — a one-way event. The last frame holds the after-state (the field keeps moving,
  so it is not a frozen hold). Sound is not determinable from the sheets; the delivered file
  appears video-only.

## Comparison with docs/VISUAL_GRAMMAR.md

(Written after the answers above, by reading the grammar file.)

Agreements — my answers match the grammar on: one changing thing (the subject) plus the
field's response; scene share 0.738 vs "about 74%"; 0 cuts, static camera; two cases under
the same treatment; the subject as the only saturated green; the field bending around the
canopy, shedding vortices, and reorganising after the felling; the clock as state chips
plus the light cycle (luminance 68.5 to 36.9 through the event); headline 5 words (cap 7);
body 34 words (cap 40); the absences (no chart, legend, colour bar, axes, map, scale bar,
numbers beyond the kicker); no clean loop; caption block 23.1% of frame height by the scene
bands (1 - 0.769) vs "about 22%".

Differences and amendments:

1. **Text roles: I count 6, the grammar's table counts 5.** The table lists "4 (kicker,
   headline, body, handle) plus one state chip per panel". The place-and-year chip
   ("SYCAMORE GAP · 2021") is a separate chip that never changes, and I counted it as its
   own role. Consequence: the `FRAME_BUDGET` cap of 5 roles would refuse the reference's
   own layout if roles are counted my way. Proposed amendment: define the role as "panel
   chip (place + state)" = 1 role, which keeps the cap at 5 consistent with the reference.
   The alternative (raise the cap to 6) spends the leniency the method reserves for
   measurements, so I propose the definition, not the raise.
2. **Act shares: I reported the tool's 45/10/45; the grammar uses 40/15/45.** The difference
   is ~1 s on the event's start: the light starts falling at s8 (luminance 49.0, down from
   59.0), the chip flips at s9. The study doc already documents the two readings. Not a
   disagreement about the film — but the method should say which reading the gate uses for
   `INTERVENTION["acts"]`.
3. **Vehicles: not confirmed by me.** The grammar lists "people, vehicles, lit rooms in
   every panel" as scale figures. I confirmed people and lit rooms; at sheet resolution I
   could not confirm vehicles. Flagged as unverified, not as a contradiction — it needs one
   zoomed frame to settle, and the method says to look at the sheets once.
4. **Body paraphrase.** Section 3.7 says the body states "what was held fixed and what was
   varied"; the actual body states what was run and what was watched, which section 6.5
   says correctly. Minor wording fix for 3.7.

Nothing in the grammar surprised me after the measurement, which is the point of the method:
the numbers did the work before the reading did.

## Note for the integrator

The full suite (855 passed, 12 skipped, 0 failed, 738.90 s) regenerated
`tests/fixtures/intake/synthetic_paper.pdf` in place — the `pdf` fixture in
`tests/test_intake.py` writes into the fixture dir, not a tmp dir, so every
suite run dirties that tracked file with a new CreationDate only. I restored
it before committing; this branch carries only the report + the taken line.
