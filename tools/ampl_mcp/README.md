# ampl_mcp: AMPL on your laptop, driven from Claude desktop

`server.py` is a small MCP server (stdio) that gives Claude five tools over an AMPL session on your own machine:
`solve_model`, `get_variable`, `get_duals`, `run_ampl`, `list_models`. The Claude workspace cannot download AMPL,
so this is the laptop route. GitHub Actions has the same solve in `.github/workflows/solve.yml`.

## Install (once)

Run these in the Python environment you will point Claude at. Use the full path to that Python if you use a venv.

```bash
pip install amplpy "mcp>=1.2"
python -m amplpy.modules install highs coin       # HiGHS (MIP) and CBC
python -m amplpy.modules activate <your-academic-licence-uuid>
```

- `<your-academic-licence-uuid>` is your own AMPL academic licence UUID. Paste it only in the terminal. Do not put it
  in a file, a commit, or a chat. The academic licence needs internet access to renew its lease.
- The server imports `FastMCP` from mcp 1.x and falls back to `MCPServer` in mcp 2.x. Only the mcp 2.x import path has
  been checked in this repo so far.

## Connect to Claude desktop

Edit `claude_desktop_config.json`:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

Add an `mcpServers` entry (absolute paths only):

```json
{
  "mcpServers": {
    "ampl": {
      "command": "/absolute/path/to/python",
      "args": ["/absolute/path/to/offshore_simulations/tools/ampl_mcp/server.py"],
      "env": {
        "AMPL_MCP_ROOTS": "/absolute/path/to/offshore_simulations/offsim/solve/ampl"
      }
    }
  }
}
```

Quit and reopen Claude desktop. Then ask Claude to `list_models`: it should show `cvrp.mod`.

`AMPL_MCP_ROOTS` lists the folders the server may read, separated by `:` on macOS and Linux or `;` on Windows.
If unset, the root is `~/ampl-models`. Put only the models you trust under these roots.

## What the tools do

| Tool | Does |
|---|---|
| `solve_model(model_path, data_path, solver, options, seconds)` | reads the model (and data), solves with `highs` or `cbc`, returns status, objective, wall time |
| `get_variable(name, limit)` | values of a variable after the last solve |
| `get_duals(constraint, limit)` | dual values of a constraint after the last solve |
| `run_ampl(statements)` | runs AMPL statements in the session (`solve`, `display`, `option`, `let`, ...) |
| `list_models(directory)` | `.mod`, `.dat`, `.run` files under a root folder |

## Security notes

- **stdio only.** No port is opened. The server makes no network calls of its own.
- **Folders.** Every path is resolved and must sit under `AMPL_MCP_ROOTS`. Symlinks are followed before the check.
- **Text screen.** Before anything runs, AMPL text is refused if it contains `!` (shell escape; `!=` is allowed),
  `shell`, `cd`, `remove`, `include`, `commands`, `write`, `read`, `data`, `model`, `reset`, `close`, `quit`,
  `solution`, or a `>` or `|` redirection. Model files get the same check with comments ignored, and refuse a
  redirection to a quoted file name. This is a guard against accidents and prompt-injected commands. It is not a
  sandbox: AMPL can still run a long solve, so keep `seconds` short.
- **Solvers.** Only `highs` and `cbc`. Solver options must be plain `name=value` pairs.
- **Output.** Nothing is printed to stdout, which carries the protocol. AMPL output goes to stderr and to the tool result,
  truncated to 20,000 characters.

## Risks, not yet verified

- The workspace where this was written cannot start AMPL, so none of the AMPL calls here has run against a real
  AMPL. They follow the amplpy 0.18 type stubs (`get_variable`, `get_constraint(...).get_values("dual")`,
  `get_current_objective`, `set_option`, `solve_result`).
- The CBC time-limit option is not verified. `highs` uses `time_limit`.
- The screen is a list of patterns, not a parser. A determined model could still reach a file the solver can open.
