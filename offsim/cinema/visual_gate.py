"""Visual gate: the machine judges its own frames (docs/STYLE_REFERENCE.md "Visual gate", SYSTEM_PLAN section 4 row Visual).

    r = inspect(img_or_path, spec=None)          # measure one rendered frame (PIL image, ndarray or path) -> dict
    ok, reasons = passes(r, strict=False)        # reasons = ["<rule>: <what was measured vs the limit>", ...]
    with capture_text() as texts:                # optional: record every text draw the renderer makes (skia Canvas.text and
        img = render_something()                 #   PIL ImageDraw.text), so contrast, type scale and margins use the film's
    r = inspect(img, {"text": texts})            #   own text metadata instead of guessing from pixels
    ok, why = compare(frame, golden, tol=0.35)   # structural regression against a committed reference frame

Rules (ids are what `reasons` start with). HARD rules fail the gate always; SOFT rules fail it only with strict=True and are
otherwise returned in report["warnings"]. Every threshold lives in GATE_SPEC with its source: a number from
docs/STYLE_REFERENCE.md (rule numbers) or a measurement of the golden frames in tests/golden/ (tests/golden/make_goldens.py
prints the table). Nothing here is tuned to make a failing frame pass: a frame that fails is a finding.

    edges      HARD  edge density (Sobel, fraction of pixels on an edge), whole frame and main panel, inside a band: below =
                     empty, above = mush
    strokes    HARD  median equivalent width of the strong linework and type (coverage-weighted, so a 0.6 px
                     antialiased hairline measures 0.6) must reach the minimum at the delivered size
    palette    HARD  share of pixels farther than a palette-derived tolerance from the palette gamut (declared colours and
                     every blend of two of them: antialiasing and alpha stay inside)
    accent     HARD  accent-dominant pixels above the cap (an accent that floods the frame is not an accent); SOFT below the floor
    contrast   HARD  WCAG 2.x ratio of every recorded text box vs the colour behind it >= 4.5; without text metadata the
                     per-region luminance ratio is computed and reported as SOFT
    type_scale SOFT  distinct text sizes (the methods line, the smallest group at the bottom, not counted) <= 4 (rule 17 says 3,
                     the soft limit); HARD above `max_hard`
    margins    HARD  text boxes and ink inside the safe area; ink touching the frame edge = clipped. Bleed boxes (a full-width
                     panel by design) are exempt for ink, never for text
    balance    HARD  an empty half (top, bottom, left, right) of the ink; SOFT: sparse cells of the 3 x 3 ink grid

What it cannot judge: whether the picture is right (physics, labels, numbers), whether geometry is correct (a rotor on the
ground passes), taste, colour-blind legibility, motion. It sees one frame at a time.
"""
from __future__ import annotations

import contextlib
import copy
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi
from scipy.spatial import cKDTree

from offsim.cinema.look import PALETTES

HARD, SOFT = "hard", "soft"
AW = 480                                   # analysis width in px: every density below is measured on a 480 px wide copy

# ----------------------------------------------------------------------------------------------------- spec as data
# Numbers marked G come from the golden frames (tests/golden/*.png, table printed by tests/golden/make_goldens.py);
# R17 / R12 / R6 are docs/STYLE_REFERENCE.md rules; W is WCAG 2.x; D is a definition of a measuring instrument.
GATE_SPEC = {
    "palette_name": "section-plan",
    "edges": {
        "sobel_tau": 0.03,                 # D: a step of 3 L* (of 100) between neighbours is an edge pixel
        "panel": [0.0, 0.17, 1.0, 0.75],   # D: main panel box (fractions x0 y0 x1 y1): below the header, above the deck/methods
        "overall": [0.050, 0.374],         # G: [0.5 x lowest (findings 0.0997), 2 x highest (map 0.1871)] over the three goldens
        "in_panel": [0.043, 0.374],        # G: same factors on the main-panel measure (lowest findings 0.0870, highest map 0.1871)
        "src": "golden frames: band = [0.5 x the lowest, 2 x the highest] over the three goldens (section, map, findings)",
    },
    "strokes": {
        "bg_window": 11,                   # D: surround = grey opening / closing of L* with an 11 px window (strokes narrower than that; wider = fills)
        "strong_frac": 0.25,               # D: stroke ink = at least 25 % of the palette ink-vs-ground contrast against its surround
        "min_median_px": 0.75,             # CAD rule 4: a line under 0.75 px on screen is dropped (invisible); G: the full-size reference frames measure 0.90-1.45
        "preview_of": None,                # when the frame is a reduced preview of a delivered width, scale the minimum by w/preview_of
        "src": "STYLE_REFERENCE CAD rule 4 (0.75 px visibility floor), rules 2 and 12 (weights 2.4 / 1.3 / 0.8, hairlines 0.6 px); golden "
               "measurement (equivalent width 0.90-1.45 px at 1080 wide). Brief V1 said 1 px: the references measure 0.90-0.98 on muted type, so 1 px would fail them",
    },
    "palette": {
        "max_off_share": 0.05,             # G: golden frames measure 0.5-0.8 %; 5 % is the allowed band
        "tol_scale": 0.5,                  # tolerance = tol_scale x median nearest-neighbour Lab distance between palette colours
        "tol_floor": 3.0,                  # D: never tighter than 3 Delta E (just-noticeable difference ~2.3)
        "extra_colors": [],                # extra declared colours (hex) beyond PALETTES + vessel fills/strokes + finding states
        "src": "tolerance from the palette's own spread (brief V1); share limit from goldens",
    },
    "accent": {
        "min_share": 0.001, "max_share": 0.08,
        "src": "max: brief V1 and rule 6 (one hot accent). min: half the lowest golden (0.21 %); the brief's 1 % floor does not hold for any reference frame (0.2-0.4 %: one accent word, markers, a line)",
    },
    "contrast": {
        "min_ratio": 4.5, "src": "WCAG 2.x AA, normal text",
        "region_grid": [6, 8], "region_edge_min": 0.01,
        "textured_l_std": 3.0,             # D: robust (MAD) L* spread of the ring around a text box above this = textured field (streaks, map): warning only
    },
    "type_scale": {
        "max_soft": 4, "merge_px": 0.75, "methods_y_min": 0.55,
        "src": "rule 17 (<= 3 sizes plus the methods line; brief V1 flags above 4); SOFT because section.py draws 9 sizes today",
    },
    "margins": {
        "safe": 0.03, "ink_band_share": 0.004, "clip_px": 1, "ink_de": 6.0, "bleed": [],
        "src": "G: every furniture element of the findings golden sits >= 3.2 % from the edge (kicker 44/1350, margin 56/1080) and "
               "its margin band holds 0.0 % ink (0.4 % allowed for antialiasing); EBU R95 action-safe 3.5 % is the broadcast "
               "reference, 3 % is the feed limit",
    },
    "balance": {
        "min_half_share": 0.13, "thin_cell_ratio": 0.2, "max_thin_cells": 3,
        "src": "G: smallest half share of the section/findings goldens is 0.27 (findings, text is left-aligned), halved with margin; map golden 0.15 (coast on one side) thirded; thin cells 0/2/0 on the goldens, 3 allowed",
    },
}
# per kind: panel box / bleed boxes / bands measured on the matching golden
KINDS = {
    "section": {"edges": {"panel": [0.0, 0.17, 1.0, 0.75]}, "margins": {"bleed": [[0.0, 0.17, 1.0, 0.43]]}},   # sea section is full-bleed (section.py: y 236..573 of 1350)
    "map": {"edges": {"panel": [0.0, 0.0, 1.0, 1.0]}, "margins": {"bleed": [[0.0, 0.0, 1.0, 1.0]]}, "balance": {"min_half_share": 0.05, "max_thin_cells": 9},
            "type_scale": {"max_soft": 9}},      # a panel inside the section frame: balance, bleed and type scale are judged on the composed frame
    "findings": {"edges": {"panel": [0.0, 0.17, 1.0, 0.75]}},
}


def merge_spec(base: dict, over: dict | None) -> dict:
    """Deep-merge overrides into a copy of base. Unknown top-level or nested keys raise KeyError (a typo is a refusal)."""
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if k not in out:
            raise KeyError(f"unknown visual spec key {k!r}; have {sorted(out)}")
        if isinstance(out[k], dict) and isinstance(v, dict):
            for kk, vv in v.items():
                if kk not in out[k]:
                    raise KeyError(f"unknown visual spec key {k}.{kk}; have {sorted(out[k])}")
                out[k][kk] = vv
        else:
            out[k] = v
    return out


def spec_for(kind=None, over=None) -> dict:
    base = merge_spec(GATE_SPEC, {})
    if kind:
        if kind not in KINDS:
            raise KeyError(f"unknown frame kind {kind!r}; have {sorted(KINDS)}")
        base = merge_spec(base, KINDS[kind])
    return merge_spec(base, over)


# ----------------------------------------------------------------------------------------------------- colour
def _hex(c):
    c = c.lstrip("#")
    return [int(c[i:i + 2], 16) for i in (0, 2, 4)]


def srgb_to_linear(a):
    a = np.asarray(a, float) / 255.0
    return np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)


def rel_luminance(rgb):
    lin = srgb_to_linear(rgb)
    return lin[..., 0] * 0.2126 + lin[..., 1] * 0.7152 + lin[..., 2] * 0.0722


def wcag_ratio(rgb1, rgb2) -> float:
    a, b = float(rel_luminance(rgb1)), float(rel_luminance(rgb2))
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


_M = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750], [0.0193339, 0.1191920, 0.9503041]])
_WHITE = np.array([0.95047, 1.0, 1.08883])


def rgb_to_lab(rgb):
    xyz = srgb_to_linear(rgb) @ _M.T / _WHITE
    f = np.where(xyz > 216 / 24389, np.cbrt(xyz), (24389 / 27 * xyz + 16) / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], axis=-1)


def _load(img) -> np.ndarray:
    if isinstance(img, (str, Path)):
        img = Image.open(img)
    if isinstance(img, Image.Image):
        img = img.convert("RGB")
        return np.asarray(img, dtype=np.uint8)
    a = np.asarray(img)
    if a.ndim != 3 or a.shape[2] not in (3, 4):
        raise ValueError("frame must be an RGB image or HxWx3 array")
    return a[..., :3].astype(np.uint8)


def _analysis(rgb: np.ndarray) -> np.ndarray:
    h, w = rgb.shape[:2]
    if w == AW:
        return rgb
    im = Image.fromarray(rgb)
    return np.asarray(im.resize((AW, max(1, round(h * AW / w))), Image.BOX if w > AW else Image.BICUBIC))


# ----------------------------------------------------------------------------------------------------- palette
def palette_members(spec) -> dict:
    """name -> hex of every declared colour: the named palette, the vessel line-art tables, finding state colours, extras."""
    pal = PALETTES[spec["palette_name"]]
    out = {k: v for k, v in pal.items() if isinstance(v, str)}
    for i, v in enumerate(pal.get("field_diverging", [])):
        out[f"field{i}"] = v
    try:
        from offsim.cinema.vessel_lineart import FILLS, STROKES
        out.update({f"fill_{k}": v for k, v in FILLS.items()})
        out.update({f"stroke_{k}": v for k, v in STROKES.items()})
    except Exception:                                      # pragma: no cover
        pass
    out.update({"grid": "#4a3236", "land": "#432629", "house_fill": "#4a2b2d", "state_unload": "#e0c7ad", "state_dp": "#a78466",
                "state_load": "#c9a98c", "state_sail": "#846a5d"})
    out.update({f"extra{i}": c for i, c in enumerate(spec["palette"]["extra_colors"])})
    return out


def palette_tolerance(members: dict, spec) -> float:
    lab = rgb_to_lab(np.array([_hex(c) for c in members.values()], float))
    d = np.linalg.norm(lab[:, None] - lab[None], axis=-1)
    np.fill_diagonal(d, np.inf)
    nn = d.min(axis=1)
    nn = nn[nn > 0.5]                                       # near-duplicate declared colours do not define the spread
    return max(float(spec["palette"]["tol_floor"]), float(spec["palette"]["tol_scale"] * np.median(nn)))


def _gamut_points(members: dict) -> np.ndarray:
    cols = np.array([_hex(c) for c in members.values()], float)
    pts = [cols]
    ts = np.linspace(0.1, 0.9, 9)[:, None, None]
    i, j = np.triu_indices(len(cols), 1)
    pts.append((cols[i][None] * (1 - ts) + cols[j][None] * ts).reshape(-1, 3))
    return rgb_to_lab(np.concatenate(pts))


def palette_stats(rgb: np.ndarray, spec) -> dict:
    members = palette_members(spec)
    tol = palette_tolerance(members, spec)
    tree = cKDTree(_gamut_points(members))
    flat = rgb.reshape(-1, 3)
    key = (flat[:, 0].astype(np.uint32) << 16) | (flat[:, 1].astype(np.uint32) << 8) | flat[:, 2]
    uniq, inv, cnt = np.unique(key, return_inverse=True, return_counts=True)
    u_rgb = np.stack([(uniq >> 16) & 255, (uniq >> 8) & 255, uniq & 255], axis=-1)
    u_lab = rgb_to_lab(u_rgb)
    dist, _ = tree.query(u_lab)
    off = float(cnt[dist > tol].sum() / cnt.sum())
    acc = np.array(_hex(PALETTES[spec["palette_name"]]["accent"]), float)
    acc_lab = rgb_to_lab(acc)
    others = rgb_to_lab(np.array([_hex(c) for k, c in members.items() if k != "accent"], float))
    acc_tol = 0.5 * float(np.min(np.linalg.norm(others - acc_lab, axis=1)))
    acc_share = float(cnt[np.linalg.norm(u_lab - acc_lab, axis=1) <= acc_tol].sum() / cnt.sum())
    worst = np.argsort(-np.where(dist > tol, cnt, 0))[:3]
    off_colors = [("#%02x%02x%02x" % tuple(u_rgb[k]), round(float(cnt[k] / cnt.sum()), 4)) for k in worst if dist[k] > tol]
    return {"off_share": off, "tolerance_de": tol, "accent_share": acc_share, "accent_tol_de": acc_tol, "off_colors": off_colors,
            "n_members": len(members)}


# ----------------------------------------------------------------------------------------------------- edges, ink
def _box_px(box, w, h):
    return int(round(box[0] * w)), int(round(box[1] * h)), max(int(round(box[2] * w)), int(round(box[0] * w)) + 1), max(int(round(box[3] * h)), int(round(box[1] * h)) + 1)


def edge_map(rgb_a: np.ndarray, tau: float):
    L = rgb_to_lab(rgb_a)[..., 0] / 100.0
    gx = ndi.sobel(L, axis=1, mode="nearest") / 8.0         # 1/8 normalises the 3x3 Sobel so a one-pixel step of height s gives s/2
    gy = ndi.sobel(L, axis=0, mode="nearest") / 8.0
    return np.hypot(gx, gy) > tau


def edge_stats(rgb: np.ndarray, spec) -> dict:
    a = _analysis(rgb)
    e = edge_map(a, spec["edges"]["sobel_tau"])
    h, w = e.shape
    x0, y0, x1, y1 = _box_px(spec["edges"]["panel"], w, h)
    return {"overall": float(e.mean()), "in_panel": float(e[y0:y1, x0:x1].mean())}


def ink_mask(rgb_a: np.ndarray, spec) -> np.ndarray:
    pal = PALETTES[spec["palette_name"]]
    grounds = rgb_to_lab(np.array([_hex(pal["ground"]), _hex(pal.get("ground_deep", pal["ground"]))], float))
    lab = rgb_to_lab(rgb_a)
    d = np.min(np.linalg.norm(lab[:, :, None, :] - grounds[None, None], axis=-1), axis=-1)
    return d > spec["margins"]["ink_de"]


def balance_stats(rgb: np.ndarray, spec) -> dict:
    ink = ink_mask(_analysis(rgb), spec)
    h, w = ink.shape
    total = float(ink.sum())
    halves = {"top": ink[: h // 2].sum(), "bottom": ink[h // 2:].sum(), "left": ink[:, : w // 2].sum(), "right": ink[:, w // 2:].sum()}
    if total == 0:
        return {"ink_fraction": 0.0, "halves": {k: 0.0 for k in halves}, "cells": [[0.0] * 3 for _ in range(3)], "thin_cells": 9, "min_half": 0.0}
    cells = np.array([[ink[r * h // 3:(r + 1) * h // 3, c * w // 3:(c + 1) * w // 3].mean() for c in range(3)] for r in range(3)])
    mean = cells.mean()
    shares = {k: float(v / total) for k, v in halves.items()}
    return {"ink_fraction": float(ink.mean()), "halves": shares, "min_half": min(shares.values()), "cells": cells.round(4).tolist(),
            "thin_cells": int((cells < spec["balance"]["thin_cell_ratio"] * mean).sum()) if mean > 0 else 9}


# ----------------------------------------------------------------------------------------------------- strokes
def stroke_stats(rgb: np.ndarray, spec) -> dict:
    """Equivalent stroke widths of the strong linework and type. A pixel is stroke ink when it differs from its surround
    (L* minus its grey opening for light strokes, its grey closing for dark ones; / 100) by at least `strong_frac` of the palette's ink-vs-ground contrast (so faint grid lines,
    streak textures and fills' soft edges are not judged here; the edges rule sees them); dark-on-light and light-on-dark
    are separate. Its width is min(horizontal run, vertical run) where a run's width is the *sum of coverage* across it
    (coverage = contrast / ink-vs-ground contrast, <= 1), so an antialiased 0.6 px line measures 0.6 whatever its pixel phase
    (0.5 + 0.1 + ... splits sum to the same), not 1 or 2."""
    s = spec["strokes"]
    pal = PALETTES[spec["palette_name"]]
    ref = abs(float(rgb_to_lab(np.array(_hex(pal["ink"]), float))[0] - rgb_to_lab(np.array(_hex(pal["ground"]), float))[0])) / 100.0
    L = rgb_to_lab(rgb)[..., 0] / 100.0
    win = (int(s["bg_window"]),) * 2
    opened, closed = ndi.grey_opening(L, size=win), ndi.grey_closing(L, size=win)       # surround of light / dark strokes
    widths = []
    for sign in (1.0, -1.0):
        d = np.clip(L - opened, 0, None) if sign > 0 else np.clip(closed - L, 0, None)
        mask = d >= s["strong_frac"] * ref
        mask &= ndi.uniform_filter(mask.astype(float), size=win) < 0.5                  # a stroke is the minority of its neighbourhood (the gaps between dense lines are not strokes)
        if mask.sum() < 20:
            continue
        cov = np.clip(d / ref, 0, 1) * mask
        parts = []
        for struct in ([[0, 0, 0], [1, 1, 1], [0, 0, 0]], [[0, 1, 0], [0, 1, 0], [0, 1, 0]]):
            lab, n = ndi.label(mask, structure=struct)
            parts.append(np.bincount(lab.ravel(), weights=cov.ravel(), minlength=n + 1)[lab])
        widths.append(np.minimum(parts[0], parts[1])[mask])
    if not widths:
        return {"median_px": 0.0, "p10_px": 0.0, "thin_share": 1.0, "n_ink_px": 0}
    w = np.concatenate(widths)
    return {"median_px": float(np.median(w)), "p10_px": float(np.percentile(w, 10)), "thin_share": float((w < 0.75).mean()), "n_ink_px": int(w.size)}


# ----------------------------------------------------------------------------------------------------- text metadata
def _color_rgb(c, alpha=None):
    if c is None:
        return None
    if isinstance(c, str):
        h = c.lstrip("#")
        v = [int(h[i:i + 2], 16) for i in range(0, 6, 2)]
        a = int(h[6:8], 16) / 255 if len(h) == 8 else 1.0
    else:
        v = [int(x) for x in list(c)[:3]]
        a = (list(c)[3] / 255 if len(c) > 3 else 1.0)
    return v, a * (1.0 if alpha is None else float(alpha))


@contextlib.contextmanager
def capture_text(canvas=None):
    """Record every text draw made through offsim.cinema.draw.Canvas.text and PIL ImageDraw.text while active.
    Yields a list of dicts {text, box (x0,y0,x1,y1 in canvas px), size, color (rgb), alpha, canvas (w, h)}. Patches are
    restored on exit; drawing behaviour is unchanged. `canvas=(w, h)` keeps only draws onto a canvas of that size (the
    frame itself, not a map panel that is pasted into it)."""
    from offsim.cinema.draw import Canvas
    recs: list = []
    orig_c, orig_p = Canvas.text, ImageDraw.ImageDraw.text

    def c_text(self, x, y, s, font=("Inter", "Bold"), size=16, color="#ffffff", tracking=0.0, anchor="l", alpha=None):
        if str(s).strip() and canvas in (None, (self.w, self.h)):
            w = self.measure(s, font, size, tracking)
            x0 = float(x) - {"l": 0.0, "m": w / 2, "r": w}[anchor]
            col = _color_rgb(color, alpha)
            recs.append({"text": s, "box": (x0, float(y) - 0.78 * size, x0 + w, float(y) + 0.22 * size), "size": float(size),
                         "color": col[0], "alpha": col[1], "canvas": (self.w, self.h)})
        return orig_c(self, x, y, s, font, size, color, tracking, anchor, alpha)

    def p_text(self, xy, text, fill=None, font=None, *a, **k):
        size = getattr(font, "size", None) or k.get("font_size")
        if str(text).strip() and size and canvas in (None, tuple(self.im.size)):
            try:
                from PIL import ImageFont
                w = float((font or ImageFont.load_default(size)).getlength(text))
            except Exception:                              # pragma: no cover
                w = 0.55 * size * len(str(text))
            col = _color_rgb(fill if fill is not None else "#ffffff")
            x, y = float(xy[0]), float(xy[1])
            recs.append({"text": text, "box": (x, y + 0.12 * size, x + w, y + 1.1 * size), "size": float(size),
                         "color": col[0], "alpha": col[1], "canvas": tuple(self.im.size)})
        return orig_p(self, xy, text, fill, font, *a, **k)

    Canvas.text, ImageDraw.ImageDraw.text = c_text, p_text
    try:
        yield recs
    finally:
        Canvas.text, ImageDraw.ImageDraw.text = orig_c, orig_p


def _place(rec, fw, fh):
    """Text record -> (x0, y0, x1, y1, size) in the frame's own pixels (uniform fit, centred, like section.fit)."""
    cw, ch = rec["canvas"]
    k = min(fw / cw, fh / ch)
    ox, oy = (fw - cw * k) / 2, (fh - ch * k) / 2
    x0, y0, x1, y1 = rec["box"]
    return ox + x0 * k, oy + y0 * k, ox + x1 * k, oy + y1 * k, rec["size"] * k


def text_contrast(rgb: np.ndarray, texts, spec) -> dict:
    """WCAG ratio per recorded text box. Background = the ring of pixels around the box (the box itself holds glyph
    pixels and their antialiased blends); `textured` = the ring's robust L* spread (MAD) is above the spec (streaks, map), where one
    background colour does not exist and the verdict is only a warning."""
    h, w = rgb.shape[:2]
    rows = []
    for rec in texts:
        x0, y0, x1, y1, size = _place(rec, w, h)
        t = max(3, int(round(0.5 * size)))
        X0, Y0, X1, Y1 = max(0, int(x0) - t), max(0, int(y0) - t), min(w, int(math.ceil(x1)) + t), min(h, int(math.ceil(y1)) + t)
        if X1 - X0 < 2 or Y1 - Y0 < 2:
            continue
        mask = np.ones((Y1 - Y0, X1 - X0), bool)
        mask[max(0, int(y0) - 1 - Y0):int(math.ceil(y1)) + 1 - Y0, max(0, int(x0) - 1 - X0):int(math.ceil(x1)) + 1 - X0] = False
        ring = rgb[Y0:Y1, X0:X1][mask].astype(float)
        if len(ring) < 8:
            continue
        fg = np.array(rec["color"], float)
        bgc = np.median(ring, axis=0)
        a = rec["alpha"]
        lum = rel_luminance(ring)
        Lr = rgb_to_lab(ring)[:, 0]
        textured = bool(1.4826 * np.median(np.abs(Lr - np.median(Lr))) > spec["contrast"]["textured_l_std"])     # robust spread (MAD)
        ratio = wcag_ratio(fg * a + bgc * (1 - a), bgc)
        order = np.argsort(lum)
        worst = ring[order[int(0.9 * (len(order) - 1))]] if rel_luminance(fg) > rel_luminance(bgc) else ring[order[int(0.1 * (len(order) - 1))]]
        rows.append({"text": str(rec["text"])[:40], "ratio": round(ratio, 2), "ratio_worst_bg": round(min(ratio, wcag_ratio(fg * a + worst * (1 - a), worst)), 2),
                     "textured": textured, "size_px": round(size, 1)})
    return {"mode": "text", "n": len(rows), "items": rows, "min_ratio": min((r["ratio"] for r in rows), default=None)}


def region_contrast(rgb: np.ndarray, spec) -> dict:
    a = _analysis(rgb)
    h, w = a.shape[:2]
    e = edge_map(a, spec["edges"]["sobel_tau"])
    lum = rel_luminance(a)
    gc, gr = spec["contrast"]["region_grid"]
    low = []
    for r in range(gr):
        for c in range(gc):
            ys, ye, xs, xe = r * h // gr, (r + 1) * h // gr, c * w // gc, (c + 1) * w // gc
            if e[ys:ye, xs:xe].mean() < spec["contrast"]["region_edge_min"]:
                continue
            reg = lum[ys:ye, xs:xe].ravel()
            ratio = (np.percentile(reg, 98) + 0.05) / (np.percentile(reg, 2) + 0.05)
            if ratio < spec["contrast"]["min_ratio"]:
                low.append({"cell": [r, c], "ratio": round(float(ratio), 2)})
    return {"mode": "regions", "low_regions": low, "n": gc * gr, "min_ratio": min((x["ratio"] for x in low), default=None)}


def type_scale(texts, fw, fh, spec) -> dict:
    """Distinct text sizes in the renderer's own canvas px (a preview of the same layout has the same scale)."""
    t = spec["type_scale"]
    if not texts:
        return {"n_sizes": None, "sizes": [], "methods_size": None}
    items = [(r["size"], _place(r, fw, fh)[1] / fh) for r in texts]            # (canvas size, y0 fraction)
    merged = []
    for s_ in sorted({round(sz * 2) / 2 for sz, _ in items}):                   # merge sizes closer than merge_px
        if merged and s_ - merged[-1] < t["merge_px"]:
            continue
        merged.append(s_)
    methods = None
    if len(merged) > 1:
        grp = [yf for sz, yf in items if abs(sz - merged[0]) < t["merge_px"]]
        if grp and all(yf >= t["methods_y_min"] for yf in grp):
            methods = merged[0]
    return {"n_sizes": len(merged) - (1 if methods is not None else 0), "sizes": merged, "methods_size": methods}


def margin_stats(rgb: np.ndarray, texts, spec) -> dict:
    m = spec["margins"]
    h, w = rgb.shape[:2]
    safe = m["safe"]
    s_px = safe * min(w, h)
    out_text = []
    for rec in texts or []:
        x0, y0, x1, y1, _ = _place(rec, w, h)
        if x0 < s_px - 0.5 or y0 < s_px - 0.5 or x1 > w - s_px + 0.5 or y1 > h - s_px + 0.5:
            out_text.append({"text": str(rec["text"])[:40], "box": [round(x0), round(y0), round(x1), round(y1)]})
    # ink in the safe-margin band (analysis copy), bleed boxes exempt
    ink = ink_mask(_analysis(rgb), spec)
    ah, aw = ink.shape
    allowed = np.zeros_like(ink)
    for b in m["bleed"]:
        x0, y0, x1, y1 = _box_px(b, aw, ah)
        allowed[y0:y1, x0:x1] = True
    bw = max(1, int(round(safe * min(aw, ah))))
    band = np.zeros_like(ink)
    band[:bw], band[-bw:], band[:, :bw], band[:, -bw:] = True, True, True, True
    band &= ~allowed
    # clipping: ink in the outermost clip_px rows/columns at full resolution, outside bleed boxes along that side
    c = max(1, int(m["clip_px"]))
    pal = PALETTES[spec["palette_name"]]
    grounds = rgb_to_lab(np.array([_hex(pal["ground"]), _hex(pal.get("ground_deep", pal["ground"]))], float))

    def inkpx(part):
        d = np.min(np.linalg.norm(rgb_to_lab(part)[..., None, :] - grounds, axis=-1), axis=-1)
        return d > m["ink_de"]

    def free(axis_len, side):                               # 1-D mask along the strip: True where ink is NOT allowed to touch
        ok = np.ones(axis_len, bool)
        for b in m["bleed"]:
            touches = {"left": b[0] <= 0.001, "right": b[2] >= 0.999, "top": b[1] <= 0.001, "bottom": b[3] >= 0.999}[side]
            if touches:
                lo, hi = (b[1], b[3]) if side in ("left", "right") else (b[0], b[2])
                ok[int(lo * axis_len):int(math.ceil(hi * axis_len))] = False
        return ok

    strips = {"top": (rgb[:c], 1), "bottom": (rgb[-c:], 1), "left": (rgb[:, :c], 0), "right": (rgb[:, -c:], 0)}
    clipped = {}
    for side, (part, ax) in strips.items():
        ink_s = inkpx(part)
        along = ink_s.any(axis=ax) if ink_s.ndim == 2 else ink_s
        along = ink_s.any(axis=0) if side in ("top", "bottom") else ink_s.any(axis=1)
        n = int((along & free(along.size, side)).sum())
        if n > max(2, 0.004 * max(h, w)):
            clipped[side] = n
    return {"text_outside": out_text, "ink_band_share": float((ink & band).sum() / max(band.sum(), 1)), "clipped": clipped}


# ----------------------------------------------------------------------------------------------------- inspect / passes
def inspect(image_or_path, spec=None) -> dict:
    """Measure one frame. `spec` = dict of overrides merged over GATE_SPEC (plus optional keys: kind, text = records from
    capture_text, strict is not a measuring option). Returns the report: measures, per-rule findings, warnings."""
    over = dict(spec or {})
    kind, texts = over.pop("kind", None), over.pop("text", None)
    sp = spec_for(kind, over)
    rgb = _load(image_or_path)
    h, w = rgb.shape[:2]
    rep = {"size": [w, h], "kind": kind, "spec": sp, "findings": [], "has_text_meta": texts is not None}
    F = rep["findings"]

    def add(rule, sev, ok, msg, **vals):
        F.append({"rule": rule, "severity": sev, "ok": bool(ok), "msg": msg, **vals})

    # edges
    es = rep["edges"] = edge_stats(rgb, sp)
    lo, hi = sp["edges"]["overall"]
    plo, phi = sp["edges"]["in_panel"]
    ok_o, ok_p = lo <= es["overall"] <= hi, plo <= es["in_panel"] <= phi
    why = []
    if es["overall"] < lo:
        why.append(f"overall edge density {es['overall']:.4f} < {lo:.4f} (empty)")
    if es["overall"] > hi:
        why.append(f"overall edge density {es['overall']:.4f} > {hi:.4f} (mush)")
    if es["in_panel"] < plo:
        why.append(f"main-panel edge density {es['in_panel']:.4f} < {plo:.4f} (empty)")
    if es["in_panel"] > phi:
        why.append(f"main-panel edge density {es['in_panel']:.4f} > {phi:.4f} (mush)")
    add("edges", HARD, ok_o and ok_p, "; ".join(why) or f"edge density {es['overall']:.4f} overall, {es['in_panel']:.4f} in panel")
    # strokes
    st = rep["strokes"] = stroke_stats(rgb, sp)
    pv = sp["strokes"]["preview_of"]
    need = sp["strokes"]["min_median_px"] * (min(1.0, w / pv) if pv else 1.0)
    st["required_px"] = need
    add("strokes", HARD, st["median_px"] >= need,
        f"median stroke {st['median_px']:.2f} px < {need:.2f} px at the delivered size ({st['thin_share']:.0%} of ink pixels under 0.75 px)"
        if st["median_px"] < need else f"median stroke {st['median_px']:.2f} px")
    # palette + accent
    ps = rep["palette"] = palette_stats(rgb, sp)
    add("palette", HARD, ps["off_share"] <= sp["palette"]["max_off_share"],
        f"{ps['off_share']:.1%} of pixels are outside the palette (> {ps['tolerance_de']:.1f} Delta E from any declared colour or blend; "
        f"worst {ps['off_colors'][:2]}); limit {sp['palette']['max_off_share']:.0%}"
        if ps["off_share"] > sp["palette"]["max_off_share"] else f"{ps['off_share']:.2%} off palette")
    a = ps["accent_share"]
    amax, amin = sp["accent"]["max_share"], sp["accent"]["min_share"]
    add("accent", HARD, a <= amax, f"accent covers {a:.1%} of the frame (> {amax:.0%}: an accent that floods the frame is not an accent)"
        if a > amax else f"accent covers {a:.2%}")
    if a <= amax:
        add("accent", SOFT, a >= amin, f"accent covers {a:.2%} (< {amin:.2%}: no accent in the frame)" if a < amin else f"accent covers {a:.2%}")
    # contrast
    if texts:
        tc = rep["contrast"] = text_contrast(rgb, texts, sp)
        mr = sp["contrast"]["min_ratio"]
        bad = [r for r in tc["items"] if not r["textured"] and r["ratio"] < mr]
        add("contrast", HARD, not bad,
            f"{len(bad)} text box(es) below {mr}:1 on a flat background, worst {min(bad, key=lambda r: r['ratio'])['ratio']}:1 "
            f"({min(bad, key=lambda r: r['ratio'])['text']!r})" if bad else f"{tc['n']} text boxes, lowest {tc['min_ratio']}:1")
        tex = [r for r in tc["items"] if r["textured"] and min(r["ratio"], r["ratio_worst_bg"]) < mr]
        add("contrast", SOFT, not tex,
            f"{len(tex)} text box(es) over a textured field below {mr}:1 (median or brightest background), worst "
            f"{min(tex, key=lambda r: min(r['ratio'], r['ratio_worst_bg']))['text']!r} {min(min(r['ratio'], r['ratio_worst_bg']) for r in tex)}:1"
            if tex else "no text over a textured field below the limit")
    else:
        tc = rep["contrast"] = region_contrast(rgb, sp)
        add("contrast", SOFT, not tc["low_regions"],
            f"{len(tc['low_regions'])} region(s) with edge content below {sp['contrast']['min_ratio']}:1 luminance range (no text metadata), "
            f"worst {tc['min_ratio']}:1" if tc["low_regions"] else "all inked regions above 4.5:1 (no text metadata)")
    # type scale
    ts = rep["type_scale"] = type_scale(texts, w, h, sp) if texts else {"n_sizes": None, "sizes": [], "methods_size": None}
    if ts["n_sizes"] is not None:
        t = sp["type_scale"]
        add("type_scale", SOFT, ts["n_sizes"] <= t["max_soft"],
            f"{ts['n_sizes']} text sizes {ts['sizes']} (methods line {ts['methods_size']}) > {t['max_soft']}: rule 17 allows 3 plus the methods line"
            if ts["n_sizes"] > t["max_soft"] else f"{ts['n_sizes']} text sizes plus methods line")
    # margins
    ms = rep["margins"] = margin_stats(rgb, texts, sp)
    probs = []
    if ms["clipped"]:
        probs.append("ink clipped at the frame edge: " + ", ".join(f"{k} ({v} px)" for k, v in ms["clipped"].items()))
    if ms["text_outside"]:
        probs.append(f"{len(ms['text_outside'])} text box(es) outside the {sp['margins']['safe']:.0%} safe area, e.g. {ms['text_outside'][0]['text']!r}")
    if ms["ink_band_share"] > sp["margins"]["ink_band_share"]:
        probs.append(f"ink fills {ms['ink_band_share']:.1%} of the safe-margin band (> {sp['margins']['ink_band_share']:.1%})")
    add("margins", HARD, not probs, "; ".join(probs) or "ink inside the safe area")
    # balance
    bs = rep["balance"] = balance_stats(rgb, sp)
    bsp = sp["balance"]
    add("balance", HARD, bs["min_half"] >= bsp["min_half_share"],
        f"empty half: {min(bs['halves'], key=bs['halves'].get)} half holds {bs['min_half']:.0%} of the ink (< {bsp['min_half_share']:.0%})"
        if bs["min_half"] < bsp["min_half_share"] else f"smallest half holds {bs['min_half']:.0%} of the ink")
    add("balance", SOFT, bs["thin_cells"] <= bsp["max_thin_cells"],
        f"{bs['thin_cells']} of 9 grid cells are sparse (< {bsp['thin_cell_ratio']:.0%} of the mean ink density; allowed {bsp['max_thin_cells']})"
        if bs["thin_cells"] > bsp["max_thin_cells"] else f"{bs['thin_cells']} sparse grid cells")
    rep["warnings"] = [f"{f['rule']}: {f['msg']}" for f in F if f["severity"] == SOFT and not f["ok"]]
    return rep


def passes(report: dict, strict: bool = False):
    """(ok, reasons). HARD failures always; SOFT failures too when strict. Reasons read '<rule>: <measured vs limit>'."""
    bad = [f for f in report["findings"] if not f["ok"] and (f["severity"] == HARD or strict)]
    return (not bad), [f"{f['rule']}: {f['msg']}" for f in bad]


# ----------------------------------------------------------------------------------------------------- golden comparison
def structure(image_or_path, spec=None) -> dict:
    """Per-region ink and edge density on a 4 x 4 grid (the quantities compare() judges). The analysis copy is lightly
    blurred (sigma 1 px) first so sensor-style noise and one-pixel shifts do not move edge pixels across the threshold."""
    sp = spec_for(None, spec)
    a = _analysis(_load(image_or_path))
    a = np.clip(ndi.gaussian_filter(a.astype(float), (1.0, 1.0, 0)) + 0.5, 0, 255).astype(np.uint8)
    ink, e = ink_mask(a, sp), edge_map(a, sp["edges"]["sobel_tau"])
    h, w = ink.shape
    ci = [[float(ink[r * h // 4:(r + 1) * h // 4, c * w // 4:(c + 1) * w // 4].mean()) for c in range(4)] for r in range(4)]
    ce = [[float(e[r * h // 4:(r + 1) * h // 4, c * w // 4:(c + 1) * w // 4].mean()) for c in range(4)] for r in range(4)]
    return {"ink": ci, "edges": ce, "aspect": round(h / w, 3)}


def compare(frame, golden, tol: float = 0.35, floor_ink: float = 0.04, floor_edge: float = 0.008, spec=None):
    """(ok, reasons). A structural change = a 4 x 4 region whose ink or edge density differs from the golden by more than
    `tol` x max(golden value, floor) (floors keep near-empty regions from tripping on a few pixels), or a different aspect.
    Pixel noise, antialiasing and sub-pixel shifts stay far below this; a moved, removed or added element does not."""
    a, b = structure(frame, spec), structure(golden, spec)
    why = []
    if abs(a["aspect"] - b["aspect"]) > 0.02:
        why.append(f"aspect {a['aspect']} vs golden {b['aspect']}")
    for name, fl in (("ink", floor_ink), ("edges", floor_edge)):
        for r in range(4):
            for c in range(4):
                g, v = b[name][r][c], a[name][r][c]
                if abs(v - g) > tol * max(g, fl):
                    why.append(f"{name} density in region (row {r}, col {c}) is {v:.3f}, golden {g:.3f} (tolerance {tol:.0%})")
    return (not why), why
