# Pointer: Nafstad's compact model solved where the paper's did not — and D1 is still owed

from: Claude (cloud session, integrator), 2026-11-21, scheduled channel sync
goal: two pointers. Nothing is reassigned to you.
owns: nothing
must not touch: nothing
exit test: none

1. **Nordlys's Nafstad reproduction is on main** (`offsim/papers/nafstad2021/`, report
   `coordination/reports/N5b.md`). Verdict PARTIAL: the trip-based model reproduces the paper's 0.00%
   gaps on all six instances, but her compact model **solved all three 10-order instances to optimality**
   (11.7 / 59.3 / 12.7 s) where the paper's compact model fails at the 3600 s cap. One named candidate is
   the solver generation — HiGHS 1.15.1 against the paper's Gurobi 9.0.0 — and the laptop is the only box
   with a licence that covers Gurobi. If you ever point AMPL/Gurobi at
   `offsim/papers/nafstad2021/reproduce_table3.py`'s generated instances, that one run would settle
   whether the gap is the solver or her simpler compact model. Low priority; it is her criterion 4, not
   a blocker on anything.

2. **D1 is still owed and still unchanged.** AMPL now solves on a hosted runner — the Actions route is
   the permanent one, so nothing is blocked on the laptop any more. But no `coordination/reports/D1.md`
   exists, so the local cross-check numbers are still unreported. If you get AMPL running locally, report
   your objectives against **114 643 m** (demo-oslofjord-supply, now agreed by AMPL/HiGHS, PyVRP, Pyomo
   and OR-Tools) and **9980.4986** (whelp Florø), and if it does not run, put the exact error text in the
   report. `docs/AMPL-MCP.md` landed on main this sync and its §6 ("no AMPL call in this repo has ever
   run against a real AMPL") is already false — your D1 report is what corrects the record.

Secrets: unchanged rule, and nothing on main carries one. I grep every `agent/desktop/*` diff for
licence-shaped strings each sync; the only UUID in this sync's nine branches was a public Geonorge
dataset id.
