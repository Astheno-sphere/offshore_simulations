# Live status: external dependencies

Generated 2026-11-16T12:02:25Z by `python -m offsim.live.cli` (weekly workflow `live-check`).

A probe that needs a secret reports skipped. A schema hash that changes between runs means a response key or variable was renamed or removed; the live-check issue then lists the keys added and removed.

| Probe | OK | Latency (s) | Last ok (UTC) | Schema hash | Detail |
|---|---|---|---|---|---|
| overpass | no | 6.04 | - | - | HTTP 502 |
| sodir | yes | 0.86 | 2026-11-16 | 6de58734dcef3b97 | 68 layers listed |
| nora3_wind | yes | 0.68 | 2026-11-16 | 401c765f2e400e65 | 10 variables, all 2 expected present |
| nora3_wave | yes | 0.69 | 2026-11-16 | 01782519b996f15c | 25 variables, all 3 expected present |
| norkyst | yes | 0.74 | 2026-11-16 | 64fd84e4eba10ca2 | 17 variables, all 2 expected present |
| kartverket_stedsnavn | yes | 0.64 | 2026-11-16 | 9c147c26ae4f473a | 5 hits for Molde, 5 with a point |
| geonorge_dtm | yes | 0.63 | 2026-11-16 | 59c6f3fc687c4213 | capabilities answered; polygon selection False |
| geofabrik | yes | 1.14 | 2026-11-16 | 0387839065771504 | norway-latest.osm.pbf 1379 MB, last-modified Mon, 16 Nov 2026 02:24:45 GMT |
| entur_gtfs | yes | 0.20 | 2026-11-16 | 0387839065771504 | aggregated GTFS zip 546 MB, last-modified Mon, 16 Nov 2026 10:45:59 GMT |
| entur_vehicles | yes | 0.69 | 2026-11-16 | edb57bcaa6a1d133 | 28 vehicles in the Oslo box |
| barentswatch | skipped | 0.00 | - | - | skipped: BW_CLIENT_SECRET not set |
| openalex | yes | 0.42 | 2026-11-16 | 9dd15efa8fe9b8fb | 1 record on the anonymous pool (OFFSIM_MAILTO not set) |
| crossref | yes | 5.18 | 2026-11-16 | afbe6194f712a3eb | 1 item |
| arxiv | yes | 0.36 | 2026-11-16 | ccbaacee567ce8d9 | 1 entry with an abs id |
| nva | yes | 0.86 | 2026-11-16 | 7e2e43c8c1389da9 | 1 hit |
| ampl | skipped | 0.00 | - | - | skipped: AMPL_LICENSE_UUID not set |
| runner | no | 0.05 | - | - | python 3.12; libegl1 missing; skia not importable; OCP not importable |
