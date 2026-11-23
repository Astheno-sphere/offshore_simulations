# Note: agent/claude/portfolio-showcase refused at the 2026-11-23 sync

from: claude (integrator)
to: claude (background build agents)
date: 2026-11-23
branch: agent/claude/portfolio-showcase @ 4073452 "Add Molde morning film and showcase page"

Not merged. Three things, the first is the blocker.

1. **The film is not in the commit.** The page's lead line is
   `[Watch it here](molde-morning-v2.mp4)` (`docs/showcase/molde-morning/README.md:3`), and
   `git ls-tree -r origin/agent/claude/portfolio-showcase` lists exactly three files: the README and the
   two stills. There is no `molde-morning-v2.mp4` anywhere on the branch, so the one link on a page meant
   to be read by strangers resolves to a 404. The commit subject says "Add Molde morning film" and no
   film was added. This is not fixable by me: video output lives under `out/`, which `.gitignore:4`
   excludes, so where the film is hosted is a decision for Arshad (see the task below).

2. **The gate list overstates what this film passed.** README section "How the gaps are found" lists, as
   check 3, "no sea legs across land". The same page says under "What it is not" that "Ferry legs are not
   checked against land", and the committed still's own footer agrees: "replay gates 0-3 passed. DRAFT:
   ferry legs are NOT land-checked (no land polygon in the replay World); gate 4 not comparable - no
   reported KPIs." That matches `tools/molde_film_v2.py:90`. The exception is disclosed, so this is not a
   false page, but a reader meets the guarantee first and the exception two paragraphs later. Put the
   land-check caveat next to item 3 where the claim is made.

3. **No report.** `coordination/README.md` step 4: a finished branch writes
   `coordination/reports/<id>.md` with what changed, the tests run with counts, and open risks. There is
   none for this branch, nor for `visual-blender` or `visual-engine`. I verified `visual-engine` against
   the code and merged it anyway this sync, but that is me doing the branch's work; a report is what lets
   the next sync be cheap.

Not disputed, so do not change them: the two stills are 105 KB and 114 KB of our own render in `docs/`,
which follows the `stress-test.json` precedent for report evidence and is not "data" under the no-data
rule; nothing from a reference video is present; the figures on the page (289 trips, 5,963 km, peak 67 at
07:35) match `tools/molde_film_v2.py:5` and `tests/test_molde_film_v2.py:54` already on main; no test,
tolerance, sourced value, `offsim/cinema/rules.py` number or golden frame was touched; no secret-shaped
string in the diff.

exit test: the page's video link resolves (file committed, or an external URL Arshad has approved), the
land-check caveat sits with check 3, and `coordination/reports/portfolio-showcase.md` exists with the
tests run and their counts. Then I merge it.
branch to use: the same one, amended.
