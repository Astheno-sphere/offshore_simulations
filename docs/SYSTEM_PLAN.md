# SYSTEM_PLAN: from a toolbox to a machine

Written 2026-11-11 after reading the repo state (main 03f174f, wip/cad-assets-heli 6341c2c, papers/auto 0c451c6,
PR #1 open). This is a plan, not a build. Nothing here has been executed. Read with `docs/AUDIT.md` (audit 5).

## 0. Verdict

We built organs, not an organism. Every part exists (solvers, engines, gates, feed, intake, CAD, physics, films)
and most parts are tested alone. What is missing is the nervous system: nothing carries a paper from feed to
article as one tracked job, nothing diagnoses a failed gate, nothing stops docs, skills and code from drifting
apart, and nothing proves the outside world (data hosts, AMPL, CI runners) still answers.

## 1. Measured state (facts, 2026-11-11)

| Area | Fact | Evidence |
|---|---|---|
| Branches | Three truths: main (green), wip (PR #1, 449 pass locally, CI red), papers/auto (unmerged data) | `gh api .../branches` |
| CI on wip | Red 8 times, fails in `apt-get install libegl1 ...` (index download), never reaches pytest | run logs |
| Gap finder | DID fire live on 2026-11-09: 712 papers (crossref 563, nva 93, arxiv 56), 26 gaps. Result stranded on papers/auto because Actions may not open PRs | papers run log |
| Gap quality | 18 of 26 gaps are `no-code` (noise: abstracts rarely mention code). HRP gaps suggest engine `replay`, but the helicopter engine is `air`. One record dated 2027 | papers/gaps.yaml |
| OpenAlex | 0 records: HTTP 429 from Actions and from the VM. Our best source is dead | TESTLOG 2026-11-11 |
| Workflows never run | solve (AMPL), entur-realtime, render, film. fetch-world not re-run since the timeout fix | Actions history |
| Releases | Only world-oslofjord. No Bergen data, no weather, no DEM, no AIS | releases |
| Tests changed, not code | 5 failures closed by editing tests. Premises were wrong, so mostly right, but it exposed a model gap (see 2.6) | commits 9268d3e..996fce0 |
| CAD QA | pass: psv, bus, train, person. fail: s92 and aw189 (rotor 20 %, fuselage 30 %, width 340 % off), platform_jacket, tree, building (dims missing) | TESTLOG, registry.yaml |
| Unabsorbed deps | Declared, never imported: build123d, datashader, gtfs-kit, osmnx, phiflow, taichi, pyvista, r5py, xarray-spatial, pypdf | requirements*.txt vs imports |
| Spec stubs | emissions, motion/diptych, weather/operability parts, osm overture, parts of weather/fetch | `raise NotImplementedError` |
| Catalog | 159 tools: 55 candidate, 46 watch, 33 tested, 13 wired, 8 installed. Two thirds is shelfware | catalog/tools.yaml |
| Agents | No `.claude/agents/`, no `.mcp.json`. Subagents and MCP servers exist only as chat habits | repo tree |
| Output | No article generator. The goal says "LinkedIn articles and videos"; only video exists | CLI |

## 2. Flaws, named

1. **No conductor.** `offsim run` handles one scenario. Nothing owns the journey feed -> gap -> reproduce ->
   experiment -> findings -> article + film -> publish. The journey lives in skill prose and in chat memory.
2. **Gates judge but do not diagnose.** A failure is a free-text string. No error codes, no playbook, no repair
   attempt, no record of what was tried. Every failure costs a fresh investigation (and tokens).
3. **No concordance.** Docs, skills, catalog, registry and CLI are five hand-kept copies of the truth. Proven drift:
   gap finder maps HRP to `replay`; CLAUDE.md still says agents render as sprites; RESUME carries a line about a
   "main tree sprite sheet" that is not in this repo; skills cite flags nobody verified.
4. **The outside world is unproven.** Offline fixtures pass, live hosts were never called, or failed silently
   (OpenAlex 429, fetch-world timeout, papers PR permission, apt on the new runner image).
5. **Learning is not captured.** Lessons sit in TESTLOG prose. Nothing turns a lesson into a guard test or a
   playbook entry, so the machine does not get harder to break.
6. **Simulation depth.** Recovery policy in the air engine is a single rule (rebook into free slots this week);
   the optimal program has almost no slack, so the experiment's answer is decided by an unmodelled choice
   (overtime, weekend flights, carry-over, spare helicopter). Also: no benchmark validation for the fluid solver,
   gate 4 compares one run instead of ensemble medians, ensemble reports keep quantiles but not runs, no cost or
   emissions model, weather limits unsourced, Stavanger and Bergen never solved in CI (skipped as slow).
7. **Visual chain is unstitched.** (Correction from Nordlys, 2026-11-12: section.py v7 to v10 on his VM already draws
   with skia and CAD HLR; it is uncommitted. Task N1 brings it in. The text below describes the repo as committed.) CAD solids -> HLR drawings exist. skia Canvas exists. Inter exists. Hillshade and
   sun() exist. The films use none of them (section.py still draws `vessel_lineart` with PIL). No visual gate
   (density, type scale, contrast, golden frames), so quality is judged by eye in chat.
8. **Intake is shallow.** pdfplumber glues words and misses unruled tables; the helicopter paper's appendix was
   read by hand. No table reader, no GROBID, no structured equations.
9. **Gap finder is a counter, not a scout.** No ranking, no dedupe, no feasibility check against what our engines
   and data can do, no human review file (gaps.yaml is overwritten weekly), no path from gap to experiment draft.
10. **Coordination.** Several agents now touch the repo (this one, "Nordlys", CI bot). No protocol for who owns
    which branch, no lock, reports get lost when an agent is stopped (marine/air report was lost).
11. **Tool absorption has no exit.** Tools enter the catalog and stay candidates forever. No rule that forces
    "wire it or drop it", no weekly budget.
12. **Drift of purpose.** We repeatedly slid from building the machine into making one frame or one place
    (Molde, concept stills). The plan below has a rule against it (section 7).

## 3. Target architecture: five additions

```
                       +----------------------- CONDUCTOR (offsim/studio) -----------------------+
 feed -> triage -> gap -> paper intake -> scenario -> run(gates) -> experiment -> findings -> article + film -> publish
   |        |       |          |             |            |              |            |             |
   +--------+-------+----------+-------------+-----+------+--------------+------------+-------------+
                                                    |
        DOCTOR (diagnose, repair, learn)   CONCORDANCE (drift guards)   LIVE-CHECK (outside world)   AGENTS (.claude)
```

### 3.1 Conductor: `offsim/studio/`
- `funnel.yaml`: the stages as data. Each stage: entry criteria, command, artefacts, exit gate, owner skill, model tier.
- `ledger`: one `offsim/papers/<id>/state.json` per paper: stage, artefact hashes, gate results, blockers with
  error codes, attempts, next action. Append-only history. This is the resume function at paper level.
- CLI: `offsim status` (board of all papers by stage), `offsim next <id>` (print or run the next step),
  `offsim advance <id>` (run until a gate stops or a human decision is needed).
- Human decisions are explicit stage types (`decide:`), e.g. gap choice, assumption sign-off, publish.

### 3.2 Doctor: `offsim/doctor/`
- `codes.py`: every gate failure and tool error gets a stable code, e.g. `G0-SRC-MISSING`, `G0-TOOL-UNAVAILABLE`,
  `G1-PLAN-INFEASIBLE`, `G2-REPLAY-DRIFT`, `G3-SPEED`, `G3-LAND-CROSSING`, `G3E-ENSEMBLE`, `G4-KPI-MISMATCH`,
  `G4B-AIS`, `G4C-ENTUR`, `DATA-HOST-TIMEOUT`, `DATA-SCHEMA`, `CI-ENV`, `QA-ASSET-DIM`, `VIS-DENSITY`.
- `playbooks/<code>.yaml`: symptoms, ordered checks (each a callable returning evidence), repairs tagged
  `auto` (safe, deterministic: refetch, widen snap radius within limit, switch solver seed, rebuild cache) or
  `human` (touches a sourced value, an assumption or a tolerance). Auto repairs never change a number that is on screen.
- `offsim doctor <report.json | id>`: classify -> run checks -> apply auto repairs (max 2 attempts) -> rerun the gate
  -> write `diagnosis.json` + a ledger entry. If still failing: one clear question for the human.
- `lessons.jsonl` + `offsim learn`: each resolved failure records symptom, root cause, fix, and the guard test added.
  Rule: a lesson is not closed until a test or a playbook check exists for it.

### 3.3 Concordance: `tests/test_concordance.py` (the whip)
Fails CI when the copies of truth disagree. Sketch:

```python
def test_cli_commands_in_skills_exist():        # every `offsim <cmd>` in skills/*.md and docs is a real subcommand
def test_engines_doc_matches_registry():        # docs/ENGINES.md tables == ENGINE_MODULES / SOLVER_MODULES keys
def test_gap_engines_are_registered():          # research.gaps suggested engine covers the class (HRP -> air)
def test_requirements_are_imported_or_listed(): # every pinned package is imported, or in catalog as installed/watch
def test_spec_stubs_are_listed():               # every NotImplementedError module appears in docs/ROADMAP.md
def test_funnel_stage_commands_exist():         # funnel.yaml commands resolve; each stage has an owner skill file
def test_workflow_inputs_match_docs():          # inputs named in RESUME/skills exist in the workflow YAML
def test_resume_mentions_only_repo_paths():     # paths cited in docs/RESUME.md exist (kills the sprite-sheet line)
def test_agents_md_rules_have_guards():         # each hard rule in AGENTS.md names the test that enforces it
def test_no_test_weakening():                   # a diff that edits an assert must touch docs/LESSONS or carry "why:" 
```

### 3.4 Live-check: `.github/workflows/live-check.yml` + `offsim/live/`
- One tiny probe per external dependency (2 min budget each, small bbox, one record): Overpass, Sodir, NORA3 wind,
  NORA3 wave, NorKyst, Kartverket DTM, stedsnavn, Geofabrik HEAD, Entur GTFS HEAD, Entur vehicles, BarentsWatch,
  OpenAlex, Crossref, arXiv, NVA, AMPL activate + 1 solve, apt packages on the current runner image.
- Output `docs/LIVE_STATUS.md` + `live_status.json` (ok, latency, schema hash, last ok date). Weekly cron + manual.
- A changed schema hash opens an issue with the diff. `live_checked` flags in code read this file.
- Known first fixes it will force: OpenAlex polite pool (`mailto`, backoff, or API key secret), papers PR permission
  (or commit to a data branch + issue instead of a PR), apt retry on the runner, fetch-world rerun.

### 3.5 Agents and MCP as repo assets
- `.claude/agents/`: `repairer` (sonnet: owns doctor playbooks), `corrector` (sonnet: gates, never edits values),
  `scout` (haiku: feed, tags, tool absorption), `extractor` (sonnet: paper -> scenario with page refs),
  `modeller` (opus/fable: new problem classes, AMPL + Pyomo twins), `drafter` (sonnet: CAD assets to QA pass),
  `director` (sonnet: storyboard, visual gate), `writer` (sonnet: article from report refs), `integrator`
  (opus/fable: merges, concordance, RESUME). Each file: tools allowed, files owned, exit tests.
- `.mcp.json`: `ampl` (tools/ampl_mcp, laptop), Entur Journey Planner MCP, Entur Transit Data MCP. Optional later:
  a read-only `offsim` MCP exposing status, ledger and reports so any client can drive the machine.
- Coordination protocol in AGENTS.md: one integration branch at a time, agents work in `agent/<role>/<task>`
  branches, every agent writes `coordination/reports/<task>.md` before it exits (reports can no longer be lost),
  RESUME is edited only by the integrator.

## 4. Depth work the machine needs (after section 3 exists)

| Track | Items |
|---|---|
| Simulation | Recovery policies as data (overtime, weekend, carry-over, spare) for `air`; benchmark suite (`tests/bench/`: Ghia cavity, AMPL = Pyomo = HiGHS on WFPPP small, OpenCLSim = replay); gate 4 on ensemble medians; ensemble keeps runs (parquet); cost + emissions built; sourced operability limits; Stavanger and Bergen solved on Actions with AMPL |
| Intake | Word-gap fix (pdfplumber tolerances), unruled table reader, GROBID service on Actions, equation capture; verify Docling licence and try it as the structured reader |
| Gap scout | Drop `no-code` unless full text checked; rank = support x novelty x feasibility (class registered, data pulled) x audience; `papers/review.yaml` (human, never overwritten); `offsim gap draft <gap_id>` -> experiment.yaml skeleton; OpenAlex restored; date sanity |
| Visual | Films draw CAD drawings through skia (retire `vessel_lineart`); hillshade + sun() in map panel; visual gate (edge density, type scale, contrast, palette, safe margins) + golden frames; s92/aw189 rebuilt to QA pass; registry status computed, never hand-set |
| Output | `offsim article <id>`: markdown + figures from `report:` refs with the same narration rules, LinkedIn length presets, methods box, assumptions list; publish stage (muse.ai upload, article export) |
| Tools | Absorb-or-drop sweep: wire taichi backend or drop; datashader for AIS density; xarray-spatial into terrain_tint; osmnx stats or drop; r5py on Actions or drop; OR-Tools CP-SAT for sync classes; OpenTNSim, SUMO as engines only when a paper needs them |

## 5. Plan of action

Order matters: P0 makes the ground solid, P1 builds the nervous system, P2 to P4 are depth. One wave at a time;
the integrator merges and runs the full suite between waves. No studies, no frames, until P1 is merged.

| Wave | Work package | Model | Owns | Exit test |
|---|---|---|---|---|
| P0 | W0 unblock: apt retry in tests.yml, merge PR #1, merge papers/auto as data, papers workflow without PR creation, RESUME cleanup | integrator (main session) | workflows, RESUME | CI green on main with wip merged |
| P1 | W1 concordance tests + fix every drift they find | sonnet | tests/test_concordance.py, docs, skills | new tests green |
| P1 | W2 conductor: funnel.yaml, ledger, status/next/advance | sonnet | offsim/studio/, __main__ | demo paper walks all stages in a test |
| P1 | W3 doctor: codes, playbooks, doctor/learn CLI, pipeline emits codes | sonnet | offsim/doctor/, pipeline (codes only) | each code has a test that triggers and classifies it |
| P1 | W4 live-check workflow + probes + LIVE_STATUS | haiku | offsim/live/, workflow | probes pass offline with fixtures; workflow dispatchable |
| P1 | W5 agents + MCP: .claude/agents, .mcp.json, coordination protocol | haiku | .claude/, .mcp.json, AGENTS.md | frontmatter valid; concordance covers them |
| P2 | W6 gap scout upgrade | sonnet | offsim/research, offsim/feed | ranking test on the live 712-paper set |
| P2 | W7 intake depth | sonnet | offsim/intake | helicopter paper: appendix tables A1 to A3 extracted with pages |
| P2 | W8 article generator + publish stage | sonnet | offsim/publish, offsim/motion/narrate reuse | article from demo report, all numbers resolve to refs |
| P3 | W9 simulation depth (recovery policies, benches, ensemble runs, gate 4 medians) | fable/opus | engines/air_engine, montecarlo, tests/bench | benches green; policy is a scenario key |
| P3 | W10 cost + emissions + operability sources | sonnet | offsim/emissions, weather/operability | sourced defaults, omitted when unsourced |
| P4 | W11 visual chain: CAD -> skia in films, visual gate, golden frames | sonnet | motion/section, mappanel, cinema | visual gate in story.check; goldens stable |
| P4 | W12 asset repair: s92, aw189, jacket, tree, building to QA pass | sonnet | assets/cad | registry computed, all nine qa-pass |
| P5 | W13 absorb-or-drop sweep + weekly tool-scout workflow | haiku | catalog, requirements | no declared-never-imported package left |

### Firing commands
Say the wave or package ids ("fire W1 W2 W3"). The main session then launches, in one message, one background
agent per package with this template (Claude Code Agent tool):

```
Agent(subagent_type="general-purpose", model="<model from table>", run_in_background=true,
      description="<W-id> <name>",
      prompt="Repo /home/claude/offshore_simulations. Read AGENTS.md and docs/SYSTEM_PLAN.md section <3.x/4> for
              <W-id>. You own only: <Owns>. Do not commit or push. Exit test: <Exit test>. Write your report to
              coordination/reports/<W-id>.md before you stop. Run python -m pytest -q tests at the end.")
```

After W5 lands, the same is a one-liner per role: `Agent(subagent_type="repairer", ...)` etc.
Other agents (Qwen, Codex): read AGENTS.md, take one package, branch `agent/<role>/<W-id>`, same exit test.

## 6. Decisions needed from Arshad (blocking P0)
1. Merge PR #1 after the apt fix? (recommended: yes, wip is 449 pass locally)
2. Papers workflow: allow Actions to create PRs (Settings, Actions, General), or switch to "push data branch + open issue" (recommended, no setting needed).
3. The "main tree sprite sheet" mentioned in RESUME: where does it live? It is not in this repo. Bring it in or drop the line.
4. Who is Nordlys and which environment is `venv-studio`? The protocol in 3.5 needs to know every writer.
5. OpenAlex: add a contact email as repo variable `OFFSIM_MAILTO` (polite pool) or an API key secret.
6. AMPL: secret `AMPL_LICENSE_UUID` on GitHub, and the laptop MCP (tools/ampl_mcp/README.md).

## 7. Whip rules (anti-drift, enforced by the integrator and by concordance tests)
- Machine before artefact: no still, film, place-specific world or study while a P1 package is open.
- A failing test is fixed in code, or the test edit carries a `why:` line and a LESSONS entry.
- No tool enters requirements without an import and a test in the same change.
- No number, sentence or asset on screen without a report ref, a narration rule or a QA pass.
- Every agent leaves a report file; every session ends with RESUME updated by the integrator only.
- One integration branch. Data branches (papers/auto) merge weekly or are reported stale by `offsim status`.
