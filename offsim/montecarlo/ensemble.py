"""L3 ensemble: weather years x seeds x variants -> distributions, with paired (common-random-number) comparison.

Spec: offsim/montecarlo/__init__.py. Design notes
- One run = (variant, weather year, seed). Every variant sees the SAME years and the SAME seeds (common random
  numbers), so `compare` pairs on (year, seed) and the difference is the policy, not the dice.
- Every SimResult goes through `offsim.contract.validate(traj, agents, land=world.land)`. A violation, or an
  engine exception, is recorded in `Ensemble.failures` as {variant, year, seed, kind, detail} so the run can be
  replayed, and `Ensemble.ok` becomes False. Failed runs stay in `runs` with `valid=False` and are excluded
  from quantiles and comparisons. Nothing downstream may use an ensemble whose `ok` is False.
- `engines.base.Unsupported` is NOT a run failure: it propagates (the engine cannot represent the scenario).
- `variants` maps name -> Plan; when it is None the single `plan` runs as variant "base". When `variants` is
  given, `plan` is not run (pass the baseline inside `variants`). Variants that need different problems,
  worlds or engines are run with separate calls and joined with `Ensemble.merge`.
- `workers > 1` uses a ProcessPoolExecutor; problem/plan/world/engine/weather must then be picklable under the
  platform's start method. Output order is deterministic (variant, year, seed) for any worker count.
- Relative effects are taken against the mean of b (the baseline) of the pairs: (mean(a-b)) / mean(b).
"""
from __future__ import annotations

import math
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from offsim.contract import validate as validate_contract
from offsim.engines.base import Engine, Plan, Problem, Unsupported, WeatherSeries, World

META_COLS = ("variant", "year", "wx", "seed", "valid", "engine", "weather")
N_BOOT = 2000


# --------------------------------------------------------------------------------------------- helpers
def _clean(x: Any):
    """Make anything JSON-safe: numpy scalars -> python, NaN/inf -> None, unknown objects -> str."""
    if isinstance(x, dict):
        return {str(k): _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple, set)):
        return [_clean(v) for v in x]
    if x is None or isinstance(x, (str, bool, np.bool_)):
        return None if x is None else (x if isinstance(x, str) else bool(x))
    if isinstance(x, (int, np.integer)):
        return int(x)
    if isinstance(x, (float, np.floating)):
        return float(x) if math.isfinite(x) else None
    return str(x)


def _qname(q: float) -> str:
    return f"p{round(q * 100, 4):g}"


# --------------------------------------------------------------------------------------------- one run
_CTX: dict = {}


def _init(ctx: dict) -> None:
    _CTX.clear()
    _CTX.update(ctx)


def _execute(ctx: dict, task: tuple) -> dict:
    variant, wx, seed = task
    weather = ctx["weather"][wx]
    year = ctx["labels"][wx]
    row = {"variant": variant, "year": year, "wx": wx, "seed": seed, "valid": True,
           "engine": getattr(ctx["engine"], "name", type(ctx["engine"]).__name__),
           "weather": weather.source if weather is not None else None}
    fail = None
    try:
        res = ctx["engine"].simulate(ctx["problem"], ctx["plans"][variant], ctx["world"], weather, seed)
    except Unsupported as e:
        return {"unsupported": str(e)}
    except Exception as e:  # noqa: BLE001 - recorded with (variant, year, seed) so it can be replayed
        row["valid"] = False
        fail = {"variant": variant, "year": year, "seed": seed, "kind": "engine_error",
                "detail": f"{type(e).__name__}: {e}"[:300]}
        return {"row": row, "failure": fail}
    for k, v in (res.kpis or {}).items():
        if isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, bool):
            row[k] = float(v)
    if ctx["validate"]:
        rep = validate_contract(res.traj, res.agents, land=ctx["world"].land)
        if not rep.ok:
            row["valid"] = False
            fail = {"variant": variant, "year": year, "seed": seed, "kind": "contract",
                    "detail": [f"[{c}] {a}: {d}" for c, a, d in rep.violations[:10]],
                    "n_violations": len(rep.violations)}
    return {"row": row, "failure": fail}


def _worker(task: tuple) -> dict:
    return _execute(_CTX, task)


# --------------------------------------------------------------------------------------------- results
@dataclass
class Comparison:
    """Paired difference a - b over (year, seed) pairs. `ci` / `rel_ci` are bootstrap 95% intervals."""
    kpi: str
    a: str
    b: str
    n: int
    mean: float
    ci: tuple[float, float]
    rel_mean: float          # mean(a-b) / mean(b), relative to the baseline b
    rel_ci: tuple[float, float]
    diffs: pd.DataFrame      # columns: year, wx, seed, a, b, diff
    n_boot: int = N_BOOT
    seed: int = 0

    def to_dict(self, include_diffs: bool = False) -> dict:
        d = {"kpi": self.kpi, "a": self.a, "b": self.b, "n_pairs": self.n, "mean_diff": self.mean,
             "ci95": list(self.ci), "rel_mean": self.rel_mean, "rel_ci95": list(self.rel_ci),
             "n_boot": self.n_boot, "boot_seed": self.seed}
        if include_diffs:
            d["diffs"] = self.diffs.to_dict("records")
        return _clean(d)


@dataclass
class Ensemble:
    runs: pd.DataFrame
    failures: list = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    _comparisons: list = field(default_factory=list, repr=False)

    # -- status
    @property
    def valid_runs(self) -> pd.DataFrame:
        return self.runs[self.runs["valid"]] if len(self.runs) else self.runs

    @property
    def ok(self) -> bool:
        return not self.failures and len(self.valid_runs) > 0

    @property
    def kpi_names(self) -> list[str]:
        return [c for c in self.runs.columns if c not in META_COLS]

    @property
    def variants(self) -> list[str]:
        return list(dict.fromkeys(self.runs["variant"])) if len(self.runs) else []

    def _need(self, kpi: str):
        if kpi not in self.runs.columns or kpi in META_COLS:
            raise KeyError(f"unknown KPI {kpi!r}; have {self.kpi_names}")

    # -- statistics
    def quantiles(self, kpi: str, q=(0.1, 0.5, 0.9)) -> pd.DataFrame:
        """Rows = variants, columns p10/p50/p90 (per q) plus mean and n; valid runs only."""
        self._need(kpi)
        rows = {}
        for v in self.variants:
            x = self.valid_runs.loc[self.valid_runs["variant"] == v, kpi].dropna().to_numpy(float)
            r = {_qname(p): float(np.quantile(x, p)) if x.size else float("nan") for p in q}
            r["mean"] = float(x.mean()) if x.size else float("nan")
            r["n"] = int(x.size)
            rows[v] = r
        return pd.DataFrame.from_dict(rows, orient="index")

    def compare(self, kpi: str, a: str, b: str, n_boot: int = N_BOOT, seed: int = 0) -> Comparison:
        """Paired a - b over (year, seed) pairs present and valid in both variants, bootstrap 95% CI."""
        self._need(kpi)
        for v in (a, b):
            if v not in self.variants:
                raise KeyError(f"unknown variant {v!r}; have {self.variants}")
        vr = self.valid_runs
        cols = ["year", "wx", "seed", kpi]
        pa = vr.loc[vr["variant"] == a, cols].rename(columns={kpi: "a"})
        pb = vr.loc[vr["variant"] == b, cols].rename(columns={kpi: "b"})
        d = pa.merge(pb, on=["year", "wx", "seed"], how="inner").dropna(subset=["a", "b"])
        d = d.sort_values(["wx", "seed"]).reset_index(drop=True)
        if d.empty:
            raise ValueError(f"no valid (year, seed) pairs for {a!r} vs {b!r} on {kpi!r}")
        d["diff"] = d["a"] - d["b"]
        diff, base = d["diff"].to_numpy(float), d["b"].to_numpy(float)
        n = len(d)
        rng = np.random.default_rng(seed)
        idx = rng.integers(0, n, size=(n_boot, n))
        bm = diff[idx].mean(axis=1)
        den = base[idx].mean(axis=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            br = np.where(den != 0, bm / den, np.nan)
        ci = (float(np.percentile(bm, 2.5)), float(np.percentile(bm, 97.5)))
        rci = ((float(np.nanpercentile(br, 2.5)), float(np.nanpercentile(br, 97.5)))
               if np.isfinite(br).any() else (float("nan"), float("nan")))
        mb = float(base.mean())
        rel = float(diff.mean() / mb) if mb != 0 else float("nan")
        c = Comparison(kpi, a, b, n, float(diff.mean()), ci, rel, rci, d, n_boot, seed)
        self._comparisons = [x for x in self._comparisons if (x.kpi, x.a, x.b) != (kpi, a, b)] + [c]
        return c

    # -- output
    def to_report(self) -> dict:
        """JSON-safe dict for report["ensemble"]. Includes every comparison made so far on this object."""
        sources = list(dict.fromkeys(s for s in self.runs["weather"] if s)) if len(self.runs) else []
        q = {k: {v: row for v, row in self.quantiles(k).to_dict("index").items()} for k in self.kpi_names}
        return _clean({
            "ok": self.ok,
            "validated": self.meta.get("validated", True),
            "n_runs": int(len(self.runs)),
            "n_valid": int(len(self.valid_runs)),
            "variants": self.variants,
            "seeds": self.meta.get("seeds"),
            "years": self.meta.get("years"),
            "engines": sorted(set(self.runs["engine"])) if len(self.runs) else [],
            "weather_sources": sources,
            "synthetic_weather": any(str(s).startswith("SYNTHETIC") for s in sources),
            "kpis": self.kpi_names,
            "quantiles": q,
            "comparisons": [c.to_dict() for c in self._comparisons],
            "failures": self.failures,
        })

    @classmethod
    def merge(cls, *ens: "Ensemble") -> "Ensemble":
        """Join ensembles run separately (e.g. one per variant with its own problem/engine). Seeds and weather
        years must be identical, otherwise the pairing that makes the comparison meaningful is lost."""
        if not ens:
            raise ValueError("nothing to merge")
        for e in ens[1:]:
            if (e.meta.get("seeds"), e.meta.get("years")) != (ens[0].meta.get("seeds"), ens[0].meta.get("years")):
                raise ValueError("cannot merge ensembles with different seeds or weather years (breaks CRN)")
        names = [v for e in ens for v in e.variants]
        if len(names) != len(set(names)):
            raise ValueError(f"variant names overlap: {names}")
        runs = pd.concat([e.runs for e in ens], ignore_index=True)
        meta = dict(ens[0].meta)
        meta["validated"] = all(e.meta.get("validated", True) for e in ens)
        return cls(runs, [f for e in ens for f in e.failures], meta)


# --------------------------------------------------------------------------------------------- driver
def run_ensemble(problem: Problem, plan: Plan | None, world: World, engine: Engine,
                 weather_years: list[WeatherSeries], seeds: list[int],
                 variants: dict[str, Plan] | None = None, validate: bool = True,
                 workers: int = 1) -> Ensemble:
    """Run every (variant, weather year, seed) and collect an Ensemble. See module docstring.

    weather_years may be empty only for engines with needs_weather False; they then run once per seed with
    weather None and year label None. `validate=False` skips the contract check and is recorded in the
    report (validated: false); a report so marked must not feed a render.
    """
    seeds = [int(s) for s in seeds]
    if not seeds or len(set(seeds)) != len(seeds):
        raise ValueError("seeds must be a non-empty list of distinct ints")
    plans = dict(variants) if variants else {"base": plan}
    if not plans or any(p is None for p in plans.values()):
        raise ValueError("need a plan (or variants={name: Plan})")
    weather: list[WeatherSeries | None] = list(weather_years) or [None]
    if weather[0] is None and getattr(engine, "needs_weather", False):
        raise ValueError(f"engine {getattr(engine, 'name', engine)!r} needs weather; weather_years is empty")
    labels = [w.year if (w is not None and w.year is not None) else (None if w is None else i)
              for i, w in enumerate(weather)]
    ctx = {"problem": problem, "plans": plans, "world": world, "engine": engine,
           "weather": weather, "labels": labels, "validate": validate}
    tasks = [(v, wx, s) for v in plans for wx in range(len(weather)) for s in seeds]
    if workers and workers > 1:
        with ProcessPoolExecutor(max_workers=workers, initializer=_init, initargs=(ctx,)) as ex:
            outs = list(ex.map(_worker, tasks, chunksize=max(1, len(tasks) // (workers * 4))))
    else:
        outs = [_execute(ctx, t) for t in tasks]
    for o in outs:
        if "unsupported" in o:
            raise Unsupported(o["unsupported"])
    runs = pd.DataFrame([o["row"] for o in outs])
    for c in META_COLS:
        if c not in runs.columns:
            runs[c] = None
    lead = list(META_COLS)
    runs = runs[lead + [c for c in runs.columns if c not in lead]]
    failures = [o["failure"] for o in outs if o.get("failure")]
    meta = {"validated": bool(validate), "seeds": seeds, "years": labels,
            "engine": getattr(engine, "name", type(engine).__name__), "workers": int(workers or 1)}
    return Ensemble(runs, failures, meta)
