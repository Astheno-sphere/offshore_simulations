"""Terrain as texture (docs/STYLE_REFERENCE.md rule 13): hillshade + slope from a DEM, tinted in the palette's ground
tones, as an RGBA layer to put under every map. Never fakes terrain: for_bbox returns None plus a reason when the world
has no DEM product.

    rgba = hillshade_rgba(dem, cellsize_m, look.PALETTES["section-plan"], azimuth=315, altitude=45)
    rgba, why = for_bbox("data/worlds/oslofjord", (10.4, 59.6, 10.9, 59.95), (800, 600), palette)

Conventions match offsim.worlds.depth: row 0 of the array is north, columns run west -> east. Pure numpy (the hillshade is
the standard Horn-style normal-vector model; xarray-spatial gives the same result and is not needed).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np


def _rgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float64)


def hillshade_rgba(dem_array, cellsize_m, palette, azimuth=315.0, altitude=45.0, z=1.0, alpha_range=(0.10, 0.90),
                   slope_full_deg=40.0, smooth_sigma=0.0):
    """RGBA uint8 (H, W, 4) hillshade tinted with `palette` (ground_deep -> ground -> streak_hi), alpha rising with slope.

    dem_array: (H, W) metres, row 0 north; NaN = no data (alpha 0). cellsize_m: scalar, or (dx, dy). azimuth: light
    direction in degrees clockwise from north (315 = from the NW); altitude: light elevation above horizon; z: vertical
    exaggeration. Flat ground gets shade = sin(altitude) -> the palette ground colour at low alpha; lit flanks lighten
    toward streak_hi, shaded flanks darken toward ground_deep; alpha_range = (flat, slope_full_deg-or-steeper).
    smooth_sigma: Gaussian blur (cells) applied to the DEM before the gradient — the 50 m EMODnet grid is noisy at
    film scale, and unblurred it reads as dirt, not relief (v9 terrain fix).
    """
    dem = np.asarray(dem_array, dtype=np.float64)
    if dem.ndim != 2 or min(dem.shape) < 3:
        raise ValueError("dem_array must be 2-D with at least 3x3 cells")
    dx, dy = (cellsize_m, cellsize_m) if np.isscalar(cellsize_m) else cellsize_m
    nodata = ~np.isfinite(dem)
    zz = np.where(nodata, np.nanmean(dem) if (~nodata).any() else 0.0, dem) * z
    if smooth_sigma:
        from scipy.ndimage import gaussian_filter
        zz = gaussian_filter(zz, smooth_sigma)
    gy, gx = np.gradient(zz, dy, dx)                         # d/drow, d/dcol
    dz_de, dz_dn = gx, -gy
    slope = np.hypot(dz_de, dz_dn)
    nz = 1.0 / np.sqrt(1.0 + slope ** 2)
    ne, nn = -dz_de * nz, -dz_dn * nz
    alt, az = np.radians(altitude), np.radians(azimuth)
    shade = np.clip(ne * np.sin(az) * np.cos(alt) + nn * np.cos(az) * np.cos(alt) + nz * np.sin(alt), 0.0, 1.0)
    rel = (shade / np.sin(alt))[..., None]                   # flat ground = 1
    deep, ground, hi = _rgb(palette["ground_deep"]), _rgb(palette["ground"]), _rgb(palette.get("streak_hi", "#c9a98c"))
    dark = deep + np.clip(rel, 0, 1) * (ground - deep)
    light = ground + np.clip((rel - 1.0) * 0.8, 0, 1) * (hi - ground) * 0.6
    rgb = np.where(rel < 1.0, dark, light)
    slope_deg = np.degrees(np.arctan(slope))
    a0, a1 = alpha_range
    alpha = a0 + (a1 - a0) * np.clip(slope_deg / slope_full_deg, 0.0, 1.0)
    alpha = np.where(nodata, 0.0, alpha)
    out = np.concatenate([rgb, (alpha * 255.0)[..., None]], axis=-1)
    return np.clip(out + 0.5, 0, 255).astype("uint8")


def _find_dem(world_dir):
    w = Path(world_dir)
    cands = sorted(w.glob("depth/*/dem.tif")) + ([w / "dem.tif"] if (w / "dem.tif").exists() else [])
    if not cands:
        return None
    try:
        from .depth import TIERS
        cands.sort(key=lambda p: TIERS.get(p.parent.name, (1e9,))[0])      # finest grid first
    except Exception:
        pass
    return cands[0]


def for_bbox(world_dir, bbox, size, palette=None, azimuth=315.0, altitude=45.0, z=1.0, land_only=True,
             smooth_sigma=0.0, alpha_range=None):
    """Hillshade RGBA for lon/lat bbox (w, s, e, n) at size (width_px, height_px) from the world's merged DEM
    (data/worlds/<world>/depth/<tier>/dem.tif from offsim.worlds.depth.build_world_depth).

    Returns (rgba (h, w, 4) uint8, "ok: <dem path>") or (None, reason). Never synthesises terrain: if there is no DEM, or
    it does not cover the bbox, the reason says what to fetch (fetch-world workflow, then fetch_world --pull). Sea cells
    (band 2) are transparent when land_only. Hillshade is computed at DEM resolution, then resampled to `size`.
    smooth_sigma / alpha_range: v9 terrain tuning — blur the noisy 50 m grid and cap the slope alpha so relief reads
    as texture, not speckle (defaults keep the old look).
    """
    if palette is None:
        from ..cinema import look
        palette = look.PALETTES["section-plan"]
    dem_path = _find_dem(world_dir)
    if dem_path is None:
        return None, (f"no DEM product under {world_dir} (expected depth/<tier>/dem.tif); run the fetch-world workflow "
                      f"and `python -m offsim.worlds.fetch_world --pull <world>`, then offsim.worlds.depth.build_world_depth")
    try:
        import rasterio
        from rasterio.windows import from_bounds
        from rasterio.warp import transform_bounds
        from rasterio.crs import CRS
        from PIL import Image
    except Exception as e:
        return None, f"rasterio/PIL unavailable: {e}"
    with rasterio.open(dem_path) as ds:
        b = transform_bounds(CRS.from_epsg(4326), ds.crs, *bbox, densify_pts=21)
        db = ds.bounds
        if b[0] >= db.right or b[2] <= db.left or b[1] >= db.top or b[3] <= db.bottom:
            return None, f"bbox {tuple(bbox)} lies outside the DEM {dem_path} (bounds {tuple(db)} in {ds.crs})"
        win = from_bounds(*b, transform=ds.transform).round_offsets().round_lengths()
        elev = ds.read(1, window=win, boundless=True, fill_value=np.nan).astype("float64")
        sea = ds.read(2, window=win, boundless=True, fill_value=0) > 0.5 if ds.count >= 2 else np.zeros(elev.shape, bool)
        tf = ds.window_transform(win)
        geographic = ds.crs.is_geographic
        lat0 = (bbox[1] + bbox[3]) / 2
    if min(elev.shape) < 3:
        return None, f"DEM window for bbox is {elev.shape}, too small to shade"
    if geographic:
        dx, dy = abs(tf.a) * 111_320.0 * np.cos(np.radians(lat0)), abs(tf.e) * 111_320.0
    else:
        dx, dy = abs(tf.a), abs(tf.e)
    rgba = hillshade_rgba(elev, (dx, dy), palette, azimuth, altitude, z,
                          alpha_range=alpha_range or (0.10, 0.90), smooth_sigma=smooth_sigma)
    if land_only:
        rgba[..., 3] = np.where(sea, 0, rgba[..., 3])
    img = Image.fromarray(rgba, "RGBA")
    pm = Image.fromarray((rgba[..., :3].astype("float32") * (rgba[..., 3:4] / 255.0)).astype("uint8"), "RGB")
    # resample premultiplied to avoid dark fringes, then un-premultiply
    a = img.getchannel("A").resize(tuple(size), Image.BILINEAR)
    c = pm.resize(tuple(size), Image.BILINEAR)
    ca, aa = np.asarray(c, dtype="float32"), np.asarray(a, dtype="float32")[..., None]
    rgb = np.where(aa > 0, ca * 255.0 / np.maximum(aa, 1.0), 0.0)
    return np.clip(np.concatenate([rgb, aa], axis=-1) + 0.5, 0, 255).astype("uint8"), f"ok: {dem_path}"
