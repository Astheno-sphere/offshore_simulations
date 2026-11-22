"""Walkers cross roads only on zebra crossings (used by prep.py; shapely only).

fix_walks(lines, road, zebras): wherever a walker's line crosses the carriageway away from a zebra, the crossing is
moved onto the nearest zebra that runs the same way (within 35 degrees) and lies within `reach` metres: the walker goes
along the pavement to the zebra's kerb end, crosses along the zebra line from kerb to kerb (a zebra mapped only to a
median is extended to the far kerb), and rejoins its line on the far pavement. Short wobbles onto the road are left.
"""
import math
from shapely.geometry import LineString, Point
from shapely.ops import unary_union


def fix_walks(lines, road, zebras, zone=2.2, reach=14, kerb=.9):
    if road is None or road.is_empty or not zebras: return lines
    zebras = [z for z in zebras if z.length > 1.5]
    near_zebra = unary_union([z.buffer(zone, cap_style=2) for z in zebras])
    bad = lambda p: road.contains(Point(p)) and not near_zebra.contains(Point(p))

    def crossing_line(z):
        """the zebra's line from kerb to kerb, a little beyond each kerb"""
        (x0, y0), (x1, y1) = z.coords[0], z.coords[-1]
        L = math.hypot(x1 - x0, y1 - y0); ux, uy = (x1 - x0) / L, (y1 - y0) / L
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        long = LineString([(mx - ux * 80, my - uy * 80), (mx + ux * 80, my + uy * 80)]).intersection(road)
        pieces = [g for g in getattr(long, 'geoms', [long]) if g.geom_type == 'LineString' and not g.is_empty and g.length > .5]
        if not pieces: return None
        g = min(pieces, key=lambda g: g.distance(Point(mx, my)))
        (a, b) = g.coords[0], g.coords[-1]
        return (a[0] - ux * kerb, a[1] - uy * kerb), (b[0] + ux * kerb, b[1] + uy * kerb), (ux, uy)

    lines_of = [c for c in (crossing_line(z) for z in zebras) if c]
    out = []
    for line in lines:
        L = LineString(line)
        if L.length < 1: out.append(line); continue
        step = .5
        pts = [L.interpolate(k * step).coords[0] for k in range(int(L.length / step) + 1)] + [tuple(line[-1])]
        res, i, n, moved = [], 0, len(pts), False
        while i < n:
            if not bad(pts[i]): res.append(pts[i]); i += 1; continue
            j = i
            while j < n and bad(pts[j]): j += 1
            E, X = (res[-1] if res else pts[i]), (pts[j] if j < n else pts[-1])
            dx, dy = X[0] - E[0], X[1] - E[1]; d = math.hypot(dx, dy)
            best = None
            if (j - i) * step > 3 and d > 2:
                mid = Point((E[0] + X[0]) / 2, (E[1] + X[1]) / 2)
                for a, b, (ux, uy) in lines_of:
                    if abs(ux * dx + uy * dy) / d < math.cos(math.radians(35)): continue   # runs another way
                    dist = LineString([a, b]).distance(mid)
                    if dist < reach and (best is None or dist < best[0]):
                        if ux * dx + uy * dy < 0: a, b = b, a
                        best = (dist, a, b)
            if best:
                _, a, b = best
                res += [a, b]; moved = True
                # rejoin the line on the far side at its point nearest the zebra's far end
                k = j
                while k + 1 < n and Point(pts[k + 1]).distance(Point(b)) < Point(pts[k]).distance(Point(b)): k += 1
                i = k
            else:
                res += pts[i:j]; i = j
        if not moved: out.append(line); continue
        clean = [res[0]]
        for q in res[1:]:
            if (q[0] - clean[-1][0]) ** 2 + (q[1] - clean[-1][1]) ** 2 > .04: clean.append(q)
        # the line was sampled every half metre to test it; hand back only its corners (within 12 cm), or a route that was
        # 15 points becomes 900: a heavier page and slower traffic for the same walk
        slim = LineString(clean).simplify(.12, preserve_topology=False)
        out.append([(round(x, 2), round(y, 2)) for x, y in slim.coords] if len(slim.coords) >= 2 else clean)
    return out
