"""2D incompressible Boussinesq flow on a vertical section. SPEC: build to this docstring.

Method: Stam (1999) "Stable Fluids": semi-Lagrangian advection, implicit diffusion, pressure projection
(Jacobi or conjugate gradient), buoyancy force f_z = g * beta * (T - T_ref) (Boussinesq). Grid NxM in metres,
solid cells from an obstacle mask (hull, superstructure, helideck, platform legs) with no-slip/no-penetration.
Inflow: log or power-law wind profile on the upwind boundary from the hour's wind speed (NORA3 10 m, scaled by
height with a cited exponent); outflow on the downwind boundary. Heat sources: turbine exhaust cells at a given
temperature and mass flow (sourced or `assumption: true`).

    class Section2D:
        def __init__(self, nx, nz, dx_m, mask, nu=1.5e-5, kappa=2.2e-5, beta=1/300, seed=0, backend="numpy"|"taichi")
        def set_inflow(self, profile)            # u(z) in m/s
        def add_heat(self, cells, temp_k)
        def step(self, dt) -> None               # CFL-limited; raises if unstable
        @property u, w, T                        # fields in SI
    def obstacle_mask(lineart_svg_or_polys, nx, nz, dx_m) -> np.ndarray[bool]

Validation required before any number is reported: lid-driven cavity (Ghia 1982 centreline) and a buoyant plume
rise check; tests in tests/test_physics.py. Display-only use (texture) may run without them, flagged in meta.
"""


class Section2D:
    def __init__(self, *a, **k):
        raise NotImplementedError("spec in offsim/physics/fluid2d.py")


def obstacle_mask(*a, **k):
    raise NotImplementedError("spec in offsim/physics/fluid2d.py")
