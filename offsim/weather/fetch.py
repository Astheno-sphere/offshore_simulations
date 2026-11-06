"""Metocean subsetting for the fetch-world workflow. Runs on GitHub Actions: thredds.met.no is blocked in the Claude workspace.

Library: xarray + netCDF4 over OPeNDAP. URLs and variable names below were taken from the metocean-api (MIT)
source, v1.1.14 (`metocean_api/ts/internal/metno/met_products.py`), because the servers cannot be reached here.
`verified` therefore means "matches metocean-api source", NOT "opened live"; `live_checked` stays False until the
first Actions run has logged a successful open (record it in docs/TESTLOG.md). A dataset we could not trace to a
source has `verified: False` and `subset` raises NotImplementedError("unverified: ...") for it.

Output per dataset: NetCDF4, dims (time, lat, lon) on a REGULAR lon/lat grid, int16 scale/offset, zlib.
Canonical variables: nora3_wind -> u10, v10 (m/s, to-direction components, from wind_speed + wind_direction);
nora3_wave -> hs (m), tp (s), thq (deg); norkyst_v3 -> u, v (m/s east/north, shallowest depth level).
"""
from __future__ import annotations

import math
import time
from datetime import datetime, timedelta, timezone

import numpy as np

LICENCE = "CC BY 4.0 — MET Norway"
THREDDS = "https://thredds.met.no/thredds/dodsC"


def _month_urls(pattern):
    def f(start: datetime, end: datetime):
        out, d = [], datetime(start.year, start.month, 1)
        while d <= end:
            out.append(pattern.format(ym=d.strftime("%Y%m")))
            d = datetime(d.year + (d.month == 12), d.month % 12 + 1, 1)
        return out
    return f


def _norkyst_v3_urls(start: datetime, end: datetime):
    lo, hi = datetime(2012, 1, 5), datetime(2025, 12, 31, 23)
    if start < lo or end > hi + timedelta(hours=1):
        raise NotImplementedError(f"unverified: norkyst_v3 URL pattern is only known for {lo:%F}..{hi:%F} "
                                  "(metocean-api 1.1.14); extend after checking the THREDDS catalog romshindcast/norkyst_v3")
    out, d = [], datetime(start.year, start.month, start.day)
    while d <= end:
        out.append(f"{THREDDS}/romshindcast/norkyst_v3/zdepth/{d:%Y}/{d:%m}/norkyst800-{d:%Y%m%d}.nc")
        d += timedelta(days=1)
    return out


DATASETS = {
    "nora3_wind": {
        "verified": True, "live_checked": False,
        "catalog": "nora3-wind-wave", "native_res_m": 3000.0,
        "urls": _month_urls(THREDDS + "/nora3_subset_atmos/wind_hourly_v2/arome3kmwind_1hr_{ym}.nc"),
        "native_vars": ["wind_speed", "wind_direction"], "out_vars": ["u10", "v10"],
        "lonlat": ("longitude", "latitude"), "select": {"height": 10.0},
        "source": "metocean-api 1.1.14 NORA3WindSub; dims time,height,y,x; lon/lat 2D; wind_direction is meteorological (from)",
        "note": "3 km hourly. Open risks: height coordinate value 10 assumed; wind_direction assumed relative to true north.",
    },
    "nora3_wave": {
        "verified": True, "live_checked": False,
        "catalog": "nora3-wind-wave", "native_res_m": 3000.0,
        "urls": _month_urls(THREDDS + "/nora3_subset_wave/wave_tser/{ym}_NORA3wave_sub_time_unlimited.nc"),
        "native_vars": ["hs", "tp", "thq"], "out_vars": ["hs", "tp", "thq"],
        "lonlat": ("longitude", "latitude"), "select": {},
        "source": "metocean-api 1.1.14 Nora3WaveSub (inherits Nora3Wave: rotated grid dims rlat,rlon; lon/lat 2D; vars hs,tp,thq)",
        "note": "Hourly. Open risk: that the *_sub_time_unlimited file holds the full grid, not point series (code raises if lon/lat are 1D).",
    },
    "norkyst_v3": {
        "verified": True, "live_checked": False,
        "catalog": "norkyst-v3-800m", "native_res_m": 800.0,
        "urls": _norkyst_v3_urls,
        "native_vars": ["u_eastward", "v_northward"], "out_vars": ["u", "v"],
        "lonlat": ("lon", "lat"), "select": {"depth": "shallowest"},
        "source": "metocean-api 1.1.14 Norkyst800_v3 (daily zdepth files 2012-01-05..2025-12-31; dims time,depth,Y,X; lon/lat 2D)",
        "note": "Curvilinear: regridded to regular lon/lat. u_eastward/v_northward are already geographic. 2026+ unverified.",
    },
    "wam800": {
        "verified": False, "live_checked": False,
        "catalog": "mywavewam800", "native_res_m": 800.0, "urls": None,
        "native_vars": ["hs", "tp", "thq"], "out_vars": ["hs", "tp", "thq"],
        "source": "none: path mywavewam800 not found in metocean-api; forecast archive only",
        "note": "unverified",
    },
}

METOCEAN_API_PRODUCT = {"nora3_wind": "NORA3_wind_sub", "nora3_wave": "NORA3_wave_sub", "norkyst_v3": "NORKYST800_V3"}


def _parse_utc(s: str) -> datetime:
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return (d.astimezone(timezone.utc) if d.tzinfo else d).replace(tzinfo=None)


def _spec(dataset: str) -> dict:
    if dataset not in DATASETS:
        raise KeyError(dataset)
    spec = DATASETS[dataset]
    if not spec["verified"] or not spec.get("urls"):
        raise NotImplementedError(f"unverified: {dataset}: {spec['source']}")
    return spec


def _open(url: str):
    """Open one OPeNDAP URL lazily (isolated so tests can substitute synthetic datasets)."""
    import xarray as xr
    return xr.open_dataset(url, decode_timedelta=False)


def _spatial_window(ds, lonlat, bbox, pad_cells=2):
    """Index slices of the two spatial dims covering bbox (from the 2D lon/lat arrays; small, loaded eagerly)."""
    lon, lat = ds[lonlat[0]], ds[lonlat[1]]
    if lon.ndim != 2:
        raise ValueError(f"expected 2D {lonlat} on a curvilinear grid, got dims {lon.dims}")
    w, s, e, n = bbox
    lo, la = np.asarray(lon.values, float), np.asarray(lat.values, float)
    hit = (lo >= w) & (lo <= e) & (la >= s) & (la <= n)
    if not hit.any():
        raise ValueError(f"bbox {bbox} does not intersect the dataset grid")
    d0, d1 = lon.dims
    r, c = np.where(hit)
    return {d0: slice(max(int(r.min()) - pad_cells, 0), int(r.max()) + pad_cells + 1),
            d1: slice(max(int(c.min()) - pad_cells, 0), int(c.max()) + pad_cells + 1)}


def _canonical(name: str, spec: dict, ds):
    """Native variables -> canonical ones (still on the native grid)."""
    import xarray as xr
    sel = dict(spec.get("select", {}))
    if sel.get("depth") == "shallowest" and "depth" in ds.dims:
        ds = ds.isel(depth=int(np.argmin(np.abs(ds["depth"].values))))
        sel.pop("depth")
    elif sel.get("depth") == "shallowest":
        sel.pop("depth")
    for k, v in sel.items():
        if k in ds.dims:
            ds = ds.sel({k: v}, method="nearest")
    if name == "nora3_wind":
        ws, wd = ds["wind_speed"], np.deg2rad(ds["wind_direction"])
        out = xr.Dataset({"u10": -ws * np.sin(wd), "v10": -ws * np.cos(wd)})
        out["u10"].attrs.update(units="m s-1", long_name="10 m wind, eastward component (towards)")
        out["v10"].attrs.update(units="m s-1", long_name="10 m wind, northward component (towards)")
    else:
        out = xr.Dataset({o: ds[n] for n, o in zip(spec["native_vars"], spec["out_vars"])})
        if name == "norkyst_v3":
            out["u"].attrs.update(units="m s-1"); out["v"].attrs.update(units="m s-1")
    keep = [v for v in (spec["lonlat"][0], spec["lonlat"][1]) if v in ds]
    for v in keep:
        out[v] = ds[v]
    return out.set_coords(keep)


def regrid_to_lonlat(ds, lonlat=("lon", "lat"), res_m: float = 800.0, bbox=None):
    """Curvilinear (2D lon/lat) -> regular lon/lat (dims time, lat, lon) by Delaunay-linear interpolation.
    The triangulation is built once and reused for every time step and variable. Cells outside the source
    grid and NaN (land) neighbours stay NaN."""
    import xarray as xr
    from scipy.interpolate import LinearNDInterpolator

    lon2, lat2 = np.asarray(ds[lonlat[0]].values, float), np.asarray(ds[lonlat[1]].values, float)
    w, s, e, n = bbox if bbox else (np.nanmin(lon2), np.nanmin(lat2), np.nanmax(lon2), np.nanmax(lat2))
    dlat = res_m / 111_320.0
    dlon = dlat / math.cos(math.radians((s + n) / 2))
    glon = w + dlon * np.arange(int((e - w) / dlon + 1e-9) + 1)
    glat = s + dlat * np.arange(int((n - s) / dlat + 1e-9) + 1)
    gx, gy = np.meshgrid(glon, glat)
    pts = np.column_stack([lon2.ravel(), lat2.ravel()])
    sdims = ds[lonlat[0]].dims
    out = {}
    for name, v in ds.data_vars.items():
        if not set(sdims) <= set(v.dims):
            continue
        v = v.transpose(*[d for d in v.dims if d not in sdims], *sdims)
        lead = v.shape[:-2]
        flat = np.asarray(v.values, float).reshape(-1, lon2.size)
        res = np.full((flat.shape[0], glat.size, glon.size), np.nan)
        f, last = None, None
        for i, row in enumerate(flat):
            ok = np.isfinite(row)
            if not ok.any():
                continue
            if f is not None and np.array_equal(ok, last):
                f.values[:, 0] = row[ok]  # same mask: reuse the triangulation, swap the values
            else:
                f, last = LinearNDInterpolator(pts[ok], row[ok], fill_value=np.nan), ok
            res[i] = f(gx, gy)
        res = res.reshape(*lead, glat.size, glon.size)
        out[name] = (tuple(d for d in v.dims if d not in sdims) + ("lat", "lon"), res.astype("float32"), v.attrs)
    coords = {"lat": glat, "lon": glon}
    if "time" in ds.coords:
        coords["time"] = ds["time"].values
    return xr.Dataset({k: xr.DataArray(a, dims=d, attrs=at) for k, (d, a, at) in out.items()}, coords=coords)


def int16_encoding(ds) -> dict:
    """Per-variable int16 scale/offset: 65534 levels between min and max, -32768 reserved for NaN."""
    enc = {}
    for name, v in ds.data_vars.items():
        a = v.values[np.isfinite(v.values)]
        lo, hi = (float(a.min()), float(a.max())) if a.size else (0.0, 1.0)
        scale = (hi - lo) / 65534.0 or 1.0
        enc[name] = {"dtype": "int16", "scale_factor": scale, "add_offset": lo + 32767.0 * scale,
                     "_FillValue": np.int16(-32768), "zlib": True, "complevel": 4}
    return enc


def _engine():
    try:
        import netCDF4  # noqa: F401
        return "netcdf4"
    except ImportError:
        return "h5netcdf"


def subset(dataset: str, bbox: tuple, start_utc: str, hours: int, out_path: str) -> dict:
    """Open OPeNDAP, select bbox/time server-side, regrid to a regular lon/lat grid, scale to int16, write NetCDF.
    bbox = (west, south, east, north) degrees; start_utc ISO 'YYYY-MM-DDTHH:MM'; hours = length (hourly steps, inclusive start).
    Returns a manifest entry {dataset, url, urls, licence 'CC BY 4.0 — MET Norway', vars, shape, bbox, fetched_utc, ...}.
    Raises NotImplementedError('unverified: ...') for a dataset whose server path/variables are not traced to a source."""
    import xarray as xr

    spec = _spec(dataset)
    t0 = _parse_utc(start_utc)
    t1 = t0 + timedelta(hours=hours - 1)
    urls = spec["urls"](t0, t1)
    lonlat = spec["lonlat"]
    parts, window = [], None
    for url in urls:
        ds = _open(url)
        if window is None:
            window = _spatial_window(ds, lonlat, bbox)
        ds = ds[[v for v in ds.variables if v in spec["native_vars"] or v in lonlat or v in ("time", "height", "depth")]]
        ds = ds.isel(window).sel(time=slice(np.datetime64(t0), np.datetime64(t1)))
        if ds.sizes.get("time", 0) == 0:
            continue
        parts.append(_canonical(dataset, spec, ds).load())
    if not parts:
        raise ValueError(f"{dataset}: no time steps in {t0:%FT%H}..{t1:%FT%H} UTC")
    keep = [v for v in lonlat if v in parts[0].coords]
    if len(parts) > 1:  # lon/lat are static: concat only the time-varying data
        parts = [p.drop_vars(keep) if i else p for i, p in enumerate(parts)]
        ds = xr.concat(parts, dim="time", data_vars="minimal", coords="minimal", compat="override")
    else:
        ds = parts[0]
    reg = regrid_to_lonlat(ds, lonlat, spec["native_res_m"], bbox)
    reg = reg.assign_attrs(title=f"{dataset} subset", licence=LICENCE, source_urls=" ".join(urls),
                           history=f"offsim.weather.fetch.subset {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}")
    reg.to_netcdf(out_path, engine=_engine(), encoding=int16_encoding(reg))
    return {"dataset": dataset, "catalog": spec["catalog"], "url": urls[0], "urls": urls, "licence": LICENCE,
            "credit": "MET Norway (CC BY 4.0)", "vars": list(reg.data_vars),
            "shape": [int(reg.sizes[d]) for d in ("time", "lat", "lon")], "bbox": list(bbox),
            "start_utc": f"{t0:%Y-%m-%dT%H:%M}", "hours": hours, "file": str(out_path),
            "verified_source": spec["source"], "live_checked": spec["live_checked"],
            "fetched_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def point_series(dataset: str, lon: float, lat: float, start_utc: str, end_utc: str):
    """Hourly series at one site via metocean-api (operability statistics, weather windows). Returns a pandas DataFrame.
    NotImplementedError if metocean-api is not installed or the dataset has no verified metocean-api product."""
    prod = METOCEAN_API_PRODUCT.get(dataset)
    if prod is None:
        raise NotImplementedError(f"unverified: no metocean-api product for {dataset}")
    try:
        from metocean_api import ts
    except ImportError as exc:
        raise NotImplementedError("metocean-api not installed (pip install metocean-api)") from exc
    t = ts.TimeSeries(lon=lon, lat=lat, start_time=start_utc, end_time=end_utc, product=prod)
    t.import_data(save_csv=False)
    return t.data
