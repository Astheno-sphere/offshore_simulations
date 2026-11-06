# Test log (manual runs that are not automated tests)

Evidence for catalog entries whose status is `tested` but which no automated test exercises. Each line: date ·
catalog id · environment · what ran · result. Automated evidence lives in `tests/` and CI instead.

| Date | Catalog id | Environment | What ran | Result |
|---|---|---|---|---|
| 2026-11-06 | blender-bpy | Claude workspace, bpy 5.2, 2 CPU, no GPU | 640×360 test scene, three engines | Workbench 1.4 s, Cycles CPU 16 spp 4 s, EEVEE 47 s per frame |
| 2026-11-06 | blender-bpy | same | `offsim/assets/models/make_models.py` | 4 glTF models written (psv, ferry, platform, wind_turbine) |
| 2026-11-06 | remotion | Remotion 4, system Chrome | 60-frame composition via `npx remotion render --browser-executable` | MP4 written |
| 2026-11-06 | manim | Manim 0.22.1 + apt libpango1.0-dev, dvisvgm, LaTeX | MathTex objective scene `-ql` | MP4 written; fails without dvisvgm |
| 2026-11-06 | pyvista | PyVista off-screen (VTK) | read `platform.glb`, screenshot | PNG written, no display needed |
| 2026-11-06 | hyperframes | HyperFrames 0.9.19, `HYPERFRAMES_BROWSER_PATH=/usr/bin/google-chrome` | blank example, `render -q draft` | 10 s 1920×1080 MP4; first attempt failed on GSAP CDN (blocked) → vendored GSAP fixed it |
| 2026-11-06 | gsap | GSAP 3.15 from npm inside HyperFrames card | `hyperframes lint` on `kpi_card` | 0 errors |
| 2026-11-06 | deckgl | deck.gl 9, Chrome + SwiftShader | TripsLayer/IconLayer/ScenegraphLayer/PathLayer frames; `render.py --check` in CI | ~8 fps at 640×360; all layers load |
| 2026-11-06 | fluentui-emoji | raw.githubusercontent download | 18 PNGs + MIT licence vendored | rendered in sprite mode |
| 2026-11-06 | osm-coastline | GitHub Actions `fetch-world` (oslofjord) | Overpass coastline → land polygons → release `world-oslofjord` | 4,753 ways; pulled and used by the demo |
| 2026-11-06 | trimesh | trimesh 5.2 | `python -m offsim.assets.lineart` | plan lines: psv 210, ferry 132, platform 66, turbine 61 |
| 2026-11-06 | ffmpeg | system ffmpeg | frames → H.264 veryfast; xfade chain defined | MP4 written |
