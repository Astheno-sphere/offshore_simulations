"""searoute-py behind the (legs, dist_m, time_s) contract, and its disagreement with our own SeaGraph, as numbers.

The comparison asserts only what must hold for ANY router (a route is no shorter than the great circle, a ratio is
finite). It never asserts agreement between the two: a disagreement is a finding for the report, not a test to tune."""
import json
import os

import numpy as np
import pytest

pytest.importorskip("searoute")
from offsim.contract import haversine_m  # noqa: E402
from offsim.traffic.searoute_adapter import SearouteGraph, compare_with_seagraph  # noqa: E402

BERGEN, STAVANGER, KRISTIANSAND = (5.32, 60.39), (5.73, 58.97), (7.99, 58.15)


def test_contract_shape_and_units():
    g = SearouteGraph(speed_mps=6.0)
    legs, dist, time = g.legs([BERGEN, STAVANGER, KRISTIANSAND])
    assert set(legs) == {(i, j) for i in range(3) for j in range(3) if i != j}
    assert dist.shape == time.shape == (3, 3) and (np.diag(dist) == 0).all() and (np.diag(time) == 0).all()
    assert np.allclose(time, dist / 6.0) and np.allclose(dist, dist.T)
    assert legs[(0, 1)][0] == BERGEN and legs[(0, 1)][-1] == STAVANGER          # endpoints exactly as given
    assert legs[(1, 0)] == legs[(0, 1)][::-1]
    gc = haversine_m(BERGEN[0], BERGEN[1], STAVANGER[0], STAVANGER[1])
    assert gc <= dist[0, 1] < 3 * gc                                            # never shorter than the great circle


def test_distance_is_measured_like_our_other_legs():
    g = SearouteGraph()
    p = g.path(BERGEN, STAVANGER)
    a = np.array(p)
    assert g.last_props["lane_m"] + g.last_props["stub_m"] == pytest.approx(
        haversine_m(a[:-1, 0], a[:-1, 1], a[1:, 0], a[1:, 1]).sum(), rel=1e-9)


def test_bad_speed_is_refused():
    with pytest.raises(ValueError):
        SearouteGraph(speed_mps=0)


def _ne_land():
    import pyogrio
    shp = os.path.join(os.path.dirname(pyogrio.__file__), "tests", "fixtures", "naturalearth_lowres", "naturalearth_lowres.shp")
    if not os.path.exists(shp):
        pytest.skip("Natural Earth 110m fixture shipped inside pyogrio is not installed")
    import geopandas as gpd
    return gpd.read_file(shp).cx[-2:16, 54:64].geometry.union_all()


# (name, a, b): the first rounds Lindesnes (land in the way), the second is open North Sea water.
ROUTES = [("Utsira-Skagerrak round Lindesnes", (4.5, 59.0), (9.5, 57.8)), ("open North Sea N-S", (3.8, 57.5), (4.2, 60.0))]


@pytest.mark.parametrize("name,a,b", ROUTES, ids=[r[0] for r in ROUTES])
def test_disagreement_with_seagraph_is_measured_and_reported(name, a, b, tmp_path):
    """LAND is 1:110m Natural Earth (very coarse: no skerries, fjords or islands), so SeaGraph's absolute number here is
    optimistic. This is a smoke comparison of two routers on one pair of points, not a calibration of either."""
    from offsim.worlds.sealanes import SeaGraph

    sea = SeaGraph(_ne_land(), bbox=(3.5, 56.5, 11.0, 60.5), spacing_m=2500, clearance_m=2500)
    r = compare_with_seagraph(sea, a, b)
    assert r["snap_m"] == [0.0, 0.0], "pick points in water; a snapped endpoint would blur the comparison"
    assert r["seagraph_m"] >= r["great_circle_m"] * 0.999 and r["searoute_m"] >= r["great_circle_m"] * 0.999
    assert np.isfinite(r["ratio"]) and r["ratio"] > 0
    assert r["stub_m"] == pytest.approx(r["searoute_m"] - r["searoute_lane_m"], rel=1e-6)
    (tmp_path / "disagreement.json").write_text(json.dumps({name: r}, indent=1))
    print(f"\nSEAROUTE vs SEAGRAPH {name}: seagraph {r['seagraph_m']/1000:.1f} km, searoute {r['searoute_m']/1000:.1f} km "
          f"(lane {r['searoute_lane_m']/1000:.1f} + stubs {r['stub_m']/1000:.1f}), great circle {r['great_circle_m']/1000:.1f} km, "
          f"searoute/seagraph {r['ratio']:.3f}, lane-only {r['lane_rel_diff']:+.3f}")
