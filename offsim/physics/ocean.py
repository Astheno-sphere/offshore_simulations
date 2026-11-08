"""Sea surface along a section from a wave spectrum. SPEC.

JONSWAP spectrum S(w; Hs, Tp, gamma=3.3 default, cited) -> N frequency components with random phases from the
seed; linear superposition eta(x, t) = sum a_i cos(k_i x - w_i t + phi_i), deep-water dispersion w^2 = g k
(finite depth from the world's bathymetry when given). Hs/Tp from the hour of the WeatherSeries.
Check: the significant height of the synthesised record 4*std(eta) is within 5% of Hs over a long record.

    def jonswap(w, hs_m, tp_s, gamma=3.3) -> np.ndarray
    def surface(x_m, t_s, hs_m, tp_s, seed=0, n=128, depth_m=None) -> np.ndarray
"""


def jonswap(*a, **k):
    raise NotImplementedError("spec in offsim/physics/ocean.py")


def surface(*a, **k):
    raise NotImplementedError("spec in offsim/physics/ocean.py")
