"""Light and colour: defined (presets are data; functions not built). Spec: docs/VISUAL_SPEC.md §6.

In-renderer (deck.gl, SwiftShader): LightingEffect sun + ≤2 luma.gl passes (vignette, tiltShift). luma.gl has no
bloom and no LUT pass: grading, grain and bloom happen once in ffmpeg after capture (cheaper than per-frame passes).
"""

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
    "section-plan": {"ground": "#331c22", "ground_deep": "#2a161a", "streak_lo": "#846a5d", "streak_hi": "#c9a98c",
                     "accent": "#e5a028", "ink": "#f2e9df", "muted": "#9c8a80",
                     "field_diverging": ["#4f8f9c", "#9cc3c4", "#efe3cf", "#e89a5b", "#c8442f"]},
}
# bloom: split → threshold (lutyuv) → gblur → blend=screen. Kept as a recipe until a film needs it.
BLOOM_RECIPE = "split[a][b];[b]lutyuv=y='if(gt(val,200),val,0)',gblur=sigma=12[g];[a][g]blend=all_mode=screen"


def sun(time_of_day_h: float, azimuth_deg: float = 220.0) -> dict:
    """LightingEffect params: ambient + directional colour/intensity for elevation 25–45° (one sun per film)."""
    raise NotImplementedError


def grade(name: str) -> str:
    """ffmpeg -vf chain for a preset in GRADES (KeyError if unknown)."""
    return GRADES[name]
