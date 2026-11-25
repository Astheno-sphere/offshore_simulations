# Blender bridge

Flat (toon) stills of the CAD solids, rendered by Blender (bpy 5.2, GPL) in a separate process.

## Process boundary

- `offsim/blender/export.py` builds a CadQuery asset (`offsim/assets/cad/`) and writes a GLB (one node per part, metres,
  glTF Y-up; Blender's importer restores Z-up). It returns the tight bounding box in the CAD frame, so it compares directly
  with the sourced `dims` of the asset. Output goes to `out/blender/` (gitignored).
- `offsim/blender/shot.py` `render_shot(spec, out_png)` writes `scene.json` next to the PNG and runs
  `python tools/blender_shot.py <scene.json> <out.png>` with `subprocess` (timeout). It returns seconds, resolution,
  samples and the bbox check measured on the imported objects. `helideck_spec()` builds the S-92 on the platform helideck.
- `tools/blender_shot.py` is the only file that imports bpy. `tests/test_blender_bridge.py` fails if `offsim.blender` imports it.

## scene.json

| key | meaning |
|---|---|
| `assets[]` | `glb`, `name`, `position` [x,y,z] m, `heading_deg` about +Z from +x, `scale`, `colours` {part-name substring or `default`: palette token or hex}, optional `expect_size_m` (checked, reported as `max_rel_err`) |
| `sea` | optional. `level_m`, `size_m`, `colour`, `displacement_npy` (square height grid in metres, e.g. from a JONSWAP field; flat plane if absent or missing). Kept out of Freestyle |
| `camera` | `position`, `look_at`, `lens_mm`, `sensor_mm`, optional `dof_fstop` (off by default), optional `clip_start_m` (0.1) and `clip_end_m` (20000; raise it for map shots, the Bergen service area reaches about 220 km). Static only |
| `lights` | `key`, `fill`, `rim`, each `dir` (vector pointing to the light), `kelvin`, `strength`. In the flat look they set the tonal bands and tints |
| `sky` | `top`, `bottom` tokens; vertical gradient, no HDRI |
| `palette` | token to hex, merged over the defaults in the script (`sea`, `sky_top`, `sky_bottom`, `hull`, `accent`, `steel`, `deck`, `ink`) |
| `shading` | `mode: flat` (only mode), `line_px` Freestyle ink thickness (0 turns ink off), `crease_deg` |
| `resolution`, `samples`, `seed` | default [960, 540], 16, 0. Cycles CPU, denoiser off, fixed seed |

Flat look: an emission shader whose colour steps in three bands with the normal's angle to the key light, a lift on the rim
light, no textures; Freestyle draws silhouette, border and crease lines.

## Draft here, 1080p on the workflow

Drafts and stills (960x540, 16 samples) run in the Claude workspace (2 CPUs, no GPU): about 7 s for the S-92 on the helideck.
1080p and long sample counts go to the `render` workflow (`.github/workflows/render.yml`). Not yet done: wave displacement
from `offsim.physics` (no JONSWAP module exists yet), animated cameras, any shading mode but `flat`.

## Versions
This workspace runs `bpy` 5.2.3 (Python 3.13). Nordlys's VM runs the Blender 4.2.23 LTS binary (`blender -b --python`, where Blender's own flags land in argv). Two machines, two versions: write scene scripts against the 4.2 API unless a 5.x feature is needed, and say so in the commit.
