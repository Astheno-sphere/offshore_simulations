"""Human review of gaps (L6): verdicts in papers/review.yaml, a ranked terminal list, and an experiment skeleton.

    python -m offsim gap list [--top N] [--all]                             # ranked table from papers/gaps.yaml
    python -m offsim gap review <gap_id> --verdict take|drop|later --note "..."   # append a verdict
    python -m offsim gap draft <gap_id>                                     # offsim/papers/<base>/experiment.yaml

papers/review.yaml is the human's file. `gap review` only appends to it; gaps.py reads it and never writes it.
Each entry keeps the paper ids the gap had when it was judged. On regeneration (apply_reviews):
- take / later: the status becomes the verdict; the gap stays as the human left it.
- drop: stays dropped while its papers are the same. When new papers join the cell, it reopens, and the gap says so.

`gap draft` never proposes a value: hypothesis, solver, ensemble, the decision rule and any number are null, and every
name it does fill in (engine, KPI names) is listed under `assumptions` with assumption: true.
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from offsim.research import experiment
from offsim.research.tags import KPI_RULES

VERDICTS = ("take", "drop", "later")
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GAPS = ROOT / "papers" / "gaps.yaml"
DEFAULT_REVIEW = ROOT / "papers" / "review.yaml"
REVIEW_HEADER = ("# Human verdicts on gaps (papers/gaps.yaml). Appended only by `offsim gap review`; gaps.py reads this\n"
                 "# file and never writes it. The last entry for a gap_id is its verdict.\n"
                 "reviews:\n")
DRAFT_HEADER = ("# Skeleton from `offsim gap draft`. Null values and the names listed under assumptions need a human.\n"
                "# The decision rule (kpi, compare, better, min_effect) and the hypothesis are yours: write them before any run.\n")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def paper_slug(paper_id: str) -> str:
    """Directory name for a paper: 'nva:0198...' or a DOI -> lowercase letters, digits and dashes."""
    return re.sub(r"[^a-z0-9]+", "-", paper_id.lower()).strip("-")


def _read_gaps(path) -> list[dict]:
    doc = yaml.safe_load(Path(path).read_text()) or {}
    return doc.get("gaps") or []


def _gap(gaps: list[dict], gap_id: str) -> dict:
    for g in gaps:
        if g["gap_id"] == gap_id:
            return g
    raise KeyError(f"no gap {gap_id!r} in the gap list (known: {len(gaps)} gaps)")


def load_reviews(path) -> dict[str, dict]:
    """{gap_id: latest review entry}. A missing or empty file means no verdicts."""
    p = Path(path)
    if not p.is_file():
        return {}
    doc = yaml.safe_load(p.read_text()) or {}
    return {r["gap_id"]: r for r in (doc.get("reviews") or [])}


def add_review(gap_id: str, verdict: str, note: str, *, gaps_path=DEFAULT_GAPS, review_path=DEFAULT_REVIEW,
               now: str | None = None) -> dict:
    """Append one verdict to papers/review.yaml. The file is appended to, never rewritten."""
    if verdict not in VERDICTS:
        raise ValueError(f"verdict must be one of {VERDICTS}, not {verdict!r}")
    if not note or not note.strip():
        raise ValueError("a note is required: say why")
    gap = _gap(_read_gaps(gaps_path), gap_id)
    entry = {"gap_id": gap_id, "verdict": verdict, "note": note.strip(), "at_utc": now or _now(),
             "papers": list(gap["papers"])}
    p = Path(review_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    text = p.read_text() if p.is_file() else ""
    doc = yaml.safe_load(text) if text.strip() else None
    if doc is None:
        text = REVIEW_HEADER
    elif not isinstance(doc, dict) or "reviews" not in doc:
        raise ValueError(f"{p} exists but has no 'reviews:' list; not touched")
    with p.open("a") as f:
        if doc is None:                     # new file, or comments only: open the list first
            f.write(REVIEW_HEADER)
        f.write(yaml.safe_dump([entry], sort_keys=False, allow_unicode=True, width=10_000))
    return entry


def apply_reviews(gaps: list[dict], reviews: dict[str, dict]) -> list[str]:
    """Apply human verdicts to a fresh gap list, in place. Returns one message per thing the reader should know."""
    msgs = []
    ids = {g["gap_id"] for g in gaps}
    for gid in sorted(set(reviews) - ids):
        msgs.append(f"{gid}: reviewed, but no such gap in this regeneration (kept in review.yaml)")
    for g in gaps:
        r = reviews.get(g["gap_id"])
        if not r:
            continue
        judged = set(r.get("papers") or [])
        new = sorted(set(g["papers"]) - judged)
        rec = {"verdict": r["verdict"], "at_utc": r.get("at_utc"), "note": r.get("note"),
               "papers_at_review": len(judged)}
        if r["verdict"] == "drop" and new:
            g["status"] = "open"
            rec["reopened"] = True
            rec["new_papers"] = new
            g["why"] += f" Reopened: {len(new)} papers joined this cell after the drop of {r.get('at_utc')}."
            msgs.append(f"{g['gap_id']}: reopened, {len(new)} new papers since the drop")
        elif r["verdict"] == "drop":
            g["status"] = "dropped"
            g["why"] += f" Dropped by human on {r.get('at_utc')} ({r.get('note')}); no new papers since."
            msgs.append(f"{g['gap_id']}: stays dropped, no new papers since")
        else:
            g["status"] = r["verdict"]
            if new:
                rec["new_papers"] = new
        g["review"] = rec
    return msgs


def format_table(gaps: list[dict], top: int = 20, show_all: bool = False) -> str:
    rows = [g for g in gaps if show_all or g.get("status") != "dropped"][:top]
    head = f"{'#':>3} {'score':>7} {'supp':>5} {'novel':>6} {'feas':>5} {'aud':>5}  {'status':<8} gap_id"
    lines = [head, "-" * len(head)]
    for i, g in enumerate(rows, 1):
        f = g["factors"]
        lines.append(f"{i:>3} {f['score']:>7.4f} {f['support']:>5.2f} {f['novelty']:>6.2f} {f['feasibility']:>5.2f} "
                     f"{f['audience']:>5.2f}  {g.get('status', 'open'):<8} {g['gap_id']}")
    if not rows:
        lines.append("(no gaps to show; use --all to include dropped ones)")
    return "\n".join(lines)


def draft(gap_id: str, *, gaps_path=DEFAULT_GAPS, root: Path = ROOT) -> Path:
    """Write offsim/papers/<base>/experiment.yaml as a skeleton. Refuses to overwrite; validates with experiment.load."""
    gap = _gap(_read_gaps(gaps_path), gap_id)
    base = gap.get("base_paper") or gap["papers"][0]
    kpis = list(gap.get("kpis") or KPI_RULES)
    engine = gap["engine"]
    out_dir = root / "offsim" / "papers" / paper_slug(base)
    out = out_dir / "experiment.yaml"
    if out.exists():
        raise FileExistsError(f"{out} exists; a human file is never overwritten")
    doc = {
        "gap_id": gap_id,
        "base": "scenario.yaml",
        "hypothesis": None,
        "variants": {"paper": {"solver": None, "engine": engine}},
        "ensemble": {"weather": {"dataset": None, "years": None, "season": None}, "seeds": None},
        "kpis": kpis,
        "decision": {"kpi": kpis[0], "compare": [], "better": None, "min_effect": None},
        "assumptions": [
            {"path": "variants.paper.engine", "value": engine, "assumption": True,
             "why": "suggested by the gap finder from docs/ENGINES.md Choosing; not confirmed"},
            {"path": "decision.kpi", "value": kpis[0], "assumption": True,
             "why": "first KPI name of the base paper's tags (or the engine vocabulary); the decision rule is the human's"},
            {"path": "kpis", "value": kpis, "assumption": True,
             "why": "KPI names the base paper's tags mention; not confirmed"},
        ],
        "base_paper": base,                     # the gap's factors stay in papers/gaps.yaml: no number here
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    out.write_text(DRAFT_HEADER + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True))
    try:
        experiment.load(out)
    except Exception:
        out.unlink()
        raise
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="offsim gap", description="Rank, review and draft research gaps.")
    sub = ap.add_subparsers(dest="sub", required=True)
    ls = sub.add_parser("list", help="ranked gap table")
    ls.add_argument("--top", type=int, default=20)
    ls.add_argument("--all", action="store_true", help="include dropped gaps")
    ls.add_argument("--gaps", default=str(DEFAULT_GAPS))
    rv = sub.add_parser("review", help="append a human verdict to papers/review.yaml")
    rv.add_argument("gap_id")
    rv.add_argument("--verdict", required=True, choices=VERDICTS)
    rv.add_argument("--note", required=True)
    rv.add_argument("--gaps", default=str(DEFAULT_GAPS))
    rv.add_argument("--review", default=str(DEFAULT_REVIEW))
    dr = sub.add_parser("draft", help="write offsim/papers/<base>/experiment.yaml skeleton")
    dr.add_argument("gap_id")
    dr.add_argument("--gaps", default=str(DEFAULT_GAPS))
    a = ap.parse_args(argv)
    try:
        if a.sub == "list":
            print(format_table(_read_gaps(a.gaps), a.top, a.all))
        elif a.sub == "review":
            e = add_review(a.gap_id, a.verdict, a.note, gaps_path=a.gaps, review_path=a.review)
            print(f"review recorded: {e['gap_id']} {e['verdict']} ({len(e['papers'])} papers judged) -> {a.review}")
        else:
            print(f"skeleton written: {draft(a.gap_id, gaps_path=a.gaps)}")
    except (KeyError, ValueError, FileExistsError) as exc:
        print(f"offsim gap {a.sub}: {exc.args[0] if exc.args else exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
