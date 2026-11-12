"""Gap table over rule tags (L6): which (problem class, mode) areas are well covered and where a kind of paper is missing.

    gap_table(tags)                       -> DataFrame: observed counts per (class, mode, region, uncertainty)
    find_gaps(tags, min_support=2)        -> ranked list of gap dicts (kinds below), each with four factors and a score
    write_gaps(gaps, path)                -> papers/gaps.yaml

Gap kinds, evaluated per (class, mode) with at least `min_support` papers:
- no-norway:      no supporting paper has a Norwegian region (NCS, Oslofjord, Norway). The method exists but has
                  never been shown on Norwegian geography.
- no-uncertainty: every supporting paper has uncertainty "none". Only deterministic results exist.
- no-code:        no supporting paper links code or data AND every supporting record states that its code or data is
                  unavailable (tags.code_statement). An abstract that is silent about code proves nothing, so silence
                  never yields this kind (the first live run emitted 18 such gaps, all from silence).

Synonym classes are merged before any check (WFPPP is the helicopter problem tagged HRP): the gap carries the union
of the papers and lists the names it absorbed in `synonyms`.

Ranking: score = support x novelty x feasibility x audience, each factor in 0..1, all four written into the gap
(`factors`) with the reason (`factor_notes`):
- support      min(1, papers / 5): the cell is backed once it has about five papers.
- novelty      ref / (own + ref), ref = the largest cell that shares this class or this mode. A thin cell next to a
               well-covered one approaches 1; a cell that is itself the largest approaches 0. No neighbour: 0.5.
- feasibility  (solver covers class + engine covers class + data reachable) / 3, 1 only when all three hold.
               Solver and engine come from offsim.engines.available() and the `classes` attributes of the registered
               tools; the engine is the gap's suggested engine. Data: the target region must have a world definition
               (offsim/worlds/<name>.yaml, the fetch path) or data/worlds/<name>/ on disk.
               The target of a no-norway gap is Norway; otherwise the Norwegian region the papers name, else the
               first foreign region named (no world, so unreachable), else none (no place named, unreachable).
- audience     editorial weight, not evidence: 1.0 when the target is Norwegian AND the mode is one we can film
               (psv, heli, ferry: a 3D asset or CAD module exists), 0.6 when only one holds, 0.2 when neither.

A gap is a lead, not a result. Tags route work only; values come from paper-extract with page sources.
Human verdicts live in papers/review.yaml (offsim/research/review.py); they are applied after ranking.

CLI: python -m offsim.research.gaps --tags papers/tags.jsonl --out papers/gaps.yaml --min-support 2 --review papers/review.yaml
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

from offsim.research.review import apply_reviews, load_reviews
from offsim.research.tags import KPI_RULES, NORWAY_REGIONS

KINDS = ("no-norway", "no-uncertainty", "no-code")
COLUMNS = ["class", "mode", "region", "uncertainty", "n"]
SUPPORT_SATURATION = 5                                   # papers at which a cell counts as fully backed
CLASS_SYNONYMS = {"WFPPP": "HRP"}                        # solver/engine problem name -> tag class (same problem)
CLASS_ALIAS = {"HRP": "WFPPP"}                           # tag class -> the name registered tools use for it
FILMABLE_MODES = frozenset({"psv", "heli", "ferry"})     # a 3D asset or CAD module exists: psv.glb / marine_film.py,
                                                         # air.py, ferry.glb
ROOT = Path(__file__).resolve().parents[2]
# region -> world definitions that cover it (offsim/worlds/<name>.yaml is the documented fetch path)
REGION_WORLDS = {
    "NCS": ("bergen-ncs", "north-sea-stavanger"),
    "North Sea": ("north-sea-stavanger",),
    "Oslofjord": ("oslofjord",),
    "Norway": ("bergen-ncs", "north-sea-stavanger", "oslofjord"),
}


def _cells(t: dict):
    """(class, mode, region) combinations of one tag. Missing mode -> 'none'."""
    modes = t.get("mode") or ["none"]
    regions = t.get("region") or ["none"]
    for c, m, r in itertools.product(t.get("classes") or [], modes, regions):
        yield c, m, r


def gap_table(tags: list[dict]) -> pd.DataFrame:
    """Observed paper counts per (class, mode, region, uncertainty). Only cells with papers appear."""
    rows = []
    for t in tags:
        for c, m, r in _cells(t):
            rows.append({"class": c, "mode": m, "region": r, "uncertainty": t.get("uncertainty", "none"),
                         "paper_id": t["paper_id"]})
    if not rows:
        return pd.DataFrame(columns=COLUMNS)
    df = pd.DataFrame(rows)
    return (df.groupby(["class", "mode", "region", "uncertainty"])["paper_id"].nunique()
              .rename("n").reset_index())


def suggest_engine(cls: str, mode: str) -> str:
    """Engine for a gap, per docs/ENGINES.md 'Choosing'. The class decides first (it must be one the engine's `classes`
    covers: tests/test_concordance.py checks this against the registry); the mode only routes classes no engine covers."""
    if cls == "WIND-INST":
        return "orbit"
    if cls == "WIND-OM":
        return "wombat"
    if cls == "HRP":                        # helicopter routing = weekly flight program problem WFPPP (solver whelp)
        return "air"
    if cls == "VRPTW":                      # openclsim has no time windows
        return "replay"
    if cls == "PDP":                        # paired pickup/delivery: replay is the only engine that lists PDP
        return "replay"
    if cls == "CVRP":
        return "openclsim" if mode in ("psv", "ferry", "ctv") else "replay"
    if mode == "wtiv":
        return "orbit"
    if mode == "sov":
        return "wombat"
    if mode == "heli":
        return "air"
    if mode in ("psv", "ferry", "ctv"):
        return "openclsim"
    return "replay"


def capabilities() -> dict:
    """{'solvers': {name: classes}, 'engines': {name: classes}} for the tools that import here (offsim.engines.available)."""
    from offsim.engines import base
    status = base.available()
    caps = {"solvers": {}, "engines": {}}
    for kind, getter in (("solvers", base.get_solver), ("engines", base.get_engine)):
        for name, st in status[kind].items():
            if st == "ok":
                caps[kind][name] = set(getter(name).classes)
    return caps


def world_reachable(region: str, root: Path = ROOT) -> bool:
    """True when a world that covers `region` is defined (its fetch path exists) or already pulled to data/worlds."""
    for name in REGION_WORLDS.get(region, ()):
        if (root / "offsim" / "worlds" / f"{name}.yaml").is_file() or (root / "data" / "worlds" / name).is_dir():
            return True
    return False


def _factor_support(n: int) -> float:
    return min(1.0, n / SUPPORT_SATURATION)


def _factor_novelty(own: int, ref: int) -> tuple[float, str]:
    if ref == 0:
        return 0.5, "no neighbouring cell (same class or mode) to compare with: 0.5"
    return round(ref / (own + ref), 3), f"largest neighbour {ref} papers, this cell {own}: {ref}/({own}+{ref})"


def _target_region(kind: str, members: dict) -> str:
    if kind == "no-norway":
        return "Norway"
    named = set().union(*(set(t.get("region") or []) for t in members.values())) - {"none"}
    nor = sorted(named & NORWAY_REGIONS)
    if nor:
        return nor[0]
    return sorted(named)[0] if named else "none"


def _factor_feasibility(cls, engine, kind, members, caps, root) -> tuple[float, str]:
    alias = CLASS_ALIAS.get(cls, cls)
    solver = any(alias in c for c in caps["solvers"].values())
    eng = alias in caps["engines"].get(engine, set())
    region = _target_region(kind, members)
    data = world_reachable(region, root)
    value = round((int(solver) + int(eng) + int(data)) / 3, 3)
    note = (f"solver {'covers ' + alias if solver else 'none covers ' + alias}; "
            f"engine {engine} {'covers' if eng else 'does not cover'} {alias}; "
            f"data target {region} {'reachable' if data else 'not reachable (no world definition or pulled data)'}")
    return value, note


def _factor_audience(kind, mode, members) -> tuple[float, str]:
    norway = kind == "no-norway" or any(set(t.get("region") or []) & NORWAY_REGIONS for t in members.values())
    film = mode in FILMABLE_MODES
    value = 1.0 if norway and film else (0.6 if norway or film else 0.2)
    return value, (f"editorial weight: Norwegian target {'yes' if norway else 'no'}, "
                   f"filmable mode {'yes' if film else 'no'} -> {value}")


def _no_code(members: dict) -> tuple[bool, str]:
    """(emit, reason). Needs the record to carry the answer: a link, or a statement that code/data is unavailable."""
    if any(t.get("code") or t.get("data") for t in members.values()):
        return False, "a supporting paper links code or data"
    stated = sum(1 for t in members.values() if t.get("code_statement") == "unavailable")
    if stated < len(members):
        return False, f"{len(members) - stated} of {len(members)} records state nothing about code or data"
    return True, f"all {stated} records state that their code or data is unavailable (abstract text)"


def _canon(cls: str) -> str:
    return CLASS_SYNONYMS.get(cls, cls)


def _groups(tags: list[dict]) -> dict:
    """(canonical class, mode) -> {'members': {paper_id: tag}, 'raw': {class names absorbed}}. Mode 'none' is no cell."""
    groups: dict = {}
    for t in tags:
        for c, m in {(c, m) for c, m, _ in _cells(t)}:
            if m == "none":
                continue
            g = groups.setdefault((_canon(c), m), {"members": {}, "raw": set()})
            g["members"][t["paper_id"]] = t
            g["raw"].add(c)
    return groups


def find_gaps(tags: list[dict], min_support: int = 2, caps: dict | None = None, root: Path = ROOT,
              suppressed: list | None = None) -> list[dict]:
    """Gaps of the three kinds per (class, mode) with enough papers, ranked by score (highest first).

    `caps` defaults to capabilities() (what imports here). `suppressed`, when given, collects the cells where a
    no-code gap was withheld for lack of evidence, so the caller can report them.
    """
    caps = capabilities() if caps is None else caps
    groups = _groups(tags)
    gaps = []
    for key in sorted(groups):
        cls, mode = key
        members = groups[key]["members"]
        ids = sorted(members)
        if len(ids) < min_support:
            continue
        n = len(ids)
        emit_code, code_reason = _no_code(members)
        checks = {
            "no-norway": (not any(set(t.get("region") or []) & NORWAY_REGIONS for t in members.values()),
                          f"{n} papers on {cls}/{mode}; none tags a Norwegian region."),
            "no-uncertainty": (all(t.get("uncertainty", "none") == "none" for t in members.values()),
                               f"{n} papers on {cls}/{mode}; all deterministic (uncertainty none)."),
            "no-code": (emit_code,
                        f"{n} papers on {cls}/{mode}; none links code or data; {code_reason}."),
        }
        if suppressed is not None and not emit_code and not any(
                t.get("code") or t.get("data") for t in members.values()):
            suppressed.append({"cell": f"{cls}/{mode}", "papers": n, "reason": code_reason})
        engine = suggest_engine(cls, mode)
        own = n
        ref = max((len(g["members"]) for k, g in groups.items()
                   if k != key and (k[0] == cls or k[1] == mode)), default=0)
        nov, nov_note = _factor_novelty(own, ref)
        base = min(ids, key=lambda p: (-members[p].get("confidence", 0), p))
        kpis = sorted(set().union(*(set(t.get("kpis") or []) for t in members.values()))) or sorted(KPI_RULES)
        for kind in KINDS:
            hit, why = checks[kind]
            if not hit:
                continue
            fea_k, fea_note_k = _factor_feasibility(cls, engine, kind, members, caps, root)
            aud, aud_note = _factor_audience(kind, mode, members)
            sup = _factor_support(n)
            score = round(sup * nov * fea_k * aud, 4)
            entry = {
                "gap_id": f"{kind}-{cls}-{mode}".lower(), "kind": kind, "class": cls, "mode": mode,
                "support": n, "papers": ids, "why": why, "engine": engine, "status": "open",
                "base_paper": base, "kpis": kpis,
                "factors": {"support": round(sup, 3), "novelty": nov, "feasibility": fea_k, "audience": aud,
                            "score": score},
                "factor_notes": {"support": f"{n} papers, saturates at {SUPPORT_SATURATION}",
                                 "novelty": nov_note, "feasibility": fea_note_k, "audience": aud_note},
            }
            if kind == "no-code":
                entry["factor_notes"]["evidence"] = code_reason
            absorbed = sorted(groups[key]["raw"] - {cls})
            if absorbed:
                entry["synonyms"] = absorbed
            gaps.append(entry)
    gaps.sort(key=lambda g: (-g["factors"]["score"], g["gap_id"]))
    return gaps


def write_gaps(gaps: list[dict], path) -> None:
    """Write papers/gaps.yaml with a generation time and the gap list."""
    doc = {"generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "gaps": gaps}
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Gap table and ranked gap list from papers/tags.jsonl.")
    ap.add_argument("--tags", default="papers/tags.jsonl")
    ap.add_argument("--out", default="papers/gaps.yaml")
    ap.add_argument("--min-support", type=int, default=2)
    ap.add_argument("--review", default="papers/review.yaml", help="human verdicts, applied after ranking (read only)")
    args = ap.parse_args(argv)
    tags = [json.loads(l) for l in Path(args.tags).read_text().splitlines() if l.strip()]
    suppressed: list = []
    gaps = find_gaps(tags, args.min_support, suppressed=suppressed)
    for msg in apply_reviews(gaps, load_reviews(args.review)):
        print(f"review: {msg}")
    write_gaps(gaps, args.out)
    open_n = sum(1 for g in gaps if g["status"] == "open")
    print(f"gaps: {len(tags)} tagged papers, {len(gaps)} gaps ({open_n} open), {len(suppressed)} no-code cells "
          f"withheld for lack of availability evidence -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
