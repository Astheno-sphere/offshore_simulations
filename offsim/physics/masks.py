"""Obstacle masks for the panel solver: world geometry (metres) -> boolean solid cells.

    m = polys_to_mask(polys, nx, nz, dx_m, origin=(x0_m, z0_m))      # filled polygons (shapely geometries or point lists)
    m = strokes_to_mask(polylines, width_m, nx, nz, dx_m, origin)    # thin members (lattice tubes) thickened to a width
    m = fill_pockets(m)                                              # fluid not connected to the outflow column becomes solid

Cell (i, j) has its centre at x0 + (i + 0.5) dx, z0 + (j + 0.5) dx. A cell is solid when its centre is inside the shape,
so a feature thinner than one cell can vanish: callers thicken thin members with `strokes_to_mask(width >= dx)`.
"""
from __future__ import annotations

import numpy as np
import shapely
from scipy import ndimage as ndi
from shapely.geometry import LineString, Polygon


def _centres(nx, nz, dx_m, origin):
    xs = origin[0] + (np.arange(nx) + 0.5) * dx_m
    zs = origin[1] + (np.arange(nz) + 0.5) * dx_m
    gx, gz = np.meshgrid(xs, zs, indexing="ij")
    return gx, gz


def _geom(g):
    if hasattr(g, "geom_type"):
        return g
    return Polygon(list(g))


def polys_to_mask(polys, nx, nz, dx_m, origin=(0.0, 0.0)):
    gx, gz = _centres(nx, nz, dx_m, origin)
    m = np.zeros((nx, nz), bool)
    for p in polys:
        g = _geom(p)
        if g.is_empty:
            continue
        minx, miny, maxx, maxy = g.bounds
        i0 = max(0, int((minx - origin[0]) / dx_m) - 1)
        i1 = min(nx, int((maxx - origin[0]) / dx_m) + 2)
        k0 = max(0, int((miny - origin[1]) / dx_m) - 1)
        k1 = min(nz, int((maxy - origin[1]) / dx_m) + 2)
        if i1 <= i0 or k1 <= k0:
            continue
        m[i0:i1, k0:k1] |= shapely.contains_xy(g, gx[i0:i1, k0:k1], gz[i0:i1, k0:k1])
    return m


def strokes_to_mask(polylines, width_m, nx, nz, dx_m, origin=(0.0, 0.0)):
    """Polylines thickened to `width_m` (a lattice member drawn as a hidden-line edge pair or a single edge)."""
    geoms = [LineString(p).buffer(width_m / 2.0, cap_style=2) for p in polylines if len(p) >= 2]
    return polys_to_mask(geoms, nx, nz, dx_m, origin)


def fill_pockets(mask, outflow_col=-1, open_top=False):
    """Fluid cells (4-connected) that do not reach the outflow column (or the open top row) are filled: a closed pocket has no
    pressure reference and no flow can enter it, so it is solid for the solver (reported by the caller)."""
    lab, n = ndi.label(~mask)
    if n == 0:
        return mask.copy()
    keep = set(np.unique(lab[outflow_col, :])) - {0}
    if open_top:
        keep |= set(np.unique(lab[:, -1])) - {0}
    out = mask | ((lab > 0) & ~np.isin(lab, list(keep)))
    return out
