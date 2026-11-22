#!/usr/bin/env python3
"""Assemble a Pocket City page: one self-contained HTML file that works offline and from disk.

  python3 build.py --scene work/scene.json --city work/city.json [--landmarks work/landmarks.js] --out pocket-city.html

city.json is checked first (required fields, every season and occasion has a sourced note). The page carries the
shared drawing kit, the scene, city.json and landmarks.js as text blocks; page.js starts the render workers.
"""
import argparse, json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, '..', 'assets')

REQUIRED = ['name', 'seasons', 'styles']


def check_city(city, scene):
    problems, warnings = [], []
    for k in REQUIRED:
        if k not in city: problems.append(f'city.json needs "{k}"')
    ids = set()
    for s in city.get('seasons', []) + city.get('occasions', []):
        if 'id' not in s or 'label' not in s: problems.append(f'every season/occasion needs id and label: {s}'); continue
        if s['id'] in ids: problems.append(f'duplicate season id {s["id"]}')
        ids.add(s['id'])
        n = s.get('note') or {}
        if not (n.get('text') and n.get('source') and n.get('url')):
            problems.append(f'season "{s["id"]}" needs a note with text, source and url (only sourced facts go on the card)')
    months = city.get('months')
    if months and (len(months) != 12 or any(m not in ids for m in months)):
        problems.append('months must list 12 season ids, January first')
    # seasons must look different. A season shows through what it changes on screen; leaves only count where some trees shed them
    # the share of the scene's trees that shed their leaves, from each tree's species and its rule (a mix counts by its shares)
    tr = city.get('trees') or {}; default = tr.get('default') or {}; rules = tr.get('rules') or []
    def shed_share(species):
        r = next((r for r in rules if re.search(r.get('match', '^$'), species or '', re.I)), None)
        base = {**default, **(r or {})}; mix = base.get('mix') or [{}]; tot = sum(m.get('share', 1) for m in mix)
        return sum(m.get('share', 1) for m in mix if not {**base, **m}.get('evergreen')) / tot
    sp = scene.get('species') or []; trees = scene.get('trees') or []
    shed = sum(shed_share(sp[t[2]] if 0 <= t[2] < len(sp) else '') for t in trees) / len(trees) if trees else 0
    sheds = shed >= .25
    def look(x):
        keys = ('wet', 'snow', 'ice', 'haze', 'wx', 'umbrellas', 'coats', 'cafes', 'boats', 'night', 'petals', 'decor', 'dress', 'grass')
        return json.dumps([x.get(k) for k in keys] + ([x.get('leaves')] if sheds else []), sort_keys=True)
    chips = [x for x in city.get('seasons', []) if 'id' in x]
    for i, x in enumerate(chips):
        for y in chips[i + 1:]:
            if look(x) == look(y):
                warnings.append(f'seasons "{x["id"]}" and "{y["id"]}" will look the same on screen (only the crowd differs'
                                + ('' if sheds else f'; only {round(shed * 100)}% of the trees here shed their leaves, so the leaf season barely shows')
                                + '). Merge them, or give each something real that differs: see references/seasons-occasions.md')
    bids = {b['id'] for b in scene['buildings']}
    for bid in (city.get('buildings') or {}):
        if bid not in bids: warnings.append(f'buildings: id {bid} is not in the scene (cut away or a typo)')
    for v in city.get('views', []) + city.get('legend', []):
        if 'camera' not in v: problems.append(f'view/legend "{v.get("label") or v.get("name")}" needs a camera')
    for n in city.get('notes', []):
        if not n.get('links'): warnings.append(f'field note "{n.get("title")}" has no source link')
    return problems, warnings


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--scene', default='work/scene.json'); ap.add_argument('--city', default='work/city.json')
    ap.add_argument('--landmarks', default='', help='optional landmarks.js with hand-built famous buildings')
    ap.add_argument('--out', default='pocket-city.html')
    a = ap.parse_args()
    scene = json.load(open(a.scene, encoding='utf-8'))
    city = json.load(open(a.city, encoding='utf-8'))
    problems, warnings = check_city(city, scene)
    for w in warnings: print('note:', w)
    if problems:
        for p in problems: print('PROBLEM:', p)
        sys.exit('Fix city.json and run again.')
    kit = lambda n: open(os.path.join(ASSETS, 'kit', n + '.js'), encoding='utf-8').read()
    lm = open(a.landmarks, encoding='utf-8').read() if a.landmarks else '/* no hand-built landmarks */'
    data = 'const SCENE=' + json.dumps(scene, ensure_ascii=False, separators=(',', ':')) + ';\nconst CITY=' + json.dumps(city, ensure_ascii=False, separators=(',', ':')) + ';'
    def block(i, t):
        t = t.replace('</script', '<' + chr(92) + '/script')
        return '<script type="text/plain" id="' + i + '">\n' + t + '\n</script>\n'
    tpl = open(os.path.join(ASSETS, 'template.html'), encoding='utf-8').read()
    meta = {k: scene['meta'][k] for k in ('lat', 'lon', 'size', 'rotation', 'osm_base')}
    parts = [block('projection', kit('projection')), block('models', kit('models')), block('streetFigures', kit('streetFigures')),
             block('data', data), block('landmarks', lm), block('city', kit('city')), block('foliage', kit('foliage')), block('painter', kit('painter')),
             '<script type="application/json" id="cityData">' + json.dumps(city, ensure_ascii=False).replace('</', '<\\/') + '</script>\n',
             '<script type="application/json" id="sceneMeta">' + json.dumps(meta) + '</script>\n',
             '<script>\n' + open(os.path.join(ASSETS, 'page.js'), encoding='utf-8').read() + '\n</script>\n</body></html>\n']
    html = tpl.replace('<!--POCKET-CITY-BLOCKS-->', ''.join(parts))
    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or '.', exist_ok=True)
    open(a.out, 'w', encoding='utf-8').write(html)
    print(f'Built {a.out} ({len(html) // 1024} KB). Open it in a browser, or check it with: node render.mjs {a.out} --out shots/')


if __name__ == '__main__':
    main()
