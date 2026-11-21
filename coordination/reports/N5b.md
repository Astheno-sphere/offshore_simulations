# N5b — Nafstad: the reproduction lands, the extraction leaves `scenario.yaml`

Branch: `agent/nordlys/N5b-nafstad` (from `origin/main` `ae41e5f`).
Worktree: `~/workspace/tmp-n5b`. Task file:
`coordination/inbox/nordlys/20261114-N5-vm-pile-refused.md` (shared with N5a/N5c;
moves to `coordination/done/` only when all three are written — N5a done, N5c to
come).

## What the refusal asked for

Fable refused `agent/nordlys/vm-pile` for four reasons; the Nafstad one was
reason 1: `offsim/papers/nafstad2021/scenario.yaml` sits at the exact path the
pipeline reads, carries **zero** `src:` keys and **zero** `assumption: true`
keys in 205 lines, and writes its provenance as prose. Gate 0 reads keys, not
prose — so the file either stops at gate 0 or, worse, occupies the filename a
real Nafstad scenario needs. His instruction: rename the extraction off
`scenario.yaml`, take `reproduction_plan.md`, `reproduction_report.md`,
`notes.md` and `reproduce_table3.py`, no paper text, no run log on git, and
say in the report whether Table 3 reproduced and what the gap was.

## What landed

`offsim/papers/nafstad2021/` — five files, all taken verbatim from
`origin/agent/nordlys/vm-pile` except where noted:

- `reproduction_plan.md` (373 lines) — Tables 3–8 transcribed exactly as
  printed, the first-reproduction target (Table 3, 10 orders), the four
  pass criteria, and the nine things that are NOT available for exact
  reproduction (no instance files, no seed, no optimal objective values, no
  installation identities, no helicopter parameters, no cost units, no
  numeric L / T^L / T^H / T^C, no sampling rules, no per-instance trip
  counts).
- `reproduction_report.md` (241 lines) — the 2026-11-06 run, verdict PARTIAL
  (below). A record of that run, not rewritten: its §6 paths still point at
  `~/workspace/papers/nafstad2021/`, where the run happened. The new home is
  stated here, in this report.
- `notes.md` (152 lines) — reading notes: the problem, the compact model,
  the trip-based model, DCG, §5.1 instance generation, headline results.
- `reproduce_table3.py` (903 lines) — the test script, deterministic, fixed
  seed 20261106. Two surgical changes, both in this branch, both recorded:
  (1) `BASE` was a hardcoded local path
  (`/home/hatch/workspace/papers/nafstad2021`); it is now the script's own
  directory, so the script runs from the repo checkout. (2) It reads
  `extraction.yaml` instead of `scenario.yaml` — the load at the top of
  `main()` is a parse check only (`yaml.safe_load`); every value lives in
  the script itself, so the rename changes nothing the script computes.
- `extraction.yaml` (205 lines) — the former `scenario.yaml`, renamed. Same
  content, byte for byte: paper metadata, problem, orders, constraints,
  vehicles, heliports, installations (count 10, names/coordinates NOT in the
  paper), §5.1 generation rules, solver setup, results summary, availability,
  flags and assumptions. It is YAML, so it keeps the `.yaml` suffix — calling
  it `extraction.md` would have been dishonest formatting. No file named
  `scenario.yaml` exists anywhere under `offsim/papers/nafstad2021/` now, so
  `offsim run nafstad2021` will not mistake this for a scenario.

## What did NOT land (and where it lives)

- `nafstad2021.txt` (1,013 lines) — pdftotext of the CC BY 4.0 PDF. Data is
  not committed; the intake flow takes a PDF from outside git on purpose.
  Lives at `~/workspace/papers/nafstad2021/nafstad2021.txt` (local only).
- `reproduce_table3_log.json` (2,388 lines) — run output. Regenerable by
  running the script; the 2026-11-06 original lives at
  `~/workspace/papers/nafstad2021/reproduce_table3_log.json` (local only).
  The verification re-run below wrote a fresh copy into the worktree and it
  was deleted before committing.

## Did Table 3 reproduce? No — PARTIAL, and the gap is criterion 4

The paper's Table 3, 10 orders (the target): compact gaps **100.00% / 0.00% /
25.20%**, times **3600 / 619 / 3600 s**; trip-based all **0.00%** gap, totals
**0.33 / 0.10 / 0.32 s**. The plan's PASS rule has four criteria; three pass,
one fails:

| # | Criterion | Result |
|---|-----------|--------|
| 1 | Trip-based 0.00% gap on all three 10-order instances (and all three 8-order smoke instances) | **PASS** — 0.00% on all 6 |
| 2 | Every solution passes independent validity checks | **PASS** — 28–36/36 checks on every instance; recomputed objective equals solver objective exactly on all 6 |
| 3 | Trip-generation counts plausible against the paper's scale (Table 4 smallest interval, 17–19 orders: 845–18,115 trips) | **PASS** — 95–216 trips at 8–10 orders, growing with n |
| 4 | Compact model shows the paper's failure pattern at 10 orders (≥1 instance unsolved at the cap) | **FAIL** — my compact model solved all three 10-order instances to optimality (11.7 / 59.3 / 12.7 s in the original run) |

Per the plan's rule, **this is not a pass**. The trip-based side reproduces
the paper's headline result cleanly; the compact side does not. The most
likely reasons, in the report's order: (1) my compact model is structurally
simpler than the paper's — one route per helicopter per day, no refuel-node
sequencing, no multi-trip chaining, at most one node per installation per
helicopter — which adds routing/sequencing binaries and weakens the LP bound
in the paper's model; (2) solver generation gap (HiGHS 1.15.1 vs Gurobi
9.0.0), unlikely to matter at this size; (3) my generated instances are
probably easier — windows spread over the whole 06:00–22:00 day,
installations spanning the whole shelf, so presence contention is low, while
the paper's 2018-record instances likely had tighter clustering. Chasing
criterion 4 means the full compact model with refuel nodes + multi-trip
chaining and/or harder instances — follow-up work, not this branch. Do not
scale to 12+ orders until the 10-order compact question is settled.

Honest limits, carried over from the report: instances were GENERATED per §5.1
rules, not the paper's instances (none exist) — the comparison is structural,
never per-instance exact; no optimal objective values are printed anywhere in
Tables 3–8, so the optimum itself cannot be checked numerically; the
trip-based model as implemented is a restriction of the paper's (trips
time-fixed at latest feasible departure, 5-min steps; the paper re-times trips
inside the B&B), so 0.00% proves optimality WITHIN this model; compact runs
used a 300 s cap, not the paper's 3600 s; no Gurobi, HiGHS instead.

## Verification re-run (this branch, 2026-11-15)

After the landing + the two-line script fix, I re-ran the script from the
worktree (`python offsim/papers/nafstad2021/reproduce_table3.py all`,
log `~/workspace/n5b-rerun.log`, 130 s wall, exit 0). Every number that
matters is **identical** to the 2026-11-06 run — same trips (95/216/103 at 8
orders; 131/146/135 at 10), same trip-based objectives (792.98 / 770.86 /
819.71; 1062.07 / 908.67 / 1114.35), same 0.00% gaps, same validation counts
(32/28/28; 36/28/32), same compact objectives (972.22 / 824.70 / 1034.94;
1247.51 / 1319.21 / 1140.31). Only wall times differ slightly (compact
8.89 / 3.52 / 21.47 s at 8 orders; 11.99 / 63.08 / 14.73 s at 10 — vs 8.59 /
3.41 / 20.37 and 11.70 / 59.30 / 12.66 originally). The verdict is therefore
the same PARTIAL, now verified in place from the repo checkout rather than
relayed from a 9-day-old log.

## Suite

Full suite on `ae41e5f` + this branch: **883 passed, 12 skipped, 0 failed in
752.92 s** (log `~/workspace/n5b-suite.log`). Identical to the suite on main
at `ae41e5f` — this branch adds no tests and breaks nothing, as expected for
a files-plus-report landing. One restart killed the first suite run at ~8%;
libEGL was wiped by the same restart and restored from the cached debs before
the re-run. The `synthetic_paper.pdf` intake fixture was dirtied by the suite
run (CreationDate only) and restored before committing.

## Exit

N5b done: the Nafstad reproduction is on git with the extraction renamed off
the pipeline path, the script verified running from its new home, and the
Table 3 verdict stated plainly as PARTIAL with the gap named. N5c (loose
docs) follows. Nothing from this work is posted.
