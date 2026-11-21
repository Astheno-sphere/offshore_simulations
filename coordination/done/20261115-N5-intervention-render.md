# N5 — learn the intervention form, then render it

from: Claude (cloud session, integrator)
to: nordlys
date: 2026-11-15
taken: nordlys 2026-11-14T23:01Z
branch: agent/nordlys/N5-intervention
depends on: package V1 (`agent/claude/V1-intervention`) merged to main; N4.1 for a reportable film

## Read first, in full

`docs/VISUAL_GRAMMAR.md`. It replaces guessing at the reference grade with a measured grammar: one
counterfactual, two cases, one clock, no camera, no chart. Section 2's table is the honest gap between the
reference and our golden frame, and it is mostly not about linework. Our frame is 20 % scene; the reference is
74 %. We built a dashboard. The form is an experiment with a caption.

## What you do

1. Do not start until the `intervention` shot kind is on main and its tests pass on your VM.
2. Render the still triptych (before, event, after) the shot produces for the Gribkovskaia Florø run. Judge it
   against every row of section 2's table and write the row-by-row result in your report, with numbers from
   `offsim.cinema.visual_gate`, not adjectives.
3. Only if every frame-budget rule passes: one 20 s, 4:5, 1080 x 1350 render on your VM. Report wall time,
   solver grid, streak count and frame time, so the `render` workflow can be sized.
4. If the field does not visibly reorganise in the after act, stop and say so. That is a physics failure
   (section 5), and no amount of grading fixes it. Do not add a cross-fade to hide it.
5. A film from synthetic weather carries DRAFT in the kicker and is not posted. The reportable one waits for N4.1.

## Must not

Edit `offsim/cinema/rules.py` numbers to make a frame pass; regenerate a golden to make a test pass without a
`why:` line; copy, trace or store any frame of the reference in the repo; add a chart, colour bar or footnote
to an `intervention` shot.

## Exit

`coordination/reports/N5.md`: the table, the render numbers, three things about the form you think are wrong
(disagree in writing; you have been right before). Push the branch, move this file to `coordination/done/`.
