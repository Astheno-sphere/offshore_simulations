# CAD sprite sheet — helicopter + bus (2026-11-10)

**Sheet:** `cad-sprites.png` — 3000×2120 px (A4 landscape at ~250 dpi), 2 assets × 4
orthographic views, one scale per asset. Per-view stills in `stills/` (1200×900 each).
CAD sources with this report: `s92.step` (560 KB) + `bus.step` (244 KB).

## What was built

Two new CAD assets, following the PSV route exactly (cadquery solid → OpenCASCADE HLR →
skia line drawing, same line-weight hierarchy 2.2 / 1.2 / 0.7). Both are stylised: no
manufacturer drawing was sourced, so **every dimension is `assumption: true`** and the
sheet says so. A paper film may not use either asset until a drawing is sourced.

**S-92-like offshore helicopter** (`offsim/assets/cad/air.py`, 10 parts): lofted fuselage +
tail boom from 8 elliptical sections (ruled loft — a smooth loft overshot the design width
by 10%, measured 3.31 m vs 3.0 m, so the ruled loft's section seams read as frame stations
instead), swept tail fin + stabiliser, 4-blade main rotor stopped fore/aft + athwart,
tail rotor on the port fin, sponsons + tricycle gear, twin engine deck with exhausts,
rescue hoist starboard, pitot + antenna. Cockpit glazing is 2D dark glass, not in the
solid (the v10 PSV lesson). Dims (QA-measured): length 20.90 m (airframe, fuselage part —
the fused bbox is 21.50 m overall incl. tail rotor disc and pitot), rotor Ø 17.20 m,
height 5.15 m, fuselage width 3.00 m. Edge density 153.9 m / 142 polylines.

**FRAM 701 city bus** (`offsim/assets/cad/land.py`, 5 parts): slab-sided body from a spline
side profile (sloped windshield, rounded roof corners), two axles with wheels + hub discs,
door mirrors (the only parts wider than the body — width is measured on the body part),
roof AC pod, bumpers. Side windows, doors, destination display and lights are 2D dark
glass / faint panel lines, not in the solid. Dims (QA-measured): length 12.20 m, width
2.55 m, height 3.15 m. Edge density 44.2 m / 33 polylines.

**New projection views** (`offsim/assets/cad/drawing.py`): `project(shape, view)` now takes
side / front / rear / top / three-quarter, all through the same HLR path (the default
"side" is byte-identical to the old projection, so the gale film is untouched). The
three-quarter view looks from front-starboard-above, nose right — it shows the rescue
hoist. QA (`offsim/assets/cad/qa.py`) gained a generic bbox-axis table plus per-part
measurement (fuselage width, body width).

**The sheet** (`offsim/assets/cad/sheet.py`, `tools/cad_sprites.py`): light paper
(#E8E1CF) with dark ink — a drafting document, not a film frame, so the polarity flips
from the films' dark ground; the fills are the same maroon family in pale tints. Every
view labelled, every asset named, scale bar per asset (S-92 29.6 px/m, bus 50.9 px/m),
dims from QA, assumption note in the footer. Measured per view (prims / edge length):

| asset | side | front | top | three-quarter |
|---|---|---|---|---|
| S-92 | 371 / 358.8 m | 385 / 228.7 m | 377 / 392.2 m | 550 / 366.3 m |
| bus | 142 / 192.8 m | 179 / 97.8 m | 193 / 139.0 m | 236 / 133.7 m |

## Gates

CAD QA passes for both assets (all dims within 1%, all dims assumed). Full test suite:
**399 passed, 3 skipped** (was 393 at v10; +6 new sprite tests, incl. a regression test
for the round-1 rotor bug). No gated run needed — the sheet is an asset, not a film.

## Whipster

- Round 1 FAIL: the main rotor blades were built at z=0 and drew on the ground (a real
  geometry bug QA could not catch — the bbox z-max comes from the rotor head); cabin
  windows read as black tiles; cockpit glass was a black patch; the front view read as
  a face; wheels were black blobs; the fin read as a separate brown sail.
- Round 1 → 2 fixes: blades translated to the rotor plane (z 5.01–5.08) + a regression
  test; windows smaller with gaps; glazing shrunk; wheels outline-only; fin in the
  fuselage tone.
- Round 2 PASS. Nits recorded, not rebuild triggers: tail rotor reads as a small
  diamond smudge on the fin; windows uniform dark squares; the front view faintly
  suggests a face at a glance; wheel octagons visible at full size; the bus top view
  is the emptiest cell.

## Timings

Sheet build ~15 s per run (assets + HLR + render + STEP export). Full suite 133.8 s.
The VM wiped libEGL/libGL mid-task (the known failure mode) and the apt cache was empty
this time, so the restore cost ~20 min wall (apt-get update 70.8 MB in 17 min at
69 kB/s, then install; one wrong package name, `libgl-dispatch0`, dropped — it lives
inside libglvnd0). Recorded here so the next wipe is a one-command fix:
`sudo apt-get install -y libegl1 libgl1 libglvnd0 libglx0`.

## Unverified / known limits

- His eyes on the sheet (my whipster check is on the stills + sheet).
- The 3/4 views carry linework only (no 2D glazing — not honest from rects in that
  projection). The bus has no rear view on the sheet (rear details exist in land.py;
  the sheet shows side/front/top/three-quarter per the brief).
- Nothing posted, nobody contacted, nothing committed (gh not logged in on this VM).
  Uncommitted working-tree work grows: air.py, land.py, sheet.py, drawing.py views,
  qa.py axes, registry.yaml, tests/test_cad_sprites.py, tools/cad_sprites.py.

## Train vs bus

The brief asked: build the bus first, but say if a train would serve better. It would
not, for the work on the table: the bus is the Molde film's vehicle (FRAM 701 is in the
replay — 231 bus trips that morning), and the helicopter is the next film's vehicle
(Gribkovskaia Bergen program). No current film needs a train — Molde has no railway
station, and the nearest rail (Raumabanen, Åndalsnes–Dombås) belongs to a future
intercity story, not this one. A train asset would be the next one to build if that
story opens.
