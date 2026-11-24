# Resume log

Hand-written state for the next session (human or Claude). `python -m offsim resume` prints this file's
**Next** section together with git state, open roadmap rows and open risks. Update it at the end of every
session and whenever work is interrupted. Newest first.

## 2026-11-22 — channel sync: N5a's refusal closed and the helideck rerun merged. 1022 pass, 38 skip (this box, CI-shaped).

Four branches new since the 2026-11-21 sync, all from Nordlys, all merged. The stale-tracking-ref incident
did not recur: the explicit refspec fetch brought in 20 branches the previous `git fetch origin main` form
had never recorded locally. `live/status` has no merge base with main by design (orphan status branch, three
status commits) and is not merged; `vm-pile` (22 commits) stays refused from 2026-11-14 and
`wip/cad-assets-heli` stays superseded.

**Merged (4):**
- **N5a (film tools), refusal of 2026-11-21 closed.** `git grep /home/hatch` on the branch now returns
  nothing, and `tools/molde_film_v2.py:55-66` resolves `FILM_DIR` from `OFFSIM_FILM_DIR` with a repo-relative
  default and reads nothing at import time, so the `FileNotFoundError` that aborted collection of the whole
  suite is gone. Three `skipif` guards skip the measured-input tests instead of erroring. No test on main was
  edited; the edited tests are the branch's own, added in 6ea5716 and fixed in 4fafe53.
- **helideck-rerun — N4.3 under sourced limits.** The headline survives sourcing: P90 unmet flights/week
  **1.0** at the routine end (IOGP App.6 Chart 2 p.142, 26.75 m/s / 5.5 m) and **0.0** at the regulatory end
  (SPA.HOFO.135 60 kt incl. gusts = 30.87 m/s, Hs 7.0 m), against 1.0 under the old assumed pair. Recomputed
  from the committed JSON rather than read off the report: A mean 0.237, max 10, 12/312 weeks over 1;
  B mean 0.064, max 5, 3/312. Infeasible-day share moves a lot — 11.0% (A) to 3.6% (B), 7.8% assumed in
  between — so **the share is not reportable as a point figure; only the P90 claim is unblocked**, and it must
  be reported as a range. `apply_limit_overrides()` defaults both overrides to `None`, so no sourced
  parameter, tolerance, `rules.py` number or golden frame changed; one test added, none edited.
  Nordlys's own question answered: the two JSON files (112 KB and 109 KB, per-winter and per-week summary
  rows, no point series) are report evidence, not data — `stress-test.json` and its `.plans.json` are already
  tracked in that directory, so this follows the precedent. The 4.3 MB point series correctly stayed local.
- **ampl-help** and **n8-note** — coordination files only (an AMPL hands-on task for desktop, a pointer to the
  N8 push-route note).

**Refused (0).** Nothing failed verification this sync.

**Decisions recorded (mine):**
- The sourced **pair A (26.75 m/s, 5.5 m) becomes the scenario default** in `build_scenario`, with the stale
  CAP 437 note at `offsim/solve/whelp.py:823` deleted. Pair A, not B: the conservative reading is the one
  that must hold, and it is the end where the lean fleet has no slack. Not done in this sync — it moves a
  scenario parameter and every gate reading it must be rerun. Task filed:
  `coordination/inbox/nordlys/20261122-helideck-default-limits.md`, branch `agent/nordlys/helideck-default`.
- **metocean-api stays unpinned for now**, against my own 2026-11-21 note to pin it. PyPI has up to 1.1.14,
  but nothing here ties a version to the committed 3.0E/60.6N series, and a guessed pin is a silent
  reproducibility gap. Asked Nordlys for `metocean_api.library_version()` from `venv-studio`; I pin that
  exact version next sync. `fetch.point_series` stays unreachable on a clean image until then.

**Environment note:** this box came up bare (no project packages). Rebuilt from the Dockerfile's requirement
set; `manimpango` needs `libpango1.0-dev` from apt before pip will build it. Worth adding to docs/MACHINE.md
if another fresh cloud session hits it.

**Blocked, and on whom:**
- **Arshad** — unchanged and now four syncs old: the A9 decision (one word); `BW_CLIENT_ID` /
  `BW_CLIENT_SECRET` as Actions secrets under exactly those names and `OFFSIM_MAILTO` as a repository
  *variable*; publishing `world-bergen-ncs.zip` as a release asset (no create-release or asset-upload tool
  exists here, so `fetch_world --pull` and the winter stress test on Actions stay blocked on a human).
  Audit 10's H2 merge gap still needs the human decision recorded there.
- **Nordlys** — the metocean-api version, and N8's workflow patch via the push route.
- **Claude desktop** — `coordination/reports/D1.md` still does not exist; local AMPL objectives against
  114 643 m and 9980.4986 remain unreported. Not blocking: AMPL runs on Actions.

## 2026-11-20 — channel sync: no actor pushed; J2 (harness hooks) arrived on main and is verified. 974 pass, 22 skip (this box, CI-shaped).

Scheduled integrator run, nobody watching. **No actor pushed anything, a third sync in a row.**
`coordination/inbox/claude/` empty; no new branch or commit from any of the three actors since the 11-18
sync: `agent/nordlys/vm-pile` still 8a08fa6 under the 11-14 refusal, `live/status` still 1ca411d (11-16, and
by design never carried on main), `wip/cad-assets-heli` still 41389a1 (spent). Nordlys silent seven days with
nine open inbox items; the laptop silent five days. Both scheduled workflows are Monday-only, so nothing was
due since 11-16. **Nothing merged here, nothing refused.**

**What is new on main came from Arshad, not an agent**: `cbac150` + merge `05f9251` on 11-19, J2 — five
harness hooks (`tools/hooks/gate.py`, `.claude/settings.json`, `docs/HOOKS.md`, `tests/test_hooks_gate.py`,
6 rows in `docs/GUARDS.md`, AGENTS.md item 5, THIRD_PARTY_NOTICES.md). It was pushed straight to main without
a sync, so this run reviewed it after the fact instead of before.

Verified here against the code, not the report: the range is **931 insertions, 0 deleted lines** across 8
files — no existing test edited, nothing under `out/` or `data/`, no `offsim/cinema/rules.py`, no golden
frame, no tolerance, no sourced value, no catalog status. Grepped every added line for a UUID literal: none,
so the hook's own patterns carry no secret. Probed `gate.py` on stdin: H1 blocks `Write` to
`out/demo/report.json`, H3 blocks `git add out/...`, H4 blocks a licence-shaped UUID and prints only "a
secret-shaped string is present" (no echo), and the legitimate twin `cat out/demo/report.json` passes
(exit 0). The report's claim of 984 pass / 12 skip is consistent with this box's 974 pass / 22 skip — the
10-test difference is manimpango (will not build here) and `metocean-api` (deliberately absent, per the
11-18 decision still being open). Full suite: **974 passed, 22 skipped, exit 0**.

**This run's finding, and it is a hole in the guard itself: H2 does not see `git merge`.** H2 keeps
`rules.py`, `visual_gate.py`, `tests/golden/*` and scenario `reported:`/tolerance lines on an
`agent/<who>/<id>` branch and makes a `git commit` that modifies one of them carry a `why:` line. Probed on
main: an *Edit* of `rules.py` is blocked (correctly), but `git merge --no-ff agent/... -m "Merge N3"` passes
with exit 0 and no `why:` required. That is exactly the integrator's path, and exactly where the `why:` lines
have in practice been written — the 11-14 N3 merge put four of them in the merge commit precisely because the
branch commits had empty bodies. So the one route by which a golden frame or a tolerance actually reaches
main is the one route H2 does not check. Not a refusal; recorded as audit 10 material. The matching nuisance:
the integrator on `main` or `wip/*` cannot touch those files at all without `OFFSIM_HOOKS_OFF=H2`, which the
J2 report already states.

**Notes written** (no reply was owed, so these are pointers, not tasks):
`coordination/inbox/nordlys/20261120-N10-hooks-live-on-main.md` — H2 and H5 are what will bite the
intervention-render work; `agent/nordlys/*` already satisfies H2's branch rule.
`coordination/inbox/desktop/20261120-D4-hooks-live-and-python3.md` — J2 states the hook fails **open** where
`python3` is not on PATH ("some Windows laptops"), i.e. H4 silently stops guarding on the one box that holds
the licence. One line asked back: `python3 --version` in the shell that session uses.

**For Arshad to decide.** Unchanged and still unanswered from 11-18, and it is the one thing this run cannot
settle: whether `metocean-api` goes into `tests.yml` and the Dockerfile, or whether the NORA3 point-series
backend is accepted in writing as CI-untested. With the marker added on 11-18 those nine end-to-end tests now
skip on every runner and in the image; skipping is not proving. Audit 9's tree-provenance decision (a species
default at a published bound: sourced, or assumption?) is also still open, and `pine`/`birch` still hold the
other convention three lines from `spruce`.

**Blocked, and on whom.** Arshad, unchanged for five runs: `BW_CLIENT_ID`, `BW_CLIENT_SECRET`,
`AMPL_LICENSE_UUID`, `OFFSIM_MAILTO` and the dispatch PAT. Nordlys: N4 then N5-N7, seven days silent. The
laptop: the two D1 objectives, five days silent, and now the `python3` check. The `runner` probe's
`libegl1 / skia / OCP` failure from 11-17 still stands unexamined. `tests/test_intake.py` still dirties
`tests/fixtures/intake/synthetic_paper.pdf` on every suite run; restored by hand again here — five sessions
have now paid for that one, and it is a two-line fix (write to `tmp_path`).

## 2026-11-18 — channel sync: nobody pushed; main's CI has been red since 11-12 and is now fixed. 913 pass, 22 skip (CI-shaped env).

Scheduled integrator run, nobody watching. **No actor pushed anything, again.** `coordination/inbox/claude/`
empty, no new report in `coordination/reports/`, no new branch or commit on origin since the 11-17 sync
commit itself: `live/status` still 1ca411d, `agent/nordlys/vm-pile` still 8a08fa6 under the 11-14 refusal,
`wip/cad-assets-heli` still 41389a1 (spent). Nordlys silent five days with six open inbox items; the laptop
silent three days. Both scheduled workflows are Monday-only (`live-check` 41 3 * * 1, `papers` 23 5 * * 1),
so nothing was due since 11-16 and nothing is missing. **Nothing merged, nothing refused.**

**The finding: the `tests` workflow has failed on main on every push since 2026-11-12 and no sync entry
noticed.** Runs 183-191 are all red, including run 191 on the 11-17 sync commit. Both jobs fail on exactly
the same two tests and nothing else — `tests/test_metocean_api.py::test_fetch_one_winter_reaches_load_years_in_the_expected_shape`
and `::test_fetch_world_dir_layout_is_what_a_scenario_points_at` — with all six units `failed` instead of `ok`.
Cause: those two end-to-end tests lack the `@needs_lib` marker that the other nine tests in the file carry.
`metocean-api` is deliberately optional (`requirements-weather.txt`: "optional, for fetch.point_series"),
`xarray`/`netCDF4` are not, so wherever xarray is installed and metocean-api is not — both CI jobs, and the
machine image — the two tests run without the library and every fetch fails. On this box the whole file was
skipping for want of xarray, which is why three sessions of "922 pass, 13 skip" never saw it.
**The 11-14 entry already names this exact defect** (line: "without the last one, `tests/test_metocean_api.py`
fails 2 tests that lack the `@needs_lib` marker every other test in that file carries") — but it was filed as
a note about this box's install recipe, the recipe then installed `metocean-api` to make local runs green,
and the marker was never added. Six days of red CI were paid for a one-line-each omission.

Reproduced here before fixing: with `xarray`+`netCDF4` installed and `metocean-api` absent, the two tests fail
with byte-for-byte the CI assertions. **Fixed** by adding `@needs_lib` to both (`why:` line in the commit).
Nothing else touched: no tolerance, no sourced value, no number in `cinema/rules.py`, no golden frame, no
assertion. Full suite in the CI-shaped environment (the 11-15 recipe, `manim` stripped, **without**
metocean-api): 935 collected, **913 passed, 22 skipped, exit 0** — which is the image-tests job's own
913 passed with its 20 skips plus these 2. **Confirmed after the push: run 192 is green in all three
jobs** (pytest, render-check, image-tests) — the first green `tests` run on main since 2026-11-12.

**For Arshad to decide, and it is the only thing this run cannot settle:** whether `metocean-api` goes into
the CI install step. With the marker, the nine end-to-end tests of the NORA3 point-series backend now skip on
every runner and in the machine image, so that backend is proven only on a box where someone installed the
optional library by hand. Either add `pip install metocean-api` to `tests.yml` and the Dockerfile (the tests
are offline, fixture-served, and take ~3 s), or accept in writing that the backend is CI-untested. The
marker is correct either way — without the library the test cannot pass — but skipping is not proving.

**Blocked, and on whom.** Arshad, unchanged for four runs: `BW_CLIENT_ID`, `BW_CLIENT_SECRET`,
`AMPL_LICENSE_UUID`, `OFFSIM_MAILTO` and the dispatch PAT. The laptop is still the only possible source of
the two D1 numbers. The `runner` probe's `libegl1 / skia / OCP` failure from 11-17 stands unexamined.
`tests/test_intake.py` still dirties `tests/fixtures/intake/synthetic_paper.pdf` on every suite run; restored
by hand again here. Four sessions have now paid for that one.

## 2026-11-17 — channel sync: the hosted runners woke up. papers feed merged, gap ranking corrected. main 922 pass, 13 skip (this box).

Scheduled integrator run, nobody watching. **No actor pushed anything.** Nothing in
`coordination/inbox/claude/`, no new report in `coordination/reports/`, nothing new from Nordlys (silent on
origin since 11-13) or the laptop (since 11-15), and no `agent/claude/*` branch has a commit off main. The
only new material on origin came from GitHub Actions: two scheduled workflows ran on **hosted runners on
Monday 2026-11-16, the first time any workflow has ever run there**. The 11-15 line "not one workflow has
ever run on a hosted runner" is now out of date; the dispatch PAT and the four secrets are still missing,
but the schedules themselves clearly work.

**Merged to main**: `papers/auto` (75bc4a7, the weekly feed) — the branch-side diff is confined to
`papers/{feed.jsonl,feed.status.json,tags.jsonl,gaps.yaml}`. `feed.jsonl` 712 -> 965 records, append-only
(the first 712 lines are byte-identical) and all 965 lines valid JSON. `tags.jsonl` regenerated here
**byte-identically**, so the tagger is sound. No code, test, tolerance, sourced value, `cinema/rules.py`
number or golden frame touched; nothing under `out/`; no secret-shaped credential (the UUID-shaped strings
in the diff are public `oa_url` record ids).

**Merged with one conflict resolved against the branch, and that is the finding of this run.**
`papers/gaps.yaml` conflicted, and the runner's copy is *wrong*: `papers.yml` installs only
`pyyaml pandas`, and `offsim/research/gaps.py` probes feasibility against what is importable, so the runner
recorded `engine replay does not cover VRPTW` and `solver none covers PDP` where a full-dependency box
records both as covered. `no-norway-vrptw-psv` scored 0.618 there against 0.927 here, and the gap ordering
changes with it. I committed the **locally regenerated** `gaps.yaml` (same code, same merged feed, same
`review.yaml`, full environment: 16 gaps, 16 open, 30 no-code cells withheld for want of availability
evidence) and kept the runner's feed, status and tags. Every `gaps.yaml` ever produced by that workflow
carries the same defect. Note in Nordlys's inbox (`20261117-N8-runners-live.md`); the fix belongs in the
workflow's install step, or in `gaps.py` refusing to score feasibility it could not probe — **not** in the
ranking numbers.

**Not merged.** `live/status` (1ca411d) is an orphan branch by design, history kept there — never merged,
but read: 15 of 17 probes answer. `ampl` and `barentswatch` are `skipped` for want of their secrets, and
the **`runner` probe fails: `libegl1 missing; skia not importable; OCP not importable`** — so on stock
`ubuntu-latest` the line-art renderer and the CAD solids are both absent and `film`/`render`/asset QA
cannot work there. Source health: `crossref` and `nva` ok, `openalex` partial (5 errors, one HTTP 400),
`arxiv` partial (2 errors, one 429), `overpass` HTTP 502 at probe time. `agent/nordlys/vm-pile` still
carries 22 commits under the 2026-11-14 refusal, grounds unchanged. `wip/cad-assets-heli` is still the one
content-identical Dockerfile commit — spent, deletable.

**Blocked, and on whom.** Arshad, unchanged and now in the way of three things: the four Actions
secrets/variables (`BW_CLIENT_ID`, `BW_CLIENT_SECRET`, `AMPL_LICENSE_UUID`, `OFFSIM_MAILTO`) and the
dispatch PAT. Without them `solve` still cannot produce an AMPL objective, so the laptop remains the only
possible source of the two D1 numbers (pointer left in `coordination/inbox/desktop/`), `barentswatch` stays
unprobed, and the OpenAlex feed keeps running on the anonymous pool — which is the likeliest reading of its
5 errors. Nordlys: six open inbox items, nothing pushed in four days.

Note for the next run of this box: the install recipe from 11-15 still holds (`manim` must be stripped out
of `requirements-motion.txt` or manimpango takes the whole pip run down). 935 collected, 922 pass, 13 skip.
The `tests/test_intake.py` fixture-timestamp bug is **still live** — every suite run dirties
`tests/fixtures/intake/synthetic_paper.pdf`; restored by hand again here, still not fixed. Three sessions
have now paid for it.

## 2026-11-15 — channel sync: D1 (the AMPL link) merged; its cross-check still owed. main 922 pass, 13 skip (this box).

Scheduled integrator run, nobody watching. One branch was new on origin: `agent/desktop/D1-ampl-link`
(10 commits, 965 insertions), the first work ever pushed by the laptop actor.

**Merged to main** (c2948a5), each claim checked against the code rather than the summary:
- `agent/desktop/D1-ampl-link` — `docs/LOCAL_LAB.md` (the Windows lab at `E:\OffsimLab`, build order L0-L6),
  `tools/ampl_studio/` (local Streamlit GUI over AMPL, model text screened the way the MCP server screens it),
  `offsim/solve/ampl_backend.py`, the `ampl-model` skill, and the MCP server widened by `AMPL_MCP_SOLVERS`
  (default stays `highs,cbc`; a test holds that). The one change worth the merge is in `ampl_adapter.py`:
  amplpy 0.18 puts the (i, j) pair in the `to_pandas()` index, so `_arcs_with_value` read arcs from the wrong
  place — a defect only a licensed box could find, and it is confined to the AMPL path.
  Secret scan of the whole diff: clean (no UUID-shaped or long hex/base64 string; `AMPL_LICENSE_UUID` as an
  env-var name and placeholder licence paths only). No test edited to pass (`tests/test_ampl.py` is +23/-0,
  the other two test files are new); no tolerance, sourced value, `cinema/rules.py` number or golden frame
  touched; nothing under `out/`, no data, no solver binary.

**Merged with a debt, recorded in `coordination/inbox/desktop/20261115-D1-still-owed.md`**: there is no
`coordination/reports/D1.md`, so the task's item 3 — the cross-check that matters — is unreported: AMPL
objective vs the Pyomo twin on the CVRP demo (114643.0 m, seeds 1 and 2) and whelp Florø vs 9980.4986.
`LOCAL_LAB.md` admits it ("NEXT: D1 report"). Merged anyway because nothing on main reads an AMPL objective
yet and refusing would have stranded the adapter fix on a branch; **until those two numbers exist,
`offsim/solve/ampl/{cvrp,vrptw,whelp}.mod` are still only text-checked as models.** Also owed: the 20
Windows test failures live only in `E:\OffsimLab\runs\L2_report.md`, a path nobody else can read, and
`tools/ampl_studio/` is a new tool absent from `catalog/tools.yaml` (concordance does not catch it today).

**Not merged, nothing refused new.** `agent/nordlys/vm-pile` still carries 22 unmerged commits under the
2026-11-14 refusal; grounds unchanged, note already in Nordlys's inbox, branch kept on origin.
`wip/cad-assets-heli` shows one commit off main (the Dockerfile core-deps line) but it is content-identical
to what main already has — the merge stages nothing, so the branch is spent and can be deleted.
No `agent/claude/*` branch has anything off main; V1 (the intervention shot) was already merged by the
later 11-14 session and its report reads straight, including the test it rewrote with the reason stated.

**Blocked, and on whom.** Arshad, unchanged and now in the way of D1 as well: the four Actions
secrets/variables (`BW_CLIENT_ID`, `BW_CLIENT_SECRET`, `AMPL_LICENSE_UUID`, `OFFSIM_MAILTO`) and the
dispatch PAT. Not one workflow has ever run on a hosted runner, so the `solve` workflow cannot confirm the
AMPL numbers either — which leaves the laptop as the only place they can come from, and makes the missing
D1 report the single thing holding up the AMPL link. Nordlys: silent on origin since 11-13 with five open
inbox items (N4, both N5s, N6, and desktop's new N7); a pointer went into his inbox saying N7's Linux check
is already spent here. Nobody has deleted the six merged branches; no branch-deletion tool in the connector.

Note for the next run of this box: a fresh container again had no deps. `requirements.txt` plus
motion/render/weather/engines/gis/physics/graphics/intake/cad `-c constraints.txt pytest-timeout mcp
metocean-api` installs clean **only with `manim` stripped out of `requirements-motion.txt`** — manimpango
needs pangocairo and aborts the whole pip run, taking every other package with it. 935 collected, 922 pass,
13 skip. The `tests/test_intake.py` fixture-timestamp bug from 11-14 is still live: every suite run dirties
`tests/fixtures/intake/synthetic_paper.pdf`. Restored by hand again here; still not fixed.

## 2026-11-14 — channel sync: N2, N3 and loop-proof merged; vm-pile refused. main 870 pass, 10 skip (this box).

Scheduled integrator run, nobody watching. Four Nordlys branches were waiting on origin, none of them seen by
the 11-13 session (which wrote N4 believing the N2/N3 tasks were still unclaimed — they were done on branches).

**Merged to main**, each verified here against the code rather than the summary:
- `agent/nordlys/N2-actions` — overpass probe retry, fetch `get()` retry, feed 429 backoff + degraded status
  file, `sea_polygons` vectorised, sodir keyword fix. Its one untested change was the `sea_polygons` rewrite,
  and the report said so: I ran the new code against the pre-N2 scan from git on 8 cases (sine split, closed
  ring, 400-segment zigzag, 5 random three-line coasts) — identical areas and filled bounds, 0 mismatches — and
  added `tests/test_osm.py::test_sea_polygons_votes_known_geometry`. Its three test files are pure additions
  (0 deleted lines). `live_status.json` NOT merged: `probes.py` reads `ROOT/live_status.json` as "the previous
  run", and `live-check.yml` commits it to `live/status` in a worktree so main does not carry one.
- `agent/nordlys/N3-assets-visual` — CAD QA re-run here on all nine film-eligible assets, all `(True, [])`, so
  the four `built -> qa-pass` statuses are measured. Four tests were edited; all four had encoded a defect that
  is now fixed (one by its own docstring's instruction), so all four stand, but the commits say `(why: in
  commit)` with an empty body, so the `why:` lines are in my merge commit instead. `tests/golden/section.png`
  was never pushed (binary) — the stale frame failed the branch's own new assertion here with `margins: ink
  fills 6.5%`; regenerated via `make_goldens.py`, passes; map/findings came back byte-identical.
- `agent/nordlys/loop-proof` — scenarios and storyboards only. `scenario.real.yaml` differs from the committed
  synth scenario in the weather block alone (verified by diff); `Flor\xF8` normalised to `Florø` to match.
  Its weather dir `data/worlds/bergen/metocean` exists only on the VM, so nobody else can run it yet.

**Refused**: `agent/nordlys/vm-pile` (22 commits, 9,678 insertions). Note written to
`coordination/inbox/nordlys/20261114-N5-vm-pile-refused.md` with the evidence and a three-way split. Grounds:
`offsim/papers/nafstad2021/scenario.yaml` sits at the path the pipeline reads with **zero** `src:` and **zero**
`assumption: true` keys (provenance as prose only) so it cannot pass gate 0 and occupies a filename a real
scenario needs; no task file and no report, so 810 lines of new tests and 3,058 of new tools arrive with no
stated result; committed run output and pdftotext (`reproduce_table3_log.json` 2,389 lines, `nafstad2021.txt`
1,014) — licence is fine (CC BY 4.0), the repo rule is not; and v1+v2 of both film tools. Branch kept on origin.

**Fixed here**, because N2 asked the integrator for it: `.github/workflows/papers.yml` now adds and commits
`papers/feed.status.json`, and the no-growth early exit checks the status file too — a week where every source
429s produced 0 new records and looked identical to a quiet week, which is exactly the record the file exists
to keep.

**Open risk, audit 9 in `docs/AUDIT.md`**: the spruce default moved 25 -> 30 m and `assumption -> src` because
30 m is the low end of a cited range, and that relabelling is what cleared the CAD QA gate. Merged — the number
is inside its citation and no solid was fitted — but `pine` and `birch` three lines away still follow the old
convention, so both conventions now live in one dict.

**Blocked, and on whom.** Arshad: the four Actions secrets/variables (`BW_CLIENT_ID`, `BW_CLIENT_SECRET`,
`AMPL_LICENSE_UUID`, `OFFSIM_MAILTO`) and the dispatch PAT — until one of them exists, no workflow can be
triggered from the VM and not one workflow has ever run on a hosted runner. Nordlys: N4 (the 24-winter
metocean fetch, then the hosted live-check, then the winter-infeasibility experiment), then N5. Nobody has
deleted the five merged branches; no branch-deletion tool exists in the connector.

Note for the next run of this box: a fresh cloud container has none of the deps. `requirements.txt` plus
graphics/cad/motion/physics/engines/gis/intake/weather/render, and `pip install metocean-api` — without the
last one, `tests/test_metocean_api.py` fails 2 tests that lack the `@needs_lib` marker every other test in
that file carries. 880 collected here, 870 pass, 10 environment skips (manimpango will not build here).
Small hygiene bug seen three times today: `tests/test_intake.py` regenerates the committed fixture
`tests/fixtures/intake/synthetic_paper.pdf` with a fresh CreationDate, so every suite run dirties the
working tree and the diff is pure timestamp. It should write to tmp_path, or the fixture should not be
in git. Restored by hand each time here; not fixed.

## 2026-11-13 — gap scout live, loop rehearsed, Nordlys invigilated. main 735 pass, 7 skip.
- W6 merged: gap noise killed (of 712 records only 4 state a code link, 0 state unavailability, so `no-code` is now
  dormant and the list fell 26 -> 8), gaps ranked support x novelty x feasibility x audience with every factor
  written into the entry, synonym dedupe, `offsim gap list | review | draft`, human verdicts in papers/review.yaml
  (the papers workflow now reads it from main so a regeneration cannot lose them).
  Top gap: no-norway-vrptw-psv 0.38. NO gap reaches feasibility 1: every top gap is a class no registered solver or
  engine covers. That is the real next build (modeller work), not more diagrams.
- Loop rehearsed end to end on synthetic weather: helicopter scenario passes gates 0-4, gate 4 reproduces the paper's
  Floro instance (9980.50 vs 9980), status marks it not reportable, and `offsim article` refuses it. See TESTLOG.
- Audit 6: Nordlys's N2/N3 re-verified by me. CAD QA pass for all nine is true; AW189 fixed from a new source (EASA
  drawing), not by bending a dim; he found a real bug in our own qa.py (radial rotor measure). Two gaps: his
  tests/golden/section.png is stale (test fails on a clean checkout until regenerated) and NO workflow has run on
  Actions - all his runs were local on his VM, so the runner path is still unproven.
- Never run on Actions: solve (AMPL), film, render, entur-realtime, live-check. papers and fetch-world: one run each.
Open decisions for Arshad: cap WIND-OM/WIND-INST feasibility at 2/3 (they dispatch themselves, no solver)? audience
weights and the filmable set {psv, heli, ferry} are editorial. Secrets still unset: BW_CLIENT_ID/SECRET, AMPL_LICENSE_UUID.

## 2026-11-12 (night) — the machine is alive on main: image built, CI green, article + visual gate in. 720 pass, 7 skip.
- `tests` CI on main: SUCCESS (the 30-min hang was the Stavanger whelp test; Nordlys marked it OFFSIM_SLOW).
- `machine-image`: SUCCESS. `ghcr.io/astheno-sphere/offsim:latest` exists (two build failures first: constraints.txt
  outside the build context, then no C/Fortran toolchain in python:3.12-slim; both logged in TESTLOG).
- New CI job `image-tests` runs the full suite inside that image on main: one statement for laptop, Codespace and CI.
- R1 merged: Nordlys's skia + CAD-HLR section film, mappanel, sheet.py, cad_sprites, ghia1982 harness; S-92 QA pass.
- W8 merged: `offsim article` (linkedin | thought | readme_entry) + `offsim publish`; every digit must trace to a
  report ref, refuses failed gates / synthetic weather / unlisted assumptions. Funnel stages article+publish are real.
- V1 merged: `offsim/cinema/visual_gate.py` (edges, strokes, palette, accent, contrast, type scale, margins, balance),
  golden frames, findings ported to skia, `story.check` refuses a storyboard whose frame fails and names the rule.
- The gate's first act was to refuse our own frames; both faults repaired in section.py (chart fills the mapless band;
  tick labels brightened to 7:1) and logged via `offsim learn`. Remaining soft findings: 8 text sizes (rule 17 allows
  3 + methods) and two labels over the streak field at ~2.9:1.
Open, in order: (1) Arshad: package access + Codespaces secrets -> create the Codespace (docs/MACHINE.md);
(2) Actions: live-check, papers, fetch-world bergen-ncs; set OFFSIM_MAILTO, AMPL_LICENSE_UUID, MUSE_AI_KEY;
(3) P2: W6 gap scout (18 of 26 gaps are no-code noise), W7 intake tables; (4) drafter: aw189 + platform_jacket QA;
(5) director: reduce the section's type scale to rule 17.

## 2026-11-12 (evening) — main is the machine: P1 + Nordlys's film path merged. 670 pass, 6 skip.
main = W0 + W1-W5 (conductor, doctor, concordance, live-check, agents+MCP) + R1 (Nordlys's N1 reconciled:
section.py skia+CAD-HLR, mappanel, sheet.py, cad_sprites, ghia1982 harness, linkedin reports; drawing.py merged;
S-92 now QA pass). CAD QA: 7 pass, aw189 fail, platform_jacket unmeasurable. Reports in coordination/reports/.
Open, in order:
  1. machine-image build (Dockerfile fixed after the first failure: constraints.txt was outside the build context).
     Then Arshad: package access + Codespaces secrets, create the Codespace (docs/MACHINE.md).
  2. CI on the hosted runner: the test step produced no output for 30 min; now `pytest -v -u` names the test live.
     Read the newest tests run on main; if it is one test, fix it, else move the test job inside the image.
  3. Arshad on Actions: live-check (first real probe of every host), papers (data branch + issue), fetch-world
     bergen-ncs; set variable OFFSIM_MAILTO and secrets AMPL_LICENSE_UUID / MUSE_AI_KEY (Actions + Codespaces).
  4. Then P2: W6 gap scout (18 of 26 gaps are no-code noise), W7 intake tables, W8 article generator.
  5. Drafter: aw189 + platform_jacket to QA pass. Director: the visual gate (density, type, contrast, goldens).

## 2026-11-12 (later) — the machine on GitHub: docs/MACHINE.md
.devcontainer/devcontainer.json (Codespaces), Dockerfile extended to every extra, machine-image.yml (GHCR image),
tools/machine_setup.sh (AMPL activation from a Codespaces secret). NOT built yet (no Docker here): Arshad runs
Actions -> machine-image, then creates a Codespace. Open: CI test job hangs on the runner (per-test timeout added,
read the durations in the last tests run); then move the test job into the image; merge PR #1.

## 2026-11-12 — W0 + P1 (W1-W5) built and merged into wip/cad-assets-heli. 607 pass, 5 skip locally.
W0: CI apt retries + requirements-cad, papers workflow -> data branch + issue, papers/auto data merged, coordination/
channel (task N1 for Nordlys: bring uncommitted CAD sources + section.py v7-v10 in on agent/nordlys/N1-cad-sources).
W1 tests/test_concordance.py (13 drift guards) + docs/GUARDS.md; gaps.py engine mapping fixed (HRP -> air).
W2 offsim/studio (funnel.yaml, ledger, conductor): `offsim status | next | advance | decide`.
W3 offsim/doctor (22 codes, playbooks, diagnose/repair, lessons): `offsim doctor | learn`; pipeline emits codes.
W4 offsim/live (17 probes) + live-check.yml: `offsim live`. Unverified live until its first Actions run.
W5 .claude/agents (9 roles), .mcp.json (ampl, Entur x2), AGENTS.md protocol.
Next: CI green on this branch -> merge PR #1 -> Arshad runs live-check + papers + fetch-world on Actions, sets
OFFSIM_MAILTO variable and AMPL_LICENSE_UUID secret -> Nordlys N1 -> then P2 (W6 gap scout, W7 intake, W8 article).

## 2026-11-11 (later) — system review, plan only: docs/SYSTEM_PLAN.md
Nothing built. Verdict, measured state, 12 named flaws, five additions (conductor, doctor, concordance, live-check,
agents+MCP), wave plan W0-W13 with models, owners, exit tests and firing commands, 6 decisions for Arshad.
Next: Arshad answers section 6, then "fire W0", then "fire W1 W2 W3 W4 W5".

## 2026-11-11 — HALTED branch continued (Nordlys, subagent): 5 failing tests fixed, suite green. Uncommitted, nothing pushed.

Key finding: the air engine was NOT broken — its `_rebook` is correct. Three of the five failures were wrong test
premises, and the other two were stale expectations. The solved Florø program is packed back-to-back (eq 11, no idle
slots): days 1-4 use slots 0-40/41, Monday's tail (slots 32-39) is the week's only slack, so a Tuesday storm
legitimately rebooks nothing (verified by trace: every candidate rejected on weather or occupancy). A 120 nm flight is
125 min = 9 fly slots and FITS a 4 h window (16 slots). psv passes QA now; whelp/air ship, so the registry test's sets
were stale.
Fixes (tests only; no solver/engine code changed):
  - tests/test_engines_core.py::test_registry_lists_every_tool_we_ship — expected engines + "air", solvers + "whelp".
  - tests/test_cad_drawing.py::test_story_check_gates_asset_shots — psv now asserts QA pass (`qa("psv") == (True, [])`);
    the "cannot be built" refusal path is now covered by a bad-params case instead.
  - tests/test_whelp.py::test_infeasible_when_a_flight_cannot_fit_any_window — window 4 h -> 2 h (8 slots < 9 fly slots).
  - tests/test_whelp.py::test_air_storm_day_cancels_and_rebooks — storm moved Tue -> Mon 07:00-12:00 (the week's only
    slack is Monday's tail): 2 cancelled, 1 rebooked (F4 -> Mon 15:00, +8 h), 1 unmet.
  - tests/test_whelp.py::test_air_rebooked_flights_respect_the_rules — storm Mon 00:00-10:00, same outcome; assertions kept strict.
  - NEW tests/test_whelp.py::test_air_tuesday_storm_has_no_slack_so_flights_go_unmet — pins the discovered fact
    (Tue storm: 3 cancelled, 0 rebooked, 3 unmet; engine reports unmet rather than inventing slack).
Suite (venv-studio, full runs): before 443 pass, 5 fail, 7 skip; after 449 pass, 0 fail, 7 skip (346 s). The HALTED
entry said 445/5/5; the 2-test difference is pass -> skip accounting, same 5 failures. The 7 skips are pre-existing
environment skips: 3 AMPL (amplpy absent), 2 SLOW (OFFSIM_SLOW unset), 1 Stavanger (solve 81 s > 60 s conditional
skip — the [12, 16] h assertion never runs on this VM), 1 vessel (deck.gl node_modules absent).
Follow-ons done: catalog entries whelp, air, cadquery, build123d, cadquery-ocp (159 tools, 54 pulled; `catalog_build.py
--check` passes); requirements-cad in CI (.github/workflows/tests.yml pytest job, + novtk-restore step — build123d pulls
cadquery-ocp-novtk, which breaks CadQuery VTK; 20-min timeout unchanged, watch the first CI run); registry.yaml
statuses from measured QA gates — qa-pass: psv, bus, train, person; built: platform_jacket, s92, aw189, tree, building.
Pipeline.py diff (WIP commit) reviewed — CORRECT: EXTRA_KEYS += wfppp, TOOL_PACKAGES += whelp (pyomo, highspy) + air (),
gate 1 WFPPP branch uses whelp.check_program, gate 2 compares planned_variable_cost (1e-6) and flights_planned_per_week
(exact) from the air engine KPIs; exercised by the passing pipeline tests. `pipeline.build_variant` exists, so the
experiment runner's default builder resolves.
Self-learning loops verified live (see docs/TESTLOG.md): paper intake on the fixture (3 pp, 15 evidence rows, draft
scenario); feed via Crossref (49 records for one query; OpenAlex 429s from this VM, degrades gracefully; arXiv 0 hits);
tag (49) -> gaps (2 gaps, support 12 each); experiment runner unit-verified (test_montecarlo, fake builder/weather) —
real end-to-end NOT run (that is the Gribkovskaia experiment, deliberately not started); `offsim resume` works.
Remains: s92/aw189 QA fail (dims off rotor ~21%, fuselage ~28-30%, width 341-366% — declared dims do not match the
built solid); platform_jacket/tree/building QA fail (missing dims, all assumed); 23 more Bergen winters to fetch; AMPL
install awaits approval + UUID via secure capture; sea_polygons + Sodir keyword bugs; CAD duplication with Nordlys's main-tree CAD sources (sprite sheet at docs/linkedin/06-cad-sprites/cad-sprites.png on
the VM, sources uncommitted): Arshad decided 2026-11-12 to bring the sources in via branch agent/nordlys/cad-sources. Quirk: test_intake.py's fixture regenerates the committed
synthetic_paper.pdf with fresh timestamps on every run (timestamp-only diff) — reverted here; it will show modified
again after any suite run.

## 2026-11-09 — HALTED by Arshad (weekly limit). Branch `wip/cad-assets-heli`, not merged to main.
State: 445 pass, 5 fail, 5 skip. Built: cad/drawing.py (HLR line classes, cache), qa.py (scale/detail gate),
registry.yaml, story `asset:` hook, land.py (bus, train, person, tree, building; 27 tests pass), marine.py (psv,
platform_jacket) + air.py (s92, aw189) (agent finished; report lost: re-check dims/sources in module docstrings),
solve/whelp.py + ampl/whelp.mod + engines/air_engine.py + paper scenarios (agent killed mid-work; pipeline.py edited).
Failing, fix first next session:
  - tests/test_engines_core.py::test_registry_lists_every_tool_we_ship (add "air" to expected engines)
  - tests/test_cad_drawing.py::test_story_check_gates_asset_shots
  - tests/test_whelp.py: infeasible-window, storm-day cancels/rebooks, rebooked-rules (air engine incomplete)
Then: catalog entries (cadquery, build123d, OCP; whelp, air), requirements-cad in CI, registry status -> built/qa-pass,
review the pipeline.py diff from the killed agent, merge to main. Goal reminder: build the machine, do not run studies.

## 2026-11-09 — CAD-grade assets + helicopter simulation (superseded by the HALTED entry above)
Contract written: `offsim/assets/cad/base.py` (exact solids, real scale, sourced dims; registry). requirements-cad.txt
(cadquery, build123d, OCP = OpenCASCADE, Apache-2.0). Agents (none commit): D drawing.py (HLR line classes) + qa.py +
registry.yaml + story `asset:` hook; M marine.py (psv, platform_jacket) + air.py (s92, aw189); L land.py (bus, train,
person, tree, building); H solve/whelp.py + ampl/whelp.mod + engines/air_engine.py + paper scenario (WFPPP).
If interrupted: git status; pytest; finish per docstrings; merge catalog/docs; commit.

## 2026-11-08 (night) — audit-5 fixes wired (done)
`offsim run` drives every registered solver/engine (pyvrp, pyomo, ampl; replay, road, openclsim, wombat, orbit, gtfs)
via scenario `solver:`/`engine:`; gates 0, 1, 1b_exact (`certify:`), 2, 3, 3e_ensemble (`ensemble:`), 4, 4b (AIS),
4c_entur. `offsim paper <pdf>` drafts with page evidence (pdfplumber). One CLI: paper, run, experiment, story, film,
world, layer, timetable, feed, tag, gaps, entur, tools, catalog, resume. Story shot types `section`, `findings`
(fan/paired/state_gantt), narration rules (`offsim/motion/narrate.py`, safe evaluator). Visual lib: skia Canvas
(`cinema/draw.py`), Inter font (OFL), `look.sun()`, terrain hillshade. Skills rewritten to the current system. 363 tests.
Open: section/map panels still PIL (switch to draw.py), ensemble report has quantiles only (no per-run tracks for
ghost_tracks), gate 4 compares the single run not ensemble medians, all external data still unverified live.

## 2026-11-08 (late) — Norway-wide worlds + road/bus + AIS gate (done)
Any place in Norway: `python -m offsim.worlds.fetch_world --place Molde --modes sea,road,bus` (Actions: fetch-world
inputs place/modes/radius_km) -> world spec v2 (`offsim/worlds/place.py`; v1 worlds still load as [sea]). Modes imply
layers: road/walk -> OSM roads, bus -> + Entur GTFS (`offsim/transit/gtfs.py` clip/trajectories), air -> helipads +
aerodromes. Engines `road` (networkx RoadGraph, oneway, maxspeed; pipeline `domain: land`) and `gtfs` (timetable replay,
bus/ferry/rail/tram agents). Gate 4b AIS calibration in `offsim run` (opt-in `validate: {ais: true}`). 265 tests pass.
Not yet live: stedsnavn API, Entur zip, real OSM roads. Installed for next phase: skia-python, datashader, xarray-spatial.
Added: user GeoJSON layers (`offsim/worlds/user_layers.py`), paper timetables -> GTFS (`offsim/transit/from_paper.py`),
Entur realtime client + gate 4c (`offsim/transit/entur.py`, `observed.py`, workflow `entur-realtime`), data-intake rules
(ARCHITECTURE), transit rules in research-scout/paper-extract skills, level-up rules 9-17 (STYLE_REFERENCE).

## 2026-11-08 — engine layer built (done)
Architecture (`docs/ARCHITECTURE.md`, 7 layers + import rule enforced by `tests/test_architecture.py`), definitions
(`docs/ENGINES.md`), interfaces (`offsim/engines/base.py`). Built and tested here: solvers pyvrp, pyomo; engines replay,
openclsim (weather windows), wombat, orbit; `offsim/montecarlo` (CRN ensemble, bootstrap CI); `offsim/weather/years.py`;
`offsim/research` (experiment spec + runner, tags, gaps); `offsim/feed` (OpenAlex/Crossref/arXiv/NVA, fixtures);
`offsim/traffic` (AIS port calls, calibration, gate 4b spec; BarentsWatch client); `offsim/worlds/osm.py`; fetch-world
`--osm/--ais`. Wired, not run: AMPL (`solve.yml`, `tools/ampl_mcp`), `papers.yml`. Specs only: `offsim/emissions`,
`offsim/motion/findings.py`. 205 tests pass, 2 skip (AMPL solve needs a licence).
Not yet live-checked: NORA3 variable names, NVA fields, BarentsWatch endpoints, pyrosm on a real pbf, every AMPL call.

## 2026-11-07 — four visual layers built and integrated

Done: camera (per-frame track, centripetal spline, van Wijk fly, follow/orbit, `shot_plan` inspector — demo passes);
depth (datum-first merge, pydelatin mesh, baked hillshade, isobaths, EMODnet/Geonorge fetchers); weather (NORA3/NorKyst
subsetting, seeded particle trails, Hs texture, PSV weather effects); vessel (display-only fillets, speed ramps, DP
jitter, bob, Kelvin wake, heli profile; toy max offset 12 m, demo 16 m). Renderer: Python precomputes camera track,
display tracks, terrain and weather blocks; line art and wakes drawn at fixed screen size (cartographic symbols);
horizon haze hides the data edge. One command: `python -m offsim film <storyboard> [--muse unlisted]`; Actions
workflow `film`; Dockerfile; muse.ai upload (hosting only).

Interrupted and recovered: the depth builder hit the sub-agent rate limit; its uncommitted work in
/home/claude/wt/depth was finished by hand (terrain.js, requirements, catalog) and merged.

## Next
000. Next build: skia-python stroke renderer + open font (rule 12, 17), terrain hillshade under maps (rule 13).
00. You: Actions -> fetch-world with place `Molde`, modes `sea,road,bus` -> first live run of stedsnavn + OSM + Entur;
    then `--pull molde` here and run the road template / a GTFS replay on real data; fix what the log shows.
0. Wire engines into `offsim run`: scenario `engine:` / `ensemble:` blocks, `pipeline.build_variant` for
   `research/run_experiment.py`, WIND-OM / WIND-INST past gate 0; wind adapters onto `world.legs`.
0b. You: secret `AMPL_LICENSE_UUID` → Actions **solve** on the demo; allow Actions to create PRs (Settings → Actions) for **papers**.
0c. Build `offsim/emissions` and `offsim/motion/findings.py` to their specs.
0d. Section physics BUILT (display grade): `offsim/physics` fluid2d (consistent projection), ocean (JONSWAP), streaks;
    tests/test_physics.py; draft still `tools/section_still.py` (PSV in a gale, plume over the cargo deck; inputs assumed).
    DONE 5 s film `tools/section_film.py` (moving sea, heave/pitch, detailed line art `cinema/vessel_lineart.py`,
    narration chosen from measured values) + map panel (`motion/mappanel.py`: OSM coast, gated demo route, eased zoom).
    Next: NORA3 Hs/wind on the map (fetch-world --metocean), real PSV class geometry, cavity validation (Ghia 1982)
    before any section number is reported, real vessel geometry and exhaust data.
1. Actions → **fetch-world** `oslofjord` with `depth: true` and `metocean_start` (e.g. 2024-01-10T00:00, 48 h) — first live
   run of the DEM and MET Norway fetchers; fix whatever the log shows; flip `live_checked` in weather/fetch.py.
2. `python -m offsim.worlds.depth --world oslofjord --tier fjord` on the pulled DEM → terrain in the demo map shot.
3. Add `weather: {wind: nora3_wind, wave: nora3_wave, particles: 2500}` to the demo map shot; dry-run; review a still.
4. Actions → **film** on the demo storyboard (add secret `MUSE_AI_KEY` to upload) → review the MP4.
5. First paper (PSV supply routing) via `paper-extract` → `offsim run`.

## 2026-11-21 — AMPL on Actions; four solvers agree (integrator)

- Cloud session can dispatch workflows and read logs (not download artifacts).
- `solve` on a hosted runner, AMPL + HiGHS with the academic licence: demo-oslofjord-supply optimal, 114.64 km,
  2 routes, equal to PyVRP, Pyomo and OR-Tools. `test_ampl.py` 20 passed, 14 skipped (no `mcp` in the job; fixed).
- `live-check` on a hosted runner: 15 ok / 1 fail / 1 skip. AMPL ok. BarentsWatch skipped (BW_CLIENT_ID not seen
  by the job), OFFSIM_MAILTO not set as a variable, runner probe needed libEGL (fixed).
- Broadcast written to the nordlys, desktop and claude inboxes.

## 2026-11-21 — channel sync: eight of Nordlys's nine branches merged, N5a refused (integrator)

Suite on merged main: **938 passed, 27 skipped, 0 failed**. This workspace was fresh, so main did not
even collect until `pyvrp`, `shapely`, `geopandas`, `ortools`, `skia-python`, `cadquery` and `openclsim`
were installed from the requirements files — the 11 "failures" on first run were all missing `openclsim`.

**Merged (8):**
- **A9** — Nordlys's reply to Audit 9: `src` means the VALUE is stated in the source, not merely inside a
  cited interval. Doc-only; `land.py` untouched. Spruce height 30 m keeps `src` (cited floor), crown 8.4 m
  does not survive the rule (interior to 7.6–13.7). **Awaits Arshad's one-word decision** — the rule +
  crown relabel, or one of Fable's two options.
- **N4** — winter stress test: the weekly program replayed against 24 DJF winters, 1560 operating days,
  121 infeasible (7.8%), P90 unmet flights/week = 1.0, **exactly at the pre-registered ≤1 boundary**.
  Limits (wind 25 m/s, Hs 6.0 m) and B positions carried as `limits_assumption`/`positions_assumption`
  true — compliant, unsourced, not reportable as sourced. Paper variant under Table 4 windows
  [16,14,10,10] is **infeasible** at stage 2: a model discrepancy, same family as Audit 8's fleet
  disagreement, not a driver bug and not to be widened away. 4.3 MB point series stays local (no release
  tool here).
- **N5** — intervention film: the invented headline ("THE S-92 MAKES ITS OWN WIND") replaced by one
  derived from the measurement ("DECK WIND FALLS AS THE S-92 LEAVES", Arshad's call, recorded in the
  report), plus the missing `shot_intervention` render path so `offsim film` stops raising KeyError. Test
  added, none edited. Film rendered on the VM, DRAFT/synthetic, not posted.
- **N5b** — Nafstad 2021: extraction renamed off `scenario.yaml` to `extraction.yaml` (Fable's refusal
  reason 1 closed — nothing now occupies the pipeline path with zero `src:` keys). Table 3 verdict
  **PARTIAL**: trip-based 0.00% on all six, criterion 4 fails because her compact model solved where the
  paper's did not.
- **N5c** — four loose docs home under `docs/` (AMPL-MCP, HANDOVER-2026-11-11, UPGRADE-REPORT,
  architecture-diagram.html), each with its staleness mapped rather than edited out.
- **N6, N7/N8/N9** — four reference-study exams. Reports only; no frame of any reference video committed.
- **N11** — audited Grasshopper data-trees note, teaching the audited pass, not the first one.

**Refused (1): N5a (film tools).** Seven hardcoded `/home/hatch/...` paths are committed, and
`tests/test_molde_film_v2.py:21` reads one at **import** time, so pytest aborts collection of the whole
suite — `FileNotFoundError: /home/hatch/workspace/docs/linkedin/05-molde/v2/measure.json`, 1 error, 5
skipped, nothing else runs. Its own "880 passed" is true only on the VM, with the untracked symlink and
copied `report.json` the report itself says must not land. Note with the file:line table in
`coordination/inbox/nordlys/`. Nothing else about the branch is disputed; the `metadata_uuid` in
`offsim/worlds/bergen.yaml` is a public Geonorge dataset id, matching three world files already on main.

**Blocked, and on whom:**
- **Arshad** — the A9 decision (above, one word). `BW_CLIENT_ID` / `BW_CLIENT_SECRET` as Actions secrets
  under exactly those names, `OFFSIM_MAILTO` as a repository *variable*. Publishing
  `world-bergen-ncs.zip` as a release asset: no create-release or asset-upload tool exists here, so
  `fetch_world --pull` and the winter stress test on Actions stay blocked on a human.
- **Nordlys** — N5a paths.
- **Claude desktop** — `coordination/reports/D1.md` still does not exist; local AMPL objectives against
  114 643 m and 9980.4986 remain unreported. No longer blocking anything, since AMPL runs on Actions.
- **Integrator (me), next sync** — pin `metocean-api` (nowhere in `requirements.txt`/`constraints.txt`,
  only a comment in `requirements-weather.txt:6`, so `fetch.point_series` is unreachable on a clean
  image). N4's claim that two metocean tests are unguarded is stale: 21 passed, 10 skipped, 0 failed.
- Audit 10's H2 merge gap is untouched and still needs the human decision recorded there: these eight
  merges went in with no `why:` enforcement on the merge path, as Audit 10 predicted.

- 2026-11-21 (2): BarentsWatch mapped and live; J1 merged (gate 1 time windows, gate 4 fleet, 25 seeded faults); N4.3 winter result awaits sourced helideck limits. Broadcast 2 in all inboxes.

- 2026-11-25: OPEN (claude): branch `agent/claude/visual-engine` (sea `offsim/physics/jonswap.py` + Blender bridge `offsim/blender/`, `tools/blender_shot.py`) is unmerged; full suite not yet run on it; `offsim/physics/ocean.py` and `jonswap.py` duplicate each other (reconcile before merge); the Blender shot is not wired into the film; city-roads catalog candidate pending. NEW: `docs/VISUAL_DEFINITIONS.md` (schema first, each rule cites a verified source) fed by a verified-source scout; no definition enters the repo unverified (Abhinav's repo held none of Nordlys's hex tokens).
