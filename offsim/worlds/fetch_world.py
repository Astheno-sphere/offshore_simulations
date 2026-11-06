"""Fetch a study world (land, offshore installations, fields, pipelines) from open Norwegian sources.

Runs where the internet is open: GitHub Actions (`fetch-world` workflow) or your laptop. The
Claude workspace cannot reach these hosts, so it pulls the packaged world from a GitHub release:

    python -m offsim.worlds.fetch_world --world oslofjord --out data/worlds/oslofjord   # fetch (Actions/laptop)
    python -m offsim.worlds.fetch_world --pull oslofjord                               # download release (anywhere)
    python -m offsim.worlds.fetch_world --world oslofjord --out w --metocean 2024-01-10T00:00 48   # + wind/wave/current

`--metocean START_UTC HOURS` adds metocean/<YYYYMMDD-HH>_<hours>h_<dataset>.nc (regular lon/lat, int16 scaled; MET Norway
CC BY 4.0) inside the world package. A dataset that fails is recorded in the manifest (not fatal); needs xarray, netCDF4, scipy.

Worlds are fetched, never committed (OSM is ODbL; see data/osm/README.md). Each package carries
manifest.json with sources, licences, query time and feature counts.
"""
import argparse
import json
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OVERPASS = "https://overpass-api.de/api/interpreter"
SODIR = "https://factmaps.sodir.no/api/rest/services/Factmaps/FactMapsWGS84/FeatureServer"
UA = {"User-Agent": "offshore-simulations (github.com/Astheno-sphere/offshore_simulations)"}


def get(url, data=None, timeout=300):
    req = urllib.request.Request(url, data=data, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def land_from_osm(bbox, out):
    """Coastline ways in the box -> land polygons (lon/lat) via coast.sea_polygons."""
    import geopandas as gpd
    from shapely.geometry import LineString, box
    from shapely.ops import transform
    from pyproj import Transformer

    from offsim.worlds.coast import sea_polygons

    w, s, e, n = bbox
    q = f'[out:json][timeout:300];way["natural"="coastline"]({s},{w},{n},{e});out geom;'
    js = json.loads(get(OVERPASS, data=urllib.parse.urlencode({"data": q}).encode()))
    lines = [LineString([(p["lon"], p["lat"]) for p in el["geometry"]]) for el in js["elements"] if len(el.get("geometry", [])) > 1]
    utm = "EPSG:32632"
    coast = gpd.GeoDataFrame(geometry=lines, crs=4326).to_crs(utm)
    frame = gpd.GeoSeries([box(w, s, e, n)], crs=4326).to_crs(utm).total_bounds
    sea, filled = sea_polygons(coast, tuple(frame))
    land = box(*filled).difference(sea)
    back = Transformer.from_crs(utm, 4326, always_xy=True).transform
    land = transform(back, land).simplify(0.0003)
    gpd.GeoDataFrame(geometry=[land], crs=4326).to_file(out / "land.geojson", driver="GeoJSON")
    return {"coastline_ways": len(lines)}


def sodir_layers(bbox, keywords, out):
    """Every FactMaps layer whose name contains a keyword, clipped to the box, paged by 1000."""
    meta = json.loads(get(f"{SODIR}?f=json"))
    w, s, e, n = bbox
    counts = {}
    for lyr in meta.get("layers", []):
        name = lyr["name"]
        if not any(k.lower() in name.lower() for k in keywords):
            continue
        feats, off = [], 0
        while True:
            params = {"where": "1=1", "geometry": f"{w},{s},{e},{n}", "geometryType": "esriGeometryEnvelope",
                      "inSR": 4326, "outSR": 4326, "spatialRel": "esriSpatialRelIntersects", "outFields": "*",
                      "f": "geojson", "resultOffset": off, "resultRecordCount": 1000}
            page = json.loads(get(f"{SODIR}/{lyr['id']}/query?{urllib.parse.urlencode(params)}"))
            feats += page.get("features", [])
            if len(page.get("features", [])) < 1000:
                break
            off += 1000
        slug = "".join(c if c.isalnum() else "_" for c in name.lower()).strip("_")
        (out / f"sodir_{slug}.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
        counts[name] = len(feats)
    return counts


METOCEAN_DATASETS = ("nora3_wind", "nora3_wave", "norkyst_v3")


def metocean(bbox, out, start_utc, hours, datasets=METOCEAN_DATASETS):
    """NORA3 wind/wave + NorKyst v3 currents for the world bbox -> out/metocean/. Returns manifest entries."""
    from offsim.weather.fetch import LICENCE, subset

    md = Path(out) / "metocean"
    md.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H", time.strptime(start_utc[:13], "%Y-%m-%dT%H"))
    entries = []
    for name in datasets:
        path = md / f"{stamp}_{hours}h_{name}.nc"
        try:
            e = subset(name, tuple(bbox), start_utc, hours, str(path))
            e["file"] = f"metocean/{path.name}"
        except Exception as exc:  # one failing server must not lose the land/offshore data
            e = {"dataset": name, "licence": LICENCE, "error": f"{type(exc).__name__}: {exc}"}
        entries.append(e)
    return entries


def fetch(world, out, metocean_args=None):
    cfg = yaml.safe_load((HERE / f"{world}.yaml").read_text())
    out.mkdir(parents=True, exist_ok=True)
    man = {"world": world, "bbox": cfg["bbox"], "fetched_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "sources": []}
    if cfg.get("osm_land", True):
        c = land_from_osm(cfg["bbox"], out)
        man["sources"].append({"name": "OpenStreetMap coastline (Overpass)", "licence": "ODbL 1.0",
                               "credit": "© OpenStreetMap contributors", **c})
    if cfg.get("sodir_keywords"):
        c = sodir_layers(cfg["bbox"], cfg["sodir_keywords"], out)
        man["sources"].append({"name": "Norwegian Offshore Directorate FactMaps (WGS84)", "licence": "NLOD 2.0",
                               "credit": "Source: Norwegian Offshore Directorate", "layers": c})
    if metocean_args:
        man["sources"].append({"name": "MET Norway NORA3 wind/wave + NorKyst v3 currents (THREDDS OPeNDAP)",
                               "licence": "CC BY 4.0 — MET Norway", "credit": "MET Norway (CC BY 4.0)",
                               "datasets": metocean(cfg["bbox"], out, metocean_args[0], int(metocean_args[1]))})
    man["manual"] = cfg.get("manual", [])
    (out / "manifest.json").write_text(json.dumps(man, indent=1))
    print(json.dumps(man, indent=1))


REPO = "Astheno-sphere/offshore_simulations"


def pull(world, dest=None):
    """Download release `world-<name>` via the REST API (works where GraphQL is blocked) and unzip it."""
    dest = Path(dest or ROOT / "data/worlds" / world)
    dest.mkdir(parents=True, exist_ok=True)
    rel = json.loads(subprocess.run(["gh", "api", f"repos/{REPO}/releases/tags/world-{world}"],
                                    check=True, capture_output=True, text=True).stdout)
    for asset in rel["assets"]:
        if not asset["name"].endswith(".zip"):
            continue
        z = dest / asset["name"]
        with open(z, "wb") as fh:
            subprocess.run(["gh", "api", "-H", "Accept: application/octet-stream",
                            f"repos/{REPO}/releases/assets/{asset['id']}"], check=True, stdout=fh)
        subprocess.run(["unzip", "-o", "-q", str(z), "-d", str(dest)], check=True)
        z.unlink()
    print(f"world {world} -> {dest}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--world")
    ap.add_argument("--out")
    ap.add_argument("--pull")
    ap.add_argument("--metocean", nargs=2, metavar=("START_UTC", "HOURS"), help="also subset wind/wave/current, e.g. 2024-01-10T00:00 48")
    a = ap.parse_args()
    if a.pull:
        pull(a.pull, a.out)
    else:
        fetch(a.world, Path(a.out or ROOT / "data/worlds" / a.world), a.metocean)
