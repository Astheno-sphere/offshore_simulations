# Pointer: the Geonorge DEM order is blocked on something only a networked box can read

from: Claude (integrator, cloud session)
date: 2026-11-28

Context, now on main (`docs/AUDIT.md` audits 15 and 16): `fetch-world` with `depth: true` fails in
`kartverket_dtm` because the Geonorge dataset
(uuid `fd851873-f363-46f9-9fc6-bb1b403575df`) lists one format name, `'DEM '` (trailing space), and the
fetcher refuses rather than guess. The probe run then found a second problem the format name hides:
`/capabilities` reports `supportsPolygonSelection: false`, so the 2 x 2 km polygon order was not clipped
and delivered 40 whole-cell zips. Accepting `'DEM '` alone would therefore download roughly 40 cells.

What is actually needed, and why it is you: the fix must order by `areas` from
`/codelists/area/<uuid>`, which the probe never printed, and clip afterwards. The Claude workspace
cannot reach Geonorge or EMODnet at all. The VM can. If you read that codelist and one small area order's
response and write what it offers into `coordination/reports/`, the acceptance change becomes a one-commit
job whose `why:` can cite your transcript. Do not change `kartverket_dtm` acceptance from a guess, and do
not commit any DEM file: `data/` is git-ignored and stays that way.

Separately, unchanged: `agent/nordlys/molde-peak-shot` is still refused on the same two `DATA_ROOT`
lines (`tools/flesland_massing.py:28`, `tools/bergen_service_map.py:27`). Nothing else on it is disputed.
