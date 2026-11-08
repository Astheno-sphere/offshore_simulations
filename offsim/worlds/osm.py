"""OpenStreetMap layers for a world, from a Geofabrik .osm.pbf, clipped to the world bbox (pyrosm).

Runs on Actions or a laptop (needs the pbf; the Claude workspace cannot reach Geofabrik) and writes into the world
package, which `fetch_world --pull` brings back:

    python -m offsim.worlds.fetch_world --world oslofjord --out data/worlds/oslofjord --osm
    python -m offsim.worlds.osm --pbf norway-latest.osm.pbf --bbox 10.2 58.95 11.05 59.95 --out data/worlds/oslofjord/osm

Layers -> <out>/<layer>.geojson (EPSG:4326) and <out>/manifest.json:
    quays      man_made=pier|quay, harbour=*                      (lines/polygons/points)
    ferry      route=ferry                                        (lines)
    roads      pyrosm driving network                             (lines; highway, name, maxspeed, oneway, ref)
    buildings  building=*  + height_m, height_src, height_assumption
    landuse    landuse=industrial|port
    helipads   aeroway=helipad|heliport                           (points/polygons)
    aerodromes aeroway=aerodrome (airports, e.g. Sola ENZV, Molde Årø ENML) (points/polygons)

Building height (`add_height_m`): the `height` tag if it parses (metres; "12", "12.5 m", feet "40 ft"/40'), else
`building:levels` x LEVEL_HEIGHT_M (3 m) with height_src="levels_x3_assumption" and height_assumption=True, else NaN
with height_src="none". Anything derived from the levels default is an assumption and must be cited as such in a
scenario (`assumption: true`). Overture Maps buildings (better coverage of heights in some areas) are the spec in
`overture_buildings_spec`.

Licence: ODbL 1.0, credit "(c) OpenStreetMap contributors"; the manifest carries both. Data is never committed.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

import numpy as np
import pandas as pd

LEVEL_HEIGHT_M = 3.0
FT_TO_M = 0.3048
LICENCE = "ODbL 1.0"
CREDIT = "© OpenStreetMap contributors"
GEOFABRIK_NORWAY = "https://download.geofabrik.de/europe/norway-latest.osm.pbf"
LAYERS = ("quays", "ferry", "roads", "buildings", "landuse", "helipads", "aerodromes")

# pyrosm custom filters (filter_type="keep": a feature matching any key/value is kept) and tags to expose as columns
FILTERS = {
    "quays": ({"man_made": ["pier", "quay"], "harbour": True}, ["man_made", "harbour", "name", "seamark:type"]),
    "ferry": ({"route": ["ferry"]}, ["route", "name", "operator", "ref", "duration", "ferry"]),
    "landuse": ({"landuse": ["industrial", "port"]}, ["landuse", "name", "industrial"]),
    "helipads": ({"aeroway": ["helipad", "heliport"]}, ["aeroway", "name", "ref", "icao", "iata"]),
    "aerodromes": ({"aeroway": ["aerodrome"]}, ["aeroway", "name", "ref", "icao", "iata"]),
}


def parse_height_m(value) -> float:
    """OSM `height` tag -> metres, NaN if unparseable. "12", "12.5", "12 m", "12,5 m", "40 ft", "40'", "40'6\"" ."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return float("nan")
    s = str(value).strip().lower().replace(",", ".")
    m = re.fullmatch(r"(\d+)'\s*(?:(\d+(?:\.\d+)?)\s*(?:\"|in)?)?", s)           # feet and inches: 40'6"
    if m:
        return (int(m.group(1)) * 12 + float(m.group(2) or 0)) * 0.0254
    m = re.fullmatch(r"(-?\d+(?:\.\d+)?)\s*(m|meter|meters|metre|metres|ft|feet)?", s)
    if not m:
        return float("nan")
    v = float(m.group(1))
    if v <= 0:
        return float("nan")
    return v * FT_TO_M if m.group(2) in ("ft", "feet") else v


def parse_levels(value) -> float:
    """`building:levels` -> float, NaN if unparseable or <= 0."""
    try:
        v = float(str(value).strip().replace(",", ".").split(";")[0])
    except (TypeError, ValueError):
        return float("nan")
    return v if v > 0 else float("nan")


def add_height_m(gdf, level_height_m: float = LEVEL_HEIGHT_M):
    """Add height_m, height_src ("height_tag" | "levels_x3_assumption" | "none") and height_assumption (bool) to a
    buildings GeoDataFrame. Accepts the level tag as `building:levels` or `building_levels`. Returns a copy."""
    out = gdf.copy()
    hcol = out["height"] if "height" in out.columns else pd.Series(np.nan, index=out.index)
    lcol = next((out[c] for c in ("building:levels", "building_levels") if c in out.columns), pd.Series(np.nan, index=out.index))
    h = hcol.map(parse_height_m).astype(float)
    lv = lcol.map(parse_levels).astype(float)
    from_levels = h.isna() & lv.notna()
    out["height_m"] = h.where(~from_levels, lv * level_height_m)
    out["height_src"] = np.where(h.notna(), "height_tag", np.where(from_levels, f"levels_x{level_height_m:g}_assumption", "none"))
    out["height_assumption"] = from_levels.to_numpy()
    return out


def clip_to_bbox(gdf, bbox):
    """Keep features intersecting bbox (west, south, east, north); geometries are not cut (pyrosm already clips)."""
    from shapely.geometry import box

    if gdf is None or len(gdf) == 0:
        return gdf
    return gdf[gdf.intersects(box(*bbox))].reset_index(drop=True)


def _jsonable(gdf):
    """Columns safe for GeoJSON: scalars stay, lists/dicts/sets become JSON strings, `tags` is kept as a string."""
    out = gdf.copy()
    for c in out.columns:
        if c == "geometry":
            continue
        if out[c].map(lambda v: isinstance(v, (list, dict, set, tuple))).any():
            out[c] = out[c].map(lambda v: json.dumps(sorted(v) if isinstance(v, set) else v, default=str)
                                if isinstance(v, (list, dict, set, tuple)) else v)
        if str(out[c].dtype).startswith(("datetime", "timedelta")):
            out[c] = out[c].astype(str)
    return out


def write_layer(gdf, out_dir, name: str) -> int:
    """Write <out_dir>/<name>.geojson (EPSG:4326). An empty layer is written as an empty FeatureCollection so the
    package always has the file. Returns the feature count."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}.geojson"
    if gdf is None or len(gdf) == 0:
        path.write_text(json.dumps({"type": "FeatureCollection", "features": []}))
        return 0
    g = _jsonable(gdf.to_crs(4326) if gdf.crs is not None else gdf.set_crs(4326))
    g = g.loc[~g.geometry.isna() & ~g.geometry.is_empty]
    path.write_text(g.to_json(drop_id=True, na="drop"))
    return int(len(g))


def write_manifest(out_dir, layers: dict, bbox, source: str, source_date: str | None = None, source_url: str | None = None) -> dict:
    """<out_dir>/manifest.json: source file/date/url, ODbL licence + attribution, bbox, per-layer counts, assumptions."""
    man = {
        "name": "OpenStreetMap extract (Geofabrik)",
        "source": source, "source_url": source_url or GEOFABRIK_NORWAY, "source_date": source_date,
        "licence": LICENCE, "credit": CREDIT,
        "attribution": f"{CREDIT}, available under the {LICENCE}; data via Geofabrik GmbH",
        "bbox": list(bbox), "processed_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "layers": {k: {"file": f"{k}.geojson", "features": int(v)} for k, v in layers.items()},
        "assumptions": [f"buildings without a height tag but with building:levels: height_m = levels x {LEVEL_HEIGHT_M:g} m "
                        "(height_src=levels_x3_assumption, height_assumption=true)"],
    }
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    (Path(out_dir) / "manifest.json").write_text(json.dumps(man, indent=1))
    return man


def pbf_date(pbf) -> str:
    """Date of the extract: file mtime (Geofabrik sets it to the extract timestamp), UTC ISO date."""
    return time.strftime("%Y-%m-%d", time.gmtime(Path(pbf).stat().st_mtime))


def extract_layers(pbf, bbox, layers=LAYERS) -> dict:
    """Read the pbf with pyrosm, clipped to bbox -> {layer: GeoDataFrame (EPSG:4326)}. Needs pyrosm (requirements-gis.txt).
    A layer pyrosm finds nothing for comes back empty rather than failing the run."""
    import geopandas as gpd
    from pyrosm import OSM

    osm = OSM(str(pbf), bounding_box=list(bbox))
    out = {}
    for name in layers:
        try:
            if name == "roads":
                g = osm.get_network(network_type="driving", extra_attributes=["ref"])
            elif name == "buildings":
                g = osm.get_buildings(extra_attributes=["height", "building:levels"])
            else:
                crit, keys = FILTERS[name]
                g = osm.get_data_by_custom_criteria(custom_filter=crit, osm_keys_to_keep=keys, filter_type="keep",
                                                    keep_nodes=True, keep_ways=True, keep_relations=True)
        except Exception as exc:  # one failing layer must not lose the others
            print(f"osm layer {name}: {type(exc).__name__}: {exc}")
            g = None
        out[name] = gpd.GeoDataFrame(geometry=[], crs=4326) if g is None else g
    return out


def postprocess(layers: dict, bbox) -> dict:
    """Clip every layer to bbox; add height_m to buildings. Pure GeoDataFrame in/out (this is what the tests cover)."""
    out = {}
    for name, g in layers.items():
        g = clip_to_bbox(g, bbox)
        if name == "buildings" and g is not None and len(g):
            g = add_height_m(g)
        out[name] = g
    return out


def build_osm_layers(pbf, bbox, out_dir, layers=LAYERS, source_url: str | None = None) -> dict:
    """pbf -> <out_dir>/<layer>.geojson + manifest.json for the bbox. Returns the manifest."""
    got = postprocess(extract_layers(pbf, bbox, layers), bbox)
    counts = {name: write_layer(g, out_dir, name) for name, g in got.items()}
    return write_manifest(out_dir, counts, bbox, source=Path(pbf).name, source_date=pbf_date(pbf), source_url=source_url)


def overture_buildings_spec(bbox, out_dir, release: str | None = None):
    """SPEC (not built; runs on Actions where Overture's S3 is reachable): Overture Maps buildings for the bbox.

    Build to this contract, then add the evidence to catalog/tools.yaml (overture):
      1. Fetch, either with the CLI
             overturemaps download --bbox=W,S,E,N -f geoparquet --type=building -o <out_dir>/overture_buildings.parquet
         or with DuckDB (httpfs + spatial) straight from the release on S3
             SELECT id, height, num_floors, class, names.primary AS name, ST_AsWKB(geometry) AS geometry
             FROM read_parquet('s3://overturemaps-us-west-2/release/<release>/theme=buildings/type=building/*', hive_partitioning=1)
             WHERE bbox.xmin BETWEEN W AND E AND bbox.ymin BETWEEN S AND N;
         `release` pins the Overture release (e.g. "2025-10-22.0"); never "latest", so the world is reproducible.
      2. Normalise to the same columns as the OSM buildings layer: height_m from `height` (metres, source "overture_height");
         else num_floors x LEVEL_HEIGHT_M with height_assumption=True; else NaN. Keep `id` as overture_id.
      3. Write <out_dir>/buildings_overture.geojson and add it to the OSM manifest with its own licence (Overture buildings
         are ODbL where derived from OSM and CDLA-Permissive-2.0 otherwise: record the per-feature `sources` dataset and
         take the strictest attribution) and the release id.
      4. Never merge silently with OSM buildings: report overlap (IoU > 0.5) and keep both layers.
    """
    raise NotImplementedError("spec: Overture Maps buildings fetch (overturemaps CLI / DuckDB on Actions); see docstring")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--pbf", required=True)
    ap.add_argument("--bbox", nargs=4, type=float, required=True, metavar=("W", "S", "E", "N"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--layers", nargs="+", default=list(LAYERS), choices=LAYERS)
    a = ap.parse_args()
    print(json.dumps(build_osm_layers(a.pbf, a.bbox, a.out, a.layers), indent=1))
