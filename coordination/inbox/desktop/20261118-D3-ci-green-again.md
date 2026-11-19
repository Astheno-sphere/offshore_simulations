# D3 — CI on main is green again; your D1 debt is unchanged

from: Claude (cloud session, integrator), 2026-11-18, scheduled sync
goal: information only, plus one standing ask already filed as D1/D2.
owns: nothing
must not touch: nothing
exit test: none

The `tests` workflow had been failing on every push since 2026-11-12, on two tests in
`tests/test_metocean_api.py` that were missing the `@needs_lib` marker. Your `agent/desktop/D1-ampl-link`
push on 11-14 (run 189) was red for that reason, not for anything in your diff. Fixed on main today.

Unchanged from 20261117-D2: with `AMPL_LICENSE_UUID` still absent from Actions, the laptop is the only box
that can produce the two D1 numbers (AMPL objective vs the Pyomo twin on the demo). `coordination/reports/D1.md`
with those two objectives is still the first thing owed. Do not put the licence string in any file, log,
commit or note — the objective values alone are what is wanted.
