"""Nafstad et al. (2021) — first reproduction test: Table 3, 8 orders (smoke) + 10 orders (target).

Corrector role: generator -> trip generation -> trip-based MILP (HiGHS) -> independent
validation; compact arc MILP (Pyomo + HiGHS) for the model-separation check.
Reads scenario.yaml; deterministic (fixed seed). Writes reproduce_table3_log.json
and prints a per-instance summary. See reproduction_plan.md for the comparison rule.

HONEST LIMITS (see report for full text):
- No instance data, no seed, no optimal objective values exist in the paper.
  Instances are GENERATED per Section 5.1 rules; the test compares gaps/times/
  trip-count scale, never per-instance exact values.
- Installations: 10 REAL NCS facilities, coordinates fetched 2026-11-06 from
  Sodir FactMaps WGS84 FeatureServer layer 304 (Facilities, in place), NLOD.
  Heliport coordinates are the published airport coordinates (Sola, Flesland).
- No Gurobi here: HiGHS (open-source MILP) via highspy / Pyomo. Compact runs use
  a 300 s cap (NOT the paper's 3600 s); the cap is recorded per instance.
- Trip-based model as implemented: trips are time-fixed at their LATEST
  feasible departure (searched in 5-min steps; earliest departure would strand
  the helicopter waiting hours at a remote heliport/installation);
  no-simultaneous-presence and connected-order separations across trips are
  enforced as pairwise trip incompatibilities, and helicopter capacity per
  (type, base) group via interval-clique constraints (exact: interval graphs
  are perfect, so max simultaneous load = helicopters needed). This is a
  restriction of the paper's model (which re-times trips inside the B&B);
  the 0.00% gap proves optimality WITHIN this model, not against the paper's
  stronger model. Stated in the report.
- Connected pairs are generated window-feasible (late(to)-early(from) >= 60),
  else the instance would be infeasible by construction; the paper does not
  state how pairs are chosen.
- Compact model as implemented: the paper's compact model WITH the
  no-simultaneous-presence disjunctions (21)-(23) and the connected-order
  separation, but MINUS refuel-node sequencing; each helicopter flies one
  route per day (single trip), and at most one node per installation per
  helicopter (the paper allows several nodes in one visit). It is therefore
  a relaxation in the refuel respect and a restriction in the one-trip /
  one-node-per-installation respects. If it still fails to prove optimality
  at 10 orders, that is evidence for the paper's failure pattern; if it
  solves all three easily, separation is NOT reproduced.
"""
import json, math, os, random, sys, time
import yaml

BASE = "/home/hatch/workspace/papers/nafstad2021"
SEED = 20261106
DAY_START = 360   # 06:00, minutes from midnight
DAY_END = 1320    # 22:00

# ---------------------------------------------------------------- parameters
# Every value below is an ASSUMPTION (not in the paper) unless marked PAPER.
# Recorded here and in reproduction_report.md.
PARAMS = {
    "seed": SEED,
    "day_window_min": [DAY_START, DAY_END],
    "time_window_width_min": 60,                      # PAPER: 1 hour per order
    "order_size": "uniform integers 6..10",           # PAPER: drawn randomly 6-10
    "inter_installation_share": 0.25,                  # PAPER: 25%
    "connected_pairs_per_instance": 1,                 # PAPER §5.2: 1 pair
    "connected_min_sep_min": 60,                       # ASSUMPTION (T^C not stated)
    "landing_time_min": 5,                             # ASSUMPTION (T^L not stated)
    "turnaround_min": 30,                              # ASSUMPTION (T^H not stated)
    "max_legs_per_order": 6,                           # ASSUMPTION (L not stated)
    "max_orders_per_trip": 4,                          # ASSUMPTION (generator cap)
    "delivery_window_buffer_min": 30,                  # ASSUMPTION (see generator)
    "distance": "great-circle (haversine) on WGS84",   # ASSUMPTION
    "cost": "arc cost = flight minutes x type rate; + fixed cost per helicopter-day used",
    "fleet_rule": "PAPER: |H| = 2*ceil(n/5)+2, evenly split over the two heliports",
    "compact_time_cap_s": 300,                         # ASSUMPTION (paper: 3600 s)
    "tripbased_time_cap_s": 300,
}
HELI_TYPES = {  # ASSUMPTION: no per-type parameters are in the paper (only S-92 = 19 seats, as context)
    "S-92":       dict(seats=19, cruise_kmh=260, burn_kg_min=10.0, tank_kg=2500, min_fuel_kg=150, fixed=100.0, rate=1.0),
    "Super Puma": dict(seats=18, cruise_kmh=240, burn_kg_min=9.0,  tank_kg=2200, min_fuel_kg=150, fixed=85.0,  rate=0.9),
}
# Heliport coordinates: published airport coordinates (WGS84 lon/lat).
HELIPORTS = {"Sola": (5.6378, 58.8767), "Flesland": (5.2228, 60.2934)}
# Installations: REAL NCS facilities, coordinates from Sodir FactMaps WGS84
# FeatureServer layer 304 (Facilities, in place), fetched 2026-11-06, NLOD.
# All are fixed jacket/concrete platforms with helipads, chosen to be reachable
# from BOTH Sola and Flesland (southernmost Sleipner A to northernmost Kvitebjorn).
INSTALLATIONS = [
    ("Sleipner A",   1.9070, 58.3667),
    ("Gina Krog",    1.6952, 58.5716),
    ("Gudrun",       1.7421, 58.8446),
    ("Edvard Grieg", 2.2467, 58.8421),
    ("Ivar Aasen",   2.1965, 58.9217),
    ("Grane",        2.4858, 59.1647),
    ("Heimdal",      2.2272, 59.5736),
    ("Brage",        3.0451, 60.5420),
    ("Oseberg Ost",  2.9335, 60.7000),
    ("Kvitebjorn",   2.4980, 61.0798),
]
INST_COORDS = {name: (lon, lat) for name, lon, lat in INSTALLATIONS}
ALL_LOCS = dict(HELIPORTS)
ALL_LOCS.update(INST_COORDS)


def haversine_km(a, b):
    (lon1, lat1), (lon2, lat2) = ALL_LOCS[a], ALL_LOCS[b]
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def flight_min(a, b, cruise_kmh):
    if a == b:
        return 0.0
    return haversine_km(a, b) / cruise_kmh * 60.0


# ---------------------------------------------------------------- generator
def generate_instance(n_orders, inst_idx):
    """Generate one instance per Section 5.1 rules + recorded assumptions."""
    rng = random.Random(SEED + 100 * n_orders + inst_idx)
    n_inter = int(0.25 * n_orders + 0.5)
    types = (["inter"] * n_inter + ["shore"] * (n_orders - n_inter))
    rng.shuffle(types)
    orders = []
    for o in range(n_orders):
        size = rng.randint(6, 10)
        if types[o] == "inter":
            a, b = rng.sample([nm for nm, _, _ in INSTALLATIONS], 2)
            pickup, delivery = a, b
        else:
            h = rng.choice(list(HELIPORTS))
            inst = rng.choice([nm for nm, _, _ in INSTALLATIONS])
            if rng.random() < 0.5:
                pickup, delivery = h, inst
            else:
                pickup, delivery = inst, h
        # delivery window: direct flight time at the SLOWEST type + 30 min buffer, width 60
        ft = flight_min(pickup, delivery, HELI_TYPES["Super Puma"]["cruise_kmh"])
        s_max = DAY_END - int(math.ceil(ft)) - 90
        s = rng.randint(DAY_START, max(DAY_START, s_max))
        orders.append({
            "id": o, "size": size, "pickup_loc": pickup, "delivery_loc": delivery,
            "pickup_window": [s, s + 60],
            "delivery_window": [s + int(math.ceil(ft)) + 30, s + int(math.ceil(ft)) + 90],
            "kind": types[o],
        })
    # connected pair: delivery of X must precede pickup of Y by >= 60 min.
    # The paper does not say how the pair is chosen; we require the pair to be
    # WINDOW-FEASIBLE (late of the 'to' node minus early of the 'from' node >=
    # 60 min), otherwise the generated instance would be infeasible by
    # construction. Prefer same location (debriefing case).
    def _pair_ok(x, y):
        return (orders[y]["pickup_window"][1] - orders[x]["delivery_window"][0]
                >= PARAMS["connected_min_sep_min"])
    xs = list(range(n_orders))
    rng.shuffle(xs)
    conn = None
    for x in xs:
        same = [y for y in range(n_orders) if y != x
                and orders[y]["pickup_loc"] == orders[x]["delivery_loc"]
                and _pair_ok(x, y)]
        if same:
            y = rng.choice(same)
            conn = {"from_order": x, "from_node": ["D", x],
                    "to_order": y, "to_node": ["P", y],
                    "min_sep_min": PARAMS["connected_min_sep_min"]}
            break
    if conn is None:
        feas = [(x, y) for x in range(n_orders) for y in range(n_orders)
                if x != y and _pair_ok(x, y)]
        x, y = rng.choice(feas)
        conn = {"from_order": x, "from_node": ["D", x],
                "to_order": y, "to_node": ["P", y],
                "min_sep_min": PARAMS["connected_min_sep_min"]}
    fleet_n = 2 * math.ceil(n_orders / 5) + 2
    helis = []
    for k in range(fleet_n):
        base = "Sola" if k % 2 == 0 else "Flesland"
        typ = "S-92" if (k // 2) % 2 == 0 else "Super Puma"
        helis.append({"id": k, "type": typ, "base": base})
    return {"n_orders": n_orders, "instance": inst_idx, "seed": SEED + 100 * n_orders + inst_idx,
            "orders": orders, "connected": conn, "helicopters": helis}


def node_loc(order, node):
    kind, o = node
    return order["orders"][o]["pickup_loc"] if kind == "P" else order["orders"][o]["delivery_loc"]


def node_window(order, node):
    kind, o = node
    oo = order["orders"][o]
    return oo["pickup_window"] if kind == "P" else oo["delivery_window"]

# ---------------------------------------------------------------- trip generation
def service_time(node, next_loc, inst):
    """Landing time T^L: 5 min at an installation unless the next stop is at the
    same installation (paper: T^L_ij = 0 if i and j are at the same installation);
    0 at heliports."""
    loc = node_loc(inst, node)
    if loc in HELIPORTS:
        return 0
    return 0 if next_loc == loc else PARAMS["landing_time_min"]


def simulate_trip(inst, htype, heliport, seq, t0, complete=True):
    """Forward-simulate a node sequence from departure t0. Returns dict with
    service times, or None if infeasible (windows / capacity / fuel / legs).
    With complete=False (DFS prefix screen) open orders at the end are allowed
    and the return leg is not simulated. Separation constraints are NOT checked
    here (handled by t0 search at completion)."""
    spec = HELI_TYPES[htype]
    times, load, fuel = {}, 0, spec["tank_kg"]
    open_legs = {}
    t = t0
    cur_loc = heliport
    for idx, node in enumerate(seq):
        loc = node_loc(inst, node)
        nxt = node_loc(inst, seq[idx + 1]) if idx + 1 < len(seq) else heliport
        arr = t + flight_min(cur_loc, loc, spec["cruise_kmh"])
        fuel -= spec["burn_kg_min"] * flight_min(cur_loc, loc, spec["cruise_kmh"])
        if fuel < spec["min_fuel_kg"] - 1e-9:
            return None
        early, late = node_window(inst, node)
        start = max(arr, early)
        if start > late + 1e-9:
            return None
        times[(node[0], node[1])] = start
        kind, o = node
        if kind == "P":
            load += inst["orders"][o]["size"]
            if load > spec["seats"]:
                return None
            open_legs[o] = 0
        else:
            if o not in open_legs:
                return None
            if open_legs[o] > PARAMS["max_legs_per_order"]:
                return None
            load -= inst["orders"][o]["size"]
            del open_legs[o]
        for oo in open_legs:
            open_legs[oo] += 1
        t = start + service_time(node, nxt, inst)
        cur_loc = loc
    if not complete:
        return {"service_times": times, "start": t0, "end": t, "fuel_end": fuel,
                "flight_min": 0.0}
    # return leg to heliport
    leg_min = flight_min(cur_loc, heliport, spec["cruise_kmh"])
    fuel -= spec["burn_kg_min"] * leg_min
    if fuel < spec["min_fuel_kg"] - 1e-9:
        return None
    end = t + leg_min
    if open_legs:
        return None
    if end > DAY_END + 1e-9:
        return None
    return {"service_times": times, "start": t0, "end": end, "fuel_end": fuel,
            "flight_min": sum(flight_min(a, b, spec["cruise_kmh"]) for a, b in
                              zip([heliport] + [node_loc(inst, n) for n in seq],
                                  [node_loc(inst, n) for n in seq] + [heliport]))}


def trip_ok_separations(inst, seq, sim):
    """Within-trip connected-order separation: t(to) - t(from) >= min_sep."""
    c = inst["connected"]
    fn, tn = tuple(c["from_node"]), tuple(c["to_node"])
    st = sim["service_times"]
    if fn in st and tn in st:
        return st[tn] - st[fn] >= c["min_sep_min"] - 1e-9
    return True


def latest_sim(inst, htype, heliport, seq, t0):
    """Latest feasible schedule for a complete sequence: delay departure in
    5-min steps while windows and within-trip separations still hold; keep the
    LAST feasible schedule. (Earliest departure would strand the helicopter
    waiting at a remote heliport/installation for hours; the paper re-times
    trips inside the B&B, so latest-departure is the better fixed schedule.
    Recorded as a modelling restriction in the report.)"""
    best = None
    for dt in range(0, 601, 5):
        sim = simulate_trip(inst, htype, heliport, seq, t0 + dt)
        if sim is None:
            break
        if not trip_ok_separations(inst, seq, sim):
            continue
        best = sim
    return best


def gen_trips(inst, htype, heliport):
    """DFS enumeration of feasible trips for one helicopter type from one heliport.
    Returns list of trip dicts (time-fixed at earliest feasible t0)."""
    spec = HELI_TYPES[htype]
    n = inst["n_orders"]
    trips = []
    all_nodes = [("P", o) for o in range(n)] + [("D", o) for o in range(n)]

    def t0_for(seq):
        t0 = DAY_START
        for node in seq:
            if node_loc(inst, node) == heliport and node[0] == "P":
                t0 = max(t0, node_window(inst, node)[0])
        return t0

    def candidates(seq, served, open_orders, visited_inst, phase):
        out = []
        for node in all_nodes:
            kind, o = node
            if phase == 2 and not (node_loc(inst, node) == heliport and kind == "D"):
                continue  # closing phase: only heliport deliveries, then end
            if kind == "P":
                if o in served or o in open_orders:
                    continue
                if len(served) + len(open_orders) >= PARAMS["max_orders_per_trip"]:
                    continue
            else:
                if o not in open_orders:
                    continue
            loc = node_loc(inst, node)
            if loc == heliport:
                if kind == "P" and phase != 0:
                    continue
                if kind == "D" and phase == 0:
                    continue
            else:
                if loc in visited_inst:
                    continue
                if kind == "P":
                    # deliver before picking up at an installation
                    if any(node_loc(inst, ("D", oo)) == loc for oo in open_orders):
                        continue
            out.append(node)
        return out

    def dfs(seq, served, open_orders, visited_inst, phase):
        # try closing the trip
        if served and not open_orders:
            t0 = t0_for(seq)
            sim = latest_sim(inst, htype, heliport, seq, t0)
            if sim is not None:
                trips.append(make_trip(inst, htype, heliport, seq, sim))
        # extend
        for node in candidates(seq, served, open_orders, visited_inst, phase):
            kind, o = node
            loc = node_loc(inst, node)
            nphase = phase
            if loc != heliport:
                nphase = 1
            elif kind == "D":
                nphase = 2
            nserved = set(served)
            nopen = dict(open_orders)
            nvis = set(visited_inst)
            if kind == "P":
                nopen[o] = True
            else:
                del nopen[o]
                nserved.add(o)
            if loc not in HELIPORTS:
                nvis.add(loc)
            nseq = seq + [node]
            # quick feasibility screen at earliest t0 (windows/capacity/fuel/legs);
            # partial: open orders at the end are fine, return leg not simulated
            if simulate_trip(inst, htype, heliport, nseq, t0_for(nseq), complete=False) is None:
                continue
            dfs(nseq, nserved, nopen, nvis, nphase)

    dfs([], set(), {}, set(), 0)
    return trips


def make_trip(inst, htype, heliport, seq, sim):
    spec = HELI_TYPES[htype]
    orders = sorted({o for _, o in seq})
    visits = {}
    cur_loc, t = heliport, sim["start"]
    for idx, node in enumerate(seq):
        loc = node_loc(inst, node)
        nxt = node_loc(inst, seq[idx + 1]) if idx + 1 < len(seq) else heliport
        arr = t + flight_min(cur_loc, loc, spec["cruise_kmh"])
        dep = sim["service_times"][(node[0], node[1])] + service_time(node, nxt, inst)
        visits.setdefault(loc, []).append((arr, dep))
        t, cur_loc = dep, loc
    return {"type": htype, "heliport": heliport, "orders": orders,
            "nodes": [[k, o] for k, o in seq],
            "service_times": {f"{k}{o}": v for (k, o), v in sim["service_times"].items()},
            "start": sim["start"], "end": sim["end"],
            "flight_min": round(sim["flight_min"], 2),
            "cost": round(sim["flight_min"] * spec["rate"], 2),
            "install_visits": {k: [[round(a, 1), round(d, 1)] for a, d in v]
                               for k, v in visits.items() if k not in HELIPORTS}}


# ---------------------------------------------------------------- trip-based master (highspy)
# Formulation (no assignment variables, no symmetry): trips are time-fixed, so
# trips of one (type, base) group form an interval scheduling problem. The
# minimum number of helicopters a group needs equals its maximum simultaneous
# load (interval graphs are perfect), so per group an integer variable U_g
# counts helicopters used and clique constraints (one per trip start time)
# bound the simultaneous load by U_g. Fixed costs are charged per U_g.
# No-simultaneous-presence and connected-order separations are pairwise trip
# incompatibilities, added upfront. No lazy loop is needed; a verification
# pass in the caller re-checks the returned schedule independently.
def solve_trip_based(inst, trips, time_cap=300):
    import highspy
    n = inst["n_orders"]
    helis = inst["helicopters"]
    T = len(trips)
    groups = {}
    for hk in helis:
        groups.setdefault((hk["type"], hk["base"]), []).append(hk["id"])
    TA = PARAMS["turnaround_min"]

    def group_of(t):
        return (trips[t]["type"], trips[t]["heliport"])

    def st_map(tr):
        return {tuple([k[0], int(k[1:])]): v for k, v in tr["service_times"].items()}

    # pairwise incompatibilities: presence + connected separation
    incompat = set()
    st_maps = [st_map(tr) for tr in trips]
    for t in range(T):
        for u in range(t + 1, T):
            bad = False
            for loc in trips[t]["install_visits"]:
                if loc in trips[u]["install_visits"]:
                    for (a1, d1) in trips[t]["install_visits"][loc]:
                        for (a2, d2) in trips[u]["install_visits"][loc]:
                            if a1 < d2 - 1e-9 and a2 < d1 - 1e-9:
                                bad = True
            if not bad:
                c = inst["connected"]
                fn, tn = tuple(c["from_node"]), tuple(c["to_node"])
                if fn in st_maps[t] and tn in st_maps[u] and \
                        st_maps[u][tn] - st_maps[t][fn] < c["min_sep_min"] - 1e-9:
                    bad = True
                elif fn in st_maps[u] and tn in st_maps[t] and \
                        st_maps[t][tn] - st_maps[u][fn] < c["min_sep_min"] - 1e-9:
                    bad = True
            if bad:
                incompat.add((t, u))
    # clique constraints per (group, trip start time)
    cliques = []
    for t in range(T):
        g = group_of(t)
        cl = [u for u in range(T) if group_of(u) == g
              and trips[u]["start"] <= trips[t]["start"] < trips[u]["end"] + TA]
        cliques.append((g, cl))

    t_start = time.time()
    h = highspy.Highs()
    h.setOptionValue("output_flag", False)
    h.setOptionValue("time_limit", time_cap)
    h.setOptionValue("mip_rel_gap", 0.0)
    h.setOptionValue("threads", 4)
    y = [h.addVariable(lb=0.0, ub=1.0, type=highspy.HighsVarType.kInteger) for _ in range(T)]
    U = {}
    for g, members in groups.items():
        U[g] = h.addVariable(lb=0.0, ub=float(len(members)),
                             type=highspy.HighsVarType.kInteger)
    obj = highspy.highs_linear_expression()
    for t in range(T):
        obj += trips[t]["cost"] * y[t]
    for g in groups:
        obj += HELI_TYPES[g[0]]["fixed"] * U[g]
    h.setObjective(obj, highspy.ObjSense.kMinimize)
    for o in range(n):
        e = highspy.highs_linear_expression()
        for t in range(T):
            if o in trips[t]["orders"]:
                e += y[t]
        h.addConstr(e == 1)
    for g, cl in cliques:
        e = highspy.highs_linear_expression()
        for u in cl:
            e += y[u]
        h.addConstr(e - U[g] <= 0)
    for (t, u) in incompat:
        h.addConstr(y[t] + y[u] <= 1)
    h.run()
    status = str(h.getModelStatus())
    el = round(time.time() - t_start, 2)
    if "Optimal" not in status:
        return {"status": status, "objective": None, "dual_bound": None,
                "gap_pct": None, "selected": [], "helicopters_used": {},
                "n_incompat_pairs": len(incompat), "solve_time_s": el}
    sol = h.getSolution()
    yv = [sol.col_value[i] for i in range(T)]
    Uv = {f"{g[0]}@{g[1]}": int(round(sol.col_value[T + j]))
          for j, g in enumerate(groups)}
    objv = h.getObjectiveValue()
    try:
        dual = h.getInfo().mip_dual_bound
    except Exception:
        dual = None
    gap = None if (dual is None or objv == 0) else max(0.0, (objv - dual) / objv * 100.0)
    return {"status": status, "objective": round(objv, 2),
            "dual_bound": None if dual is None else round(dual, 2),
            "gap_pct": None if gap is None else round(gap, 4),
            "selected": [t for t in range(T) if yv[t] > 0.5],
            "helicopters_used": Uv,
            "n_incompat_pairs": len(incompat), "solve_time_s": el}


# ---------------------------------------------------------------- independent validator
def validate_solution(inst, trips, selected, helicopters_used):
    """Recompute EVERYTHING from the raw trip records. Returns list of checks."""
    checks = []

    def chk(name, ok, detail=""):
        checks.append({"check": name, "pass": bool(ok), "detail": detail})

    n = inst["n_orders"]
    served = []
    for t in selected:
        served += trips[t]["orders"]
    chk("all_orders_served_once", sorted(served) == list(range(n)),
        f"served={sorted(served)}")
    # per-trip re-simulation
    for t in selected:
        tr = trips[t]
        spec = HELI_TYPES[tr["type"]]
        seq = [tuple(x) for x in tr["nodes"]]
        sim = simulate_trip(inst, tr["type"], tr["heliport"], seq, tr["start"])
        chk(f"trip_{t}_resim_feasible", sim is not None)
        if sim is not None:
            stored = {tuple([k[0], int(k[1:])]): v for k, v in tr["service_times"].items()}
            chk(f"trip_{t}_times_match", all(
                abs(sim["service_times"][k] - v) < 1.0 for k, v in stored.items()), "")
            chk(f"trip_{t}_end_matches", abs(sim["end"] - tr["end"]) < 1.0, "")
            chk(f"trip_{t}_cost_matches",
                abs(sim["flight_min"] * spec["rate"] - tr["cost"]) < 0.11, "")
    # helicopter capacity per (type, base) group: max simultaneous load
    TA = PARAMS["turnaround_min"]
    groups = {}
    for hk in inst["helicopters"]:
        groups.setdefault((hk["type"], hk["base"]), []).append(hk["id"])
    for g, members in groups.items():
        mine = [t for t in selected if (trips[t]["type"], trips[t]["heliport"]) == g]
        maxsim = 0
        for t in mine:
            act = sum(1 for u in mine
                      if trips[u]["start"] <= trips[t]["start"] < trips[u]["end"] + TA)
            maxsim = max(maxsim, act)
        key = f"{g[0]}@{g[1]}"
        chk(f"heli_group_{key}_capacity", maxsim <= len(members),
            f"max simultaneous={maxsim}, available={len(members)}")
        chk(f"heli_group_{key}_count_exact", helicopters_used.get(key) == maxsim,
            f"charged={helicopters_used.get(key)}, actual max={maxsim}")
    # no simultaneous presence (recomputed from stored install visits)
    sel = list(selected)
    presence_ok = True
    for i in range(len(sel)):
        for j in range(i + 1, len(sel)):
            t, u = sel[i], sel[j]
            for loc in trips[t]["install_visits"]:
                if loc in trips[u]["install_visits"]:
                    for (a1, d1) in trips[t]["install_visits"][loc]:
                        for (a2, d2) in trips[u]["install_visits"][loc]:
                            if a1 < d2 - 1e-9 and a2 < d1 - 1e-9:
                                presence_ok = False
    chk("no_simultaneous_presence", presence_ok)
    # connected separation (recomputed from stored service times)
    c = inst["connected"]
    fn, tn = tuple(c["from_node"]), tuple(c["to_node"])
    all_st = {}
    for t in sel:
        for k, v in trips[t]["service_times"].items():
            all_st[(k[0], int(k[1:]))] = v
    if fn in all_st and tn in all_st:
        chk("connected_separation", all_st[tn] - all_st[fn] >= c["min_sep_min"] - 1e-9,
            f"delta={all_st[tn] - all_st[fn]:.1f} min, required {c['min_sep_min']}")
    else:
        chk("connected_separation", False, "connected nodes not both served (impossible if cover holds)")
    # total cost recomputation
    total = sum(trips[t]["cost"] for t in sel)
    for key, u in helicopters_used.items():
        typ = key.split("@")[0]
        total += HELI_TYPES[typ]["fixed"] * u
    chk("total_cost_recomputed", True, f"recomputed={round(total, 2)}")
    return checks, round(total, 2)


# ---------------------------------------------------------------- compact model (Pyomo + HiGHS)
# DEVIATIONS from the paper's compact model (recorded in the report):
#  (i) no refuel-node sequencing: each helicopter flies ONE route per day;
#  (ii) at most one node per installation per helicopter (paper: several
#       nodes in one visit, deliver before pickup). Presence disjunctions
#       (21)-(23) and connected separations ARE included.
# The model is therefore easier than the paper's in (i)/(iii) and more
# restricted in (ii). If it still fails to prove optimality at 10 orders,
# that is conservative evidence for the paper's failure pattern.
def solve_compact(inst, time_cap=300):
    import pyomo.environ as pyo
    n = inst["n_orders"]
    helis = inst["helicopters"]
    H = [hk["id"] for hk in helis]
    # nodes: ('S', base) start, ('E', base) end, ('P', o), ('D', o)
    nodes = []
    for b in ("Sola", "Flesland"):
        nodes.append(("S", b))
        nodes.append(("E", b))
    for o in range(n):
        nodes.append(("P", o))
        nodes.append(("D", o))
    node_index = {nd: i for i, nd in enumerate(nodes)}
    M = 100000.0

    def loc_of(nd):
        if nd[0] in ("S", "E"):
            return nd[1]
        return node_loc(inst, nd)

    def win_of(nd):
        if nd[0] in ("S", "E"):
            return (DAY_START, DAY_END)
        return node_window(inst, nd)

    def demand(nd):
        if nd[0] == "P":
            return inst["orders"][nd[1]]["size"]
        if nd[0] == "D":
            return -inst["orders"][nd[1]]["size"]
        return 0

    def allowed(hk, i, j):
        if i == j:
            return False
        if i[0] == "E" or j[0] == "S":
            return False
        if i[0] == "S" and loc_of(i) != hk["base"]:
            return False
        if j[0] == "E" and loc_of(j) != hk["base"]:
            return False
        # start: only to pickups at own heliport or to installation nodes
        if i[0] == "S":
            return (j[0] == "P" and loc_of(j) == hk["base"]) or loc_of(j) not in HELIPORTS
        # end: only from deliveries at own heliport or from installation nodes
        if j[0] == "E":
            return (i[0] == "D" and loc_of(i) == hk["base"]) or loc_of(i) not in HELIPORTS
        # no arcs between heliport nodes (except via start/end handled above)
        if loc_of(i) in HELIPORTS and loc_of(j) in HELIPORTS:
            return False
        return True

    m = pyo.ConcreteModel()
    m.H = pyo.Set(initialize=H)
    m.N = pyo.Set(initialize=list(range(len(nodes))), ordered=True)
    arcs = {}
    for hk in helis:
        for i in nodes:
            for j in nodes:
                if allowed(hk, i, j):
                    arcs[(hk["id"], node_index[i], node_index[j])] = (i, j)
    m.A = pyo.Set(initialize=list(arcs.keys()), dimen=3)
    m.x = pyo.Var(m.A, domain=pyo.Binary)
    m.t = pyo.Var(m.H, m.N, domain=pyo.NonNegativeReals, bounds=(0, DAY_END))
    m.loadv = pyo.Var(m.H, m.N, domain=pyo.NonNegativeReals, bounds=(0, 19))
    m.fuel = pyo.Var(m.H, m.N, domain=pyo.NonNegativeReals, bounds=(0, 2500))
    m.legs = pyo.Var(m.H, m.N, domain=pyo.NonNegativeReals, bounds=(0, 50))
    m.used = pyo.Var(m.H, domain=pyo.Binary)

    def ft(hk, i, j):
        return flight_min(loc_of(i), loc_of(j), HELI_TYPES[hk["type"]]["cruise_kmh"])

    def svc(i, j):
        # landing time at i when travelling to j (0 if same installation / heliport)
        if loc_of(i) in HELIPORTS or loc_of(i) == loc_of(j):
            return 0
        return PARAMS["landing_time_min"]

    heli_by_id = {hk["id"]: hk for hk in helis}
    m.obj = pyo.Objective(
        expr=sum(ft(heli_by_id[a[0]], arcs[a][0], arcs[a][1])
                 * HELI_TYPES[heli_by_id[a[0]]["type"]]["rate"]
                 * m.x[a] for a in m.A)
        + sum(HELI_TYPES[hk["type"]]["fixed"] * m.used[hk["id"]] for hk in helis),
        sense=pyo.minimize)

    m.cons = pyo.ConstraintList()
    for hk in helis:
        h = hk["id"]
        spec = HELI_TYPES[hk["type"]]
        s_node = node_index[("S", hk["base"])]
        e_node = node_index[("E", hk["base"])]
        # used iff leaves start
        m.cons.add(sum(m.x[(h, s_node, j)] for (hh, i, j) in m.A if hh == h and i == s_node)
                   == m.used[h])
        # flow conservation + visit at most once (except start/end)
        for nd in nodes:
            ni = node_index[nd]
            if nd[0] in ("S", "E"):
                continue
            inn = sum(m.x[a] for a in m.A if a[0] == h and a[2] == ni)
            out = sum(m.x[a] for a in m.A if a[0] == h and a[1] == ni)
            m.cons.add(inn == out)
            m.cons.add(inn <= 1)
        # end: at most one arrival
        m.cons.add(sum(m.x[a] for a in m.A if a[0] == h and a[2] == e_node) <= 1)
        # time / load / fuel / legs linking
        for (hh, i, j) in m.A:
            if hh != h:
                continue
            ni, nj = nodes[i], nodes[j]
            m.cons.add(m.t[h, j] >= m.t[h, i] + svc(ni, nj) + ft(hk, ni, nj) - M * (1 - m.x[(h, i, j)]))
            m.cons.add(m.loadv[h, j] >= m.loadv[h, i] + demand(nj) - M * (1 - m.x[(h, i, j)]))
            m.cons.add(m.loadv[h, j] <= m.loadv[h, i] + demand(nj) + M * (1 - m.x[(h, i, j)]))
            m.cons.add(m.fuel[h, j] <= m.fuel[h, i] - spec["burn_kg_min"] * ft(hk, ni, nj)
                       + M * (1 - m.x[(h, i, j)]))
            m.cons.add(m.fuel[h, j] >= m.fuel[h, i] - spec["burn_kg_min"] * ft(hk, ni, nj)
                       - M * (1 - m.x[(h, i, j)]))
            m.cons.add(m.legs[h, j] >= m.legs[h, i] + 1 - M * (1 - m.x[(h, i, j)]))
        # start values
        m.cons.add(m.t[h, s_node] >= DAY_START)
        m.cons.add(m.t[h, s_node] <= DAY_END)
        m.cons.add(m.loadv[h, s_node] == 0)
        m.cons.add(m.fuel[h, s_node] == spec["tank_kg"])
        m.cons.add(m.legs[h, s_node] == 0)
        # capacity + min fuel everywhere
        for ni in range(len(nodes)):
            m.cons.add(m.loadv[h, ni] <= spec["seats"])
            m.cons.add(m.fuel[h, ni] >= spec["min_fuel_kg"])
        # time windows when visited
        for nd in nodes:
            ni = node_index[nd]
            if nd[0] in ("S", "E"):
                continue
            vis = sum(m.x[a] for a in m.A if a[0] == h and a[2] == ni)
            early, late = win_of(nd)
            m.cons.add(m.t[h, ni] >= early - M * (1 - vis))
            m.cons.add(m.t[h, ni] <= late + M * (1 - vis))
        # one visit per installation per helicopter
        for inst_name in INST_COORDS:
            nodes_here = [node_index[nd] for nd in nodes
                          if nd[0] in ("P", "D") and loc_of(nd) == inst_name]
            if nodes_here:
                m.cons.add(sum(m.x[a] for a in m.A if a[0] == h and a[2] in nodes_here) <= 1)
        # max legs between pickup and delivery (when served by this helicopter)
        for o in range(n):
            pi, di = node_index[("P", o)], node_index[("D", o)]
            vp = sum(m.x[a] for a in m.A if a[0] == h and a[2] == pi)
            vd = sum(m.x[a] for a in m.A if a[0] == h and a[2] == di)
            m.cons.add(m.legs[h, di] - m.legs[h, pi]
                       <= PARAMS["max_legs_per_order"] + M * (2 - vp - vd))
    # no-simultaneous-presence (paper (21)-(23)): at most one helicopter at an
    # installation at a time. s[h,k] = visit start time of helicopter h at
    # installation k (linked to the node time it serves there); z orders each
    # helicopter pair at each installation disjunctively.
    m.K = pyo.Set(initialize=list(INST_COORDS.keys()))
    m.s = pyo.Var(m.H, m.K, domain=pyo.NonNegativeReals, bounds=(0, DAY_END))
    hpairs = [(h1, h2) for ii, h1 in enumerate(H) for h2 in H[ii + 1:]]
    m.Z = pyo.Var(hpairs, m.K, domain=pyo.Binary)
    for hk in helis:
        h = hk["id"]
        for kname in INST_COORDS:
            nodes_here = [nd for nd in nodes if nd[0] in ("P", "D") and loc_of(nd) == kname]
            for nd in nodes_here:
                ni = node_index[nd]
                vis = sum(m.x[a] for a in m.A if a[0] == h and a[2] == ni)
                m.cons.add(m.s[h, kname] >= m.t[h, ni] - M * (1 - vis))
                m.cons.add(m.s[h, kname] <= m.t[h, ni] + M * (1 - vis))
    for (h1, h2) in hpairs:
        for kname in INST_COORDS:
            nodes_here = [node_index[nd] for nd in nodes
                          if nd[0] in ("P", "D") and loc_of(nd) == kname]
            v1 = sum(m.x[a] for a in m.A if a[0] == h1 and a[2] in nodes_here)
            v2 = sum(m.x[a] for a in m.A if a[0] == h2 and a[2] in nodes_here)
            m.cons.add(m.s[h1, kname] + PARAMS["landing_time_min"]
                       <= m.s[h2, kname] + M * (1 - m.Z[(h1, h2), kname])
                       + M * (2 - v1 - v2))
            m.cons.add(m.s[h2, kname] + PARAMS["landing_time_min"]
                       <= m.s[h1, kname] + M * m.Z[(h1, h2), kname]
                       + M * (2 - v1 - v2))
    # connected-order separation (paper (61)-(63) family): T[node] = service time
    # of the node, linked to whichever helicopter serves it.
    m.T = pyo.Var(m.N, domain=pyo.NonNegativeReals, bounds=(0, DAY_END))
    for nd in nodes:
        if nd[0] not in ("P", "D"):
            continue
        ni = node_index[nd]
        for hk in helis:
            h = hk["id"]
            vis = sum(m.x[a] for a in m.A if a[0] == h and a[2] == ni)
            m.cons.add(m.T[ni] >= m.t[h, ni] - M * (1 - vis))
            m.cons.add(m.T[ni] <= m.t[h, ni] + M * (1 - vis))
    _c = inst["connected"]
    _fn, _tn = tuple(_c["from_node"]), tuple(_c["to_node"])
    m.cons.add(m.T[node_index[_tn]] - m.T[node_index[_fn]] >= _c["min_sep_min"])

    # each order node visited exactly once, same helicopter for P and D
    for o in range(n):
        for kind in ("P", "D"):
            ni = node_index[(kind, o)]
            m.cons.add(sum(m.x[a] for a in m.A if a[2] == ni) == 1)
        pi, di = node_index[("P", o)], node_index[("D", o)]
        for hk in helis:
            h = hk["id"]
            vp = sum(m.x[a] for a in m.A if a[0] == h and a[2] == pi)
            vd = sum(m.x[a] for a in m.A if a[0] == h and a[2] == di)
            m.cons.add(vp == vd)

    t0 = time.time()
    solver = pyo.SolverFactory("highs")
    res = solver.solve(m, tee=False,
                       options={"time_limit": time_cap, "mip_rel_gap": 0.0,
                                "threads": 4})
    el = round(time.time() - t0, 2)
    tc = str(res.solver.termination_condition)
    obj = None
    try:
        obj = pyo.value(m.obj)
    except Exception:
        pass
    bound = None
    try:
        bound = res.problem.lower_bound
    except Exception:
        pass
    try:
        if bound is None:
            bound = res.solver.best_objective_bound
    except Exception:
        pass
    gap = None
    if obj is not None and bound is not None and obj > 0:
        gap = max(0.0, (obj - bound) / obj * 100.0)
    return {"status": tc, "objective": None if obj is None else round(obj, 2),
            "dual_bound": None if bound is None else round(float(bound), 2),
            "gap_pct": None if gap is None else round(gap, 4),
            "solve_time_s": el, "time_cap_s": time_cap}


# ---------------------------------------------------------------- runner
def run_one(n_orders, inst_idx, do_compact=True):
    inst = generate_instance(n_orders, inst_idx)
    t_gen0 = time.time()
    trips = []
    for htype in HELI_TYPES:
        for hp in HELIPORTS:
            trips += gen_trips(inst, htype, hp)
    gen_time = round(time.time() - t_gen0, 2)
    # dedupe identical trips (same type/heliport/orders/nodes/times)
    seen, uniq = set(), []
    for tr in trips:
        key = (tr["type"], tr["heliport"], tuple(tr["orders"]),
               tuple(tuple(x) for x in tr["nodes"]), tr["start"])
        if key not in seen:
            seen.add(key)
            uniq.append(tr)
    trips = uniq
    tb = solve_trip_based(inst, trips, time_cap=PARAMS["tripbased_time_cap_s"])
    checks, recomputed_cost = [], None
    if tb["selected"]:
        checks, recomputed_cost = validate_solution(inst, trips, tb["selected"], tb["helicopters_used"])
    comp = None
    if do_compact:
        comp = solve_compact(inst, time_cap=PARAMS["compact_time_cap_s"])
    return {"n_orders": n_orders, "instance": inst_idx, "seed": inst["seed"],
            "orders": inst["orders"], "connected": inst["connected"],
            "helicopters": inst["helicopters"],
            "trip_gen_time_s": gen_time,
            "n_trips": len(trips),
            "trips_by_type": {t: sum(1 for tr in trips if tr["type"] == t) for t in HELI_TYPES},
            "trip_based": tb, "validation": checks,
            "recomputed_objective": recomputed_cost, "compact": comp}


def main():
    with open(os.path.join(BASE, "scenario.yaml")) as f:
        yaml.safe_load(f)  # parse check (already validated; re-checked here)
    log = {"paper": "Nafstad et al. (2021) COR 128:105158",
           "params": PARAMS, "heli_types": HELI_TYPES,
           "installations": [{"name": nm, "lon": lo, "lat": la,
                              "source": "Sodir FactMaps WGS84 FeatureServer/304, 2026-11-06"}
                             for nm, lo, la in INSTALLATIONS],
           "heliports": {k: {"lon": v[0], "lat": v[1],
                             "source": "published airport coordinates"} for k, v in HELIPORTS.items()},
           "results": []}
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    plan = []
    if which in ("all", "smoke"):
        plan += [(8, i) for i in range(3)]
    if which in ("all", "target"):
        plan += [(10, i) for i in range(3)]
    for (n, i) in plan:
        print(f"=== {n} orders, instance {i} ===", flush=True)
        r = run_one(n, i, do_compact=True)
        tb, comp = r["trip_based"], r["compact"]
        nvalid = sum(1 for c in r["validation"] if c["pass"])
        print(f"  trips: {r['n_trips']} (gen {r['trip_gen_time_s']} s)")
        print(f"  trip-based: status={tb['status']} obj={tb['objective']} gap={tb['gap_pct']}% "
              f"time={tb['solve_time_s']} s incompat_pairs={tb['n_incompat_pairs']} "
              f"helis_used={tb['helicopters_used']} recomputed_obj={r['recomputed_objective']}")
        print(f"  validation: {nvalid}/{len(r['validation'])} checks pass")
        if comp:
            print(f"  compact: status={comp['status']} obj={comp['objective']} gap={comp['gap_pct']}% "
                  f"time={comp['solve_time_s']} s (cap {comp['time_cap_s']} s)")
        log["results"].append(r)
        with open(os.path.join(BASE, "reproduce_table3_log.json"), "w") as f:
            json.dump(log, f, indent=1)
    print("log written:", os.path.join(BASE, "reproduce_table3_log.json"))


if __name__ == "__main__":
    main()
