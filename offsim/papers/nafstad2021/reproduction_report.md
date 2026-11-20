# Nafstad et al. (2021) — First reproduction test: Table 3 (10 orders) + 8-order smoke

**Paper:** Nafstad, Haugseth, Høyland & Stålhane, *An exact solution method for a
rich helicopter vehicle routing problem*, Computers & Operations Research 128
(2021) 105158, DOI 10.1016/j.cor.2020.105158 (CC BY 4.0).

**Date:** 2026-11-06. **Test script:** `reproduce_table3.py` (deterministic,
fixed seed, reads `scenario.yaml`). **Machine log:**
`reproduce_table3_log.json` (6 records, full instance data + results).

## Verdict: PARTIAL REPRODUCTION — not a full PASS

The plan's PASS rule has four criteria. Three pass, one fails:

| # | Criterion | Result |
|---|-----------|--------|
| 1 | Trip-based reaches exactly 0.00% gap on all three 10-order instances (and all three 8-order smoke instances) | **PASS** — 0.00% on all 6 instances |
| 2 | Every returned solution passes independent validity checks (capacity, fuel, time windows, connected-order separations, no simultaneous presence) | **PASS** — 28–36/36 checks on every instance; recomputed objective equals solver objective exactly on all 6 |
| 3 | Trip-generation counts plausible against the paper's scale (Table 4 smallest interval, 17–19 orders: 845–18,115 trips) | **PASS** — 95–216 trips at 8–10 orders, growing with n as expected |
| 4 | Compact model shows the paper's failure pattern at 10 orders (at least one instance unsolved at the cap) | **FAIL** — my compact model solved all three 10-order instances to optimality (11.7 / 59.3 / 12.7 s) |

Per the plan's rule ("if our compact model solves all three easily, separation is
NOT reproduced"), **this is not a pass**. The trip-based side reproduces the
paper's headline result cleanly; the compact side does not. The most likely
reasons are in §4 below — my compact model is structurally simpler than the
paper's, and my generated instances are probably easier than the paper's.

## Per-instance results vs paper values

### Smoke — 8 orders (paper: everything solves; compact 11–298 s; trip-based total 0.03–0.13 s)

| Inst | Trips (gen s) | Trip-based obj | Gap | Solve s | Valid | Compact obj | Compact gap | Compact s |
|------|---------------|----------------|-----|---------|-------|-------------|-------------|-----------|
| 0 | 95 (0.15) | 792.98 | 0.00% | 0.05 | 32/32 | 972.22 | 0.00% | 8.59 |
| 1 | 216 (0.28) | 770.86 | 0.00% | 0.27 | 28/28 | 824.70 | 0.00% | 3.41 |
| 2 | 103 (0.15) | 819.71 | 0.00% | 0.05 | 28/28 | 1034.94 | 0.00% | 20.37 |

### Target — Table 3, 10 orders

Paper values: compact gaps **100.00% / 0.00% / 25.20%**, times **3600 / 619 /
3600 s**; trip-based all **0.00%** gap, trip-gen **0.01 s** each, B&B **0.32 /
0.09 / 0.31 s**, totals **0.33 / 0.10 / 0.32 s**.

| Inst | Trips (gen s) | Trip-based obj | Gap | Solve s | Total s (gen+solve) | Valid | Compact obj | Compact gap | Compact s |
|------|---------------|----------------|-----|---------|---------------------|-------|-------------|-------------|-----------|
| 0 | 131 (0.19) | 1062.07 | 0.00% | 0.08 | 0.27 | 36/36 | 1247.51 | 0.00% | 11.70 |
| 1 | 146 (0.19) | 908.67 | 0.00% | 0.09 | 0.28 | 28/28 | 1319.21 | 0.00% | 59.30 |
| 2 | 135 (0.19) | 1114.35 | 0.00% | 0.08 | 0.27 | 32/32 | 1140.31 | 0.00% | 12.66 |

Notes:
- Trip-based totals (0.27–0.28 s) sit in the same ballpark as the paper's
  (0.10–0.33 s); my trip generation is slower than the paper's (0.15–0.28 s vs
  0.01 s) and my master solve faster — the split differs, the total does not.
- Compact objectives are 7–26% HIGHER than trip-based objectives on the same
  instance. That is expected and is not a contradiction: my compact model is a
  different (more restricted) problem — one route per helicopter per day and at
  most one node per installation per helicopter — so its optimum is not
  comparable to the trip-based optimum, and neither is comparable to the
  paper's (no optimal objective values are printed anywhere in Tables 3–8).
- Selected trip-based solutions use 2–3 helicopters (of 6 available) and 4–6
  trips; the cheaper Super Puma is preferred whenever feasible, which is the
  expected cost-minimising behaviour.

## Hardware, solver, versions

- VM: 4 vCPU (AMD EPYC 9D25), 7.7 GB RAM (~0.6 GB free during the run).
- Python 3.12.3; HiGHS **1.15.1** via highspy (no `__version__` attribute);
  Pyomo **6.10.1**; OR-Tools 9.15.6755 (installed, not used in the final run);
  numpy 2.5.3, scipy 1.18.1, PyYAML 6.0.1.
- **No Gurobi here.** Paper hardware/solver: Lenovo NextScale nx360 M5,
  E5-2643v3, 512 GB RAM, Gurobi 9.0.0. Computing time is indicative only.
- Time caps (ASSUMPTION, paper used 3600 s): compact 300 s, trip-based 300 s
  per instance. No cap was ever hit.
- Total wall-clock for the final full run (smoke + target, final script):
  ~4 min. Seed: 20261106; instance seed = 20261106 + 100·n_orders + instance.

## 1. What was reproduced

The trip-based method's headline behaviour is exactly as the paper describes:
sub-second proven-optimal solutions at 8 and 10 orders, with trip counts in the
low hundreds — the same order of magnitude the paper reports at the smallest
sizes. Every solution was independently re-validated from scratch (the validator
recomputes cost, capacity, fuel, time windows, connected separations and
simultaneous-presence from the trip data, not from solver output) and passed
every check, with the recomputed cost matching the solver objective to the
cent on all six instances.

## 2. What was NOT reproduced (criterion 4)

The paper's compact model fails badly at 10 orders (two of three instances
unsolved at the 3600 s cap, gaps 100% and 25.2%). Mine solved all three in
12–59 s. Adding the no-simultaneous-presence disjunctions (21)–(23) and the
connected-order separation to my compact model slowed it (instance 1:
42.9 → 59.3 s) but did not break it. Candidate causes, most plausible first:

1. **My compact model is structurally simpler than the paper's.** One route
   per helicopter per day (no refuel-node sequencing, no multi-trip chaining),
   and at most one node per installation per helicopter. The paper's compact
   model has refuel nodes and lets a helicopter fly several trips in a day,
   which adds a large set of routing/sequencing binaries and weakens the LP
   bound. This is the biggest known gap.
2. **Solver generation gap.** HiGHS 1.15.1 (2025) vs Gurobi 9.0.0 (2020).
   On a model of this size (6 helicopters × 20 order nodes) the presence
   disjunctions add only 150 ordering binaries — not enough to stall a
   modern MIP solver.
3. **My generated instances are probably easier than the paper's.** My time
   windows are spread uniformly over the whole 06:00–22:00 day and my
   installations span the whole Norwegian Continental Shelf (Sleipner to
   Kvitebjorn, ~300 km apart), so installation-sharing and presence
   contention are low. The paper's instances (2018 flight records, 10
   installations in a tighter cluster) likely had tighter window clustering
   and more contention, which is exactly what makes the presence constraints
   bite.
4. Possibly further unmodelled paper features (e.g. refuelling-node
   sequencing interacting with presence).

What would be needed to test criterion 4 properly: implement the full compact
model with refuel nodes and multi-trip chaining, and/or generate harder
instances (tighter windows, clustered installations). That is follow-up work,
not part of this run.

## 3. Honest limits (do not read past these)

- **No instance data files, no seed, no repository link exist.** Instances were
  GENERATED per §5.1 rules in `scenario.yaml`, not the paper's instances.
  Every comparison is therefore structural (does the method behave the same
  way?), not numerical (did it get the same answer?).
- **No optimal objective values are printed anywhere in Tables 3–8** — only
  gaps, times, trip counts, B&B nodes. The optimum itself CANNOT be checked
  numerically against the paper. Pass/fail rests on the 0.00% gap (proven
  optimal via my own lower bound) plus the independent validity checks.
- **Trip-based model as implemented is a restriction of the paper's model:**
  trips are time-fixed at their LATEST feasible departure (searched in 5-min
  steps; the paper re-times trips inside the B&B), and helicopter capacity
  per (type, base) group is enforced via interval-clique constraints. The
  0.00% gap proves optimality WITHIN this model, not against the paper's
  stronger model.
- **Compact model as implemented deviates from the paper's:** WITH the
  no-simultaneous-presence disjunctions (21)–(23) and the connected-order
  separation, but WITHOUT refuel-node sequencing; one route per helicopter
  per day; at most one node per installation per helicopter (the paper allows
  several nodes in one visit).
- 300 s caps, not the paper's 3600 s. No Gurobi; HiGHS instead.

## 4. Assumptions used (all 16 flagged unknowns, plus build-time ones)

All values are also recorded in `scenario.yaml` and in the JSON log's
`params` / `heli_types` / `installations` sections.

- **Installations (10, real coordinates):** Sleipner A (1.9070, 58.3667),
  Gina Krog (1.6952, 58.5716), Gudrun (1.7421, 58.8446), Edvard Grieg
  (2.2467, 58.8421), Ivar Aasen (2.1965, 58.9217), Grane (2.4858, 59.1647),
  Heimdal (2.2272, 59.5736), Brage (3.0451, 60.5420), Oseberg Ost (2.9335,
  60.7000), Kvitebjorn (2.4980, 61.0798) — fetched 2026-11-06 from **Sodir
  FactMaps WGS84 FeatureServer, layer 304 "Facilities, in place"** (NLOD
  licence), all fixed jacket/concrete platforms with helipads. Fig. 2 in the
  paper is schematic only, so this is my choice of 10, not the paper's.
- **Heliports:** Sola (5.6378, 58.8767), Flesland (5.2228, 60.2934) —
  published airport coordinates.
- **Helicopter table (my values; the paper gives no table):** S-92 — 19 seats,
  260 km/h, burn 10 kg/min, tank 2500 kg, min fuel 150 kg, fixed 100,
  rate 1.0/min. Super Puma — 18 seats, 240 km/h, 9 kg/min, 2200 kg,
  150 kg, fixed 85, rate 0.9/min. Cost = flight minutes × rate + fixed per
  helicopter-day used.
- **Distance / flight time:** great-circle (haversine) on WGS84; flight time
  = distance / cruise speed of the helicopter type.
- **Fleet rule (paper):** |H| = 2·ceil(n/5)+2, evenly split over the two
  heliports → 6 helicopters for n=8 and n=10 (3 per base). Bases alternate
  Sola/Flesland by id; types alternate S-92 / Super Puma.
- **Day:** 06:00–22:00 (360–1320 min). **Time-window width:** 1 hour.
  **Order size:** uniform int 6–10. **Inter-installation share:** 25%
  (round-half-up: 2 of 8, 3 of 10).
- **Window generation (my rule):** pickup window start uniform in
  [360, 1320 − ceil(direct flight at slowest type) − 90]; delivery window =
  [pickup start + ceil(direct flight) + 30, +90]. Shore orders 50/50
  heliport→installation vs installation→heliport; heliport and installation
  uniform.
- **Landing time T^L:** 5 min at installations (0 if next stop is the same
  installation, per paper; 0 at heliports). **Turnaround T^H:** 30 min
  between trips. **Max legs per order L:** 6. **Max orders per trip:** 4
  (generator cap). **Connected separation T^C:** 60 min.
- **Connected pair (my rule, paper silent):** chosen window-feasible —
  late(to node) − early(from node) ≥ 60 min — preferring same location
  (debriefing case). An infeasible pair would make the instance infeasible
  by construction, so this filter is a generator requirement, not a paper
  property. The first version of the generator lacked this filter and
  produced an infeasible 8-order instance; the filter fixed it.
- **Trip scheduling (my rule, paper re-times trips):** trips are time-fixed
  at their LATEST feasible departure (5-min steps). Earliest departure was
  tried first and rejected: it strands the helicopter waiting hours at a
  remote heliport/installation and made the master infeasible for the wrong
  reason (artificially long trip spans exhausting the 2–3 helicopters).
- **Heliport basing tie-break, T^C values, max legs, landing/turnaround
  times:** as listed above; none are stated in the paper and all are flagged
  in `scenario.yaml`.
- Paper quirks recorded in `scenario.yaml`: §5.4 "Table 3" cross-reference
  means Table 5; Table 7 header ambiguity; Table 8 "D trips" units read as
  absolute differences.

## 5. Bugs found and fixed during this run

1. Script part 1 lost when a second write overwrote instead of appending —
   recovered by prepending from `/tmp/part1.py`.
2. `simulate_trip` treated partial DFS prefixes as complete trips (zero trips
   generated) — fixed with a `complete=False` flag for the DFS prefix screen.
3. highspy API: `highs_linear_expression()` (not `HighsLinearExpression`);
   `sol.col_value` (not `colvalue`).
4. Lazy-constraint loop for trip incompatibilities hit its 50-iteration cap
   (183 s, no solution) — assignment-variable symmetry. Rewrote the master
   as a clique / U_g formulation (no assignment variables, all
   incompatibilities upfront). Exact for interval scheduling.
5. Connected-pair generator produced a temporally impossible pair
   (see §4) — fixed with the window-feasibility filter.
6. Pyomo reserved name `m.load` → renamed `m.loadv`; objective generator
   variable scoping bug fixed.

## 6. Files

- `~/workspace/papers/nafstad2021/reproduce_table3.py` — 900+ lines,
  deterministic, reads `scenario.yaml`, generates, solves (trip-based via
  highspy, compact via Pyomo + HiGHS), validates independently, writes JSON.
- `~/workspace/papers/nafstad2021/reproduce_table3_log.json` — full machine
  log: params, helicopter table, installations, all 6 instances with orders,
  connected pairs, trip counts, solver results, validation checks.
- `~/workspace/papers/nafstad2021/reproduction_report.md` — this file.
- `~/workspace/papers/nafstad2021/reproduction_plan.md`,
  `~/workspace/papers/nafstad2021/scenario.yaml` — test design and problem
  specification (pre-existing, read before building; `scenario.yaml` parsed
  OK with `yaml.safe_load`, no fix needed).

## 7. Next steps (for the parent, not this run)

- To chase criterion 4: full compact model with refuel nodes + multi-trip
  chaining, and/or harder instances (tighter windows, clustered
  installations). Only then can the compact failure pattern be claimed
  reproduced or refuted.
- Do not scale to larger n (17–19+ orders, Tables 4–8) until the 10-order
  compact question is settled — the trip-based side is ready to scale, the
  compact comparison is not.
- Migration of this test into `offsim/papers/nafstad2021/` is the parent's
  job, after this result lands.
