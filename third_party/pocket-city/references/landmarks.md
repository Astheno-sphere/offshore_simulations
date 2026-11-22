# Hand-building a landmark

Every famous building inside the plot is built by hand in `work/landmarks.js`. The generic engine draws ordinary
streets well; a cathedral, a temple gate, a mosque or a mall front drawn as a box is wrong at a glance.

## Method

1. **Trace, don't recall.** Find a published plan (architect's site, heritage register, Wikimedia Commons drawings,
   an academic survey) and at least three photographs from different sides. Read the dimensions you can (total
   height, tower height, number of bays, storey count). Note each source.
2. **Use the map footprint** as the outer limit: `findBuilding(id)` gives the clipped ring, and OSM `building:part`
   ids give storeys and towers if they are mapped. Where the map is coarse, derive sub-volumes from the plan
   (offsets along the footprint's axes) and check them against the photographs.
3. **Break it into parts** the way it is built: base, body, roof, tower, spire, porch, colonnade, canopy, dome. Each
   part is a few calls to the kit. Give each volume its own footprint, never overlapping another (split the OSM
   outline where a tower or aisle meets the body), and order them with `planOrder`: it is correct from every angle.
   Check renders from at least six yaws, including a high one: a tower drawn over its church only shows from some.
4. **Check in a render** from six sides and from above (`render.mjs --view` with cameras you add for it) and at close zoom.
   Compare with the photographs; fix proportions before adding detail.

## The module

```js
// landmarks.js — runs inside the drawing engine; every kit function is available
const LANDMARKS = [
  {
    name: 'Kanji Museum',
    ids: ['w123456789'],               // these generic buildings are replaced by what build() returns
    build() {
      const b = findBuilding('w123456789'), ring = b.ring;
      const body = block(ring, 0, 13.5, { facade: 'civic', wall: '#ece3d3', trim: '#f8f1e2', floor: 4.5, bay: 3.6 });
      const cap = roofOver({ c: b.obb.c, ax: b.obb.ax, L: b.obb.L - 2, W: b.obb.W - 2 }, 13.5,
                           { roof: 'hipped', pitch: 22, roofColour: '#77797f', roofTex: 'kawara' });
      return obj(ring, 20, () => planOrder([body, { fp: ring, z1: 20, svg: cap() }].map(p => ({ ...p, svg: p.svg ?? p.draw() }))));
    }
  }
];
// optional: parts that move or appear only in a season/occasion (stalls, floats, a stage, falling petals);
// place people and props only where standable(x, y) is true
function CITY_EXTRA(t) {
  if (SEASON.id !== 'matsuri') return [];
  return [{ fp: rect(0, 10, 4, 8), h: 20, draw: t => /* svg string */ '' }];
}
```

`build()` returns one model `{ fp, h, draw }` (or a list). `fp` is the plan footprint used for depth order and
shadows; `h` its top; `draw()` returns the SVG-like markup. Models are cached per camera, so `draw()` may be slow.

## The kit (all in scope)

| Function | What it gives |
|---|---|
| `findBuilding(id)` | the scene building: `ring`, `holes`, `h`, `lv`, `min`, `obb` {c, ax, L, W}, `n` (name), `pois` |
| `block(ring, z0, z1, style)` | a flat-topped volume with painted elevations: `{fp, z1, draw}` |
| `walls(ring, z0, z1, {st: makeStyle({...}), body: colour})` | just the walls (returns a draw function) |
| `makeStyle({...})` | a full style from a few fields (`facade`, `wall`, `floor`, `bay`, `trim`, `shutters`...) |
| `roofOver({c, ax, L, W}, wallTop, {roof, pitch, roofColour, roofTex, eaves})` | gabled, hipped or pyramidal roof (returns a draw function) |
| `peak(ring, baseZ, [x, y, tipZ], colour)` | a pointed roof or spire over any ring |
| `loft(ringA, ringB, n => tone(n, soft(colour)))` | the surface between two 3D rings (domes, drums, tapering towers: stack several) |
| `shape(points3D, colour, ink)` | one flat face (`ink` = outline weight, 0 for none) |
| `edge(a, b, colour, width)` | a line in metres (railings, mullions, ridges) |
| `stick(a, b, radius, colour)` / `ball(c, r, soft(colour))` | posts, poles, finials, lanterns |
| `rect(x, y, w, d)` / `polygon(x, y, r, n)` / `atZ(ring, z)` | rings |
| `tone(n, soft(c))`, `vis(n)`, `vNewell(pts)`, `depthOf(p)`, `avg(pts)` | shading, facing, sorting for your own faces |
| `sheetInk(face4, 'kawara'|'slate'|'pantile'|'tiles'|'copper', u, v)` | a material texture that turns with the face |
| `planOrder(parts)` | order `{fp, z1, svg}` parts that **touch** (tower against a nave, wings, aisles): sorts each pair by the side of their shared wall the reader is on. Always use it inside one landmark |
| `planSort(parts)` | order separate, non-touching parts back to front (can guess wrong for volumes that touch) |
| `ccw(ring)` | the ring running counter-clockwise. **Pass every OSM ring through it before building faces yourself**: on a clockwise ring each face points inward and the far walls get drawn instead of the near ones |
| `lightPool(x, y, r, colour, strength)` | soft light on the ground (lamp, fire, tree), fading to its edge; use a light colour |
| `standable(x, y, gap)` | true if a person or prop may stand there: in the plot, not on water, not in a building, `gap` m from the quay |
| `SEASON` | the current season or occasion (`SEASON.id`, `SEASON.snow`, ...) |

**Close every level on top.** Walls you build yourself (a ring of quads) have no lid. Wherever a volume ends or steps in
(a tower's cornice, the flat roof round a drum or lantern, a terrace), draw the top face too with `shape(ringAtZ, colour)`.
Seen from above, an open shaft shows the street through the building. `block()` and `roofOver()` already close
theirs. Check every hand-built volume from the Bird's-eye view, not only from the side.

**Draw at draw time.** Call `.draw()`, the function `roofOver` returns, and anything that reads `SEASON` only inside the
function you pass to `obj(...)`, never in the body of the build function. At build time `SEASON` does not exist yet:
the landmark throws, and it simply vanishes from the picture (the error is logged as `landmark <name>` inside the
worker, so the page shows nothing). After building, search the render for every landmark from a close view.
| `UPX` | metres per screen pixel: draw fine detail only when `UPX < 0.3` |

Lettering on walls (a name over a gate): paint it in a custom elevation or as faces; wall text must go through
`wallText(g, text, x, y, width)` inside an elevation painter because elevations run right-to-left.

## Worked examples

`assets/examples/singapore-landmarks.js` is the code of Pocket City Singapore, which uses the same kit under older
names (`section` is the ancestor of `walls`). Read `buildFunan()` (a multi-part mall: storeys from `building:part`,
a split footprint so front and back sort correctly, an escalator bank, roof gardens) and the cathedral section
(`nave`, `transept`, `spire`, `pinnacles`: footprints derived from the plan along the building's axis, lancet windows
in custom elevation styles, a spire from `peak`). Both were traced from architects' drawings and photographs.
