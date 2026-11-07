"""Import rules from docs/ARCHITECTURE.md and offsim/engines/base.py, checked on the AST (no imports executed).

The layer map is data (LAYERS, FORBIDDEN): to add a layer or a rule, edit the tables, not the checker.
Relative imports are resolved to absolute module names before matching. Imports inside functions count.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "offsim"

# layer name -> offsim paths (files or package dirs, relative to the repo root)
LAYERS: dict[str, list[str]] = {
    "L5 present": ["offsim/scene.py", "offsim/motion", "offsim/render_deck", "offsim/cinema"],
    "L2 simulate": ["offsim/engines"],
    "L1 solve": ["offsim/solve"],
}

# layer name -> module prefixes its files may not import (dotted names; a prefix matches itself and children)
FORBIDDEN: dict[str, list[str]] = {
    "L5 present": ["offsim.solve", "offsim.engines"],        # L5 reads report.json + trajectories only
    "L2 simulate": ["requests", "urllib", "urllib3", "http.client", "httpx", "aiohttp", "offsim.feed"],   # engines never fetch
}

SKIP_DIRS = {"node_modules", "__pycache__"}


def py_files(rel: str):
    path = ROOT / rel
    if path.is_file():
        yield path
    else:
        for f in sorted(path.rglob("*.py")):
            if not SKIP_DIRS & set(f.relative_to(ROOT).parts):
                yield f


def module_name(path: Path) -> str:
    parts = list(path.relative_to(ROOT).with_suffix("").parts)
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def imported_modules(source: str, this_module: str, is_package: bool = False) -> set[str]:
    """Absolute dotted names imported by `source` (every `import x` and `from x import y` -> x and x.y)."""
    out: set[str] = set()
    base = this_module.split(".") if is_package else this_module.split(".")[:-1]
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                anchor = base[: len(base) - (node.level - 1)] if node.level > 1 else base
                mod = ".".join(anchor + ([node.module] if node.module else []))
            else:
                mod = node.module or ""
            if mod:
                out.add(mod)
                out |= {f"{mod}.{a.name}" for a in node.names if a.name != "*"}
    return out


def violations(source: str, this_module: str, forbidden: list[str], is_package: bool = False) -> list[str]:
    hits = []
    for m in sorted(imported_modules(source, this_module, is_package)):
        for f in forbidden:
            if m == f or m.startswith(f + "."):
                hits.append(f"{m} (forbidden: {f})")
                break
    return hits


def test_layer_map_points_at_real_code():
    for layer, paths in LAYERS.items():
        for rel in paths:
            assert (ROOT / rel).exists(), f"{layer}: {rel} does not exist; update LAYERS"
    assert sum(1 for _ in py_files("offsim/engines")) >= 4          # base, __init__, replay_engine, openclsim_adapter


@pytest.mark.parametrize("layer", sorted(FORBIDDEN))
def test_layer_does_not_import_forbidden_modules(layer):
    bad = []
    for rel in LAYERS[layer]:
        for f in py_files(rel):
            for v in violations(f.read_text(), module_name(f), FORBIDDEN[layer], f.name == "__init__.py"):
                bad.append(f"{f.relative_to(ROOT)}: {v}")
    assert not bad, f"{layer} import rule broken:\n  " + "\n  ".join(bad)


def test_checker_catches_what_it_should():
    """The rule checker itself: absolute, from-, relative and function-local imports are all seen."""
    f = FORBIDDEN["L5 present"]
    assert violations("import offsim.solve.pyvrp_adapter", "offsim.scene", f)
    assert violations("from offsim.engines import get_engine", "offsim.scene", f)
    assert violations("from offsim import solve", "offsim.scene", f)                        # from-import of a package
    assert violations("from ..solve import x", "offsim.cinema.camera", f)                    # relative, one level up
    assert violations("from . import y\ndef g():\n    import offsim.engines.base", "offsim.motion.story", f)
    assert not violations("from offsim.contract import kpis\nfrom .rules import R", "offsim.cinema.camera", f)
    e = FORBIDDEN["L2 simulate"]
    assert violations("import requests", "offsim.engines.x", e)
    assert violations("from urllib.request import urlopen", "offsim.engines.x", e)
    assert violations("from offsim.feed import rss", "offsim.engines.x", e)
    assert not violations("import pandas, simpy\nfrom offsim.contract import kpis", "offsim.engines.x", e)
