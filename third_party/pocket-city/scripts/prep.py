#!/usr/bin/env python3
"""Turn the OpenStreetMap extract into the scene the Pocket City engine draws.

  python3 prep.py --osm work/osm.json --plot work/plot.json --drive right --out work/scene.json

Engine coordinates are metres from the plot centre, turned so the square's sides run along x and y (x to the right,
y up, z up: like east, north, up, only turned, never mirrored). Everything is clipped to the square; buildings the edge
cuts are kept and marked cut (they are drawn in section).

What comes out (all measured from the map, nothing invented):
  buildings  footprints with height, levels, min height, roof shape/colour, material, use, name, famous flag
  roads      carriageway polygons (centrelines widened by class, width or lanes)
  paths      pavements beside roads and footways;  walk: pedestrian streets and squares
  lawns      parks, gardens, grass, woods;  water: sea (from the coastline), rivers, canals, ponds;  sand: beaches
  rails      tram and train lines
  trees      mapped trees (natural=tree, tree rows) with species and height when mapped; woods and parks with no
             mapped trees get trees scattered over their mapped area (species 'Woodland' / 'Park tree': illustrative)
  boats      small boats moored along quays and a few at anchor (illustrative; only where the map has sea or harbour)
  routes     traffic lanes for cars, bikes and walkers, each running edge to edge
  markings   zebra crossings;  centerlines: lane lines;  pois: named shops and places (for shopfront signs)
  furniture  bus stops, street lamps, benches, signals
Needs shapely (pip install shapely).
"""
import argparse, json, math, os, re, sys
from shapely.geometry import Polygon, LineString, Point, MultiPolygon, MultiLineString, box, GeometryCollection
from shapely.ops import unary_union, linemerge, polygonize, nearest_points
from shapely import affinity

DRIVE = {'motorway': 14, 'trunk': 14, 'primary': 13, 'secondary': 11, 'tertiary': 9.5, 'unclassified': 7,
         'residential': 7, 'living_street': 5, 'service': 4.2, 'motorway_link': 7, 'trunk_link': 7, 'primary_link': 7,
         'secondary_link': 6.5, 'tertiary_link': 6, 'road': 7, 'busway': 7}
FOOT = {'pedestrian': 6, 'footway': 2.4, 'path': 2, 'cycleway': 2.4, 'steps': 2.4, 'bridleway': 2.5, 'track': 3,
        'corridor': 2}
SIDEWALK = {'motorway': 0, 'trunk': 3, 'primary': 3.2, 'secondary': 2.8, 'tertiary': 2.4, 'unclassified': 1.6,
            'residential': 1.8, 'living_street': 0, 'service': 0, 'road': 1.8}
RIVER = {'river': 22, 'canal': 12, 'stream': 3, 'ditch': 1.6, 'drain': 1.6}


def num(v):
    if v is None: return None
    m = re.match(r'\s*([\d.]+)', str(v).replace(',', '.'))
    if not m: return None
    x = float(m.group(1))
    if 'ft' in str(v) or "'" in str(v): x *= .3048
    return x


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--osm', default='work/osm.json'); ap.add_argument('--plot', default='work/plot.json')
    ap.add_argument('--drive', choices=['right', 'left'], default='right', help='which side traffic keeps to')
    ap.add_argument('--level', type=float, default=3.2, help='metres per storey when only levels are mapped')
    ap.add_argument('--green-open', type=float, default=0, metavar='SPACING',
                    help='draw unmapped open land as gardens with trees this many metres apart (e.g. 9); only where '
                         'photos show the open land is green (hillside gardens, villas); illustrative')
    ap.add_argument('--bank-trees', type=float, default=0, metavar='SPACING',
                    help='line canal and river banks with trees this many metres apart (e.g. 7), where photos show '
                         'trees along the water (willows, cherries, limes); species name "Bank tree"; illustrative')
    ap.add_argument('--out', default='work/scene.json')
    a = ap.parse_args()

    data = json.load(open(a.osm)); plot = json.load(open(a.plot))
    lat0, lon0, rot, size = plot['lat'], plot['lon'], plot['rotation'], plot['size']
    half = size / 2
    kx, ky = 111320 * math.cos(math.radians(lat0)), 110574
    cr, sr = math.cos(math.radians(-rot)), math.sin(math.radians(-rot))

    def P(lat, lon):
        x, y = (lon - lon0) * kx, (lat - lat0) * ky
        return (x * cr - y * sr, x * sr + y * cr)

    SQ = box(-half, -half, half, half)
    BIG = SQ.buffer(30, join_style=2)
    r2 = lambda v: round(v, 2)
    els = data['elements']
    nodes = [e for e in els if e['type'] == 'node']
    ways = [e for e in els if e['type'] == 'way' and e.get('geometry')]
    rels = [e for e in els if e['type'] == 'relation']

    def line_of(e):
        return LineString([P(p['lat'], p['lon']) for p in e['geometry']])

    def poly_of(e):
        try:
            if e['type'] == 'way':
                pts = [P(p['lat'], p['lon']) for p in e['geometry']]
                if len(pts) < 4 or pts[0] != pts[-1]: return None
                return Polygon(pts).buffer(0)
            outer = [Polygon([P(p['lat'], p['lon']) for p in m['geometry']]).buffer(0) for m in e.get('members', [])
                     if m.get('role') == 'outer' and m.get('geometry') and len(m['geometry']) >= 4]
            inner = [Polygon([P(p['lat'], p['lon']) for p in m['geometry']]).buffer(0) for m in e.get('members', [])
                     if m.get('role') == 'inner' and m.get('geometry') and len(m['geometry']) >= 4]
            if not outer: return None
            g = unary_union(outer)
            if inner: g = g.difference(unary_union(inner))
            return g
        except Exception:
            return None

    def polys(g):
        if g is None or g.is_empty: return []
        if g.geom_type == 'Polygon': return [g]
        return [p for p in getattr(g, 'geoms', []) if p.geom_type == 'Polygon']

    def rings(p, tol=.15):
        p = p.simplify(tol, preserve_topology=True)
        if p.is_empty or p.geom_type != 'Polygon': return None
        ext = [[r2(x), r2(y)] for x, y in list(p.exterior.coords)[:-1]]
        if len(ext) < 3: return None
        return [ext] + [[[r2(x), r2(y)] for x, y in list(i.coords)[:-1]] for i in p.interiors if Polygon(i).area > 4]

    def clip_polys(geoms, tol=.15, min_area=1.5):
        g = unary_union([x for x in geoms if x is not None and not x.is_empty])
        out = []
        for p in polys(g.intersection(SQ)):
            if p.area < min_area: continue
            r = rings(p, tol)
            if r: out.append(r)
        return out

    # ---------------- buildings ----------------
    blds = []
    for e in ways + rels:
        t = e.get('tags', {})
        isb, isp = 'building' in t and t.get('building') != 'no', 'building:part' in t and t.get('building:part') != 'no'
        if not (isb or isp): continue
        if t.get('building') in ('roof',) and not isp:
            kind = 'roof'
        else:
            kind = 'part' if isp and not isb else 'building'
        if t.get('location') == 'underground' or t.get('layer', '0').startswith('-'): continue
        g = poly_of(e)
        if g is None or g.is_empty or g.area < 3 or not g.intersects(BIG): continue
        blds.append({'e': e, 't': t, 'g': g, 'kind': kind})
    parts = [b for b in blds if b['kind'] == 'part']
    for b in blds:   # an outline whose parts cover most of it is drawn as its parts (OSM simple 3D buildings)
        if b['kind'] != 'building' or not parts: continue
        inside = [p['g'] for p in parts if b['g'].contains(p['g'].representative_point())]
        if inside and unary_union(inside).intersection(b['g']).area > .6 * b['g'].area:
            b['skip'] = True
            for p in parts:   # the parts carry the outline's name and fame, and point back to it (landmarks replace both)
                if b['g'].contains(p['g'].representative_point()):
                    p['of'] = f"{b['e']['type'][0]}{b['e']['id']}"
                    p['t'] = {**{k: v for k, v in b['t'].items() if k in ('name', 'wikidata', 'wikipedia', 'heritage', 'amenity', 'shop', 'tourism')}, **p['t']}
    famous_names = set(plot.get('famous_inside', []))
    out_b = []
    for b in blds:
        if b.get('skip'): continue
        t, g = b['t'], b['g']
        lv = num(t.get('building:levels')); h = num(t.get('height'))
        mn = num(t.get('min_height'))
        if mn is None and num(t.get('building:min_level')) is not None: mn = num(t.get('building:min_level')) * a.level
        rh = num(t.get('roof:height'))
        if rh is None and num(t.get('roof:levels')) is not None: rh = num(t.get('roof:levels')) * a.level * .8
        name = t.get('name', '')
        famous = name in famous_names or any(k in t for k in ('wikidata', 'wikipedia', 'heritage'))
        clipped = g.intersection(SQ)
        cut = clipped.area < g.area - .5
        pieces = polys(clipped)
        for k, p in enumerate(pieces):
            if p.area < 3: continue
            rr = rings(p)
            if not rr: continue
            obb = p.minimum_rotated_rectangle
            oc = list(obb.exterior.coords)[:4]
            e1 = (oc[1][0] - oc[0][0], oc[1][1] - oc[0][1]); e2 = (oc[2][0] - oc[1][0], oc[2][1] - oc[1][1])
            l1, l2 = math.hypot(*e1), math.hypot(*e2)
            ax = e1 if l1 >= l2 else e2; L, W = max(l1, l2), min(l1, l2)
            ax = (ax[0] / (L or 1), ax[1] / (L or 1))
            c = obb.centroid
            rec = {'id': f"{b['e']['type'][0]}{b['e']['id']}" + (f'.{k}' if len(pieces) > 1 else ''),
                   'ring': rr[0], 'holes': rr[1:], 'kind': b['kind'], 'type': t.get('building') or t.get('building:part'),
                   'h': h, 'lv': lv, 'min': mn or 0, 'roof': t.get('roof:shape'), 'rh': rh, 'rcol': t.get('roof:colour'),
                   'rdir': t.get('roof:orientation'), 'col': t.get('building:colour'), 'mat': t.get('building:material'),
                   'use': t.get('shop') or t.get('amenity') or t.get('tourism') or t.get('office') or t.get('craft'),
                   'n': name, 'famous': famous, 'cut': cut, **({'of': b['of']} if b.get('of') else {}),
                   'obb': {'c': [r2(c.x), r2(c.y)], 'ax': [round(ax[0], 4), round(ax[1], 4)], 'L': r2(L), 'W': r2(W),
                           'fill': round(p.area / (obb.area or 1), 3)}}
            out_b.append({k2: v for k2, v in rec.items() if v not in (None, '', [], False) or k2 in ('min',)})

    # ---------------- streets ----------------
    carriage, pave, foot, walk, centerlines, rails = [], [], [], [], [], []
    drive_lines = []
    for e in ways:
        t = e.get('tags', {}); hw = t.get('highway')
        if not hw: continue
        closed = e['geometry'][0] == e['geometry'][-1]
        if (t.get('area') == 'yes' or (hw == 'pedestrian' and closed)) and closed:
            g = poly_of(e)
            if g is not None: walk.append(g)
            continue
        if t.get('tunnel') in ('yes', 'building_passage') or t.get('layer', '0').startswith('-'): continue
        L = line_of(e)
        if not L.intersects(BIG): continue
        if hw in DRIVE:
            w = num(t.get('width')) or (num(t.get('lanes')) * 3.1 if num(t.get('lanes')) else DRIVE[hw])
            w = max(3.2, min(w, 30))
            carriage.append(L.buffer(w / 2, cap_style=2, join_style=1))
            sw = SIDEWALK.get(hw, 0)
            if t.get('sidewalk') in ('no', 'none', 'separate'): sw = 0
            elif t.get('sidewalk') in ('both', 'left', 'right', 'yes') and sw == 0: sw = 1.6
            if sw: pave.append(L.buffer(w / 2 + sw, cap_style=2, join_style=1))
            drive_lines.append({'L': L, 'w': w, 'sw': sw, 'hw': hw, 'name': t.get('name', ''), 'oneway': t.get('oneway') in ('yes', '1', 'true') or t.get('junction') == 'roundabout',
                                'lanes': num(t.get('lanes'))})
        elif hw in FOOT:
            w = num(t.get('width')) or FOOT[hw]
            if hw == 'pedestrian': walk.append(L.buffer(w / 2, cap_style=2, join_style=1))
            else: foot.append(L.buffer(w / 2, cap_style=1, join_style=1))
    for e in ways:   # area:highway and squares
        t = e.get('tags', {})
        if t.get('area:highway') or t.get('place') == 'square':
            g = poly_of(e)
            if g is not None: walk.append(g)
        if t.get('railway') in ('rail', 'tram', 'light_rail', 'subway', 'narrow_gauge') and t.get('tunnel') != 'yes':
            L = line_of(e).intersection(SQ)
            for seg in getattr(L, 'geoms', [L]):
                if seg.geom_type == 'LineString' and seg.length > 4:
                    rails.append({'kind': t['railway'], 'p': [[r2(x), r2(y)] for x, y in seg.coords]})
    car_u = unary_union(carriage) if carriage else Polygon()
    bld_u = unary_union([b['g'] for b in blds if b['kind'] != 'roof' and not b.get('skip')]) if blds else Polygon()
    pave_u = unary_union(pave + foot).difference(car_u).difference(bld_u) if (pave or foot) else Polygon()
    walk_u = unary_union(walk).difference(car_u) if walk else Polygon()

    # ---------------- green, water ----------------
    green, water = [], []
    for e in ways + rels:
        t = e.get('tags', {})
        kind = None
        if t.get('leisure') in ('park', 'garden', 'playground', 'pitch', 'common', 'dog_park'): kind = t['leisure']
        elif t.get('landuse') in ('grass', 'meadow', 'village_green', 'recreation_ground', 'cemetery', 'forest', 'orchard', 'allotments', 'flowerbed'): kind = t['landuse']
        elif t.get('natural') in ('grassland', 'scrub', 'wood', 'heath'): kind = t['natural']
        if kind:
            g = poly_of(e)
            if g is not None and g.intersects(SQ): green.append((kind, g))
        if t.get('natural') == 'water' or t.get('waterway') == 'riverbank' or t.get('landuse') in ('reservoir', 'basin') or t.get('water'):
            g = poly_of(e)
            if g is not None and g.intersects(SQ): water.append(g)
        if e['type'] == 'way' and t.get('waterway') in RIVER and t.get('tunnel') != 'culvert' and e['geometry'][0] != e['geometry'][-1]:
            w = num(t.get('width')) or RIVER[t['waterway']]
            water.append(line_of(e).buffer(w / 2, cap_style=2))
    # the sea: OpenStreetMap draws it as natural=coastline lines with the land on the left and the water on the right
    coast = [line_of(e) for e in ways if e.get('tags', {}).get('natural') == 'coastline']
    if coast:
        region = SQ.buffer(40, join_style=2)
        cl = unary_union([c.intersection(region) for c in coast])
        segs = [s for s in (getattr(cl, 'geoms', None) or [cl]) if s.geom_type == 'LineString' and s.length > 0]
        for face in polygonize(unary_union([region.exterior] + segs)):
            q = face.representative_point()
            best = None
            for s_ in segs:
                c = list(s_.coords)
                for a_, b_ in zip(c, c[1:]):
                    d = LineString([a_, b_]).distance(q)
                    if best is None or d < best[0]: best = (d, a_, b_)
            if best and (best[2][0] - best[1][0]) * (q.y - best[1][1]) - (best[2][1] - best[1][1]) * (q.x - best[1][0]) < 0:
                water.append(face)
    water_u = unary_union(water) if water else Polygon()
    # piers, jetties and breakwaters people walk on
    piers = []
    for e in ways:
        t = e.get('tags', {})
        if t.get('man_made') in ('pier', 'breakwater', 'groyne', 'quay'):
            g = poly_of(e) if e['geometry'][0] == e['geometry'][-1] else line_of(e).buffer((num(t.get('width')) or 3) / 2, cap_style=2)
            if g is not None and g.intersects(SQ): piers.append(g)
    if piers:
        pier_u = unary_union(piers)
        walk_u = unary_union([walk_u, pier_u]).difference(car_u); water_u = water_u.difference(pier_u)
    sand = []
    for e in ways + rels:
        t = e.get('tags', {})
        if t.get('natural') in ('beach', 'sand') or t.get('leisure') == 'beach_resort':
            g = poly_of(e)
            if g is not None and g.intersects(SQ): sand.append(g)
    sand_u = unary_union(sand).difference(water_u).difference(bld_u).difference(car_u) if sand else Polygon()
    lawns = []
    for kind, g in green:
        for p in polys(g.difference(car_u).difference(bld_u).difference(water_u).intersection(SQ)):
            if p.area > 4:
                r = rings(p, .25)
                if r: lawns.append({'kind': kind, 'r': r})

    # ---------------- trees ----------------
    species, trees = [], []
    def sp_index(t):
        s = t.get('species:en') or t.get('taxon:en') or t.get('species') or t.get('taxon') or t.get('genus:en') or t.get('genus') or ''
        if not s:
            lt = t.get('leaf_type'); s = {'broadleaved': 'Broadleaf tree', 'needleleaved': 'Conifer'}.get(lt, '')
        if not s: return -1
        if s not in species: species.append(s)
        return species.index(s)
    def add_tree(x, y, t):
        p = Point(x, y)
        if not SQ.buffer(-1).contains(p) or bld_u.contains(p) or car_u.buffer(-.8).contains(p): return
        h = num(t.get('height'))
        trees.append([r2(x), r2(y), sp_index(t), str(round(h, 1)) if h else ''])
    for n in nodes:
        t = n.get('tags', {})
        if t.get('natural') == 'tree':
            add_tree(*P(n['lat'], n['lon']), t)
    for e in ways:
        t = e.get('tags', {})
        if t.get('natural') == 'tree_row':
            L = line_of(e); k = 0
            while k <= L.length:
                q = L.interpolate(k); add_tree(q.x, q.y, t); k += 7
    mapped_trees = len(trees)
    if a.bank_trees and not water_u.is_empty:   # trees along the water's edge, on land that is free
        name = 'Bank tree'
        if name not in species: species.append(name)
        land_free = SQ.buffer(-1.5).difference(water_u.buffer(.9)).difference(bld_u.buffer(1.4)).difference(car_u.buffer(.6))
        shore = water_u.boundary.intersection(SQ.buffer(-2))
        have = [Point(t_[0], t_[1]) for t_ in trees]
        for l in (getattr(shore, 'geoms', None) or [shore]):
            if l.geom_type != 'LineString': continue
            d = a.bank_trees / 2
            while d < l.length:
                p0, p1 = l.interpolate(max(0, d - .5)), l.interpolate(min(l.length, d + .5))
                tx, ty = p1.x - p0.x, p1.y - p0.y; m_ = math.hypot(tx, ty) or 1
                for sgn in (1, -1):
                    q = Point(p0.x + tx / 2 + sgn * -ty / m_ * 1.7, p0.y + ty / 2 + sgn * tx / m_ * 1.7)
                    if land_free.contains(q) and all(q.distance(h) > 3 for h in have):
                        trees.append([r2(q.x), r2(q.y), species.index(name), '']); have.append(q); break
                d += a.bank_trees
    if a.green_open:   # land the map leaves blank: becomes garden (kind 'open') and gets park trees below
        taken = unary_union([water_u.buffer(12), bld_u.buffer(1.2), car_u.buffer(.5), pave_u.buffer(.3), walk_u.buffer(.3), sand_u]
                            + [g for _, g in green])
        for p_ in polys(SQ.difference(taken)):
            if p_.area > 60 and p_.area / max(1, p_.length) > 2.2:   # no thin slivers
                green.append(('open', p_))
                r = rings(p_, .25)
                if r: lawns.append({'kind': 'open', 'r': r})
    # woods and parks: OSM rarely maps each tree there, so fill the mapped area (illustrative, marked by species name)
    import random
    rng = random.Random(7)
    SPACING = {'open': a.green_open or 9, 'wood': 6.5, 'forest': 6.5, 'scrub': 7.5, 'park': 10, 'garden': 10, 'orchard': 7, 'cemetery': 12,
               'nature_reserve': 7, 'village_green': 14, 'recreation_ground': 15, 'common': 12}
    blocked = unary_union([bld_u.buffer(2.2), car_u.buffer(1), water_u.buffer(.6), pave_u, walk_u, sand_u])
    near = [Point(t_[0], t_[1]) for t_ in trees]
    for kind, g in green:
        sp = SPACING.get(kind)
        if not sp: continue
        area = g.intersection(SQ.buffer(-1.5)).difference(blocked)
        if area.is_empty: continue
        if any(area.contains(p_) for p_ in near): continue   # trees already mapped there: trust the map
        name = 'Woodland' if kind in ('wood', 'forest', 'scrub', 'nature_reserve') else 'Garden tree' if kind == 'open' else 'Park tree'
        if name not in species: species.append(name)
        x0, y0, x1, y1 = area.bounds; y = y0 + sp * .5; row = 0
        while y < y1:
            x = x0 + (sp * .5 if row % 2 else 0) + rng.uniform(0, sp * .3)
            while x < x1:
                px, py = x + rng.uniform(-.35, .35) * sp, y + rng.uniform(-.35, .35) * sp
                if area.contains(Point(px, py)) and len(trees) < 1100:
                    trees.append([r2(px), r2(py), species.index(name), ''])
                x += sp
            y += sp * .87; row += 1

    # ---------------- boats (illustrative) ----------------
    boats = []
    # boats only where the water is wide enough to moor them (a harbour, the sea, a river or canal over ~12 m): never on streams
    wide = water_u.buffer(-6).buffer(6.2).intersection(water_u) if not water_u.is_empty else Polygon()
    if not wide.is_empty and wide.area > 300:
        sea = wide.intersection(SQ.buffer(-2))
        land_edge = water_u.boundary.intersection(SQ.buffer(-3))
        quay = unary_union([car_u, walk_u, pave_u]).buffer(6)
        edges = [l for l in (getattr(land_edge, 'geoms', None) or [land_edge]) if l.geom_type == 'LineString']
        k, hulls = 0, []
        def boat_fp(cx, cy, ux, uy, L):   # the boat's plan, a little wider than its beam
            W = max(1.5, L * .31) / 2 + .2; h = L / 2 + .2
            return Polygon([(cx + ux * a - uy * b, cy + uy * a + ux * b) for a, b in ((-h, -W), (h, -W), (h, W), (-h, W))])
        for l in edges:
            d = 2.5
            while d < l.length - 2:
                a_, b_ = l.interpolate(d - .5), l.interpolate(d + .5)
                tx, ty = b_.x - a_.x, b_.y - a_.y; n_ = math.hypot(tx, ty) or 1
                nx, ny = -ty / n_, tx / n_
                q = Point(a_.x + nx * 4, a_.y + ny * 4)
                if not sea.contains(q): nx, ny = -nx, -ny; q = Point(a_.x + nx * 4, a_.y + ny * 4)
                L = rng.choice([5.2, 6, 7, 8.5])
                cx, cy = a_.x + nx * (L / 2 + 1.2), a_.y + ny * (L / 2 + 1.2)
                hull = boat_fp(cx, cy, nx, ny, L)
                straight = False
                if 3 < d < l.length - 3:   # keep off corners: the shore 3 m either side runs the same way
                    p0, p1 = l.interpolate(d - 3), l.interpolate(d + 3); ux_, uy_ = p1.x - p0.x, p1.y - p0.y; m_ = math.hypot(ux_, uy_) or 1
                    straight = abs((ux_ * ty - uy_ * tx) / (m_ * n_)) < .2 and m_ > 5.6
                if quay.contains(a_) and straight and sea.buffer(-.4).contains(hull) and not any(hull.intersects(h) for h in hulls) and rng.random() < .85:
                    hulls.append(hull.buffer(.25))
                    boats.append({'x': r2(cx), 'y': r2(cy), 'a': round(math.degrees(math.atan2(ny, nx)), 1), 'l': L, 'k': k}); k += 1
                d += rng.choice([3.2, 3.6, 4.2])
        # a few at anchor further out
        x0, y0, x1, y1 = sea.bounds
        for i in range(60):
            if len([b for b in boats if b.get('anchor')]) >= 9: break
            px, py = rng.uniform(x0, x1), rng.uniform(y0, y1); p_ = Point(px, py)
            L, ang = rng.choice([7, 9, 11]), rng.uniform(-math.pi, math.pi)
            hull = boat_fp(px, py, math.cos(ang), math.sin(ang), L)
            if sea.buffer(-3).contains(hull) and not any(hull.buffer(4).intersects(h) for h in hulls) and land_edge.distance(p_) > 18:
                hulls.append(hull.buffer(.25))
                boats.append({'x': r2(px), 'y': r2(py), 'a': round(math.degrees(ang), 1), 'l': L, 'k': k, 'anchor': 1}); k += 1

    quay_top, quay_shade, shore_lines = [], [], []
    if not water_u.is_empty:
        shore = water_u.boundary.intersection(SQ.buffer(-1.2))   # inside the plot, never along the plate's edge
        land = SQ.difference(water_u)
        quay_top = clip_polys([shore.buffer(.45, cap_style=2).intersection(land)], .1, .3)
        quay_shade = clip_polys([shore.buffer(.7, cap_style=2).intersection(water_u)], .1, .3)
        # the shoreline itself (not the plate edge, not round piers): decorations such as quay lights follow it
        sh = shore.difference(pier_u.buffer(1.5)) if piers else shore
        shore_lines = [[[r2(x), r2(y)] for x, y in g.simplify(.2).coords] for g in (getattr(sh, 'geoms', None) or [sh])
                       if g.geom_type == 'LineString' and g.length > 8]

    # ---------------- traffic routes ----------------
    edge = SQ.exterior
    def at_edge(pt): return edge.distance(Point(pt)) < 4
    def offset(line, d):
        if abs(d) < .01: return line
        try:
            o = line.offset_curve(d, join_style=2, mitre_limit=3)
        except AttributeError:   # shapely 1.8
            o = line.parallel_offset(abs(d), 'left' if d > 0 else 'right', join_style=2, mitre_limit=3)
            if d < 0 and o.geom_type == 'LineString': o = LineString(list(o.coords)[::-1])
        return o if o.geom_type == 'LineString' else None
    routes = []
    bydir = {}
    for d in drive_lines:
        key = d['name'] or id(d)
        bydir.setdefault((key, d['oneway']), []).append(d)
    keep_side = 1 if a.drive == 'right' else -1
    for (key, oneway), group in bydir.items():
        merged = linemerge(MultiLineString([g['L'] for g in group])) if len(group) > 1 else group[0]['L']
        w = max(g['w'] for g in group); sw = max(g['sw'] for g in group); hw = group[0]['hw']; name = group[0]['name']
        for seg in getattr(merged, 'geoms', [merged]):
            seg = seg.intersection(SQ)
            for s in getattr(seg, 'geoms', [seg]):
                if s.geom_type != 'LineString' or s.length < 30: continue
                a0, a1 = s.coords[0], s.coords[-1]
                through = at_edge(a0) and at_edge(a1)
                dirs = [s] if oneway else [s, LineString(list(s.coords)[::-1])]
                lane = 0 if oneway else w / 4
                if sw:   # walkers on both pavements, both ways
                    for side in (-1, 1):
                        o = offset(s, side * (w / 2 + sw / 2))
                        if o is None: continue
                        free = o.difference(bld_u.buffer(.4))
                        for f in getattr(free, 'geoms', [free]):
                            if f.geom_type == 'LineString' and f.length > 20:
                                pts = [[r2(x), r2(y)] for x, y in f.coords]
                                routes.append({'kind': 'ped', 'name': name, 'p': pts})
                                routes.append({'kind': 'ped', 'name': name, 'p': pts[::-1]})
                elif hw in ('living_street', 'service', 'residential', 'unclassified') and w <= 7.5:
                    # narrow lanes without pavements: walkers keep to the edges
                    for side in (-1, 1):
                        o = offset(s, side * (w / 2 - .6))
                        if o is not None and o.length > 20:
                            free = o.difference(bld_u.buffer(.3))
                            for f in getattr(free, 'geoms', [free]):
                                if f.geom_type == 'LineString' and f.length > 20:
                                    pts = [[r2(x), r2(y)] for x, y in f.coords]
                                    routes.append({'kind': 'ped', 'name': name, 'p': pts if side < 0 else pts[::-1]})
    # cars and bikes: shortest paths through the street network, edge to edge, obeying one-way streets
    import heapq
    graph, wid = {}, {}
    key = lambda q: (round(q[0] * 2) / 2, round(q[1] * 2) / 2)
    for d in drive_lines:
        if d['hw'] == 'service': continue
        clipped = d['L'].intersection(SQ.buffer(.5))
        for seg in getattr(clipped, 'geoms', [clipped]):
            if seg.geom_type != 'LineString': continue
            pts = [key(q) for q in seg.coords]
            for u, v in zip(pts, pts[1:]):
                if u == v: continue
                L = math.hypot(v[0] - u[0], v[1] - u[1])
                graph.setdefault(u, []).append((v, L)); graph.setdefault(v, [])
                if not d['oneway']: graph[v].append((u, L))
                wid[(u, v)] = wid[(v, u)] = (d['w'], d['oneway'], d['hw'])
    near_edge = [n for n in graph if edge.distance(Point(n)) < 2.5]
    entries = [n for n in near_edge if graph[n]]
    exits = set(n for n in near_edge)
    def paths_from(src):
        dist, prev, pq = {src: 0}, {}, [(0, src)]
        while pq:
            dd, u = heapq.heappop(pq)
            if dd > dist.get(u, 1e18): continue
            for v, L in graph[u]:
                nd = dd + L
                if nd < dist.get(v, 1e18): dist[v] = nd; prev[v] = u; heapq.heappush(pq, (nd, v))
        return dist, prev
    cand = []
    for src in entries:
        dist, prev = paths_from(src)
        for dst in exits:
            if dst == src or dst not in dist or dist[dst] < 45: continue
            if math.hypot(dst[0] - src[0], dst[1] - src[1]) < 30: continue
            chain = [dst]
            while chain[-1] != src: chain.append(prev[chain[-1]])
            chain.reverse()
            cand.append((dist[dst], chain))
    cand.sort(key=lambda c: -c[0])
    used_pairs, chosen = set(), []
    for L, chain in cand:   # long, distinct trips first; at most 14 car routes
        pair = (chain[0], chain[-1])
        if pair in used_pairs or any(abs(chain[0][0] - c[0][0]) + abs(chain[0][1] - c[0][1]) < 3 and abs(chain[-1][0] - c[-1][0]) + abs(chain[-1][1] - c[-1][1]) < 3 for c in chosen): continue
        used_pairs.add(pair); chosen.append(chain)
        if len(chosen) >= 14: break
    for chain in chosen:
        line = LineString(chain).simplify(.3)
        two_way = any(not wid.get((u, v), (0, True, ''))[1] for u, v in zip(chain, chain[1:]))
        w = min(wid.get((u, v), (7, False, ''))[0] for u, v in zip(chain, chain[1:]))
        o = offset(line, -keep_side * (min(w / 4, 1.8) if two_way else 0))
        if o is not None and o.length > 40:
            routes.append({'kind': 'car', 'name': '', 'p': [[r2(x), r2(y)] for x, y in o.coords]})
        if len([r for r in routes if r['kind'] == 'bike']) < 8 and w >= 6:
            o = offset(line, -keep_side * (w / 2 - .9 if two_way else w / 2 - .9))
            if o is not None and o.length > 40:
                routes.append({'kind': 'bike', 'name': '', 'p': [[r2(x), r2(y)] for x, y in o.coords]})

    for e in ways:   # footways and pedestrian streets
        t = e.get('tags', {})
        if t.get('highway') in ('footway', 'pedestrian', 'path', 'steps') and not (t.get('area') == 'yes'):
            if t.get('footway') == 'crossing': continue
            s = line_of(e).intersection(SQ).difference(bld_u.buffer(.3))
            for f in getattr(s, 'geoms', [s]):
                if f.geom_type == 'LineString' and f.length > 20:
                    pts = [[r2(x), r2(y)] for x, y in f.coords]
                    routes.append({'kind': 'ped', 'name': t.get('name', ''), 'p': pts}); routes.append({'kind': 'ped', 'name': t.get('name', ''), 'p': pts[::-1]})
        if t.get('highway') == 'cycleway':
            s = line_of(e).intersection(SQ)
            for f in getattr(s, 'geoms', [s]):
                if f.geom_type == 'LineString' and f.length > 25:
                    pts = [[r2(x), r2(y)] for x, y in f.coords]
                    routes.append({'kind': 'bike', 'name': t.get('name', ''), 'p': pts})
                    if t.get('oneway') != 'yes': routes.append({'kind': 'bike', 'name': t.get('name', ''), 'p': pts[::-1]})

    # ---------------- lane lines, crossings ----------------
    for d in drive_lines:
        if d['hw'] in ('primary', 'secondary', 'tertiary', 'trunk') or (d['lanes'] or 0) >= 2:
            s = d['L'].intersection(SQ)
            for f in getattr(s, 'geoms', [s]):
                if f.geom_type == 'LineString' and f.length > 10:
                    centerlines.append({'name': d['name'], 'p': [[r2(x), r2(y)] for x, y in f.coords]})
    markings = []
    for n in nodes:
        t = n.get('tags', {})
        if t.get('highway') == 'crossing' or t.get('crossing') in ('zebra', 'marked', 'traffic_signals', 'uncontrolled'):
            if t.get('crossing') in ('unmarked', 'no'): continue
            p = Point(P(n['lat'], n['lon']))
            if not SQ.buffer(-3).contains(p): continue
            best = min(drive_lines, key=lambda d: d['L'].distance(p), default=None)
            if not best or best['L'].distance(p) > 2: continue
            s = best['L'].project(p); a1 = best['L'].interpolate(max(0, s - .5)); b1 = best['L'].interpolate(min(best['L'].length, s + .5))
            dx, dy = b1.x - a1.x, b1.y - a1.y; l = math.hypot(dx, dy) or 1
            nx, ny = -dy / l, dx / l; hw2 = best['w'] / 2
            markings.append([[r2(p.x - nx * hw2), r2(p.y - ny * hw2)], [r2(p.x + nx * hw2), r2(p.y + ny * hw2)]])

    # ---------------- shops, places, street furniture ----------------
    pois, furniture = [], []
    for n in nodes:
        t = n.get('tags', {})
        x, y = P(n['lat'], n['lon'])
        if not SQ.contains(Point(x, y)): continue
        kind = t.get('shop') or t.get('amenity') or t.get('craft') or t.get('tourism')
        if t.get('name') and kind and kind not in ('bench', 'waste_basket', 'bicycle_parking', 'parking', 'vending_machine', 'telephone', 'post_box'):
            pois.append({'x': r2(x), 'y': r2(y), 'name': t['name'], 'en': t.get('name:en', ''), 'kind': kind})
        hw = t.get('highway')
        if hw == 'bus_stop': furniture.append({'k': 'bus_stop', 'x': r2(x), 'y': r2(y), 'name': t.get('name', ''), 'ref': t.get('ref', ''), 'shelter': t.get('shelter') == 'yes'})
        elif hw == 'street_lamp': furniture.append({'k': 'lamp', 'x': r2(x), 'y': r2(y)})
        elif hw == 'traffic_signals': furniture.append({'k': 'signal', 'x': r2(x), 'y': r2(y)})
        elif t.get('amenity') == 'bench': furniture.append({'k': 'bench', 'x': r2(x), 'y': r2(y)})
        elif t.get('amenity') == 'vending_machine': furniture.append({'k': 'vending', 'x': r2(x), 'y': r2(y)})
        elif t.get('amenity') == 'fountain': furniture.append({'k': 'fountain', 'x': r2(x), 'y': r2(y)})
        elif t.get('man_made') == 'torii' or t.get('historic') in ('wayside_shrine', 'memorial', 'monument'): furniture.append({'k': t.get('man_made') or t.get('historic'), 'x': r2(x), 'y': r2(y), 'name': t.get('name', '')})

    # outdoor café tables in front of bars, cafés, restaurants and ice-cream shops, on the nearest open paving
    # (illustrative: OSM rarely maps outdoor seating; outdoor_seating=no is respected)
    open_floor = unary_union([walk_u, pave_u]).difference(bld_u.buffer(.6)).difference(car_u.buffer(.4)).intersection(SQ.buffer(-1))
    tables = []
    for n in nodes:
        t = n.get('tags', {})
        if t.get('amenity') not in ('cafe', 'bar', 'restaurant', 'pub', 'ice_cream', 'fast_food') or t.get('outdoor_seating') == 'no': continue
        x, y = P(n['lat'], n['lon']); p_ = Point(x, y)
        if not SQ.contains(p_) or open_floor.is_empty: continue
        q = nearest_points(p_, open_floor)[1]
        if q.distance(p_) > 12: continue
        dx, dy = q.x - x, q.y - y; d = math.hypot(dx, dy) or 1; ux, uy = dx / d, dy / d
        for i in range(6):
            cx = q.x + ux * (1.4 + 2.3 * (i // 3)) + (-uy) * 2.3 * (i % 3 - 1)
            cy = q.y + uy * (1.4 + 2.3 * (i // 3)) + ux * 2.3 * (i % 3 - 1)
            c = Point(cx, cy)
            if open_floor.buffer(-.9).contains(c) and all(math.hypot(cx - a_[0], cy - a_[1]) > 2 for a_ in tables):
                tables.append((cx, cy)); furniture.append({'k': 'cafe', 'x': r2(cx), 'y': r2(cy), 'i': len(tables)})
    # walkers cross the carriageway only on zebra crossings (walks.py)
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from walks import fix_walks
        peds = [r for r in routes if r['kind'] == 'ped']
        fixed = fix_walks([r['p'] for r in peds], car_u, [LineString(m) for m in markings if len(m) > 1])
        for r, f in zip(peds, fixed): r['p'] = [[r2(x), r2(y)] for x, y in f]
    except Exception as e:
        print('  (walk fix skipped:', e, ')')
    north = (round(-math.sin(math.radians(-rot)) * 1, 5), round(math.cos(math.radians(-rot)), 5))
    scene = {
        'meta': {'lat': lat0, 'lon': lon0, 'rotation': rot, 'size': size, 'half': half, 'north': [north[0], north[1], 0],
                 'drive': a.drive, 'place': plot.get('place', ''), 'osm_base': plot.get('osm_base'), 'level': a.level},
        'corners': [[half, -half], [half, half], [-half, half], [-half, -half]],
        'buildings': out_b,
        'roads': clip_polys([car_u]), 'paths': clip_polys([pave_u], .2, 2), 'walk': clip_polys([walk_u], .2, 4),
        'lawns': lawns, 'water': clip_polys([water_u], .3, 4), 'sand': clip_polys([sand_u], .3, 4), 'boats': boats,
        'quay': quay_top, 'quayShade': quay_shade, 'shore': shore_lines, 'rails': rails,
        'trees': trees, 'species': species, 'routes': routes, 'markings': markings, 'centerlines': centerlines,
        'pois': pois, 'furniture': furniture,
    }
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(scene, open(a.out, 'w'), ensure_ascii=False, separators=(',', ':'))
    kinds = {}
    for r in routes: kinds[r['kind']] = kinds.get(r['kind'], 0) + 1
    unknown_h = sum(1 for b in out_b if b.get('h') is None and b.get('lv') is None)
    print(f"Scene: {len(out_b)} buildings ({sum(1 for b in out_b if b.get('cut'))} cut by the edge, {unknown_h} without mapped height), "
          f"{mapped_trees} mapped trees + {len(trees) - mapped_trees} in woods/parks (illustrative), {len(lawns)} green areas, {len(boats)} boats (illustrative), {len(scene['water'])} water areas, {len(pois)} named shops/places, "
          f"routes {kinds}, {len(markings)} crossings.")
    print('Saved', a.out, f'({os.path.getsize(a.out) // 1024} KB)')


if __name__ == '__main__':
    main()
