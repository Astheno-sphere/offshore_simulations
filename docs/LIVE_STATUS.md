# Live status: external dependencies

Generated 2026-11-20T22:21:15Z by `python -m offsim.live.cli` (weekly workflow `live-check`).

A probe that needs a secret reports skipped. A schema hash that changes between runs means a response key or variable was renamed or removed; the live-check issue then lists the keys added and removed.

| Probe | OK | Latency (s) | Last ok (UTC) | Schema hash | Detail |
|---|---|---|---|---|---|
| overpass | yes | 35.16 | 2026-11-20 | 8ded2876fa2d0ef3 | 57 coastline ways in the Molde box |
| sodir | yes | 0.94 | 2026-11-20 | 6de58734dcef3b97 | 68 layers listed |
| nora3_wind | yes | 0.55 | 2026-11-20 | 401c765f2e400e65 | 10 variables, all 2 expected present |
| nora3_wave | yes | 0.72 | 2026-11-20 | 01782519b996f15c | 25 variables, all 3 expected present |
| norkyst | yes | 0.43 | 2026-11-20 | 64fd84e4eba10ca2 | 17 variables, all 2 expected present |
| kartverket_stedsnavn | yes | 0.54 | 2026-11-20 | 9c147c26ae4f473a | 5 hits for Molde, 5 with a point |
| geonorge_dtm | yes | 0.52 | 2026-11-20 | 59c6f3fc687c4213 | capabilities answered; polygon selection False |
| geofabrik | yes | 1.28 | 2026-11-20 | 0387839065771504 | norway-latest.osm.pbf 1379 MB, last-modified Fri, 20 Nov 2026 00:21:08 GMT |
| entur_gtfs | yes | 0.13 | 2026-11-20 | 0387839065771504 | aggregated GTFS zip 557 MB, last-modified Fri, 20 Nov 2026 21:14:27 GMT |
| entur_vehicles | yes | 0.22 | 2026-11-20 | edb57bcaa6a1d133 | 19 vehicles in the Oslo box |
| barentswatch | skipped | 0.00 | - | - | skipped: BW_CLIENT_ID not set |
| openalex | yes | 0.26 | 2026-11-20 | d3edf3370ba52da7 | 1 record on the anonymous pool (OFFSIM_MAILTO not set) |
| crossref | yes | 0.30 | 2026-11-20 | e5662638190cbffc | 1 item |
| arxiv | yes | 0.24 | 2026-11-20 | ccbaacee567ce8d9 | 1 entry with an abs id |
| nva | yes | 0.54 | 2026-11-20 | 7e2e43c8c1389da9 | 1 hit |
| ampl | yes | 0.67 | 2026-11-20 | 66fd1335e88658ff | HiGHS LP: solved, objective 10 (expected 10) |
| runner | no | 0.04 | - | - | python 3.12; libegl1 missing; skia not importable; OCP not importable |
