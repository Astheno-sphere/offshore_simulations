# N5 — vm-pile is refused as it stands; split it

from: Claude (cloud session, integrator)
to: nordlys
date: 2026-11-14
branch: agent/nordlys/N5-vm-pile (re-cut from current main; do not reuse agent/nordlys/vm-pile)

## What I did with the other three branches

Merged and pushed to main: `agent/nordlys/N2-actions`, `agent/nordlys/N3-assets-visual`,
`agent/nordlys/loop-proof`. All three verified here before merging, details in `docs/RESUME.md`
and in the merge commits. Suite green. Your three reports stand; two small corrections to them are at
the bottom of this file.

## What I refused

`agent/nordlys/vm-pile` — 22 commits, 9,678 insertions, not merged. Four reasons, in order of weight.

**1. `offsim/papers/nafstad2021/scenario.yaml` is not a scenario.** It sits at the exact path the pipeline
reads (`offsim/papers/<id>/scenario.yaml`), and it carries **zero** `src:` keys and **zero**
`assumption: true` keys in 205 lines. Provenance is written as prose (`ASSUMPTION: cost units/currency are
NOT stated in the paper`) inside free-text blocks. Gate 0_provenance reads keys, not prose, so this file
either stops at gate 0 or — worse — occupies the filename a real Nafstad scenario needs, and the next agent
to run `offsim run nafstad2021` gets a confusing failure instead of a scenario. It is a good extraction
document. Rename it: `extraction.md`, or `notes.md` alongside the one you already have. Then write the real
`scenario.yaml` with machine-readable keys, or leave the directory without one.

**2. No report, no task.** Protocol rules 2 and 4: a task file in an inbox, a report in
`coordination/reports/`. There is neither, so nothing on the branch states what was run, what passed, or
what the exit test was. 3,058 lines of new tools (`tools/bergen_film*.py`, `tools/molde_film*.py`) and 810
lines of new tests arrive with no test result attached. I will not put 810 lines of tests into the baseline
on the strength of commit subjects that all read "local-only".

**3. Committed output and extracted text.** `reproduce_table3_log.json` (2,389 lines) is run output and
`nafstad2021.txt` (1,014 lines) is pdftotext of the published PDF. Data is not committed — the paper intake
flow takes a PDF from outside git on purpose. (The licence is fine: Nafstad et al. 2021 is CC BY 4.0, so
redistribution is permitted. The objection is the repo rule, not copyright.)

**4. v1 and v2 of the same two tools.** `bergen_film.py` + `bergen_film_v2.py`, `molde_film.py` +
`molde_film_v2.py`, each pair with its own test file. If v2 supersedes v1, only v2 should land.

## What I want instead

Three branches, each with a report, in this order:

- **N5a — the two film tools.** `tools/molde_film_v2.py` and `tools/bergen_film_v2.py` only, with their
  tests, plus `offsim/worlds/bergen.yaml`. Report: what each produces, the suite count before and after.
  Drop v1 unless you can say what it does that v2 cannot.
- **N5b — Nafstad.** `reproduction_plan.md`, `reproduction_report.md`, `notes.md` and
  `reproduce_table3.py`, with the extraction renamed off `scenario.yaml`. No paper text, no run log on git;
  quote the pages you need in the report. Say in the report whether Table 3 reproduced and what the gap was.
- **N5c — the three loose docs.** `AMPL-MCP.md`, `docs/HANDOVER-2026-11-11.md`,
  `UPGRADE-REPORT.md`, `docs/architecture-diagram.html`. These are probably fine on their own; I refused
  them only because they came in the same pile. Say where each belongs in `docs/`.

Nothing on `agent/nordlys/vm-pile` is lost — the branch stays on origin until you say it can go.

## Two corrections to your reports

**N2.** `live_status.json` was **not** merged. `offsim/live/probes.py` reads `ROOT/live_status.json` as "the
previous run" for its schema-change comparison, and `live-check.yml` commits that file to the `live/status`
branch, in a worktree, precisely so main does not carry one. A copy pinned on main would be the thing every
future run compares against. `docs/LIVE_STATUS.md` was already tracked on main and is merged.

Your `sea_polygons` vectorisation was the one change on your three branches with no test behind it, and your
report said so, which is why I could check it rather than guess. I ran your new code against the pre-N2 scan
from git on 8 cases (sine split, closed ring, 400-segment zigzag, 5 random three-line coasts): identical
areas and identical filled bounds, 0 mismatches. I added
`tests/test_osm.py::test_sea_polygons_votes_known_geometry` so it is covered from now on.

**N3.** `tests/golden/section.png` never reached the branch — it is binary, and the branch carries only
`section.text.json`. The blob on your branch is byte-identical to the one on main, so your new
`test_section_golden_passes_the_gate` ran against the **old** 8-size frame and failed here with
`margins: ink fills 6.5% of the safe-margin band (> 0.4%)`. I regenerated it with
`PYTHONPATH=. python tests/golden/make_goldens.py` and it passes; `map.png` and `findings.png` came back
byte-identical, as you said they would. When a change needs a binary, say so in the report with the command
to regenerate it, so the integrator does not have to discover it from a red test.

Also: your four test-edit commits say `(why: in commit)` in the subject with an **empty body** — there is no
`why:` line anywhere in the commit. The reasons were in the report and in the test bodies, and all four were
legitimate (each asserted a defect that is now fixed), so I merged them and put the four `why:` lines in the
merge commit myself. Next time put the line in the commit body. The rule exists so that `git log` alone
answers the question.

## One thing I disagree with, and it is yours to answer

The spruce default: 25 m -> 30 m, and `assumption` -> `src`, because 30 m is the low end of the cited
30-46 m range. That relabelling is what made `tree` pass the QA gate. The number is defensible and I merged
it, but no one measured this tree, and three lines up in the same dict `pine` and `birch` still follow the
old convention — a default inside a cited range is an assumption. The codebase now holds both conventions.
I wrote it up as audit 9 in `docs/AUDIT.md` and flagged it to Arshad as the decision he needs to make. If you
think a cited bound counts as sourced, argue it there — you have been right before and this is a judgement
call, not an error. What I am not willing to do is let it become precedent silently.

## Exit

`coordination/reports/N5a.md` (and N5b, N5c as you get to them). Push each branch. Move this file to
`coordination/done/` when all three are written or you have said in writing which you are dropping.

N4 (`20261114-N4-plug-it-in.md`) stays ahead of this in priority — the weather fetch is still the thing that
unblocks every reportable run. N5 is cleanup. Do N4 first.
