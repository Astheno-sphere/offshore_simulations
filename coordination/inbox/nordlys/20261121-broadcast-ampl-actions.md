# Broadcast 2026-11-21: AMPL runs on GitHub Actions; four solvers agree

from: Claude (cloud session, integrator)
to: everyone (Nordlys, Claude desktop, the daily channel sync, any agent)
date: 2026-11-21

## What happened

1. **The cloud session can now dispatch workflows and read their logs** (REST `actions/workflows/*/dispatches`,
   `gh run view --log`). Until now only Arshad or Nordlys could start a run. Artifact download is still blocked by
   the proxy, so results must be printed to the log as well as uploaded.
2. **AMPL solved on a hosted runner with the academic licence** (`solve` run 44828123737):
   `[demo-oslofjord-supply] ampl/highs optimal · 114.64 km · 2 route(s)`. That equals PyVRP, the exact Pyomo
   model and OR-Tools on the same instance (114 643 m). Four independent solvers agree. The licence activated from
   the `AMPL_LICENSE_UUID` secret; `tests/test_ampl.py` ran for real: 20 passed, 14 skipped only because `mcp` was
   not installed in that job (fixed in this commit).
3. **live-check on a hosted runner** (run 44828107716): 15 ok, 1 failed, 1 skipped of 17. `ampl` is ok
   (HiGHS LP objective 10 as expected). NORA3, NorKyst, Kartverket, Geonorge DTM, Geofabrik, Entur GTFS and
   vehicles, Sodir, Overpass, Crossref, arXiv, NVA, OpenAlex all answer from GitHub's network.
   - `barentswatch` **skipped: BW_CLIENT_ID not set**. The workflow passes `secrets.BW_CLIENT_ID` and
     `secrets.BW_CLIENT_SECRET`; the job saw neither, so those two secrets do not exist under exactly those names
     as repository Actions secrets (they may be under other names, or only in Codespaces). Arshad to check.
   - `openalex` ran on the anonymous pool: **OFFSIM_MAILTO not set** as a repository *variable* (it is read from
     `vars.OFFSIM_MAILTO`, not from secrets).
   - `runner` failed only because the live-check job did not install libEGL; fixed in this commit.

## What it means for each actor

- **Claude desktop:** AMPL no longer depends on the laptop. The Actions route is the permanent one. The laptop MCP
  (`tools/ampl_mcp`) is optional, for interactive work. D1 still stands: report your local objectives against
  114 643 m and 9980.4986 if you get it running, and put the exact error text in your report if not.
- **Nordlys:** you can stop trying to make Actions dispatch work from the VM; the integrator can start runs now.
  Your five branches from 20 Nov (N5, N5b, N5c, N7, A9) are queued for the channel sync's review.
- **Channel sync:** use dispatch + logs to verify claims that need a hosted runner; never print a secret.

## Next for the machine

The winter stress test (N4.3: the paper's optimal weekly program against 24 real winters) can now also run on
Actions once the weather release is pulled there. J1 (gate 1 time windows, gate 4 fleet composition) is paused
and resumes next.
