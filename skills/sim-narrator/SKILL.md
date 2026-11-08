---
name: sim-narrator
description: Writes the words around a validated simulation result - on-screen captions and narration rules, the status line, the LinkedIn post and the README entry - strictly from report.json measured values and report refs (KPIs, gates, ensemble quantiles, experiment decision), citing the paper and data sources. Use when a validated run, experiment or video needs a caption, post, summary or explanation for planners, recruiters or the OR community.
---

# sim-narrator

Input: `offsim/papers/<id>/report.json`, `scenario.yaml`, and for an experiment its `experiment_report.json`.
Never the paper's abstract alone.

## Status words (computed by the runner: quote them, never rewrite them)
- Run: **reproduced**, **re-run under assumptions**, **did not reproduce**.
- Experiment (`decision.status`): **supported**, **not supported**, **inconclusive**. Inconclusive is a finding: say so.
- Any run on synthetic years carries **(synthetic weather, not reportable)**. Never narrate it as a finding.
- A blocked experiment (`ensemble.ok` False) has no decision. Say it is blocked and give no result.

## Narration rules (`narration: [{when: "...", text: "..."}]`)
- `when` is a condition on measured values. `offsim.motion.narrate` chooses the text whose `when` holds.
- `text` may contain only numbers that come from `report:` refs. Write one sentence per possible outcome, so no
  sentence can be contradicted by the measurements.
- Two passes: the film measures first, then chooses the text, then renders. Every sentence on screen must survive that check.

## Post (about 120-180 words)
1. The operational question in one line, in the reader's words ("How many helicopter flights does a crew change on 20 platforms need?").
2. The method as a procedure, one sentence, crediting the authors.
3. The result: our measured number next to the paper's, with its status word.
4. One caveat that matters: synthetic demand, missing weather, assumed speeds, or the ensemble spread.
5. Links: DOI, repo path, data credits (Sodir NLOD, Kartverket, Kystverket, OSM ODbL, "Source: Entur AS" where used, AIS as licensed).

## Rules
- Every number traces to a report ref. Round as the corrector printed it.
- Every single number carries its uncertainty: the P10-P90 band or 95% CI from `report["ensemble"]`, or the words "single run, no ensemble".
- No superlatives, no engagement bait. House voice: plain, measured, specific.
- Name people and companies only as authors or data owners, never as endorsing the result.
- Do not caption or post a result that failed a gate.
