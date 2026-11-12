---
template: readme_entry
requires:
  - paper.id
  - derived.paper_title
  - derived.repo_path
  - derived.n_gates
  - derived.n_gates_pass
  - derived.n_assumptions
  - derived.commit_short
  - derived.run_date
  - provenance.solver
  - provenance.engine
  - status
narration_include: [_common]
narration:
  result:
    - when: derived.has_comparison > 0
      text: "Paired comparison of {derived.cmp_a} against {derived.cmp_b} on {derived.cmp_label}: {derived.cmp_pct:.1f}% (interval {derived.cmp_lo_pct:.1f}% to {derived.cmp_hi_pct:.1f}%, {derived.cmp_n:.0f} pairs)."
    - when: derived.has_ensemble > 0
      text: "{derived.head_label}, median {derived.head_p50:.1f} {derived.head_unit} (lower decile {derived.head_p10:.1f}, upper decile {derived.head_p90:.1f}), {ensemble.n_valid:.0f} valid runs."
    - text: "Single run, no ensemble: {kpis.distance_km:.1f} km, makespan {derived.makespan_h:.1f} hours."
---
### {{ref:paper.id}}

{{ref:derived.paper_title}}

- Status: {{ref:status}}
- Gates: {{ref:derived.n_gates_pass}} of {{ref:derived.n_gates}} passed
- Result: {{narrate:result}}
- Method: {{ref:provenance.solver}} on the {{ref:provenance.engine}} engine; commit {{ref:derived.commit_short}}, run on {{ref:derived.run_date}}
- Assumptions: {{ref:derived.n_assumptions}} values, listed in the article
- Code: {{ref:derived.repo_path}}

{{list:assumptions}}
