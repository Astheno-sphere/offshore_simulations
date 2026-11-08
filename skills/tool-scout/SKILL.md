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

`offsim tools` lists the catalog from the CLI; the search above is the same data.

## 3. Vet before adding
- **Licence**: read LICENSE. MIT/BSD/Apache can be imported. GPL/AGPL: separate process only.
  Unknown: record `licence: check`.
- **Alive**: last push within ~2 years, or a stable published release.
- **Fit**: name the layer and the step it serves; if it duplicates a tested tool, mark `watch`.
- **Runs where**: try `pip install` here; data hosts are blocked here (then `runs: actions`, or `laptop`).

## 4. Record
Add one entry to `catalog/tools.yaml` (fields: id, name, url, layer, licence, status, runs, priority, role).
Then `python tools/catalog_build.py` (rebuilds `docs/TOOLS.md`) and `python -m pytest -q tests/test_repo.py`.

## Evidence rule (checked by the tests)
- `tested`, `wired` and `installed` need `evidence:` paths; the test checks that each path exists.
- A manual run is recorded in `docs/TESTLOG.md` and cited from `evidence:`.
- `installed` means the tool is in a manifest (`requirements*.txt`); otherwise it is `candidate`.
- A spec that raises `NotImplementedError` is built to its docstring first, then its tool gets evidence here.
- Promote `candidate` to `tested` only after it ran here, with the result written in `role`.

## Rules
- Never vendor third-party code into `offsim/`; depend on it or call it.
- Never store star counts (they go stale); note maintenance in `role` if it matters.
- Prefer one good tool per job over three half-used ones.
