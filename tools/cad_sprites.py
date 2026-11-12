"""Build the CAD sprite sheet: S-92-like helicopter + FRAM city bus.

    PYTHONPATH=. python tools/cad_sprites.py --out ~/workspace/docs/linkedin/06-cad-sprites

Builds both assets (QA must pass), exports their STEP files, renders the sprite sheet
(2 assets x 4 orthographic views, one scale per asset) and the per-view stills, and prints
the measured manifest (prims, edge lengths, scales, QA) as JSON — the report's numbers
come from this output, never typed by hand.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from offsim.assets.cad import air_sprite as air, land_sprite as land
from offsim.assets.cad.sheet import _build_asset
from offsim.assets.cad.qa import check as _qa
from offsim.assets.cad.sheet import render_sheet


def _export_step(asset, path: Path):
    """Export the fused solid as STEP (OCP writer, via the cadquery shape)."""
    try:
        asset.shape.exportStep(str(path))
    except AttributeError:
        import cadquery as cq
        cq.exporters.export(cq.Workplane(obj=asset.shape), str(path))
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out/cad-sprites")
    a = ap.parse_args()
    out = Path(a.out)
    stills = out / "stills"
    out.mkdir(parents=True, exist_ok=True)
    stills.mkdir(parents=True, exist_ok=True)

    assets = [
        ("s92", "S-92 — OFFSHORE HELICOPTER", "Gribkovskaia fleet · Bergen program",
         air.SPRITE_FILLS, air.s92_sprite_details, air.s92_glass_3d),
        ("bus", "FRAM 701 — CITY BUS", "Kvam–Molde–Årølia · Molde film",
         land.SPRITE_FILLS, land.bus_sprite_details, land.bus_glass_3d),
    ]
    for name, *_ in assets:
        asset = _build_asset(name)
        rep = _qa(asset)
        assert rep["ok"], f"{name} QA failed: {rep['dims']}"
        assert sorted(rep["assumptions"]) == sorted(asset.dims), f"{name}: every dim must be assumed"
        _export_step(asset, out / f"{name}.step")
        print(f"{name}: QA ok, {len(asset.parts)} parts, "
              f"edge {rep['edge_density']['edge_m']:.1f} m / "
              f"{rep['edge_density']['n_polylines']} polylines")

    manifest = render_sheet(str(out / "cad-sprites.png"), assets, out_stills_dir=stills)
    print(json.dumps(manifest, indent=1, default=str))
    print("sheet:", out / "cad-sprites.png")
    print("stills:", sorted(p.name for p in stills.iterdir()))


if __name__ == "__main__":
    main()
