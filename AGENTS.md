# AGENTS.md — for any coding agent (Claude, Qwen, Codex, ...)

Read `CLAUDE.md` first: its rules apply to every agent, not only Claude. Then:

1. **Where things are**: `docs/ARCHITECTURE.md` (layers, interfaces, what runs where), `docs/ENGINES.md` (each solver /
   engine: mapping, assumptions, limits), `docs/STYLE_REFERENCE.md` (the visual grade and the craft rules learned),
   `docs/RESUME.md` (current state + next steps; `python -m offsim resume`), `catalog/tools.yaml` (tools, with evidence).
2. **Reproduce the current film**: `bash tools/reproduce_film.sh` (versions pinned in `constraints.txt`; data pulled
   from the GitHub release, never committed). The film is deterministic: same inputs, same frames.
3. **Hard rules** (the ones agents break most):
   - Never render, narrate or post a result that failed a gate (`offsim run` gates 0-4; films refuse failed runs).
   - Every scenario value has a source (page/table) or `assumption: true`; assumptions are printed on screen.
   - On-screen sentences are chosen from measured values (two-pass: measure, then render). Never hand-write a claim.
   - New solver/engine = implement `offsim/engines/base.py` (`Solver` / `Engine`), raise `Unsupported` instead of
     approximating, add tests, add a catalog entry with `evidence:` paths, add its section to `docs/ENGINES.md`.
   - Visual work follows `docs/STYLE_REFERENCE.md` (detail density, three line weights, 2x supersampling, tonal fills,
     real layers only on maps, cinema rate caps in `offsim/cinema/rules.py`).
   - Run `python -m pytest -q tests` before every commit; update `docs/RESUME.md` and `docs/TESTLOG.md`.
4. **Environment limits**: data hosts (Kartverket, Kystverket, MET Norway, Overpass, AMPL downloads) are reached only by
   the GitHub Actions workflows (`fetch-world`, `solve`, `papers`); results come back as releases/artifacts.
