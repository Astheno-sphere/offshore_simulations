import numpy as np
import pytest

from offsim.physics.jonswap import Sea

CASES = [(0.5, 4.0), (2.0, 8.0), (4.5, 11.0), (8.0, 14.0)]


@pytest.mark.parametrize("hs,tp", CASES)
def test_spectral_hs_recovered(hs, tp):
    assert abs(Sea(hs, tp).hs_from_spectrum() - hs) / hs < 0.005


def test_time_series_hs():
    # Assumption: 8% tolerance on 4*std of a ~1.5 h record (finite-record sampling noise of a random-phase sum).
    for hs, tp in [(2.0, 8.0), (4.5, 11.0)]:
        for seed in (1, 2, 3, 4):
            s = Sea(hs, tp, seed=seed)
            t = np.arange(0, 5400, 0.5)
            e = np.array([s.eta(np.array([0.0]), ti)[0] for ti in t])
            assert abs(4 * e.std() - hs) / hs < 0.08


def test_seed_determinism():
    x = np.linspace(0, 500, 50)
    assert np.array_equal(Sea(2, 8, seed=5).eta(x, 3.0), Sea(2, 8, seed=5).eta(x, 3.0))
    assert not np.array_equal(Sea(2, 8, seed=5).eta(x, 3.0), Sea(2, 8, seed=6).eta(x, 3.0))


@pytest.mark.parametrize("hs,tp", CASES)
def test_peak_period(hs, tp):
    s = Sea(hs, tp)
    w = np.linspace(s.w_lo, s.w_hi, 20000)
    assert abs(2 * np.pi / w[np.argmax(s.spectrum(w))] - tp) / tp < 0.02


@pytest.mark.parametrize("hs,tp", [(0, 8), (-1, 8), (2, 0), (2, -3), (float("nan"), 8)])
def test_rejects_bad_inputs(hs, tp):
    with pytest.raises(ValueError):
        Sea(hs, tp)


def test_dtype_and_shapes():
    s = Sea(2, 8)
    assert s.eta(np.zeros(7), 0.0).shape == (7,)
    x, z = s.transect(0, 100, 11, 1.0)
    assert x.dtype == z.dtype == np.float32 and x.shape == z.shape == (11,)
    X, Y, Z = s.grid(16, 8, 200.0, 2.0)
    assert X.shape == Y.shape == Z.shape == (8, 16)
    assert Z.dtype == np.float32 and np.all(Z[:, :1] == Z[0, 0])  # unidirectional: constant along y
    assert Sea(2, 8, depth_m=30).k[0] > Sea(2, 8).k[0] * 0.99
