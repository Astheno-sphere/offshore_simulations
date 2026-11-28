"""The stress-pair delta as numbers, shared by both render paths: the skia plan panel (`motion/mappanel.py`) and the deck.gl scene
(`scene.py`, drawn by `render_deck/src/layers/delta.js`). numpy only, no drawing, so one geometry is tested once.

The data comes from `offsim.research.stress.load_stress_pair` (sidecars hash-verified there, in Python, where the report lives); nothing
here reads a file. `belongs_to` and `delta_block` add the guard the deck path needs: a pair is only embedded in a scene that shows the
run it was measured on.
"""
from __future__ import annotations

import numpy as np

from offsim.cinema.rules import DELTA_LAYER


def delta_geometry(pair, t):
    """The stress-pair delta at simulation time `t`, as numbers only (no drawing; the panel draws exactly this).

    `pair` is `offsim.research.stress.load_stress_pair(...)`: two validated tracks of one agent, a = compare[0] (candidate) and
    b = compare[1] (baseline). Rungs are the paired positions a(t_i)-b(t_i) on the union of both time grids over the window both
    tracks cover, up to `t`, plus a front rung at `t` itself so the ribbon grows smoothly between samples; each track is
    piecewise linear in lon/lat, so these rungs are the same evaluation `research.stress.divergence` maximises, and the widest
    rung IS the report's `max_divergence_m` once `t` has passed t*. The ribbon is the ring "a forward, b reversed", a single
    region whose width at any moment is the divergence at that moment: it carries no tunable number.

    Returns {rung_t, pa, pb (n,2 lon/lat), track_a, track_b (done part of each track, ending at t), connector ((lon,lat) a, b) or None
    until t reaches t_star_s}.
    """
    a, b = pair["compare"]
    (t1, lo1, la1), (t2, lo2, la2) = pair["tracks"][a], pair["tracks"][b]
    lo_t, hi_t = max(t1[0], t2[0]), min(t1[-1], t2[-1])
    grid = np.union1d(t1, t2)
    grid = grid[(grid >= lo_t) & (grid <= hi_t)]
    if t < lo_t:
        rt = grid[:0]
    else:
        tc = min(t, hi_t)
        rt = grid[grid <= tc]
        if len(rt) == 0 or rt[-1] < tc:
            rt = np.append(rt, tc)

    def at(tt, ts, lo, la):
        return np.c_[np.interp(tt, ts, lo), np.interp(tt, ts, la)]

    def done(ts, lo, la):
        if t < ts[0]:
            return np.zeros((0, 2))
        k = ts <= t
        pts = np.c_[lo[k], la[k]]
        if ts[-1] > t:                       # the track is still under way: end it on the interpolated position at t
            pts = np.vstack([pts, at(np.array([t]), ts, lo, la)])
        return pts

    star = pair["t_star_s"]
    conn = None
    if t >= star:
        ts_ = np.array([star])
        conn = (tuple(at(ts_, t1, lo1, la1)[0]), tuple(at(ts_, t2, lo2, la2)[0]))
    return {"rung_t": rt, "pa": at(rt, t1, lo1, la1), "pb": at(rt, t2, lo2, la2),
            "track_a": done(t1, lo1, la1), "track_b": done(t2, lo2, la2), "connector": conn}


def _track(traj, agent_id):
    """(t, lon, lat) of one agent, strictly increasing t, exactly as `research.stress` prepares tracks."""
    g = traj[traj["agent_id"].astype(str) == str(agent_id)].sort_values("t", kind="stable")
    t, lo, la = g["t"].to_numpy(float), g["lon"].to_numpy(float), g["lat"].to_numpy(float)
    if not len(t):
        return t, lo, la
    keep = np.r_[t[1:] > t[:-1], True]
    return t[keep], lo[keep], la[keep]


def belongs_to(pair, traj):
    """The variant name whose sidecar track IS the scene's validated track for the pair's agent, else None.

    A stress pair is a claim about two specific runs. Drawn over a scene that shows some other run (other agent, other clock, another
    part of the world) it would be a claim about the wrong simulation, so the deck path refuses it unless one of the two tracks
    matches the scene's validated trajectory point for point (same times, same lon/lat to 1e-9 degrees)."""
    t, lo, la = _track(traj, pair["agent_id"])
    for name in pair["compare"]:
        ts, lo2, la2 = pair["tracks"][name]
        if len(ts) == len(t) and len(t) and np.allclose(ts, t, rtol=0, atol=1e-6) \
                and np.allclose(lo2, lo, rtol=0, atol=1e-9) and np.allclose(la2, la, rtol=0, atol=1e-9):
            return name
    return None


def delta_block(pair, traj):
    """The `delta` block of scene.json: everything the deck.gl layer draws, derived from the verified pair. Raises ValueError when the
    pair does not belong to the run `traj` shows.

    rung_t/pa/pb are the full-window rungs (the layer draws those with rung_t <= t, plus a front rung interpolated between the last
    drawn rung and the next, which is exact because both tracks are linear between rungs); ribbon_polys is the same ring closed over the
    whole window; track_a/track_b are the two tracks with their own times; t_star_connector is the pair at t_star_s. `style` is
    rules.DELTA_LAYER (assumption: set by eye). a = compare[0] (candidate), b = compare[1] (baseline).
    """
    which = belongs_to(pair, traj)
    if which is None:
        raise ValueError(f"stress pair for agent {pair['agent_id']!r} ({pair['compare']}) does not belong to the run this scene shows: "
                         "neither of its sidecar tracks equals the scene's validated trajectory; refusing to draw a claim about another simulation")
    a, b = pair["compare"]
    g = delta_geometry(pair, 1e18)
    ring = [[float(x), float(y)] for x, y in g["pa"]] + [[float(x), float(y)] for x, y in g["pb"][::-1]]
    star = pair["t_star_s"]
    conn = delta_geometry(pair, star)["connector"]
    return {
        "variant_names": [a, b], "agent_id": pair["agent_id"], "draft": bool(pair.get("draft")),
        "max_divergence_m": float(pair["max_divergence_m"]), "t_star_s": float(star), "matches_scene_variant": which,
        "rung_t": [float(x) for x in g["rung_t"]],
        "pa": [[float(x), float(y)] for x, y in g["pa"]], "pb": [[float(x), float(y)] for x, y in g["pb"]],
        "ribbon_polys": [ring + [ring[0]]],
        "track_a": {"path": [[float(x), float(y)] for x, y in zip(pair["tracks"][a][1], pair["tracks"][a][2])],
                    "ts": [float(x) for x in pair["tracks"][a][0]]},
        "track_b": {"path": [[float(x), float(y)] for x, y in zip(pair["tracks"][b][1], pair["tracks"][b][2])],
                    "ts": [float(x) for x in pair["tracks"][b][0]]},
        "t_star_connector": [[float(x), float(y)] for x, y in conn],
        "style": {"ribbon_alpha": DELTA_LAYER["ribbon_alpha"], "track_px": DELTA_LAYER["track_px"], "dash_px": list(DELTA_LAYER["dash_px"])},
    }
