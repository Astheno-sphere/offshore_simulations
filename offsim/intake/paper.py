"""Paper PDF -> DRAFT with page-referenced evidence (audit 5, fix 3).

RULE: drafts are evidence, not values. Nothing written here is trusted. Every scenario field in
`scenario.draft.yaml` is `{value: null, src: null, candidates: [...]}`; the paper-extract step (Claude or a human)
confirms each value against its page and moves it into a real `scenario.yaml` with `src:` (page/table) or
`assumption: true`. The `.draft.yaml` suffix and the null values keep gate 0 from running a draft.

    python -m offsim.intake.paper <pdf> [--out offsim/papers]

Functions:
    extract(pdf)     -> {source, metadata, headings, pages: [{page, text, tables}], warnings}
    evidence(ex)     -> [{kind, value, unit, orig_value, orig_unit, page, snippet, source, label?}]
                        value/unit are SI (m/s, s, m, kg, m3/s, kg/s); the original is kept in orig_*.
    classify(ex)     -> offsim.research.tags.tag() on title + abstract (rule tags, confidence < 1)
    draft(pdf, out)  -> Path of offsim/papers/<slug>/ with extract.json, evidence.csv, scenario.draft.yaml,
                        timetable.draft.yaml (ferry/bus papers), notes.md

Open source only (pdfplumber MIT, pypdf BSD). Scanned PDFs have no text layer: this reports them and stops short
(OCR would be a later option: ocrmypdf / Tesseract). Only open-access figures may be redistributed; the PDF itself
is never copied into the draft folder.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

import yaml

DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s\"<>]+)")
YEAR_RE = re.compile(r"(?<!\d)((?:19[89]|20[0-3])\d)(?!\d)")
HEADING_RE = re.compile(r"^(?:(?:\d{1,2}(?:\.\d{1,2}){0,3}\.?)\s+[A-Z][^\n]{2,80}"
                        r"|(?:Abstract|Introduction|Literature review|Related work|Problem description|Methodology|"
                        r"Methods?|Computational (?:study|results|experiments)|Case study|Results|Discussion|"
                        r"Conclusions?|References|Appendix)\b[^\n]{0,40})$")

# ---------------------------------------------------------------- units
KN = 1852 / 3600
UNIT_SI = {  # normalised unit -> (factor, SI unit)
    "kn": (KN, "m/s"), "kt": (KN, "m/s"), "knot": (KN, "m/s"), "knots": (KN, "m/s"),
    "km/h": (1 / 3.6, "m/s"), "kmh": (1 / 3.6, "m/s"), "m/s": (1.0, "m/s"),
    "t": (1000.0, "kg"), "tonne": (1000.0, "kg"), "tonnes": (1000.0, "kg"), "ton": (1000.0, "kg"), "tons": (1000.0, "kg"),
    "kg": (1.0, "kg"),
    "m3": (1.0, "m3"), "m^3": (1.0, "m3"), "m³": (1.0, "m3"),
    "h": (3600.0, "s"), "hr": (3600.0, "s"), "hrs": (3600.0, "s"), "hour": (3600.0, "s"), "hours": (3600.0, "s"),
    "min": (60.0, "s"), "mins": (60.0, "s"), "minute": (60.0, "s"), "minutes": (60.0, "s"),
    "s": (1.0, "s"), "sec": (1.0, "s"), "second": (1.0, "s"), "seconds": (1.0, "s"),
    "nm": (1852.0, "m"), "nmi": (1852.0, "m"), "nautical miles": (1852.0, "m"), "nautical mile": (1852.0, "m"),
    "km": (1000.0, "m"), "m": (1.0, "m"),
}


def to_si(value: float, unit: str) -> tuple[float, str]:
    """Convert (value, unit) to SI when the unit is known; otherwise return it unchanged."""
    u = unit.strip().lower()
    if u in UNIT_SI:
        f, si = UNIT_SI[u]
        return value * f, si
    return value, unit.strip()


def _num(s: str) -> float:
    s = s.replace(" ", "").replace(" ", "").replace(" ", "")
    if re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", s):
        s = s.replace(",", "")
    else:
        s = s.replace(",", ".")
    return float(s)


NUM = r"(?<![\w.])(\d{1,3}(?:[   ,]\d{3})+(?:\.\d+)?(?!\d)|\d+(?:[.,]\d+)?)"
WORDNUM = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve".split())}
NOUNS_FLEET = r"(?:PSVs?|vessels?|ships?|ferr(?:y|ies)|helicopters?|aircraft|buses|bus|trucks?|vehicles?|boats?|CTVs?|SOVs?|tugs?)"
NOUNS_SIZE = (r"(?:customers?|installations?|nodes?|platforms?|ports?|sites?|requests?|orders?|locations?|"
              r"demand points|stops|turbines?|wind farms?|offshore units?)")

SPEED = re.compile(NUM + r"\s*(knots?|kn|kt|km/h|m/s)(?![\w/])", re.I)
CAP_UNITS = re.compile(NUM + r"\s*(tonnes?|tons?|t|m3|m\^3|m³|TEU|passengers?|pax|deck m2|m2)(?![\w/²])", re.I)
TIME = re.compile(NUM + r"\s*(hours?|hrs?|h|minutes?|mins?|min|seconds?|sec|s)(?![\w/])", re.I)
DIST = re.compile(NUM + r"\s*(nautical miles?|nmi|nm|km)(?![\w/²])", re.I)
FUEL = re.compile(NUM + r"\s*(tonnes?|tons?|t|kg|litres?|liters?|l)\s*(?:/|per\s+)\s*(day|d|h|hour|nm|km)(?!\w)", re.I)
COST_A = re.compile(NUM + r"\s*(million\s+|mill\.?\s+|MNOK\b)?\s*(NOK|USD|EUR|kr\b|\$|€)(\s*(?:/|per\s+|a\s+)\s*(?:day|hour|h|d|nm|km)\b)?", re.I)
COST_B = re.compile(r"(NOK|USD|EUR|\$|€)\s*" + NUM + r"(\s*(?:/|per\s+)\s*(?:day|hour|h|d|nm|km)\b)?", re.I)
FLEET = re.compile(r"(?<![\w.])(\d+|" + "|".join(WORDNUM) + r")\s+(?:[A-Za-z-]+\s+)?(" + NOUNS_FLEET + r")\b", re.I)
SIZE = re.compile(NUM + r"\s+(?:[A-Za-z-]+\s+)?(" + NOUNS_SIZE + r")\b", re.I)
SIZE_N = re.compile(r"\b[nN]\s*=\s*(\d+)")
HS = re.compile(r"(?:\bHs\b|significant wave height|wave height)[^.\d]{0,40}?" + NUM + r"\s*m(?![\w/])", re.I)
WIND = re.compile(r"wind(?: speed)?[^.\d]{0,30}?" + NUM + r"\s*m/s", re.I)
TW_CLOCK = re.compile(r"(?:between|from)\s+(\d{1,2}[:.]\d{2})\s+(?:and|to|-)\s+(\d{1,2}[:.]\d{2})", re.I)
KPI = re.compile(r"\b(total cost|objective(?: value| function)?|optimality gap|gap|makespan|total distance|"
                 r"fuel consumption|total emissions|emissions)\b[^.\d%]{0,40}?" + NUM + r"\s*(%|[A-Za-z]{1,6}(?:/\w+)?)?", re.I)
KPI_KEY = {"total cost": "total_cost", "objective": "objective", "optimality gap": "gap_pct", "gap": "gap_pct",
           "makespan": "makespan_s", "total distance": "distance_km", "fuel consumption": "fuel_t",
           "total emissions": "co2_t", "emissions": "co2_t"}

KW = {  # context keywords -> kind (checked in order)
    "time": [("time_window", r"time[- ]windows?|\btw\b|opening hours|available between"),
             ("headway", r"headway|interval|frequency|every"),
             ("dwell", r"dwell|stop time"),
             ("run_time", r"run(?:ning)? time|travel time|sailing time|crossing time"),
             ("service", r"service|handling|unloading|loading|turnaround|berth|alongside|operation time")],
    "qty": [("demand", r"demand"), ("capacity", r"capacity|payload|deadweight|dwt|carr(?:y|ies)|load")],
}


def _sentences(text: str) -> list[str]:
    flat = re.sub(r"\s*\n\s*", " ", text)
    return [s.strip() for s in re.split(r"(?<=[.;!?])\s+(?=[A-Z0-9(\[])", flat) if s.strip()]


def _snip(s: str, a: int, b: int, width: int = 260) -> str:
    if len(s) <= width:
        return s
    lo = max(0, min(a - 80, len(s) - width))
    return ("..." if lo else "") + s[lo:lo + width] + ("..." if lo + width < len(s) else "")


def _ev(kind, value, unit, page, snippet, source="text", **extra):
    sv, su = to_si(value, unit)
    d = {"kind": kind, "value": round(sv, 6), "unit": su, "orig_value": value, "orig_unit": unit,
         "page": page, "snippet": snippet, "source": source}
    d.update(extra)
    return d


# ---------------------------------------------------------------- extraction
def _first_page_meta(page) -> dict:
    words = page.extract_words(extra_attrs=["size"], keep_blank_chars=False, use_text_flow=False)
    if not words:
        return {"title": "", "authors": []}
    lines: dict[int, list] = {}
    for w in words:
        lines.setdefault(round(w["top"] / 3), []).append(w)
    rows = []
    for k in sorted(lines):
        ws = sorted(lines[k], key=lambda w: w["x0"])
        rows.append((" ".join(w["text"] for w in ws), max(w["size"] for w in ws), ws[0]["top"]))
    top = max(r[1] for r in rows)
    title_rows = [r for r in rows if r[1] >= top - 0.6]
    first = rows.index(title_rows[0])
    # contiguous block of title-sized lines
    block = []
    for r in rows[first:]:
        if r[1] >= top - 0.6:
            block.append(r)
        else:
            break
    title = " ".join(r[0] for r in block).strip()
    authors: list[str] = []
    for r in rows[first + len(block):first + len(block) + 4]:
        t = r[0]
        if re.match(r"(abstract|keywords?|doi|received|https?:)", t, re.I) or re.search(r"@|universit|institute|department", t, re.I):
            if authors:
                break
            continue
        if sum(c.isdigit() for c in t) > 3 or len(t) > 140:
            continue
        parts = [p.strip(" ,*†‡0123456789") for p in re.split(r",|\band\b|&|;", t)]
        names = [p for p in parts if re.fullmatch(r"[A-ZÆØÅ][\w.'’-]*(?:\s+[A-ZÆØÅ]?[\w.'’-]+){0,4}", p)]
        if names:
            authors = names
            break
    return {"title": title, "authors": authors}


def extract(pdf) -> dict:
    """Per page text and tables (pdfplumber), plus best-effort metadata and section headings."""
    import pdfplumber
    pdf = Path(pdf)
    data = pdf.read_bytes()
    pages, warnings, meta_pdf = [], [], {}
    first_meta = {"title": "", "authors": []}
    with pdfplumber.open(pdf) as doc:
        meta_pdf = {k: str(v) for k, v in (doc.metadata or {}).items()}
        for i, page in enumerate(doc.pages, start=1):
            text = page.extract_text() or ""
            tables = []
            try:
                for t in page.extract_tables():
                    rows = [[(c or "").replace("\n", " ").strip() for c in row] for row in t if row]
                    if len(rows) >= 2:
                        tables.append({"page": i, "rows": rows})
            except Exception as e:  # pragma: no cover - pdfplumber edge cases
                warnings.append(f"p.{i}: table extraction failed: {e}")
            if len(text.strip()) < 20:
                warnings.append(f"p.{i}: no text layer (scanned? OCR needed: ocrmypdf/Tesseract)")
            pages.append({"page": i, "text": text, "tables": tables})
            if i == 1:
                first_meta = _first_page_meta(page)
    full1 = pages[0]["text"] if pages else ""
    alltext = "\n".join(p["text"] for p in pages)
    doi_m = DOI_RE.search(full1) or DOI_RE.search(alltext)
    doi = doi_m.group(1).rstrip(".,;)") if doi_m else ""
    years = [int(y) for y in YEAR_RE.findall(full1)]
    year = None
    if years:
        c = Counter(years)
        year = max(c, key=lambda y: (c[y], y))
    title = first_meta["title"] or re.sub(r"\.pdf$", "", meta_pdf.get("Title", "")) or (full1.splitlines() or [""])[0]
    headings = []
    for p in pages:
        for line in p["text"].splitlines():
            line = line.strip()
            if HEADING_RE.match(line) and len(line) < 90 and not re.search(r"[.,]\s*$", line.rstrip(".")) :
                headings.append({"page": p["page"], "heading": line})
    abstract = ""
    m = re.search(r"\bAbstract\b[:.\s—-]*(.+?)(?=\n\s*(?:Keywords?|Key words|1\.?\s+Introduction|Introduction)\b|\Z)", full1, re.S | re.I)
    if m:
        abstract = re.sub(r"\s+", " ", m.group(1)).strip()[:2500]
    return {
        "source": {"file": pdf.name, "sha256": hashlib.sha256(data).hexdigest(), "pages": len(pages)},
        "metadata": {"title": title, "authors": first_meta["authors"], "doi": doi, "year": year,
                     "abstract": abstract, "pdf_info": meta_pdf},
        "headings": headings, "pages": pages, "warnings": warnings,
    }


# ---------------------------------------------------------------- evidence
def _kind_by_kw(ctx: str, group: str):
    for kind, pat in KW[group]:
        if re.search(pat, ctx, re.I):
            return kind
    return None


def _text_evidence(page: int, text: str) -> list[dict]:
    out = []
    for s in _sentences(text):
        for m in SPEED.finditer(s):
            out.append(_ev("speed", _num(m.group(1)), m.group(2).lower(), page, _snip(s, m.start(), m.end())))
        for m in CAP_UNITS.finditer(s):
            unit = m.group(2)
            u = unit.lower()
            ctx = s[max(0, m.start() - 70):m.end() + 30]
            if u in ("teu", "passenger", "passengers", "pax", "deck m2", "m2"):
                kind = "demand" if re.search("demand", ctx, re.I) else "capacity"
                if u == "m2" and "deck" not in ctx.lower():
                    continue
                unit = "deck m2" if u == "m2" else ("passengers" if u.startswith("pass") else unit)
            else:
                kind = _kind_by_kw(ctx, "qty")
                if not kind:
                    continue
            out.append(_ev(kind, _num(m.group(1)), unit if unit.lower() == "teu" else unit.lower() if u in UNIT_SI else unit,
                           page, _snip(s, m.start(), m.end())))
        for m in TIME.finditer(s):
            ctx = s[max(0, m.start() - 70):m.end() + 30]
            kind = _kind_by_kw(ctx, "time")
            if kind:
                out.append(_ev(kind, _num(m.group(1)), m.group(2).lower(), page, _snip(s, m.start(), m.end())))
        for m in TW_CLOCK.finditer(s):
            out.append(_ev("time_window", 0.0, "", page, _snip(s, m.start(), m.end()),
                           orig_value=f"{m.group(1)}-{m.group(2)}", orig_unit="clock"))
        for m in DIST.finditer(s):
            out.append(_ev("distance", _num(m.group(1)), m.group(2).lower(), page, _snip(s, m.start(), m.end())))
        for m in FUEL.finditer(s):
            v, mu, per = _num(m.group(1)), m.group(2).lower(), m.group(3).lower()
            mass = mu in ("t", "tonne", "tonnes", "ton", "tons", "kg")
            kg = v * (1000 if mu in ("t", "tonne", "tonnes", "ton", "tons") else 1) if mass else v / 1000  # litres -> m3
            den = {"day": 86400, "d": 86400, "h": 3600, "hour": 3600, "nm": 1852, "km": 1000}[per]
            unit = ("kg" if mass else "m3") + ("/s" if per in ("day", "d", "h", "hour") else "/m")
            e = _ev("fuel", kg / den, unit, page, _snip(s, m.start(), m.end()))
            e["orig_value"], e["orig_unit"] = v, f"{m.group(2)}/{per}"
            out.append(e)
        costs = [(m, m.group(3) if m.re is COST_A else m.group(1), _num(m.group(1) if m.re is COST_A else m.group(2)),
                  m.group(2) if m.re is COST_A else None, m.group(4) if m.re is COST_A else m.group(3))
                 for m in list(COST_A.finditer(s)) + list(COST_B.finditer(s))]
        seen_pos = set()
        for m, cur, v, mult, per in costs:
            if m.start() in seen_pos:
                continue
            seen_pos.add(m.start())
            if mult:
                v *= 1e6  # "million" / "mill." / MNOK
            cur = {"kr": "NOK", "$": "USD", "€": "EUR"}.get(cur.lower(), cur.upper())
            rate = re.sub(r"\s+", "", per or "").replace("per", "/").replace("a", "/") if per else ""
            unit = cur + (rate if rate.startswith("/") else (("/" + rate) if rate else ""))
            out.append(_ev("cost_rate" if rate else "cost", v, unit, page, _snip(s, m.start(), m.end())))
        for m in FLEET.finditer(s):
            w = m.group(1).lower()
            n = int(w) if w.isdigit() else WORDNUM[w]
            out.append(_ev("fleet_size", float(n), m.group(2), page, _snip(s, m.start(), m.end())))
        for m in SIZE.finditer(s):
            out.append(_ev("instance_size", _num(m.group(1)), m.group(2).lower(), page, _snip(s, m.start(), m.end())))
        for m in SIZE_N.finditer(s):
            out.append(_ev("instance_size", float(m.group(1)), "n", page, _snip(s, m.start(), m.end())))
        for m in HS.finditer(s):
            out.append(_ev("weather_limit_hs", _num(m.group(1)), "m", page, _snip(s, m.start(), m.end())))
        for m in WIND.finditer(s):
            out.append(_ev("weather_limit_wind", _num(m.group(1)), "m/s", page, _snip(s, m.start(), m.end())))
        for m in KPI.finditer(s):
            label = KPI_KEY[m.group(1).lower()]
            out.append(_ev("reported_kpi", _num(m.group(2)), (m.group(3) or "").strip(), page,
                           _snip(s, m.start(), m.end()), label=label))
    return out


HEADER_KIND = [("speed", r"speed"), ("capacity", r"capacity|payload|deadweight|dwt"), ("demand", r"demand"),
               ("service", r"service|handling|unloading|loading"), ("time_window", r"time window|\btw\b"),
               ("cost", r"cost|price|charter|rate"), ("distance", r"distance|length"),
               ("fuel", r"fuel"), ("fleet_size", r"number of|no\. of|count|vessels|fleet"),
               ("instance_size", r"customers|installations|nodes|size")]


def _table_evidence(t: dict) -> list[dict]:
    rows, page = t["rows"], t["page"]
    hdr = rows[0]
    cols = []
    for j, h in enumerate(hdr):
        m = re.match(r"(.*?)\s*[\(\[]\s*([^\)\]]+?)\s*[\)\]]\s*$", h)
        name, unit = (m.group(1), m.group(2)) if m else (h, "")
        kind = next((k for k, pat in HEADER_KIND if re.search(pat, name, re.I)), None)
        cols.append((kind, unit))
    out = []
    for r in rows[1:]:
        label = r[0] if r else ""
        for j, cell in enumerate(r):
            if j == 0 or j >= len(cols) or not cols[j][0] or not cell:
                continue
            m = re.fullmatch(NUM, cell.strip())
            if not m:
                continue
            kind, unit = cols[j]
            snippet = f"table p.{page}: " + " | ".join(hdr) + " // " + " | ".join(r)
            out.append(_ev(kind, _num(m.group(1)), unit, page, snippet[:300], source="table", row=label))
    return out


def evidence(ex: dict) -> list[dict]:
    """Regex candidates for scenario fields, with page and snippet. Candidates only: nothing is confirmed."""
    out = []
    for p in ex["pages"]:
        out += _text_evidence(p["page"], p["text"])
        for t in p["tables"]:
            out += _table_evidence(t)
    seen, uniq = set(), []
    for e in out:
        key = (e["kind"], e["value"], e["unit"], e["page"], e["snippet"][:80], e.get("label"))
        if key not in seen:
            seen.add(key)
            uniq.append(e)
    return uniq


def classify(ex: dict) -> dict:
    """Rule tags (offsim.research.tags.tag) on title + abstract. Routing only; never a source of values."""
    from offsim.research.tags import tag
    md = ex["metadata"]
    rec = {"id": md.get("doi") or ex["source"]["file"], "title": md.get("title", ""), "abstract": md.get("abstract", "")}
    if not rec["abstract"] and ex["pages"]:  # no abstract heading: fall back on the first page
        rec["abstract"] = re.sub(r"\s+", " ", ex["pages"][0]["text"])[:2500]
    return tag(rec)


# ---------------------------------------------------------------- draft files
def slugify(ex: dict, fallback: str) -> str:
    md = ex["metadata"]
    parts = []
    if md.get("authors"):
        parts.append(md["authors"][0].split()[-1])
    if md.get("year"):
        parts.append(str(md["year"]))
    stop = {"a", "an", "the", "of", "for", "and", "in", "on", "to", "with", "by", "problem", "approach", "model"}
    words = [w for w in re.findall(r"[A-Za-z]+", md.get("title", "")) if w.lower() not in stop]
    parts += words[:2]
    slug = re.sub(r"[^a-z0-9]+", "-", "-".join(parts).lower()).strip("-")
    return slug or re.sub(r"[^a-z0-9]+", "-", fallback.lower()).strip("-") or "paper"


def _cand(ev, kinds, label=None, limit=10):
    sel = [e for e in ev if e["kind"] in kinds and (label is None or e.get("label") == label)]
    sel.sort(key=lambda e: (e["page"], e["source"] != "table"))
    return [{"value": e["value"], "unit": e["unit"], "orig": f"{e['orig_value']} {e['orig_unit']}".strip(),
             "page": e["page"], "snippet": e["snippet"]} for e in sel[:limit]]


def _field(ev, kinds, label=None, **extra):
    return {"value": None, "src": None, **extra, "candidates": _cand(ev, kinds, label)}


def scenario_draft(ex: dict, ev: list[dict], tags: dict, slug: str) -> dict:
    md = ex["metadata"]
    kpis = ["total_cost", "objective", "gap_pct", "makespan_s", "distance_km", "fuel_t", "co2_t"]
    return {
        "draft": True,
        "paper": {"id": slug, "title": md.get("title", ""), "authors": md.get("authors", []), "year": md.get("year"),
                  "doi": md.get("doi", ""), "licence": None},
        "problem": {"class": {"value": None, "src": None, "candidates": [{"value": c, "page": None, "snippet": "rule tag"}
                                                                       for c in tags["classes"]]},
                    "objective": _field(ev, ["reported_kpi"], None, hint="what the paper minimises"),
                    "constraints": [], "solver": None},
        "world": None,
        "fleet": [{"cls": {"value": None, "src": None,
                           "candidates": [{"value": m, "page": None, "snippet": "rule tag"} for m in tags["mode"]]},
                   "count": _field(ev, ["fleet_size"]),
                   "capacity": _field(ev, ["capacity"], unit=None),
                   "speed_mps": _field(ev, ["speed"]),
                   "domain": None, "base": None}],
        "instance": {"source": None, "file": None,
                     "size": _field(ev, ["instance_size"]),
                     "service_s": _field(ev, ["service"]),
                     "demand": _field(ev, ["demand"]),
                     "time_windows": _field(ev, ["time_window"]),
                     "distances_m": _field(ev, ["distance"]),
                     "base": {"name": None, "lon": None, "lat": None, "src": None},
                     "stops": []},
        "costs": {"cost": _field(ev, ["cost"]), "cost_rate": _field(ev, ["cost_rate"]), "fuel": _field(ev, ["fuel"])},
        "sim": {"shared_resources": {},
                "weather_limit_hs_m": _field(ev, ["weather_limit_hs"]),
                "weather_limit_wind_mps": _field(ev, ["weather_limit_wind"])},
        "reported": {k: _field(ev, ["reported_kpi"], k) for k in kpis},
        "story": {"question": None, "accent": None, "comparison": None},
    }


def wants_timetable(ex: dict, tags: dict) -> bool:
    md = ex["metadata"]
    text = f"{md.get('title', '')} {md.get('abstract', '')}"
    return bool({"ferry"} & set(tags["mode"])) or bool(re.search(r"\bbus(?:es)?\b|timetabl|headway", text, re.I))


def timetable_draft(ex: dict, ev: list[dict], tags: dict) -> dict:
    md = ex["metadata"]
    mode = "ferry" if "ferry" in tags["mode"] else "bus"
    return {
        "draft": True,
        "source": {"paper": md.get("title", ""), "doi": md.get("doi", "")},
        "service": {"days": None, "start_date": None, "end_date": None},
        "lines": [{
            "id": None, "mode": mode,
            "stops": [{"id": None, "name": None, "lon": None, "lat": None, "src": None}],
            "run_time_min": _field(ev, ["run_time"]),
            "dwell_s": _field(ev, ["dwell"]),
            "headway_min": _field(ev, ["headway"]),
            "first": None, "last": None, "both_directions": None,
        }],
    }


CSV_COLS = ["kind", "value", "unit", "orig_value", "orig_unit", "page", "source", "label", "row", "snippet"]
REQUIRED = [("fleet_size", "fleet count"), ("speed", "vessel speed"), ("capacity", "vehicle capacity"),
            ("demand", "demand per stop"), ("service", "service/handling time"), ("time_window", "time windows"),
            ("distance", "distances"), ("instance_size", "instance size"), ("reported_kpi", "reported KPIs")]


def notes(ex: dict, ev: list[dict], tags: dict, tt: bool) -> str:
    md = ex["metadata"]
    c = Counter(e["kind"] for e in ev)
    L = [f"# Draft notes: {md.get('title') or ex['source']['file']}", "",
         "DRAFT ONLY. Everything here is a candidate; paper-extract confirms each value against its page "
         "(`src: p.X Table Y`) or marks it `assumption: true`.", "",
         "## Source",
         f"- file: {ex['source']['file']} (sha256 {ex['source']['sha256'][:16]}..., {ex['source']['pages']} pages)",
         f"- DOI: {md.get('doi') or 'not found'}; year: {md.get('year') or 'not found'}",
         f"- authors (best effort): {', '.join(md.get('authors', [])) or 'not found'}", "",
         "## Classification (rule tags, routing only)",
         f"- classes: {', '.join(tags['classes']) or 'none'}; mode: {', '.join(tags['mode']) or 'none'}; "
         f"region: {', '.join(tags['region'])}",
         f"- uncertainty: {tags['uncertainty']}; method: {tags['method']}; confidence: {tags['confidence']}",
         f"- code: {tags['code']}; data: {tags['data']}", "",
         "## Evidence found (count by kind)"]
    L += [f"- {k}: {n}" for k, n in sorted(c.items())] or ["- none"]
    L += ["", "## Missing (no candidate found; check the paper by hand or fill by assumption)"]
    miss = [label for k, label in REQUIRED if not c.get(k)]
    L += [f"- {m}" for m in miss] or ["- nothing obviously missing"]
    L += ["- always by hand: stop coordinates (lon/lat), base quay, objective definition, constraints, instance files"]
    if ex["warnings"]:
        L += ["", "## Warnings"] + [f"- {w}" for w in ex["warnings"]]
    L += ["", "## Files",
          "- extract.json: full text and tables per page", "- evidence.csv: all candidates",
          "- scenario.draft.yaml: template-shaped, all values null with candidates (gate 0 must refuse it)"]
    if tt:
        L += ["- timetable.draft.yaml: ferry/bus paper; schema in offsim/transit/from_paper.py"]
    L += ["", "## Licence",
          "Only open-access (CC BY etc.) figures and instance data may be redistributed. The PDF is not copied here. "
          "Record the paper's licence in `paper.licence` before using any figure or table in a film."]
    return "\n".join(L) + "\n"


def _dump(path: Path, data: dict, header: str):
    path.write_text(header + yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=120))


def draft(pdf, out_root="offsim/papers") -> Path:
    """Write offsim/papers/<slug>/ with the draft files; returns the folder."""
    pdf = Path(pdf)
    ex = extract(pdf)
    ev = evidence(ex)
    tags = classify(ex)
    slug = slugify(ex, pdf.stem)
    d = Path(out_root) / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "extract.json").write_text(json.dumps({**ex, "tags": tags}, ensure_ascii=False, indent=1))
    with (d / "evidence.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLS, extrasaction="ignore")
        w.writeheader()
        for e in ev:
            w.writerow(e)
    hdr = ("# DRAFT, not a scenario. Values are null on purpose: candidates are evidence with page refs.\n"
           "# paper-extract confirms each one (src: page/table) or marks assumption: true, then writes scenario.yaml.\n")
    _dump(d / "scenario.draft.yaml", scenario_draft(ex, ev, tags, slug), hdr)
    tt = wants_timetable(ex, tags)
    if tt:
        _dump(d / "timetable.draft.yaml", timetable_draft(ex, ev, tags),
              hdr.replace("scenario.yaml", "timetable.yaml"))
    (d / "notes.md").write_text(notes(ex, ev, tags, tt))
    return d


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Paper PDF -> draft with page-referenced evidence (candidates, not values).")
    ap.add_argument("pdf")
    ap.add_argument("--out", default="offsim/papers")
    a = ap.parse_args(argv)
    if not Path(a.pdf).is_file():
        print(f"error: no such PDF: {a.pdf}", file=sys.stderr)
        return 2
    try:
        d = draft(a.pdf, a.out)
    except Exception as e:                      # unreadable/encrypted PDF: say so, no traceback
        print(f"error: could not read {a.pdf}: {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    ex = json.loads((d / "extract.json").read_text())
    with (d / "evidence.csv").open(encoding="utf-8") as f:
        n = sum(1 for _ in csv.DictReader(f))
    print(f"draft: {d}")
    print(f"pages: {ex['source']['pages']}  evidence: {n}  tables: {sum(len(p['tables']) for p in ex['pages'])}  "
          f"classes: {','.join(ex['tags']['classes']) or 'none'}")
    for w in ex["warnings"]:
        print("warning:", w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
