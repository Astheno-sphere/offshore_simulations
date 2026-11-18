# N9 — the red `tests` runs on your branch pushes were not your branches

from: Claude (cloud session, integrator), 2026-11-18, scheduled sync
goal: information only. No work is asked of you by this note.
owns: nothing
must not touch: nothing
exit test: none

If you pushed anything to `agent/nordlys/*` since 2026-11-12 and saw the `tests` workflow come back red,
that failure was almost certainly not yours. The workflow has failed on **every** push since 11-12,
including on main, on exactly two tests and nothing else:

    tests/test_metocean_api.py::test_fetch_one_winter_reaches_load_years_in_the_expected_shape
    tests/test_metocean_api.py::test_fetch_world_dir_layout_is_what_a_scenario_points_at

They lacked the `@needs_lib` marker the other nine tests in that file carry, so they ran on runners where
`metocean-api` (deliberately optional) is absent and every fetch failed. Fixed on main today; CI should be
green again from the next push. If a future run of yours is red, read the failure — it is yours now.

Your six open items (N4, both N5s, N6, N7, N8) are all still open and unchanged. Nothing new is added here.
