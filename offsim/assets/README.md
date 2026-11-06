# Assets

| Folder | What | Licence | Source |
|---|---|---|---|
| `sprites/` | Cartoony 3D-style PNGs (256²) for moving agents: ship, ferry, helicopter, boats, worker, person, trucks, oil drum, fuel pump, battery, factory, package | MIT (`sprites/LICENSE-fluentui-emoji.txt`) | [microsoft/fluentui-emoji](https://github.com/microsoft/fluentui-emoji), 3D style, unmodified |
| `models/` | Low-poly glTF: `psv`, `ferry`, `platform` (helideck, flare), `wind_turbine` | MIT (ours) | `models/make_models.py` (Blender bpy, runs here) |

Sprites face left (bow to the west); the renderer mirrors them when an agent heads east.
Add a sprite: drop a PNG here, map an agent class to it in `offsim/style.json` → `sprites`.
Add a model: a function in `make_models.py`, re-run it, map a site kind in `style.json` → `models`.
More free sources (CC0 boats, Noto/OpenMoji icons, Poly Haven): `python tools/catalog_build.py --find assets`.
