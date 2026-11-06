"""Cinematic rulebook as data. `shot_plan` (camera.py) checks storyboards against these numbers before any
render. Values marked `src` are cited; others are house rules of thumb (see docs/VISUAL_SPEC.md §4).
Change a number here, not in a storyboard."""

CAMERA = {
    "zoom_rate_max": 0.35,        # zoom levels / s (≈1.27x scale/s); target 0.15–0.25
    "zoom_rate_target": (0.15, 0.25),
    "pitch_rate_max": 10.0,       # deg / s
    "bearing_rate_orbit_max": 6.0,  # deg / s
    "bearing_rate_reveal_max": 3.0,
    "pan_rate_max": 0.6,          # screen widths / s
    "pan_rate_with_vessel_max": 0.25,
    "shot_min_s": 2.5,
    "shot_typical_s": (4.0, 8.0),
    "film_hold_in_s": 0.4,        # static frames at the very start (thumbnail/autoplay)
    "film_hold_out_s": 0.8,
    "cut_max_angular_rate": 2.0,  # deg / s; no hard cut while faster
    "cut_max_zoom_rate": 0.10,
    "crossfade_frames": (6, 10),  # when a cut must happen in motion
    "cut_bearing_jump_min": 30.0,  # 30° rule: a cut changes bearing by 0° (continuity) or ≥30°; 1–29° reads as a jump cut
    "keep_screen_direction": True,  # 180° rule: a vessel keeps its screen direction across cuts (no mirrored re-entry)
    "lead_space_frac": (0.30, 0.35),  # tracked vessel placed this far from the edge opposite its heading
    "look_ahead_s": (4.0, 6.0),
    "follow_spring_omega": (2.0, 4.0),  # rad/s, critically damped, closed form only
    "van_wijk_when": {"zoom_delta_min": 2.0, "screen_widths_min": 1.0},  # else spline
    "ease_default": "cubic_in_out",
    "ease_hero": "quint_in_out",
}

SHOT_GRAMMAR = ["establish", "descend", "follow", "event", "reveal"]  # wide z7–9 p0–30 → p50–60 → track → push/orbit → pull back
SHOTS_PER_FILM = {"30s": (5, 8), "45s": (5, 8), "60s": (6, 10)}

VESSEL = {
    "psv_rot_service_deg_min": 20.0,   # rate of turn at service speed (house start value)
    "psv_rot_manoeuvre_deg_min": 45.0,
    "turn_radius_ship_lengths": (2.0, 3.0),
    "quay_ramp_m": (300.0, 500.0),     # linear speed ramp to 0 on approach
    "depart_ramp_s": 20.0,
    "dp_rms_m": 1.5, "dp_heading_rms_deg": 0.5, "dp_periods_s": (7.0, 40.0),
    "kelvin_half_angle_deg": 19.47,    # physics
    "wake_len_ship_lengths": (8.0, 12.0),
    "heave_per_hs": 0.25, "roll_per_hs_deg": 1.2, "roll_max_deg": 6.0, "pitch_per_hs_deg": 0.6, "pitch_max_deg": 3.0,
    "display_offset_max_m": 25.0,      # cosmetic motion may never move a vessel further than this from the validated track
}

HELICOPTER = {"climb_mps": (8.0, 10.0), "cruise_kn": 140.0, "descent_mps": (3.0, 5.0), "deck_hover_s": 30.0, "flare_m": 100.0}

LOOK = {
    "sun_elevation_deg": (25.0, 45.0),  # one sun per film
    "grades": ["north-sea-steel", "golden-hour", "night-ops"],  # one grade per film, applied in ffmpeg
    "max_screen_passes": 2,              # luma.gl effects per frame on SwiftShader (vignette, tiltShift)
}
