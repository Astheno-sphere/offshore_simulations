# The machine: one environment on GitHub, plug and play for any agent

The repo is the machine. Its body is one container image, built from `Dockerfile` by the `machine-image` workflow and
published at `ghcr.io/astheno-sphere/offsim`. Everyone runs the same image:

| Who | How they enter | Notes |
|---|---|---|
| Arshad | GitHub -> Code -> Codespaces -> Create codespace (uses `.devcontainer/devcontainer.json`) | browser or VS Code; persistent, stops when idle, resumes with state |
| Claude (Claude Code) | inside the Codespace terminal (`claude`), or the cloud session cloning the repo | reads `CLAUDE.md`, `.claude/agents/`, `.mcp.json` |
| Nordlys and other agents (Qwen, Codex, ...) | open the same Codespace or `docker run ghcr.io/astheno-sphere/offsim` with the repo mounted | read `AGENTS.md`, take a task from `coordination/inbox/` |
| CI | workflows (next step: run the test job inside this image, so the runner image can no longer break us) | `tests.yml` |

Why this and not a private VM: a VM is one person's computer, invisible to the others, and its uncommitted work is
lost to everyone else (it happened: CAD sources and section.py v7-v10). A Codespace is created from the repo, carries
the rules with it, and can reach what the Claude cloud workspace cannot: AMPL downloads, Kartverket, MET Norway, Entur.

Rules that travel with the machine: `AGENTS.md` (hard rules, roles, protocol), `CLAUDE.md`, `docs/GUARDS.md`,
`tests/test_concordance.py` (drift), `offsim doctor` (diagnosis), `offsim status` (where every paper stands),
`coordination/` (who is doing what).

Setup, once (Arshad):
1. Actions -> machine-image -> Run workflow (about 20 min). Then Packages -> offsim -> Package settings -> make it
   public or grant the repo access, so Codespaces can pull it.
2. Settings -> Secrets and variables -> Codespaces: add `AMPL_LICENSE_UUID` (and `MUSE_AI_KEY`, `OFFSIM_MAILTO`).
   These are separate from Actions secrets; add both.
3. Code -> Codespaces -> Create codespace on the integration branch. First start runs `tools/machine_setup.sh`
   (AMPL activation, tool table, runner probe) and prints the resume state.
Cost: Codespaces has a monthly free quota for personal accounts (core-hours and storage); a 4-core machine uses it
four times as fast as a 1-core. Set the idle timeout to 15 min and stop it when done. Check the current quota in
GitHub billing settings before relying on it.

Unverified until the first build: the image has not been built yet (the Claude workspace has no Docker). Expect one
round of fixes from the first `machine-image` log; record it in `docs/TESTLOG.md`.
