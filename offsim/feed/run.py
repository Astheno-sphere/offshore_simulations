"""CLI: run every query against every source, append only papers not already in the feed file.

    python -m offsim.feed.run --queries papers/queries.yaml --out papers/feed.jsonl --since 2015-01-01
    python -m offsim.feed.run ... --sources openalex,arxiv

queries.yaml:  {queries: [free text | "author:<surname>", ...], sources: optional list}
Existing records in --out are read first, so reruns add only new papers (dedupe by id and normalised title).
A source that fails for one query is reported on stderr and skipped; the other sources still run.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import yaml

from offsim.feed import SOURCES
from offsim.feed.sources import dedupe, keys


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


def collect(queries, since, sources=None, fetch=None, pause=0.0, errors=None) -> list[dict]:
    """Run each (query, source) pair and return the deduplicated new records (no file I/O)."""
    sources = sources or SOURCES
    found = []
    for q in queries:
        for name, fn in sources.items():
            try:
                found.extend(fn(q, since, fetch=fetch))
            except Exception as exc:  # one failing source must not stop the feed
                msg = f"{name} {q!r}: {type(exc).__name__}: {exc}"
                if errors is not None:
                    errors.append(msg)
                print("feed warning:", msg, file=sys.stderr)
            if pause and fetch is None:
                time.sleep(pause)
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
    new = dedupe(collect(queries, args.since, chosen, pause=args.pause), seen=seen)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a") as f:
        for rec in new:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"feed: {len(queries)} queries, {len(chosen)} sources; {before} existing, {len(new)} new -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
