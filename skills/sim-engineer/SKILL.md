---
name: sim-engineer
description: Builds the simulation and ensemble layer of offshore_simulations - picks the engine for a scenario (replay, openclsim, wombat, orbit), writes experiment.yaml from a research gap, runs variants over NORA3 weather years and seeds with common random numbers, and reads the decision (supported / not supported / inconclusive). Use after a paper reproduces and before anything is visualised, or when asked for distributions, P90 delays, weather sensitivity or a variant comparison.
---

# sim-engineer

Code: `offsim/montecarlo/ensemble.py` (`run_ensemble`, `Ensemble`), `offsim/weather/years.py` (`load_years`),
`offsim/research/run_experiment.py` (`run`), `offsim/research/experiment.py` (`load`, `decide`). Tests: `tests/test_montecarlo.py`.
Definitions of each engine: `docs/ENGINES.md`. Layers: `docs/ARCHITECTURE.md` (L2 simulate, L3 ensemble).

## 1. Choose the engine (docs/ENGINES.md, "Choosing")
| Operation | Engine |
|---|---|
| Check a routing plan in time on sea lanes, berth/helideck queues (gate 2) | `replay` |
| Cyclic vessel logistics (PSV, ferry, barge) with weather windows, ensemble work | `openclsim` |
| Offshore-wind O&M (failures, CTV/SOV dispatch, availability) | `wombat` |
| Offshore-wind installation (WTIV, feeders, port) | `orbit` |
| Land legs on roads (trucks, vans, workers) | `road` |
| Bus, ferry, rail timetable replay (Entur GTFS) | `gtfs` |
- Set the engine in the scenario (`engine:`) and per variant in experiment.yaml. Pick the engine whose assumptions match the paper, not the prettiest output. `python -c "from offsim.engines import available; print(available())"` shows what imports here.
- If an engine cannot represent a scenario feature it raises `Unsupported`. That is a result (report it at gate 0), never a reason to approximate. `run_ensemble` lets it propagate.
- Two engines on one small instance must agree on deterministic KPIs within 1% before either is trusted on a large one.

## 2. Write experiment.yaml (next to scenario.yaml)
Schema and status rule: docstring of `offsim/research/experiment.py`. Rules:
- Start from a **reproduced** base (`offsim run` status `reproduced` or `re-run under assumptions`). No gap experiment on an unreproduced paper.
- Write `decision` (kpi, compare `[variant, baseline]`, `better: lower|higher`, `min_effect`) **before** running. Never edit it after seeing results.
- Every override carries a source or `assumption: true`. Weather limits come from `offsim/weather/operability.py`; unsourced ones stay assumptions and are listed in the report.
- `ensemble.weather` for the default loader: `{dataset: NORA3, path: <dir>, point: [lon, lat], years: [first, last], season: DJF}`; `seeds: N` (0..N-1) or a list. Season `DJF` of year Y = Dec Y .. Feb Y+1.
- KPIs must be ones the engine really reports (`wait_s`, `weather_wait_s`, `makespan_s`, `distance_km`, ... see ENGINES.md); do not list a KPI nobody computes.

## 3. Run
```
python -m offsim experiment papers/<paper>/experiment.yaml
```
Writes `experiment_report.json`. The Python API behind it: `offsim.research.run_experiment.run(path, build=..., workers=4, out=...)`.
- `build(experiment, variant) -> (problem, plan, world, engine)`; `offsim.pipeline.build_variant` is the builder the CLI uses.
- Plans for the base come from `python -m offsim run` (gates 0-4); an experiment reruns variants, it does not re-solve the base by hand.
- Weather data arrives via the `fetch-world` workflow (Actions) and `python -m offsim.worlds.fetch_world --pull <world>` (here or laptop). This workspace cannot reach MET Norway. Never substitute `synthetic_years`: it is TEST-ONLY, flagged `synthetic_weather`, and makes `reportable` False.
- All variants get the same years and seeds (common random numbers); `Ensemble.compare` pairs on (year, seed) and bootstraps a 95% CI (2000 resamples, seeded). Use `Ensemble.merge` when variants need different problems or engines.
- Use `validate=True` (default). `validate=False` is for profiling only and is recorded as `validated: false`.

## 4. What must pass before anything is visualised
1. `ensemble.ok` is True: every run passed `offsim.contract.validate` (no failures; each failure carries `(variant, year, seed)` so it can be replayed). On failure the experiment has no decision (`blocked`); hand over to `sim-corrector`, do not drop runs to get green.
2. `reportable` is True: real weather, validated, ok.
3. The base scenario's `report.json` gates 0-4 passed, plus 1b, 3e, 4b, 4c wherever the scenario set them (`sim-corrector`).
4. The decision comes from `decision.status` and `ensemble.comparisons` only. `inconclusive` is a valid finding: say so, or add years/seeds (more resamples do not help).
5. Numbers shown or narrated come from `report["ensemble"]` refs (`quantiles`, `comparisons`). Then `visual-director` (distribution shot, map shot, card shot).

## Traps
- Different seeds per variant destroy pairing; never re-seed inside an engine other than from the `seed` argument.
- Relative effect is measured against the baseline mean of the pairs; a baseline near zero makes it unstable, so state the absolute difference too.
- Weather years are few (about 20-25 NORA3 winters): the CI reflects year-to-year spread; do not inflate `seeds` to shrink it.
- NORA3 variable names in `years.py` follow `fetch.py` (metocean-api source) and are not yet checked against a live file; the first Actions pull should be logged in `docs/TESTLOG.md`.
