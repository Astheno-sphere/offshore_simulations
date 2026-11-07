"""L3 ensemble: one plan, many weather years and seeds -> distributions, not single numbers.

Spec (build to this docstring; tests in tests/test_montecarlo.py):

    run_ensemble(problem, plan, world, engine, weather_years, seeds, variants=None) -> Ensemble

- weather_years: list[WeatherSeries] (e.g. NORA3 winters 2000-2023, one series per season).
- seeds: list[int]; the same seeds are reused for every variant (common random numbers), so a
  difference between variants is the policy, not the dice.
- variants: {name: Plan} to compare (baseline vs the paper's method vs our gap variant).
- Ensemble.runs: DataFrame one row per (variant, year, seed) with every KPI from SimResult.kpis.
- Ensemble.quantiles(kpi, q=(0.1, 0.5, 0.9)) -> DataFrame by variant.
- Ensemble.compare(kpi, a, b) -> paired differences per (year, seed) with mean and a bootstrap 95% CI.
- Ensemble.to_report() -> dict written under report["ensemble"]; the renderer and narrator read only this.
- Every SimResult in the ensemble passes offsim.contract.validate; a single failure fails the ensemble
  (it is reported with its (variant, year, seed) so it can be replayed).
"""
from offsim.montecarlo.ensemble import Ensemble, run_ensemble  # noqa: F401
