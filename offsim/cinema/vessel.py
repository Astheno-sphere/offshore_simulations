"""Cosmetic vessel and aircraft motion. Spec: docs/VISUAL_SPEC.md §5.

Rule: display-only. These functions read the validated trajectory and return a DISPLAY copy; they never write back.
`display_offset_check` must stay <= rules.VESSEL['display_offset_max_m'] or the render is refused.
All randomness is seeded and closed-form in t (sum of sines), so a frame renders identically every time.

Offset budget (horizontal metres between validated and display position at the same instant), 25 m in total:
  * corner fillets   <= FILLET_BUDGET_M (12 m): the arc may cut a corner by at most this much
  * speed ramps      <= RAMP_BUDGET_M  (12 m): along-track lag/lead of the time-warp, which counts as offset
  * DP jitter        peak ~3.7 m, only while stationary (state dp/load/unload), faded in/out, so it never adds to
                     the other two in practice; the measured sum is checked and the budgets shrink if it is exceeded.
Trade-offs that follow from the 25 m cap (documented, not hidden):
  * A 400 m quay ramp would need a 400 m along-track lag, so the effective ramp is ~RAMP_BUDGET_M long (a few seconds).
    The requested length is an upper bound, never exceeded.  Departure ramps are shortened the same way.
  * A filleted corner of 2.5 ship lengths (190 m) is only allowed where it stays within the budget (e.g. <= ~24 deg
    deflection); sharper corners get a smaller radius.  The path therefore turns faster than the 20 deg/min the
    HEADING may turn at.  Heading is rate-limited separately and, with the forward/backward pass below, begins turning
    before the corner and finishes after it, so the hull crabs slightly through sharp corners.  Nothing is hidden: the
    heading never snaps, the position never leaves the 25 m corridor.
"""
from __future__ import annotations

import zlib
from functools import lru_cache

import numpy as np
import pandas as pd

from offsim.cinema.rules import HELICOPTER, VESSEL
from offsim.contract import EARTH_R, MOVING, haversine_m

KN = 0.514444
FILLET_BUDGET_M = 12.0
RAMP_BUDGET_M = 12.0
JITTER_STATES = ("dp", "load", "unload")
MANOEUVRE_SPEED_MPS = 2.5      # below this the manoeuvring rate of turn applies
ROT_MANOEUVRE_DEG_MIN = VESSEL["psv_rot_manoeuvre_deg_min"]
_CORNER_MIN_RAD = np.radians(0.5)

# ------------------------------------------------------------------------------------------ helicopter phase table
# One table; the simulation and the display must both read it so validated and display times agree.
# Horizontal speeds in climb/descent are the climb-out / approach speeds; cruise is rules.HELICOPTER['cruise_kn'].
HELI_PHASES = (
    {"name": "climb", "vz_mps": float(np.mean(HELICOPTER["climb_mps"])), "vh_mps": 30.0},
    {"name": "cruise", "vh_mps": HELICOPTER["cruise_kn"] * KN},
    {"name": "descent", "vz_mps": -float(np.mean(HELICOPTER["descent_mps"])), "vh_mps": 30.0,
     "to_height_m": 20.0},                                  # descend to this height above the deck, then flare
    {"name": "flare", "length_m": HELICOPTER["flare_m"], "vh_end_mps": 0.0},   # linear decel over the last 100 m
    {"name": "hover", "duration_s": HELICOPTER["deck_hover_s"]},               # on the deck point
)
HELI_CRUISE_ALT_M = 300.0


# ----------------------------------------------------------------------------------------------------- geometry
def _enu(lon, lat, lon0, lat0):
    c = np.cos(np.radians(lat0))
    return EARTH_R * c * np.radians(np.asarray(lon) - lon0), EARTH_R * np.radians(np.asarray(lat) - lat0)


def _lonlat(x, y, lon0, lat0):
    c = np.cos(np.radians(lat0))
    return lon0 + np.degrees(np.asarray(x) / (EARTH_R * c)), lat0 + np.degrees(np.asarray(y) / EARTH_R)


def _hdg(ux, uy):
    """Heading, degrees clockwise from north, [0, 360), from an east/north direction."""
    return np.degrees(np.arctan2(ux, uy)) % 360.0


def _seed_for(seed, aid):
    return (int(seed) * 1_000_003 + zlib.crc32(str(aid).encode())) & 0x7FFFFFFF


# ----------------------------------------------------------------------------------------------- seeded sines
@lru_cache(maxsize=256)
def _jitter_params(seed: int):
    rng = np.random.default_rng([int(seed), 17])
    lo, hi = VESSEL["dp_periods_s"]
    per = np.exp(rng.uniform(np.log(lo), np.log(hi), (3, 3)))     # 3 channels x 3 sines, periods 7-40 s
    # one sine in the 7-12 s band so the motion never looks like drift only
    per[:, 0] = rng.uniform(lo, 12.0, 3)
    ph = rng.uniform(0, 2 * np.pi, (3, 3))
    return per, ph


def dp_jitter(seed: int, t: float, rms_m: float = 1.5, heading_rms_deg: float = 0.5) -> tuple[float, float, float]:
    """Station-keeping while state == 'dp' or alongside: (dx_m, dy_m, dheading_deg), 3 sines, periods 7–40 s.
    dx east, dy north (metres). `rms_m` is the radial (2-D) RMS, so each axis has rms_m/sqrt(2); heading RMS is
    `heading_rms_deg`. Three equal-amplitude sines: RMS = a*sqrt(3/2). Closed form in t; `t` may be an array."""
    per, ph = _jitter_params(int(seed))
    tt = np.asarray(t, dtype=float)
    scale = np.array([rms_m / np.sqrt(2), rms_m / np.sqrt(2), heading_rms_deg]) / np.sqrt(1.5)
    out = [scale[c] * sum(np.sin(2 * np.pi * tt / per[c, k] + ph[c, k]) for k in range(3)) for c in range(3)]
    if tt.ndim == 0:
        return float(out[0]), float(out[1]), float(out[2])
    return out[0], out[1], out[2]


@lru_cache(maxsize=256)
def _bob_params(seed: int):
    rng = np.random.default_rng([int(seed), 29])
    ph = rng.uniform(0, 2 * np.pi, (3, 2))
    det = 1.0 + rng.uniform(-0.04, 0.04, (3, 2))                 # incommensurate periods
    return ph, det


def bob(hs_m: float, tp_s: float, t: float, seed: int) -> tuple[float, float, float]:
    """(heave_m, roll_deg, pitch_deg) from local Hs/Tp: heave≈0.25·Hs, roll=min(6, 1.2·Hs), pitch=min(3, 0.6·Hs);
    two incommensurate periods near Tp and 1.3·Tp. Feeds ScenegraphLayer getOrientation/getTranslation.
    Amplitudes are the peak values (weights 0.65/0.35 sum to 1). Closed form in t; `t` may be an array."""
    ph, det = _bob_params(int(seed))
    tp = max(float(tp_s), 1.0)
    tt = np.asarray(t, dtype=float)
    amp = (VESSEL["heave_per_hs"] * hs_m,
           min(VESSEL["roll_max_deg"], VESSEL["roll_per_hs_deg"] * hs_m),
           min(VESSEL["pitch_max_deg"], VESSEL["pitch_per_hs_deg"] * hs_m))
    # heave and pitch lead on the period near Tp, roll on 1.3 Tp (beam sea rolls slower)
    w = ((0.65, 0.35), (0.35, 0.65), (0.65, 0.35))
    out = []
    for c in range(3):
        p1, p2 = tp * det[c, 0], 1.3 * tp * det[c, 1]
        out.append(amp[c] * (w[c][0] * np.sin(2 * np.pi * tt / p1 + ph[c, 0]) + w[c][1] * np.sin(2 * np.pi * tt / p2 + ph[c, 1])))
    if tt.ndim == 0:
        return float(out[0]), float(out[1]), float(out[2])
    return out[0], out[1], out[2]


# ------------------------------------------------------------------------------------------------ wake (Kelvin)
WAKE_REF_MPS = 7.0
WAKE_ALPHA_MAX = 0.6


def wake(path_lonlat, t: float, speed_mps: float, length_m: float, n_seg: int = 12, wake_len_lengths: float = 10.0):
    """Kelvin V (half-angle 19.47°) as two fading paths + centre trail; length 8–12 ship lengths; alpha ∝ speed.
    `path_lonlat`: the display track up to now, oldest first, last point = the vessel at `t` (the caller samples it
    as a pure function of t, so the wake is too; `t` is part of the contract only). Returns a list of segments
    {"kind": "arm_l"|"arm_r"|"trail", "path": [[lon,lat],[lon,lat]], "alpha": 0..1}; alpha = WAKE_ALPHA_MAX *
    min(1, speed/WAKE_REF_MPS) fading linearly to 0 at the far end; the centre trail is half as strong."""
    pts = np.asarray(path_lonlat, dtype=float)
    a0 = WAKE_ALPHA_MAX * min(1.0, max(0.0, float(speed_mps)) / WAKE_REF_MPS)
    if len(pts) < 2 or a0 < 0.01:
        return []
    lon0, lat0 = pts[-1, 0], pts[-1, 1]
    x, y = _enu(pts[:, 0], pts[:, 1], lon0, lat0)
    seg = np.hypot(np.diff(x), np.diff(y))
    keep = np.r_[True, seg > 1e-6]                          # drop repeated points
    x, y = x[keep], y[keep]
    seg = np.hypot(np.diff(x), np.diff(y))
    if len(seg) == 0:
        return []
    back = np.r_[0.0, np.cumsum(seg[::-1])]                 # distance back from the vessel at each point, newest first
    xr, yr = x[::-1], y[::-1]
    W = float(np.clip(wake_len_lengths, *VESSEL["wake_len_ship_lengths"])) * float(length_m)
    W = min(W, back[-1])
    ds = np.linspace(0.0, W, n_seg + 1)
    px, py = np.interp(ds, back, xr), np.interp(ds, back, yr)
    # direction of travel at each wake point: from the older point towards the newer one
    k = np.clip(np.searchsorted(back, ds, side="right") - 1, 0, len(seg) - 1)
    ux, uy = -(xr[k + 1] - xr[k]), -(yr[k + 1] - yr[k])
    nrm = np.hypot(ux, uy)
    ux, uy = ux / nrm, uy / nrm
    tan = np.tan(np.radians(VESSEL["kelvin_half_angle_deg"]))
    lat_off = ds * tan
    arms = {"arm_l": (px - uy * lat_off, py + ux * lat_off), "arm_r": (px + uy * lat_off, py - ux * lat_off), "trail": (px, py)}
    out = []
    for kind, (ax, ay) in arms.items():
        lo, la = _lonlat(ax, ay, lon0, lat0)
        for j in range(n_seg):
            fade = max(0.0, 1.0 - 0.5 * (ds[j] + ds[j + 1]) / max(W, 1e-9))
            out.append({"kind": kind, "path": [[float(lo[j]), float(la[j])], [float(lo[j + 1]), float(la[j + 1])]],
                        "alpha": float(a0 * fade * (0.5 if kind == "trail" else 1.0))})
    return out


# -------------------------------------------------------------------------------------------- track construction
def _prep(g):
    g = g.sort_values("t", kind="stable")
    t = g["t"].to_numpy(float)
    g = g[np.r_[t[1:] > t[:-1], True]]                      # equal times: the last row (state after the event) wins
    t = g["t"].to_numpy(float)
    lon0, lat0 = float(g["lon"].iloc[0]), float(g["lat"].iloc[0])
    x, y = _enu(g["lon"].to_numpy(float), g["lat"].to_numpy(float), lon0, lat0)
    alt = g["alt_m"].to_numpy(float) if "alt_m" in g else np.zeros(len(g))
    load = g["load"].to_numpy(float) if "load" in g else None
    return t, x, y, alt, list(g["state"]), load, lon0, lat0


def _runs(x, y):
    """Maximal stretches of consecutive moving legs as (first_row, last_row)."""
    mov = np.hypot(np.diff(x), np.diff(y)) > 0.05
    runs, i, n = [], 0, len(x)
    while i < n - 1:
        if mov[i]:
            j = i
            while j < n - 1 and mov[j]:
                j += 1
            runs.append((i, j))
            i = j
        else:
            i += 1
    return runs


class _Run:
    """One moving stretch: validated polyline, arc length, and (optionally) its filleted corners."""

    def __init__(self, t, x, y, i0, i1, fillet, radius_m, b_f):
        self.i0, self.i1 = i0, i1
        self.rt, self.px, self.py = t[i0:i1 + 1], x[i0:i1 + 1], y[i0:i1 + 1]
        dx, dy = np.diff(self.px), np.diff(self.py)
        self.len = np.hypot(dx, dy)
        self.S = np.r_[0.0, np.cumsum(self.len)]
        self.L = float(self.S[-1])
        self.ux, self.uy = dx / self.len, dy / self.len
        self.corners = []
        if fillet:
            for k in range(1, len(self.px) - 1):
                self._corner(k, radius_m, b_f)

    def _corner(self, k, radius_m, b_f):
        ax, ay, bx, by = self.ux[k - 1], self.uy[k - 1], self.ux[k], self.uy[k]
        cross, dot = ax * by - ay * bx, ax * bx + ay * by
        d = float(np.arctan2(abs(cross), dot))
        if d < _CORNER_MIN_RAD:
            return
        half = d / 2
        r = radius_m
        if np.cos(half) > 1e-6:
            r = min(r, b_f / (1 / np.cos(half) - 1))      # mid-arc distance to the vertex = r(sec(d/2)-1) <= b_f
        tmax = 0.5 * min(self.len[k - 1], self.len[k])
        tl = r * np.tan(half)
        if tl > tmax:
            r, tl = tmax / np.tan(half), tmax
        if tl < 0.2 or r < 0.2:
            return
        sg = 1.0 if cross >= 0 else -1.0
        p1x, p1y = self.px[k] - tl * ax, self.py[k] - tl * ay
        cx, cy = p1x + r * sg * -ay, p1y + r * sg * ax
        self.corners.append(dict(s0=self.S[k] - tl, s1=self.S[k] + tl, cx=cx, cy=cy, r=r, a1=float(np.arctan2(p1y - cy, p1x - cx)),
                                 sg=sg, d=d, ax=ax, ay=ay))

    def at(self, s):
        """Display position and unit tangent at validated arc length s (array)."""
        s = np.clip(s, 0.0, self.L)
        x, y = np.interp(s, self.S, self.px), np.interp(s, self.S, self.py)
        k = np.clip(np.searchsorted(self.S, s, side="right") - 1, 0, len(self.len) - 1)
        ux, uy = self.ux[k].copy(), self.uy[k].copy()
        for c in self.corners:
            m = (s >= c["s0"]) & (s <= c["s1"])
            if not m.any():
                continue
            q = (s[m] - c["s0"]) / (c["s1"] - c["s0"])
            ang = c["a1"] + c["sg"] * c["d"] * q
            x[m], y[m] = c["cx"] + c["r"] * np.cos(ang), c["cy"] + c["r"] * np.sin(ang)
            rot = c["sg"] * c["d"] * q
            ux[m] = c["ax"] * np.cos(rot) - c["ay"] * np.sin(rot)
            uy[m] = c["ax"] * np.sin(rot) + c["ay"] * np.cos(rot)
        return x, y, ux, uy


def _warp(tt, ta, tb, td, tr):
    """Display time-warp tau(t): speed ratio w ramps 0->wc over td, holds wc, ramps wc->0 over tr; tau(ta)=ta, tau(tb)=tb."""
    T = tb - ta
    wc = T / (T - 0.5 * (td + tr))
    u = tt - ta
    td, tr = max(td, 1e-9), max(tr, 1e-9)
    tau = np.where(u < td, wc * u * u / (2 * td), np.where(u <= T - tr, wc * (td / 2 + u - td), T - wc * (T - u) ** 2 / (2 * tr)))
    return ta + np.clip(tau, 0.0, T)


def _ramps(run, quay_ramp_m, depart_ramp_s, b_r):
    """Ramp durations (arrival, departure) in s, shortened so the along-track shift stays <= b_r metres."""
    T = float(run.rt[-1] - run.rt[0])
    vbar = run.L / T
    tr, td = 2.0 * quay_ramp_m / max(vbar, 1e-6), float(depart_ramp_s)
    if tr + td > 0.5 * T:
        f = 0.5 * T / (tr + td)
        tr, td = tr * f, td * f
    grid = np.linspace(run.rt[0], run.rt[-1], 800)
    for _ in range(8):
        shift = np.abs(np.interp(_warp(grid, run.rt[0], run.rt[-1], td, tr), run.rt, run.S) - np.interp(grid, run.rt, run.S)).max()
        if shift <= b_r:
            break
        f = 0.95 * b_r / shift
        tr, td = tr * f, td * f
    return tr, td


def _track(g, *, fillet, warp, radius_lengths, length_m, quay_ramp_m, depart_ramp_s, b_f, b_r, dt_s):
    """Display positions on a time grid + the target (tangent) heading. All stages share this one routine."""
    t, x, y, alt, states, load, lon0, lat0 = _prep(g)
    times = t
    if dt_s:
        grid = np.arange(t[0], t[-1], dt_s)
        if len(grid):
            i = np.searchsorted(t, grid)
            near = np.minimum(np.abs(grid - t[np.clip(i, 0, len(t) - 1)]), np.abs(grid - t[np.clip(i - 1, 0, len(t) - 1)]))
            times = np.sort(np.r_[t, grid[near > 1e-6]])
    ri = np.clip(np.searchsorted(t, times, side="right") - 1, 0, len(t) - 1)
    X, Y = x[ri].copy(), y[ri].copy()
    tgt = np.full(len(times), np.nan)
    info = []
    radius_m = radius_lengths * length_m
    for (i0, i1) in _runs(x, y):
        run = _Run(t, x, y, i0, i1, fillet, radius_m, b_f)
        sel = (times >= run.rt[0] - 1e-9) & (times <= run.rt[-1] + 1e-9)
        tt = times[sel]
        if warp:
            tr, td = _ramps(run, quay_ramp_m, depart_ramp_s, b_r)
            tt = _warp(tt, run.rt[0], run.rt[-1], td, tr)
        s = np.interp(tt, run.rt, run.S)
        X[sel], Y[sel], ux, uy = run.at(s)
        tgt[sel] = _hdg(ux, uy)
        info.append((run.rt[0], run.rt[-1], float(tgt[sel][0]), float(tgt[sel][-1])))
    # stationary stretches: face the previous heading for the first half, the next departure heading for the second half
    mov = ~np.isnan(tgt)
    if info:
        for k, tm in enumerate(times):
            if mov[k]:
                continue
            prev = [r for r in info if r[1] <= tm]
            nxt = [r for r in info if r[0] >= tm]
            if prev and nxt:
                mid = 0.5 * (prev[-1][1] + nxt[0][0])
                tgt[k] = prev[-1][3] if tm < mid else nxt[0][2]
            else:
                tgt[k] = prev[-1][3] if prev else nxt[0][2]
    else:
        tgt[:] = 0.0
    return dict(t=times, x=X, y=Y, alt=np.interp(times, t, alt), ri=ri, states=[states[i] for i in ri],
                load=None if load is None else load[ri], tgt=tgt, lon0=lon0, lat0=lat0)


def _limit_heading(t, x, y, tgt_deg, rot_service_deg_min, rot_manoeuvre_deg_min):
    """Rate-limited display heading. Forward pass lags the target, backward pass leads it; the mean is centred on the
    change, starts turning before a corner and ends after it, and each step is bounded by the larger limit of the two
    passes' per-step limits, so the rate never exceeds the limit. Slow intervals (< MANOEUVRE_SPEED_MPS) use the
    manoeuvring rate. Returns degrees in [0, 360)."""
    n = len(t)
    h = np.degrees(np.unwrap(np.radians(tgt_deg)))
    if n < 2:
        return h % 360.0
    dt = np.diff(t)
    sp = np.hypot(np.diff(x), np.diff(y)) / np.maximum(dt, 1e-9)
    lim = np.where(sp < MANOEUVRE_SPEED_MPS, rot_manoeuvre_deg_min, rot_service_deg_min) / 60.0 * dt   # deg per interval
    f, b = h.copy(), h.copy()
    for i in range(1, n):
        f[i] = f[i - 1] + np.clip(h[i] - f[i - 1], -lim[i - 1], lim[i - 1])
    for i in range(n - 2, -1, -1):
        b[i] = b[i + 1] + np.clip(h[i] - b[i + 1], -lim[i], lim[i])
    return (0.5 * (f + b)) % 360.0


def _stage(traj, *, fillet, warp, rot_max_deg_min, rot_manoeuvre_deg_min, radius_lengths, length_m, quay_ramp_m, depart_ramp_s,
           b_f, b_r, dt_s):
    out = []
    for aid, g in traj.groupby("agent_id", sort=False):
        tr = _track(g, fillet=fillet, warp=warp, radius_lengths=radius_lengths, length_m=length_m, quay_ramp_m=quay_ramp_m,
                    depart_ramp_s=depart_ramp_s, b_f=b_f, b_r=b_r, dt_s=dt_s)
        hd = _limit_heading(tr["t"], tr["x"], tr["y"], tr["tgt"], rot_max_deg_min, rot_manoeuvre_deg_min)
        lon, lat = _lonlat(tr["x"], tr["y"], tr["lon0"], tr["lat0"])
        df = pd.DataFrame({"agent_id": aid, "t": tr["t"], "lon": lon, "lat": lat, "alt_m": tr["alt"], "state": tr["states"]})
        if tr["load"] is not None:
            df["load"] = tr["load"]
        df["heading"] = hd
        out.append(df)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def heading_smooth(traj, rot_max_deg_min: float = 20.0, radius_lengths: float = 2.5, length_m: float = 76.0,
                   rot_manoeuvre_deg_min: float | None = None, dt_s: float = 2.0, offset_budget_m: float = FILLET_BUDGET_M):
    """Per-row display heading: rate-limited turns and fillet (circular arc) corners at waypoints instead of snaps.
    Returns a DISPLAY DataFrame (agent_id, t, lon, lat, alt_m, state[, load], heading) sampled every `dt_s` and at every
    validated row time, so arrival/departure times at stops are unchanged and stop positions are exact. Corners inside a
    moving stretch get an arc of radius radius_lengths*length_m, reduced where needed so the arc stays <= offset_budget_m
    from the polyline (and within half the adjacent segments); the vessel keeps its validated schedule along the
    polyline, mapped linearly onto the arc. Heading is the arc tangent rate-limited to rot_max_deg_min (and
    rot_manoeuvre_deg_min below 2.5 m/s, default the same); at a stop it turns towards the next departure during the
    dwell. The input is not modified."""
    return _stage(traj, fillet=True, warp=False, rot_max_deg_min=rot_max_deg_min,
                  rot_manoeuvre_deg_min=rot_max_deg_min if rot_manoeuvre_deg_min is None else rot_manoeuvre_deg_min,
                  radius_lengths=radius_lengths, length_m=length_m, quay_ramp_m=0.0, depart_ramp_s=0.0,
                  b_f=offset_budget_m, b_r=0.0, dt_s=dt_s)


def speed_profile(traj, quay_ramp_m: float = 400.0, depart_ramp_s: float = 20.0, offset_budget_m: float = RAMP_BUDGET_M,
                  dt_s: float = 2.0):
    """Display time-warp so vessels decelerate into quays and accelerate out; arrival/departure times unchanged.
    Per moving stretch the display speed ratio ramps linearly 0 -> w_c over the departure ramp, holds w_c (slightly > 1
    to repay the lost distance) and ramps w_c -> 0 over the arrival ramp (constant deceleration over ~quay_ramp_m).
    The along-track shift versus the validated track counts as display offset, so the ramps are shortened until it is
    <= offset_budget_m (default 12 m): quay_ramp_m and depart_ramp_s are upper bounds, in practice the ramp is a few
    seconds. Returns a DISPLAY DataFrame (agent_id, t, lon, lat, alt_m, state[, load]) at row times plus every dt_s."""
    df = _stage(traj, fillet=False, warp=True, rot_max_deg_min=1e9, rot_manoeuvre_deg_min=1e9, radius_lengths=0.0, length_m=0.0,
                quay_ramp_m=quay_ramp_m, depart_ramp_s=depart_ramp_s, b_f=0.0, b_r=offset_budget_m, dt_s=dt_s)
    return df.drop(columns="heading")


# ------------------------------------------------------------------------------------------------ the full copy
def _to_arrays(display):
    """{agent: (t, lon, lat)} from a display_agents dict or a DataFrame."""
    if isinstance(display, pd.DataFrame):
        return {a: (g["t"].to_numpy(float), g["lon"].to_numpy(float), g["lat"].to_numpy(float)) for a, g in display.groupby("agent_id", sort=False)}
    return {a: (np.asarray(v["ts"], float), np.asarray([p[0] for p in v["path"]], float), np.asarray([p[1] for p in v["path"]], float))
            for a, v in display.items() if isinstance(v, dict) and "path" in v}


def display_offset_check(validated, display) -> float:
    """INSPECTOR. Max distance (m) between validated and display positions over all frames.
    `validated`: trajectory DataFrame; `display`: the dict from display_agents or a DataFrame with agent_id,t,lon,lat.
    Both tracks are linearly interpolated exactly as the renderer does; the difference of two piecewise-linear tracks
    is piecewise linear, so its maximum lies on the union of both time grids, which is what is evaluated."""
    worst = 0.0
    disp = _to_arrays(display)
    for aid, g in validated.groupby("agent_id", sort=False):
        if aid not in disp:
            continue
        g = g.sort_values("t", kind="stable")
        tv, lv, av = g["t"].to_numpy(float), g["lon"].to_numpy(float), g["lat"].to_numpy(float)
        keep = np.r_[tv[1:] > tv[:-1], True]
        tv, lv, av = tv[keep], lv[keep], av[keep]
        td, ld, ad = disp[aid]
        lo, hi = max(tv[0], td[0]), min(tv[-1], td[-1])
        tt = np.union1d(tv, td)
        tt = tt[(tt >= lo) & (tt <= hi)]
        if len(tt) == 0:
            continue
        d = haversine_m(np.interp(tt, tv, lv), np.interp(tt, tv, av), np.interp(tt, td, ld), np.interp(tt, td, ad))
        worst = max(worst, float(np.max(d)))
    return worst


def _default_hs(lon, lat, t):
    return 1.0, 7.0


def _jitter_weight(t, states):
    """0..1 envelope: 1 inside dp/load/unload stretches, smoothstep over 6 s at both ends (and 0 outside)."""
    on = np.array([s in JITTER_STATES for s in states])
    w = np.zeros(len(t))
    i = 0
    while i < len(t):
        if on[i]:
            j = i
            while j + 1 < len(t) and on[j + 1]:
                j += 1
            # the stretch lasts from t[i] until the first row that is not jitter-state (t[j+1]) or the end
            ta, tb = t[i], t[j + 1] if j + 1 < len(t) else t[j]
            ramp = min(6.0, 0.5 * (tb - ta))
            if ramp > 0:
                u = np.clip(np.minimum(t[i:j + 1] - ta, tb - t[i:j + 1]) / ramp, 0.0, 1.0)
                w[i:j + 1] = u * u * (3 - 2 * u)
            i = j + 1
        else:
            i += 1
    return w


def _display_once(traj, spec, seed, hs_at, b_f, b_r, dt_s, rot, rot_man, radius_lengths, quay_ramp_m, depart_ramp_s):
    out = {}
    for aid, g in traj.groupby("agent_id", sort=False):
        row = spec.loc[aid] if aid in spec.index else None
        domain = str(row["domain"]) if row is not None and "domain" in spec.columns and pd.notna(row["domain"]) else "sea"
        length_m = float(row["length_m"]) if row is not None and "length_m" in spec.columns and pd.notna(row["length_m"]) else 76.0
        sea = domain == "sea"
        tr = _track(g, fillet=sea, warp=sea, radius_lengths=radius_lengths, length_m=length_m, quay_ramp_m=quay_ramp_m,
                    depart_ramp_s=depart_ramp_s, b_f=b_f, b_r=b_r, dt_s=dt_s if sea else None)
        t = tr["t"]
        hd = _limit_heading(t, tr["x"], tr["y"], tr["tgt"], rot if sea else 1e5, rot_man if sea else 1e5)
        x, y = tr["x"].copy(), tr["y"].copy()
        roll = np.zeros(len(t))
        pitch = np.zeros(len(t))
        heave = np.zeros(len(t))
        if sea:
            asd = _seed_for(seed, aid)
            w = _jitter_weight(t, tr["states"])
            if w.any():
                dx, dy, dh = dp_jitter(asd, t, VESSEL["dp_rms_m"], VESSEL["dp_heading_rms_deg"])
                x, y, hd = x + w * dx, y + w * dy, (hd + w * dh) % 360.0
            lon0, lat0 = tr["lon0"], tr["lat0"]
            lo, la = _lonlat(x, y, lon0, lat0)
            for k in range(len(t)):
                hs = hs_at(float(lo[k]), float(la[k]), float(t[k]))
                hs, tp = (hs if np.ndim(hs) else (hs, 7.0))
                heave[k], roll[k], pitch[k] = bob(float(hs), float(tp), float(t[k]), asd)
        lon, lat = _lonlat(x, y, tr["lon0"], tr["lat0"])
        out[str(aid)] = {"path": [[float(a), float(b), float(c)] for a, b, c in zip(lon, lat, tr["alt"])],
                         "ts": [float(v) for v in t], "states": list(tr["states"]),
                         "heading": [float(v) for v in hd], "roll": [float(v) for v in roll],
                         "pitch": [float(v) for v in pitch], "heave": [float(v) for v in heave]}
    return out


def display_agents(traj, agents, seed: int = 0, hs_at=None, *, dt_s: float = 2.0, rot_max_deg_min: float = 20.0,
                   rot_manoeuvre_deg_min: float = ROT_MANOEUVRE_DEG_MIN, radius_lengths: float = 2.5,
                   quay_ramp_m: float = 400.0, depart_ramp_s: float = 20.0) -> dict:
    """The renderer's DISPLAY copy of a validated trajectory (the input is never modified).
    Returns {agent_id: {"path": [[lon,lat,z]], "ts": [s], "states": [str], "heading": [deg cw from north, 0..360],
    "roll": [deg], "pitch": [deg], "heave": [m]}, ..., "max_offset_m": float}.
    `path/ts/states` have the same meaning as in scene.build_scene (so app.js can interpolate them) but are sampled at
    every validated row time plus every `dt_s` (~2 s), alongside and along arcs.
    Sea agents get corner fillets + speed ramps (arrival times unchanged), DP jitter while state in dp/load/unload
    (faded in/out over 6 s) and bob from `hs_at(lon, lat, t)` -> Hs or (Hs, Tp) (default Hs 1.0 m, Tp 7 s). Air and land
    agents keep their validated positions (heading and nothing else). `max_offset_m` is display_offset_check over
    everything; if it exceeds rules.VESSEL['display_offset_max_m'] the fillet/ramp budgets are shrunk and the copy
    rebuilt, and if that cannot satisfy the limit a ValueError refuses the render. Seeded: same seed, identical copy."""
    hs_at = hs_at or _default_hs
    spec = agents.set_index("agent_id")
    limit = VESSEL["display_offset_max_m"]
    b_f, b_r = FILLET_BUDGET_M, RAMP_BUDGET_M
    for _ in range(8):
        out = _display_once(traj, spec, seed, hs_at, b_f, b_r, dt_s, rot_max_deg_min, rot_manoeuvre_deg_min, radius_lengths,
                            quay_ramp_m, depart_ramp_s)
        off = display_offset_check(traj, out)
        if off <= limit:
            out["max_offset_m"] = off
            return out
        b_f, b_r = 0.8 * b_f, 0.8 * b_r
    raise ValueError(f"display offset {off:.1f} m exceeds the {limit:.0f} m limit; refusing to build the display copy")


# ----------------------------------------------------------------------------------------------------- helicopter
def _heli_route(route):
    if isinstance(route, dict):
        r = dict(route)
        pts = r["path"]
    else:
        r, pts = {}, route
    pts = np.asarray(pts, dtype=float)
    lon0, lat0 = pts[0, 0], pts[0, 1]
    x, y = _enu(pts[:, 0], pts[:, 1], lon0, lat0)
    seg = np.hypot(np.diff(x), np.diff(y))
    return dict(x=x, y=y, S=np.r_[0.0, np.cumsum(seg)], lon0=lon0, lat0=lat0, t0=float(r.get("t0", 0.0)),
                deck_alt_m=float(r.get("deck_alt_m", 0.0)), cruise_alt_m=float(r.get("cruise_alt_m", HELI_CRUISE_ALT_M)))


def _heli_plan(route):
    """Plan -> (phases, climb height dh, route). Phases [(name, t_start, t_end, dist_start_m, dist_end_m)], seconds from route['t0'] (default 0).
    `route`: [(lon, lat), ...] or {"path": [...], "t0", "deck_alt_m", "cruise_alt_m"}. Built from HELI_PHASES, the same table the
    simulation uses. A route too short for the cruise altitude gets a lower cruise altitude (never below the flare height)."""
    r = _heli_route(route)
    P = {p["name"]: p for p in HELI_PHASES}
    D = float(r["S"][-1])
    vc, vd = P["climb"]["vh_mps"] / P["climb"]["vz_mps"], P["descent"]["vh_mps"] / -P["descent"]["vz_mps"]
    flare_h, flare_len = P["descent"]["to_height_m"], P["flare"]["length_m"]
    dh = max(min(r["cruise_alt_m"] - r["deck_alt_m"], (D - flare_len + vd * flare_h) / (vc + vd)), flare_h + 0.1)
    d_climb, d_desc = vc * dh, vd * (dh - flare_h)
    d_cruise = D - d_climb - d_desc - flare_len
    if d_cruise < -1e-6:
        raise ValueError(f"route of {D:.0f} m is too short for the helicopter phase table")
    d_cruise = max(d_cruise, 0.0)
    t_climb = dh / P["climb"]["vz_mps"]
    t_cruise = d_cruise / P["cruise"]["vh_mps"]
    t_desc = (dh - flare_h) / -P["descent"]["vz_mps"]
    t_flare = 2.0 * flare_len / P["descent"]["vh_mps"]
    t_hover = P["hover"]["duration_s"]
    edges = np.cumsum([0.0, t_climb, t_cruise, t_desc, t_flare, t_hover]) + r["t0"]
    dists = np.cumsum([0.0, d_climb, d_cruise, d_desc, flare_len, 0.0])
    names = ["climb", "cruise", "descent", "flare", "hover"]
    return [(n, float(edges[i]), float(edges[i + 1]), float(dists[i]), float(dists[i + 1])) for i, n in enumerate(names)], dh, r


def heli_timeline(route):
    """Phase boundaries [(name, t_start, t_end, dist_start_m, dist_end_m)] for the simulation to share (see _heli_plan)."""
    return _heli_plan(route)[0]


def heli_profile(route, t: float):
    """(lon, lat, alt_m, heading) through climb 8–10 m/s, cruise 140 kn, descent 3–5 m/s, 30 s deck hover, 100 m flare.
    The SAME phase table must drive the simulation so display and validated times agree: see HELI_PHASES and heli_timeline.
    Climb and descent are monotonic in altitude; the flare (last 100 m) decelerates linearly to the deck point while
    dropping from the flare height to the deck; the hover holds position and deck altitude for 30 s. Before the first
    phase the aircraft waits at the start, after the hover it stays on the deck. Heading = bearing of the current leg."""
    tl, dh, r = _heli_plan(route)
    P = {p["name"]: p for p in HELI_PHASES}
    alt0, flare_h = r["deck_alt_m"], P["descent"]["to_height_m"]
    t = float(t)
    name, ta, tb, da, db = next((ph for ph in tl if t < ph[2]), tl[-1])
    u = float(np.clip(t - ta, 0.0, tb - ta))
    if t <= tl[0][1]:
        name, u, ta, tb, da, db = "climb", 0.0, tl[0][1], tl[0][2], tl[0][3], tl[0][4]
    if name == "climb":
        s, alt = da + P["climb"]["vh_mps"] * u, alt0 + P["climb"]["vz_mps"] * u
    elif name == "cruise":
        s, alt = da + P["cruise"]["vh_mps"] * u, alt0 + dh
    elif name == "descent":
        s, alt = da + P["descent"]["vh_mps"] * u, alt0 + dh + P["descent"]["vz_mps"] * u
    elif name == "flare":
        v0, T = P["descent"]["vh_mps"], tb - ta
        s, alt = da + v0 * u - v0 * u * u / (2 * T), alt0 + flare_h * (1 - u / T)
    else:
        s, alt = db, alt0
    S = r["S"]
    x, y = np.interp(s, S, r["x"]), np.interp(s, S, r["y"])
    k = int(np.clip(np.searchsorted(S, s, side="right") - 1, 0, len(S) - 2))
    while k > 0 and S[k + 1] - S[k] < 1e-9:
        k -= 1
    hd = float(_hdg(r["x"][k + 1] - r["x"][k], r["y"][k + 1] - r["y"][k]))
    lon, lat = _lonlat(x, y, r["lon0"], r["lat0"])
    return float(lon), float(lat), float(alt), hd
