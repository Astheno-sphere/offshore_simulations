"""Print-grade vector drawing on skia-python (BSD-3): anti-aliased paths, round joins and caps, dashes, alpha, real fonts.

Docs/STYLE_REFERENCE.md rules 12 (strokes) and 17 (typography). PIL stays for raster compositing only. There is no PIL
fallback: if skia cannot be imported this module raises ImportError (a silent fallback would change the look unnoticed).

    from offsim.cinema.draw import Canvas, draw_prims
    cv = Canvas(1280, 720, bg="#331c22", ss=2)            # coordinates are always in 1x pixels; ss only adds resolution
    cv.polygon(pts, fill="#4a2b2d", stroke="#f2e9df", width=2.4)
    cv.line(pts, "#f2e9df", 0.6, dash=(6, 4))             # hairline detail stroke
    cv.text(40, 60, "SECTION", font=("Inter", "Bold"), size=28, color="#f2e9df", tracking=1.5)
    img = cv.to_pil()                                      # PIL RGB (RGBA if bg=None), box-downsampled by ss; cv.save(path)

Switching other modules to this (they are owned by other work, so not edited here):
* vessel_lineart.draw(d, prims, to_px, ss)  ->  draw_prims(canvas, prims, to_px)
  Same primitive tuples (kind, points, weight, fill, outline) and the same FILLS/STROKES tables. Differences: to_px must
  return 1x pixel coordinates (the Canvas applies ss itself), and weights are 1x px, drawn fractionally (0.8 stays 0.8
  instead of rounding to 1). Old call: draw(d, prims, to_px_ss, ss) with to_px_ss = lambda x, z: (ox + s*ss*x, ...);
  new call: draw_prims(cv, prims, lambda x, z: (ox + s*x, ...)).
* PIL ImageFont.truetype(DejaVu...) -> Canvas.text(..., font=("Inter", weight)); weights from look.FONTS
  (Regular, Medium, SemiBold, Bold). Measure with Canvas.measure(s, font, size, tracking).
* Mix with PIL rasters (hillshade tiles, sprites): img = cv.to_pil(); base.alpha_composite(img) or paste(img, mask=img).
"""
from __future__ import annotations

try:
    import skia
except Exception as e:  # pragma: no cover - environment dependent
    raise ImportError("offsim.cinema.draw needs skia-python (pip install -r requirements-graphics.txt): %s" % e) from e

import numpy as np
from PIL import Image

from . import look
from .vessel_lineart import FILLS, STROKES

_TYPEFACES = {}


def _typeface(family, weight):
    if family != "Inter":
        raise ValueError(f"only the bundled open font 'Inter' is available (got {family!r}); see offsim.cinema.look.FONTS")
    key = weight
    if key not in _TYPEFACES:
        tf = skia.Typeface.MakeFromFile(look.font_path(weight))
        if tf is None:
            raise OSError(f"cannot load font {look.font_path(weight)}")
        _TYPEFACES[key] = tf
    return _TYPEFACES[key]


def parse_color(c, alpha=None):
    """'#rrggbb' | '#rrggbbaa' | (r,g,b) | (r,g,b,a) (0-255) -> (r, g, b, a). `alpha` (0..1) multiplies a."""
    if isinstance(c, str):
        h = c.lstrip("#")
        if len(h) not in (6, 8):
            raise ValueError(f"bad colour {c!r}")
        v = [int(h[i:i + 2], 16) for i in range(0, len(h), 2)]
        r, g, b, a = (v + [255])[:4] if len(v) == 3 else v
    else:
        v = list(c)
        r, g, b = v[:3]
        a = v[3] if len(v) > 3 else 255
    if alpha is not None:
        a = a * float(alpha)
    return int(r), int(g), int(b), int(round(min(255, max(0, a))))


def _paint(color, alpha=None, stroke=False, width=1.0, dash=None):
    r, g, b, a = parse_color(color, alpha)
    p = skia.Paint(AntiAlias=True, Color=skia.Color(r, g, b, a))
    if stroke:
        p.setStyle(skia.Paint.kStroke_Style)
        p.setStrokeWidth(float(width))
        p.setStrokeJoin(skia.Paint.kRound_Join)
        p.setStrokeCap(skia.Paint.kRound_Cap)
        if dash:
            p.setStrokeCap(skia.Paint.kButt_Cap)          # so on/off lengths are true
            p.setPathEffect(skia.DashPathEffect.Make([float(x) for x in dash], 0.0))
    return p


def _path(pts, close=False):
    path = skia.Path()
    pts = list(pts)
    path.moveTo(float(pts[0][0]), float(pts[0][1]))
    for x, y in pts[1:]:
        path.lineTo(float(x), float(y))
    if close:
        path.close()
    return path


class Canvas:
    """w x h pixel canvas; drawing in 1x pixel units, rendered at ss x resolution and box-downsampled by to_pil()."""

    def __init__(self, w, h, bg="#000000", ss=1):
        self.w, self.h, self.ss = int(w), int(h), int(ss)
        if self.ss < 1:
            raise ValueError("ss must be >= 1")
        self.bg = bg
        self.surface = skia.Surface(self.w * self.ss, self.h * self.ss)
        self.cv = self.surface.getCanvas()
        self.cv.scale(self.ss, self.ss)
        if bg is None:
            self.cv.clear(skia.Color4f(0, 0, 0, 0))
        else:
            r, g, b, a = parse_color(bg)
            self.cv.clear(skia.Color(r, g, b, a))

    # -- shapes -------------------------------------------------------------------------------------------------
    def polygon(self, pts, fill=None, stroke=None, width=1.0, alpha=None, dash=None):
        """Closed polygon; fill and/or stroke (round joins). Colours: hex or tuple; alpha 0..1 scales both."""
        if len(pts) < 2:
            return
        path = _path(pts, close=True)
        if fill is not None:
            self.cv.drawPath(path, _paint(fill, alpha))
        if stroke is not None and width > 0:
            self.cv.drawPath(path, _paint(stroke, alpha, True, width, dash))

    def line(self, pts, color, width=1.0, dash=None, alpha=None):
        """Open polyline with round joins and caps; dash = (on, off, ...) in px."""
        if len(pts) < 2:
            return
        self.cv.drawPath(_path(pts), _paint(color, alpha, True, width, dash))

    def lines(self, polylines, color, width=1.0, dash=None, alpha=None):
        """Many open polylines in one path / one draw call (road layers, coastlines).
        Each polyline is a separate subpath — no connecting segment between them."""
        path = skia.Path()
        n = 0
        for pts in polylines:
            pts = list(pts)
            if len(pts) < 2:
                continue
            path.moveTo(float(pts[0][0]), float(pts[0][1]))
            for x, y in pts[1:]:
                path.lineTo(float(x), float(y))
            n += 1
        if n:
            self.cv.drawPath(path, _paint(color, alpha, True, width, dash))

    def circle(self, cx, cy, r, fill=None, stroke=None, width=1.0, alpha=None):
        if fill is not None:
            self.cv.drawCircle(float(cx), float(cy), float(r), _paint(fill, alpha))
        if stroke is not None and width > 0:
            self.cv.drawCircle(float(cx), float(cy), float(r), _paint(stroke, alpha, True, width))

    # -- text ---------------------------------------------------------------------------------------------------
    def _font(self, font, size):
        fam, wt = font
        f = skia.Font(_typeface(fam, wt), float(size))
        f.setSubpixel(True)
        f.setEdging(skia.Font.Edging.kSubpixelAntiAlias)
        return f

    def measure(self, s, font=("Inter", "Regular"), size=16, tracking=0.0):
        """Advance width in px of `s` (tracking = extra px between glyphs)."""
        f = self._font(font, size)
        return f.measureText(s) + tracking * max(0, len(s) - 1)

    def text(self, x, y, s, font=("Inter", "Bold"), size=16, color="#ffffff", tracking=0.0, anchor="l", alpha=None):
        """Text with baseline at y. anchor 'l' | 'm' | 'r' relative to x. tracking = extra px per glyph (letter-spacing)."""
        f = self._font(font, size)
        width = f.measureText(s) + tracking * max(0, len(s) - 1)
        x0 = float(x) - {"l": 0.0, "m": width / 2, "r": width}[anchor]
        paint = _paint(color, alpha)
        if not tracking:
            self.cv.drawString(s, x0, float(y), f, paint)
            return
        pen = x0
        for ch in s:
            self.cv.drawString(ch, pen, float(y), f, paint)
            pen += f.measureText(ch) + tracking

    # -- output -------------------------------------------------------------------------------------------------
    def to_pil(self):
        """PIL image of size (w, h): RGB if bg was given, RGBA if bg is None. Box-filters the ss x supersample."""
        snap = self.surface.makeImageSnapshot()
        arr = snap.toarray(colorType=skia.kRGBA_8888_ColorType, alphaType=skia.kPremul_AlphaType).astype("float32")
        if self.ss > 1:
            s = self.ss
            arr = arr.reshape(self.h, s, self.w, s, 4).mean(axis=(1, 3))
        a = arr[..., 3:4]
        if self.bg is None:
            rgb = np.where(a > 0, arr[..., :3] * 255.0 / np.maximum(a, 1e-6), 0.0)
            out = np.concatenate([rgb, a], axis=-1)
            return Image.fromarray(np.clip(out + 0.5, 0, 255).astype("uint8"), "RGBA")
        return Image.fromarray(np.clip(arr[..., :3] + 0.5, 0, 255).astype("uint8"), "RGB")

    def save(self, path):
        self.to_pil().save(path)
        return path


def draw_prims(canvas, prims, to_px, fills=None, strokes=None):
    """Render vessel_lineart primitives (kind, points, weight, fill, outline) on a Canvas. Drop-in for
    vessel_lineart.draw: to_px(x_m, z_m) -> (px, py) in 1x pixels. fills/strokes override FILLS/STROKES."""
    fills = FILLS if fills is None else fills
    strokes = STROKES if strokes is None else strokes
    for kind, pts, w, fill, outline in prims:
        px = [to_px(x, z) for x, z in pts]
        col = strokes.get(outline, outline)
        if kind == "poly":
            canvas.polygon(px, fill=fills.get(fill, fill) if fill else None, stroke=col, width=w)
        else:
            canvas.line(px, col, w)
