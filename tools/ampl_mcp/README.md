# ampl_mcp

Minimal MCP server that puts AMPL inside Claude Code and any MCP client.

## Install

```powershell
pip install "mcp[cli]" amplpy
python -m amplpy.modules install highs gurobi cplex copt
python -m amplpy.modules activate $env:AMPL_LICENSE_UUID
```

## Tools exposed

| tool              | purpose                                                            |
|-------------------|--------------------------------------------------------------------|
| `check_license`   | version, expiry line, installed solvers                            |
| `list_solvers`    | preferred-order list of solver modules                             |
| `solve_text`      | solve an inline AMPL model string, return objective and variables  |
| `solve_file`      | read `.mod` (and optional `.dat`) and solve                        |
| `compare_highs`   | gate-2 check: commercial solver vs HiGHS on the same model         |
| `run_script`      | run an arbitrary AMPL script, return its stdout and stderr         |

## Register in `.mcp.json`

Already wired at the repo root. Each Claude Code session in this repo loads it.

The server reads `AMPL_LICENSE_UUID` from env on startup and activates once.
Never commit the UUID — keep it in your OS environment or in a GitHub Actions
secret of the same name.
