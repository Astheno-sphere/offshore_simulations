---
name: pocket-diorama
description: Isometric hand-drawn "Pocket City" diorama of a real Norwegian quay, harbour or base as a visual for a validated run. Use when a film or post needs a place-of-the-result establishing visual, a scene card, or a still of where the simulation happens. Wraps third_party/pocket-city (MIT, April Zhu).
---

# pocket-diorama (offsim wrapper)

Upstream skill: `third_party/pocket-city/SKILL.md` (untouched; read it for the pipeline). This file only adds our rules.
Pipeline: OSM json -> `plot.py` -> `prep.py` -> research -> `city.json` -> `landmarks.js` -> `build.py` -> `render.mjs`.

## Rules that differ from upstream

- The Claude workspace cannot reach Overpass or Nominatim. `fetch_osm.py` runs on Actions or the laptop; bring `osm.json`
  in via a release (the fetch-world route), never by retrying here. Use `--lat --lon` (Kartverket stedsnavn gives them).
- A diorama is a scene, not a result. Nothing on screen may carry a number unless it is a `report:` ref of a run that passed
  `offsim.contract.validate` and the corrector. Field notes state only what a named source says; the rest is listed as
  illustrative. Vehicles, boats and people in the page are illustrative until driven by a trajectory (see Next).
- Drive side: `--drive right` for Norway. Seasons: use the DJF winter regime where the film is a winter-weather argument.
- Style stays upstream's (flat colour, fine ink). It is a second visual language beside our CAD-linework one; do not mix
  them in one shot. Per `docs/VISUAL_GRAMMAR.md` a film still argues by one form; the diorama is the establishing shot only.
- No em dashes in any text we add to `city.json`.
- Heavy: Chrome renders only for checks here (`render.mjs`, `CHROME=/usr/bin/google-chrome`); 1080p video goes to the
  `render` workflow. Never commit `osm.json`, `scene.json` or built pages (data and outputs).

## Evidence

Toolchain proven offline: bundled Portofino example builds byte-identically and renders headless (docs/TESTLOG.md).
Not yet run on a Norwegian place: needs `osm.json` from Actions.

## Next (not built)

1. Workflow `pocket-osm` (dispatch: lat, lon, size) running `fetch_osm.py` and publishing `osm.json` to a release.
2. Seam for truth: replace `city.json` boat/vehicle motion with replayed trajectory from `report.json` so the moving
   things are the simulation, not decoration. Needs a read of `third_party/pocket-city/assets/kit/city.js` first.
