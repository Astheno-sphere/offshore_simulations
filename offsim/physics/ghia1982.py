"""Ghia, Ghia & Shin (1982) lid-driven cavity benchmark, Tables I-II.

Reference: U. Ghia, K. N. Ghia, C. T. Shin, "High-Re solutions for incompressible flow
using the Navier-Stokes equations and a multigrid method", J. Comput. Phys. 48(3),
387-411, 1982, doi:10.1016/0021-9991(82)90058-4. Unit square cavity, lid speed U = 1,
u along the vertical centreline (x = 0.5) and v along the horizontal centreline
(y = 0.5), normalised by U, at Re = 100, 400, 1000 (129x129 grids).

Values transcribed from the tables as reproduced by FlowDeck
(https://www.flow-deck.com/validation/benchmarks/lid-driven-cavity.html, retrieved
2026-11-08; the page's own model results are CC BY 4.0, the reference values are
Ghia et al.'s as cited there). Cross-checked against the values quoted in
shaia/CFD docs/validation/lid-driven-cavity.md (u(0.5, 0.5) = -0.20581,
u_min = -0.21090, v(0.5, 0.5) = 0.05454 at Re = 100 — all match).

KNOWN MISPRINT (excluded from comparisons): Ghia's v = -0.23827 at x = 0.9063,
Re = 400 breaks the smooth profile and is widely regarded as a misprint; it is
stored here as None so no comparison can silently use it.
"""
from __future__ import annotations

REYNOLDS = (100, 400, 1000)

# y/L -> (u_Re100, u_Re400, u_Re1000) along the vertical centreline x = 0.5.
U_TABLE = [
    (1.0000, 1.00000, 1.00000, 1.00000),
    (0.9766, 0.84123, 0.75837, 0.65928),
    (0.9688, 0.78871, 0.68439, 0.57492),
    (0.9609, 0.73722, 0.61756, 0.51117),
    (0.9531, 0.68717, 0.55892, 0.46604),
    (0.8516, 0.23151, 0.29093, 0.33304),
    (0.7344, 0.00332, 0.16256, 0.18719),
    (0.6172, -0.13641, 0.02135, 0.05702),
    (0.5000, -0.20581, -0.11477, -0.06080),
    (0.4531, -0.21090, -0.17119, -0.10648),
    (0.2813, -0.15662, -0.32726, -0.27805),
    (0.1719, -0.10150, -0.24299, -0.38289),
    (0.1016, -0.06434, -0.14612, -0.29730),
    (0.0703, -0.04775, -0.10338, -0.22220),
    (0.0625, -0.04192, -0.09266, -0.20196),
    (0.0547, -0.03717, -0.08186, -0.18109),
    (0.0000, 0.00000, 0.00000, 0.00000),
]

# x/L -> (v_Re100, v_Re400, v_Re1000) along the horizontal centreline y = 0.5.
V_TABLE = [
    (1.0000, 0.00000, 0.00000, 0.00000),
    (0.9688, -0.05906, -0.12146, -0.21388),
    (0.9609, -0.07391, -0.15663, -0.27669),
    (0.9531, -0.08864, -0.19254, -0.33714),
    (0.9453, -0.10313, -0.22847, -0.39188),
    (0.9063, -0.16914, None, -0.51550),  # Re=400 value is the known misprint
    (0.8594, -0.22445, -0.44993, -0.42665),
    (0.8047, -0.24533, -0.38598, -0.31966),
    (0.5000, 0.05454, 0.05188, 0.02526),
    (0.2344, 0.17527, 0.30174, 0.32235),
    (0.2266, 0.17507, 0.30203, 0.33075),
    (0.1563, 0.16077, 0.28124, 0.37095),
    (0.0938, 0.12317, 0.22965, 0.32627),
    (0.0781, 0.10890, 0.20920, 0.30353),
    (0.0703, 0.10091, 0.19713, 0.29012),
    (0.0625, 0.09233, 0.18360, 0.27485),
    (0.0000, 0.00000, 0.00000, 0.00000),
]


def centreline(re, component="u"):
    """(positions, values) for Re in (100, 400, 1000); component 'u' or 'v'.
    The known-misprint point is dropped (not zeroed)."""
    if re not in REYNOLDS:
        raise ValueError(f"Ghia tables exist only for Re in {REYNOLDS}, got {re}")
    j = REYNOLDS.index(re) + 1
    table = U_TABLE if component == "u" else V_TABLE
    pos = [row[0] for row in table if row[j] is not None]
    val = [row[j] for row in table if row[j] is not None]
    return pos, val
