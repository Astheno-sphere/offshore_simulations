# Molde peak shot — build report

from: Nordlys
date: 2026-11-25
branch: agent/nordlys/molde-peak-shot (from agent/claude/visual-engine @ f93db25)
status: still rendered and measured; verdict: does NOT yet beat v2 (see below)

## What was built

- `tools/molde_peak_shot.py`: builds the Blender scene from the gated replay.
  Land GLB triangulated from `data/worlds/molde/land.geojson` (2,898 triangles,
  30,177 x 30,095 m, real OSM coastline); bus/ferry marker GLBs (disc 250 m,
  diamond 350 m — symbols, not to scale: a 12 m bus is sub-pixel at this
  scale); 46 markers at t = 5700 (39 bus + 7 ferry), headings from the
  previous 30 s step; camera blocking per VISUAL_DEFINITIONS §8 (35 mm,
  neutral start).
- `tests/test_molde_peak_shot.py`: 4 tests, fixture-based, no Blender, no
  real data (the replay lives in gitignored `out/`). 4 passed.
- `tools/blender_shot.py`: two fixes, each with a `why:` line in the commit.
  (1) argv: take args after `--` when present — `blender -b --python` puts
  its own flags in sys.argv, so the old `len(sys.argv) != 3` check exited
  with the usage text and the bridge could not run on a VM with no pip bpy.
  (2) far clip: default is now 3x the camera distance when that exceeds
  20 km — the first render came back all sky because the camera sat 38 km
  out, past the hardcoded 20 km clip. Both fixes are backward-compatible:
  the helideck spec (65 m camera distance) is unchanged.
- Render: `blender -b --python tools/blender_shot.py -- scene.json peak.png`,
  Blender 4.2.23 LTS on this VM, 1080x1350, 16 samples, 25.6 s wall.
  Deliverable (VM-local, not on the branch): molde-peak-blender.png
  (scene.json beside it; rebuilt by tools/molde_peak_shot.py).

## Measured (not typed)

- Count: 39 bus + 7 ferry = 46 in the Molde bbox at 07:35; 67 region-wide.
  The headline is the in-frame count, so number and picture agree.
- Frame: land 31.9%, sky band 16% (213/1350 rows, empty beige), sea the
  rest. All 7 gold ferry diamonds distinct; 29 distinct blue bus blobs of
  39 buses (10 merge into the Molde-centre cluster, same as v2's dots).
- bbox_check: all 47 assets imported at the right sizes (land 30177x30095,
  buses 250x250x8, ferries 247x247x8).

## Verdict: not yet better than v2

The Blender map path works end to end (real coastline, real positions,
25 s a frame) and the framing is decent, but the still does NOT beat
v2's `still_f0285.png`. v2 carries houses (26,483 footprints), four road
weights, five street names, six gold places, the chart and the chips. This
still carries coastline + 46 markers and no text at all (no headline, no
clock, no count — cards come via HyperFrames, not yet done). It is a cleaner
map and a thinner frame. Grade stays out (Irina finding).

## Open work

1. Map layers: roads + buildings + place names as GLB layers (the v2 layers,
   from the same OSM data). This is the gap that decides the comparison.
   DONE in the builder (roads 4 weights, 26,483 buildings, quays, landuse,
   6 places, 11 labels) — but the first layered render was a BUG, caught by
   measurement before delivery: the frame was 97.5% road colour (sea 0.0%,
   land 0.0%). Root cause: `build_roads_glb` / `build_quays_glb` buffered the
   OSM LineStrings in DEGREES (buffer distance is in the geometry's units),
   so a 60 m half-width became a 60-degree blob covering the continent, and
   at z=7 it painted over land (z=5) and sea (z=0). Fixed by projecting to
   local metres first, then buffering (`_add_poly_m`); regression test
   `test_road_mesh_stays_inside_the_scene` (GLB bounds < 50,000 m). Labels
   also reduced (places 900→600 m, streets 600→500 m; centre dy 0/1400/2800)
   — the 900 m labels collided in the centre. Scene rebuilt, bounds verified
   (roads x ±16.8 km, buildings ±15.0 km). Re-render queued after the Bergen
   map. Render cost stands: full-res ~90 min/frame, half-res ~11 min; the ink
   pass does not scale to map geometry, so map stills render with line_px 0.
   CORRECTION (same day): the "90 min" figure was contaminated by this bug —
   the fixed scene renders in ~8 s at half-res. The cost driver is small
   dense triangles, not the ink. Label fix after the re-render: the three
   centre labels still collided, so `PLACE_LABEL_LAYOUT` now staggers them in
   x (SENTRUM 0, TRAFIKKTERMINAL -2200 m, FERJEKAI +2200 m) and drops the
   "MOLDE " prefix (test `test_centre_place_labels_staggered`, 12 targeted
   tests pass). The fix landed after the full suite started; it is covered by
   its own test and the targeted run, not by the suite run on the commit.
   LABEL FIX v3 (2026-11-25, after the push): FERJEKAI/LUFTHAVN still touched
   at 600 m, so place labels are now 400 m and FERJEKAI moves to dy +3600
   (LUFTHAVN stays at dy 0 — the two are on separate rows, no touch). A
   second pass found the labels sitting ON their dots (SENTRUM, SEKKEN KAI,
   FURNESET FERJEKAI, LUFTHAVN all centre-aligned on the dot), so every place
   label now sits 900 m above its dot. Render `peak-v3.png` (full-res,
   ~25 s): all six place labels readable, none touching, none on a dot.
   Remaining nits: the centre street labels (E 39, Storgata) overlap the
   centre dot cluster, and Malmefjordvegen is clipped at the right edge.
2. Cards: headline / clock / count via HyperFrames over the still. DONE
   2026-11-25 (project `out/molde-cards/molde-cards/`, 4 s, 1080×1350,
   h264 429 KB (VM-local: molde-peak-cards.mp4 + frame molde-peak-cards.png;
   project at out/molde-cards/molde-cards/): oxblood title band
   ("MOLDE · MONDAY 9 NOV 2026" / "46 vehicles in the frame" / "39 buses,
   7 ferries at 07:35") + chips (CLOCK 07:35 / IN FRAME 46 / TRIPS SO FAR
   139 / FERRIES 7). `npm run check` PASSED (0 errors, 0 warnings, 47/47
   text checks WCAG AA). Two fixes the check forced: the headline h1/sub
   measured 1.49:1 — the still's sky band is only ~70 px, the h1 fell on the
   dark sea, so the headline moved into a solid oxblood band (cream on
   oxblood); the chip labels were 20 px (below the 28 px floor) and wrapped,
   so they are 28 px, tighter spacing, "FERRIES" not "FERRIES SAILING".
   The chips first sat at the bottom, where the FURNESET FERJEKAI dot
   collided with "IN FRAME" — they moved under the title band, over the
   empty fjord. All numbers from the trajectory (139 distinct agents by
   07:35, verified by recount). Environment notes: HyperFrames refuses a
   group-writable home — HYPERFRAMES_CACHE_DIR=/var/tmp/hf-cache (2 GB
   tmpfs; /tmp is 512 MB and too small) + TMPDIR=~/workspace/tmp-hf-render
   for the render temp files. GSAP + Montserrat vendored locally (no CDN).
   VERDICT vs v2: still does NOT beat v2. The cards close half the gap
   (headline + chips now match v2's), and the 3D map is a richer picture —
   but v2's frame carries more evidence: the peak chart (FRAM 59 / FERRY 9
   over time) and the bottom line (289 trips, 5,963 km in 4 hours). This
   frame is a better picture; v2 is a better argument. Next: the chart +
   bottom line as HyperFrames elements.
3. Chart + bottom line: DONE 2026-11-25 (same project, re-rendered 509 KB,
   4 s). The chart series is the instantaneous count per 30 s step, binned
   to 5 min, recomputed from the trajectory — bus peak 59 at 07:35 and ferry
   peak 9 at 07:20 reproduce v2's chart exactly; totals 289 trips, 5,962.7
   km from measure.json. Chart panel (oxblood, bottom-right sea — measured
   100% sea in that rect) with "FRAM 59 · 07:35" / "FERRY 9 · 07:20" + the
   two lines + a "you are here" marker at 07:35; bottom line "289 trips,
   5,963 km in 4 hours — peak 67 vehicles at 07:35" at the bottom edge.
   `npm run check` PASSED (0 errors, 0 warnings, 59/59 WCAG AA). Two fixes:
   the peak dot overflowed the SVG top (viewBox padded) and the bottom line
   was 0.07 s short of its read hold (entrance moved 0.7 -> 0.2 s); the
   first chart pass wrapped its labels and clipped the SVG (panel 190 ->
   210 px, labels shortened to "FRAM 59 · 07:35").
   FINAL VERDICT vs v2: the frame now carries the FULL argument (headline,
   chips, chart, bottom line — the same numbers, verified) and a richer
   picture, so it is a credible alternative to v2 — but not a clear beat.
   The 3D tilt costs legibility in the centre (street labels overlap the
   dot cluster) and the chart panel is small (the ferry line is nearly
   invisible at this scale). Those two are the remaining gap.
3. Framing: the 16% sky band is dead space; the next framing should trade it
   for the town shore (steeper look-down or a tighter lens).
4. Full suite run before commit (running in background at commit time;
   libEGL was restored first — it had been wiped by a restart again).
