# Study: abhinavbwj carousel "What informal cities do better" (Instagram DgA9DnwkVVq, 13 slides, posted 2026-11-22)

Method: all 13 slides viewed in the owner's Chrome (Claude in Chrome), zoomed per slide, plus the page text. No download, nothing committed from the images.
Limits: viewed at screen size (about 430 px wide per slide), so type sizes below are fractions of the slide, not measured pixels. Re-measure with a saved file.
Owner comment on the post (account arshad.abbasia) asks when his Rhino MCP and visual skills will be published: not published, so we build our own.

## Slide system (same on every slide)
- Near-black ground. Warm amber fill for lit rooms and highlighted data; cream (off-white) line and figure colour; one cool steel blue reserved for the "planned" comparison. Three hues plus neutrals, nothing else.
- Bottom third is a fixed text block: small spaced orange capital kicker, a bold geometric sans headline (Montserrat-like) in cream with the last two or three words in amber, then a 3 to 5 line body in lighter weight, then a one-line grey source note, handle bottom right. A swipe cue on slide 1 only.
- Top 55 to 65 % is the picture. Headline is 4 to 6 words and states the finding; the kicker names the topic.
- 13 slides: cover, 2 stories (Quinta Monroy 2004, Map Kibera 2009), 1 scale statistic, 5 computed comparisons, 1 hillside case, 1 synthesis, 1 lesson, 1 recap with maps. Order: claim, scale, evidence in five measures, cases, synthesis, lesson.

## The illustration level
- Building cross-sections as line drawings with the rooms filled amber where lit, interiors furnished, people as small cream silhouettes doing things (cooking, building, selling, carrying). Hidden-line architectural section feel, thin consistent stroke, flat fills, no shading, no gradients.
- A repeating figure and furniture vocabulary (people, beds, shelves, bikes, washing lines, tap, drain pipes, a hillside stair) clearly drawn from a library. Storytelling is by who is where, not by labels.
- Context objects carry the argument: a lane with washing lines, a drain under the street, 5-minute amenities row, a hillside of stacked houses.
- Not verifiable from the page how these were made (hand drawn, generated or scripted). Treat the look as the target, not the method.

## The data level
- Maps are figure-ground: black ground, building footprints in neutral grey, the studied place highlighted in amber and the planned comparison in blue-grey. Same scale and window (1 km square) for every place, so panels compare directly. Small multiples in 2 or 3 panels with a coloured label chip stating the measured value on the panel.
- Metrics are computed from OpenStreetMap with OSMnx (the footnote says so): share of a 400 m circle reachable on foot, route length against straight line (median of 300 pairs per site), median open-ground width between buildings (colour bands under 2 m up to over 16 m), median building footprint, share of ground covered, junctions per km squared.
- Every figure carries the date of the data (November 2026), the window, the method in one line, and a completeness caveat (informal districts are less fully mapped), plus named outside sources (UN Statistics 2024, IBGE 2022, Map Kibera, Elemental).
- Bar charts: small, labelled on the mark, orange for informal and blue for planned, no axes chrome.
- The conclusion is hedged honestly: three of the districts win on two counts, corners and reach are mixed.

## Tool read
- The carousel maps are Python and OSMnx by the author's own footnote, not Rhino. Rhino, Grasshopper and Heron appear in the Dubai walkability reel (3D massing, solar analysis). So there are two stacks: Python geographic analytics plus illustration for carousels, Rhino-Grasshopper for 3D urban films.
- Heron (a Grasshopper GIS import plug-in) and Rhino MCP are not verified here. Rhino is commercial (trial available); QGIS is GPL, run as a separate process. Both need a licence and install check on the owner's Windows laptop before we plan on them.

## Missing levels in our work (gap table)
| Level | Abhinav | Ours today |
|---|---|---|
| Type system | fixed kicker, headline with amber accent words, body, source line, handle; Montserrat | text blocks of mixed size, many at once |
| Colour | black, amber, cream, one blue; amber is the data | maroon ground, low contrast, accents compete |
| Illustration | section drawings with lit interiors and people | hidden-line vessel and helicopter CAD, no people, no interiors |
| Geography | real figure-ground maps at equal scale, with computed overlays | one small low-detail map |
| Analytics | OSMnx metrics with method, date, caveat on slide | no geographic analytics layer; numbers only from our own run |
| Story | human anchor (named place and year), claim to evidence to lesson, hedged | question and proof, without a human or a place |
| Density of real data | every building in a km window | simplified outlines |
| Sourcing on slide | every number has a source line | numbers rely on `report:` refs but source line is not on slide |

## What to build for Irina (proposal, owner decides)
1. Visual identity: black, amber, cream, one blue (for the weather or the comparison). A slide template with kicker, headline with amber accent, body, source line.
2. Human cabin section: a hidden-line section of the S-92 cabin and the Flesland heliport terminal, cabin windows lit amber, passengers as cream figures. Cancelled flights become empty seats and people left in the terminal. Needs a small figure library, built once.
3. Figure-ground map: Bergen service area and Flesland inset from real OSM (we already hold it), 20 installations in amber, rings, plan legs; small multiples for the three limit sets drawn on the same grid.
4. Computed facts with method line, date and caveat on each frame.
5. Rhino and Grasshopper only if we pursue a 3D massing walkthrough; for the carousel-style film the Python stack we have is enough.
