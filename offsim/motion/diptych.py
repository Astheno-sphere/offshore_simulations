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


# TODO(director): the stress-pair delta layer is BUILT, in offsim/motion/mappanel.py (not here), and is still waiting for your sign-off.
# Data: `report:decision.pair.stress` (offsim/research/stress.py, audit 13), read back through `stress.load_stress_pair(report, base_dir)`,
# which refuses a sidecar whose SHA-256 is not the report's. Drawing: `MapPanel.frame(..., delta={"pair": ..., "t": simulation_seconds})`
# (audit 14). This file stays a spec stub (SYSTEM_PLAN spec-stub row); the live diptych is story.py ALIASES {"diptych": "section"} ->
# section.py, plan map in mappanel.py. NOT wired into section.py or any film yet: nothing calls `delta=`.
#
# What the layer does, and where it differs from the first proposal here:
#   - The ribbon is the paired-time region between the two validated tracks (rungs a(t_i)-b(t_i) on the union time grid over the window
#     both cover, drawn as one path). Its width at any moment is the divergence at that moment and its widest rung is
#     `report:decision.pair.stress.max_divergence_m`. It carries no tunable number, so the band half-width `w` this stub first proposed
#     (a time window around t*) and the metre buffer a later request asked for are both NOT used: a buffer around one route says
#     nothing about where the other route is.
#   - Tracks: a = compare[0] (candidate) dashed accent, b = compare[1] (baseline) solid ink; a legend chip names them with the
#     experiment's own variant names. DIRECTOR TO DECIDE: dashed already means "not yet sailed" on the single-vessel route, so here the
#     colour carries the identity and the dash is secondary. The layer is refused with wind streaks on (v9 verdict).
#   - Clock: simulation time, supplied by the caller (as section.route_at does), not `u`; the t* connector appears when t >= t_star_s.
#   - Three readability numbers (ribbon alpha, track width, dash) are `rules.DELTA_LAYER`, flagged `assumption: True`: set by eye.
#   - The KPI card MUST cite BOTH `report:decision.pair.stress.max_divergence_m` (what the picture shows) AND `report:decision.effect` with
#     `report:decision.ci95` (what the ensemble shows), and say how extreme the picture is with `.distribution.n_pairs` and `.p50`. The
#     panel prints no number. The frame's `limits` line (EVIDENCE.limits_min) must say this is the largest-divergence pair, selected on
#     spatial divergence and not on the decision KPI, not the median; a measured value is carried as a limit, not as `assumption: true`.
#   - Refuses: `stress_blocked`, no `decision.pair.stress`, a missing or altered sidecar, and an unreportable report unless it is rendered
#     as a stamped DRAFT.
def layout(*a, **k):
    raise NotImplementedError("spec in offsim/motion/diptych.py")


frame = layout
