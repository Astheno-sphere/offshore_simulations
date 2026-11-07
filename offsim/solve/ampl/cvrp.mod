# Capacitated vehicle routing (CVRP), two-index formulation with Miller-Tucker-Zemlin (MTZ) load variables.
#
# Formulation source: the textbook MTZ construction (Miller, Tucker and Zemlin, 1960), in the capacity form
# used for vehicle routing in Toth and Vigo (eds.), "Vehicle Routing: Problems, Methods, and Applications",
# 2nd ed., SIAM 2014, chapter 2 (two-index formulation, load constraints). Check the equation numbers
# against the book before citing them in a paper.
#
# Data: written by offsim/solve/ampl_adapter.py (write_dat). NODES = {0 = depot, 1..n = clients},
# VEH = maximum number of vehicles, cap = vehicle capacity, demand[i] = units at client i,
# dist[i,j] = metres between nodes i and j.
#
# Model in words:
#   x[i,j] = 1 if a vehicle drives directly from node i to node j.
#   Every client is left once and entered once. At most VEH arcs leave the depot.
#   u[i] = load on board after serving client i, with demand[i] <= u[i] <= cap.
#   An arc i -> j between clients forces u[j] >= u[i] + demand[j], so no cycle avoids the depot.
#   Objective: total distance driven.

set NODES;
set CLIENTS within NODES;
set ARCS := {i in NODES, j in NODES: i != j};

param VEH integer >= 1;
param cap > 0;
param demand {CLIENTS} >= 0;
param dist {NODES, NODES} >= 0;

var x {ARCS} binary;
var u {CLIENTS} >= 0;

minimize total_distance:
    sum {(i, j) in ARCS} dist[i, j] * x[i, j];

# each client is left exactly once
subject to leave {i in CLIENTS}:
    sum {j in NODES: j != i} x[i, j] = 1;

# each client is entered exactly once
subject to enter {j in CLIENTS}:
    sum {i in NODES: i != j} x[i, j] = 1;

# at most VEH routes (the depot's in- and out-degree balance follows from leave and enter)
subject to fleet_limit:
    sum {j in CLIENTS} x[0, j] <= VEH;

# load bounds
subject to load_min {i in CLIENTS}:
    demand[i] <= u[i];

subject to load_max {i in CLIENTS}:
    u[i] <= cap;

# MTZ load propagation: if i -> j is used, the load after j includes j's demand.
# When x[i,j] = 0 the constraint is always satisfied, because u[i] <= cap and u[j] >= demand[j].
subject to mtz {i in CLIENTS, j in CLIENTS: i != j}:
    u[i] - u[j] + cap * x[i, j] <= cap - demand[j];
