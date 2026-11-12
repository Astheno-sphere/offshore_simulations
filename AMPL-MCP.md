# AMPL ↔ Muse via MCP — investigation (research only, 2026-11-09)

**Verdict: yes, it connects — and most of the work is already done.**
The repo already contains its own AMPL MCP server (`tools/ampl_mcp/server.py`), written for
exactly this. It has never run against a real AMPL. The official AMPL MCP server exists too,
but it is a *knowledge* server: it answers AMPL questions, it does not solve models.
Nothing was installed in this round; no licence was used or asked for.

## 1. What the repo has today (verified on disk)

- **Solver:** `offsim/solve/ampl_adapter.py` — AMPL route solver behind the `Solver`
  protocol (class CVRP only, `.mod` at `offsim/solve/ampl/cvrp.mod`). amplpy is imported
  lazily; `ampl_status()` probes in a subprocess. Licence UUIDs never appear in code,
  logs or `plan.json`.
- **MCP server:** `tools/ampl_mcp/server.py` + `README.md` — stdio server, five tools:
  `solve_model` (model + data → status/objective/wall time), `get_variable`,
  `get_duals`, `run_ampl` (statements in the session), `list_models`. Solvers allowlisted
  to `highs` / `cbc` only. Files confined to `AMPL_MCP_ROOTS` (default `~/ampl-models`).
  AMPL text is screened before it runs (no `!` shell escape, no `shell`/`cd`/`remove`/
  `include`/`write`/`read`/`data`/`model`/`reset`, no `>`/`|` redirection). The README is
  explicit: the screen is a guard, not a sandbox — only load models you wrote or trust.
- **Actions route (already built):** `.github/workflows/solve.yml` installs amplpy +
  `highs`/`coin` modules and activates the licence from the repository secret
  `AMPL_LICENSE_UUID`. Needs the secret added by the user; no local install required.
- **Docs:** `catalog/tools.yaml` has `ampl` (status: wired, runs: actions) and `ampl-mcp`
  (status: wired, runs: laptop); `docs/RESUME.md` says "Wired, not run: AMPL …
  every AMPL call [not yet live-checked]". `skills/opt-model/SKILL.md`: Pyomo twin of
  each `.mod` for cross-check; AMPL itself needs a licence (Community Edition on
  registration).

## 2. What is on this VM (verified 2026-11-09, read-only checks)

| Check | Result |
|---|---|
| `amplpy` in venv-studio, venv-geo, venv-finish, venv-scout, venv-kepler | **not installed in any** |
| AMPL binary / `~/.ampl` | **absent** |
| `gurobipy` / Gurobi | **absent** |
| `mcp` package in venv-studio | **2.3.0 present** |
| `ampl_status()` | `(False, "ModuleNotFoundError: No module named 'amplpy'")` |
| `tools/ampl_mcp/server.py` under mcp 2.3.0 | **loads; `list_tools()` returns all five tools** (`solve_model`, `get_variable`, `get_duals`, `run_ampl`, `list_models`). The mcp 1.x `FastMCP` import fails on 2.x as expected; the file's fallback to `MCPServer` is the path that works. |
| `tests/test_ampl.py` | real-solve tests skip without AMPL; screen + fake-AMPL tests exist. |

## 3. What exists on the web (read, not run)

- **Official AMPL MCP Knowledge Server** — https://dev.ampl.com/ai/mcp-server.html,
  remote endpoint `https://mcp-kb.ampl.com/mcp`, OAuth sign-in, tools appear as `ampl_kb`:
  `search_kb` (modes explain / implement / debug / enumerate), `enumerate_kb_section`,
  `get_chunk`, `get_style_guide`, `get_response_guide`, `list_doc_areas`, `rate_response`.
  **Execution boundary, in AMPL's own words: "The server supplies evidence and guidance.
  It does not execute optimization models."** Useful for writing and debugging `.mod`
  files; it is not a solver connection.
- **Install path (AMPL's own docs):**
  `pip install amplpy` → `python -m amplpy.modules install highs cbc gurobi` →
  `python -m amplpy.modules activate <license-uuid>`. Windows/Linux/macOS, x86_64 + aarch64.
- **Academic licence (AMPL for Academics, A4A)** — free for students/faculty/researchers
  with an academic email; annual revalidation. AMPL's own floating-licence page:
  *"The Academic Community Edition license is limited to each user personally, but it
  lets them use AMPL and solvers on any computer — even on more than one computer — at
  the same time."* It is a cloud licence: it needs internet to renew its lease
  (this VM has internet). **Caveat, from AMPL's own pages: "The license needs to
  occasionally be used from an academic IP address or further information will be
  requested."** This VM is not an academic IP — activation will very likely work, but
  AMPL may ask for more information later. Not a blocker; flag it and move on.
- **Solvers in the academic licence:** Gurobi, CPLEX, Xpress, COPT, Mosek + all
  open-source solvers (HiGHS, CBC, …), 12 months with renewal. So the paper's
  **Gurobi 12.0.1 is covered by his academic licence** — no separate Gurobi licence
  needed. But: the repo's server and adapter allowlist only `highs`/`cbc` today, so
  using Gurobi needs the `gurobi` module installed **and** a small allowlist change
  in `server.py` + `ampl_adapter.py` (a later step, after the first HiGHS solve works).
  The CBC time-limit option is unverified in the repo (README risks).

## 4. The connection path for Muse (this VM)

Three steps, in order. No new invention needed — it follows the Rhino precedent that
already works in this workspace (`~/workspace/custom-skills/rhino-mcp/SKILL.md`,
`~/workspace/custom-connectors/custom.rhino/`).

1. **Install + activate in venv-studio** (needs his approval — it overrides repo
   `AGENTS.md` rule 4, "AMPL downloads only via Actions", the same way the Molde fetch
   did):
   `~/workspace/venvs/venv-studio/bin/python -m pip install amplpy "mcp>=1.2"` →
   `python -m amplpy.modules install highs coin gurobi` →
   `python -m amplpy.modules activate <uuid>`. The UUID goes in the terminal / secure
   capture only — never in chat, a file, or a commit (repo rule, and the UUID is the
   licence). Verify with `ampl_status()` → `(True, "ok")` and one real `cvrp.mod` solve.
2. **Build a `custom.ampl` connector** on the Rhino pattern: a `client.py` under
   `~/workspace/custom-connectors/custom.ampl/` that spawns `tools/ampl_mcp/server.py`
   over stdio and exposes `list-tools` / `call-tool` / `run-script`. One design point
   the Rhino skill already learned: **one session per server process** — the AMPL
   session lives in the server process, so `solve_model` then `get_variable` must share
   one process; the client needs the `run-script` (chained calls) form, not one-shot
   calls. Point `AMPL_MCP_ROOTS` at the repo's model dirs (`offsim/solve/ampl` plus
   the paper folders, e.g. `offsim/papers/gribkovskaia-slettemark-2025/` once the
   helicopter `.mod` exists).
3. **Optional, complementary:** connect the official AMPL Knowledge Server
   (`https://mcp-kb.ampl.com/mcp`, OAuth) as a second MCP source for writing/debugging
   `.mod` files. No licence needed. It never solves anything — the repo's server does
   that.

After step 2, the loop is: I write a `.mod` + `.dat`, solve through the server,
read variables/duals back, cross-check against the Pyomo twin, and iterate — the
"fun with AMPL" the user wants, with the repo's gates still in front of any film.

## 5. The one concrete next step

**Approve the install, and supply the licence UUID through the secure capture page
(never in chat).** Concretely, his approval unlocks exactly this, nothing more:

```bash
~/workspace/venvs/venv-studio/bin/python -m pip install amplpy "mcp>=1.2"
~/workspace/venvs/venv-studio/bin/python -m amplpy.modules install highs coin gurobi
~/workspace/venvs/venv-studio/bin/python -m amplpy.modules activate <uuid-from-secure-capture>
```

Then I verify `ampl_status()` and run one real `cvrp.mod` solve, and only then build
the `custom.ampl` connector. The alternative that needs no approval and no local
install is the Actions route: add the secret `AMPL_LICENSE_UUID` in the repo settings
and `solve.yml` runs AMPL there — but that does **not** connect AMPL to me; the MCP
path is the only one where I drive the solver.

## 6. What remains unverified

- No AMPL call in this repo has ever run against a real AMPL (README risks; RESUME).
  The server's amplpy calls follow the 0.18 type stubs; `get_constraint(...).get_values("dual")`,
  the CBC `seconds=` option, and the mcp 2.x tool-call round-trip are all untested live.
- Whether the academic licence activates cleanly from this VM's IP (see the academic-IP
  caveat above); whether the lease renews across VM restarts (licence state lives in the
  amplpy modules dir under the venv, which survives; the VM's system packages do not).
- Whether Muse's connector flow accepts a local stdio MCP server the way Claude Desktop
  does — the Rhino precedent proves the client.py pattern works in this workspace, but
  the AMPL connector itself is not built yet.
- The helicopter `.mod` for the Gribkovskaia–Slettemark paper does not exist yet;
  neither does the weekly-helicopter problem class. AMPL connection comes before that
  build, not with it.

## Sources

- Repo (verified on disk): `tools/ampl_mcp/server.py`, `tools/ampl_mcp/README.md`,
  `offsim/solve/ampl_adapter.py`, `offsim/solve/ampl/cvrp.mod`, `tests/test_ampl.py`,
  `.github/workflows/solve.yml`, `catalog/tools.yaml`, `skills/opt-model/SKILL.md`.
- Web (read 2026-11-09): https://dev.ampl.com/ai/mcp-server.html (official MCP Knowledge
  Server), https://ampl.com/academia/ (A4A solvers), https://dev.ampl.com/help/floating-licenses/installation.html
  (personal licence, any computer), https://dev.ampl.com/ampl/python/modules.html (install/activate).
