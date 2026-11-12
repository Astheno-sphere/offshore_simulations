# AGENTS.md — for any coding agent (Claude, Qwen, Codex, ...)

Read `CLAUDE.md` first: its rules apply to every agent, not only Claude. Then:

1. **Where things are**: `docs/ARCHITECTURE.md` (layers, interfaces, what runs where), `docs/ENGINES.md` (each solver /
   engine: mapping, assumptions, limits), `docs/STYLE_REFERENCE.md` (the visual grade and the craft rules learned),
   `docs/RESUME.md` (current state + next steps; `python -m offsim resume`), `catalog/tools.yaml` (tools, with evidence).
2. **Reproduce the current film**: `bash tools/reproduce_film.sh` (versions pinned in `constraints.txt`; data pulled
   from the GitHub release, never committed). The film is deterministic: same inputs, same frames.
3. **Hard rules** (the ones agents break most):
   - Never render, narrate or post a result that failed a gate (`offsim run` gates 0, 1, 1b, 2, 3, 3e, 4, 4b, 4c; films refuse failed runs).
   - Every scenario value has a source (page/table) or `assumption: true`; assumptions are printed on screen.
   - On-screen sentences are chosen from measured values (two-pass: measure, then render). Never hand-write a claim.
   - New solver/engine = implement `offsim/engines/base.py` (`Solver` / `Engine`), raise `Unsupported` instead of
     approximating, add tests, add a catalog entry with `evidence:` paths, add its section to `docs/ENGINES.md`.
   - Visual work follows `docs/STYLE_REFERENCE.md` (detail density, three line weights, 2x supersampling, tonal fills,
     real layers only on maps, cinema rate caps in `offsim/cinema/rules.py`).
   - Run `python -m pytest -q tests` before every commit; update `docs/RESUME.md` and `docs/TESTLOG.md`.
4. **Environment limits**: data hosts (Kartverket, Kystverket, MET Norway, Overpass, AMPL downloads) are reached only by
   the GitHub Actions workflows (`fetch-world`, `solve`, `papers`); results come back as releases/artifacts.

## Writers and coordination

Summary of `coordination/README.md`. Git is the channel: no shared chat and no MCP is needed.

- **Writers**: Arshad (owner), Claude (laptop or cloud session; the integrator in the main session), Nordlys (Muse
  agent on a VM, env `venv-studio`), and their subagents.
- **Branches**: work on `agent/<who>/<id>` only. Never push to `main`. One integration branch at a time (currently
  `wip/cad-assets-heli`, merged to `main` via PR #1).
- **Tasks**: a file `coordination/inbox/<to>/<YYYYMMDD>-<id>-<slug>.md` with from, goal, owns, must not touch, exit
  test and branch. Take it by adding `taken: <who> <UTC time>` and pushing.
- **Reports**: when done, write `coordination/reports/<id>.md` (changes, tests with counts, open risks, disagreements),
  push, and move the task file to `coordination/done/`.
- **Integration**: only the integrator edits `docs/RESUME.md` and merges into the integration branch.
- **Tests**: a failing test is fixed in code. A test edit needs a `why:` line in the commit and in the report.
- **Secrets** (the AMPL licence UUID, API keys) never enter files, logs or the coordination channel.

## Roles

Each role is a Claude Code subagent file in `.claude/agents/`. Any other agent takes the same role from the table
by reading its skill and the file. `tests/test_agents.py` checks that this table lists every agent file.

| Role | Agent file | Read first (skill) | Model | Owns |
|---|---|---|---|---|
| repairer | `.claude/agents/repairer.md` | `skills/sim-corrector/SKILL.md` | sonnet | `offsim/doctor/` and its playbooks (auto repairs only) |
| corrector | `.claude/agents/corrector.md` | `skills/sim-corrector/SKILL.md` | sonnet | verdicts only; read-only on scenario values |
| scout | `.claude/agents/scout.md` | `skills/tool-scout/SKILL.md`, `skills/research-scout/SKILL.md` | haiku | `catalog/tools.yaml`, `docs/TOOLS.md` (rebuilt) |
| extractor | `.claude/agents/extractor.md` | `skills/paper-extract/SKILL.md` | sonnet | `offsim/papers/<id>/` scenario, timetable, notes |
| modeller | `.claude/agents/modeller.md` | `skills/opt-model/SKILL.md`, `skills/sim-engineer/SKILL.md` | opus | new problem classes; solver and engine adapters |
| drafter | `.claude/agents/drafter.md` | none (`docs/VISUAL_SPEC.md`) | sonnet | `offsim/assets/cad/` to QA pass |
| director | `.claude/agents/director.md` | `skills/visual-director/SKILL.md` | sonnet | `storyboard.yaml`; visual gate |
| writer | `.claude/agents/writer.md` | `skills/sim-narrator/SKILL.md` | sonnet | article and post text from report refs |
| integrator | `.claude/agents/integrator.md` | `skills/offsim-foundations/SKILL.md` | opus | merges; `docs/RESUME.md` (only editor) |

## MCP servers

Project config: `.mcp.json` (no secrets in it). Claude Code asks for approval the first time it loads these servers.

| Server | Transport | Gives | Runs where |
|---|---|---|---|
| `ampl` | stdio: `python tools/ampl_mcp/server.py` | `solve_model`, `get_variable`, `get_duals`, `run_ampl`, `list_models` over a local AMPL session | laptop only. Needs `amplpy`, `mcp`, a local AMPL install, and the academic licence entered in the terminal (never in a file). Roots: `offsim/solve/ampl` and `offsim/papers`, colon-separated. Not in the Claude workspace. |
| `entur-journey-planner` | http `https://api.entur.io/journey-planner-mcp/v1/mcp` | trip planning, departures, stop lookup (no auth) | any session with internet access. The Claude workspace cannot reach `api.entur.io`. Credit "Source: Entur AS". |
| `entur-transit-data` | http `https://api.entur.io/transit-data/v1beta/mcp` | transit data and NeTEx lookups (beta) | same as above |

If Entur rejects a call for a missing `ET-Client-Name` header, add the header in your own local Claude settings with a
generic `<company>-<application>` value. Do not add it to `.mcp.json`.

## Firing a package

Claude Code, main session: launch one background agent per package, in one message. Use the role name as
`subagent_type` when the role has an agent file, otherwise `general-purpose`:

```
Agent(subagent_type="<role>", run_in_background=true,
      description="<W-id> <name>",
      prompt="Repo <repo root>. Read AGENTS.md and docs/SYSTEM_PLAN.md section <3.x/4/5> for <W-id>. You own only:
              <owns>. Do not touch: <must not touch>. Do not commit to main. Exit test: <exit test>.
              Write coordination/reports/<W-id>.md before stopping. Run python -m pytest -q tests at the end.")
```

Any other agent (Qwen, Codex, Nordlys): take a task file from `coordination/inbox/<to>/` (see Writers and coordination),
add the `taken:` line, branch `agent/<role>/<W-id>`, work to the same exit test, and write the report to
`coordination/reports/<W-id>.md`.
