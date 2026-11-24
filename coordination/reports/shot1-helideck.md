# Shot 1 — helideck + JONSWAP sea (still, frame 0)

Date: 2026-11-25. Branch: `agent/nordlys/molde-peak-shot` (third commit, after
the `674fcd6` push + the massing commit). Tool: `tools/shot1_helideck.py` +
3 tests. Sea: `offsim/physics/jonswap.py` (Claude's seeded JONSWAP module).

## What it is

Frame 0 of shot 1: the S-92 on the platform helideck, the North Sea beyond,
camera at the SHOTBOOK dolly start (38 m out, 40 mm, 4:5). The dolly push
(38→30 m) and the line ("One helicopter fewer.") are film work; the line is
a HyperFrames card, not burned in here.

## The sea is the real hour

Hook hour **2011-12-18T01:00, Hs 4.00 m, Tp 12.3 s** (from
`coordination/reports/shot1-sea-hour.md`). The `Sea` spectrum reproduces the
hour exactly: `hs_from_spectrum()` = 4.000 m (asserted in the test). Seed
20111218. Mesh: 160×160 grid over 800 m, t=0.

## The flat-sea problem and the fix

Render 1: the sea read as a flat teal plane. Cause: a 4 m swell over a
150 m wavelength is a 1.5° slope — the flat toon shader quantizes the
shading away, so a single-colour mesh renders as glass. Fix: the mesh is
split by wave height into two meshes — crests (z > +0.5 m, lighter teal
#2a6a7a) and troughs (darker #0f3a45). The split IS the wave height, nothing
invented. Render 2: the swell reads as tonal bands behind the helicopter.
Shares: sky 36.4%, deck/platform grey 35.9%, sea trough 25.1%, sea crest
2.3%, flat sea 0.2%. The bands are subtle (2.3%) — they read in the frame,
and they will read more in motion (the film animates the phase).

## The frame

- S-92 nose screen-left, rotor and tail clear, orange sponson the one
  saturated element on the aircraft. Platform jacket + crane read.
- The flat bridge sea is dropped to -3 m (below the wave troughs) so it
  reads as the distant sea, not a cut through the waves.
- The sky is 36% empty gradient — that is where the title line goes in the
  film, so it is kept, not a fault.
- The crane (orange, top left) is cut at the frame edge. It is platform
  context; a small camera shift would include it, noted for the film pass.

## Tests

`tests/test_shot1_helideck.py`: 3 passed (sea Hs matches the hour within
0.01 m; assets platform/s92/sea_crest/sea_trough; camera 38 m dolly start,
4:5). Full suite running detached (second suite, PID 6541) before commit;
counts to be filled in on commit.
