---
name: tool-scout
description: Find, vet and record open-source tools, datasets, MCP servers and Claude skills for offshore and maritime logistics simulation and visualisation (routing solvers, AIS, metocean, offshore wind models, emissions, 3D/2.5D rendering, video). Searches the catalog first, then GitHub and the web, checks licence and activity, and adds vetted entries to catalog/tools.yaml. Use when asked "is there a tool for X", "what are we missing", or before writing something that may already exist.
---

# tool-scout

## 1. Search what we already have
```bash
python tools/catalog_build.py --find <word>     # e.g. ais, weather, helicopter, wind, glTF
python tools/catalog_build.py --now             # what the current paper needs
```

## 2. Search outward (only if the catalog has nothing that fits)
```bash
gh search repos "<terms>" --sort stars --limit 10 --json fullName,stargazersCount,license,updatedAt,description
gh search repos --topic <topic> --sort stars --limit 10 --json fullName,stargazersCount,license,description
```
Useful topics: `maritime`, `ais`, `vehicle-routing-problem`, `offshore-wind`, `ship-routing`,
`discrete-event-simulation`, `deckgl`, `openstreetmap-data`. Multi-word queries often return nothing:
fall back to topics, PyPI, and web search for papers' code links (Zenodo, journal "code availability").
Also look in the sister repo's bank: `computational_Logistics/knowledge-bank/catalog/` (1,800+ skills).

## 3. Vet before adding
- **Licence**: read LICENSE. MIT/BSD/Apache can be imported. GPL/AGPL: separate process only.
  Unknown: record `licence: check`.
- **Alive**: last push within ~2 years, or a stable published release.
- **Fit**: name the layer and the step it serves; if it duplicates a tested tool, mark `watch`.
- **Runs where**: try `pip install` here; data hosts are often blocked here (then `runs: actions`).

## 4. Record
Add one entry to `catalog/tools.yaml` (fields: id, name, url, layer, licence, status, runs, priority,
role), then `python tools/catalog_build.py` and `python -m pytest -q tests/test_repo.py`.
Promote `candidate` → `tested` only after it ran here with a result written in `role`.

## Rules
- Never vendor third-party code into `offsim/`; depend on it or call it.
- Never store star counts (they go stale); note maintenance in `role` if it matters.
- Prefer one good tool per job over three half-used ones.
