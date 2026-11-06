"""Repo structure: catalog valid and rendered, skills well-formed, router points at real skills."""
import json
import re

import yaml

from conftest import ROOT
import catalog_build


def test_catalog_is_valid_and_docs_are_current():
    cat = catalog_build.load()
    assert catalog_build.problems(cat) == []
    assert len(cat["tools"]) >= 40
    assert (ROOT / "docs/TOOLS.md").read_text() == catalog_build.render(cat), "run: python tools/catalog_build.py"


def test_core_tools_are_tested_with_evidence():
    tools = {t["id"]: t for t in catalog_build.load()["tools"]}
    for i in ("pyvrp", "simpy", "deckgl", "opt-model"):
        assert tools[i]["status"] == "tested" and tools[i].get("evidence"), i   # evidence paths are checked in problems()


def frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    return yaml.safe_load(m.group(1)) if m else None


def test_skills_have_frontmatter_named_like_their_folder():
    skills = sorted((ROOT / "skills").glob("*/SKILL.md"))
    assert len(skills) >= 6
    for s in skills:
        fm = frontmatter(s.read_text())
        assert fm and fm["name"] == s.parent.name and len(fm["description"]) > 60, s


def test_router_points_only_at_existing_skills():
    text = (ROOT / "skills/offsim-foundations/SKILL.md").read_text()
    named = set(re.findall(r"`([a-z][a-z0-9-]+)`", text)) & {p.name for p in (ROOT / "skills").iterdir()}
    assert {"paper-extract", "sim-corrector", "visual-director", "sim-narrator", "opt-model"} <= named


def test_plugin_manifest():
    m = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())
    assert m["name"] == "offshore-simulations" and m["version"]


def test_spec_modules_document_every_function():
    """The four visual layers are built (camera, vessel, weather, depth). Every public function keeps its contract
    docstring; any function still unbuilt must raise NotImplementedError rather than return a silent stub."""
    import inspect

    from offsim.cinema import camera, look, vessel
    from offsim.weather import fetch, visual
    from offsim.worlds import depth
    for mod in (camera, vessel, look, fetch, visual, depth):
        for n, f in inspect.getmembers(mod, inspect.isfunction):
            if f.__module__ == mod.__name__ and not n.startswith("_"):
                assert (f.__doc__ or "").strip(), f"{mod.__name__}.{n} has no contract"


def test_rules_and_sourced_weather_bands():
    from offsim.cinema.rules import CAMERA, VESSEL
    from offsim.weather.operability import psv_effect
    assert CAMERA["zoom_rate_max"] <= 0.35 and CAMERA["shot_min_s"] >= 2.5 and VESSEL["display_offset_max_m"] <= 25
    assert psv_effect(2.0)["service_factor"] == 1.0 and psv_effect(4.0)["speed_delta_kn"] == -2.0 and psv_effect(5.0)["wow"]
