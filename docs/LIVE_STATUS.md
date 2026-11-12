# Live status: external dependencies

Generated 2026-11-12T20:19:31Z by `python -m offsim.live.cli` (weekly workflow `live-check`).

A probe that needs a secret reports skipped. A schema hash that changes between runs means a response key or variable was renamed or removed; the live-check issue then lists the keys added and removed.

| Probe | OK | Latency (s) | Last ok (UTC) | Schema hash | Detail |
|---|---|---|---|---|---|
| overpass | yes | 30.34 | 2026-11-12 | 8ded2876fa2d0ef3 | 57 coastline ways in the Molde box |
| sodir | yes | 1.16 | 2026-11-12 | 6de58734dcef3b97 | 68 layers listed |
| nora3_wind | yes | 1.86 | 2026-11-12 | 401c765f2e400e65 | 10 variables, all 2 expected present |
| nora3_wave | yes | 0.75 | 2026-11-12 | 01782519b996f15c | 25 variables, all 3 expected present |
| norkyst | yes | 0.60 | 2026-11-12 | 64fd84e4eba10ca2 | 17 variables, all 2 expected present |
| kartverket_stedsnavn | yes | 0.84 | 2026-11-12 | 9c147c26ae4f473a | 5 hits for Molde, 5 with a point |
| geonorge_dtm | yes | 0.78 | 2026-11-12 | 59c6f3fc687c4213 | capabilities answered; polygon selection False |
| geofabrik | yes | 1.38 | 2026-11-12 | 0387839065771504 | norway-latest.osm.pbf 1379 MB, last-modified Thu, 12 Nov 2026 02:18:15 GMT |
| entur_gtfs | yes | 0.55 | 2026-11-12 | 0387839065771504 | aggregated GTFS zip 550 MB, last-modified Thu, 12 Nov 2026 20:01:24 GMT |
| entur_vehicles | yes | 0.45 | 2026-11-12 | edb57bcaa6a1d133 | 24 vehicles in the Oslo box |
| barentswatch | skipped | 0.00 | - | - | skipped: BW_CLIENT_ID not set |
| openalex | no | 0.29 | - | - | HTTP 429 (rate limited; Retry-After 13234) on the polite pool |
| crossref | yes | 0.88 | 2026-11-12 | e5662638190cbffc | 1 item |
| arxiv | yes | 0.32 | 2026-11-12 | ccbaacee567ce8d9 | 1 entry with an abs id |
| nva | yes | 0.62 | 2026-11-12 | 7e2e43c8c1389da9 | 1 hit |
| ampl | skipped | 0.00 | - | - | skipped: AMPL_LICENSE_UUID not set |
| runner | yes | 4.01 | 2026-11-12 | 2de9f510c6ad9cc1 | python 3.12; libegl1 installed; skia importable; OCP importable |
