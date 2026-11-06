"""Camera: defined interfaces (not built). Spec: docs/VISUAL_SPEC.md §4. Every function is a pure f(t[, seed]);
the renderer evaluates them inside window.draw(t). No transitions, timers or per-frame integrators.

ViewState = {"longitude", "latitude", "zoom", "pitch", "bearing"}.
Key       = {"t": seconds, **ViewState} or {"t", "fit": [[w, s], [e, n]], "pitch", "bearing"}.
"""


def ease(name: str, u: float) -> float:
    """u∈[0,1] → [0,1]. Names: linear, cubic_in_out, quint_in_out, smoothstep. Clamp u."""
    raise NotImplementedError


def camera_spline(keys: list, t: float) -> dict:
    """Centripetal Catmull-Rom (alpha 0.5) through keys on (lon, lat, zoom, pitch, bearing), eased per segment;
    velocity continuous at keys (smoothstep chains are forbidden: they stop at every key)."""
    raise NotImplementedError


def camera_fly(a: dict, b: dict, u: float) -> dict:
    """Van Wijk–Nuij smooth zoom-pan from a to b at normalised u (deck.gl FlyToInterpolator.interpolateProps, no duration).
    Use only when the move crosses ≥2 zoom levels or ≥1 screen width (rules.CAMERA['van_wijk_when'])."""
    raise NotImplementedError


def camera_follow(track_lonlat_t, t: float, lead_s: float = 5.0, omega: float = 3.0, offset: dict | None = None) -> dict:
    """Follow-cam on a vessel: target = position at t + lead_s, low-passed by a critically damped spring in closed form;
    places the vessel at rules.CAMERA['lead_space_frac'] opposite its heading."""
    raise NotImplementedError


def camera_orbit(center_lonlat, t: float, t0: float, deg_per_s: float, zoom: float, pitch: float) -> dict:
    """Orbit around a site at ≤ rules.CAMERA['bearing_rate_orbit_max']."""
    raise NotImplementedError


def shot_plan(storyboard: dict, viewport: tuple[int, int]) -> list[str]:
    """INSPECTOR. Sample each map shot's camera at 30 fps and return rule violations: zoom/pitch/bearing/pan rates,
    shot length, film holds, cuts in motion, bearing jump between consecutive shots, missing shot grammar.
    `offsim story --dry-run` will refuse a storyboard with violations once this is built."""
    raise NotImplementedError
