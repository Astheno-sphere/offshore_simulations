"""Declared shape of an ensemble tree (docs/DATA_TREES.md, "Data trees in this machine").

An ensemble is a data tree with path {variant; year; seed}. A *branch* is a path without its last level
({variant; year}); its *items* are the seeds. The expected tree is the cross product of the declared keys; the observed
tree is what the valid runs actually hold. `TreeShape.diff` names exactly which paths are missing, extra, duplicated or
short, so a silent shape error (an empty year, a variant on other seeds) becomes a loud, specific one.

Pure: no I/O, no engine. Keys are compared as python values (None stays None, numpy scalars are unwrapped).
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from itertools import product
from typing import Any, Iterable, Sequence

LEVELS = ("variant", "year", "seed")


class TreeShapeError(ValueError):
    """A result tree does not have the shape that was declared for it."""


def _key(x: Any):
    """Python value for a key: unwrap numpy scalars, NaN -> None (a missing weather-year label)."""
    if hasattr(x, "item"):
        x = x.item()
    if isinstance(x, float) and x != x:
        return None
    return x


def _uniq(xs: Iterable) -> tuple:
    return tuple(dict.fromkeys(_key(x) for x in xs))


def fmt_path(p: Sequence) -> str:
    return "{" + "; ".join("-" if x is None else str(x) for x in p) + "}"


@dataclass(frozen=True)
class ShapeDiff:
    """expected - observed, by path. `short` maps a branch to (items observed, items expected) when it has fewer."""
    missing: tuple
    extra: tuple
    duplicate: tuple
    short: tuple          # ((branch, have, want), ...)
    expected_paths: int
    observed_paths: int

    @property
    def ok(self) -> bool:
        return not (self.missing or self.extra or self.duplicate)

    def summary(self, limit: int = 5) -> dict:
        """Compact, JSON-safe: counts plus up to `limit` example paths per kind."""
        return {"ok": self.ok, "expected_paths": self.expected_paths, "observed_paths": self.observed_paths,
                "n_missing": len(self.missing), "n_extra": len(self.extra), "n_duplicate": len(self.duplicate),
                "n_short_branches": len(self.short),
                "missing": [fmt_path(p) for p in self.missing[:limit]],
                "extra": [fmt_path(p) for p in self.extra[:limit]],
                "short": [f"{fmt_path(b)} {h}/{w}" for b, h, w in self.short[:limit]]}


@dataclass(frozen=True)
class Observed:
    levels: tuple
    paths: tuple               # distinct paths seen, first-seen order
    counts: dict               # path -> number of rows (1 for a well-formed tree)

    @property
    def branches(self) -> dict:
        """branch (path minus last level) -> number of distinct items under it."""
        out: dict = {}
        for p in self.paths:
            out[p[:-1]] = out.get(p[:-1], 0) + 1
        return out

    @property
    def n_branches(self) -> int:
        return len(self.branches)


@dataclass(frozen=True)
class TreeShape:
    """Ordered level names plus the expected keys of each level."""
    levels: tuple
    keys: tuple            # one tuple of expected keys per level

    @classmethod
    def expected(cls, variants: Iterable, years: Iterable, seeds: Iterable, levels: Sequence[str] = LEVELS) -> "TreeShape":
        return cls(tuple(levels), (_uniq(variants), _uniq(years), _uniq(seeds)))

    def paths(self) -> list:
        return [tuple(p) for p in product(*self.keys)]

    @property
    def n_paths(self) -> int:
        n = 1
        for k in self.keys:
            n *= len(k)
        return n

    @property
    def n_branches(self) -> int:
        return self.n_paths // max(1, len(self.keys[-1]))

    @property
    def items_per_branch(self) -> int:
        return len(self.keys[-1])

    def describe(self) -> dict:
        return {"levels": list(self.levels), "sizes": {n: len(k) for n, k in zip(self.levels, self.keys)},
                "branches": self.n_branches, "items_per_branch": self.items_per_branch, "paths": self.n_paths}

    def observed(self, runs, valid_only: bool = True) -> Observed:
        """Read the tree out of a runs table (one row per path). `valid_only` drops rows with valid False."""
        df = runs
        if valid_only and len(df) and "valid" in df.columns:
            df = df[df["valid"].astype(bool)]
        cols = [df[n].tolist() if len(df) else [] for n in self.levels]
        seen = Counter(tuple(_key(x) for x in row) for row in zip(*cols))
        return Observed(self.levels, tuple(seen), dict(seen))

    def diff(self, obs: Observed) -> ShapeDiff:
        want = self.paths()
        want_set = set(want)
        have = set(obs.paths)
        missing = tuple(p for p in want if p not in have)
        extra = tuple(p for p in obs.paths if p not in want_set)
        duplicate = tuple(p for p, n in obs.counts.items() if n > 1)
        got = Counter(p[:-1] for p in have if p in want_set)
        full = self.items_per_branch
        short = tuple((b, got[b], full) for b in dict.fromkeys(p[:-1] for p in want) if got[b] < full)
        return ShapeDiff(missing, extra, duplicate, short, len(want), len(have))
