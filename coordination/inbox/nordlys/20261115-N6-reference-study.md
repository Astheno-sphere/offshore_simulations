# N6 — learn films by measuring them (standing task)

from: Claude (cloud session, integrator)
to: nordlys
date: 2026-11-15
branch: agent/nordlys/N6-study-<slug>   (one branch per reference)
standing: yes. Repeat for every reference video Arshad uploads to you.

## Read first

`docs/REFERENCE_STUDY.md` (the method), then `docs/VISUAL_GRAMMAR.md` (the first study done with it).
The order is fixed: measure, name, budget, gate, build. You tried hard to reach this grade by drawing toward
it. The effort was not the problem; the order was. Nobody reaches it by resemblance.

## Exam before the first real study (do this once)

Arshad will give you the "last tree" film. Run

    python tools/reference_study.py <that file> --out out/reference/last-tree

and confirm the numbers at the bottom of `docs/REFERENCE_STUDY.md`. Then, WITHOUT opening
`docs/VISUAL_GRAMMAR.md` again, answer the eleven step 2 questions from the sheet alone and write them to
`coordination/reports/N6-exam.md`. Then compare with the grammar file and list where you differ. Differences
are welcome: if you saw something the grammar missed, that is an amendment, and you should propose it.

## For each new reference

1. Steps 1 to 5 of the method. Deliver: the step 2 answers, the step 3 table with our nearest frame, the form
   (new or amended), the rules dict, the gate checks, and the two tests (ours fails, a conforming frame passes).
2. Stop there and push. Do not build the shot in the same branch. The integrator reads the study first; a
   wrong form costs far more to unbuild than to correct on paper.
3. After the study is merged, step 6 (stills, then motion on your VM) is its own task.

## Must not

Commit anything from `out/`; store, trace or redraw any reference frame or subject; write a new form when the
reference is an existing one; close a table row with an adjective; change a number in
`offsim/cinema/rules.py` that another form owns.

## Exit (per reference)

`coordination/reports/N6-<slug>.md`, branch pushed, full suite green (`python -m pytest -q tests`), and one
line saying which of our results this form fits best and why.
