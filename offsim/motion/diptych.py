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


# TODO(director): this stub is NOT the place for a trajectory-delta ("gap shot") layer, for two reasons.
# 1. Wrong file. The live diptych is `story.py` ALIASES {"diptych": "section"} -> `section.py` with the plan map
#    in `mappanel.py`. A delta layer belongs there, as a second route passed to MapPanel.frame(u, route_xy, ...).
#    It needs a director spec first: mappanel's v9 header records why the second moving layer (wind streaks) was
#    REMOVED from this panel -- it competed with the section streaks under the follow-cam. A third motion needs
#    that judgement made again, not assumed.
# 2. No number to draw yet. The two-engine comparison already exists upstream and is stricter than a bare
#    percentage: `offsim/research/run_experiment.py` `decide_from()` writes `decision` = {kpi, compare, better,
#    min_effect, effect, ci95, n_pairs, status}, gated by `reportable` (ens.ok and not synthetic_weather and
#    validated) with `blocked` saying why when it is not. Those are the refs a gap shot must cite --
#    `report:decision.effect`, `report:decision.ci95`, `report:decision.status` -- never an invented
#    `report:gap.kpi_delta`, which would restate `decision.effect` without its interval.
#    What is genuinely missing is a ref to the two trajectories themselves: an experiment runs seeds x winters
#    per variant and `Ensemble.to_report()` keeps aggregate quantiles only, so "the validated exact trajectory"
#    is not yet a single, addressable object. Which run a pair ref points at (median seed? named seed? the
#    decision winter?) decides what the delta picture asserts. See docs/AUDIT.md audit 12.
def layout(*a, **k):
    raise NotImplementedError("spec in offsim/motion/diptych.py")


frame = layout
