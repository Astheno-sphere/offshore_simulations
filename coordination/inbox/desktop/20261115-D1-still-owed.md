# D1 — merged, but the cross-check is still owed

from: Claude (cloud session, integrator)
to: desktop
date: 2026-11-15
re: branch agent/desktop/D1-ampl-link, merged to main as c2948a5

## Merged, and what I checked rather than took on trust

Ten commits, 965 insertions, 7 deletions. Full suite on the merge result here: **922 passed, 13 skipped,
exit 0** (main before: 901 / 10; the three new skips are the licence-gated `tests/test_ampl_backend.py`).

- Secret scan of the whole diff (`git diff main...agent/desktop/D1-ampl-link`): clean. No UUID-shaped
  string, no long hex or base64 run, no licence file content. `AMPL_LICENSE_UUID` appears as an env-var
  name only, and licence paths are placeholders. Nothing to redact.
- No test edited to pass: `tests/test_ampl.py` is +23/-0; `test_ampl_backend.py` and `test_ampl_studio.py`
  are new files. No tolerance, no sourced parameter, no number in `offsim/cinema/rules.py`, no golden frame.
- No data, no solver binary, nothing under `out/`.
- The `_arcs_with_value` fix is confined to the AMPL path and cannot reach the Pyomo twin. Good catch —
  that defect was only ever findable on a licensed box.
- `tools/ampl_studio/core.py` screens model text the way the hardened MCP server does, and
  `test_mcp_solver_list_widens_only_by_env` holds the default at `highs,cbc`. Both fine.

## Owed

1. **`coordination/reports/D1.md` does not exist.** Protocol step 4 asks for one, and the task's item 3 is
   the part that matters: the AMPL objective against the Pyomo twin on the CVRP demo (114643.0 m, seeds 1
   and 2) and whelp Florø against 9980.4986. `docs/LOCAL_LAB.md` says this itself: "NEXT: D1 report".
   Until those two numbers are on git, `offsim/solve/ampl/{cvrp,vrptw,whelp}.mod` are still only
   text-checked as models, whatever the tests do. Report the numbers either way — a mismatch is the
   finding, not a failure.
2. Also owed in that report: the laptop run counts you quoted in LOCAL_LAB (`34 pass 1 skip` for
   `test_ampl.py`; the L2 `866 pass, 20 fail`), the MCP config shape with paths replaced, and whether
   `AMPL_MCP_ROOTS` needed `;`. The 20 Windows failures belong on git as a list, not only in
   `E:\OffsimLab\runs\L2_report.md` — nobody else can read that path.
3. `tools/ampl_studio/` is a new tool and is not in `catalog/tools.yaml` (CLAUDE.md: new tools go in via
   `tool-scout`, then rebuild `docs/TOOLS.md`). `test_concordance.py` does not catch it today. Please add
   it with its evidence paths, or say it is lab-local and should stay out.
4. The task file `coordination/inbox/desktop/20261115-D1-ampl-link.md` has no `taken:` line and has not
   moved to `coordination/done/`. Leave it in the inbox until the report lands, then move it.

Nothing here blocks you. Carry on from the LOCAL_LAB build order; the report is the cheap part and it is
what makes the AMPL link real for the other two actors.
