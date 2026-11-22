# city.json

Everything about the place that the map does not say. Colours are hex strings; a list of colours means "vary between
these" (each building picks one by its id). Full examples: `assets/examples/portofino/city.json` and `assets/examples/gion/city.json`.

```jsonc
{
  "name": "Kyoto",                       // big title on the card
  "title": "Gion, Kyoto",                // browser tab: "Pocket City · <title>"
  "region": "Gion",                      // small red line above the title (district, or country)
  "place": "Shijō-dōri × Hanamikōji",    // the street corner or square, under the title
  "flag": "<svg viewBox='0 0 30 20'>…</svg>",   // optional 30×20 flag or emblem; leave out to hide
  "timezone": "Asia/Tokyo",              // picks the opening season from today's local month
  "level": 3.0,                          // metres per storey when only levels are known (default 3.2)

  "styles": {
    "default": { ... a style ... },      // applies to every building
    "rules": [                           // first rule that matches wins (add "more": true to keep matching)
      { "if": { "minLevels": 4 }, "set": { "facade": "office", "roof": "flat" } },
      { "if": { "type": ["temple", "shrine"] }, "set": { "facade": "temple", "roof": "hipped", "pitch": 35 } }
    ]
  },
  "buildings": {                         // overrides for single buildings, by id from scene.json
    "w123456": { "levels": 5, "facade": "stucco", "wall": "#e8d8c0" }
  },

  "palette": { "ground": "#eadfc9", "road": "#b8aeb2", "pavement": "#ebdfc8", "walk": "#e6d7be", "grass": "#b4d784",
               "water": "#86c6cc", "slab": "#d8c5a3", "marking": "#f4ead3", "kerb": "#e3c477", "paving": "#c6baa7",
               "rail": "#7d7f86", "sand": "#ecd9a8", "quay": "#d9cfbb" },
                                         // water: one colour, read from photos (harbour turquoise, canal green-grey, river brown-green).
                                         // The engine paints the rest from it: see "Water" below
  "paving": { "style": "slabs", "size": 0.7, "colour": "#c6baa7" },   // pavements and squares: style slabs (stone, running bond: piazzas, old towns),
                                                 // ishidatami (long granite slabs: Japanese lanes), tiles (square concrete: modern cities), grid (joints only).
                                                 // size = row height in metres; colour = joints; optional "stone" = slab colour. Default: tiles.
                                                 // Never leave a famous square on grid: look at what it is really paved with.
  "lamp": { "colour": "#5d6b66", "height": 5.2, "head": "#f3e7c4", "auto": true },
  "shops": { "signs": ["CAFÉ", "BAKERY"], "font": "sans-serif", "fascias": ["#526e75", "#9f6554"], "awnings": ["#af7762"] },

  "boats": { "hulls": ["#f3efe4", "#2f5f8a"], "stripes": ["#b8483b"], "covers": ["#3f6e9a"], "inside": "#c8a27a",
             "cabin": "#f6f3ea" },             // moored boats prep.py places on quays and at anchor (only where there is water)
  "cafes": { "umbrellas": ["#f3efe4", "#2f5f8a"], "stripes": true, "table": "#f1ece0", "chair": "#8a6f55" },
                                         // outdoor tables prep.py sets in front of bars, cafés, restaurants, ice-cream shops
  "trees": {
    "default": { "style": 3, "colours": ["#8ab673", "#adca7c"], "height": 8 },   // clear greens, never grey-green
    "rules": [ { "match": "Prunus|cherry", "style": 3, "blossom": "#f4c7cf", "autumn": "#d4774f", "height": 6 },
               { "match": "Pinus|pine", "style": 5, "evergreen": true },
               // prep.py names the trees it scatters in woods "Woodland", in parks "Park tree", in --green-open land
               // "Garden tree": give each a mix of the species photos show there (share = weight, vary = height spread)
               { "match": "Woodland", "evergreen": true, "vary": .4, "mix": [ { "style": 3, "colours": ["#63994e"], "height": 9, "share": 5 },
                 { "style": 2, "height": 13, "share": 2 }, { "style": 7, "height": 12, "share": 1 } ] } ],
    "extra": [ [12.5, -30, 7, "Prunus × yedoensis"] ]   // photographed trees missing from the map: x, y, height, species
  },
  "people": { "skin": [...], "clothes": [...], "pants": [...], "hair": [...], "umbrellas": [...], "bikes": [...] },
  "vehicles": { "kinds": ["small", "hatch", "mpv"], "colours": [...], "plate": "#f2f2ee",
                "taxi": { "share": 0.25, "colours": ["#2c2c34"], "kind": "sedan", "sign": "#f6e7a6" } },

  "seasonLabel": "Season",               // or "Weather" for wet/dry regimes
  "seasons": [ { "id": "spring", "label": "Spring", "leaves": "blossom", "wx": "fluff", "note": { ... } }, ... ],
  "occasionLabel": "Special scenes",
  "occasions": [ { "id": "matsuri", "label": "Gion Matsuri", "crowd": 1.6, "decor": { "lanterns": [...] }, "note": { ... } } ],
  "months": ["winter","winter","spring","spring","spring","summer","summer","summer","autumn","autumn","autumn","winter"],

  "isoLabel": "Overview",                // no longer shown: pages open on Cinematic, which starts on this camera
  "cameras": { "iso": { "yaw": -35, "pitch": 33, "zoom": 0.93, "x": 0, "y": 0, "z": 4 } },   // optional; zoom is fitted to the plot
  "views":  [ { "id": "street", "label": "Hanamikōji", "camera": { "yaw": 20, "pitch": 24, "zoom": 3.5, "x": -10, "y": 4, "z": 3 } } ],
  "legend": [ { "name": "Machiya", "source": "OpenStreetMap", "count": "84", "icon": "buildings", "camera": { ... } } ],
  "notes":  [ { "title": "Machiya", "text": "…", "links": [ { "label": "Kyoto City", "url": "https://…" } ] } ],
  "credits": [ { "label": "Kyoto City tree survey", "url": "https://…" } ]
}
```

## A style (in `default`, rule `set`, or `buildings`)

| Field | Values | Default |
|---|---|---|
| `facade` | `house`, `apartment`, `brick`, `stucco`, `painted` (Italian/Ligurian: wall-dominant, narrow windows, louvred shutters, painted surrounds and quoins), `civic`, `temple`, `shophouse`, `timber`, `office`, `glass`, `plain`, `warehouse` | `house` |
| `wall` | colour or list | `#eee2ca` |
| `levels`, `floor`, `height` | storeys when unmapped; storey height m; force a wall height m | 3, `level`, - |
| `roof` | `auto` (OSM roof:shape, else flat), `flat`, `gabled`, `hipped`, `pyramidal` | `auto` |
| `pitch` | roof slope in degrees | 30 |
| `ridge` | `long` (along the footprint), `short` (across), `street` (parallel to the street it faces) | `long` |
| `roofColour`, `flatRoof` | colours for pitched roofs and for flat roofs | `#c8c4b8` |
| `roofTex` | `kawara`, `pantile`, `slate`, `tiles`, `copper` (texture on pitched roofs) | none |
| `eaves` | overhang m | 0.45 |
| `maxSpan`, `rectFill` | widest span that gets a pitched roof; how rectangular the footprint must be | 22, 0.78 |
| `parapet`, `rooftop` | flat-roof parapet height m; `none` hides rooftop units | 0.5 |
| `eave1`, `eave1Depth` | a pent roof above the ground floor on street faces (machiya, shophouses) | false, 0.75 |
| `bay` | window bay width m | by façade |
| `glass`, `frame`, `trim`, `dark` | window glass colours, frames, trim/cornices, railings | soft defaults |
| `shutters` | colour or list: shutters beside each window | none |
| `shutterOpen` | `painted` façade: share of windows with shutters open (the rest closed) | 0.55 |
| `balcony` | `true` every window, `"some"` alternate | none |
| `bars` | `false` removes glazing bars | true |
| `wood`, `slat`, `noren` | `timber` façade: wood, lattice slat and shop-curtain colours | browns, indigo/red |
| `shop` | `poi` (shopfront where the map has a named shop), `street` (every street face), `none` | `poi` |
| `shopHeight`, `shopWall`, `fascia`, `awning`, `awningDepth`, `awnings`, `stripes` | shopfront tuning; `awning`: `false`, `"some"` | |

## Rule conditions (`if`)

`type` (OSM building value, string or list), `use` (shop/amenity value), `mat`, `name` (regex), `famous`, `cut`,
`minH`/`maxH` (m), `minLevels`/`maxLevels`, `minArea`/`maxArea` (m²), `unknownHeight` (true/false),
`nearStreet` (true/false: the footprint touches a carriageway).

## Seasons and occasions

See `seasons-occasions.md` for the fields (`leaves`, `wet`, `snow`, `coats`, `umbrellas`, `wx`, `haze`, `crowd`,
`cafes`, `boats`, `grass`, `petals`, `night`, `litShare`, `dress`, `decor`, `ice`, `sub`, `icon`, `note`). `note` is required on every one: `{ "text", "source", "url" }`.
Chip icons exist for `spring`, `summer`, `autumn`, `winter` (set `icon` to reuse one for another id).

## Water

Wherever the map has sea, a harbour, a river or a canal, the engine paints it from `palette.water` alone:
- a wash that deepens toward the banks, with a bright waterline;
- the reflections of waterside buildings (wall and roof colours), trees (the season's leaf colour) and boats, broken
  into soft level bands the way ripples break a real reflection, and turning with the camera;
- light and dark ripples that drift (they stop when the simulation is paused).
A season with `"ice": true` freezes it to a pale flat sheet. There is nothing to configure: choose the water colour
from photos and check it beside the boats and quay. Hand-built landmarks are not mirrored.

## Cameras

`yaw` (degrees, turn), `pitch` (12-74, look-down angle), `zoom` (1 ≈ a 186 m plot fills the stage; the overview is
fitted automatically), `x`, `y` (the point to look at, plot metres), `z` (height of that point). Find good views by
opening the page, moving there, and reading the values: in the browser console, `JSON.stringify(camera)`.

## Tree styles

`style` picks the tree's form: 1 upright broadleaf with a leader, 2 vase / umbrella (plane, umbrella pine), 3 round
(oak, holm oak, lime), 4 fine-leaved (birch, willow), 5 conifer, 6 sparse open crown (olive), 7 narrow column (cypress,
poplar).
