"""MCP server that lets Claude drive AMPL on your laptop (stdio). See README.md next to this file.

Tools: solve_model, get_variable, get_duals, run_ampl, list_models.

Rules this file enforces
- stdout is the MCP channel: nothing here prints to stdout. AMPL output goes to a buffer and to stderr.
- File access only under the folders in AMPL_MCP_ROOTS (os.pathsep-separated; default ~/ampl-models).
- AMPL text is screened before it runs: no shell escape (`!`, `shell`), no `cd`, `remove`, `include`,
  `commands`, `write`, `read`, `data`, `model`, `reset`, and no `>` or `|` redirection. Model files get the same
  screen, with comments ignored. The screen is a guard, not a sandbox: only load models you wrote or trust.
- Solver names come from an allowlist; solver options are validated as name=value pairs.
- No network calls. The academic AMPL licence renews over the internet, through AMPL's own tooling only.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

try:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server
except ImportError:  # mcp 2.x renamed FastMCP to MCPServer
    from mcp.server.mcpserver import MCPServer as _Server

mcp = _Server("ampl")

SOLVERS = ("highs", "cbc")
MAX_SECONDS = 1800.0
MAX_FILE_BYTES = 5_000_000
MAX_OUTPUT_CHARS = 20_000
EXTENSIONS = {".mod", ".dat", ".run"}

_DENY_WORDS = re.compile(r"\b(shell|cd|remove|include|commands|write|writetable|wtable)\b", re.IGNORECASE)
_DENY_LEADING = {"shell", "cd", "remove", "include", "commands", "write", "writetable", "wtable", "read",
                 "readtable", "table", "data", "model", "reset", "close", "quit", "solution"}
_NOT_SHELL = re.compile(r"!(?!=)")           # `!` starts a shell escape; `!=` is AMPL not-equal
_REDIRECT_ANY = re.compile(r">(?!=)|\|")     # run_ampl: no redirection at all
_REDIRECT_FILE = re.compile(r">\s*[\"']|\|")  # model files: only redirection to a quoted file name is refused
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")
_OPT_KEY = re.compile(r"[a-z_][a-z0-9_]{0,40}")
_OPT_VAL = re.compile(r"[A-Za-z0-9_.+\-]{1,40}")


def _strip_comments(text: str) -> str:
    return "\n".join(line.split("#", 1)[0] for line in text.splitlines())


def screen(text: str, *, model_file: bool = False) -> None:
    """Raise ValueError if the AMPL text could run a command, read or write files outside the model."""
    body = _strip_comments(text)
    m = _DENY_WORDS.search(body)
    if m:
        raise ValueError(f"AMPL text uses {m.group(0)!r}, which this server does not run")
    if _NOT_SHELL.search(body):
        raise ValueError("AMPL text contains '!' (shell escape); this server does not run shell commands")
    if (_REDIRECT_FILE if model_file else _REDIRECT_ANY).search(body):
        raise ValueError("AMPL text redirects output to a file or pipe; not allowed through this server")
    for stmt in body.split(";"):
        words = stmt.strip().split()
        if words and words[0].lower() in _DENY_LEADING:
            raise ValueError(f"statement {words[0]!r} is not allowed through this server")


def _roots() -> list[Path]:
    raw = os.environ.get("AMPL_MCP_ROOTS") or str(Path.home() / "ampl-models")
    return [Path(p).expanduser().resolve() for p in raw.split(os.pathsep) if p.strip()]


def _inside_roots(path: str, must_exist: bool = True) -> Path:
    roots = _roots()
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = roots[0] / p
    p = p.resolve()
    if not any(p.is_relative_to(r) for r in roots):
        raise PermissionError(f"{p} is outside AMPL_MCP_ROOTS")
    if must_exist and not p.exists():
        raise FileNotFoundError(str(p))
    return p


def _screen_file(path: Path) -> None:
    if path.suffix not in EXTENSIONS:
        raise ValueError(f"{path.name}: expected one of {sorted(EXTENSIONS)}")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f"{path.name} is larger than {MAX_FILE_BYTES} bytes")
    screen(path.read_text(encoding="utf-8", errors="strict"), model_file=True)


def _solver_options(solver: str, options: dict | None, seconds: float) -> str:
    seconds = min(max(float(seconds), 1.0), MAX_SECONDS)
    parts = {"time_limit": seconds} if solver == "highs" else {"seconds": seconds}
    for k, v in (options or {}).items():
        if not _OPT_KEY.fullmatch(str(k)) or not _OPT_VAL.fullmatch(str(v)):
            raise ValueError(f"solver option {k}={v!r} is not a plain name=value pair")
        parts[str(k)] = v
    return " ".join(f"{k}={v}" for k, v in parts.items())


def _checked_name(name: str) -> str:
    if not _NAME.fullmatch(name):
        raise ValueError(f"{name!r} is not an AMPL identifier")
    return name


# --- AMPL session (created on first use; never at import) ----------------------------------------------------
_SESSION: dict = {"ampl": None, "out": None}


def _session():
    if _SESSION["ampl"] is None:
        try:
            from amplpy import AMPL, OutputHandler
        except ImportError as e:
            raise RuntimeError("amplpy is not installed: pip install amplpy") from e

        class Collector(OutputHandler):
            def __init__(self):
                self.lines: list[str] = []

            def output(self, kind, msg):
                self.lines.append(str(msg))
                print(msg, end="", file=sys.stderr)  # stderr only: stdout carries the MCP protocol

        try:
            ampl = AMPL()
        except Exception as e:  # amplpy raises RuntimeError when the AMPL binary cannot start
            raise RuntimeError("AMPL could not start. Install the AMPL binary, the solver modules and the "
                               "academic licence as in tools/ampl_mcp/README.md.") from e
        _SESSION["out"] = Collector()
        ampl.set_output_handler(_SESSION["out"])
        _SESSION["ampl"] = ampl
    return _SESSION["ampl"]


def _to_records(obj, limit: int) -> tuple[int, list]:
    df = obj.to_pandas() if hasattr(obj, "to_pandas") else obj
    return len(df), json.loads(df.head(limit).to_json(orient="records"))


# --- tools -----------------------------------------------------------------------------------------------------
@mcp.tool()
def solve_model(model_path: str, data_path: str | None = None, solver: str = "highs",
                options: dict[str, str] | None = None, seconds: float = 60.0) -> dict:
    """Load an AMPL model (and optional data file) from AMPL_MCP_ROOTS, solve it, return status, objective and time.

    solver: highs or cbc. options: extra solver options as name=value (e.g. {"random_seed": "1"}) for the
    solver's own options string. seconds: time limit, clamped to 1..1800.
    """
    if solver not in SOLVERS:
        raise ValueError(f"solver must be one of {SOLVERS}")
    model = _inside_roots(model_path)
    _screen_file(model)
    data = None
    if data_path:
        data = _inside_roots(data_path)
        _screen_file(data)
    ampl = _session()
    ampl.reset()
    ampl.read(str(model))
    if data is not None:
        ampl.read_data(str(data))
    ampl.set_option("solver", solver)
    ampl.set_option(f"{solver}_options", _solver_options(solver, options, seconds))
    t0 = time.perf_counter()
    ampl.solve(verbose=False)
    wall = time.perf_counter() - t0
    obj = ampl.get_current_objective()
    return {"model": model.name, "solver": solver, "status": ampl.solve_result,
            "objective": float(obj.value()) if obj is not None else None,
            "solve_seconds": round(wall, 3)}


@mcp.tool()
def get_variable(name: str, limit: int = 1000) -> dict:
    """Values of a variable after the last solve: its total row count and the first `limit` rows."""
    ampl = _session()
    total, rows = _to_records(ampl.get_variable(_checked_name(name)).get_values(), min(max(limit, 1), 10000))
    return {"name": name, "rows": total, "values": rows}


@mcp.tool()
def get_duals(constraint: str, limit: int = 1000) -> dict:
    """Dual values of a constraint after the last solve (first `limit` rows)."""
    ampl = _session()
    total, rows = _to_records(ampl.get_constraint(_checked_name(constraint)).get_values("dual"),
                              min(max(limit, 1), 10000))
    return {"name": constraint, "rows": total, "duals": rows}


@mcp.tool()
def run_ampl(statements: str) -> dict:
    """Run AMPL statements in the current session (solve, display, option, let, subject to, ...).

    Refused: shell escapes (!, shell), cd, remove, include, commands, write, read, data, model, reset, close,
    quit, solution, any redirection with > or |. Output is returned (truncated) and also written to stderr.
    """
    screen(statements)
    ampl = _session()
    _SESSION["out"].lines.clear()
    ampl.eval(statements)
    text = "".join(_SESSION["out"].lines)
    return {"ok": True, "output": text[:MAX_OUTPUT_CHARS], "truncated": len(text) > MAX_OUTPUT_CHARS,
            "solve_result": ampl.solve_result}


@mcp.tool()
def list_models(directory: str | None = None) -> list[dict]:
    """AMPL files (.mod, .dat, .run) under a folder inside AMPL_MCP_ROOTS (default: the first root)."""
    base = _inside_roots(directory or str(_roots()[0]))
    if not base.is_dir():
        raise NotADirectoryError(str(base))
    out = []
    for p in sorted(base.rglob("*")):
        if p.suffix in EXTENSIONS and p.is_file():
            try:
                p = _inside_roots(str(p))
            except PermissionError:
                continue
            out.append({"path": str(p), "bytes": p.stat().st_size})
        if len(out) >= 500:
            break
    return out


if __name__ == "__main__":
    mcp.run(transport="stdio")
