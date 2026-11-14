"""AMPL MCP server. Exposes AMPL to Claude Code and any MCP client.

Tools:
  - check_license   : license status, expiry, solvers reachable
  - list_solvers    : installed solver modules
  - solve_text      : solve an inline AMPL model string
  - solve_file      : solve a .mod/.run file from the repo
  - compare_highs   : solve with best commercial solver and HiGHS, return both
  - run_script      : execute an AMPL script (option, display, solve) and return output

Run:  python tools/ampl_mcp/server.py     (stdio transport, per MCP spec)
License activation: set AMPL_LICENSE_UUID in env, or run
    python -m amplpy.modules activate <uuid>  once per user profile.
"""
from __future__ import annotations

import io
import os
import sys
from pathlib import Path
from typing import Any

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    sys.stderr.write(
        "mcp[cli] not installed. Run: pip install 'mcp[cli]' amplpy\n"
    )
    raise

from amplpy import AMPL, modules

mcp = FastMCP("ampl")

_SOLVER_ORDER = ("gurobi", "cplex", "copt", "highs")


def _activate_if_needed() -> None:
    uuid = os.environ.get("AMPL_LICENSE_UUID")
    if uuid:
        try:
            modules.activate(uuid)
        except Exception as e:
            sys.stderr.write(f"[ampl_mcp] activate warning: {e}\n")


def _best() -> str:
    for s in _SOLVER_ORDER:
        if s in modules.installed():
            return s
    raise RuntimeError("No AMPL solver module installed")


@mcp.tool()
def check_license() -> dict[str, Any]:
    """Return AMPL version string and license line (expiry, user)."""
    _activate_if_needed()
    a = AMPL()
    out = a.getOutput("option version;")
    return {"version_option": out.strip(), "installed_solvers": modules.installed()}


@mcp.tool()
def list_solvers() -> list[str]:
    """Installed AMPL solver modules, preferred order first."""
    inst = set(modules.installed())
    return [s for s in _SOLVER_ORDER if s in inst] + sorted(inst - set(_SOLVER_ORDER))


@mcp.tool()
def solve_text(model: str, solver: str = "", options: dict[str, str] | None = None) -> dict[str, Any]:
    """Solve an inline AMPL model. Returns objective, status, variable values."""
    _activate_if_needed()
    a = AMPL()
    a.eval(model)
    a.setOption("solver", solver or _best())
    for k, v in (options or {}).items():
        a.setOption(k, str(v))
    a.solve()
    objs = {name: obj.value() for name, obj in a.getObjectives()}
    vars_ = {name: v.value() for name, v in a.getVariables()}
    return {
        "solver": a.getOption("solver"),
        "status": str(a.getValue("solve_result")),
        "objectives": objs,
        "variables": vars_,
    }


@mcp.tool()
def solve_file(path: str, data_path: str = "", solver: str = "") -> dict[str, Any]:
    """Read an AMPL .mod (and optional .dat) and solve."""
    _activate_if_needed()
    a = AMPL()
    a.read(str(Path(path)))
    if data_path:
        a.readData(str(Path(data_path)))
    a.setOption("solver", solver or _best())
    a.solve()
    return {
        "solver": a.getOption("solver"),
        "status": str(a.getValue("solve_result")),
        "objectives": {n: o.value() for n, o in a.getObjectives()},
    }


@mcp.tool()
def compare_highs(model: str, tol: float = 1e-6) -> dict[str, Any]:
    """Solve same model with best commercial solver and HiGHS, report delta."""
    _activate_if_needed()
    results = {}
    for s in (_best(), "highs"):
        a = AMPL()
        a.eval(model)
        a.setOption("solver", s)
        a.solve()
        objs = {n: o.value() for n, o in a.getObjectives()}
        results[s] = {"status": str(a.getValue("solve_result")), "objectives": objs}
    first_obj = next(iter(results[_best()]["objectives"].values()))
    highs_obj = next(iter(results["highs"]["objectives"].values()))
    delta = abs(first_obj - highs_obj)
    match = delta <= tol * max(1.0, abs(first_obj))
    return {"match": match, "delta": delta, "results": results}


@mcp.tool()
def run_script(script: str) -> dict[str, str]:
    """Run arbitrary AMPL script text (option, display, solve, let, ...)."""
    _activate_if_needed()
    a = AMPL()
    buf_out = io.StringIO()
    buf_err = io.StringIO()
    a.setOutputHandler(lambda k, msg: buf_out.write(msg))
    a.setErrorHandler(lambda ex: buf_err.write(str(ex) + "\n"))
    try:
        a.eval(script)
    except Exception as e:
        buf_err.write(f"eval error: {e}\n")
    return {"stdout": buf_out.getvalue(), "stderr": buf_err.getvalue()}


if __name__ == "__main__":
    _activate_if_needed()
    mcp.run()
