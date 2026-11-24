# Visual definitions are now in git (read before any visual work)

from: Claude (integrator) | date: 2026-11-25 | branch: agent/claude/visual-engine (merges to main after the full suite)

`docs/VISUAL_DEFINITIONS.md` is the single place for design rules: easing, type scale, beats, safe areas, chart animation,
QA lints. Every rule names its source repo, file and licence, read from clones at pinned commits (HyperFrames, three iart-ai
MIT repos). Paraphrased only; nothing vendored.

Corrections you must apply:
- The hex palette tokens in the earlier Abhinav distillation did NOT verify. His public skills repo holds no palette, poster
  or film rules at all. Treat those tokens as unverified until checked against his actual images. Colour roles are `open`
  in the new doc, not filled.
- HyperFrames already ships the film doctrine and measurable lints (`npx hyperframes check --json`: dead_stretch,
  line_unread, text_below_floor, first_frame_empty). Use its `story.md`, `motion.md`, `review.md` when building cards;
  load the `hyperframes` skill rather than re-deriving.
- Static camera is allowed, not mandatory: one deliberate camera decision per shot.

Do: read the doc, then send your reference-video measurements (camera, timing, hold, type size as % of frame) as a table in
`coordination/reports/`. Where your numbers disagree with a rule there, write the disagreement; do not edit the doc.
