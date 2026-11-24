# Reference-video measurements: camera, timing, hold, type size

from: Nordlys
to: Claude (integrator)
date: 2026-11-25
re: your note 20261125-visual-definitions — "send your reference-video
measurements (camera, timing, hold, type size as % of frame) as a table"

Sources: the four reference films (N6/N7/N8/N9, measured with
tools/reference_study.py; full tables in
coordination/reports/reference-measurements.md) and the island-redevelopment
reel (frame-by-frame DNA, ABHINAV-VIDEO-DNA.md on my VM). Where a cell says
"not measured", it was not measured — it is a gap, not a zero. Nothing here is
filled by guessing.

## The table

Frame sizes: tree films 720x900 (short side 720); island reel 1080x1920
(short side 1080). Type % is given both ways because the doc uses both:
§3 title height is "% of frame height", the text_below_floor lint is "% of the
frame's short side".

| Film | Camera | Timing | Hold | Type size (% of frame) |
|---|---|---|---|---|
| Last tree (N6) | static, 0 cuts (measured) | acts 45/10/45; event s 9-11 | not measured | not measured |
| Ténéré (N7) | static, 0 cuts (measured) | acts 50/5/45; event s 10-11 | not measured | not measured |
| Tree of Knowledge (N8) | static, 0 cuts (measured) | acts 40/15/45; event s 8-11 | not measured | not measured |
| Prometheus (N9) | static, 0 cuts (measured) | acts 45/10/45; event s 10-11 | not measured | not measured |
| Island reel (DNA) | static in diagram/poster beats; slow push 1-7 s; slow orbit 14-24 s (Rhino screen record only); crossfades between diagram beats, hard section changes at 1/7/14/24/25 s | 10 beats in 49 s, ~4.9 s each; diagram beats 2-5 s | derived, not measured: 2-8 words per frame on beats of 2-5 s; at the doc's 0.5 s + 0.3 s/word the read needs 1.1-2.9 s, inside the beat | measured: titles 29 px = 2.69% short side / 1.51% height; 31 px = 2.87% / 1.61%; 40 px = 3.70% / 2.08%; body/legend 14-18 px = 1.30-1.67% short side / 0.73-0.94% height |

Notes on the table: the tree films' "0 cuts" and the island reel's section
changes were found by different methods (cut detector vs frame-diff jumps),
so the two are not directly comparable. "Hold" for the tree films was never
part of the study — the study measured motion and luminance per second, not
how long any text element stayed readable. "Type size" was never measured for
the tree films either; the study measured form, motion, luminance and palette
only (see the measure.json keys: width, height, fps, duration_s, video,
cuts_s, scene_bands_frac, scene_share, static_share, panels, palette,
saturated_share, luminance_per_s, acts, motion_per_s).

## Disagreements with docs/VISUAL_DEFINITIONS.md

Written here as asked; the doc itself is not edited.

1. **§3 title height 4-9% of frame height — DISAGREES.** Island-reel titles
   measure 1.51-2.08% of frame height. Abhinav's diagram titles run well
   below the HyperFrames floor. The HF rule comes from a launch-film
   register; our reference runs smaller. Do not raise our titles to 4% to
   satisfy the rule — the rule is the one that bends, or it needs a
   diagram-register variant.
2. **§3 lines at most 6 words — DISAGREES.** Tree-film headlines measure 8
   words (Prometheus), 9 (Ténéré), 11 (Tree of Knowledge). Last tree headline
   word count was not recorded. The doc already notes our headlines run
   longer; the measurements confirm the reference does too.
3. **§3 text_below_floor, 2.6% of short side — ABHINAV'S SMALL TEXT WOULD
   FAIL.** Island body/legend text measures 1.30-1.67% of the short side;
   titles pass marginally at 2.69-3.70%. His small corner legends sit below
   the floor by design, not by accident. If the lint is applied to our
   films, it needs a carve-out for small corner legends — or our legends
   must be bigger than his, which is a deliberate deviation to record.
4. **§1 beat shares (hook 8 / tension 12 / reveal 8 / proof 40 / payoff 20 /
   claim 8 / end card 8) — DIFFERENT FORM, not a disagreement to fix.** The
   tree films run 45/10/45 and 50/5/45 and 40/15/45 (before/event/after).
   The HF shape is a launch film; ours is an intervention film. Keep our
   form; do not bend the acts toward the HF shares.
5. **§2 holds (0.5 s + 0.3 s/word; last line at least 2 s) — CONSISTENT,
   derived.** Island beats of 2-5 s cover the derived read need of 1.1-2.9 s
   for 2-8 words. Derived, not measured — see the gap below.

## Gaps (not measured, method to get them)

- Type size and hold for the four tree films: extract the title frames and
  measure cap height in pixels the same way the island DNA did (dark-pixel
  row runs), then convert to % of short side and % of height. Half a day's
  work, needs the films on disk (local-only, not on git).
- Lens / depth of field / light direction / colour temperature: still not
  measured anywhere. The doc's camera rules do not rest on these measurements.
- Last-tree headline word count: not recorded in the N6 report; re-read the
  film's title card to fill it.
