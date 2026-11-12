"""Section physics: projection, buoyancy, wave spectrum, streak determinism."""
import numpy as np

from offsim.physics import ocean, streaks
from offsim.physics.fluid2d import Section2D, obstacle_mask, wind_profile


def test_projection_reduces_divergence():
    s = Section2D(60, 30, 1.0, jacobi=200)
    rng = np.random.default_rng(0)
    s.u[1:-1, 1:-1] = rng.normal(size=(58, 28))
    s.w[1:-1, 1:-1] = rng.normal(size=(58, 28))
    d0 = np.abs(s.divergence()).mean()
    s._project()
    assert np.abs(s.divergence()).mean() < 0.3 * d0


def test_hot_blob_rises():
    s = Section2D(40, 60, 0.5)
    hot = np.zeros((40, 60), bool)
    hot[18:22, 5:9] = True
    s.add_heat(hot, 400.0)
    for _ in range(80):
        s.step(0.02)
    top = np.where(((s.T - s.t_ref) > 5).any(0))[0].max()
    assert top >= 11 and s.w[15:25, 8:20].mean() > 0    # warm air risen above the source (top cell 8)


def test_inflow_and_obstacle_wake():
    nx, nz, dx = 120, 40, 0.5
    m = obstacle_mask([[(20, 0), (26, 0), (26, 8), (20, 8)]], nx, nz, dx)
    s = Section2D(nx, nz, dx, m)
    s.set_inflow(wind_profile((np.arange(nz) + 0.5) * dx, 10.0))
    for _ in range(150):
        s.step(0.02)
    assert np.all(s.u[m] == 0)
    behind = s.u[56:64, 2:12].mean()
    free = s.u[56:64, 30:38].mean()
    assert behind < free              # sheltered wake behind the block


def test_jonswap_hs():
    t = np.arange(0, 3600 * 3, 0.5)
    eta = np.array([ocean.surface([0.0], ti, 3.0, 9.0, seed=4)[0] for ti in t[::4]])
    assert abs(4 * eta.std() - 3.0) / 3.0 < 0.08
    w = np.linspace(0.3, 3, 2000)
    s = ocean.jonswap(w, 3.0, 9.0)
    assert abs(4 * np.sqrt(np.trapezoid(s, w)) - 3.0) < 1e-6


def test_streaks_deterministic():
    m = np.zeros((50, 20), bool)
    u = np.ones((50, 20)) * 2.0
    w = np.zeros((50, 20))
    a = streaks.trace(m, u, w, 1.0, 0.2, n=200, tail=8, seed_=3)
    b = streaks.trace(m, u, w, 1.0, 0.2, n=200, tail=8, seed_=3)
    assert np.array_equal(np.nan_to_num(a), np.nan_to_num(b))


def test_vessel_lineart_detail_and_solids():
    from offsim.cinema.vessel_lineart import W1, W2, W3, psv_profile
    prims, solids, exhaust = psv_profile(28.0, 10.0)
    weights = {w for _, _, w, _, _ in prims}
    assert len(prims) > 120 and {W1, W2, W3} <= weights      # detail density + three-weight hierarchy
    assert len(solids) >= 5 and exhaust[1] > 10.0 + 15        # funnel top well above the waterline


def test_ghia_reference_tables():
    """Ghia 1982 Tables I-II as stored: 17 u points, 16 v points at Re=400 (the known
    misprint v=-0.23827 at x=0.9063 is dropped, not zeroed)."""
    from offsim.physics.ghia1982 import centreline

    y, u100 = centreline(100, "u")
    assert len(y) == 17 and abs(u100[8] + 0.20581) < 1e-5   # u(0.5, 0.5), centreline
    assert abs(min(u100) + 0.21090) < 1e-5                  # u_min
    x, v400 = centreline(400, "v")
    assert len(x) == 16 and 0.9063 not in x
    _, v100 = centreline(100, "v")
    assert abs(v100[8] - 0.05454) < 1e-5                   # v(0.5, 0.5)


def test_ghia_cavity_runs_and_reports():
    """Ghia validation harness: runs to a finite, vortical state and reports errors.
    No error threshold is asserted — the repo has none, and inventing one would turn
    a measurement into a verdict. The numbers live in proof/ghia-cavity.json."""
    import importlib.util

    import numpy as np

    spec = importlib.util.spec_from_file_location("ghia_cavity", "tools/ghia_cavity.py")
    ghia = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ghia)
    r = ghia.run_cavity(100, n=33, t_end=8.0, jacobi=40)
    assert np.isfinite(r["u_min"]) and r["u_min"] < 0        # primary vortex: reversed flow mid-cavity
    assert r["v_max"] > 0
    assert r["u_err"]["rms"] >= 0 and r["v_err"]["rms"] >= 0
    assert r["u_err"]["n_points"] == 15 and r["v_err"]["n_points"] == 15  # interior points only


def test_narration_follows_measurement():
    import importlib.util
    spec = importlib.util.spec_from_file_location("film", "tools/section_film.py")
    film = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(film)
    clear = film.narration([(0, 1.0, 6.0), (1, 2.0, 4.2)])
    hit = film.narration([(0, 12.0, 0.5)])
    assert "stays clear" in clear[1] and "4 m" in clear[1]
    assert "reaches the cargo deck" in hit[1]


def test_mappanel_frame_and_zoom_rule():
    from shapely.geometry import Polygon

    from offsim.motion import mappanel
    land = Polygon([(10.0, 59.0), (10.2, 59.0), (10.2, 59.4), (10.0, 59.4)])
    mp = mappanel.MapPanel(land, (10.1, 59.1, 10.6, 59.3), size=(400, 150), seconds=5)
    route = [(10.3, 59.25), (10.4, 59.2), (10.5, 59.15)]
    a = mp.frame(0.0, route, 2, route[1])
    b = mp.frame(1.0, route, 2, route[1])
    assert a.size == b.size == (400, 150)
    assert mappanel.ZOOM_RATE <= 0.35                         # cinema rule cap
    v0, v1 = mp._view(0, route[1]), mp._view(1, route[1])
    assert v1[2] < v0[2]                                      # zooms in over the shot


def test_mappanel_second_vessel_and_route_at():
    """v6 demo film: a second vessel draws on the same panel; route_at advances with the run clock."""
    import importlib.util
    import numpy as np
    from shapely.geometry import Polygon

    from offsim.motion import mappanel
    land = Polygon([(10.0, 59.0), (10.2, 59.0), (10.2, 59.4), (10.0, 59.4)])
    mp = mappanel.MapPanel(land, (10.1, 59.1, 10.6, 59.3), size=(400, 150), seconds=5)
    route = [(10.3, 59.25), (10.4, 59.2), (10.5, 59.15)]
    other = ("PSV-2", [(10.3, 59.2), (10.4, 59.15)], 1, (10.3, 59.2))
    img = mp.frame(0.5, route, 2, route[1], others=[other])
    assert img.size == (400, 150)
    # v8: a second vessel whose marker is off-frame gets an edge indicator, not silence
    far = ("PSV-2", [(11.5, 59.2)], 1, (11.5, 59.2))
    assert mp.frame(0.5, route, 2, route[1], others=[far]).size == (400, 150)
    spec = importlib.util.spec_from_file_location("film", "tools/section_film.py")
    film = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(film)
    times = np.array([0.0, 100.0, 200.0])
    assert film.route_at(route, times, 0.0) == (1, route[0])
    k, mk = film.route_at(route, times, 150.0)
    assert k == 2 and abs(mk[0] - 10.45) < 1e-9 and abs(mk[1] - 59.175) < 1e-9  # interpolated midpoint
    assert film.route_at(route, times, 999.0) == (3, route[2])


def test_demo_narration_from_report_numbers():
    """v6 deck text: run totals come from the gated report, the plume finding from the solver."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("film", "tools/section_film.py")
    film = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(film)
    run = {"vessels": 2, "sites": 6, "distance_km": 113.346, "makespan_s": 20026.14}
    clear = film.narration([(0, 1.0, 6.0), (1, 2.0, 4.2)], run)
    assert "2 vessels, 6 sites, 113 km in 5.6 h" in clear[0]
    assert "4 m" in clear[1] and "stays clear" in clear[1]
    hit = film.narration([(0, 12.0, 0.5)], run)
    assert "reaches the deck" in hit[1]
    # both branches must fit one line at font 22 in the 968 px deck (v6 frame f0360 overflowed)
    from PIL import Image, ImageDraw, ImageFont
    fnt = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
    d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    worst = film.narration([(0, 99.0, 12.0)], run)
    for lines in (clear, hit, worst):
        for line in lines:
            assert d.textlength(line, font=fnt) <= 968, line
