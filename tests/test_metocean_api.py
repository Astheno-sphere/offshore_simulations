"""metocean-api backend (offsim.worlds.metocean_api), proven OFFLINE.

No test here touches the network. The library's own code runs for real against small synthetic monthly files
(tests/fixtures/metocean/, built by make_fixtures.py, modelled on what metocean-api 1.1.14 expects of the THREDDS files)
through `url_mirror`, which serves http(s) URLs from a directory and raises for anything it does not have. What this does
NOT prove: that the live NORA3 files have the structure the fixtures assume (docs/ENGINES.md, "Weather data: two backends").
"""
import importlib.util
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

xr = pytest.importorskip("xarray")
pytest.importorskip("netCDF4")

from offsim.worlds import fetch_world, metocean_api as mapi
from offsim.weather import years as wyears

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "tests/fixtures/metocean"
POINT = (3.0, 60.6)
HAVE_LIB = importlib.util.find_spec("metocean_api") is not None
needs_lib = pytest.mark.skipif(not HAVE_LIB, reason="metocean-api not installed (pip install metocean-api)")


def _gen():
    spec = importlib.util.spec_from_file_location("metocean_fixture_maker", FIX / "make_fixtures.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def mirror(tmp_path):
    """A mirror holding winters 2000/01 and 2001/02 (generated; the first is the committed set)."""
    d = tmp_path / "mirror"
    d.mkdir()
    g = _gen()
    for f in FIX.glob("*.nc"):
        shutil.copy(f, d)
    for p in ("nora3_wave", "nora3_wind"):
        for ym in ((2001, 12), (2002, 1), (2002, 2)):
            g.write_month(d, p, *ym)
    return d


def run(out, mirror_dir, years, **kw):
    kw.setdefault("isolation", "inprocess")
    kw.setdefault("retries", 0)
    kw.setdefault("backoff_s", ())
    logs = []
    man = mapi.fetch_series(out, POINT, years, "DJF", mirror=mirror_dir, log=logs.append, **kw)
    return man, logs


# --------------------------------------------------------------------------------------------- variable mapping
def test_mapping_table_is_what_the_weather_loader_reads():
    """Stored names are names years.py reads, and years._canonical turns them into the columns the engines need."""
    raw = {}
    for prod in mapi.PRODUCTS.values():
        for v in prod.vars:
            if v.years_name:
                assert v.stored in wyears._RAW, f"{v.stored} would be ignored by load_years"
                raw[v.stored] = pd.Series([1.0, 2.0])
    out = wyears._canonical(pd.DataFrame(raw))
    want = {v.years_name for p in mapi.PRODUCTS.values() for v in p.vars if v.years_name}
    assert want == {"hs_m", "tp_s", "dir_deg", "wind_mps"} == set(out.columns)


def test_mapping_table_pins_the_names_units_and_height():
    assert [(v.lib, v.stored, v.units, v.years_name) for v in mapi.PRODUCTS["nora3_wave"].vars] == [
        ("hs", "hs", "m", "hs_m"), ("tp", "tp", "s", "tp_s"), ("thq", "thq", "degrees", "dir_deg")]
    assert [(v.lib, v.stored, v.units, v.years_name) for v in mapi.PRODUCTS["nora3_wind"].vars] == [
        ("wind_speed_10m", "wind_speed", "m s-1", "wind_mps"), ("wind_direction_10m", "wind_direction", "degrees", None)]
    assert mapi.PRODUCTS["nora3_wind"].height == (10,)
    assert mapi.PRODUCTS["nora3_wave"].api == "NORA3_wave_sub" and mapi.PRODUCTS["nora3_wind"].api == "NORA3_wind_sub"


def test_wrong_variable_names_raise_instead_of_passing_through():
    with pytest.raises(mapi.VariableMappingError, match="hs_sea"):
        mapi.map_variable("nora3_wave", "hs_sea")                 # a real NORA3 variable we did not ask for
    with pytest.raises(mapi.VariableMappingError):
        mapi.map_variable("nora3_wind", "wind_speed")             # no height suffix: ambiguous, refused
    with pytest.raises(mapi.VariableMappingError):
        mapi.map_variable("nora3_wind", "wind_speed_10.0m")       # what the library emits when `height` is not passed
    with pytest.raises(mapi.VariableMappingError, match="unknown product"):
        mapi.product("nora3_atm")
    t = pd.RangeIndex(3)
    good = pd.DataFrame({"hs": [1.0, 2, 3], "tp": [8.0, 9, 10], "thq": [1.0, 2, 3]}, index=t)
    assert list(mapi.map_columns("nora3_wave", good).columns) == ["hs", "tp", "thq"]
    with pytest.raises(mapi.VariableMappingError, match="missing \\['thq'\\]"):
        mapi.map_columns("nora3_wave", good.drop(columns="thq"))
    with pytest.raises(mapi.VariableMappingError, match="unexpected \\['hs_sea'\\]"):
        mapi.map_columns("nora3_wave", good.assign(hs_sea=0.0))
    heights = pd.DataFrame({"wind_speed_10.0m": [1.0], "wind_speed_20.0m": [2.0], "wind_direction_10.0m": [3.0]})
    with pytest.raises(mapi.VariableMappingError):
        mapi.map_columns("nora3_wind", heights)


def test_currents_are_documented_but_not_fetched_here():
    assert mapi.CURRENT_MAPPING["u_eastward"] == "u" and mapi.CURRENT_MAPPING["v_northward"] == "v"
    with pytest.raises(mapi.UnsupportedProduct, match="currents"):
        mapi.product("norkyst_v3")


@needs_lib
def test_requested_variables_exist_in_the_installed_library():
    """A library upgrade that renames a variable or product fails here, not in a 24-winter run."""
    from metocean_api.ts.internal import products as lib
    for key, prod in mapi.PRODUCTS.items():
        lp = lib.find_product(prod.api)
        assert set(prod.request_vars) <= set(lp.get_default_variables()), key
        assert lp.name == prod.api


@needs_lib
def test_library_columns_on_fixtures_match_the_table(tmp_path, mirror):
    """The library's real code path, fed fixtures: the DataFrame columns are exactly the table's `lib` names."""
    for key, prod in mapi.PRODUCTS.items():
        unit = mapi.Unit(key, 2000, 12)
        with mapi.url_mirror(mirror):
            df, lon, lat, urls, _ = mapi.fetch_frame(unit, POINT, tmp_path / "w")
        assert list(df.columns) == [v.lib for v in prod.vars], key
        assert (lon, lat) == POINT and len(df) == 744 and urls[0].startswith("https://thredds.met.no/")
    # without `height` the library flattens every height: this is why the wind request pins height=[10]
    from metocean_api import ts
    t = ts.TimeSeries(lon=POINT[0], lat=POINT[1], start_time="2000-12-01", end_time="2000-12-31",
                      variable=["wind_speed"], product="NORA3_wind_sub", datafile="x.csv")
    old = Path.cwd()
    import os
    os.chdir(tmp_path)
    try:
        with mapi.url_mirror(mirror):
            t.import_data(save_csv=False)
    finally:
        os.chdir(old)
    assert sorted(t.data.columns) == ["wind_speed_10.0m", "wind_speed_20.0m", "wind_speed_50.0m"]


def test_url_mirror_never_falls_through_to_the_network(tmp_path):
    with mapi.url_mirror(tmp_path):
        with pytest.raises(FileNotFoundError, match="mirror"):
            xr.open_dataset("https://thredds.met.no/thredds/dodsC/anything.nc")
    assert xr.open_dataset.__module__.startswith("xarray")        # patch removed again


# ------------------------------------------------------------------------------------------------ units / parsing
def test_24_winters_are_144_units_and_wrap_the_new_year():
    units = mapi.month_units(list(range(2000, 2024)), "DJF")
    assert len(units) == 24 * 3 * 2 == 144
    assert (units[0].ym, units[-1].ym) == ("200012", "202402")
    assert {u.product for u in units} == {"nora3_wave", "nora3_wind"}
    u = mapi.Unit("nora3_wave", 2001, 2)
    assert (u.start, u.end, u.filename, u.key) == ("2001-02-01", "2001-02-28", "pt_nora3_wave_200102.nc", "nora3_wave:200102")
    assert (mapi.Unit("nora3_wave", 2000, 2).end) == "2000-02-29"
    assert len(mapi.month_units([2010], None)) == 12 * 2             # all-year season


def test_parsers():
    assert mapi.parse_years("2000-2003") == [2000, 2001, 2002, 2003]
    assert mapi.parse_years("2001,2005,2003-2004") == [2001, 2003, 2004, 2005]
    for bad in ("2003-2000", "20x0", ""):
        with pytest.raises(ValueError):
            mapi.parse_years(bad)
    assert mapi.parse_point("3.0,60.6") == (3.0, 60.6)
    with pytest.raises(ValueError, match="lon,lat"):
        mapi.parse_point("60.6;3.0")
    with pytest.raises(ValueError, match="out of range"):
        mapi.parse_point("60.6,200")


# ------------------------------------------------------------------------------------------------------ validation
def _frame(unit, **over):
    idx = unit.expected_index()
    d = {v.stored: np.full(len(idx), (v.lo + v.hi) / 4) for v in mapi.PRODUCTS[unit.product].vars}
    d.update(over)
    return pd.DataFrame(d, index=idx)


def test_validate_frame_refuses_gaps_nan_range_and_duplicates():
    u = mapi.Unit("nora3_wave", 2001, 1)
    mapi.validate_frame(u, _frame(u))
    with pytest.raises(mapi.DataValidationError, match="expected 744 hourly steps.*1 missing"):
        mapi.validate_frame(u, _frame(u).drop(_frame(u).index[10]))
    f = _frame(u)
    f.iloc[5, 0] = np.nan
    with pytest.raises(mapi.DataValidationError, match="NaN"):
        mapi.validate_frame(u, f)
    with pytest.raises(mapi.DataValidationError, match="outside plausible"):
        mapi.validate_frame(u, _frame(u, hs=np.full(744, 9.969e36)))        # the netCDF default fill value
    dup = pd.concat([_frame(u), _frame(u).iloc[:1]])
    with pytest.raises(mapi.DataValidationError, match="duplicate"):
        mapi.validate_frame(u, dup)


# ------------------------------------------------------- end to end on fixtures, and the shape weather/ receives
def test_fetch_one_winter_reaches_load_years_in_the_expected_shape(tmp_path, mirror):
    out = tmp_path / "pt"
    man, logs = run(out, mirror, [2000])
    assert man["summary"] == {"expected": 6, "ok": 6, "failed": 0, "pending": 0, "complete": True}
    assert sorted(p.name for p in out.glob("pt_*.nc")) == sorted(u.filename for u in mapi.month_units([2000], "DJF"))
    assert not list(out.glob("*.tmp")) and not (out / ".work").exists()
    ws = wyears.load_years(out, POINT, [2000], season="DJF")
    assert len(ws) == 1 and ws[0].year == 2000 and ws[0].source == "NORA3 DJF 2000/01"
    df = ws[0].df
    assert list(df.columns) == ["t", "hs_m", "wind_mps", "tp_s", "dir_deg"]
    assert len(df) == (31 + 31 + 28) * 24 and df["t"].iloc[0] == 0 and np.all(np.diff(df["t"]) == 3600)
    assert not df.isna().any().any()
    # values: the centre cell, 10 m height, hour 0 of Dec 2000, as the fixture generator defines them
    g = _gen()
    hs0 = float(g.wave_file(2000, 12)["hs"].isel(time=0, rlat=1, rlon=1))
    ws0 = float(g.wind_file(2000, 12)["wind_speed"].isel(time=0, height=0, y=1, x=1))
    assert df["hs_m"].iloc[0] == pytest.approx(hs0, abs=0.006)
    assert df["wind_mps"].iloc[0] == pytest.approx(ws0, abs=0.006)
    ws20 = float(g.wind_file(2000, 12)["wind_speed"].isel(time=0, height=1, y=1, x=1))
    assert abs(df["wind_mps"].iloc[0] - ws20) > 0.5, "20 m wind was read instead of 10 m"
    # the file carries provenance
    with xr.open_dataset(out / "pt_nora3_wind_200012.nc") as ds:
        assert ds.attrs["licence"].startswith("CC BY 4.0") and ds.attrs["backend"] == "metocean-api"
        assert ds["wind_speed"].attrs["source_column"] == "wind_speed_10m"
        assert float(ds["lon"][0]) == 3.0 and float(ds["lat"][0]) == 60.6


def test_fetch_world_dir_layout_is_what_a_scenario_points_at(tmp_path, mirror):
    out = tmp_path / "metocean_point"
    run(out, mirror, [2000], products=("nora3_wave", "nora3_wind"))
    man = json.loads((out / "manifest.json").read_text())
    assert man["backend"] == "metocean-api" and man["point"] == {"lon": 3.0, "lat": 60.6} and man["live_checked"] is False
    e = man["units"]["nora3_wave:200012"]
    assert e["status"] == "ok" and e["rows"] == 744 and e["dist_km"] == 0.0 and e["attempts"] == 1


# ---------------------------------------------------------------------------------------------------------- resume
class Spy:
    def __init__(self, monkeypatch, die_on=None):
        self.calls = []
        self.die_on = die_on
        real = mapi.fetch_frame

        def wrapped(unit, point, workdir):
            self.calls.append(unit.key)
            if self.die_on and len(self.calls) == self.die_on:
                raise KeyboardInterrupt("simulated kill -INT")
            return real(unit, point, workdir)
        monkeypatch.setattr(mapi, "fetch_frame", wrapped)


@needs_lib
def test_resume_skips_what_exists_and_fetches_only_what_is_missing(tmp_path, mirror, monkeypatch):
    out = tmp_path / "pt"
    spy = Spy(monkeypatch)
    run(out, mirror, [2000])
    assert len(spy.calls) == 6
    spy.calls.clear()
    man, logs = run(out, mirror, [2000, 2001])                       # 12 expected, 6 on disk
    assert sorted(spy.calls) == sorted(u.key for u in mapi.month_units([2001], "DJF")), "re-downloaded something it had"
    assert any("RESUMING: 6/12" in l for l in logs) and man["summary"]["complete"]
    spy.calls.clear()
    man, logs = run(out, mirror, [2000, 2001])                       # everything present: no request at all
    assert spy.calls == [] and any("RESUMING: 12/12" in l and "0 to fetch" in l for l in logs)
    # damage: one file deleted, one truncated, one left half-written by a kill
    (out / "pt_nora3_wind_200101.nc").unlink()
    bad = out / "pt_nora3_wave_200201.nc"
    bad.write_bytes(bad.read_bytes()[:500])
    (out / "pt_nora3_wave_200012.nc.tmp").write_bytes(b"partial")
    spy.calls.clear()
    man, logs = run(out, mirror, [2000, 2001])
    assert sorted(spy.calls) == ["nora3_wave:200201", "nora3_wind:200101"]
    assert (out / "pt_nora3_wave_200201.nc.bad").exists() and not list(out.glob("*.tmp"))
    assert man["summary"]["complete"] and wyears.load_years(out, POINT, [2000, 2001], season="DJF")


@needs_lib
def test_a_killed_run_keeps_every_finished_unit(tmp_path, mirror, monkeypatch):
    out = tmp_path / "pt"
    spy = Spy(monkeypatch, die_on=4)
    with pytest.raises(KeyboardInterrupt):
        run(out, mirror, [2000])
    assert len(list(out.glob("pt_*.nc"))) == 3
    man = json.loads((out / "manifest.json").read_text())                # written after every unit
    assert sum(1 for e in man["units"].values() if e["status"] == "ok") == 3
    monkeypatch.undo()
    spy2 = Spy(monkeypatch)
    man, logs = run(out, mirror, [2000])
    assert len(spy2.calls) == 3 and man["summary"]["complete"] and any("RESUMING: 3/6" in l for l in logs)


def test_resume_refuses_a_different_point_in_the_same_directory(tmp_path, mirror):
    out = tmp_path / "pt"
    run(out, mirror, [2000])
    with pytest.raises(mapi.PointMismatch, match="use another --out"):
        mapi.fetch_series(out, (3.1, 60.6), [2000], "DJF", mirror=mirror, isolation="inprocess", log=lambda s: None)


# -------------------------------------------------------------------------------------------------------- failures
@needs_lib
def test_a_failed_request_is_recorded_in_the_manifest_not_swallowed(tmp_path, mirror):
    out = tmp_path / "pt"
    (mirror / "200101_NORA3wave_sub_time_unlimited.nc").unlink()        # the server "does not have" this month
    man, logs = run(out, mirror, [2000])
    assert man["summary"] == {"expected": 6, "ok": 5, "failed": 1, "pending": 0, "complete": False}
    e = man["units"]["nora3_wave:200101"]
    assert e["status"] == "failed" and "FileNotFoundError" in e["error"] and e["attempts"] == 1
    assert any("nora3_wave:200101" in x["stage"] and "FileNotFoundError" in x["error"] for x in man["errors"])
    assert any("FAILED" in l for l in logs) and any("INCOMPLETE" in l and "resume" in l for l in logs)
    on_disk = json.loads((out / "manifest.json").read_text())
    assert on_disk["units"]["nora3_wave:200101"]["status"] == "failed"
    # server comes back: only the failed unit is fetched, attempts accumulate, the error clears
    shutil.copy(FIX / "200101_NORA3wave_sub_time_unlimited.nc", mirror)
    man, _ = run(out, mirror, [2000])
    assert man["summary"]["complete"] and man["errors"] == []
    assert man["units"]["nora3_wave:200101"]["status"] == "ok" and man["units"]["nora3_wave:200101"]["attempts"] == 2


@needs_lib
def test_bad_data_is_a_permanent_failure_and_is_not_retried(tmp_path, mirror):
    ds = xr.open_dataset(mirror / "200101_NORA3wave_sub_time_unlimited.nc").load()
    ds["hs"][:, :, :] = 9.969e36
    ds.close()
    ds.to_netcdf(mirror / "200101_NORA3wave_sub_time_unlimited.nc")
    sleeps = []
    man, _ = run(tmp_path / "pt", mirror, [2000], retries=3, backoff_s=(1.0,), sleep=sleeps.append)
    e = man["units"]["nora3_wave:200101"]
    assert e["status"] == "failed" and e["permanent"] is True and e["attempts"] == 1 and "outside plausible" in e["error"]
    assert sleeps == []


def _fail_runner(exc):
    def r(unit, timeout):
        raise exc
    return r


def test_transient_failure_retries_then_gives_up(tmp_path):
    sleeps = []
    man, logs = run(tmp_path / "pt", None, [2000], runner=_fail_runner(mapi.UnitTimeout("no result within 600 s")),
                    retries=2, backoff_s=(15.0, 60.0), sleep=sleeps.append, max_consecutive_failures=99)
    assert sleeps[:2] == [15.0, 60.0] and all(e["attempts"] == 3 for e in man["units"].values())
    assert man["summary"]["failed"] == 6 and not man["summary"]["complete"]


def test_circuit_breaker_stops_a_run_against_a_dead_server(tmp_path):
    calls = []

    def r(unit, timeout):
        calls.append(unit.key)
        raise mapi.UnitTimeout("dead")
    man, logs = run(tmp_path / "pt", None, list(range(2000, 2024)), runner=r, max_consecutive_failures=3)
    assert len(calls) == 3 and man["stopped"] == "consecutive_failures"
    assert man["summary"]["failed"] == 3 and man["summary"]["pending"] == 141
    assert any("STOP" in l and "again to continue" in l for l in logs)


def test_runtime_limit_stops_cleanly_before_starting_another_unit(tmp_path):
    man, logs = run(tmp_path / "pt", None, [2000], runner=_fail_runner(AssertionError("must not run")), max_runtime_s=0)
    assert man["stopped"] == "deadline" and man["summary"]["pending"] == 6


# ------------------------------------------------------------------------------ hard per-request timeout (subprocess)
def test_hard_timeout_kills_a_hung_worker(tmp_path):
    t0 = time.time()
    with pytest.raises(mapi.UnitTimeout, match="worker killed"):
        mapi.run_isolated([sys.executable, "-c", "import time; time.sleep(120)"], timeout_s=1.5, cwd=tmp_path)
    assert time.time() - t0 < 20


def test_worker_results_are_typed(tmp_path):
    ok = mapi.run_isolated([sys.executable, "-c", "print('spinner\\b-\\nRESULT {\"rows\": 3}')"], 20, tmp_path)
    assert ok == {"rows": 3}
    with pytest.raises(mapi.DataValidationError, match="boom"):
        mapi.run_isolated([sys.executable, "-c", "print('RESULT {\"error\": \"DataValidationError\", \"message\": \"boom\"}'); raise SystemExit(3)"], 20, tmp_path)
    with pytest.raises(mapi.UnitFailed, match="exited 1"):
        mapi.run_isolated([sys.executable, "-c", "import sys; sys.stderr.write('network is unreachable'); sys.exit(1)"], 20, tmp_path)


@needs_lib
def test_subprocess_isolation_end_to_end_on_fixtures(tmp_path, mirror):
    """The default path: each unit in its own killed-on-timeout child, library run for real, files valid."""
    out = tmp_path / "pt"
    man = mapi.fetch_series(out, POINT, [2000], "DJF", ("nora3_wave",), mirror=mirror, unit_timeout_s=120, log=lambda s: None)
    assert man["summary"]["complete"] and len(list(out.glob("pt_nora3_wave_*.nc"))) == 3


# ----------------------------------------------------------------------------------- GPL rule: metocean-stats
def test_importing_the_backend_never_loads_the_gpl_dependency():
    code = ("import sys, offsim.worlds.metocean_api as m; "
            "bad = [k for k in sys.modules if k.split('.')[0] in ('metocean_stats', 'lmoments3')]; "
            "assert not bad, bad; print('clean')")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert out.returncode == 0 and "clean" in out.stdout, out.stderr[-400:]


def test_metocean_stats_is_imported_only_inside_the_child_worker():
    import ast
    tree = ast.parse((ROOT / "offsim/worlds/metocean_api.py").read_text())
    where = []
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.Module)):
            for node in (fn.body if isinstance(fn, ast.FunctionDef) else []):
                for sub in ast.walk(node):
                    if isinstance(sub, ast.ImportFrom) and (sub.module or "").split(".")[0] in mapi.GPL_MODULES:
                        where.append(fn.name)
                    if isinstance(sub, ast.Import) and any(a.name.split(".")[0] in mapi.GPL_MODULES for a in sub.names):
                        where.append(fn.name)
    top = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    assert not any((getattr(n, "module", "") or "").split(".")[0] in mapi.GPL_MODULES or
                   any(a.name.split(".")[0] in mapi.GPL_MODULES for a in getattr(n, "names", [])) for n in top)
    assert set(where) == {"_stats_worker_main"}, where


@pytest.mark.skipif(importlib.util.find_spec("metocean_stats") is None, reason="metocean-stats not installed")
def test_metocean_stats_runs_in_a_child_process_on_the_fetched_series(tmp_path, mirror):
    out = tmp_path / "pt"
    run(out, mirror, [2000]) if HAVE_LIB else pytest.skip("metocean-api not installed")
    res = mapi.run_stats(out, [2000], "DJF", thresholds=(2.5, 4.5), op_hours=(6.0,))
    w = res["winters"]["2000"]["hs<2.5_op6h"]
    assert set(w) == {"mean", "p10", "p50", "p90"} and w["p10"] <= w["p50"] <= w["p90"] and w["mean"] > 0.25
    assert not any(k.split(".")[0] in ("metocean_stats", "lmoments3") for k in sys.modules), "GPL dependency was imported in-process"
    assert res["tool"] == "metocean-stats" and (out / "stats_metocean_stats.json").exists()


# ------------------------------------------------------------------- the existing fetch path is unchanged
def _stub_world(monkeypatch, calls):
    monkeypatch.setattr(fetch_world, "land_from_osm", lambda *a, **k: calls.append("land") or {"coastline_ways": 0})
    monkeypatch.setattr(fetch_world, "sodir_layers", lambda *a, **k: calls.append("sodir") or {})
    monkeypatch.setattr(fetch_world, "metocean", lambda bbox, out, start, hours, datasets=None: calls.append(("legacy", start, hours, tuple(datasets))) or [])


def test_default_backend_is_legacy_and_the_legacy_call_is_unchanged(tmp_path, monkeypatch):
    import inspect
    sig = inspect.signature(fetch_world.fetch)
    assert sig.parameters["metocean_backend"].default == "legacy" and sig.parameters["metocean_api"].default is None
    assert list(sig.parameters)[:3] == ["world", "out", "metocean_args"]          # positional order kept
    assert fetch_world.METOCEAN_DATASETS == ("nora3_wind", "nora3_wave", "norkyst_v3")
    calls = []
    _stub_world(monkeypatch, calls)
    monkeypatch.setattr(mapi, "fetch_series", lambda *a, **k: pytest.fail("new backend must not run by default"))
    fetch_world.fetch("oslofjord", tmp_path / "w", ("2024-01-10T00:00", "48"))
    assert ("legacy", "2024-01-10T00:00", 48, fetch_world.METOCEAN_DATASETS) in calls
    man = json.loads((tmp_path / "w/manifest.json").read_text())
    assert any("NORA3 wind/wave" in s["name"] for s in man["sources"]) and not (tmp_path / "w/metocean_point").exists()


def test_new_backend_is_offered_beside_it_and_recorded_in_the_world_manifest(tmp_path, monkeypatch):
    calls = []
    _stub_world(monkeypatch, calls)

    def fake(out, point, years, season, **kw):
        calls.append(("api", Path(out).name, point, years, season, kw.get("max_runtime_s")))
        return {"point": {"lon": point[0], "lat": point[1]}, "years": years, "season": season, "stopped": None, "live_checked": False,
                "summary": {"expected": 6, "ok": 5, "failed": 1, "pending": 0, "complete": False},
                "errors": [{"stage": "metocean-api nora3_wave:200101", "error": "UnitTimeout: x", "seconds": 0}]}
    monkeypatch.setattr(mapi, "fetch_series", fake)
    fetch_world.fetch("oslofjord", tmp_path / "w", None, metocean_backend="metocean-api",
                      metocean_api={"point": POINT, "years": [2000], "season": "DJF", "max_runtime_s": 7200})
    assert ("api", "metocean_point", POINT, [2000], "DJF", 7200) in calls and not any(isinstance(c, tuple) and c[0] == "legacy" for c in calls)
    man = json.loads((tmp_path / "w/manifest.json").read_text())
    src = [s for s in man["sources"] if s.get("backend") == "metocean-api"][0]
    assert src["units"]["failed"] == 1 and src["dir"] == "metocean_point/" and src["licence"].startswith("CC BY 4.0")
    assert man["errors"] and man["errors"][0]["stage"] == "metocean-api nora3_wave:200101"


def test_backend_options_cannot_be_mixed(tmp_path, monkeypatch):
    _stub_world(monkeypatch, [])
    with pytest.raises(ValueError, match="legacy backend"):
        fetch_world.fetch("oslofjord", tmp_path / "a", ("2024-01-10T00:00", "48"), metocean_backend="metocean-api", metocean_api={"point": POINT})
    with pytest.raises(ValueError, match="metocean_backend='metocean-api'"):
        fetch_world.fetch("oslofjord", tmp_path / "b", None, metocean_api={"point": POINT})
    with pytest.raises(ValueError, match="must be"):
        fetch_world.fetch("oslofjord", tmp_path / "c", None, metocean_backend="nope")


def test_cli_flags_and_defaults():
    out = subprocess.run([sys.executable, "-m", "offsim.worlds.fetch_world", "--help"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    for flag in ("--metocean ", "--metocean-datasets", "--metocean-backend", "--metocean-point", "--metocean-years", "--metocean-season",
                 "--metocean-max-minutes"):
        assert flag in out, flag
    assert "legacy (default)" in out
    h = subprocess.run([sys.executable, "-m", "offsim.worlds.metocean_api", "fetch", "--help"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    for flag in ("--point", "--years", "--season", "--unit-timeout", "--max-runtime-min", "--mirror", "--world", "--out"):
        assert flag in h, flag


def test_the_documented_bergen_command_parses():
    """The exact command in docs/ENGINES.md and the report: its arguments are valid and expand to 144 units."""
    pt = mapi.parse_point("3.0,60.6")
    yrs = mapi.parse_years("2000-2023")
    assert (pt, yrs[0], yrs[-1], len(mapi.month_units(yrs, "DJF"))) == ((3.0, 60.6), 2000, 2023, 144)
    assert mapi.default_out("bergen-ncs") == ROOT / "data/worlds/bergen-ncs/metocean_point"
    assert (ROOT / "offsim/worlds/bergen-ncs.yaml").exists()
    bbox = fetch_world.yaml.safe_load((ROOT / "offsim/worlds/bergen-ncs.yaml").read_text())["bbox"]
    assert bbox[0] <= pt[0] <= bbox[2] and bbox[1] <= pt[1] <= bbox[3], "documented point lies outside the bergen-ncs bbox"
