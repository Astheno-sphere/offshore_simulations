"""Paper sources for the L6 research feed. Stdlib only (urllib, json, xml.etree).

Each source function takes (query, since, fetch=None) and returns a list of paper records:

    {id, title, year, authors, venue, abstract, oa_url, source, fetched_utc}

- id: canonical DOI (lower-case, no URL prefix); arXiv records without a DOI use "arXiv:<id>";
  records with neither use "<source>:<native id>".
- query: free text (all words must match), or "author:<surname>" for an author search where the API
  supports it. Author search is not supported by NVA beyond plain text (the surname is sent as the query).
- since: "YYYY-MM-DD" publication-date floor. Applied in the API request where the API supports it, and
  again client-side for every source.
- fetch: optional callable url -> bytes. Tests pass a fake; production uses urllib (see _get).
- OFFSIM_MAILTO (env, optional): sent as `mailto` to OpenAlex and Crossref (polite pools).

Field-name status: OpenAlex, Crossref and arXiv are written from their public API documentation shapes and are
exercised only by recorded fixtures in tests/fixtures/feed/ (the workspace cannot reach the APIs). NVA: fields
unverified live; parsed defensively, missing fields become empty values rather than errors.
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

USER_AGENT = "offsim-feed/0.1 (offshore research feed; contact via OFFSIM_MAILTO)"
ARXIV_NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


def _get(url: str) -> bytes:
    """Default fetcher: one GET with a user agent and a 60 s timeout. Raises on HTTP errors."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _mailto(params: dict) -> dict:
    mail = os.environ.get("OFFSIM_MAILTO")
    if mail:
        params["mailto"] = mail
    return params


def _author(query: str) -> str | None:
    """'author:Fagerholt' -> 'Fagerholt'; plain text -> None."""
    q = query.strip()
    return q.split(":", 1)[1].strip() if q.lower().startswith("author:") else None


def _doi(raw) -> str | None:
    """'https://doi.org/10.1016/X' -> '10.1016/x'; anything that is not a DOI -> None."""
    if not raw:
        return None
    d = re.sub(r"^(https?://)?(dx\.)?doi\.org/", "", str(raw).strip(), flags=re.I).lower()
    return d if d.startswith("10.") else None


def _canon(doi: str | None, fallback: str) -> str:
    """Canonical id. arXiv's own DOIs (10.48550/arXiv.<id>) become 'arXiv:<id>' so they dedupe with arXiv."""
    if doi:
        m = re.match(r"10\.48550/arxiv\.(.+)$", doi)
        return "arXiv:" + m.group(1) if m else doi
    return fallback


def _record(id_, title, year, authors, venue, abstract, oa_url, source) -> dict:
    return {
        "id": id_, "title": " ".join((title or "").split()), "year": year,
        "authors": [a for a in (authors or []) if a], "venue": venue or None,
        "abstract": " ".join((abstract or "").split()), "oa_url": oa_url or None,
        "source": source, "fetched_utc": _now(),
    }


def _year(v) -> int | None:
    try:
        return int(str(v)[:4])
    except (TypeError, ValueError):
        return None


def _after(year: int | None, since: str | None) -> bool:
    """Client-side year floor. Unknown years are kept (the API filter already applied)."""
    return since is None or year is None or year >= int(since[:4])


def _abstract_from_inverted(idx: dict | None) -> str:
    """OpenAlex stores abstracts as {word: [positions]}. Rebuild the running text."""
    if not idx:
        return ""
    words = {}
    for word, positions in idx.items():
        for p in positions:
            words[p] = word
    return " ".join(words[i] for i in sorted(words))


def openalex(query: str, since: str, per_page: int = 50, fetch=None) -> list[dict]:
    """OpenAlex works search (api.openalex.org/works).

    Filter: from_publication_date:<since> plus title_and_abstract.search:<query>, or
    authorships.author.display_name.search:<surname> for 'author:' queries.
    Abstract: abstract_inverted_index is rebuilt into text. Open-access link: open_access.oa_url, then
    best_oa_location.landing_page_url.
    """
    fetch = fetch or _get
    name = _author(query)
    term = (f"authorships.author.display_name.search:{name}" if name
            else f"title_and_abstract.search:{query}")
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode(_mailto({
        "filter": f"from_publication_date:{since},{term}", "per-page": per_page}))
    out = []
    for w in json.loads(fetch(url)).get("results", []):
        doi = _doi(w.get("doi"))
        oa = w.get("open_access") or {}
        best = w.get("best_oa_location") or {}
        year = w.get("publication_year")
        if not _after(year, since) or not w.get("title"):
            continue
        out.append(_record(
            _canon(doi, "openalex:" + str(w.get("id", "")).rsplit("/", 1)[-1]),
            w["title"], year,
            [(a.get("author") or {}).get("display_name") for a in w.get("authorships", [])],
            ((w.get("primary_location") or {}).get("source") or {}).get("display_name"),
            _abstract_from_inverted(w.get("abstract_inverted_index")),
            oa.get("oa_url") or best.get("landing_page_url"), "openalex"))
    return out


def crossref(query: str, since: str, rows: int = 50, fetch=None) -> list[dict]:
    """Crossref works (api.crossref.org/works).

    query.bibliographic=<query> or query.author=<surname>; filter from-pub-date:<since>.
    JATS markup in abstracts is stripped. Crossref does not state open access, so oa_url is None here.
    """
    fetch = fetch or _get
    name = _author(query)
    params = {"filter": f"from-pub-date:{since}", "rows": rows}
    params["query.author" if name else "query.bibliographic"] = name or query
    url = "https://api.crossref.org/works?" + urllib.parse.urlencode(_mailto(params))
    out = []
    for it in json.loads(fetch(url)).get("message", {}).get("items", []):
        title = (it.get("title") or [""])[0]
        parts = ((it.get("issued") or {}).get("date-parts") or [[None]])[0]
        year = _year(parts[0]) if parts else None
        if not title or not _after(year, since):
            continue
        doi = _doi(it.get("DOI"))
        out.append(_record(
            _canon(doi, "crossref:" + str(it.get("URL", title[:40]))),
            title, year,
            [" ".join(filter(None, [a.get("given"), a.get("family")])) for a in it.get("author", [])],
            (it.get("container-title") or [None])[0],
            re.sub(r"<[^>]+>", " ", it.get("abstract") or ""), None, "crossref"))
    return out


def arxiv(query: str, since: str, max_results: int = 50, fetch=None) -> list[dict]:
    """arXiv API (export.arxiv.org/api/query), Atom XML parsed with xml.etree.

    Text query: every word becomes all:<word> joined by AND. Author query: au:<surname>.
    Entry id 'http://arxiv.org/abs/2301.01234v1' gives 'arXiv:2301.01234' (version removed). A journal DOI
    from arxiv:doi overrides it as the canonical id. Entries whose id is not an abs URL (API errors) are skipped.
    """
    fetch = fetch or _get
    name = _author(query)
    sq = f"au:{name}" if name else " AND ".join(f"all:{w}" for w in query.split())
    url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode({
        "search_query": sq, "start": 0, "max_results": max_results,
        "sortBy": "submittedDate", "sortOrder": "descending"})
    out = []
    for e in ET.fromstring(fetch(url)).findall("a:entry", ARXIV_NS):
        raw_id = (e.findtext("a:id", "", ARXIV_NS) or "").strip()
        if "/abs/" not in raw_id:
            continue
        aid = re.sub(r"v\d+$", "", raw_id.rsplit("/abs/", 1)[1])
        published = (e.findtext("a:published", "", ARXIV_NS) or "")[:10]
        year = _year(published)
        if not _after(year, since) or (published and published < since):
            continue
        pdf = next((l.get("href") for l in e.findall("a:link", ARXIV_NS) if l.get("title") == "pdf"), None)
        out.append(_record(
            _canon(_doi(e.findtext("arxiv:doi", None, ARXIV_NS)), f"arXiv:{aid}"),
            e.findtext("a:title", "", ARXIV_NS), year,
            [a.findtext("a:name", None, ARXIV_NS) for a in e.findall("a:author", ARXIV_NS)],
            e.findtext("arxiv:journal_ref", None, ARXIV_NS) or "arXiv",
            e.findtext("a:summary", "", ARXIV_NS), pdf or f"https://arxiv.org/abs/{aid}", "arxiv"))
    return out


def nva(query: str, since: str | None = None, results: int = 50, fetch=None) -> list[dict]:
    """Norwegian research archive search (api.nva.unit.no/search/resources?query=...).

    FIELDS UNVERIFIED LIVE. Assumed shape: {"hits": [{"identifier", "entityDescription": {"mainTitle",
    "abstract", "publicationDate": {"year"}, "contributors": [{"identity": {"name"}}], "reference":
    {"doi", "publicationContext": {"name"}}}}]}. Every lookup is defensive: a missing field gives an
    empty value and a hit without a title is skipped. Plain text only (no author: prefix); the surname is
    sent as the query. oa_url is None.
    """
    fetch = fetch or _get
    url = "https://api.nva.unit.no/search/resources?" + urllib.parse.urlencode(
        {"query": query, "results": results})
    data = json.loads(fetch(url))
    out = []
    for h in data.get("hits") or data.get("results") or []:
        ed = h.get("entityDescription") or {}
        ref = ed.get("reference") or {}
        ctx = ref.get("publicationContext") or {}
        title = ed.get("mainTitle") or ed.get("title") or ""
        year = _year((ed.get("publicationDate") or {}).get("year"))
        if not title or not _after(year, since):
            continue
        doi = _doi(ref.get("doi"))
        out.append(_record(
            _canon(doi, "nva:" + str(h.get("identifier") or h.get("id") or title[:40])),
            title, year,
            [((c.get("identity") or {}).get("name")) for c in ed.get("contributors", [])],
            ctx.get("name") or ctx.get("title"), ed.get("abstract"), None, "nva"))
    return out


def norm_title(title: str) -> str:
    """Lower-case alphanumerics only, single spaces. Used for title-level dedupe."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).split())


def keys(rec: dict) -> set[str]:
    """Dedupe keys: the canonical id, and the normalised title if it is long enough to be distinctive."""
    k = {"id:" + rec["id"].lower()}
    t = norm_title(rec.get("title", ""))
    if len(t) >= 20:
        k.add("title:" + t)
    return k


def dedupe(records: list[dict], seen: set[str] | None = None) -> list[dict]:
    """Keep the first record for each DOI/arXiv id or normalised title. `seen` (mutated) carries keys across
    calls, so run.py can skip papers already in papers/feed.jsonl."""
    seen = set() if seen is None else seen
    out = []
    for r in records:
        k = keys(r)
        if k & seen:
            continue
        seen |= k
        out.append(r)
    return out
