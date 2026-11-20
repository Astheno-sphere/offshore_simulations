# D4 — hooks are live on main, and one of them may not run on your box

from: Claude (cloud session, integrator), 2026-11-20, scheduled sync
goal: information, plus one thing to check on the laptop and report in a line.
owns: nothing
must not touch: nothing
exit test: `python3 --version` on the laptop, reported in your next report or note.

Arshad merged J2 to main on 11-19: five harness hooks in `tools/hooks/gate.py`, wired through
`.claude/settings.json`, documented in `docs/HOOKS.md`. H4 is the one that matters most here — it blocks a
write or command carrying a UUID near "AMPL" or "licence/license", and its message is only "a secret-shaped
string is present", never the string. That is a guard on exactly the path your box is the only one that can
walk, so it is on your side, not against you.

**The thing to check.** `coordination/reports/J2.md` states that where `python3` is not on PATH — "some
Windows laptops" — the hook errors without blocking, i.e. it fails open and H4 silently stops guarding.
Run `python3 --version` in the shell your Claude desktop session actually uses and say in one line whether it
resolves. If it does not, H4 is not protecting the only box that holds the licence, and the licence discipline
there is manual until that is fixed.

Unchanged from 20261115-D1-still-owed and 20261117-D2: `coordination/reports/D1.md` with the AMPL objective
and the Pyomo twin objective on the demo scenario is still the first thing owed, and still only possible on
your box while `AMPL_LICENSE_UUID` is absent from Actions. The objective values alone are what is wanted; the
licence string enters no file, log, commit or note.
