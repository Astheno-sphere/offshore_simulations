"""Gate-2 cross-check: the ampl_backend's commercial solver equals HiGHS."""
from __future__ import annotations

import pytest

amplpy = pytest.importorskip("amplpy")
from offsim.solve.ampl_backend import (
    best_available_solver,
    certify_against_highs,
    solve_model,
)


def _license_ok() -> bool:
    try:
        from amplpy import modules
        return "base" in modules.installed()
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _license_ok(),
    reason="AMPL modules not installed; see tools/ampl_mcp/README.md",
)


def test_trivial_lp_solvers_agree():
    model = "var x>=0; var y>=0; minimize c: x+2*y; s.t. r: x+y>=3;"
    match, commercial, highs = certify_against_highs(model, tol=1e-6)
    assert match, (commercial, highs)
    assert commercial.objective == pytest.approx(3.0)
    assert highs.objective == pytest.approx(3.0)


def test_small_assignment_mip_matches_across_solvers():
    # Pure 3x3 assignment. True optimum: a->2 (2) + b->1 (6) + c->3 (1) = 9.
    model = """
    set W; set T;
    param cost{W, T};
    var x{W, T} binary;
    minimize total: sum{w in W, t in T} cost[w,t]*x[w,t];
    s.t. one_per_worker{w in W}: sum{t in T} x[w,t] = 1;
    s.t. one_per_task{t in T}: sum{w in W} x[w,t] = 1;
    data;
    set W := a b c;
    set T := 1 2 3;
    param cost: 1  2  3 :=
      a         9  2  7
      b         6  4  3
      c         5  8  1 ;
    """
    match, commercial, highs = certify_against_highs(model, tol=1e-6)
    assert match, (commercial, highs)
    assert commercial.objective == pytest.approx(9.0)
