"""Sea surface along a section from a JONSWAP spectrum.

S(w) = alpha g^2 w^-5 exp(-1.25 (wp/w)^4) gamma^r, r = exp(-(w-wp)^2 / (2 sigma^2 wp^2)), sigma 0.07/0.09,
gamma 3.3 (JONSWAP mean, Hasselmann et al. 1973), scaled so 4*sqrt(m0) = Hs exactly. Linear superposition with
seeded random phases; deep-water dispersion w^2 = g k (finite depth: w^2 = g k tanh(k h)).
Check (tests/test_physics.py): 4*std(eta) of a long record is within 5% of Hs.
"""
from __future__ import annotations

import numpy as np

G = 9.81


def jonswap(w, hs_m, tp_s, gamma=3.3):
    w = np.asarray(w, float)
    wp = 2 * np.pi / tp_s
    sigma = np.where(w <= wp, 0.07, 0.09)
    r = np.exp(-((w - wp) ** 2) / (2 * sigma ** 2 * wp ** 2))
    s = G ** 2 * w ** -5.0 * np.exp(-1.25 * (wp / w) ** 4) * gamma ** r
    m0 = np.trapezoid(s, w)
    return s * (hs_m / 4) ** 2 / m0


def _k(w, depth_m):
    k = w ** 2 / G
    if depth_m:
        for _ in range(30):
            k = w ** 2 / (G * np.tanh(k * depth_m))
    return k


def components(hs_m, tp_s, seed=0, n=128, gamma=3.3, depth_m=None):
    wp = 2 * np.pi / tp_s
    w = np.linspace(0.4 * wp, 4.0 * wp, n)
    s = jonswap(w, hs_m, tp_s, gamma)
    a = np.sqrt(2 * s * (w[1] - w[0]))
    phi = np.random.default_rng(seed).uniform(0, 2 * np.pi, n)
    return w, _k(w, depth_m), a, phi


def surface(x_m, t_s, hs_m, tp_s, seed=0, n=128, depth_m=None):
    """Elevation eta (m) at positions x_m (array) and time t_s (scalar)."""
    w, k, a, phi = components(hs_m, tp_s, seed, n, depth_m=depth_m)
    x = np.asarray(x_m, float)[:, None]
    return (a * np.cos(k * x - w * t_s + phi)).sum(1)
