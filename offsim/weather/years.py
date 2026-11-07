"""Weather years for the ensemble: NORA3 netCDF (as written by offsim.weather.fetch) -> WeatherSeries per season.

load_years(path_or_dir, point, years, season=None) -> list[WeatherSeries]
- path_or_dir: one NetCDF file or a directory of *.nc. Wave and wind products are separate files in fetch.py
  (nora3_wave -> hs, tp, thq; nora3_wind -> u10, v10); files are merged on time at the chosen point.
- point = (lon, lat), WGS84. Nearest grid cell (regular lat/lon grid, or 2D lon/lat arrays). Raises if the
  nearest cell is farther than `max_dist_km` or is NaN (land / outside the grid): nothing is filled or guessed.
- Columns: t (s from the season's nominal start), hs_m, wind_mps (hypot of u10, v10, or wind_speed), tp_s and
  dir_deg (wave direction thq) when present. Missing hs or wind raises: the engines need both.
- season: None = calendar year; else month initials such as "DJF", "JJA", "NDJM" (list of month numbers also
  accepted). Year Y with a season that wraps the new year starts in Y: "DJF" 2010 = 1 Dec 2010 .. 28 Feb 2011.
  WeatherSeries.year = Y; source = "NORA3 DJF 2010/11". Seasons missing from the data raise ValueError.
- Variable names follow fetch.py (metocean-api 1.1.14 names); they have not been checked against a live file
  (see docs/AUDIT.md). Alternative names accepted: hs_m, tp_s, wind_mps, wind_speed.

synthetic_years: TEST-ONLY generator. Never used for reported results; its source string says so and
Ensemble.to_report flags synthetic_weather.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from offsim.engines.base import WeatherSeries

SYNTHETIC_SOURCE = "SYNTHETIC (test only)"
_MON = "JFMAMJJASOND"
_RAW = ("hs", "hs_m", "tp", "tp_s", "thq", "dir_deg", "u10", "v10", "wind_speed", "wind_mps")


def haversine_m(lon1, lat1, lon2, lat2):
    """Great-circle metres (local copy: L0 must not import the contract layer)."""
    lon1, lat1, lon2, lat2 = map(np.radians, (lon1, lat1, lon2, lat2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6_371_008.8 * np.arcsin(np.sqrt(a))


def season_months(season) -> list[int]:
    """'DJF' -> [12, 1, 2]; None -> 1..12; a list of ints must be consecutive (mod 12)."""
    if season is None:
        return list(range(1, 13))
    if not isinstance(season, str):
        m = [int(x) for x in season]
        if not m or any((m[i + 1] - m[i]) % 12 != 1 for i in range(len(m) - 1)) or not all(1 <= x <= 12 for x in m):
            raise ValueError(f"season months must be consecutive 1..12, got {season!r}")
        return m
    s = season.strip().upper()
    dbl = _MON * 2
    hits = [i for i in range(12) if len(s) <= 12 and dbl[i:i + len(s)] == s]
    if len(hits) != 1:
        raise ValueError(f"season {season!r} is {'ambiguous' if hits else 'not a run of months'} (use e.g. 'DJF')")
    return [(hits[0] + k) % 12 + 1 for k in range(len(s))]


def _nearest(ds, lon: float, lat: float):
    """Dataset reduced to the nearest grid cell, plus that cell's (lon, lat)."""
    if "lat" in ds.dims and "lon" in ds.dims:
        pt = ds.sel(lat=lat, lon=lon, method="nearest")
        return pt, float(pt["lon"]), float(pt["lat"])
    for nx, ny in (("longitude", "latitude"), ("lon", "lat")):
        if nx in ds and ny in ds and ds[nx].ndim == 2:
            lo, la = ds[nx].values, ds[ny].values
            d = haversine_m(lo, la, lon, lat)
            i, j = np.unravel_index(int(np.nanargmin(d)), d.shape)
            pt = ds.isel({ds[nx].dims[0]: int(i), ds[nx].dims[1]: int(j)})
            return pt, float(lo[i, j]), float(la[i, j])
    raise ValueError("cannot find a lat/lon grid (dims lat, lon or 2D longitude/latitude) in the dataset")


def _point_frame(path: Path, lon: float, lat: float, max_dist_km: float) -> pd.DataFrame:
    import xarray as xr

    with xr.open_dataset(path) as ds:
        if "time" not in ds.coords or ds["time"].dtype.kind != "M":
            raise ValueError(f"{path}: needs a decoded datetime 'time' coordinate")
        pt, glon, glat = _nearest(ds, lon, lat)
        dist = float(haversine_m(glon, glat, lon, lat)) / 1000.0
        if dist > max_dist_km:
            raise ValueError(f"{path}: nearest grid cell is {dist:.1f} km from ({lon}, {lat}) (> {max_dist_km} km)")
        cols = {}
        for v in _RAW:
            if v in pt.data_vars:
                a = pt[v].squeeze(drop=True)
                if a.dims != ("time",):
                    raise ValueError(f"{path}: variable {v} has dims {a.dims} at the point, expected ('time',)")
                cols[v] = pd.Series(np.asarray(a.values, float), index=pd.DatetimeIndex(pt["time"].values))
    if not cols:
        raise ValueError(f"{path}: none of {_RAW} found")
    return pd.DataFrame(cols)


def _canonical(raw: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=raw.index)
    for dst, srcs in (("hs_m", ("hs_m", "hs")), ("tp_s", ("tp_s", "tp")), ("dir_deg", ("dir_deg", "thq"))):
        for s in srcs:
            if s in raw:
                out[dst] = raw[s]
                break
    if "wind_mps" in raw:
        out["wind_mps"] = raw["wind_mps"]
    elif "wind_speed" in raw:
        out["wind_mps"] = raw["wind_speed"]
    elif "u10" in raw and "v10" in raw:
        out["wind_mps"] = np.hypot(raw["u10"], raw["v10"])
    missing = [c for c in ("hs_m", "wind_mps") if c not in out]
    if missing:
        raise ValueError(f"missing {missing}: give both the nora3_wave and nora3_wind files (or a directory of both)")
    return out[["hs_m", "wind_mps"] + [c for c in ("tp_s", "dir_deg") if c in out]]


def load_years(path_or_dir, point: tuple[float, float], years, season=None, dataset: str = "NORA3",
               max_dist_km: float = 30.0) -> list[WeatherSeries]:
    """One WeatherSeries per year (or season-of-year) at `point` = (lon, lat). See module docstring."""
    p = Path(path_or_dir)
    files = sorted(p.glob("*.nc")) if p.is_dir() else [p]
    if not files or not all(f.exists() for f in files):
        raise FileNotFoundError(f"no NetCDF files at {p}")
    lon, lat = float(point[0]), float(point[1])
    raw = pd.concat([_point_frame(f, lon, lat, max_dist_km) for f in files])
    raw = raw.groupby(level=0).first().sort_index()   # merges wave+wind files and monthly files of one product
    df_all = _canonical(raw)
    months = season_months(season)
    out = []
    for y in years:
        start = pd.Timestamp(int(y), months[0], 1)
        end = start + pd.DateOffset(months=len(months))
        d = df_all[(df_all.index >= start) & (df_all.index < end)]
        if d.empty:
            raise ValueError(f"no data for {season or 'year'} {y} ({start:%F}..{end:%F}); "
                             f"data span {df_all.index.min():%F}..{df_all.index.max():%F}")
        if d.isna().any().any():
            bad = d.isna().sum()
            raise ValueError(f"NaN at the point in {season or 'year'} {y}: {bad[bad > 0].to_dict()} "
                             "(land cell or gap; choose another point)")
        df = d.copy()
        df.insert(0, "t", (df.index - start).total_seconds().to_numpy(float))
        df = df.reset_index(drop=True)
        label = f"{y}/{str(int(y) + 1)[-2:]}" if (end - pd.DateOffset(days=1)).year > start.year else f"{y}"
        tag = f"{season} " if season else ""
        out.append(WeatherSeries(df, f"{dataset} {tag}{label}", int(y)))
    return out


def synthetic_years(n: int, hours: int, seed: int, hs_mean: float = 2.0) -> list[WeatherSeries]:
    """TEST-ONLY synthetic weather: AR(1) log-Hs with random storms. NOT a metocean model, never calibrated,
    never used for reported results (source = "SYNTHETIC (test only)"; year is None).

    Each series is hourly, columns t, hs_m, wind_mps, tp_s; deterministic in (seed, index). `hs_mean` is the
    approximate mean of the background sea state before storms (storms raise the realised mean).
    """
    out = []
    phi, sig = 0.985, 0.35
    for i in range(n):
        rng = np.random.default_rng([int(seed), i])
        x = np.empty(hours)
        x[0] = rng.normal(0, sig / np.sqrt(1 - phi ** 2))
        eps = rng.normal(0, sig, hours)
        for k in range(1, hours):
            x[k] = phi * x[k - 1] + eps[k]
        var = sig ** 2 / (1 - phi ** 2)
        hs = hs_mean * np.exp(x - var / 2)
        h = np.arange(hours)
        for _ in range(rng.poisson(hours / 240.0)):
            c, w, a = rng.uniform(0, hours), rng.uniform(8, 24), rng.uniform(1.5, 4.0)
            hs = hs + a * np.exp(-0.5 * ((h - c) / w) ** 2)
        hs = np.clip(hs, 0.1, 14.0)
        wind = np.clip(2.0 + 2.6 * np.sqrt(hs) + rng.normal(0, 1.0, hours), 0.3, None)
        tp = np.clip(3.5 + 2.2 * np.sqrt(hs) + rng.normal(0, 0.5, hours), 2.0, None)
        df = pd.DataFrame({"t": h * 3600.0, "hs_m": hs, "wind_mps": wind, "tp_s": tp})
        out.append(WeatherSeries(df, SYNTHETIC_SOURCE, None))
    return out
