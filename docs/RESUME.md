# Resume log

Hand-written state for the next session (human or Claude). `python -m offsim resume` prints this file's
**Next** section together with git state, open roadmap rows and open risks. Update it at the end of every
session and whenever work is interrupted. Newest first.

## 2026-11-07 — four visual layers built and integrated

Done: camera (per-frame track, centripetal spline, van Wijk fly, follow/orbit, `shot_plan` inspector — demo passes);
depth (datum-first merge, pydelatin mesh, baked hillshade, isobaths, EMODnet/Geonorge fetchers); weather (NORA3/NorKyst
subsetting, seeded particle trails, Hs texture, PSV weather effects); vessel (display-only fillets, speed ramps, DP
jitter, bob, Kelvin wake, heli profile; toy max offset 12 m, demo 16 m). Renderer: Python precomputes camera track,
display tracks, terrain and weather blocks; line art and wakes drawn at fixed screen size (cartographic symbols);
horizon haze hides the data edge. One command: `python -m offsim film <storyboard> [--muse unlisted]`; Actions
workflow `film`; Dockerfile; muse.ai upload (hosting only).

Interrupted and recovered: the depth builder hit the sub-agent rate limit; its uncommitted work in
/home/claude/wt/depth was finished by hand (terrain.js, requirements, catalog) and merged.

## Next
1. Actions → **fetch-world** `oslofjord` with `depth: true` and `metocean_start` (e.g. 2024-01-10T00:00, 48 h) — first live
   run of the DEM and MET Norway fetchers; fix whatever the log shows; flip `live_checked` in weather/fetch.py.
2. `python -m offsim.worlds.depth --world oslofjord --tier fjord` on the pulled DEM → terrain in the demo map shot.
3. Add `weather: {wind: nora3_wind, wave: nora3_wave, particles: 2500}` to the demo map shot; dry-run; review a still.
4. Actions → **film** on the demo storyboard (add secret `MUSE_AI_KEY` to upload) → review the MP4.
5. First paper (PSV supply routing) via `paper-extract` → `offsim run`.
