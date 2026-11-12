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

Gate 4b (wired: offsim.pipeline runs it when the scenario sets `validate: {ais: true}`): after gates 0-4 (offsim.pipeline), `compare_to_sim` checks the
simulated port-call durations and sailing speeds against the AIS calibration. A scenario that declares an
`ais_calibration:` file would fail the run when `compare_to_sim(...)["pass"]` has any False. Until wired, call it
by hand and record the outcome in docs/TESTLOG.md.

Raw NMEA (pyais, MIT, imported): `decode_nmea` turns AIVDM/AIVDO sentences (types 1/2/3 position, 5 static, multipart
reassembled, checksums verified, every rejected line reported with a reason) into the same normalised table that
`load_ais` returns, and `to_trajectory` turns that into contract columns. `compare_decoded` is the whole of gate 4b
against a decoded track. See docs/ENGINES.md "AIS validation (gate 4b)".

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
    """Gate 4b (wired into offsim.pipeline, opt-in): simulated vs AIS quantiles.

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


# ---------------------------------------------------------------------------------------------------------------
# Raw NMEA -> the same tables (pyais). No network: the input is a file or an iterable of lines.
# ---------------------------------------------------------------------------------------------------------------
POSITION_TYPES = (1, 2, 3)
STATIC_TYPES = (5,)

# Gate 4b tolerances. ASSUMPTION (assumption: true): these are judgement values, not derived from a paper or a data set.
# They are the defaults compare_to_sim has always had; the right values depend on how much run-to-run spread real PSV
# traffic shows, which needs the first real HAIS calibration to judge. Callers may override every one of them.
GATE_4B_TOLERANCE = {"tol_rel": 0.25, "tol_abs_s": 600.0, "tol_abs_kn": 1.0, "min_n": 1, "assumption": True}

REJECT_COLUMNS = ["line_no", "reason", "sentence"]


class DecodeResult:
    """positions: normalised ais table (mmsi, timestamp, lon, lat, sog, cog, ship_type) incl. ship_type from type 5
    where the MMSI sent one; static: one row per type-5 message; rejects: every input line that produced nothing,
    with line_no (1-based), reason, sentence; counts: lines / decoded messages by type."""

    def __init__(self, positions, static, rejects, counts):
        self.positions, self.static, self.rejects, self.counts = positions, static, rejects, counts

    def __repr__(self):
        return f"DecodeResult(positions={len(self.positions)}, static={len(self.static)}, rejects={len(self.rejects)})"


def nmea_checksum_ok(sentence: str) -> bool:
    """True when the hex after '*' equals the XOR of the characters between '!' (or '$') and '*'."""
    s = sentence.strip()
    if not s or s[0] not in "!$" or "*" not in s:
        return False
    body, _, tail = s[1:].rpartition("*")
    try:
        want = int(tail[:2], 16)
    except ValueError:
        return False
    got = 0
    for ch in body:
        got ^= ord(ch)
    return got == want


def _split_line(raw: str):
    """'<epoch seconds> !AIVDM,...' -> (timestamp or None, sentence). A bare sentence has no time."""
    raw = raw.strip()
    if raw.startswith(("!", "$")):
        return None, raw
    head, _, rest = raw.partition(" ")
    try:
        ts = pd.Timestamp(float(head), unit="s", tz="UTC")
    except (ValueError, OverflowError):
        return None, raw
    return ts, rest.strip()


def decode_nmea(lines, default_time=None) -> DecodeResult:
    """Decode NMEA AIS lines. `lines` is a path (text file) or an iterable of str/bytes.

    Line format: "<unix epoch seconds> !AIVDM,..." (a receiver log with arrival times). A message carries no calendar
    date of its own (only the UTC second), so a line without an epoch gets `default_time` if given, else it is
    REJECTED with reason 'no timestamp' (it cannot enter a trajectory). A multipart message takes the time of its
    first fragment.

    Handled: types 1/2/3 (position), 5 (static: ship_type, name, callsign, IMO, draught, dimensions), multipart
    reassembly keyed by (talker, sequence id, channel, fragment count) with out-of-order fragments sorted; a
    position of lon 181 / lat 91 ('not available') is rejected, as is a bad checksum, an unparseable line, an
    incomplete multipart message and any other message type ('unsupported type N'). Nothing is dropped silently:
    positions + static + rejects account for every non-blank line (`counts['lines']`)."""
    from pyais import decode as pyais_decode

    if isinstance(lines, (str, Path)):
        lines = Path(lines).read_text().splitlines()
    pos_rows, static_rows, rejects = [], [], []
    pending: dict = {}                      # key -> {"frags": {n: sentence}, "cnt": int, "ts", "line_no"}
    counts = {"lines": 0, "by_type": {}}

    def rej(no, reason, sent):
        rejects.append({"line_no": no, "reason": reason, "sentence": sent})

    def emit(no, ts, parts):
        try:
            d = pyais_decode(*parts).asdict()
        except Exception as exc:            # pyais raises several exception types; each becomes a reported reject
            rej(no, f"pyais {type(exc).__name__}: {exc}", " | ".join(parts))
            return
        t = d.get("msg_type")
        counts["by_type"][t] = counts["by_type"].get(t, 0) + 1
        if t in POSITION_TYPES:
            lon, lat = d.get("lon"), d.get("lat")
            if lon is None or lat is None or abs(lon) >= 180.0 + 1e-9 or abs(lat) >= 90.0 + 1e-9 or lon == 181 or lat == 91:
                rej(no, "position not available (lon 181 / lat 91)", " | ".join(parts))
                return
            sog = d.get("speed")
            pos_rows.append({"mmsi": int(d["mmsi"]), "timestamp": ts, "lon": float(lon), "lat": float(lat),
                             "sog": np.nan if sog is None or sog >= 102.3 else float(sog),
                             "cog": np.nan if d.get("course") is None or d["course"] >= 360 else float(d["course"]),
                             "ship_type": np.nan})
        elif t in STATIC_TYPES:
            st = lambda k: (str(d.get(k) or "").strip("@ ").strip())
            static_rows.append({"mmsi": int(d["mmsi"]), "timestamp": ts, "shipname": st("shipname"),
                                "callsign": st("callsign"), "ship_type": d.get("ship_type"), "imo": d.get("imo"),
                                "draught": d.get("draught"), "to_bow": d.get("to_bow"), "to_stern": d.get("to_stern"),
                                "to_port": d.get("to_port"), "to_starboard": d.get("to_starboard"),
                                "destination": st("destination")})
        else:
            rej(no, f"unsupported type {t}", " | ".join(parts))

    for no, raw in enumerate(lines, start=1):
        raw = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
        if not raw.strip():
            continue
        counts["lines"] += 1
        ts, sent = _split_line(raw)
        if ts is None and default_time is not None:
            ts = pd.Timestamp(default_time, tz="UTC") if pd.Timestamp(default_time).tzinfo is None else pd.Timestamp(default_time)
        if not sent.startswith("!") or not sent[1:6].startswith(("AI", "BS", "AB", "AD", "AN", "AR", "AS", "AT", "AX", "BD", "SA", "BM")):
            rej(no, "not an AIS sentence", raw.strip())
            continue
        if not nmea_checksum_ok(sent):
            rej(no, "bad or missing checksum", sent)
            continue
        f = sent[1:sent.rindex("*")].split(",")
        try:
            cnt, num = int(f[1]), int(f[2])
            seq, chan = f[3], f[4]
        except (IndexError, ValueError):
            rej(no, "malformed NMEA fields", sent)
            continue
        if ts is None:
            rej(no, "no timestamp (give lines an epoch prefix or default_time)", sent)
            continue
        if cnt == 1:
            emit(no, ts, [sent])
            continue
        key = (f[0], seq, chan, cnt)
        slot = pending.setdefault(key, {"frags": {}, "ts": ts, "line_no": no})
        if num in slot["frags"]:                                   # a repeated fragment number starts a new message
            rej(slot["line_no"], "incomplete multipart message (superseded)", " | ".join(slot["frags"][k] for k in sorted(slot["frags"])))
            slot.update(frags={}, ts=ts, line_no=no)
        slot["frags"][num] = sent
        if len(slot["frags"]) == cnt:
            emit(slot["line_no"], slot["ts"], [slot["frags"][k] for k in sorted(slot["frags"])])
            del pending[key]
    for slot in pending.values():
        rej(slot["line_no"], "incomplete multipart message (missing fragments)", " | ".join(slot["frags"][k] for k in sorted(slot["frags"])))

    static = pd.DataFrame(static_rows, columns=["mmsi", "timestamp", "shipname", "callsign", "ship_type", "imo", "draught",
                                                "to_bow", "to_stern", "to_port", "to_starboard", "destination"])
    positions = pd.DataFrame(pos_rows, columns=["mmsi", "timestamp", "lon", "lat", "sog", "cog", "ship_type"])
    if len(static) and len(positions):
        types = static.dropna(subset=["ship_type"]).drop_duplicates("mmsi", keep="last").set_index("mmsi")["ship_type"]
        positions["ship_type"] = positions["mmsi"].map(types).astype(float)
    positions = load_ais(positions) if len(positions) else positions.astype({"mmsi": "int64"})
    return DecodeResult(positions, static, pd.DataFrame(rejects, columns=REJECT_COLUMNS).sort_values("line_no").reset_index(drop=True), counts)


def to_trajectory(positions: pd.DataFrame, t0=None, min_speed_kn: float = 1.0, anonymise: bool = False) -> pd.DataFrame:
    """Normalised AIS table -> contract trajectory rows (agent_id, t, lon, lat, state, plus sog_kn).

    t = seconds since `t0` (default: the earliest fix). state = 'sail' where the speed of the segment starting at the
    row (haversine/dt, falling back to reported sog) is >= min_speed_kn, else 'idle'. agent_id is the MMSI as text, or 'V01', 'V02' ... when
    `anonymise` (MMSI is vessel identity: use it for anything that leaves the repo)."""
    from offsim.contract import haversine_m

    df = load_ais(positions) if "timestamp" in positions else positions
    if df.empty:
        return pd.DataFrame(columns=["agent_id", "t", "lon", "lat", "state", "sog_kn"])
    t0 = df["timestamp"].min() if t0 is None else pd.Timestamp(t0, tz="UTC") if pd.Timestamp(t0).tzinfo is None else pd.Timestamp(t0)
    ids = {m: (f"V{i + 1:02d}" if anonymise else str(m)) for i, m in enumerate(sorted(df["mmsi"].unique()))}
    out = []
    for m, g in df.sort_values(["mmsi", "timestamp"]).groupby("mmsi", sort=True):
        t = (g["timestamp"] - t0).dt.total_seconds().to_numpy()
        sog = g["sog"].to_numpy(dtype=float)
        # contract.validate: "the state of the leg is the state at its start", so row i labels segment i -> i+1 and takes
        # that segment's speed; the last row has no leg and uses its own sog.
        d = haversine_m(g["lon"].to_numpy()[:-1], g["lat"].to_numpy()[:-1], g["lon"].to_numpy()[1:], g["lat"].to_numpy()[1:])
        with np.errstate(divide="ignore", invalid="ignore"):
            seg = np.where(np.diff(t) > 0, d / np.diff(t) / KN_TO_MPS, np.nan)
        arriving = np.concatenate([seg, sog[-1:]]) if len(sog) else sog
        arriving = np.where(np.isnan(arriving), sog, arriving)
        out.append(pd.DataFrame({"agent_id": ids[m], "t": t, "lon": g["lon"].to_numpy(), "lat": g["lat"].to_numpy(),
                                 "state": np.where(np.nan_to_num(arriving, nan=0.0) >= min_speed_kn, "sail", "idle"), "sog_kn": sog}))
    return pd.concat(out, ignore_index=True)


def compare_decoded(sim_traj, positions: pd.DataFrame, places, port_durations_s: dict | None = None, window=None,
                    mmsi=None, ship_types=None, gap: timedelta = timedelta(hours=2), tolerance: dict | None = None,
                    area: str = "unspecified"):
    """Gate 4b end to end: a decoded AIS track (any normalised positions table, from `decode_nmea` or HAIS) against a
    simulated contract trajectory. Returns (table, calib) where table is `compare_to_sim`'s DataFrame.

    What is compared (and nothing else):
      sailing_speed_kn  p10 / p50 / p90 of moving-segment speed, simulated (state in MOVING, haversine/dt) vs AIS
                        (reported sog, else derived; segments below 1 kn excluded).
      port_call_s       p10 / p50 / p90 of dwell at each named place in `port_durations_s` {place: [seconds]}, vs AIS
                        stops (>= 20 min within 250 m) matched to `places` within their radius_m.
    window: (start, end) UTC; AIS fixes outside it are ignored. It should span at least one complete port call per
    place compared, otherwise n_ais is 0 and the row is not judged (pass = NaN). Quantiles, not paired values: the
    simulation is a plan and AIS is a different day, so only distributions are comparable.
    tolerance: overrides for GATE_4B_TOLERANCE (tol_rel, tol_abs_s, tol_abs_kn, min_n). Its defaults are an
    assumption (see GATE_4B_TOLERANCE)."""
    tol = {k: v for k, v in {**GATE_4B_TOLERANCE, **(tolerance or {})}.items() if k != "assumption"}
    df = filter_ais(load_ais(positions), mmsi=mmsi, ship_types=ship_types,
                    start=window[0] if window else None, end=window[1] if window else None)
    if df.empty:
        raise ValueError("no AIS fixes left in the comparison window")
    dates = f"{df['timestamp'].min():%Y-%m-%d}..{df['timestamp'].max():%Y-%m-%d}"
    tracks = build_tracks(df, gap=gap)
    calls = port_calls(tracks, places) if places is not None else pd.DataFrame(columns=["mmsi", "place", "arrive", "depart", "duration_s"])
    calib = calibration(calls, tracks, area=area, dates=dates)
    return compare_to_sim(sim_traj, calib, port_durations_s, **tol), calib


def process_nmea(path, out_dir, bbox=None, places=None, ship_types=None, area: str = "unspecified", dates=None) -> dict:
    """fetch_world --ais equivalent for a raw NMEA log: decode, write <out_dir>/ais_rejects.csv (always, even if empty:
    a clean decode is evidence), then `process_hais` on the decoded positions (calibration.json, port_calls.csv)."""
    res = decode_nmea(path)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    res.rejects.to_csv(out / "ais_rejects.csv", index=False)
    return process_hais(res.positions, out_dir, bbox=bbox, places=places, ship_types=ship_types, area=area, dates=dates)
