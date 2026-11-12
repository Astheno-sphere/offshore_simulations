"""Molde morning film: narration rules fire on the measured morning, and every on-screen
line fits its width (the v6 deck-width lesson, now asserted). No rendering here — the
film tool's --only still check covers pixels."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.molde_film import DECK1_RULES, DECK2_RULES, HEADLINE, deck_lines, narration_values
from offsim.cinema.draw import Canvas
from offsim.motion import narrate

FILM_DIR = Path("/home/hatch/workspace/docs/linkedin/05-molde")


def test_narration_values_match_report():
    v = narration_values()
    rep = json.loads((Path(__file__).resolve().parents[1]
                      / "out/molde-gtfs-replay/report.json").read_text())
    assert v["trips"] == int(rep["measured"]["trips"]) == 289
    assert abs(v["vehicle_km"] - rep["measured"]["vehicle_km"]) < 0.1
    assert v["peak_vehicles"] == int(rep["measured"]["peak_vehicles"]) == 67
    assert v["ferry_trips"] == 58
    assert abs(v["ferry_share_pct"] - 8.0) < 0.1
    assert v["ferry_1070_trips"] == 23


def test_deck_rules_fire_the_measured_sentences():
    d1, d2 = deck_lines()
    assert d1 == "289 trips, 5,963 km in 4 hours — peak 67 vehicles at 07:35."
    assert d2 == "But 1 in 5 trips is a ferry, and the sea carries only 8% of the distance."
    # the rules, not literals: the ferry rule only fires on the measured split
    v = narration_values()
    assert narrate.choose(DECK2_RULES, {**v, "ferry_trips": 10}) != d2


def test_every_on_screen_line_fits():
    probe = Canvas(1080, 1350, bg="#331c22", ss=1)
    for line in HEADLINE:
        w = sum(probe.measure(t, ("Inter", "Bold"), 52) for t, _ in line)
        assert w <= 968, f"headline too wide: {w:.0f}px"
    for d in deck_lines():
        assert probe.measure(d, ("Inter", "Regular"), 22) <= 968, f"deck too wide: {d}"


def test_measure_json_is_the_replay_not_a_retype():
    m = json.loads((FILM_DIR / "measure.json").read_text())
    assert m["totals"]["trips"] == 289
    assert m["totals"]["vehicle_km"] == 5962.7
    assert m["peak"]["vehicles_all"] == 67
    assert m["peak"]["at_clock"] == "07:35"
    assert m["bus"]["trips"] + m["ferry"]["trips"] == 289
    assert m["source"]["gates"] == {"0_provenance": True, "1_plan": True,
                                    "2_replay_equals_plan": True, "3_contract": True,
                                    "4_paper": False}
