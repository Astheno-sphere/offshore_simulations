---
template: thought
narration_include: [_common]
requires:
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
  - derived.packages_line
  - provenance.solver
  - provenance.engine
  - provenance.graph
  - provenance.scenario_sha256
  - kpis.distance_km
  - derived.makespan_h
  - status
narration:
  stance:
    - when: derived.status_key == "reproduced"
      text: "The run reproduced the reported figure, which is the weakest claim a simulation can make and still worth making: the model and the paper agree on the one number the paper chose to publish."
    - when: derived.status_key == "re-run under assumptions"
      text: "The run agrees with the reported figure, but only under assumptions we had to supply. The agreement is real; its reach is limited by every assumption listed below."
    - when: derived.status_key == "did not reproduce"
      text: "The run did not reproduce the reported figure. That is not a failure of the exercise. A gap between a paper and a faithful re-run is exactly where a method note, a missing input or an error is hiding."
    - when: derived.status_key == "not comparable"
      text: "The paper gives no figure this run can be held against, so there is nothing to reproduce. What remains is the run itself: a method executed end to end under gates, with its inputs and limits stated."
    - text: "The status word is {status}. We quote it as the pipeline printed it and do not soften it."
  spread:
    - when: derived.has_ensemble > 0
      text: "The spread is the result. Under {derived.head_variant}, the median {derived.head_label} is {derived.head_p50:.1f} {derived.head_unit}. The lower decile is {derived.head_p10:.1f} and the upper decile is {derived.head_p90:.1f}. A planner who plans to the median meets the upper decile often enough that the width of that band matters more than the centre."
    - text: "There is no spread here. One run gives one number, {kpis.distance_km:.1f} km sailed over a fleet makespan of {derived.makespan_h:.1f} hours, and a single number cannot tell a reader how far to trust itself. We say so rather than dress it up."
  limits:
    - when: derived.has_ensemble > 0
      text: "What the ensemble does not cover: anything outside the weather years and seeds it drew from, and anything the scenario fixed by assumption. Its weather sources are {derived.weather_sources}."
    - text: "What this run does not cover: weather, because no ensemble was run, and any variation in demand, because the scenario fixes it. Both would change the answer, and neither is estimated here."
---
# {{ref:derived.paper_title}}

*Status: {{ref:status}}. Run on {{ref:derived.run_date}}, commit {{ref:derived.commit_short}}.*

## The question

{{narrate:hook}} A routing paper makes a claim about a system, and the useful test of that claim is whether someone else, with the stated inputs and an independent implementation, gets the same number. Most of the time nobody checks, because checking is slow and unrewarded. We built a pipeline that makes the check cheap, and this note reports what it did on this scenario.

## What was run

{{narrate:credit}} The method is executed by a solver, replayed by a simulation engine, and the replay is compared with the plan the solver produced. If those two disagree, the run stops, because a simulation that cannot reproduce its own plan has nothing to say about the world.

The run passed {{ref:derived.n_gates_pass}} of {{ref:derived.n_gates}} gates: {{ref:derived.gates_passed}}. Provenance is the first of them. Every value in the scenario carries either a source in the paper, with its page or table, or an explicit mark that it is an assumption. A value with neither stops the run before the solver starts.

## What the run shows

{{narrate:stance}} {{narrate:status_line}}

{{narrate:answer}}

{{narrate:spread}}

{{figures}}

## What it does not show

{{narrate:limits}} {{narrate:caveat}}

The point of writing this down is that a reader can see where the result stops. A claim without its edge is advertising. A claim with its edge can be built on, argued with or repeated by someone who is not us.

## The method argument

Simulation results usually reach readers through a sentence somebody wrote after looking at a chart. That sentence is where overclaiming enters. Our rule is that no sentence in the article, the film or the post is written by hand once the run exists. Each sentence is chosen by a rule over the measured values, and each number is read from the run's report. If the run did not measure a thing, the machine cannot say it. This article is built that way: it would have been refused had a gate failed, had the weather been synthetic, or had the report carried no paper to cite.

This costs something. The prose is plainer than a human would make it, and it cannot reach for the vivid claim the data did not earn. We think that is the right trade for a result someone might plan a fleet around.

## Assumptions

{{ref:derived.n_assumptions}} values in this run are assumptions rather than sourced inputs. They fall under these scenario sections: {{ref:derived.assumption_sections}}. In full:

{{list:assumptions}}

Each should be replaced by a sourced value before the result is read as more than a demonstration of method.

## Reproduce it

Scenario and code are in {{ref:derived.repo_path}}, at commit {{ref:derived.commit_short}}. The solver is {{ref:provenance.solver}}, the engine is {{ref:provenance.engine}}, and the graph is {{ref:provenance.graph}}. Packages: {{ref:derived.packages_line}}. The scenario is identified by the hash {{ref:provenance.scenario_sha256}}, so a changed input is visible as a changed hash. {{narrate:doi}}
