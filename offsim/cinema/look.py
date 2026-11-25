"""Light and colour: presets are data; sun() and ground_tint() are built (pure functions). Spec: docs/VISUAL_SPEC.md §6.

In-renderer (deck.gl, SwiftShader): LightingEffect sun + ≤2 luma.gl passes (vignette, tiltShift). luma.gl has no
bloom and no LUT pass: grading, grain and bloom happen once in ffmpeg after capture (cheaper than per-frame passes).
"""

import math
from pathlib import Path

# ffmpeg filter chains, applied once to the assembled film. Tune here; one grade per film.
GRADES = {
    "north-sea-steel": "eq=contrast=1.06:saturation=0.85:gamma=0.98,colorbalance=bs=0.04:ms=0.02:hs=-0.02,"
                       "vignette=PI/5,noise=alls=5:allf=t",
    "golden-hour": "eq=contrast=1.04:saturation=1.05,colorbalance=rs=0.03:rm=0.04:bs=-0.03,vignette=PI/5,noise=alls=4:allf=t",
    "night-ops": "eq=brightness=-0.04:contrast=1.10:saturation=0.70,colorbalance=bs=0.08:bm=0.04,vignette=PI/4,noise=alls=7:allf=t",
}
# Editorial palettes (docs/STYLE_REFERENCE.md). Colours are data; renderers and templates read them from here.
PALETTES = {
    # warm dark ground, streak greys, one hot accent, diverging field (sampled from the reference, then ours to tune)
    "section-plan": {"ground": "#331c22", "ground_deep": "#2a161a", "sea": "#16323a", "streak_lo": "#846a5d", "streak_hi": "#c9a98c",
                     "accent": "#e5a028", "ink": "#f2e9df", "muted": "#9c8a80",
                     "field_diverging": ["#4f8f9c", "#9cc3c4", "#efe3cf", "#e89a5b", "#c8442f"]},
}
# Palettes learned from the studies (coordination/reports/abhinav-*.md) and the owner's brand. Hex values are ESTIMATED BY EYE from screen
# captures, not measured pixels: tune them against saved frames (`eyes dna` palette) before treating any as exact. Roles: ground, accent
# (carries data), comparison (the other case), ink (text and line). Every palette has the same keys so a shot can switch palette by name.
def _pal(ground, deep, sea, lo, hi, accent, ink, muted, comparison, field):
    return {"ground": ground, "ground_deep": deep, "sea": sea, "streak_lo": lo, "streak_hi": hi, "accent": accent, "ink": ink,
            "muted": muted, "comparison": comparison, "field_diverging": field}


PALETTES.update({
    # AB2 / AB3 carousels: near-black, one amber, cream line, one steel blue for the comparison
    "amber-black": _pal("#0e0e10", "#08080a", "#101418", "#6b5a45", "#d8c8ab", "#e9a23b", "#efe6d2", "#8d8678", "#7fb2c9",
                        ["#3b6f8f", "#8fb8cc", "#efe6d2", "#e9a23b", "#c7452b"]),
    # AB1 Dubai reel: mid-grey ground, white massing, red network, yellow chip, steel comparison
    "grey-red-chip": _pal("#8e949b", "#767c83", "#7d8a96", "#b9bec3", "#ffffff", "#c8332b", "#151515", "#4a4f55", "#5f84a8",
                          ["#5f84a8", "#c5d3df", "#ffffff", "#f3e36b", "#c8332b"]),
    # AB4 Hamburg / AB5 Pol reels: black, neon network in amber, cyan, magenta and green
    "neon-black": _pal("#050507", "#020203", "#07090d", "#59606b", "#e8e4d8", "#ffb02e", "#f1efe8", "#7c8088", "#32c5d2",
                       ["#32c5d2", "#7fe0e6", "#f1efe8", "#ffb02e", "#d8449a"]),
    # owner brand, dark: oxblood ground, gold accent, orange comparison
    "oxblood-gold": _pal("#2a1216", "#1d0b0e", "#1b2a2e", "#7a5a4e", "#d9bfa0", "#c79a3b", "#f2e9df", "#9c8a80", "#d8602c",
                         ["#4f8f9c", "#9cc3c4", "#efe3cf", "#d8602c", "#9e2a2f"]),
    # owner brand, light: paper ground, oxblood accent, teal comparison
    "paper-oxblood": _pal("#efe9dc", "#e3dccb", "#c9d4d2", "#8c7a6c", "#2a1216", "#7a1f2b", "#2a1216", "#7d6f66", "#1f4e5f",
                          ["#1f4e5f", "#7fa5ad", "#efe9dc", "#c79a3b", "#7a1f2b"]),
    # owner brand, steel: charcoal ground, orange accent, cool grey comparison
    "charcoal-orange": _pal("#1c1d20", "#121315", "#1a2228", "#6d6a64", "#d6cfc2", "#f07a2a", "#ece7de", "#8a867e", "#8fa4b5",
                            ["#8fa4b5", "#c9d3db", "#ece7de", "#f07a2a", "#b4381e"]),
})
# bloom: split → threshold (lutyuv) → gblur → blend=screen. Kept as a recipe until a film needs it.
BLOOM_RECIPE = "split[a][b];[b]lutyuv=y='if(gt(val,200),val,0)',gblur=sigma=12[g];[a][g]blend=all_mode=screen"


# Open font (Inter 4.1, SIL OFL 1.1; licence next to the files). Rule 17. Draw with offsim.cinema.draw.Canvas.text.
_FONT_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"
FONTS = {w: str(_FONT_DIR / f"Inter-{w}.ttf") for w in ("Regular", "Medium", "SemiBold", "Bold")}


def font_path(weight: str = "Regular") -> str:
    """Path of the Inter TTF for a weight in FONTS (KeyError if unknown)."""
    return FONTS[weight]


def _smooth(a: float, b: float, x: float) -> float:
    t = min(1.0, max(0.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


def _hex(c):
    c = c.lstrip("#")
    return [int(c[i:i + 2], 16) for i in (0, 2, 4)]


def _to_hex(rgb) -> str:
    return "#" + "".join(f"{int(round(min(255.0, max(0.0, v)))):02x}" for v in rgb)


def _mix(a, b, t):
    return [x + (y - x) * t for x, y in zip(a, b)]


def solar_elevation_azimuth(time_of_day_h: float, lat: float = 60.0, doy: int = 172):
    """Solar (elevation_deg, azimuth_deg clockwise from north) for true solar time `time_of_day_h` (12 = solar noon).

    NOAA General Solar Position Calculations (simplified, https://gml.noaa.gov/grad/solcalc/solareqns.PDF):
    fractional year g = 2*pi/365*(doy-1+(h-12)/24); declination by the Fourier series of Spencer (1971) as given by NOAA;
    hour angle = 15 deg per hour from solar noon (equation of time and longitude offset ignored: "time of day" here is
    solar time, which is what the film clock needs). No refraction correction. Accurate to a fraction of a degree.
    """
    g = 2 * math.pi / 365.0 * (doy - 1 + (time_of_day_h - 12.0) / 24.0)
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g) - 0.006758 * math.cos(2 * g)
            + 0.000907 * math.sin(2 * g) - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    ha = math.radians(15.0 * (time_of_day_h - 12.0))
    la = math.radians(lat)
    sin_el = math.sin(la) * math.sin(decl) + math.cos(la) * math.cos(decl) * math.cos(ha)
    el = math.asin(max(-1.0, min(1.0, sin_el)))
    # azimuth from north, clockwise
    y = -math.sin(ha) * math.cos(decl)
    x = math.cos(la) * math.sin(decl) - math.sin(la) * math.cos(decl) * math.cos(ha)
    az = math.degrees(math.atan2(y, x)) % 360.0
    return math.degrees(el), az


def sun(time_of_day_h: float, azimuth_deg: float = 220.0, lat: float = 60.0, doy: int = None) -> dict:
    """LightingEffect params from the simulated clock (rule 11). Pure function.

    time_of_day_h: true solar time in hours (12 = solar noon); wraps modulo 24. doy: day of year (default 172 = 21 June).
    Returns dict(elevation_deg, azimuth_deg, ambient, key_color, tint, solar_azimuth_deg):
      elevation_deg      real solar elevation from solar_elevation_azimuth (negative = below the horizon)
      azimuth_deg        the *art-directed* key-light azimuth you passed (one sun per film: the shadow direction must not
                         swing across the frame); the physical azimuth is reported as solar_azimuth_deg
      ambient            0.12 (night) .. 0.55 (day) fill intensity, smooth in elevation
      key_color          hex of the key light: moonlight blue at night, warm orange at low sun, near-white at high sun
      tint               hex mood colour to multiply/overlay on the frame (blue-grey night, amber golden hour, neutral day)
    Use ground_tint(palette, elevation_deg) for the map ground colour.
    """
    doy = 172 if doy is None else int(doy)
    el, solar_az = solar_elevation_azimuth(time_of_day_h % 24.0, lat, doy)
    day = _smooth(-4.0, 20.0, el)                       # 0 night .. 1 full day
    warm = max(0.0, 1.0 - abs(el - 5.0) / 12.0) if el > -6.0 else 0.0     # golden-hour bump, peaks at 5 deg
    night_key, low_key, day_key = _hex("#7d8fb8"), _hex("#ffae6b"), _hex("#fff3e2")
    key = _mix(night_key, day_key, day)
    key = _mix(key, low_key, warm * 0.85)
    night_t, low_t, day_t = _hex("#27304a"), _hex("#e9a15d"), _hex("#f4f1ea")
    tint = _mix(_mix(night_t, day_t, day), low_t, warm * 0.7)
    return {"elevation_deg": el, "azimuth_deg": float(azimuth_deg), "ambient": 0.12 + 0.43 * day,
            "key_color": _to_hex(key), "tint": _to_hex(tint), "solar_azimuth_deg": solar_az}


def ground_tint(palette: dict, elevation: float) -> str:
    """Ground colour (hex) for a sun elevation in degrees: palette["ground"] by day, blended toward a darker blue-shifted
    night value (elevation <= -6) and a warmer value at low sun (peak ~5 deg). Rule 11. `palette` is an entry of PALETTES."""
    ground = _hex(palette["ground"])
    deep = _hex(palette.get("ground_deep", palette["ground"]))
    night = _mix([c * 0.45 for c in deep], [18, 24, 44], 0.35)
    warm_t = _mix(ground, [150, 78, 52], 0.30)
    c = _mix(night, ground, _smooth(-6.0, 12.0, elevation))
    warm = max(0.0, 1.0 - abs(elevation - 4.0) / 11.0) if elevation > -6.0 else 0.0
    return _to_hex(_mix(c, warm_t, warm * 0.8))


def grade(name: str) -> str:
    """ffmpeg -vf chain for a preset in GRADES (KeyError if unknown)."""
    return GRADES[name]
