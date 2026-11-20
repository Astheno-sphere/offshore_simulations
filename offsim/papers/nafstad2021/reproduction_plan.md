# Nafstad et al. (2021) — reproduction plan

**Paper:** Nafstad, Haugseth, Høyland & Stålhane, *Computers & Operations
Research* 128 (2021) 105158, DOI 10.1016/j.cor.2020.105158.
**Source text:** `nafstad2021.txt` (pdftotext of the CC BY 4.0 PDF), read in full.
**Scope of this plan:** extraction and test design only. No solver built here.

## (a) Tables 3–8, transcribed exactly as printed

Transcription conventions: numbers are copied as printed, including the
paper's thousands separators (spaces in Table 4, e.g. "4 231") and its
one-decimal/two-decimal choices. Where pdftotext garbled a header, the garble
is noted in place and the reading used is stated — nothing was reconstructed
by guessing. "Opt. gap" is the optimality gap at termination (0.00% = solved
to proven optimality). "Comp. time" is computing time in seconds. Time limit
throughout: 3600 s (1 hour) per instance; for Tables 5–8 the B&B time is
adjusted for trip-generation time so trip-gen + B&B ≤ 3600 s.

### Table 3 — Compact model (Section 3.1) vs trip-based model (Section 3.2), 8–16 orders, 3 instances per size

Columns: # Orders | compact Opt. gap [%] | compact Comp. time [s] | trip-based
Opt. gap [%] | trip-based Trip gen. time [s] | trip-based B&B time [s] |
trip-based Comp. time [s] (trip-gen + B&B).

> Extraction note: pdftotext renders the trip-based B&B-time header as
> "TtB&B time [s]"; read as "B&B time [s]". Two rows show a 0.01 s
> discrepancy between the printed comp. time and trip-gen + B&B
> (12 orders row 1: 0.01 + 0.33 = 0.34 vs printed 0.35; 16 orders row 3:
> 0.05 + 1.73 = 1.78 vs printed 1.77). Consistent with rounding of unrounded
> values; not a transcription error.

| # Orders | Compact Opt. gap | Compact Comp. time [s] | Trip-based Opt. gap | Trip gen. time [s] | B&B time [s] | Trip-based Comp. time [s] |
|---:|---:|---:|---:|---:|---:|---:|
| 8 | 0.00 % | 37 | 0.00 % | 0.01 | 0.03 | 0.04 |
| 8 | 0.00 % | 11 | 0.00 % | 0.00 | 0.03 | 0.03 |
| 8 | 0.00 % | 298 | 0.00 % | 0.01 | 0.12 | 0.13 |
| 10 | 100.00 % | 3600 | 0.00 % | 0.01 | 0.32 | 0.33 |
| 10 | 0.00 % | 619 | 0.00 % | 0.01 | 0.09 | 0.10 |
| 10 | 25.20 % | 3600 | 0.00 % | 0.01 | 0.31 | 0.32 |
| 12 | 100.00 % | 3600 | 0.00 % | 0.01 | 0.33 | 0.35 |
| 12 | 100.00 % | 3600 | 0.00 % | 0.01 | 0.04 | 0.05 |
| 12 | 53.65 % | 3600 | 0.00 % | 0.01 | 0.44 | 0.45 |
| 14 | 100.00 % | 3600 | 0.00 % | 0.03 | 1.12 | 1.15 |
| 14 | 100.00 % | 3600 | 0.00 % | 0.01 | 0.28 | 0.29 |
| 14 | 100.00 % | 3600 | 0.00 % | 0.02 | 0.52 | 0.54 |
| 16 | 100.00 % | 3600 | 0.00 % | 0.04 | 1.48 | 1.52 |
| 16 | 100.00 % | 3600 | 0.00 % | 0.02 | 0.86 | 0.88 |
| 16 | 100.00 % | 3600 | 0.00 % | 0.05 | 1.73 | 1.77 |

Paper's reading (Section 5.2): the compact model struggles at 10 orders and
solves none at 12+ orders within an hour (most gaps 100% = no feasible solution
found); the trip-based model solves all instances from 8 to 16 orders within
two seconds.

### Table 4 — Trip generation time and number of trips (Algorithm 1), 17–52 orders

Each row aggregates 9 instances (3 instances of each order size in the
interval). Columns: Orders interval | Time generating trips [s]: Min, Average,
Max | Number of trips: Min, Average, Max.

| Orders | Time Min [s] | Time Avg [s] | Time Max [s] | Trips Min | Trips Avg | Trips Max |
|---|---:|---:|---:|---:|---:|---:|
| 17–19 | 0.01 | 0.05 | 0.20 | 845 | 4 231 | 18 115 |
| 20–22 | 0.01 | 0.11 | 0.39 | 1 390 | 8 427 | 25 902 |
| 23–25 | 0.03 | 0.11 | 0.32 | 2 868 | 8 616 | 22 230 |
| 26–28 | 0.08 | 0.40 | 1.97 | 6 720 | 21 087 | 75 117 |
| 29–31 | 0.09 | 0.74 | 2.23 | 6 790 | 34 368 | 87 416 |
| 32–34 | 0.19 | 5.51 | 18.50 | 13 472 | 172 859 | 535 536 |
| 35–37 | 1.30 | 7.18 | 16.14 | 50 616 | 198 262 | 441 960 |
| 38–40 | 1.56 | 11.56 | 42.35 | 53 442 | 278 478 | 871 101 |
| 41–43 | 3.66 | 35.85 | 82.94 | 103 800 | 780 779 | 1 697 120 |
| 44–46 | 4.36 | 123.47 | 696.44 | 132 187 | 2 137 780 | 10 902 628 |
| 47–49 | 16.13 | 92.33 | 274.94 | 762 245 | 2 021 542 | 4 945 039 |
| 50–52 | 15.51 | 218.86 | 621.90 | 942 007 | 3 793 540 | 9 411 108 |

Paper's reading: total trip-gen time < 1 minute up to 40 orders; worst case
over all instances < 12 min (720 s). Trip counts vary hugely within an
interval (e.g. 44–46: 132,187 to 10,902,628), driven by order distribution
across heliports/installations and by arc removal / time-window reduction.

### Table 5 — Trip-based model: standard B&B vs Lazy vs DCG, 17–52 orders

Per method and order-size interval: number of instances solved to optimality
(# Opt., out of 9), average optimality gap (Opt. gap [%]), average total
computing time (Comp. time [s], trip-gen + B&B). Tot./Avg. row: total # Opt.
(out of 108), average gap and average time over all tested instances.

| Orders | B&B # Opt. | B&B Opt. gap | B&B Comp. time [s] | Lazy # Opt. | Lazy Opt. gap | Lazy Comp. time [s] | DCG # Opt. | DCG Opt. gap | DCG Comp. time [s] |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 17–19 | 9 | 0.00 % | 16.36 | 9 | 0.00 % | 5.49 | 9 | 0.00 % | 4.73 |
| 20–22 | 9 | 0.00 % | 190.40 | 9 | 0.00 % | 54.31 | 9 | 0.00 % | 10.39 |
| 23–25 | 9 | 0.00 % | 275.82 | 9 | 0.00 % | 33.98 | 9 | 0.00 % | 44.76 |
| 26–28 | 8 | 1.58 % | 928.97 | 9 | 0.00 % | 395.29 | 9 | 0.00 % | 63.68 |
| 29–31 | 7 | 2.57 % | 1541.25 | 9 | 0.00 % | 969.34 | 8 | 0.62 % | 772.64 |
| 32–34 | 1 | 20.61 % | 3233.70 | 3 | 35.80 % | 2540.17 | 3 | 16.18 % | 2579.32 |
| 35–37 | 1 | 28.76 % | 3413.04 | 3 | 28.07 % | 2935.91 | 3 | 14.84 % | 2585.45 |
| 38–40 | 0 | 23.51 % | 3600.00 | 2 | 67.07 % | 3365.38 | 2 | 41.16 % | 3151.38 |
| 41–43 | 0 | 53.18 % | 3600.00 | 0 | 68.79 % | 3600.00 | 0 | 39.12 % | 3600.00 |
| 44–46 | 0 | 64.36 % | 3600.00 | 0 | 48.61 % | 3600.00 | 0 | 71.34 % | 3600.00 |
| 47–49 | 0 | 90.69 % | 3600.00 | 0 | 100.00 % | 3600.00 | 0 | 100.00 % | 3600.00 |
| 50–52 | 0 | 91.34 % | 3600.00 | 0 | 100.00 % | 3600.00 | 0 | 100.00 % | 3600.00 |
| Tot./Avg. | 44 | 31.38 % | 2300.0 | 53 | 37.36 % | 2058.3 | 52 | 31.94 % | 1967.7 |

Paper's reading: all methods solve all instances up to 25 orders; 26–31
orders: 15/18 (B&B), 18/18 (Lazy), 17/18 (DCG) solved; above 31 orders fewer
than half per interval; above 40 orders none solved to optimality by any
method (though feasible solutions are found for many). Lazy solves one more
instance than DCG overall; DCG has lower average gap and time. Neither
outperforms the other for one connected pair — the DCG advantage appears in
Table 6, where connected orders multiply.

### Table 6 — Effect of the number of connected orders, 30-order instances, trip-based model

Five instances of 30 orders each, each solved 9 times with |N^C| = 0…8 pairs
of connected orders. Per method: # Opt. (out of 5), average Opt. gap [%],
average Comp. time [s]. For DCG also: average number of times constraints
(61)–(63) were added during the B&B search (# Cons.).

| \|N^C\| | B&B # Opt. | B&B Opt. gap | B&B Comp. time [s] | Lazy # Opt. | Lazy Opt. gap | Lazy Comp. time [s] | DCG # Opt. | DCG Opt. gap | DCG Comp. time [s] | DCG # Cons. |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 5 | 0.00 % | 2595.24 | 4 | 0.33 % | 1668.36 | 5 | 0.00 % | 471.59 | 73.6 |
| 1 | 3 | 0.95 % | 2804.86 | 5 | 0.00 % | 1095.65 | 5 | 0.00 % | 359.72 | 76.0 |
| 2 | 3 | 0.95 % | 2501.21 | 5 | 0.00 % | 1089.97 | 5 | 0.00 % | 737.95 | 94.6 |
| 3 | 3 | 1.44 % | 2368.23 | 5 | 0.00 % | 1001.42 | 5 | 0.00 % | 816.27 | 151.8 |
| 4 | 3 | 3.15 % | 3067.16 | 5 | 0.00 % | 1034.59 | 5 | 0.00 % | 1177.73 | 99.6 |
| 5 | 3 | 4.03 % | 2469.74 | 4 | 0.72 % | 1545.19 | 5 | 0.00 % | 909.73 | 137.0 |
| 6 | 4 | 1.58 % | 2223.34 | 4 | 0.33 % | 1583.26 | 4 | 1.34 % | 1194.56 | 144.0 |
| 7 | 3 | 3.27 % | 2222.25 | 4 | 0.20 % | 1722.28 | 5 | 0.00 % | 737.87 | 145.2 |
| 8 | 3 | 4.19 % | 2215.46 | 3 | 3.47 % | 2058.27 | 4 | 0.94 % | 1829.65 | 161.8 |
| Tot./Avg. | 30 | 2.17 % | 2496.39 | 39 | 0.56 % | 1422.11 | 43 | 0.25 % | 915.01 | 120.4 |

Paper's reading: DCG significantly outperforms Lazy here (Lazy ~50% longer on
average, 4 fewer instances solved). Computing time rises with connected
orders for all methods, with outliers (Lazy with 0 connected orders is slower
than with 1–6 pairs and fails one instance).

### Table 7 — Average trips generated and average B&B nodes vs connected orders

Same 5×30-order instances as Table 6. Columns: |N^C| | average # Trips
generated | average # B&B nodes: B&B | Lazy | DCG.

> Extraction note: the PDF header layout is ambiguous. This reading follows
> the text of Section 5.3: there is ONE "# Trips" column (a single average
> per |N^C| row) because trips are generated once, a priori, and the count is
> therefore method-independent; the three following columns are B&B nodes per
> method. If the builder re-reads the PDF and finds four method-specific trip
> columns instead, this table must be corrected before use.

| \|N^C\| | # Trips (avg) | B&B nodes — B&B | B&B nodes — Lazy | B&B nodes — DCG |
|---:|---:|---:|---:|---:|
| 0 | 47695.2 | 57440.8 | 77568.0 | 69721.2 |
| 1 | 45564.4 | 33261.0 | 53397.0 | 55336.6 |
| 2 | 45151.4 | 29664.0 | 53671.8 | 144530.4 |
| 3 | 42890.4 | 21094.4 | 59297.4 | 132799.2 |
| 4 | 41573.0 | 47016.0 | 88488.6 | 345396.4 |
| 5 | 38420.2 | 30898.8 | 93327.4 | 271439.8 |
| 6 | 36524.6 | 38656.6 | 207333.6 | 327316.6 |
| 7 | 33749.8 | 34993.0 | 194810.0 | 147105.4 |
| 8 | 30298.8 | 35063.6 | 171104.2 | 635135.6 |

Paper's reading: trip counts fall ~30% as connected pairs go 0 → 8
(47,695.2 → 30,298.8), because arc removal and time-window narrowing leave
fewer feasible paths. DCG builds much larger B&B trees yet is faster, because
each node solves faster (fewer, sparser constraints added at a time).

### Table 8 — One vs two heliports (DCG method), 17–37 orders

Flesland removed; all pickup/delivery nodes and helicopters moved to Sola.
Per order interval (9 instances each): # Opt. (out of 9), average Opt. gap
[%], average total Comp. time [s], average deviation in objective value
(D obj. [%]) and in number of trips (D trips) when using one instead of two
heliports, computed only over instances solved to optimality in both versions.

> Extraction note: "D trips" values are printed WITHOUT units. Read as
> absolute differences in average trip counts (not %), per the caption
> ("average difference in ... number of trips"). This is uncertain — the paper
> does not state the unit. Do not convert to percentages.

| Orders | # Opt. | Opt. gap | Comp. time [s] | D obj. | D trips |
|---|---:|---:|---:|---:|---:|
| 17–19 | 9 | 0.00 % | 3.90 | 1.21 % | -5.56 |
| 20–22 | 9 | 0.00 % | 8.51 | 0.41 % | -196.22 |
| 23–25 | 9 | 0.00 % | 59.13 | 1.38 % | -98.00 |
| 26–28 | 9 | 0.00 % | 95.60 | 1.99 % | -597.33 |
| 29–31 | 9 | 0.00 % | 376.69 | 0.34 % | 175.33 |
| 32–34 | 4 | 14.14 % | 2273.47 | 0.15 % | 2199.11 |
| 35–37 | 4 | 6.20 % | 2378.85 | 1.13 % | -4214.44 |

Paper's reading (Section 5.4): all instances up to 31 orders solved to
optimality, plus 8 of 18 in 32–37. Objective values rise slightly with one
heliport (helicopters fly further to installations closest to Bergen); trip
counts are "not effected much"; helicopters used are mostly the same (±1).
Methodology works about equally well with one heliport.

> Extraction note: Section 5.4 text says "Comparing these results to those
> presented in Table 3" — Table 3 is the 8–16-order compact comparison, so
> this must mean Table 5 (the DCG results for 17–52 orders). Treat as a
> cross-reference error in the paper, not an extraction error.

## (b) First reproduction target

**Smoke test first: Table 3, 8 orders.** All three methods solve all three
8-order instances to 0.00% gap (compact in 11–298 s; trip-based total time
0.03–0.13 s). This is the sanity check that the generator, the model and the
solver all run end to end before anything discriminating is attempted.

**First reproduction target: Table 3, 10 orders (3 instances).**

Why 10 and not 8: 8 orders does not discriminate — every method solves it.
10 orders is the smallest size where the paper's headline claim first shows:
the compact model breaks (gaps 100.00% / 0.00% / 25.20%; times 3600 / 619 /
3600 s — one instance not even feasible within the hour) while the trip-based
model solves all three to 0.00% gap in 0.33 / 0.10 / 0.32 s total
(trip-gen 0.01 s each; B&B 0.32 / 0.09 / 0.31 s). Reproducing this split is
the smallest meaningful test of the whole chain (generator → trip generation
→ model → solver). It is also cheap: trip generation is 0.01 s and the whole
test runs in seconds.

Paper's reported values for the target (Table 3, 10 orders):

| Instance | Compact Opt. gap | Compact Comp. time [s] | Trip-based Opt. gap | Trip gen. [s] | B&B [s] | Trip-based Comp. time [s] |
|---|---:|---:|---:|---:|---:|---:|
| 10 orders #1 | 100.00 % | 3600 | 0.00 % | 0.01 | 0.32 | 0.33 |
| 10 orders #2 | 0.00 % | 619 | 0.00 % | 0.01 | 0.09 | 0.10 |
| 10 orders #3 | 25.20 % | 3600 | 0.00 % | 0.01 | 0.31 | 0.32 |

Sequence after the target passes: Table 3 at 12, 14, 16 orders (trip-based
still 0.00%, all ≤ 1.77 s; compact all 100% except one 53.65% at 12 orders);
then Table 4 trip-generation counts for 17–19 orders (845–18,115 trips,
avg 4,231); then Table 5 DCG at 17–19 orders (9/9 optimal, avg 4.73 s).

## (c) Comparison rule — what counts as a pass

**The central fact shaping this rule: no optimal objective VALUES are printed
anywhere in Tables 3–8.** The paper reports only optimality gaps, computing
times, trip counts, B&B node counts and constraint-add counts. So "reproduce
the optimal objective" cannot be checked numerically against the paper at all.
The pass criteria below are built around what the paper actually reports.

### Primary criteria (must all hold for a PASS on the first target)

1. **Optimality (binary, exact):** our trip-based implementation reaches
   **0.00% gap on all three 10-order instances** (and all three 8-order
   smoke instances). Gap is a proof of optimality, not a measurement — there
   is no tolerance to negotiate. Any gap > 0.00% on a 10-order instance is a
   FAIL for that instance.
2. **Feasibility / validity (binary, exact):** every solution returned must
   pass the Corrector's independent checks — all orders served once by one
   helicopter, seat capacity never exceeded, fuel feasible, time windows met,
   connected-order separations met, no two helicopters at one installation at
   the same time, max-legs rule respected. A 0.00% gap on an invalid solution
   is a FAIL, not a pass.
3. **Trip-generation counts (aggregate, order-of-magnitude):** the number of
   trips our labeller generates for 10-order instances must be plausible
   against the paper's scale — Table 4's smallest interval (17–19 orders)
   spans 845–18,115 trips, and Table 3's 0.01 s trip-gen times imply small
   counts at 8–16 orders. Record our counts; a count wildly outside the
   paper's scale (e.g. 10× the Table 4 maximum for a smaller instance) is a
   FAIL of the generator, not of the solver. (No exact per-instance trip
   count exists to match — see (d).)
4. **Model separation (qualitative, must hold):** the compact model must show
   the paper's failure pattern at 10 orders — at least one of the three
   instances unsolved (gap > 0%) at the 3600 s limit, and the trip-based
   model must solve all three. If our compact model solves all three easily,
   something differs from the paper (formulation strength, instance
   difficulty, or solver) and the reproduction is NOT a pass even if the
   trip-based numbers look right. (Compact runs are expensive — 3600 s each
   worst case — so this check may run with a reduced limit first and the full
   3600 s limit only to confirm; record whatever limit was used.)

### Computing time (indicative only — NOT a pass/fail criterion)

The paper ran on a Lenovo NextScale nx360 M5, Intel E5-2643v3 six-core
2×3.40 GHz, 512.0 GB RAM, Linux, Gurobi 9.0.0, with instance generation and
trip labelling in C++. Our hardware, solver and language will differ, so
times are compared only as orders of magnitude: trip-based total time for
10-order instances should be **seconds, not minutes** (paper: 0.10–0.33 s);
a result in the same ballpark (within ~10×) is consistent, a result 100×
slower is a warning to investigate, not an automatic fail. Record machine,
solver + version, and language alongside every time.

### Later tables (same rule, scaled up)

- Table 4: compare our trip counts per size interval against the paper's
  min/avg/max bands (distributional — most of our instances should fall
  inside the band; the band is wide, e.g. 132,187–10,902,628 at 44–46 orders).
- Table 5: compare # Opt. per interval and average gap; exact match of # Opt.
  is NOT expected (different random instances) — match the pattern (all
  solved to 25 orders; ~half solved at 32–37; none above 40).
- Table 6: the DCG-vs-Lazy separation is the claim to test (DCG 43/45 vs
  Lazy 39/45, DCG ~35% faster on average). Pattern match, not exact counts.
- Table 8: pattern match (all solved to 31 orders; objective +0.15–1.99%
  with one heliport).

## (d) What is NOT available for exact reproduction

1. **No instance data files exist.** No data appendix, no repository link, no
   supplementary material anywhere in the paper. The instances exist only as
   the generative description in Section 5.1, driven by 2018 flight records
   provided by TietoEVRY (acknowledged, not published). **Consequence: the
   test reproduces the GENERATION RULES plus the solve, and compares aggregate
   table values — never instance-by-instance exact values.** Any claim of an
   exact per-instance match would be false.
2. **No random seed.** The paper reports no seed for any random draw. Even
   with identical rules, our instances will differ from theirs.
3. **No optimal objective values.** Tables 3–8 print gaps and times only.
   There is no number to compare a computed optimum against.
4. **No installation identities or coordinates.** Ten installations, unnamed,
   no coordinates, Figure 2 schematic only. Distances — and therefore flight
   times, fuel use and costs — cannot be reconstructed from the paper.
5. **No helicopter parameters.** No seat counts (except S-92 = 19 as
   background), speeds, fuel burn, tank sizes or fixed costs per type.
6. **No cost coefficients or units.** Arc costs and fixed helicopter costs
   are symbols (C^h_ij, C^H_h), never numbers.
7. **No numeric values for L (max legs), T^L (landing time), T^H
   (turnaround/refuel/rest time), or T^C_ij (connected-order time
   differences).** All are parameters of the model, never instantiated.
8. **No sampling rules** for time-window start times or for pickup/delivery
   locations (only: order sizes 6–10, window width 1 hour, 25%
   inter-installation, 1 connected pair in §5.2).
9. **No per-instance trip counts for Tables 3–8** (only interval aggregates
   in Table 4 and averages in Table 7), and no per-instance B&B node counts.

## (e) Assumptions / unknowns flagged

Everything below must be decided — and the decision recorded with its value —
by whoever builds the generator/solver. None of it is in the paper.

1. ASSUMPTION — Cost model: currency/units, arc-cost formula (e.g. per-km or
   per-minute), fixed cost per helicopter-day per type. (Paper: symbols only.)
2. ASSUMPTION — Helicopter table: seats, cruise speed, fuel burn/hour, tank
   capacity, fixed cost for Super Puma and Sikorsky S-92. (Paper: types named
   only; S-92 = 19 seats as background.)
3. ASSUMPTION — The 10 installations: names, coordinates, and the distance
   source. (Paper: unnamed, schematic map only.) Suggested: 10 real NCS
   installations reachable from both Sola and Flesland, recorded explicitly.
4. ASSUMPTION — Time-window start times: distribution and day-start
   convention. (Paper: width 1 hour only.)
5. ASSUMPTION — Order location sampling: how pickup/delivery locations are
   drawn across the 2 heliports + 10 installations, and how the 25%
   inter-installation share is enforced. (Paper: share stated, sampling rule not.)
6. ASSUMPTION — Order-size distribution: "drawn randomly in the interval
   between 6 and 10" — recorded here as uniform on integers 6–10 unless the
   builder finds reason otherwise.
7. ASSUMPTION — Connected-order time differences T^C_ij: values per pair.
   (Paper: concept + "minimum amount of time" only.)
8. ASSUMPTION — Max legs L, landing time T^L, turnaround time T^H: numeric
   values. (Paper: parameters only.)
9. ASSUMPTION — Flight-time/fuel model: distance metric (great-circle?
   rhumb-line?), cruise speeds per type. (Paper: "based on distance and
   cruising speed" only.)
10. ASSUMPTION — Random seed(s) for our own generator (must be fixed and
    recorded so OUR results are reproducible, even though they cannot match
    the paper's instances).
11. ASSUMPTION — Solver substitution: the paper used Gurobi 9.0.0 (commercial)
    and C++ for generation/labelling. If we use an open solver (e.g. HiGHS
    via Pyomo, OR-Tools, or a PyVRP-based heuristic for cross-checking),
    that substitution and its effect on times/gaps must be recorded. Exact
    reproduction of a commercial solver's B&B behaviour is not expected;
    optimality (0.00% gap) is solver-independent and remains the pass
    criterion.
12. ASSUMPTION — Which heliport each helicopter is based at for a given
    instance (paper: "evenly distributed among the two heliports" — the
    tie-break for odd fleet sizes is not stated).
13. UNKNOWN — Table 7 header ambiguity (one "# Trips" column vs
    method-specific columns) and Table 8 "D trips" units (read as absolute
    differences; paper does not state units). Both flagged in (a); if the
    builder re-reads the PDF and resolves them differently, correct this plan
    before using those two tables as targets.
14. UNKNOWN — Two 0.01 s rounding discrepancies in Table 3 (see (a)). Immaterial
    to the test; recorded for completeness.
15. UNKNOWN — Section 5.4's "Table 3" cross-reference (read as Table 5).
    Recorded for completeness.
