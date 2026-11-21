# Helideck-limits rerun: N4.3 sensitivity pair (sourced limits)

from: Nordlys (VM, self-taken — Broadcast 2 next step)
to: Nordlys
date: 2026-11-21
taken: nordlys 2026-11-21 17:10 UTC
owns: tools/winter_stress.py (CLI limit overrides), the two rerun outputs,
  coordination/reports/helideck-rerun.md
must not touch: main, build_scenario defaults in offsim/solve/whelp.py
  (which pair becomes the default is the integrator's call, not this task's),
  the original stress-test.json, secrets, data/
branch: agent/nordlys/helideck-rerun
exit test: stress-A.json and stress-B.json replayed from the existing plans
  checkpoint (no re-solve), with P90 unmet flights/week + infeasible days
  for each pair, compared against the original assumed pair (25 m/s, 6.0 m),
  in coordination/reports/helideck-rerun.md

## Sourcing (done, note ~/workspace/helideck-limits-sourcing.md)

- Wind, hard limit: SPA.HOFO.135 (Reg (EU) 2016/1199) — wind at the
  helideck ≤60 kt incl. gusts = 30.87 m/s. Applies in Norway via EEA.
- Wind + Hs, planning thresholds: IOGP Aircraft Management Guidelines,
  App. 6, Chart 2, p. 142 — routine consult 52 kt (26.75 m/s) / Hs 5.5 m;
  precautionary 59 kt (30.35 m/s) / Hs 7.0 m; deck motion pitch/roll ±3°,
  heave 1.0 m/s. Consult thresholds, not hard go/no-go.
- CAP 437 is the design standard, not the source for these numbers — the
  placeholder note in build_scenario ("source from CAP 437 helideck
  motion limits") is stale and must not be repeated.

## Rerun design

- Pair A (routine / conservative): wind 26.75 m/s, Hs 5.5 m.
- Pair B (regulatory / permissive): wind 30.87 m/s, Hs 7.0 m.
- Same driver, same 24 winters, same plans checkpoint
  (stress-test.json.plans.json, --plans; no re-solve — the plans do not
  depend on the weather limits). Only the limits change.
- Driver gains --wind-mps / --hs-m / --limits-src overrides; the output
  records the limits used, limits_src, and limits_assumption False when
  overridden (today it hardcodes True). Outputs to out/ (per the 2026-11-21
  rule, no new checkpoint on git).
- Report P90 + infeasible days + cancelled/rebooked/unmet for each pair
  against the original. The spread between A and B is the answer.

## Caveats to carry into the report

- SPA.HOFO.135 is gust-inclusive; the metocean series is hourly mean wind.
  Using mean against a gust limit understates breaches.
- Hs is a proxy for deck motion on mobile units (binding: pitch/roll ±3°,
  heave 1.0 m/s). Fixed installations need no Hs limit; the driver already
  applies Hs to mobile units only.
