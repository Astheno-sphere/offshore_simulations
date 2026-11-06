"""Weather in the SIMULATION: apply the sourced PSV Hs bands (operability.psv_effect) to a plan's stop data.

Pure, vectorised helper for the replay layer to call; it does not edit offsim/sim/replay.py. The bands are
approximate (Gribkovskaia 2022, see operability.SRC_PSV): scenarios that use them must say so.
"""
from __future__ import annotations

from .operability import psv_effect

KN = 0.514444          # m/s per knot
MIN_SPEED_FACTOR = 0.25  # a band never slows a vessel below a quarter of its planned speed


def apply_psv_weather(service_s, speed_mps, hs_at_stops) -> dict:
    """Per stop i: Hs `hs_at_stops[i]` (m, at the stop's time) -> band from `psv_effect`.
    - service_s[i]  x band service factor (1.0 / 1.2 / 1.3); in the wait-on-weather band (Hs >= 4.5 m) offloading
      stops, so the service time is returned UNCHANGED and `wow[i]` is True: the caller waits for Hs to drop, then
      serves at the planned duration.
    - speed_mps[i]  + band speed change (0 / -2 / -3 kn), floored at 25% of the planned speed.
    Inputs are equal-length sequences (or scalars broadcast to the length of hs_at_stops).
    Returns {"service_s": [...], "speed_mps": [...], "wow": [bool...], "hs_m": [...], "speed_delta_kn": [...],
    "service_factor": [...]} (lists, JSON-safe). Raises ValueError on length mismatch or negative inputs."""
    hs = _seq(hs_at_stops, None)
    n = len(hs)
    sv, sp = _seq(service_s, n), _seq(speed_mps, n)
    if not (len(sv) == len(sp) == n):
        raise ValueError(f"length mismatch: service {len(sv)}, speed {len(sp)}, hs {n}")
    out = {"service_s": [], "speed_mps": [], "wow": [], "hs_m": [], "speed_delta_kn": [], "service_factor": []}
    for h, s, v in zip(hs, sv, sp):
        if h < 0 or s < 0 or v < 0:
            raise ValueError("negative hs, service time or speed")
        b = psv_effect(h)
        f = b["service_factor"]
        out["service_s"].append(float(s) if f is None else float(s) * f)
        out["speed_mps"].append(max(float(v) + b["speed_delta_kn"] * KN, MIN_SPEED_FACTOR * float(v)))
        out["wow"].append(bool(b["wow"]))
        out["hs_m"].append(float(h))
        out["speed_delta_kn"].append(b["speed_delta_kn"])
        out["service_factor"].append(1.0 if f is None else f)
    return out


def _seq(x, n):
    try:
        return [float(a) for a in x]
    except TypeError:
        if n is None:
            return [float(x)]
        return [float(x)] * n
