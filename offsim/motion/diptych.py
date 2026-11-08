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


def layout(*a, **k):
    raise NotImplementedError("spec in offsim/motion/diptych.py")


frame = layout
