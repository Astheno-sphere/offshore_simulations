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


def test_narration_follows_measurement():
    import importlib.util
    spec = importlib.util.spec_from_file_location("film", "tools/section_film.py")
    film = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(film)
    clear = film.narration([(0, 1.0, 6.0), (1, 2.0, 4.2)])
    hit = film.narration([(0, 12.0, 0.5)])
    assert "stays clear" in clear[1] and "4 m" in clear[1]
    assert "reaches the cargo deck" in hit[1]
