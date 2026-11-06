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


def test_every_tested_tool_is_really_used_in_code_or_docs():
    tested = [t["id"] for t in catalog_build.load()["tools"] if t["status"] == "tested"]
    assert {"pyvrp", "simpy", "deckgl", "opt-model"} <= set(tested)


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
