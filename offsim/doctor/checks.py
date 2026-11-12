"""Playbook checks: read-only functions `check(ctx) -> {"ok": bool | None, "evidence": {...}}`.

ok=True   the check found nothing wrong on its axis; ok=False it found (part of) the cause, evidence says what;
ok=None   the check could not run (missing input); never read as a pass.
Checks never write, never touch the network and never edit a scenario. `ctx` (built by offsim.doctor.build_ctx):
  report, gate, entry, detail, code, root, data_root, world, world_dir, scenario_path, scenario (dict | None), report_dir
Every function named in a playbook's `checks:` must exist here (tests/test_doctor.py).
"""
from __future__ import annotations

import ast
import ctypes.util
import importlib.util
import json
import re
import subprocess
from pathlib import Path

from offsim.doctor.codes import contract_kinds


def _r(ok, **evidence):
    return {"ok": ok, "evidence": evidence}


def _d(ctx):
    return ctx.get("detail")


def _dd(ctx):
    d = _d(ctx)
    return d if isinstance(d, dict) else {}


def _classes(ctx):
    sc = ctx.get("scenario") or {}
    return list((sc.get("problem") or {}).get("class") or [])


# ----------------------------------------------------------------------------------------------- gate 0
def unsourced_paths(ctx):
    """Scenario leaves with a value but no src / assumption (gate 0 list)."""
    paths = _dd(ctx).get("unsourced") or []
    return _r(not paths, unsourced=list(paths), rule="every value needs src (page/table) or assumption: true; never invent a src")


def scenario_has_intake_candidates(ctx):
    """Does the paper's intake draft hold a cited candidate (page ref) for the unsourced values? Reads only."""
    pid = (ctx.get("report") or {}).get("paper", {}).get("id")
    root = Path(ctx["root"])
    cands = [p for p in ((root / "offsim/papers" / str(pid)), (root / "out" / str(pid))) if pid and p.exists()]
    drafts = [str(f.relative_to(root)) for c in cands for f in c.glob("scenario.draft.yaml")]
    return _r(bool(drafts), drafts=drafts, hint="candidates carry page refs; a human picks the value and the src")


def classes_registered(ctx):
    """Problem classes vs the classes handled by importable registered solvers/engines."""
    from offsim.pipeline import supported_classes
    known, bad = supported_classes()
    want = set(_classes(ctx)) or set(_dd(ctx).get("unsupported_classes") or [])
    missing = sorted(want - known)
    return _r(not missing, unsupported=missing, registered=sorted(known), tools_not_importing=bad)


def tool_import_errors(ctx):
    """Names in detail.unavailable with the import error, and whether the package behind the tool is installed."""
    from offsim.pipeline import TOOL_PACKAGES
    un = _dd(ctx).get("unavailable") or {}
    rows = {}
    for key, msg in un.items():
        name = key.split(":", 1)[-1]
        pk = TOOL_PACKAGES.get(name, ())
        rows[key] = {"error": msg, "packages": {p: importlib.util.find_spec(p.replace("-", "_")) is not None for p in pk}}
    return _r(not un, unavailable=rows)


def tool_covers_classes(ctx):
    """Which registered solvers/engines declare the scenario's problem classes (candidates to switch to: a human decision)."""
    from offsim.engines.base import ENGINE_MODULES, SOLVER_MODULES, get_engine, get_solver
    want = set(_classes(ctx))
    cover = {"solver": [], "engine": []}
    for kind, mods, get in (("solver", SOLVER_MODULES, get_solver), ("engine", ENGINE_MODULES, get_engine)):
        for n in mods:
            try:
                if want and want <= set(get(n).classes):
                    cover[kind].append(n)
            except Exception:                                             # noqa: BLE001
                continue
    mm = _dd(ctx).get("tool_mismatch") or _dd(ctx).get("entur_validation")
    return _r(not mm, mismatch=mm, classes=sorted(want), tools_that_cover=cover)


def data_paths_present(ctx):
    """Every `missing_*` path recorded by gate 0: does it exist now? Evidence carries the fix command the pipeline wrote."""
    d = _dd(ctx)
    rows = {k: {"path": v, "exists": bool(v) and Path(str(v)).exists()} for k, v in d.items()
            if k.startswith("missing_") and isinstance(v, str)}
    for k in ("road_graph_error", "weather_error"):
        if k in d:
            rows[k] = {"error": d[k]}
    still = [k for k, r in rows.items() if r.get("exists") is False or "error" in r]
    return _r(not still, items=rows, fix=d.get("fix"), world=ctx.get("world"))


def world_manifest_errors(ctx):
    """data/worlds/<w>/manifest.json `errors` (stage timeouts, failed sources) and the files that exist."""
    wd = ctx.get("world_dir")
    if not wd:
        return _r(None, reason="scenario has no world (world: none)")
    man = Path(wd) / "manifest.json"
    if not man.exists():
        return _r(False, reason=f"no manifest at {man}: world not pulled", fix=f"python -m offsim.worlds.fetch_world --pull {ctx.get('world')}")
    errs = json.loads(man.read_text()).get("errors") or []
    return _r(not errs, errors=errs, files=sorted(p.name for p in Path(wd).iterdir())[:30])


def weather_block_declared(ctx):
    """missing_weather: the engine needs weather but the scenario has no `weather:` / `ensemble.weather` block."""
    sc = ctx.get("scenario")
    if sc is None:
        return _r(None, reason="scenario file not found")
    has = bool(sc.get("weather") or (sc.get("ensemble") or {}).get("weather"))
    return _r(has, weather_block=has, note="declaring a weather block is a modelling choice: ask the human which years/point")


# ----------------------------------------------------------------------------------------------- gate 1 / 1b
def plan_recheck(ctx):
    """Recompute from gate-1 detail: loads <= capacity, vehicles used <= fleet, no client twice."""
    d = _dd(ctx)
    if "routes" not in d:
        return _r(None, reason="gate detail has no routes", detail_keys=sorted(d))
    routes, loads, cap = d["routes"], d.get("loads") or [], d.get("capacity")
    flat = [c for r in routes for c in r]
    return _r(len(flat) == len(set(flat)) and (cap is None or all(x <= cap for x in loads)),
              routes=len(routes), clients=len(flat), duplicated=sorted({c for c in flat if flat.count(c) > 1}),
              loads=loads, capacity=cap, zero_based_client=(0 in flat))


def pyvrp_only_via_adapter(ctx):
    """Lesson: PyVRP 0.14 index offsets and is_client() live in offsim/solve/pyvrp_adapter.py. Nothing else may import pyvrp."""
    root = Path(ctx["root"]) / "offsim"
    offenders = []
    for f in root.rglob("*.py"):
        if f.name == "pyvrp_adapter.py" or "doctor" in f.parts:
            continue
        if re.search(r"^\s*(from pyvrp\b|import pyvrp\b)", f.read_text(errors="ignore"), re.M):
            offenders.append(str(f.relative_to(ctx["root"])))
    return _r(not offenders, importers_outside_adapter=offenders, rule="client node = idx + number_of_depots; is_client() is a method")


def solver_seed_sensitivity(ctx):
    """Informational: the seed the failing run used (provenance) and the packages; a different seed is a legal retry."""
    prov = (ctx.get("report") or {}).get("provenance") or {}
    return _r(None, solver=prov.get("solver"), pyvrp=(prov.get("packages") or {}).get("pyvrp"), note="retry with seed+1, same time budget")


def exact_gap_numbers(ctx):
    """Gate 1b numbers: gap vs gap_tol, exact status, errors."""
    d = _dd(ctx)
    gap, tol = d.get("gap"), d.get("gap_tol")
    return _r(gap is not None and tol is not None and gap <= tol, gap=gap, gap_tol=tol, exact_status=d.get("exact_status"),
              error=d.get("error"), n_clients=d.get("n_clients"), heuristic_m=d.get("heuristic_m"), exact_m=d.get("exact_m"),
              bound_m=d.get("bound_m"))


# ----------------------------------------------------------------------------------------------- gate 2
def replay_gap(ctx):
    """Gate 2 rows: planned vs simulated. A gap far above tol (>10 %) points at a different graph/index, near tol at snapping."""
    d = _d(ctx)
    rows = d if isinstance(d, list) else []
    if not rows:
        err = {k: v for k, v in _dd(ctx).items() if str(k).endswith("_engine")}
        return _r(False if err else None, engine_error=err)
    worst = max((r.get("rel_gap") or 0.0) for r in rows)
    return _r(all(r.get("pass") for r in rows), worst_rel_gap=worst, rows=rows,
              reading="gap > 10 %: index/graph mismatch between solver and replay" if worst > 0.10 else "gap near tolerance: snapping or rounding")


def graph_used(ctx):
    """Which graph the run used (provenance.graph): sealanes | roads | none. `none` with a real world = straight legs."""
    g = ((ctx.get("report") or {}).get("provenance") or {}).get("graph")
    sc = ctx.get("scenario") or {}
    world = ctx.get("world")
    straight = g == "none" and bool(world) and world != "none"
    return _r(not straight, graph=g, world=world, domain_hint=(sc.get("fleet") or [{}])[0].get("domain"),
              reading="world is set but no graph was used: legs are straight" if straight else None)


# ----------------------------------------------------------------------------------------------- gate 3
def contract_violations(ctx):
    """Violation kinds and the first lines of the contract report."""
    txt = str(_d(ctx) or "")
    return _r(not contract_kinds(txt), kinds=contract_kinds(txt), first_lines=txt.splitlines()[:6])


def worst_speed_vs_vmax(ctx):
    """Parse 'worst X m/s' and 'above vmax Y m/s' from the contract text."""
    txt = str(_d(ctx) or "")
    m = re.search(r"above vmax ([\d.]+) m/s; worst ([\d.]+) m/s", txt)
    if not m:
        return _r(None, reason="no speed violation in the detail text")
    vmax, worst = float(m.group(1)), float(m.group(2))
    return _r(False, vmax_mps=vmax, worst_mps=worst, ratio=worst / vmax,
              reading="ratio > 3: a leg crosses a detour/teleport or the time axis is wrong; near 1.05-1.3: snapped quay or vmax unit (kn vs m/s)")


def legs_cross_land_with_straight_graph(ctx):
    """Lesson: straight legs crossed real land (audit 1). Sea legs must follow offsim.worlds.sealanes. Checks the run's graph."""
    g = graph_used(ctx)["evidence"]
    kinds = contract_kinds(_d(ctx))
    straight = g["graph"] == "none"
    return _r(not ("land" in kinds and straight), graph=g["graph"], world=g["world"], land_violation="land" in kinds,
              fix="rerun with the pulled world so legs route on sea lanes" if straight else "legs already on lanes: check the quay snap radius (quay_snap_m)")


def quay_snaps(ctx):
    """report.quay_snap_m: large snaps put a node on land/other water."""
    sn = (ctx.get("report") or {}).get("quay_snap_m") or {}
    big = {k: v for k, v in sn.items() if v and v > 500}
    return _r(not big, snaps_over_500m=big, all=sn or None)


def capacity_range(ctx):
    txt = str(_d(ctx) or "")
    m = re.search(r"load range \[([^,]+), ([^\]]+)\] outside \[0, ([^\]]+)\]", txt)
    return _r(not m, load_lo=m and m.group(1), load_hi=m and m.group(2), capacity=m and m.group(3))


def stationary_motion(ctx):
    txt = str(_d(ctx) or "")
    m = re.search(r"moves (\d+) m while '(\w+)'", txt)
    return _r(not m, metres=m and int(m.group(1)), state=m and m.group(2),
              reading="engine emitted a stationary state on a moving leg" if m else None)


def teleport_count(ctx):
    txt = str(_d(ctx) or "")
    m = re.search(r"(\d+) position jump", txt)
    return _r(not m, jumps=m and int(m.group(1)), reading="zero elapsed time between rows at different positions: engine event order")


# ----------------------------------------------------------------------------------------------- gate 3e
def ensemble_failures(ctx):
    d = _dd(ctx)
    return _r(not d.get("failures"), n_runs=d.get("n_runs"), n_valid=d.get("n_valid"), failures=(d.get("failures") or [])[:5],
              weather_sources=d.get("weather_sources"), unsupported=d.get("unsupported"))


def ensemble_weather_is_synthetic(ctx):
    ens = (ctx.get("report") or {}).get("ensemble") or {}
    syn = ens.get("synthetic_weather")
    if syn is None:
        syn = "synthetic" in json.dumps(_dd(ctx).get("weather_sources", ""))
    return _r(not syn, synthetic_weather=syn, reading="synthetic weather is test-only: report.reportable stays False")


# ----------------------------------------------------------------------------------------------- gate 4 / 4b / 4c
def kpi_gaps(ctx):
    """Gate 4 rows: paper vs ours, gap vs tolerance, missing measurements, assumptions in play."""
    rows = _d(ctx) if isinstance(_d(ctx), list) else []
    bad = [r for r in rows if not r.get("pass")]
    return _r(not bad, failing=bad, missing_measured=[r["kpi"] for r in bad if r.get("ours") is None],
              assumptions=(ctx.get("report") or {}).get("assumptions"),
              rule="the paper's value and tolerance are fixed; the status word is 'did not reproduce', not a bug to hide")


def kpi_names_measurable(ctx):
    """Reported KPI names the engine did not measure (ours is None): name mismatch, not a numeric gap."""
    rows = _d(ctx) if isinstance(_d(ctx), list) else []
    measured = sorted((ctx.get("report") or {}).get("measured") or {})
    missing = [r["kpi"] for r in rows if r.get("ours") is None]
    return _r(not missing, not_measured=missing, measured_names=measured)


def ais_gate_rows(ctx):
    d = _dd(ctx)
    return _r(not d.get("failed") and not d.get("reason"), reason=d.get("reason"), failed=(d.get("failed") or [])[:5], src=d.get("src"))


def ais_calibration_present(ctx):
    wd = ctx.get("world_dir")
    p = Path(wd) / "ais" / "calibration.json" if wd else None
    return _r(bool(p and p.exists()), path=str(p) if p else None)


def entur_gate_rows(ctx):
    d = _dd(ctx)
    return _r(not d.get("reason"), reason=d.get("reason"), t0_utc=d.get("t0_utc"), journeys=(d.get("journeys") or [])[:5])


def entur_vehicles_present(ctx):
    wd = ctx.get("world_dir")
    p = Path(wd) / "entur" / "vehicles.csv" if wd else None
    n = sum(1 for _ in p.open()) - 1 if p and p.exists() else 0
    return _r(n > 0, path=str(p) if p else None, rows=max(n, 0))


# ----------------------------------------------------------------------------------------------- QA, data, CI
def asset_dims(ctx):
    """CAD QA report (dict from offsim.assets.cad.qa.qa) or the refusal text: failed/missing dims."""
    d = ctx.get("detail")
    if isinstance(d, dict) and "dims" in d:
        bad = {r["name"]: r["rel_err"] for r in d["dims"] if r.get("pass") is False}
        return _r(not bad and not d.get("missing_required"), off=bad, missing_required=d.get("missing_required"),
                  principal_sourced=d.get("principal_sourced"), tol=d.get("tol"))
    return _r(False, text=str(d)[:300])


def asset_has_sourced_dim(ctx):
    d = ctx.get("detail")
    ok = bool(isinstance(d, dict) and d.get("principal_sourced"))
    return _r(ok, rule="a dim value moves only to a cited figure; the solid is rebuilt to the dim, never the dim to the solid")


def host_errors(ctx):
    """Stage errors in the world manifest and 429/timeouts in the detail text."""
    errs = (world_manifest_errors(ctx)["evidence"].get("errors") or [])
    txt = str(_d(ctx) or "")
    hits = [e for e in errs if re.search(r"timed out|exceeded|429|Timeout|Too Many", str(e.get("error", "")), re.I)]
    return _r(not hits and not re.search(r"429|Too Many|timed out", txt, re.I), manifest_hits=hits, text=txt[:200])


def stage_budgets_present(ctx):
    """Lesson: a silent fetch hung 30 min. fetch_world must keep per-stage budgets (BUDGET_S) and flush its log."""
    f = Path(ctx["root"]) / "offsim/worlds/fetch_world.py"
    txt = f.read_text() if f.exists() else ""
    return _r("BUDGET_S" in txt and "def stage" in txt and "flush=True" in txt, file=str(f.relative_to(ctx["root"])) if f.exists() else None)


def data_schema_columns(ctx):
    """Missing/unexpected names in the error text (KeyError 'x', missing columns [...])."""
    txt = str(_d(ctx) or "")
    keys = re.findall(r"KeyError: ?['\"]?([\w .-]+)", txt) + re.findall(r"missing columns \[([^\]]*)\]", txt)
    return _r(not keys, names=keys, text=txt[:200])


def intake_kpi_label_tolerant(ctx):
    """Lesson: intake KPI phrase must map by longest known key, never KeyError on an unknown phrase."""
    try:
        from offsim.intake.paper import _kpi_label
        a, b = _kpi_label("objective function"), _kpi_label("weird metric")
        return _r(a == "objective" and b.startswith("kpi_"), objective_function=a, weird_metric=b)
    except Exception as exc:                                              # noqa: BLE001
        return _r(False, error=f"{type(exc).__name__}: {exc}")


def egl_available(ctx):
    """Lesson: skia-python needs the system libEGL/libGL (apt libegl1 libgl1)."""
    egl, gl = ctypes.util.find_library("EGL"), ctypes.util.find_library("GL")
    return _r(bool(egl and gl), libEGL=egl, libGL=gl, fix="sudo apt-get install -y libegl1 libgl1 libfontconfig1 (retry once with --fix-missing)")


def ci_workflow_retries_apt(ctx):
    f = Path(ctx["root"]) / ".github/workflows/tests.yml"
    txt = f.read_text() if f.exists() else ""
    return _r("apt-get install" in txt and "--fix-missing" in txt, file=str(f) if f.exists() else None)


def numpy_float_in_approx(ctx):
    """Lesson: newer pytest rejects numpy float32 in pytest.approx(...). Flag approx() calls whose argument is a numpy scalar
    constructor (np.float32(..), np.float64(..)). Plain float(..) is the fix."""
    root = Path(ctx["root"]) / "tests"
    hits = []
    for f in root.glob("test_*.py"):
        if f.name == "test_doctor.py":
            continue
        try:
            tree = ast.parse(f.read_text())
        except SyntaxError:
            continue
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "approx" and n.args:
                a = n.args[0]
                if isinstance(a, ast.Call) and getattr(a.func, "attr", "") in ("float32", "float64", "float16"):
                    hits.append(f"{f.name}:{n.lineno}")
    return _r(not hits, hits=hits, fix="wrap with float(...) before approx")


def tests_weakened(ctx):
    """Lesson: 5 failures were closed by editing tests (premises were wrong, but it must be a decision). Lists removed assert
    lines in `git diff HEAD -- tests` (read only). Check the premise first; edit with a `why:` line and a LESSONS entry."""
    try:
        out = subprocess.run(["git", "diff", "-U0", "HEAD", "--", "tests"], cwd=ctx["root"], capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        return _r(None, reason=f"git unavailable: {exc}")
    removed = [ln[1:].strip() for ln in out.splitlines() if ln.startswith("-") and not ln.startswith("---") and "assert" in ln]
    added = [ln for ln in out.splitlines() if ln.startswith("+") and not ln.startswith("+++")]
    why = any("why:" in ln for ln in added)
    return _r(not removed or why, removed_asserts=removed[:10], why_line_present=why)


def lessons_have_guards(ctx):
    """Every closed lesson names a guard that exists (offsim.doctor.lessons)."""
    from offsim.doctor import lessons
    bad = [(i, ls["code"]) for i, ls in enumerate(lessons.load(), 1) if not ls.get("open") and not lessons.guard_exists(ls.get("guard"), ctx["root"])]
    return _r(not bad, bad=bad)
