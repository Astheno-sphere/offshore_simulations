---
name: ampl-model
description: Use AMPL for exact LP/MIP certification of PyVRP plans and for gate-2 cross-checks. Summon when the request mentions AMPL, exact optimality, duality gap, LP relaxation bounds, or when a PyVRP plan needs independent proof.
---

# ampl-model

The `opt-model` skill owns Pyomo/HiGHS exact models. This skill owns AMPL.

## When to use AMPL over Pyomo/HiGHS

- A reader cares about commercial-solver corroboration (Gurobi, CPLEX, COPT).
- Instance size pushes HiGHS past its practical limit; Gurobi or CPLEX is needed.
- The paper itself was modelled in AMPL and we want to stay in the author's language (runs on the laptop via ampl_mcp, or on Actions via solve.yml).
- Gate-2 double-check: solve the same model with HiGHS and with the best commercial solver, compare objectives within `tol`.

## Interfaces

- `offsim.solve.ampl_adapter` — the route solver behind the `Solver` protocol. Reads `offsim/solve/ampl/cvrp.mod`, writes `plan.json`. Used by the `solve` GitHub Actions workflow.
- `offsim.solve.ampl_backend` — low-level helper: `solve_model(...)`, `certify_against_highs(...)`.
- `tools/ampl_mcp/server.py` — MCP server exposing AMPL to Claude Code: `check_license`, `list_solvers`, `solve_text`, `solve_file`, `compare_highs`, `run_script`.

## Licensing

Academic UUID lives in the `AMPL_LICENSE_UUID` env var locally and as a GitHub Actions secret. It is never committed, logged or written into any plan or report. See `solve.yml` for CI activation, `tools/ampl_mcp/README.md` for local activation.

## Gate-2 recipe

1. Solve the scenario with PyVRP (`offsim.solve.pyvrp_adapter`).
2. On small instances (≤ ~30 stops), solve the same scenario exactly with AMPL + Gurobi.
3. Call `compare_highs` to confirm the commercial objective equals the HiGHS objective within `1e-6`.
4. Record both objectives in `plan.provenance`; the corrector flags the plan if PyVRP's objective exceeds the AMPL lower bound by more than the paper's stated tolerance.

## What this skill does not do

- Does not render videos. Does not fetch worlds. Does not post captions.
- Does not approximate: AMPL is the exact backstop, not a replacement for PyVRP on large instances.
