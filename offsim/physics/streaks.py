"""Streak texture: many short advected tracer tails coloured by a scalar (the "brushed" look).

Seeded uniformly in fluid cells (fixed seed -> identical frames), advected RK2 through (u, w), tails of the last
K positions, respawned when they leave the domain or hit a solid. Drawn as alpha-faded polylines on an RGBA layer.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import map_coordinates


def seed(mask, n, seed=0):
    rng = np.random.default_rng(seed)
    nx, nz = mask.shape
    p = np.c_[rng.uniform(0, nx - 1, n * 2), rng.uniform(0, nz - 1, n * 2)]
    ok = ~mask[p[:, 0].astype(int), p[:, 1].astype(int)]
    return p[ok][:n], rng


def _vel(p, u, w):
    c = [p[:, 0], p[:, 1]]
    return np.c_[map_coordinates(u, c, order=1, mode="nearest"), map_coordinates(w, c, order=1, mode="nearest")]


def advect(p, u, w, dx_m, dt, mask, rng):
    """One RK2 step in grid units; particles leaving the domain or entering solid cells respawn at x=0."""
    k1 = _vel(p, u, w) * dt / dx_m
    k2 = _vel(p + 0.5 * k1, u, w) * dt / dx_m
    q = p + k2
    nx, nz = u.shape
    bad = (q[:, 0] < 0) | (q[:, 0] > nx - 1) | (q[:, 1] < 0) | (q[:, 1] > nz - 1)
    bad |= mask[np.clip(q[:, 0].astype(int), 0, nx - 1), np.clip(q[:, 1].astype(int), 0, nz - 1)]
    if bad.any():
        q[bad] = np.c_[rng.uniform(0, 3, bad.sum()), rng.uniform(0, nz - 1, bad.sum())]
    return q, bad


def trace(mask, u, w, dx_m, dt, n=6000, tail=14, seed_=0):
    """Tails (n, tail, 2) in grid units through a frozen field; broken where a particle respawned."""
    p, rng = seed(mask, n, seed_)
    tails = np.full((len(p), tail, 2), np.nan)
    for k in range(tail):
        tails[:, k] = p
        p, bad = advect(p, u, w, dx_m, dt, mask, rng)
        tails[bad, : k + 1] = np.nan
    return tails


def draw(tails, scalar, cmap, size, grid_shape, alpha=0.45, width=1):
    """tails in grid units -> RGBA image (size px). scalar: (n,) in 0..1; cmap: callable -> rgb 0..1;
    grid_shape: (nx, nz) of the field, so x maps to the image width."""
    W, H = size
    s = W / grid_shape[0]
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for tl, v in zip(tails, scalar):
        pts = [(x * s, H - z * s) for x, z in tl if np.isfinite(x)]
        if len(pts) < 2:
            continue
        r, g, b = (np.array(cmap(v)[:3]) * 255).astype(int)
        for i in range(len(pts) - 1):
            a = int(255 * alpha * (i + 1) / len(pts))
            d.line([pts[i], pts[i + 1]], fill=(r, g, b, a), width=width)
    return layer
