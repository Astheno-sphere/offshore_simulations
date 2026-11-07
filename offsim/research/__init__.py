"""L6 research: papers in, testable gaps out, experiments that the engine layer can run.

    feed (offsim.feed)  ->  papers/feed.jsonl         one record per paper (OpenAlex/Crossref/arXiv/NVA/Brage)
    tag                 ->  papers/tags.jsonl         problem class, region, uncertainty, code?, data?, KPIs
    gaps                ->  papers/gaps.yaml          cells of the gap table nobody has filled
    experiment          ->  offsim/papers/<id>/experiment.yaml   baseline vs variant(s), ensemble, hypotheses

Definitions (docs/ARCHITECTURE.md, "Research loop"):
- Paper record: {id (doi or arXiv id), title, year, authors, venue, abstract, oa_url, source, fetched_utc}.
- Tag: {paper_id, classes: [CVRP|VRPTW|PDP|PSV-PDP|FSMP|HRP|WIND-OM|WIND-INST|FERRY-SCHED|CREW-ROUTE|...],
        mode: [psv|ferry|heli|ctv|sov|wtiv|truck|worker], region: [NCS|North Sea|Oslofjord|...|none],
        uncertainty: none|weather|demand|failure|multiple, method: exact|heuristic|simulation|hybrid,
        code: url|null, data: url|null, kpis: [...], tagged_by: rule|llm|human, confidence: 0..1}.
  Tags from an LLM carry confidence < 1 and are never used for a reported value: values come from
  the paper via paper-extract with page/table sources.
- Gap: a cell (class x mode x region x uncertainty) with supporting papers, plus why it matters and
  which engine can test it. Kinds: "no-norway" (method exists, never run on Norwegian geography),
  "no-uncertainty" (deterministic only), "no-code" (not reproducible), "no-validation" (never checked
  against AIS), "contradiction" (two papers report incompatible KPIs for comparable settings).
- Experiment: {gap_id, base_paper, hypothesis, variants: {name: {solver, engine, overrides}},
  ensemble: {weather: NORA3 years, seeds}, kpis, decision_rule}. Runs through `python -m offsim run`;
  the status word for an experiment is "supported" | "not supported" | "inconclusive" (CI spans 0).

Modules (specs; see each file): offsim.research.tags, offsim.research.gaps, offsim.research.experiment.
"""
