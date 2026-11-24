# Shot 3 — Flesland massing inset (still)

Date: 2026-11-25. Branch: `agent/nordlys/molde-peak-shot` (second commit,
after the `674fcd6` push). Tool: `tools/flesland_massing.py` + 2 tests.
Data: `out/flesland-massing/buildings.json` (9,932 buildings in the 5 km box).

## What it is

The shot-3 opening frame: the terminal massing around the helipad, camera
east-southeast of the pad looking west, 40 mm, low oblique. The push to the
pad and the match cut to the map are film work, after the validated report
(routes come from `plan.routes`).

## Counts (QA gate: buildings shown = buildings drawn)

- Inset (1.5 km around the pad): **552 buildings** — 97 measured (`height`
  tag, cream), 8 assumed (`building:levels` x 3 m, tinted tan), 447 flat
  (no height mapped — flat footprint, no invented height).
- Tallest near the pad: 30 m (unnamed), then 16 m; Clarion Hotel Bergen
  Airport 15 m. The terminal buildings near the pad are 9–12 m — low, which
  is why the massing reads as a low skyline, honestly.

## The pad

The pad is the **mapped OSM helipad polygon** at (5.2247, 60.2973) on the
Bergen airport apron — not the instances.yaml heliport (5.2181, 60.2934,
assumption, ~700 m away) that the service-area map uses. The difference is
sub-pixel on the map, so the match cut stays consistent. The other mapped
helipad polygon is at (5.2281, 60.299); the only Point helipad near Flesland
in the file is Hovland Hovedgaard (5.2449, 60.2624), a different heliport.

## Framing iterations (all half-res, 540x675, 8 samples, ~9 s each)

1. Camera SW, 2100 m out, 25 deg: ground was a disc — a floating island,
   the banned tell. Buildings sub-pixel. Rejected.
2. Real Bergen land clipped to the inset box, camera SW 900 m: buildings
   due WEST of the pad were out of frame (they cluster at bearings -86 to
   -102 deg). Cream measured 0.0% in frame. Rejected.
3. Camera flipped to the SE, looking west: terminal blocks visible on the
   horizon. FLESLAND clipped right, HELIPAD label huge and clipped left.
4. Camera lower (120 m), look past the pad to the terminal: massing reads,
   pad reads, but FLESLAND still clipped and the sky was 25%+.
5. **Accepted (render6):** camera [pad+350, -200, 180], look at [pad-250,
   +50, 0]; one label (FLESLAND, 80 m, fits); pad r=30 + halo r=45;
   HELIPAD text dropped — the gold disc is the helipad, it needs no name.
   Shares: land 57.6%, sea 12.0%, sky 7.6%, flat 5.4%, gold pad 2.6%.

## Honest gap

The tint-by-source is **not legible in the frame**: measured cream reads
0.2% (sunlit tops only); the 14.5% "tan" is mostly shaded cream — the toon
shading darkens cream into the tan band, so measured and assumed buildings
cannot be told apart by eye. The distinction survives in the data
(`height_src`, `height_assumption`) and in the counts above, not in the
pixels. If the film needs the tint to read, the assumed tint needs more
contrast (or the key light moved to the buildings' south faces). The massing
is context, not the argument, so this is recorded, not blocking.

## Tests

`tests/test_flesland_massing.py`: 2 passed (extrude prism geometry; scene
counts 1/1/1 + tint colours + pad position). Full suite running detached
before commit (AGENTS.md house rule); counts to be filled in on commit.

## Open

- The push (camera move) and the leg lighting need the validated report.
- The 30 m building (tallest near the pad) is unnamed in OSM — it reads as
  a block, not a named landmark.
