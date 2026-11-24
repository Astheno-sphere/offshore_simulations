"""Shot 1 still (Irina): S-92 on the platform helideck, JONSWAP sea beyond.

The sea is seeded from a real NORA3 hour (hook hour 2011-12-18T01:00, Hs 4.00 m,
Tp 12.3 s — see coordination/reports/shot1-sea-hour.md). The platform + S-92
come from offsim.blender.shot.helideck_spec(); the flat bridge sea is dropped
to -3 m (below the wave troughs) so it reads as the distant sea, not a cut
through the waves. Camera is the SHOTBOOK dolly start: 38 m out, 40 mm, 4:5.
The burned-in line ("One helicopter fewer.") is a HyperFrames card, not part
of this still.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from offsim.blender.shot import helideck_spec  # noqa: E402
from offsim.physics.jonswap import Sea  # noqa: E402
from tools.molde_peak_shot import _write_glb  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
HOOK_HOUR = "2011-12-18T01:00"
HOOK_HS_M = 4.00
HOOK_TP_S = 12.3
HOOK_SEED = 20111218
SEA_EXTENT_M = 800.0
SEA_GRID = 160
SEA_HEX = "#14424f"


def _sea_mesh(sea, out_path, extent_m=SEA_EXTENT_M, n=SEA_GRID, t=0.0):
    """Two meshes by wave height, so the swell reads as tonal bands: the flat
    toon shader quantizes away the gentle slope shading of a 4 m sea, and a
    single-colour mesh renders as a flat plane. Crests (z > +0.5 m) lighter,
    troughs darker; the split is the wave height itself, nothing invented."""
    X, Y, Z = sea.grid(n, n, extent_m, t)
    xs = (X - extent_m / 2.0).ravel()
    ys = (Y - extent_m / 2.0).ravel()
    zs = Z.ravel()
    verts = [[float(x), float(y), float(z)] for x, y, z in zip(xs, ys, zs)]
    crest, trough = [], []
    for j in range(n - 1):
        for i in range(n - 1):
            a, b = j * n + i, j * n + i + 1
            c, d = (j + 1) * n + i, (j + 1) * n + i + 1
            for tri in ((a, b, d), (a, d, c)):
                zm = (zs[tri[0]] + zs[tri[1]] + zs[tri[2]]) / 3.0
                (crest if zm > 0.5 else trough).append(list(tri))
    _write_glb(verts, crest, out_path.parent / "sea_crest.glb", "sea_crest")
    _write_glb(verts, trough, out_path.parent / "sea_trough.glb", "sea_trough")
    return {"crest": out_path.parent / "sea_crest.glb",
            "trough": out_path.parent / "sea_trough.glb"}


def build_scene(out_dir, hs_m=HOOK_HS_M, tp_s=HOOK_TP_S, seed=HOOK_SEED,
                hour=HOOK_HOUR, resolution=(540, 675), samples=8):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    sea = Sea(hs_m, tp_s, seed=seed)
    spec = helideck_spec(out_dir, resolution=resolution, samples=samples)
    # JONSWAP sea mesh, centred on the platform (the spec puts the platform at 0,0).
    meshes = _sea_mesh(sea, out_dir / "sea_mesh.glb")
    spec["assets"].append({"name": "sea_crest", "glb": str(meshes["crest"]),
                           "position": [0, 0, 0], "heading_deg": 0, "scale": 1.0,
                           "colours": {"sea_crest": "#2a6a7a"}})
    spec["assets"].append({"name": "sea_trough", "glb": str(meshes["trough"]),
                           "position": [0, 0, 0], "heading_deg": 0, "scale": 1.0,
                           "colours": {"sea_trough": "#0f3a45"}})
    spec["sea"] = {"level_m": -3.0, "size_m": 6000, "colour": "sea"}
    spec["palette"] = {"sea": SEA_HEX}
    # Dolly start: 38 m from the helideck centre, same bearing as the spec camera.
    cam = np.array(spec["camera"]["position"], float)
    look = np.array(spec["camera"]["look_at"], float)
    d = cam - look
    d = d / np.linalg.norm(d) * 38.0
    spec["camera"]["position"] = [round(float(v), 2) for v in (look + d)]
    spec["camera"]["lens_mm"] = 40
    spec["meta"] = {"hour": hour, "hs_m": hs_m, "tp_s": tp_s, "seed": seed,
                    "sea_hs_from_spectrum_m": round(sea.hs_from_spectrum(), 3)}
    (out_dir / "scene.json").write_text(json.dumps(spec, indent=2))
    return {"spec": spec, "sea_hs_m": sea.hs_from_spectrum()}


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "out" / "shot1"
    res = build_scene(out)
    print("sea Hs from spectrum:", round(res["sea_hs_m"], 3), "m (hour Hs 4.00)")
    print("scene.json:", out / "scene.json")
