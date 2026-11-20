# N10 — harness hooks H1-H5 are live on main; read docs/HOOKS.md before your next push

from: Claude (cloud session, integrator), 2026-11-20, scheduled sync
goal: information only. Nothing is asked of you beyond knowing what will now block you.
owns: nothing
must not touch: nothing
exit test: none

Arshad merged J2 to main on 11-19 (`.claude/settings.json`, `tools/hooks/gate.py`, `docs/HOOKS.md`,
`tests/test_hooks_gate.py`). Five hooks now refuse tool calls rather than relying on an agent remembering
a rule. Verified here by probing `gate.py` directly: H1 blocks a Write to `out/<run>/report.json`, H3 blocks
`git add out/...`, H4 blocks a licence-shaped string and prints only "a secret-shaped string is present",
and a read-only `cat` of the same path passes. Full suite on main: 974 passed, 22 skipped, exit 0.

The two that will touch your work:
- **H2**: `offsim/cinema/rules.py`, `offsim/cinema/visual_gate.py`, `tests/golden/*` and scenario
  `reported:` / tolerance lines may be written only on a branch named `agent/<who>/<id>` — so
  `agent/nordlys/<id>`, which is what you already use. A `git commit` that modifies one of them needs a
  `why:` line in the message read from `-m`, a heredoc or `-F`; a commit written in an editor is not seen.
- **H5** (Stop): a session cannot finish while a new or modified `*storyboard*.yaml` points at a report
  with a failed gate. If your intervention-render work ends on a storyboard whose run has not passed,
  expect to be held there.

Escape hatch, for the record: `OFFSIM_HOOKS_OFF=H2` (per-hook) or `disableAllHooks`. Using it is a thing to
say in your report, not a thing to do quietly.

Still open on you, unchanged for six days: N4 (the 24-winter metocean fetch, then the hosted live-check, then
the winter-infeasibility experiment), then N5, N6, N7. `agent/nordlys/vm-pile` is still refused under
20261114-N5-vm-pile-refused (unchanged at 8a08fa6); the three-way split in that note is still the way in.
