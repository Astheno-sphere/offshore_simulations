# Visual specification

How offshore_simulations films look and how they are made. Numbers live in code
(`offsim/cinema/rules.py`, `offsim/worlds/depth.py`, `offsim/weather/operability.py`); this page explains them.
Status per item: **built** (runs, tested) · **defined** (interface + contract in code, raises NotImplementedError) · **planned**.

## 1. Rendering rules (all shots)

1. **Frame-exact.** `window.draw(t)` is the only clock. No `requestAnimationFrame`, `Date.now`, deck.gl
   `transitionDuration`, GSAP ticker or GPU particle state. Randomness is seeded and closed-form in `t`
   (sums of sines, fixed respawn schedules), never integrated per frame. *built* (renderer), *rule* (everything else)
2. **Display never edits truth.** Smoothing, wakes, bobbing, DP jitter act on a display copy of the validated
   trajectory; max display offset ≤ 25 m (`display_offset_check`). *defined*
3. **Offline.** No tile servers, CDNs or live APIs at render time: every asset is a file or data URL built from a
   world release. Test: render `--check` with the network blocked. *built* (renderer), *rule*
4. **Gate before pixels.** `offsim run` gates 0–3, then `story --dry-run` (refs, tools, renderer `--check`,
   `hyperframes lint`, and `shot_plan` once built). *built* / *defined*
5. **One look per film.** One sun, one grade, one palette (`style.json`), one accent.
6. **Cost budget on SwiftShader (no GPU).** ≤ 2 screen passes (vignette, tilt-shift) per frame; terrain ≤ 400k
   triangles; textures ≤ 4096 px; grading, grain and bloom once in ffmpeg after capture; shadows off (fake with a
   blob decal). Lines need `antialiasing: true` when any post effect is on (effects disable MSAA).
7. **Credits always on screen:** © OpenStreetMap contributors (ODbL) · © Kartverket (CC BY 4.0) · MET Norway
   (CC BY 4.0) · Norwegian Offshore Directorate (NLOD) · EMODnet/GEBCO when used · "illustrative bathymetry,
   not for navigation" · "SYNTHETIC" for any invented input · status word from the report.

## 2. Map depth — *defined* (`offsim/worlds/depth.py`)

| Tier | Use | Grid | Exaggeration land / sea | Mesh max error | Isobaths (m) |
|---|---|---|---|---|---|
| fjord | Oslofjord-wide | 50 m | 3× / 5× | 2 m | 10 20 50 100 200 300 |
| port | ~5×5 km harbour close-ups | 10 m land, 5 m (NGU 1 m) sea | 1.5× / 2× | 1 m | 5 10 20 50 |
| shelf | North Sea off Stavanger | ~115 m (EMODnet) | 4× / 30× | 5 m | 50 100 200 300 500 700 |

Pipeline (fetch on Actions → process → render offline):
1. **Fetch:** Kartverket DTM10 (land, CC BY 4.0, Geonorge download API), Kartverket seabed terrain 5/25/50 m
   (WCS), NGU 1 m (inner Oslofjord only), EMODnet DTM (North Sea), GEBCO for gaps. Raw tiles → release
   `world-<name>-dem-raw`.
2. **Merge** (`merge_dem`): one CRS (EPSG:25833 Oslofjord, 25832/4326 Stavanger); **datum first** (land NN2000,
   seabed chart datum, EMODnet LAT); mosaic by priority with 3–5 cell feather; burn the OSM coastline at 0 m;
   COG with `elevation`, `bathy_mask`, `source_id`.
3. **Outputs:** `terrain_mesh` (pydelatin TIN → SimpleMeshLayer) · `hillshade_texture` (multidirectional
   hillshade × depth tint, baked PNG → BitmapLayer or mesh texture) · `isobaths` (smoothed contours, every 5th
   bold, labelled → PathLayer, CAD style, same line weight family as the vessel line art).
4. **Later:** Protomaps bbox extract (PMTiles) for roads, buildings, ports, labels; MapLibre interleaved only if
   its idle event can gate frames.

## 3. Weather — data *built, not yet live-checked* (`offsim/weather/fetch.py`), simulation *partly built* (`effects.py`), visuals *built* (`visual.py`, `render_deck/src/layers/weather.js`)

| Layer | Source | On screen | In the simulation |
|---|---|---|---|
| Wind 10 m | NORA3 (3 km, hourly) | seeded particle trails (TripsLayer), speed-coloured | helicopter limits (*assumption* until CAP 437 read) |
| Waves Hs/Tp/dir | NORA3 wave hindcast; WAM 800 m | Hs colour field (BitmapLayer), vessel bob ∝ Hs | PSV speed loss, service time, wait-on-weather (**sourced bands**, `operability.py`) |
| Surface current | NorKyst v3 800 m (from 2024) | current arrows / slow trails | drift for DP and approach (planned) |

Particles: `seed_particles` (Poisson-disc in water) → `integrate_streamlines` (RK4, fixed respawn schedule)
→ TripsLayer with `currentTime = t`. Byte-identical re-render is the acceptance test. GPU particle libraries
(weatherlayers-gl, deck.gl-community ParticleLayer) are drafts-only.

PSV weather bands (Gribkovskaia 2022, approximate): Hs < 2.5 m normal · 2.5–3.5 m service +20% ·
3.5–4.5 m −2 kn, service +30% · ≥ 4.5 m wait on weather.

## 4. Camera — rules *built as data* (`offsim/cinema/rules.py`), functions *defined* (`camera.py`)

Shot grammar: **establish** (zoom 7–9, pitch 0–30) → **descend** (pitch → 50–60) → **follow** (track a vessel,
lead space 30–35%, look-ahead 4–6 s) → **event** (push-in or orbit on the moment that matters) → **reveal**
(pull back to the whole plan). 5–8 shots in 30–45 s; shots 4–8 s, never < 2.5 s; hold 0.4 s in, 0.8 s out.

| Limit | Value |
|---|---|
| zoom rate | ≤ 0.35 levels/s (target 0.15–0.25) |
| pitch rate | ≤ 10°/s |
| bearing rate | orbit ≤ 6°/s, reveal ≤ 3°/s |
| pan rate | ≤ 0.6 screen widths/s; ≤ 0.25 with a vessel on screen |
| cuts | only when < 2°/s and < 0.1 zoom/s; else 6–10 frame crossfade |
| 30° / 180° rules | consecutive shots change bearing 0° or ≥ 30°; vessels keep screen direction |

Interpolation: centripetal Catmull-Rom through keys (velocity continuous; the current smoothstep-per-segment
renderer stops at every key — to be replaced by `camera_spline`), van Wijk fly only for moves ≥ 2 zoom levels or ≥ 1
screen width, critically damped spring (closed form) for follow-cam. `shot_plan` will refuse storyboards that
break these limits.

## 5. Vessel and aircraft motion — *defined* (`offsim/cinema/vessel.py`), display-only

PSV rate of turn ≤ 20°/min at service speed (45°/min manoeuvring), filleted turns of 2–3 ship lengths; linear
speed ramp to zero over the last 300–500 m to a quay, 20 s departure ramp; DP jitter < 1.5 m RMS, < 0.5° heading
(3 sines, 7–40 s); Kelvin wake half-angle 19.47°, 8–12 ship lengths, alpha ∝ speed; bob from local Hs/Tp:
heave 0.25·Hs, roll min(6°, 1.2·Hs), pitch min(3°, 0.6·Hs). Helicopter: climb 8–10 m/s, cruise 140 kn, descent
3–5 m/s, 30 s deck hover, 100 m flare — the same phase table must drive the simulation.

## 6. Look — presets *built as data* (`offsim/cinema/look.py`)

In deck.gl: LightingEffect sun (elevation 25–45°, one azimuth per film), vignette + tilt-shift (luma.gl effects,
≤ 2 passes). In ffmpeg, once: grade presets `north-sea-steel`, `golden-hour`, `night-ops` (eq, colorbalance,
vignette, grain); bloom recipe (threshold → gblur → screen). Line art and isobaths share one stroke family:
1.3 px agents, 1 px isobaths, 1.6 px every 5th isobath.

## 7. Motion graphics and sound — *built* (storyboard), *planned* (sound)

Storyboard shots: `equation` (Manim) → `map` (deck.gl) → `card` (HyperFrames + GSAP count-ups, values only from
`report:` refs). Planned: Vivus line-drawing card (vessel elevation drawn stroke by stroke from `lineart/*.json`
side view), weather legend card, captions. Sound (planned): Pixabay content licence (no attribution) or
Freesound **CC0 only** (per-clip licence; CC-BY needs credit, CC-BY-NC forbidden); engine/sea/rotor beds at
−24 LUFS under music, normalised in ffmpeg.

## 8. Granularity at a glance

| Thing | Granularity |
|---|---|
| Simulation time step | event-driven (SimPy); trajectory sampled ≤ 500 m per leg |
| Weather fields | hourly, 3 km (NORA3) / 800 m (NorKyst, WAM); interpolated linearly in time at render |
| Particles | 2–6k per frame (square format), life 30 min sim time, respawn staggered |
| Sea lanes | 300 m grid, 60 m clearance (fjord); planned 50 m grid near quays |
| Terrain | tiers in §2 |
| Video | 30 fps; square 1080², vertical 1080×1350, wide 1920×1080; drafts 640×360 |
