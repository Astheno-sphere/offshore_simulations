"""Weather in the SIMULATION (not cosmetic): speed loss, service time, wait-on-weather.

PSV_HS_BANDS is sourced (Gribkovskaia, offshore supply vessel planning, UiO seminar slides 2022 — table layout
was ambiguous, treat as approximate). Helicopter and crane limits are NOT sourced yet: scenarios using them
must carry `assumption: true` until DNV-ST-N001 / NORSOK R-003 / CAP 437 / SPA.HOFO.135 values are read.
"""

SRC_PSV = ("Gribkovskaia I., Offshore supply vessel planning, UiO seminar 2022-06-08, "
           "https://mn.uio.no/math/english/research/groups/statistics-data-science/events/seminars/lectures-2020/"
           "irina_Gribkovskaia_offshore-supply-vessel-planning-uio-08.06.22.pdf")

# (Hs upper bound m, speed change knots, service time factor, wait_on_weather)
PSV_HS_BANDS = [
    (2.5, 0.0, 1.00, False),
    (3.5, 0.0, 1.20, False),
    (4.5, -2.0, 1.30, False),
    (float("inf"), -3.0, None, True),   # ≥4.5 m: offloading stops, vessel waits (WOW)
]

HELI = {"wind_limit_kn": None, "deck_motion": None, "src": None, "assumption": True}      # check: CAP 437, HCA limitations list
CRANE = {"hs_limit_m": None, "wind_limit_ms": None, "src": None, "assumption": True}       # check: DNV-ST-N001, NORSOK R-003


def psv_effect(hs_m: float) -> dict:
    """Band lookup for the replay: {'speed_delta_kn', 'service_factor', 'wow'}."""
    for upper, dv, factor, wow in PSV_HS_BANDS:
        if hs_m < upper:
            return {"speed_delta_kn": dv, "service_factor": factor, "wow": wow, "src": SRC_PSV}
    raise ValueError(hs_m)


def weather_windows(series, limit_hs: float, min_hours: float):
    """Contiguous periods with Hs < limit for ≥ min_hours (operability gate input). Not built."""
    raise NotImplementedError
