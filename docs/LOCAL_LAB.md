# Local lab: AMPL + offsim on the owner's Windows machine

Status: **BUILDING.** `<LAB>` = `E:\OffsimLab` (owner, 2026-11-15). L0, L1, L3 done; L4 wired; L2, L5, L6 open.
Resume: read this file, then continue at the first unchecked step in "Build order".

## Facts verified 2026-11-15 (on the machine, not assumed)

- AMPL 20260809 at `%USERPROFILE%\AMPL`, GUI `amplide\amplide.exe` present. Licence file `%USERPROFILE%\AMPL\ampl.lic`
  (AMPL for Academics, expires 2027-11-13, updated 2026-11-15) already activates the trial solvers.
- Solvers that solved a test model through amplpy: highs, gurobi, cplex, copt, cbc, xpress, mosek, scip, gcg,
  knitro, baron, conopt, ipopt, bonmin, couenne, octeract, lindoglobal, snopt, minos, lgo, loqo.
  gecode works but takes integer/constraint programming models only, no continuous variables.
- `%USERPROFILE%\Downloads\ampl.lic` (2026-11-13) is an OLDER copy, differs from the installed one. Keep as backup, never commit.
- System Python 3.14 has amplpy 0.18 + mcp, but no pyvrp etc. Miniconda (Python 3.13) exists. CI/Docker use Python 3.12.
- Disk: one physical HDD split into C: (462 GB, 241 free), D: (25), E: (406, 163 free), F: (38). OneDrive present.
- The AMPL licence UUID is NOT needed locally (the licence file is active). It is needed only as GitHub secret
  `AMPL_LICENSE_UUID` (Actions + Codespaces), set by the owner in Settings. Never in chat, never in git.

## Rules

1. One home: every local file of this work lives under `<LAB>` (L0). Nothing in Downloads.
2. Git is the online truth. `<LAB>\repo\offshore_simulations` is the clone; push = backup and sharing.
3. Data and run outputs never enter git (`<LAB>\data`, `<LAB>\runs`).
4. Secrets: licence stays where AMPL put it. No UUID, key or password in any file under `<LAB>` or in chat.
5. One Python env for the lab: conda env `offsim`, Python 3.12 (same as CI). System Python is not used.
6. GUI first: double-click launchers on the desktop; Claude sits beside it through the `ampl` MCP server.
7. Every launcher is a plain `.bat` readable in Notepad. No hidden magic.

## Target layout

```
<LAB>\
  00_START_HERE.md          what each folder is, how to launch, how to resume
  launch\
    AMPL IDE.lnk            the official AMPL GUI (editor + console + solver output)
    AMPL Console.bat        ampl.exe prompt, solver list printed on start
    Solve This.bat          drag a .run/.mod onto it -> solves, writes log to runs\
    AMPL Studio.bat         local web GUI (Streamlit): pick model, data, solver, see results
    Offsim Shell.bat        conda env offsim, cwd = repo, prints `python -m offsim resume`
  repo\offshore_simulations git clone (moved from Downloads)
  models\                   scratch AMPL work: vrp\ heli\ psv\ transit\ teaching\
  notebooks\                AMPL MO-book / Colab examples, own experiments
  runs\                     solve logs and outputs, dated, not in git
  data\                     worlds, NORA3, AIS, not in git
  env\offsim.yml            exported conda env, rebuildable
```

Desktop gets one folder shortcut `Offsim Lab` -> `<LAB>\launch`.

## Online side (unchanged, already built)

GitHub repo + Actions `solve.yml` (needs `AMPL_LICENSE_UUID` secret) + Codespace from `ghcr.io/astheno-sphere/offsim`.
Local and online share the same repo; models written in `<LAB>\models` graduate into `repo\offsim\solve\ampl\` when they
become part of the pipeline.

## Build order (agents, cheapest model that can do it)

| id | step | owner | needs |
|---|---|---|---|
| L0 | owner picks `<LAB>` drive | owner | - |
| L1 | folder skeleton, 00_START_HERE.md, `.bat` launchers, `.lnk` shortcuts, desktop folder | Haiku agent | L0 |
| L2 | conda env `offsim` (py3.12) from requirements*.txt + amplpy modules; full test suite; export env\offsim.yml | Sonnet agent | L0 |
| L3 | AMPL Studio: `repo\tools\ampl_studio\app.py` (Streamlit; model/data picker, 21-solver dropdown, options, log, variable tables, export CSV), tests | Sonnet agent | - (parallel with L2) |
| L4 | move repo clone from Downloads to `<LAB>\repo`; point Claude desktop + `.mcp.json` ampl server at absolute path; verify MCP handshake | Claude (orchestrator) | L1 |
| L5 | smoke test: each launcher once, Studio solves the toy LP with 3 solvers, MCP `list_solvers` from Claude | Claude | L1-L4 |
| L6 | log result in docs/TESTLOG.md, update this file's status, commit (push when owner says) | Claude | L5 |

## State log

- 2026-11-15: facts verified, plan written. Local main = origin/main fb565aa + 4 AMPL commits, not pushed.
  Branch `local/ampl-backend` holds the older local MCP server rewrite (not merged on purpose).
- 2026-11-15: lab at E:\OffsimLab. Repo cloned to `E:\OffsimLab\repo\offshore_simulations` (the Downloads clone is now
  the old copy; delete only after the owner agrees). L1: launchers + `AMPL IDE.lnk` + desktop `Offsim Lab.lnk`;
  `Solve This.bat` on models\teaching\toy.run -> 11 on highs, gurobi, knitro, baron. L3: `tools/ampl_studio/`
  (Streamlit) + tests, no new failures. MCP server: solver list widened by env `AMPL_MCP_SOLVERS` (default stays
  highs,cbc), per-solver time-limit keys from a probe, Windows split of the POSIX root list; 2 tests added.
  User env `AMPL_MCP_SOLVERS` set; Claude desktop config gets an `ampl` entry (backup `claude_desktop_config.json.bak-20261115`).
  Known Windows-only test failures, pre-existing: pyvrp missing under system Python 3.14 (3), two concordance docs
  drifts, test_architecture reads files as cp1252 (set PYTHONUTF8=1).
- 2026-11-15 (late): L2 env offsim py3.12 built (866 pass, 20 fail, mostly Windows paths/encoding/POSIX; list in E:\OffsimLab\runs\L2_report.md). First real AMPL run of tests/test_ampl.py found an ampl_adapter bug (amplpy 0.18 to_pandas index shape); fixed, 34 pass 1 skip. Pushed to agent/desktop/D1-ampl-link. NEXT: D1 report (coordination/reports/D1.md): CVRP demo vs Pyomo 114643.0 m, whelp Floro vs 9980.4986, MCP config shape; smoke-test AMPL Studio.bat and Offsim Shell.bat.
