"""Molde morning v2: same measured morning as v1, richer map.

Same narration (re-measured in v2/measure.json — identical totals), plus the v2
map contract: two mode colours with the mode named on the map and the chart,
street names and lit places from OSM/GTFS tags inside the bbox, and the credit
line. No rendering here — the film tool's --only still check covers pixels.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.molde_film_v2 import (  # noqa: E402
    CREDIT, DECK1_RULES, DECK2_RULES, DRAFT, FERRY, FRAM, HEADLINE, LIT_PLACES,
    METHODS, STREET_LABELS, deck_lines, narration_values,
)
from offsim.cinema.draw import Canvas  # noqa: E402
from offsim.motion import narrate  # noqa: E402

FILM_DIR = Path("/home/hatch/workspace/docs/linkedin/05-molde/v2")
REPO = Path(__file__).resolve().parents[1]


def test_narration_values_match_report():
    v = narration_values()
    rep = json.loads((REPO / "out/molde-gtfs-replay/report.json").read_text())
    assert v["trips"] == int(rep["measured"]["trips"]) == 289
    assert abs(v["vehicle_km"] - rep["measured"]["vehicle_km"]) < 0.1
    assert v["peak_vehicles"] == int(rep["measured"]["peak_vehicles"]) == 67
    assert v["ferry_trips"] == 58
    assert abs(v["ferry_share_pct"] - 8.0) < 0.1
    assert v["ferry_1070_trips"] == 23


def test_deck_lines_unchanged_from_v1():
    d1, d2 = deck_lines()
    assert d1 == "289 trips, 5,963 km in 4 hours — peak 67 vehicles at 07:35."
    assert d2 == "But 1 in 5 trips is a ferry, and the sea carries only 8% of the distance."
    v = narration_values()
    assert narrate.choose(DECK2_RULES, {**v, "ferry_trips": 10}) != d2


def test_per_mode_series_sum_to_all_and_peaks_match():
    m = json.loads((FILM_DIR / "measure.json").read_text())
    s = m["active_series_30s"]
    assert len(s["bus"]) == len(s["all"]) == len(s["ferry"]) == 480
    assert all(b + f == a for b, f, a in zip(s["bus"], s["ferry"], s["all"]))
    assert m["peak_by_mode"]["bus"] == {"vehicles": 59, "at_clock": "07:35"}
    assert m["peak_by_mode"]["ferry"] == {"vehicles": 9, "at_clock": "07:20"}
    assert m["totals"] == json.loads(
        (FILM_DIR.parent / "measure.json").read_text())["totals"]


def test_two_mode_colours_are_distinct_and_from_the_palette():
    assert FRAM != FERRY
    assert FRAM == "#4f8f9c"  # palette field_diverging[0]
    assert FERRY == "#e5a028"  # palette accent (gold)


def test_every_on_screen_line_fits():
    probe = Canvas(1080, 1350, bg="#331c22", ss=1)
    for line in HEADLINE:
        w = sum(probe.measure(t, ("Inter", "Bold"), 52) for t, _ in line)
        assert w <= 968, f"headline too wide: {w:.0f}px"
    for d in deck_lines():
        assert probe.measure(d, ("Inter", "Regular"), 22) <= 968, f"deck too wide: {d}"
    for s, weight in ((METHODS, "Regular"), (DRAFT, "Regular"), (CREDIT, "Bold")):
        assert probe.measure(s, ("Inter", weight), 13) <= 968, f"footer too wide: {s}"
    assert "Arshad Abbasia" in CREDIT


def test_map_labels_come_from_real_tags_inside_the_bbox():
    rep = json.loads((REPO / "out/molde-gtfs-replay/report.json").read_text())
    lon0, lat0, lon1, lat1 = rep["provenance"]["world_manifest"]["bbox"]
    assert len(LIT_PLACES) == 6
    for _label, lon, lat, src in LIT_PLACES:
        assert lon0 <= lon <= lon1 and lat0 <= lat <= lat1, f"{_label} outside bbox"
        assert src, f"{_label} has no source"
    assert len(STREET_LABELS) == 5
    assert [s[0] for s in STREET_LABELS] == [
        "E39", "Fv 64", "Storgata", "Julsundvegen · Fv 662", "Frænavegen · Fv 538"]
    # every lit place and street label is placed without an overlapping fallback
    placed = json.loads((FILM_DIR / "placed.json").read_text())
    assert placed["fell_back"] == []
    assert len(placed["placed"]) == len(LIT_PLACES) + len(STREET_LABELS) + 1  # + FRAM 701
