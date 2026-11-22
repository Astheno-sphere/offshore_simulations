"""Display sea surface from a JONSWAP spectrum (leaf module, numpy only).

Display only: Hs and Tp are arguments, callers pass report:weather values; nothing here edits truth.
S(w) = alpha g^2 w^-5 exp(-1.25 (wp/w)^4) gamma^r, r = exp(-(w-wp)^2 / (2 sigma^2 wp^2)), sigma 0.07 (w<=wp) / 0.09,
gamma 3.3 default (Hasselmann et al. 1973). alpha is set numerically so that 4*sqrt(m0) = Hs over the band used.
Dispersion: w^2 = g k (deep water) or w^2 = g k tanh(k h) when depth_m is given; g = 9.81 m/s2 (physics constant).
Linear superposition of N components, random phases and in-bin frequency jitter from numpy Generator(seed).
Simplifications: linear waves, one direction (no spreading), no wave-structure interaction.
"""
from __future__ import annotations

import numpy as np

G = 9.81  # m/s2, standard gravity (physics constant)
_BAND = (0.4, 4.0)  # component band as multiples of the peak angular frequency
_DENSE = 4096  # points for the numeric moment integral


def _trapz(y, x):
    return float(np.sum(0.5 * (y[1:] + y[:-1]) * np.diff(x)))


def _wavenumber(w, depth_m):
    k = w ** 2 / G
    if depth_m:
        for _ in range(50):
            k = w ** 2 / (G * np.tanh(k * depth_m))
    return k


class Sea:
    def __init__(self, hs_m, tp_s, seed=1, n_components=64, gamma=3.3, depth_m=None, direction_deg=0.0):
        if not (hs_m > 0) or not np.isfinite(hs_m):
            raise ValueError(f"hs_m must be > 0, got {hs_m!r}")
        if not (tp_s > 0) or not np.isfinite(tp_s):
            raise ValueError(f"tp_s must be > 0, got {tp_s!r}")
        if int(n_components) < 2:
            raise ValueError("n_components must be >= 2")
        if gamma < 1:
            raise ValueError("gamma must be >= 1")
        if depth_m is not None and not depth_m > 0:
            raise ValueError("depth_m must be > 0 or None")
        self.hs_m, self.tp_s, self.seed = float(hs_m), float(tp_s), seed
        self.n, self.gamma, self.depth_m = int(n_components), float(gamma), depth_m
        self.direction = np.deg2rad(direction_deg)  # single direction, no spreading (simplification)
        self.wp = 2 * np.pi / self.tp_s
        self.w_lo, self.w_hi = _BAND[0] * self.wp, _BAND[1] * self.wp
        wd = np.linspace(self.w_lo, self.w_hi, _DENSE)
        self._alpha = (self.hs_m / 4) ** 2 / _trapz(self._shape(wd), wd)  # m0 = (Hs/4)^2 exactly
        rng = np.random.default_rng(seed)
        edges = np.linspace(self.w_lo, self.w_hi, self.n + 1)
        w = edges[:-1] + rng.uniform(0, 1, self.n) * np.diff(edges)  # jitter: no periodic repeat
        self.w = w
        self.k = _wavenumber(w, depth_m)
        self.a = np.sqrt(2 * self.spectrum(w) * np.diff(edges))
        self.phi = rng.uniform(0, 2 * np.pi, self.n)

    def _shape(self, w):
        w = np.asarray(w, float)
        sigma = np.where(w <= self.wp, 0.07, 0.09)
        r = np.exp(-((w - self.wp) ** 2) / (2 * sigma ** 2 * self.wp ** 2))
        return G ** 2 * w ** -5.0 * np.exp(-1.25 * (self.wp / w) ** 4) * self.gamma ** r

    def spectrum(self, omega):
        """S(omega) in m2 s/rad, for omega > 0."""
        return self._alpha * self._shape(omega)

    def hs_from_spectrum(self):
        """4*sqrt(m0), numeric integral over the component band."""
        wd = np.linspace(self.w_lo, self.w_hi, _DENSE)
        return 4 * float(np.sqrt(_trapz(self.spectrum(wd), wd)))

    def eta(self, x, t, y=0.0):
        """Elevation (m) at x (m, array) and time t (s); waves travel along direction (default +x)."""
        x = np.asarray(x, float)
        s = x * np.cos(self.direction) + np.asarray(y, float) * np.sin(self.direction)
        out = np.zeros(s.shape)
        for a, k, w, p in zip(self.a, self.k, self.w, self.phi):
            out += a * np.cos(k * s - w * t + p)
        return out

    def transect(self, x0, x1, n, t):
        x = np.linspace(x0, x1, int(n))
        return x.astype(np.float32), self.eta(x, t).astype(np.float32)

    def grid(self, nx, ny, extent_m, t):
        """(X, Y, Z) float32 arrays of shape (ny, nx); extent_m = (Lx, Ly) or a scalar for a square. Waves go +x."""
        lx, ly = (extent_m, extent_m) if np.isscalar(extent_m) else extent_m
        xs, ys = np.linspace(0, lx, int(nx)), np.linspace(0, ly, int(ny))
        X, Y = np.meshgrid(xs, ys)
        Z = np.zeros(X.shape)
        for a, k, w, p in zip(self.a, self.k, self.w, self.phi):
            Z += a * np.cos(k * X - w * t + p)  # unidirectional along +x
        return X.astype(np.float32), Y.astype(np.float32), Z.astype(np.float32)
