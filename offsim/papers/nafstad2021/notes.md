# Nafstad et al. (2021) — reading notes

**Paper:** Nafstad, Haugseth, Høyland & Stålhane, "An exact solution method for a
rich helicopter flight scheduling problem arising in offshore oil and gas
logistics", *Computers & Operations Research* 128 (2021) 105158,
DOI 10.1016/j.cor.2020.105158. Open access CC BY 4.0. NTNU, Department of
Industrial Economics and Technology Management. Data from 2018 flight records
on the Norwegian continental shelf, via TietoEVRY.

## What the problem is

Every day, helicopters must move offshore personnel between two onshore
heliports (Bergen Flesland and Stavanger Sola) and ten offshore installations,
and sometimes between installations themselves — e.g. between a flotel and a
production platform, or moving experts from one platform to another. In 2018
there were over 350,000 personnel deployments on the Norwegian continental
shelf, about 1,000 people a day, and one operator estimates annual helicopter
costs around 2 billion NOK. Today the flying is planned manually; the paper
argues optimisation can save significant money.

Personnel going from the same place to the same place, with the same time
restrictions and dependencies, are aggregated into one **order**: a pickup node
and a delivery node, a number of people, and a time window (earliest and latest
service time). The fleet is **heterogeneous** — helicopters differ in seats,
fixed daily cost, fuel burn per hour, and tank size — and each helicopter is
based at one heliport and starts and ends its day there. A **trip** is one
outing from a heliport to some installations and back; a **route** is the
sequence of trips one helicopter flies in a day, with refuelling (heliports
only) and pilot rest between trips.

The problem is a rich vehicle routing problem: pickup-and-delivery, multiple
depots, heterogeneous fleet, multi-trip, time windows, plus **temporal
synchronisation** — some orders are *connected*: a replacement must arrive a
minimum time before the person being replaced can leave (debriefing), or
someone flying out and back in one day needs enough time on the installation to
do their job. And because an installation usually has a single helipad, no two
helicopters may be at the same installation at the same time. Safety rules cap
the number of legs a passenger may travel between pickup and delivery; time at
an installation is constant regardless of how many people get on or off;
flight time and fuel use depend on distance and cruising speed, not on wind or
load. The objective is to fly all orders at minimum cost (distance cost plus
the fixed cost of each helicopter used).

## The compact formulation (Section 3.1, one paragraph)

The compact model is an arc-flow formulation on a graph whose nodes are the
pickup and delivery points plus start, refuelling and end nodes at the
heliports. Binary variables say whether helicopter *h* flies arc *(i,j)* as leg
*k* of its day, with extra variables tracking passengers on board, fuel level
and arrival time at each node, whether a helicopter is used at all, and two
helper variables that encode which helicopter serves which node-pair and in
which order — the machinery that enforces the no-two-helicopters-at-once rule.
Constraints (2)–(28) make sure every order is served exactly once by one
helicopter, routes are continuous and start/end at the right heliport, leg
numbers are consistent, no order exceeds the leg cap, fuel stays within bounds,
capacity is respected, time windows hold, connected orders keep their minimum
separation, and no installation is visited by two helicopters simultaneously.
It is a correct model, but a weak one computationally: in the tests it cannot
solve 10-order instances reliably, and at 12 orders and above it finds nothing
— not even a feasible solution — within an hour.

## The extended (trip-based) formulation (Section 3.2, one paragraph)

The trip-based model turns the problem inside out. Instead of deciding
arc by arc, it first generates **all feasible trips** — every heliport →
installations → heliport sequence a helicopter could legally fly — and then
the model just picks trips and strings them into routes: binary variable
*k_hrs* = 1 if helicopter *h* flies trip *r* as its *s*-th trip of the day.
Constraints make sure every order is covered, each helicopter flies at most
one trip per trip-number, trips are used in order, trip start times respect
each trip's earliest/latest start, consecutive trips leave room for
refuelling/rest, connected orders keep their separation, and the
no-simultaneous-presence rule holds. The model is much smaller in the
variables that matter, but it depends entirely on being able to enumerate all
trips up front — which is where the labelling algorithm (Section 4.1) comes
in. A label is a partial path plus resources: open orders, unreachable orders,
legs travelled per order, fuel left, earliest/latest arrival, and a time
counter for connected orders. Labels are extended arc by arc and discarded
whenever a resource window is violated, so only feasible trips survive. The
paper also preprocesses arcs (13 removal rules) and narrows time windows for
connected orders, which cuts the trip count dramatically.

## Delayed constraint generation (Section 4.2)

The expensive part of the trip-based model is the no-two-helicopters-at-once
machinery: constraints (36)–(43) involve dense big-M formulations and an
exponential number of ordering variables. The obvious fix — the commercial
solver's own *lazy constraints* — works, but weakly, because the constraints
are dense and each one touches many trips. So the authors reformulate that
part of the model as an exponential family of very sparse constraints (each
involving exactly five variables), **leave them out of the model entirely**,
solve the relaxed model by branch-and-bound, and every time an integer
solution turns up, check it against the omitted constraints: if it violates
any, add just those constraints and re-solve the node; if it violates none,
it is a valid primal bound. That is delayed constraint generation. It also
applies to the connected-order time constraints (36)–(37), rewritten to fire
only for nodes that are actually in a connected pair. The payoff is in the
numbers: with many connected orders, DCG solves 43 of 45 test instances to
optimality against 39 for lazy constraints and 30 for plain branch-and-bound,
at roughly half the lazy method's average time — even though DCG's
branch-and-bound trees are far larger, because each node solves much faster
(fewer, sparser constraints).

## How the test instances were generated (Section 5.1)

Input came from 2018 flight records. The two heliports are Bergen Flesland
and Stavanger Sola, the two busiest on the shelf, plus ten installations that
have frequent flights to both heliports and are reachable from both — a fully
connected network. (The installations are **not named** and no coordinates are
given; Figure 2 is a schematic map.) Each instance is defined by: number of
orders; personnel per order (drawn randomly, 6–10 people); pickup and delivery
location of each order; a one-hour-wide time window per order; and which orders
are connected, with their required time differences. Three instances were
generated per instance size. Orders between installations were set to 25% of
the total — deliberately high (flight records suggest ~5% is realistic) to
force more coordination between helicopters. The fleet is Super Puma and
Sikorsky S-92 helicopters (the two most used types on the shelf); fleet size
is 2·⌈n/5⌉ + 2 for n orders, evenly split between the two heliports — "just
large enough to make the instance feasible", since using fewer helicopters is
part of the objective. Tests ran in Gurobi 9.0.0 on a Lenovo NextScale nx360 M5
(Intel E5-2643v3 six-core 2×3.40 GHz, 512 GB, Linux); trip generation and
instance generation were written in C++. Time limit: one hour per instance.

## What the results show (Section 5, headline only — full tables in reproduction_plan.md)

- **Table 3 (8–16 orders):** the compact model solves 8-order instances but
  collapses at 10+; the trip-based model solves all 15 instances to optimality
  in under 2 seconds.
- **Table 4:** trip generation takes under a minute up to 40 orders and under
  12 minutes worst-case up to 52 orders, but the number of trips explodes
  (up to ~10.9 million for one 44–46-order instance).
- **Table 5 (17–52 orders):** plain B&B solves 44/108, lazy 53/108, DCG
  52/108 to optimality; all instances up to 25 orders are solved by all
  methods; none above 40 orders by any.
- **Table 6 (30 orders, 0–8 connected pairs):** DCG clearly wins — 43/45
  optimal, average time 915 s vs 1,422 s (lazy) and 2,496 s (B&B).
- **Table 8 (one vs two heliports):** the method works about as well with a
  single heliport (Sola only); objective values rise slightly (+0.15–1.99%).

## What is NOT in the paper (and therefore cannot be reproduced exactly)

No instance files, no repository, no supplementary data, no random seed. No
coordinates or names for the ten installations. No helicopter parameters at
all — no seat counts (except the S-92's 19 seats, mentioned as background),
no speeds, fuel burn, tank sizes or fixed costs. No cost units. No landing
time, no turnaround time, no maximum-legs number, no connected-order time
differences, no rule for drawing time-window start times or order locations.
And no optimal objective *values* are printed anywhere — the tables report
only gaps, times, trip counts and node counts. So a reproduction can never
match the paper instance-by-instance; it can only rebuild the same *kind* of
instances from the stated generation rules, solve them, and compare the
aggregate pattern. That is exactly what reproduction_plan.md is designed to do.
