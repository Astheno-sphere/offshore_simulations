"""AMPL Studio core: no AMPL needed except the one solve test, which skips when AMPL is not found."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "ampl_studio"))
import core  # noqa: E402

TOY = "var x >= 0, <= 3; var y >= 0; maximize z: 3*x + 2*y; s.t. a: x + y <= 4; s.t. b: x + 3*y <= 6;"


def test_roots_default_and_env(monkeypatch, tmp_path):
    monkeypatch.delenv("AMPL_STUDIO_ROOTS", raising=False)
    assert any(r.name == "papers" for r in core.allowed_roots())
    monkeypatch.setenv("AMPL_STUDIO_ROOTS", f"{tmp_path}")
    assert core.allowed_roots() == [tmp_path.resolve()]


def test_inside_roots(tmp_path):
    root = tmp_path / "models"
    root.mkdir()
    (root / "a.mod").write_text(TOY)
    assert core.inside_roots(root / "a.mod", [root.resolve()]).name == "a.mod"
    with pytest.raises(PermissionError):
        core.inside_roots(tmp_path / "other.mod", [root.resolve()], must_exist=False)
    with pytest.raises(PermissionError):
        core.inside_roots(root / ".." / "x.mod", [root.resolve()], must_exist=False)
    with pytest.raises(FileNotFoundError):
        core.inside_roots(root / "missing.mod", [root.resolve()])


def test_list_models_and_read_checked(tmp_path):
    (tmp_path / "a.mod").write_text(TOY)
    (tmp_path / "b.txt").write_text("x")
    (tmp_path / "bad.mod").write_text("shell 'dir';")
    roots = [tmp_path.resolve()]
    assert [p.name for p in core.list_models(roots)] == ["a.mod", "bad.mod"]
    assert core.read_checked(tmp_path / "a.mod", roots) == TOY
    with pytest.raises(ValueError):
        core.read_checked(tmp_path / "bad.mod", roots)


@pytest.mark.parametrize("bad", ["shell 'dir';", "cd /;", "remove x;", "!dir", "display x > 'f.txt';",
                                 "include a.mod;", "x: 1 | 2;", "model other.mod;", "write bfoo;"])
def test_screen_rejects(bad):
    with pytest.raises(ValueError):
        core.screen(bad)


def test_screen_accepts_model_and_comments():
    core.screen(TOY)
    core.screen("param n; # shell is only a comment\ndata;\nparam n := 3;")
    core.screen("var x; s.t. c: x != 1 or x >= 0;")
    core.screen("model a.mod;\nsolve;", script=True)


def test_script_files_checked(tmp_path):
    root = tmp_path.resolve()
    (root / "a.mod").write_text(TOY)
    core.check_script_files("model a.mod;", root, [root])
    with pytest.raises(PermissionError):
        core.check_script_files("model ../outside.mod;", root, [root])


def test_probe_solvers_from_fake_dir(tmp_path):
    for n in ("ampl", "highs", "cbc", "ipopt", "gecode", "notasolver"):
        (tmp_path / f"{n}.exe").write_text("")
    groups = core.probe_solvers(tmp_path)
    assert groups == {"LP/MIP": ["highs", "cbc"], "NLP/MINLP": ["ipopt"], "CP": ["gecode"]}
    assert core.all_solvers(groups) == ["highs", "cbc", "ipopt", "gecode"]
    assert core.probe_solvers(None) == {}
    assert core.probe_solvers(tmp_path / "empty") == {}


def test_find_ampl_dir_env(monkeypatch, tmp_path):
    monkeypatch.setenv("AMPL_DIR", str(tmp_path))
    assert core.find_ampl_dir() == tmp_path


def test_build_options():
    assert core.build_options("highs", "outlev=1   timelim=60") == ("highs_options", "outlev=1 timelim=60")
    assert core.build_options("cbc", "") == ("cbc_options", "")
    assert core.build_options("cbc", "presolve") == ("cbc_options", "presolve")
    for bad in ("outlev=1; shell 'x'", "a='b'", "x=$(y)"):
        with pytest.raises(ValueError):
            core.build_options("highs", bad)
    with pytest.raises(ValueError):
        core.build_options("hi ghs; shell", "")


def test_write_log_names(tmp_path):
    p = core.write_log("my model.mod", "highs", "text", tmp_path)
    assert p.parent == tmp_path and p.name.endswith("_my_model_highs.log")
    assert p.read_text(encoding="utf-8") == "text"


def test_solve_rejects_unsafe_text_without_ampl():
    r = core.solve(solver="highs", model_text="shell 'dir';", write_logs=False)
    assert r["error"] and "ValueError" in r["error"]


@pytest.mark.skipif(core.find_ampl_dir() is None or "highs" not in core.all_solvers(
    core.probe_solvers(core.find_ampl_dir())), reason="AMPL with highs not found (AMPL runs on the laptop)")
def test_toy_lp_with_highs():
    pytest.importorskip("amplpy")
    r = core.solve(solver="highs", model_text=TOY, write_logs=False)
    assert r["error"] is None, r["error"]
    assert r["status"] == "solved"
    assert r["objectives"][0]["value"] == pytest.approx(11.0)
    df = r["variables"]
    assert dict(zip(df["variable"], df["value"])) == pytest.approx({"x": 3.0, "y": 1.0})
    assert "variable,index,value" in core.variables_csv(df)
    cmp = core.compare_table([r])
    assert list(cmp.columns) == ["solver", "status", "objective", "seconds"]
