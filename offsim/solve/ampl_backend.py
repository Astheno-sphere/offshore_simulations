"""AMPL backend for exact LP/MIP certification of PyVRP plans.

Mirrors the Pyomo/HiGHS interface used by `opt-model`. Prefers Gurobi for MIP,
falls back to CPLEX, COPT, HiGHS. License activated via AMPL_LICENSE_UUID env
var or a previously stored user license (amplpy.modules activate).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from amplpy import AMPL, modules

_SOLVER_ORDER = ("gurobi", "cplex", "copt", "highs")


def _ensure_license() -> None:
    uuid = os.environ.get("AMPL_LICENSE_UUID")
    if not uuid:
        return
    # Idempotent; writes license file for ampl_module_base.
    try:
        modules.activate(uuid)
    except Exception:
        pass


def best_available_solver() -> str:
    installed = set(modules.installed())
    for s in _SOLVER_ORDER:
        if s in installed:
            return s
    raise RuntimeError("No AMPL solver module installed.")


@dataclass
class AmplResult:
    objective: float
    solver: str
    status: str
    solve_time_s: float
    variables: dict[str, float]


def solve_model(
    model_text: str | None = None,
    model_path: str | Path | None = None,
    data: Mapping[str, Any] | None = None,
    solver: str | None = None,
    objective: str | None = None,
    options: Mapping[str, str] | None = None,
) -> AmplResult:
    """Solve an AMPL model from text or .mod file. Returns objective + vars."""
    _ensure_license()
    ampl = AMPL()
    if model_path:
        ampl.read(str(model_path))
    elif model_text:
        ampl.eval(model_text)
    else:
        raise ValueError("model_text or model_path required")

    if data:
        for name, val in data.items():
            try:
                ampl.getParameter(name).set(val)
            except Exception:
                try:
                    ampl.getSet(name).setValues(val)
                except Exception:
                    pass

    chosen = solver or best_available_solver()
    ampl.setOption("solver", chosen)
    if options:
        for k, v in options.items():
            ampl.setOption(k, v)

    ampl.solve()
    obj_name = objective or next(iter(ampl.getObjectives()), (None, None))[0]
    obj_val = ampl.getObjective(obj_name).value() if obj_name else float("nan")
    status = ampl.getValue("solve_result")
    solve_time = float(ampl.getValue("_total_solve_time") or 0.0)

    vars_out: dict[str, float] = {}
    for name, v in ampl.getVariables():
        try:
            vars_out[name] = v.value()
        except Exception:
            pass

    return AmplResult(
        objective=float(obj_val),
        solver=chosen,
        status=str(status),
        solve_time_s=solve_time,
        variables=vars_out,
    )


def certify_against_highs(
    model_text: str,
    data: Mapping[str, Any] | None = None,
    tol: float = 1e-6,
) -> tuple[bool, AmplResult, AmplResult]:
    """Solve the same model with the best commercial solver and with HiGHS.
    Returns (match, commercial, highs)."""
    commercial = solve_model(model_text=model_text, data=data,
                             solver=best_available_solver())
    highs = solve_model(model_text=model_text, data=data, solver="highs")
    match = abs(commercial.objective - highs.objective) <= tol * max(
        1.0, abs(commercial.objective)
    )
    return match, commercial, highs
