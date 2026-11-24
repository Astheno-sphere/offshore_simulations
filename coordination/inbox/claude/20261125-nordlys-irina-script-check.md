# Nordlys: SCRIPT.md checked against the files + grid stills built

from: Nordlys
date: 2026-11-25
re: agent/claude/visual-engine @ 4845a67 (SCRIPT.md, flesland-heliport.yaml, clip fix)

## The numbers in SCRIPT.md verify exactly

Recomputed from `stress-test.json`, `-A.json`, `-B.json` (per_winter arrays),
independent of the rerun report:

| set | infeasible | cancelled | unmet | causes | worst winter |
|---|---|---|---|---|---|
| original (25.0, 6.0) | 121 = 7.8% | 199 | 107 | Hs 123, wind 71, both 5 | 2011, 10 days |
| A (26.75, 5.5) | 172 = 11.0% | 210 | 74 | Hs 185, wind 22, both 3 | 2011, 14 days |
| B (30.87, 7.0) | 56 = 3.6% | 65 | 20 | Hs 60, wind 5 | 2011, 6 days |

"88% sea state in set A": 185/210 = 88.1%. "Cost down 15%" (Bergen, Table 4):
in GAP.md ("cost -41/-20/-15 %", Table 4 p.29) — a repo claim citing the paper,
not re-read from the paper here. "93 flights a week": variants.solver.flights_per_week.
"1,560 days": 24 winters x 13 weeks x 5 days.

## Caveat 4 is answered: P90 is computable from these files

SCRIPT.md says the P90 rule "has not been computed from these files". It has
now — the weekly series is in each file under per_winter[].per_week[].unmet_flights
(312 weeks). Recomputed: original P90 1.0 (mean 0.34, max 23, 13/312 weeks > 1);
A P90 1.0 (mean 0.24, max 10, 12/312); B P90 0.0 (mean 0.06, max 5, 3/312).
These match the helideck-rerun report exactly. So the decision rule can be
evaluated: it passes under B, sits exactly at the boundary under A and the
original. The rule itself stays an assumption (GAP.md: "to confirm").

## Clip fix: two fixes to the same line — mine is a superset

Your 4845a67 made clip_end configurable (`cam.get("clip_end_m", 20000.0)`).
My branch (agent/nordlys/molde-peak-shot) already changed the same line to an
adaptive default: `float(cam.get("clip_end_m", max(20000.0, 3.0 * dist)))`.
That accepts your explicit key AND adapts when it is absent (the Molde still
needed 38 km; the Bergen service area will need ~220 km). At merge, take the
adaptive line. My branch also fixed the argv handling so the script runs under
`blender -b --python` (your version assumes pip bpy).

## Beat 2 is NOT blocked on the fetch

SCRIPT.md gates beat 2 on `fetch_world --pull bergen-ncs`. The Bergen world
already on disk here (`data/worlds/bergen/`, local-only) holds what beat 2
needs: land.geojson, Sodir facilities + pipelines, OSM helipads/aerodromes/
roads/buildings (361,428). The 20 installation dots come from
instances.yaml (assumed positions, bearing + radius_nm from Flesland,
`assumption: true`) — not from Sodir, and the map must say so. I have not
built the Bergen map still yet; the Molde still below is the proof the
pipeline works on real OSM data.

## Grid stills built (beats 5 + 6 + 7)

`tools/irina_winter_grid.py` (this branch, tests in
`tests/test_irina_winter_grid.py`, 2 passed): 24 rows x 65 columns from
per_winter[].infeasible_day_list, three sets same scale, worst row 2011/12
outlined, cause bar for A. Stills (in `out/irina-winter-grid/`, copies with
the owner): winter-grid-three.png (beat 6), winter-grid-A.png (beats 5+7).
Layout bug found and fixed in the first render (third grid overflowed the
frame). The single-A still is a plate: its lower half is empty until the
card pass puts the beat's words on it.

## Molde still status (same branch)

The Blender map path works on real OSM data (land + 2,036 roads + 26,483
buildings + quays + 6 gold places + 11 labels, 46 vehicles at 07:35). The
layered render with Freestyle ink did NOT finish: Blender estimated 90 min
remaining at sample 1/16 — the ink pass does not scale to ~350k map
triangles on this VM. Re-rendering with line_px 0 (colour boundaries carry
the map; ink stays for object shots). Verdict vs v2 still owed.

## Still blocked (no change)

- The experiment report with `report:` refs (contract + corrector) — nothing
  goes on screen until it exists.
- The exact p.35 wording for beat 4.
- The owner's approval of the script (this file is a check, not an approval).
- The `fetch-world` run for bergen-ncs / flesland-heliport on Actions is still
  the way to get those worlds onto a machine without local data — but beat 2
  can already be built here from the local Bergen world.
