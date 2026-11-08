# Gap: does the lean optimal fleet survive a real North Sea winter?

Paper: Gribkovskaia & Slettemark (2025), Tactical Helicopter Transportation Planning for Offshore Personnel on the
NCS, Logistics 9(2):73, CC BY 3.0. Weekly Flight Program Planning Problem (WFPPP), deterministic.

What the paper found (Table 4, p.29): optimal programs need one helicopter fewer than Equinor's actual resources at
every heliport (Florø 1 vs 2, Stavanger 2 vs 3, Bergen 4 vs 5), cost -41/-20/-15 %, utilisation 87-96 %.
What the paper does not model (p.35): flight cancellations, postponed flights and delays caused by installations'
operational needs and weather; planners protect the week with time slacks, but the amount is not optimised or tested.

Question (pre-registered): run the optimal Bergen program (4 helicopters, windows 16/14/10/10 h) and the actual
resources (5 helicopters) through every NORA3 winter week; flights whose departure hour exceeds helideck/flight
limits are cancelled and rebooked into the remaining weekly capacity.
KPI: unmet half-flights per week, delayed passengers, recovery time.
Decision rule: the lean fleet is "winter-robust" if P90 unmet flights/week <= 1 (assumption, to confirm).
Status words: supported | not supported | inconclusive (experiment.decide).

Data from the paper: Tables A1-A3 (demand, opening hours), Table 3 (window costs), p.25 (125 kn, 10 min deck,
1 h turnaround, 15 min slots, split threshold 15 min, flight-hour cost 140 masked units).
Not in the paper: installation positions (masked; 50-120 nm) -> assumed positions calibrated so the reproduced
optimal costs match Table 4; weather limits -> sourced (CAP 437 / NORSOK / operator manuals) or assumption: true.
