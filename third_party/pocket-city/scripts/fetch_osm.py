#!/usr/bin/env python3
"""Fetch OpenStreetMap data around a place for a Pocket City.

  python3 fetch_osm.py --place "Gion, Kyoto" --size 200 --out work/osm.json
  python3 fetch_osm.py --lat 35.0037 --lon 135.7751 --size 200 --out work/osm.json

The download covers more than the plot (a margin on every side), so plot.py can still move and turn the square to
keep famous buildings whole. Only the Python standard library is used. Data: (c) OpenStreetMap contributors, ODbL.
"""
import argparse, json, math, sys, time, urllib.error, urllib.parse, urllib.request

UA = 'pocket-city-skill/1.0 (OpenStreetMap extract for an illustrated city diorama)'
OVERPASS = ['https://overpass-api.de/api/interpreter', 'https://overpass.kumi.systems/api/interpreter',
            'https://maps.mail.ru/osm/tools/overpass/api/interpreter']


def get(url, data=None, timeout=180):
    try:
        req = urllib.request.Request(url, data=data, headers={'User-Agent': UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.URLError as e:
        # some system Pythons ship an old SSL library that certain servers refuse; curl usually works there
        if 'SSL' not in str(e) and 'CERTIFICATE' not in str(e).upper(): raise
        import subprocess
        cmd = ['curl', '-sS', '-f', '-m', str(timeout), '-A', UA, url]
        if data is not None: cmd[1:1] = ['--data-binary', '@-']
        r = subprocess.run(cmd, input=data, capture_output=True)
        if r.returncode: raise RuntimeError(r.stderr.decode()[:200] or f'curl exit {r.returncode}')
        return r.stdout


def geocode(place):
    q = urllib.parse.urlencode({'q': place, 'format': 'json', 'limit': 1})
    res = json.loads(get('https://nominatim.openstreetmap.org/search?' + q, timeout=60))
    if not res:
        sys.exit(f'Could not find "{place}". Try a more specific name, or pass --lat and --lon.')
    r = res[0]
    return float(r['lat']), float(r['lon']), r.get('display_name', place)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--place', help='a place name to look up (Nominatim)')
    ap.add_argument('--lat', type=float); ap.add_argument('--lon', type=float)
    ap.add_argument('--size', type=float, default=200, help='plot side in metres (150-250 recommended)')
    ap.add_argument('--margin', type=float, default=0, help='extra metres around the search area (default: 60%% of the size)')
    ap.add_argument('--out', default='work/osm.json')
    a = ap.parse_args()

    name = a.place or ''
    if a.lat is None or a.lon is None:
        if not a.place:
            sys.exit('Give --place, or --lat and --lon.')
        a.lat, a.lon, name = geocode(a.place)
        print(f'Found: {name} ({a.lat:.5f}, {a.lon:.5f})')
    if not 80 <= a.size <= 600:
        sys.exit('Size must be between 80 and 600 m (150-250 m recommended).')

    # half the diagonal (the square may turn) plus room to slide it
    reach = a.size * .71 + (a.margin or a.size * .6)
    dlat = reach / 110574
    dlon = reach / (111320 * math.cos(math.radians(a.lat)))
    bb = f'{a.lat - dlat:.6f},{a.lon - dlon:.6f},{a.lat + dlat:.6f},{a.lon + dlon:.6f}'
    # one compact query (several small clauses time out on busy servers); out geom carries coordinates inline
    q = f"""[out:json][timeout:170];
(
  nwr["building"]({bb}); nwr["building:part"]({bb});
  way["highway"]({bb}); way["area:highway"]({bb}); way["railway"]({bb});
  nwr["landuse"]({bb}); nwr["leisure"]({bb}); nwr["natural"]({bb});
  nwr["waterway"]({bb}); way["water"]({bb}); way["place"="square"]({bb});
  nwr["historic"]({bb}); nwr["tourism"]({bb}); way["amenity"]({bb}); way["man_made"]({bb});
  node["highway"]({bb}); node["amenity"]({bb}); node["shop"]({bb}); node["craft"]({bb});
);
out geom;"""
    body = urllib.parse.urlencode({'data': q}).encode()
    raw, err = None, None
    for url in OVERPASS:
        for attempt in range(2):
            try:
                print('Overpass:', url)
                raw = get(url, body)
                break
            except Exception as e:  # busy servers answer 429/504; wait and try the next one
                err = e; print('  busy:', e); time.sleep(8)
        if raw:
            break
    if not raw:
        sys.exit(f'Overpass did not answer ({err}). Wait a minute and run again.')
    data = json.loads(raw)
    data['pocket_city'] = {'lat': a.lat, 'lon': a.lon, 'size': a.size, 'place': name, 'bbox': bb,
                           'fetched': time.strftime('%Y-%m-%d'), 'osm_base': data.get('osm3s', {}).get('timestamp_osm_base')}
    import os
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(data, open(a.out, 'w'))
    els = data['elements']
    count = lambda f: sum(1 for e in els if f(e.get('tags', {})))
    print(f"Saved {a.out}: {len(els)} elements; {count(lambda t: 'building' in t)} buildings, "
          f"{count(lambda t: 'highway' in t)} streets and nodes, {count(lambda t: t.get('natural') == 'tree')} trees.")


if __name__ == '__main__':
    main()
