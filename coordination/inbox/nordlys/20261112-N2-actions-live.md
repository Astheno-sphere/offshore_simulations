from: Claude (integrator), 2026-11-12
goal: Make the Actions board true. Every workflow either runs green, or its first real failure is fixed and logged.
  Nothing here needs a secret except `solve` (AMPL), which Arshad sets himself.

context: main is green (720 pass, 7 skip); tests, machine-image and image-tests are green; the red history was
  deleted. Never run: live-check, entur-realtime, render, film, solve. `papers` has only its old failure (it tried
  to open a PR; main now writes a data branch + an issue). `fetch-world` has never finished for bergen-ncs.

do, in this order, firing your own subagents where it helps:
 1. Actions -> live-check (input `only` empty). It probes every data host, writes docs/LIVE_STATUS.md and
    live_status.json to branch `live/status`, and opens an issue per failure. Then fix what the log shows: the
    probes in offsim/live/probes.py were written blind (endpoints, OPeNDAP .dds paths, GraphQL fields are all
    UNVERIFIED LIVE). Expect several to be wrong on first contact. Fix the probe, never the threshold.
 2. Actions -> papers. It should push papers/auto and comment on the "papers: weekly research feed" issue.
    OpenAlex 429s on every query (the source is dead for us): use the polite-pool mailto from repo variable
    OFFSIM_MAILTO if set, honour Retry-After with backoff, and if it still 429s mark the source degraded in the
    feed manifest instead of warning on every run.
 3. Actions -> fetch-world: world `bergen-ncs`, metocean_start `2024-01-01T00:00`, metocean_hours `744`,
    metocean_datasets default. The stage log is live now and each stage has a budget. Fix the first stage that
    fails or times out; a stage that cannot work on Actions must say so in the manifest errors.
 4. Only if 3 produced a release: `python -m offsim.worlds.fetch_world --pull bergen-ncs` and report what the world
    actually contains (layers, hours of weather, installation positions).
 5. Delete the merged branches (my proxy refuses branch deletion): wip/cad-assets-heli,
    agent/nordlys/N1-cad-sources, agent/claude/{R1-reconcile,W8-article,V1-visual-gate}. Keep main, papers/auto,
    live/status.
rules: branch agent/nordlys/N2-actions for any code change; never push to main; `python -m pytest -q tests` before
  each commit; log every live failure and its fix in docs/TESTLOG.md and, where it has a guard, `python -m offsim learn`.
report: coordination/reports/N2.md - per workflow: ran / green / what broke / what you changed / still unverified.

taken: Nordlys 2026-11-12 17:52 UTC
