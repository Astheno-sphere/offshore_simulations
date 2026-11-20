<!-- Notes prepared by Nordlys from Abhinav Bhardwaj's carousel (link below), audited against Rutten and Issa.
     Paraphrased teaching notes with citations; no slide, frame or image is stored in this repo.
     Section "Data trees in this machine" at the end is ours. -->

# Data Trees in Grasshopper — notes from Abhinav Bhardwaj

Source: https://www.instagram.com/p/Df7tq2qEaT5/
Author: Abhinav Bhardwaj (@abhinavbwj), posted 19 Nov 2026
Format: 15 slides. Each slide is a silent looping video of a live Grasshopper canvas — sliders move, panels update, no audio. Viewed logged-out, no sign-in needed.

Sources cited on the slides (paraphrased): David Rutten, The Why and How of Data Trees (McNeel, 2018); Rajaa Issa, Essential Algorithms and Data Structures for Grasshopper, ch. 3 (updated 15 Jul 2024); McNeel component reference. The "R." on the slides is Rajaa Issa — resolved from the primary source, not guessed from the low-resolution slide.

## AUDIT — 20 Nov 2026 (read this first)

The first pass summarised a browser viewing of the carousel without an independent check. This audit re-checked every claim against Rutten and Issa ch. 3. Verdict: the core is right, the first pass was not fully to the point.

CONFIRMED against the primary sources: address = path + index; a list is a tree with one branch {0}; a single item is one branch with one item; Partition arithmetic; Tree Item {1}[2] = 5; item-to-tree matching (one number meets every item, structure unchanged); short-list-to-tree matching (a list repeats in each branch); Graft 3 results vs 9; Flatten preserves order into {0}; Mass Addition 3 / 12 / 21, total 36; Simplify drops shared levels ({0;0;1;0} becomes {1}); Flip rows to columns with nulls on unequal branches; Path Mapper {A;i} to {i} groups by index; Trim merges from the last level, Shift from the first.

CORRECTED in this file:
- Slides 7–8 use a Text Format component ("{0}+{1}={2}"), not numeric Addition. Its outputs are strings such as "0+0=0". The pairing logic stands; calling them sums was wrong.
- Slide 5: the headline says Series gives one list at {0}. The panel as read in the first viewing said {0;0}. The headline is the correct one; the panel reading is suspect and is not taught here.

NOT TAUGHT — unresolved, do not use as fact:
- Slide 7 (list B plugged in) and slide 8 (ungrafted row) were read as producing deeper paths such as {0;0}, {0;1}. That conflicts with Issa §3.3.2, which says the short list repeats in each branch and the result keeps the input tree's structure, and it conflicts with slide 7's own single-number state, which kept {0}, {1}, {2}. It also inverts slide 8: the grafted row was read as shallower than the ungrafted row, but grafting adds a level. The counts (3 vs 9) and the values are right; the path readings are not trusted until checked in Grasshopper.
- Slide 15 Simplify: as read it returns 12 branches of 1, identical to Graft. Simplify of a 3-branch tree cannot do that — it should leave 3 branches. Either the panel was misread or the slide is wrong. Do not teach it.

DERIVED, not seen (panels were cut off): slide 12, branch {2} after Path Mapper holds 2, 5, 8; slide 13, Trim branch {1} holds 4, 5, 6, 7 and Shift branch {1} holds 2, 3, 6, 7. These follow from the stated rules; they were not visible in the viewing.

## The big idea

Grasshopper has one data structure. Every value lives at an address made of two parts: the branch path in curly brackets, and the item index inside that branch. A plain list is just a tree with the single branch {0}.

## 1. Address

Example used throughout: 9 numbers, 0–8, split into branches of 3.
- {0} holds 0, 1, 2
- {1} holds 3, 4, 5
- {2} holds 6, 7, 8

Tree Statistics reads a tree without changing it. Its outputs are the paths, the length of each branch, and the branch count. Here: paths {0},{1},{2}; 3 items per branch; 3 branches.

## 2. Partition makes branches

Partition List cuts one list into equal branches. The size setting is items per branch.
- 12 items at size 4 → 3 branches of 4
- 12 items at size 3 → 4 branches of 3
- 13 items at size 4 → a fourth branch holding just item 12

## 3. Paths grow with every split

Each operation that splits data adds a level to the path. Older steps sit on the left.
- Series gives one list at {0}
- Partition adds a branch per list
- Graft adds a branch per item

Worked chain, 4 numbers split 2-by-2 then grafted: the grafted result has one item per branch, {0;0}, {0;1}, {1;0}, {1;1}.

## 4. Reading one address

Tree Item takes a path and an index. With the 9-number tree above, path {1} and index 2 returns 5. Change the path to move between branches; change the index to move inside a branch. Path {2}, index 2 returns 8.

## 5. How matching works

When a tree meets a list, each branch meets the whole list. When it meets a single number, that number meets every item.

Worked example, shown with a Text Format component, so the outputs are strings such as "0+0=0", not numeric sums: tree branches {0}=0,1,2 etc., list B = 0,10,20, single value = 100.
- Unconnected second input → nulls in every branch
- List B plugged in → each branch pairs with 0, 10, 20 (e.g. branch {0} gives "0+0=0", "1+10=11", "2+20=22")
- Single 100 plugged in → every item pairs with 100 (0→"0+100=100", 1→"1+100=101" … 8→"8+100=108")

The resulting paths for the list-B state were read as {0;0}, {0;1}, {0;2} in the first viewing. That reading is NOT trusted — see Audit. The pairing above is trusted; the paths are not.

## 6. Graft changes the count

Two lists of 3 numbers paired item by item give 3 results. Graft the first list first and each of its numbers meets all of the second list — 9 results instead of 3.

So: graft is the switch between pairing item-by-item and pairing every-with-every. The counts are trusted; the panel paths as read in the first viewing are not (see Audit).

## 7. Flatten makes one list

Flatten puts every branch, in order, into the single path {0}. Branch order and item order inside each branch stay the same.

Why it matters: Mass Addition on the 9-number tree sums each branch separately (3, 12, 21). After Flatten it sums everything (36).

## 8. Simplify keeps what differs

Repeated grafting leaves messy paths like {0;0;1;0}. Simplify drops the levels every path shares. {0;0;1;0} becomes {1}. Order and contents stay the same.

## 9. Flip turns rows into columns

Flip Matrix moves item i of every branch into branch {i}.
- 12 numbers in 3 branches of 4 → 4 branches of 3
- Branch {0} becomes 0, 4, 8; branch {1} becomes 1, 5, 9; and so on
- Branches of unequal length leave nulls

## 10. Path Mapper writes the rule

Path Mapper rewrites each path with a rule, instead of using a fixed component.
- Rule {A;i} → {i} groups items by their index: the 9-number tree regroups so branch {0} holds 0, 3, 6, branch {1} holds 1, 4, 7
- Target {0} flattens; target {A;i} grafts

## 11. Trim the end, Shift the start

Two partitions on 8 numbers give paths {0;0}, {0;1}, {1;0}, {1;1}.
- Trim Tree (depth 1) merges branches from the last level
- Shift Paths merges them from the first level

Same depth, different end of the path — check which end you need before picking.

## 12. The whole map — same 12 numbers, four tools

Start: 12 numbers, size 4 → 3 branches of 4.
- Graft → 12 branches of 1
- Flatten → 1 branch of 12
- Flip → 4 branches of 3
- Simplify → see Audit. As read it showed 12 branches like Graft, which cannot be right for a 3-branch input. Do not use that reading.

## Caveats from the viewing

- A few panels are scrolled, so their last rows fall below the visible edge. Rows completed by arithmetic are labelled DERIVED in the Audit section.
- The slides are silent looping videos of a live canvas, not stills: panel values change over the loop, and a mid-transition frame can show different values from the settled frame.
- No audio, so there is no transcript to cross-check the diagrams against.

---

## Data trees in this machine

We do not run Grasshopper, but every multi-run result in this repo is a data tree, and the failure the slides
warn about ("most wrong results are silent tree errors") is the one we keep having. This section maps the
operations above onto our code, so the vocabulary is shared between agents.

### Our trees

| Result | Path | Item | Where |
|---|---|---|---|
| Ensemble (gate 3e) | `{variant; year; seed}` | one run's KPIs | `offsim/montecarlo/ensemble.py`, `Ensemble.runs` |
| Paired comparison | `{year; seed}` | `a - b` for one KPI | `Ensemble.compare`, `Comparison.diffs` |
| Paper instances | `{instance}` | one solved plan | `offsim/solve/whelp.py`, `instances.yaml` |
| Trajectory | `{agent}` | rows in time order | `offsim/contract.py` |
| Gap ranking | `{gap}` | four factor scores | `offsim/research/gaps.py` |

`Ensemble.runs` is one flattened table with the path held in its `variant`, `year` and `seed` columns. That is
a valid way to store a tree only as long as every operation keys on those columns. The moment code pairs rows by
position instead of by path, it is matching without a tree, and the error is silent.

### The operations, in our terms

| Slide operation | Our equivalent | The silent error it guards against |
|---|---|---|
| Tree Statistics (paths, branch lengths, branch count) | none yet. The expected shape is never declared, so it is never checked | a branch that should exist is empty and nothing notices. Bergen's calibration block was exactly this: an empty branch the tooling worked around (audit 8) |
| Matching a tree with a list (each branch meets the whole list) | every variant sees the same `years` and `seeds` (common random numbers) | if one variant ran on different seeds, its branch meets a different list, and `compare` measures the dice, not the policy |
| Graft (3 pairings become 9) | pairing on `(year, seed)` against a cross product of every run of `a` with every run of `b` | the same code computes a paired difference or an unpaired one depending on structure; both produce a clean number, only one is the experiment we designed |
| Mass Addition per branch (3, 12, 21) against flattened (36) | per-winter KPI against pooled KPI | a confidence interval from pooled runs treats 24 winters x seeds as independent draws; it is narrower than the truth when winters differ. Decide which one the claim needs before computing it |
| Flatten | `Ensemble.runs` itself | none, as long as the path columns travel with every row |
| Flip (rows to columns, nulls on unequal branches) | pivoting runs to a variant x KPI table | a variant with fewer valid runs leaves holes that a mean silently skips |
| Path Mapper `{A;i}` to `{i}` | regrouping runs by year to ask "which winters break the plan" | regrouping without saying so changes what the statistic means |
| Trim against Shift | dropping `seed` (Trim, the last level) against dropping `variant` (Shift, the first) | same depth, opposite meaning: one averages over the dice, the other mixes policies |

### The rule we take from it

**Every stage that produces a tree declares the shape it expects, and a check compares it with what it got,
before any number leaves the stage.** Expected shape means: the path levels and their names, the branch count,
and the item count per branch. For an ensemble that is `|variants| x |years| x |seeds|` runs, and
`|years| x |seeds|` pairs per comparison; a comparison with fewer pairs than that is refused, not quietly
averaged over what is left.

Status: built (T3). `offsim/montecarlo/shape.py` holds `TreeShape` (expected keys per level, `observed`, `diff`), and
`Ensemble.expected_shape()`, `shape()`, `shape_ok` and `shape_report()` expose it. `Ensemble.compare` raises `TreeShapeError`,
naming the missing `(year, seed)` keys, when it would pair fewer than `|years| x |seeds|`; a complete ensemble gives
byte-identical output to before. Gate 3e adds `detail.shape` (expected vs observed sizes, counts, up to 5 missing paths) and
fails with the doctor code `ENS-SHAPE` on any mismatch, unless a run failure is also present, which keeps `G3E-ENSEMBLE`.
`Ensemble.ok` is still the run-failure verdict only. Not yet covered: the `{instance}`, `{agent}` and `{gap}` trees in the
table above declare no shape, and the pooled-versus-per-winter confidence-interval choice is still the caller's to state.
