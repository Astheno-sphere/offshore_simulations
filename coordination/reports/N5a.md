# N5a — the two film tools

Branch: `agent/nordlys/N5a-film-tools`, from origin/main `7ae6be0`.
Task: `coordination/inbox/nordlys/20261114-N5-vm-pile-refused.md` (Fable's refusal of
`agent/nordlys/vm-pile`; N5a is the first of three splits, in order N5a, N5b, N5c).
Worktree: `~/workspace/tmp-n5a`. Date: 2026-11-15.

## What lands

| file | what it is |
| --- | --- |
| `tools/bergen_film.py` (1,150 lines) | Bergen film v1: the 30 s landscape film builder (hook, plan, findings). The base v2 is a delta on. |
| `tools/bergen_film_v2.py` (755 lines) | Bergen film v2: same film, vertical 1080×1350, reworked hook and captions. Imports v1 as `B` (`line 66: import bergen_film as B`). |
| `tools/molde_film_v2.py` (692 lines) | Molde film v2: standalone rewrite, 30 s vertical. Does not import any v1. |
| `tests/test_bergen_film.py` (157 lines) | v1 tests. |
| `tests/test_bergen_film_v2.py` (311 lines) | v2 tests. |
| `tests/test_molde_film_v2.py` (86 lines) | Molde v2 tests. |
| `offsim/worlds/bergen.yaml` (25 lines) | Bergen world descriptor the film tools read. |

## The v1 verdict (the task's escape clause)

Fable asked to drop v1 unless v2 cannot do without it. The answer splits by film:

- **Bergen v1 STAYS.** `bergen_film_v2.py` line 66 does `import bergen_film as B` and
  calls into it throughout; v2 is a delta on v1, not a replacement. Deleting v1 would
  break v2. Its tests stay with it.
- **Molde v1 DROPPED.** `molde_film_v2.py` is a standalone rewrite; it imports no v1
  module. `tools/molde_film.py` and `tests/test_molde_film.py` are not on this branch
  and stay on the refused `vm-pile` branch until Arshad says it can go.

## Two N3 bit-rot fixes in bergen_film_v2.py

N3 split the CAD sprite fills/details into `offsim/assets/cad/air_sprite.py`, and v2
still pointed at the old names. Both fixes are in this commit, with their `why:` lines.

1. Line 192: `from offsim.assets.cad import air as _A` →
   `from offsim.assets.cad import air_sprite as _A`.
   why: N3 moved `SPRITE_FILLS` and `s92_sprite_details` into `air_sprite.py`; `air.py`
   holds neither. (My first attempt, `_A.SHEET_FILLS`, was wrong — `SHEET_FILLS` lives
   in `offsim/assets/cad/sheet.py`. The repo pattern, confirmed in
   `tests/test_cad_sprites.py`, is `build("s92_sprite")` + `air_sprite as air`.)
2. `asset = build("s92")` → `asset = build("s92_sprite")`.
   why: the sprite part names the film uses (`fin`, `stabilizer`, …) live on the
   `s92_sprite` asset; `build("s92")` parts are fuselage/gear/glazing/mast/nacelles/
   rotor/sponsons/tail_rotor/tailboom/tailfin, so the film died with `KeyError: 'fin'`
   from `offsim/assets/cad/sheet.py:397` (`asset.parts[part]`).

## Test results

Three new test files, run alone first: **25 passed, 0 failed** (67.75 s).

Full suite, before and after (the task asked for both):

- Before: main `7ae6be0` — **855 passed, 12 skipped, 0 failed** (738.90 s, measured
  2026-11-15 on the N6 branch, which is main plus a report only).
- After: this branch — **880 passed, 12 skipped, 0 failed in 856.14 s (14:16)**,
  145 warnings. 880 − 855 = 25, exactly the three new files. No test edited.
  Log: `/tmp/n5a-suite.log` on this VM.

## Notes for the integrator

- **No binaries.** Everything on this branch is text; nothing to regenerate.
- **Fixture side effect, handled.** The suite regenerates
  `tests/fixtures/intake/synthetic_paper.pdf` in place (only its CreationDate changes;
  the fixture writes into `tests/fixtures/intake/`, not a tmp dir — same note as in the
  N6 report). It was restored with `git checkout` before committing, so it is not in
  this commit.
- **Test wiring, not committed.** The worktree holds two untracked/ignored helpers the
  suite needed here and which must not land: a symlink `data/worlds/bergen` → the main
  tree's data dir (for `land.geojson`), and a copied `out/molde-gtfs-replay/report.json`
  from the main tree. If CI runs these tests, those inputs need a real home.
- **Not in N5a (follow-up).** `tools/bergen_film_v3.py` — the tool that built the
  delivered Irina film v3 — sits uncommitted in the main tree and is not part of this
  branch, as specified. It is the next film-tools follow-up, not part of the vm-pile
  split.

## Exit

Report written. Next: push (expected to hit the same credential block as N4/N6 —
bundle fallback), then N5b (Nafstad) and N5c (loose docs), in that order.
