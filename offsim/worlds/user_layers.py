"""Your own GeoJSON as a world layer: smaller and more precise than a country-wide OSM extract.

Why: norway-latest.osm.pbf is ~1.3 GB; a world needs a few MB. Any GeoJSON you have (a municipality road file, a
port's quay layout from a paper, digitised bus stops, Kartverket/Geonorge downloads, QGIS exports) can replace or
extend an OSM layer. The engines read the same files (`data/worlds/<w>/osm/<kind>.geojson`), so no engine changes.

Rules (checked here, refused otherwise):
- CRS: WGS84 lon/lat (EPSG:4326). Other CRSs are reprojected if the file declares them; undeclared + values outside
  lon/lat ranges -> refused (likely UTM 32/33N without a CRS tag).
- Geometry and required properties per kind (KINDS below). Roads need `highway` or `maxspeed`/`speed_kph`.
- Provenance: `--src` (where it came from: dataset, page/table for papers) and `--licence` are required and written
  to `<kind>.source.json` next to the layer; the world manifest lists user layers. No source -> refused.
- Clipped to the world bbox; optional `--simplify-m` (Douglas-Peucker in metres) for heavy files.
- Mode: `replace` (default, the OSM layer is swapped) or `merge` (appended, duplicates by geometry dropped).

    python -m offsim.worlds.user_layers --world molde --kind roads --file my_roads.geojson \\
        --src "Statens vegvesen NVDB export 2026-10" --licence NLOD-2.0 [--mode merge] [--simplify-m 2]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import geopandas as gpd
import yaml

ROOT = Path(__file__).resolve().parents[2]

KINDS = {
    "roads": ({"LineString", "MultiLineString"}, [("highway", "maxspeed", "speed_kph")]),
    "quays": ({"Point", "Polygon", "MultiPolygon", "LineString"}, []),
    "ferry": ({"LineString", "MultiLineString"}, []),
    "buildings": ({"Polygon", "MultiPolygon"}, []),
    "landuse": ({"Polygon", "MultiPolygon"}, []),
    "helipads": ({"Point", "Polygon"}, []),
    "aerodromes": ({"Point", "Polygon", "MultiPolygon"}, []),
    "stops": ({"Point"}, [("name", "stop_id")]),
    "sites": ({"Point", "Polygon"}, [("name", "id")]),        # installations, turbines, customers from a paper
}


def _bbox(world, data_root):
    spec = data_root / "data/worlds" / world / "world.yaml"
    if not spec.exists():
        spec = ROOT / "offsim/worlds" / f"{world}.yaml"
    if not spec.exists():
        raise FileNotFoundError(f"no world spec for {world!r}: run fetch_world --place {world} first")
    d = yaml.safe_load(spec.read_text())
    return tuple(d["bbox"])


def check(gdf, kind):
    """Problems as strings ([] = ok). CRS and lon/lat range, geometry types, required properties."""
    if kind not in KINDS:
        return [f"unknown kind {kind!r}; known: {sorted(KINDS)}"]
    probs = []
    types, required = KINDS[kind]
    if gdf.crs is None:
        b = gdf.total_bounds
        if not (-180 <= b[0] <= 180 and -90 <= b[1] <= 90 and -180 <= b[2] <= 180 and -90 <= b[3] <= 90):
            probs.append("no CRS declared and coordinates are not lon/lat (UTM?): declare the CRS in the file")
    bad = set(gdf.geom_type.unique()) - types
    if bad:
        probs.append(f"{kind}: geometry types {sorted(bad)} not allowed (allowed {sorted(types)})")
    for alts in required:
        if not any(a in gdf.columns and gdf[a].notna().any() for a in alts):
            probs.append(f"{kind}: needs one of properties {list(alts)}")
    return probs


def add_layer(world, kind, file, src, licence, mode="replace", simplify_m=None, data_root=None):
    """Validate, normalise and install a user GeoJSON as world layer `kind`. Returns the manifest entry."""
    if not src or not licence:
        raise ValueError("--src and --licence are required (provenance rule)")
    data_root = Path(data_root or ROOT)
    gdf = gpd.read_file(file)
    probs = check(gdf, kind)
    if probs:
        raise ValueError("; ".join(probs))
    gdf = gdf.set_crs(4326) if gdf.crs is None else gdf.to_crs(4326)
    x0, y0, x1, y1 = _bbox(world, data_root)
    n_in = len(gdf)
    gdf = gdf.clip((x0, y0, x1, y1))
    gdf = gdf[~gdf.geometry.is_empty]
    if simplify_m:
        utm = gdf.estimate_utm_crs()
        gdf = gdf.to_crs(utm).simplify(simplify_m).to_frame("geometry").join(gdf.drop(columns="geometry")).set_crs(utm).to_crs(4326)
    out_dir = data_root / "data/worlds" / world / "osm"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{kind}.geojson"
    if mode == "merge" and out.exists():
        old = gpd.read_file(out)
        gdf = gpd.GeoDataFrame(__import__("pandas").concat([old, gdf], ignore_index=True), crs=4326)
        gdf = gdf[~gdf.geometry.to_wkb().duplicated()]
    elif mode not in ("replace", "merge"):
        raise ValueError("mode must be replace or merge")
    gdf.to_file(out, driver="GeoJSON")
    entry = {"kind": kind, "file": str(Path(file).name), "src": src, "licence": licence, "mode": mode,
             "features_in": n_in, "features_kept": int(len(gdf)), "simplify_m": simplify_m}
    (out_dir / f"{kind}.source.json").write_text(json.dumps(entry, indent=1))
    man = data_root / "data/worlds" / world / "manifest.json"
    m = json.loads(man.read_text()) if man.exists() else {}
    m.setdefault("user_layers", {})[kind] = entry
    man.write_text(json.dumps(m, indent=1))
    return entry


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--world", required=True)
    ap.add_argument("--kind", required=True, choices=sorted(KINDS))
    ap.add_argument("--file", required=True)
    ap.add_argument("--src", required=True)
    ap.add_argument("--licence", required=True)
    ap.add_argument("--mode", default="replace", choices=["replace", "merge"])
    ap.add_argument("--simplify-m", type=float)
    a = ap.parse_args()
    print(add_layer(a.world, a.kind, a.file, a.src, a.licence, a.mode, a.simplify_m))


if __name__ == "__main__":
    main()
