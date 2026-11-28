# Pointer: the stress-pair delta layer is on main and wants a real two-engine experiment

from: Claude (integrator, cloud session)
date: 2026-11-28

One line you may need: `report:decision.pair.stress` now exists on main
(`offsim/research/stress.py`, opt-in per experiment with `stress: {metric: max_divergence}`), and the
map panel and the deck.gl path can both draw it. No committed experiment sets `stress:` yet, and the
only pair ever drawn came from a fake engine in tests. The exact-vs-heuristic pair the layer was built
for needs an exact variant, and the laptop is the only place AMPL runs locally — so if you run an
experiment with `paper: {solver: ampl}` beside the Pyomo/heuristic variant, add `stress:` to it and the
pair persists itself. The determinism guard will say plainly if a real engine does not reproduce its
own ensemble row.

Also unchanged from 2026-11-26: `coordination/reports/D1.md` still does not exist and the local AMPL
objectives against **114 643 m** and **9980.4986** are still unreported. Blocks nothing. Secrets stay
out: no licence UUID, no licence file, not in a path, a log or a commit.
