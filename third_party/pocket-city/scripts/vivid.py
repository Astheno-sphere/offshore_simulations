#!/usr/bin/env python3
"""Richer colour for a city.json, when the first render reads grey or washed out.

  python3 vivid.py work/city.json

Every plain hex colour gets more saturation: greens (trees, grass, shutters) by half, everything else a little.
Greys stay grey. The file is marked "vivid": true so it is never boosted twice. Compare the render with daylight
photos afterwards: the page should be as rich as the place on a clear day, never richer.
"""
import colorsys, json, re, sys
GREEN, REST = 1.5, 1.14
def boost(hx):
    r, g, b = (int(hx[i:i+2], 16) / 255 for i in (1, 3, 5)); h, l, s = colorsys.rgb_to_hls(r, g, b)
    if s < .06: return hx
    green = 65 <= h * 360 <= 165
    s2 = min(.82 if green else .9, s * (GREEN if green else REST)); l2 = l * (.985 if green else 1)
    return '#%02x%02x%02x' % tuple(round(v * 255) for v in colorsys.hls_to_rgb(h, l2, s2))
def walk(v):
    if isinstance(v, dict): return {k: walk(x) for k, x in v.items()}
    if isinstance(v, list): return [walk(x) for x in v]
    return boost(v) if isinstance(v, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', v) else v
if __name__ == '__main__':
    if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help'): sys.exit(__doc__)
    for p in sys.argv[1:]:
        c = json.load(open(p))
        if c.get('vivid'): print('already vivid', p); continue
        c = walk(c); c['vivid'] = True
        json.dump(c, open(p, 'w'), ensure_ascii=False, indent=1); print('vivid', p)
