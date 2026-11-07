"""Finding shots: how a *result* is shown, as opposed to the operation (map shots). SPEC.

A map shot shows what one run did. A finding shot shows what the ensemble says. Every value comes from
report["ensemble"] (offsim.montecarlo.Ensemble.to_report); a finding shot refuses a report without it.

Shot kinds (storyboard `kind:`), each a pure function report -> scene/data dict for an existing renderer:
- `ghost_tracks`  deck.gl: N runs' trajectories drawn at low alpha under the highlighted P50 run; shows
                  spread in route/timing caused by weather. Renderer: render_deck TripsLayer, already built.
- `fan`           KPI over time or over weather years: P10-P90 band, P25-P75 band, P50 line, per variant.
                  Renderer: HyperFrames card with an SVG chart (template offsim/motion/templates/fan/).
- `paired`        baseline vs variant: paired differences per (year, seed) as a strip + mean and 95% CI bar,
                  status word from the experiment decision (supported / not supported / inconclusive).
- `state_gantt`   per vessel: states over time (sail, dp, wait, load) with weather-wait highlighted and the
                  Hs series as a strip under it; the "why" of a delay. Renderer: HyperFrames or Manim.
- `weather_year`  calendar heat strip of operable hours per year (from operability limits), to show which
                  winters drive the P90.
Rules: axis ranges fixed across variants; uncertainty always shown when a single number is shown; the
status word appears with every comparison; units in SI or nautical (kn, nm) per docs/VISUAL_SPEC.md.

    def ghost_tracks(report, ensemble_dir, n=40) -> dict
    def fan(report, kpi, by="variant") -> dict
    def paired(report, kpi, a, b) -> dict
    def state_gantt(traj, weather, agents=None) -> dict
    def weather_year(weather_years, limits) -> dict
"""


def _spec(*_a, **_k):
    raise NotImplementedError("spec in offsim/motion/findings.py docstring")


ghost_tracks = fan = paired = state_gantt = weather_year = _spec
