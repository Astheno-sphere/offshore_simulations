"""Metocean: data in (Actions), weather in the simulation, weather on screen. Spec: docs/VISUAL_SPEC.md §3.

Data (all fetched by the fetch-world workflow, never here; see catalog layer `metocean`):
  NORA3 hindcast   wind (3 km, hourly) + waves (Hs, Tp, dir)   MET Norway, CC BY 4.0, OPeNDAP, no login
  NorKyst v3 800 m surface currents u/v (+15 depth levels)     MET Norway, CC BY 4.0, from 2024-01-01
  WAM 800 m        coastal wave forecast                        MET Norway (licence: check)
  fallbacks        ERA5 (CDS token), Copernicus Marine (login) as Actions secrets
Package per world: data/worlds/<world>/metocean/<YYYYMMDD-HH>_<hours>h_<dataset>.nc (bbox, hourly, regular lon/lat, int16 scaled).
Code: fetch.py (subset), visual.py (particles, Hs texture, arrows, weather_scene), effects.py (PSV bands applied to a plan).
"""
