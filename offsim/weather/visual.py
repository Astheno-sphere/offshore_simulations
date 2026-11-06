"""Weather on SCREEN. Spec: docs/VISUAL_SPEC.md §3.

Decision: our own seeded particles, pre-integrated in Python, drawn with deck.gl TripsLayer at currentTime = t.
Fully frame-exact. GPU particle libraries (weatherlayers-gl MPL-2.0, deck.gl-community ParticleLayer) keep internal
state / own fps and are drafts-only until a byte-identical re-render test passes.

Fields are xarray Datasets with dims (time, lat, lon). Time is either numeric (scene seconds) or datetime64, which is
converted to scene seconds against an epoch (`attrs['epoch_utc']`, an argument, or the first time stamp).
Wind uses variables u10/v10, currents u/v (m/s, east/north). NaN (land) is treated as calm.

Everything here is a pure function of its arguments: same inputs, same bytes.
"""
from __future__ import annotations

import base64
import io
import json
import math
from pathlib import Path

import numpy as np

R_EARTH = 6_371_008.8
DEG = 180.0 / math.pi
STYLE = json.loads((Path(__file__).resolve().parents[1] / "style.json").read_text())
MAX_PARTICLES = 6000
MAX_POINTS = 600_000   # vertices in one scene (guards the JSON size)


def _rgb(h: str):
    h = h.lstrip("#")
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


# Fixed ramps in the house palette (offsim/style.json): [fraction of vmin..vmax, rgb, alpha 0..1]
HS_RAMP = [(0.0, _rgb("#2E5B78"), 0.35), (0.4, _rgb(STYLE["cls"]["ferry"]), 0.60),
           (0.65, _rgb(STYLE["paper"]), 0.75), (1.0, _rgb(STYLE["accent"]), 0.90)]
SPEED_RAMP = [(0.0, _rgb(STYLE["cls"]["ferry"]), 0.55), (0.5, _rgb(STYLE["paper"]), 0.80),
              (1.0, _rgb(STYLE["accent"]), 0.95)]
SOURCE = {"hs": "MET Norway NORA3 wave hindcast, CC BY 4.0", "wind": "MET Norway NORA3 wind, CC BY 4.0",
          "current": "MET Norway NorKyst v3, CC BY 4.0"}
UV = {"wind": ("u10", "v10"), "current": ("u", "v")}


def _ramp_at(ramp, f):
    """Vectorised ramp lookup: f array in [0,1] -> (..., 4) float rgba (alpha 0..1)."""
    f = np.clip(np.asarray(f, float), 0.0, 1.0)
    xs = [r[0] for r in ramp]
    out = np.empty(f.shape + (4,))
    for c in range(3):
        out[..., c] = np.interp(f, xs, [r[1][c] for r in ramp])
    out[..., 3] = np.interp(f, xs, [r[2] for r in ramp])
    return out


# ------------------------------------------------------------------ field

def _scene_seconds(ds, epoch=None):
    t = ds["time"].values
    if np.issubdtype(t.dtype, np.datetime64):
        e = np.datetime64(epoch if epoch is not None else ds.attrs.get("epoch_utc", t[0]), "ns")
        return (t.astype("datetime64[ns]") - e) / np.timedelta64(1, "s")
    return t.astype(float)


class Field:
    """Time-varying u/v on a regular lon/lat grid; bilinear in space, linear in time, clamped in time, calm outside."""

    def __init__(self, lon, lat, t, u, v):
        self.lon, self.lat, self.t = (np.asarray(a, float) for a in (lon, lat, t))
        self.u, self.v = (np.nan_to_num(np.asarray(a, float), nan=0.0) for a in (u, v))
        self.nt, self.ny, self.nx = self.u.shape
        assert self.v.shape == self.u.shape and self.t.size == self.nt

    @classmethod
    def from_ds(cls, ds, names=None, epoch=None):
        if isinstance(ds, Field):
            return ds
        names = names or next(n for n in (("u10", "v10"), ("u", "v")) if n[0] in ds)
        ds = ds.sortby("lat").sortby("lon")
        if "time" not in ds.dims:
            ds = ds.expand_dims(time=[0.0])
        t = _scene_seconds(ds, epoch)
        o = np.argsort(t)
        a, b = ds[names[0]].transpose("time", "lat", "lon").values, ds[names[1]].transpose("time", "lat", "lon").values
        return cls(ds["lon"].values, ds["lat"].values, t[o], a[o], b[o])

    def _plane(self, a, i, fx, fy, ix, iy):
        p = a[i]
        return ((1 - fy) * ((1 - fx) * p[iy, ix] + fx * p[iy, ix + 1])
                + fy * ((1 - fx) * p[iy + 1, ix] + fx * p[iy + 1, ix + 1]))

    def sample(self, t: float, lon, lat):
        """(u, v) in m/s at scene time t for arrays lon/lat. Zero outside the grid."""
        lon, lat = np.asarray(lon, float), np.asarray(lat, float)
        inside = (lon >= self.lon[0]) & (lon <= self.lon[-1]) & (lat >= self.lat[0]) & (lat <= self.lat[-1])
        if self.nx < 2 or self.ny < 2:
            return np.zeros_like(lon), np.zeros_like(lon)
        fx = np.interp(lon, self.lon, np.arange(self.nx))
        fy = np.interp(lat, self.lat, np.arange(self.ny))
        ix, iy = np.minimum(fx.astype(int), self.nx - 2), np.minimum(fy.astype(int), self.ny - 2)
        fx, fy = fx - ix, fy - iy
        if self.nt == 1 or t <= self.t[0]:
            i0 = i1 = 0
            w = 0.0
        elif t >= self.t[-1]:
            i0 = i1 = self.nt - 1
            w = 0.0
        else:
            i1 = int(np.searchsorted(self.t, t, side="right"))
            i0 = i1 - 1
            w = (t - self.t[i0]) / (self.t[i1] - self.t[i0])
        out = []
        for a in (self.u, self.v):
            x = self._plane(a, i0, fx, fy, ix, iy)
            if w:
                x = (1 - w) * x + w * self._plane(a, i1, fx, fy, ix, iy)
            out.append(np.where(inside, x, 0.0))
        return out[0], out[1]


# ------------------------------------------------------------------ seeds

def _land_geom(land):
    """None | shapely geometry | GeoJSON dict | deck-style polygons (rings, or lists of rings) -> shapely or None."""
    if land is None:
        return None
    if hasattr(land, "geom_type"):
        return land
    from shapely.geometry import Polygon, shape
    from shapely.ops import unary_union
    if isinstance(land, dict):
        return shape(land)
    polys = []
    for p in land:
        rings = [p] if p and isinstance(p[0][0], (int, float)) else list(p)
        polys.append(Polygon(rings[0], rings[1:]))
    return unary_union(polys) if polys else None


def seed_particles(bbox: tuple, n: int, seed: int, land=None):
    """n start points (lon, lat) in open water, deterministic for `seed`: a blue-noise-like jittered grid in
    equirectangular metres, thinned by a seeded permutation; points inside `land` (shapely geometry, GeoJSON, or
    deck-style polygons in lon/lat) are rejected. Returns float array shape (n, 2).
    Raises ValueError if the box has too little water for n points."""
    import shapely

    w, s, e, n_ = bbox
    rng = np.random.default_rng(seed)
    g = _land_geom(land)
    coslat = math.cos(math.radians((s + n_) / 2))
    aspect = ((e - w) * coslat) / (n_ - s)
    if g is not None:
        probe = np.column_stack([rng.uniform(w, e, 4000), rng.uniform(s, n_, 4000)])
        frac = max(float((~shapely.contains_xy(g, probe[:, 0], probe[:, 1])).mean()), 1e-3)
    else:
        frac = 1.0
    m = int(math.ceil(1.3 * n / frac))
    for _ in range(6):
        nc = max(1, int(math.ceil(math.sqrt(m * aspect))))
        nr = max(1, int(math.ceil(m / nc)))
        cx, cy = np.meshgrid(np.arange(nc), np.arange(nr))
        x = w + (cx.ravel() + rng.random(cx.size)) / nc * (e - w)
        y = s + (cy.ravel() + rng.random(cy.size)) / nr * (n_ - s)
        keep = np.ones(x.size, bool) if g is None else ~shapely.contains_xy(g, x, y)
        pts = np.column_stack([x[keep], y[keep]])
        if len(pts) >= n:
            pick = np.sort(rng.permutation(len(pts))[:n])
            return pts[pick]
        m *= 2
    raise ValueError(f"cannot place {n} water points in {bbox}")


# ------------------------------------------------------------------ streamlines

def integrate_streamlines(field, seeds, t0: float, t1: float, dt_s: float = 60.0, life_s: float = 1800.0, speedup: float = 1.0,
                          stagger: int = 10, out_dt_s: float | None = None, prewarm: bool = False, decimals: int = 6):
    """RK4 through a time-varying u/v field (wind or current) -> trips [{i, path, timestamps, speed}] for TripsLayer.
    Integration is in metres in a local equirectangular frame per particle (origin = its seed, cos(lat) fixed);
    the field is bilinear in space, linear in time; `speedup` multiplies the field speed (`speed` stays physical m/s).
    Respawn is a fixed schedule, never random: particle i is born at t0 + (i mod K)·life_s/K (K = `stagger`) and
    reborn at its seed every life_s; one trip per life, vertices every out_dt_s (multiple of dt_s, default dt_s),
    cut at t1. prewarm=True also emits the life before the first birth so the screen is full from t0.
    `field`: Field or xarray Dataset (time, lat, lon) with u10/v10 or u/v. seeds: (n, 2) lon/lat."""
    f = Field.from_ds(field)
    seeds = np.asarray(seeds, float)
    n = len(seeds)
    out_dt = float(out_dt_s or dt_s)
    sub = max(1, int(round(out_dt / dt_s)))
    h = out_dt / sub
    steps = int(math.floor(life_s / out_dt + 1e-9))
    idx = np.arange(n)
    phase = (idx % stagger) * life_s / stagger
    k_min = -1 if prewarm else 0
    trips = []
    for ph in range(min(stagger, n)):
        members = idx[idx % stagger == ph]
        lon0, lat0 = seeds[members, 0], seeds[members, 1]
        kx = 1.0 / (R_EARTH * np.cos(np.radians(lat0)) / DEG)   # deg lon per metre
        ky = DEG / R_EARTH                                       # deg lat per metre
        k = k_min
        while True:
            start = t0 + phase[members[0]] + k * life_s
            k += 1
            if start + life_s <= t0:
                continue
            if start >= t1:
                break
            x = np.zeros(len(members))
            y = np.zeros(len(members))
            cols_lon, cols_lat, cols_sp, ts = [], [], [], []
            for j in range(steps + 1):
                t = start + j * out_dt
                if t > t1 + 1e-9:
                    break
                u, v = f.sample(t, lon0 + x * kx, lat0 + y * ky)
                cols_lon.append(lon0 + x * kx)
                cols_lat.append(lat0 + y * ky)
                cols_sp.append(np.hypot(u, v))
                ts.append(t)
                if j == steps:
                    break
                tt = t
                for _ in range(sub):
                    def vel(tq, xq, yq):
                        a, b = f.sample(tq, lon0 + xq * kx, lat0 + yq * ky)
                        return a * speedup, b * speedup
                    k1 = vel(tt, x, y)
                    k2 = vel(tt + h / 2, x + h / 2 * k1[0], y + h / 2 * k1[1])
                    k3 = vel(tt + h / 2, x + h / 2 * k2[0], y + h / 2 * k2[1])
                    k4 = vel(tt + h, x + h * k3[0], y + h * k3[1])
                    x = x + h / 6 * (k1[0] + 2 * k2[0] + 2 * k3[0] + k4[0])
                    y = y + h / 6 * (k1[1] + 2 * k2[1] + 2 * k3[1] + k4[1])
                    tt += h
            if len(ts) < 2:
                continue
            for q, i in enumerate(members):
                trips.append({"i": int(i),
                              "path": [[round(float(a[q]), decimals), round(float(b[q]), decimals)] for a, b in zip(cols_lon, cols_lat)],
                              "timestamps": [round(float(tv), 3) for tv in ts],
                              "speed": [round(float(c[q]), 3) for c in cols_sp]})
    trips.sort(key=lambda d: (d["timestamps"][0], d["i"]))
    return trips


# ------------------------------------------------------------------ Hs texture

def _merc_y(lat):
    return np.log(np.tan(np.pi / 4 + np.radians(lat) / 2))


def _lat_from_merc(y):
    return np.degrees(2 * np.arctan(np.exp(y)) - np.pi / 2)


def _field_at(ds, name, t, epoch=None):
    """Scalar field at scene time t: (lon, lat, 2D array [lat, lon]) bilinear-in-time."""
    ds = ds.sortby("lat").sortby("lon")
    if "time" not in ds.dims:
        ds = ds.expand_dims(time=[0.0])
    ts = _scene_seconds(ds, epoch)
    o = np.argsort(ts)
    a = ds[name].transpose("time", "lat", "lon").values.astype(float)[o]
    ts = ts[o]
    if len(ts) == 1 or t <= ts[0]:
        z = a[0]
    elif t >= ts[-1]:
        z = a[-1]
    else:
        i = int(np.searchsorted(ts, t, side="right"))
        w = (t - ts[i - 1]) / (ts[i] - ts[i - 1])
        z = (1 - w) * a[i - 1] + w * a[i]
    return ds["lon"].values.astype(float), ds["lat"].values.astype(float), z


def _bilinear_grid(lon, lat, z, qlon, qlat):
    """z[lat, lon] sampled at the grid qlat x qlon; NaN outside the grid or next to NaN."""
    fx = np.interp(qlon, lon, np.arange(lon.size), left=np.nan, right=np.nan)
    fy = np.interp(qlat, lat, np.arange(lat.size), left=np.nan, right=np.nan)
    if lon.size < 2 or lat.size < 2:
        return np.full((qlat.size, qlon.size), np.nan)
    ix = np.minimum(np.nan_to_num(fx).astype(int), lon.size - 2)
    iy = np.minimum(np.nan_to_num(fy).astype(int), lat.size - 2)
    ax, ay = (fx - ix)[None, :], (fy - iy)[:, None]
    p = lambda dy, dx: z[(iy + dy)[:, None], (ix + dx)[None, :]]
    return (1 - ay) * ((1 - ax) * p(0, 0) + ax * p(0, 1)) + ay * ((1 - ax) * p(1, 0) + ax * p(1, 1))


def hs_texture(ds, t: float, cmap: str = "offsim-sea", vmin: float = 0.0, vmax: float = 6.0, *,
               threshold: float = 1.0, bbox: tuple | None = None, max_px: int = 256, var: str = "hs", epoch=None):
    """Wave height at scene time t as an RGBA PNG (data URL) + bounds for BitmapLayer; colour ramp fixed per film.
    Fully transparent where Hs <= threshold (or NaN/outside the data); above it the alpha fades in over 0.5 m, then
    the fixed house ramp runs cool blue -> paper -> accent #FF5B3A between vmin and vmax. The image is resampled
    uniformly in Web-Mercator y (what BitmapLayer stretches), longest side <= max_px.
    Returns {"t", "image": "data:image/png;base64,...", "bounds": [w, s, e, n]}."""
    from PIL import Image

    if cmap != "offsim-sea":
        raise ValueError(f"unknown colour map {cmap!r} (the ramp is fixed per film: 'offsim-sea')")
    lon, lat, z = _field_at(ds, var, t, epoch)
    w, s, e, n = bbox if bbox else (lon.min(), lat.min(), lon.max(), lat.max())
    mx = (e - w) * math.cos(math.radians((s + n) / 2))
    my = n - s
    wpx = max(2, int(round(max_px * min(1.0, mx / max(mx, my)))))
    hpx = max(2, int(round(max_px * min(1.0, my / max(mx, my)))))
    qlon = w + (np.arange(wpx) + 0.5) / wpx * (e - w)
    ym = _merc_y(n) - (np.arange(hpx) + 0.5) / hpx * (_merc_y(n) - _merc_y(s))
    qlat = _lat_from_merc(ym)                      # row 0 = north
    hs = _bilinear_grid(lon, lat, z, qlon, qlat)
    f = (hs - vmin) / (vmax - vmin)
    rgba = _ramp_at(HS_RAMP, np.nan_to_num(f))
    fade = np.clip((hs - threshold) / 0.5, 0.0, 1.0)
    alpha = np.where(np.isfinite(hs) & (hs > threshold), rgba[..., 3] * fade, 0.0)
    img = np.zeros(hs.shape + (4,), np.uint8)
    img[..., :3] = np.round(rgba[..., :3]).astype(np.uint8)
    img[..., 3] = np.round(alpha * 255).astype(np.uint8)
    img[img[..., 3] == 0] = 0
    buf = io.BytesIO()
    Image.fromarray(img, "RGBA").save(buf, format="PNG", compress_level=9)
    return {"t": float(t), "image": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii"),
            "bounds": [float(w), float(s), float(e), float(n)]}


# ------------------------------------------------------------------ arrows

def arrows(ds, t: float, spacing_px: int = 64, *, bbox: tuple | None = None, view_px: tuple = (1080, 1080),
           vmax: float = 1.5, names=None, epoch=None, decimals: int = 5):
    """Current/wind arrows on a screen-regular grid as PathLayer segments (CAD style, length ∝ speed).
    The grid is spacing_px apart on a view_px canvas that shows bbox (so it stays regular on screen at that framing);
    tail on the grid node, length = speed/vmax · 0.8 · spacing (capped), head wings 25° / 25% of the length.
    Every arrow has the same 5 vertices (tail, tip, wing, tip, wing) so two frames can be blended vertex by vertex.
    Returns [{"path": [[lon, lat] x5], "speed": m/s}]; arrows over NaN/no data are omitted."""
    f = Field.from_ds(ds, names, epoch)
    w, s, e, n = bbox if bbox else (f.lon[0], f.lat[0], f.lon[-1], f.lat[-1])
    coslat = math.cos(math.radians((s + n) / 2))
    width_m = (e - w) * coslat * R_EARTH / DEG
    height_m = (n - s) * R_EARTH / DEG
    m_per_px = max(width_m / view_px[0], height_m / view_px[1])
    nx, ny = max(1, int(width_m / m_per_px // spacing_px)), max(1, int(height_m / m_per_px // spacing_px))
    gx = w + (np.arange(nx) + 0.5) / nx * (e - w)
    gy = s + (np.arange(ny) + 0.5) / ny * (n - s)
    qx, qy = np.meshgrid(gx, gy)
    u, v = f.sample(t, qx.ravel(), qy.ravel())
    sp = np.hypot(u, v)
    cell_m = spacing_px * m_per_px
    out = []
    for lon0, lat0, a, b, c in zip(qx.ravel(), qy.ravel(), u, v, sp):
        if c < 1e-3:
            continue
        L = min(c / vmax, 1.0) * 0.8 * cell_m
        ux, uy = a / c, b / c
        head = 0.25 * L
        def pt(dx, dy):
            return [round(float(lon0 + dx / (R_EARTH * math.cos(math.radians(lat0)) / DEG)), decimals),
                    round(float(lat0 + dy / R_EARTH * DEG), decimals)]
        ang = math.radians(25)
        def wing(sign):
            ca, sa = math.cos(math.pi - sign * ang), math.sin(math.pi - sign * ang)
            return (L * ux + head * (ux * ca - uy * sa), L * uy + head * (ux * sa + uy * ca))
        wa, wb = wing(+1), wing(-1)
        out.append({"path": [pt(0, 0), pt(L * ux, L * uy), pt(*wa), pt(L * ux, L * uy), pt(*wb)], "speed": round(float(c), 3)})
    return out


# ------------------------------------------------------------------ legend

def legend(kind: str, units: str, vmin: float, vmax: float) -> dict:
    """Overlay legend spec: colour ramp (fraction, rgb, alpha) between vmin and vmax, units, source line
    ('MET Norway NORA3 ..., CC BY 4.0'). kind: 'hs' | 'wind' | 'current'."""
    if kind not in SOURCE:
        raise ValueError(f"legend kind {kind!r} not in {sorted(SOURCE)}")
    ramp = HS_RAMP if kind == "hs" else SPEED_RAMP
    return {"kind": kind, "units": units, "vmin": float(vmin), "vmax": float(vmax),
            "ramp": [[float(p), list(map(int, c)), float(a)] for p, c, a in ramp], "source": SOURCE[kind]}


# ------------------------------------------------------------------ scene block

def _frame_times(ds, t0, t1, epoch):
    ts = np.sort(_scene_seconds(ds if "time" in ds.dims else ds.expand_dims(time=[0.0]), epoch))
    lo = ts[ts <= t0].max() if (ts <= t0).any() else ts[0]
    hi = ts[ts >= t1].min() if (ts >= t1).any() else ts[-1]
    return [float(x) for x in ts[(ts >= lo) & (ts <= hi)]]


def weather_scene(bbox, t0, t1, land=None, seed=0, n_particles=3000, ds_wind=None, ds_wave=None, ds_current=None, *,
                  life_s=1800.0, trail_s=600.0, speedup=1.0, dt_s=60.0, out_dt_s=120.0, epoch_utc=None,
                  hs_threshold=1.0, hs_vmax=6.0, hs_max_px=192, arrow_spacing_px=64, view_px=(1080, 1080),
                  wind_vmax=25.0, current_vmax=1.5) -> dict:
    """The `weather` block of a scene, all on the scene time base (seconds), JSON-safe and deterministic:

    {"particles": {"kind": "wind"|"current"|None, "trips": [{i, path, timestamps, speed}], "trail_s": s},
     "hs":        {"frames": [{"t", "image": data-URL PNG}], "bounds": [w, s, e, n]},      # hourly, brackets [t0, t1]
     "arrows":    [{"t", "paths": [{"path": [[lon, lat] x5], "speed"}]}],                   # current arrows, hourly
     "legend":    {"hs": legend|None, "particles": legend|None, "arrows": legend|None},
     "credit":    "MET Norway NORA3 wind/wave, NorKyst v3 (CC BY 4.0)"}

    Particles follow wind if ds_wind else current; arrows use currents (ds_current). n_particles <= 6000.
    Datasets: (time, lat, lon) with u10/v10 (wind), hs (wave), u/v (current); datetime64 times are converted to scene
    seconds against epoch_utc (default: the earliest first time stamp). Land: see seed_particles."""
    if n_particles > MAX_PARTICLES:
        raise ValueError(f"n_particles {n_particles} > {MAX_PARTICLES}")
    if not t1 > t0:
        raise ValueError("t1 must be after t0")
    firsts = [np.datetime64(d["time"].values[0]) for d in (ds_wind, ds_wave, ds_current)
              if d is not None and "time" in d.dims and np.issubdtype(d["time"].values.dtype, np.datetime64)]
    epoch = epoch_utc if epoch_utc is not None else (min(firsts) if firsts else None)
    bbox = tuple(float(x) for x in bbox)
    credit = []
    legends = {"hs": None, "particles": None, "arrows": None}

    src_kind, src = ("wind", ds_wind) if ds_wind is not None else ("current", ds_current)
    particles = {"kind": None, "trips": [], "trail_s": float(trail_s)}
    if src is not None and n_particles > 0:
        field = Field.from_ds(src, UV[src_kind], epoch)
        seeds = seed_particles(bbox, n_particles, seed, land)
        lives = (t1 - t0) / life_s + 2
        if n_particles * lives * (life_s / out_dt_s + 1) > MAX_POINTS:
            raise ValueError("particle scene too large: raise out_dt_s, lower n_particles or t1 - t0")
        trips = integrate_streamlines(field, seeds, t0, t1, dt_s=dt_s, life_s=life_s, speedup=speedup,
                                      out_dt_s=out_dt_s, prewarm=True, decimals=5)
        particles = {"kind": src_kind, "trips": trips, "trail_s": float(trail_s)}
        vmax = wind_vmax if src_kind == "wind" else current_vmax
        legends["particles"] = legend(src_kind, "m/s", 0.0, vmax)
        credit.append("NORA3 wind" if src_kind == "wind" else "NorKyst v3 currents")

    hs = {"frames": [], "bounds": list(bbox)}
    if ds_wave is not None:
        for t in _frame_times(ds_wave, t0, t1, epoch):
            fr = hs_texture(ds_wave, t, vmax=hs_vmax, threshold=hs_threshold, bbox=bbox, max_px=hs_max_px, epoch=epoch)
            hs["frames"].append({"t": fr["t"], "image": fr["image"]})
        legends["hs"] = legend("hs", "m", hs_threshold, hs_vmax)
        credit.append("NORA3 waves")

    arrow_frames = []
    if ds_current is not None:
        for t in _frame_times(ds_current, t0, t1, epoch):
            arrow_frames.append({"t": t, "paths": arrows(ds_current, t, arrow_spacing_px, bbox=bbox, view_px=view_px,
                                                         vmax=current_vmax, names=UV["current"], epoch=epoch)})
        legends["arrows"] = legend("current", "m/s", 0.0, current_vmax)
        if "NorKyst v3 currents" not in credit:
            credit.append("NorKyst v3 currents")

    return {"particles": particles, "hs": hs, "arrows": arrow_frames, "legend": legends,
            "credit": ("MET Norway " + ", ".join(credit) + " (CC BY 4.0)") if credit else ""}
