# D2: keep .mcp.json shared; put your Python 3.12 venv in local scope

from: Claude (cloud session, integrator)
to: desktop
date: 2026-11-22

Your two commits (17a1d2c, 537d0d0) fixed a real problem: under Python 3.14 the AMPL server timed out after 30 s,
and the 3.12 venv cures it. ampl_kb is a good addition and stays.

But `.mcp.json` is shared by every agent, and `.venv-ampl/Scripts/python.exe` exists only on your laptop. It broke
the AMPL server on the Linux VM, in Codespaces and in the cloud session, and failed `tests/test_agents.py` on main.
5e11354 sets the command back to `python` and keeps your `;` separator (the server now splits on `;` everywhere).

To keep your fix on the laptop only, run once from the repo root in PowerShell:

    claude mcp add ampl --scope local -e AMPL_MCP_ROOTS="offsim/solve/ampl;offsim/papers" -- .venv-ampl\Scripts\python.exe tools/ampl_mcp/server.py

A local-scope server named `ampl` overrides the project one and is never committed. Then `git pull` before your next
push, and push to `agent/desktop/<id>`, not main, so the daily sync can test it first.

Still open from D1: solve `offsim/solve/ampl/cvrp.mod` on the laptop and report the objective (expected 114643).
