"""Camera. Spec: docs/VISUAL_SPEC.md §4; numbers: offsim/cinema/rules.py (CAMERA).

Python is the brain: the camera is computed here for every output frame (`camera_track`) and handed to the renderer
as a per-frame track (`render_deck/src/layers/camera.js: cameraAtFrame`). `shot_plan` inspects exactly those frames.
Every function is a pure f(t[, seed]); no transitions, timers or per-frame integrators.

ViewState = {"longitude", "latitude", "zoom", "pitch", "bearing"}.
Key       = {"t": seconds, **ViewState} (camera_spline) ; storyboard keys use {"at": 0..1, fit | lon/lat/zoom, ...}.
Web Mercator uses 512 px tiles (deck.gl convention): world size in pixels = 512 * 2**zoom.
Bearing is kept continuous (unwrapped) along a track, so rates are plain differences.
"""
from __future__ import annotations

import math

import numpy as np

from .rules import CAMERA

DIMS = ("longitude", "latitude", "zoom", "pitch", "bearing")
TILE = 512.0
MAX_ZOOM = 24.0


# ---------------------------------------------------------------- helpers
def ease(name: str, u: float) -> float:
    """u∈[0,1] → [0,1]. Names: linear, cubic_in_out, quint_in_out, smoothstep. Clamp u."""
    u = 0.0 if u <= 0.0 else 1.0 if u >= 1.0 else float(u)
    if name == "linear":
        return u
    if name == "smoothstep":
        return u * u * (3.0 - 2.0 * u)
    if name == "cubic_in_out":
        return 4.0 * u ** 3 if u < 0.5 else 1.0 - (-2.0 * u + 2.0) ** 3 / 2.0
    if name == "quint_in_out":
        return 16.0 * u ** 5 if u < 0.5 else 1.0 - (-2.0 * u + 2.0) ** 5 / 2.0
    raise ValueError(f"unknown ease {name!r}")


def _world(lon: float, lat: float) -> tuple[float, float]:
    """lon/lat → Web Mercator world pixels at zoom 0 (512 px world, y down)."""
    lat = max(-85.05112878, min(85.05112878, lat))
    x = (lon + 180.0) / 360.0 * TILE
    y = (1.0 - math.log(math.tan(math.pi / 4.0 + math.radians(lat) / 2.0)) / math.pi) / 2.0 * TILE
    return x, y


def _lonlat(x: float, y: float) -> tuple[float, float]:
    lon = x / TILE * 360.0 - 180.0
    lat = math.degrees(2.0 * math.atan(math.exp((1.0 - 2.0 * y / TILE) * math.pi)) - math.pi / 2.0)
    return lon, lat


def _vec(v: dict) -> np.ndarray:
    miss = [d for d in ("longitude", "latitude", "zoom") if d not in v]
    if miss:
        raise ValueError(f"view/key lacks {miss} (resolve 'fit' with fit_view first)")
    return np.array([float(v["longitude"]), float(v["latitude"]), float(v["zoom"]),
                     float(v.get("pitch", 0.0)), float(v.get("bearing", 0.0))])


def _view(a) -> dict:
    return {d: float(x) for d, x in zip(DIMS, a)}


def _shortest(b0: float, b1: float) -> float:
    """b1 shifted by a multiple of 360 so it lies within 180 of b0."""
    return b1 - 360.0 * round((b1 - b0) / 360.0)


def fit_view(bbox, viewport, pitch: float = 0.0, bearing: float = 0.0, padding: float = 0.06) -> dict:
    """View state that fits bbox [[w, s], [e, n]] in `viewport` (W, H) px. Same asymmetric padding as app.js view():
    top 0.22+p, bottom 0.12+p (fractions of H), left p, right 0.12+p (fractions of W), so the map clears the title
    block and the legend. Equivalent to WebMercatorViewport.fitBounds (pitch/bearing are passed through, not fitted)."""
    (w, s), (e, n) = bbox
    W, H = float(viewport[0]), float(viewport[1])
    p = padding
    top, bottom, left, right = round(H * (0.22 + p)), round(H * (0.12 + p)), round(W * p), round(W * (0.12 + p))  # app.js Math.round
    x0, y1 = _world(w, s)
    x1, y0 = _world(e, n)
    ex, ey = max(x1 - x0, 1e-12), max(y1 - y0, 1e-12)
    avail_w, avail_h = W - left - right, H - top - bottom
    if avail_w <= 0 or avail_h <= 0:
        raise ValueError("padding leaves no room")
    sx, sy = avail_w / ex, avail_h / ey  # px per world unit, per axis
    zoom = min(MAX_ZOOM, math.log2(min(sx, sy)))
    # identical to @math.gl/web-mercator fitBounds: the centre shift uses the per-axis scale (so the non-limiting axis is
    # shifted slightly less than the exact amount; it has slack, so the bbox still sits inside the padded rectangle)
    cx = (x0 + x1) / 2.0 + (right - left) / 2.0 / sx
    cy = (y0 + y1) / 2.0 - (top - bottom) / 2.0 / sy  # deck world y points up, ours down
    lon, lat = _lonlat(cx, cy)
    return {"longitude": lon, "latitude": lat, "zoom": zoom, "pitch": float(pitch), "bearing": float(bearing)}


# ---------------------------------------------------------------- spline
def _dist(a: np.ndarray, b: np.ndarray) -> float:
    """Metric for the centripetal knot spacing: pan in screen widths, zoom levels, pitch and bearing scaled to comparable units."""
    z = (a[2] + b[2]) / 2.0
    lat = math.radians((a[1] + b[1]) / 2.0)
    pan = math.hypot((b[0] - a[0]) * math.cos(lat), b[1] - a[1]) / (360.0 / 2.0 ** z) * 1.0
    return math.sqrt(pan ** 2 + (b[2] - a[2]) ** 2 + ((b[3] - a[3]) / 45.0) ** 2 + ((b[4] - a[4]) / 45.0) ** 2)


def _spline_prepare(keys: list):
    ks = sorted(keys, key=lambda k: k["t"])
    T = np.array([float(k["t"]) for k in ks])
    P = np.array([_vec(k) for k in ks])
    for i in range(1, len(P)):  # unwrap bearing so the spline never takes the long way round
        P[i, 4] = _shortest(P[i - 1, 4], P[i, 4])
    return T, P


def _spline_velocities(T: np.ndarray, P: np.ndarray, alpha: float = 0.5) -> np.ndarray:
    """Tangents dP/dt at each key from the centripetal Catmull-Rom parametrisation (knot spacing d**alpha), end tangents
    from reflected ghost points. Tangents are converted to time with the mean ds/dt around the key, so the Hermite
    segments in time are C1 (velocity continuous). A key next to a zero-length segment (a hold) gets velocity 0, so
    holds are exactly static and moves ease out of them."""
    n = len(T)
    V = np.zeros_like(P)
    if n < 2:
        return V
    ET = np.concatenate([[2 * T[0] - T[1]], T, [2 * T[-1] - T[-2]]])
    EP = np.vstack([2 * P[0] - P[1], P, 2 * P[-1] - P[-2]])
    d = [_dist(EP[k], EP[k + 1]) for k in range(n + 1)]
    ds = [max(x, 1e-9) ** alpha for x in d]
    for i in range(n):
        k = i + 1
        sa, sb = ds[k - 1], ds[k]
        if d[k - 1] < 1e-9 or d[k] < 1e-9:
            continue
        m = (EP[k] - EP[k - 1]) / sa - (EP[k + 1] - EP[k - 1]) / (sa + sb) + (EP[k + 1] - EP[k]) / sb
        V[i] = m * (sa + sb) / (ET[k + 1] - ET[k - 1])
    return V


def _hermite(p0, p1, v0, v1, h, u):
    u2, u3 = u * u, u * u * u
    return ((2 * u3 - 3 * u2 + 1) * p0 + (u3 - 2 * u2 + u) * h * v0 + (-2 * u3 + 3 * u2) * p1 + (u3 - u2) * h * v1)


def camera_spline(keys: list, t: float) -> dict:
    """Centripetal Catmull-Rom (alpha 0.5) through keys on (lon, lat, zoom, pitch, bearing); keys are {"t": seconds, **ViewState}.
    Passes through every key, velocity is continuous at interior keys (smoothstep chains are forbidden: they stop at
    every key). Equal consecutive keys are holds (zero velocity). Bearing is unwrapped (the result may leave ±180).
    t outside the keys clamps to the first/last key."""
    if not keys:
        raise ValueError("no keys")
    T, P = _spline_prepare(keys)
    if len(T) == 1 or t <= T[0]:
        return _view(P[0])
    if t >= T[-1]:
        return _view(P[-1])
    V = _spline_velocities(T, P)
    i = int(np.searchsorted(T, t, side="right") - 1)
    i = min(i, len(T) - 2)
    h = T[i + 1] - T[i]
    return _view(_hermite(P[i], P[i + 1], V[i], V[i + 1], h, (t - T[i]) / h))


# ---------------------------------------------------------------- van Wijk & Nuij
def camera_fly(a: dict, b: dict, u: float, viewport=(1080, 1080), rho: float = 1.414) -> dict:
    """Van Wijk–Nuij smooth zoom-pan from a to b at normalised u∈[0,1] (closed form, same maths as @math.gl/web-mercator
    flyToViewport, no duration). lon/lat/zoom follow the optimal zoom-out/zoom-in path (zoom dips on long moves); pitch and
    bearing lerp (bearing the short way). Endpoints are exact. Use only when the move crosses ≥2 zoom levels or ≥1
    screen width (rules.CAMERA['van_wijk_when']). `viewport` only sets w0 = max(W, H), the reference screen width."""
    A, B = _vec(a), _vec(b)
    u = 0.0 if u <= 0.0 else 1.0 if u >= 1.0 else float(u)
    if u == 0.0:
        return _view(A)
    if u == 1.0:
        return _view(B)
    bear = A[4] + (_shortest(A[4], B[4]) - A[4]) * u
    pitch = A[3] + (B[3] - A[3]) * u
    z0, z1 = A[2], B[2]
    x0, y0 = _world(A[0], A[1])
    x1, y1 = _world(B[0], B[1])
    dx, dy = x1 - x0, y1 - y0
    w0 = float(max(viewport))
    scale = 2.0 ** (z1 - z0)
    w1 = w0 / scale
    u1 = math.hypot(dx, dy) * 2.0 ** z0  # pixels at the start zoom
    if u1 < 0.01:  # centre barely moves: linear, as deck.gl
        return {"longitude": A[0] + (B[0] - A[0]) * u, "latitude": A[1] + (B[1] - A[1]) * u,
                "zoom": z0 + (z1 - z0) * u, "pitch": float(pitch), "bearing": float(bear)}
    r2 = rho * rho
    b0 = (w1 * w1 - w0 * w0 + r2 * r2 * u1 * u1) / (2 * w0 * r2 * u1)
    b1 = (w1 * w1 - w0 * w0 - r2 * r2 * u1 * u1) / (2 * w1 * r2 * u1)
    r0 = math.log(math.sqrt(b0 * b0 + 1) - b0)
    r1 = math.log(math.sqrt(b1 * b1 + 1) - b1)
    S = (r1 - r0) / rho
    s = u * S
    w = math.cosh(r0) / math.cosh(r0 + rho * s)
    uu = (w0 * ((math.cosh(r0) * math.tanh(r0 + rho * s) - math.sinh(r0)) / r2)) / u1
    lon, lat = _lonlat(x0 + dx * uu, y0 + dy * uu)
    return {"longitude": lon, "latitude": lat, "zoom": z0 + math.log2(1.0 / w), "pitch": float(pitch), "bearing": float(bear)}


# ---------------------------------------------------------------- follow / orbit
def _track_arrays(track, agent_id=None):
    if agent_id is not None:
        track = track[track["agent_id"] == agent_id]
    elif "agent_id" in track and track["agent_id"].nunique() > 1:
        raise ValueError("trajectory has several agents: pass agent_id")
    tr = track.sort_values("t")
    return tr["t"].to_numpy(float), tr["lon"].to_numpy(float), tr["lat"].to_numpy(float)


def _lowpassed_target(T, X, Y, t: float, lead_s: float, omega: float):
    """Critically damped spring (unity DC gain, impulse response ω² s e^{-ωs}) driven by the look-ahead target
    p(τ+lead_s), evaluated in closed form: the target is piecewise linear between trajectory samples, so the
    convolution over the past is an exact sum of per-piece integrals. History beyond 14/ω s is folded into the
    value there (weight < 1e-5). No state, no integrator: a pure function of t."""
    W = 14.0 / omega
    lo = t - W
    cuts = T - lead_s
    pts = np.concatenate([[lo], cuts[(cuts > lo) & (cuts < t)], [t]])
    tx = lambda tau: np.interp(tau + lead_s, T, X)  # noqa: E731
    ty = lambda tau: np.interp(tau + lead_s, T, Y)  # noqa: E731

    def F0(s):  # ∫ ω² s e^{-ωs} ds  (antiderivative)
        return -(omega * s + 1.0) * math.exp(-omega * s)

    def F1(s):  # ∫ ω² s² e^{-ωs} ds
        return -(omega ** 2 * s * s + 2 * omega * s + 2.0) * math.exp(-omega * s)

    out = np.zeros(2)
    for a, b in zip(pts[:-1], pts[1:]):
        if b <= a:
            continue
        s1, s2 = t - b, t - a  # s decreases with tau
        for k, f in enumerate((tx, ty)):
            fa, fb = f(a), f(b)
            g1 = (fa - fb) / (s2 - s1)  # slope w.r.t. s
            g0 = fb - g1 * s1
            out[k] += g0 * (F0(s2) - F0(s1)) + g1 * (F1(s2) - F1(s1))
    tail = (omega * W + 1.0) * math.exp(-omega * W)
    out += tail * np.array([tx(lo), ty(lo)])
    return float(out[0]), float(out[1])


def _half_ray(az_screen_deg: float, W: float, H: float) -> float:
    sx, cy = abs(math.sin(math.radians(az_screen_deg))), abs(math.cos(math.radians(az_screen_deg)))
    return min((W / 2.0) / sx if sx > 1e-9 else float("inf"), (H / 2.0) / cy if cy > 1e-9 else float("inf"))


def camera_follow(track_lonlat_t, t: float, lead_s: float = 5.0, omega: float = 3.0, offset: dict | None = None, *,
                  agent_id=None, zoom: float = 12.0, pitch: float = 50.0, bearing: float = 0.0, viewport=(1080, 1080)) -> dict:
    """Follow-cam on a vessel. `track_lonlat_t`: DataFrame (agent_id, t, lon, lat). The look-ahead target (position at
    t+lead_s) is low-passed by a critically damped spring (closed form, `_lowpassed_target`); its direction gives a
    smoothed heading. The vessel is then placed rules.CAMERA['lead_space_frac'] (mean, or offset['lead_space_frac'])
    from the screen edge opposite its heading, i.e. the camera centre sits ahead of the vessel by (1-2·frac)·half the
    screen extent along the heading; the sideways lag of the spring is kept but limited to ±25% of the half extent.
    zoom/pitch/bearing are the camera's (constant here)."""
    T, X, Y = _track_arrays(track_lonlat_t, agent_id)
    frac = float((offset or {}).get("lead_space_frac", sum(CAMERA["lead_space_frac"]) / 2.0))
    W, H = float(viewport[0]), float(viewport[1])
    px_per = 2.0 ** zoom  # world (zoom-0, 512 px) units → screen px

    cx, cy = _lowpassed_target(T, X, Y, t, lead_s, omega)
    cx2, cy2 = _lowpassed_target(T, X, Y, t + 0.5, lead_s, omega)
    cx1, cy1 = _lowpassed_target(T, X, Y, t - 0.5, lead_s, omega)
    vx, vy = float(np.interp(t, T, X)), float(np.interp(t, T, Y))

    # smoothed heading from the spring output, in world pixels (x east, y south)
    (a0, b0), (a1, b1) = _world(cx1, cy1), _world(cx2, cy2)
    hx, hy = a1 - a0, b1 - b0
    if math.hypot(hx, hy) < 1e-12:  # standing still: fall back to the look-ahead direction, else no shift
        (a0, b0), (a1, b1) = _world(vx, vy), _world(cx, cy)
        hx, hy = a1 - a0, b1 - b0
    vwx, vwy = _world(vx, vy)
    if math.hypot(hx, hy) < 1e-12:
        lon, lat = _lonlat(vwx, vwy)
        return {"longitude": lon, "latitude": lat, "zoom": zoom, "pitch": pitch, "bearing": bearing}
    n = math.hypot(hx, hy)
    hx, hy = hx / n, hy / n
    az = math.degrees(math.atan2(hx, -hy))  # compass azimuth of the heading
    half = _half_ray(az - bearing, W, H)
    ahead = (1.0 - 2.0 * frac) * half  # screen px the centre sits ahead of the vessel
    # sideways part of the spring's lag (world px), limited
    (sx, sy) = _world(cx, cy)
    dx, dy = (sx - vwx) * px_per, (sy - vwy) * px_per
    nx, ny = -hy, hx
    side = dx * nx + dy * ny
    half_side = _half_ray(az - bearing + 90.0, W, H)
    side = max(-0.25 * half_side, min(0.25 * half_side, side))
    ox = vwx + (hx * ahead + nx * side) / px_per
    oy = vwy + (hy * ahead + ny * side) / px_per
    lon, lat = _lonlat(ox, oy)
    return {"longitude": lon, "latitude": lat, "zoom": zoom, "pitch": pitch, "bearing": bearing}


def camera_orbit(center_lonlat, t: float, t0: float, deg_per_s: float, zoom: float, pitch: float) -> dict:
    """Orbit around a site at ≤ rules.CAMERA['bearing_rate_orbit_max'] (ValueError above it). Bearing = (t-t0)·deg_per_s."""
    if abs(deg_per_s) > CAMERA["bearing_rate_orbit_max"] + 1e-9:
        raise ValueError(f"orbit {deg_per_s} deg/s exceeds {CAMERA['bearing_rate_orbit_max']}")
    return {"longitude": float(center_lonlat[0]), "latitude": float(center_lonlat[1]), "zoom": float(zoom),
            "pitch": float(pitch), "bearing": float((t - t0) * deg_per_s)}


# ---------------------------------------------------------------- per-frame track
def _resolve_key(cam: dict, key: dict, viewport) -> dict:
    """Merge shot-level camera defaults (pitch, bearing, fit, padding, zoom_offset) with a key and resolve to a view state."""
    k = {**{x: cam[x] for x in ("fit", "pitch", "bearing", "padding", "zoom_offset", "longitude", "latitude", "zoom") if x in cam}, **key}
    if "fit" in key and "longitude" not in key:  # an explicit fit on the key beats shot-level lon/lat/zoom
        for x in ("longitude", "latitude", "zoom"):
            k.pop(x, None)
    pitch, bearing = float(k.get("pitch", 0.0)), float(k.get("bearing", 0.0))
    if "fit" in k and "longitude" not in k:
        v = fit_view(k["fit"], viewport, pitch, bearing, k.get("padding", 0.06))
    else:
        v = {"longitude": float(k["longitude"]), "latitude": float(k["latitude"]), "zoom": float(k["zoom"]), "pitch": pitch, "bearing": bearing}
    v["zoom"] += float(k.get("zoom_offset", 0.0))
    return v


def camera_track(shot: dict, t0: float, t1: float, seconds: float, fps: int, viewport, traj=None) -> list[dict]:
    """One viewState per output frame for a storyboard map shot: round(seconds*fps) frames, frame i at shot time i/fps and
    simulation time t0 + (t1-t0)·i/n. shot['camera'] = {pitch, bearing, fit | lon/lat/zoom, padding, zoom_offset,
    keys: [{at: 0..1, fit | lon/lat/zoom, pitch, bearing, move: spline|fly, ease}], follow: {agent_id, lead_s, zoom, pitch,
    bearing, omega}}. A key with move: fly is reached from the previous key by van Wijk–Nuij (eased with `ease`, default
    cubic_in_out); other consecutive keys form one centripetal Catmull-Rom run. `follow` needs `traj` (agent_id,t,lon,lat) and
    overrides the keys. Frame = {"i", "s", "t", longitude, latitude, zoom, pitch, bearing}; bearing is continuous (unwrapped)."""
    n = int(round(seconds * fps))
    cam = shot.get("camera", shot)
    frames_t = [t0 + (t1 - t0) * i / n for i in range(n)]
    out: list[dict] = []
    fol = cam.get("follow")
    if fol:
        if traj is None:
            raise ValueError("follow shot needs traj")
        for i in range(n):
            s = i / fps
            v = camera_follow(traj, frames_t[i], lead_s=fol.get("lead_s", 5.0), omega=fol.get("omega", 3.0), agent_id=fol.get("agent_id"),
                              zoom=fol.get("zoom", 12.0), pitch=fol.get("pitch", cam.get("pitch", 50.0)),
                              bearing=fol.get("bearing", cam.get("bearing", 0.0)), viewport=viewport)
            out.append({"i": i, "s": s, "t": frames_t[i], **v})
        return out
    raw = sorted(cam.get("keys") or [{"at": 0.0}], key=lambda k: k["at"])
    keys = []
    for k in raw:
        v = _resolve_key(cam, k, viewport)
        keys.append({"t": float(k["at"]) * seconds, "v": v, "move": k.get("move", "spline"), "ease": k.get("ease", CAMERA["ease_default"])})
    # unwrap bearing along keys
    for i in range(1, len(keys)):
        keys[i]["v"]["bearing"] = _shortest(keys[i - 1]["v"]["bearing"], keys[i]["v"]["bearing"])
    # runs of spline-connected keys; a fly key starts its own segment from the previous key
    runs, cur = [], [keys[0]]
    for k in keys[1:]:
        if k["move"] == "fly":
            runs.append(cur)
            cur = [k]
        else:
            cur.append(k)
    runs.append(cur)
    run_keys = [[{"t": k["t"], **k["v"]} for k in r] for r in runs]
    V = [_spline_velocities(*_spline_prepare(rk)) if len(rk) > 1 else None for rk in run_keys]
    prep = [_spline_prepare(rk) for rk in run_keys]
    for i in range(n):
        s = i / fps
        if s <= keys[0]["t"]:
            v = dict(keys[0]["v"])
        elif s >= keys[-1]["t"]:
            v = dict(keys[-1]["v"])
        else:
            v = None
            for r_i, r in enumerate(runs):
                if r_i > 0:  # fly segment between previous run's last key and this run's first key
                    a, b = runs[r_i - 1][-1], r[0]
                    if a["t"] <= s < b["t"]:
                        u = (s - a["t"]) / max(b["t"] - a["t"], 1e-9)
                        v = camera_fly(a["v"], b["v"], ease(b["ease"], u), viewport)
                        break
                if len(r) > 1 and r[0]["t"] <= s <= r[-1]["t"]:
                    T, P = prep[r_i]
                    j = min(int(np.searchsorted(T, s, side="right") - 1), len(T) - 2)
                    h = T[j + 1] - T[j]
                    v = _view(_hermite(P[j], P[j + 1], V[r_i][j], V[r_i][j + 1], h, (s - T[j]) / h))
                    break
            if v is None:
                v = dict(keys[-1]["v"])
        out.append({"i": i, "s": s, "t": frames_t[i], **v})
    return out


# ---------------------------------------------------------------- inspector
def _px_pan(f0: dict, f1: dict) -> float:
    z = (f0["zoom"] + f1["zoom"]) / 2.0
    x0, y0 = _world(f0["longitude"], f0["latitude"])
    x1, y1 = _world(f1["longitude"], f1["latitude"])
    return math.hypot(x1 - x0, y1 - y0) * 2.0 ** z


def _rates(fr: list[dict], fps: int, W: float) -> dict:
    """Per-interval rates (one entry per consecutive pair): zoom/s, pitch deg/s, bearing deg/s, pan screen widths/s."""
    a = np.zeros((max(len(fr) - 1, 0), 4))
    for i in range(len(fr) - 1):
        f0, f1 = fr[i], fr[i + 1]
        a[i] = (abs(f1["zoom"] - f0["zoom"]) * fps, abs(f1["pitch"] - f0["pitch"]) * fps,
                abs(f1["bearing"] - f0["bearing"]) * fps, _px_pan(f0, f1) / W * fps)
    return {"zoom": a[:, 0], "pitch": a[:, 1], "bearing": a[:, 2], "pan": a[:, 3]}


def _span(fr, i0, i1):
    """Max deviation inside frames [i0, i1): zoom, pitch, bearing, pan in px."""
    seg = fr[i0:i1]
    if len(seg) < 2:
        return 0.0, 0.0, 0.0, 0.0
    return (max(abs(f["zoom"] - seg[0]["zoom"]) for f in seg), max(abs(f["pitch"] - seg[0]["pitch"]) for f in seg),
            max(abs(f["bearing"] - seg[0]["bearing"]) for f in seg), max(_px_pan(seg[0], f) for f in seg))


def shot_plan(storyboard: dict, viewport: tuple[int, int], fps: int = 30, tracks: dict | None = None) -> list[str]:
    """INSPECTOR. Sample every map shot's camera_track (or `tracks[shot_index]`, a list of frames) at `fps` and return
    violations of rules.CAMERA as strings 'shot <i> (<type>) @<film s>s: <what> <value> vs <limit>'. Checks: shot_min_s for
    all shots; zoom, pitch, bearing (reveal limit, orbit limit if camera.role == 'orbit') and pan rates (0.25 widths/s for
    follow shots, else 0.6); film holds (first film_hold_in_s / last film_hold_out_s static when a map shot opens/closes
    the film; non-map shots are static and count towards film length); cuts: camera rates at the first/last frame of a map
    shot next to another shot must be < cut_max_angular_rate and < cut_max_zoom_rate (else crossfade needed), and between
    two map shots the bearing step is 0 (±0.5°) or ≥ cut_bearing_jump_min. Not checked: SHOTS_PER_FILM, screen direction
    (180° rule needs vessel headings). Follow shots need `tracks` (or are reported as unverifiable)."""
    R = CAMERA
    W = float(viewport[0])
    shots = storyboard.get("shots", [])
    tracks = tracks or {}
    msgs: list[str] = []
    starts, acc = [], 0.0
    for sh in shots:
        starts.append(acc)
        acc += float(sh.get("seconds", 0.0))
    frames: dict[int, list[dict]] = {}
    for i, sh in enumerate(shots):
        tag = f"shot {i} ({sh.get('type')})"
        sec = float(sh.get("seconds", 0.0))
        if sec < R["shot_min_s"] - 1e-9:
            msgs.append(f"{tag} @{starts[i]:.2f}s: length {sec:.2f}s vs min {R['shot_min_s']}s")
        if sh.get("type") != "map":
            continue
        if i in tracks:
            fr = tracks[i]
        else:
            if (sh.get("camera") or {}).get("follow"):
                msgs.append(f"{tag} @{starts[i]:.2f}s: follow camera cannot be checked without a track (pass tracks[{i}])")
                continue
            try:
                fr = camera_track(sh, 0.0, 1.0, sec, fps, viewport)
            except Exception as e:  # noqa: BLE001 - report, never crash the inspector
                msgs.append(f"{tag} @{starts[i]:.2f}s: camera not computable: {e}")
                continue
        frames[i] = fr
        if len(fr) < 2:
            continue
        cam = sh.get("camera", {})
        rt = _rates(fr, fps, W)
        lim = {"zoom": R["zoom_rate_max"], "pitch": R["pitch_rate_max"],
               "bearing": R["bearing_rate_orbit_max"] if cam.get("role") == "orbit" else R["bearing_rate_reveal_max"],
               "pan": R["pan_rate_with_vessel_max"] if cam.get("follow") else R["pan_rate_max"]}
        unit = {"zoom": "zoom/s", "pitch": "deg/s", "bearing": "deg/s", "pan": "screen widths/s"}
        for q in ("zoom", "pitch", "bearing", "pan"):
            j = int(np.argmax(rt[q]))
            if rt[q][j] > lim[q] + 1e-9:
                msgs.append(f"{tag} @{starts[i] + fr[j]['s']:.2f}s: {q} rate {rt[q][j]:.3f} {unit[q]} vs max {lim[q]}")
    # film holds
    if shots and 0 in frames:
        fr = frames[0]
        nfr = min(len(fr), int(round(R["film_hold_in_s"] * fps)) + 1)
        dz, dp, db, dpx = _span(fr, 0, nfr)
        if any((dz > 1e-3, dp > 0.05, db > 0.05, dpx / W > 1e-3)):
            msgs.append(f"shot 0 (map) @0.00s: film opening not static for {R['film_hold_in_s']}s (dzoom {dz:.4f}, dpitch {dp:.3f}, dbearing {db:.3f}, pan {dpx / W:.4f} widths)")
    last = len(shots) - 1
    if last >= 0 and last in frames:
        fr = frames[last]
        nfr = min(len(fr), int(round(R["film_hold_out_s"] * fps)) + 1)
        dz, dp, db, dpx = _span(fr, len(fr) - nfr, len(fr))
        if any((dz > 1e-3, dp > 0.05, db > 0.05, dpx / W > 1e-3)):
            msgs.append(f"shot {last} (map) @{starts[last] + fr[-nfr]['s']:.2f}s: film ending not static for {R['film_hold_out_s']}s (dzoom {dz:.4f}, dpitch {dp:.3f}, dbearing {db:.3f}, pan {dpx / W:.4f} widths)")
    # cuts
    for i in range(len(shots) - 1):
        a, b = shots[i], shots[i + 1]
        cut_t = starts[i + 1]
        for idx, edge in ((i, -1), (i + 1, 0)):
            if idx not in frames or len(frames[idx]) < 2:
                continue
            fr = frames[idx]
            k = max(len(fr) - 2, 0) if edge == -1 else 0
            r = _rates(fr[k:k + 2], fps, W)
            ang = max(r["pitch"][0], r["bearing"][0])
            if ang >= R["cut_max_angular_rate"] - 1e-9:
                msgs.append(f"cut {i}->{i + 1} @{cut_t:.2f}s: shot {idx} angular rate {ang:.2f} deg/s vs max {R['cut_max_angular_rate']} (crossfade {R['crossfade_frames']} frames or hold)")
            if r["zoom"][0] >= R["cut_max_zoom_rate"] - 1e-9:
                msgs.append(f"cut {i}->{i + 1} @{cut_t:.2f}s: shot {idx} zoom rate {r['zoom'][0]:.3f}/s vs max {R['cut_max_zoom_rate']}")
        if i in frames and i + 1 in frames:
            jump = abs(frames[i + 1][0]["bearing"] - frames[i][-1]["bearing"]) % 360.0
            jump = min(jump, 360.0 - jump)
            if 0.5 < jump < R["cut_bearing_jump_min"]:
                msgs.append(f"cut {i}->{i + 1} @{cut_t:.2f}s: bearing jump {jump:.1f} deg vs 0 or >= {R['cut_bearing_jump_min']} (30 degree rule)")
    return msgs
