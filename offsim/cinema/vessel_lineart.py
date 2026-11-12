"""Detailed side-profile line art for vessels (docs/STYLE_REFERENCE.md, "why the reference reads as detailed").

Rules encoded here, learned from the reference:
1. Detail density at real proportions: hull, sheer, bow flare, bulwark posts, portholes, boot-top line, tiered
   superstructure, wraparound bridge windows, wings, mast + radar, funnels, davit + rescue boat, cargo, crane, crew.
2. Line-weight hierarchy: W1 outline, W2 structure, W3 detail (px at 1x; drawn supersampled).
3. Tonal fills (2-3 values from the palette), never one flat fill.
4. Scale cues: people 1.8 m tall, rails 1.1 m, windows 1.2 m.
Geometry is a stylised ~85 m PSV (UT 755-like proportions; ASSUMED until a class drawing is sourced).

    prims, solids, exhaust = psv_profile(x0, z0)   # bow at x0 facing -x (into a wind from -x)
    draw(draw_ctx, prims, to_px, scale, palette)       # to_px(x_m, z_m) -> (px, py); scale = px per metre
Primitives: (kind, points, weight, fill, outline) with kind in {"poly", "line"}; solids: polygons for the fluid mask.
"""
from __future__ import annotations

import numpy as np

W1, W2, W3 = 2.4, 1.3, 0.8


def _arc(xc, zc, r, a0, a1, n=8):
    a = np.linspace(a0, a1, n)
    return list(zip(xc + r * np.cos(a), zc + r * np.sin(a)))


def psv_profile(x0, z0, length=85.0, pitch_rad=0.0, pivot=None):
    """Return (prims, solids) in metres. x0 = bow tip; z0 = waterline. Optional pitch about pivot (x, z)."""
    L = length
    def X(u):                                   # u = metres from the bow; bow at x0, stern toward +x
        return x0 + u
    deck, fcsle, keel = z0 + 4.5, z0 + 7.5, z0 - 6.2
    P = []                                      # primitives
    S = []                                      # solids
    # hull with bow flare and forecastle step
    hull = [(X(0), fcsle + 0.6), (X(2.5), z0 + 1.0), (X(6), keel + 0.8), (X(10), keel), (X(L - 4), keel),
            (X(L - 1.5), keel + 1.8), (X(L), deck - 0.6), (X(L), deck), (X(24), deck), (X(24), fcsle), (X(1.2), fcsle + 0.6)]
    P.append(("poly", hull, W1, "hull", "ink"))
    S.append(hull)
    P.append(("line", [(X(3.2), z0 + 0.35), (X(L - 0.5), z0 + 0.35)], W3, None, "accent_dim"))      # boot-top
    for u in np.arange(6, L - 4, 3.2):                                                               # hull plating
        P.append(("line", [(X(u), keel + 0.3), (X(u), z0 - 0.2)], W3, None, "line_faint"))
    for u in np.arange(8, 22, 2.2):                                                                  # portholes
        P.append(("poly", _arc(X(u), z0 + 2.6, 0.35, 0, 2 * np.pi, 10), W3, None, "ink"))
    # bulwark + rail along the cargo deck
    P.append(("line", [(X(24), deck + 1.1), (X(L - 0.5), deck + 1.1)], W2, None, "ink"))
    for u in np.arange(24.5, L, 1.6):
        P.append(("line", [(X(u), deck), (X(u), deck + 1.1)], W3, None, "ink"))
    # superstructure tiers (forward), bridge with wraparound windows, wings
    tiers = [(3.0, 23.0, fcsle, fcsle + 3.0), (4.0, 22.0, fcsle + 3.0, fcsle + 6.0), (5.0, 21.0, fcsle + 6.0, fcsle + 8.6)]
    for a, b, z1, z2 in tiers:
        box = [(X(a), z1), (X(b), z1), (X(b), z2), (X(a + 0.6), z2)]
        P.append(("poly", box, W2, "house", "ink"))
        S.append(box)
        for u in np.arange(a + 1.4, b - 1.0, 1.9):
            P.append(("poly", [(X(u), z1 + 1.1), (X(u + 1.1), z1 + 1.1), (X(u + 1.1), z1 + 2.2), (X(u), z1 + 2.2)], W3, "window", "ink"))
    zb = fcsle + 8.6
    bridge = [(X(4.0), zb), (X(22.5), zb), (X(22.5), zb + 3.0), (X(5.2), zb + 3.0)]
    P.append(("poly", bridge, W1, "house", "ink"))
    S.append(bridge)
    P.append(("poly", [(X(4.6), zb + 1.0), (X(22.0), zb + 1.0), (X(22.0), zb + 2.4), (X(5.0), zb + 2.4)], W3, "glass", "ink"))
    for u in np.arange(6, 22, 1.5):
        P.append(("line", [(X(u), zb + 1.0), (X(u), zb + 2.4)], W3, None, "ink"))
    P.append(("line", [(X(2.0), zb + 0.2), (X(24.5), zb + 0.2)], W2, None, "ink"))                  # wings
    # mast, radar, antennas
    P.append(("line", [(X(13), zb + 3.0), (X(13), zb + 9.5)], W2, None, "ink"))
    P.append(("line", [(X(10.5), zb + 6.2), (X(15.5), zb + 6.2)], W2, None, "ink"))
    P.append(("line", [(X(11.5), zb + 8.0), (X(14.5), zb + 8.0)], W3, None, "ink"))
    P.append(("line", [(X(16.5), zb + 3.0), (X(16.5), zb + 6.5)], W3, None, "ink"))
    # funnels: twin exhaust uptakes at the aft side of the house
    fun = [(X(22.0), fcsle + 6.0), (X(25.5), fcsle + 6.0), (X(25.0), zb + 4.2), (X(22.4), zb + 4.2)]
    P.append(("poly", fun, W1, "funnel", "ink"))
    S.append(fun)
    P.append(("line", [(X(22.2), zb + 3.2), (X(25.2), zb + 3.2)], W3, None, "accent_dim"))
    # rescue boat on davit (port side, visible in profile)
    P.append(("poly", [(X(14), fcsle + 3.4), (X(19.5), fcsle + 3.4), (X(19.0), fcsle + 4.6), (X(14.4), fcsle + 4.6)], W3, "accent_fill", "ink"))
    # cargo on the aft deck: containers + pipe stack
    for u, w, h in ((30, 6.1, 2.6), (37, 6.1, 2.6), (44, 12.2, 2.6), (58, 6.1, 5.2)):
        box = [(X(u), deck), (X(u + w), deck), (X(u + w), deck + h), (X(u), deck + h)]
        P.append(("poly", box, W2, "cargo", "ink"))
        for v in np.arange(u + 0.5, u + w, 0.5):
            P.append(("line", [(X(v), deck + 0.2), (X(v), deck + h - 0.2)], W3 * 0.7, None, "line_faint"))
    for k in range(4):
        P.append(("poly", _arc(X(68 + k * 1.1), deck + 0.55 + (k % 2) * 0.9, 0.5, 0, 2 * np.pi, 10), W3, None, "ink"))
    # crew (scale): two people, 1.8 m
    for u in (52.5, 74.0):
        P.append(("poly", _arc(X(u), deck + 1.62, 0.18, 0, 2 * np.pi, 8), W3, "ink", "ink"))
        P.append(("line", [(X(u), deck + 1.42), (X(u), deck + 0.75)], W2, None, "ink"))
        P.append(("line", [(X(u), deck + 0.75), (X(u - 0.25), deck)], W3, None, "ink"))
        P.append(("line", [(X(u), deck + 0.75), (X(u + 0.25), deck)], W3, None, "ink"))
    if pitch_rad and pivot is not None:
        c, s = np.cos(pitch_rad), np.sin(pitch_rad)
        rot = lambda pts: [(pivot[0] + (x - pivot[0]) * c - (z - pivot[1]) * s,
                            pivot[1] + (x - pivot[0]) * s + (z - pivot[1]) * c) for x, z in pts]
        P = [(k, rot(p), w, f, o) for k, p, w, f, o in P]
        S = [rot(p) for p in S]
    exhaust = (X(23.7), zb + 4.2)
    if pitch_rad and pivot is not None:
        exhaust = tuple(np.array(rot([exhaust])[0]))
    return P, S, exhaust


FILLS = {"hull": "#3d2326", "house": "#4a2b2d", "funnel": "#53302f", "window": "#2f1a1e", "glass": "#26333a",
         "cargo": "#432729", "accent_fill": "#8a5a2a", "ink": "#f2e9df", "boot": "#5c3532",  # v9: boot-top stripe
         # v10 (working ship, not a toy): light from above, one value step per face. The hull gets a
         # vertical value gradient (sheer lightest, keel darkest); the superstructure steps up one
         # value per tier; glass varies pane to pane. All in the same dark-maroon family — tonal
         # modelling, not new colours. The old flat keys keep their values, so the v7 profile is untouched.
         "hull_top": "#6b3a34", "hull_low": "#2a161a",
         "house_mid": "#55302e", "house_top": "#5f3833", "bridge": "#66403a",
         "glass_dim": "#1e2a30", "funnel_band": "#7a4038"}
STROKES = {"ink": "#f2e9df", "accent_dim": "#b07a2a", "line_faint": "#6b4f4a"}


def draw(d, prims, to_px, ss=1.0):
    """Draw primitives on a PIL ImageDraw (supersampled canvas: pass ss = supersampling factor)."""
    for kind, pts, w, fill, outline in prims:
        px = [to_px(x, z) for x, z in pts]
        width = max(1, int(round(w * ss)))
        col = STROKES.get(outline, outline)
        if kind == "poly":
            d.polygon(px, fill=FILLS.get(fill) if fill else None)
            d.line(px + [px[0]], fill=col, width=width, joint="curve")
        else:
            d.line(px, fill=col, width=width)
