"""Run an experiment.yaml: variants -> ensemble -> pre-registered decision.

    run(experiment_path, engine_name=None, *, build=None, load_weather=None, workers=1, out=None) -> dict

- `build(experiment, variant_name) -> (problem, plan, world, engine)` turns one variant of the experiment into
  runnable objects. It is injected so this module stays testable and below the pipeline layer; `offsim.pipeline`
  will supply the real builder (`build_variant`). Until it exists, `build=None` raises NotImplementedError.
- `load_weather(experiment) -> list[WeatherSeries]` defaults to `offsim.weather.years.load_years` using
  `ensemble.weather.{path, point}` plus `years: [first, last]` (inclusive) and `season` from experiment.yaml.
- `engine_name` overrides every variant's `engine` before `build` sees it (e.g. cross-check on another engine).
- Each variant is run with its own problem/world/engine, over the SAME weather years and seeds (common random
  numbers), then joined with Ensemble.merge. `ensemble.seeds` is an int N (seeds 0..N-1) or an explicit list.
- Decision: relative paired effect of decision.compare[0] vs decision.compare[1] on decision.kpi, signed so
  that positive = better (`better: lower|higher`), fed to experiment.decide(effect, ci, min_effect) ->
  supported | not supported | inconclusive. If the ensemble has any contract failure the status is None and
  `blocked` says why; nothing may be narrated. Synthetic weather sets reportable False.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Callable

from offsim.montecarlo.ensemble import Ensemble, run_ensemble
from offsim.research import experiment as exp_mod


def seeds_from(spec) -> list[int]:
    if isinstance(spec, int):
        return list(range(spec))
    return [int(s) for s in spec]


def default_load_weather(experiment: exp_mod.Experiment):
    from offsim.weather.years import load_years

    w = experiment.ensemble.get("weather", {})
    if "path" not in w or "point" not in w:
        raise ValueError("ensemble.weather needs path and point (lon, lat) for the default loader; "
                         "or pass load_weather= to run()")
    y = w["years"]
    years = list(range(y[0], y[1] + 1)) if len(y) == 2 else list(y)
    return load_years(w["path"], tuple(w["point"]), years, w.get("season"), dataset=w.get("dataset", "NORA3"))


def oriented_effect(rel_mean: float, rel_ci: tuple[float, float], better: str) -> tuple[float, tuple[float, float]]:
    """Relative effect of a vs the baseline, signed so positive = better."""
    if better not in ("lower", "higher"):
        raise ValueError(f"decision.better must be lower|higher, got {better!r}")
    if better == "higher":
        return rel_mean, (rel_ci[0], rel_ci[1])
    return -rel_mean, (-rel_ci[1], -rel_ci[0])


def decide_from(ens: Ensemble, decision: dict, n_boot: int = 2000, seed: int = 0) -> dict:
    a, b = decision["compare"][:2]
    c = ens.compare(decision["kpi"], a, b, n_boot=n_boot, seed=seed)
    effect, ci = oriented_effect(c.rel_mean, c.rel_ci, decision.get("better", "lower"))
    status = exp_mod.decide(effect, ci, float(decision["min_effect"]))
    return {"kpi": decision["kpi"], "compare": [a, b], "better": decision.get("better", "lower"),
            "min_effect": float(decision["min_effect"]), "effect": effect, "ci95": list(ci),
            "n_pairs": c.n, "status": status}


def run(experiment_path, engine_name: str | None = None, *, build: Callable | None = None,
        load_weather: Callable | None = None, workers: int = 1, out=None) -> dict:
    ex = exp_mod.load(experiment_path)
    if engine_name:
        ex = dataclasses.replace(ex, variants={k: {**v, "engine": engine_name} for k, v in ex.variants.items()})
    if build is None:
        try:
            from offsim.pipeline import build_variant as build  # type: ignore[attr-defined]
        except ImportError as e:
            raise NotImplementedError("no builder: pass build=(experiment, variant)->(problem, plan, world, engine); "
                                      "offsim.pipeline.build_variant will supply it") from e
    weather = (load_weather or default_load_weather)(ex)
    seeds = seeds_from(ex.ensemble["seeds"])
    parts = []
    for name in ex.variants:
        problem, plan, world, engine = build(ex, name)
        parts.append(run_ensemble(problem, None, world, engine, weather, seeds, variants={name: plan},
                                  workers=workers))
    ens = Ensemble.merge(*parts)
    result = {"gap_id": ex.gap_id, "hypothesis": ex.hypothesis, "decision": None, "blocked": None}
    if ens.ok:
        result["decision"] = decide_from(ens, ex.decision)
        for k in ex.kpis:                      # the pre-registered KPI list, compared like the decision pair
            if k != ex.decision["kpi"] and k in ens.kpi_names:
                ens.compare(k, *ex.decision["compare"][:2])
    else:
        result["blocked"] = f"ensemble failed: {len(ens.failures)} failure(s); see ensemble.failures"
    result["ensemble"] = ens.to_report()
    result["reportable"] = bool(ens.ok and not result["ensemble"]["synthetic_weather"]
                                and result["ensemble"]["validated"])
    if out:
        Path(out).write_text(json.dumps(result, indent=2))
    return result
