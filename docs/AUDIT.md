# Framework audit

Running record of weaknesses found in the flow and what was done. Newest first.

## 2026-11-06 — audit 2 (flow, motion, vectors)

| # | Finding | Risk | Fix |
|---|---|---|---|
| 1 | `scenario.yaml` had a template but nothing consumed it; each stage was run by hand | steps skipped, gates forgotten | `python -m offsim run <scenario>`: gates 0–4 in order, stops at the first failure, writes `report.json` (`offsim/pipeline.py`) |
| 2 | No provenance on results | a number cannot be traced to code, data or inputs | `report.json.provenance`: scenario SHA-256, git commit + dirty flag, package versions, world manifest, run time |
| 3 | Gate 0 did not exist: unsourced parameters and unsupported problem classes went straight to the solver | silent approximation of a paper | gate 0 refuses values without `src`/`assumption` and classes outside `SUPPORTED` |
| 4 | Status word ("reproduced") was the narrator's judgement | over-claiming | computed by the runner: assumptions present → at best "re-run under assumptions" |
| 5 | Motion graphics had no structure: one map clip, static camera | no story, no reuse | `storyboard.yaml` + `python -m offsim story`: Manim equation → deck.gl map with eased camera keyframes → HyperFrames KPI card → ffmpeg crossfades |
| 6 | Numbers on screen could be typed by hand | narration drifting from results | card values must be `report:` refs; literals are refused; storyboard refused if gates 0–3 failed |
| 7 | Renderer was only checked by looking at images | slow, subjective, not in CI | `render.py --check` draws headlessly and reports layer health + page errors, writes nothing; CI job `render-check` |
| 8 | Agents drawn as sprites/models only; no CAD-style vectors | not the engineering look wanted | `lineart` mode: feature edges of our glTF models (trimesh) as metric plan-view lines rotated by heading (`offsim/assets/lineart/`) |
| 9 | Models too coarse for line art | sparse drawings | PSV/ferry detail pass (cargo, crane, pipes, railings, lifeboats, windows): 210 / 132 plan lines |
| 10 | HyperFrames template fetched GSAP from a CDN | fails offline and here | GSAP vendored from npm into each card project |

## 2026-11-06 — audit 1 (first real world)

| # | Finding | Fix |
|---|---|---|
| 1 | Straight legs crossed real land (contract caught it) | `offsim/worlds/sealanes.py`, solver distances on the same lanes |
| 2 | `--pull` pointed at the old repo and used blocked GraphQL | REST API, correct repo |
| 3 | Sprites/models missed in frames (async load) | warm-up before capture |

## Open risks (next audits)

- Quay positions are approximate: Moss snaps ~585 m, S6 ~203 m. Need real quay coordinates (Kystverket port data) and a finer local grid near ports.
- Runner supports CVRP/VRPTW only. Helicopter papers (synchronisation, multi-trip, PDP) need an OR-Tools CP-SAT or MIP path before gate 0 can pass.
- Weather is absent: no metocean windows (catalog: metocean-api / NORA3) — offshore operations results will be optimistic.
- Speed in replay is constant; no acceleration, DP time or port manoeuvring (catalog: fossen-pvs).
- GSAP licence is not OSI; if the brand becomes a company product, re-check GreenSock's standard licence terms.
- Video assembly (`story` without `--dry-run`) is implemented but its full render runs only on demand (by design: no images in audits).
