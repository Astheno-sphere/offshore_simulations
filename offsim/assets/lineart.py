"""CAD-style line art from our glTF models: feature edges (creases) + outline, projected to a plan
view (top-down, for the map) and a side elevation (for explainers). Output is vector geometry in
metres, so the renderer draws it as lines at any zoom, rotated by heading.

    python -m offsim.assets.lineart            # models/*.glb -> lineart/*.json

JSON: {"plan": [[[x, y], [x, y]], ...], "side": [...], "bbox_plan": [...], "units": "m", "forward": "+y"}
"""
import json
from pathlib import Path

import numpy as np
import trimesh

HERE = Path(__file__).resolve().parent
CREASE_DEG = 25.0


def load(glb):
    scene = trimesh.load(glb, force="scene")
    mesh = scene.to_geometry() if hasattr(scene, "to_geometry") else scene.dump(concatenate=True)
    # glTF is Y-up; our models were authored Z-up, +Y forward: rotate back to Z-up
    mesh.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
    return mesh


def feature_edges(mesh, crease_deg=CREASE_DEG):
    """Edges where adjacent faces bend more than crease_deg, plus open/boundary edges."""
    adj = mesh.face_adjacency
    angles = mesh.face_adjacency_angles
    sharp = mesh.face_adjacency_edges[angles > np.radians(crease_deg)]
    counts = np.bincount(mesh.edges_unique_inverse, minlength=len(mesh.edges_unique))
    boundary = mesh.edges_unique[counts == 1]
    edges = np.vstack([sharp, boundary]) if len(boundary) else sharp
    return mesh.vertices[edges]                      # (n, 2, 3)


def project(segs, drop_axis, keep=(0, 1), decimals=2, min_len=0.05):
    """Orthographic projection: drop one axis, merge duplicates, drop dots."""
    seg2 = np.round(segs[:, :, list(keep)], decimals)
    lens = np.linalg.norm(seg2[:, 1] - seg2[:, 0], axis=1)
    seg2 = seg2[lens > min_len]
    key = {tuple(sorted(map(tuple, s))) for s in seg2.tolist()}
    return [list(map(list, s)) for s in sorted(key)]


def lineart(glb):
    m = load(glb)
    segs = feature_edges(m)
    plan = project(segs, drop_axis=2, keep=(0, 1))   # x across, y forward
    side = project(segs, drop_axis=0, keep=(1, 2))   # y forward, z up
    xy = np.array([p for s in plan for p in s]) if plan else np.zeros((1, 2))
    return {"plan": plan, "side": side, "bbox_plan": [*xy.min(0).tolist(), *xy.max(0).tolist()],
            "units": "m", "forward": "+y", "source": Path(glb).name}


def main():
    out = HERE / "lineart"
    out.mkdir(exist_ok=True)
    for glb in sorted((HERE / "models").glob("*.glb")):
        art = lineart(glb)
        (out / f"{glb.stem}.json").write_text(json.dumps(art, separators=(",", ":")))
        print(f"{glb.stem:13s} plan {len(art['plan']):4d} lines · side {len(art['side']):4d} lines · bbox {np.round(art['bbox_plan'], 1).tolist()}")


if __name__ == "__main__":
    main()
