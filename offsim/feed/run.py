"""CLI: run every query against every source, append only papers not already in the feed file.

    python -m offsim.feed.run --queries papers/queries.yaml --out papers/feed.jsonl --since 2015-01-01
    python -m offsim.feed.run ... --sources openalex,arxiv

queries.yaml:  {queries: [free text | "author:<surname>", ...], sources: optional list}
Existing records in --out are read first, so reruns add only new papers (dedupe by id and normalised title).
A source that fails for one query is reported on stderr and skipped; the other sources still run.
A source that fails every query with HTTP 429 is reported once as degraded (not once per query) and
recorded in a status file next to --out (<out>.status.json, e.g. papers/feed.status.json) with per-source
record/error counts, so a later run can see the degradation without re-reading the warnings.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

from offsim.feed import SOURCES
from offsim.feed.sources import dedupe, is_rate_limited, keys, retry_after_s


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def source_status(st: dict) -> str:
    """ok / partial / empty / error / degraded from one source's collected stats."""
    if st["records"] == 0 and st["errors"] > 0 and st["errors_429"] == st["errors"]:
        return "degraded"          # every call failed with 429, nothing returned
    if st["records"] == 0 and st["errors"] > 0:
        return "error"
    if st["records"] > 0 and st["errors"] > 0:
        return "partial"
    if st["records"] == 0:
        return "empty"
    return "ok"


def load_queries(path) -> tuple[list[str], list[str] | None]:
    """Return (queries, sources-or-None). Raises ValueError when the file has no queries."""
    d = yaml.safe_load(Path(path).read_text()) or {}
    queries = [str(q).strip() for q in d.get("queries", []) if str(q).strip()]
    if not queries:
        raise ValueError(f"{path}: no queries")
    return queries, d.get("sources")


def load_seen(out) -> tuple[set[str], int]:
    """Keys of records already in the feed file, and how many there are."""
    seen, n = set(), 0
    p = Path(out)
    if p.exists():
        for line in p.read_text().splitlines():
            if line.strip():
                seen |= keys(json.loads(line))
                n += 1
    return seen, n


def collect(queries, since, sources=None, fetch=None, pause=0.0, errors=None, status=None) -> list[dict]:
    """Run each (query, source) pair and return the deduplicated new records (no file I/O).

    When `status` is given (a dict), it is filled with per-source stats
    {name: {records, errors, errors_429, last_error, retry_after_s, status}}.
    HTTP 429s are not warned per query: a source that returns nothing and fails
    every call with 429 gets one 'feed degraded' line at the end; a source that
    still returned records keeps its per-query 429 warnings.
    """
    sources = sources or SOURCES
    found = []
    stats = {name: {"records": 0, "errors": 0, "errors_429": 0, "last_error": None,
                    "retry_after_s": None} for name in sources}
    warn429: dict[str, list[str]] = {}
    for q in queries:
        for name, fn in sources.items():
            st = stats[name]
            try:
                recs = fn(q, since, fetch=fetch)
                st["records"] += len(recs)
                found.extend(recs)
            except Exception as exc:  # one failing source must not stop the feed
                st["errors"] += 1
                st["last_error"] = f"{type(exc).__name__}: {exc}"
                msg = f"{name} {q!r}: {type(exc).__name__}: {exc}"
                if is_rate_limited(exc):
                    st["errors_429"] += 1
                    ra = retry_after_s(exc)
                    if ra is not None:
                        st["retry_after_s"] = ra
                    warn429.setdefault(name, []).append(msg)
                else:
                    if errors is not None:
                        errors.append(msg)
                    print("feed warning:", msg, file=sys.stderr)
            if pause and fetch is None:
                time.sleep(pause)
    for name, st in stats.items():
        st["status"] = source_status(st)
        if st["status"] == "degraded":
            print(f"feed degraded: {name} returned 0 records, {st['errors_429']}x 429 after retries"
                  + (f" (Retry-After {st['retry_after_s']}s)" if st["retry_after_s"] is not None else "")
                  + "; see the status file", file=sys.stderr)
        else:
            for msg in warn429.get(name, []):
                if errors is not None:
                    errors.append(msg)
                print("feed warning:", msg, file=sys.stderr)
    if status is not None:
        status.update(stats)
    return dedupe(found, seen=set())


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--queries", default="papers/queries.yaml")
    ap.add_argument("--out", default="papers/feed.jsonl")
    ap.add_argument("--since", default="2015-01-01", help="publication-date floor, YYYY-MM-DD")
    ap.add_argument("--sources", default=None, help="comma list; default: all, or the queries file's list")
    ap.add_argument("--pause", type=float, default=1.0, help="seconds between live API calls (politeness)")
    args = ap.parse_args(argv)

    queries, file_sources = load_queries(args.queries)
    names = args.sources.split(",") if args.sources else file_sources
    chosen = {n: SOURCES[n] for n in names} if names else SOURCES
    seen, before = load_seen(args.out)
    stats: dict = {}
    new = dedupe(collect(queries, args.since, chosen, pause=args.pause, status=stats), seen=seen)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a") as f:
        for rec in new:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    status_path = out.with_suffix(".status.json")
    status_path.write_text(json.dumps({
        "generated_utc": _now(), "since": args.since, "queries": len(queries),
        "sources": stats}, ensure_ascii=False, indent=2) + "\n")
    print(f"feed: {len(queries)} queries, {len(chosen)} sources; {before} existing, {len(new)} new -> {out}; status -> {status_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
