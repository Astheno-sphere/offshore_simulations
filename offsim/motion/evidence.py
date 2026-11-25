"""Evidence-form frame builder (rules.EVIDENCE, docs/VISUAL_GRAMMAR.md section 10). One template: the real reference above, the result
below with a `REPLAY / <finding>` label, a corner counter row, then kicker, headline with accent words, body, the limits line, the method
lines and the source line. Pure drawing: panels arrive as PIL images (or None, drawn as a visible 'not pulled' placeholder, never hidden),
numbers arrive already resolved from `report:` refs by the caller. Checked by offsim/cinema/evidence.py before it draws.
"""
from __future__ import annotations

from PIL import Image

from offsim.cinema import look
from offsim.cinema.draw import Canvas
from offsim.cinema.evidence import evidence_plan

W, H = 1080, 1350                                   # 4:5
FONT = ("Inter", "Bold")
FONT_R = ("Inter", "Regular")
FONT_M = ("Inter", "Medium")


def _wrap(cv, text, font, size, width):
    lines, cur = [], ""
    for w in str(text).split():
        t = (cur + " " + w).strip()
        if cv.measure(t, font, size) <= width or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    return lines + ([cur] if cur else [])


def _placeholder(cv, box, pal, label):
    x0, y0, x1, y1 = box
    cv.polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], fill=pal["ground_deep"])
    step = 28
    bh = y1 - y0
    for k in range(int(-bh // step), int((x1 - x0) // step) + 2):
        ax, bx = x0 + k * step, x0 + k * step + bh                    # a diagonal from the top edge to the bottom edge, clipped to the box
        t0, t1 = max(0.0, (x0 - ax) / bh), min(1.0, (x1 - ax) / bh)
        if t1 <= t0:
            continue
        cv.line([(ax + t0 * bh, y0 + t0 * bh), (ax + t1 * bh, y0 + t1 * bh)], pal["muted"], 1.0, alpha=0.25)
    cv.text((x0 + x1) / 2, (y0 + y1) / 2, label, FONT_M, 22, pal["muted"], tracking=3.0, anchor="m")


def _paste(img: Image.Image, panel: Image.Image | None, box, cv, pal, label):
    x0, y0, x1, y1 = (int(v) for v in box)
    if panel is None:
        _placeholder(cv, box, pal, label)
        return
    p = panel.convert("RGB")
    s = max((x1 - x0) / p.width, (y1 - y0) / p.height)           # cover, centred crop
    p = p.resize((max(1, round(p.width * s)), max(1, round(p.height * s))))
    cx, cy = (p.width - (x1 - x0)) // 2, (p.height - (y1 - y0)) // 2
    img.paste(p.crop((cx, cy, cx + (x1 - x0), cy + (y1 - y0))), (x0, y0))


def render_evidence(shot: dict, values: dict | None = None, panels: dict | None = None, palette: str = "amber-black",
                    size=(W, H), draft: str | None = None) -> Image.Image:
    """Return the frame. `values` maps a counter ref (the `ref` string) to its display text; a counter whose ref is missing raises.
    `draft` (e.g. 'DRAFT, NOT REPORTABLE') is stamped top-right and is required for anything whose refs are not yet validated."""
    probs = evidence_plan({"shots": [shot]})
    if probs:
        raise ValueError("evidence shot refused: " + "; ".join(probs))
    pal = look.PALETTES[palette]
    w, h = size
    mx, my = round(0.06 * w), round(0.05 * h)
    cv = Canvas(w, h, pal["ground"], ss=2)
    panels = panels or {}
    ref = shot["reference"]
    # panels: reference 0.07-0.30, result 0.33-0.62 of height, labels above each
    ref_box = (mx, 0.085 * h, w - mx, 0.225 * h)
    res_box = (mx, 0.275 * h, w - mx, 0.515 * h)
    cv.text(mx, 0.065 * h, "REAL " + str(ref["kind"]).upper() + "  /  " + str(ref.get("source", "")).upper()[:60], FONT_M, 17, pal["muted"], tracking=2.5)
    cv.text(mx, 0.262 * h, "REPLAY  /  " + shot["finding"].upper(), FONT_M, 17, pal["accent"], tracking=2.5)
    img_layers = []
    base = cv.to_pil()
    cv2 = Canvas(w, h, None, ss=2)                                # second layer so panel pixels sit under overlays
    _paste(base, panels.get("reference"), ref_box, Canvas(w, h, None, ss=1), pal, "REFERENCE NOT PULLED")
    _paste(base, panels.get("result"), res_box, Canvas(w, h, None, ss=1), pal, "RESULT NOT BUILT")
    # placeholders draw on a throwaway canvas above; redo them on the real one when absent
    cv = Canvas(w, h, None, ss=2)
    for key, box, lab in (("reference", ref_box, "REFERENCE NOT PULLED"), ("result", res_box, "RESULT NOT BUILT")):
        if panels.get(key) is None:
            _placeholder(cv, box, pal, lab)
    # counters sit in their own row under the result so they never cover data; the number is the largest type on the frame
    x, base_y = mx, res_box[3] + 82
    for c in shot.get("counters", []):
        val = (values or {}).get(c["ref"])
        if val is None:
            raise KeyError(f"counter {c['ref']!r} has no resolved value")
        cv.text(x, base_y, str(val), FONT, 78, pal["accent"])
        nw = cv.measure(str(val), FONT, 78)
        cv.text(x + nw + 14, base_y - 6, str(c["label"]).upper(), FONT_M, 15, pal["ink"], tracking=2.0)
        x += nw + 14 + cv.measure(str(c["label"]).upper(), FONT_M, 15, 2.0) + 46
    # text block
    y = base_y + 52
    cv.text(mx, y, str(shot["kicker"]).upper() if shot.get("kicker") else "", FONT_M, 19, pal["accent"], tracking=4.0)
    head, acc = shot["headline"], shot.get("accent") or ""
    size_h = 62
    words, pos = head.split(), head.find(acc) if acc else -1
    lines, cur = [], []
    for wd in words:
        if cv.measure(" ".join(cur + [wd]), FONT, size_h) > w - 2 * mx and cur:
            lines.append(cur); cur = [wd]
        else:
            cur.append(wd)
    lines.append(cur)
    if len(lines) > 1 and len(lines[-1]) == 1:                # no orphan word: pull one down from the line above
        lines[-1].insert(0, lines[-2].pop())
    idx = 0
    y += 12
    for ln in lines:
        y += size_h * 1.06
        px = mx
        for wd in ln:
            start = head.find(wd, idx)
            inside = pos >= 0 and pos <= start < pos + len(acc)
            idx = start + len(wd)
            cv.text(px, y, wd, FONT, size_h, pal["accent"] if inside else pal["ink"])
            px += cv.measure(wd + " ", FONT, size_h)
    y += 26
    if shot.get("body"):
        for ln in _wrap(cv, shot["body"], FONT_R, 24, w - 2 * mx)[:2]:
            y += 31
            cv.text(mx, y, ln, FONT_R, 24, pal["ink"], alpha=0.9)
    y += 34
    cv.text(mx, y, "THIS FRAME IS NOT", FONT_M, 13, pal["comparison"], tracking=2.5)
    for ln in _wrap(cv, "  ".join(shot["limits"]), FONT_R, 19, w - 2 * mx)[:2]:
        y += 25
        cv.text(mx, y, ln, FONT_R, 19, pal["muted"])
    y += 32
    cv.text(mx, y, "METHOD", FONT_M, 13, pal["comparison"], tracking=2.5)
    meth = "  ·  ".join(f"{m['label']} ({'assumed' if m.get('assumption') else m.get('ref', '')})" for m in shot["method"])
    for ln in _wrap(cv, meth, FONT_R, 17, w - 2 * mx)[:2]:
        y += 22
        cv.text(mx, y, ln, FONT_R, 17, pal["muted"])
    if y > h - my - 10:
        raise ValueError(f"evidence frame text overflows the frame by {y - (h - my - 10):.0f}px: shorten body, limits or method")
    cv.text(mx, h - my + 6, shot.get("source", ""), FONT_R, 16, pal["muted"], alpha=0.8)
    cv.text(w - mx, h - my + 6, shot.get("handle", ""), FONT_M, 16, pal["muted"], anchor="r")
    if draft:
        cv.text(w - mx, 0.04 * h, draft.upper(), FONT, 16, pal["comparison"], tracking=2.5, anchor="r")
    top = cv.to_pil()
    base = base.convert("RGBA")
    base.alpha_composite(top.convert("RGBA"))
    return base.convert("RGB")
