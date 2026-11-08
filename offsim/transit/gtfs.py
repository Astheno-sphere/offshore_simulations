"""GTFS timetable -> trajectory contract: buses, ferries, trams and trains as agents (L0 data + L2 helpers).

Source: Entur national GTFS (NLOD 2.0, https://data.norge.no/nlod/en/2.0), clipped to a bounding box by `clip`
on the fetch workflow, then read here. Plain pandas + numpy; no network, no gtfs-kit.

Pipeline
    clip(zip_or_dir, bbox, out_dir, date)   national zip -> small GTFS folder + manifest.json   (Actions)
    load(dir)                               -> Feed (times parsed to seconds, past-midnight safe)
    service_ids_on / trips_on               which services / trips run on a date (calendar + calendar_dates)
    trajectories(feed, date, t0, t1)        -> (traj, agents) in the trajectory contract (offsim.contract)
    headways / in_service / kpis            small analysis helpers

Time. GTFS times are seconds since the *service day's* midnight and may exceed 24:00:00 ("25:10:00" = 01:10 the
next morning). `t0`/`t1` are seconds on the same clock, so t0=0, t1=86400 is the service day. Trips of the previous
service day that are still running after midnight appear with a negative offset (`offset_s = -86400`) and their
agent_id gets the suffix "~prev" so it cannot collide with the same trip of the requested day.

Mapping to the contract (what a trip *means* as an agent)
- One agent per trip, agent_id = trip_id. cls from route_type: bus | ferry | rail | tram (see `route_class`);
  domain "land" for bus/rail/tram, "sea" for ferry. capacity NaN (GTFS has none). Extra agents columns: trip_id,
  route_id, route_short_name, route_type, t_start, t_end (seconds from t0, may be < 0 / > window), has_shape.
- Position: along the trip's shape polyline. Stop positions on the shape come from `shape_dist_traveled` when both
  shapes.txt and the trip's stop_times carry it for every row (units are normalised, so km or m both work);
  otherwise each stop is projected onto the polyline, searching forward only (a loop route cannot jump back).
  No shape (or an unknown shape_id): straight lines between stops. Between stops speed is constant.
- State: "drive" ("sail" for ferries) while moving, "wait" while dwelling at a stop (arrival != departure) and at the
  terminus; "idle" is never used. A row is emitted at every stop arrival and departure plus every `sample_s`
  grid time (grid anchored at t0), so dwell is exact and the validator's "state of the leg is the state at its start"
  rule holds.
- vmax_mps = 1.1 x the largest observed stop-to-stop speed of that trip (distance along the path / travel time),
  floored at 1 m/s.
- Missing stop times (non-timepoints) are interpolated by distance along the path; times are forced monotonic and a
  moving leg gets at least 1 s (a zero-time hop between distinct stops would be a teleport); both are counted in the
  `meta` of `build`.

Limits. The timetable is the plan: delays, real-time and cancellations are not modelled. Frequency-based
trips (frequencies.txt) are not expanded. Trips with an unknown route_type (air, taxi, cable car, ...) are dropped and
counted. Ferry shapes are only as good as the operator's shape; without one the ferry runs straight between
quays and may cross land (the contract's land check will say so when given the sea mask).
"""
from __future__ import annotations

import datetime as _dt
import io
import json
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

import numpy as np
import pandas as pd

from offsim.contract import haversine_m

SOURCE = "Entur national GTFS"
LICENCE = "NLOD 2.0"
LICENCE_URL = "https://data.norge.no/nlod/en/2.0"
ATTRIBUTION = "Contains data under NLOD 2.0 from Entur"

_CHUNK = 1_000_000
_VMAX_FACTOR = 1.1
_MIN_VMAX = 1.0
_MIN_HOP_S = 1.0
_DAY = 86400.0

_STOP_COLS = ["stop_id", "stop_name", "stop_lat", "stop_lon", "location_type", "parent_station"]
_ST_COLS = ["trip_id", "stop_id", "arrival_time", "departure_time", "stop_sequence", "shape_dist_traveled"]
_SHAPE_COLS = ["shape_id", "shape_pt_lat", "shape_pt_lon", "shape_pt_sequence", "shape_dist_traveled"]
_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


# --- time and route type ------------------------------------------------------------------------------------

def parse_time(s) -> float:
    """"HH:MM:SS" -> seconds since the service day's midnight. Hours may exceed 23: "25:10:00" -> 90600.
    Blank / None / NaN -> NaN."""
    if s is None or (isinstance(s, float) and np.isnan(s)):
        return float("nan")
    s = str(s).strip()
    if not s:
        return float("nan")
    h, m, sec = s.split(":")
    return float(int(h) * 3600 + int(m) * 60 + int(sec))


def parse_times(series: pd.Series) -> pd.Series:
    """Vectorised `parse_time` (blank -> NaN)."""
    parts = series.astype("string").str.strip().str.split(":", expand=True)
    if parts.shape[1] < 3:
        return pd.Series(np.nan, index=series.index)
    num = parts.iloc[:, :3].apply(pd.to_numeric, errors="coerce")
    return (num[0] * 3600 + num[1] * 60 + num[2]).astype(float)


def route_class(route_type) -> str | None:
    """GTFS route_type (basic and extended/Entur codes) -> "bus" | "ferry" | "rail" | "tram" | None.
    None = not modelled (air 1100s, taxi 1500s, cable car 6/1300s, ...); such trips are dropped.
    tram: 0, 900-999.  rail: 1 (metro), 2, 5, 7, 12, 100-199, 300-499 (metro 400s), 1400s (funicular).
    bus: 3, 11 (trolleybus), 200-299 (coach), 700-899.  ferry: 4, 1000-1099 (water), 1200-1299 (ferry)."""
    try:
        rt = int(float(route_type))
    except (TypeError, ValueError):
        return None
    if rt == 0 or 900 <= rt <= 999:
        return "tram"
    if rt in (1, 2, 5, 7, 12) or 100 <= rt <= 199 or 300 <= rt <= 499 or 1400 <= rt <= 1499:
        return "rail"
    if rt in (3, 11) or 200 <= rt <= 299 or 700 <= rt <= 899:
        return "bus"
    if rt == 4 or 1000 <= rt <= 1099 or 1200 <= rt <= 1299:
        return "ferry"
    return None


def _domain(cls: str) -> str:
    return "sea" if cls == "ferry" else "land"


def _as_date(d) -> _dt.date:
    if isinstance(d, _dt.datetime):
        return d.date()
    if isinstance(d, _dt.date):
        return d
    s = str(d).strip().replace("-", "")
    return _dt.date(int(s[:4]), int(s[4:6]), int(s[6:8]))


def _ymd(d: _dt.date) -> str:
    return d.strftime("%Y%m%d")


# --- file access (dir or zip), chunked ----------------------------------------------------------------------

@contextmanager
def _open(src, name: str) -> Iterator[io.BufferedIOBase | None]:
    """Binary handle on `name` (e.g. "stops.txt") in a GTFS dir or zip (also when the zip nests a folder); None if absent."""
    p = Path(src)
    if p.is_dir():
        f = p / name
        if not f.exists():
            yield None
            return
        with open(f, "rb") as fh:
            yield fh
        return
    with zipfile.ZipFile(p) as z:
        hit = next((n for n in z.namelist() if n == name or n.endswith("/" + name)), None)
        if hit is None:
            yield None
            return
        with z.open(hit) as fh:
            yield fh


def _read(src, name: str, usecols: list[str] | None = None, chunksize: int | None = None):
    """DataFrame (or chunk iterator when chunksize) of a GTFS table, all as str, restricted to existing `usecols`.
    Absent file -> empty DataFrame (or empty iterator)."""
    def gen():
        with _open(src, name) as fh:
            if fh is None:
                return
            head = pd.read_csv(fh, nrows=0, dtype=str, encoding="utf-8-sig")
        cols = [c for c in head.columns if usecols is None or c in usecols]
        with _open(src, name) as fh:
            for ch in pd.read_csv(fh, dtype=str, usecols=cols, chunksize=chunksize or _CHUNK, encoding="utf-8-sig",
                                  keep_default_na=False, na_values=[""]):
                yield ch
    if chunksize:
        return gen()
    parts = list(gen())
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=usecols or [])


# --- feed ---------------------------------------------------------------------------------------------------

@dataclass
class Feed:
    """A loaded GTFS folder. stop_times has float columns arr_s, dep_s (blank times -> NaN) and int stop_seq."""
    stops: pd.DataFrame
    routes: pd.DataFrame
    trips: pd.DataFrame
    stop_times: pd.DataFrame
    calendar: pd.DataFrame
    calendar_dates: pd.DataFrame
    shapes: pd.DataFrame
    agency: pd.DataFrame = field(default_factory=pd.DataFrame)
    manifest: dict = field(default_factory=dict)
    path: str = ""
    _shape_cache: dict = field(default_factory=dict, repr=False)


def load(path) -> Feed:
    """Read a GTFS folder (or zip) written by `clip` or any GTFS source. Only needed columns of stop_times / shapes
    are kept. Raises FileNotFoundError when stops/trips/stop_times are missing."""
    src = Path(path)
    stops = _read(src, "stops.txt", _STOP_COLS)
    trips = _read(src, "trips.txt")
    st = _read(src, "stop_times.txt", _ST_COLS)
    routes = _read(src, "routes.txt")
    for nm, df in (("stops.txt", stops), ("trips.txt", trips), ("stop_times.txt", st)):
        if df.empty and not len(df.columns):
            raise FileNotFoundError(f"{nm} missing or empty in {src}")
    stops["stop_lat"] = pd.to_numeric(stops["stop_lat"], errors="coerce")
    stops["stop_lon"] = pd.to_numeric(stops["stop_lon"], errors="coerce")
    st["arr_s"] = parse_times(st["arrival_time"]) if "arrival_time" in st else np.nan
    st["dep_s"] = parse_times(st["departure_time"]) if "departure_time" in st else np.nan
    st["arr_s"] = st["arr_s"].fillna(st["dep_s"])
    st["dep_s"] = st["dep_s"].fillna(st["arr_s"])
    st["stop_seq"] = pd.to_numeric(st["stop_sequence"], errors="coerce").fillna(0).astype(int)
    if "shape_dist_traveled" in st:
        st["shape_dist_traveled"] = pd.to_numeric(st["shape_dist_traveled"], errors="coerce")
    else:
        st["shape_dist_traveled"] = np.nan
    st = st.drop(columns=[c for c in ("arrival_time", "departure_time", "stop_sequence") if c in st])
    shapes = _read(src, "shapes.txt", _SHAPE_COLS)
    if len(shapes):
        for c in ("shape_pt_lat", "shape_pt_lon", "shape_pt_sequence", "shape_dist_traveled"):
            shapes[c] = pd.to_numeric(shapes.get(c), errors="coerce")
    man = {}
    mp = src / "manifest.json"
    if src.is_dir() and mp.exists():
        man = json.loads(mp.read_text())
    return Feed(stops=stops, routes=routes, trips=trips, stop_times=st,
                calendar=_read(src, "calendar.txt"), calendar_dates=_read(src, "calendar_dates.txt"),
                shapes=shapes, agency=_read(src, "agency.txt"), manifest=man, path=str(src))


# --- service calendar ---------------------------------------------------------------------------------------

def _service_ids(calendar: pd.DataFrame, calendar_dates: pd.DataFrame, date) -> set[str]:
    d = _as_date(date)
    ymd = _ymd(d)
    active: set[str] = set()
    if len(calendar):
        wd = _WEEKDAYS[d.weekday()]
        c = calendar
        ok = (c["start_date"] <= ymd) & (c["end_date"] >= ymd) & (c[wd] == "1")
        active = set(c.loc[ok, "service_id"])
    if len(calendar_dates):
        ex = calendar_dates[calendar_dates["date"] == ymd]
        active |= set(ex.loc[ex["exception_type"] == "1", "service_id"])
        active -= set(ex.loc[ex["exception_type"] == "2", "service_id"])
    return active


def service_ids_on(feed: Feed, date) -> set[str]:
    """service_ids running on `date` (str "YYYYMMDD"/"YYYY-MM-DD" or datetime.date): calendar.txt weekday + date range,
    then calendar_dates.txt: exception_type 1 adds, 2 removes (also for services absent from calendar.txt)."""
    return _service_ids(feed.calendar, feed.calendar_dates, date)


# --- trips --------------------------------------------------------------------------------------------------

def _trip_spans(feed: Feed) -> pd.DataFrame:
    """Per trip: first departure and last arrival (service-day seconds), number of stops."""
    key = "_spans"
    if key not in feed._shape_cache:
        st = feed.stop_times
        g = st.groupby("trip_id", sort=False)
        feed._shape_cache[key] = pd.DataFrame({"start_s": g["dep_s"].min(), "end_s": g["arr_s"].max(),
                                               "n_stops": g.size()})
        e2 = g["dep_s"].max()
        sp = feed._shape_cache[key]
        sp["end_s"] = np.fmax(sp["end_s"], e2)
    return feed._shape_cache[key]


def trips_on(feed: Feed, date, t0: float | None = None, t1: float | None = None, route_types=None) -> pd.DataFrame:
    """Trips running on `date` that overlap the window [t0, t1] (seconds on the service-day clock; None = open).
    route_types: iterable of route_type codes (as in routes.txt, int or str) or classes ("bus", "ferry", ...).
    Columns: trip_id, route_id, route_type, cls, service_id, shape_id, route_short_name, start_s, end_s, n_stops,
    offset_s, agent_id. Trips of the previous service day still running after midnight are included with
    offset_s = -86400 (start_s/end_s already shifted) and agent_id = trip_id + "~prev"."""
    lo = -np.inf if t0 is None else float(t0)
    hi = np.inf if t1 is None else float(t1)
    d = _as_date(date)
    tr = feed.trips
    rt = feed.routes
    rcols = [c for c in ("route_id", "route_type", "route_short_name") if c in rt.columns]
    base = tr.merge(rt[rcols], on="route_id", how="left") if len(rt) else tr.assign(route_type=np.nan)
    if "shape_id" not in base:
        base["shape_id"] = np.nan
    if "route_short_name" not in base:
        base["route_short_name"] = np.nan
    base["cls"] = base["route_type"].map(route_class)
    spans = _trip_spans(feed)
    out = []
    for off, day in ((0.0, d), (-_DAY, d - _dt.timedelta(days=1))):
        sids = service_ids_on(feed, day)
        b = base[base["service_id"].isin(sids)].merge(spans, left_on="trip_id", right_index=True, how="inner")
        b = b.assign(start_s=b["start_s"] + off, end_s=b["end_s"] + off, offset_s=off)
        if off:
            b = b[b["end_s"] > 0]          # only the part after midnight matters
        b = b[(b["end_s"] >= lo) & (b["start_s"] <= hi)]
        b["agent_id"] = b["trip_id"] + ("~prev" if off else "")
        out.append(b)
    res = pd.concat(out, ignore_index=True)
    if route_types is not None:
        want = {str(x) for x in route_types}
        res = res[res["route_type"].astype(str).isin(want) | res["cls"].isin(want)]
    cols = ["agent_id", "trip_id", "route_id", "route_type", "cls", "service_id", "shape_id", "route_short_name",
            "start_s", "end_s", "n_stops", "offset_s"]
    return res[cols].sort_values(["start_s", "agent_id"], kind="stable").reset_index(drop=True)


# --- geometry along a shape ---------------------------------------------------------------------------------

class _Path:
    """Polyline with cumulative haversine length; positions by along-distance, projection of points (forward only)."""

    def __init__(self, lon, lat):
        lon = np.asarray(lon, float)
        lat = np.asarray(lat, float)
        self.lon, self.lat = lon, lat
        seg = haversine_m(lon[:-1], lat[:-1], lon[1:], lat[1:]) if len(lon) > 1 else np.zeros(0)
        self.seg = np.asarray(seg, float)
        self.cum = np.concatenate([[0.0], np.cumsum(self.seg)])
        self.length = float(self.cum[-1])
        kx = np.cos(np.radians(lat.mean())) if len(lat) else 1.0
        self.x, self.y = lon * kx, lat

    def at(self, s):
        """lon, lat at along-distance(s) s (clipped to [0, length])."""
        s = np.clip(np.asarray(s, float), 0.0, self.length)
        if len(self.seg) == 0:
            return np.full(s.shape, self.lon[0]), np.full(s.shape, self.lat[0])
        i = np.clip(np.searchsorted(self.cum, s, side="right") - 1, 0, len(self.seg) - 1)
        with np.errstate(divide="ignore", invalid="ignore"):
            u = np.where(self.seg[i] > 0, (s - self.cum[i]) / self.seg[i], 0.0)
        return self.lon[i] + u * (self.lon[i + 1] - self.lon[i]), self.lat[i] + u * (self.lat[i + 1] - self.lat[i])

    def project(self, lons, lats):
        """Along-distance of each point's nearest position, never behind the previous point's segment."""
        out = np.zeros(len(lons))
        if len(self.seg) == 0:
            return out
        px, py = np.asarray(lons) * (np.cos(np.radians(self.lat.mean()))), np.asarray(lats)
        ax, ay, bx, by = self.x[:-1], self.y[:-1], self.x[1:], self.y[1:]
        dx, dy = bx - ax, by - ay
        l2 = dx * dx + dy * dy
        start = 0
        for k in range(len(px)):
            sl = slice(start, None)
            with np.errstate(divide="ignore", invalid="ignore"):
                u = np.where(l2[sl] > 0, ((px[k] - ax[sl]) * dx[sl] + (py[k] - ay[sl]) * dy[sl]) / l2[sl], 0.0)
            u = np.clip(u, 0.0, 1.0)
            d2 = (ax[sl] + u * dx[sl] - px[k]) ** 2 + (ay[sl] + u * dy[sl] - py[k]) ** 2
            j = int(np.argmin(d2))
            out[k] = self.cum[start + j] + u[j] * self.seg[start + j]
            start += j
        return np.maximum.accumulate(out)


def _shape_path(feed: Feed, shape_id) -> tuple[_Path, np.ndarray | None] | None:
    if shape_id is None or (isinstance(shape_id, float) and np.isnan(shape_id)) or not len(feed.shapes):
        return None
    cache = feed._shape_cache
    if ("shape", shape_id) in cache:
        return cache[("shape", shape_id)]
    if "_shape_groups" not in cache:
        cache["_shape_groups"] = {k: v for k, v in feed.shapes.groupby("shape_id", sort=False)}
    g = cache["_shape_groups"].get(shape_id)
    res = None
    if g is not None and len(g) >= 2:
        g = g.sort_values("shape_pt_sequence", kind="stable")
        sd = g["shape_dist_traveled"].to_numpy(float)
        sd = sd if not np.isnan(sd).any() and sd[-1] > sd[0] else None
        res = (_Path(g["shape_pt_lon"], g["shape_pt_lat"]), sd)
    cache[("shape", shape_id)] = res
    return res


# --- trajectories -------------------------------------------------------------------------------------------

def _profile(feed: Feed, stops_xy: dict, trip_id: str, g: pd.DataFrame, shape_id, stats: dict):
    """(path, s_stop, arr, dep, stop_ids, has_shape) for one trip, or None when unusable. Times in service-day seconds."""
    g = g.sort_values("stop_seq", kind="stable")
    sid = g["stop_id"].to_numpy()
    keep = np.array([s in stops_xy for s in sid])
    if keep.sum() < 2:
        stats["bad_trips"] += 1
        return None
    g, sid = g[keep], sid[keep]
    lon = np.array([stops_xy[s][0] for s in sid])
    lat = np.array([stops_xy[s][1] for s in sid])
    arr, dep = g["arr_s"].to_numpy(float).copy(), g["dep_s"].to_numpy(float).copy()
    if np.isnan(arr).all() and np.isnan(dep).all():
        stats["bad_trips"] += 1
        return None
    sp = _shape_path(feed, shape_id)
    if sp is not None:
        path, sd = sp
        tsd = g["shape_dist_traveled"].to_numpy(float)
        if sd is not None and not np.isnan(tsd).any() and tsd[-1] > tsd[0]:
            f = np.clip((tsd - sd[0]) / (sd[-1] - sd[0]), 0, 1)
            s = np.maximum.accumulate(f * path.length)
        else:
            s = path.project(lon, lat)
    else:
        path = _Path(lon, lat)
        s = path.cum.copy()
    has_shape = sp is not None
    # fill missing times by distance between timed stops
    t_known = np.where(np.isnan(dep), arr, dep)
    ok = ~np.isnan(t_known)
    if ok.sum() < 2:
        stats["bad_trips"] += 1
        return None
    if (~ok).any():
        stats["interpolated_times"] += int((~ok).sum())
        fill = np.interp(s, s[ok], t_known[ok]) if np.all(np.diff(s[ok]) > 0) else np.interp(
            np.arange(len(s)), np.flatnonzero(ok), t_known[ok])
        arr = np.where(np.isnan(arr), fill, arr)
        dep = np.where(np.isnan(dep), fill, dep)
    arr = np.where(np.isnan(arr), dep, arr)
    dep = np.where(np.isnan(dep), arr, dep)
    # interleave arr0,dep0,arr1,dep1,... ; monotonic, dwell >= 0, moving hops >= 1 s
    seq = np.empty(2 * len(s))
    seq[0::2], seq[1::2] = arr, np.maximum(dep, arr)
    gaps = np.maximum(np.diff(seq), 0.0)
    ds = np.append(np.diff(s), 0.0)
    hop = np.arange(len(gaps)) % 2 == 1                      # dep_i -> arr_{i+1}
    short = hop & (ds[np.arange(len(gaps)) // 2] > 0.5) & (gaps < _MIN_HOP_S)
    if short.any():
        stats["floored_hops"] += int(short.sum())
        gaps = np.where(short, _MIN_HOP_S, gaps)
    seq_new = seq[0] + np.concatenate([[0.0], np.cumsum(gaps)])
    return path, s, seq_new[0::2], seq_new[1::2], sid, has_shape


def build(feed: Feed, date, t0: float, t1: float, sample_s: float = 30.0, route_types=None):
    """Like `trajectories` but returns (traj, agents, events, meta). events: agent_id, node (stop_id), event "dwell",
    t (s from t0), duration_s. meta: counts of dropped / repaired trips."""
    t0, t1, sample_s = float(t0), float(t1), float(sample_s)
    if t1 <= t0 or sample_s <= 0:
        raise ValueError("need t1 > t0 and sample_s > 0")
    tr = trips_on(feed, date, t0, t1, route_types)
    stats = {"bad_trips": 0, "interpolated_times": 0, "floored_hops": 0, "unknown_route_type": 0, "no_shape": 0}
    stats["unknown_route_type"] = int(tr["cls"].isna().sum())
    tr = tr[tr["cls"].notna()]
    stops_xy = {r.stop_id: (r.stop_lon, r.stop_lat) for r in feed.stops.dropna(subset=["stop_lat", "stop_lon"]).itertuples()}
    st = feed.stop_times[feed.stop_times["trip_id"].isin(set(tr["trip_id"]))]
    groups = {k: v for k, v in st.groupby("trip_id", sort=False)}
    rows, agent_rows, ev = [], [], []
    for r in tr.itertuples():
        g = groups.get(r.trip_id)
        if g is None:
            stats["bad_trips"] += 1
            continue
        prof = _profile(feed, stops_xy, r.trip_id, g, r.shape_id, stats)
        if prof is None:
            continue
        path, s, arr, dep, sid, has_shape = prof
        stats["no_shape"] += 0 if has_shape else 1
        off = r.offset_s
        arr, dep = arr + off, dep + off
        ts, te = arr[0], dep[-1]
        lo, hi = max(ts, t0), min(te, t1)
        if hi <= lo:
            continue
        k0 = int(np.ceil((lo - t0) / sample_s))
        k1 = int(np.floor((hi - t0) / sample_s))
        grid = t0 + sample_s * np.arange(k0, k1 + 1)
        evt = np.concatenate([arr, dep])
        times = np.unique(np.concatenate([grid, [lo, hi], evt[(evt >= lo) & (evt <= hi)]]))
        times = times[(times >= lo) & (times <= hi)]
        xp = np.empty(2 * len(s))
        xp[0::2], xp[1::2] = arr, dep
        sp_ = np.empty(2 * len(s))
        sp_[0::2] = sp_[1::2] = s
        pos = np.interp(times, xp, sp_)
        lon, lat = path.at(pos)
        k = np.clip(np.searchsorted(arr, times, side="right") - 1, 0, len(arr) - 1)
        dwell = (times < dep[k]) & (dep[k] > arr[k])
        moving = "sail" if r.cls == "ferry" else "drive"
        state = np.where(dwell | (times >= te), "wait", moving)
        obs = _observed_vmax(s, arr, dep)
        agent_rows.append({"agent_id": r.agent_id, "cls": r.cls, "vmax_mps": obs, "capacity": np.nan,
                           "domain": _domain(r.cls), "trip_id": r.trip_id, "route_id": r.route_id,
                           "route_short_name": r.route_short_name, "route_type": r.route_type,
                           "t_start": ts - t0, "t_end": te - t0, "has_shape": bool(has_shape)})
        rows.append(pd.DataFrame({"agent_id": r.agent_id, "t": times - t0, "lon": lon, "lat": lat, "alt_m": 0.0,
                                  "state": state}))
        for i in np.flatnonzero(dep > arr):
            if dep[i] > t0 and arr[i] < t1:
                ev.append((r.agent_id, sid[i], "dwell", arr[i] - t0, float(dep[i] - arr[i])))
    cols = ["agent_id", "t", "lon", "lat", "alt_m", "state"]
    traj = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=cols)
    agents = pd.DataFrame(agent_rows, columns=["agent_id", "cls", "vmax_mps", "capacity", "domain", "trip_id", "route_id",
                                               "route_short_name", "route_type", "t_start", "t_end", "has_shape"])
    events = pd.DataFrame(ev, columns=["agent_id", "node", "event", "t", "duration_s"])
    return traj, agents, events, stats


def _observed_vmax(s, arr, dep) -> float:
    ds = np.diff(s)
    dt = np.maximum(arr[1:] - dep[:-1], _MIN_HOP_S)
    v = ds / dt if len(ds) else np.zeros(1)
    return float(max(_MIN_VMAX, (v.max() if len(v) else 0.0) * _VMAX_FACTOR))


def trajectories(feed: Feed, date, t0: float, t1: float, sample_s: float = 30.0, route_types=None):
    """(traj, agents) in the trajectory contract for all trips running on `date` within [t0, t1] (service-day seconds).
    traj columns: agent_id, t (s from t0), lon, lat, alt_m, state. See the module docstring for the mapping."""
    traj, agents, _, _ = build(feed, date, t0, t1, sample_s, route_types)
    return traj, agents


# --- analysis helpers ---------------------------------------------------------------------------------------

def headways(feed: Feed, date, stop_id: str) -> pd.DataFrame:
    """Departures at `stop_id` on `date`, sorted: columns trip_id, route_id, dep_s, headway_s (gap to the previous
    departure at that stop, NaN for the first). Includes previous-day trips running past midnight (negative dep_s)."""
    tr = trips_on(feed, date)
    st = feed.stop_times[feed.stop_times["stop_id"] == stop_id]
    m = st.merge(tr[["agent_id", "trip_id", "route_id", "offset_s"]], on="trip_id", how="inner")
    m["dep_s"] = m["dep_s"] + m["offset_s"]
    m = m[(m["dep_s"] >= 0) | (m["offset_s"] < 0)]
    m = m[m["dep_s"] < _DAY]
    m = m.sort_values("dep_s", kind="stable")[["trip_id", "route_id", "dep_s"]].reset_index(drop=True)
    m["headway_s"] = m["dep_s"].diff()
    return m


def in_service(traj: pd.DataFrame, step_s: float = 60.0) -> pd.Series:
    """Vehicles in service by time: number of agents with first_t <= t <= last_t, on a grid of step_s over the trajectory."""
    if traj.empty:
        return pd.Series(dtype=float, name="in_service")
    g = traj.groupby("agent_id")["t"]
    a, b = g.min().to_numpy(), g.max().to_numpy()
    grid = np.arange(np.floor(traj["t"].min()), traj["t"].max() + step_s, step_s)
    n = np.searchsorted(np.sort(a), grid, side="right") - np.searchsorted(np.sort(b), grid, side="left")
    return pd.Series(n.astype(float), index=pd.Index(grid, name="t"), name="in_service")


def kpis(traj: pd.DataFrame, agents: pd.DataFrame | None = None, step_s: float = 60.0) -> dict:
    """{trips, vehicle_km, peak_vehicles, peak_t, mean_headway_s}.
    peak_vehicles: maximum of `in_service` on a step_s grid. mean_headway_s: mean gap between successive trip starts
    of the whole set (network dispatch interval; agents.t_start when given, else first row of each agent); NaN with
    fewer than 2 trips. For one stop's headway use `headways`."""
    if traj.empty:
        return {"trips": 0.0, "vehicle_km": 0.0, "peak_vehicles": 0.0, "peak_t": float("nan"),
                "mean_headway_s": float("nan")}
    t = traj.sort_values(["agent_id", "t"], kind="stable")
    same = (t["agent_id"].to_numpy()[1:] == t["agent_id"].to_numpy()[:-1])
    d = haversine_m(t["lon"].to_numpy()[:-1], t["lat"].to_numpy()[:-1], t["lon"].to_numpy()[1:], t["lat"].to_numpy()[1:])
    km = float(np.sum(d[same]) / 1000.0)
    ins = in_service(traj, step_s)
    if agents is not None and "t_start" in agents:
        starts = np.sort(agents["t_start"].to_numpy(float))
    else:
        starts = np.sort(traj.groupby("agent_id")["t"].min().to_numpy())
    hw = float(np.diff(starts).mean()) if len(starts) > 1 else float("nan")
    return {"trips": float(traj["agent_id"].nunique()), "vehicle_km": km, "peak_vehicles": float(ins.max()),
            "peak_t": float(ins.idxmax()), "mean_headway_s": hw}


# --- clip ---------------------------------------------------------------------------------------------------

def clip(zip_or_dir, bbox, out_dir, date=None, *, whole_trips: bool = True) -> dict:
    """Clip a (national) GTFS zip or folder to bbox = (min_lon, min_lat, max_lon, max_lat) and write a GTFS folder.

    Selection
    - stops: those inside bbox (boundary inclusive).
    - trips: a trip is kept when it has >= 2 stop_times at in-bbox stops. With `whole_trips=True` (default) the kept
      trip keeps ALL its stop_times, so out-of-bbox stops it serves are written to stops.txt too (a bus leaving the
      box still runs its true timetable and positions); `whole_trips=False` keeps only the in-bbox stop_times
      (smaller, but trips end at the box edge).
    - date: when given, only trips whose service runs on `date` or on the day before (past-midnight carry-over)
      are considered; calendar/calendar_dates are cut to the kept services.
    - routes, shapes, calendar, calendar_dates, agency: only what the kept trips reference (shapes whole, not cut).
    Streaming: tables are read in chunks of 1M rows with only the needed columns (stop_times: trip_id, stop_id,
    arrival_time, departure_time, stop_sequence, shape_dist_traveled), three passes over stop_times; memory stays
    proportional to the *kept* data plus a trip_id counter.

    Writes stops/routes/trips/stop_times/calendar/calendar_dates/shapes/agency .txt and manifest.json
    (source "Entur national GTFS", licence NLOD 2.0, date, bbox, counts). Returns the manifest."""
    min_lon, min_lat, max_lon, max_lat = map(float, bbox)
    src, out = Path(zip_or_dir), Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    stops = _read(src, "stops.txt", _STOP_COLS)
    lat = pd.to_numeric(stops["stop_lat"], errors="coerce")
    lon = pd.to_numeric(stops["stop_lon"], errors="coerce")
    inbox = (lon >= min_lon) & (lon <= max_lon) & (lat >= min_lat) & (lat <= max_lat)
    in_ids = set(stops.loc[inbox, "stop_id"])

    cal = _read(src, "calendar.txt")
    cald = _read(src, "calendar_dates.txt")
    svc_ok = None
    if date is not None:
        d = _as_date(date)
        svc_ok = _service_ids(cal, cald, d) | _service_ids(cal, cald, d - _dt.timedelta(days=1))

    trips = _read(src, "trips.txt")
    if svc_ok is not None:
        trips = trips[trips["service_id"].isin(svc_ok)]
    cand = set(trips["trip_id"])

    # pass 1: count in-bbox stops per candidate trip
    counts: dict[str, int] = {}
    for ch in _read(src, "stop_times.txt", ["trip_id", "stop_id"], chunksize=_CHUNK):
        ch = ch[ch["trip_id"].isin(cand) & ch["stop_id"].isin(in_ids)]
        for k, v in ch["trip_id"].value_counts().items():
            counts[k] = counts.get(k, 0) + int(v)
    kept = {k for k, v in counts.items() if v >= 2}
    trips = trips[trips["trip_id"].isin(kept)]

    # pass 2: write stop_times of kept trips
    st_path = out / "stop_times.txt"
    st_path.unlink(missing_ok=True)
    used_stops: set[str] = set()
    n_st = 0
    first = True
    for ch in _read(src, "stop_times.txt", _ST_COLS, chunksize=_CHUNK):
        ch = ch[ch["trip_id"].isin(kept)]
        if not whole_trips:
            ch = ch[ch["stop_id"].isin(in_ids)]
        if ch.empty:
            continue
        used_stops |= set(ch["stop_id"])
        n_st += len(ch)
        ch.to_csv(st_path, mode="w" if first else "a", header=first, index=False)
        first = False
    if first:
        pd.DataFrame(columns=_ST_COLS).to_csv(st_path, index=False)

    keep_stops = stops[stops["stop_id"].isin(used_stops)]
    keep_stops.to_csv(out / "stops.txt", index=False)
    trips.to_csv(out / "trips.txt", index=False)

    routes = _read(src, "routes.txt")
    routes = routes[routes["route_id"].isin(set(trips["route_id"]))]
    routes.to_csv(out / "routes.txt", index=False)

    svc = set(trips["service_id"])
    cal[cal["service_id"].isin(svc)].to_csv(out / "calendar.txt", index=False)
    cald[cald["service_id"].isin(svc)].to_csv(out / "calendar_dates.txt", index=False)

    shape_ids = set(trips["shape_id"].dropna()) if "shape_id" in trips else set()
    sh_path = out / "shapes.txt"
    sh_path.unlink(missing_ok=True)
    n_sh, first = 0, True
    for ch in _read(src, "shapes.txt", _SHAPE_COLS, chunksize=_CHUNK):
        ch = ch[ch["shape_id"].isin(shape_ids)]
        if ch.empty:
            continue
        n_sh += len(ch)
        ch.to_csv(sh_path, mode="w" if first else "a", header=first, index=False)
        first = False
    if first:
        pd.DataFrame(columns=_SHAPE_COLS).to_csv(sh_path, index=False)

    ag = _read(src, "agency.txt")
    if len(ag) and "agency_id" in ag and "agency_id" in routes:
        ag = ag[ag["agency_id"].isin(set(routes["agency_id"].dropna())) | ag["agency_id"].isna()]
    ag.to_csv(out / "agency.txt", index=False)

    manifest = {
        "source": SOURCE, "licence": LICENCE, "licence_url": LICENCE_URL, "attribution": ATTRIBUTION,
        "date": None if date is None else _as_date(date).isoformat(),
        "bbox": [min_lon, min_lat, max_lon, max_lat], "whole_trips": bool(whole_trips),
        "input": src.name, "clipped_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "counts": {"stops_in_bbox": len(in_ids), "stops": int(len(keep_stops)), "routes": int(len(routes)),
                   "trips": int(len(trips)), "stop_times": int(n_st), "shape_points": int(n_sh),
                   "services": len(svc)},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest
