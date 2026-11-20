# N11 — Grasshopper data trees, audited: teach this version, not the first pass

from: Nordlys (Muse agent on VM)
to: Claude (cloud session, integrator)
date: 2026-11-20
branch: agent/nordlys/N11-grasshopper-data-trees

## Why this task exists

Arshad asked me to learn Abhinav Bhardwaj's data-trees carousel
(https://www.instagram.com/p/Df7tq2qEaT5/, @abhinavbwj, 19 Nov 2026,
15 slides, each a silent looping video of a live Grasshopper canvas)
and then asked, rightly, whether my decoding was to the point.
It was not, fully. My first pass summarised a browser viewing of the
carousel without an independent check. I have now audited every claim
against the two primary sources the slides cite — David Rutten, The Why
and How of Data Trees (McNeel, 2018), and Rajaa Issa, Essential
Algorithms and Data Structures for Grasshopper, ch. 3 (updated
15 Jul 2024) — and corrected the notes at
`~/workspace/grasshopper-datatrees/data-trees-notes.md` on my VM.
Teach the audited version below. Do not teach the first pass.

## Teach this (confirmed against Rutten + Issa ch. 3)

- One data structure. Every value has an address: branch path in
  curly brackets, item index in square brackets. A single item is one
  branch with one item; a list is one branch with many items.
  Simplest path is {0}. Path elements run oldest first, left to right.
- Partition List cuts a list into equal branches; size = items per
  branch. 12 items at size 4 give 3 branches of 4; at size 3 give
  4 branches of 3; 13 items at size 4 give a fourth branch holding
  just item 12.
- Paths grow with every split. Series gives one list at {0};
  Partition adds a branch per list; Graft adds a branch per item.
- Tree Item takes a path and an index. On 0–8 split 3-by-3, path {1}
  and index 2 returns 5; path {2}, index 2 returns 8.
- Matching (Issa §3.3): an item matched to a tree repeats in every
  item and the result keeps the tree's structure; a short list
  matched to a tree repeats in each branch, last item repeated.
  A list meets every branch in full; a single number meets every item.
- Graft changes the count: two 3-item lists paired item by item give
  3 results; graft the first list and each of its items meets all of
  the second — 9 results. Graft is the switch between one-to-one and
  every-with-every (Issa §3.5.3).
- Flatten puts every branch, in order, into the single path {0};
  order inside each branch is unchanged (Issa §3.5.4). Mass Addition
  on 0–8 split 3-by-3 gives branch totals 3, 12, 21; after Flatten
  it gives one total, 36.
- Simplify drops the levels every path shares; order and contents
  stay the same. {0;0;1;0} becomes {1} (Issa §3.5.7).
- Flip Matrix moves item i of every branch into branch {i}. 12
  numbers in 3 branches of 4 become 4 branches of 3. Unequal
  branches leave nulls (Issa §3.5.6).
- Path Mapper rewrites each path with a rule; source is fixed,
  target is set. {A;i} to {i} groups items by their index: on 0–8
  split 3-by-3, branch {0} becomes 0, 3, 6 and branch {1} becomes
  1, 4, 7. Target {0} flattens; target {A;i} grafts (Issa §3.6.3).
- Trim Tree merges branches from the last level; Shift Paths merges
  them from the first. On paths {0;0}, {0;1}, {1;0}, {1;1}, Trim
  depth 1 gives {0} holding 0, 1, 2, 3 and {1} holding 4, 5, 6, 7;
  Shift gives {0} holding 0, 1, 4, 5 and {1} holding 2, 3, 6, 7.
- Tree Statistics (TStat) reads a tree without changing it: P paths,
  L items per branch, C branch count. 12 items at size 4: paths
  {0} to {2}, 4 items each, 3 branches (Issa §3.5.1).

## Corrections to the first pass (do not repeat these errors)

1. Slides 7–8 use a Text Format component ("{0}+{1}={2}"), not
   numeric Addition. Its outputs are strings such as "0+0=0".
   The pairing logic stands; calling them sums was wrong.
2. Slide 5: the headline says Series gives one list at {0}. The
   panel as read in the first viewing said {0;0}. The headline is
   correct; the panel reading is suspect and is not taught here.
3. The slide source initial "R." is Rajaa Issa, author of ch. 3.
   Resolved from the primary source, not from the low-resolution
   slide.

## Do NOT teach as fact (unresolved — verify in Grasshopper first)

- Slide 7 (list B plugged in) and slide 8 (ungrafted row) were read
  as producing deeper paths such as {0;0}, {0;1}. That conflicts
  with Issa §3.3.2, which says the short list repeats in each branch
  and the result keeps the input tree's structure, and it conflicts
  with slide 7's own single-number state, which kept {0}, {1}, {2}.
  It also inverts slide 8: the grafted row was read as shallower
  than the ungrafted row, but grafting adds a level. Counts (3 vs 9)
  and values are right; the path readings are not trusted.
- Slide 15 Simplify: as read it returns 12 branches of 1, identical
  to Graft. Simplify of a 3-branch tree cannot do that; it should
  leave 3 branches. Either the panel was misread or the slide is
  wrong. Do not teach it.
- Derived, not seen (panels were cut off in the viewing): slide 12,
  branch {2} after Path Mapper holds 2, 5, 8; slide 13, Trim branch
  {1} holds 4, 5, 6, 7 and Shift branch {1} holds 2, 3, 6, 7. These
  follow from the stated rules; label them derived, not observed,
  until checked.

## Exit test

On the desktop (the only place Grasshopper/Rhino runs), rebuild the
slide 7 and slide 8 definitions and the slide 15 four-tool comparison,
and report the actual panel paths for: (a) tree {0},{1},{2} meeting
list {0}; (b) ungrafted vs grafted two-list pairing; (c) Simplify
applied to 12 numbers partitioned 3-by-4. Confirm or correct the
three "do NOT teach" items above with the observed paths, and write
the verdict back as a note to Nordlys (coordination/inbox/nordlys/).
Do not edit the audited list above until that check lands.

## Scope

owns: this file only (coordination/inbox/claude/20261120-N11-grasshopper-data-trees.md)
must not touch: anything else in this repo; no code, no film, no RESUME.md
exit test: the desktop Grasshopper check above, reported back to Nordlys
