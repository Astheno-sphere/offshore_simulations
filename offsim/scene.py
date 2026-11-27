"""Build a renderer scene (JSON) from a *validated* trajectory. The renderer never sees anything else."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from offsim.contract import Report

ROOT = Path(__file__).resolve().parent.parent
WORLD_STACK_LAYERS = ("coast", "lanes", "dem_hillshade", "isobaths", "metocean", "ais")


def polygons(geom):
    """shapely (Multi)Polygon in lon/lat -> deck.gl PolygonLayer rings [[outer], [hole], ...]."""
    if geom is None or geom.is_empty:
        return []
    parts = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
    return [[[list(c) for c in p.exterior.coords]] + [[list(c) for c in h.coords] for h in p.interiors] for p in parts]


def build_scene(traj: pd.DataFrame, agents: pd.DataFrame, report: Report, *, camera: dict, overlay: dict,
                land=None, lanes=None, sites=None, accent=(), kpi_track=None, seconds=20, trail_s=None,
                land_relief_m=None, display=None, terrain=None, weather=None, camera_track=None,
                delta_pair=None, traffic=None, absent_reasons=None) -> dict:
    """camera: deck.gl view state {longitude, latitude, zoom, pitch, bearing}.
    overlay: {kicker, title, legend: [[hex, label]], source, watermark}. accent: agent ids drawn in the accent.
    kpi_track: [[label, [[t, display_value], ...]], ...] values shown over time (from offsim.contract.kpis only).

    delta_pair: `offsim.research.stress.load_stress_pair(...)` (sidecars already hash-verified there). It is embedded as `scene["delta"]`
    only when it belongs to the run `traj` shows (`motion.delta.belongs_to`); otherwise ValueError. A draft pair stamps the frame.
    traffic: an AIS block from `offsim.traffic.positions.load_traffic` (fetched HAIS data only); None draws nothing.
    absent_reasons: {layer: why} for layers the caller knows are missing (see `diagnose_world`); `scene["world_stack"]` names every
    layer of WORLD_STACK_LAYERS as present, or absent with a reason, so an empty layer is never silent."""
    if not report.ok:
        raise ValueError(f"refusing to build a scene from an invalid trajectory\n{report}")
    cls = agents.set_index("agent_id")["cls"].to_dict()
    out = []
    for aid, g in traj.groupby("agent_id", sort=False):
        if display and aid in display:     # display-only copy (offsim.cinema.vessel); truth was validated above
            d = display[aid]
            out.append({"id": str(aid), "cls": cls[aid], "accent": aid in accent, **{k: d[k] for k in
                        ("path", "ts", "states", "heading", "roll", "pitch", "heave") if k in d}})
            continue
        alt = g["alt_m"] if "alt_m" in g else 0.0
        out.append({"id": str(aid), "cls": cls[aid], "accent": aid in accent,
                    "path": [[float(x), float(y), float(z)] for x, y, z in zip(g["lon"], g["lat"], alt if hasattr(alt, "__iter__") else [alt] * len(g))],
                    "ts": [float(t) for t in g["t"]], "states": list(g["state"])})
    t0, t1 = float(traj["t"].min()), float(traj["t"].max())
    delta = None
    if delta_pair is not None:
        from offsim.motion.delta import delta_block
        delta = delta_block(delta_pair, traj)               # raises when the pair is about some other run
        if delta["draft"] and not overlay.get("stamp"):
            overlay = {**overlay, "stamp": "DRAFT, NOT REPORTABLE"}
        names = {v for v, _ in (overlay.get("legend") or [])}
        legend = list(overlay.get("legend") or [])
        st = json.loads((ROOT / "offsim/style.json").read_text())      # the colours layers/delta.js draws the two tracks in
        for nm, col in ((delta["variant_names"][1], st["paper"]), (delta["variant_names"][0], st["accent"])):
            if nm not in names:
                legend.append([col, nm])
        overlay = {**overlay, "legend": legend}
    scene = {"t0": t0, "t1": t1, "land_relief_m": land_relief_m, "seconds": seconds, "trail_s": trail_s or (t1 - t0) / 6,
             "camera": camera, "overlay": {**overlay, "kpi_track": kpi_track or []},
             "world": {"land": polygons(land), "lanes": lanes or [], "sites": sites or [], "terrain": terrain},
             "weather": weather, "agents": out,
             "domains": agents.set_index("cls")["domain"].to_dict() if "domain" in agents else {},
             "display_max_offset_m": (display or {}).get("max_offset_m")} | ({"camera": {**camera, "track": camera_track}} if camera_track else {})
    if delta is not None:
        scene["delta"] = delta
    if traffic is not None:
        scene["traffic"] = traffic
    scene["world_stack"] = world_stack(scene, absent_reasons)
    return scene


def world_stack(scene: dict, reasons: dict | None = None) -> dict:
    """Which world layers the scene actually carries, derived from the scene itself, and why each missing one is missing.

    -> {layer: {"present": True, "detail": ...} | {"present": False, "reason": ...}} for every layer in WORLD_STACK_LAYERS. Presence is
    read from the scene's content, never from a file path, so it cannot disagree with what the renderer draws. A missing layer's reason is
    the caller's (`reasons[layer]`, see `diagnose_world`) or, failing that, the argument that was not passed: never an empty string.
    The renderer prints this at start and the frame can name the absences, so an empty map is a named absence, not a mystery."""
    reasons = reasons or {}
    w = scene.get("world") or {}
    terr = w.get("terrain") or {}
    wx = scene.get("weather") or {}
    iso = (terr.get("isobaths") or {}).get("features") if isinstance(terr.get("isobaths"), dict) else terr.get("isobaths")
    trips = ((wx.get("particles") or {}).get("trips")) or []
    frames = ((wx.get("hs") or {}).get("frames")) or []
    tr = scene.get("traffic") or {}
    found = {
        "coast": (bool(w.get("land")), f"{len(w.get('land') or [])} polygons", "no land polygons in the scene (land= was None or empty)"),
        "lanes": (bool(w.get("lanes")), f"{len(w.get('lanes') or [])} lanes", "no lanes in the scene (lanes= was None or empty)"),
        "dem_hillshade": (bool((terr.get("texture") or {}).get("image")),
                          "baked hillshade" + (" + terrain mesh" if terr.get("positions") else ""),
                          "no terrain/hillshade in the scene (terrain= was None: no depth bundle was loaded)"),
        "isobaths": (bool(iso), f"{len(iso or [])} contour features", "no isobaths in the scene (terrain= was None or has no isobaths.geojson)"),
        "metocean": (bool(trips or frames or wx.get("arrows")),
                     f"{len(trips)} particle trips, {len(frames)} Hs frames; {wx.get('credit', 'source not stated')}",
                     "no weather block in the scene (weather= was None)"),
        "ais": (bool(tr.get("points")), f"{len(tr.get('points') or [])} positions, {tr.get('n_vessels', '?')} vessels; {tr.get('source', 'source not stated')}",
                "no traffic block in the scene (traffic= was None)"),
    }
    out = {}
    for layer in WORLD_STACK_LAYERS:
        ok, detail, default = found[layer]
        out[layer] = {"present": True, "detail": detail} if ok else {"present": False, "reason": reasons.get(layer) or default}
    return out


def diagnose_world(world: str, tier: str = "fjord", root=None) -> dict:
    """{layer: why it is absent} for a world, from what is (not) in data/worlds/<world>/. Pass it as `absent_reasons=` to `build_scene`.
    It only explains absences; whether a layer is present is decided by `world_stack` from the scene's content."""
    d = Path(root or ROOT) / "data/worlds" / world
    why = {}
    if not (d / "land.geojson").exists():
        why["coast"] = f"{d}/land.geojson is missing: python -m offsim.worlds.fetch_world --pull {world}"
    if not (d / "depth" / tier / "terrain.json").exists():
        if (d / "dem_raw").exists():
            why["dem_hillshade"] = why["isobaths"] = (f"raw DEM is pulled ({d}/dem_raw) but not processed: run offsim.worlds.depth.build_world_depth "
                                                       f"to write depth/{tier}/terrain.json, hillshade.png, isobaths.geojson")
        else:
            why["dem_hillshade"] = why["isobaths"] = (f"no DEM: nothing at {d}/depth/{tier}. python -m offsim.worlds.fetch_world --pull {world} --depth "
                                                       f"needs the release world-{world}-dem-raw, which the fetch-world workflow publishes only when it is "
                                                       "run with depth=true; then offsim.worlds.depth.build_world_depth")
    if not (d / "metocean").exists():
        why["metocean"] = (f"no metocean in {d}/metocean: fetch-world with metocean_start and nora3_wind,nora3_wave (or --metocean START HOURS). "
                           "Only synthetic weather can stand in, and a scene built on it must be stamped DRAFT, NOT REPORTABLE")
    if not (any((d / "ais").glob("*.parquet")) or any((d / "ais").glob("*.csv"))):
        why["ais"] = (f"no AIS positions in {d}/ais: place a Kystverket HAIS Parquet/CSV clip there (calibration.json alone holds statistics, not "
                      "positions). The BarentsWatch API client is a spec and its BW_CLIENT_ID/BW_CLIENT_SECRET are not set up")
    return why


def load_terrain(depth_dir) -> dict | None:
    """terrain.json + isobaths.geojson + hillshade.png (as data URL) from offsim.worlds.depth.build_world_depth output."""
    import base64

    d = Path(depth_dir)
    if not (d / "terrain.json").exists():
        return None
    t = json.loads((d / "terrain.json").read_text())
    if (d / "isobaths.geojson").exists():
        t["isobaths"] = json.loads((d / "isobaths.geojson").read_text())
    if (d / "hillshade.png").exists():
        t.setdefault("texture", {})["image"] = "data:image/png;base64," + base64.b64encode((d / "hillshade.png").read_bytes()).decode()
    return t


def write(scene: dict, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(scene, separators=(",", ":")))
    return path
