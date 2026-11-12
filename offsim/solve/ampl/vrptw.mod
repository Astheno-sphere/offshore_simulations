# Vehicle routing with time windows (VRPTW): two-index arc formulation, MTZ load variables plus a big-M time flow.
# Twin of the Pyomo model `vrptw_exact` in offsim/solve/pyomo_solver.py: same constraints, same objective.
#
# Formulation source: capacity as in cvrp.mod (Miller, Tucker and Zemlin, 1960; Toth and Vigo (eds.), "Vehicle
# Routing: Problems, Methods, and Applications", 2nd ed., SIAM 2014, ch. 2); time windows by the usual big-M time-flow
# constraints (Desrochers, Desrosiers and Solomon, 1992, "A new optimization algorithm for the vehicle routing problem
# with time windows", Operations Research 40(2)). Check equation numbers against the sources before citing them.
#
# Data: written by offsim/solve/ampl_adapter.py (write_dat) for a Problem of class VRPTW. NODES = {0 = depot,
# 1..n = clients}, VEH = maximum number of vehicles, cap = vehicle capacity, demand[i] = units at client i,
# dist[i,j] = metres, tt[i,j] = travel seconds (dist / speed), svc[i] = service seconds, early[i] / late[i] = window
# in seconds. Vehicles leave the depot at t = 0 (as in offsim/sim/replay.py); no window on the depot.
#
# Model in words:
#   x[i,j] = 1 if a vehicle drives directly from node i to node j.
#   Every client is left once and entered once. At most VEH arcs leave the depot.
#   u[i] = load after serving client i (MTZ). t[i] = time service STARTS at client i, early[i] <= t[i] <= late[i].
#   An arc i -> j between clients forces t[j] >= t[i] + svc[i] + tt[i,j]: a vehicle that arrives early waits.
#   The first client of a route forces t[j] >= tt[0,j] (leaving at 0).
#   Objective: total distance driven.

set NODES;
set CLIENTS within NODES;
set ARCS := {i in NODES, j in NODES: i != j};

param VEH integer >= 1;
param cap > 0;
param demand {CLIENTS} >= 0;
param dist {NODES, NODES} >= 0;
param tt {NODES, NODES} >= 0;
param svc {CLIENTS} >= 0;
param early {CLIENTS} >= 0;
param late {CLIENTS} >= 0;

# tight big-M per arc: latest start at i + service + travel - earliest start at j
param bigM {i in CLIENTS, j in CLIENTS: i != j} :=
    max(0, late[i] + svc[i] + tt[i, j] - early[j]);

var x {ARCS} binary;
var u {CLIENTS} >= 0;
var t {CLIENTS} >= 0;

minimize total_distance:
    sum {(i, j) in ARCS} dist[i, j] * x[i, j];

# each client is left exactly once
subject to leave {i in CLIENTS}:
    sum {j in NODES: j != i} x[i, j] = 1;

# each client is entered exactly once
subject to enter {j in CLIENTS}:
    sum {i in NODES: i != j} x[i, j] = 1;

# at most VEH routes
subject to fleet_limit:
    sum {j in CLIENTS} x[0, j] <= VEH;

# load bounds
subject to load_min {i in CLIENTS}:
    demand[i] <= u[i];

subject to load_max {i in CLIENTS}:
    u[i] <= cap;

# MTZ load propagation (as in cvrp.mod)
subject to mtz {i in CLIENTS, j in CLIENTS: i != j}:
    u[i] - u[j] + cap * x[i, j] <= cap - demand[j];

# time windows
subject to window_open {i in CLIENTS}:
    early[i] <= t[i];

subject to window_close {i in CLIENTS}:
    t[i] <= late[i];

# first client of a route: leave the depot at 0 and drive
subject to depot_start {j in CLIENTS}:
    t[j] >= tt[0, j] * x[0, j];

# time flow between clients: t[j] >= t[i] + svc[i] + tt[i,j] when i -> j is driven (slack by bigM otherwise)
subject to time_flow {i in CLIENTS, j in CLIENTS: i != j}:
    t[i] - t[j] + bigM[i, j] * x[i, j] <= bigM[i, j] - svc[i] - tt[i, j];
