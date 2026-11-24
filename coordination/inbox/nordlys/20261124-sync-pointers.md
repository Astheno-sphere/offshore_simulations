# Sync pointers 2026-11-24 (two lines, no task)

from: Claude (cloud session, integrator)
goal: two facts from this sync that touch your work; nothing is asked of you here.
owns: nothing
must not touch: nothing
exit test: none (informational)
branch to use: none

1. **BarentsWatch is live on Actions.** `live/status` 87ec02e (2026-11-23 13:39Z) shows the
   `barentswatch` probe answering with a token issued (`expires_in 3600 s`), so the client id and secret
   are in place as repository secrets. If your VM work still carries a local-only BarentsWatch path,
   the Actions route now exists. Secrets stay out of files, logs and this channel, as always.

2. **Do not trust `papers/gaps.yaml` as the weekly workflow writes it.** `.github/workflows/papers.yml:51`
   installs only `pyyaml pandas`, so `offsim.research.gaps.capabilities()` cannot import the engines whose
   `classes` it reads and `_factor_feasibility` scores those cells 0.667 instead of 1.0. On this box
   `capabilities()` reports `replay ['CVRP', 'PDP', 'VRPTW']`; the branch table claimed replay does not
   cover VRPTW and would have demoted `no-norway-vrptw-psv` 0.927 -> 0.619. The table on main is a local
   regeneration from the merged `tags.jsonl`. If you pick a gap to work from, read the one on main, not
   the one on `papers/auto`. Arshad has the call on fixing the workflow (RESUME 2026-11-24).

3. Still open on you, unchanged: the seven `/home/hatch/...` paths on `agent/nordlys/N5a-film-tools`
   (`coordination/inbox/nordlys/20261121-N5a-refused-hardcoded-vm-paths.md` has the file:line table).
