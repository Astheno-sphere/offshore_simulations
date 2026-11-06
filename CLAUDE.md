# offshore_simulations — instructions for Claude

Start at `skills/offsim-foundations/SKILL.md` (router + conventions). The flow is fixed:
paper → scenario.yaml → solve → replay → contract + corrector gates → scene → render → post.

- Never render, narrate or post a result that has not passed `offsim.contract.validate` and the
  corrector's paper comparison. `build_scene` enforces the first; you enforce the second.
- Every scenario parameter needs a source (page/table) or `assumption: true`.
- Before writing a new component, search the catalog: `python tools/catalog_build.py --find <x>`.
  New tools go in `catalog/tools.yaml` via the `tool-scout` skill; then rebuild `docs/TOOLS.md`.
- The Claude workspace cannot reach Kartverket, Kystverket, Sodir, Overpass or tile servers. Data comes
  in via the `fetch-world` workflow → GitHub release → `python -m offsim.worlds.fetch_world --pull <world>`.
- Agents render as characters (`style.json` agent_mode: sprite | model). Vessels route on sea lanes
  (`offsim.worlds.sealanes`), never straight across land; report quay snaps.
- Heavy renders (1080p, Blender) go to the `render` workflow; drafts and stills are fine here.
- GPL tools run as separate processes, never imported. Data is never committed (see `.gitignore`).
- PyVRP 0.14: use `offsim/solve/pyvrp_adapter.py`; it handles `is_client()` and client index offsets.
- Commits are authored by Arshad Akhtar Abbasia with Claude as co-author.
- Run `python -m pytest -q tests` before every commit.
