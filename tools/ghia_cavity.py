"""Lid-driven cavity validation of offsim.physics.fluid2d against Ghia et al. 1982.

The section solver (Stam 1999 stable fluids, Boussinesq) is display-grade by its own
docstring until a validation test against a published case exists for any number it
reports. This is that test: a unit-square cavity, top lid at U = 1, other walls
no-slip, explicit viscosity nu = U*L/Re, steady centreline profiles compared with
Ghia Tables I-II (offsim/physics/ghia1982.py).

Two honest limits, stated up front:
- The solver has no viscosity term of its own: the diffusion step here is explicit
  FTCS, added in the CavitySection subclass (the base solver is untouched). The
  scheme's own numerical diffusion is still present on top of nu, so the effective
  Re is >= the nominal one — the comparison measures the sum, not nu alone.
- The lid velocity is imposed on the top row of cells (cell-centred scheme); Ghia's
  values are nodal. Profiles are linearly interpolated onto Ghia's node positions.

No pass threshold is asserted anywhere: the repo has none, and inventing one would
turn a measurement into a verdict. The JSON records the errors; UPGRADE-REPORT.md
states what they mean.

    PYTHONPATH=. python tools/ghia_cavity.py --re 100 400 1000 --n 65 --out proof/ghia-cavity.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from offsim.physics.fluid2d import Section2D
from offsim.physics.ghia1982 import centreline


class CavitySection(Section2D):
    """Section2D in a lid-driven cavity: unit square, lid u = 1, no-slip walls,
    explicit viscosity nu, Neumann pressure on all sides (no outflow)."""

    def __init__(self, n, nu, jacobi=60):
        super().__init__(n, n, 1.0 / n, jacobi=jacobi)
        self.nu = float(nu)
        self.u[:, :] = 0.0
        self.w[:, :] = 0.0

    def _bc(self):
        self.u[0, :] = 0.0
        self.u[-1, :] = 0.0
        self.u[:, 0] = 0.0
        self.w[0, :] = 0.0
        self.w[-1, :] = 0.0
        self.w[:, 0] = 0.0
        self.u[:, -1] = 1.0  # lid (corners included, Ghia convention)
        self.w[:, -1] = 0.0
        self.u[self.mask] = 0.0
        self.w[self.mask] = 0.0

    def _project(self):
        div = self.divergence()
        p = self.p
        for _ in range(self.jacobi):
            pn = p.copy()
            pn[1:-1, 1:-1] = (p[2:, 1:-1] + p[:-2, 1:-1] + p[1:-1, 2:] + p[1:-1, :-2]
                              - div[1:-1, 1:-1] * self.dx ** 2) / 4
            pn[0, :] = pn[1, :]      # Neumann on all sides (no outflow leg)
            pn[-1, :] = pn[-2, :]
            pn[:, 0] = pn[:, 1]
            pn[:, -1] = pn[:, -2]
            p = pn
        self.p = p
        self.u[1:-1, 1:-1] -= (p[2:, 1:-1] - p[1:-1, 1:-1]) / self.dx
        self.w[1:-1, 1:-1] -= (p[1:-1, 2:] - p[1:-1, 1:-1]) / self.dx

    def _diffuse(self, f, dt):
        lap = np.zeros_like(f)
        lap[1:-1, 1:-1] = (f[2:, 1:-1] + f[:-2, 1:-1] + f[1:-1, 2:] + f[1:-1, :-2]
                           - 4.0 * f[1:-1, 1:-1]) / self.dx ** 2
        out = f.copy()
        out[1:-1, 1:-1] = f[1:-1, 1:-1] + dt * self.nu * lap[1:-1, 1:-1]
        return out

    def step(self, dt):
        vmax = float(np.max(np.hypot(self.u, self.w))) or 1e-9
        if vmax * dt / self.dx > 1.0:
            raise ValueError(f"CFL {vmax * dt / self.dx:.2f} > 1; reduce dt")
        u, w = self._advect(self.u, dt), self._advect(self.w, dt)
        self.u, self.w = self._diffuse(u, dt), self._diffuse(w, dt)
        self._bc()
        self._project()
        self._bc()
        self.time += dt


def _profiles(sec):
    """(u along vertical centreline, v along horizontal centreline) at cell centres."""
    xs = (np.arange(sec.nx) + 0.5) * sec.dx
    zs = (np.arange(sec.nz) + 0.5) * sec.dx
    i0 = int(np.argmin(np.abs(xs - 0.5)))
    k0 = int(np.argmin(np.abs(zs - 0.5)))
    return xs, sec.u[i0, :], zs, sec.w[:, k0]


def _errors(pos_sim, val_sim, pos_ref, val_ref):
    """Interpolate the simulated profile onto Ghia's positions; max/RMS error on
    interior points only (the two wall endpoints are boundary values, not results)."""
    interp = np.interp(pos_ref, pos_sim, val_sim)
    err = np.abs(interp - np.asarray(val_ref))
    interior = np.ones(len(pos_ref), bool)
    interior[0] = interior[-1] = False
    return {"max_abs": float(err[interior].max()), "rms": float(np.sqrt((err[interior] ** 2).mean())),
            "n_points": int(interior.sum())}


def run_cavity(re, n=65, t_end=60.0, jacobi=60, steady_tol=1e-4, check_every=5.0):
    """Run one Re to steady state (or t_end); return the comparison dict."""
    nu = 1.0 / float(re)  # U = 1, L = 1
    sec = CavitySection(n, nu, jacobi=jacobi)
    dx = sec.dx
    dt = 0.9 * min(dx / 1.0, dx * dx / (4.0 * nu))
    prev = None
    steady_at = None
    t = 0.0
    while t < t_end:
        target = min(t + check_every, t_end)
        while t < target:
            sec.step(dt)
            t += dt
        _, u_c, _, v_c = _profiles(sec)
        cur = np.concatenate([u_c, v_c])
        if prev is not None and np.max(np.abs(cur - prev)) < steady_tol:
            steady_at = round(t, 3)
            break
        prev = cur
    xs, u_c, zs, v_c = _profiles(sec)
    out = {"re": re, "n": n, "nu": nu, "dx": dx, "dt": dt, "t_end": t,
           "steady_at": steady_at, "jacobi": jacobi,
           "u_min": float(u_c.min()), "u_min_y": float(xs[int(np.argmin(u_c))]),
           "v_min": float(v_c.min()), "v_max": float(v_c.max())}
    for comp, pos_sim, val_sim in (("u", xs, u_c), ("v", zs, v_c)):
        pos_ref, val_ref = centreline(re, comp)
        out[f"{comp}_err"] = _errors(pos_sim, val_sim, pos_ref, val_ref)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--re", type=int, nargs="+", default=[100])
    ap.add_argument("--n", type=int, default=65)
    ap.add_argument("--t-end", type=float, default=60.0)
    ap.add_argument("--jacobi", type=int, default=60)
    ap.add_argument("--out", default="proof/ghia-cavity.json")
    a = ap.parse_args()
    results = [run_cavity(re, n=a.n, t_end=a.t_end, jacobi=a.jacobi) for re in a.re]
    for r in results:
        print(f"Re={r['re']:>5} n={r['n']} t={r['t_end']:.1f} steady_at={r['steady_at']} "
              f"u_err max={r['u_err']['max_abs']:.4f} rms={r['u_err']['rms']:.4f} | "
              f"v_err max={r['v_err']['max_abs']:.4f} rms={r['v_err']['rms']:.4f} | "
              f"u_min={r['u_min']:.4f} @ y={r['u_min_y']:.3f}")
    p = Path(a.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"solver": "offsim.physics.fluid2d Section2D + explicit FTCS viscosity (CavitySection)",
                             "reference": "Ghia, Ghia & Shin 1982, JCP 48:387-411, Tables I-II",
                             "note": "No pass threshold exists in the repo; errors are reported, not judged.",
                             "results": results}, indent=1))
    print("wrote", p)


if __name__ == "__main__":
    main()
