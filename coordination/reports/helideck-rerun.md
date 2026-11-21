# Helideck-limits rerun: N4.3 under sourced limits

Task: `coordination/inbox/nordlys/20261121-helideck-rerun.md`
Branch: `agent/nordlys/helideck-rerun`
Date: 2026-11-21

## Question

Broadcast 2 named N4.3 the strongest result the machine has produced and
blocked it from any article: the go/no-go limits (wind 25 m/s, Hs 6.0 m)
were assumptions. This rerun replaces them with sourced limits and asks
whether the pre-registered finding — the lean 4-helicopter Bergen fleet
keeps P90 unmet flights/week ≤ 1 — survives.

## Sourcing (full note: ~/workspace/helideck-limits-sourcing.md)

- **Wind, hard limit — SPA.HOFO.135** (Commission Regulation (EU)
  2016/1199 amending Regulation (EU) No 965/2012, EASA Air OPS Part-SPA
  Subpart K; applies in Norway via the EEA): *"Operation to an offshore
  location shall only be performed when the wind speed at the helideck is
  reported to be not more than 60 knots including gusts."* 60 kt =
  30.87 m/s. Corroborated by the AAIB bulletin on G-MCSH (Elgin, Feb 2023),
  whose footnote names SPA.HOFO.135 as the regulatory basis for the
  operator's 60 kt limit.
- **Wind + Hs, planning thresholds — IOGP Aircraft Management Guidelines,
  Appendix 6, Chart 2, p. 142**: routine operations consult the company
  supervisor when winds exceed **52 kt (26.75 m/s)** or significant waves
  exceed **5.5 m**; precautionary operations at **59 kt (30.35 m/s)** or
  **7 m**; verify pitch/roll > ±3°, heave > 1.0 m/s. These are consult
  thresholds, not hard go/no-go limits.
- **CAP 437 is not the source.** It is the helideck design standard
  (turbulence σ ≤ 1.75 m/s, helideck movement). The placeholder note in
  `build_scenario` ("source from CAP 437 helideck motion limits") is
  stale; this task does not repeat it, and the default in
  `offsim/solve/whelp.py` is deliberately left unchanged (see Open).

## Method

- Two sensitivity pairs, same driver, same 24 DJF winters, same point
  series (3.0E, 60.6N), same solved plans — loaded from the existing
  `stress-test.json.plans.json` checkpoint (`--plans`), **no re-solve**:
  the plans do not depend on the weather limits.
  - **Pair A (routine / conservative):** wind 26.75 m/s, Hs 5.5 m
    (IOGP routine thresholds used as a hard cancel).
  - **Pair B (regulatory / permissive):** wind 30.87 m/s, Hs 7.0 m
    (SPA.HOFO.135 wind + IOGP precautionary Hs).
  - Reference row: the original assumed pair (25 m/s, 6.0 m).
- Driver change (`tools/winter_stress.py`): `--wind-mps`, `--hs-m`,
  `--limits-src` overrides, extracted into `apply_limit_overrides()`; the
  output now records the limits used, `limits_src`, and
  `limits_assumption: False` when overridden (it previously hardcoded
  `True`). Outputs:
  `offsim/papers/irinagribkovskaia-2025-tactical-helicopter/stress-test-A.json`
  and `stress-test-B.json` (result JSON on git, per the 2026-11-21 rule;
  no new checkpoint written).
- P90 method re-validated: recomputing it from the original
  `stress-test.json` per-week unmet counts reproduces N4.3 exactly
  (P90 1.0, mean 0.34, max 23, 13/312 weeks over 1).

## Results (solver variant [16,16,12,10], 1560 operating days)

| | ORIG (25, 6.0) assumed | A (26.75, 5.5) | B (30.87, 7.0) |
|---|---|---|---|
| Infeasible days | 121 (7.8%) | 172 (11.0%) | 56 (3.6%) |
| Winters with zero infeasible | 0 | 0 | 2 |
| Cancelled / rebooked / unmet | 199 / 92 / 107 | 210 / 136 / 74 | 65 / 45 / 20 |
| Cancel causes | Hs 123, wind 71, both 5 | Hs 185, wind 22, both 3 | Hs 60, wind 5, both 0 |
| **P90 unmet flights/week** | **1.0** | **1.0** | **0.0** |
| Mean unmet/week | 0.34 | 0.24 | 0.06 |
| Max unmet/week | 23 | 10 | 5 |
| Weeks over 1 unmet | 13/312 | 12/312 | 3/312 |
| Worst winter (unmet) | 2015: 31 | 2015: 18 | 2015: 5 |

## Reading

- **The headline survives sourcing.** P90 ≤ 1 holds under both sourced
  pairs — 1.0 at the routine end, 0.0 at the regulatory end. The lean
  fleet's pre-registered threshold is met across the whole sourced range.
- **But the margin is zero at the routine end.** Pair A meets the
  threshold exactly at the boundary, as the original did. Under the
  conservative reading the fleet has no slack; under the regulatory
  reading it has plenty. Any article must report the range, not a point.
- **The infeasible share moves a lot:** 3.6% (B) to 11.0% (A), original
  7.8% in between. "No winter clean" holds at A and the original, but B
  has 2 clean winters.
- **The causes flip as expected:** A cancels more on waves (185 vs 123,
  since 5.5 < 6.0) and far fewer on wind (22 vs 71, since 26.75 > 25);
  B nearly eliminates wind cancellations (5). A cancels more flights
  overall (210) yet leaves fewer unmet (74) than the original — the
  cancellations spread out and rebooking absorbs more (136 vs 92).
  Unmet is driven by clustered bad weeks, and 2015 is the worst winter
  under all three pairs.
- The paper variant ([16,14,10,10]) is unchanged by this rerun: it is
  infeasible at stage 1/2 before any weather is applied, so no replay
  exists for it under any limits.

## Caveats (carried, not resolved)

- SPA.HOFO.135 is **gust-inclusive**; the metocean series is hourly
  **mean** wind. Using mean against a gust limit understates breaches,
  so pair B is optimistic on wind by an unknown amount.
- Hs is a **proxy** for deck motion on mobile units (binding: pitch/roll
  ±3°, heave 1.0 m/s). Fixed installations need no Hs limit; the driver
  already applies Hs to mobile units only.
- Pair A uses IOGP **consult** thresholds as a hard cancel — a
  conservative modelling choice, labelled as such in the output's
  `limits_src`.
- The operator's own OM may set tighter per-installation limits (some
  NUIs at 45 kt per the CHC minutes). If one surfaces, it supersedes
  these generic figures for those installations.

## Open (not this task's call)

- Which pair becomes the scenario default in `build_scenario` — the
  integrator's call. The placeholder defaults (25/6.0) and their stale
  CAP 437 note are still in `offsim/solve/whelp.py:823`.
- The film/article may now cite the P90 range (1.0 at routine, 0.0 at
  regulatory) with the sourced limits — the N4.3 block on reporting is
  lifted for the P90 claim only, not for the infeasible-days share,
  which spans 3.6–11.0%.

## Tests

- New test `test_limit_overrides_replace_scenario_defaults` in
  `tests/test_winter_stress.py` (why: the override helper is new code
  and the rerun's correctness rests on it replacing the scenario
  defaults exactly). Targeted file: **4 passed**.
- Refactor check: after extracting `apply_limit_overrides()`, pair A was
  re-run and the output compared against the first run — identical
  except `wall_s` timing fields.
- Full suite: **1004 passed, 14 skipped, 0 failed in 678.81s** (this
  worktree, branch `agent/nordlys/helideck-rerun`, venv-studio).
