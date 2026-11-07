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
Local run (needs network; the Claude workspace has none for the APIs):
```bash
python -m offsim.feed.run --queries papers/queries.yaml --out papers/feed.jsonl --since 2015-01-01
python -m offsim.research.tags --feed papers/feed.jsonl --out papers/tags.jsonl
python -m offsim.research.gaps --tags papers/tags.jsonl --out papers/gaps.yaml
```
Inside Claude without network, read the branch with `gh` as above. WebFetch only works on URLs already in the
conversation, so do not use it to call the APIs.

## 2. Review the tags
Open `papers/tags.jsonl` and spot-check the papers behind any gap. Known weak spots of the rules:
- "Norway" can fire on a non-geographic mention (funder or affiliation). Funder phrases are excluded; others are not.
- "robust" and "stochastic" alone give uncertainty `multiple`, so a deterministic paper can be missed as a gap.
- Author queries (`author:<surname>`) return common-name noise. Keep only papers whose author list matches.
Correct a wrong tag by hand in the review notes, not in the rules, unless the same error repeats.

## 3. Confirm gaps
For each `status: open` gap in `papers/gaps.yaml`:
1. Read the supporting papers (`papers` list) and confirm the kind is true: a Norwegian case really is absent,
   the uncertainty really is absent, the code or data really is not linked.
2. Check the suggested `engine` against `docs/ENGINES.md` "Choosing". Overrule it only with a reason written down.
3. Mark the gap `confirmed` or `dropped` with a one-line reason. Do not edit the generated fields.

## 4. Propose an experiment
Write `experiment.yaml` next to the paper's scenario (`offsim/papers/<id>/experiment.yaml`). Format: the docstring
of `offsim/research/experiment.py`. Required: `gap_id`, `base`, `hypothesis`, `variants` (each with `solver` and
`engine`), `ensemble`, `kpis`, `decision`.
- The base scenario must be `reproduced` or `re-run under assumptions` first (`paper-extract`, then `offsim run`).
- Write the decision rule (`kpi`, `compare`, `better`, `min_effect`) before any run. Never change it after a result.
- Every parameter a variant changes gets a source page or `assumption: true`.
- Each variant names its `engine`; pick one from the engine table, not the one that looks best.

## Rules
- Tags route work only. A tag, a rule hit or an LLM tag is never a reported value.
- Values come from `paper-extract` with a page or table source, or they are marked `assumption: true`.
- A gap is a lead. It becomes work only after the confirm step and an experiment file.
- Do not commit or push unless asked. Papers and gaps live on `papers/auto`, changed by the workflow.
- Nothing is narrated from an experiment until its ensemble passes every contract check (`sim-corrector`).
