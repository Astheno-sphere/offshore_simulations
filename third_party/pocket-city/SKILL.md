---
name: pocket-city
description: Build a "Pocket City" of any place in the world - an interactive, hand-drawn isometric diorama of a square plot (150-250 m) with real buildings, streets, trees, shopfronts, traffic and people, as one self-contained HTML page. Use it when someone wants a pocket city, a city diorama, an isometric map or miniature of a street, a neighbourhood or a landmark's surroundings, or a playable street scene of a real place. The skill fetches OpenStreetMap data, places the square so no famous building is cut, researches the buildings' anatomy and street-level design, the climate (seasons or wet/dry weather) and the local culture (festivals and special occasions), then builds the page in the Pocket City style.
---

# Pocket City

You make one page: a square plot of a real place, drawn as a Pocket City (warm paper, flat colour, fine ink, isometric).
The reader turns and zooms it, switches seasons and special occasions, and watches cars, bikes and people move.
Everything measurable comes from OpenStreetMap; everything else comes from research you can cite. The look is
fixed by the kit; your job is the place.

Works in any coding agent that can run Python 3.9+ and Node 18+ (Claude Code, Codex, others). Every step is a script
or a file you write. Paths below are relative to this skill's folder (`SKILL_DIR`); keep your work in a folder of the
user's project, e.g. `pocket-city-<place>/` with a `work/` subfolder.

Setup once: `pip install shapely` (Python), Node 18+ (22+ preferred), and Google Chrome or Chromium for the check
renders (`render.mjs`; set `CHROME=/path` if needed). Network access to openstreetmap.org (Overpass, Nominatim) and the
web for research. Sandboxed agents (Codex runs without network by default): ask the user to allow network for the
fetch step and the research, or to run `fetch_osm.py` themselves and hand you `work/osm.json`. If Chrome cannot start
inside the sandbox, ask the user to run the `render.mjs` line or to open the page and tell you what they see.

## The steps

1. **Agree the place and size.** A place name, an address or coordinates, and a square side between 150 and 250 m
   (200 m if they don't say). Bigger is slower to draw and harder to fill with detail; smaller rarely shows a whole
   street. If they name a landmark to feature, note it for `--keep`.

2. **Fetch the map.**
   `python3 SKILL_DIR/scripts/fetch_osm.py --place "Gion, Kyoto" --size 200 --out work/osm.json`
   (or `--lat --lon`). If Overpass is busy it retries other servers; if all fail, wait a minute and run again.

3. **Place the square.**
   `python3 SKILL_DIR/scripts/plot.py --osm work/osm.json --out work/plot.json [--keep "Name;Other name"]`
   It turns the square to follow the main streets and slides it (up to 40% of its size) so that no famous building
   (wikidata, wikipedia, heritage, historic, place of worship, museum, attraction, or anything in `--keep`) is cut by
   the edge. Open `work/plot-preview.svg` (gold = famous, red = cut, blue = water and coast, green = woods). A square
   with a mix of water, green and buildings makes the best Pocket City; move it with `--lat --lon` or `--size` if it
   is mostly one of them. Rules:
   - **Never cut a famous building.** If the report still lists one as cut: try `--size` a little larger,
     `--rotate north` or another angle, `--slide .5`, or re-centre with `--lat --lon`. If the landmark is bigger than
     the plot, tell the user and agree a larger size or leaving it out.
   - Also look yourself: a building everyone knows may lack tags. Search the place's landmarks during research
     (step 5) and re-run with `--keep` if one is near the edge.

4. **Turn the map into a scene.**
   `python3 SKILL_DIR/scripts/prep.py --osm work/osm.json --plot work/plot.json --drive right --out work/scene.json`
   Use `--drive left` where traffic keeps left (UK, Ireland, Japan, India, Hong Kong, Singapore, Australia, ...).
   The sea comes from the coastline, beaches become sand, piers become paving; boats are moored along quays and
   café tables set outside bars and restaurants (both illustrative). Woods and parks with no mapped trees are filled
   with trees. Where photos show the land the map leaves blank is green (hillside gardens, villas, terraces), add
   `--green-open 9` to draw it as gardens with trees 9 m apart; never use it for car parks, yards or bare plazas.
   Where photos show trees lining a canal or river that the map lacks, add `--bank-trees 7` (trees 7 m apart along the
   banks, named "Bank tree"). Walking routes are moved onto the mapped zebra crossings, so people cross where they
   really do.
   Read the summary line: how many buildings lack a mapped height, how many trees are mapped or added, how many
   boats and named shops.

5. **Research the place.** This is the work that makes a Pocket City good. Follow `references/research.md` (building
   anatomy and street-level design) and `references/seasons-occasions.md` (climate and culture). Keep a sources list
   as you go: every fact you will put on screen needs a page you actually read. Look at real photographs of these
   very streets (street-level imagery, the city's own photo archives, Wikimedia Commons), not at your memory of the
   city. For each famous building in the plot, find a published plan or elevation and several photographs.

6. **Write `work/city.json`.** The schema and every option are in `references/city-json.md`; a complete example is
   `assets/examples/portofino/city.json` (a harbour: sea, boats, woods, painted fronts, a church landmark,
   a bonfire festival) and `assets/examples/gion/city.json` (a tiled-roof old town). In short: a style for each kind of building (rules matched on OSM building type,
   height, use, name) with façade, colours, roof form, pitch, ridge direction and shopfront; overrides for named
   buildings; palette; people and vehicles; 2-5 seasons or weather regimes with sourced notes; 1-3 special occasions
   with decorations and sourced notes; the month-to-season table; views and legend cameras; field notes with links.

7. **Hand-build the landmarks.** A famous building drawn as a generic block is the most visible failure. For each
   one inside the plot, write a module in `work/landmarks.js` following `references/landmarks.md`: trace the
   footprint and parts from the published plan, check every proportion against photographs, and build it from the
   kit's parts (walls with painted elevations, pitched and hipped roofs, towers, domes, porches, canopies).
   `assets/examples/singapore-landmarks.js` shows two full examples (a folded copper mall front with escalators, a
   Gothic cathedral with nave, transept, tower and spire).

8. **Build and check.**
   `python3 SKILL_DIR/scripts/build.py --scene work/scene.json --city work/city.json --landmarks work/landmarks.js --out pocket-city-<place>.html`
   (`build.py` refuses a city.json with unsourced season notes or missing cameras, and prints a `note:` when two
   seasons would look the same on screen: act on every note.) Then render it:
   `node SKILL_DIR/scripts/render.mjs pocket-city-<place>.html --out shots --view iso,bird,<your views> --season <each id>`
   and `--zoom 4` for close-ups of shopfronts and landmarks. Look at every PNG if you can view images; if you cannot,
   ask the user to open the page and describe what they see. Go through the checklist below, fix city.json or
   landmarks.js, rebuild. Repeat until it passes.

9. **Deliver** the single HTML file (it works offline and from disk) and a short summary: the plot (size, turn, what
   is inside), the landmarks you built and their sources, the seasons and occasions with their sources, and what is
   illustrative (unmapped heights, façade details, colours, trips, weather).

## Checklist before you deliver

- No famous building is cut by the plot edge; every one inside is a hand-built landmark that matches its photos.
- Landmarks look right from every side: render at least six yaws and one high view; a tower or wing drawn over its
  neighbour means the parts overlap or were not ordered with `planOrder`.
- Towers and other hand-built boxes show their near faces, not a hollow V of their far walls (rings through `ccw`).
- Every hand-built level is closed on top: from the Bird's-eye view no tower, cornice or drum shows the street through
  an open shaft. Every landmark actually appears: one that throws while building simply vanishes, so find each one in
  a close render.
- Nobody stands in the water or inside a building (`standable`); boats sit in water, not on the quay.
- Night scenes (`night: true` on an occasion, for evening events such as lights, bonfires, processions): lit windows,
  lamps and decorations read as lit, and everything else is dusk, not black.
- Roofs: the right form for the place (flat, gabled, hipped, tiled, slate, metal) and ridges running the right way
  (e.g. parallel to the street for Kyoto machiya and Dutch canal-house fronts turned gable-on: check photos).
- Heights look right against photos; unmapped buildings use the typical storey count for their street.
- Ground floors read as the street really is: shopfronts where there are shops, with real shop names from the map
  where they exist; lattice, shutters, arcades, stoops or walls where there are not.
- Street furniture, paving, lamps, vehicles (types, colours, taxis, plate colours) and driving side match the place.
- Colour: the page should feel like the place on a clear day. If it reads grey or washed out, check photos for wall,
  shutter, roof and awning colours and the greenery you are missing; leaves and grass are clearly green, never
  grey-green (`scripts/vivid.py` lifts a dull city.json). Never paint a place brighter than its photos, nor duller.
- Water and green: the water colour is read from photos (the engine adds the wash, reflections and ripples); boats,
  trees in woods and gardens match the place (boat types and colours, tree species, which ones shed their leaves).
- Paving: squares and pavements use the style the place really has (`paving.style`: slabs, ishidatami, tiles), not a
  bare grid.
- Each season or weather regime looks different on screen, by more than the crowd (leaves where trees shed them, light,
  ground, rain or snow, clothing, café tables, boats); a mild evergreen coast gets two or three chips, not four. Each
  occasion shows its decorations and crowd. Seasonal notes are one sourced fact each, short, with a working link.
- The page turns smoothly in the Cinematic view. Hundreds of trees are fine (crowds of trees are drawn lighter by
  themselves); thousands of hand-built parts in `landmarks.js` are not: merge faces that share a colour.
- No page errors in the render output; the page opens straight from disk.
- Text on screen states only what a named source says; everything else is listed as illustrative in the field notes.

## Rules that keep the style

- Draw from references, never from memory. Real objects only (no abstract state cubes or icons in the scene).
- Keep the kit's look: flat colours, fine ink, calm motion. Do not add glow, gradients or drop shadows of your own
  (the engine's own night lights, water wash and reflections are part of the look).
- People are small figures; no portraits, no likenesses, no recognisable individuals.
- Credit the data: OpenStreetMap (ODbL) is already in the footer and field notes; add any other dataset you used
  (tree registers, 3D building data) to `credits` and `notes`.
- If the place is sensitive (a site of conflict, a disaster, a place of worship during prayer), keep it respectful:
  everyday street life, no staged events.

## Files

- `scripts/fetch_osm.py`, `plot.py`, `prep.py`, `build.py`, `render.mjs`: the pipeline above (run any with `-h`).
  `walks.py` (used by prep.py: walking routes onto zebra crossings), `vivid.py` (richer colour for a dull city.json).
- `assets/kit/`: the drawing kit (projection, models, people, foliage, painter: shared with the Pocket City atlas)
  and `city.js`, the engine that draws any scene in the look set by city.json.
- `assets/template.html`, `assets/page.js`: the page around the drawing.
- `assets/examples/`: Portofino (Liguria) and Gion Shirakawa (Kyoto, kept under the name gion), each with city.json, landmarks.js and the built page;
  the Singapore landmark code.
- `references/`: research guides, the city.json schema, the landmark kit.

Licence: MIT (see LICENSE). Map data stays under the OpenStreetMap ODbL. Made by April Zhu (april-zhu.com).
