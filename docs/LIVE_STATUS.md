# Live status: external dependencies

Generated 2026-11-21T11:11:17Z by `python -m offsim.live.cli` (weekly workflow `live-check`).

A probe that needs a secret reports skipped. A schema hash that changes between runs means a response key or variable was renamed or removed; the live-check issue then lists the keys added and removed.

| Probe | OK | Latency (s) | Last ok (UTC) | Schema hash | Detail |
|---|---|---|---|---|---|
| overpass | yes | 33.57 | 2026-11-21 | 8ded2876fa2d0ef3 | 57 coastline ways in the Molde box |
| sodir | yes | 1.10 | 2026-11-21 | 6de58734dcef3b97 | 68 layers listed |
| nora3_wind | yes | 0.83 | 2026-11-21 | 401c765f2e400e65 | 10 variables, all 2 expected present |
| nora3_wave | yes | 0.73 | 2026-11-21 | 01782519b996f15c | 25 variables, all 3 expected present |
| norkyst | yes | 0.74 | 2026-11-21 | 64fd84e4eba10ca2 | 17 variables, all 2 expected present |
| kartverket_stedsnavn | yes | 0.81 | 2026-11-21 | 9c147c26ae4f473a | 5 hits for Molde, 5 with a point |
| geonorge_dtm | yes | 0.63 | 2026-11-21 | 59c6f3fc687c4213 | capabilities answered; polygon selection False |
| geofabrik | yes | 1.76 | 2026-11-21 | 0387839065771504 | norway-latest.osm.pbf 1379 MB, last-modified Sat, 21 Nov 2026 01:26:17 GMT |
| entur_gtfs | yes | 0.20 | 2026-11-21 | 0387839065771504 | aggregated GTFS zip 556 MB, last-modified Sat, 21 Nov 2026 10:42:15 GMT |
| entur_vehicles | yes | 0.66 | 2026-11-21 | edb57bcaa6a1d133 | 28 vehicles in the Oslo box |
| barentswatch | yes | 0.51 | 2026-11-21 | 07bce3055a086a8c | token issued (expires_in 3600 s) |
| openalex | yes | 0.28 | 2026-11-21 | d3edf3370ba52da7 | 1 record on the anonymous pool (OFFSIM_MAILTO not set) |
| crossref | yes | 0.26 | 2026-11-21 | e5662638190cbffc | 1 item |
| arxiv | yes | 0.25 | 2026-11-21 | ccbaacee567ce8d9 | 1 entry with an abs id |
| nva | yes | 0.82 | 2026-11-21 | 7e2e43c8c1389da9 | 1 hit |
| ampl | yes | 0.97 | 2026-11-21 | 66fd1335e88658ff | HiGHS LP: solved, objective 10 (expected 10) |
| runner | yes | 0.94 | 2026-11-21 | 2de9f510c6ad9cc1 | python 3.12; libegl1 installed; skia importable; OCP importable |
