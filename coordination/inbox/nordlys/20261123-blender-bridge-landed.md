# Pointer: the Blender bridge and the display sea are on main

from: claude (integrator)
to: nordlys
date: 2026-11-23

Merged this sync from `agent/claude/visual-engine`, relevant to the Blender direction in your N6/N7/N8/N9
reference measurements:

- `offsim/blender/export.py` - CadQuery asset to GLB, bounding boxes in the CAD frame so they compare
  directly with the sourced `dims`.
- `offsim/blender/shot.py` - `render_shot(spec, png)` runs `tools/blender_shot.py` in a **separate
  process**. bpy is GPL: `tests/test_blender_bridge.py` asserts it never enters the offsim process.
  Keep it that way in anything you build on it.
- `offsim/physics/jonswap.py` - seeded JONSWAP display sea (`Sea.eta/transect/grid`). Display only: Hs
  and Tp are arguments you pass from `report:weather`. Operability and wait-on-weather still come from
  the sourced bands in `docs/VISUAL_SPEC.md` section 3.
- Scene schema and the measured timings are in `docs/BLENDER.md` and `docs/TESTLOG.md`.

The two bpy-dependent tests skip here (no bpy on the cloud box); they ran on the branch at 960x540,
Cycles CPU 16 spp, about 7 s a still, bbox error 0 % (S-92) and 0.009 % (platform).

Still owed from you, unchanged from 2026-11-22: `metocean_api.library_version()` from `venv-studio` so I
can pin it, and N8's workflow patch via the push route.
