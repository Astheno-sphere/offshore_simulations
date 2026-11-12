"""NORA3 point series through MET Norway's `metocean-api`: a resumable, month-by-month fetch of many winters.

Runs where the internet is open (a VM, GitHub Actions). The Claude workspace cannot reach thredds.met.no: everything
here is proven offline against small synthetic files (tests/fixtures/metocean/), and the first live run is what turns
the catalog status from `wired` into `tested` (docs/ENGINES.md, "Weather data: two backends").

    python -m offsim.worlds.metocean_api fetch --world bergen-ncs --point 3.0,60.6 --years 2000-2023 --season DJF
    python -m offsim.worlds.metocean_api status --world bergen-ncs        # what is on disk, what is missing
    python -m offsim.worlds.metocean_api stats --world bergen-ncs --point 3.0,60.6 --years 2000-2023 --season DJF

Why this exists next to `offsim.weather.fetch` (the bbox/OPeNDAP subsetter, still the default): that path fetches one
period for a whole box in one stage with one wall budget. A 24-winter point series is 144 independent requests
(2 products x 24 winters x 3 months); this backend makes each one a unit that is fetched, validated and written on its own.

Design (the point is that a killed run loses at most the unit in flight):
  unit      = (product, year-month). One file `pt_<product>_<YYYYMM>.nc`, written to `*.tmp` and renamed, so a file
              either does not exist or is whole. The library is called once per month (it downloads and merges the
              whole requested span in memory and keeps nothing if it fails half way).
  resume    = on start every expected file is opened and checked (variables, hours, NaN, range, requested point). Valid
              ones are skipped; bad ones are moved aside to `*.bad`; only the missing units are fetched.
  timeout   = each unit runs in its own subprocess with a hard wall limit (`--unit-timeout`, default 600 s) and is
              killed on expiry. A SIGALRM budget cannot do this: netCDF4's OPeNDAP reads block inside C code, where
              Python never gets to run the signal handler (the likely reason the first 30-minute stage never ended).
              A `.dodsrc` with HTTP.TIMEOUT / HTTP.CONNECTTIMEOUT is also written for the child (best effort).
  manifest  = `manifest.json` in the output directory, rewritten after every unit: per-unit status, attempts, error,
              nearest grid cell, seconds; plus a summary and an `errors` list in the shape fetch_world uses.
  breaker   = `--max-consecutive-failures` (default 6) stops a run against a dead server instead of burning hours.

Variables are mapped by an explicit table (PRODUCTS). A name that is not in it raises `VariableMappingError`; nothing
passes through under a guessed name. The stored names are exactly the ones `offsim.weather.years.load_years` reads
(hs, tp, thq, wind_speed), so `weather: {dir: <out>, point: [lon, lat], years: [...], season: DJF}` works unchanged.

Licences: metocean-api LGPL-2.1-or-later (imported here, lazily, never modified or vendored). metocean-stats MIT but it
requires `lmoments3` (GPL-3.0): it is only ever run in a child process (`stats`), never imported by this module.
Data: MET Norway, CC BY 4.0.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import math
import os
import re
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
BACKEND = "metocean-api"
LICENCE = "CC BY 4.0 — MET Norway"
CREDIT = "MET Norway (CC BY 4.0)"
MANIFEST = "manifest.json"
DEFAULT_UNIT_TIMEOUT_S = 600
DEFAULT_MAX_DIST_KM = 10.0       # NORA3 is a 3 km grid; metocean-api itself only refuses beyond 50 km
GPL_MODULES = ("metocean_stats", "lmoments3")


class MetoceanApiError(Exception):
    """Base class. `permanent` errors are not retried (a retry would give the same answer)."""
    permanent = False


class VariableMappingError(MetoceanApiError):
    permanent = True


class DataValidationError(MetoceanApiError):
    permanent = True


class UnitTimeout(MetoceanApiError):
    pass


class UnitFailed(MetoceanApiError):
    pass


class PointMismatch(MetoceanApiError):
    permanent = True


class UnsupportedProduct(MetoceanApiError):
    """Asked for something this backend deliberately does not fetch (currents). Not a spec stub: nothing is pending."""
    permanent = True


# --------------------------------------------------------------------------------------------------------------------
# Variable mapping. Names come from the installed library (metocean-api 1.1.14, ts/internal/metno/met_products.py).
# --------------------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Var:
    lib: str          # column in the DataFrame the library returns
    stored: str       # variable name in our NetCDF; for the consumed ones this IS the name offsim.weather.years reads
    units: str
    years_name: str | None   # canonical column offsim.weather.years builds from it (None: stored, not consumed there)
    lo: float         # plausible range, inclusive; outside raises (catches fill values and unit mistakes)
    hi: float


@dataclass(frozen=True)
class Product:
    key: str                  # our name; matches offsim.weather.fetch dataset names
    api: str                  # metocean-api product string
    request_vars: tuple       # `variable=` passed to TimeSeries
    height: tuple | None      # `height=` passed to TimeSeries (wind is flattened to <var>_<h>m columns)
    vars: tuple
    convention: str           # as declared by the library (`Convention`), recorded in the file
    url_pattern: str          # documentation only; the library builds the real URL


PRODUCTS: dict[str, Product] = {
    "nora3_wave": Product(
        "nora3_wave", "NORA3_wave_sub", ("hs", "tp", "thq"), None,
        (Var("hs", "hs", "m", "hs_m", 0.0, 30.0),
         Var("tp", "tp", "s", "tp_s", 0.0, 40.0),
         Var("thq", "thq", "degrees", "dir_deg", 0.0, 360.0)),
        "OCEANIC (library Nora3Wave.convention: direction towards)",
        "https://thredds.met.no/thredds/dodsC/nora3_subset_wave/wave_tser/<YYYYMM>_NORA3wave_sub_time_unlimited.nc"),
    "nora3_wind": Product(
        "nora3_wind", "NORA3_wind_sub", ("wind_speed", "wind_direction"), (10,),
        (Var("wind_speed_10m", "wind_speed", "m s-1", "wind_mps", 0.0, 90.0),
         Var("wind_direction_10m", "wind_direction", "degrees", None, 0.0, 360.0)),
        "METEOROLOGICAL (library NORA3WindSub.convention: direction from)",
        "https://thredds.met.no/thredds/dodsC/nora3_subset_atmos/wind_hourly_v2/arome3kmwind_1hr_<YYYYMM>.nc"),
}

# Documented, NOT fetched by this backend: surface current. offsim.weather.years does not consume it; the bbox backend
# (offsim.weather.fetch, norkyst_v3) still provides it for the visual layer.
CURRENT_MAPPING = {"product": "NORKYST800_V3", "u_eastward": "u", "v_northward": "v",
                   "note": "fetch.py names; not fetched here (daily files, heavy; years.py does not read currents)"}


def product(key: str) -> Product:
    if key == "norkyst_v3":
        raise UnsupportedProduct("currents are not fetched by the metocean-api backend: " + CURRENT_MAPPING["note"])
    if key not in PRODUCTS:
        raise VariableMappingError(f"unknown product {key!r}; this backend has {sorted(PRODUCTS)}")
    return PRODUCTS[key]


def map_variable(product_key: str, lib_name: str) -> Var:
    """Library column name -> Var. Raises VariableMappingError for anything not in the table."""
    for v in product(product_key).vars:
        if v.lib == lib_name:
            return v
    raise VariableMappingError(
        f"{product_key}: library column {lib_name!r} is not mapped; known: {[v.lib for v in product(product_key).vars]}")


def map_columns(product_key: str, df: pd.DataFrame) -> pd.DataFrame:
    """DataFrame from metocean-api -> DataFrame with our stored names, in table order.
    Both directions are strict: a missing expected column and an unexpected extra column raise (an extra column means the
    request returned something other than what we asked for, e.g. every height instead of 10 m)."""
    prod = product(product_key)
    have, want = list(df.columns), [v.lib for v in prod.vars]
    missing = [c for c in want if c not in have]
    extra = [c for c in have if c not in want]
    if missing or extra:
        raise VariableMappingError(
            f"{product_key}: library returned columns {have}; expected exactly {want} "
            f"(missing {missing}, unexpected {extra}). Not guessing a mapping.")
    return pd.DataFrame({v.stored: df[v.lib].to_numpy(float) for v in prod.vars}, index=df.index)


# --------------------------------------------------------------------------------------------------------------------
# Units
# --------------------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Unit:
    product: str
    year: int
    month: int

    @property
    def ym(self) -> str:
        return f"{self.year:04d}{self.month:02d}"

    @property
    def key(self) -> str:
        return f"{self.product}:{self.ym}"

    @property
    def filename(self) -> str:
        return f"pt_{self.product}_{self.ym}.nc"

    @property
    def start(self) -> str:                       # 'YYYY-MM-DD': the library cannot take 'YYYY-MM-DDTHH:MM' for *_sub products
        return f"{self.year:04d}-{self.month:02d}-01"

    @property
    def end(self) -> str:
        return f"{self.year:04d}-{self.month:02d}-{pd.Timestamp(self.year, self.month, 1).days_in_month:02d}"

    def expected_index(self) -> pd.DatetimeIndex:
        t0 = pd.Timestamp(self.year, self.month, 1)
        return pd.date_range(t0, periods=t0.days_in_month * 24, freq="h")


def season_months(season) -> list[int]:
    """'DJF' -> [12, 1, 2]; None -> 1..12 (same rule as offsim.weather.years.season_months)."""
    from offsim.weather.years import season_months as sm
    return sm(season)


def month_units(years, season, products=("nora3_wave", "nora3_wind")) -> list[Unit]:
    """Every (product, month) a load_years(years, season) call will read. Year Y of a season that wraps the new year
    starts in Y: 'DJF' 2000 = Dec 2000, Jan 2001, Feb 2001."""
    months = season_months(season)
    units = []
    for y in years:
        start = pd.Timestamp(int(y), months[0], 1)
        for k in range(len(months)):
            m = start + pd.DateOffset(months=k)
            units += [Unit(p, int(m.year), int(m.month)) for p in products]
    for p in products:
        product(p)
    return sorted(set(units), key=lambda u: (u.year, u.month, u.product))


def parse_years(text: str) -> list[int]:
    """'2000-2023' -> 2000..2023; '2001,2005' -> [2001, 2005]; mixed forms allowed."""
    out = []
    for part in str(text).split(","):
        m = re.fullmatch(r"\s*(\d{4})\s*-\s*(\d{4})\s*", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if b < a:
                raise ValueError(f"year range {part!r} runs backwards")
            out += list(range(a, b + 1))
        elif re.fullmatch(r"\s*\d{4}\s*", part):
            out.append(int(part))
        else:
            raise ValueError(f"cannot read years from {part!r} (use 2000-2023 or 2001,2005)")
    return sorted(set(out))


def parse_point(text: str) -> tuple[float, float]:
    m = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*", str(text))
    if not m:
        raise ValueError(f"point must be 'lon,lat' (e.g. 3.0,60.6), got {text!r}")
    lon, lat = float(m.group(1)), float(m.group(2))
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise ValueError(f"point out of range: lon {lon}, lat {lat} (order is lon,lat)")
    return lon, lat


def haversine_km(lon1, lat1, lon2, lat2) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (lon1, lat1, lon2, lat2))
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(a))


# --------------------------------------------------------------------------------------------------------------------
# One unit: library call -> mapped, validated frame -> atomic NetCDF
# --------------------------------------------------------------------------------------------------------------------
def library_version() -> str | None:
    try:
        from importlib.metadata import version
        return version("metocean-api")
    except Exception:  # noqa: BLE001
        return None


@contextlib.contextmanager
def url_mirror(directory):
    """Serve every http(s) URL that `xarray.open_dataset` is asked for from `directory/<last path segment>`.
    Offline mode for tests and for pre-downloaded monthly files. A URL whose file is not in the mirror raises
    FileNotFoundError: it never falls through to the network. Local paths pass through."""
    import xarray as xr
    directory = Path(directory)
    orig = xr.open_dataset

    def served(path, *a, **k):
        if isinstance(path, str) and re.match(r"https?://", path):
            local = directory / path.rsplit("/", 1)[1]
            if not local.exists():
                raise FileNotFoundError(f"mirror {directory}: no file for {path}")
            return orig(str(local), *a, **k)
        return orig(path, *a, **k)

    xr.open_dataset = served
    try:
        yield
    finally:
        xr.open_dataset = orig


def fetch_frame(unit: Unit, point, workdir: Path) -> tuple[pd.DataFrame, float, float, list[str], dict]:
    """Call metocean-api for one month at `point`. Returns (library frame, lon_data, lat_data, source urls, headers).
    The library writes its cache/ directory into the current directory, so chdir into `workdir` for the call."""
    try:
        from metocean_api import ts
        from metocean_api.ts.internal import products as lib_products
    except ImportError as exc:
        raise MetoceanApiError("metocean-api is not installed (pip install metocean-api)") from exc
    prod = product(unit.product)
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    series = ts.TimeSeries(lon=point[0], lat=point[1], start_time=unit.start, end_time=unit.end,
                           variable=list(prod.request_vars), name=f"offsim-{unit.key}", product=prod.api,
                           height=list(prod.height) if prod.height else None)
    old = Path.cwd()
    os.chdir(workdir)
    try:
        series.import_data(save_csv=False, save_nc=False, use_cache=False)
    finally:
        os.chdir(old)
    if series.data is None or series.lon_data is None or series.lat_data is None:
        raise UnitFailed(f"{unit.key}: library returned no data")
    urls = lib_products.find_product(prod.api).get_url_for_dates(unit.start, unit.end)
    return series.data, float(series.lon_data), float(series.lat_data), urls, {}


def validate_frame(unit: Unit, mapped: pd.DataFrame) -> None:
    """Hourly, whole month, no NaN, plausible values. Raises DataValidationError naming the first problem."""
    prod = product(unit.product)
    idx = pd.DatetimeIndex(mapped.index)
    if idx.has_duplicates:
        raise DataValidationError(f"{unit.key}: duplicate timestamps")
    want = unit.expected_index()
    if not idx.equals(want):
        missing = want.difference(idx)
        extra = idx.difference(want)
        raise DataValidationError(
            f"{unit.key}: expected {len(want)} hourly steps {want[0]:%F %H}..{want[-1]:%F %H}, got {len(idx)} "
            f"({len(missing)} missing, first {missing[0] if len(missing) else '-'}; {len(extra)} extra)")
    for v in prod.vars:
        a = mapped[v.stored].to_numpy(float)
        bad = int(np.isnan(a).sum())
        if bad:
            raise DataValidationError(f"{unit.key}: {v.stored} has {bad} NaN of {a.size} (masked or land cell at the nearest point)")
        if a.min() < v.lo or a.max() > v.hi:
            raise DataValidationError(f"{unit.key}: {v.stored} range {a.min():g}..{a.max():g} {v.units} outside plausible {v.lo:g}..{v.hi:g} "
                                      "(fill value, wrong variable or wrong units?)")


def write_unit_file(path: Path, unit: Unit, mapped: pd.DataFrame, point, lon_data: float, lat_data: float, urls) -> dict:
    """Atomic write: dims (time, lat, lon) with lat/lon of length 1 = the grid cell, which is what years._nearest expects."""
    import xarray as xr
    prod = product(unit.product)
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {v.stored: (("time", "lat", "lon"), mapped[v.stored].to_numpy("float32")[:, None, None],
                       {"units": v.units, "source_column": v.lib}) for v in prod.vars}
    ds = xr.Dataset(data, coords={"time": mapped.index.to_numpy("datetime64[ns]"), "lat": [lat_data], "lon": [lon_data]})
    ds.attrs.update({
        "title": f"{unit.product} point series {unit.ym}", "backend": BACKEND, "product": unit.product,
        "metocean_api_product": prod.api, "metocean_api_version": library_version() or "unknown",
        "direction_convention": prod.convention, "licence": LICENCE, "credit": CREDIT,
        "requested_lon": float(point[0]), "requested_lat": float(point[1]),
        "source_urls": " ".join(urls), "fetched_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "note": "values rounded to 0.01 by metocean-api",
    })
    enc = {k: {"zlib": True, "complevel": 4, "dtype": "float32", "_FillValue": np.float32(np.nan)} for k in data}
    try:
        ds.to_netcdf(tmp, engine="netcdf4", encoding=enc)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()
    dist = haversine_km(point[0], point[1], lon_data, lat_data)
    return {"file": path.name, "bytes": path.stat().st_size, "rows": int(len(mapped)),
            "lon_data": round(lon_data, 5), "lat_data": round(lat_data, 5), "dist_km": round(dist, 3)}


def produce_unit(unit: Unit, point, out_dir: Path, workdir: Path, mirror=None, max_dist_km=DEFAULT_MAX_DIST_KM) -> dict:
    """Everything for one unit, in this process: fetch, map, validate, write. Returns the manifest fields."""
    t0 = time.time()
    ctx = url_mirror(mirror) if mirror else contextlib.nullcontext()
    with ctx:
        df, lon_d, lat_d, urls, _ = fetch_frame(unit, point, Path(workdir))
    dist = haversine_km(point[0], point[1], lon_d, lat_d)
    if dist > max_dist_km:
        raise DataValidationError(f"{unit.key}: nearest grid cell ({lon_d:.3f}, {lat_d:.3f}) is {dist:.1f} km from {tuple(point)} (> {max_dist_km} km)")
    mapped = map_columns(unit.product, df)
    validate_frame(unit, mapped)
    info = write_unit_file(Path(out_dir) / unit.filename, unit, mapped, point, lon_d, lat_d, urls)
    info["seconds"] = round(time.time() - t0, 1)
    return info


def check_file(path: Path, unit: Unit, point, max_dist_km=DEFAULT_MAX_DIST_KM) -> str | None:
    """None if `path` is a complete, valid file for exactly this unit and point; else the reason it is not."""
    import xarray as xr
    path = Path(path)
    if not path.exists():
        return "missing"
    prod = product(unit.product)
    try:
        with xr.open_dataset(path) as ds:
            if ds.attrs.get("backend") != BACKEND or ds.attrs.get("product") != unit.product:
                return f"not a {BACKEND} {unit.product} file"
            if (abs(float(ds.attrs.get("requested_lon", np.nan)) - point[0]) > 1e-9
                    or abs(float(ds.attrs.get("requested_lat", np.nan)) - point[1]) > 1e-9):
                return (f"requested point {ds.attrs.get('requested_lon')},{ds.attrs.get('requested_lat')} "
                        f"differs from {point[0]},{point[1]}")
            missing = [v.stored for v in prod.vars if v.stored not in ds.data_vars]
            if missing:
                return f"variables missing: {missing}"
            frame = pd.DataFrame({v.stored: np.asarray(ds[v.stored].squeeze(drop=True).values, float) for v in prod.vars},
                                 index=pd.DatetimeIndex(ds["time"].values))
        validate_frame(unit, frame)
    except MetoceanApiError as exc:
        return str(exc)
    except Exception as exc:  # noqa: BLE001 - truncated or corrupt file
        return f"unreadable: {type(exc).__name__}: {exc}"
    return None


# --------------------------------------------------------------------------------------------------------------------
# Isolation: one subprocess per unit, killed on timeout
# --------------------------------------------------------------------------------------------------------------------
def _dodsrc(directory: Path, timeout_s: int) -> Path:
    p = directory / ".dodsrc"
    p.write_text(f"HTTP.TIMEOUT={int(timeout_s)}\nHTTP.CONNECTTIMEOUT={min(60, int(timeout_s))}\n")
    return p


def worker_command(unit: Unit, point, out_dir: Path, workdir: Path, mirror=None, max_dist_km=DEFAULT_MAX_DIST_KM) -> list[str]:
    spec = {"product": unit.product, "year": unit.year, "month": unit.month, "point": list(point), "out": str(out_dir),
            "workdir": str(workdir), "mirror": str(mirror) if mirror else None, "max_dist_km": max_dist_km}
    return [sys.executable, "-m", "offsim.worlds.metocean_api", "_worker", json.dumps(spec)]


def run_isolated(cmd: list[str], timeout_s: float, cwd: Path, env_extra: dict | None = None) -> dict:
    """Run a worker command with a hard wall limit. Returns the worker's result dict; raises UnitTimeout, the typed
    MetoceanApiError the worker reported, or UnitFailed."""
    env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONPATH=os.pathsep.join([str(ROOT), os.environ.get("PYTHONPATH", "")]).rstrip(os.pathsep))
    env.update(env_extra or {})
    cwd = Path(cwd)
    cwd.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        out, err = proc.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate()
        raise UnitTimeout(f"no result within {timeout_s:.0f} s; worker killed")
    result = None
    for line in reversed(out.splitlines()):
        k = line.rfind("RESULT {")          # the library's progress spinner writes backspaces into the same stdout line
        if k >= 0:
            result = json.loads(line[k + 7:])
            break
    if proc.returncode == 0 and result is not None:
        return result
    if result is not None and "error" in result:
        cls = {"VariableMappingError": VariableMappingError, "DataValidationError": DataValidationError,
               "PointMismatch": PointMismatch}.get(result["error"], UnitFailed)
        raise cls(result.get("message", result["error"]))
    tail = (err.strip().splitlines() or out.strip().splitlines() or ["no output"])[-1][:300]
    raise UnitFailed(f"worker exited {proc.returncode}: {tail}")


def _worker_main(spec_json: str) -> int:
    spec = json.loads(spec_json)
    unit = Unit(spec["product"], int(spec["year"]), int(spec["month"]))
    workdir = Path(spec["workdir"])
    try:
        info = produce_unit(unit, tuple(spec["point"]), Path(spec["out"]), workdir, mirror=spec.get("mirror"),
                            max_dist_km=float(spec.get("max_dist_km", DEFAULT_MAX_DIST_KM)))
        print("\nRESULT " + json.dumps(info), flush=True)
        return 0
    except MetoceanApiError as exc:
        print("\nRESULT " + json.dumps({"error": type(exc).__name__, "message": str(exc)}), flush=True)
        return 3
    except Exception as exc:  # noqa: BLE001
        print("\nRESULT " + json.dumps({"error": type(exc).__name__, "message": f"{type(exc).__name__}: {exc}"}), flush=True)
        return 4


# --------------------------------------------------------------------------------------------------------------------
# Manifest
# --------------------------------------------------------------------------------------------------------------------
def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def write_json_atomic(path: Path, obj) -> None:
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, sort_keys=False))
    os.replace(tmp, path)


def new_manifest(out_dir: Path, point, years, season, products) -> dict:
    return {"backend": BACKEND, "licence": LICENCE, "credit": CREDIT,
            "library": {"metocean-api": library_version(), "licence": "LGPL-2.1-or-later"},
            "point": {"lon": point[0], "lat": point[1]}, "years": list(years), "season": season,
            "products": list(products), "created_utc": _now(), "updated_utc": _now(),
            "live_checked": False, "units": {}, "errors": [], "summary": {}}


def load_manifest(out_dir: Path, point) -> dict | None:
    p = Path(out_dir) / MANIFEST
    if not p.exists():
        return None
    man = json.loads(p.read_text())
    if man.get("backend") != BACKEND:
        raise PointMismatch(f"{p} was not written by the {BACKEND} backend; use another --out")
    mp = man.get("point", {})
    if abs(mp.get("lon", 1e9) - point[0]) > 1e-9 or abs(mp.get("lat", 1e9) - point[1]) > 1e-9:
        raise PointMismatch(f"{out_dir} holds files for point {mp.get('lon')},{mp.get('lat')}, not {point[0]},{point[1]}. "
                            "Mixing points in one directory would silently blend two sites in load_years: use another --out.")
    return man


def summarise(man: dict, expected: list[Unit]) -> dict:
    st = [man["units"].get(u.key, {}).get("status", "pending") for u in expected]
    return {"expected": len(expected), "ok": st.count("ok"), "failed": st.count("failed"), "pending": st.count("pending"),
            "complete": st.count("ok") == len(expected)}


# --------------------------------------------------------------------------------------------------------------------
# The fetch
# --------------------------------------------------------------------------------------------------------------------
def fetch_series(out_dir, point, years, season="DJF", products=("nora3_wave", "nora3_wind"), *,
                 unit_timeout_s: float = DEFAULT_UNIT_TIMEOUT_S, retries: int = 2, backoff_s=(15.0, 60.0),
                 max_runtime_s: float | None = None, max_consecutive_failures: int = 6, isolation: str = "subprocess",
                 mirror=None, max_dist_km: float = DEFAULT_MAX_DIST_KM, runner=None, sleep=time.sleep,
                 log=lambda s: print(s, flush=True)) -> dict:
    """Fetch every month the (years, season) request needs, skipping what is already valid on disk.

    Returns the manifest dict (also written to <out_dir>/manifest.json after every unit). `manifest["summary"]["complete"]`
    is True only when every expected unit is on disk and valid. `manifest["stopped"]` is set when the run ended early
    ('deadline' or 'consecutive_failures'): run the same command again to continue.

    isolation='subprocess' (default) runs each unit in a child killed after `unit_timeout_s`; 'inprocess' calls the
    library directly (tests, debugging: no hard timeout). `runner(unit, attempt_timeout_s) -> info` replaces both
    (tests). `mirror` serves URLs from a local directory (offline)."""
    out_dir = Path(out_dir).resolve()        # workers run in another cwd: every path handed to them is absolute
    out_dir.mkdir(parents=True, exist_ok=True)
    mirror = str(Path(mirror).resolve()) if mirror else None
    point = (float(point[0]), float(point[1]))
    units = month_units(years, season, products)
    t_start = time.time()
    stamp = lambda: time.strftime("%H:%M:%S")

    man = load_manifest(out_dir, point) or new_manifest(out_dir, point, years, season, products)
    man.update({"years": list(years), "season": season, "products": list(products), "stopped": None, "updated_utc": _now()})
    for stale in out_dir.glob("*.tmp"):      # a killed run can leave the half-written file; it was never renamed into place
        stale.unlink()

    # 1. what is already there?
    present, to_fetch = [], []
    for u in units:
        reason = check_file(out_dir / u.filename, u, point, max_dist_km)
        if reason is None:
            present.append(u)
        else:
            if reason != "missing":
                bad = out_dir / (u.filename + ".bad")
                os.replace(out_dir / u.filename, bad)
                log(f"[{stamp()}] {u.key}: existing file rejected ({reason}); moved to {bad.name}")
            to_fetch.append(u)
    for u in present:
        e = man["units"].get(u.key, {})
        if e.get("status") != "ok":
            man["units"][u.key] = {**e, "status": "ok", "file": u.filename, "note": "found valid on disk"}
    for u in to_fetch:
        if man["units"].get(u.key, {}).get("status") == "ok":
            man["units"][u.key]["status"] = "failed"     # manifest said ok, disk says no
            man["units"][u.key]["error"] = "file missing or invalid on resume"
    total = len(units)
    if present:
        log(f"[{stamp()}] RESUMING: {len(present)}/{total} units already on disk and valid (skipped); {len(to_fetch)} to fetch "
            f"[{BACKEND}, point {point[0]},{point[1]}, {season or 'all-year'} {years[0]}..{years[-1]}]")
    else:
        log(f"[{stamp()}] STARTING: 0/{total} units on disk; {len(to_fetch)} to fetch "
            f"[{BACKEND}, point {point[0]},{point[1]}, {season or 'all-year'} {years[0]}..{years[-1]}]")
    man["summary"] = summarise(man, units)
    write_json_atomic(out_dir / MANIFEST, man)

    # 2. fetch what is missing
    work_root = out_dir / ".work"
    consecutive = 0
    done_before = len(present)
    for i, u in enumerate(to_fetch, start=1):
        elapsed = time.time() - t_start
        if max_runtime_s is not None and elapsed >= max_runtime_s:
            man["stopped"] = "deadline"
            log(f"[{stamp()}] STOP: runtime limit {max_runtime_s:.0f} s reached with {len(to_fetch) - i + 1} units left. Run the same command again to continue.")
            break
        if consecutive >= max_consecutive_failures:
            man["stopped"] = "consecutive_failures"
            log(f"[{stamp()}] STOP: {consecutive} units failed in a row; the server is probably unreachable. "
                f"See {MANIFEST} errors. Run the same command again to continue.")
            break
        budget = unit_timeout_s if max_runtime_s is None else max(30.0, min(unit_timeout_s, max_runtime_s - elapsed))
        entry = man["units"].get(u.key, {})
        attempts = int(entry.get("attempts", 0))
        err = None
        info = None
        for attempt in range(1, retries + 2):
            attempts += 1
            workdir = work_root / u.key.replace(":", "_")
            try:
                if runner is not None:
                    info = runner(u, budget)
                elif isolation == "inprocess":
                    info = produce_unit(u, point, out_dir, workdir, mirror=mirror, max_dist_km=max_dist_km)
                else:
                    workdir.mkdir(parents=True, exist_ok=True)
                    rc = _dodsrc(workdir, int(budget))
                    info = run_isolated(worker_command(u, point, out_dir, workdir, mirror, max_dist_km), budget, workdir,
                                        {"DODSRC": str(rc)})
                reason = check_file(out_dir / u.filename, u, point, max_dist_km)
                if reason is not None:
                    raise DataValidationError(f"{u.key}: file written but fails its own check: {reason}")
                err = None
                break
            except MetoceanApiError as exc:
                err = exc
            except Exception as exc:  # noqa: BLE001
                err = UnitFailed(f"{type(exc).__name__}: {exc}")
            if err.permanent or attempt > retries:
                break
            wait = backoff_s[min(attempt - 1, len(backoff_s) - 1)] if backoff_s else 0.0
            log(f"[{stamp()}] [{done_before + i}/{total}] {u.key}: attempt {attempt} failed ({type(err).__name__}: {err}); retry in {wait:.0f} s")
            sleep(wait)
        shutil_rmtree(work_root / u.key.replace(":", "_"))
        if err is None:
            consecutive = 0
            man["units"][u.key] = {"status": "ok", "attempts": attempts, "fetched_utc": _now(), **info}
            log(f"[{stamp()}] [{done_before + i}/{total}] {u.key}: ok ({info.get('seconds', '?')} s, {info.get('rows')} h, cell {info.get('lon_data')},{info.get('lat_data')})")
        else:
            consecutive += 1
            man["units"][u.key] = {"status": "failed", "attempts": attempts, "error": f"{type(err).__name__}: {err}",
                                   "permanent": bool(err.permanent), "failed_utc": _now()}
            log(f"[{stamp()}] [{done_before + i}/{total}] {u.key}: FAILED after {attempts} attempt(s): {type(err).__name__}: {err}")
        man["summary"] = summarise(man, units)
        man["updated_utc"] = _now()
        man["errors"] = [{"stage": f"metocean-api {k}", "error": v["error"], "seconds": 0}
                         for k, v in man["units"].items() if v.get("status") == "failed"]
        write_json_atomic(out_dir / MANIFEST, man)

    shutil_rmtree(work_root, only_if_empty=True)
    man["summary"] = summarise(man, units)
    man["errors"] = [{"stage": f"metocean-api {k}", "error": v["error"], "seconds": 0}
                     for k, v in man["units"].items() if v.get("status") == "failed"]
    man["updated_utc"] = _now()
    write_json_atomic(out_dir / MANIFEST, man)
    s = man["summary"]
    log(f"[{stamp()}] {'COMPLETE' if s['complete'] else 'INCOMPLETE'}: {s['ok']}/{s['expected']} ok, {s['failed']} failed, {s['pending']} pending"
        + ("" if s["complete"] else "; run the same command again to resume (valid files are not fetched twice)"))
    return man


def shutil_rmtree(path: Path, only_if_empty: bool = False) -> None:
    import shutil
    path = Path(path)
    if not path.exists():
        return
    if only_if_empty:
        with contextlib.suppress(OSError):
            path.rmdir()
        return
    shutil.rmtree(path, ignore_errors=True)


def manifest_source(man: dict, rel_dir: str = "metocean_point/") -> dict:
    """The entry fetch_world adds to its own manifest `sources`."""
    s = man.get("summary", {})
    return {"name": "MET Norway NORA3 wave + wind point series via metocean-api (THREDDS OPeNDAP)", "licence": LICENCE,
            "credit": CREDIT, "backend": BACKEND, "dir": rel_dir, "point": man.get("point"), "season": man.get("season"),
            "years": [man["years"][0], man["years"][-1]] if man.get("years") else None, "units": s,
            "stopped": man.get("stopped"), "live_checked": man.get("live_checked", False)}


def status(out_dir, point=None, years=None, season="DJF", products=("nora3_wave", "nora3_wind")) -> dict:
    """What is on disk, from the manifest (and, when the request is given, from the files themselves)."""
    out_dir = Path(out_dir)
    p = out_dir / MANIFEST
    man = json.loads(p.read_text()) if p.exists() else None
    res = {"dir": str(out_dir), "manifest": man["summary"] if man else None,
           "files": len(list(out_dir.glob("pt_*.nc"))), "bad": len(list(out_dir.glob("*.bad")))}
    if man and point is None:
        point = (man["point"]["lon"], man["point"]["lat"])
        years, season, products = man["years"], man["season"], man["products"]
    if point is not None and years:
        units = month_units(years, season, products)
        ok = [u.key for u in units if check_file(out_dir / u.filename, u, point) is None]
        res["disk"] = {"expected": len(units), "valid": len(ok), "missing": [u.key for u in units if u.key not in ok][:10]}
    return res


# --------------------------------------------------------------------------------------------------------------------
# metocean-stats: separate process only (it requires lmoments3, GPL-3.0)
# --------------------------------------------------------------------------------------------------------------------
def read_series(out_dir, product_key: str, years=None, season=None) -> pd.DataFrame:
    """Concatenate the monthly point files of one product into one frame indexed by time (stored names)."""
    import xarray as xr
    prod = product(product_key)
    frames = []
    for f in sorted(Path(out_dir).glob(f"pt_{product_key}_*.nc")):
        with xr.open_dataset(f) as ds:
            frames.append(pd.DataFrame({v.stored: np.asarray(ds[v.stored].squeeze(drop=True).values, float) for v in prod.vars},
                                       index=pd.DatetimeIndex(ds["time"].values)))
    if not frames:
        raise FileNotFoundError(f"no pt_{product_key}_*.nc in {out_dir}")
    return pd.concat(frames).sort_index()


def run_stats(out_dir, years, season="DJF", thresholds=(2.5, 3.5, 4.5), op_hours=(6.0, 12.0), timeout_s=600) -> dict:
    """Hs weather-window statistics per winter from metocean-stats, computed in a CHILD process. This process never
    imports metocean_stats or lmoments3 (GPL-3.0). Cross-check for our own windows code, not an input to a run."""
    out_dir = Path(out_dir)
    hs = read_series(out_dir, "nora3_wave")["hs"]
    months = season_months(season)
    winters = {}
    for y in years:
        t0 = pd.Timestamp(int(y), months[0], 1)
        t1 = t0 + pd.DateOffset(months=len(months))
        w = hs[(hs.index >= t0) & (hs.index < t1)]
        if len(w):
            winters[str(int(y))] = {"time": [t.isoformat() for t in w.index], "hs": [float(x) for x in w.to_numpy()]}
    if not winters:
        raise DataValidationError(f"no hs data for years {years} in {out_dir}")
    job = out_dir / ".stats_job.json"
    res = out_dir / "stats_metocean_stats.json"
    write_json_atomic(job, {"winters": winters, "thresholds": list(thresholds), "op_hours": list(op_hours)})
    cmd = [sys.executable, "-W", "ignore", "-m", "offsim.worlds.metocean_api", "_stats_worker", str(job), str(res)]
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(ROOT), os.environ.get("PYTHONPATH", "")]).rstrip(os.pathsep))
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s, env=env, cwd=out_dir)
    finally:
        job.unlink(missing_ok=True)
    if p.returncode != 0:
        raise UnitFailed(f"metocean-stats worker exited {p.returncode}: {(p.stderr.strip().splitlines() or ['no output'])[-1][:300]}")
    return json.loads(res.read_text())


def _stats_worker_main(job_path: str, out_path: str) -> int:
    """Child process: the only place metocean_stats is imported."""
    from metocean_stats.stats import general     # GPL-3.0 dependency (lmoments3) is loaded here, in this child only
    job = json.loads(Path(job_path).read_text())
    out = {"tool": "metocean-stats", "function": "metocean_stats.stats.general.weather_window_length", "unit": "days (waiting + operation, library definition)",
           "thresholds_hs_m": job["thresholds"], "op_hours": job["op_hours"], "winters": {}, "errors": []}
    for y, w in job["winters"].items():
        s = pd.Series(w["hs"], index=pd.DatetimeIndex(w["time"]))
        out["winters"][y] = {}
        for thr in job["thresholds"]:
            for op in job["op_hours"]:
                try:
                    mean, p10, p50, p90 = general.weather_window_length(s, float(thr), float(op), 1.0)
                    out["winters"][y][f"hs<{thr}_op{op:g}h"] = {"mean": float(mean), "p10": float(p10), "p50": float(p50), "p90": float(p90)}
                except Exception as exc:  # noqa: BLE001 - e.g. no window at all in that winter
                    out["errors"].append({"winter": y, "hs_limit": thr, "op_hours": op, "error": f"{type(exc).__name__}: {exc}"})
    write_json_atomic(Path(out_path), out)
    return 0


# --------------------------------------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------------------------------------
def default_out(world: str) -> Path:
    return ROOT / "data" / "worlds" / world / "metocean_point"


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "_worker":
        return _worker_main(argv[1])
    if argv and argv[0] == "_stats_worker":
        return _stats_worker_main(argv[1], argv[2])
    ap = argparse.ArgumentParser(prog="python -m offsim.worlds.metocean_api", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p, need_request=True):
        p.add_argument("--world", help="world name; output defaults to data/worlds/<world>/metocean_point")
        p.add_argument("--out", help="output directory (overrides --world)")
        p.add_argument("--point", required=need_request, help="lon,lat WGS84, e.g. 3.0,60.6")
        p.add_argument("--years", required=need_request, help="2000-2023 or 2001,2005; year Y of DJF = Dec Y .. Feb Y+1")
        p.add_argument("--season", default="DJF", help="month initials (default DJF); 'all' for whole calendar years")
        p.add_argument("--products", default=",".join(PRODUCTS), help="comma list of " + ",".join(PRODUCTS))

    f = sub.add_parser("fetch", help="fetch (or resume) the point series")
    common(f)
    f.add_argument("--unit-timeout", type=float, default=DEFAULT_UNIT_TIMEOUT_S, help="hard wall limit per monthly request, seconds (default 600)")
    f.add_argument("--retries", type=int, default=2, help="extra attempts per unit for transient failures (default 2)")
    f.add_argument("--max-runtime-min", type=float, default=None, help="stop cleanly after this many minutes (resume by re-running)")
    f.add_argument("--max-consecutive-failures", type=int, default=6)
    f.add_argument("--max-dist-km", type=float, default=DEFAULT_MAX_DIST_KM)
    f.add_argument("--mirror", help="serve the monthly files from this local directory instead of thredds.met.no (offline)")
    f.add_argument("--inprocess", action="store_true", help="no subprocess isolation (no hard timeout); debugging only")
    s = sub.add_parser("status", help="what is on disk and valid")
    common(s, need_request=False)
    t = sub.add_parser("stats", help="Hs weather-window statistics via metocean-stats, in a child process")
    common(t)
    t.add_argument("--thresholds", default="2.5,3.5,4.5", help="Hs limits in m (default: the PSV bands)")
    t.add_argument("--op-hours", default="6,12")
    a = ap.parse_args(argv)

    out = Path(a.out) if a.out else (default_out(a.world) if a.world else None)
    if out is None:
        ap.error("give --out or --world")
    season = None if (a.season or "").lower() == "all" else a.season
    products = tuple(x for x in a.products.split(",") if x)
    if a.cmd == "status":
        pt = parse_point(a.point) if a.point else None
        print(json.dumps(status(out, pt, parse_years(a.years) if a.years else None, season, products), indent=1))
        return 0
    years = parse_years(a.years)
    if a.cmd == "stats":
        print(json.dumps(run_stats(out, years, season, tuple(float(x) for x in a.thresholds.split(",")),
                                   tuple(float(x) for x in a.op_hours.split(","))), indent=1))
        return 0
    man = fetch_series(out, parse_point(a.point), years, season, products, unit_timeout_s=a.unit_timeout, retries=a.retries,
                       max_runtime_s=a.max_runtime_min * 60 if a.max_runtime_min else None,
                       max_consecutive_failures=a.max_consecutive_failures, isolation="inprocess" if a.inprocess else "subprocess",
                       mirror=a.mirror, max_dist_km=a.max_dist_km)
    return 0 if man["summary"]["complete"] else 2


if __name__ == "__main__":
    sys.exit(main())
