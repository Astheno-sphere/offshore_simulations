"""Gap table over rule tags (L6): which (problem class, mode) areas are well covered and where a kind of paper is missing.

    gap_table(tags)                     -> DataFrame: observed counts per (class, mode, region, uncertainty)
    find_gaps(tags, min_support=2)      -> list of gap dicts (kinds below)
    write_gaps(gaps, path)              -> papers/gaps.yaml

Gap kinds, evaluated per (class, mode) with at least `min_support` papers:
- no-norway:      no supporting paper has a Norwegian region (NCS, Oslofjord, Norway). The method exists but has
                  never been shown on Norwegian geography.
- no-uncertainty: every supporting paper has uncertainty "none". Only deterministic results exist.
- no-code:        no supporting paper links code or data. The result cannot be reproduced from the paper alone.

Each gap carries: gap_id, kind, class, mode, support, papers (ids), why, engine (suggested, from docs/ENGINES.md
"Choosing"), status "open". Engine rules, class first: WIND-INST -> orbit; WIND-OM -> wombat; HRP -> air (WFPPP);
VRPTW -> replay; CVRP -> openclsim for psv, ferry, ctv, else replay. Classes no engine covers (PSV-PDP, PDP, FSMP,
MIRP, ...) follow the mode: wtiv -> orbit; sov -> wombat; heli -> air; psv, ferry, ctv -> openclsim (replay checks
the plan first); else replay. Truck cases are judgement calls: confirm them before a gap becomes an experiment.

A gap is a lead, not a result. Tags route work only; values come from paper-extract with page sources.

CLI: python -m offsim.research.gaps --tags papers/tags.jsonl --out papers/gaps.yaml --min-support 2
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

from offsim.research.tags import NORWAY_REGIONS

KINDS = ("no-norway", "no-uncertainty", "no-code")
COLUMNS = ["class", "mode", "region", "uncertainty", "n"]


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


def find_gaps(tags: list[dict], min_support: int = 2) -> list[dict]:
    """Gaps of the three kinds for every (class, mode) pair with enough papers. Sorted by kind, class, mode."""
    groups: dict[tuple[str, str], dict[str, dict]] = {}
    for t in tags:
        for c, m in {(c, m) for c, m, _ in _cells(t)}:
            groups.setdefault((c, m), {})[t["paper_id"]] = t

    gaps = []
    for (cls, mode), by_id in sorted(groups.items()):
        members = list(by_id.values())
        if mode == "none" or len(members) < min_support:
            continue
        ids = sorted(by_id)
        checks = {
            "no-norway": (not any(set(t.get("region") or []) & NORWAY_REGIONS for t in members),
                          f"{len(ids)} papers on {cls}/{mode}; none tags a Norwegian region."),
            "no-uncertainty": (all(t.get("uncertainty", "none") == "none" for t in members),
                               f"{len(ids)} papers on {cls}/{mode}; all deterministic (uncertainty none)."),
            "no-code": (not any(t.get("code") or t.get("data") for t in members),
                        f"{len(ids)} papers on {cls}/{mode}; none links code or data."),
        }
        for kind in KINDS:
            hit, why = checks[kind]
            if hit:
                gaps.append({
                    "gap_id": f"{kind}-{cls}-{mode}".lower(), "kind": kind, "class": cls, "mode": mode,
                    "support": len(ids), "papers": ids, "why": why,
                    "engine": suggest_engine(cls, mode), "status": "open",
                })
    return gaps


def write_gaps(gaps: list[dict], path) -> None:
    """Write papers/gaps.yaml with a generation time and the gap list."""
    doc = {"generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "gaps": gaps}
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Gap table and gap list from papers/tags.jsonl.")
    ap.add_argument("--tags", default="papers/tags.jsonl")
    ap.add_argument("--out", default="papers/gaps.yaml")
    ap.add_argument("--min-support", type=int, default=2)
    args = ap.parse_args(argv)
    tags = [json.loads(l) for l in Path(args.tags).read_text().splitlines() if l.strip()]
    gaps = find_gaps(tags, args.min_support)
    write_gaps(gaps, args.out)
    print(f"gaps: {len(tags)} tagged papers, {len(gaps)} gaps -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
