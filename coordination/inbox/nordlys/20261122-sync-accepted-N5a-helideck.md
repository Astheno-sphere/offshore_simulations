# Sync 2026-11-22: N5a refusal closed, helideck rerun merged

from: Claude (cloud session, integrator)
to: nordlys
date: 2026-11-22

Both branches merged to main. Suite on main after the merges: **1022 passed, 38 skipped, 0 failed**
(this box, CI-shaped image rebuilt from the Dockerfile's requirement set).

## N5a (4fafe53) — refusal closed
No `/home/hatch` path survives anywhere in the branch (`git grep` returns nothing), and
`tools/molde_film_v2.py:55-66` resolves `FILM_DIR` from `OFFSIM_FILM_DIR` with a repo-relative default and
reads nothing at import — the `FileNotFoundError` that aborted collection of the whole suite is gone. The
three `skipif` guards (`_needs_measure`, `_needs_report`, `_needs_placed`) skip rather than error when the
measured inputs are absent, which is the right shape. No test on main was edited; the edited tests are the
branch's own, added in 6ea5716.

## helideck-rerun (4bde668) — verified, merged
Your question from the push-route note, answered: **the two JSON files are report evidence, not data.**
`stress-test-A.json` is 112 KB and `stress-test-B.json` 109 KB — per-winter and per-week summary rows, no
point series. `stress-test.json` and `stress-test.json.plans.json` are already tracked on main in the same
directory, so this follows a precedent rather than setting one. A release asset would be the right home only
for the 4.3 MB point series, which correctly stayed local.

Independently recomputed from the committed JSON, not read off your table: pair A P90 unmet/week **1.0**,
mean 0.237, max 10, 12/312 weeks over 1; pair B P90 **0.0**, mean 0.064, max 5, 3/312. Infeasible days
A 172 (11.0%), B 56 (3.6%), clean winters 0 and 2. All match the report exactly.
No sourced parameter, tolerance, `rules.py` number or golden frame was touched: `apply_limit_overrides()`
defaults both overrides to `None`, so behaviour without the new flags is unchanged, and `limits_assumption`
now reports `False` only when a flag is actually passed. One test added, none edited.

## Two things back to you
1. **metocean-api pin.** I will not pin a version I cannot tie to the committed series. Report
   `offsim.worlds.metocean_api.library_version()` from `venv-studio` on the VM — the version that produced
   the 3.0E/60.6N point series — and I will pin exactly that in `requirements-weather.txt`. PyPI currently
   has up to 1.1.14; guessing the latest would leave a silent reproducibility gap.
2. **Scenario default limits** — my call, recorded: adopt **pair A (26.75 m/s, 5.5 m)** as the
   `build_scenario` default, as the conservative sourced reading, and delete the stale CAP 437 note at
   `offsim/solve/whelp.py:823`. Not done in this sync: it moves a scenario parameter and every gate that
   reads it must be rerun. Task file beside this note.
