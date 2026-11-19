# Harness hooks (`tools/hooks/gate.py`)

Claude Code hooks that hold the most important hard rules whatever the model decides. Wired in `.claude/settings.json`
(`PreToolUse` on Write, Edit, MultiEdit, NotebookEdit, Bash; `Stop`). Each rule is a pure function of the hook JSON, tested in
`tests/test_hooks_gate.py`. The pattern (exit 2 to block, a `stop_hook_active` loop guard, protected evidence files) comes from
Abhinav Bhardwaj's Junior Architect Pipeline (MIT; see `THIRD_PARTY_NOTICES.md`); no code was copied.

All hooks: never block a read; never block `python -m pytest`; **fail open** (an internal error or malformed input is logged to
stderr and the call is allowed); about 30 ms per call. A block names the rule and this file.

## What each hook blocks

### H1
`out/**/report.json`, `trajectory.csv`, `agents.csv`, `run.json`, `state.json` written by anything but the pipeline.
- Write, Edit, MultiEdit, NotebookEdit on those paths: always blocked.
- Bash: a redirect (`>`, `>>`, `tee`), `cp`/`mv`/`install` onto, `rm`/`truncate`/`touch` of, `sed -i` on, `dd of=`, `curl -o` to one of
  those paths, also inside `bash -c`; after `cd .../out` the bare file names count; a `python -c` or heredoc line that names one
  of the files and calls a write API.
- The pipeline is recognised by its command line: `python -m offsim run ...` (with env assignments, `timeout`, `uv run` in front).
  Such a segment may write them; a shell redirect from it onto a protected file is still blocked. `python -m pytest` is exempt.
- Not blocked: reading (`cat`, `jq`, `grep`, `cp` out of them), writing any other file under `out/`.

### H2
Edits to `offsim/cinema/rules.py`, `offsim/cinema/visual_gate.py`, `tests/golden/*`, and, in `offsim/papers/*/scenario*.yaml`, a
change to the `reported:` block or to any line naming a tolerance (`rel_tol`, `abs_tol`, `gap_tol`, `tol`, `tolerance`).
- Write or Edit: blocked unless the branch is `agent/<who>/<id>`. An unknown branch (detached HEAD, no repo) is allowed.
- `git commit`: blocked when the index (or `-a`) modifies or deletes one of those files and the message has no `why:` line
  (read from `-m`, a heredoc or `-F file`). New files (a new golden) need no `why:`.
- Not enforced: that the same task does not then claim a gate passes. A hook cannot see a claim; the integrator and the
  corrector check `why:` lines in review. A commit made with an editor (no `-m`, no `-F`) is not seen.

### H3
- `git add` of a path under `out/` or `data/`, anything under `out/reference/`, and any forced add (`-f`) of `.`, `*` or `-A`.
- `git commit` while the index holds a file under `out/` or `data/`, however it got there.
- Not blocked: `git add .` or `-A` without `-f` (they respect `.gitignore`), writing files into `out/`.

### H4
A write (Write, Edit, MultiEdit, NotebookEdit) or a Bash command, commit messages and heredocs included, that holds
- a UUID within 100 characters of `AMPL`, or within 40 characters of `licence`/`license` (a dataset id in a URL or after
  `metadata_uuid:` is not counted), or
- a BarentsWatch client secret: `BW_CLIENT_SECRET=<value>` or `client_secret=<value>` in text that names BarentsWatch, where the
  value has 12 or more characters with letters and digits and is not a placeholder (`$VAR`, `<...>`, `xxxx`, `os.environ...`).

The message says only "a secret-shaped string is present"; the string is never printed. `python -m pytest` is exempt.
Only what is about to be written or run is checked, not files already on disk.

### H5 (Stop)
Refuses to finish while a storyboard that is new or modified in the working tree (`git status`, `*storyboard*.yaml`) names, in
its `run:` line, a `report.json` with a failed gate (every gate but `4_paper`, as `offsim/motion/story.py` does). A missing report
(out/ is not synced to the cloud) allows. `stop_hook_active` allows, so the agent is never trapped in a loop.

## Limits (what a hook cannot see)
A script the agent writes and then runs can write a protected file; a commit message built from variables; a claim in prose. The
hooks stop the direct paths and the common indirect ones. The pipeline's own gates stay the source of truth.

## Disabling one in an emergency
- One rule, one session: set `OFFSIM_HOOKS_OFF=H2` (comma list, or `all`) in the environment, or in `.claude/settings.local.json`
  as `{"env": {"OFFSIM_HOOKS_OFF": "H2"}}` (not committed).
- All of them: delete the `PreToolUse` and `Stop` entries under `hooks` in `.claude/settings.json`, or set `"disableAllHooks": true`
  in `.claude/settings.local.json`.
- Say why in the coordination report. A hook that blocks legitimate work is a bug: fix the rule and add a test.
- The command is `python3 -S`; where `python3` is missing (some Windows setups) the hook errors without blocking.
