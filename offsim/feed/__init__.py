"""L0/L6 paper feed: OpenAlex, Crossref, arXiv and NVA search, deduplicated into papers/feed.jsonl.

    python -m offsim.feed.run --queries papers/queries.yaml --out papers/feed.jsonl --since 2015-01-01

Record schema and sources: see offsim/feed/sources.py. Tagging: offsim/research/tags.py.
"""
from .sources import arxiv, crossref, dedupe, nva, openalex

SOURCES = {"openalex": openalex, "crossref": crossref, "arxiv": arxiv, "nva": nva}

__all__ = ["SOURCES", "arxiv", "crossref", "dedupe", "nva", "openalex"]
