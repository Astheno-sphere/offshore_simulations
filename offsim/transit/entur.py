"""Entur realtime client: vehicle positions (collector) and departures. Stdlib only, polling only (no websockets).
Runs on Actions or a laptop: the Claude workspace cannot reach api.entur.io.

Source: Entur AS (credit "Source: Entur AS"); licence open (NLOD 2.0 for the data; check developer.entur.no/apis/open).
All open Entur APIs are HTTP POST GraphQL and need the header `ET-Client-Name: <company>-<application>`
(`client_headers`; env ENTUR_CLIENT_NAME, default "astheno-offshoresimulations"). Unidentified clients get 60 req/min and
5 req/s, answered with HTTP 429 + Retry-After; `graphql` honours Retry-After and retries.

Endpoints (from developer.entur.no/apis/open, 2026-11-08):
    VEHICLES_URL        https://api.entur.io/realtime/v2/vehicles/graphql      real-time positions, delays, occupancy
    JOURNEY_PLANNER_URL https://api.entur.io/journey-planner/v3/graphql
    TRANSIT_DATA_URL    https://api.entur.io/transit-data/v1beta/graphql       (beta, not used here)
    MCP (no auth, candidate Claude desktop connectors): https://api.entur.io/journey-planner-mcp/v1/mcp ,
                                                       https://api.entur.io/transit-data/v1beta/mcp

UNVERIFIED LIVE. GraphQL field names, argument names, variable types and units (delay, speed) were written from the
public documentation as recalled; nothing here has run against the real service. The vehicle query is
    vehicles(boundingBox: {minLat, minLon, maxLat, maxLon}[, codespaceId]) { vehicleId line { lineRef publicCode }
        serviceJourney { id } lastUpdated location { latitude longitude } delay bearing speed }
and the parser reads every field with `.get` fallbacks (alternative names are tried: `vehicleRef`, `lastUpdatedTime`,
`recordedAtTime`, `lat`/`lon`). `delay` may be seconds (number) or an ISO-8601 duration ("PT2M30S"); `speed` is taken as
m/s (assumption, check the schema in the GraphiQL explorer). Fix QUERY_FIELDS / _row before trusting any output.
Tests use hand-written fixtures (tests/fixtures/entur/).

Injectable network: every call goes through `post(url, body_bytes, headers) -> bytes` (default `default_post`, urllib).
A fake that raises `RateLimited(retry_after)` (or urllib's HTTPError 429) exercises the retry path.

Pipeline
    python -m offsim.transit.entur collect --bbox lon0,lat0,lon1,lat1 --minutes 60 --out data/worlds/<w>/entur/vehicles.csv
        -> vehicles.csv (vehicle_id, line_ref, service_journey_id, t_utc, lon, lat, delay_s, bearing, speed_mps)
    offsim.transit.observed.observed_trajectories(read_csv(path), t0_utc)  -> contract trajectories
    offsim.transit.observed.compare_to_schedule / gate_4c                  -> gate 4c (opt-in, see observed.py)
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

import pandas as pd

VEHICLES_URL = "https://api.entur.io/realtime/v2/vehicles/graphql"
JOURNEY_PLANNER_URL = "https://api.entur.io/journey-planner/v3/graphql"
TRANSIT_DATA_URL = "https://api.entur.io/transit-data/v1beta/graphql"
MCP_JOURNEY_PLANNER = "https://api.entur.io/journey-planner-mcp/v1/mcp"
MCP_TRANSIT_DATA = "https://api.entur.io/transit-data/v1beta/mcp"
DEFAULT_CLIENT = "astheno-offshoresimulations"
CREDIT = "Source: Entur AS"
COLUMNS = ["vehicle_id", "line_ref", "service_journey_id", "t_utc", "lon", "lat", "delay_s", "bearing", "speed_mps"]
MIN_EVERY_S = 2.0           # 60 req/min and 5 req/s for unidentified clients; we stay well below both
MAX_RETRY_WAIT_S = 120.0

QUERY_FIELDS = ("vehicleId line { lineRef publicCode } serviceJourney { id } lastUpdated "
                "location { latitude longitude } delay bearing speed")   # unverified live

Post = Callable[[str, bytes, dict], bytes]


class RateLimited(Exception):
    """HTTP 429. `retry_after` is the Retry-After header in seconds (None when absent)."""

    def __init__(self, retry_after: float | None = None):
        super().__init__(f"HTTP 429 (Retry-After {retry_after})")
        self.retry_after = retry_after


class EnturError(RuntimeError):
    """GraphQL `errors` without usable data, or an unparseable response."""


def client_headers(env=None) -> dict:
    """Headers every Entur call needs. ET-Client-Name = env ENTUR_CLIENT_NAME (empty counts as unset) or the default."""
    env = os.environ if env is None else env
    name = (env.get("ENTUR_CLIENT_NAME") or "").strip() or DEFAULT_CLIENT
    return {"ET-Client-Name": name, "Content-Type": "application/json", "Accept": "application/json"}


def default_post(url: str, body: bytes, headers: dict, timeout: int = 60) -> bytes:
    """urllib POST. HTTP 429 is raised as RateLimited(Retry-After seconds); other HTTP errors propagate."""
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise RateLimited(_retry_after(getattr(e, "headers", None))) from e
        raise


def _retry_after(headers) -> float | None:
    try:
        v = headers.get("Retry-After") if headers is not None else None
        return float(v) if v is not None else None
    except (TypeError, ValueError):       # HTTP-date form: fall back to the backoff
        return None


def graphql(url: str, query: str, variables: dict | None = None, post: Post | None = None, *,
            retries: int = 4, sleep: Callable[[float], None] = time.sleep, env=None) -> dict:
    """POST one GraphQL query and return the `data` object. HTTP 429 sleeps for Retry-After (else 2, 4, 8 ... s,
    capped at 120 s) and retries up to `retries` times, then re-raises RateLimited. A response with `errors` and no
    `data` raises EnturError."""
    post = post or default_post
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    headers = client_headers(env)
    for attempt in range(retries + 1):
        try:
            raw = post(url, body, headers)
            break
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise
            err = RateLimited(_retry_after(e.headers))
        except RateLimited as e:
            err = e
        if attempt == retries:
            raise err
        wait = err.retry_after if err.retry_after is not None else 2.0 ** (attempt + 1)
        sleep(min(max(wait, 0.0), MAX_RETRY_WAIT_S))
    try:
        js = json.loads(raw)
    except (ValueError, TypeError) as e:
        raise EnturError(f"response is not JSON: {e}") from e
    if not isinstance(js, dict):
        raise EnturError("response is not a JSON object")
    if js.get("errors") and not js.get("data"):
        raise EnturError("; ".join(str(e.get("message", e)) if isinstance(e, dict) else str(e) for e in js["errors"])[:500])
    return js.get("data") or {}


# --- vehicle positions ---------------------------------------------------------------------------------------

def vehicle_query(codespace: str | None = None) -> str:
    cs_var = ", $codespace: String" if codespace else ""
    cs_arg = ", codespaceId: $codespace" if codespace else ""
    return (f"query V($minLat: Float!, $minLon: Float!, $maxLat: Float!, $maxLon: Float!{cs_var}) "
            f"{{ vehicles(boundingBox: {{minLat: $minLat, minLon: $minLon, maxLat: $maxLat, maxLon: $maxLon}}{cs_arg}) "
            f"{{ {QUERY_FIELDS} }} }}")


_ISO_DUR = re.compile(r"^(-)?P(?:T(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)S)?)$")


def _delay_s(v) -> float:
    """Delay in seconds from a number or an ISO-8601 duration ("PT2M30S", "-PT45S"); NaN when unknown."""
    if v is None or v == "":
        return float("nan")
    if isinstance(v, (int, float)):
        return float(v)
    m = _ISO_DUR.match(str(v).strip())
    if m:
        s = sum(float(x or 0) * k for x, k in zip(m.groups()[1:], (3600, 60, 1)))
        return -s if m.group(1) else s
    try:
        return float(v)
    except ValueError:
        return float("nan")


def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


def _row(v: dict, fetched: pd.Timestamp):
    if not isinstance(v, dict):
        return None
    loc = v.get("location") or {}
    lon = _num(loc.get("longitude", loc.get("lon")))
    lat = _num(loc.get("latitude", loc.get("lat")))
    if lon != lon or lat != lat:
        return None
    vid = v.get("vehicleId") or v.get("vehicleRef") or v.get("id")
    if vid in (None, ""):
        return None
    line = v.get("line") or {}
    sj = v.get("serviceJourney") or {}
    t = pd.to_datetime(v.get("lastUpdated") or v.get("lastUpdatedTime") or v.get("recordedAtTime"), utc=True, errors="coerce")
    if pd.isna(t):
        t = fetched
    return {"vehicle_id": str(vid), "line_ref": line.get("lineRef") or line.get("publicCode") or "",
            "service_journey_id": sj.get("id") or "", "t_utc": t, "lon": lon, "lat": lat,
            "delay_s": _delay_s(v.get("delay")), "bearing": _num(v.get("bearing")), "speed_mps": _num(v.get("speed"))}


def vehicles(bbox, codespace: str | None = None, post: Post | None = None, *,
             url: str = VEHICLES_URL, clock: Callable[[], float] = time.time, **kw) -> pd.DataFrame:
    """One snapshot of live vehicles inside bbox = (lon0, lat0, lon1, lat1). Returns DataFrame(vehicle_id, line_ref,
    service_journey_id, t_utc [tz-aware UTC, the vehicle's lastUpdated, else the fetch time], lon, lat, delay_s,
    bearing, speed_mps). Rows without a position or id are dropped. UNVERIFIED LIVE field names: see module docstring."""
    lon0, lat0, lon1, lat1 = (float(x) for x in bbox)
    variables = {"minLat": min(lat0, lat1), "minLon": min(lon0, lon1), "maxLat": max(lat0, lat1), "maxLon": max(lon0, lon1)}
    if codespace:
        variables["codespace"] = codespace
    data = graphql(url, vehicle_query(codespace), variables, post, **kw)
    fetched = pd.Timestamp(clock(), unit="s", tz="UTC")
    rows = [r for r in (_row(v, fetched) for v in (data.get("vehicles") or [])) if r]
    df = pd.DataFrame(rows, columns=COLUMNS)
    df["t_utc"] = pd.to_datetime(df["t_utc"], utc=True)
    return df


def _iso(t) -> str:
    return pd.Timestamp(t).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def read_csv(path) -> pd.DataFrame:
    """Read a vehicles.csv written by `collect` (t_utc parsed to tz-aware UTC)."""
    df = pd.read_csv(path, dtype={"vehicle_id": str, "line_ref": str, "service_journey_id": str}, keep_default_na=False,
                     na_values=[""]).reindex(columns=COLUMNS)
    df["line_ref"] = df["line_ref"].fillna("")
    df["service_journey_id"] = df["service_journey_id"].fillna("")
    df["t_utc"] = pd.to_datetime(df["t_utc"], utc=True)
    return df


def collect(bbox, minutes: float, every_s: float = 30.0, out_csv="vehicles.csv", post: Post | None = None,
            sleep: Callable[[float], None] = time.sleep, codespace: str | None = None, max_failures: int = 3,
            **kw) -> int:
    """Poll `vehicles` every `every_s` seconds (>= 2 s: Entur allows 60 req/min, 5 req/s) for `minutes` minutes
    (floor(minutes*60/every_s)+1 polls) and append new rows to out_csv. Rows are deduplicated by (vehicle_id, t_utc),
    also against rows already in the file, so a re-run or an overlapping poll never duplicates. A failed poll is logged and
    skipped; `max_failures` failures in a row re-raise. Returns the number of rows appended."""
    every_s = max(float(every_s), MIN_EVERY_S)
    n_polls = int(float(minutes) * 60.0 // every_s) + 1
    out = Path(out_csv)
    out.parent.mkdir(parents=True, exist_ok=True)
    seen: set = set()
    if out.exists() and out.stat().st_size:
        old = read_csv(out)
        seen = set(zip(old["vehicle_id"], old["t_utc"].map(_iso)))
    added, fails = 0, 0
    for i in range(n_polls):
        try:
            df = vehicles(bbox, codespace, post, **kw)
            fails = 0
        except Exception as e:                       # noqa: BLE001 - network/API faults must not lose the collected data
            fails += 1
            print(f"poll {i + 1}/{n_polls} failed: {e}", file=sys.stderr)
            if fails >= max_failures:
                raise
        else:
            keys = list(zip(df["vehicle_id"], df["t_utc"].map(_iso))) if len(df) else []
            new = [k not in seen for k in keys]
            df = df[new].copy() if len(df) else df
            df = df.drop_duplicates(["vehicle_id", "t_utc"])
            seen.update(zip(df["vehicle_id"], df["t_utc"].map(_iso)))
            if len(df):
                df["t_utc"] = df["t_utc"].map(_iso)
                df.to_csv(out, mode="a", header=not (out.exists() and out.stat().st_size), index=False)
                added += len(df)
            print(f"poll {i + 1}/{n_polls}: {len(df)} new rows ({added} total)")
        if i < n_polls - 1:
            sleep(every_s)
    return added


# --- departures (Journey Planner) ----------------------------------------------------------------------------

DEPARTURES_QUERY = ("query D($id: String!, $n: Int!) { stopPlace(id: $id) { id name estimatedCalls(numberOfDepartures: $n) "
                    "{ realtime aimedDepartureTime expectedDepartureTime destinationDisplay { frontText } "
                    "serviceJourney { id line { publicCode } } } } }")      # unverified live


def departures(stop_place_id: str, n: int = 10, post: Post | None = None, **kw) -> pd.DataFrame:
    """Next `n` departures of a stop place ("NSR:StopPlace:...") from Journey Planner v3. Minimal fields; UNVERIFIED LIVE.
    Returns DataFrame(service_journey_id, line, destination, aimed_utc, expected_utc, realtime, delay_s)."""
    data = graphql(JOURNEY_PLANNER_URL, DEPARTURES_QUERY, {"id": stop_place_id, "n": int(n)}, post, **kw)
    calls = ((data.get("stopPlace") or {}).get("estimatedCalls")) or []
    rows = []
    for c in calls:
        sj = c.get("serviceJourney") or {}
        aimed = pd.to_datetime(c.get("aimedDepartureTime"), utc=True, errors="coerce")
        exp = pd.to_datetime(c.get("expectedDepartureTime"), utc=True, errors="coerce")
        rows.append({"service_journey_id": sj.get("id") or "", "line": (sj.get("line") or {}).get("publicCode") or "",
                     "destination": (c.get("destinationDisplay") or {}).get("frontText") or "", "aimed_utc": aimed,
                     "expected_utc": exp, "realtime": bool(c.get("realtime")),
                     "delay_s": float((exp - aimed).total_seconds()) if pd.notna(aimed) and pd.notna(exp) else float("nan")})
    return pd.DataFrame(rows, columns=["service_journey_id", "line", "destination", "aimed_utc", "expected_utc", "realtime",
                                       "delay_s"])


def _bbox(s: str):
    p = [float(x) for x in s.split(",")]
    if len(p) != 4:
        raise argparse_error("--bbox needs lon0,lat0,lon1,lat1")
    return tuple(p)


def argparse_error(msg: str) -> SystemExit:
    print(msg, file=sys.stderr)
    return SystemExit(2)


def main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=f"Entur realtime ({CREDIT}). Unverified live endpoints.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect", help="poll vehicle positions and append to a CSV")
    c.add_argument("--bbox", required=True, help="lon0,lat0,lon1,lat1")
    c.add_argument("--minutes", type=float, default=60.0)
    c.add_argument("--every-s", type=float, default=30.0)
    c.add_argument("--codespace", default=None, help="optional operator codespace filter, e.g. RUT")
    c.add_argument("--out", required=True)
    d = sub.add_parser("departures", help="print the next departures of a stop place")
    d.add_argument("--stop", required=True)
    d.add_argument("-n", type=int, default=10)
    a = ap.parse_args(argv)
    if a.cmd == "collect":
        n = collect(_bbox(a.bbox), a.minutes, a.every_s, a.out, codespace=a.codespace)
        print(f"{n} rows -> {a.out}  ({CREDIT})")
    else:
        print(departures(a.stop, a.n).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
