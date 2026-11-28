"""AIS positions for the deck.gl traffic layer: a deterministic subsample of a FETCHED HAIS clip, never anything else.

    block = load_traffic(path, bbox=(w, s, e, n))      # -> scene.json `traffic` (see offsim.scene.build_scene(traffic=))
    block = load_traffic_world("oslofjord", bbox=...)  # looks in data/worlds/<world>/ais/ (git-ignored), None when nothing is there

The data comes from the person's own HAIS order (Kystverket) or the BarentsWatch fetch, saved under data/worlds/<w>/ais/, which `.gitignore`
covers: it is never committed and never generated here. No file, no layer: `load_traffic_world` returns None and `world_stack` names why.

What the block claims: where vessels were, as a spatial density. The dots are NOT replayed against the simulation clock (`time_synchronised`
is False) and carry no time, so the layer cannot be mistaken for a claim about when anything happened. `epoch_utc` is the clip's first
timestamp, for the caption only. The caps (`max_vessels`, `max_points`) only keep scene.json small and are flagged assumption: they are
not sourced. The subsample is fixed-seed, so the same clip gives the same bytes."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from offsim.traffic.ais import filter_ais, load_ais

CAPS = {"max_vessels": 400, "max_points": 20000, "seed": 7, "assumption": True}    # size limits for scene.json, set by hand, not sourced
EXTS = (".parquet", ".geoparquet", ".csv")


def load_traffic(path, *, bbox=None, ship_types=None, source: str | None = None, max_vessels: int = CAPS["max_vessels"],
                 max_points: int = CAPS["max_points"], seed: int = CAPS["seed"]) -> dict | None:
    """Subsample a HAIS clip -> {points: [[lon, lat]], n_vessels, n_rows, source, epoch_utc, seed, caps_assumption, time_synchronised}.
    None when the filtered clip has no rows. `source` is the credit printed in the frame; default names the file, so it is never blank."""
    df = filter_ais(load_ais(path), bbox=bbox, ship_types=ship_types)
    if df.empty:
        return None
    rng = np.random.default_rng(seed)
    ids = np.sort(df["mmsi"].unique())
    if len(ids) > max_vessels:
        ids = np.sort(rng.choice(ids, size=max_vessels, replace=False))
        df = df[df["mmsi"].isin(ids)]
    df = df.sort_values(["mmsi", "timestamp"], kind="stable")
    xy = df[["lon", "lat"]].to_numpy()
    if len(xy) > max_points:
        xy = xy[np.sort(rng.choice(len(xy), size=max_points, replace=False))]
    return {"points": [[round(float(x), 5), round(float(y), 5)] for x, y in xy], "n_vessels": int(len(ids)), "n_rows": int(len(df)),
            "source": source or f"AIS clip {Path(str(path)).name} (Kystverket HAIS or BarentsWatch, fetched)",
            "epoch_utc": df["timestamp"].min().isoformat(), "seed": seed, "caps_assumption": True, "time_synchronised": False}


def load_traffic_world(world: str, *, root=None, **kw) -> dict | None:
    """The first clip in data/worlds/<world>/ais/ (sorted by name), or None when there is none."""
    root = Path(root) if root else Path(__file__).resolve().parents[2]
    d = root / "data/worlds" / world / "ais"
    clips = sorted(p for p in d.glob("*") if p.suffix.lower() in EXTS) if d.is_dir() else []
    return load_traffic(clips[0], **kw) if clips else None
