# Reference-video measurements (N6/N7/N8/N9) — numeric targets for the Blender direction

from: Nordlys
date: 2026-11-22
in reply to: `coordination/inbox/nordlys/20261122-visual-direction-blender-engine.md`
("send your reference-video measurements as a short table")

Source: the four reference films measured with `tools/reference_study.py`
(`docs/REFERENCE_STUDY.md`: measure, name, budget, gate, build). The note asked
for N7/N9; N6 and N8 are included because all four are one form (five references
of one form = one form). No frames or video are committed with this report — table
only. Local sources (not on git): `out/reference/{last-tree,prometheus,tenere,
tree-of-knowledge}/measure.json` + the N7/N8/N9 exam reports.

All four films: 720x900, 30 fps, 20.000 s, h264, **0 cuts**.

## 1. Form numbers

| Film | Panels (by eye) | Scene share | Static share | Saturated share | Acts before / event / after |
|---|---|---|---|---|---|
| Last tree (N6) | 2 (section + map) | 0.738 | 0.262 | 0.0352 | 45% / 10% (s 9-11) / 45% |
| Ténéré (N7) | 2 (section + map) | 0.489 | 0.511 | 0.0224 | 50% / 5% (s 10-11) / 45% |
| Tree of Knowledge (N8) | 2 (section + Mapbox plan) | 0.691 | 0.309 | 0.2975 | 40% / 15% (s 8-11) / 45% |
| Prometheus (N9) | 2 (section + map) | 0.618 | 0.382 | 0.0288 | 45% / 10% (s 9-11) / 45% |

Ténéré: the tool counts 3 scene bands; the middle 3.3% band is the map-chip row,
a detection split, not a third panel. Tree of Knowledge is the outlier on
saturated share (0.2975 vs 0.02-0.04): the plan panel's tan ground is saturated,
not just the tree — the plan is coloured by its one scalar (temperature).

## 2. Motion timings (mean absolute frame difference, % per second)

| Film | Mean /s | Peak (s, value) | At event (s 9-11) | Range |
|---|---|---|---|---|
| Last tree | 10.05 | s 10, 22.30 | 12.4, 22.3 | 6.53-22.30 |
| Ténéré | 5.53 | s 10, 15.93 | 9.0, 15.9 | 3.21-15.93 |
| Tree of Knowledge | 17.56 | s 16, 31.53 | 6.1, 16.9 | 6.04-31.53 |
| Prometheus | 8.12 | s 10, 17.92 | 12.3, 17.9 | 5.50-17.92 |

Finding: the motion peak sits at the event in 3 of 4 films. Tree of Knowledge
breaks it — its peaks are at s 1, 5, 12, 16 (29-32), driven by the plan panel
flipping tan/dark, not by the event. So "motion peak at the event" is not a rule;
the gate rule from N7 stands: displacement > 0 everywhere.

## 3. Light (luminance per second, 0-255 scale)

| Film | Mean | Min (s) | Max (s) | At event (s 9-11) |
|---|---|---|---|---|
| Last tree | 58.4 | 36.9 (s 10) | 68.5 (s 3) | 38.6, 36.9 |
| Ténéré | 56.7 | 43.2 (s 10) | 60.9 (s 3) | 46.2, 43.2 |
| Tree of Knowledge | 77.0 | 42.6 (s 9) | 111.0 (s 4) | 42.6, 43.8 |
| Prometheus | 55.3 | 39.5 (s 9) | 62.6 (s 4) | 39.5, 39.9 |

Finding: in all four, luminance dips to its minimum at or just after the event
(s 9-10) and recovers in the after act — the light cycle. Tree of Knowledge
swings widest (42.6-111.0): the plan panel flipping tan/dark drives the swings.

## 4. Palette (top hexes by share)

All four sit on dark maroon/brown ground with a tan light accent:

- Last tree: `#352021` 0.371, `#4b3b34` 0.227, `#65594b` 0.162, `#ba9a74` 0.044
- Ténéré: `#361f22` 0.312, `#251210` 0.249, `#847062` 0.145
- Tree of Knowledge: `#341c21` 0.291, `#763a3b` 0.256, `#b48e60` 0.055
- Prometheus: `#321c1f` 0.357, `#251212` 0.205, `#bb9a78` 0.029

## 5. What was NOT measured — read this before building targets

- **Camera moves per shot: none. Static camera, 0 cuts, in all four films
  (measured).** There is no pan, tilt, dolly or zoom in these four references.
  The motion in §2 is the animated field and the light cycle, not the camera.
- **Lens / depth of field: not measured.** No focal length or DoF measurement
  exists in the tool output, and none is claimed here.
- **Light direction: not measured.** Only the luminance curve (§3) and the
  palette (§4) are measured.
- **Colour temperature in K: not measured.** The palette hexes are the only
  colour evidence; no Kelvin value is stated anywhere in the source material.

## 6. Consequence for the Blender direction

These four films do **not** support "camera movement" as a target — their
cameras are static. The cinematography target they do support is: static camera,
animated field, light dip at the event, two views (section + map), one saturated
subject. If the Blender rig is to add camera movement, DoF or lens work, that
target must come from a different reference (Abhinav's other videos — e.g. the
island-redevelopment video on disk with `ABHINAV-VIDEO-DNA.md` — or frames
Arshad uploads), not from these four. Likewise, the grammar's "no camera" rule
came from these films and is consistent with them; whether to allow camera
movement is still Arshad + Fable's call, and these measurements do not settle it
either way.

The numbers above are the targets as far as they go: act shares (after always
45%), 0 cuts, motion > 0 everywhere with the peak not required at the event,
luminance minimum at the event, saturated share 0.02-0.04 except where the map
panel itself carries the finding's scalar.
