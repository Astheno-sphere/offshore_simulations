# Reference study: how to learn a film

For any agent handed a reference video and asked to "reach that level". Read this before you draw anything.
`docs/VISUAL_GRAMMAR.md` is the first worked example of this method; `docs/STYLE_REFERENCE.md` holds the look.

## The mistake this method exists to stop

Looking at a reference and trying to draw something that resembles it. That produces a copy of the surface with
none of the argument, costs a great deal, and fails the same way every time. We did it for a week. The reference
grade is not a look. It is a decision about what the film is *for*, followed by the removal of everything else.
You cannot see that decision by admiring frames. You can see it by measuring them.

So the order is fixed: **measure, name, budget, gate, build.** Never build first.

## Rules that do not bend

1. **Nothing from a reference enters git.** No frame, crop, trace, palette file exported from it, or redraw of
   its subject. Work under `out/reference/<slug>/` (ignored). What enters git is numbers and your own words.
2. **Learn the grammar, not the piece.** Our films are about logistics on Norwegian geography and our own
   results. A reference teaches a form; the content is always ours.
3. **Every claim about a reference is a measurement or is marked "by eye".**
4. **A form is only learned when the gate can refuse a frame that breaks it.** A description nobody enforces
   is a mood board.

## Step 1. Measure (five minutes, almost free)

    python tools/reference_study.py <video> --out out/reference/<slug>

It writes `measure.json`, `sheet.jpg` (one frame per second) and `motion.jpg` (a dense strip). Look at the two
sheets once. Do not page through the video frame by frame; the sheet is the film at a glance and costs one image.

The tool gives you: duration, size, cuts, the number of scene panels, the share of the frame that is scene, the
share that never changes, the dominant palette, the share of saturated pixels, luminance per second, and acts if
there is an event dip.

## Step 2. Read what the tool cannot (by eye, from the sheet)

Answer every line. One line each. If you cannot answer, say so; do not guess.

- **Question.** What single question does the film answer? Write it as a question.
- **Changing things.** List everything that changes over the film. Then strike the ones that are only the field
  responding. How many are left? (In the strongest form the answer is one.)
- **Subject.** What is the film about, and how is it marked out from everything else?
- **World.** What stays still, and what gives it scale (people, vehicles, lit rooms, known objects)?
- **Field.** What fills the space and moves? What physical quantity is it? Does it react to the subject?
  Where does it speed up, curl, or stall, and is that where physics says it should?
- **Cases.** How many instances are shown under the same treatment? How do they differ?
- **Clock.** What tells the viewer where they are in time? (A chip, a clock, a sun, a cut.)
- **Text.** List each text role with its size relative to the frame height and whether it ever changes.
  Count the words in the headline and in the body.
- **Absent.** What would a dashboard have included that is not here? (Charts, legends, colour bars, axes,
  footnotes, logos.) Absences are the most instructive part of a good frame.
- **Camera.** Does it move? If so, how fast and why?
- **Sound and loop.** Does it loop cleanly? Is the last frame a hold?

## Step 3. Put our frame beside it

Run the same tool on our nearest film or still, and fill the same table for both. The table in
`docs/VISUAL_GRAMMAR.md` section 2 is the model: reference in one column, ours in the next, one property per
row, numbers where the tool gave them. The rows with the largest gap are the lesson. Expect them to be about
*how much of the frame is scene* and *how many things change*, not about line weight.

## Step 4. Name the form

A form is a reusable way of making one kind of argument. Give it a one-word name and write, in order:

1. the one idea, in a sentence;
2. its parts (subject, world, field, cases, clock, text), each defined so that another agent could tell whether
   a frame has it;
3. its time structure, as shares of the film;
4. what it forbids;
5. which of our results it fits, and the test for whether a result fits (for the intervention form: is there
   something that can be switched?).

If the new reference is the same form as one we already hold, do not write a new form. Add what it teaches to
the existing one and say what changed. Five references of one form are one form.

Forms held so far: `section + map, one clock` (`docs/STYLE_REFERENCE.md`), `intervention`
(`docs/VISUAL_GRAMMAR.md`).

## Step 5. Budget and gate

Turn the measurements into limits and put them in `offsim/cinema/rules.py` as a named dict, each number with a
comment saying where it was measured. Then make `offsim/cinema/visual_gate.py` read that dict for the form's
shot kind, with one stable message per rule. Write two tests: one of our existing frames must fail the new
rules, and a frame built to the form must pass. If you cannot write the failing test, you have not found what
the reference does differently.

Limits are measured, then rounded toward the lenient side. The reference at 74 % scene gives a floor of 65 %,
not 74 %: the rule is there to refuse a dashboard, not to clone a layout.

## Step 6. Build, and judge with numbers

Build the shot kind to the form. Stills first, one per act. Run the tool and the gate on your own stills and
fill the step 3 table again with a third column. Report the rows where you still fall short. A row may not be
closed with an adjective.

Then, and only then, motion; and only on the VM or the `render` workflow.

## Physics is not optional

In every reference worth studying the moving texture is a solved field, not an effect. If our field does not
bend around the world, shed from it, and reorganise when the subject changes, the film has failed however good
the linework is. `docs/VISUAL_GRAMMAR.md` section 5 lists the six rules. Forcing comes from the run through
`report:` refs; an invented field is decoration and is refused.

## What a finished study leaves in git

- a section in `docs/VISUAL_GRAMMAR.md` (new form) or an amendment (same form), with the step 3 table;
- a dict in `offsim/cinema/rules.py`;
- gate checks and the two tests;
- a report in `coordination/reports/` with the step 2 answers, your stills' table, and what you disagree with;
- nothing else. In particular, no file under `out/`.

## Worked example to check yourself against

The "last tree" film behind `docs/VISUAL_GRAMMAR.md`. The tool reports: 20 s, 720 x 900, 0 cuts, 2 panels,
scene share 0.738, static share 0.262, saturated share 0.035, acts before 0 to 9 s, event 9 to 11 s, after
11 to 20 s. Read by eye from the state chips, the acts are nearer 8 / 3 / 9 s; the chip changes before the
panel is fully dark, which is why the two readings differ and why step 2 exists. If your run of the tool on the
same file does not return those numbers, stop and find out why before studying anything else.

## Studies done with the browser route (no download)
When a reference is a public post and no file can be saved, view it in Claude in Chrome (zoom the media region at intervals, read the page text),
write the report under `coordination/reports/abhinav-<slug>.md` (numbers by eye are marked, nothing committed from the images), push the learned
rules into `docs/VISUAL_DEFINITIONS.md` section 16, and when a form emerges add its budget to `offsim/cinema/rules.py` and an inspector with tests.
This gives structure, layout, palette, type and method; it cannot give easing, shot lengths, cut types or sound: those need a file and `eyes dna`.
Five studies so far, and the form they produced: `docs/VISUAL_GRAMMAR.md` section 10.

