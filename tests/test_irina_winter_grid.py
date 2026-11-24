"""Irina winter grid: cells come from infeasible_day_list, nothing typed."""
import json

from tools.irina_winter_grid import load_sets, render_grid


def _fixture(tmp_path):
    paper = tmp_path / "paper"
    paper.mkdir()
    for fname, days in (("stress-test.json", ["w0d0", "w0d4", "w12d2"]),
                        ("stress-test-A.json", ["w1d1", "w1d2"]),
                        ("stress-test-B.json", [])):
        winters = []
        for i in range(24):
            winters.append({"year": 2000 + i, "operating_days": 65, "weeks": 13,
                            "infeasible_days": 0, "infeasible_day_list": [],
                            "cancel_causes": {}})
        winters[0]["infeasible_day_list"] = days
        winters[0]["infeasible_days"] = len(days)
        winters[0]["cancel_causes"] = {"hs": len(days)}
        d = {"results": {"solver": {"per_winter": winters}}}
        (paper / fname).write_text(json.dumps(d))
    return paper


def test_cells_from_day_list(tmp_path):
    sets = load_sets(_fixture(tmp_path))
    assert [s["infeasible"] for s in sets] == [3, 2, 0]
    assert sets[0]["grid"][0][0] is True    # w0d0 -> col 0
    assert sets[0]["grid"][0][4] is True    # w0d4 -> col 4
    assert sets[0]["grid"][0][62] is True   # w12d2 -> col 62
    assert sets[0]["grid"][0][1] is False
    assert sets[1]["grid"][0][6] is True    # w1d1 -> col 6
    assert sets[2]["grid"][0][0] is False


def test_render_writes_pngs(tmp_path):
    sets = load_sets(_fixture(tmp_path))
    out = tmp_path / "out"
    out.mkdir()
    stats = render_grid(sets, out / "three.png")
    assert (out / "three.png").exists()
    assert stats["sets"][0][1] == 3
    render_grid(sets, out / "single.png", single=1)
    assert (out / "single.png").exists()
