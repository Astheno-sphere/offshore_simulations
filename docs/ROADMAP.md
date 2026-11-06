# Roadmap: from framework to the first post

Effort in working sessions (one session ≈ one focused Claude run). "You" = Arshad.

| # | Step | Who | Effort | Done when |
|---|---|---|---|---|
| 1 | Framework, contract, gates, skills, catalog | Claude | done | CI green |
| 2 | Run **fetch-world** for `oslofjord` ✔ and `north-sea-stavanger` | You (Actions tab, 5 min) | — | releases `world-*` exist |
| 3 | Pull worlds, check land polygons and Sodir layers ✔ (Oslofjord; Sodir pending the Stavanger fetch) | Claude | done | `--pull` works, land check passes on a real coast |
| 4 | Order Kystverket AIS for PSVs (offshore/supply ship type) and Oslofjord ferries | You (hais.kystverket.no, 15 min) | — | GeoParquet link arrives |
| 5 | Sea lanes ✔ (grid from coastline, `offsim/worlds/sealanes.py`); refine with Kystverket reference routes and real quay positions | Claude | 1 | fairways followed; quay snap < 200 m |
| 6 | **First paper**: a PSV supply routing paper (CVRP/VRPTW structure fits PyVRP) | You pick, Claude extracts | 2–4 | `reported:` KPIs within tolerance, or a clear "did not reproduce" |
| 7 | Validate speeds and port times against AIS | Claude | 1 | simulated vs AIS medians reported |
| 8 | Motion grammar v1 (characters ✔, 3D sites ✔) + Manim intro + Remotion captions | Claude | 1 | first square + vertical video |
| 9 | Post | You | — | LinkedIn, video hosted (muse.ai) |
| 10 | Second paper: offshore helicopters (needs OR-Tools CP-SAT or a MIP for synchronisation) | both | 2–3 | |
| 11 | Sustainable-energy series: WOMBAT (wind O&M vessels) and ORBIT (installation) on a Norwegian site; cetos for CO2 and electric-PSV what-ifs | both | 2 each | |

To the first post: about 5–8 Claude sessions and about 30 minutes of your time. Each later paper reuses
the machine: 1–2 sessions.
