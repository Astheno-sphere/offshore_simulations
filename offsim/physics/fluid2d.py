"""2D incompressible Boussinesq flow on a vertical section (x along the section, z up).

Method: Stam (1999) "Stable Fluids": semi-Lagrangian advection (bilinear), pressure projection by Jacobi
iterations on the Poisson equation, buoyancy f_z = g * beta * (T - T_ref) (Boussinesq). Explicit molecular
viscosity is omitted: at section grid scales (dx ~ 0.5 m) the scheme's numerical diffusion is far larger than
air's nu = 1.5e-5 m2/s, so adding it would change nothing visible; this is a display-grade solver (meta flag)
until a validation test against a published case is added for any number it reports.

Boundaries: solid cells from `mask` (True = solid) get zero velocity; upwind (x=0) inflow u(z) from the wind
profile; downwind (x=end) zero-gradient outflow; top free-slip; bottom (sea) handled by the mask.

    sec = Section2D(nx, nz, dx_m, mask)
    sec.set_inflow(u_of_z)            # m/s per row
    sec.add_heat(cells_mask, temp_k)  # held at temp_k (exhaust)
    sec.step(dt)                      # raises if CFL > 1
    sec.u, sec.w, sec.T               # SI fields, shape (nx, nz)
"""
from __future__ import annotations

import numpy as np
from scipy.ndimage import map_coordinates

G = 9.81


class Section2D:
    def __init__(self, nx, nz, dx_m, mask=None, beta=1 / 300, t_ref=288.0, jacobi=60):
        self.nx, self.nz, self.dx = nx, nz, float(dx_m)
        self.mask = np.zeros((nx, nz), bool) if mask is None else mask.astype(bool)
        self.u = np.zeros((nx, nz))
        self.w = np.zeros((nx, nz))
        self.T = np.full((nx, nz), t_ref)
        self.p = np.zeros((nx, nz))
        self.beta, self.t_ref, self.jacobi = beta, t_ref, jacobi
        self.inflow = np.zeros(nz)
        self.heat = None
        self.time = 0.0
        self.meta = {"grade": "display", "method": "Stam 1999 stable fluids, Boussinesq buoyancy"}
        gx, gz = np.meshgrid(np.arange(nx), np.arange(nz), indexing="ij")
        self._gx, self._gz = gx.astype(float), gz.astype(float)

    def set_inflow(self, profile):
        self.inflow = np.asarray(profile, float)
        self.u[:] = self.inflow[None, :]
        self._bc()

    def add_heat(self, cells, temp_k):
        self.heat = (cells.astype(bool), float(temp_k))

    def _advect(self, f, dt):
        x = self._gx - dt * self.u / self.dx
        z = self._gz - dt * self.w / self.dx
        return map_coordinates(f, [x, z], order=1, mode="nearest")

    def _bc(self):
        self.u[0, :] = self.inflow
        self.w[0, :] = 0
        self.u[-1, :] = self.u[-2, :]
        self.w[-1, :] = self.w[-2, :]
        self.w[:, -1] = 0
        self.u[self.mask] = 0
        self.w[self.mask] = 0

    def divergence(self):
        # backward differences; with the forward-difference gradient in _project, div(grad p) is the 5-point Laplacian,
        # so the projection is consistent (u at i is effectively the face i+1/2, as on a MAC grid)
        d = np.zeros_like(self.u)
        d[1:-1, 1:-1] = ((self.u[1:-1, 1:-1] - self.u[:-2, 1:-1]) + (self.w[1:-1, 1:-1] - self.w[1:-1, :-2])) / self.dx
        d[self.mask] = 0
        return d

    def _project(self):
        div = self.divergence()
        p = self.p
        fluid = ~self.mask
        for _ in range(self.jacobi):
            pn = p.copy()
            pn[1:-1, 1:-1] = (p[2:, 1:-1] + p[:-2, 1:-1] + p[1:-1, 2:] + p[1:-1, :-2] - div[1:-1, 1:-1] * self.dx ** 2) / 4
            pn[~fluid] = 0
            pn[-1, :] = 0                    # outflow: p = 0
            pn[0, :] = pn[1, :]
            pn[:, 0] = pn[:, 1]
            pn[:, -1] = pn[:, -2]
            p = pn
        self.p = p
        self.u[1:-1, 1:-1] -= (p[2:, 1:-1] - p[1:-1, 1:-1]) / self.dx
        self.w[1:-1, 1:-1] -= (p[1:-1, 2:] - p[1:-1, 1:-1]) / self.dx

    def step(self, dt):
        vmax = float(np.max(np.hypot(self.u, self.w))) or 1e-9
        if vmax * dt / self.dx > 1.0:
            raise ValueError(f"CFL {vmax * dt / self.dx:.2f} > 1; reduce dt")
        if self.heat is not None:
            self.T[self.heat[0]] = self.heat[1]
        u, w, T = self._advect(self.u, dt), self._advect(self.w, dt), self._advect(self.T, dt)
        self.u, self.w, self.T = u, w, T
        self.w += dt * G * self.beta * (self.T - self.t_ref)
        self.T[0, :] = self.t_ref
        self._bc()
        self._project()
        self._bc()
        self.time += dt


def obstacle_mask(polys, nx, nz, dx_m):
    """Rasterise polygons [(x_m, z_m), ...] (hull, superstructure) into a solid mask (nx, nz)."""
    from matplotlib.path import Path
    xs = (np.arange(nx) + 0.5) * dx_m
    zs = (np.arange(nz) + 0.5) * dx_m
    gx, gz = np.meshgrid(xs, zs, indexing="ij")
    pts = np.c_[gx.ravel(), gz.ravel()]
    m = np.zeros(nx * nz, bool)
    for poly in polys:
        m |= Path(poly).contains_points(pts)
    return m.reshape(nx, nz)


def wind_profile(z_m, u10, alpha=0.11):
    """Power-law wind profile u(z) = u10 (z/10)^alpha; alpha 0.11 is the offshore value in IEC 61400-3
    (cited as the default; override per scenario). z clipped at 0.5 m."""
    return u10 * (np.maximum(z_m, 0.5) / 10.0) ** alpha
