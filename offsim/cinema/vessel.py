"""Cosmetic vessel and aircraft motion: defined interfaces (not built). Spec: docs/VISUAL_SPEC.md §5.

Rule: display-only. These functions read the validated trajectory and return a DISPLAY copy; they never write back.
`display_offset_check` must stay ≤ rules.VESSEL['display_offset_max_m'] or the render is refused.
All randomness is seeded and closed-form in t (sum of sines), so a frame renders identically every time.
"""


def heading_smooth(traj, rot_max_deg_min: float = 20.0, radius_lengths: float = 2.5, length_m: float = 76.0):
    """Per-row display heading: rate-limited turns and fillet (clothoid/Bézier) corners at waypoints instead of snaps."""
    raise NotImplementedError


def speed_profile(traj, quay_ramp_m: float = 400.0, depart_ramp_s: float = 20.0):
    """Display time-warp so vessels decelerate into quays and accelerate out; arrival/departure times unchanged."""
    raise NotImplementedError


def dp_jitter(seed: int, t: float, rms_m: float = 1.5, heading_rms_deg: float = 0.5) -> tuple[float, float, float]:
    """Station-keeping while state == 'dp' or alongside: (dx_m, dy_m, dheading_deg), 3 sines, periods 7–40 s."""
    raise NotImplementedError


def wake(path_lonlat, t: float, speed_mps: float, length_m: float):
    """Kelvin V (half-angle 19.47°) as two fading paths + centre trail; length 8–12 ship lengths; alpha ∝ speed."""
    raise NotImplementedError


def bob(hs_m: float, tp_s: float, t: float, seed: int) -> tuple[float, float, float]:
    """(heave_m, roll_deg, pitch_deg) from local Hs/Tp: heave≈0.25·Hs, roll=min(6, 1.2·Hs), pitch=min(3, 0.6·Hs);
    two incommensurate periods near Tp and 1.3·Tp. Feeds ScenegraphLayer getOrientation/getTranslation."""
    raise NotImplementedError


def heli_profile(route, t: float):
    """(lon, lat, alt_m, heading) through climb 8–10 m/s, cruise 140 kn, descent 3–5 m/s, 30 s deck hover, 100 m flare.
    The SAME phase table must drive the simulation so display and validated times agree."""
    raise NotImplementedError


def display_offset_check(validated, display) -> float:
    """INSPECTOR. Max distance (m) between validated and display positions over all frames."""
    raise NotImplementedError
