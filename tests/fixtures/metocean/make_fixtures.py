"""Builds the small synthetic MET Norway monthly files the metocean-api tests serve instead of thredds.met.no.

NOT real NORA3 data. The structure is modelled on what metocean-api 1.1.14 expects when it reads the two products
(`metocean_api/ts/internal/metno/met_products.py`): they have NOT been compared with a live server file.

  nora3_wave   <YYYYMM>_NORA3wave_sub_time_unlimited.nc   dims time, rlat, rlon; 2D longitude/latitude(rlat, rlon);
                                                          vars hs (m), tp (s), thq (deg) + hs_sea (unrequested extra)
  nora3_wind   arome3kmwind_1hr_<YYYYMM>.nc               dims time, height, y, x; 2D longitude/latitude(y, x);
                                                          vars wind_speed (m/s), wind_direction (deg), per height

The 3 x 3 grid is centred on POINT = (lon 3.0, lat 60.6). Values are deterministic in (product, year, month), smooth,
and different at every height so that reading the wrong height or the wrong variable changes the answer.

    python tests/fixtures/metocean/make_fixtures.py [OUT_DIR]       # rewrites the committed set (Dec 2000 - Feb 2001)
"""
from __future__ import annotations

import calendar
import sys
from pathlib import Path

import numpy as np
import xarray as xr

HERE = Path(__file__).resolve().parent
POINT = (3.0, 60.6)                      # lon, lat: the centre cell of the grid
HEIGHTS = (10.0, 20.0, 50.0)
WAVE_NAME = "{ym}_NORA3wave_sub_time_unlimited.nc"
WIND_NAME = "arome3kmwind_1hr_{ym}.nc"
COMMITTED = ((2000, 12), (2001, 1), (2001, 2))


def hours(year: int, month: int) -> np.ndarray:
    n = calendar.monthrange(year, month)[1] * 24
    return np.datetime64(f"{year:04d}-{month:02d}-01T00:00:00") + np.arange(n) * np.timedelta64(1, "h")


def _series(n: int, phase: float, base: float, amp: float) -> np.ndarray:
    k = np.arange(n)
    return base + amp * np.sin(2 * np.pi * k / 61.0 + phase) + 0.4 * amp * np.sin(2 * np.pi * k / 11.0)


def wave_file(year: int, month: int) -> xr.Dataset:
    t = hours(year, month)
    ph = year * 0.7 + month
    rlat, rlon = np.arange(3.0), np.arange(3.0)
    lat = np.array([[60.5 + 0.1 * i] * 3 for i in range(3)])
    lon = np.array([[2.9 + 0.1 * j for j in range(3)] for _ in range(3)])
    hs = np.clip(_series(len(t), ph, 3.0, 1.6), 0.2, None)
    tp = np.clip(_series(len(t), ph + 1, 9.0, 2.0), 3.0, None)
    thq = np.mod(_series(len(t), ph + 2, 200.0, 60.0), 360.0)       # cells differ by degrees (below), not a factor
    cell = (1.0 + 0.02 * np.arange(9).reshape(3, 3))              # the centre cell (index 4) has factor 1.08
    f = lambda v: (v[:, None, None] * cell[None]).astype("float32")
    g = lambda v: np.mod(v[:, None, None] + np.arange(9).reshape(3, 3)[None], 360.0).astype("float32")
    attrs = dict(hs=("m", "sea_surface_wave_significant_height"), tp=("s", "sea_surface_wave_period_at_variance_spectral_density_maximum"),
                 thq=("degrees", "sea_surface_wave_from_direction"), hs_sea=("m", "sea_surface_wind_wave_significant_height"))
    data = {"hs": f(hs), "tp": f(tp), "thq": g(thq), "hs_sea": f(hs * 0.6)}
    ds = xr.Dataset({k: (("time", "rlat", "rlon"), v, {"units": attrs[k][0], "standard_name": attrs[k][1]}) for k, v in data.items()},
                    coords={"time": t, "rlat": rlat, "rlon": rlon})
    ds["longitude"] = (("rlat", "rlon"), lon)
    ds["latitude"] = (("rlat", "rlon"), lat)
    return ds


def wind_file(year: int, month: int) -> xr.Dataset:
    t = hours(year, month)
    ph = year * 0.3 + month
    y, x = np.arange(3.0), np.arange(3.0)
    lat = np.array([[60.5 + 0.1 * i] * 3 for i in range(3)])
    lon = np.array([[2.9 + 0.1 * j for j in range(3)] for _ in range(3)])
    ws10 = np.clip(_series(len(t), ph, 11.0, 4.0), 0.5, None)
    wd10 = np.mod(_series(len(t), ph + 3, 240.0, 80.0), 360.0)
    ws = np.stack([ws10 * (1.0 + 0.15 * h) for h in range(len(HEIGHTS))], axis=1)       # [time, height]
    wd = np.stack([np.mod(wd10 + 5.0 * h, 360.0) for h in range(len(HEIGHTS))], axis=1)
    cell = (1.0 + 0.02 * np.arange(9).reshape(3, 3))
    full = lambda a: (a[:, :, None, None] * cell[None, None]).astype("float32")
    wdir = np.mod(wd[:, :, None, None] + np.arange(9).reshape(3, 3)[None, None], 360.0).astype("float32")   # cells differ by degrees, not a factor
    ds = xr.Dataset({"wind_speed": (("time", "height", "y", "x"), full(ws), {"units": "m s-1", "standard_name": "wind_speed"}),
                     "wind_direction": (("time", "height", "y", "x"), wdir, {"units": "degree", "standard_name": "wind_from_direction"})},
                    coords={"time": t, "height": np.array(HEIGHTS), "y": y, "x": x})
    ds["longitude"] = (("y", "x"), lon)
    ds["latitude"] = (("y", "x"), lat)
    return ds


def write_month(out_dir: Path, product: str, year: int, month: int) -> Path:
    ym = f"{year:04d}{month:02d}"
    name = WAVE_NAME if product == "nora3_wave" else WIND_NAME
    ds = wave_file(year, month) if product == "nora3_wave" else wind_file(year, month)
    path = Path(out_dir) / name.format(ym=ym)
    path.parent.mkdir(parents=True, exist_ok=True)
    ds.to_netcdf(path, engine="netcdf4", encoding={v: {"zlib": True, "complevel": 6} for v in ds.data_vars})
    return path


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE
    for p in ("nora3_wave", "nora3_wind"):
        for y, m in COMMITTED:
            print(write_month(out, p, y, m))
