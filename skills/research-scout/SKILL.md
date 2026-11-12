---
name: research-scout
description: Run the L6 paper feed, review the rule tags, confirm gap candidates (no-norway, no-uncertainty, no-code), and propose an experiment.yaml that tests one gap under real weather. Use when asked "what is missing in the literature", "run the feed", "which gaps are open", or before writing any experiment. Tags route work only; values come from paper-extract with page sources.
---

# research-scout

## 1. Get the feed
Preferred: the weekly workflow (`.github/workflows/papers.yml`) or a manual run. It writes branch `papers/auto`
with `papers/feed.jsonl`, `papers/tags.jsonl` and `papers/gaps.yaml`, and one open pull request.
```bash
gh workflow run papers.yml -f since=2015-01-01
gh run list --workflow papers.yml --limit 3
gh api repos/{owner}/{repo}/contents/papers/gaps.yaml?ref=papers/auto --jq .content | base64 -d
```
Local run (needs network; the Claude workspace has none for the APIs). Same three steps as CLI commands
(`offsim feed`, `offsim tag`, `offsim gaps`; each wraps `offsim.feed.run`, `offsim.research.tags`,
`offsim.research.gaps`; flags as in `offsim <cmd> --help`):
```bash
offsim feed --queries papers/queries.yaml --out papers/feed.jsonl --since 2015-01-01
offsim tag --feed papers/feed.jsonl --out papers/tags.jsonl
offsim gaps --tags papers/tags.jsonl --out papers/gaps.yaml
```
Inside Claude without network, read the branch with `gh` as above. WebFetch only works on URLs already in the
conversation, so do not use it to call the APIs.

## 2. Review the tags
Open `papers/tags.jsonl` and spot-check the papers behind any gap. Known weak spots of the rules:
- "Norway" can fire on a non-geographic mention (funder or affiliation). Funder phrases are excluded; others are not.
- "robust" and "stochastic" alone give uncertainty `multiple`, so a deterministic paper can be missed as a gap.
- Author queries (`author:<surname>`) return common-name noise. Keep only papers whose author list matches.
Correct a wrong tag by hand in the review notes, not in the rules, unless the same error repeats.

## 3. Rank and confirm gaps
Gaps come ranked: `papers/gaps.yaml` holds, per gap, `factors` (support, novelty, feasibility, audience, score) and
`factor_notes` that say why each number is what it is. Argue with a factor by changing the note's evidence, not the number.
```bash
offsim gap list --top 10            # ranked table; dropped gaps hidden (--all shows them)
offsim gap review <gap_id> --verdict take|drop|later --note "why"   # appends to papers/review.yaml
```
- `no-code` is emitted only when every supporting record states its code or data is unavailable (`code_statement`
  in tags). Silence in an abstract is not evidence; see the `gaps` CLI output for the cells withheld.
- Feasibility 1 needs a solver and an engine that declare the class, and data for the target region. WIND-OM and
  WIND-INST have an engine but no solver, so they stop at 2/3 by this rule.
- The verdict is the human's. `papers/review.yaml` is never regenerated: a dropped gap stays dropped until new papers
  join its cell, and then the gap says so. Confirm the kind is true by reading the `papers` list before a `take`.
- Check the suggested `engine` against `docs/ENGINES.md` "Choosing"; overrule it only with a reason in the note.

## 4. Propose an experiment
`offsim gap draft <gap_id>` writes `offsim/papers/<base>/experiment.yaml` from the gap and its base paper (the supporting
paper with the highest tag confidence). It refuses to overwrite and writes no number: hypothesis, solver, ensemble,
`decision.better` and `decision.min_effect` are null, and every filled name (engine, KPI) is listed under `assumptions`.
Format: the docstring of `offsim/research/experiment.py`. `sim-engineer` runs it with `python -m offsim experiment <yaml>`.
- The base scenario must be `reproduced` or `re-run under assumptions` first: `offsim paper <pdf>` drafts it, `paper-extract` confirms it, `offsim run` gates it.
- Write the decision rule (`kpi`, `compare`, `better`, `min_effect`) before any run. Never change it after a result.
- Every parameter a variant changes gets a source page or `assumption: true`.
- Each variant names its `engine`; pick one from the engine table, not the one that looks best.

## Rules
- Tags route work only. A tag, a rule hit or an LLM tag is never a reported value.
- Values come from `paper-extract` with a page or table source, or they are marked `assumption: true`.
- A gap is a lead. It becomes work only after the confirm step and an experiment file.
- Do not commit or push unless asked. Papers and gaps live on `papers/auto`, changed by the workflow.
- `papers/review.yaml` is human-owned: `offsim gap review` appends to it; nothing rewrites it.
- Nothing is narrated from an experiment until its ensemble passes every contract check (`sim-corrector`).

## Transit and timetable papers (added 2026-11-08)
- Tag bus/ferry/rail papers with mode and region; they route to the `gtfs` engine (timetable replay) or `road` engine.
- When a paper gives a network (stops, run times, headways/departures, service days), propose a `timetable.yaml`
  (see `offsim/transit/from_paper.py`) for paper-extract to fill with page/table sources.
- Gap kinds to look for in Norway: schedule vs reality (Entur Vehicle Positions, gate 4c), timetable vs demand
  (SSB grids), ferry-bus connections (Entur GTFS joins), electrification/charging windows on real timetables.
- Data the user supplies (timetables, frequencies, GeoJSON) is welcome: record its source; it goes through the same
  provenance rules as paper values.
