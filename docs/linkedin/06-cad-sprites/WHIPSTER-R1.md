# Whipster — CAD sprite sheet, round 1: FAIL

Checked: the sheet + s92-side / s92-front stills at full size. The bus passes on its own.
The sheet fails because of the helicopter.

## The bug (not a look issue — real geometry)

**The main rotor blades are on the ground.** In the side view the two long horizontal
lines at the BOTTOM, below the wheels, are the rotor blades: the blade solid was built
in the XY workplane at z=0 and never translated up to the rotor plane (ROTOR_Z 5.05).
The mast and head are at the right height; the blades sit at z 0–0.07. QA passed
because the bbox z-max comes from the head (5.15), so nothing caught it. A helicopter
whose rotor is at ground level is not a helicopter.

## The look faults (helicopter)

1. **Cabin windows read as black tiles.** Five identical dark squares in a row — the
   v10 "identical white squares" problem, now in dark. Too big (0.85 x 0.70), too flat,
   and glass vs glass_dim is invisible on paper.
2. **Cockpit glazing is a dark blob.** The nose glass spans x 6.3–9.55 — most of the
   nose — and reads as a black patch, not glazing.
3. **Front view reads as a face.** The big dark windshield trapezoid on the circular
   fuselage is a visor on a face. Too wide, too dark, dominates the view.
4. **Wheels are black blobs.** The wheel fill (#241a1c) covers the whole circle; the hub
   is invisible. Same on the bus. A wheel that reads as a black dot is a toy wheel.
5. **The fin reads as a separate brown sail.** Its fill (house_mid) is darker than the
   fuselage (house), so the tail looks bolted on.
6. **Tail rotor reads as a diamond smudge** on the fin, not a rotor. Re-examine after
   the rotor fix; if it still reads wrong, simplify it.

## What reads right (keep)

- The sheet itself: layout, labels, scale bars, dims from QA, assumption note. Clean.
- Helicopter side: fuselage loft, tail boom, loft section seams read as frame stations.
- Helicopter top + three-quarter: read as a helicopter. Bus side/front/top/three-quarter:
  read as a bus (wheels aside).
- No white squares, no stick-men. The v10 lessons held.

## Fixes for round 2

1. Blades to z 5.01–5.08 (translate the blade solid); verify from the rotor part bbox
   AND from the still — the blade line must sit at the top of the side view.
2. Cabin windows smaller (0.65 x 0.60), uniform dark glass, visible gaps.
3. Cockpit glazing smaller (x 7.2–9.2, z 2.25–3.05), mullions kept.
4. Front windshield narrower (y ±0.9, z 2.3–3.15).
5. Wheels outline-only (drop "gear"/"wheels" from the fill maps) — the HLR circles +
   hub discs carry them; no black fill.
6. Fin fill = "house" (same as the fuselage).
