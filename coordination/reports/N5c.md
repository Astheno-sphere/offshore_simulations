# N5c — the four loose docs find their homes in `docs/`

Branch: `agent/nordlys/N5c-loose-docs` (from `origin/main` `1223aae` — the
D1-merged main, not `ae41e5f`).
Worktree: `~/workspace/tmp-n5c`. Task file:
`coordination/inbox/nordlys/20261114-N5-vm-pile-refused.md` (shared with N5a/N5b;
this is the last of the three — the task file moves to `coordination/done/` on
this branch).

## What landed, and where

All four files are taken verbatim from `origin/agent/nordlys/vm-pile`. They
are dated records, so they land as-is — the staleness in each is mapped below
instead of silently edited out. One line was added to `docs/ARCHITECTURE.md`
(pointing at the diagram); nothing else was edited.

| File (vm-pile) | Home on main | What it is |
|---|---|---|
| `AMPL-MCP.md` (root) | `docs/AMPL-MCP.md` | AMPL↔Muse-via-MCP investigation, 2026-11-09 |
| `docs/HANDOVER-2026-11-11.md` | `docs/HANDOVER-2026-11-11.md` | Handover to Claude, 2026-11-11 evening |
| `UPGRADE-REPORT.md` (root) | `docs/UPGRADE-REPORT.md` | Absorb + skia + Molde live run + Ghia, 2026-11-09 |
| `docs/architecture-diagram.html` | `docs/architecture-diagram.html` | System diagram, drawn 11 Nov 2026 from main @ 21db4f7 |

The two root files moved under `docs/` because that is where the repo's
written record lives (RESUME, SYSTEM_PLAN, VISUAL_GRAMMAR, and now these).
`docs/ARCHITECTURE.md` gained one line under its opening paragraph:
"Visual version: architecture-diagram.html — a snapshot drawn 11 Nov 2026
from main @ 21db4f7; its 'state right now' panel is dated, not current."
It had no link to the diagram before.

## What is stale in each (read the date first)

- **`docs/AMPL-MCP.md`.** Its §6 says "No AMPL call in this repo has ever
  run against a real AMPL" — **false since the D1 merge** (`c2948a5`):
  `b4ed06c` is the first real AMPL run of `test_ampl` on the laptop
  (amplpy 0.18, arcs read from the index). The investigation's §5 next step
  (approve the install, supply the UUID, build `custom.ampl`) is partly
  superseded by the desktop lab (`docs/LOCAL_LAB.md`, `tools/ampl_studio/`),
  but the cross-check numbers that would close the investigation are still
  owed: no `coordination/reports/D1.md`, so AMPL-vs-Pyomo (114643.0) and
  whelp Florø (9980.4986) remain unreported, and the `.mod` files are still
  only text-checked as models. The "amplpy not installed in any venv" row
  in §2 is still true for this VM; the laptop now has it.
- **`docs/HANDOVER-2026-11-11.md`.** Almost everything time-bound in it has
  moved on: `wip/cad-assets-heli` is spent (Claude's 2026-11-15 sync:
  content-identical to main, can be deleted); THREDDS maintenance ended
  12 Nov and the 24 winters are on disk; the thesis deadline (Sat 14 Nov)
  has passed; the pilot film v2 it describes as running was superseded by
  v3 and then the intervention film. It stays as a record of the 11 Nov
  evening, when all of that was live.
- **`docs/UPGRADE-REPORT.md`.** A 2026-11-09 snapshot: suite 369 passed
  (main now 922), "local main ahead 2 of origin/main" (long since merged),
  Ghia failing at Re ≥ 400 (still failing — that finding stands), RoadGraph
  endpoint-only noding with 911 weak components (still open — the Molde
  redo prerequisites list it), `fetch_world` needing TMPDIR handling for
  pyrosm (still open). The pyrosm/TMPDIR lesson and the Ghia numbers are
  the durable parts; the rest is history.
- **`docs/architecture-diagram.html`.** A snapshot drawn from main @ 21db4f7.
  Its "STATE RIGHT NOW — 11 NOV 2026" panel is dated: THREDDS down (back
  now), CI red on the wip branch (wip spent), "AMPL — licence ready, never
  called live" (called live on the laptop since D1), suite 399 (now 922),
  "whelp lives on the wip branch, not merged" (wip spent; whelp's merge
  state is the integrator's call). The layer diagram itself (L6–L5, the
  loop, the one rule) is still the architecture.

## Also on this branch: a note to the integrator

`coordination/inbox/claude/20261115-nordlys-bundles-awaiting-push.md` —
Claude's 2026-11-15 sync said nothing has arrived from me on origin since
2026-11-13. The note lists the seven committed branches sitting as verified
bundles on this VM (N4, N6, N5a, N5, A9, N7-reference-studies, N5b), states
that push is blocked here (no credentials), and asks for fetch+push. It also
raises the N7 number collision (his desktop task file vs my Ténéré study)
with my N10 proposal. Claude reads that inbox first every sync.

## Suite

Full suite on `1223aae` + this branch: **904 passed, 14 skipped, 0 failed in
624.65 s** (log `~/workspace/n5c-suite.log`). The first run on this branch
came back 903 passed, 14 skipped, **1 failed** — a concordance test
(`test_workflow_inputs_named_in_docs_exist_in_the_workflow_yaml`) read the
word "if" in `docs/UPGRADE-REPORT.md` ("Actions fetch-world inputs if the
local route ever blocks") as a fetch-world input name. The YAML is correct
(no such input), so the doc was reworded by one word to "inputs, should the
local route ever block" — the only edit to any landed file, recorded here and
in the commit message. The single test then passed in 0.37 s and the full
re-run is green. Collection parity verified: 915 tests collected on this
branch and on clean main alike; the gap to Claude's 922/13 on his box is
environmental (licence/platform-gated tests that do not collect on this VM),
not a regression. The `synthetic_paper.pdf` intake fixture was dirtied by
the suite run (CreationDate only) and restored before committing. One
restart killed the first suite run at ~17%; libEGL was wiped by the same
restart and restored from the cached debs before the re-run.

## Exit

N5c closes the vm-pile split: N5a (film tools) + N5b (Nafstad) + N5c (loose
docs) are all written. The shared task file moves to `coordination/done/` on
this branch. Nothing from this work is posted.
