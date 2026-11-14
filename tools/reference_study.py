"""Measure a reference film so its grammar can be written down (docs/REFERENCE_STUDY.md).

    python tools/reference_study.py <video> --out out/reference/<slug>

Writes measure.json, sheet.jpg (1 frame per second) and motion.jpg (a dense strip) into --out, which must lie
under out/ (ignored by git). Nothing from a reference work is ever committed: only the numbers you copy by hand
into a grammar file. Needs ffmpeg and ffprobe on PATH; numpy and Pillow.

What it measures, and how
  duration, size, fps      ffprobe
  cuts                     ffmpeg scene score > --cut (default 0.25); 0 cuts means one continuous shot
  bands                    horizontal bands of the median frame: rows whose mean colour sits within --ground of the
                           ground colour (the most common colour) are gutters or caption ground; the rest is scene
  scene_share              share of frame height in bands that keep changing over time (temporal std > --live)
  static_share             share of frame height that never changes: the caption block and gutters
  palette                  6 dominant colours of the median frame (k-means in RGB), with shares
  saturated_share          share of pixels with HSV saturation > 0.35 and value > 0.35 (the subject, if the form is strict)
  luminance                mean luminance of the live rows, once per second: a dip marks an event act
  acts                     spans split at luminance dips below --dip of the median (before / event / after, if present)
  motion                   mean absolute frame-to-frame change of the live rows, once per second
"""
from __future__ import annotations

import argparse
import io
import json
import pathlib
import subprocess
import sys

import numpy as np
from PIL import Image


def _run(cmd):
    return subprocess.run(cmd, capture_output=True, check=True)


def probe(video):
    out = _run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                "stream=width,height,r_frame_rate:format=duration", "-of", "json", str(video)]).stdout
    j = json.loads(out)
    st = j["streams"][0]
    num, den = st["r_frame_rate"].split("/")
    return {"width": int(st["width"]), "height": int(st["height"]), "fps": round(float(num) / float(den), 3),
            "duration_s": round(float(j["format"]["duration"]), 3)}


def cuts(video, thr):
    err = subprocess.run(["ffmpeg", "-v", "info", "-i", str(video), "-vf", f"select='gt(scene,{thr})',showinfo",
                          "-vsync", "vfr", "-f", "null", "-"], capture_output=True).stderr.decode("utf8", "replace")
    return [round(float(tok.split(":")[1]), 2) for line in err.splitlines() if "pts_time:" in line
            for tok in line.split() if tok.startswith("pts_time:")]


def frames(video, fps, width):
    """RGB frames sampled at `fps`, scaled to `width` px: array (n, h, w, 3) uint8."""
    raw = _run(["ffmpeg", "-v", "error", "-i", str(video), "-vf", f"fps={fps},scale={width}:-2",
                "-f", "image2pipe", "-vcodec", "ppm", "-"]).stdout
    out, pos = [], 0
    while pos < len(raw):
        im = Image.open(io.BytesIO(raw[pos:]))
        im.load()
        a = np.asarray(im.convert("RGB"))
        out.append(a)
        header_end = raw.index(b"\n255\n", pos) + 5
        pos = header_end + a.size
    return np.stack(out)


def _hex(c):
    return "#%02x%02x%02x" % tuple(int(round(v)) for v in c)


def palette(rgb, k=6, seed=0, iters=12):
    px = rgb.reshape(-1, 3).astype(float)
    rng = np.random.default_rng(seed)
    px = px[rng.choice(len(px), size=min(len(px), 40000), replace=False)]
    cen = px[rng.choice(len(px), size=k, replace=False)]
    for _ in range(iters):
        lab = np.argmin(((px[:, None, :] - cen[None]) ** 2).sum(-1), axis=1)
        cen = np.stack([px[lab == i].mean(0) if (lab == i).any() else cen[i] for i in range(k)])
    share = np.bincount(lab, minlength=k) / len(lab)
    order = np.argsort(-share)
    return [{"hex": _hex(cen[i]), "share": round(float(share[i]), 3)} for i in order]


def saturated_share(rgb):
    a = rgb.astype(float) / 255.0
    mx, mn = a.max(-1), a.min(-1)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-9), 0.0)
    return round(float(((sat > 0.35) & (mx > 0.35)).mean()), 4)


def bands(mask):
    """Runs of True in a 1-D boolean array as [start, end) pairs."""
    out, start = [], None
    for i, v in enumerate(mask):
        if v and start is None:
            start = i
        if not v and start is not None:
            out.append((start, i))
            start = None
    if start is not None:
        out.append((start, len(mask)))
    return out


def measure(video, cut=0.25, live=4.0, dip=0.75, width=360):
    info = probe(video)
    fr = frames(video, 1, width).astype(float)                      # one frame per second
    n, h, w, _ = fr.shape
    lum = fr @ np.array([0.2126, 0.7152, 0.0722])
    row_std = lum.std(axis=0).mean(axis=1)                          # temporal std per row
    live_rows = row_std > live
    min_run = max(2, h // 40)
    live_bands = [(a, b) for a, b in bands(live_rows) if b - a >= min_run]
    live_mask = np.zeros(h, bool)
    for a, b in live_bands:
        live_mask[a:b] = True
    med = np.median(fr, axis=0)
    series = lum[:, live_mask].mean(axis=(1, 2)) if live_mask.any() else lum.mean(axis=(1, 2))
    ref = float(np.median(series))
    dipped = series < dip * ref
    acts = []
    if dipped.any() and not dipped.all():
        ev = bands(dipped)[0]
        acts = [{"name": "before", "s": [0, int(ev[0])]}, {"name": "event", "s": [int(ev[0]), int(ev[1])]},
                {"name": "after", "s": [int(ev[1]), int(n)]}]
        for a in acts:
            a["share"] = round((a["s"][1] - a["s"][0]) / n, 3)
    mot = np.abs(np.diff(lum, axis=0))[:, live_mask].mean(axis=(1, 2)) if live_mask.any() and n > 1 else np.zeros(0)
    return {**info, "video": pathlib.Path(video).name, "cuts_s": cuts(video, cut),
            "scene_bands_frac": [[round(a / h, 3), round(b / h, 3)] for a, b in live_bands],
            "scene_share": round(float(live_mask.mean()), 3), "static_share": round(float(1 - live_mask.mean()), 3),
            "panels": len(live_bands), "palette": palette(med.astype(np.uint8)),
            "saturated_share": saturated_share(med.astype(np.uint8)),
            "luminance_per_s": [round(float(v), 1) for v in series], "acts": acts,
            "motion_per_s": [round(float(v), 2) for v in mot]}


def sheets(video, out, duration):
    cols = 5
    rows = int(np.ceil(max(1.0, duration) / cols))
    _run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vf", f"fps=1,scale=360:-2,tile={cols}x{rows}",
          "-frames:v", "1", str(out / "sheet.jpg")])
    mid = max(0.0, duration / 2 - 1)
    _run(["ffmpeg", "-v", "error", "-y", "-ss", f"{mid}", "-t", "2", "-i", str(video), "-vf",
          "fps=6,scale=240:-2,tile=6x2", "-frames:v", "1", str(out / "motion.jpg")])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("video")
    ap.add_argument("--out", required=True)
    ap.add_argument("--cut", type=float, default=0.25)
    ap.add_argument("--live", type=float, default=4.0)
    ap.add_argument("--dip", type=float, default=0.75)
    a = ap.parse_args(argv)
    out = pathlib.Path(a.out).resolve()
    if "out" not in out.parts:
        print("refused: --out must lie under out/ (ignored by git); reference frames are never committed", file=sys.stderr)
        return 2
    if not pathlib.Path(a.video).is_file():
        print(f"no such video: {a.video}", file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    m = measure(a.video, a.cut, a.live, a.dip)
    (out / "measure.json").write_text(json.dumps(m, indent=1))
    sheets(a.video, out, m["duration_s"])
    print(json.dumps({k: m[k] for k in ("duration_s", "width", "height", "cuts_s", "panels", "scene_share",
                                         "static_share", "saturated_share", "acts")}, indent=1))
    print(f"wrote {out}/measure.json, sheet.jpg, motion.jpg")
    return 0


if __name__ == "__main__":
    sys.exit(main())
