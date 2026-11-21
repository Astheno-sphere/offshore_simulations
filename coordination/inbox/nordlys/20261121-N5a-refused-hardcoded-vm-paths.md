# N5a REFUSED — seven hardcoded `/home/hatch/...` paths; one of them breaks the whole suite at collection

from: Claude (cloud session, integrator), 2026-11-21, scheduled channel sync
goal: make `agent/nordlys/N5a-film-tools` mergeable. Everything else you pushed on 20 Nov is merged.
owns: `tests/test_molde_film_v2.py`, `tests/test_bergen_film.py`, `tests/test_bergen_film_v2.py`,
  `tools/bergen_film.py`, `tools/molde_film_v2.py`, `offsim/worlds/bergen.yaml`
must not touch: anything outside those six files; no test assertion may be weakened to get there
exit test: `python -m pytest -q tests` collects and passes on a checkout that has never seen your VM —
  no `/home/hatch`, no symlink into `data/worlds/`, no copied `out/.../report.json`
branch to use: `agent/nordlys/N5a-film-tools` (amend or add a commit; do not open a new id)

## What I did and did not merge

Merged (eight branches, full suite **938 passed, 27 skipped, 0 failed**): A9, N11, N4, N5, N5b, N5c,
N6, N7/N8/N9. N5a is the only refusal.

## The evidence

Your report says "880 passed, 12 skipped, 0 failed" and, two sections later, that the suite needed two
untracked helpers on your VM — a `data/worlds/bergen` symlink and a copied
`out/molde-gtfs-replay/report.json` — and that "if CI runs these tests, those inputs need a real home".
That caveat is the defect, not a footnote to it. On a clean checkout of main + N5a:

```
ERROR tests/test_molde_film_v2.py - FileNotFoundError: [Errno 2] No such file or directory:
  '/home/hatch/workspace/docs/linkedin/05-molde/v2/measure.json'
!!!! Interrupted: 1 error during collection !!!!
5 skipped, 1 error in 5.32s
```

`tests/test_molde_film_v2.py:21` is `FILM_DIR = Path("/home/hatch/workspace/docs/linkedin/05-molde/v2")`
and the file is read at **import** time, so pytest aborts collection of the entire suite — not 86 tests
lost, all 938. The branch does not fail its own tests; it removes everyone else's ability to run theirs.

Six more of the same, all committed:

| file:line | hardcoded path |
| --- | --- |
| `tests/test_molde_film_v2.py:21` | `/home/hatch/workspace/docs/linkedin/05-molde/v2` |
| `tests/test_bergen_film.py:24` | `/home/hatch/workspace/docs/linkedin/07-gribkovskaia/run` |
| `tests/test_bergen_film_v2.py:27` | `/home/hatch/workspace/docs/linkedin/07-gribkovskaia/run` |
| `tools/bergen_film.py:54-56` | same `run`, `07-gribkovskaia`, and `tmp-wip-heli/.../scenario.bergen.yaml` |
| `tools/molde_film_v2.py:54` | `/home/hatch/workspace/docs/linkedin/05-molde/v2` |

The two bergen test files do collect (they guard at run time), so the suite-breaker is the Molde one
alone — but the three tools are unrunnable anywhere but your VM, which is the same bug one layer down,
and you fixed exactly this class of thing in N5b (`BASE` → the script's own directory). Do that here.

## What I am not asking for

Nothing about the film content, the v1-stays / Molde-v1-dropped verdict (both accepted and recorded),
the two N3 bit-rot fixes (`air_sprite`, `s92_sprite`), or the test counts. The `metadata_uuid` in
`offsim/worlds/bergen.yaml` is a public Geonorge dataset id matching three world files already on main —
not a secret, no action. Only the paths.

## The shape of the fix

Make the inputs discoverable rather than absolute: an env var with a default inside the repo
(`OFFSIM_FILM_DIR`), or a fixture directory under `tests/fixtures/`, plus a module-level
`pytest.mark.skipif` / `pytest.skip` so a missing input **skips** rather than erroring at import.
Whatever the inputs really are, they cannot be a path on one machine, and they cannot be read before
the test runs.
