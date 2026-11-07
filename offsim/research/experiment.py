"""Experiment spec: a gap turned into variants the ensemble can compare.

experiment.yaml (next to the paper's scenario.yaml):

    gap_id: psv-ncs-weather-01
    base: scenario.yaml                       # the reproduced paper (must have status reproduced / re-run)
    hypothesis: "Robust schedule cuts P90 delay by >= 20% vs deterministic on NCS winters"
    variants:
      paper:    {solver: pyomo, engine: openclsim}
      robust:   {solver: ampl, engine: openclsim, overrides: {sim.slack_h: {value: 6, assumption: true}}}
    ensemble: {weather: {dataset: NORA3, years: [2000, 2023], season: DJF}, seeds: 20}
    kpis: [delay_p90_h, fuel_t, co2_t, service_level]
    decision: {kpi: delay_p90_h, compare: [robust, paper], better: lower, min_effect: 0.20}

Status: supported (effect >= min_effect and CI excludes 0) | not supported (CI excludes the effect) |
inconclusive. Nothing is narrated before the experiment's ensemble passes every contract check.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

REQUIRED = ("gap_id", "base", "hypothesis", "variants", "ensemble", "kpis", "decision")


@dataclass
class Experiment:
    gap_id: str
    base: Path
    hypothesis: str
    variants: dict
    ensemble: dict
    kpis: list
    decision: dict
    extra: dict = field(default_factory=dict)


def load(path) -> Experiment:
    path = Path(path)
    d = yaml.safe_load(path.read_text())
    missing = [k for k in REQUIRED if k not in d]
    if missing:
        raise ValueError(f"{path}: missing {missing}")
    dec = d["decision"]
    if dec.get("kpi") not in d["kpis"]:
        raise ValueError(f"{path}: decision.kpi {dec.get('kpi')!r} not in kpis")
    for name in dec.get("compare", []):
        if name not in d["variants"]:
            raise ValueError(f"{path}: decision compares unknown variant {name!r}")
    for name, var in d["variants"].items():
        if "engine" not in var or "solver" not in var:
            raise ValueError(f"{path}: variant {name!r} needs solver and engine")
    return Experiment(d["gap_id"], path.parent / d["base"], d["hypothesis"], d["variants"], d["ensemble"],
                      d["kpis"], dec, {k: x for k, x in d.items() if k not in REQUIRED})


def decide(effect_mean: float, ci: tuple[float, float], min_effect: float) -> str:
    """Status word from a paired relative effect (positive = the variant is better) and its 95% CI."""
    lo, hi = ci
    if lo > 0 and effect_mean >= min_effect:
        return "supported"
    if hi < min_effect:
        return "not supported"
    return "inconclusive"
