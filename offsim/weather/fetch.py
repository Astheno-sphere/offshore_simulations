"""Metocean subsetting for the fetch-world workflow: defined interfaces (not built).
Runs on GitHub Actions (thredds.met.no is blocked in the Claude workspace). Library: xarray + netCDF4 over OPeNDAP;
metocean-api (MIT) is the reference for dataset paths and point series.
"""

DATASETS = {
    # name: (catalog id, variables we need, note)
    "nora3_wind": ("nora3-wind-wave", ["wind_speed", "wind_direction", "u10", "v10"], "3 km hourly; variable names: check"),
    "nora3_wave": ("nora3-wind-wave", ["hs", "tp", "thq"], "Hs, peak period, mean direction; grid spacing: check"),
    "norkyst_v3": ("norkyst-v3-800m", ["u", "v"], "curvilinear: regrid to EPSG:4326; take shallowest level"),
    "wam800": ("mywavewam800", ["hs", "tp", "thq"], "forecast archive only"),
}


def subset(dataset: str, bbox: tuple, start_utc: str, hours: int, out_path: str) -> dict:
    """Open OPeNDAP, select bbox/time server-side, regrid to a regular lon/lat grid, scale to int16, write NetCDF.
    Returns a manifest entry {dataset, url, licence 'CC BY 4.0 — MET Norway', vars, shape, fetched_utc}."""
    raise NotImplementedError


def point_series(dataset: str, lon: float, lat: float, start_utc: str, end_utc: str):
    """Hourly series at one site via metocean-api (operability statistics, weather windows)."""
    raise NotImplementedError
