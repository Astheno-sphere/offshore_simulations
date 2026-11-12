# offshore_simulations — instructions for Claude

Other agents: see AGENTS.md (same rules, plus a one-command reproduction of the current film).

Start at `skills/offsim-foundations/SKILL.md` (router + conventions). The flow is fixed:
paper → scenario.yaml → `python -m offsim run` (gates 0–4 plus the opt-in 1b, 3e, 4b, 4c; report.json) → storyboard.yaml →
`python -m offsim story --dry-run` → `python -m offsim story` → post. See `docs/AUDIT.md` for open risks.

- Never render, narrate or post a result that has not passed `offsim.contract.validate` and the
  corrector's paper comparison. `build_scene` enforces the first; you enforce the second.
- Every scenario parameter needs a source (page/table) or `assumption: true`.
- Before writing a new component, search the catalog: `python tools/catalog_build.py --find <x>`.
  New tools go in `catalog/tools.yaml` via the `tool-scout` skill; then rebuild `docs/TOOLS.md`.
- The Claude workspace cannot reach Kartverket, Kystverket, Sodir, Overpass or tile servers. Data comes
  in via the `fetch-world` workflow → GitHub release → `python -m offsim.worlds.fetch_world --pull <world>`.
- Agents render per `style.json` `agent_mode`: sprite | model | lineart (`dot` is debug). `lineart` is CAD-style
  linework; `offsim/assets/cad` builds parametric CAD solids with hidden-line drawings, and an asset shot needs its
  QA pass (`python -m offsim.assets.cad.qa <name>`). Vessels route on sea lanes (`offsim.worlds.sealanes`), never
  straight across land; report quay snaps.
- AMPL never runs in the Claude workspace (binary download blocked). It runs on GitHub Actions (`solve` workflow,
  secret `AMPL_LICENSE_UUID`) or on the laptop (`tools/ampl_mcp`); the Pyomo twin runs here.
- Numbers on screen come only from `report:` refs. Verify renders with `render.py --check` / `story --dry-run`
  before producing video; do not render images during audits unless asked.
- Visual work follows `docs/VISUAL_SPEC.md`; numbers are in `offsim/cinema/rules.py`. Interfaces that raise
  NotImplementedError are specs: build them to their docstring, then add the tool's evidence to the catalog.
- Catalog status `tested`/`wired`/`installed` needs `evidence:` paths (checked); manual runs go in `docs/TESTLOG.md`.
- Heavy renders (1080p, Blender) go to the `render` workflow; drafts and stills are fine here.
- GPL tools run as separate processes, never imported. Data is never committed (see `.gitignore`).
- PyVRP 0.14: use `offsim/solve/pyvrp_adapter.py`; it handles `is_client()` and client index offsets.
- Commits are authored by Arshad Akhtar Abbasia with Claude as co-author.
- Run `python -m pytest -q tests` before every commit. `tests/test_concordance.py` fails when docs, skills, catalog and
  code drift apart (commands, engine tables, requirements, stubs, cited paths, gate list); `docs/GUARDS.md` names the
  test or gate that enforces each hard rule in AGENTS.md. Fix the drift, never the assertion.
