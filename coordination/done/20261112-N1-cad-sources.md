from: Claude (integrator), on Arshad's decision of 2026-11-12
goal: Bring your uncommitted main-tree work into git so it can be reconciled with the repo, losing nothing.
  a) The CAD sprite sources behind docs/linkedin/06-cad-sprites/cad-sprites.png (and the sheet itself).
  b) offsim/motion/section.py v7-v10 (skia + CAD HLR drawing), which makes flaw 2.7 of docs/SYSTEM_PLAN.md stale.
  c) The tests.yml change you described (requirements-cad + novtk-restore step) if it differs from what is now on
     wip/cad-assets-heli (I added requirements-cad, apt retries and an import check there).
owns: whatever those files are; list them in the report.
must not touch: docs/RESUME.md, main, wip/cad-assets-heli (push only to your branch).
branch: agent/nordlys/N1-cad-sources, cut from origin/wip/cad-assets-heli.
exit test: `python -m pytest -q tests` on your branch (report counts and skips), plus a table in the report mapping
  each of your CAD sources to the repo asset it duplicates or extends (offsim/assets/cad/{marine,air,land}.py), with
  your recommendation per asset: keep repo / keep yours / merge, and why (QA numbers from `python -m offsim.assets.cad.qa`).
report: coordination/reports/N1.md. Include any disagreement with docs/SYSTEM_PLAN.md, with evidence.
taken: Nordlys 2026-11-12T01:05:20Z
