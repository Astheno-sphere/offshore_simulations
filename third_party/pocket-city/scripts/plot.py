#!/usr/bin/env python3
"""Choose the square plot: its centre, its turn, and no famous building cut by its edge.

  python3 plot.py --osm work/osm.json --out work/plot.json
  python3 plot.py --osm work/osm.json --size 220 --keep "Minamiza;Ichiriki" --out work/plot.json

The square starts on the place you asked for, turned so the main streets run along its sides (or north-up with
--rotate north, or any angle with --rotate 30). It then slides up to 40% of its size to find the position where no
famous building is cut. Famous means: a wikidata or wikipedia tag, a heritage or historic tag, a place of worship, a
museum or attraction, or a listed name you pass with --keep (those must end up wholly inside).
Writes plot.json and plot-preview.svg (open it to check). Needs shapely (pip install shapely).
"""
import argparse, json, math, os, sys
from shapely.geometry import Polygon, LineString, Point, box, MultiPolygon
from shapely.ops import unary_union
from shapely import affinity

FAMOUS_BUILDINGS = {'cathedral', 'church', 'chapel', 'temple', 'shrine', 'mosque', 'synagogue', 'castle', 'palace',
                    'government', 'train_station', 'museum', 'tower', 'monastery', 'basilica', 'pagoda'}


def local(lat0, lon0):
    kx, ky = 111320 * math.cos(math.radians(lat0)), 110574
    return lambda lat, lon: ((lon - lon0) * kx, (lat - lat0) * ky)


def outlines(els, en):
    """Every building outline as (element, shapely polygon)."""
    out = []
    for e in els:
        t = e.get('tags', {})
        if 'building' not in t and 'building:part' not in t:
            continue
        try:
            if e['type'] == 'way' and e.get('geometry') and len(e['geometry']) >= 4:
                g = Polygon([en(p['lat'], p['lon']) for p in e['geometry']])
            elif e['type'] == 'relation':
                outer = [m for m in e.get('members', []) if m.get('role') == 'outer' and m.get('geometry')]
                rings = [Polygon([en(p['lat'], p['lon']) for p in m['geometry']]) for m in outer if len(m['geometry']) >= 4]
                g = unary_union([r.buffer(0) for r in rings]) if rings else None
            else:
                continue
            if g is None or g.is_empty:
                continue
            g = g.buffer(0)
            if g.area > 2:
                out.append((e, g))
        except Exception:
            continue
    return out


def fame(t, keep):
    name = t.get('name', '') + '|' + t.get('name:en', '')
    if keep and any(k.strip() and k.strip().lower() in name.lower() for k in keep):
        return 10
    s = 0
    lodging = t.get('tourism') in ('hotel', 'apartment', 'guest_house', 'hostel', 'motel') or t.get('building') in ('hotel', 'apartments')
    if lodging and not ('heritage' in t or 'historic' in t):
        return 0   # a hotel or flats with a wikidata tag is not a landmark
    if 'wikidata' in t or 'wikipedia' in t: s += 3
    if 'heritage' in t or 'historic' in t or 'heritage:operator' in t: s += 2
    if t.get('amenity') == 'place_of_worship' or t.get('building') in FAMOUS_BUILDINGS: s += 1.5
    if t.get('tourism') in ('attraction', 'museum', 'gallery') : s += 1.5
    return s


def street_bearing(els, en, centre, reach):
    """Length-weighted mode of street directions (mod 90) near the centre, in degrees."""
    bins = [0.0] * 90
    c = Point(centre)
    weight = {'primary': 3, 'secondary': 3, 'tertiary': 2.5, 'residential': 1.5, 'unclassified': 1.5, 'pedestrian': 1.5,
              'living_street': 1.5, 'service': .6, 'footway': .4, 'trunk': 3}
    for e in els:
        hw = e.get('tags', {}).get('highway')
        if e['type'] != 'way' or hw not in weight or not e.get('geometry'):
            continue
        pts = [en(p['lat'], p['lon']) for p in e['geometry']]
        for a, b in zip(pts, pts[1:]):
            m = Point((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            if m.distance(c) > reach:
                continue
            L = math.hypot(b[0] - a[0], b[1] - a[1])
            ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 90
            for k in range(-3, 4):   # a little smoothing
                bins[int(round(ang + k)) % 90] += L * weight[hw] * (1 - abs(k) / 4)
    best = max(range(90), key=lambda i: bins[i])
    return best if best <= 45 else best - 90


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--osm', default='work/osm.json')
    ap.add_argument('--size', type=float, help='plot side in metres (default: the size given to fetch_osm.py)')
    ap.add_argument('--lat', type=float); ap.add_argument('--lon', type=float)
    ap.add_argument('--rotate', default='auto', help='auto (follow the streets), north, or degrees')
    ap.add_argument('--keep', default='', help='names that must be wholly inside, separated by ;')
    ap.add_argument('--slide', type=float, default=.4, help='how far the square may move, as a share of its size')
    ap.add_argument('--out', default='work/plot.json')
    a = ap.parse_args()

    data = json.load(open(a.osm)); meta = data.get('pocket_city', {})
    lat0, lon0 = a.lat or meta['lat'], a.lon or meta['lon']
    size = a.size or meta.get('size', 200)
    if not 80 <= size <= 600:
        sys.exit('Size must be between 80 and 600 m.')
    en = local(lat0, lon0)
    els = data['elements']
    keep = [k for k in a.keep.split(';') if k.strip()]

    if a.rotate == 'auto':
        rot = street_bearing(els, en, (0, 0), size * .75)
    elif a.rotate == 'north':
        rot = 0.0
    else:
        rot = float(a.rotate)

    blds = outlines(els, en)
    # famous buildings: merge the outline and parts that share a name, so a temple and its halls count as one
    famous = {}
    for e, g in blds:
        t = e.get('tags', {})
        s = fame(t, keep)
        if s <= 0:
            continue
        key = t.get('name') or f"{e['type']}/{e['id']}"
        f = famous.setdefault(key, {'name': key, 'en': t.get('name:en', ''), 'fame': 0, 'geoms': [], 'ids': []})
        f['fame'] = max(f['fame'], s); f['geoms'].append(g); f['ids'].append(f"{e['type']}/{e['id']}")
    for f in famous.values():
        f['g'] = unary_union(f['geoms']).buffer(.3).buffer(-.3)
    famous = [f for f in famous.values() if f['g'].distance(Point(0, 0)) < size * 1.2]
    ordinary = [g for e, g in blds if fame(e.get('tags', {}), keep) <= 0 and g.distance(Point(0, 0)) < size * 1.2]

    half = size / 2
    def square(cx, cy, rot):
        return affinity.rotate(box(cx - half, cy - half, cx + half, cy + half), rot, origin=(cx, cy))

    def score(cx, cy, rot):
        sq = square(cx, cy, rot); edge = sq.exterior
        cost, cut, inside = 0, [], []
        for f in famous:
            g = f['g']
            if g.within(sq):
                inside.append(f['name']); continue
            if f['fame'] >= 10:   # asked for by name: anything but wholly inside fails, more so the further out it is
                cost += 2000 + g.difference(sq).area * 2
                if g.intersects(sq) and g.intersection(sq).area >= 1: cut.append(f['name'])
                continue
            if not g.intersects(sq) or g.intersection(sq).area < 1:
                continue
            cut.append(f['name']); cost += 120 * f['fame']
        cost += sum(1 for g in ordinary if g.intersects(edge)) * .04   # a cleaner edge, only a little
        cost += math.hypot(cx, cy) / size * 12                           # stay near the place asked for
        return cost, cut, inside

    # the street-following turn first; if that still cuts a famous building, also try north-up and small turns either way
    turns = [rot] + ([0.0, rot - 8, rot + 8] if a.rotate == 'auto' else [])
    best = None
    step = max(4, size / 40)
    r = int(size * a.slide / step)
    for k, tr in enumerate(turns):
        cr, sr = math.cos(math.radians(tr)), math.sin(math.radians(tr))
        for i in range(-r, r + 1):
            for j in range(-r, r + 1):
                dx, dy = i * step, j * step   # slide along the turned axes
                cx, cy = dx * cr - dy * sr, dx * sr + dy * cr
                c, cut, inside = score(cx, cy, tr)
                c += k and 3   # prefer following the streets when it costs nothing
                if best is None or c < best[0]:
                    best = (c, cx, cy, cut, inside, tr)
        if best[3] == [] and not [f for f in famous if f['fame'] >= 10 and f['name'] not in best[4]]:
            break
    c, cx, cy, cut, inside, rot = best
    k = 1 / (111320 * math.cos(math.radians(lat0)))
    clat, clon = lat0 + cy / 110574, lon0 + cx * k
    too_big = [f['name'] for f in famous if f['fame'] >= 10 and f['name'] not in inside]
    plot = {'lat': round(clat, 7), 'lon': round(clon, 7), 'rotation': rot, 'size': size,
            'asked': {'lat': lat0, 'lon': lon0}, 'moved_m': round(math.hypot(cx, cy), 1),
            'famous_inside': sorted(inside), 'famous_cut': sorted(cut), 'keep_missing': too_big,
            'place': meta.get('place', ''), 'osm_base': meta.get('osm_base')}
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(plot, open(a.out, 'w'), ensure_ascii=False, indent=1)

    # preview: buildings grey, famous ones gold (red if cut), the square, the asked-for point
    sq = square(cx, cy, rot)
    view = size * .9
    S = 900 / (2 * view)
    X = lambda x: (x + view) * S; Y = lambda y: (view - y) * S
    def path(g):
        polys = getattr(g, 'geoms', [g])
        return ''.join('M' + 'L'.join(f'{X(x):.1f} {Y(y):.1f}' for x, y in p.exterior.coords) + 'Z' for p in polys if p.geom_type == 'Polygon')
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 900" font-family="sans-serif"><rect width="900" height="900" fill="#f6f2e8"/>']
    line = lambda e: 'M' + 'L'.join(f'{X(x):.1f} {Y(y):.1f}' for x, y in (en(p["lat"], p["lon"]) for p in e['geometry']))
    for e in els:   # woods and parks green, water and the coastline blue, so the square can be judged against them
        t = e.get('tags', {})
        if e['type'] != 'way' or not e.get('geometry'): continue
        closed = e['geometry'][0] == e['geometry'][-1]
        if closed and (t.get('natural') in ('wood', 'scrub') or t.get('landuse') in ('forest', 'grass', 'meadow') or t.get('leisure') in ('park', 'garden')):
            svg.append(f'<path d="{line(e)}Z" fill="#d6e3c3"/>')
        elif closed and (t.get('natural') == 'water' or t.get('waterway') == 'riverbank'):
            svg.append(f'<path d="{line(e)}Z" fill="#bcd8dc"/>')
        elif t.get('natural') == 'coastline' or t.get('waterway') in ('river', 'canal'):
            svg.append(f'<path d="{line(e)}" fill="none" stroke="#7fb2bb" stroke-width="5"/>')
    for e in els:
        if e['type'] == 'way' and e.get('tags', {}).get('highway') and e.get('geometry'):
            svg.append(f'<path d="M' + 'L'.join(f'{X(x):.1f} {Y(y):.1f}' for x, y in (en(p["lat"], p["lon"]) for p in e['geometry'])) + '" fill="none" stroke="#d8cfc0" stroke-width="3"/>')
    for g in ordinary:
        svg.append(f'<path d="{path(g)}" fill="#cfc8bc" stroke="#9c9486" stroke-width=".6"/>')
    for f in famous:
        col = '#d9534f' if f['name'] in cut else '#e0b23c'
        svg.append(f'<path d="{path(f["g"])}" fill="{col}" stroke="#6b5420" stroke-width="1"/>')
        p = f['g'].representative_point()
        svg.append(f'<text x="{X(p.x):.0f}" y="{Y(p.y):.0f}" font-size="11" fill="#3b2f12">{f["name"][:28]}</text>')
    svg.append(f'<path d="{path(sq)}" fill="none" stroke="#2f5a4a" stroke-width="3"/>')
    svg.append(f'<circle cx="{X(0):.1f}" cy="{Y(0):.1f}" r="5" fill="#2f5a4a"/>')
    svg.append(f'<text x="12" y="24" font-size="15" fill="#2f5a4a">{size:.0f} m square, turned {rot:.0f}°, moved {plot["moved_m"]} m · gold = famous, red = cut, blue = water/coast, green = woods</text></svg>')
    prev = os.path.join(os.path.dirname(os.path.abspath(a.out)), 'plot-preview.svg')
    open(prev, 'w').write(''.join(svg))

    print(f'Plot: {size:.0f} m, centre {clat:.6f}, {clon:.6f}, turned {rot:.0f}°, moved {plot["moved_m"]} m from the asked point.')
    print('Famous and whole inside:', ', '.join(inside) or 'none')
    if cut: print('STILL CUT (try --size larger, --rotate north, or a different centre):', ', '.join(cut))
    if too_big: print('NOT INSIDE (bigger than the plot or too far):', ', '.join(too_big))
    print('Saved', a.out, 'and', prev)


if __name__ == '__main__':
    main()
