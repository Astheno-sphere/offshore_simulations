"""Rule-based tagger for feed records (L6). No LLM here: a second, LLM tagger may add tags later with confidence < 1.

    tag(record) -> {paper_id, classes, mode, region, uncertainty, method, code, data, kpis, tagged_by, confidence}

Rules match regular expressions against title + abstract (case-insensitive):
- classes: problem classes (CVRP, VRPTW, PDP, PSV-PDP, FSMP, HRP, MIRP, WIND-OM, WIND-INST, FERRY-SCHED,
  CREW-ROUTE). A class fires when one of its patterns matches and, where it lists `required`, one of those too.
- mode: vessel/vehicle kinds (psv, ferry, heli, ctv, sov, wtiv, truck, worker). Empty list when none.
- region: NCS, North Sea, Oslofjord, Norway, UK, Brazil, Gulf of Mexico, Baltic, Mediterranean; ["none"] when none.
  "Norwegian research council" and similar funder/institution phrases do not count as Norway.
- uncertainty: none | weather | demand | failure | multiple. One specific source gives that source; two or more
  give "multiple". Generic words only (uncertain, stochastic, robust, chance-constrained) give "multiple" too, so
  that a paper which admits uncertainty is never counted as deterministic.
- method: exact | heuristic | simulation | hybrid (two or more families, or "matheuristic"); None when unknown.
- code / data: first github/gitlab/bitbucket URL in the text is code. A zenodo/figshare/dryad/osf link is code when
  "code|software|implementation|algorithm" appears within 80 characters before it, otherwise data.
- code_statement: "unavailable" when the text says code or data is not available / on request / proprietary; None
  otherwise (silence is not evidence). The gap finder needs this before it can call a cell "no-code".
- kpis: engine-vocabulary KPI names (makespan_s, wait_s, weather_wait_s, distance_km, fuel_t, co2_t, availability,
  install_days, service_level, cost) that the text mentions.
- confidence: 0 with no class; otherwise 0.3 + 0.1 per filled field (second class hit, mode, region, method,
  specific uncertainty, code or data), capped at 0.9. A rule tag never reaches 1.

Tags only route work (see docs/ARCHITECTURE.md, "Research loop"). A tag never supplies a reported value.

CLI: python -m offsim.research.tags --feed papers/feed.jsonl --out papers/tags.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# class -> (patterns, required-any patterns or None)
CLASS_RULES = {
    "PSV-PDP": ([r"supply vessel", r"\bpsv\b", r"platform supply"], None),
    "CVRP": ([r"capacitated vehicle routing", r"\bcvrp\b"], None),
    "VRPTW": ([r"time[- ]window"], [r"vehicle rout", r"routing", r"\bvrp"]),
    "PDP": ([r"pick(?:-| )?up and deliver", r"\bpdp\b"], None),
    "FSMP": ([r"fleet size", r"fleet mix", r"\bfsmp?\b"], None),
    "HRP": ([r"helicopter", r"\bhrp\b"], None),
    "MIRP": ([r"inventory[- ]routing", r"\bmirp?\b"], None),
    "WIND-OM": ([r"\bo&m\b", r"operations? and maintenance", r"\bsov\b", r"\bctv\b",
                 r"wind farm.{0,30}maintenance"], None),
    "WIND-INST": ([r"installation vessel", r"\bwtiv\b", r"turbine installation", r"installation logistics"], None),
    "FERRY-SCHED": ([r"ferr(?:y|ies)"], [r"schedul", r"timetabl", r"charg"]),
    "CREW-ROUTE": ([r"crew transfer", r"crew (?:boat|change|rotation)", r"crew rout",
                    r"crew.{0,20}helicopter", r"helicopter.{0,20}crew"], None),
}

MODE_RULES = {
    "psv": [r"supply vessel", r"\bpsv", r"platform supply"],
    "ferry": [r"ferr(?:y|ies)"],
    "heli": [r"helicopter", r"helideck"],
    "ctv": [r"crew transfer", r"\bctv"],
    "sov": [r"service operation vessel", r"\bsov\b"],
    "wtiv": [r"installation vessel", r"\bwtiv\b", r"wind turbine installation"],
    "truck": [r"\btruck", r"\blorr(?:y|ies)\b", r"vehicle rout"],
    "worker": [r"technician", r"workforce", r"crew (?:rout|schedul)"],
}

REGION_RULES = {
    "NCS": [r"norwegian continental shelf", r"\bncs\b"],
    "North Sea": [r"north sea"],
    "Oslofjord": [r"oslo ?fjord"],
    "Norway": [r"\bnorway\b", r"norwegian(?! (?:research|council|university|institute))",
               r"\bmolde\b", r"\bstavanger\b", r"\bbergen\b", r"\btrondheim\b", r"\bkristiansund\b"],
    "UK": [r"united kingdom", r"\buk\b", r"scotland", r"aberdeen"],
    "Brazil": [r"brazil", r"campos basin", r"santos basin"],
    "Gulf of Mexico": [r"gulf of mexico"],
    "Baltic": [r"baltic"],
    "Mediterranean": [r"mediterranean"],
}
NORWAY_REGIONS = frozenset({"NCS", "Oslofjord", "Norway"})

UNCERTAINTY_RULES = {
    "weather": [r"weather", r"wave height", r"significant wave", r"wind speed", r"metocean", r"sea state"],
    "demand": [r"stochastic demand", r"uncertain demand", r"demand uncertaint"],
    "failure": [r"failure", r"breakdown", r"unplanned maintenance", r"reliability", r"availability"],
}
GENERIC_UNCERTAINTY = [r"uncertain", r"stochastic", r"robust", r"chance[- ]constrained"]

METHOD_RULES = {
    "exact": [r"branch[- ](?:and|&)[- ](?:price|cut|bound)", r"column generation", r"mixed[- ]integer",
              r"\bmip\b", r"\bmilp\b", r"exact (?:algorithm|solution|method)"],
    "heuristic": [r"heuristic", r"genetic algorithm", r"large neighbou?rhood", r"\balns\b", r"tabu",
                  r"simulated annealing", r"particle swarm"],
    "simulation": [r"simulat(?!ed annealing)", r"discrete[- ]event", r"agent[- ]based", r"monte carlo"],
}

# An abstract that says the code or data is not available is evidence about availability; silence is not.
# Used only as evidence for a no-code gap (offsim/research/gaps.py): a record with neither a link nor such a
# statement says nothing about code, so it cannot support "no code" (abstracts rarely mention code at all).
UNAVAILABLE = [
    r"(?:code|data|software|implementation|dataset)s?\b[^.;]{0,60}\b(?:is |are )?(?:not|never|no longer) "
    r"(?:publicly |openly )?(?:available|released|shared|published)",
    r"(?:available|shared|provided|released)\s+(?:up)?on\s+request",
    r"(?:proprietary|confidential|commercially sensitive) (?:data|dataset|information|model)",
]

CODE_LINK = re.compile(r"https?://(?:www\.)?(?:github\.com|gitlab\.com|bitbucket\.org)/[\w.\-]+/[\w.\-]+", re.I)
ARCHIVE_LINK = re.compile(r"https?://(?:www\.)?(?:zenodo\.org|figshare\.com|datadryad\.org|osf\.io)/[^\s)\]>\"']*"
                          r"|10\.5281/zenodo\.\d+", re.I)
KPI_RULES = {
    "makespan_s": [r"makespan", r"completion time"],
    "wait_s": [r"waiting time", r"wait(?:ing)? time", r"idle time"],
    "weather_wait_s": [r"weather[- ](?:delay|wait|downtime)"],
    "distance_km": [r"travel distance", r"route length", r"total distance"],
    "fuel_t": [r"\bfuel\b"],
    "co2_t": [r"\bco2\b", r"emission", r"carbon"],
    "availability": [r"availability"],
    "install_days": [r"installation (?:time|duration)"],
    "service_level": [r"service level"],
    "cost": [r"\bcosts?\b"],
}


def _hits(text: str, patterns) -> int:
    return sum(1 for p in patterns if re.search(p, text, re.I))


def _classes(text: str) -> tuple[list[str], int]:
    """Classes that fired, and the number of pattern hits across them."""
    out, n = [], 0
    for cls, (pats, required) in CLASS_RULES.items():
        k = _hits(text, pats)
        if k and (required is None or _hits(text, required)):
            out.append(cls)
            n += k
    return out, n


def _uncertainty(text: str) -> str:
    specific = [u for u, pats in UNCERTAINTY_RULES.items() if _hits(text, pats)]
    if len(specific) == 1:
        return specific[0]
    if specific or _hits(text, GENERIC_UNCERTAINTY):
        return "multiple"
    return "none"


def _method(text: str) -> str | None:
    if re.search(r"matheuristic", text, re.I):
        return "hybrid"
    families = [m for m, pats in METHOD_RULES.items() if _hits(text, pats)]
    if len(families) >= 2:
        return "hybrid"
    return families[0] if families else None


def _code_and_data(text: str) -> tuple[str | None, str | None]:
    m = CODE_LINK.search(text)
    code = m.group(0).rstrip(".,;") if m else None
    data = None
    for z in ARCHIVE_LINK.finditer(text):
        link = z.group(0).rstrip(".,;")
        before = text[max(0, z.start() - 80):z.start()]
        if re.search(r"code|software|implementation|algorithm", before, re.I):
            code = code or link
        elif data is None:
            data = link
    return code, data


def _code_statement(text: str) -> str | None:
    """'unavailable' when the record says its code or data cannot be had; None when it says nothing either way."""
    return "unavailable" if _hits(text, UNAVAILABLE) else None


def tag(record: dict) -> dict:
    """Rule tags for one feed record. Pure function: same record, same tags."""
    text = f"{record.get('title', '')} {record.get('abstract', '')}"
    plain = re.sub(r"https?://\S+", " ", text)  # keyword rules ignore URLs ("routing" in a repo name is no class)
    classes, class_hits = _classes(plain)
    modes = [m for m, pats in MODE_RULES.items() if _hits(plain, pats)]
    regions = [r for r, pats in REGION_RULES.items() if _hits(plain, pats)] or ["none"]
    uncertainty = _uncertainty(plain)
    method = _method(plain)
    code, data = _code_and_data(text)
    kpis = [k for k, pats in KPI_RULES.items() if _hits(plain, pats)]
    code_statement = _code_statement(plain)
    if not classes:
        confidence = 0.0
    else:
        filled = (len(modes) > 0) + (regions != ["none"]) + (method is not None) \
            + (uncertainty not in ("none",)) + (code is not None or data is not None) + (class_hits >= 2)
        confidence = round(min(0.9, 0.3 + 0.1 * filled), 2)
    return {
        "paper_id": record["id"], "classes": classes, "mode": modes, "region": regions,
        "uncertainty": uncertainty, "method": method, "code": code, "data": data, "code_statement": code_statement,
        "kpis": kpis, "tagged_by": "rule", "confidence": confidence,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Rule-tag papers/feed.jsonl into papers/tags.jsonl.")
    ap.add_argument("--feed", default="papers/feed.jsonl")
    ap.add_argument("--out", default="papers/tags.jsonl")
    args = ap.parse_args(argv)
    rows = [json.loads(l) for l in Path(args.feed).read_text().splitlines() if l.strip()]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(tag(r), ensure_ascii=False) + "\n" for r in rows))
    print(f"tags: {len(rows)} records -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
