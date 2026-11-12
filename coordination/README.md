# Coordination channel (git is the channel)

Writers: Arshad, Claude (laptop/cloud session, integrator), Nordlys (Muse agent on a VM, env `venv-studio`) and
their subagents. No MCP or shared chat is needed: agents talk through files in this folder, on git.

Protocol
1. Before any work: `git fetch`, read `docs/RESUME.md`, `docs/SYSTEM_PLAN.md`, then your inbox `coordination/inbox/<you>/`.
2. A task is one file `coordination/inbox/<to>/<YYYYMMDD>-<id>-<slug>.md` with: from, goal, owns (files), must not
   touch, exit test, branch to use. Take it by adding a line `taken: <who> <UTC time>` and pushing.
3. Work on branch `agent/<who>/<id>` only. Never push to `main`. Never commit uncommitted piles straight onto an
   integration branch: bring them in on your own branch so they can be reviewed and reconciled.
4. When done: write `coordination/reports/<id>.md` (what changed, tests run with counts, open risks, anything you
   disagree with), push, and move the task file to `coordination/done/`.
5. Disagreements and corrections go in the report or in `coordination/inbox/<other>/` as a note. They are welcome:
   a correction with evidence beats a silent fix. Example: Nordlys's note that flaw 2.7 in SYSTEM_PLAN is stale.
6. Only the integrator (Claude main session, or Arshad) edits `docs/RESUME.md` and merges into the integration
   branch. One integration branch at a time (currently `wip/cad-assets-heli` -> `main` via PR #1).
7. A test is never edited to pass without a `why:` line in the commit and a line in the report.
8. Secrets (AMPL UUID, API keys) never enter files, logs or this channel.
