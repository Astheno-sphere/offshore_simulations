"""Whole-panel 2D incompressible flow with a switchable subject (docs/VISUAL_GRAMMAR.md section 5).

The world (platform, terrain, hull, deck) is solid cells of the grid, not a picture over a free stream. A `Subject` is the one
switchable thing the film is about: extra solid cells (a fuselage, a building), a momentum source (rotor downwash), a heat
source, a porous drag region (a tree crown). The solver keeps running through the switch: the after state is computed from the
before state, never cross-faded.

Method (display grade, same family as fluid2d.Section2D but with a direct pressure solve):
  * MAC grid. u[k, j] at x = k dx (k = 0..nx, k = 0 the inlet face), w[i, l] at z = l dx (l = 0 floor .. nz lid); p at cells.
  * advection: semi-Lagrangian with an RK2 backtrace and a MacCormack correction clamped to the local extrema (second order,
    little numerical diffusion, so a wake can shed); scalar T advected the same way.
  * no-slip: a face touching a solid cell carries zero velocity. Floor and lid are free-slip floor; the top is open (p = 0 ghost) or a free-slip lid.
    x = nx is a free outflow (p = 0 in the ghost cell). Inflow u(z, t) = boundary-layer profile * (1 + I n(z, t)); n is band-limited and seeded, so a
    run is deterministic for a given seed.
  * pressure: sparse Poisson matrix on the fluid cells, factorised once per geometry (LU); the divergence after projection is
    at round-off, so mass is conserved to solver precision (tests/test_intervention.py states the tolerance).
  * forces: momentum source (m/s2), Darcy drag (semi-implicit, 1/s), Boussinesq buoyancy g beta (T - Tref).

    s = PanelSolver(nx, nz, dx, world_mask, inflow_profile, seed=1)
    s.set_subject(Subject("S-92", solid=..., accel=(fx, fz)))
    s.schedule(t_s, None)                # at t_s the subject is removed (or replaced); the solver keeps stepping
    s.step(dt)                           # raises if CFL > 2
    uc, wc = s.cell_velocity()           # cell-centred m/s
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import ndimage as ndi
from scipy import sparse
from scipy.sparse.linalg import splu

from offsim.physics.masks import fill_pockets

G = 9.81


@dataclass
class Subject:
    """The one switchable thing. Every part is optional and defined on cells of the panel grid (nx, nz)."""
    name: str = "subject"
    solid: np.ndarray | None = None          # bool: extra solid cells (no-slip)
    accel: tuple | None = None               # (fx, fz) m/s2 per cell: a momentum source (rotor downwash)
    heat: tuple | None = None                # (bool mask, temp_k): cells held at temp_k
    porous: tuple | None = None              # (bool mask, k_per_s): a = -k u inside (a tree crown, a hedge)
    meta: dict = field(default_factory=dict)


def _bil(f, x, z):
    """Bilinear sample of f at index coordinates (x, z), clamped to the array; also returns the 4-point min and max."""
    nx, nz = f.shape
    x = np.clip(x, 0.0, nx - 1.000001)
    z = np.clip(z, 0.0, nz - 1.000001)
    i0, k0 = x.astype(np.intp), z.astype(np.intp)
    fx, fz = x - i0, z - k0
    a, b, c, d = f[i0, k0], f[i0 + 1, k0], f[i0, k0 + 1], f[i0 + 1, k0 + 1]
    val = (a * (1 - fx) + b * fx) * (1 - fz) + (c * (1 - fx) + d * fx) * fz
    return val, np.minimum(np.minimum(a, b), np.minimum(c, d)), np.maximum(np.maximum(a, b), np.maximum(c, d))


class PanelSolver:
    def __init__(self, nx, nz, dx_m, world, inflow, seed=1, turbulence=0.08, beta=1 / 300.0, t_ref=288.0,
                 confinement=0.0, top="open", nu=0.0, smag=0.0):
        self.top_open = (top == "open")
        self.nx, self.nz, self.dx = int(nx), int(nz), float(dx_m)
        self.world = np.asarray(world, bool).copy()
        assert self.world.shape == (self.nx, self.nz)
        self.inflow = np.asarray(inflow, float).copy()             # u(z) at cell heights, m/s
        self.turbulence, self.beta, self.t_ref, self.confinement = float(turbulence), float(beta), float(t_ref), float(confinement)
        self.nu, self.smag = float(nu), float(smag)
        self.seed = int(seed)
        self.time = 0.0
        self.inflow_gain = 1.0                                       # spin-up knob: scales the inflow (1 = the forcing itself)
        self.subject: Subject | None = None
        self._switches: list = []
        self.u = np.zeros((nx + 1, nz))
        self.w = np.zeros((nx, nz + 1))
        self.T = np.full((nx, nz), t_ref)
        self.meta = {"grade": "display", "method": "MAC grid, semi-Lagrangian + MacCormack, direct Poisson, no-slip masks"}
        rng = np.random.default_rng(self.seed)
        k = 7                                                      # inflow perturbation: k travelling sinusoids in (z, t)
        self._pert = {"f": rng.uniform(0.04, 0.45, k), "lam": rng.uniform(6.0, 45.0, k), "ph": rng.uniform(0, 2 * np.pi, k),
                      "ph2": rng.uniform(0, 2 * np.pi, k), "a": rng.uniform(0.5, 1.0, k)}
        self._pert["a"] = self._pert["a"] / np.sqrt(0.5 * np.sum(self._pert["a"] ** 2))      # unit std
        self._zc = (np.arange(nz) + 0.5) * self.dx
        gx, gz = np.meshgrid(np.arange(nx + 1), np.arange(nz), indexing="ij")
        self._gu = (gx.astype(float), gz.astype(float) + 0.5)       # u positions in cell units
        gx, gz = np.meshgrid(np.arange(nx), np.arange(nz + 1), indexing="ij")
        self._gw = (gx.astype(float) + 0.5, gz.astype(float))
        gx, gz = np.meshgrid(np.arange(nx), np.arange(nz), indexing="ij")
        self._gc = (gx.astype(float) + 0.5, gz.astype(float) + 0.5)
        self._rebuild()
        self.u[:] = self._u_in(0.0)[None, :]
        self._close_faces()
        self._project()

    # ------------------------------------------------------------------------------------------------ geometry
    def schedule(self, t_s, subject):
        """At time t_s switch the subject to `subject` (None = remove it). The solver keeps running."""
        self._switches.append((float(t_s), subject))
        self._switches.sort(key=lambda p: p[0])

    def set_subject(self, subject):
        self.subject = subject
        self._rebuild()
        self._close_faces()
        self._project()

    def _rebuild(self):
        nx, nz = self.nx, self.nz
        solid = self.world.copy()
        if self.subject is not None and self.subject.solid is not None:
            solid |= self.subject.solid
        self.solid = fill_pockets(solid, open_top=self.top_open)
        s = self.solid
        self.uo = np.zeros((nx + 1, nz), bool)
        self.uo[1:nx] = ~s[:-1] & ~s[1:]
        self.uo[nx] = ~s[nx - 1]
        self.uo[0] = ~s[0]
        self.wo = np.zeros((nx, nz + 1), bool)
        self.wo[:, 1:nz] = ~s[:, :-1] & ~s[:, 1:]
        if self.top_open:
            self.wo[:, nz] = ~s[:, nz - 1]                         # open top: far-field pressure (p = 0 ghost cell)
        fl = ~s
        idx = -np.ones((nx, nz), np.intp)
        idx[fl] = np.arange(int(fl.sum()))
        self._idx, self._nfl = idx, int(fl.sum())
        rows, cols, vals = [], [], []
        diag = np.zeros(self._nfl)
        # open faces: left (not at the inlet), right (to the ghost p=0 at nx), bottom/top between fluid cells
        for (di, dj) in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            ii, jj = np.nonzero(fl)
            ni, nj = ii + di, jj + dj
            inside = (ni >= 0) & (ni < nx) & (nj >= 0) & (nj < nz)
            c = idx[ii, jj]
            if di == 1:                                            # outflow face: Dirichlet ghost
                out = ni == nx
                np.add.at(diag, c[out], -1.0)
            if dj == 1 and self.top_open:
                np.add.at(diag, c[nj == nz], -1.0)
            ok = inside.copy()
            ok[inside] &= fl[ni[inside], nj[inside]]
            np.add.at(diag, c[ok], -1.0)
            rows.append(c[ok]); cols.append(idx[ni[ok], nj[ok]]); vals.append(np.ones(int(ok.sum())))
        rows.append(np.arange(self._nfl)); cols.append(np.arange(self._nfl)); vals.append(diag)
        A = sparse.csc_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(self._nfl, self._nfl))
        self._lu = splu(-A)
        self._fluid_mask = fl

    def _close_faces(self):
        self.u *= self.uo
        self.w *= self.wo
        self.u[0] = self._u_in(self.time) * self.uo[0]

    # ------------------------------------------------------------------------------------------------ inflow
    def _u_in(self, t):
        p = self._pert
        arg = 2 * np.pi * (p["f"][:, None] * t + self._zc[None, :] / p["lam"][:, None]) + p["ph"][:, None]
        n = (p["a"][:, None] * np.sin(arg)).sum(0)
        return np.maximum(self.inflow * self.inflow_gain * (1.0 + self.turbulence * n), 0.0)

    # ------------------------------------------------------------------------------------------------ projection
    def divergence(self):
        d = (self.u[1:] - self.u[:-1] + self.w[:, 1:] - self.w[:, :-1]) / self.dx
        d[self.solid] = 0.0
        return d

    def _project(self):
        D = (self.u[1:] - self.u[:-1] + self.w[:, 1:] - self.w[:, :-1])
        rhs = D[self._fluid_mask] * self.dx            # sum (p_nb - p_c) = dx * D   (D = dx * div)
        p_f = self._lu.solve(-rhs)
        p = np.zeros((self.nx, self.nz))
        p[self._fluid_mask] = p_f
        du = np.zeros_like(self.u)
        du[1:self.nx] = (p[1:] - p[:-1]) / self.dx
        du[self.nx] = (0.0 - p[self.nx - 1]) / self.dx
        self.u -= du * self.uo
        self.u[0] = self._u_in(self.time) * self.uo[0]
        dw = np.zeros_like(self.w)
        dw[:, 1:self.nz] = (p[:, 1:] - p[:, :-1]) / self.dx
        if self.top_open:
            dw[:, self.nz] = (0.0 - p[:, self.nz - 1]) / self.dx
        self.w -= dw * self.wo
        self.p = p

    # ------------------------------------------------------------------------------------------------ advection
    def _vel_at(self, x, z):
        return _bil(self.u, x, z - 0.5)[0], _bil(self.w, x - 0.5, z)[0]

    def _trace(self, gx, gz, h):
        """Backtrace by h (cell units per unit velocity) with an RK2 midpoint: returns the foot points in cell units."""
        u1, w1 = self._vel_at(gx, gz)
        u2, w2 = self._vel_at(gx - 0.5 * h * u1, gz - 0.5 * h * w1)
        return gx - h * u2, gz - h * w2

    def _advect(self, f, g, off, dt):
        h = dt / self.dx
        x0, z0 = self._trace(g[0], g[1], h)
        fwd, mn, mx = _bil(f, x0 - off[0], z0 - off[1])
        x1, z1 = self._trace(g[0], g[1], -h)                       # forward-then-back error estimate (MacCormack)
        # back-substitute: sample the forward result at the forward foot points
        back = _bil(fwd, x1 - off[0], z1 - off[1])[0]
        return np.clip(fwd + 0.5 * (f - back), mn, mx)

    # ------------------------------------------------------------------------------------------------ step
    def cell_velocity(self):
        return 0.5 * (self.u[1:] + self.u[:-1]), 0.5 * (self.w[:, 1:] + self.w[:, :-1])

    def cfl(self, dt):
        return float(max(np.abs(self.u).max(), np.abs(self.w).max())) * dt / self.dx

    def step(self, dt):
        while self._switches and self.time >= self._switches[0][0] - 1e-12:
            _, sub = self._switches.pop(0)
            self.set_subject(sub)
        if self.cfl(dt) > 2.0:
            raise ValueError(f"CFL {self.cfl(dt):.2f} > 2; reduce dt")
        sub = self.subject
        u = self._advect(self.u, self._gu, (0.0, 0.5), dt)
        w = self._advect(self.w, self._gw, (0.5, 0.0), dt)
        T = self._advect(self.T, self._gc, (0.5, 0.5), dt)
        self.u, self.w, self.T = u, w, T
        if sub is not None and sub.heat is not None:
            self.T[sub.heat[0]] = sub.heat[1]
        # forces
        if sub is not None and sub.accel is not None:
            fx, fz = sub.accel
            self.u[1:self.nx] += dt * 0.5 * (fx[1:] + fx[:-1])
            self.w[:, 1:self.nz] += dt * 0.5 * (fz[:, 1:] + fz[:, :-1])
        if sub is not None and sub.porous is not None:
            m, k = sub.porous
            kk = np.where(m, float(k), 0.0)
            self.u[1:self.nx] /= 1.0 + dt * 0.5 * (kk[1:] + kk[:-1])
            self.w[:, 1:self.nz] /= 1.0 + dt * 0.5 * (kk[:, 1:] + kk[:, :-1])
        if self.beta:
            dT = self.T - self.t_ref
            if np.any(dT):
                self.w[:, 1:self.nz] += dt * G * self.beta * 0.5 * (dT[:, 1:] + dT[:, :-1])
        if self.confinement:
            self._confine(dt)
        if self.nu or self.smag:
            self._diffuse(dt)
        self.time += dt
        self._close_faces()
        self._project()

    def _diffuse(self, dt):
        """Explicit viscous term: constant nu plus a Smagorinsky eddy viscosity (Cs dx)^2 |S|, the display-grade stand-in for the
        turbulent mixing a 2D grid at dx = 0.4 m cannot resolve. Closed faces stay at zero (no-slip); edges are zero-gradient."""
        uc, wc = self.cell_velocity()
        nu = np.full((self.nx, self.nz), self.nu)
        if self.smag:
            dudx = np.gradient(uc, self.dx, axis=0)
            dwdz = np.gradient(wc, self.dx, axis=1)
            shear = np.gradient(uc, self.dx, axis=1) + np.gradient(wc, self.dx, axis=0)
            S = np.sqrt(2 * (dudx ** 2 + dwdz ** 2) + shear ** 2)
            nu = nu + (self.smag * self.dx) ** 2 * S
        nu = np.minimum(nu, 0.2 * self.dx ** 2 / dt)       # explicit-diffusion stability
        nu_u = np.empty_like(self.u)
        nu_u[1:self.nx] = 0.5 * (nu[1:] + nu[:-1])
        nu_u[0], nu_u[self.nx] = nu[0], nu[-1]
        nu_w = np.empty_like(self.w)
        nu_w[:, 1:self.nz] = 0.5 * (nu[:, 1:] + nu[:, :-1])
        nu_w[:, 0], nu_w[:, self.nz] = nu[:, 0], nu[:, -1]
        for f, nf, mask, interior in ((self.u, nu_u, self.uo, (slice(1, self.nx), slice(None))), (self.w, nu_w, self.wo, (slice(None), slice(1, self.nz)))):
            p = np.pad(f, 1, mode="edge")
            lap = (p[2:, 1:-1] + p[:-2, 1:-1] + p[1:-1, 2:] + p[1:-1, :-2] - 4 * f) / self.dx ** 2
            f[interior] += (dt * nf * lap)[interior] * mask[interior]

    def _confine(self, dt):
        """Vorticity confinement (Fedkiw 2001) restores small eddies the grid would smear; eps = self.confinement."""
        uc, wc = self.cell_velocity()
        om = (np.gradient(wc, self.dx, axis=0) - np.gradient(uc, self.dx, axis=1))
        a = np.abs(om)
        gx, gz = np.gradient(a, self.dx, axis=0), np.gradient(a, self.dx, axis=1)
        n = np.hypot(gx, gz) + 1e-9
        nx_, nz_ = gx / n, gz / n
        fx, fz = nz_ * om, -nx_ * om
        fx[self.solid] = 0
        fz[self.solid] = 0
        e = self.confinement * self.dx
        self.u[1:self.nx] += dt * e * 0.5 * (fx[1:] + fx[:-1])
        self.w[:, 1:self.nz] += dt * e * 0.5 * (fz[:, 1:] + fz[:, :-1])

    def run(self, seconds, dt):
        for _ in range(int(round(seconds / dt))):
            self.step(dt)

    # ------------------------------------------------------------------------------------------------ diagnostics
    def net_flux(self):
        """(inflow, outflow) in m2/s through the open inlet and outlet faces."""
        return float((self.u[0] * self.uo[0]).sum() * self.dx), float((self.u[self.nx] * self.uo[self.nx]).sum() * self.dx)

    def max_divergence(self):
        """Largest |div u| (1/s) over fluid cells: mass conservation residual."""
        return float(np.abs(self.divergence()).max())
