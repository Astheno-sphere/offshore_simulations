"""Sea polygons from OSM coastline ways, which keep land on the left and sea on the right.

Borrowed unchanged from Astheno-sphere/computational_Logistics (skills/visual-narrative/scripts/coast.py, MIT).
"""
import numpy as np
from shapely.geometry import MultiLineString, Point, box
from shapely.ops import linemerge, polygonize, unary_union


def sea_polygons(coast, bounds, probe=4.0):
    """coast: GeoDataFrame of natural=coastline in a metric CRS (lines, plus closed rings that OSMnx
    turned into island polygons). bounds: (x0, y0, x1, y1) of the area to fill.
    Returns (sea geometry, bounds actually filled)."""
    frame = box(*bounds)
    lines = [p for g in coast.geometry if g.geom_type in ("LineString", "MultiLineString")
             for p in (g.geoms if g.geom_type == "MultiLineString" else [g])]
    islands = [g for g in coast.geometry if g.geom_type in ("Polygon", "MultiPolygon")]
    # join ways end to start; directed, because direction is what says which side is sea
    merged = linemerge(MultiLineString(lines), directed=True) if lines else None
    # an extract cut on a lat/lon box ends its coastline on a curved edge: shrink the metric frame
    # until every loose coastline end lies outside it, so the coast splits the frame cleanly
    parts = [] if merged is None else (list(merged.geoms) if merged.geom_type == "MultiLineString" else [merged])
    ends = [Point(p.coords[k]) for p in parts if not p.is_closed for k in (0, -1)]
    inside = [e.distance(frame.exterior) for e in ends if frame.contains(e)]
    if inside:
        frame = box(*frame.buffer(-(max(inside) + 1.0), join_style=2).bounds)
    # node the uncut lines with the frame edge (clipping first leaves endpoints a hair off the edge)
    noded = unary_union([frame.boundary] + ([merged] if merged else []))
    faces = [f for f in polygonize(noded) if frame.contains(f.representative_point())]
    # vote: a point just right of each coastline segment is sea, just left is land.
    # Two speed traps, both measured on Bergen-NCS (34k ways, 1.06M segments, 13,500 faces):
    # (1) the naive scan is O(segments x faces) — that blew the 15-min coast budget;
    # (2) STRtree.query(predicate="within") is NOT a fix either: the predicate runs an
    # unprepared point-in-polygon over the whole ring of each bbox candidate (~385 us
    # per probe against the 182k-vertex sea face). So: bbox candidates from one vectorized
    # STRtree query, then prepared-geometry contains() (indexed point-in-polygon, ~us),
    # first match per probe. Votes are identical to the predicate version (faces are
    # disjoint, so at most one face contains a probe point); verified on a 2,000-probe
    # sample and on the synthetic split-frame/island cases.
    from shapely.prepared import prep
    from shapely.strtree import STRtree
    import shapely
    tree = STRtree(faces)
    prepped = [prep(f) for f in faces]
    px, py, pw = [], [], []
    for ln in parts:
        xy = np.asarray(ln.coords, dtype=float)
        if len(xy) < 2:
            continue
        d = xy[1:] - xy[:-1]
        n = np.hypot(d[:, 0], d[:, 1])
        ok = n > 0
        if not ok.any():
            continue
        d, n = d[ok], n[ok]
        mid = (xy[:-1][ok] + xy[1:][ok]) / 2
        off = np.column_stack([d[:, 1] / n * probe, -d[:, 0] / n * probe])
        px.append(np.concatenate([mid[:, 0] + off[:, 0], mid[:, 0] - off[:, 0]]))
        py.append(np.concatenate([mid[:, 1] + off[:, 1], mid[:, 1] - off[:, 1]]))
        pw.append(np.concatenate([np.ones(len(mid)), -np.ones(len(mid))]))
    votes = np.zeros(len(faces))
    if px:
        pts = shapely.points(np.concatenate(px), np.concatenate(py))
        wts = np.concatenate(pw)
        ii, jj = tree.query(pts)
        done = np.zeros(len(pts), dtype=bool)
        for a, b in zip(ii, jj):
            if done[a]:
                continue
            if prepped[b].contains(pts[a]):
                votes[b] += wts[a]
                done[a] = True
    sea = [f for f, v in zip(faces, votes) if v > 0]
    out = unary_union(sea) if sea else frame.buffer(0).difference(frame)
    for isl in islands:
        out = out.difference(isl)
    return out, frame.bounds
