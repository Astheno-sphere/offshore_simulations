"""Observed transit (Entur realtime vehicle positions) -> contract trajectories, and schedule-vs-observed validation.

GATE 4c (transit realtime validation, opt-in; analogous to AIS gate 4b in offsim.traffic.ais.compare_to_sim). The GTFS
engine replays the published timetable (offsim.transit.gtfs); this gate asks how well that timetable describes what the
vehicles did, using positions collected by `offsim.transit.entur collect` (Source: Entur AS):

    obs   = entur.read_csv("data/worlds/<w>/entur/vehicles.csv")
    o_tr, o_ag = observed_trajectories(obs, t0_utc)             # same clock as the scheduled trajectory (see below)
    cmp   = compare_to_schedule(s_traj, o_tr)                   # one row per journey
    res   = gate_4c(cmp)                                        # {"pass": bool, "detail": {...}}

Not wired into `offsim run`: call it by hand and record the outcome in docs/TESTLOG.md until a scenario flag
(`validate: {transit_realtime: true}`) is added to offsim.pipeline. A run that judges no journey FAILS (as gate 4b does for a
calibration that judges nothing).

Clock. `observed_trajectories(vehicles_df, t0_utc)` writes t = seconds since the UTC instant t0_utc. The scheduled trajectory
uses seconds since its own t0 (gtfs: the service-day clock + the window start). The caller must pick t0_utc as the UTC
instant of the schedule's t = 0 (service-day midnight in Europe/Oslo is 23:00 or 22:00 UTC the evening before); the gate
cannot detect an offset. Observed rows before t0_utc are dropped.

Matching. A scheduled agent is a GTFS trip (agent_id = trip_id, "~prev" suffix for yesterday's trips). Entur GTFS trip_id
equals the NeTEx ServiceJourney id, which is what the realtime feed reports, so `match="service_journey_id"` joins
observed agent_id (= service_journey_id) to scheduled agent_id with "~prev" stripped (or to a `service_journey_id` column
when a frame has one). `match="agent_id"` joins on agent_id as is.

Delay (per observed point). The observed position is projected onto the scheduled path (local metric plane, nearest segment);
the scheduled time at that point of the path is interpolated from the scheduled trajectory (first arrival, so a dwell
counts from its start); delay = t_observed - t_scheduled, positive = late. Points farther than `off_route_m` from the
path are dropped. Loop routes that revisit the same place can project to the wrong lap (known limit).
Travel-time ratio = observed time between the first and last observed point / scheduled time between the same two path
positions (>= 1 means slower than the timetable).

Tolerances in `gate_4c` are ASSUMPTIONS (assumption: true), not sourced from Entur or a paper: median |delay| <= 180 s
(a common punctuality threshold is "within 3 min"; unsourced here) and median travel-time ratio <= 1.25. Change them in the
scenario and state them on screen.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from offsim.contract import haversine_m

CLS_DEFAULT = "bus"
MOVING_MPS = 0.5          # below this a vehicle counts as waiting (assumption)
VMAX_FACTOR = 1.1         # as offsim.transit.gtfs
MIN_VMAX = 1.0
EARTH_R = 6_371_008.8

GATE_4C_ASSUMPTIONS = {
    "max_median_delay_s": {"value": 180.0, "assumption": True, "note": "median over journeys of |median delay|"},
    "max_tt_ratio": {"value": 1.25, "assumption": True, "note": "median over journeys of observed/scheduled travel time"},
}


def _to_utc(t) -> pd.Timestamp:
    t = pd.Timestamp(t)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def observed_trajectories(vehicles_df: pd.DataFrame, t0_utc, cls: str = CLS_DEFAULT, domain: str = "land"):
    """(traj, agents) in the trajectory contract from an `entur.vehicles` / `entur.read_csv` table.

    Agent = one service journey (agent_id = service_journey_id; a vehicle id is used when the journey id is empty, and
    "<journey>|<vehicle>" when several vehicles report the same journey, so tracks never interleave). t = seconds since
    t0_utc; rows before it, rows without position/time and repeated (agent, t) pairs are dropped. State of a leg: "drive" if the
    vehicle moved >= MOVING_MPS between its two samples, else "wait" (the contract forbids moving while waiting); the last
    row takes the reported speed (>= MOVING_MPS = drive) else the previous leg's state. vmax_mps = 1.1 x the larger of the
    fastest observed leg and the fastest reported speed (floor 1 m/s). traj columns: agent_id, t, lon, lat, alt_m, state.
    agents columns: agent_id, cls, vmax_mps, capacity (NaN), domain, service_journey_id, line_ref, vehicle_id, t_start, t_end."""
    tcols = ["agent_id", "t", "lon", "lat", "alt_m", "state"]
    acols = ["agent_id", "cls", "vmax_mps", "capacity", "domain", "service_journey_id", "line_ref", "vehicle_id",
             "t_start", "t_end"]
    if vehicles_df is None or not len(vehicles_df):
        return pd.DataFrame(columns=tcols), pd.DataFrame(columns=acols)
    df = vehicles_df.copy()
    df["t_utc"] = pd.to_datetime(df["t_utc"], utc=True, errors="coerce")
    df["t"] = (df["t_utc"] - _to_utc(t0_utc)).dt.total_seconds()
    for c in ("service_journey_id", "line_ref"):
        df[c] = df[c].fillna("").astype(str) if c in df else ""
    df["vehicle_id"] = df["vehicle_id"].astype(str)
    if "speed_mps" not in df:
        df["speed_mps"] = np.nan
    df = df.dropna(subset=["t", "lon", "lat"])
    df = df[df["t"] >= 0]
    if df.empty:
        return pd.DataFrame(columns=tcols), pd.DataFrame(columns=acols)
    base = df["service_journey_id"].where(df["service_journey_id"] != "", df["vehicle_id"])
    nveh = df.assign(_b=base).groupby("_b")["vehicle_id"].transform("nunique")
    df["agent_id"] = np.where(nveh > 1, base + "|" + df["vehicle_id"], base)
    df = df.sort_values(["agent_id", "t"]).drop_duplicates(["agent_id", "t"])
    trs, ags = [], []
    for aid, g in df.groupby("agent_id", sort=False):
        lon, lat, t = g["lon"].to_numpy(float), g["lat"].to_numpy(float), g["t"].to_numpy(float)
        dt = np.diff(t)
        d = haversine_m(lon[:-1], lat[:-1], lon[1:], lat[1:]) if len(g) > 1 else np.zeros(0)
        v = d / dt if len(g) > 1 else np.zeros(0)             # dt > 0: duplicates were dropped
        state = np.where(v >= MOVING_MPS, "drive", "wait").astype(object)
        rep = g["speed_mps"].to_numpy(float)
        if len(g) > 1:
            last = "drive" if (rep[-1] == rep[-1] and rep[-1] >= MOVING_MPS) else state[-1]
        else:
            last = "drive" if (rep[-1] == rep[-1] and rep[-1] >= MOVING_MPS) else "wait"
        state = np.append(state, last) if len(g) > 1 else np.array([last], dtype=object)
        vmax = max(MIN_VMAX, VMAX_FACTOR * max(float(v.max()) if len(v) else 0.0, float(np.nanmax(rep)) if np.isfinite(rep).any() else 0.0))
        trs.append(pd.DataFrame({"agent_id": aid, "t": t, "lon": lon, "lat": lat, "alt_m": 0.0, "state": state}))
        ags.append({"agent_id": aid, "cls": cls, "vmax_mps": vmax, "capacity": np.nan, "domain": domain,
                    "service_journey_id": g["service_journey_id"].iloc[0], "line_ref": g["line_ref"].iloc[0],
                    "vehicle_id": g["vehicle_id"].iloc[0], "t_start": float(t[0]), "t_end": float(t[-1])})
    return pd.concat(trs, ignore_index=True), pd.DataFrame(ags, columns=acols)


# --- schedule vs observed -------------------------------------------------------------------------------------

def _keys(traj: pd.DataFrame, match: str) -> pd.Series:
    if match == "agent_id":
        return traj["agent_id"].astype(str)
    if match == "service_journey_id":
        if "service_journey_id" in traj.columns:
            k = traj["service_journey_id"].astype(str)
            return k.where(k != "", traj["agent_id"].astype(str))
        return traj["agent_id"].astype(str).str.replace("~prev", "", regex=False)
    raise ValueError("match must be 'service_journey_id' or 'agent_id'")


def _xy(lon, lat, lon0, lat0):
    k = np.pi / 180.0 * EARTH_R
    return (np.asarray(lon) - lon0) * np.cos(np.radians(lat0)) * k, (np.asarray(lat) - lat0) * k


def _project(px, py, ax, ay, bx, by):
    """Nearest point of polyline (ax,ay)->(bx,by) segments to each (px,py): (segment index, fraction, distance m)."""
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    with np.errstate(divide="ignore", invalid="ignore"):
        u = ((px[:, None] - ax) * dx + (py[:, None] - ay) * dy) / np.where(L2 > 0, L2, np.nan)
    u = np.clip(np.nan_to_num(u, nan=0.0), 0.0, 1.0)
    qx, qy = ax + u * dx, ay + u * dy
    dist = np.hypot(px[:, None] - qx, py[:, None] - qy)
    i = dist.argmin(axis=1)
    r = np.arange(len(px))
    return i, u[r, i], dist[r, i]


_COLS = ["service_journey_id", "n_points", "n_used", "delay_p10", "delay_p50", "delay_p90", "tt_sched_s", "tt_obs_s",
         "tt_ratio", "coverage", "max_offroute_m"]


def compare_to_schedule(sched_traj: pd.DataFrame, observed_traj: pd.DataFrame, match: str = "service_journey_id",
                        off_route_m: float = 300.0, min_path_m: float = 100.0, min_span_s: float = 60.0) -> pd.DataFrame:
    """Per journey: delay quantiles, travel-time ratio observed/scheduled, point counts (method in the module docstring).

    Both trajectories must share one clock (see the module docstring). Columns: service_journey_id, n_points (observed),
    n_used (within off_route_m of the path), delay_p10/p50/p90 (s, positive = late), tt_sched_s, tt_obs_s,
    tt_ratio (NaN when < 2 used points, scheduled span < min_span_s or observed span <= 0), coverage (share of the scheduled path
    length between the first and last used point), max_offroute_m. Observed journeys with no scheduled match, or whose
    scheduled path is shorter than min_path_m, are listed with NaN statistics (n_used = 0) so nothing silently disappears."""
    s_key, o_key = _keys(sched_traj, match), _keys(observed_traj, match)
    sg = {k: g for k, g in sched_traj.assign(_k=s_key).sort_values("t").groupby("_k", sort=False)}
    rows = []
    for k, og in observed_traj.assign(_k=o_key).sort_values("t").groupby("_k", sort=False):
        row = dict.fromkeys(_COLS, np.nan)
        row.update(service_journey_id=k, n_points=len(og), n_used=0)
        rows.append(row)
        sgp = sg.get(k)
        if sgp is None or len(sgp) < 2:
            continue
        lon0, lat0 = float(sgp["lon"].iloc[0]), float(sgp["lat"].iloc[0])
        sx, sy = _xy(sgp["lon"], sgp["lat"], lon0, lat0)
        seg = np.hypot(np.diff(sx), np.diff(sy))
        s_cum = np.concatenate([[0.0], np.cumsum(seg)])
        if s_cum[-1] < min_path_m:
            continue
        ts = sgp["t"].to_numpy(float)
        s_u, first = np.unique(s_cum, return_index=True)        # first arrival at each distance along the path
        t_at = ts[first]
        ox, oy = _xy(og["lon"], og["lat"], lon0, lat0)
        i, u, dist = _project(ox, oy, sx[:-1], sy[:-1], sx[1:], sy[1:])
        row["max_offroute_m"] = float(dist.max())
        keep = dist <= off_route_m
        row["n_used"] = int(keep.sum())
        if not keep.any():
            continue
        s_obs = (s_cum[:-1][i] + u * seg[i])[keep]
        t_obs = og["t"].to_numpy(float)[keep]
        t_sch = np.interp(s_obs, s_u, t_at)
        delay = t_obs - t_sch
        row["delay_p10"], row["delay_p50"], row["delay_p90"] = (float(x) for x in np.percentile(delay, [10, 50, 90]))
        row["coverage"] = float((s_obs[-1] - s_obs[0]) / s_cum[-1]) if len(s_obs) > 1 else 0.0
        if len(s_obs) >= 2:
            tt_s, tt_o = float(t_sch[-1] - t_sch[0]), float(t_obs[-1] - t_obs[0])
            row["tt_sched_s"], row["tt_obs_s"] = tt_s, tt_o
            if tt_s >= min_span_s and tt_o > 0:
                row["tt_ratio"] = tt_o / tt_s
    return pd.DataFrame(rows, columns=_COLS)


def gate_4c(cmp: pd.DataFrame, max_median_delay_s: float = 180.0, max_tt_ratio: float = 1.25,
            min_journeys: int = 1, min_points: int = 3) -> dict:
    """Gate 4c (opt-in): does the timetable describe the observed vehicles?

    Judged journeys: n_used >= min_points and a finite delay_p50 and tt_ratio. Pass requires >= min_journeys judged journeys,
    median over them of |delay_p50| <= max_median_delay_s AND median tt_ratio <= max_tt_ratio. Returns {"pass": bool,
    "detail": {...}}: detail holds the counts, both medians, the tolerances (flagged assumption: true, see
    GATE_4C_ASSUMPTIONS) and a `reason` when failing. Nothing judged = fail."""
    tol = {"max_median_delay_s": {**GATE_4C_ASSUMPTIONS["max_median_delay_s"], "value": float(max_median_delay_s)},
           "max_tt_ratio": {**GATE_4C_ASSUMPTIONS["max_tt_ratio"], "value": float(max_tt_ratio)}}
    detail = {"n_journeys": int(len(cmp)), "n_judged": 0, "median_abs_delay_s": None, "median_tt_ratio": None,
              "tolerances": tol, "source": "Entur AS realtime vehicle positions vs GTFS timetable"}
    if cmp is None or not len(cmp):
        detail["reason"] = "no journeys to compare"
        return {"pass": False, "detail": detail}
    j = cmp[(cmp["n_used"] >= min_points) & cmp["delay_p50"].notna() & cmp["tt_ratio"].notna()]
    detail["n_judged"] = int(len(j))
    if len(j) < max(1, min_journeys):
        detail["reason"] = f"{len(j)} judged journey(s), need {max(1, min_journeys)}"
        return {"pass": False, "detail": detail}
    d, r = float(j["delay_p50"].abs().median()), float(j["tt_ratio"].median())
    detail.update(median_abs_delay_s=d, median_tt_ratio=r)
    reasons = []
    if d > max_median_delay_s:
        reasons.append(f"median |delay| {d:.0f} s > {max_median_delay_s:.0f} s")
    if r > max_tt_ratio:
        reasons.append(f"median travel-time ratio {r:.2f} > {max_tt_ratio:.2f}")
    if reasons:
        detail["reason"] = "; ".join(reasons)
    return {"pass": not reasons, "detail": detail}
