---
template: linkedin
requires:
- paper.title
- paper.id
- derived.paper_title
- derived.n_gates
- derived.n_gates_pass
- derived.gates_passed
- derived.n_assumptions
- derived.assumption_sections
- derived.repo_path
- derived.commit_short
- derived.run_date
- provenance.solver
- provenance.engine
- provenance.graph
- derived.packages_line
- status
narration_include:
- _common
---
{{narrate:hook}}

**What this is.** {{narrate:credit}} {{narrate:status_line}}

**What we tested.** {{ref:derived.n_gates_pass}} of {{ref:derived.n_gates}} gates passed before anything was written: {{ref:derived.gates_passed}}. Every figure below is read from the run's report. None is typed by hand, and a sentence appears only if the measurements allow it.

**The measured answer.** {{narrate:answer}} {{narrate:caveat}}

{{figures}}

> **Method box.** Solver {{ref:provenance.solver}}, engine {{ref:provenance.engine}}, graph {{ref:provenance.graph}}. Commit {{ref:derived.commit_short}}, run on {{ref:derived.run_date}}. Packages: {{ref:derived.packages_line}}.

**Assumptions.** {{ref:derived.n_assumptions}} values are assumed, not sourced, across: {{ref:derived.assumption_sections}}.

{{list:assumptions}}

**Sources.** {{narrate:doi}} Code and scenario: {{ref:derived.repo_path}}.
