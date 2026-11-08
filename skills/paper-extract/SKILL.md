---
name: paper-extract
description: Turn an operations-research paper (offshore supply vessel routing, ferry scheduling, helicopter crew transport, worker routing, any VRP, PDP or scheduling variant, bus or ferry timetables) into a scenario.yaml the solver, engine and corrector can run. Starts from the offsim paper draft, confirms each value with its page, and chooses solver, engine and validation keys. Use when the user names or attaches a paper to reproduce, simulate or visualise.
---

# paper-extract

Second step of the flow (router: `offsim-foundations`). Input: the draft from `python -m offsim paper <pdf>`
(local text and table extraction with page numbers). Output: `offsim/papers/<id>/scenario.yaml` (copy of
`offsim/papers/_template/scenario.yaml`), `timetable.yaml` when the case is a network, and `notes.md`.

## Procedure
1. Get the paper: attached PDF, DOI or open-access link. Record the licence. Only open-access (CC BY etc.) figures
   and instance data may be redistributed; otherwise keep the numbers, cite, and link.
2. Run `python -m offsim paper <pdf>`. The draft is a list of candidate values, each with a page. A draft is not a
   scenario and never runs.
3. Confirm every candidate against its page. Keep it when the page says so; correct it only from the page. A value
   with no page becomes `assumption: true` with a one-line reason. Never invent a parameter to make the model run.
4. Choose the keys (table and reasons: `offsim-foundations`, `docs/ENGINES.md`):
   - `solver:` `pyvrp` (default, heuristic) | `pyomo` (exact, here) | `ampl` (exact, Actions or laptop).
   - `engine:` `replay` (default) | `openclsim` | `road` | `gtfs` | `wombat` | `orbit`. Match the paper's assumptions.
   - `certify:` gate 1b, exact bound on a small instance only.
   - `ensemble:` gate 3e, weather years and seeds, only when the question depends on weather or variability.
   - `validate: {ais: true}` gate 4b, road runs with a calibration built for that purpose.
   - `validate: {entur: true}` gate 4c, scheduled bus or ferry runs with an Entur realtime pull.
   Add a key only when the paper or the question needs it: each one adds a gate that can fail.
5. Copy the paper's headline results into `reported:` with a tolerance: 1% for exact methods on the paper's own
   instance, 2-5% for metaheuristics, wider only with a written reason.
6. List in `notes.md` what the paper does not give (instance files, speeds, service times) and how the scenario
   fills it: published benchmark, public data (Sodir, Kystverket, Entur), or assumption.
7. Hand off to `python -m offsim run <scenario.yaml>`, then `sim-corrector`. Never straight to a render.

## Format the runner reads
- `instance.base`: {name, lon, lat, src}.
- `instance.stops`: list of {name, lon, lat, demand {value, src}, optional service_s, tw {value: [early, late]}, src}.
- `fleet[0]`: count, capacity, speed_mps as {value, src}.
- Classes: gate 0 refuses any class no registered solver or engine handles. Example: `offsim/papers/demo-oslofjord-supply/`.

## Timetables and networks
If the case is a transit or ferry network, write `timetable.yaml` next to the scenario (schema in
`offsim/transit/from_paper.py`): stops with lon/lat and `src`, run times, dwell, headway or departure lists, service
days. Each value is `{value, src: "p.X Table Y"}` or `assumption: true`. Coordinates the paper does not give are
looked up (Entur stop register, Kartverket) and carry that source; they are not invented. Site or customer
coordinates go into a GeoJSON installed with `offsim.worlds.user_layers --kind sites`.

## Rules
- Units: seconds, metres, kWh. Coordinates WGS84 lon/lat.
- An assumption on any parameter that drives a `reported:` KPI still runs, but the status is
  **re-run under assumptions**, not **reproduced**. The narrator must say so.
- User-supplied data (GeoJSON, timetables) is welcome. It carries its own source line.
