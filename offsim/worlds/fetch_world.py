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

`--osm` also downloads the Geofabrik extract (world YAML `osm_pbf_url`, default norway-latest.osm.pbf; point it at a
regional extract to save RAM) and writes osm/<layer>.geojson + osm/manifest.json via offsim.worlds.osm (ODbL; needs
pyrosm). `--osm-pbf FILE` uses a local pbf instead of downloading. `--ais PATH` processes a Kystverket HAIS file
(GeoParquet/CSV) into ais/calibration.json (+ ais/port_calls.csv when the world YAML lists `ais_places`:
[{name, lon, lat, radius_m}]) via offsim.traffic.ais; optional YAML `ais_ship_types`, `ais_area`.

Any place (world spec v2, offsim/worlds/place.py, docs/ARCHITECTURE.md "Worlds v2"):

    python -m offsim.worlds.fetch_world --place Ålesund --modes sea,road,bus --radius-km 20

`--place NAME` (gazetteer key, Kartverket stedsnavn name, or "lon0,lat0,lon1,lat1") resolves the place, writes
data/worlds/<slug>/world.yaml and offsim/worlds/<slug>.yaml (if absent), then fetches that world. `--modes` (default
sea) implies flags: road/walk/bus => --osm; bus => --gtfs. `--gtfs` downloads the Entur national aggregated GTFS
(NLOD; https://storage.googleapis.com/marduk-production/outbound/gtfs/rb_norway-aggregated-gtfs.zip, unverified live;
large, cached once outside the world zip) and clips it to the bbox with offsim.transit.gtfs.clip -> <out>/gtfs/.
`--gtfs-zip FILE` uses a local zip instead of downloading.

Depth (`--depth`, docs/VISUAL_SPEC.md §2) additionally downloads raw DEM tiles into <out>/dem_raw/ plus
dem_raw/sources.json (the source list merge_dem takes); the workflow publishes them as release `world-<name>-dem-raw`.
Process them anywhere with `python -m offsim.worlds.depth --world <name> --tier fjord`.

Endpoint status (see docs/TESTLOG.md; the sandbox cannot reach these hosts, so nothing here has run live yet):
  EMODnet Bathymetry  WCS 2.0.1  https://ows.emodnet-bathymetry.eu/wcs   host/protocol confirmed from the EMODnet R client and the
                      EMODnet catalogue; coverage id and axis labels are DISCOVERED at run time (GetCapabilities/DescribeCoverage).
  Kartverket DTM      Geonorge download API https://nedlasting.geonorge.no/api   paths/schemas confirmed from its swagger.json;
                      the dataset metadata UUID comes from the world YAML and is checked against /capabilities at run time.
  Kartverket seabed   WCS - URL not confirmed -> NotImplementedError.
"""
import argparse
import io
import json
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import yaml

from offsim.worlds import place as placemod

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OVERPASS = "https://overpass-api.de/api/interpreter"
SODIR = "https://factmaps.sodir.no/api/rest/services/Factmaps/FactMapsWGS84/FeatureServer"
ENTUR_GTFS = "https://storage.googleapis.com/marduk-production/outbound/gtfs/rb_norway-aggregated-gtfs.zip"
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


class StageTimeout(Exception):
    pass


import contextlib
import signal


@contextlib.contextmanager
def stage(name, budget_s, errors):
    """Log a fetch stage with timestamps (flushed, so Actions shows progress) and cap its wall time. A stage that
    times out or fails is recorded in `errors` and the fetch continues: one slow server must not kill the job."""
    t0 = time.time()
    print(f"[{time.strftime('%H:%M:%S')}] >> {name} (budget {budget_s // 60} min)", flush=True)

    def _alarm(*_):
        raise StageTimeout(f"{name} exceeded {budget_s} s")
    old = signal.signal(signal.SIGALRM, _alarm) if hasattr(signal, "SIGALRM") else None
    if old is not None:
        signal.alarm(int(budget_s))
    try:
        yield
        print(f"[{time.strftime('%H:%M:%S')}] << {name} ok ({time.time() - t0:.0f} s)", flush=True)
    except Exception as exc:          # noqa: BLE001 - record and continue
        errors.append({"stage": name, "error": f"{type(exc).__name__}: {exc}", "seconds": round(time.time() - t0)})
        print(f"[{time.strftime('%H:%M:%S')}] !! {name} FAILED after {time.time() - t0:.0f} s: {exc}", flush=True)
    finally:
        if old is not None:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old)


BUDGET_S = {"coast": 15 * 60, "sodir": 10 * 60, "metocean": 40 * 60, "osm": 40 * 60, "gtfs": 30 * 60, "ais": 20 * 60}


def metocean(bbox, out, start_utc, hours, datasets=METOCEAN_DATASETS):
    """NORA3 wind/wave + NorKyst v3 currents for the world bbox -> out/metocean/. Returns manifest entries."""
    from offsim.weather.fetch import LICENCE, subset

    md = Path(out) / "metocean"
    md.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H", time.strptime(start_utc[:13], "%Y-%m-%dT%H"))
    entries = []
    for name in datasets:
        path = md / f"{stamp}_{hours}h_{name}.nc"
        print(f"[{time.strftime('%H:%M:%S')}]    metocean {name} {start_utc} +{hours} h", flush=True)
        try:
            e = subset(name, tuple(bbox), start_utc, hours, str(path))
            e["file"] = f"metocean/{path.name}"
        except Exception as exc:  # one failing server must not lose the land/offshore data
            e = {"dataset": name, "licence": LICENCE, "error": f"{type(exc).__name__}: {exc}"}
        entries.append(e)
    return entries


def download(url, dest, chunk=1 << 20, timeout=600):
    """Stream a (large) file to disk; returns the path."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r, open(dest, "wb") as fh:
        while True:
            b = r.read(chunk)
            if not b:
                break
            fh.write(b)
    return dest


def fetch_osm(cfg, out, pbf=None):
    """Geofabrik extract (or local `pbf`) -> out/osm/*.geojson + manifest. Returns the osm manifest."""
    from offsim.worlds import osm

    url = cfg.get("osm_pbf_url", osm.GEOFABRIK_NORWAY)
    if pbf is None:
        pbf = download(url, Path(out).resolve().parent / "_osm_cache" / url.rsplit("/", 1)[-1])   # outside the world zip
    return osm.build_osm_layers(pbf, cfg["bbox"], Path(out) / "osm", source_url=url)


def plan_layers(modes):
    """Modes -> what the fetcher must do: {'modes', 'osm', 'gtfs', 'sea', 'layers'}. road/walk/bus => osm; bus => gtfs;
    air => osm (helipads); sea => coast/sealanes (land coastline is always fetched)."""
    modes = placemod.check_modes(modes)
    return {"modes": modes, "osm": bool({"road", "walk", "bus", "air"} & set(modes)), "gtfs": "bus" in modes,
            "sea": "sea" in modes, "layers": placemod.layers_for(modes)}


def fetch_gtfs(cfg, out, zip_path=None, url=ENTUR_GTFS):
    """Entur aggregated GTFS (downloaded once to a cache dir outside the world zip, or local `zip_path`) clipped to the
    bbox by offsim.transit.gtfs.clip -> out/gtfs/. Returns a manifest source entry. Fails early with a clear message
    when offsim.transit.gtfs does not exist (checked BEFORE the large download)."""
    try:
        from offsim.transit import gtfs as gtfs_mod
    except ImportError as ex:
        raise RuntimeError("--gtfs needs offsim/transit/gtfs.py (clip(zip_path, bbox, out_dir) -> dict), which is not "
                           f"present in this checkout ({ex}); pull the transit module first") from ex
    if zip_path is None:
        zip_path = download(url, Path(out).resolve().parent / "_gtfs_cache" / url.rsplit("/", 1)[-1])
    stats = gtfs_mod.clip(str(zip_path), tuple(cfg["bbox"]), str(Path(out) / "gtfs"))
    return {"name": "Entur national aggregated GTFS (clipped to bbox by offsim.transit.gtfs)", "licence": "NLOD 2.0",
            "credit": "Source: Entur (NLOD)", "url": url, "dir": "gtfs/", "stats": stats}


def fetch_ais(cfg, out, path):
    """HAIS file -> out/ais/calibration.json (+ port_calls.csv). Returns the calibration dict."""
    from offsim.traffic import ais

    return ais.process_hais(path, Path(out) / "ais", bbox=cfg["bbox"], places=cfg.get("ais_places"),
                            ship_types=cfg.get("ais_ship_types"), area=cfg.get("ais_area", cfg.get("name", "world")))


def fetch(world, out, metocean_args=None, osm=False, osm_pbf=None, ais_path=None, gtfs=False, gtfs_zip=None,
          metocean_datasets=METOCEAN_DATASETS):
    cfg = yaml.safe_load((HERE / f"{world}.yaml").read_text())
    out.mkdir(parents=True, exist_ok=True)
    man = {"world": world, "bbox": cfg["bbox"], "fetched_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "sources": []}
    errors = man.setdefault("errors", [])
    if cfg.get("osm_land", True):
        with stage("coast (Overpass)", BUDGET_S["coast"], errors):
            c = land_from_osm(cfg["bbox"], out)
            man["sources"].append({"name": "OpenStreetMap coastline (Overpass)", "licence": "ODbL 1.0",
                                   "credit": "© OpenStreetMap contributors", **c})
    if cfg.get("sodir_keywords"):
        with stage("sodir (FactMaps)", BUDGET_S["sodir"], errors):
            c = sodir_layers(cfg["bbox"], cfg["sodir_keywords"], out)
            man["sources"].append({"name": "Norwegian Offshore Directorate FactMaps (WGS84)", "licence": "NLOD 2.0",
                                   "credit": "Source: Norwegian Offshore Directorate", "layers": c})
    if metocean_args:
        with stage(f"metocean {','.join(metocean_datasets)}", BUDGET_S["metocean"] * len(metocean_datasets), errors):
            man["sources"].append({"name": "MET Norway NORA3 wind/wave + NorKyst v3 currents (THREDDS OPeNDAP)",
                                   "licence": "CC BY 4.0 — MET Norway", "credit": "MET Norway (CC BY 4.0)",
                                   "datasets": metocean(cfg["bbox"], out, metocean_args[0], int(metocean_args[1]),
                                                        tuple(metocean_datasets))})
    if osm or osm_pbf:
        with stage("osm (Geofabrik + pyrosm)", BUDGET_S["osm"], errors):
            om = fetch_osm(cfg, out, osm_pbf)
            man["sources"].append({"name": om["name"], "licence": om["licence"], "credit": om["credit"],
                                   "layers": {k: v["features"] for k, v in om["layers"].items()}, "dir": "osm/"})
    if gtfs or gtfs_zip:
        with stage("gtfs (Entur)", BUDGET_S["gtfs"], errors):
            man["sources"].append(fetch_gtfs(cfg, out, gtfs_zip))
    if ais_path:
        with stage("ais (HAIS)", BUDGET_S["ais"], errors):
            cal = fetch_ais(cfg, out, ais_path)
            man["sources"].append({"name": "Kystverket Historic AIS (HAIS), processed by offsim.traffic", "licence": "NLOD 2.0",
                                   "credit": "Source: Kystverket", "src": cal["src"], "dir": "ais/",
                                   "port_calls": cal["port_calls"], "vessels": cal["vessels"]})
    man["manual"] = cfg.get("manual", [])
    (out / "manifest.json").write_text(json.dumps(man, indent=1))
    print(json.dumps(man, indent=1))


# ---------------------------------------------------------------------------------------------------------------
# Depth: raw DEM download (runs on Actions / laptop). Processing lives in offsim/worlds/depth.py.
# ---------------------------------------------------------------------------------------------------------------
EMODNET_WCS = "https://ows.emodnet-bathymetry.eu/wcs"
GEONORGE_DL = "https://nedlasting.geonorge.no/api"


def _is_tiff(b):
    return b[:4] in (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+")


def emodnet_coverage_ids(base=EMODNET_WCS):
    """WCS 2.0.1 GetCapabilities -> list of coverage ids (the ids are not hard-coded: EMODnet re-versions yearly)."""
    xml = get(f"{base}?service=WCS&version=2.0.1&request=GetCapabilities", timeout=120).decode("utf-8", "replace")
    return re.findall(r"<(?:\w+:)?CoverageId>\s*([^<\s]+)\s*</(?:\w+:)?CoverageId>", xml)


def emodnet_pick_coverage(ids, want=None):
    """Explicit `want` wins; else the newest `emodnet__mean*` (year suffix), else plain `emodnet__mean`."""
    if want:
        if want not in ids:
            raise RuntimeError(f"EMODnet coverage {want!r} not offered; available: {ids[:20]}")
        return want
    cand = [i for i in ids if re.fullmatch(r"emodnet__mean(_\d{4})?", i)]
    if not cand:
        raise NotImplementedError(f"endpoint unverified: no 'emodnet__mean*' coverage in GetCapabilities ({ids[:20]})")
    return sorted(cand, key=lambda i: (int(i[-4:]) if i[-4:].isdigit() else 0))[-1]


def emodnet_bathymetry(bbox, out, cfg=None):
    """EMODnet Bathymetry DTM (1/16 arc-minute, LAT) for the bbox via WCS 2.0.1 -> out/dem_raw/emodnet.tif.
    One GeoTIFF request per box; boxes up to ~5 x 3 degrees are ~10 MB. Axis labels come from DescribeCoverage."""
    cfg = cfg or {}
    base = cfg.get("url", EMODNET_WCS)
    cov = emodnet_pick_coverage(emodnet_coverage_ids(base), cfg.get("coverage"))
    desc = get(f"{base}?service=WCS&version=2.0.1&request=DescribeCoverage&coverageId={urllib.parse.quote(cov)}",
               timeout=120).decode("utf-8", "replace")
    m = re.search(r'axisLabels="([^"]+)"', desc)
    if not m:
        raise NotImplementedError("endpoint unverified: DescribeCoverage returned no axisLabels for " + cov)
    labels = m.group(1).split()
    lat_l = next((a for a in labels if a.lower().startswith("lat")), None)
    lon_l = next((a for a in labels if a.lower().startswith(("lon", "long"))), None)
    if not (lat_l and lon_l):
        raise NotImplementedError(f"endpoint unverified: axis labels {labels} are not lat/lon")
    w, s, e, n = bbox
    q = [("service", "WCS"), ("version", "2.0.1"), ("request", "GetCoverage"), ("coverageId", cov),
         ("format", "image/tiff"), ("subset", f"{lat_l}({s},{n})"), ("subset", f"{lon_l}({w},{e})")]
    body = get(f"{base}?{urllib.parse.urlencode(q)}", timeout=600)
    if not _is_tiff(body):
        raise RuntimeError("EMODnet GetCoverage did not return a TIFF: " + body[:300].decode("utf-8", "replace"))
    dst = out / "dem_raw" / "emodnet.tif"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(body)
    return {"file": "emodnet.tif", "name": f"EMODnet Bathymetry DTM ({cov})", "priority": 3, "datum": "LAT",
            "licence": "EMODnet open data, attribution required (licence text to be confirmed on the EMODnet portal)",
            "credit": "EMODnet Bathymetry Consortium (emodnet.ec.europa.eu)", "coverage": cov, "bytes": len(body),
            "endpoint": base}


def _geonorge_json(path, payload=None, method=None, timeout=120):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(f"{GEONORGE_DL}{path}", data=data, method=method or ("POST" if data else "GET"),
                                 headers={**UA, "Accept": "application/json", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"null")


def geonorge_order_files(uuid, line, wait_s=1800, poll_s=15, email=""):
    """POST /api/order with one order line, poll GET /api/order/{referenceNumber} until every file is ready.
    Returns the order receipt. Raises TimeoutError after wait_s, RuntimeError on a failed file."""
    receipt = _geonorge_json("/order", {"email": email, "orderLines": [{"metadataUuid": uuid, **line}],
                                        "usageGroup": "Visualisering", "softwareClient": "offshore-simulations",
                                        "softwareClientVersion": "1"})
    ref = receipt.get("referenceNumber")
    t0 = time.time()
    while True:
        files = receipt.get("files") or []
        states = [str(f.get("status") or "") for f in files]
        if any(re.search(r"fail|error|reject", st, re.I) for st in states):
            raise RuntimeError(f"Geonorge order {ref} failed: {states}")
        if files and all(st == "ReadyForDownload" and f.get("downloadUrl") for st, f in zip(states, files)):
            return receipt
        if time.time() - t0 > wait_s:
            raise TimeoutError(f"Geonorge order {ref} not ready after {wait_s}s (states: {states})")
        time.sleep(poll_s)
        receipt = _geonorge_json(f"/order/{ref}")


def kartverket_dtm(bbox, out, cfg=None, wait_s=1800, poll_s=15):
    """Kartverket DTM (land) clipped to the bbox via the Geonorge download API (order -> poll -> download -> unzip)
    -> out/dem_raw/kartverket_dtm*.tif. Needs depth.kartverket_dtm.metadata_uuid in the world YAML."""
    from pyproj import Transformer

    cfg = cfg or {}
    uuid = cfg.get("metadata_uuid")
    if not uuid:
        raise NotImplementedError("endpoint unverified: depth.kartverket_dtm.metadata_uuid not set in the world YAML")
    try:
        cap = _geonorge_json(f"/capabilities/{uuid}")
    except urllib.error.HTTPError as ex:
        raise NotImplementedError(f"endpoint unverified: Geonorge /capabilities/{uuid} -> HTTP {ex.code}") from ex
    code = str(cfg.get("projection_code", "25832"))
    fmt = cfg.get("format")
    if not fmt:                                     # pick a GeoTIFF-like format from the dataset's own codelist
        names = [f.get("name", "") for f in _geonorge_json(f"/codelists/format/{uuid}") or []]
        fmt = next((n for n in names if re.search(r"tif", n, re.I)), None)
        if not fmt:
            raise NotImplementedError(f"endpoint unverified: no GeoTIFF format in {names}")
    if not cap.get("supportsPolygonSelection"):
        raise NotImplementedError("endpoint unverified: dataset has no polygon selection; configure depth."
                                  "kartverket_dtm.areas ([{code,name,type}]) instead")
    tr = Transformer.from_crs(4326, int(code), always_xy=True).transform
    w, s, e, n = bbox
    ring = [tr(x, y) for x, y in ((w, s), (e, s), (e, n), (w, n), (w, s))]
    line = {"coordinates": " ".join(f"{x:.0f} {y:.0f}" for x, y in ring), "coordinatesystem": code,
            "projections": [{"code": code}], "formats": [{"name": fmt}], "usagePurpose": ["Visualisering"]}
    receipt = geonorge_order_files(uuid, line, wait_s=wait_s, poll_s=poll_s)
    dst = out / "dem_raw"
    dst.mkdir(parents=True, exist_ok=True)
    tifs = []
    for f in receipt["files"]:
        blob = get(f["downloadUrl"], timeout=900)
        if zipfile.is_zipfile(io.BytesIO(blob)):
            with zipfile.ZipFile(io.BytesIO(blob)) as z:
                for nme in z.namelist():
                    if nme.lower().endswith((".tif", ".tiff")):
                        target = dst / f"kartverket_dtm_{len(tifs)}.tif"
                        target.write_bytes(z.read(nme))
                        tifs.append(target.name)
        elif _is_tiff(blob):
            target = dst / f"kartverket_dtm_{len(tifs)}.tif"
            target.write_bytes(blob)
            tifs.append(target.name)
    if not tifs:
        raise RuntimeError(f"Geonorge order {receipt.get('referenceNumber')} delivered no GeoTIFF")
    return {"files": tifs, "name": cfg.get("name", "Kartverket DTM"), "priority": 1, "datum": "NN2000",
            "licence": cfg.get("licence", "CC BY 4.0"), "credit": "© Kartverket (CC BY 4.0)", "metadata_uuid": uuid,
            "order": receipt.get("referenceNumber"), "endpoint": GEONORGE_DL}


def kartverket_seabed(bbox, out, cfg=None):
    """Kartverket seabed terrain 5/25/50 m (WCS)."""
    raise NotImplementedError("endpoint unverified: Kartverket seabed terrain WCS URL/coverage ids not confirmed; "
                              "download by hand from geonorge.no into dem_raw/ and list it in sources.json")


def fetch_depth(world, out):
    """Raw DEM for one world into out/dem_raw/ + sources.json; merges its provenance into out/manifest.json."""
    cfg = yaml.safe_load((HERE / f"{world}.yaml").read_text())
    dcfg = cfg.get("depth") or {}
    out.mkdir(parents=True, exist_ok=True)
    srcs, prov = [], []
    todo = [("emodnet", emodnet_bathymetry), ("kartverket_dtm", kartverket_dtm), ("kartverket_seabed", kartverket_seabed)]
    for key, fn in todo:
        sc = dcfg.get(key)
        if not sc or (isinstance(sc, dict) and sc.get("enabled") is False):
            continue
        r = fn(cfg["bbox"], out, sc if isinstance(sc, dict) else {})
        prov.append({k: v for k, v in r.items() if k != "bytes"} | {"source_key": key})
        for i, f in enumerate(r.get("files") or [r["file"]]):
            srcs.append({"name": r["name"] + (f" [{i}]" if "files" in r and len(r["files"]) > 1 else ""),
                         "path": f, "priority": r["priority"], "datum": r["datum"], "licence": r["licence"],
                         "credit": r["credit"]})
    (out / "dem_raw").mkdir(parents=True, exist_ok=True)
    (out / "dem_raw" / "sources.json").write_text(json.dumps({"crs": dcfg.get("crs", "EPSG:25832"), "sources": srcs}, indent=1))
    mp = out / "manifest.json"
    man = json.loads(mp.read_text()) if mp.exists() else {"world": world, "bbox": cfg["bbox"], "sources": []}
    man["depth_sources"] = prov
    mp.write_text(json.dumps(man, indent=1))
    print(json.dumps(prov, indent=1))
    return srcs


REPO = "Astheno-sphere/offshore_simulations"


def pull(world, dest=None, raw_dem=False):
    """Download release `world-<name>` (or `world-<name>-dem-raw` with raw_dem) via the REST API (works where GraphQL
    is blocked) and unzip it."""
    dest = Path(dest or ROOT / "data/worlds" / world)
    dest.mkdir(parents=True, exist_ok=True)
    tag = f"world-{world}" + ("-dem-raw" if raw_dem else "")
    rel = json.loads(subprocess.run(["gh", "api", f"repos/{REPO}/releases/tags/{tag}"],
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
    ap.add_argument("--metocean-datasets", default=",".join(METOCEAN_DATASETS),
                    help="comma list of " + ",".join(METOCEAN_DATASETS) + " (helicopter/PSV studies: nora3_wind,nora3_wave)")
    ap.add_argument("--depth", action="store_true",
                    help="also fetch raw DEM (EMODnet, Kartverket DTM) into <out>/dem_raw; with --pull: pull world-<name>-dem-raw")
    ap.add_argument("--osm", action="store_true", help="also download the Geofabrik pbf and write osm/<layer>.geojson (needs pyrosm)")
    ap.add_argument("--osm-pbf", metavar="FILE", help="use this local .osm.pbf instead of downloading (implies --osm)")
    ap.add_argument("--ais", metavar="PATH", help="process a Kystverket HAIS GeoParquet/CSV into ais/calibration.json")
    ap.add_argument("--depth-only", action="store_true", help="fetch only the raw DEM (skip OSM/Sodir)")
    ap.add_argument("--place", metavar="NAME", help='resolve a place ("Ålesund", a stedsnavn name, or "lon0,lat0,lon1,lat1") '
                    "and write data/worlds/<slug>/world.yaml + offsim/worlds/<slug>.yaml (if absent); fetch that world")
    ap.add_argument("--modes", default=None, help="comma list of sea,road,bus,walk,air (default sea for --place); "
                    "road/walk/bus/air imply --osm, bus implies --gtfs")
    ap.add_argument("--radius-km", type=float, default=None, help="half-width of the --place box in km (default: gazetteer / 15)")
    ap.add_argument("--gtfs", action="store_true", help="download Entur aggregated GTFS and clip it to the bbox -> <out>/gtfs")
    ap.add_argument("--gtfs-zip", metavar="FILE", help="use this local GTFS zip instead of downloading (implies --gtfs)")
    a = ap.parse_args()
    if a.pull:
        pull(a.pull, a.out, raw_dem=a.depth)
    else:
        world, modes = a.world, a.modes
        if a.place:
            pl = placemod.resolve(a.place, radius_km=a.radius_km)
            world = placemod.slugify(pl.name if pl.name != "bbox" else f"bbox-{pl.lon:.2f}-{pl.lat:.2f}")
            wdir = Path(a.out or ROOT / "data/worlds" / world)
            placemod.write_world_spec(pl, modes or "sea", wdir / "world.yaml", depth=a.depth or a.depth_only, name=world)
            if not (HERE / f"{world}.yaml").exists():
                placemod.write_world_spec(pl, modes or "sea", HERE / f"{world}.yaml", depth=a.depth or a.depth_only, name=world)
        if not world:
            ap.error("one of --world, --place or --pull is required")
        plan = plan_layers(modes or placemod.load_world_spec(HERE / f"{world}.yaml")["modes"])
        dest = Path(a.out or ROOT / "data/worlds" / world)
        if not a.depth_only:
            fetch(world, dest, a.metocean, osm=a.osm or plan["osm"], osm_pbf=a.osm_pbf, ais_path=a.ais,
                  gtfs=a.gtfs or plan["gtfs"], gtfs_zip=a.gtfs_zip,
                  metocean_datasets=[d for d in a.metocean_datasets.split(",") if d])
        if a.depth or a.depth_only:
            fetch_depth(world, dest)
