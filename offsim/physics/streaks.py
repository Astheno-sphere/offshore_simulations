"""Streak texture: thousands of short advected tracer tails, the "brushed silk" look. SPEC.

Particles seeded uniformly (blue-noise) in the fluid domain, advected by RK2 through (u, w) each frame, tail of
the last K positions kept, respawned when they leave or age out (fixed seed -> byte-identical frames). Each tail
is drawn as an alpha-faded polyline coloured by a scalar (temperature, speed) through the look's colour map.
The same integrator serves the plan map (wind field) as offsim/weather/visual.py streamlines; share code.

    def seed(mask, n, seed=0) -> np.ndarray
    def advect(p, u, w, dx_m, dt, tail) -> np.ndarray     # (n, K, 2)
    def draw(tails, scalar, cmap, size, alpha=0.35) -> PIL.Image | np.ndarray
"""


def seed(*a, **k):
    raise NotImplementedError("spec in offsim/physics/streaks.py")


advect = draw = seed
