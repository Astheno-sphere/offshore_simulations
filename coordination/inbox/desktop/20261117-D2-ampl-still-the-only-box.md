# The runners are live, but the AMPL probe is still skipped — the laptop is still the only source

from: Claude (cloud session, integrator)
to: desktop
date: 2026-11-17
goal: the two D1 numbers, unchanged from 2026-11-15
owns: `coordination/reports/D1.md`
must not touch: anything under `papers/`, `docs/RESUME.md`
exit test: `coordination/reports/D1.md` carries the AMPL objective against the Pyomo twin on the CVRP demo
  (114643.0 m, seeds 1 and 2) and whelp Florø against 9980.4986
branch to use: `agent/desktop/D1-report`

Pointer, no new work in it. The weekly `live-check` workflow ran on a hosted runner for the first time on
2026-11-16, so Actions is working now — but the `ampl` probe reports `skipped: AMPL_LICENSE_UUID not set`,
and `barentswatch` reports `skipped: BW_CLIENT_SECRET not set`. The secrets are still not in the
repository. That means the `solve` workflow still cannot produce an AMPL objective, and the laptop remains
the only place those two numbers can come from.

So `20261115-D1-still-owed.md` stands exactly as written: until the report exists,
`offsim/solve/ampl/{cvrp,vrptw,whelp}.mod` are text-checked models only, and the 20 Windows test failures
are still readable only at `E:\OffsimLab\runs\L2_report.md`. `tools/ampl_studio/` is also still absent from
`catalog/tools.yaml`.

Nothing from the laptop has reached origin since 2026-11-15.
