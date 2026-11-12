"""Agents and MCP as repo assets: subagent files, .mcp.json, the AMPL server path, and the AGENTS.md role table."""
import json
import re

import yaml

from conftest import ROOT

AGENTS_DIR = ROOT / ".claude/agents"
MODELS = {"haiku", "sonnet", "opus"}
TOOLS_ALLOWED = {"Read", "Grep", "Glob", "Bash", "Edit", "Write", "WebSearch", "WebFetch"}
ROLES = {"repairer", "corrector", "scout", "extractor", "modeller", "drafter", "director", "writer", "integrator"}
MODEL_OF = {"scout": "haiku", "modeller": "opus", "integrator": "opus"}  # every other role is sonnet
UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
KEY_LIKE = re.compile(r"(api[_-]?key|secret|token|password|bearer\s|sk-[A-Za-z0-9]{8,})", re.I)
ENTUR = "https://api.entur.io/"


def split_frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    assert m, "missing YAML frontmatter"
    return yaml.safe_load(m.group(1)), m.group(2)


def agent_files():
    return sorted(AGENTS_DIR.glob("*.md"))


def test_every_agent_has_valid_frontmatter():
    files = agent_files()
    assert {f.stem for f in files} >= ROLES, "a role from the W5 list has no agent file"
    for f in files:
        fm, _ = split_frontmatter(f.read_text())
        assert fm["name"] == f.stem, f
        assert isinstance(fm.get("description"), str) and len(fm["description"]) > 60, f
        assert re.search(r"\bUse\b", fm["description"]), f"description must say when to use the role: {f}"
        assert fm["model"] in MODELS, f
        tools = {t.strip() for t in fm["tools"].split(",")}
        assert tools and tools <= TOOLS_ALLOWED, (f, tools - TOOLS_ALLOWED)


def test_models_match_the_package_table():
    for role, model in MODEL_OF.items():
        fm, _ = split_frontmatter((AGENTS_DIR / f"{role}.md").read_text())
        assert fm["model"] == model, role
    for role in ROLES - set(MODEL_OF):
        fm, _ = split_frontmatter((AGENTS_DIR / f"{role}.md").read_text())
        assert fm["model"] == "sonnet", role


def test_each_role_names_read_first_owns_exit_test_and_report_rule():
    for f in agent_files():
        _, body = split_frontmatter(f.read_text())
        for heading in ("## Read first", "## Owns", "## Must not touch", "## Exit test"):
            assert heading in body, (f.name, heading)
        assert "AGENTS.md" in body, f.name
        assert "coordination/reports/" in body and "before stopping" in body.lower(), f.name
        assert "Do not commit to main" in body, f.name


def test_mcp_json_parses_and_has_the_three_servers():
    cfg = json.loads((ROOT / ".mcp.json").read_text())
    servers = cfg["mcpServers"]
    assert set(servers) == {"ampl", "entur-journey-planner", "entur-transit-data"}
    ampl = servers["ampl"]
    assert ampl["type"] == "stdio" and ampl["command"] == "python"
    assert ampl["args"] == ["tools/ampl_mcp/server.py"]
    for root in ampl["env"]["AMPL_MCP_ROOTS"].split(":"):
        assert (ROOT / root).is_dir(), f"AMPL_MCP_ROOTS entry missing: {root}"
    for name in ("entur-journey-planner", "entur-transit-data"):
        assert servers[name]["type"] == "http" and servers[name]["url"].startswith(ENTUR), name


def test_mcp_json_holds_no_secret_like_strings():
    raw = (ROOT / ".mcp.json").read_text()
    assert not UUID.search(raw), "UUID-like string in .mcp.json"
    assert not KEY_LIKE.search(raw), "key-like string in .mcp.json"


def test_ampl_server_path_exists():
    assert (ROOT / "tools/ampl_mcp/server.py").is_file()


def test_agents_md_roles_table_lists_every_agent_file():
    text = (ROOT / "AGENTS.md").read_text()
    section = text.split("## Roles", 1)[1].split("\n## ", 1)[0]
    for f in agent_files():
        assert f"`.claude/agents/{f.name}`" in section, f.name


def test_agents_md_has_the_coordination_sections_and_keeps_hard_rules():
    text = (ROOT / "AGENTS.md").read_text()
    for heading in ("## Writers and coordination", "## Roles", "## MCP servers", "## Firing a package"):
        assert heading in text, heading
    assert "**Hard rules**" in text
    assert "Run `python -m pytest -q tests` before every commit" in text
    assert not UUID.search(text), "UUID-like string in AGENTS.md"
