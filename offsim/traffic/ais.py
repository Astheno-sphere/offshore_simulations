"""AIS -> port calls and calibration statistics -> validation of simulated trajectories.

Input: Kystverket Historic AIS (HAIS, https://hais.kystverket.no/) as GeoParquet or CSV, or any table with the
columns mmsi, timestamp, lon, lat, sog (knots), cog (deg), ship_type. Column names are normalised defensively
(`normalise_columns`), so `MMSI`, `msgtime`, `longitude`, `speed_over_ground`, `shiptype` ... are all accepted.

Pipeline (all functions are pure DataFrame in / DataFrame out; movingpandas is imported lazily):

    df     = load_ais(path)                                   # normalised, UTC timestamps, sorted, deduplicated
    df     = filter_ais(df, bbox=(w, s, e, n), ship_types=PSV_TYPES)
    tracks = build_tracks(df, gap=timedelta(hours=2))         # movingpandas TrajectoryCollection, split on gaps
    calls  = port_calls(tracks, places)                       # mmsi, place, arrive, depart, duration_s
    calib  = calibration(calls, tracks)                       # quantiles a scenario can cite
    table  = compare_to_sim(sim_values, calib)                # sim vs AIS quantiles, pass/fail

`places` is a DataFrame or list of dicts (name, lon, lat, radius_m) or a dict {name: (lon, lat[, radius_m])}.

Provenance: calibration() returns a `src` string such as "AIS HAIS <area> <dates>, offsim.traffic"; a scenario
parameter filled from `calib` cites it as its `src:` (CLAUDE.md: every parameter needs a source).

Gate 4b (spec, NOT yet wired into the pipeline): after gates 0-4 (offsim.pipeline), `compare_to_sim` checks the
simulated port-call durations and sailing speeds against the AIS calibration. A scenario that declares an
`ais_calibration:` file would fail the run when `compare_to_sim(...)["pass"]` has any False. Until wired, call it
by hand and record the outcome in docs/TESTLOG.md.

Units: durations in seconds, speeds in knots (AIS native), distances in metres. Timestamps are tz-aware UTC.
"""
from __future__ import annotations

import re
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

KN_TO_MPS = 1852.0 / 3600.0
QUANTILES = (0.1, 0.5, 0.9)

# AIS ship-and-cargo type codes (ITU-R M.1371): 31/32 tug, 52 tug, 50-59 special craft, 70-79 cargo. Offshore supply
# vessels (PSV/AHTS) report as 70-79 (cargo) or 30-39/50-59 (many report 'other'/special); there is no dedicated PSV
# code, so the default filter is a superset and callers should narrow by MMSI list when they know the fleet.
PSV_TYPES = tuple(range(70, 80)) + (31, 32, 52, 53, 57, 58, 59)
FERRY_TYPES = tuple(range(60, 70))

_ALIASES = {
    "mmsi": ("mmsi", "userid", "user_id", "mmsinumber"),
    "timestamp": ("timestamp", "time", "msgtime", "datetime", "date_time_utc", "date_time", "basedatetime", "t"),
    "lon": ("lon", "lng", "long", "longitude", "x"),
    "lat": ("lat", "latitude", "y"),
    "sog": ("sog", "speed", "speed_over_ground", "speedoverground", "speed_kn", "speed_knots"),
    "cog": ("cog", "course", "course_over_ground", "courseoverground"),
    "ship_type": ("ship_type", "shiptype", "ship_and_cargo_type", "shipandcargotype", "vessel_type", "type"),
}


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9_]", "", str(name).strip().lower().replace(" ", "_"))


def normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename whatever the source calls its columns to mmsi, timestamp, lon, lat, sog, cog, ship_type.
    Missing optional columns (sog, cog, ship_type) are created as NaN; missing mmsi/timestamp/lon/lat raise ValueError.
    Geometry columns (GeoParquet) supply lon/lat when those are absent."""
    lookup = {}
    for canon, names in _ALIASES.items():
        for n in names:
            lookup.setdefault(n, canon)
    rename, seen = {}, set()
    for c in df.columns:
        canon = lookup.get(_key(c))
        if canon and canon not in seen and c != "geometry":
            rename[c] = canon
            seen.add(canon)
    out = df.rename(columns=rename)
    geom = getattr(out, "geometry", None) if "geometry" in out.columns else None
    if ("lon" not in out.columns or "lat" not in out.columns) and geom is not None:
        out = pd.DataFrame(out.drop(columns="geometry")).assign(lon=geom.x.to_numpy(), lat=geom.y.to_numpy())
    missing = [c for c in ("mmsi", "timestamp", "lon", "lat") if c not in out.columns]
    if missing:
        raise ValueError(f"AIS table lacks {missing}; columns are {list(df.columns)}")
    for c in ("sog", "cog", "ship_type"):
        if c not in out.columns:
            out[c] = np.nan
    return pd.DataFrame(out)


def load_ais(path_or_df) -> pd.DataFrame:
    """HAIS GeoParquet / Parquet / CSV (or an in-memory DataFrame) -> normalised DataFrame with columns
    mmsi (int64), timestamp (UTC datetime64), lon, lat, sog, cog, ship_type, sorted by (mmsi, timestamp), exact
    duplicates and impossible positions (|lat|>90, |lon|>180, the AIS 'not available' 91/181) removed.
    Speeds of 102.3 kn (AIS 'not available' 1023) become NaN."""
    if isinstance(path_or_df, pd.DataFrame):
        raw = path_or_df
    else:
        p = Path(path_or_df)
        suf = p.suffix.lower()
        if suf in (".parquet", ".geoparquet", ".pq"):
            try:
                import geopandas as gpd
                raw = gpd.read_parquet(p)
            except Exception:  # plain parquet without geo metadata
                raw = pd.read_parquet(p)
        elif suf in (".csv", ".txt", ".gz"):
            raw = pd.read_csv(p, sep=None, engine="python")
        elif p.is_file() and p.open("rb").read(4) == b"PAR1":      # extension-less download link from HAIS
            try:
                import geopandas as gpd
                raw = gpd.read_parquet(p)
            except Exception:
                raw = pd.read_parquet(p)
        else:                                                      # unknown suffix and not parquet: try delimited text
            try:
                raw = pd.read_csv(p, sep=None, engine="python")
            except Exception as exc:
                raise ValueError(f"unsupported AIS file {p.name!r} (want GeoParquet/Parquet/CSV): {exc}") from exc
    df = normalise_columns(raw)[["mmsi", "timestamp", "lon", "lat", "sog", "cog", "ship_type"]].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    for c in ("lon", "lat", "sog", "cog", "ship_type"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["mmsi"] = pd.to_numeric(df["mmsi"], errors="coerce")
    df = df.dropna(subset=["mmsi", "timestamp", "lon", "lat"])
    df["mmsi"] = df["mmsi"].astype("int64")
    df = df[(df["lat"].abs() <= 90) & (df["lon"].abs() <= 180) & (df["lat"] != 91) & (df["lon"] != 181)]
    df.loc[df["sog"] >= 102.3, "sog"] = np.nan
    df = df.drop_duplicates(subset=["mmsi", "timestamp"]).sort_values(["mmsi", "timestamp"]).reset_index(drop=True)
    return df


def filter_ais(df: pd.DataFrame, bbox=None, ship_types=None, mmsi=None, start=None, end=None) -> pd.DataFrame:
    """Keep rows inside bbox (west, south, east, north), of the given ship_type codes / MMSIs, and in [start, end).
    ship_types=None keeps all (including rows with unknown type)."""
    m = pd.Series(True, index=df.index)
    if bbox is not None:
        w, s, e, n = bbox
        m &= df["lon"].between(w, e) & df["lat"].between(s, n)
    if ship_types is not None:
        m &= df["ship_type"].isin(list(ship_types))
    if mmsi is not None:
        m &= df["mmsi"].isin(list(mmsi))
    if start is not None:
        m &= df["timestamp"] >= pd.Timestamp(start, tz="UTC") if pd.Timestamp(start).tzinfo is None else df["timestamp"] >= pd.Timestamp(start)
    if end is not None:
        m &= df["timestamp"] < pd.Timestamp(end, tz="UTC") if pd.Timestamp(end).tzinfo is None else df["timestamp"] < pd.Timestamp(end)
    return df[m].reset_index(drop=True)


def build_tracks(df: pd.DataFrame, gap: timedelta = timedelta(hours=2), min_points: int = 2):
    """movingpandas TrajectoryCollection, one trajectory per MMSI, split wherever consecutive fixes are more than
    `gap` apart (ObservationGapSplitter). Trajectories with fewer than `min_points` fixes are dropped.
    Trajectory ids are "<mmsi>_<n>" (the `mmsi` column of traj.df is rewritten by the splitter: use the id)."""
    import geopandas as gpd
    import movingpandas as mpd

    if df.empty:
        raise ValueError("no AIS rows to build tracks from")
    g = gpd.GeoDataFrame(df.copy(), geometry=gpd.points_from_xy(df["lon"], df["lat"]), crs=4326)
    g["timestamp_naive"] = g["timestamp"].dt.tz_convert("UTC").dt.tz_localize(None)
    g = g.set_index("timestamp_naive", drop=False)
    coll = mpd.TrajectoryCollection(g, "mmsi", t="timestamp_naive", x="lon", y="lat", crs=4326)
    coll = mpd.ObservationGapSplitter(coll).split(gap=gap, min_length=0)
    keep = [t for t in coll.trajectories if len(t.df) >= min_points]
    return mpd.TrajectoryCollection(keep, traj_id_col="mmsi", t="timestamp_naive") if keep else coll.__class__([])


def _places_frame(places) -> pd.DataFrame:
    if isinstance(places, pd.DataFrame):
        df = places.copy()
    elif isinstance(places, (list, tuple)):                      # [{name, lon, lat, radius_m}] as in the world YAML
        df = pd.DataFrame(list(places))
    else:
        rows = []
        for name, v in dict(places).items():
            rows.append({"name": name, "lon": v[0], "lat": v[1], "radius_m": v[2] if len(v) > 2 else np.nan})
        df = pd.DataFrame(rows)
    if "radius_m" not in df.columns:
        df["radius_m"] = np.nan
    df["radius_m"] = df["radius_m"].fillna(1000.0)
    return df[["name", "lon", "lat", "radius_m"]]


def detect_stops(traj, min_duration: timedelta = timedelta(minutes=20), max_diameter_m: float = 250.0) -> pd.DataFrame:
    """movingpandas TrajectoryStopDetector on one trajectory -> DataFrame(start, end, lon, lat, duration_s) with
    tz-aware UTC start/end and the mean position of the fixes inside the stop."""
    import movingpandas as mpd

    ranges = mpd.TrajectoryStopDetector(traj).get_stop_time_ranges(min_duration=min_duration, max_diameter=max_diameter_m)
    rows = []
    for r in ranges:
        t0, t1 = (r.t_0, r.t_n) if hasattr(r, "t_0") else tuple(r)     # movingpandas >= 0.2x returns TRangeWithTrajId
        seg = traj.df.loc[(traj.df.index >= t0) & (traj.df.index <= t1)]
        rows.append({"start": pd.Timestamp(t0).tz_localize("UTC") if pd.Timestamp(t0).tzinfo is None else pd.Timestamp(t0),
                     "end": pd.Timestamp(t1).tz_localize("UTC") if pd.Timestamp(t1).tzinfo is None else pd.Timestamp(t1),
                     "lon": float(seg["lon"].mean()), "lat": float(seg["lat"].mean()),
                     "duration_s": float((pd.Timestamp(t1) - pd.Timestamp(t0)).total_seconds())})
    return pd.DataFrame(rows, columns=["start", "end", "lon", "lat", "duration_s"])


def port_calls(tracks, places, min_duration: timedelta = timedelta(minutes=20), max_diameter_m: float = 250.0,
               merge_gap: timedelta = timedelta(minutes=30)) -> pd.DataFrame:
    """Stops matched to named ports/installations within each place's radius_m (nearest place wins).
    Returns DataFrame(mmsi, place, arrive, depart, duration_s). Stops at the same place by the same vessel
    separated by less than `merge_gap` (jitter beyond max_diameter, or a brief AIS gap) are merged into one call.
    Stops matching no place are dropped (anchorage / drifting)."""
    from offsim.contract import haversine_m

    pl = _places_frame(places)
    rows = []
    for traj in tracks.trajectories:
        mmsi = int(str(traj.id).split("_")[0])      # splitters rewrite the id column as "<mmsi>_<n>"
        for _, s in detect_stops(traj, min_duration, max_diameter_m).iterrows():
            d = haversine_m(s["lon"], s["lat"], pl["lon"].to_numpy(), pl["lat"].to_numpy())
            ok = d <= pl["radius_m"].to_numpy()
            if ok.any():
                i = int(np.where(ok, d, np.inf).argmin())
                rows.append({"mmsi": mmsi, "place": pl["name"].iloc[i], "arrive": s["start"], "depart": s["end"]})
    cols = ["mmsi", "place", "arrive", "depart", "duration_s"]
    if not rows:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(rows).sort_values(["mmsi", "place", "arrive"]).reset_index(drop=True)
    merged = []
    for _, r in df.iterrows():
        last = merged[-1] if merged else None
        if last and last["mmsi"] == r["mmsi"] and last["place"] == r["place"] and r["arrive"] - last["depart"] < merge_gap:
            last["depart"] = max(last["depart"], r["depart"])
        else:
            merged.append(r.to_dict())
    out = pd.DataFrame(merged)
    out["duration_s"] = (out["depart"] - out["arrive"]).dt.total_seconds()
    return out[cols].sort_values(["arrive", "mmsi"]).reset_index(drop=True)


def _q(values, qs=QUANTILES) -> dict:
    v = np.asarray(list(values), dtype=float)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return {}
    return {f"p{int(round(q * 100))}": float(np.quantile(v, q)) for q in qs} | {"n": int(v.size)}


def moving_speeds_kn(tracks, min_speed_kn: float = 1.0) -> np.ndarray:
    """Sailing speeds (knots) of moving segments only. Uses reported `sog` where present, else the speed between
    consecutive fixes; values below `min_speed_kn` (alongside, drifting) are excluded."""
    from offsim.contract import haversine_m

    out = []
    for traj in tracks.trajectories:
        d = traj.df
        t = d.index.to_series().astype("int64").to_numpy() / 1e9
        dt = np.diff(t)
        dist = haversine_m(d["lon"].to_numpy()[:-1], d["lat"].to_numpy()[:-1], d["lon"].to_numpy()[1:], d["lat"].to_numpy()[1:])
        with np.errstate(divide="ignore", invalid="ignore"):
            derived = np.where(dt > 0, dist / dt / KN_TO_MPS, np.nan)
        sog = d["sog"].to_numpy(dtype=float)[1:] if "sog" in d.columns else np.full(len(dt), np.nan)
        v = np.where(np.isfinite(sog), sog, derived)
        out.append(v[np.isfinite(v) & (v >= min_speed_kn)])
    return np.concatenate(out) if out else np.array([])


def calibration(port_calls: pd.DataFrame, tracks, area: str = "unspecified", dates: str = "unspecified",
                min_speed_kn: float = 1.0) -> dict:
    """Sourced statistics a scenario can cite.

    {"src": "AIS HAIS <area> <dates>, offsim.traffic",
     "port_call_s": {place: {"p10","p50","p90","n"}, ...},     # call duration quantiles per place (seconds)
     "port_call_all_s": {...},                                  # all places pooled
     "sailing_speed_kn": {"p10","p50","p90","n"},               # moving segments only (>= min_speed_kn)
     "vessels": int, "port_calls": int}
    Quantiles are p10/p50/p90 (QUANTILES). Places with a single call still get a row (n=1) so callers can see thin data."""
    per = {str(p): _q(g["duration_s"]) for p, g in port_calls.groupby("place")} if len(port_calls) else {}
    return {
        "src": f"AIS HAIS {area} {dates}, offsim.traffic",
        "port_call_s": per,
        "port_call_all_s": _q(port_calls["duration_s"]) if len(port_calls) else {},
        "sailing_speed_kn": _q(moving_speeds_kn(tracks, min_speed_kn)),
        "vessels": int(port_calls["mmsi"].nunique()) if len(port_calls) else 0,
        "port_calls": int(len(port_calls)),
    }


def compare_to_sim(traj, calib: dict, port_durations_s: dict | None = None, tol_rel: float = 0.25,
                   tol_abs_s: float = 600.0, tol_abs_kn: float = 1.0, min_n: int = 1) -> pd.DataFrame:
    """Gate 4b (spec; not yet wired into offsim.pipeline): simulated vs AIS quantiles.

    traj: contract trajectory DataFrame (agent_id, t, lon, lat, state, ...). Sailing speeds come from its moving
    legs (state in contract.MOVING; knots from haversine/dt). port_durations_s: optional {place: [seconds, ...]}
    of simulated call durations (the sim's load/unload/wait dwell at that place). Either input may be None.

    Returns DataFrame(metric, place, quantile, sim, ais, delta, tol, pass, n_ais). A row passes when
    |sim - ais| <= max(tol_rel * ais, tol_abs) where tol_abs is tol_abs_s for durations and tol_abs_kn for speeds.
    Metrics with fewer than min_n AIS observations are reported with pass = NaN (not judged). Callers gate on
    `table["pass"].fillna(True).all()`."""
    from offsim.contract import MOVING, haversine_m

    rows = []

    def add(metric, place, sim_q, ais_q, abs_tol):
        for k in ("p10", "p50", "p90"):
            if k not in sim_q or k not in ais_q:
                continue
            tol = max(tol_rel * abs(ais_q[k]), abs_tol)
            n = ais_q.get("n", 0)
            rows.append({"metric": metric, "place": place, "quantile": k, "sim": sim_q[k], "ais": ais_q[k],
                         "delta": sim_q[k] - ais_q[k], "tol": tol,
                         "pass": bool(abs(sim_q[k] - ais_q[k]) <= tol) if n >= min_n else np.nan, "n_ais": n})

    if traj is not None and len(traj):
        v = []
        for _, g in traj.sort_values(["agent_id", "t"]).groupby("agent_id", sort=False):
            lon, lat, t, st = g["lon"].to_numpy(), g["lat"].to_numpy(), g["t"].to_numpy(dtype=float), g["state"].to_numpy()
            dt = np.diff(t)
            ok = (dt > 0) & np.isin(st[1:], list(MOVING))
            d = haversine_m(lon[:-1], lat[:-1], lon[1:], lat[1:])
            v.append((d[ok] / dt[ok]) / KN_TO_MPS)
        sim_v = _q(np.concatenate(v) if v else [])
        add("sailing_speed_kn", "*", sim_v, calib.get("sailing_speed_kn", {}), tol_abs_kn)
    for place, durs in (port_durations_s or {}).items():
        ais_q = calib.get("port_call_s", {}).get(place) or calib.get("port_call_all_s", {})
        add("port_call_s", place, _q(durs), ais_q, tol_abs_s)
    return pd.DataFrame(rows, columns=["metric", "place", "quantile", "sim", "ais", "delta", "tol", "pass", "n_ais"])


def process_hais(path, out_dir, bbox=None, places=None, ship_types=None, area: str = "unspecified",
                 dates: str | None = None) -> dict:
    """fetch_world --ais: HAIS file -> <out_dir>/calibration.json (+ port_calls.csv when `places` is given).
    `dates` defaults to the first..last timestamp of the data. Returns the calibration dict (also written)."""
    import json

    df = filter_ais(load_ais(path), bbox=bbox, ship_types=ship_types)
    if df.empty:
        raise ValueError("no AIS rows left after filtering (check bbox / ship types)")
    dates = dates or f"{df['timestamp'].min():%Y-%m-%d}..{df['timestamp'].max():%Y-%m-%d}"
    tracks = build_tracks(df)
    calls = port_calls(tracks, places) if places else pd.DataFrame(columns=["mmsi", "place", "arrive", "depart", "duration_s"])
    calib = calibration(calls, tracks, area=area, dates=dates)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "calibration.json").write_text(json.dumps(calib, indent=1))
    if len(calls):
        calls.to_csv(out / "port_calls.csv", index=False)
    return calib
