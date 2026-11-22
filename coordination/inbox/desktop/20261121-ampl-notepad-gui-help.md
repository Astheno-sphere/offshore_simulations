# AMPL hands-on help: Notepad / GUI, saving .dat files

from: Nordlys (VM)
to: Claude desktop (the session with the laptop)
date: 2026-11-21
taken: —
owns: nothing in the repo — hands-on AMPL help on Arshad's laptop
must not touch: repo code, main, the licence file contents, secrets
branch: agent/nordlys/ampl-help (this task file only)
exit test: a `.dat` Arshad edited himself, saved correctly, and solved in Studio

## Ask

Arshad wants hands-on help on the laptop: set up his AMPL so he can open
models in Notepad or a GUI, edit them, and save `.dat` files — then run one
end to end. Sit with him on the machine; this is a guided session, not a
background job. His machine, his clicks.

## What exists already

- Lab at `E:\OffsimLab`, amplpy 0.18.0, licence file active to 2027-11-13.
- `tools/ampl_studio/` on main: a Streamlit GUI for AMPL. Launch:
  `python -m pip install --user -r requirements-studio.txt` then
  `python -m streamlit run tools/ampl_studio/app.py`. AMPL is found through
  `AMPL_DIR`, else `ampl` on PATH, else `C:\Users\arshad\AMPL`.
- Models in `offsim/solve/ampl/`: `cvrp.mod`, `vrptw.mod`, `whelp.mod`.
- Demo scenario: `offsim/papers/demo-oslofjord-supply/scenario.yaml` —
  D1 already solved this on Actions (114.64 km = PyVRP = Pyomo = OR-Tools),
  so there is a known-good answer to check the local run against.
- Studio defaults: model roots `E:\OffsimLab\models`, `offsim/solve/ampl`,
  `offsim/papers`; solve logs go to `E:\OffsimLab\runs`.

## Session shape

1. Get AMPL Studio running and load `whelp.mod` (or the demo model) with
   its data. Solve once, show the result and the CSV download.
2. Notepad: open a `.dat` file, change one number, and save it as `.dat`
   again. The trap: Notepad defaults to "Save as type: Text Documents",
   which appends `.txt`. Use "Save as type: All files" and type the full
   `.dat` name. Confirm the saved file has no `.txt` suffix and re-solves.
3. If he prefers a GUI editor over Notepad, offer VS Code or Notepad++
   (plain-text, no formatting) — his pick, and note which one he chose.
4. End state: a `.dat` he edited himself, saved correctly, and solved in
   Studio, with the answer matching the known D1 number where it applies.

## Notes

- Do not print or paste the licence file contents anywhere.
- If AMPL is not found by Studio, check `AMPL_DIR` first, then PATH, then
  `C:\Users\arshad\AMPL` (README order).
- Report back in this inbox (or a short note to nordlys) what he chose
  (Notepad vs GUI editor) and whether the edited `.dat` solved — that is
  the exit test for this task.
