"""Section + map diptych with one clock (docs/STYLE_REFERENCE.md). SPEC.

Layout (4:5, 1080x1350; 9:16 variant 1080x1920): header (kicker caps, headline with one accent word, 2-line
deck), section panel (offsim.physics: fluid streaks + ocean surface + line-art vessel/platform), readout row
(3 labelled values bound to `report:` refs, hot value in accent), map panel (deck.gl frame from render_deck at the
same t), colour bars + scale bar + "SIMULATED", methods line generated from report.provenance, handle.
Storyboard shot kind `diptych`: {section: {...}, map: {...}, clock: {start, end, loop}, readouts: [report:...]}.
Refuses: readouts not resolving to report refs, a section without method line, a report that failed a gate.

    def layout(fmt="4:5") -> dict                          # panel boxes in px
    def frame(t, section_img, map_img, readouts, text, look) -> PIL.Image
"""


# TODO(director): the data this layer needs now exists; the layer itself is NOT built and is not specced until you sign off.
# `report:decision.pair.stress` is persisted by offsim/research/stress.py (opt-in `stress: {metric: max_divergence}` in
# experiment.yaml; docs/AUDIT.md audit 13): the (year, seed) where the two compared variants' validated trajectories diverge
# most, with where (agent_id, t_star_s, pos_a, pos_b), how typical (distribution: n_pairs, p50, p90, max) and a hash of each
# trajectory sidecar. Where the layer goes, and why not here: this file is a spec stub (SYSTEM_PLAN spec-stub row). The live
# diptych is story.py ALIASES {"diptych": "section"} -> section.py, plan map in mappanel.py, as a second route through
# MapPanel.frame(u, route_xy, ...). Not touched: mappanel.py's v9 header records why the second moving layer (wind streaks)
# was REMOVED from that panel under the follow-cam; a third motion needs that judgement made again, by you.
#
# PROPOSED SPEC, "Stress-Test Delta Layer" (needs director sign-off; nothing below is implemented):
#   Draws: the `compare[1]` (baseline) route solid, the `compare[0]` (candidate) route dashed, and a shaded band between
#     the two routes over the window [t_star_s - w, t_star_s + w]: the ring made of route a over that window followed by
#     route b reversed, a segment-to-segment polygon, nothing eyeballed. `w` is a director-set number in
#     offsim/cinema/rules.py (this stub proposes none, and invents none). A marker pair at pos_a / pos_b with the distance
#     `report:decision.pair.stress.max_divergence_m` between them.
#   Numbers on screen (all `report:` refs): the KPI card MUST cite BOTH `report:decision.pair.stress.max_divergence_m`
#     (what the picture shows) AND `report:decision.effect` with `report:decision.ci95` (what the ensemble shows). The frame
#     says how extreme the picture is with `report:decision.pair.stress.distribution.n_pairs` and `.p50` ("worst of N, median X m").
#   Limits line (the evidence form's required `limits`, EVIDENCE.limits_min): says this is the largest-divergence pair, selected
#     on spatial divergence and not on the decision KPI, not the median. This is carried as a limit, NOT as `assumption: true`:
#     in this repo that tag marks an unsourced parameter, and max_divergence_m is a measured value.
#   Refuses: a report with `stress_blocked` or no `decision.pair.stress`; a report whose `reportable` is false.
def layout(*a, **k):
    raise NotImplementedError("spec in offsim/motion/diptych.py")


frame = layout
