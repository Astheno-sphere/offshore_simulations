---
name: visual-director
description: Motion grammar for offshore_simulations - turns a validated run or experiment into a storyboard of shots (equation, map, section, findings, card) in the house palette, with every number a report ref and every number shown with its uncertainty. Renders drafts and stills here and 1080p finals on GitHub Actions. Use when a corrector-approved result needs a video, still or LinkedIn format.
---

# visual-director

Layer L5. Grade and craft rules: `docs/STYLE_REFERENCE.md`. Spec and numbers: `docs/VISUAL_SPEC.md`, `offsim/cinema/rules.py`.
Palette and voice: `offsim/style.json`, `offsim/cinema/look.py`. A storyboard that breaks a spec rule is wrong even if it renders.

## Gate before any frame
Only a run that passed gates 0-4 (and 1b, 3e, 4b, 4c where the scenario set them) gets a storyboard. An experiment
needs its ensemble ok and `reportable` True. `offsim story --dry-run` refuses otherwise.

## Shot types (`offsim/papers/<id>/storyboard.yaml`)
| Shot | Engine | Use | Numbers from |
|---|---|---|---|
| `equation` | Manim (LaTeX) | the paper's objective and key constraint, written on | the paper (no measured value) |
| `map` | deck.gl | the run on the real coast; `camera.keys` eased fly-in, push, pull-back | trajectory contract, real layers only |
| `section` | section film (`offsim.physics`, `tools/section_film.py`) | vertical sea section: hull or platform, wind and waves at the hour's Hs | `report:` refs |
| `findings` | story pipeline | distribution: fan chart or P10-P90 band, decision status | `report["ensemble"]` refs only |
| `card` | HyperFrames + GSAP (`offsim/motion/templates/kpi_card`) | KPI count-ups and the status word | `report:` refs with `scale`, `decimals`, `unit`. Literals refused |

## Checklist (STYLE_REFERENCE craft rules 1-8, level-up rules 9-17)
- [ ] Density: every quay, stop and building drawn, not sampled (rules 1, 9).
- [ ] Three line weights (outline 2.4, structure 1.3, detail 0.8 px), drawn at 2x and downscaled (rules 2, 3).
- [ ] Tonal fills: each part a different value of the ground colour (rule 4).
- [ ] Two scales on one clock: the mechanism and its consequence (rule 10).
- [ ] Light follows the simulated clock when the scenario has one (rule 11).
- [ ] One question in the headline; the deck line states what the run found that a reader would not guess (rules 6, 15).
- [ ] Narration chosen from measurements, two-pass (rule 5; `sim-narrator`).
- [ ] Real vs simulated ghost tracks side by side where AIS (4b) or Entur (4c) exists (rule 16).
- [ ] One accent colour; one geometric sans; no more than three type sizes plus the methods line (rule 17).
- [ ] Methods line generated from `report.provenance`: dataset, engine, ensemble size, gates passed, assumptions.
- [ ] Credit line: DOI, data sources with licences, and "SYNTHETIC" when any geometry or demand is invented.

## Real layers only
The map draws only layers in the world package: OSM coast, sea lanes, quays, roads, NORA3 fields. A missing layer
stays missing, never drawn from memory. Until NORA3 is pulled, map wind is uniform and labelled as such.

## Uncertainty with every number
Each number on screen shows its uncertainty: P10-P90 or the 95% CI from `report["ensemble"]`, or "single run, no
ensemble". Assumptions are printed on screen. Sim-derived frames carry the "SIMULATED" tag.

## Agents and sites
`style.json` `agent_mode`: `sprite` (default), `model`, `lineart`, `dot` (debug). Sites: `site_mode` `model` or `lineart`
for kinds that have one, columns otherwise. Models are exaggerated on purpose: say "not to scale" on screen when it matters.
Vessels route on sea lanes (`offsim.worlds.sealanes`), never straight over land. Assets warm up before capture.

## Render
- Drafts and stills: `render.py --check` (headless, writes nothing) and `python -m offsim story <storyboard> --dry-run`.
  Verify before any video. Do not render images during audits unless asked.
- Finals (1080p, Blender): `render` and `film` workflows on Actions; download from the release.
- Story without `--dry-run` renders shots and crossfades them with ffmpeg: a heavy run, so it goes to Actions or
  runs on demand.
