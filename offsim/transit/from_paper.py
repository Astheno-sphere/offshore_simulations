"""Timetables from papers (or your own data) -> a GTFS folder the `gtfs` engine replays.

Many transport papers give a network as tables: stops, run times, headways or departure lists, service days. This
turns that into GTFS so it runs through the same engine, gates and films as Entur data, with every number sourced.

timetable.yaml (next to the paper's scenario.yaml):

    source: {paper: "Author 2024, Transportation Research Part X", doi: "10.xxxx/..."}
    service: {days: [mon, tue, wed, thu, fri], start_date: 20260105, end_date: 20261231}
    lines:
      - id: "1"
        mode: bus                       # bus | ferry | rail | tram
        stops:                          # in travel order; every stop sourced or assumed
          - {id: A, name: "Molde rutebilstasjon", lon: 7.1601, lat: 62.7372, src: "p.4 Table 2"}
          - {id: B, name: "Årø", lon: 7.2600, lat: 62.7560, assumption: true}
        run_time_min: {value: [12], src: "p.5 Table 3"}        # minutes between consecutive stops (len = stops-1)
        dwell_s: {value: 30, assumption: true}
        headway_min: {value: 20, src: "p.5"}                   # either headway (+ first/last) ...
        first: "06:00"
        last: "22:00"
        # departures: {value: ["06:05", "06:35"], src: "p.6"}  # ... or explicit departure list
        both_directions: true

Rules: every stop has `src` or `assumption: true`; run_time_min, dwell_s, headway_min / departures are
{value, src|assumption}; assumptions are listed in the manifest and must be shown on screen. Frequencies are
expanded into explicit trips (exact_times), so the engine needs no frequencies.txt support.

    to_gtfs(timetable_yaml, out_dir) -> manifest dict
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import yaml

ROUTE_TYPE = {"bus": 3, "ferry": 4, "rail": 2, "tram": 0}
DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def _v(x, path, assumed):
    if isinstance(x, dict) and "value" in x:
        if not (x.get("src") or x.get("assumption")):
            raise ValueError(f"{path}: value without src or assumption")
        if x.get("assumption"):
            assumed.append(path)
        return x["value"]
    raise ValueError(f"{path}: must be {{value, src|assumption}}")


def _hm(s):
    h, m = s.split(":")[:2]
    return int(h) * 3600 + int(m) * 60


def _fmt(t):
    return f"{int(t // 3600):02d}:{int(t % 3600 // 60):02d}:{int(t % 60):02d}"


def to_gtfs(timetable_yaml, out_dir):
    d = yaml.safe_load(Path(timetable_yaml).read_text())
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    assumed = []
    svc = d["service"]
    days = {k[:3] for k in svc["days"]}
    rows = {k: [] for k in ("agency", "stops", "routes", "trips", "stop_times", "calendar")}
    rows["agency"].append({"agency_id": "paper", "agency_name": d["source"].get("paper", "paper"),
                           "agency_url": "https://doi.org/" + d["source"].get("doi", ""), "agency_timezone": "Europe/Oslo"})
    rows["calendar"].append({"service_id": "S", **{k: int(k[:3] in days) for k in DAYS},
                             "start_date": svc["start_date"], "end_date": svc["end_date"]})
    seen_stops = {}
    for li, line in enumerate(d["lines"]):
        lp = f"lines[{li}]"
        stops = line["stops"]
        for si, s in enumerate(stops):
            if not (s.get("src") or s.get("assumption")):
                raise ValueError(f"{lp}.stops[{si}] ({s.get('name')}): needs src or assumption: true")
            if s.get("assumption"):
                assumed.append(f"{lp}.stops[{si}]")
            seen_stops[s["id"]] = {"stop_id": s["id"], "stop_name": s["name"], "stop_lat": s["lat"], "stop_lon": s["lon"]}
        run = _v(line["run_time_min"], f"{lp}.run_time_min", assumed)
        if len(run) != len(stops) - 1:
            raise ValueError(f"{lp}.run_time_min needs {len(stops) - 1} values")
        dwell = float(_v(line.get("dwell_s", {"value": 0, "assumption": True}), f"{lp}.dwell_s", assumed))
        if "departures" in line:
            deps = [_hm(t) for t in _v(line["departures"], f"{lp}.departures", assumed)]
        else:
            hw = float(_v(line["headway_min"], f"{lp}.headway_min", assumed)) * 60
            t, deps = _hm(line["first"]), []
            while t <= _hm(line["last"]):
                deps.append(t)
                t += hw
        rows["routes"].append({"route_id": line["id"], "agency_id": "paper", "route_short_name": line["id"],
                               "route_type": ROUTE_TYPE[line.get("mode", "bus")]})
        dirs = [(0, stops, run)]
        if line.get("both_directions"):
            dirs.append((1, stops[::-1], run[::-1]))
        for direction, seq, rt in dirs:
            for k, dep in enumerate(deps):
                tid = f"{line['id']}_{direction}_{k}"
                rows["trips"].append({"route_id": line["id"], "service_id": "S", "trip_id": tid, "direction_id": direction})
                t = dep
                for i, s in enumerate(seq):
                    arr = t
                    depart = arr + (dwell if 0 < i < len(seq) - 1 else 0)
                    rows["stop_times"].append({"trip_id": tid, "arrival_time": _fmt(arr), "departure_time": _fmt(depart),
                                               "stop_id": s["id"], "stop_sequence": i + 1})
                    if i < len(rt):
                        t = depart + rt[i] * 60
    rows["stops"] = list(seen_stops.values())
    for name, rs in rows.items():
        with open(out / f"{name}.txt", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rs[0]))
            w.writeheader()
            w.writerows(rs)
    man = {"source": d["source"], "licence": "per paper (facts extracted with page sources)", "assumptions": assumed,
           "lines": len(d["lines"]), "trips": len(rows["trips"]), "stops": len(rows["stops"])}
    (out / "manifest.json").write_text(json.dumps(man, indent=1))
    return man
