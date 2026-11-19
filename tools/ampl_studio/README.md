# AMPL Studio

A local Streamlit GUI for AMPL. AMPL runs on the laptop only (local install through amplpy); the Claude workspace
cannot download it, and CI runs it through the `solve` workflow on GitHub Actions. Nothing here reads or prints the
licence file.

## Run

```
python -m pip install --user -r requirements-studio.txt
python -m streamlit run tools/ampl_studio/app.py
```

AMPL is found through `AMPL_DIR`, else `ampl` on PATH, else `C:\Users\arshad\AMPL`.

## Use

1. Model: pick a `.mod` (optionally with a `.dat`) or a `.run` from the allowed roots, or paste model text.
   Default roots: `E:\OffsimLab\models`, `offsim/solve/ampl`, `offsim/papers`. Override with `AMPL_STUDIO_ROOTS`
   (os.pathsep-separated).
2. Solver: the dropdown lists solver executables found next to the AMPL binary, grouped LP/MIP, NLP/MINLP, CP.
3. Options: `outlev=1 timelim=60` becomes `option <solver>_options '...'`.
4. Solve shows solve_result, objectives, time, full solver output and every variable (indexed variables flattened),
   with CSV download. Compare solvers solves the same model with each ticked solver and tabulates the result.
5. Each solve writes `<timestamp>_<model>_<solver>.log` to `E:\OffsimLab\runs` if it exists, else `./runs`.

## Safety

Same ideas as `tools/ampl_mcp/server.py`: files only under allowed roots; AMPL text is screened for `shell`, `cd`,
`remove`, `include`, `commands`, `write`, `read`, `!` and redirection. The screen is a guard, not a sandbox: load only
models you trust. `.run` scripts may use `model` and `data` statements whose files must sit under the allowed roots.

## Limits

No wall-clock kill: use solver options (`timelim`, `seconds`) to bound a run. Reported time includes solver start-up.
Pasted text cannot use `model`; pick the file instead. Compare mode runs solvers one after another.

Tests: `python -m pytest -q tests/test_ampl_studio.py`.
