# Seasons, weather and special occasions

The season chips and the occasion menu change the whole scene: leaves, ground, light, weather, clothing, crowds and
decorations. Each one shows a one-line note on the card, and that line must be a fact a named source states.

## 1. Choose the seasons (2-5 chips)

Pick what the place actually has, from its climate:
- **Temperate**: spring, summer, autumn, winter; add a snow toggle (a season with `"sub": "winter"`) only if snow is
  common enough to be a normal winter scene there.
- **Tropical, monsoon**: weather regimes instead, e.g. Dry and Wet, or Northeast monsoon / Inter-monsoon /
  Southwest monsoon. Set `seasonLabel` to "Weather".
- **Mediterranean and other mild coasts**: usually a dry, bright summer, a rainy autumn and a mild, quiet winter:
  two or three chips, not four. Most trees there are evergreen (holm oak, pine, olive, palm), so `leaves` changes
  almost nothing. A chip has to differ in something you can see: rain, crowds, café tables, boats, clothing.
- **Arid**: e.g. Cool season and Hot season; dust or haze as an occasion if it is a known event.
- **Polar or subarctic**: light matters most: e.g. Midnight sun and Polar night; snow most of the year.

**Every chip must look different on screen.** Before keeping a chip, name what the reader will see change. If the
answer is only "a few more people", drop it. Check which trees really shed their leaves (the park or forestry
service, a regional flora): never mark a whole wood evergreen or deciduous by guess. build.py warns when two chips
would look the same.

Map each calendar month to a chip in `months` (January first) so the page opens in the right one, and set
`timezone` (an IANA name like `Asia/Tokyo`).

Good sources: the national meteorological service's climate normals (JMA, KNMI, Met Office, NOAA, MSS, BoM, IMD),
the city government's climate page, phenology reports (cherry blossom, leaf colour) from the met service or a
university. Read the number you quote off the page.

## 2. What each season changes

| Field | Effect |
|---|---|
| `leaves` | `spring` (fresh green), `summer`, `autumn` (each tree's `autumn` colour), `bare` (deciduous trees lose leaves; `evergreen` trees keep them), `blossom` (trees with a `blossom` colour flower) |
| `wet` | darker ground, puddle reflections, rain; set `umbrellas` too |
| `snow` | snow on roofs and ground, snowfall |
| `coats` | everyone in winter clothes (coat, scarf, woolly hat) |
| `cafes` | café tables on the pavement: `"closed"` folds their umbrellas (rain, off-hours), `false` puts the tables away (winter, off season). Illustrative unless a source says so |
| `boats` | share of the moored boats shown, e.g. `0.5` in the off season. Illustrative |
| `grass` | a grass colour for this season, e.g. the palette green for a mild winter where lawns stay green (the default winter turns grass straw-coloured) |
| `wx` | weather particles: `rain`, `drizzle`, `snow`, `fluff` (blossom petals or seeds) |
| `haze` | a warm haze over the frame |
| `crowd` | busier (1.5) or quieter (0.6) streets |
| `dress` | `{ "colours": [...], "share": 0.6 }` clothing colours for an occasion (orange for King's Day, white for a festival) |
| `decor` | occasion decorations, below |
| `note` | `{ "text": "...", "source": "...", "url": "..." }` required |

Tree rules give each species its seasonal colours (`spring`, `autumn`, `blossom`, `winter`, `evergreen`): research
which street trees turn which colour and when, and which flower (sakura, jacaranda, frangipani).

## 3. Special occasions (1-3)

Choose occasions that change how this street looks: a festival that decorates it, a market day, a holiday parade, a
seasonal event (cherry blossom viewing, Diwali lights, Christmas market, Chinese New Year lanterns, a race weekend), or
a weather event the place is known for (haze, typhoon rain, frozen canals). Prefer ones that happen in or next to
the plot; say so in the note if it is city-wide.

For each, research: the date or season, what is put up (lanterns, bunting, flags, banners, stalls, lights), their
colours and where they hang, how crowds and traffic change (road closures!), and what people wear.

`decor` options:
- `bunting`: colours of flag strings across the two longest streets (`span` half-width in metres, `height`)
- `lanterns`: colours of lanterns hung under shop eaves along every shopfront (`lanternGap` spacing)
- `flags`: colours of small flags on lamp posts

If an occasion needs something the engine doesn't draw (floats, stalls, a stage), add it as a landmark-style part in
`landmarks.js` using `CITY_EXTRA` (see `landmarks.md`), and show it only when `SEASON.id` matches.

## 4. Writing the notes

- One fact per note, one sentence, under 110 characters. No dot separators, no lists.
- Say what the source says: "July's Gion Matsuri fills Shijō-dōri with lantern-lit floats." needs a source that
  says exactly that.
- `source` is the publisher's name as a reader would recognise it ("Japan Meteorological Agency", "Kyoto City
  Tourism Association"); `url` is the page you read.
- Never put a number on screen you did not read on the source page.

## Night scenes

Add `"night": true` (or a strength such as `0.85`) to an occasion that happens after dark: Christmas lights, an
evening bonfire, a lantern festival, a night market. Every colour sinks to dusk; windows light up (`"litShare": 0.7`
of them), lamps light and pool on the ground, and these decorations stay bright:
- `"decor": { "fairy": ["#fff3c4", "#ffe7a8"] }`: strings of lights along the street fronts and the quay edge, with a
  warm shimmer on the water.
- `"decor": { "litTrees": "Bank tree|^$" }`: a regex on tree species; those trees keep their colours and get a pool of
  light (a cherry light-up). `^$` matches mapped trees with no species.
- Light colours that never dim (use them in landmarks.js for flames, bulbs, stars): #ffd98a #ffe7a8 #fff3c4 #fbefc8
  #f6c445 #ffb85c #fff8e0 #f2c94c #fde9b0 #ffcf7a #ff8a3d #f26a2e #ffc069.
Only use night when the source says it happens in the evening (state the time in the note).

`"petals": true` on any season or occasion with `"leaves": "blossom"`: every tree whose rule has a `blossom` colour
sheds pink petals that drift down from its crown (they stay bright at night). Use it for cherry or plum blossom time.
