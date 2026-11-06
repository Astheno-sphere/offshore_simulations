"""Map depth: terrain + bathymetry -> merged DEM, mesh, baked hillshade, isobaths. Built and tested on synthetic DEMs.
Spec: docs/VISUAL_SPEC.md §2. Fetch on Actions (fetch_world.py --depth); process here with rasterio + pydelatin +
scikit-image; render offline (render_deck/src/layers/terrain.js).

Sources by priority (mosaic order): NGU 1 m (inner Oslofjord) > Kartverket seabed 5/25 m > Kartverket seabed 50 m /
DTM10 land > EMODnet 1/16' (~115 m, North Sea) > GEBCO (gaps only).
Datums: land NN2000; Kartverket seabed = sjøkartnull (chart datum); EMODnet = LAT (MSL variant exists).
Convert to one vertical datum BEFORE merging; clip land with the OSM coastline polygon (MHW), not the 0 m contour.

Conventions
-----------
* Elevation is metres, positive up (land > 0, seabed < 0), in the target datum (NN2000 unless asked otherwise).
* A "source" is a dict: ``{name, path, priority, datum, licence, credit, [datum_offset_m], [nodata], [resampling]}``;
  ``priority`` 0 is the most authoritative; ``licence`` is mandatory (it travels into the manifest).
* The merged GeoTIFF has three float32 bands: 1 ``elevation``, 2 ``bathy_mask`` (1 = sea, 0 = land), 3 ``source_id``
  (1-based index into ``sources`` as given; 0 = filled gap). Source metadata is stored in the dataset tag OFFSIM_SOURCES.
* The mesh and hillshade apply per-domain exaggeration (TIERS) *after* the datum-true merge: the DEM stays honest,
  the display copy is exaggerated. The exaggerated z is what the mesh stores (metres, deck.gl z).
"""
import base64
import json
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

TIERS = {
    # name: (grid m, land exaggeration, sea exaggeration, mesh max_error m)
    "fjord": (50, 3.0, 5.0, 2.0),          # Oslofjord-wide
    "port": (10, 1.5, 2.0, 1.0),           # ~5x5 km close-ups (5 m or NGU 1 m at sea)
    "shelf": (115, 4.0, 30.0, 5.0),        # North Sea off Stavanger; 25–40x or trenches read flat
}
TEXTURE_MAX_PX = 4096                      # SwiftShader MAX_TEXTURE_SIZE is typically 8192; stay at half
ISOBATHS_M = {"fjord": [10, 20, 50, 100, 200, 300], "port": [5, 10, 20, 50], "shelf": [50, 100, 200, 300, 500, 700]}
MAX_TRIANGLES = 400_000                    # VISUAL_SPEC §1.6
MIN_ISOBATH_LEN_M = 1000.0                 # lines shorter than this are dropped
ISOBATH_SMOOTH_CELLS = 1.5                 # Gaussian sigma on the contour copy only; the DEM is never smoothed
ISOBATH_BOLD_EVERY = 5

# Height of each vertical datum's zero surface above NN2000, metres (z_target = z_src + offset_src - offset_target).
# These are ILLUSTRATION-GRADE ASSUMPTIONS, not geodetic transformations: sub-metre, below the mesh max_error of
# every tier, and fine for pictures that carry the "not for navigation" credit. Override per source with
# `datum_offset_m` when a surveyed value is known (Kartverket publishes sjøkartnull vs NN2000 per station).
DATUM_OFFSETS_M = {
    "NN2000": 0.0,           # land datum, defines zero
    "MSL": 0.0,              # assumption: NN2000 ~ mean sea level on the Norwegian coast
    "chart_datum": -0.3,     # assumption: sjøkartnull ~ LAT; ~0.3 m below NN2000 in the (micro-tidal) Oslofjord
    "LAT": -0.3,             # assumption: same as chart_datum; shelf stations are lower (~ -0.9 m at Stavanger)
    "EGM2008": 0.0,          # assumption: GEBCO is relative to sea level; treated as NN2000
}
DATUM_NOTES = {
    "chart_datum": "Kartverket sjøkartnull; offset assumed -0.3 m vs NN2000 (assumption: true)",
    "LAT": "EMODnet default is LAT; offset assumed -0.3 m vs NN2000, Stavanger shelf would be ~-0.9 m (assumption: true)",
    "MSL": "treated as NN2000 (assumption: true)",
    "EGM2008": "treated as NN2000 (assumption: true)",
    "NN2000": "reference",
}


# ---------------------------------------------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------------------------------------------
def _style():
    return json.loads((HERE.parent / "style.json").read_text())


def _rgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float32) / 255.0


def _tier(tier):
    if tier not in TIERS:
        raise ValueError(f"unknown tier {tier!r}; choose from {sorted(TIERS)}")
    grid, land_x, sea_x, err = TIERS[tier]
    return {"grid_m": grid, "land_exag": land_x, "sea_exag": sea_x, "max_error_m": err}


def _is_geographic(crs):
    from rasterio.crs import CRS
    return CRS.from_user_input(crs).is_geographic


def _read_cog(cog):
    """-> dict(elev, sea(bool), src_id, transform, crs, shape)."""
    import rasterio
    with rasterio.open(cog) as ds:
        if ds.count < 2:
            raise ValueError(f"{cog}: expected merge_dem output with bands elevation, bathy_mask, source_id")
        elev = ds.read(1).astype("float64")
        sea = ds.read(2) > 0.5
        sid = ds.read(3).astype("int32") if ds.count >= 3 else np.zeros(elev.shape, "int32")
        tags = ds.tags()
        return {"elev": elev, "sea": sea, "src_id": sid, "transform": ds.transform, "crs": ds.crs,
                "shape": elev.shape, "tags": tags}


def _cell_size_m(transform, crs, shape):
    """Cell size in metres: (dx per row (len H), dy scalar). Geographic grids use a spherical approximation."""
    h, _ = shape
    rx, ry = abs(transform.a), abs(transform.e)
    if _is_geographic(crs):
        lat = transform.f + (np.arange(h) + 0.5) * transform.e
        return rx * 111_320.0 * np.cos(np.radians(lat)), ry * 111_320.0
    return np.full(h, rx), ry


def _exaggerated(elev, sea, tier):
    t = _tier(tier)
    return np.where(sea, elev * t["sea_exag"], elev * t["land_exag"])


def _pix2xy(tf, col, row):
    """Affine * (col, row) for arrays (pixel coordinates, 0.5 = cell centre)."""
    col, row = np.asarray(col, float), np.asarray(row, float)
    return tf.c + tf.a * col + tf.b * row, tf.f + tf.d * col + tf.e * row


def _lonlat(crs, x, y):
    from pyproj import Transformer
    if _is_geographic(crs):
        return np.asarray(x, float), np.asarray(y, float)
    lon, lat = Transformer.from_crs(crs, 4326, always_xy=True).transform(x, y)
    return np.asarray(lon, float), np.asarray(lat, float)


def _geom_to_crs(geom, crs):
    from pyproj import Transformer
    from shapely.ops import transform as sh_transform
    if _is_geographic(crs):
        return geom
    tr = Transformer.from_crs(4326, crs, always_xy=True).transform
    return sh_transform(tr, geom)


def _load_land(land):
    """GeoJSON path / dict / shapely geometry (lon/lat) -> shapely geometry."""
    from shapely.geometry import shape
    from shapely.ops import unary_union
    if land is None:
        return None
    if hasattr(land, "geom_type"):
        return land
    if isinstance(land, (str, Path)):
        land = json.loads(Path(land).read_text())
    if land.get("type") == "FeatureCollection":
        return unary_union([shape(f["geometry"]) for f in land["features"] if f.get("geometry")])
    if land.get("type") == "Feature":
        return shape(land["geometry"])
    return shape(land)


def png_data_url(path):
    """Inline a PNG as a data URL (offline render: no fetch of files, no CDN)."""
    return "data:image/png;base64," + base64.b64encode(Path(path).read_bytes()).decode("ascii")


# ---------------------------------------------------------------------------------------------------------------
# 1. merge
# ---------------------------------------------------------------------------------------------------------------
def datum_offset(src_datum, target_datum="NN2000", override=None):
    """Metres to ADD to a source elevation to express it in `target_datum` (see DATUM_OFFSETS_M for assumptions)."""
    for d in (src_datum, target_datum):
        if d not in DATUM_OFFSETS_M:
            raise ValueError(f"unknown vertical datum {d!r}; known: {sorted(DATUM_OFFSETS_M)}")
    src_level = DATUM_OFFSETS_M[src_datum] if override is None else float(override)
    return src_level - DATUM_OFFSETS_M[target_datum]


def _feather_weight(valid, cells):
    """1 deep inside the valid area, ramping to 0 at its edge over `cells` (grid borders are not edges)."""
    from scipy.ndimage import distance_transform_edt
    if valid.all():
        return valid.astype("float64")
    pad = np.pad(valid, 1, mode="edge")
    d = distance_transform_edt(pad)[1:-1, 1:-1]
    return np.clip(d / max(cells, 1), 0.0, 1.0) * valid


def merge_dem(sources: list, bbox: tuple, crs: str, out_cog: str, datum: str = "NN2000", *, res=None, land=None,
              feather_cells: int = 4) -> dict:
    """Reproject, datum-shift, mosaic by priority with 3–5 cell feathering, burn coastline at 0 m;
    COG bands: elevation, bathy_mask, source_id. Returns a manifest entry with every source licence.

    sources: list of source dicts (module docstring). bbox: (west, south, east, north) lon/lat. crs: target CRS (e.g.
    EPSG:25832). res: cell size in `crs` units, number or (rx, ry); default 50 m (or ~0.00045 deg if geographic).
    land: OSM land polygon (lon/lat GeoJSON path/dict/shapely). Cells inside it get bathy_mask 0 and elevation >= 0;
    cells outside get bathy_mask 1 and elevation <= 0. Without `land`, the sign of the merged elevation decides.
    Gaps left after mosaicking are filled from the nearest valid cell (source_id 0, counted in the manifest).
    """
    import rasterio
    from rasterio.crs import CRS
    from rasterio.features import rasterize
    from rasterio.transform import from_origin
    from rasterio.warp import Resampling, reproject, transform_bounds
    from scipy.ndimage import distance_transform_edt

    if not sources:
        raise ValueError("merge_dem needs at least one source")
    for s in sources:
        for k in ("name", "path", "priority", "datum", "licence"):
            if s.get(k) in (None, ""):
                raise ValueError(f"source {s.get('name')!r} is missing '{k}'")
    dst_crs = CRS.from_user_input(crs)
    if res is None:
        res = 0.00045 if dst_crs.is_geographic else 50.0
    rx, ry = (res, res) if np.isscalar(res) else res
    x0, y0, x1, y1 = transform_bounds(4326, dst_crs, *bbox, densify_pts=21)
    w, h = int(np.ceil((x1 - x0) / rx)), int(np.ceil((y1 - y0) / ry))
    if w * h > 80_000_000:
        raise ValueError(f"grid {w}x{h} is too large; raise `res`")
    transform = rasterio.Affine(rx, 0, x0, 0, -ry, y1)

    order = sorted(range(len(sources)), key=lambda i: (sources[i]["priority"], i))
    out = np.full((h, w), np.nan)
    sid = np.zeros((h, w), "float32")
    entries = []
    for i in reversed(order):                       # lowest priority first; higher priority overwrites/blends on top
        s = sources[i]
        off = datum_offset(s["datum"], datum, s.get("datum_offset_m"))
        z = np.full((h, w), np.nan, dtype="float32")
        with rasterio.open(s["path"]) as src:
            if src.crs is None:
                raise ValueError(f"{s['path']}: no CRS")
            nd = s.get("nodata", src.nodata)
            reproject(source=rasterio.band(src, 1), destination=z, src_transform=src.transform, src_crs=src.crs,
                      src_nodata=nd, dst_transform=transform, dst_crs=dst_crs, dst_nodata=np.nan,
                      resampling=getattr(Resampling, s.get("resampling", "bilinear")))
        z = z.astype("float64")
        z[~np.isfinite(z) | (np.abs(z) > 1e5)] = np.nan
        valid = np.isfinite(z)
        z = z + off
        wgt = _feather_weight(valid, feather_cells)
        base = out
        blended = np.where(np.isnan(base), z, wgt * z + (1.0 - wgt) * base)
        out = np.where(valid, blended, base)
        sid = np.where(valid & (np.isnan(base) | (wgt >= 0.5)), float(i + 1), sid).astype("float32")
        entries.append({"name": s["name"], "priority": s["priority"], "datum": s["datum"],
                        "datum_offset_m": round(off, 3), "assumption": s.get("datum_offset_m") is None,
                        "datum_note": DATUM_NOTES.get(s["datum"], ""), "licence": s["licence"],
                        "credit": s.get("credit", ""), "path": str(s["path"]), "source_id": i + 1,
                        "cells_valid": int(valid.sum())})
    entries.sort(key=lambda e: e["source_id"])

    gaps = ~np.isfinite(out)
    if gaps.all():
        raise ValueError("no source covers the bbox")
    if gaps.any():
        idx = distance_transform_edt(gaps, return_distances=False, return_indices=True)
        out = out[tuple(idx)]
        sid = np.where(gaps, 0.0, sid).astype("float32")

    geom = _load_land(land)
    if geom is not None:
        mask_land = rasterize([(_geom_to_crs(geom, dst_crs), 1)], out_shape=(h, w), transform=transform,
                              fill=0, dtype="uint8", all_touched=False).astype(bool)
    else:
        mask_land = out >= 0
    out = np.where(mask_land, np.maximum(out, 0.0), np.minimum(out, 0.0))   # burn coast at 0 m both ways
    bands = [out.astype("float32"), (~mask_land).astype("float32"), sid.astype("float32")]

    manifest = {"bbox": list(bbox), "crs": dst_crs.to_string(), "res": [rx, ry], "shape": [h, w], "datum": datum,
                "land_polygon": geom is not None, "filled_gap_cells": int(gaps.sum()),
                "feather_cells": feather_cells, "bands": ["elevation", "bathy_mask", "source_id"], "sources": entries,
                "elevation_range_m": [float(out.min()), float(out.max())], "out": str(out_cog)}
    Path(out_cog).parent.mkdir(parents=True, exist_ok=True)
    profile = dict(driver="GTiff", height=h, width=w, count=3, dtype="float32", crs=dst_crs, transform=transform,
                   compress="deflate", predictor=3, tiled=True, blockxsize=256, blockysize=256)
    tmp = str(out_cog) + ".tmp.tif"
    with rasterio.open(tmp, "w", **profile) as dst:
        for n, (b, d) in enumerate(zip(bands, manifest["bands"]), 1):
            dst.write(b, n)
            dst.set_band_description(n, d)
        dst.update_tags(OFFSIM_SOURCES=json.dumps(manifest))
    try:                                            # COG driver needs GDAL >= 3.1; plain tiled GTiff otherwise
        import rasterio.shutil as rsh
        rsh.copy(tmp, str(out_cog), driver="COG", compress="deflate")
        Path(tmp).unlink()
        manifest["container"] = "COG"
    except Exception:
        Path(tmp).replace(out_cog)
        manifest["container"] = "GTiff (tiled)"
    return manifest


# ---------------------------------------------------------------------------------------------------------------
# 2. mesh
# ---------------------------------------------------------------------------------------------------------------
def terrain_mesh(cog: str, tier: str) -> dict:
    """pydelatin TIN (max_error per TIERS) → {positions (lon, lat, z·exaggeration), indices, normals}; 150–400k triangles.

    Returns numpy arrays: positions (N,3) float64 lon, lat, z [m, exaggerated land/sea per TIERS]; normals (N,3) unit,
    local east/north/up from the exaggerated surface; texcoords (N,2) in [0,1] over the DEM grid (u east, v north-up:
    flipY-free convention, v=1 north), matching hillshade_texture; indices (M*3,) uint32 counter-clockwise from above;
    bounds [west, south, east, north, zmin, zmax]. max_error is applied to the exaggerated surface (conservative: true
    error is max_error / exaggeration). The mesh is capped at MAX_TRIANGLES; small DEMs simply yield fewer triangles.
    """
    from pydelatin import Delatin

    t = _tier(tier)
    d = _read_cog(cog)
    elev, sea, tf, crs = d["elev"], d["sea"], d["transform"], d["crs"]
    h, w = elev.shape
    zx = _exaggerated(elev, sea, tier).astype("float32")
    cap = MAX_TRIANGLES
    while True:                                                   # Delatin can overshoot max_triangles by a few
        tin = Delatin(zx, max_error=t["max_error_m"], max_triangles=cap)
        if len(tin.triangles) <= MAX_TRIANGLES:
            break
        cap -= max(8, len(tin.triangles) - MAX_TRIANGLES + 8)
    v = np.asarray(tin.vertices, dtype="float64")               # x = col, y = h-1-row (y up), z
    tri = np.asarray(tin.triangles, dtype="int64").reshape(-1, 3)
    col, row = v[:, 0], (h - 1) - v[:, 1]
    xs, ys = _pix2xy(tf, col + 0.5, row + 0.5)
    lon, lat = _lonlat(crs, xs, ys)
    z = v[:, 2]
    if _is_geographic(crs):                                       # metric frame for normals
        mx = (lon - lon.mean()) * 111_320.0 * np.cos(np.radians(lat.mean()))
        my = (lat - lat.mean()) * 111_320.0
    else:
        mx, my = np.asarray(xs), np.asarray(ys)
    p = np.column_stack([mx, my, z])
    n = np.cross(p[tri[:, 1]] - p[tri[:, 0]], p[tri[:, 2]] - p[tri[:, 0]])
    if (n[:, 2] < 0).sum() > len(n) / 2:                          # enforce CCW seen from above
        tri = tri[:, [0, 2, 1]]
        n = -n
    vn = np.zeros_like(p)
    for k in range(3):
        np.add.at(vn, tri[:, k], n)
    ln = np.linalg.norm(vn, axis=1, keepdims=True)
    vn = np.where(ln > 0, vn / np.where(ln > 0, ln, 1), [0.0, 0.0, 1.0])
    u = (col + 0.5) / w
    vv = 1.0 - (row + 0.5) / h
    return {"positions": np.column_stack([lon, lat, z]), "indices": tri.reshape(-1).astype("uint32"), "normals": vn,
            "texcoords": np.column_stack([u, vv]), "triangles": int(len(tri)), "vertices": int(len(p)),
            "bounds": [float(lon.min()), float(lat.min()), float(lon.max()), float(lat.max()), float(z.min()),
                       float(z.max())],
            "tier": tier, "exaggeration": {"land": t["land_exag"], "sea": t["sea_exag"]},
            "max_error_m": t["max_error_m"]}


# ---------------------------------------------------------------------------------------------------------------
# 3. hillshade
# ---------------------------------------------------------------------------------------------------------------
# Multidirectional hillshade: four light azimuths around the key light, weighted toward the key (GDAL's
# -multidirectional uses 225/270/315/360 with slope-dependent weights; we use fixed weights, same look at poster scale).
_MD_OFFSETS = (-90.0, -45.0, 0.0, 45.0)
_MD_WEIGHTS = (0.15, 0.25, 0.40, 0.20)


def _hillshade(z, dx_row, dy, azimuth, altitude):
    """z exaggerated metres (row 0 = north). Returns shade in 0..1 (flat ground = sin(altitude))."""
    gy_rows, gx = np.gradient(z, dy, axis=0), np.gradient(z, axis=1) / dx_row[:, None]
    dz_dn = -gy_rows                                           # rows run north -> south
    dz_de = gx
    nz = 1.0 / np.sqrt(1.0 + dz_de ** 2 + dz_dn ** 2)
    ne, nn = -dz_de * nz, -dz_dn * nz
    alt = np.radians(altitude)
    shade = np.zeros_like(z)
    for off, wt in zip(_MD_OFFSETS, _MD_WEIGHTS):
        az = np.radians(azimuth + off)
        le, ln_, lz = np.sin(az) * np.cos(alt), np.cos(az) * np.cos(alt), np.sin(alt)
        shade += wt * np.clip(ne * le + nn * ln_ + nz * lz, 0.0, 1.0)
    return shade


def hillshade_texture(cog: str, tier: str, azimuth: float = 315, altitude: float = 35, out_png: str = None) -> dict:
    """Multidirectional hillshade × depth/elevation tint (sea: water -> ink, darker with depth; land: muted grey-green
    from style.json), baked PNG ≤ TEXTURE_MAX_PX, for BitmapLayer or mesh texture (cheaper than runtime lighting on
    SwiftShader). Computed on the exaggerated surface so relief reads at the same strength as the mesh.

    Returns {path, width, height, bounds [w,s,e,n], corners [[lon,lat] x4: bottom-left, top-left, top-right,
    bottom-right] (BitmapLayer quad bounds; exact for rotated UTM grids), tier, azimuth, altitude}. `path` defaults to
    <cog stem>_hillshade.png. Use png_data_url(path) to inline it. Row 0 of the PNG is north.
    """
    from PIL import Image

    d = _read_cog(cog)
    elev, sea, tf, crs = d["elev"], d["sea"], d["transform"], d["crs"]
    h, w = elev.shape
    t = _tier(tier)
    zx = _exaggerated(elev, sea, tier)
    dxr, dy = _cell_size_m(tf, crs, elev.shape)
    shade = _hillshade(zx, dxr, dy, azimuth, altitude)
    rel = np.clip(shade / np.sin(np.radians(altitude)), 0.0, 2.0)[..., None]      # flat ground = 1

    st = _style()
    water, ink, land, dim, paper = (_rgb(st[k]) for k in ("water", "ink", "land", "dim", "paper"))
    sea_shallow = water + 0.22 * (dim - water)                                      # dark navy-ink, a touch lighter
    sea_deep = ink * 0.55
    land_low = land + 0.18 * (dim - land)                                           # muted grey-green
    land_high = land + 0.35 * (paper - land)
    dmax = float(max(ISOBATHS_M[tier]))
    depth = np.clip(-elev / dmax, 0.0, 1.0)[..., None] ** 0.6
    hgt = np.clip(elev / max(float(st.get("land_relief_m", 600)), 1.0), 0.0, 1.0)[..., None]
    sea_c = sea_shallow + depth * (sea_deep - sea_shallow)
    land_c = land_low + hgt * (land_high - land_low)
    base = np.where(sea[..., None], sea_c, land_c)
    k = np.where(sea[..., None], 0.70 + 0.30 * rel, 0.55 + 0.45 * rel)
    rgb = np.clip(base * k, 0.0, 1.0)
    img = Image.fromarray((rgb * 255 + 0.5).astype("uint8"), "RGB")
    if max(img.size) > TEXTURE_MAX_PX:
        s = TEXTURE_MAX_PX / max(img.size)
        img = img.resize((max(1, int(round(w * s))), max(1, int(round(h * s)))), Image.LANCZOS)
    path = Path(out_png) if out_png else Path(str(cog).rsplit(".", 1)[0] + "_hillshade.png")
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, optimize=True)
    # corners of the raster in lon/lat (pixel edges), order: BL, TL, TR, BR
    xs = [tf.c, tf.c, tf.c + tf.a * w, tf.c + tf.a * w]
    ys = [tf.f + tf.e * h, tf.f, tf.f, tf.f + tf.e * h]
    lon, lat = _lonlat(crs, np.array(xs), np.array(ys))
    corners = [[float(a), float(b)] for a, b in zip(lon, lat)]
    return {"path": str(path), "width": img.size[0], "height": img.size[1],
            "bounds": [float(lon.min()), float(lat.min()), float(lon.max()), float(lat.max())],
            "corners": corners, "tier": tier, "azimuth": azimuth, "altitude": altitude}


# ---------------------------------------------------------------------------------------------------------------
# 4. isobaths
# ---------------------------------------------------------------------------------------------------------------
def isobaths(cog: str, tier: str, levels=None, bold_every: int = ISOBATH_BOLD_EVERY, out_geojson: str = None) -> dict:
    """Contours of a Gaussian-smoothed copy (skimage.measure.find_contours), simplified to 0.5 cell, lines < 1 km
    dropped, every 5th level bold, depth labels → GeoJSON FeatureCollection (dict) for PathLayer (CAD-style).

    levels: depths in metres (positive), default ISOBATHS_M[tier]. Feature properties: depth (m), label ("50 m"),
    bold (bool: 1-based level index % bold_every == 0), level_index, length_m. Geometry: LineString [lon, lat].
    Written to `out_geojson` too when given.
    """
    from scipy.ndimage import gaussian_filter
    from shapely.geometry import LineString, mapping
    from skimage.measure import find_contours

    _tier(tier)
    levels = list(levels if levels is not None else ISOBATHS_M[tier])
    d = _read_cog(cog)
    elev, sea, tf, crs = d["elev"], d["sea"], d["transform"], d["crs"]
    depth = np.where(sea, -elev, 0.0)                         # land counts as 0 m deep: contours stay at sea
    smooth = gaussian_filter(depth, ISOBATH_SMOOTH_CELLS, mode="nearest")
    dxr, dy = _cell_size_m(tf, crs, elev.shape)
    cell = float(np.median(np.sqrt(dxr * dy)))
    feats = []
    for li, lev in enumerate(levels, 1):
        for c in find_contours(smooth, float(lev)):
            rows, cols = c[:, 0], c[:, 1]
            xs, ys = _pix2xy(tf, cols + 0.5, rows + 0.5)
            lon, lat = _lonlat(crs, np.asarray(xs), np.asarray(ys))
            # metric polyline for simplification and length
            if _is_geographic(crs):
                mx = lon * 111_320.0 * np.cos(np.radians(lat.mean()))
                my = lat * 111_320.0
            else:
                mx, my = np.asarray(xs), np.asarray(ys)
            line = LineString(np.column_stack([mx, my])).simplify(0.5 * cell, preserve_topology=False)
            if line.length < MIN_ISOBATH_LEN_M or len(line.coords) < 2:
                continue
            # map simplified metric vertices back to lon/lat by nearest original vertex (exact: simplify keeps vertices)
            lookup = {(round(a, 3), round(b, 3)): k for k, (a, b) in enumerate(zip(mx, my))}
            ids = [lookup[(round(a, 3), round(b, 3))] for a, b in line.coords if (round(a, 3), round(b, 3)) in lookup]
            if len(ids) < 2:
                continue
            ll = LineString(np.column_stack([lon[ids], lat[ids]]))
            feats.append({"type": "Feature", "geometry": mapping(ll),
                          "properties": {"depth": lev, "label": f"{lev:g} m", "bold": li % bold_every == 0,
                                         "level_index": li, "length_m": round(line.length, 1)}})
    fc = {"type": "FeatureCollection", "features": feats}
    if out_geojson:
        Path(out_geojson).parent.mkdir(parents=True, exist_ok=True)
        Path(out_geojson).write_text(json.dumps(fc, separators=(",", ":")))
    return fc


# ---------------------------------------------------------------------------------------------------------------
# 5. world build
# ---------------------------------------------------------------------------------------------------------------
def _round_list(a, nd):
    return np.round(np.asarray(a, dtype="float64"), nd).reshape(-1).tolist()


def build_world_depth(world: str, tier: str, dem_path, land_geojson=None, out_dir=None, *, bbox=None, crs=None) -> dict:
    """Run the whole depth chain for one world/tier and write, into data/worlds/<world>/depth/<tier>/ (or `out_dir`):
    terrain.json, hillshade.png, isobaths.geojson, depth_manifest.json (+ dem.tif when it merged here).

    dem_path: (a) path to a merge_dem GeoTIFF (3 bands) - used as is; (b) path to a plain single-band DEM (treated as one
    NN2000 source) or (c) a list of source dicts - both merged here with `land_geojson` at the tier grid, `bbox` (default
    offsim/worlds/<world>.yaml) and `crs` (default yaml depth.crs, else EPSG:25832). Returns the manifest (also written).

    terrain.json (consumed by render_deck/src/layers/terrain.js): see that file for the exact shape.
    """
    import rasterio
    import yaml

    t = _tier(tier)
    out = Path(out_dir) if out_dir else ROOT / "data/worlds" / world / "depth" / tier
    out.mkdir(parents=True, exist_ok=True)
    cfg_path = HERE / f"{world}.yaml"
    cfg = yaml.safe_load(cfg_path.read_text()) if cfg_path.exists() else {}
    merge_info = None
    cog = None
    if isinstance(dem_path, (str, Path)):
        with rasterio.open(dem_path) as ds:
            merged = ds.count >= 3 and "OFFSIM_SOURCES" in ds.tags()
        if merged:
            cog = str(dem_path)
    if cog is None:
        srcs = dem_path if isinstance(dem_path, list) else [
            {"name": Path(dem_path).name, "path": str(dem_path), "priority": 0, "datum": "NN2000",
             "licence": "unspecified (single-band input)"}]
        bb = bbox or cfg.get("bbox")
        if bb is None:
            raise ValueError("bbox needed to merge (not in world yaml)")
        cr = crs or (cfg.get("depth") or {}).get("crs") or "EPSG:25832"
        grid = t["grid_m"]
        if _is_geographic(cr):
            mid = (bb[1] + bb[3]) / 2
            res = (grid / (111_320.0 * np.cos(np.radians(mid))), grid / 111_320.0)
        else:
            res = grid
        cog = str(out / "dem.tif")
        merge_info = merge_dem(srcs, tuple(bb), cr, cog, res=res, land=land_geojson)
    with rasterio.open(cog) as ds:
        merge_info = merge_info or json.loads(ds.tags().get("OFFSIM_SOURCES", "{}"))

    mesh = terrain_mesh(cog, tier)
    tex = hillshade_texture(cog, tier, out_png=str(out / "hillshade.png"))
    iso = isobaths(cog, tier, out_geojson=str(out / "isobaths.geojson"))
    terrain = {
        "version": 1, "world": world, "tier": tier, "bounds": mesh["bounds"],
        "exaggeration": mesh["exaggeration"], "triangles": mesh["triangles"], "vertices": mesh["vertices"],
        "positions": _round_list(mesh["positions"], 6), "normals": _round_list(mesh["normals"], 3),
        "texcoords": _round_list(mesh["texcoords"], 5), "indices": mesh["indices"].astype(int).tolist(),
        "texture": {"file": "hillshade.png", "width": tex["width"], "height": tex["height"],
                    "bounds": tex["bounds"], "corners": tex["corners"]},
    }
    (out / "terrain.json").write_text(json.dumps(terrain, separators=(",", ":")))
    credits = sorted({s["credit"] for s in merge_info.get("sources", []) if s.get("credit")})
    manifest = {
        "world": world, "tier": tier, "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "grid_m": t["grid_m"], "exaggeration": mesh["exaggeration"], "max_error_m": t["max_error_m"],
        "triangles": mesh["triangles"], "triangle_budget": MAX_TRIANGLES,
        "texture_px": [tex["width"], tex["height"]], "texture_max_px": TEXTURE_MAX_PX,
        "isobath_depths_m": ISOBATHS_M[tier], "isobath_features": len(iso["features"]),
        "bounds": mesh["bounds"], "land_polygon": str(land_geojson) if isinstance(land_geojson, (str, Path)) else bool(land_geojson),
        "dem": merge_info, "credits": credits,
        "notice": "illustrative bathymetry, not for navigation",
        "files": {f: (out / f).stat().st_size for f in ("terrain.json", "hillshade.png", "isobaths.geojson")},
    }
    (out / "depth_manifest.json").write_text(json.dumps(manifest, indent=1))
    return manifest


def build_from_raw(world: str, tier: str, raw_dir=None, out_dir=None) -> dict:
    """Process what `fetch_world --pull <world> --depth` unpacked: data/worlds/<world>/dem_raw/sources.json (+ land.geojson)."""
    root = ROOT / "data/worlds" / world
    raw = Path(raw_dir or root / "dem_raw")
    spec = json.loads((raw / "sources.json").read_text())
    srcs = [{**s, "path": str(raw / s["path"])} for s in spec["sources"]]
    land = root / "land.geojson"
    return build_world_depth(world, tier, srcs, land if land.exists() else None, out_dir, crs=spec.get("crs"))


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="terrain.json + hillshade.png + isobaths.geojson from fetched raw DEMs")
    ap.add_argument("--world", required=True)
    ap.add_argument("--tier", required=True, choices=sorted(TIERS))
    ap.add_argument("--out")
    a = ap.parse_args()
    m = build_from_raw(a.world, a.tier, out_dir=a.out)
    print(json.dumps({k: m[k] for k in ("world", "tier", "triangles", "texture_px", "isobath_features", "files")}, indent=1))
