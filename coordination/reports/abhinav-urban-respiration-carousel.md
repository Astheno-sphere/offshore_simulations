# Study: abhinavbwj carousel "Urban Respiration Rotterdam" (Instagram DcLtJr0iMFn, 13 slides, posted 2026-08-18)

Method: all 13 slides viewed in the owner's Chrome, zoomed per slide, plus page text. Nothing downloaded or committed from the images.
Limits: stills only. The simulation panels were black or partly filled at capture time, so they are very likely short videos that grow from an empty field; I did not see them play. Sizes are fractions of the slide.

## Structure (13 slides)
- Slide 1, cover: a black ground, a spaced-capital strapline ("the form decides where the air goes"), a hidden-line building section (cream lines on black: block of flats, a cut mid-rise, a factory, a street with a tunnel) with a warm orange smoke-like field blown through it, then a 3-line title with the middle word in orange, a subtitle ("twelve fluid simulations over real building geometry"), a tiny provenance line, handle bottom right.
- Slides 2 to 13: twelve simulations, one per slide, identical template (see below). Titles: heat island, thermal comfort, wind and shelter, if the water rose, night cooling, cool air from water, traffic plume, fog, ventilation corridors, deposition, footfall, street canyon vorticity.
- The same 14123 x 3368 pixel domain strip over Rotterdam is used for the first ten; the last three switch to different windows, so a strip is reused until the physics asks for another place.

## The simulation slide template
1. Title in bold white caps, then one grey line stating what the field is and, crucially, what it is not ("simulation, not measurement", "a comfort proxy, not UTCI").
2. Label "MAPBOX SATELLITE", then the real satellite image of the window (the evidence).
3. Label "SIMULATION / <one-line finding>" ("the sealed core holds heat long after the parks let go"), then the simulation panel on black: building footprints rasterised from OSM as white masks, the field coloured on top. One colour map per physics: magma-like for heat and density, fire for wind speed, blue to white for flooding, teal for tracer, cyan-blue streaks for cool air and fog, turquoise-yellow for vorticity.
4. The bottom of the slide is code: a block giving the domain (bounding box, shape, metres per pixel, downsample, timestep), then the masks built from real OSM tags (building, highway, water, park and grass), then the solver function names ("semi-Lagrangian backtrace, unconditionally stable"). The code is the method statement and is readable.
5. Handle bottom right.
- Honesty devices in every slide: the claim says simulation, a limit is stated where the model is a proxy, and one slide says outright that the barrier and dikes are why the flooding picture is not the real map.
- Provenance on the cover: Mapbox satellite z17 at 0.37 m per pixel, Mapbox terrain elevation, OpenStreetMap via OSMnx.

## Physics and method (from the slide code)
- 2D grid solvers in Python (numpy, scipy: map_coordinates). Masks rasterised from real OSM geometry. Advection by semi-Lagrangian backtrace (stable at any time step). Domain defined by a bounding box, pixel size, a simulation downsample (8) and a fixed time step (0.85). Fields: temperature, wind speed, scalar tracer, flood level from the real elevation model, crowd density diffused on the street network.
- The comments ask for the script and the datasets; none is given. So the physics is only half public, the look is the product.

## Cinematography and narrative read
- Camera: none. Every slide is a locked top-down map with the same window; change is the field evolving in time. The only perspective drawing is the cover section.
- Pacing by repetition: twelve slides with an identical template teach the viewer where to look, so each new slide costs almost no reading effort; the one varying element is the colour map and the one-line finding.
- Narrative: not a story with a human, a field guide. The argument is cumulative: the form decides where air, heat, water and people go. Each slide gives one verdict in a short sentence under the field.
- Reference plus result in one frame (satellite above, simulation below) is the core device: the viewer can check the model against the real place.

## Gaps against our work (new)
| Level | Abhinav | Ours |
|---|---|---|
| Method on the slide | domain, resolution, time step, mask sources and solver named in readable code | parameters sit in YAML and report.json, never on screen |
| Reference above result | real satellite beside the model | no real-world reference image in any frame |
| Labelled limits | "not measurement", "proxy, not X", why the picture is not the real map | caveats exist in text but are not on the frame |
| Real mask geometry | OSM rasterised into the solver | our sea and wind are not coupled to real coastline masks |
| One template repeated | 12 identical layouts | each of our shots is a new layout |
| Fields as the hero | the simulated field fills most of the frame | our graphics are lines and counters |
| Colour map per physics | named per field | one palette |
| Cover | section drawing plus field, 3-line title with accent | dashboard |
