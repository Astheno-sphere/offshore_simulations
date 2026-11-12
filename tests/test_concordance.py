"""Concordance: docs, skills, catalog, registries and code must tell the same story (docs/SYSTEM_PLAN.md 3.3).

Static and fast: files are parsed, nothing is fetched, no solver or engine is imported (registries are read with
the AST where an optional dependency could be missing). Every failure message says which file to fix.

Temporary allow-lists are data at the top of this file (PENDING_*, HANDOVER_*). Each entry carries the reason and the
owner; delete the entry when the owner lands the change. docs/GUARDS.md maps every hard rule in AGENTS.md to the test
or gate that enforces it.
"""
from __future__ import annotations

import ast
import re
import warnings
from pathlib import Path

import pytest
import yaml

from conftest import ROOT

# --- allow-lists: things other work packages are adding right now ------------------------------------------------
# CLI commands another package is about to add to offsim/__main__.py. Docs may name them before the code exists; once the parser has one, the entry is stale and a warning asks for its removal.
PENDING_COMMANDS: set[str] = set()      # W2 landed status/next/advance/decide/doctor/learn/live; add names here for the next wave
# Repo paths other packages create (W2 studio, W3 doctor, W4 live, W5 agents). Prefix match.
PENDING_PATHS = (
    "offsim/studio", "offsim/doctor", "offsim/live", "docs/LIVE_STATUS.md", "docs/LESSONS.md",
    "out/agent_reports", "coordination/reports", "coordination/done",     # done/ appears when the first task is closed
)
# Paths that are generated output or live on the data branch (papers/auto), never committed to the working branch.
GENERATED_PATHS = ("papers/feed.jsonl", "papers/tags.jsonl", "papers/gaps.yaml", "papers/review.yaml", "papers/auto")   # papers/auto is a git branch
# Files not scanned for CLI commands: SYSTEM_PLAN is a plan whose commands (gap draft, article) do not exist yet.
COMMAND_SCAN_SKIP = {"docs/SYSTEM_PLAN.md"}
# Files that are dated history logs: stale shorthand there is a record, not a claim about the present.
HISTORY_DOCS = {"docs/RESUME.md", "docs/SYSTEM_PLAN.md", "docs/TESTLOG.md", "docs/LESSONS.md"}
# Handover: rule text in files owned by another package that still violates a check. {(test, file): reason}.
HANDOVER: dict[tuple[str, str], str] = {
}

GATES = ("0", "1", "1b", "2", "3", "3e", "4", "4b", "4c")
REPO_PATH_PREFIXES = ("offsim/", "docs/", "tools/", "skills/", "tests/", ".github/", "catalog/", "papers/",
                      "coordination/")


# --- helpers ------------------------------------------------------------------------------------------------------
def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def md_files(*extra: str) -> list[str]:
    """AGENTS.md, CLAUDE.md, docs/*.md and skills/*/SKILL.md (plus `extra`), as repo-relative paths."""
    out = ["AGENTS.md", "CLAUDE.md", *extra]
    out += sorted(str(p.relative_to(ROOT)) for p in (ROOT / "docs").glob("*.md"))
    out += sorted(str(p.relative_to(ROOT)) for p in (ROOT / "skills").glob("*/SKILL.md"))
    return [f for f in dict.fromkeys(out) if (ROOT / f).exists()]


def code_spans(text: str) -> list[tuple[int, str]]:
    """(line number, content) of every inline `code` span and every line inside a fenced block."""
    out, fenced = [], False
    for n, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            out.append((n, line))
        else:
            out += [(n, m) for m in re.findall(r"`([^`\n]+)`", line)]
    return out


def handover(test: str, rel: str) -> bool:
    return (test, rel) in HANDOVER


def table_first_column_names(text: str, heading: str) -> list[str]:
    """Backticked names in column 1 of the first markdown table after the `## heading` line."""
    m = re.search(rf"^## {re.escape(heading)}.*?$", text, re.M)
    assert m, f"docs/ENGINES.md has no '## {heading}' section"
    names, started = [], False
    for line in text[m.end():].splitlines():
        if line.startswith("## "):
            break
        if line.startswith("|"):
            started = True
            cell = line.split("|")[1].strip()
            hit = re.fullmatch(r"`([\w-]+)`", cell)
            if hit:
                names.append(hit.group(1))
        elif started:
            break
    return names


def static_classes(module: str) -> set[str]:
    """`classes = {...}` of every class in `module`, read from the AST (no import, so optional deps cannot break it)."""
    path = ROOT / (module.replace(".", "/") + ".py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    consts: dict[str, set[str]] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Set):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    consts[t.id] = {e.value for e in node.value.elts if isinstance(e, ast.Constant)}
    out: set[str] = set()
    for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
        for node in cls.body:
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "classes" for t in node.targets):
                if isinstance(node.value, ast.Set):
                    out |= {e.value for e in node.value.elts if isinstance(e, ast.Constant)}
                elif isinstance(node.value, ast.Name):
                    out |= consts.get(node.value.id, set())
    return out


def imported_top_levels(roots=("offsim", "tools", "tests", "skills")) -> set[str]:
    """Top-level module names imported anywhere in the repo, plus string constants (import_module("x"), TOOL_PACKAGES)."""
    seen: set[str] = set()
    for r in roots:
        for f in (ROOT / r).rglob("*.py"):
            if "node_modules" in f.parts or "__pycache__" in f.parts:
                continue
            try:
                tree = ast.parse(f.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    seen |= {a.name.split(".")[0] for a in node.names}
                elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                    seen.add(node.module.split(".")[0])
                elif isinstance(node, ast.Constant) and isinstance(node.value, str) and re.fullmatch(r"[A-Za-z_][\w.]*", node.value):
                    seen.add(node.value.split(".")[0])      # importlib.import_module("pyvrp"), TOOL_PACKAGES = ("pyomo", ...)
    return seen


# --- 1. CLI commands ----------------------------------------------------------------------------------------------
CMD_RE = re.compile(r"(?:python3? -m offsim|(?<![\w./-])offsim)\s+([a-z][\w-]*)")


def real_commands() -> set[str]:
    from offsim.__main__ import PASSTHROUGH, build_parser
    sub = next(a for a in build_parser()._actions if getattr(a, "choices", None))
    return set(sub.choices) | set(PASSTHROUGH)


def test_cli_commands_named_in_docs_and_skills_exist():
    real = real_commands()
    stale = sorted(PENDING_COMMANDS & real)
    if stale:
        warnings.warn(f"PENDING_COMMANDS in tests/test_concordance.py now exist in offsim.__main__: remove {stale}")
    bad = []
    for rel in md_files():
        if rel in COMMAND_SCAN_SKIP or handover("cli", rel):
            continue
        for n, span in code_spans(read(rel)):
            for cmd in CMD_RE.findall(span):
                if cmd not in real | PENDING_COMMANDS:
                    bad.append(f"{rel}:{n}: `offsim {cmd}`")
    assert not bad, ("these docs name an `offsim` subcommand that offsim/__main__.py does not define. Fix the doc, or add the "
                     f"command (known: {sorted(real)}):\n  " + "\n  ".join(bad))


# --- 2. ENGINES.md vs registries ----------------------------------------------------------------------------------
def test_engines_doc_lists_exactly_the_registered_solvers_and_engines():
    from offsim.engines.base import ENGINE_MODULES, SOLVER_MODULES
    text = read("docs/ENGINES.md")
    solvers = table_first_column_names(text, "Solvers")
    engines = table_first_column_names(text, "Engines")
    assert sorted(solvers) == sorted(SOLVER_MODULES), (
        f"docs/ENGINES.md 'Solvers' table lists {sorted(solvers)}; SOLVER_MODULES in offsim/engines/base.py has "
        f"{sorted(SOLVER_MODULES)}. Add or remove the table rows.")
    assert sorted(engines) == sorted(ENGINE_MODULES), (
        f"docs/ENGINES.md 'Engines' table lists {sorted(engines)}; ENGINE_MODULES in offsim/engines/base.py has "
        f"{sorted(ENGINE_MODULES)}. Add or remove the table rows.")


def test_every_engine_has_its_own_section_and_architecture_names_them():
    from offsim.engines.base import ENGINE_MODULES, SOLVER_MODULES
    engines_doc = read("docs/ENGINES.md")
    sections = set(re.findall(r"^### `?([\w-]+)`?", engines_doc, re.M))
    missing = sorted(set(ENGINE_MODULES) - sections)
    assert not missing, f"docs/ENGINES.md needs a '### <name>' section (mapping, KPIs, limits) for engines {missing}"
    arch = read("docs/ARCHITECTURE.md")
    diagram = "\n".join(l for l in arch.splitlines() if re.search(r"L[12] (SOLVE|SIMULATE)", l))
    absent = sorted(n for n in [*SOLVER_MODULES, *ENGINE_MODULES] if not re.search(rf"\b{n}\b", diagram))
    assert not absent, f"docs/ARCHITECTURE.md L1/L2 diagram lines do not name {absent}; add them next to the other tools"


# --- 3. gap finder suggests engines that exist and fit ------------------------------------------------------------
# Gap/tag problem classes that are named differently from the engine's `classes` entry.
TAG_CLASS_ALIAS = {"HRP": "WFPPP"}      # helicopter routing (tag) = weekly flight program problem (air engine, whelp solver)


def test_gap_finder_suggests_an_engine_that_covers_the_class():
    from offsim.engines.base import ENGINE_MODULES
    from offsim.research import gaps
    from offsim.research.tags import CLASS_RULES, MODE_RULES
    covers = {name: static_classes(mod) for name, mod in ENGINE_MODULES.items()}
    bad = []
    for cls in CLASS_RULES:
        engine_cls = TAG_CLASS_ALIAS.get(cls, cls)
        coverers = sorted(n for n, c in covers.items() if engine_cls in c)
        for mode in [*MODE_RULES, "none"]:
            got = gaps.suggest_engine(cls, mode)
            if got not in ENGINE_MODULES:
                bad.append(f"suggest_engine({cls!r}, {mode!r}) -> {got!r}, not a registered engine")
            elif coverers and got not in coverers:
                bad.append(f"suggest_engine({cls!r}, {mode!r}) -> {got!r}, but only {coverers} cover {engine_cls}")
    assert not bad, ("offsim/research/gaps.py suggest_engine disagrees with the engine registry (each engine's `classes`). "
                     "Class decides first, mode only for classes no engine covers:\n  " + "\n  ".join(bad))
    assert gaps.suggest_engine("HRP", "heli") == "air" and "WFPPP" in covers["air"], (
        "helicopter routing (HRP) must map to the `air` engine, whose classes must include WFPPP")


# --- 4. pinned packages are used or explained ---------------------------------------------------------------------
IMPORT_NAME = {"pyyaml": "yaml", "pillow": "PIL", "skia-python": "skia", "orbit-nrel": "ORBIT", "cadquery-ocp": "OCP",
               "scikit-image": "skimage", "gtfs-kit": "gtfs_kit", "xarray-spatial": "xrspatial", "netcdf4": "netCDF4"}
USED_NOT_IMPORTED = {"pytest"}      # the runner itself
EXPLAINED = re.compile(r"declared|not (?:yet )?(?:called|imported|used|wired)|never imported|unused|pending|reference|"
                       r"optional|candidate|cross-check|to be wired|planned", re.I)


def pinned_packages() -> dict[str, str]:
    """{normalised package name: requirements file} for every requirement line in requirements*.txt."""
    out = {}
    for f in sorted(ROOT.glob("requirements*.txt")):
        for line in f.read_text().splitlines():
            line = line.split("#")[0].strip()
            if not line or line.startswith("-"):
                continue
            name = re.split(r"[=<>!~\[; ]", line)[0].lower().replace("_", "-")
            out.setdefault(name, f.name)
    return out


def test_every_pinned_package_is_imported_or_explained_in_the_catalog():
    imported = {i.lower() for i in imported_top_levels()}
    catalog = yaml.safe_load(read("catalog/tools.yaml"))["tools"]
    bad = []
    for pkg, req in pinned_packages().items():
        mod = IMPORT_NAME.get(pkg, pkg.replace("-", "_")).lower()
        if mod in imported or pkg in USED_NOT_IMPORTED:
            continue
        hits = [t for t in catalog if pkg in (t["id"].lower(), t["name"].lower().split()[0]) or
                t["id"].lower().replace("-", "") == pkg.replace("-", "")]
        ok = [t for t in hits if EXPLAINED.search(t.get("role", "")) and (
            t["status"] in ("installed", "watch", "candidate") or
            (t["status"] == "tested" and "docs/TESTLOG.md" in str(t.get("evidence", ""))))]    # tested by hand, recorded in TESTLOG
        if not ok:
            bad.append(f"{pkg} ({req}): never imported under offsim/, tools/, tests/ or skills/ and "
                       + ("its catalog role does not say why it is not called yet" if hits else "has no catalog entry"))
    assert not bad, ("Declared but unused packages need an import + test (SYSTEM_PLAN rule 7) or a catalog/tools.yaml entry "
                     "with status installed|watch|candidate whose role says it is declared / not yet called, then "
                     "`python tools/catalog_build.py`:\n  " + "\n  ".join(bad))


# --- 5. spec stubs are on the roadmap -----------------------------------------------------------------------------
def stub_modules() -> list[str]:
    out = []
    for f in sorted((ROOT / "offsim").rglob("*.py")):
        if "__pycache__" in f.parts or "node_modules" in f.parts:
            continue
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Raise) and node.exc is not None:
                exc = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
                if isinstance(exc, ast.Name) and exc.id == "NotImplementedError":
                    out.append(str(f.relative_to(ROOT)))
                    break
    return out


def test_every_spec_stub_module_is_named_in_the_roadmap():
    roadmap = read("docs/ROADMAP.md")
    missing = []
    for rel in stub_modules():
        stem = rel[:-3]                                    # offsim/weather/fetch
        if stem.endswith("/__init__"):
            stem = stem[: -len("/__init__")]              # offsim/emissions
        short = stem[len("offsim/"):]                      # weather/fetch
        forms = {stem, stem.replace("/", "."), short, short.replace("/", "."), rel}
        if not any(f in roadmap for f in forms):
            missing.append(rel)
    assert not missing, ("these modules raise NotImplementedError (spec stubs) but docs/ROADMAP.md never names them; add them "
                         "to its 'Spec stubs' table (or build them): " + ", ".join(missing))


# --- 6. backticked repo paths exist -------------------------------------------------------------------------------
def backticked_paths(rel: str) -> list[tuple[int, str]]:
    out = []
    for n, span in code_spans(read(rel)):
        first = span.strip().split()[0] if span.strip() else ""
        if not first.startswith(REPO_PATH_PREFIXES):
            continue
        p = first.rstrip(".,;:)")
        p = re.split(r"::|:\d", p)[0]
        if any(c in p for c in "<>*{}|$") or "..." in p or "…" in p or p.endswith("/..."):
            continue
        out.append((n, p))
    return out


def test_paths_cited_in_agent_docs_and_skills_exist():
    files = ["AGENTS.md", "CLAUDE.md", "docs/ARCHITECTURE.md", *sorted(str(p.relative_to(ROOT)) for p in (ROOT / "skills").glob("*/SKILL.md"))]
    bad = []
    for rel in files:
        if not (ROOT / rel).exists() or handover("paths", rel):
            continue
        for n, p in backticked_paths(rel):
            if p.startswith(PENDING_PATHS) or p in GENERATED_PATHS:
                continue
            if not (ROOT / p).exists():
                bad.append(f"{rel}:{n}: `{p}`")
    assert not bad, "paths written in backticks that do not exist in the repo (fix the path or the doc):\n  " + "\n  ".join(bad)


# --- 7. workflow inputs named in docs exist -----------------------------------------------------------------------
def workflow_inputs() -> dict[str, set[str]]:
    out = {}
    for f in sorted((ROOT / ".github/workflows").glob("*.yml")):
        doc = yaml.safe_load(f.read_text())
        on = doc.get(True, doc.get("on")) or {}
        out[f.stem] = set(((on.get("workflow_dispatch") or {}).get("inputs") or {}))
    return out


IDENT = r"[a-z][a-z0-9_]*"


def workflow_input_claims(text: str, workflows: set[str]):
    """(workflow, input) pairs the text claims. A claim is read from the ~240 characters after a workflow mention:
    'inputs a, b / c', `name: value`, `name=value`, or 'with name `value`, name2 `value`'."""
    claims = []
    for para in re.split(r"\n\s*\n|\n(?=\|)", text):          # paragraphs; every table row is its own unit
        flat = re.sub(r"\s+", " ", para)
        marks = []
        for wf in workflows:
            pat = rf"`{wf}(?:\.yml)?`|workflow {wf}\b|{wf} workflow|(?<![\w`-]){wf}(?![\w`-])" if "-" in wf else \
                  rf"`{wf}(?:\.yml)?`|workflow {wf}\b|\b{wf} workflow"
            marks += [(m.start(), m.end(), wf) for m in re.finditer(pat, flat)]
        marks.sort()
        for i, (_, end, wf) in enumerate(marks):
            stop = marks[i + 1][0] if i + 1 < len(marks) else len(flat)
            window = flat[end:min(stop, end + 240)]
            for m in re.finditer(r"\binputs?\b[ :]*((?:`?" + IDENT + r"`?(?:\s*[,/]\s*|\s+and\s+))*`?" + IDENT + r"`?)", window):
                claims += [(wf, n) for n in re.findall(IDENT, m.group(1)) if n not in ("and", "the")]
            claims += [(wf, n) for n in re.findall(r"`(" + IDENT + r")(?:: |=)[^`]*`", window)]
            w = re.search(r"\bwith ((?:" + IDENT + r" `[^`]+`(?:, | and )?)+)", window)
            if w:
                claims += [(wf, n) for n in re.findall(r"(" + IDENT + r") `", w.group(1)) if n not in ("the", "a", "an")]
    return claims


def test_workflow_inputs_named_in_docs_exist_in_the_workflow_yaml():
    inputs = workflow_inputs()
    bad = []
    for rel in md_files():
        if handover("workflow", rel):
            continue
        for wf, name in workflow_input_claims(read(rel), set(inputs)):
            if name not in inputs[wf]:
                bad.append(f"{rel}: workflow {wf} has no input {name!r} (inputs: {sorted(inputs[wf]) or 'none'})")
    assert not bad, "docs/skills name workflow_dispatch inputs that the workflow YAML lacks (fix the doc or the YAML):\n  " + "\n  ".join(sorted(set(bad)))


def test_workflow_input_reader_understands_the_phrasings_we_use():
    ws = {"fetch-world", "solve"}
    got = set(workflow_input_claims("the `fetch-world` workflow (inputs `place`, `modes`, `radius_km`)", ws))
    assert got == {("fetch-world", "place"), ("fetch-world", "modes"), ("fetch-world", "radius_km")}
    got = set(workflow_input_claims("Actions: fetch-world with `depth: true` and `metocean_start`", ws))
    assert ("fetch-world", "depth") in got
    got = set(workflow_input_claims("Actions -> fetch-world with place `Molde`, modes `sea,road,bus`", ws))
    assert got == {("fetch-world", "place"), ("fetch-world", "modes")}


# --- 8. hard rules have guards ------------------------------------------------------------------------------------
def hard_rules() -> list[str]:
    """Bullets under 'Hard rules' in AGENTS.md (markdown heading or numbered item), continuation lines joined."""
    lines = read("AGENTS.md").splitlines()
    start = next((i for i, l in enumerate(lines) if "hard rules" in l.lower()), None)
    assert start is not None, "AGENTS.md has no 'Hard rules' section"
    heading = lines[start].lstrip().startswith("#")
    rules: list[str] = []
    for l in lines[start + 1:]:
        if (heading and l.startswith("#")) or (not heading and re.match(r"\d+\.", l)):
            break
        if re.match(r"\s*[-*] ", l):
            rules.append(l.strip()[2:].strip())
        elif rules and l.strip():
            rules[-1] += " " + l.strip()
    return rules


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def guards_table(hard_only: bool = False) -> list[tuple[str, list[str]]]:
    """Rows of docs/GUARDS.md; `hard_only` stops at the '## Other rules' heading (rows after it are extra guards)."""
    rows = []
    for line in read("docs/GUARDS.md").splitlines():
        if hard_only and line.startswith("## Other"):
            break
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.startswith("|") and len(cells) >= 2 and not set(cells[0]) <= set("-: ") and cells[0].lower() != "rule":
            rows.append((cells[0], re.findall(r"`([^`]+)`", cells[1])))
    return rows


def guard_problem(guard: str) -> str | None:
    """None when the guard resolves: tests/x.py::name, gate:<id>, ci:<workflow path>, or path:<repo path>."""
    if "::" in guard:
        path, name = guard.split("::", 1)
        name = name.split("[")[0]
        f = ROOT / path
        if not f.exists():
            return f"{path} does not exist"
        defs = {n.name for n in ast.walk(ast.parse(f.read_text())) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        return None if name in defs else f"{path} has no test {name}"
    kind, _, value = guard.partition(":")
    if kind == "gate":
        src = read("offsim/pipeline.py")
        return None if re.search(rf'"{re.escape(value)}"', src) else f"gate {value!r} not found in offsim/pipeline.py"
    if kind in ("ci", "path"):
        return None if (ROOT / value).exists() else f"{value} does not exist"
    return f"unknown guard form {guard!r} (use tests/x.py::name, gate:<id>, ci:<path>, path:<path>)"


def test_every_hard_rule_has_a_recorded_guard_that_exists():
    rules = hard_rules()
    assert len(rules) >= 5, "AGENTS.md 'Hard rules' lost its bullets; the guard check needs them"
    rows = guards_table()
    keyed = {norm(r): g for r, g in rows}
    missing = []
    for rule in rules:
        hit = [g for k, g in keyed.items() if k and (norm(rule).startswith(k) or k.startswith(norm(rule)[:60]))]
        if not hit or not hit[0]:
            missing.append(rule[:90])
    assert not missing, ("each hard rule in AGENTS.md needs a row in docs/GUARDS.md ('| rule | `guard` |', rule text = the start "
                         "of the bullet) naming a test, gate or CI file:\n  " + "\n  ".join(missing))
    broken = [f"{r[:50]}: {g} -> {p}" for r, gs in rows for g in gs if (p := guard_problem(g))]
    assert not broken, "docs/GUARDS.md names guards that do not exist:\n  " + "\n  ".join(broken)
    stale = [r[:60] for r, _ in guards_table(hard_only=True) if not any(norm(rule).startswith(norm(r)) or norm(r).startswith(norm(rule)[:60]) for rule in rules)]
    assert not stale, f"docs/GUARDS.md has rows for rules AGENTS.md no longer states (delete or re-word): {stale}"


# --- 9. agent docs do not contradict the code ---------------------------------------------------------------------
def test_agent_render_modes_in_claude_md_match_the_renderer():
    import json
    render = read("offsim/render_deck/render.py")
    modes = re.search(r'"--agents", choices=\[([^\]]+)\]', render)
    assert modes, "offsim/render_deck/render.py lost its --agents choices; update this test"
    choices = set(re.findall(r'"(\w+)"', modes.group(1)))
    style = json.loads(read("offsim/style.json"))
    assert style["agent_mode"] in choices, f"offsim/style.json agent_mode {style['agent_mode']!r} is not a renderer choice {sorted(choices)}"
    claude = read("CLAUDE.md")
    line = next((l for l in claude.splitlines() if "agent_mode" in l), "")
    absent = sorted(m for m in choices - {"dot"} if m not in line)
    assert not absent, f"CLAUDE.md agent_mode line must list every real mode (missing {absent}; `dot` is debug-only): {line.strip()!r}"
    assert (ROOT / "offsim/assets/cad").is_dir() and "offsim/assets/cad" in claude, (
        "CAD line art exists (offsim/assets/cad); CLAUDE.md must say agents/sites can render from it")
    director = read("skills/visual-director/SKILL.md")
    assert f"`{style['agent_mode']}` (default)" in director, f"skills/visual-director/SKILL.md must name `{style['agent_mode']}` as the default mode"


def pipeline_gate_ids() -> set[str]:
    src = read("offsim/pipeline.py")
    ids = set(re.findall(r'(?:stop\(|\["gates"\]\[)"(\w+)"', src))
    return {i.split("_")[0] for i in ids}


def test_gate_list_in_code_and_docs_agree():
    assert pipeline_gate_ids() == set(GATES), (
        f"offsim/pipeline.py has gates {sorted(pipeline_gate_ids())}; GATES in tests/test_concordance.py (and every doc that lists "
        f"them) says {GATES}. A gate was added or removed: update the docs, then GATES.")
    bad = []
    for rel in ["AGENTS.md", "CLAUDE.md", *[f for f in md_files() if f not in HISTORY_DOCS]]:
        if handover("gates", rel):
            continue
        text = read(rel)
        for m in re.finditer(r"gates? 0\s*[–-]\s*4", text):
            if not re.search(r"1b", text[m.end(): m.end() + 140]):
                bad.append(f"{rel}: '{m.group(0)}' without the sub-gates 1b, 3e, 4b, 4c right after it")
    assert not bad, ("the gate list is 0, 1, 1b, 2, 3, 3e, 4, 4b, 4c. 'gates 0-4' alone hides the opt-in gates; write "
                     "'gates 0-4 (+ 1b, 3e, 4b, 4c where the scenario sets them)':\n  " + "\n  ".join(bad))
    claude = read("CLAUDE.md")
    assert all(g in claude for g in ("1b", "3e", "4b", "4c")), "CLAUDE.md must list the opt-in gates 1b, 3e, 4b, 4c"


def test_ampl_runs_on_actions_or_laptop_everywhere_it_is_stated():
    for rel in ("offsim/solve/ampl_adapter.py", ".github/workflows/solve.yml", "tools/ampl_mcp"):
        assert (ROOT / rel).exists(), f"{rel} is where AMPL runs; docs cite it"
    engines = read("docs/ENGINES.md")
    row = next(l for l in engines.splitlines() if l.startswith("| `ampl`"))
    assert "here" not in row.split("|")[5].lower() or "Actions" in row, f"docs/ENGINES.md ampl row says AMPL runs here: {row}"
    assert re.search(r"\| AMPL .*?\| ✘", read("docs/ARCHITECTURE.md")), (
        "docs/ARCHITECTURE.md environment table must show AMPL as ✘ in the Claude workspace column")
    claude = read("CLAUDE.md")
    assert "AMPL" in claude and "Actions" in claude and "laptop" in claude, (
        "CLAUDE.md must say AMPL runs on GitHub Actions (solve.yml) or the laptop (tools/ampl_mcp), never in the Claude workspace")
    bad = []
    for rel in ["AGENTS.md", "CLAUDE.md", *sorted(str(p.relative_to(ROOT)) for p in (ROOT / "skills").glob("*/SKILL.md"))]:
        if handover("ampl", rel):
            continue
        lines = read(rel).splitlines()
        for i, l in enumerate(lines):
            if "AMPL" in l and "AMPL_LICENSE" not in l:
                a, b = i, i                     # the paragraph around the mention
                while a > 0 and lines[a - 1].strip():
                    a -= 1
                while b + 1 < len(lines) and lines[b + 1].strip():
                    b += 1
                ctx = " ".join(lines[a: b + 1])
                if not re.search(r"Actions|laptop|solve\.yml|ampl_mcp|workspace cannot|blocked|download|twin|Pyomo|exact|\.mod|opt-model", ctx):
                    bad.append(f"{rel}:{i + 1}: {l.strip()[:100]}")
    assert not bad, "AMPL is mentioned without saying where it runs (Actions solve.yml / laptop ampl_mcp):\n  " + "\n  ".join(bad)
