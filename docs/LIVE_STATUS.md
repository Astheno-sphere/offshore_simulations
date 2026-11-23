# Live status: external dependencies

Generated 2026-11-23T13:39:15Z by `python -m offsim.live.cli` (weekly workflow `live-check`).

A probe that needs a secret reports skipped. A schema hash that changes between runs means a response key or variable was renamed or removed; the live-check issue then lists the keys added and removed.

| Probe | OK | Latency (s) | Last ok (UTC) | Schema hash | Detail |
|---|---|---|---|---|---|
| overpass | no | 6.06 | 2026-11-21 | 8ded2876fa2d0ef3 | HTTP 502 |
| sodir | yes | 1.02 | 2026-11-23 | 6de58734dcef3b97 | 68 layers listed |
| nora3_wind | yes | 0.64 | 2026-11-23 | 401c765f2e400e65 | 10 variables, all 2 expected present |
| nora3_wave | yes | 0.61 | 2026-11-23 | 01782519b996f15c | 25 variables, all 3 expected present |
| norkyst | yes | 0.49 | 2026-11-23 | 64fd84e4eba10ca2 | 17 variables, all 2 expected present |
| kartverket_stedsnavn | yes | 0.47 | 2026-11-23 | 9c147c26ae4f473a | 5 hits for Molde, 5 with a point |
| geonorge_dtm | yes | 0.50 | 2026-11-23 | 59c6f3fc687c4213 | capabilities answered; polygon selection False |
| geofabrik | yes | 1.41 | 2026-11-23 | 0387839065771504 | norway-latest.osm.pbf 1379 MB, last-modified Mon, 23 Nov 2026 00:41:55 GMT |
| entur_gtfs | yes | 0.64 | 2026-11-23 | 0387839065771504 | aggregated GTFS zip 559 MB, last-modified Mon, 23 Nov 2026 12:53:11 GMT |
| entur_vehicles | yes | 0.26 | 2026-11-23 | edb57bcaa6a1d133 | 26 vehicles in the Oslo box |
| barentswatch | yes | 0.49 | 2026-11-23 | 07bce3055a086a8c | token issued (expires_in 3600 s) |
| openalex | yes | 0.37 | 2026-11-23 | f888c5c108d3c8c6 | 1 record on the anonymous pool (OFFSIM_MAILTO not set) |
| crossref | yes | 0.20 | 2026-11-23 | afbe6194f712a3eb | 1 item |
| arxiv | yes | 14.77 | 2026-11-23 | 30e7d95698435e25 | 1 entry with an abs id |
| nva | yes | 0.73 | 2026-11-23 | 7e2e43c8c1389da9 | 1 hit |
| ampl | yes | 0.86 | 2026-11-23 | 66fd1335e88658ff | HiGHS LP: solved, objective 10 (expected 10) |
| runner | yes | 0.92 | 2026-11-23 | 2de9f510c6ad9cc1 | python 3.12; libegl1 installed; skia importable; OCP importable |
