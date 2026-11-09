"""Air engine: replay a weekly helicopter flight program (WFPPP) under hourly weather, with cancellation and rebooking.

Registered as `air`, class {"WFPPP"}, needs_weather = True. Generic: any heliport, any installations; the program comes from the
`whelp` solver (`plan.meta["program"]`), the geometry and rules from `problem.extra["wfppp"]` (docs/ENGINES.md, whelp).

Mapping
- Program flight = (helicopter, weekday, start slot, installations). Slot t of weekday d departs at
  week_start + d x 24 h + day_start + t x slot. Week start = weather time `extra["weather_t0_s"]` (default: first sample of the series);
  the five weekdays are the first five 24 h blocks. `wfppp.replay.weeks` (default 1, or "all") replays that many consecutive 7-day blocks
  of the series, each with the same program; rebooking never leaves its week.
- Departure rule: a flight departs iff, for every hourly sample from the departure hour to the hour of its last minute (air time +
  deck stops), wind_mps <= limits["wind_mps"] and, when the flight serves a mobile installation, hs_m <= limits["hs_m"]
  (`extra["limits"]`, scenario sim.limits; the scenario flags them `assumption: true` until sourced from CAP 437 / the helicopter
  flight manual / operator minima). Missing limits raise Unsupported; nothing is defaulted.
- Cancelled flight: its slot is released at the planned departure and it is rebooked into the EARLIEST free slot (by weekday, slot,
  then helicopter order) at or after the planned departure, in any helicopter window of the same week, such that (1) the flight without
  its turnaround fits the window, (2) the departure slot lies in the opening hours of every installation on it, (3) no slot of
  [t, t + n_f) (turnaround included) is used by another flight of that helicopter, (4) no other flight to the same installation starts
  in that slot, (5) the weather rule holds for the new departure (the planner sees the actual series: a perfect forecast, so a
  rebooked flight is not cancelled again; this is an optimistic bound on recovery). No flight is moved to make room. Flights are
  processed in planned-departure order; none left over by Friday is UNMET.
- Deterministic for a given series; `seed` is accepted and unused.

Contract
- One agent per helicopter (cls helicopter, domain air, vmax = cruise speed). States: `fly` (great-circle legs, sampled every 5 min),
  `unload` (deck stop at an installation; the contract has no `deck` state), `load` (the turnaround at the heliport: fuel, boarding),
  `wait` (the planned flight of a cancelled departure: the helicopter is held for the weather), `idle` (otherwise, at the heliport).
  Times in seconds from the week start; the first row of a helicopter is its first block.

KPIs (sums over the replayed weeks; `weeks` says how many)
  flights_planned, flights_flown, flights_cancelled (planned flights whose departure failed the rule), flights_rebooked,
  flights_unmet, unmet_half_flights (2 per unrebookable flight: a direct flight carries two half-flights, a split one half-flight to
  each installation), unmet_half_flights_net (shortfall against the weekly demand, spare half-flights of over-served installations
  netted), delay_h_mean (mean planned-to-actual departure delay of rebooked flights, hours; 0 when none), delay_h_max,
  utilisation (slots of flown flights incl. turnaround / slots of the windows incl. one turnaround per day: Table 4's measure),
  plan_cost (the program's cost), planned_variable_cost (recomputed here from the geometry: the replay's own check of the plan),
  helicopters, window_hours, flown_hours.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from offsim.contract import haversine_m
from offsim.engines.base import Plan, Problem, SimResult, Unsupported, WeatherSeries, World, register_engine
from offsim.solve import whelp

KN_MPS = whelp.NM_M / 3600.0
SAMPLE_S = 300.0
WEEK_S = 7 * 86400.0


def _gc_point(p0, p1, f):
    """Point at fraction f of the great-circle arc p0 -> p1 (lon, lat degrees)."""
    a = np.radians([p0[0], p0[1]])
    b = np.radians([p1[0], p1[1]])
    v0 = np.array([math.cos(a[1]) * math.cos(a[0]), math.cos(a[1]) * math.sin(a[0]), math.sin(a[1])])
    v1 = np.array([math.cos(b[1]) * math.cos(b[0]), math.cos(b[1]) * math.sin(b[0]), math.sin(b[1])])
    w = math.acos(max(-1.0, min(1.0, float(v0 @ v1))))
    if w < 1e-12:
        return p0
    v = (math.sin((1 - f) * w) * v0 + math.sin(f * w) * v1) / math.sin(w)
    return math.degrees(math.atan2(v[1], v[0])), math.degrees(math.asin(max(-1.0, min(1.0, v[2]))))


@dataclass
class _Flt:
    key: int
    heli: str
    day: int
    t: int
    flight: whelp.Flight
    planned_dep: float           # seconds from the week start
    delay_s: float = 0.0
    status: str = "planned"      # planned | flown | cancelled | unmet


@register_engine("air")
def _factory():
    return AirEngine()


class AirEngine:
    name = "air"
    classes = {"WFPPP"}
    needs_weather = True

    # ----------------------------------------------------------------------------------------- inputs
    def _inputs(self, problem: Problem, plan: Plan, weather):
        if not set(problem.cls) <= self.classes:
            raise Unsupported(f"air engine handles {sorted(self.classes)}; problem needs {sorted(problem.cls)}")
        spec = whelp.parse_spec(problem)
        prog = (plan.meta or {}).get("program")
        if prog is None:
            raise Unsupported("air engine replays a weekly flight program: plan.meta['program'] is missing (solver whelp)")
        if weather is None:
            raise Unsupported("air engine needs a WeatherSeries (hourly hs_m, wind_mps)")
        lim = (problem.extra or {}).get("limits") or {}
        if "wind_mps" not in lim:
            raise Unsupported("air engine needs extra['limits']['wind_mps'] (scenario sim.limits); it will not default a safety limit")
        flights = {f.fid: f for f in whelp.generate_flights(spec)}
        for r in prog:
            f = flights.get(r["fid"])
            if f is None or [spec.inst[i].name for i in f.inst] != list(r["installations"]):
                raise Unsupported("the program was not solved on this problem's installations (flight ids differ)")
        if any(spec.inst[i].mobile for r in prog for i in flights[r["fid"]].inst) and "hs_m" not in lim:
            raise Unsupported("air engine needs extra['limits']['hs_m'] for flights to mobile installations")
        df = weather.df
        for c in ("t", "hs_m", "wind_mps"):
            if c not in df:
                raise Unsupported(f"weather series lacks column {c}")
        t = df["t"].to_numpy(float)
        if len(t) < 2 or not np.allclose(np.diff(t), 3600.0, atol=1.0):
            raise Unsupported("air engine needs an hourly weather series (t in seconds, step 3600)")
        return spec, prog, flights, lim, df

    # ----------------------------------------------------------------------------------------- simulate
    def simulate(self, problem: Problem, plan: Plan, world: World, weather: WeatherSeries | None = None, seed: int = 0) -> SimResult:
        spec, prog, flights, lim, df = self._inputs(problem, plan, weather)
        extra = problem.extra or {}
        rep = (extra["wfppp"].get("replay") or {})
        t_series = df["t"].to_numpy(float)
        wx_t0 = float(extra.get("weather_t0_s", t_series[0]))
        n_hours = len(t_series)
        first_idx = int(round((wx_t0 - t_series[0]) / 3600.0))
        weeks_cfg = rep.get("weeks", 1)
        need_h = spec.days * 24
        if weeks_cfg == "all":
            weeks = max(0, (n_hours - first_idx - need_h) // 168 + 1)
        else:
            weeks = int(weeks_cfg)
        if weeks < 1 or first_idx < 0 or first_idx + (weeks - 1) * 168 + need_h > n_hours:
            raise Unsupported(f"weather series has {n_hours} h; {weeks} week(s) from hour {first_idx} need "
                              f"{first_idx + (weeks - 1) * 168 + need_h} h")
        wind, hs = df["wind_mps"].to_numpy(float), df["hs_m"].to_numpy(float)
        wind_ok = wind <= float(lim["wind_mps"]) + 1e-12
        hs_ok = hs <= float(lim["hs_m"]) + 1e-12 if "hs_m" in lim else np.ones(n_hours, bool)
        # prefix counts of failing hours: a window [a, b] is clear when no failing hour lies inside it
        bad_w = np.concatenate([[0], np.cumsum(~wind_ok)])
        bad_h = np.concatenate([[0], np.cumsum(~hs_ok)])

        slot_s = spec.slot_min * 60.0
        day0_s = spec.day_start_h * 3600.0
        helis = {}
        for r in prog:
            helis.setdefault(r["heli"], float(r["window_h"]))
        order = sorted(helis, key=lambda h: (-helis[h], h))
        win_slots = {h: int(round(helis[h] * 60 / spec.slot_min)) for h in order}
        smax = max(win_slots.values())
        t_h, t_ij = whelp.leg_minutes(spec)
        mobile_of = {fid: any(spec.inst[i].mobile for i in f.inst) for fid, f in flights.items()}

        all_rows, events, per_week = [], [], []
        tot = dict(planned=0, flown=0, cancelled=0, rebooked=0, unmet=0, delay_sum=0.0, delay_max=0.0, slots=0, hours=0.0, planned_cost=0.0)
        unmet_net = 0
        flown_blocks = {h: [] for h in order}                     # per helicopter: (week_off, _Flt)
        wait_blocks = {h: [] for h in order}
        for wk in range(weeks):
            woff = wk * WEEK_S                                    # trajectory seconds of this week's start
            hidx0 = first_idx + wk * 168                          # weather hour index of the week's start

            def clear(dep_s, flt):
                a = hidx0 + int(math.floor(dep_s / 3600.0 + 1e-9))
                b = hidx0 + int(math.floor((dep_s + flt.dur_min * 60.0 - 1e-6) / 3600.0))
                if bad_w[b + 1] - bad_w[a] > 0:
                    return False
                return not (mobile_of[flt.fid] and bad_h[b + 1] - bad_h[a] > 0)

            def dep_of(d, t):
                return d * 86400.0 + day0_s + t * slot_s

            planned = [_Flt(k, r["heli"], r["day"], r["start_slot"], flights[r["fid"]], dep_of(r["day"], r["start_slot"]))
                       for k, r in enumerate(sorted(prog, key=lambda r: (r["day"], r["start_slot"], r["heli"])))]
            occ = {}                                              # (heli, day, slot) -> key
            land = {}                                             # (installation, day, slot) -> key
            for f in planned:
                for u in range(f.t, f.t + f.flight.n):
                    occ[f.heli, f.day, u] = f.key
                for i in f.flight.inst:
                    land[i, f.day, f.t] = f.key
            flown, rebooked_list = [], []
            nxt_key = len(planned)
            delivered = [0] * len(spec.inst)

            def release(f):
                for u in range(f.t, f.t + f.flight.n):
                    occ.pop((f.heli, f.day, u), None)
                for i in f.flight.inst:
                    land.pop((i, f.day, f.t), None)

            for f in planned:
                tw = woff + f.planned_dep
                if clear(f.planned_dep, f.flight):
                    f.status = "flown"
                    flown.append(f)
                    continue
                f.status = "cancelled"
                release(f)
                wait_blocks[f.heli].append((tw, tw + f.flight.dur_min * 60.0))
                events.append({"t": tw, "agent_id": f.heli, "event": "cancel", "week": wk, "day": f.day,
                               "installations": "+".join(spec.inst[i].name for i in f.flight.inst)})
                slot = self._rebook(f, spec, helis, order, win_slots, smax, occ, land, clear, dep_of)
                if slot is None:
                    f.status = "unmet"
                    events.append({"t": tw, "agent_id": f.heli, "event": "unmet", "week": wk, "day": f.day,
                                   "installations": "+".join(spec.inst[i].name for i in f.flight.inst)})
                    continue
                h2, d2, t2 = slot
                nf = _Flt(nxt_key, h2, d2, t2, f.flight, dep_of(d2, t2), delay_s=dep_of(d2, t2) - f.planned_dep, status="flown")
                nxt_key += 1
                for u in range(t2, t2 + f.flight.n):
                    occ[h2, d2, u] = nf.key
                for i in f.flight.inst:
                    land[i, d2, t2] = nf.key
                flown.append(nf)
                rebooked_list.append(nf)
                events.append({"t": tw, "agent_id": h2, "event": "rebook", "week": wk, "day": d2,
                               "installations": "+".join(spec.inst[i].name for i in f.flight.inst), "delay_h": nf.delay_s / 3600.0,
                               "new_departure_t": woff + nf.planned_dep})
            for f in flown:
                flown_blocks[f.heli].append((woff, f))
                for i in f.flight.inst:
                    delivered[i] += 2 if f.flight.kind == "direct" else 1
            n_cancel = sum(1 for f in planned if f.status in ("cancelled", "unmet"))
            n_unmet = sum(1 for f in planned if f.status == "unmet")
            wk_unmet_net = sum(max(0, spec.inst[i].demand_half - delivered[i]) for i in range(len(spec.inst)))
            unmet_net += wk_unmet_net
            delays = [f.delay_s / 3600.0 for f in rebooked_list]
            tot["planned"] += len(planned)
            tot["flown"] += len(flown)
            tot["cancelled"] += n_cancel
            tot["rebooked"] += len(rebooked_list)
            tot["unmet"] += n_unmet
            tot["delay_sum"] += sum(delays)
            tot["delay_max"] = max([tot["delay_max"], *delays])
            tot["slots"] += sum(f.flight.n for f in flown)
            tot["hours"] += sum(f.flight.dur_min for f in flown) / 60.0
            tot["planned_cost"] += sum(self._geometry_cost(spec, f.flight) for f in planned)
            per_week.append({"week": wk, "planned": len(planned), "cancelled": n_cancel, "rebooked": len(rebooked_list),
                             "unmet_flights": n_unmet, "unmet_half_flights": 2 * n_unmet, "unmet_half_flights_net": wk_unmet_net,
                             "delay_h_mean": float(np.mean(delays)) if delays else 0.0})

        traj_rows = []
        for h in order:
            traj_rows += self._rows(h, spec, t_h, t_ij, flown_blocks[h], wait_blocks[h], day0_s, slot_s)
        traj = pd.DataFrame(traj_rows, columns=["agent_id", "t", "lon", "lat", "state"])
        agents = pd.DataFrame([{"agent_id": h, "cls": "helicopter", "vmax_mps": spec.speed_kn * KN_MPS, "capacity": np.nan,
                                "domain": "air"} for h in order])
        capacity_slots = sum((win_slots[h] + spec.l) * spec.days for h in order) * weeks
        per_wk_planned = tot["planned"] / weeks
        kp = {"flights_planned": float(tot["planned"]), "flights_flown": float(tot["flown"]),
              "flights_cancelled": float(tot["cancelled"]), "flights_rebooked": float(tot["rebooked"]),
              "flights_unmet": float(tot["unmet"]), "unmet_half_flights": float(2 * tot["unmet"]),
              "unmet_half_flights_net": float(unmet_net),
              "delay_h_mean": float(tot["delay_sum"] / tot["rebooked"]) if tot["rebooked"] else 0.0,
              "delay_h_max": float(tot["delay_max"]), "utilisation": float(tot["slots"] / capacity_slots) if capacity_slots else 0.0,
              "plan_cost": float(plan.objective), "planned_variable_cost": float(tot["planned_cost"] / weeks),
              "helicopters": float(len(order)), "window_hours": float(sum(helis.values())), "flown_hours": float(tot["hours"]),
              "weeks": float(weeks), "flights_planned_per_week": float(per_wk_planned)}
        ev = pd.DataFrame(events, columns=None)
        if len(ev):
            ev = ev.sort_values(["t", "event"], kind="stable").reset_index(drop=True)
        return SimResult(traj=traj, agents=agents, events=ev, kpis=kp, engine=self.name, seed=seed,
                         weather=weather.source,
                         meta={"limits": {k: float(v) for k, v in lim.items()}, "per_week": per_week, "weeks": weeks,
                               "rebooking": "earliest free slot at/after the planned departure, same week, perfect forecast, no moves",
                               "weather_first_hour": first_idx})

    @staticmethod
    def _geometry_cost(spec, fl: whelp.Flight) -> float:
        """Flight-hour cost recomputed from the coordinates with the contract's haversine (not from Flight.cost)."""
        pts = [spec.heliport] + [(spec.inst[i].lon, spec.inst[i].lat) for i in fl.inst] + [spec.heliport]
        dist = sum(haversine_m(a[0], a[1], b[0], b[1]) for a, b in zip(pts, pts[1:]))
        sec = dist / (spec.speed_kn * KN_MPS) + len(fl.inst) * spec.deck_min * 60.0
        return float(spec.hour_cost * sec / 3600.0)

    # ----------------------------------------------------------------------------------------- rebooking
    @staticmethod
    def _rebook(f: _Flt, spec, helis, order, win_slots, smax, occ, land, clear, dep_of):
        """Earliest (heli, day, slot) at/after the planned departure satisfying rules (1)-(5); None when there is none."""
        fl = f.flight
        lo = max(spec.inst[i].lo for i in fl.inst)
        hi = min(spec.inst[i].hi for i in fl.inst)
        for d in range(f.day, spec.days):
            t_first = f.t if d == f.day else 0
            for t in range(max(t_first, lo), min(hi, smax - fl.n_fly + 1)):
                if any((i, d, t) in land for i in fl.inst):
                    continue
                dep = dep_of(d, t)
                if not clear(dep, fl):
                    continue
                for h in order:
                    if t + fl.n_fly > win_slots[h]:
                        continue
                    if all((h, d, u) not in occ for u in range(t, t + fl.n)):
                        return h, d, t
        return None

    # ----------------------------------------------------------------------------------------- trajectory
    @staticmethod
    def _flight_blocks(spec, t_h, t_ij, fl: whelp.Flight, dep_s: float):
        """[(t0, t1, state, p0, p1)] of one flight incl. its turnaround, from departure `dep_s`."""
        H = spec.heliport
        pts = [(spec.inst[i].lon, spec.inst[i].lat) for i in fl.inst]
        legs = [(H, pts[0], t_h[fl.inst[0]] * 60.0)]
        for a, b in zip(fl.inst, fl.inst[1:]):
            legs.append(((spec.inst[a].lon, spec.inst[a].lat), (spec.inst[b].lon, spec.inst[b].lat), t_ij[a][b] * 60.0))
        out, t = [], dep_s
        for k, (p0, p1, sec) in enumerate(legs):
            out.append((t, t + sec, "fly", p0, p1))
            t += sec
            out.append((t, t + spec.deck_min * 60.0, "unload", p1, p1))
            t += spec.deck_min * 60.0
        last = pts[-1]
        sec = t_h[fl.inst[-1]] * 60.0
        out.append((t, t + sec, "fly", last, H))
        t += sec
        out.append((t, t + spec.turnaround_min * 60.0, "load", H, H))
        return out

    def _rows(self, heli, spec, t_h, t_ij, flown, waits, day0_s, slot_s):
        H = spec.heliport
        blocks = []
        for woff, f in flown:
            blocks += self._flight_blocks(spec, t_h, t_ij, f.flight, woff + f.planned_dep)
        blocks.sort(key=lambda b: b[0])
        busy = [(b[0], b[1]) for b in blocks]
        for a, b in sorted(waits):                                  # held for the weather, minus time the helicopter is busy
            cur = a
            for s0, s1 in busy:
                if s1 <= cur or s0 >= b:
                    continue
                if s0 > cur:
                    blocks.append((cur, s0, "wait", H, H))
                cur = max(cur, s1)
            if cur < b:
                blocks.append((cur, b, "wait", H, H))
        blocks.sort(key=lambda b: b[0])
        if not blocks:
            return [(heli, day0_s, H[0], H[1], "idle"), (heli, day0_s + 3600.0, H[0], H[1], "idle")]
        rows, t_end = [], blocks[0][0]
        for b in blocks:
            if b[0] > t_end + 1e-6:
                rows.append((heli, t_end, H[0], H[1], "idle"))
            t0, t1, st, p0, p1 = b
            if st == "fly":
                n = max(1, int(math.ceil((t1 - t0) / SAMPLE_S)))
                for k in range(n):
                    p = _gc_point(p0, p1, k / n)
                    rows.append((heli, t0 + k * (t1 - t0) / n, p[0], p[1], "fly"))
            else:
                rows.append((heli, t0, p0[0], p0[1], st))
            t_end = max(t_end, t1)
        last = blocks[-1]
        rows.append((heli, last[1], last[4][0], last[4][1], "idle"))
        return rows
