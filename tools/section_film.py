"""Section + map diptych in the section-plan grade: PSV heading into a gale, exhaust over the aft deck.

    PYTHONPATH=. python tools/section_film.py --out out/film/psv_section.mp4 [--seconds 5 --fps 30]
    PYTHONPATH=. python tools/section_film.py --mode demo --out <demo-v6.mp4>   # full 24 s supply run


Thin wrapper: the film is the `section` shot type of the standard pipeline (offsim/motion/section.py, storyboard
`type: section`). Every moving element is a simulation variable; inputs are ASSUMED (vessel geometry, exhaust
temperature, weather) and labelled DRAFT; the deck text is chosen from measurements (offsim/motion/narrate.py).
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import numpy as np

from offsim.cinema.look import PALETTES
from offsim.motion import section as S
from offsim.motion.section import (PSV_GALE_NARRATION, Scene, Streaks, map_context, route_at,
                                   render_section_shot, run_section)  # noqa: F401

P = PALETTES["section-plan"]
W, H = 1080, 1350


def gale_shot(seconds=5.0, hs=2.0, tp=6.5, u10=15.0, t_exh=520.0):
    return {"type": "section", "seconds": seconds, "vessel": "psv",
            "hs": {"value": hs, "assumption": True}, "tp": {"value": tp, "assumption": True},
            "u10": {"value": u10, "assumption": True}, "t_exh": {"value": t_exh, "assumption": True},
            "kicker": "OUTER OSLOFJORD GALE  ·  SIMULATED",
            "headline": {"top": "WHERE DOES THE", "accent": "EXHAUST", "rest": "GO IN A GALE?"},
            "map": {"world": "oslofjord", "run": "out/demo-oslofjord-supply", "agent": "PSV-1", "label": "OSLOFJORD DEMO SUPPLY RUN"},
            "narration": PSV_GALE_NARRATION}




def run_context(world="oslofjord", run="out/demo-oslofjord-supply"):
    """Full-run context for the demo film: every vessel's route + times, the union bbox, and the run's
    measured totals from report.json (never typed by hand). Returns None if the run failed gates 0-3.
    Builds on map_context's fields for the section vessel (PSV-1) so the 5 s study is unchanged."""
    import json

    import geopandas as gpd
    import pandas as pd
    land_p, traj_p, rep_p = Path(f"data/worlds/{world}/land.geojson"), Path(run) / "trajectory.csv", Path(run) / "report.json"
    if not (land_p.exists() and traj_p.exists() and rep_p.exists()):
        return None
    rep = json.loads(rep_p.read_text())
    if not all(g["pass"] for k, g in rep["gates"].items() if k.startswith(("0", "1", "2", "3"))):
        return None                                           # never map a run that failed a gate
    tr = pd.read_csv(traj_p).sort_values(["agent_id", "t"]).reset_index(drop=True)
    routes, times = {}, {}
    for agent, g in tr.groupby("agent_id"):
        routes[agent] = list(zip(g.lon, g.lat))
        times[agent] = g.t.to_numpy()
    lon = np.concatenate([np.array(r).T[0] for r in routes.values()])
    lat = np.concatenate([np.array(r).T[1] for r in routes.values()])
    pad = 0.06
    bbox = (lon.min() - pad, lat.min() - pad * 0.6, lon.max() + pad, lat.max() + pad * 0.6)
    land = gpd.read_file(land_p).geometry.union_all()
    from shapely.geometry import box
    land = land.intersection(box(bbox[0] - 1.5, bbox[1] - 0.6, bbox[2] + 1.5, bbox[3] + 0.6))
    ctx = map_context(world, run, agent="PSV-1") or {}
    makespan_s = float(max(t.max() for t in times.values()))
    # distance + sites from the gated report (gate 2 replay KPI, gate 1 routes); sites = stops served
    dist_km = next((k["ours"] for k in rep["gates"]["2_replay_equals_plan"]["detail"] if k["kpi"] == "distance_km"), float("nan"))
    sites = sum(len(r) for r in rep["gates"]["1_plan"]["detail"]["routes"])
    ctx.update({"land": land, "bbox": bbox, "routes": routes, "times": times, "makespan_s": makespan_s,
                "distance_km": dist_km, "vessels": len(routes), "sites": sites, "agents": sorted(routes),
                "world_dir": Path(f"data/worlds/{world}")})
    # v9: OSM places + roads for the named map (fetched 2026-11-09 by Overpass POST into
    # data/worlds/oslofjord/osm/; every name comes from places_demo.json — a name absent from the
    # file is skipped, never guessed). The fjord name is OSM-verified (natural=bay); its anchor is
    # a cartographic choice on open water in the visible fjord, not the OSM centre (which sits at
    # the top edge of the bbox). Sites S1..S6 come from the scenario (the source of truth).
    places, roads = [], None
    places_p = Path(f"data/worlds/{world}/osm/places_demo.json")
    if places_p.exists():
        fetched = json.loads(places_p.read_text())
        want = {"Moss": "MOSS · FERRY", "Horten": "HORTEN · FERRY", "Åsgårdstrand": "ÅSGÅRDSTRAND",
                "Larkollen": "LARKOLLEN", "Bastøy": "BASTØY", "Østre Bolæren": "ØSTRE BOLÆREN",
                "Borre": "BORRE", "Vealøs": "VEALØS"}
        for p in fetched:
            if p["name"] in want and p["kind"] in ("city", "town", "village", "island"):
                places.append({"text": want[p["name"]], "lat": p["lat"], "lon": p["lon"], "kind": "place"})
        if any(p["name"] == "Oslofjorden" and p["kind"] == "bay" for p in fetched):
            places.append({"text": "OSLOFJORDEN", "lat": 59.30, "lon": 10.58, "kind": "fjord",
                           "color": "#7ba3ad"})
    scen_p = Path("offsim/papers/demo-oslofjord-supply/scenario.yaml")
    if scen_p.exists():
        import yaml
        scen = yaml.safe_load(scen_p.read_text())
        for s in scen.get("instance", {}).get("stops", []):
            places.append({"text": s["name"], "lat": s["lat"], "lon": s["lon"], "kind": "site", "size": 11})
    roads_p = Path(f"data/worlds/{world}/osm/roads_demo.geojson")
    if roads_p.exists():
        roads = json.loads(roads_p.read_text())
    roads_wide_p = Path(f"data/worlds/{world}/osm/roads_wide.geojson")
    if roads_wide_p.exists():
        roads = json.loads(roads_wide_p.read_text())
    # v9: the map's land is WIDER than the sim's contract land — the demo map's view at span 4.0 is
    # 1.12 deg lon wide but land.geojson covers only the route bbox (0.28 deg), so the panel edges
    # rendered as sea where there is land (hard vertical cuts at f0000/f0719). land_wide.geojson
    # (Overpass coastline, lon 10.00-11.10 / lat 59.00-59.60, sea_polygons, 431 s) covers the view;
    # verified 7/7 (Moss/Horten/Bastøy/Tønsberg on land; S1/S2/mid-fjord in sea). The sim's contract
    # land (ctx["land"]) is untouched — the wide land is display only.
    map_land = None
    land_wide_p = Path(f"data/worlds/{world}/osm/land_wide.geojson")
    if land_wide_p.exists():
        map_land = gpd.read_file(land_wide_p).geometry.union_all()
    ctx.update({"places": places, "roads": roads, "map_land": map_land})
    return ctx


def narration(series, run=None):
    """Deck text chosen from what the run measured (never written before the run). With run=None this is the
    v5 section study; with run=run_context() it is the full-run film (totals from the gated report)."""
    deck = max(v for _, v, _ in series)
    hs = [h for _, _, h in series if np.isfinite(h)]
    low = min(hs) if hs else float("nan")
    if run is not None:
        # deck lines must fit one line at font 22 (968 px); keep them short — the section + WHERE line
        # already say where and when.
        line1 = (f"{run['vessels']} vessels, {run['sites']} sites, "
                 f"{run['distance_km']:.0f} km in {run['makespan_s'] / 3600:.1f} h —")
        if deck >= 5:
            return (line1,
                    f"but the hot gas reaches the deck: up to +{deck:.0f} °C where the crew breathe.")
        return (line1,
                f"the hot gas never drops below {low:.0f} m over the deck: the crew zone stays clear.")
    if deck >= 5:
        return ("Bow into the wind, the funnel's hot gas is caught in the lee of the bridge",
                f"and reaches the cargo deck: up to +{deck:.0f} °C in the crew's breathing zone.")
    return ("Bow into the wind, the funnel's hot gas rolls into eddies behind the bridge",
            f"but never comes lower than {low:.0f} m above the cargo deck: the crew zone stays clear.")


HEADLINE_V5 = [[("WHERE DOES THE", False)], [("EXHAUST", True), (" GO IN A GALE?", False)]]
HEADLINE_DEMO = [[("DOES THE ", False), ("SHORTEST", True)], [("PLAN HOLD IN A GALE?", False)]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out/film/psv_section.mp4")
    ap.add_argument("--mode", choices=["section", "demo"], default="section",
                    help="section: the 5 s gale study (v5); demo: the full 24 s supply run (v6)")
    ap.add_argument("--seconds", type=float, default=None, help="film length; default 5 s (section) / 24 s (demo)")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--hs", type=float, default=2.0)     # outer-fjord gale sea (assumed); Hs 3.5 is open North Sea
    ap.add_argument("--tp", type=float, default=6.5)
    ap.add_argument("--u10", type=float, default=15.0)
    ap.add_argument("--only", type=int, default=None, help="render a single frame index (still check)")
    ap.add_argument("--resume-from", type=int, default=None,
                    help="resume a killed render: skip frames < N (already on disk, same deterministic run)")
    a = ap.parse_args()
    demo = a.mode == "demo"
    seconds = a.seconds if a.seconds is not None else (24.0 if demo else 5.0)
    out = Path(a.out)
    frames = out.parent / "frames"
    if not demo:
        # section mode: the upstream thin-wrapper path (offsim/motion/section library).
        shot = gale_shot(seconds, a.hs, a.tp, a.u10)
        if a.only is not None:
            res = run_section(shot, None, frames, a.fps, None, None, a.only, strict_map=False)
            print(res["frames"][0])
            return
        render_section_shot(shot, None, out, a.fps, frames_dir=frames, keep_frames=True, strict_map=False)
        return
    # demo mode: the v6 two-pass path (library Scene/Streaks, library render with demo kwargs + follow-cam map).
    frames.mkdir(parents=True, exist_ok=True)
    dt, sub, n = 0.015, 3, int(seconds * a.fps)

    ctx = run_context()
    from offsim.motion.mappanel import MapPanel
    # Demo mode is a dead-zone glide camera over the full run (v9): no zoom (seconds=0), a 4.0x overview,
    # no map wind streaks — the airflow lives in the section panel only, and the camera glides at most
    # 1.8 panel-widths per film (peak 0.074 widths/s, 36% under v6's follow-cam 0.116) instead of
    # locking onto a vessel covering 4.7 km/s of map at 834x time compression. The span + cap were
    # measured, not guessed: at span 3.2 / cap 1.2 the marker leaves the frame on the 193-frame
    # southward run (the camera cap cannot keep up with a 2.8 px/frame marker); span 4.0 / cap 1.8
    # holds it with worst centre-distance 0.41 of the half-frame (test_draw), and the camera stands
    # still for 212/720 frames (at the sites). A static wide map cannot work here: the route is
    # 9 km wide x 31 km tall in a 3.2:1 panel, so it would shrink to ~7% of the panel width.
    mp = MapPanel(ctx.get("map_land") or ctx["land"], ctx["bbox"], size=(W - 112, 300), seconds=0.0, span_mult=4.0,
                  world_dir=ctx["world_dir"], camera="smooth", wind_streaks=False, pan_cap=1.8,
                  roads=ctx.get("roads"), places=ctx.get("places")) if ctx else None
    draft = ("DRAFT: vessel geometry, exhaust temperature (520 K) and weather are assumptions; "
             "ship motion display-grade. Run is synthetic (gate 4 not comparable).")

    def simulate(render_frames, deck_text=None):
        sc = Scene(a.hs, a.tp, a.u10)
        st = Streaks(sc)
        for _ in range(360):                                  # spin-up: let the wake and plume develop
            sc.step(dt)
            st.advance(dt)
        series = []
        for f in range(n):
            for _ in range(sub):
                sc.step(dt)
                if render_frames:
                    st.advance(dt)
            series.append((sc.t, sc.deck_air_excess(), sc.plume_height()))
            if (render_frames and (a.only is None or f == a.only)
                    and (a.resume_from is None or f >= a.resume_from)):
                run_t = (f + 1) / n * ctx["makespan_s"]       # map moment advances over the full run
                others = []
                for ag in ctx["agents"]:
                    if ag == ctx["agent"]:
                        continue
                    dk, mk = route_at(ctx["routes"][ag], ctx["times"][ag], run_t)
                    others.append((ag, ctx["routes"][ag], dk, mk))
                if a.only is not None and mp is not None and mp.camera == "smooth" and mp._cam is None:
                    # a single-frame still must show the camera where the glide would have put it
                    # after f frames of following, not opened on the vessel at frame f
                    for ff in range(f):
                        _, mk_ff = route_at(ctx["routes"][ctx["agent"]], ctx["times"][ctx["agent"]],
                                            (ff + 1) / n * ctx["makespan_s"])
                        mp._view((ff + 1) / n, mk_ff)
                S.render(sc, st, series, f, n, frames / f"f{f:04d}.png", deck_text, mp, ctx,
                       headline=HEADLINE_DEMO,
                       kicker="OSLOFJORD DEMO SUPPLY RUN  ·  SIMULATED",
                       run_t=run_t, others=others, sea_fill=P["sea"], draft_text=draft)
                if a.only is not None:
                    return series, sc
        return series, sc

    if a.resume_from is not None:
        # A resume is only honest if the earlier frames are really there, from the same run.
        missing = [f for f in range(a.resume_from) if not (frames / f"f{f:04d}.png").exists()]
        if missing:
            raise SystemExit(f"--resume-from {a.resume_from}: {len(missing)} earlier frames missing "
                             f"(first f{missing[0]:04d}.png); refusing to encode a gapped film")
        print(f"resuming from f{a.resume_from:04d}: {a.resume_from} frames already on disk")
    series, _ = simulate(False)                               # pass 1: measure (deterministic)
    text = narration(series, ctx)
    print("narration:", " ".join(text))
    print(f"run: {ctx['vessels']} vessels, {ctx['sites']} sites, {ctx['distance_km']:.3f} km, "
          f"makespan {ctx['makespan_s'] / 3600:.2f} h")
    series, sc = simulate(True, text)                         # pass 2: render the same run
    if a.only is not None:
        print(frames / f"f{a.only:04d}.png")
        return
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(a.fps), "-i", str(frames / "f%04d.png"),
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", str(out)], check=True)
    print(out, f"{n} frames, sim {sc.t:.1f} s")


if __name__ == "__main__":
    main()
