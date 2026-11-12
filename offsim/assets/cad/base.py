"""Asset contract. Every asset is an exact solid at real scale with sourced principal dimensions.

    @register("psv")
    def build(**params) -> AssetModel

AssetModel:
    shape   cadquery.Shape (or build123d Shape) of the whole object, metres, origin and axes per AXES below
    parts   {name: Shape} named sub-solids (hull, superstructure, rotor, ...) so drawings can class/weight them
    dims    {name: {"value": float, "src": str} | {"value": float, "assumption": True}}  principal dimensions,
            e.g. loa_m, beam_m, depth_m, draught_m, rotor_diameter_m, height_m; the QA gate measures the shape
            against these (tolerance 1 %) so scale is provable
    meta    {"class": vessel|aircraft|vehicle|person|tree|building|structure, "licence": ..., "generator": module,
             "lod": 1..3, "notes": ...}
AXES: x forward (bow / nose), y to port (left), z up; origin at keel/ground on the centreline, midships or
geometric centre in x. Units metres. Moving parts (rotor, crane) are separate parts with a pivot in meta.

Rules
- Real proportions from a cited source (class drawing, manufacturer data sheet, paper table, standard). Unsourced
  dimensions are `assumption: true` and appear in the asset QA report; a paper film may not use an asset whose
  principal dimensions are all assumptions.
- LOD: 1 = silhouette-true primitives, 2 = structure (decks, windows rows, rails, legs), 3 = detail (hatches,
  railings, antennas). Films need LOD >= 2 at the size they are drawn (QA computes edge density per screen size).
- No external meshes of unknown licence. Imported models (glTF/STEP) need licence + source in meta.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

_REGISTRY: dict[str, Callable[..., "AssetModel"]] = {}


@dataclass
class AssetModel:
    shape: Any
    parts: dict = field(default_factory=dict)
    dims: dict = field(default_factory=dict)
    meta: dict = field(default_factory=dict)


def register(name: str):
    def deco(fn):
        _REGISTRY[name] = fn
        return fn
    return deco


MODULES = {  # asset name -> module that registers it (lazy, like the engine registry)
    "psv": "offsim.assets.cad.marine", "platform_jacket": "offsim.assets.cad.marine", "s92": "offsim.assets.cad.air",
    "aw189": "offsim.assets.cad.air", "bus": "offsim.assets.cad.land", "train": "offsim.assets.cad.land",
    "person": "offsim.assets.cad.land", "tree": "offsim.assets.cad.land", "building": "offsim.assets.cad.land",
    # Nordlys N1 builders (R1 reconcile): the sprite sheet / gale-film assets, all-assumed dims, different part names
    # from the repo assets above, so they are separate assets (see coordination/reports/R1.md).
    "psv_v10": "offsim.assets.cad.marine_film", "s92_sprite": "offsim.assets.cad.air_sprite",
    "bus_sprite": "offsim.assets.cad.land_sprite",
}


def build(name: str, **params) -> AssetModel:
    if name not in _REGISTRY:
        if name not in MODULES:
            raise KeyError(f"unknown asset {name!r}; known: {sorted(MODULES)}")
        import importlib
        importlib.import_module(MODULES[name])
    return _REGISTRY[name](**params)
