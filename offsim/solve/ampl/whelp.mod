# Weekly Flight Program Planning Problem (WFPPP): the flight-based model, eqs (1)-(12) of
# Gribkovskaia and Slettemark (2025), "Tactical Helicopter Transportation Planning for Offshore Personnel on the
# Norwegian Continental Shelf", Logistics 9(2):73 (CC BY 3.0), Section 4.3 (p.14-17). Same model as the Pyomo twin
# offsim.solve.whelp.solve_full; data written by offsim.solve.whelp.write_dat.
#
# Time is discretised into slots (15 min). A flight f occupies n[f] slots from its start slot, turnaround
# included; the flight WITHOUT its turnaround (n[f] - l slots) must lie inside the operating window.
#
#   y[h,w] = 1: helicopter h gets operating window w.
#   x[h,w,f,d,t] = 1: flight f is flown by helicopter h (window w) on day d, departing in slot t.
#
# Differences of FORM to the paper (same feasible set):
#   * (5), (3) and the window part of (8) are written into the index set VALID (only starts that fit the window and the
#     opening hours of every installation on the flight get a variable); (5) is kept as x <= y.
#   * (7) and (9) together are the slot occupancy constraint: every slot of [t, t + n[f]) of a helicopter holds at most
#     one flight (two intervals overlap iff one contains the other's start).
#   * (11) is written with the helicopter's daily load ld[h,d] = sum of n[f] x, a linear definition of the same right-hand side.
#   * Helicopters are sorted by window size (symmetry breaking); not in the paper.
# Demand is in half-flights: a direct flight (F1) covers two, a split flight (F2) one per installation it serves.

set I;
set H;
set W;
set F1;
set F2;
set D;
set T;
set F := F1 union F2;

param l integer >= 0;
param b {I} >= 0;
param k {W} >= 0;
param s {W} integer >= 1;
param c {F} >= 0;
param n {F} integer >= 1;
param a {I, F} binary default 0;
param pdep {I, T} binary default 0;

param S := card(T);
set U := 0..(S + l - 1);

set VALID := {h in H, w in W, f in F, d in D, t in T:
    t + n[f] - l <= s[w] and (forall {i in I} (a[i, f] = 0 or pdep[i, t] = 1))};

var y {H, W} binary;
var x {VALID} binary;
var ld {H, D} >= 0;

# (1)
minimize total_cost:
    sum {h in H, w in W} k[w] * y[h, w]
  + sum {(h, w, f, d, t) in VALID} c[f] * x[h, w, f, d, t];

# (2) demand in half-flights
subject to demand {i in I}:
    sum {(h, w, f, d, t) in VALID: f in F1 and a[i, f] = 1} 2 * x[h, w, f, d, t]
  + sum {(h, w, f, d, t) in VALID: f in F2 and a[i, f] = 1} x[h, w, f, d, t] >= b[i];

# (4) one flight to an installation per day and start slot
subject to one_landing {i in I, d in D, t in T}:
    sum {(h, w, f, dd, tt) in VALID: dd = d and tt = t and a[i, f] = 1} x[h, w, f, dd, tt] <= 1;

# (5) a flight needs the helicopter to hold that window
subject to window_selected {(h, w, f, d, t) in VALID}:
    x[h, w, f, d, t] <= y[h, w];

# (6) one window per helicopter
subject to one_window {h in H}:
    sum {w in W} y[h, w] <= 1;

# (7) + (9) no overlap incl. turnaround, one start per slot
subject to occupancy {h in H, d in D, u in U}:
    sum {(hh, w, f, dd, t) in VALID: hh = h and dd = d and t <= u and u <= t + n[f] - 1} x[hh, w, f, dd, t] <= 1;

# (10) flights per installation differ by at most one between any two days
subject to spread_up {i in I, d in D, e in D: d < e}:
    sum {(h, w, f, dd, t) in VALID: dd = d and a[i, f] = 1} x[h, w, f, dd, t]
  - sum {(h, w, f, dd, t) in VALID: dd = e and a[i, f] = 1} x[h, w, f, dd, t] <= 1;

subject to spread_down {i in I, d in D, e in D: d < e}:
    sum {(h, w, f, dd, t) in VALID: dd = e and a[i, f] = 1} x[h, w, f, dd, t]
  - sum {(h, w, f, dd, t) in VALID: dd = d and a[i, f] = 1} x[h, w, f, dd, t] <= 1;

# (11) flight shift: every flight ends no later than the slots used by the helicopter that day (window start e_w = 0)
subject to load_def {h in H, d in D}:
    ld[h, d] = sum {(hh, w, f, dd, t) in VALID: hh = h and dd = d} n[f] * x[hh, w, f, dd, t];

subject to shift {(h, w, f, d, t) in VALID}:
    (t + n[f]) * x[h, w, f, d, t] <= ld[h, d];

# symmetry: helicopters sorted by window size
subject to sorted_fleet {h in H: h + 1 in H}:
    sum {w in W} s[w] * y[h, w] >= sum {w in W} s[w] * y[h + 1, w];
