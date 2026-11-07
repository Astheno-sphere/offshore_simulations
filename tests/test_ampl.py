"""AMPL route solver and tools/ampl_mcp.

Always run: route extraction, the data writer, plan checks, the scenario guard, the AMPL text screen.
Run only where AMPL can start (GitHub Actions after activation, or the laptop): model parse and the exact solve.
"""
import importlib.util
import itertools

import yaml

import pytest

from conftest import ROOT
from offsim.engines.base import Problem, Unsupported
from offsim.solve import ampl_adapter as A

AMPL_OK, AMPL_WHY = A.ampl_status()
needs_ampl = pytest.mark.skipif(not AMPL_OK, reason=f"AMPL cannot start here: {AMPL_WHY}")

DIST = [[0, 4, 6, 5, 7], [4, 0, 3, 6, 8], [6, 3, 0, 4, 5], [5, 6, 4, 0, 3], [7, 8, 5, 3, 0]]
MOD = ROOT / "offsim/solve/ampl/cvrp.mod"


def problem(cap=6, veh=2):
    return Problem(cls={"CVRP"}, nodes=[(10.0 + 0.1 * i, 59.0) for i in range(5)], dist_m=DIST,
                   demand={1: 3, 2: 3, 3: 3, 4: 3},
                   fleet=[{"cls": "psv", "count": veh, "capacity": cap, "speed_mps": 5.0}])


def brute_force_cvrp(dist, demand, cap, veh):
    """Exact optimum for a few clients by enumeration: independent of AMPL and PyVRP."""
    n = len(dist) - 1
    best = float("inf")
    clients = list(range(1, n + 1))
    for perm in itertools.permutations(clients):
        for cuts in itertools.combinations(range(1, n), veh - 1):
            bounds = (0,) + cuts + (n,)
            routes = [perm[a:b] for a, b in zip(bounds, bounds[1:])]
            if any(not r for r in routes) or any(sum(demand[c] for c in r) > cap for r in routes):
                continue
            best = min(best, sum(dist[a][b] for r in routes for a, b in zip((0,) + r, r + (0,))))
    return best


# --- routes_from_arcs ----------------------------------------------------------------------------------------
def test_routes_from_arcs_two_routes():
    arcs = [(0, 1), (1, 2), (2, 0), (0, 3), (3, 4), (4, 0)]
    assert A.routes_from_arcs(arcs) == [[1, 2], [3, 4]]


def test_routes_from_arcs_accepts_numpy_like_floats():
    assert A.routes_from_arcs([(0.0, 1.0), (1.0, 0.0)]) == [[1]]


@pytest.mark.parametrize("arcs, why", [
    ([(0, 1), (1, 0), (2, 3), (3, 2)], "cycle without the depot"),
    ([(0, 1), (1, 2), (1, 3), (2, 0), (3, 0)], "client with two successors"),
    ([(0, 1), (1, 2), (2, 0), (0, 3)], "client entered and never left"),
])
def test_routes_from_arcs_rejects_broken_plans(arcs, why):
    with pytest.raises(ValueError):
        A.routes_from_arcs(arcs)


# --- data file --------------------------------------------------------------------------------------------------
def test_write_dat_writes_sets_and_params(tmp_path):
    text = A.write_dat(problem(), tmp_path / "cvrp.dat").read_text()
    assert "set NODES := 0 1 2 3 4;" in text
    assert "set CLIENTS := 1 2 3 4;" in text
    assert "param VEH := 2;" in text
    assert "param cap := 6.000000;" in text
    lines = text.splitlines()
    d = lines.index(next(line for line in lines if line.startswith("param demand")))
    assert lines[d + 1] == "1 3.000000 2 3.000000 3 3.000000 4 3.000000;"
    k = next(i for i, line in enumerate(lines) if line.startswith("param dist :"))
    assert lines[k].split(":")[1].replace(":=", "").split() == ["0", "1", "2", "3", "4"]
    rows = []
    for line in lines[k + 1:]:
        if line == ";":
            break
        rows.append(line.split())
    assert [r[0] for r in rows] == ["0", "1", "2", "3", "4"]
    assert [float(x) for x in rows[0][1:]] == DIST[0]
    assert [float(x) for x in rows[4][1:]] == DIST[4]


def test_write_dat_refuses_demand_above_capacity(tmp_path):
    with pytest.raises(ValueError, match="capacity"):
        A.write_dat(problem(cap=2), tmp_path / "x.dat")


def test_write_dat_refuses_other_classes(tmp_path):
    p = problem()
    p.cls = {"VRPTW"}
    with pytest.raises(Unsupported):
        A.write_dat(p, tmp_path / "x.dat")


def test_solver_refuses_other_classes_before_touching_ampl():
    p = problem()
    p.cls = {"PSV-PDP"}
    with pytest.raises(Unsupported):
        A.AMPLSolver().solve(p)


# --- plan checks and distances (pure) -------------------------------------------------------------------------
def test_route_distance_and_plan_check():
    routes = [[1, 2], [3, 4]]
    assert A.route_distance(DIST, routes) == pytest.approx((4 + 3 + 6) + (5 + 3 + 7))
    ok = A.check_plan(problem(), routes)
    assert ok["served_once"] and ok["capacity_ok"] and ok["fleet_ok"] and ok["loads"] == [6, 6]
    bad = A.check_plan(problem(), [[1, 2, 3, 4]])
    assert bad["served_once"] and not bad["capacity_ok"]


# --- model text ------------------------------------------------------------------------------------------------
def test_cvrp_mod_has_the_declared_blocks():
    text = MOD.read_text()
    for needle in ("set NODES;", "param VEH", "param cap", "param dist", "param demand", "var x {ARCS} binary;",
                   "minimize total_distance", "subject to mtz", "subject to fleet_limit"):
        assert needle in text, needle


def test_cvrp_mod_passes_the_text_screen():
    server = _server()
    server.screen(MOD.read_text(), model_file=True)


@needs_ampl
def test_cvrp_mod_parses_and_reads_data(tmp_path):
    p = A.write_dat(problem(), tmp_path / "cvrp.dat")
    ampl = A._start_ampl()
    ampl.read(str(MOD))
    ampl.read_data(str(p))
    assert ampl.get_objective("total_distance") is not None


@needs_ampl
def test_exact_solve_matches_brute_force_and_pyvrp():
    from offsim.solve.pyvrp_adapter import solve_cvrp
    plan = A.solve(problem(), seconds=20, seed=1, solver="highs")
    best = brute_force_cvrp(DIST, {1: 3, 2: 3, 3: 3, 4: 3}, cap=6, veh=2)
    assert plan.status == "optimal" and plan.bound == plan.objective
    assert plan.objective == pytest.approx(best)
    routes, cost = solve_cvrp(problem().nodes, {1: 3, 2: 3, 3: 3, 4: 3}, 2, 6, 5.0, seconds=2, dist=DIST)
    assert plan.objective <= cost + 1e-6
    assert sorted(c for r in plan.routes.values() for c in r) == [1, 2, 3, 4]


@pytest.mark.skipif(AMPL_OK, reason="AMPL starts here, so the failure path is not reached")
def test_missing_ampl_gives_a_pointer_not_a_traceback():
    with pytest.raises(RuntimeError, match="AMPL is not usable"):
        A.AMPLSolver().solve(problem())


# --- CLI guard: sea lanes need an explicit flag, and no AMPL is started ----------------------------------------
def _scenario(world):
    a = {"assumption": True}
    return {"paper": {"id": "t"}, "problem": {"class": ["CVRP"]}, "world": world,
            "fleet": [{"cls": "psv", "count": {"value": 2, **a}, "capacity": {"value": 6, **a},
                       "speed_mps": {"value": 5, **a}, "domain": "sea"}],
            "instance": {"base": {"name": "b", "lon": 10.0, "lat": 59.0, **a},
                         "stops": [{"name": f"s{k}", "lon": 10.0 + 0.1 * k, "lat": 59.1, "demand": {"value": 3, **a},
                                    **a} for k in (1, 2)]}}


def test_cli_refuses_a_world_without_great_circle(tmp_path, capsys):
    path = tmp_path / "scenario.yaml"
    path.write_text(yaml.safe_dump(_scenario("oslofjord")))
    assert A.main(["--scenario", str(path), "--out", str(tmp_path / "o")]) == 2
    assert "sea lanes" in capsys.readouterr().err
    assert not (tmp_path / "o" / "plan.json").exists()


def test_problem_from_scenario_mirrors_pipeline_nodes_and_demand():
    p = A.problem_from_scenario(_scenario("none"))
    assert len(p.nodes) == 3 and p.demand == {1: 3.0, 2: 3.0}
    assert p.fleet[0]["count"] == 2 and p.fleet[0]["capacity"] == 6.0
    assert p.dist_m.shape == (3, 3)


# --- tools/ampl_mcp (needs the mcp package) ---------------------------------------------------------------------
def _server():
    pytest.importorskip("mcp")
    spec = importlib.util.spec_from_file_location("ampl_mcp_server", ROOT / "tools/ampl_mcp/server.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_mcp_server_imports_and_exposes_the_five_tools():
    s = _server()
    for name in ("solve_model", "get_variable", "get_duals", "run_ampl", "list_models"):
        assert callable(getattr(s, name))


@pytest.mark.parametrize("bad", ['shell "ls";', "! ls;", "cd /tmp;", "remove x;", 'display x > "f";',
                                 "include a.mod;", "write bx;", "data foo.dat;"])
def test_mcp_screen_rejects_unsafe_statements(bad):
    s = _server()
    with pytest.raises(ValueError):
        s.screen(bad)


def test_mcp_screen_allows_normal_ampl():
    s = _server()
    s.screen("option solver highs; solve; display total_distance; let cap := 7; display x != 3;")


def test_mcp_paths_must_sit_under_roots(tmp_path, monkeypatch):
    s = _server()
    root = tmp_path / "models"
    root.mkdir()
    (root / "m.mod").write_text("set A;")
    monkeypatch.setenv("AMPL_MCP_ROOTS", str(root))
    assert s._inside_roots("m.mod") == (root / "m.mod").resolve()
    with pytest.raises(PermissionError):
        s._inside_roots(str(tmp_path / "elsewhere.mod"), must_exist=False)


# --- solve() flow with a fake AMPL (no binary needed): arc parsing, status mapping, guards -------------------
class _FakeVar:
    def __init__(self, rows):
        self.rows = rows

    def get_values(self):
        import pandas as pd
        return pd.DataFrame(self.rows, columns=["index0", "index1", "x.val"])


class _FakeObj:
    def __init__(self, v):
        self.v = v

    def value(self):
        return self.v


class _FakeAMPL:
    def __init__(self, used, objective, result):
        self.used, self.objective, self._result = used, objective, result
        self.options, self.data_text, self.solve_result = {}, "", "?"

    def read(self, path):
        assert str(path).endswith("cvrp.mod")

    def read_data(self, path):
        self.data_text = open(path).read()

    def set_option(self, k, v):
        self.options[k] = v

    def solve(self, verbose=False):
        self.solve_result = self._result

    def get_variable(self, name):
        assert name == "x"
        rows = [(i, j, 1.0) for i in range(5) for j in range(5) if (i, j) in self.used]
        rows.append((1, 3, 0.0))          # an unused arc at value 0 must be ignored
        return _FakeVar(rows)

    def get_objective(self, name):
        assert name == "total_distance"
        return _FakeObj(self.objective)


USED = {(0, 1), (1, 2), (2, 0), (0, 3), (3, 4), (4, 0)}


def _fake(monkeypatch, used=USED, objective=28.0, result="solved"):
    fake = _FakeAMPL(used, objective, result)
    monkeypatch.setattr(A, "_start_ampl", lambda: fake)
    return fake


def test_solve_parses_arcs_and_reports_optimal(monkeypatch):
    fake = _fake(monkeypatch)
    plan = A.AMPLSolver().solve(problem(), seconds=5, seed=3)
    assert plan.routes == {"PSV-1": [1, 2], "PSV-2": [3, 4]}
    assert plan.objective == pytest.approx(28.0) and plan.bound == pytest.approx(28.0)
    assert plan.status == "optimal" and plan.solver == "ampl/highs"
    assert fake.options["solver"] == "highs"
    assert fake.options["highs_options"] == "time_limit=5.0 random_seed=3"
    assert "set NODES := 0 1 2 3 4;" in fake.data_text


def test_solve_time_limit_has_no_bound(monkeypatch):
    _fake(monkeypatch, result="limit")
    plan = A.AMPLSolver().solve(problem(), seconds=2)
    assert plan.status == "time_limit" and plan.bound is None and plan.routes["PSV-1"] == [1, 2]


def test_solve_refuses_a_failed_result(monkeypatch):
    _fake(monkeypatch, result="infeasible")
    with pytest.raises(RuntimeError, match="infeasible"):
        A.AMPLSolver().solve(problem())


def test_solve_refuses_an_objective_that_does_not_match_the_arcs(monkeypatch):
    _fake(monkeypatch, objective=99.0)
    with pytest.raises(RuntimeError, match="does not match"):
        A.AMPLSolver().solve(problem())


def test_solve_refuses_a_plan_that_misses_a_client(monkeypatch):
    _fake(monkeypatch, used={(0, 1), (1, 0), (0, 2), (2, 3), (3, 0)}, objective=0.0)
    with pytest.raises(RuntimeError, match="plan check"):
        A.AMPLSolver().solve(problem())
