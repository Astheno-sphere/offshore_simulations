"""Weather on SCREEN: defined interfaces (not built). Spec: docs/VISUAL_SPEC.md §3.

Decision: our own seeded particles, pre-integrated in Python, drawn with deck.gl TripsLayer at currentTime = t.
Fully frame-exact. GPU particle libraries (weatherlayers-gl MPL-2.0, deck.gl-community ParticleLayer) keep internal
state / own fps and are drafts-only until a byte-identical re-render test passes.
"""


def seed_particles(bbox: tuple, n: int, seed: int, land=None):
    """n start points, Poisson-disc in open water (land mask), deterministic for seed."""
    raise NotImplementedError


def integrate_streamlines(field, seeds, t0: float, t1: float, dt_s: float = 60.0, life_s: float = 1800.0, speedup: float = 1.0):
    """RK4 through a time-varying u/v field (wind or current) → trips [{path, timestamps, speed}] for TripsLayer.
    Particles respawn on a fixed schedule (life_s, staggered by index) — never randomly per frame."""
    raise NotImplementedError


def hs_texture(ds, t: float, cmap: str = "offsim-sea", vmin: float = 0.0, vmax: float = 6.0):
    """Wave height at t as an RGBA PNG (data URL) + bounds for BitmapLayer; colour ramp fixed per film."""
    raise NotImplementedError


def arrows(ds, t: float, spacing_px: int = 64):
    """Current/wind arrows on a screen-regular grid as PathLayer segments (CAD style, length ∝ speed)."""
    raise NotImplementedError


def legend(kind: str, units: str, vmin: float, vmax: float) -> dict:
    """Overlay legend spec (colour ramp, units, source line 'MET Norway NORA3, CC BY 4.0')."""
    raise NotImplementedError
