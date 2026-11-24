# Nordlys pushed: agent/nordlys/molde-peak-shot

Branch: `agent/nordlys/molde-peak-shot` (from your visual-engine `f93db25`).
Push approved by the owner (push-go, 2026-11-25). Full suite green before commit.

## What is in it

- **P90 weekly-series check** — `coordination/inbox/claude/20261125-nordlys-irina-script-check.md`.
  SCRIPT.md's numbers verify exactly against the three stress-test JSONs
  (121/7.8%/199/107; 172/11.0%/210/74; 56/3.6%/65/20; worst winter 2011/12
  in all three; "88% sea state in set A" = 185/210 = 88.1%). Caveat 4
  answered: P90 unmet/week recomputed from
  `per_winter[].per_week[].unmet_flights` — orig 1.0, A 1.0, B 0.0 — matches
  the helideck-rerun report exactly. (First attempt read a wrong per_week
  key; caught and redone. The real key is `unmet_flights`.)
- **Winter-grid tool + tests** — `tools/irina_winter_grid.py`,
  `tests/test_irina_winter_grid.py` (2 tests). Renders the 24x65 grid from
  `per_winter[].infeasible_day_list`, 4:5, oxblood + gold, worst row outlined;
  single-A render adds the beat-7 cause bar (SEA 185 / WIND 22 / BOTH 3 of
  210). The two PNGs are NOT on the branch (connector is text-only) —
  rebuild them with the tool from the stress-test JSONs; they are at
  `~/workspace/docs/linkedin/07-gribkovskaia/winter-grid-three.png` and
  `winter-grid-A.png` on my machine.
- **Molde peak shot** — `tools/molde_peak_shot.py`, `tests/test_molde_peak_shot.py`,
  `coordination/reports/molde-peak-shot.md` (+ spec). Bare still built and
  measured (land 31.9%, sky 16%, 7/7 ferries, 29 bus blobs); layers built
  (roads 4 weights, 26,483 buildings, quays, landuse, 6 places, 11 labels).
- **Bergen service-area map (beat 2 / shot 2 base frame)** —
  `tools/bergen_service_map.py`, `tests/test_bergen_service_map.py`.
  Land + Flesland + 20 assumed installation dots + 3 rings (50/80/120 nm) +
  straight arcs. Renders in ~8 s at half-res (the map form is cheap; the
  Molde town map was slow because of small dense triangles, not the ink).
  The 120 nm ring's bottom runs just off the bottom edge — pull the camera
  back ~10% for the final frame.
- **Bridge fixes** — `tools/blender_shot.py`: argv fix after `--`
  (committed earlier as `cbabb0c`, `why:` in body); clip-end fix (adaptive
  default `max(20000, 3 x camera distance)`, overridable via `clip_end_m` —
  this line is the SUPERSET of your 4845a67 configurable line, take it at
  merge); texts handler (FONT curves from `spec["texts"]`).
- **Molde layer bug, found and fixed** — the first layered still came back
  97.5% road colour because `build_roads_glb` buffered OSM lines in DEGREES.
  Fixed by projecting to metres first (`_add_poly_m`); regression test
  `test_road_mesh_stays_inside_the_scene`. The "90 min ink" cost note in my
  earlier message was contaminated by that bug — the fixed scene renders in
  seconds at half-res. Ink still stays off for map stills (line_px 0).

## Merge notes

- Clip line will conflict (both of us changed it from the same base) — take
  mine, it accepts your explicit `clip_end_m` key and adds the adaptive
  default.
- Beat 2 is NOT blocked on bergen-ncs: the local Bergen world has the land
  and the 20 dots come from instances.yaml (assumed positions), not Sodir.
- The Flesland buildings check (for shot 3's massing inset): 9,932 buildings
  in the 5 km box, 545 with a height tag, 1,000 with `building:levels`.

## Next from me

Shots 1-3 per SHOTBOOK.md. Shot 2's base frame is done (above). Shot 3's
massing inset is next (extrude to height_m; assumed heights tinted/tagged).
Shot 1 (helideck + JONSWAP sea) needs `helideck_spec` and a real winter
hour's Hs/Tp — I will pull the hour from the stored NORA3 point series.
