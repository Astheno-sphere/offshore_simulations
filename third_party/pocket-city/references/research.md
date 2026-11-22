# Researching the buildings and the street

A Pocket City is believable when each building is built the way that street builds, and when the ground floor and
the pavement look like that street on an ordinary day. This guide is the checklist; the right-hand column tells you
which city.json field the answer goes into.

Work from evidence, in this order:
1. **Street-level photographs of these exact streets** (Wikimedia Commons, the city's archive, Mapillary/KartaView,
   tourism and heritage pages, news photos). Look at several dates and seasons.
2. **Published plans, elevations and descriptions** for named buildings (architects' project pages, heritage
   registers, the building's own site, academic papers).
3. **Typology sources** for the ordinary fabric (city planning guidelines, heritage design guides, books and articles
   on the local house type).
4. OpenStreetMap tags already in `scene.json` (building type, levels, roof shape and colour, material, shop names).
Your memory of a city is not a source: it averages many places and gets details wrong. When a detail can't be
checked, choose the plainer option and list it as illustrative.

## 1. Anatomy of the building types

Group the plot's buildings into 3-7 types (e.g. Kyoto: machiya townhouse, modern 4-9 storey mixed-use, ochaya
teahouse, temple hall; Amsterdam: canal house, 19th-century block, modern infill). For each type find:

| Question | Look for | city.json |
|---|---|---|
| How tall, how many storeys, storey height | photos, design guides, OSM levels | `levels`, `floor`, `height` |
| Roof form and pitch | flat / gabled / hipped / mansard; slope in degrees | `roof`, `pitch` |
| Which way the ridge runs | parallel to the street (Kyoto machiya, terraced houses), gable to the street (Dutch canal houses), along the plot | `ridge`: `street`, `long`, `short` |
| Roof material and colour | tile (kawara, pantile, plain), slate, metal, concrete; real colour | `roofTex`, `roofColour` |
| Eaves | overhang depth, a pent roof between storeys | `eaves`, `eave1`, `eave1Depth` |
| Wall material and colour | plaster, brick, timber, stone, render, glass, tile; a palette of 2-4 real colours | `wall`, `facade` |
| Façade rhythm | bay width, window proportion, symmetry | `bay`, `facade` |
| Openings | window type (sash, casement, sliding lattice, ribbon), shutters, balconies, bars | `facade`, `shutters`, `balcony`, `bars` |
| Ornament worth drawing | cornices, pilasters, lattice (koshi), slit windows (mushiko), arcades (five-foot way) | `facade` (`stucco`, `civic`, `timber`, `shophouse`) |
| Parapet and rooftop | parapet height, water tanks, plant, AC units, roof gardens | `parapet`, `rooftop` |

Façade kinds the engine paints: `house`, `apartment`, `brick`, `stucco`, `civic`, `temple`, `shophouse`, `timber`,
`office`, `glass`, `plain`, `warehouse`. Pick the nearest and tune it with colours, bay, shutters and balconies. If
none is close (a mosque, a pagoda, a market hall), that building is a landmark: see `landmarks.md`.

Then write **rules** that assign the types: by OSM `building` value, levels or height, use (`shop`/`amenity`), name,
area, or whether it fronts a street. Check the result in a render and add per-building overrides
(`buildings: {"w123456": {...}}`) where a rule gets one wrong. Use the ids printed in `scene.json`.

**Heights.** OSM often lacks heights. Count storeys in photos for the buildings you can see and put them in
`buildings` overrides (`levels`); let rules give the typical count to the rest. Keep `floor` true to the type
(machiya ~2.9 m, Haussmann ~3.3 m, offices ~3.8 m).

## 2. The street level

| Question | Look for | city.json |
|---|---|---|
| What is on the ground floor | shops, cafés, homes, offices, temples; which streets | `shop` (`poi`, `street`, `none`), rules with `nearStreet` |
| Shopfront anatomy | fascia height, glass, door position, awning or noren, shutters | `shopHeight`, `bay`, `awning`, `awningDepth`, `fascia`, `awnings` |
| Signs | script and language, typical words, colours | `shops.signs`, `shops.font`, `shops.fascias` (shop names from the map are used first) |
| Pavement | material, unit size and colour, kerb colour | `palette.pavement`, `paving.size`, `paving.colour`, `palette.kerb` |
| Road | asphalt tone, markings colour (white, yellow), crossings | `palette.road`, `palette.marking` |
| Ground and green | plaza stone, gravel, grass, planting | `palette.ground`, `palette.walk`, `palette.grass` |
| Lamps | post colour, height, head | `lamp.colour`, `lamp.height`, `lamp.head` |
| Street trees | species, size, which streets | `trees.rules` (by species name), `trees.extra` for photographed trees missing from the map |
| Vehicles | common car types, colours, taxi colour and share, plate colour | `vehicles` |
| People | everyday clothing colours, umbrellas, bikes | `people` |
| Traffic side | keep left or right | `prep.py --drive` |

Shop names: `scene.json` has the map's named shops (`pois`); the engine paints them on the fascia of the building
they stand in. Do not invent brand names. Generic `shops.signs` should be ordinary words in the local script
("CAFÉ", "パン", "KEDAI KOPI").

## 3. Light and colour

- Sample colours from several photos taken in clear daylight; avoid sunset or filtered images. Then keep them as rich as
  the photos: the paper tone and the wash mute everything a little, so a colour copied "soft" ends up grey. The usual
  failure is dull green: leaves and grass should be clearly green (around 35-55% saturation: e.g. `#8ab673`, `#adca7c`
  for crowns, `#b4d784` for grass), never grey-green such as `#90ad81`. Water is turquoise, teal or green-grey as the photos
  show, never a pale grey-blue.
- Only a colour that is close to pure in reality (a signal-red torii, a neon sign) is lifted a little towards the paper.
- If the first render reads washed out, run `python3 SKILL_DIR/scripts/vivid.py work/city.json` once and compare again
  with the photos: as rich as the place on a clear day, never richer.
- Use 2-4 wall colours per type so a street varies the way it really does; repeat what is common.
- Don't paint shadows or glow: the engine shades by face.

## 4. Write it down

Keep `work/sources.md`: one line per fact, with the URL and what it supports. Field notes (`notes` in city.json)
summarise what is measured, what is traced from references and what is illustrative, with links.
