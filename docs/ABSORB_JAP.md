# Absorbing the Junior Architect Pipeline (J1)

Source: Abhinav Bhardwaj, *Junior Architect Pipeline* v2.0.0 (`junior-architect/`, MIT, JavaScript), read only. Its 45
architecture tasks are out of scope and nothing of them is copied. What transfers is the **method**: a checker recomputes from
raw outputs and is trusted only after it has been shown a **seeded fault** and reported exactly that fault; a registry says,
per task, which checker guards it and how it can fail.

**Provenance.** Ideas only. No code, fixture or text was copied from the repository; the tests and fixtures here are our own
Python and YAML. If anything is ever copied, `THIRD_PARTY_NOTICES.md` must carry `Copyright (c) 2026 Abhinav Bhardwaj` and the
MIT licence text, with a comment at the copied site (see the J1 brief). The file does not exist yet because nothing needs it.

Paths in the first column are inside `junior-architect/` of THEIRS. Their `junior-architect/CLAUDE.md` does not exist in the
v2.0.0 tree (the context layer is `.jap/project.json`, created by `jap.js init`).

| Their file | What it does | Our nearest equivalent | Verdict | Reason |
|---|---|---|---|---|
| `tests/examples.test.js` + `examples/` | Runs each of 20 checkers on a folder holding seeded faults; expects a named list of issue codes per checker | `tests/test_seeded_faults.py`, `tests/fixtures/seeded/` (new); `tests/test_visual_gate.py` already does it per visual rule | **absorb** | The core idea. Ours is stricter: theirs fails only when an expected code is *missing* (extras are printed, `also:`), ours asserts the gate fails and reports exactly that fault and a clean twin passes |
| `scripts/jap.js` `check` + report shape `{status, errors, warnings, issues[{level, code, item, detail}]}` | One report per run, each issue with a stable code, the item and a detail | `report["gates"][g]` with `code` (`offsim/doctor/codes.py`) and `detail` | **adapt** | We already have stable codes. What we lacked was the *item level*: gate 1 now returns `detail.faults` (`not_served`, `served_twice`, `over_capacity`, `too_many_routes`, `time_window`) naming each offender |
| `scripts/jap.js` issue `level` (error / warn) | Warnings never fail a run | none (gates are pass/fail and stop the run); `whelp.check_program` reports idle gaps without failing | **drop** | A gate that warns is a gate that can be ignored; our rule is stop at the first failure |
| `scripts/lib.js` (`collector`, `load`, unit helpers) | Plumbing for checkers | `offsim/contract.py`, `offsim/doctor/codes.py` | **drop** | Trivial; we have the equivalents |
| `scripts/checks/design.js` `check_metrics` | Measured metric vs rule list; warns on a rule with no `source` | gate 0 (`provenance_gaps`, `offsim/pipeline.py`) | **drop** | Gate 0 is stricter: an unsourced value fails, it does not warn |
| `scripts/checks/design.js` `check_stairs` | Recomputes 2R+G, pitch, total rise = risers x riser height from raw dimensions | gate 1 (`plan_faults`) and gate 2 recompute from routes and replay | **adapt** (idea only) | "Recompute, never trust the reported number" is already how gates 1 and 2 work; the stair rules themselves are architecture and are dropped |
| `scripts/checks/design.js` `check_panels`, `check_gh`; `documentation.js` `check_views`, `check_annotation`, `check_ifc`, `check_quantities`; `visual.js` `check_board`, `check_clash`; the document checkers in `jap.js` | Area, door, panel, Grasshopper, IFC, board, clash, minutes, spec checks | none | **drop** | Architecture and construction administration |
| `scripts/checks/documentation.js` `check_dxf` | Parses the DXF header and entities itself and checks units, layers, text heights | `offsim/assets/cad/qa.py` (solid vs declared dimensions, QA-ASSET-DIM) | **drop** | The pattern (parse the artefact, do not ask the tool) is already in the CAD QA gate; DXF is not our format |
| `scripts/checks/visual.js` `sunPosition`, `check_render` | NOAA solar equations recomputed to catch a render whose sun is impossible for place and date | none (`offsim/cinema/look.py` grades light by style, not by date) | **drop** (park) | Nothing we render claims a date and place for its light. Revisit if a film shows winter light on a Norwegian coast and says so: the NOAA recomputation, in Python, would be the gate |
| `pipeline.json` per-task `checker` + `check` inputs + `deliverable` | Registry line binding a task to its checker and inputs | `GUARDS.md` (rule to test/gate), `offsim/studio/funnel.yaml` (stage to command and exit check) | **adapt** | `GUARDS.md` now points at the seeded-fault tests. A machine-readable gate registry (gate id, function, inputs, codes, seeded-fault test) is the natural next step and is **not done** here: it touches `pipeline.py` structure beyond the two gate fixes |
| `pipeline.json` per-task `failure_modes` | Plain-language list of how the task goes wrong | `offsim/doctor/playbooks/*.yaml` `symptoms:` | **adapt** | Already ours; this change adds the gate 1 time-window and gate 4 composition symptoms |
| `pipeline.json` `ceiling`, `autonomy_levels` A0-A4 | Cap on how much of a task the agent may do without the junior | `AGENTS.md` roles table, "never push to main", gates before render | **drop** | Designed to train a human junior; our owner is not a trainee. The equivalent control is "a result that failed a gate is never rendered" |
| `pipeline.json` `agent`, `skill`, `hosts`, `capabilities`, `junior_keeps` | Which subagent, skill and software host a task needs, and the human judgement kept | `.claude/agents/`, `skills/`, `catalog/tools.yaml` | **drop** | We have the equivalents; the host/capability vocabulary is for Revit and Rhino |
| `hooks/hooks.json` + `scripts/gate.js` G1 (Claude cannot write the junior's prediction or review) | PreToolUse block | none | **drop** | Human-learning device |
| `gate.js` G2 (only the checker writes `report.json`, run state, log) | PreToolUse block on Write/Edit/Bash redirects into evidence files | none: `out/<id>/report.json` is written by `pipeline.run`, nothing stops an agent editing it | **adapt** (follow-up) | A hook refusing hand edits of `out/**/report.json` would back the rule "never post a result that has not passed". Not built in J1 (hooks are outside its ownership) |
| `gate.js` G3 (prediction before any MCP call at A1/A2) | Forces an estimate before the agent works | `python -m offsim experiment` (pre-registered comparison) | **drop** | We already pre-register where it matters |
| `gate.js` G4 (Stop hook blocks finishing while a deliverable has no checker report) | Stop hook | films refuse failed runs (`tests/test_pipeline_motion.py`); no Stop hook | **adapt** (follow-up) | Cheap guard for sessions that render without a report; not built here |
| `gate.js` G5 (checkers and gates read-only during a run) | Blocks writes under the plugin directory | none | **drop** | Our workflow needs agents to fix gates in a branch; the control is "fix the gate, not the fixture" plus the exit test |
| `prediction.md`, `review.md`, `learning_log.csv`, `jap.js log` | The junior's learning record | `offsim/doctor/lessons.py`, `docs/TESTLOG.md`, `coordination/reports/` | **drop** | Our learning record is the doctor's lessons and the test log |
| `mcp/README.md`, `mcp/cad-bim-servers.example.json` (Rhino and Grasshopper: McNeel Rhino MCP Platform, MIT; Blender: Blender Lab MCP, GPL-3.0) | List of MCP hosts per CAD tool | `AGENTS.md` "MCP servers" (ampl, entur) | **drop** | Our heavy renders run in the `render` workflow, our CAD solids are parametric Python. If Blender is ever driven by an MCP server it is a separate process (GPL rule in `CLAUDE.md`), and the 3D-model work on Molde and Kristiansund is a separate repo |
| `skills/` (24), `agents/` (17), `commands/` (45), `templates/`, `scripts/board.js`, `session-start.js` | Architecture procedures, subagents, slash commands, board layout, session note | `skills/`, `.claude/agents/`, `python -m offsim` | **drop** | Domain content |

## What J1 changed in our gates

Seeded-fault results are in `coordination/reports/J1.md` and `docs/AUDIT.md` (audit 11).

- Gate 1 checks time windows (`offsim.pipeline.plan_faults`): service start must be at most `latest`; arriving early waits. It
  reuses `offsim.solve.pyvrp_adapter.windows_violations`, the function the solvers' own tests use. Failures name each fault in
  `detail.faults`.
- Gate 4 compares the fleet composition (window hours per helicopter) for a WFPPP plan, against `reported.fleet_composition`
  when the scenario lists it and otherwise against the paper's Table 4 in `offsim.solve.whelp.PAPER_RESULT`. No tolerance and no
  sourced value was changed; the committed Florø scenario still passes gates 0 to 4.
- Not changed: the replay's `tw_late` definition (audit 7, risk 2), Bergen's discrepancy itself (audit 8).
