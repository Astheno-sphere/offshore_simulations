# Visual direction: Blender as the 3D engine, path chosen per shot (read before touching visuals)

from: Claude (cloud session, integrator)
to: nordlys (desktop: read too)
date: 2026-11-22

Owner verdict: our film visuals are far below Abhinav grade (no real physics, flat cinematography, toy CAD assets).
The last scout graded us against our own rules, which was the wrong yardstick. New direction, not yet built:

1. Blender (bpy, GPL, separate process, catalog `blender-bpy`, tested) becomes the 3D, physics and camera engine.
   Our validated `report.json` and trajectories are scene data into it. HyperFrames keeps typography and cards.
2. Path is dynamic per shot, never one fixed route: a shot spec names its engine (`panel` 2D, `cad` hidden-line,
   `blender` 3D). Cheap/draft shots run here or on the laptop; heavy ones (Cycles, ocean, fluid, 1080p) are fired on
   the `render` workflow. Nothing hard-codes the route; the shot decides.
3. Physics rule: sea state comes from a seeded spectrum (JONSWAP) driven by `report:weather` Hs and Tp, rotor
   downwash from an analytic disk field we write. Display never edits truth; every number on screen is still a
   `report:` ref.
4. Absorbed so far: `third_party/pocket-city` (MIT, wrapper `skills/pocket-diorama`). It is a model of the layered
   visual infrastructure to copy in spirit: scene data -> parts kit -> engine -> render check loop. Style stays a
   second language, establishing shot only.
5. First slice (owner go pending on build): S-92 final approach to a helideck, 6 s 1080p, Cycles CPU, Irina scene.
   Blockers known: bpy needs Python 3.13 (our image is 3.12), no 1080p timing yet, helicopter geometry must come
   from our sourced CadQuery solids exported as glTF (no verified permissive model found).

What you can do now, without waiting: send your reference-video measurements (N7/N9 exams) as a short table in
`coordination/reports/`: camera moves per shot, lens/DoF cues, light direction and colour temperature, motion
timings. They become the numeric targets. Do not commit frames or video.
