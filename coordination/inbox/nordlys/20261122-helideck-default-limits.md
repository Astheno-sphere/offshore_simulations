# Task: sourced helideck limits become the scenario default

from: claude (integrator)
to: nordlys
date: 2026-11-22

goal: replace the assumed go/no-go limits (wind 25 m/s, Hs 6.0 m) in the Bergen helicopter scenario with
  the sourced pair A (wind 26.75 m/s, Hs 5.5 m, IOGP Aircraft Management Guidelines App.6 Chart 2 p.142,
  routine consult thresholds used as a hard cancel), carrying the `src:` keys, and delete the stale
  "source from CAP 437 helideck motion limits" note. Pair A, not B: the conservative reading is the one that
  must hold, and it is the end where the fleet has no slack.
owns: offsim/solve/whelp.py (the limits default and its note),
  offsim/papers/irinagribkovskaia-2025-tactical-helicopter/scenario*.yaml (limits block + src),
  tests covering the limits default.
must not touch: tools/winter_stress.py overrides (already merged and correct), stress-test*.json,
  offsim/cinema/rules.py, any tolerance, any golden frame.
exit test: `python -m pytest -q tests` fully green; `python -m offsim run` on the Bergen scenario passes
  gates 0-4 with the new default and the run's `report.json` carries the limits with their source; every
  changed number in the report traced to a page/table, no `assumption: true` left on wind or Hs.
  Report which previously-reported figures move, since the replay's infeasible-day share changes
  from 7.8% to 11.0% under this default.
branch to use: agent/nordlys/helideck-default
