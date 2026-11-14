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


class FieldStreaks:
    """Full-panel streaks for the intervention shot (docs/VISUAL_GRAMMAR.md section 5, rule 4).

    n tracers are seeded everywhere outside solid cells, advected with the solver's velocity (RK2, sub-stepped so that no
    sub-step is longer than `max_step` cells, which makes it impossible to hop over a solid cell), and keep their last `tail`
    positions: one position per frame, so a streak's drawn length is proportional to the speed it moves at. A streak dies when
    a sub-step would enter a solid cell, when it leaves the panel, or by age (probability `age_out` per frame); dead streaks are
    re-seeded in the free cells that currently hold no streak first (so the field cannot develop voids), else uniformly.

        fs = FieldStreaks(solid, dx_m, n=9000, tail=12, seed=3)
        fs.advance(u_face, w_face, dt)       # u_face (nx+1, nz), w_face (nx, nz+1): the PanelSolver arrays
        fs.hist                              # (n, tail, 2) positions in cell units, NaN where not yet drawn
        fs.measure()                         # {"cover": share of free coarse cells holding a streak, "static": share not moving}
    """

    def __init__(self, solid, dx_m, n=9000, tail=12, seed=3, cover_cell_m=1.2, age_out=0.012, static_px=0.01, px_per_m=9.0,
                 max_step=0.6, stride=1):
        self.solid = np.asarray(solid, bool)
        self.nx, self.nz = self.solid.shape
        self.dx, self.n, self.tail = float(dx_m), int(n), int(tail)
        self.rng = np.random.default_rng(seed)
        self.age_out, self.static_px, self.px_per_m, self.max_step = float(age_out), float(static_px), float(px_per_m), float(max_step)
        self.cover_cells = max(1, int(round(cover_cell_m / self.dx)))
        self.p = self._uniform(self.n)
        self.hist = np.full((self.n, self.tail, 2), np.nan)
        self.disp = np.zeros(self.n)                           # last frame displacement, cell units
        self.alive_frames = np.zeros(self.n, int)
        self.stride, self._frame = max(1, int(stride)), 0       # a tail point is kept every `stride` frames (a slow panel remembers longer)
        self._dead = np.zeros(self.n, bool)

    def set_solid(self, solid):
        """A new geometry (the subject switched). Streaks inside the new solid die and are re-seeded."""
        self.solid = np.asarray(solid, bool)
        i, k = self._ij(self.p)
        bad = self.solid[i, k]
        self._reseed(bad)

    def _ij(self, p):
        return np.clip(p[:, 0].astype(int), 0, self.nx - 1), np.clip(p[:, 1].astype(int), 0, self.nz - 1)

    def _uniform(self, m):
        out = np.empty((0, 2))
        while len(out) < m:
            q = np.c_[self.rng.uniform(0, self.nx, m * 2), self.rng.uniform(0, self.nz, m * 2)]
            i, k = self._ij(q)
            out = np.r_[out, q[~self.solid[i, k]]]
        return out[:m]

    def _empty_cells_seeds(self, m):
        """Positions in coarse cells that hold no streak head, so re-seeding fills the voids first."""
        c = self.cover_cells
        gx, gz = -(-self.nx // c), -(-self.nz // c)
        i, k = self._ij(self.p)
        occ = np.zeros((gx, gz), bool)
        ok = ~self._dead
        occ[i[ok] // c, k[ok] // c] = True
        free = ~self.solid
        pad = np.zeros((gx * c, gz * c), bool)
        pad[:self.nx, :self.nz] = free
        cell_free = pad.reshape(gx, c, gz, c).any(axis=(1, 3))
        holes = np.argwhere(cell_free & ~occ)
        if len(holes) == 0:
            return None
        pick = holes[self.rng.integers(0, len(holes), m)]
        q = (pick + self.rng.random((m, 2))) * c
        q[:, 0] = np.clip(q[:, 0], 0, self.nx - 1e-3)
        q[:, 1] = np.clip(q[:, 1], 0, self.nz - 1e-3)
        i, k = self._ij(q)
        good = ~self.solid[i, k]
        return q[good]

    def _reseed(self, dead):
        m = int(dead.sum())
        if m == 0:
            return
        self._dead[dead] = True
        holes = self._empty_cells_seeds(m)
        new = np.empty((m, 2))
        nh = 0 if holes is None else min(len(holes), m)
        if nh:
            new[:nh] = holes[:nh]
        if nh < m:
            new[nh:] = self._uniform(m - nh)
        self.p[dead] = new
        self.hist[dead] = np.nan
        self.disp[dead] = 0.0
        self.alive_frames[dead] = 0
        self._dead[dead] = False

    @staticmethod
    def _vel(p, u, w):
        from offsim.physics.panel2d import _bil
        return _bil(u, p[:, 0], p[:, 1] - 0.5)[0], _bil(w, p[:, 0] - 0.5, p[:, 1])[0]

    def advance(self, u, w, dt):
        """Advance one frame: the position after `dt` is appended to every tail. u, w: the solver's face arrays."""
        h = dt / self.dx
        ux, uz = self._vel(self.p, u, w)
        nsub = int(np.ceil(max(float(np.hypot(ux, uz).max()) * h, 1e-9) / self.max_step))
        nsub = max(1, min(nsub, 12))
        q = self.p.copy()
        dead = np.zeros(self.n, bool)
        hs = h / nsub
        for _ in range(nsub):
            a, b = self._vel(q, u, w)
            mid = q + 0.5 * hs * np.c_[a, b]
            a2, b2 = self._vel(mid, u, w)
            nq = q + hs * np.c_[a2, b2]
            out = (nq[:, 0] < 0) | (nq[:, 0] >= self.nx - 1e-3) | (nq[:, 1] < 0) | (nq[:, 1] >= self.nz - 1e-3)
            i, k = self._ij(nq)
            hit = self.solid[i, k] | out
            im, km = self._ij(0.5 * (q + nq))
            hit |= self.solid[im, km]
            dead |= hit
            q = np.where(hit[:, None], q, nq)
        disp = np.hypot(*(q - self.p).T)
        if self._frame % self.stride == 0:
            self.hist = np.roll(self.hist, 1, axis=1)
        self._frame += 1
        self.hist[:, 0] = q
        self.hist[dead, 0] = np.nan
        self.p = q
        self.disp = disp
        self.alive_frames += 1
        dead |= self.rng.random(self.n) < self.age_out
        dead |= disp * self.dx * self.px_per_m < self.static_px      # a streak that does not move is frozen texture: it dies and is re-seeded
        self._reseed(dead)

    def drawn(self):
        """Mask of streaks with at least two tail points (drawable)."""
        return np.isfinite(self.hist[:, 1, 0]) & np.isfinite(self.hist[:, 0, 0])

    def measure(self):
        """Field coverage (share of free coarse cells touched by a drawn tail) and static share (drawn streaks whose
        last-frame displacement is under `static_px` pixels at `px_per_m`)."""
        c = self.cover_cells
        gx, gz = -(-self.nx // c), -(-self.nz // c)
        d = self.drawn()
        pts = self.hist[d].reshape(-1, 2)
        pts = pts[np.isfinite(pts[:, 0])]
        i = np.clip(pts[:, 0].astype(int), 0, self.nx - 1)
        k = np.clip(pts[:, 1].astype(int), 0, self.nz - 1)
        occ = np.zeros((gx, gz), bool)
        occ[i // c, k // c] = True
        pad = np.zeros((gx * c, gz * c), bool)
        pad[:self.nx, :self.nz] = ~self.solid
        free_frac = pad.reshape(gx, c, gz, c).mean(axis=(1, 3))
        cell_free = free_frac >= 0.5                           # a coarse cell counts when at least half of it is free
        cover = float((occ & cell_free).sum() / max(cell_free.sum(), 1))
        px = self.disp[d] * self.dx * self.px_per_m
        static = float((px < self.static_px).mean()) if d.any() else 1.0
        return {"cover": cover, "static": static, "n_drawn": int(d.sum()), "free_cells": int(cell_free.sum())}
