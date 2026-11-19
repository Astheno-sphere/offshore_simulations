"""AMPL Studio core logic. No streamlit import here, so everything is testable.

AMPL runs on the laptop only (local install via amplpy; the Claude workspace cannot download it, and in CI the
`solve` workflow runs it on GitHub Actions). This module never reads or prints the licence file or any licence id.

Safety ideas reused from tools/ampl_mcp/server.py
- File access only under allowed roots (AMPL_STUDIO_ROOTS, os.pathsep-separated).
- AMPL text is screened before it runs: no shell escape (`!`, `shell`), no `cd`, `remove`, `include`, `commands`,
  `write`, `read`, `reset`, no `>` or `|` redirection. The screen is a guard, not a sandbox: load only models you trust.
- Solver names come from the probed list; solver options are plain name=value tokens.
"""
from __future__ import annotations

import os
import re
import shutil
import time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFAULT_ROOTS = (Path(r"E:\OffsimLab\models"), REPO / "offsim" / "solve" / "ampl", REPO / "offsim" / "papers")
DEFAULT_AMPL_DIR = Path(r"C:\Users\arshad\AMPL")
RUNS_DIR = Path(r"E:\OffsimLab\runs")
EXTENSIONS = {".mod", ".dat", ".run"}
MAX_FILE_BYTES = 5_000_000
MAX_LOG_CHARS = 2_000_000

SOLVER_GROUPS = {
    "LP/MIP": ["highs", "gurobi", "cplex", "copt", "cbc", "xpress", "mosek", "scip", "gcg"],
    "NLP/MINLP": ["knitro", "baron", "conopt", "ipopt", "bonmin", "couenne", "octeract", "lindoglobal", "snopt",
                  "minos", "lgo", "loqo"],
    "CP": ["gecode"],
}

# --- screening --------------------------------------------------------------------------------------------------
_DENY_WORDS = re.compile(r"\b(shell|cd|remove|include|commands|write|writetable|wtable|read|readtable)\b",
                         re.IGNORECASE)
_DENY_LEADING = {"shell", "cd", "remove", "include", "commands", "write", "writetable", "wtable", "read",
                 "readtable", "table", "reset", "close", "quit", "solution"}
_NOT_SHELL = re.compile(r"!(?!=)")           # `!` starts a shell escape; `!=` is AMPL not-equal
_REDIRECT = re.compile(r">\s*[\"']|\|")      # redirection to a quoted file name, or a pipe
_FILE_REF = re.compile(r"^\s*(?:model|data)\s+([^;\s]+)\s*;", re.IGNORECASE | re.MULTILINE)
_OPT_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_:]{0,40}(=[A-Za-z0-9_.+\-:/]{1,60})?")
_NAME = re.compile(r"[A-Za-z0-9_.\-]+")


def strip_comments(text: str) -> str:
    return "\n".join(line.split("#", 1)[0] for line in text.splitlines())


def screen(text: str, *, script: bool = False) -> None:
    """Raise ValueError if the AMPL text could run a command or write files. script=True (a .run file) also
    allows `model`/`data` statements; their file names are checked by check_script_files."""
    body = strip_comments(text)
    m = _DENY_WORDS.search(body)
    if m:
        raise ValueError(f"AMPL text uses {m.group(0)!r}, which AMPL Studio does not run")
    if _NOT_SHELL.search(body):
        raise ValueError("AMPL text contains '!' (shell escape); AMPL Studio does not run shell commands")
    if _REDIRECT.search(body):
        raise ValueError("AMPL text redirects output to a file or pipe; not allowed in AMPL Studio")
    for stmt in body.split(";"):
        words = stmt.strip().split()
        if words and words[0].lower() in _DENY_LEADING:
            raise ValueError(f"statement {words[0]!r} is not allowed in AMPL Studio")
    if not script and re.search(r"^\s*model\b", body, re.IGNORECASE | re.MULTILINE):
        raise ValueError("a `model` statement is only allowed in .run files; pick the file instead")


# --- roots ------------------------------------------------------------------------------------------------------
def allowed_roots() -> list[Path]:
    raw = os.environ.get("AMPL_STUDIO_ROOTS")
    items = [Path(p) for p in raw.split(os.pathsep) if p.strip()] if raw else list(DEFAULT_ROOTS)
    return [p.expanduser().resolve() for p in items]


def inside_roots(path: str | Path, roots: list[Path] | None = None, must_exist: bool = True) -> Path:
    roots = roots if roots is not None else allowed_roots()
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = roots[0] / p
    p = p.resolve()
    if not any(p == r or p.is_relative_to(r) for r in roots):
        raise PermissionError(f"{p} is outside the allowed roots")
    if must_exist and not p.exists():
        raise FileNotFoundError(str(p))
    return p


def list_models(roots: list[Path] | None = None, limit: int = 1000) -> list[Path]:
    """AMPL files (.mod, .dat, .run) under the allowed roots that exist."""
    roots = roots if roots is not None else allowed_roots()
    out: list[Path] = []
    for r in roots:
        if not r.is_dir():
            continue
        for p in sorted(r.rglob("*")):
            if p.suffix.lower() in EXTENSIONS and p.is_file():
                try:
                    out.append(inside_roots(p, roots))
                except PermissionError:
                    continue
            if len(out) >= limit:
                return out
    return out


def read_checked(path: str | Path, roots: list[Path] | None = None) -> str:
    """Read an AMPL file from the allowed roots and screen it. Raises on any violation."""
    p = inside_roots(path, roots)
    if p.suffix.lower() not in EXTENSIONS:
        raise ValueError(f"{p.name}: expected one of {sorted(EXTENSIONS)}")
    if p.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f"{p.name} is larger than {MAX_FILE_BYTES} bytes")
    text = p.read_text(encoding="utf-8")
    screen(text, script=p.suffix.lower() == ".run")
    return text


def check_script_files(text: str, base: Path, roots: list[Path] | None = None) -> None:
    """Every `model f;` / `data f;` in a script must resolve inside the allowed roots."""
    for m in _FILE_REF.finditer(strip_comments(text)):
        name = m.group(1).strip("\"'")
        inside_roots(base / name, roots)


# --- solvers ----------------------------------------------------------------------------------------------------
def find_ampl_dir() -> Path | None:
    env = os.environ.get("AMPL_DIR")
    if env and Path(env).is_dir():
        return Path(env)
    w = shutil.which("ampl")
    if w:
        return Path(w).resolve().parent
    if DEFAULT_AMPL_DIR.is_dir() and (DEFAULT_AMPL_DIR / "ampl.exe").exists():
        return DEFAULT_AMPL_DIR
    return None


def probe_solvers(ampl_dir: Path | str | None) -> dict[str, list[str]]:
    """{group: [solver, ...]} for solver executables sitting next to the AMPL binary. Empty groups are dropped."""
    if ampl_dir is None:
        return {}
    d = Path(ampl_dir)
    out: dict[str, list[str]] = {}
    for group, names in SOLVER_GROUPS.items():
        found = [n for n in names if (d / f"{n}.exe").is_file() or (d / n).is_file()]
        if found:
            out[group] = found
    return out


def all_solvers(groups: dict[str, list[str]]) -> list[str]:
    return [s for names in groups.values() for s in names]


def build_options(solver: str, options: str) -> tuple[str, str]:
    """Return (ampl option name, value), e.g. ('highs_options', 'outlev=1 timelim=60'). Plain tokens only."""
    if not re.fullmatch(r"[a-z][a-z0-9]{1,20}", solver or ""):
        raise ValueError(f"{solver!r} is not a solver name")
    tokens = (options or "").split()
    for t in tokens:
        if not _OPT_TOKEN.fullmatch(t):
            raise ValueError(f"solver option {t!r} is not a plain name or name=value token")
    return f"{solver}_options", " ".join(tokens)


# --- solving ----------------------------------------------------------------------------------------------------
def log_dir() -> Path:
    d = RUNS_DIR if RUNS_DIR.is_dir() else Path("runs")
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_log(model_name: str, solver: str, text: str, directory: Path | None = None) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = "".join(c if _NAME.fullmatch(c) else "_" for c in (Path(model_name).stem or "model"))[:60]
    path = (directory or log_dir()) / f"{stamp}_{safe}_{solver}.log"
    n = 1
    while path.exists():
        path = path.with_name(f"{stamp}_{safe}_{solver}_{n}.log")
        n += 1
    path.write_text(text[:MAX_LOG_CHARS], encoding="utf-8")
    return path


def _flatten_var(name: str, var):
    import pandas as pd
    df = var.get_values().to_pandas()
    if df.empty:
        return pd.DataFrame(columns=["variable", "index", "value"])
    col = df.columns[0]
    if var.indexarity() == 0:
        return pd.DataFrame([{"variable": name, "index": "", "value": float(df[col].iloc[0])}])
    rows = []
    for idx, val in df[col].items():
        label = ",".join(str(i) for i in idx) if isinstance(idx, tuple) else str(idx)
        rows.append({"variable": name, "index": label, "value": float(val)})
    return pd.DataFrame(rows)


def variables_table(ampl):
    import pandas as pd
    frames = [_flatten_var(n, v) for n, v in ampl.get_variables()]
    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame(columns=["variable", "index", "value"])
    return pd.concat(frames, ignore_index=True)


def objectives_list(ampl) -> list[dict]:
    out = []
    for name, obj in ampl.get_objectives():
        try:
            if obj.indexarity() == 0:
                out.append({"objective": name, "value": float(obj.value())})
            else:
                for idx, val in obj.get_values().to_pandas().iloc[:, 0].items():
                    label = ",".join(str(i) for i in idx) if isinstance(idx, tuple) else str(idx)
                    out.append({"objective": f"{name}[{label}]", "value": float(val)})
        except Exception:
            continue
    return out


def solve(*, solver: str, options: str = "", model_text: str = "", data_text: str = "", path: str | Path | None = None,
          data_path: str | Path | None = None,
          name: str = "pasted", ampl_dir: Path | str | None = None, roots: list[Path] | None = None,
          write_logs: bool = True) -> dict:
    """Solve with a fresh amplpy session. Source is a file under the allowed roots (path) or pasted text.

    A .mod file, or pasted text, is loaded then solved; a .dat file needs a model alongside, so pass model_text and
    data_text. A .run script is run as written (it must solve itself). Returns a dict with status, objectives,
    variables (DataFrame), time, output and log path. Errors are returned in `error`, not raised, for UI use.
    """
    res = {"solver": solver, "model": name, "status": "", "solve_result_num": None, "objectives": [],
           "variables": None, "seconds": None, "output": "", "log": None, "error": None}
    chunks: list[str] = []
    try:
        solver = solver.strip().lower()
        opt_name, opt_val = build_options(solver, options)
        script = False
        if path is not None:
            p = inside_roots(path, roots)
            text = read_checked(p, roots)
            name = p.name
            res["model"] = name
            script = p.suffix.lower() == ".run"
            if script:
                check_script_files(text, p.parent, roots)
            elif p.suffix.lower() == ".dat":
                data_text, model_text = text, model_text
            else:
                model_text = text
        else:
            screen(model_text)
        if data_path is not None:
            data_text = read_checked(data_path, roots)
        if data_text:
            screen(data_text)
        if not script and not model_text.strip():
            raise ValueError("no model text: pick a .mod file or paste a model")
        try:
            from amplpy import AMPL, Environment, OutputHandler
        except ImportError as e:
            raise RuntimeError("amplpy is not installed: python -m pip install amplpy") from e
        if ampl_dir is None:
            ampl_dir = find_ampl_dir()
        if ampl_dir is None:
            raise RuntimeError("AMPL binary not found. Set AMPL_DIR or put ampl on PATH (AMPL runs on the laptop).")

        class Collector(OutputHandler):
            def output(self, kind, msg):
                chunks.append(str(msg))

        try:
            ampl = AMPL(Environment(str(ampl_dir)))
        except Exception as e:
            raise RuntimeError("AMPL could not start; check the install and licence in the AMPL folder.") from e
        ampl.set_output_handler(Collector())
        try:
            if script:
                ampl.cd(str(Path(path).resolve().parent))
            ampl.set_option("solver", solver)
            if opt_val:
                ampl.set_option(opt_name, opt_val)
            t0 = time.perf_counter()
            if script:
                ampl.eval(text)
            else:
                ampl.eval(model_text)
                if data_text:
                    ampl.eval("data;\n" + data_text if not data_text.lstrip().lower().startswith("data") else data_text)
                t0 = time.perf_counter()
                ampl.solve()
            res["seconds"] = time.perf_counter() - t0
            res["status"] = str(ampl.get_value("solve_result"))
            res["solve_result_num"] = int(ampl.get_value("solve_result_num"))
            res["objectives"] = objectives_list(ampl)
            res["variables"] = variables_table(ampl)
        finally:
            ampl.close()
    except Exception as e:  # shown in the UI and written to the log
        res["error"] = f"{type(e).__name__}: {e}"
    res["output"] = "".join(chunks)
    if write_logs:
        head = f"model: {res['model']}\nsolver: {solver}\noptions: {options}\nstatus: {res['status']}\n"
        head += f"objectives: {res['objectives']}\nseconds: {res['seconds']}\nerror: {res['error']}\n---\n"
        try:
            res["log"] = str(write_log(res["model"], solver, head + res["output"]))
        except OSError as e:
            res["error"] = (res["error"] or "") + f" (log not written: {e})"
    return res


def compare(solvers: list[str], **kwargs) -> list[dict]:
    """Solve the same model with each solver; returns full results (see compare_table for the summary)."""
    return [solve(solver=s, **kwargs) for s in solvers]


def compare_table(results: list[dict]):
    import pandas as pd
    rows = []
    for r in results:
        obj = r["objectives"][0]["value"] if r["objectives"] else None
        rows.append({"solver": r["solver"], "status": r["status"] or (r["error"] or ""), "objective": obj,
                     "seconds": None if r["seconds"] is None else round(r["seconds"], 4)})
    return pd.DataFrame(rows, columns=["solver", "status", "objective", "seconds"])


def variables_csv(df) -> str:
    return df.to_csv(index=False)
