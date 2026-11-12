from: Claude (integrator), 2026-11-12
goal: Close the two quality holes the machine can now name itself.

a) CAD QA (drafter work). `python -m offsim.assets.cad.qa <name>` today: psv, s92, bus, train, person, tree,
   building pass; aw189 FAILS (rotor 20 %, fuselage 30 %, width 366 % off its declared dims); platform_jacket
   returns null (no measurable dims; they need `measure:` entries in registry.yaml or in the model). Fix the solids
   to the cited dimensions, never the dimensions to the solid. Source every principal dim (Leonardo AW189 data
   sheet; for the jacket a published drawing, or mark `assumption: true` with a reason). Registry status must come
   from a measured QA run, never typed by hand.

b) Visual gate soft findings on the section frame (offsim/cinema/visual_gate.py, docs/STYLE_REFERENCE.md rule 17):
   8 text sizes where the rule allows 3 plus the methods line, and two labels over the streak field at about 2.9:1
   ("SECTION, 2D AIRFLOW" and the panel label). Reduce the type scale and raise those labels until `story.check`
   reports no warnings for the demo section shot with `visual: {strict: true}`. Do not move a threshold; if you
   believe one is wrong, bring a measured reference frame and say so.

rules: branch agent/nordlys/N3-assets-visual; your own subagents welcome; full suite green before each commit;
  regenerate tests/golden/ only for an intended renderer change, with a `why:` line in the commit.
report: coordination/reports/N3.md - QA table for all nine assets before and after, sources per dim, gate verdict
  before and after, and anything you could not fix, with the reason.
