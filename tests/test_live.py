"""Live-check: probes run offline with fake fetch functions. Each probe must report ok on a realistic payload and
ok False (never an exception) on a timeout, an HTTP error or a garbage body. Secrets stay out of every result."""
import json
import subprocess
from pathlib import Path

import pytest
import yaml

from conftest import ROOT
from offsim.live import cli, probes as P
from offsim.live.probes import Resp

DDS_NORA3_WIND = """Dataset {
    Float64 time[time = 2];
    Float32 wind_speed[time = 2][y = 3][x = 3];
    Float32 wind_direction[time = 2][y = 3][x = 3];
    Float64 longitude[y = 3][x = 3];
    Grid {
     ARRAY:
        Float32 height[height = 1];
     MAPS:
        Float64 height[height = 1];
    } height_grid;
} arome3kmwind_1hr_202401.nc;
"""
DDS_NORA3_WAVE = "Dataset {\n    Float32 hs[time = 2][rlat = 3][rlon = 3];\n    Float32 tp[time = 2][rlat = 3][rlon = 3];\n    Float32 thq[time = 2][rlat = 3][rlon = 3];\n} wave.nc;\n"
DDS_NORKYST = "Dataset {\n    Float32 u_eastward[time = 2][depth = 4][Y = 3][X = 3];\n    Float32 v_northward[time = 2][depth = 4][Y = 3][X = 3];\n} norkyst800.nc;\n"
ATOM_OK = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
  <title>ArXiv Query</title><id>http://arxiv.org/api/q</id><updated>2026-11-01T00:00:00Z</updated>
  <opensearch:totalResults>1</opensearch:totalResults>
  <entry><id>http://arxiv.org/abs/2601.01234v1</id><title>Offshore routing</title><summary>x</summary>
    <published>2026-01-05T00:00:00Z</published><author><name>A. Author</name></author></entry>
</feed>"""
ATOM_ERROR = ATOM_OK.replace("http://arxiv.org/abs/2601.01234v1", "http://arxiv.org/api/errors").replace(
    "Offshore routing", "Incorrect query")

SECRET_UUID = "UUID-SECRET-1234"
SECRET_BW = "BW-SECRET-5678"
SECRET_MAIL = "someone-secret@example.org"


def j(obj, status=200):
    return Resp(status, {"content-type": "application/json"}, json.dumps(obj).encode())


def head(size=1234567, status=200, **extra):
    h = {"content-length": str(size), "content-type": "application/octet-stream", "last-modified": "Tue, 10 Nov 2026"}
    if size is None:
        h.pop("content-length")
    h.update(extra)
    return Resp(status, h, b"")


def text(body, status=200):
    return Resp(status, {}, body.encode())


def fake(route):
    """route(url, method) -> Resp | exception instance. Records every call."""
    calls = []

    def f(url, method="GET", data=None, headers=None, timeout=60):
        calls.append({"url": url, "method": method, "data": data, "headers": headers or {}})
        out = route(url, method)
        if isinstance(out, BaseException):
            raise out
        return out
    f.calls = calls
    return f


def only(path_part, answer):
    """Route: answer for URLs containing path_part; anything else is an unexpected call."""
    def route(url, method):
        if path_part in url:
            return answer
        raise AssertionError(f"unrouted {method} {url}")
    return route


OVERPASS_OK = j({"version": 0.6, "generator": "Overpass API", "osm3s": {"timestamp_osm_base": "x"},
                 "elements": [{"type": "way", "id": 1}, {"type": "way", "id": 2}]})
SODIR_OK = j({"currentVersion": 11.1, "serviceDescription": "FactMaps", "layers": [{"id": 0, "name": "Fields"}],
              "tables": []})
STEDSNAVN_OK = j({"metadata": {"totaltAntallTreff": 1}, "navn": [
    {"stedsnavn": [{"skrivemåte": "Molde"}], "navneobjekttype": "by",
     "representasjonspunkt": {"nord": 62.737, "øst": 7.157}, "kommuner": [{"kommunenavn": "Molde"}]}]})
CAPS_OK = j({"uuid": "fd851873", "supportsPolygonSelection": True, "formats": [{"name": "GeoTIFF"}]})
VEHICLES_OK = j({"data": {"vehicles": [{"vehicleId": "RUT:1", "line": {"lineRef": "L1", "publicCode": "1"},
                                         "serviceJourney": {"id": "SJ1"}, "lastUpdated": "2026-11-12T10:00:00Z",
                                         "location": {"latitude": 59.91, "longitude": 10.75},
                                         "delay": "PT30S", "bearing": 90, "speed": 5.0}]}})
TOKEN_OK = j({"access_token": "eyJ-token", "expires_in": 3600, "token_type": "Bearer", "scope": "ais"})
OPENALEX_OK = j({"meta": {"count": 9}, "results": [{"id": "https://openalex.org/W1", "doi": None,
                                                    "title": "Offshore logistics", "publication_year": 2025}]})
CROSSREF_OK = j({"status": "ok", "message-type": "work-list", "message": {"items": [
    {"DOI": "10.1234/x", "title": ["Offshore logistics"], "issued": {"date-parts": [[2025, 3]]}}]}})
NVA_OK = j({"hits": [{"identifier": "abc", "entityDescription": {"mainTitle": "Offshore"}}]})


# --- registry ------------------------------------------------------------------------------------------------------

EXPECTED = {"overpass", "sodir", "nora3_wind", "nora3_wave", "norkyst", "kartverket_stedsnavn", "geonorge_dtm",
            "geofabrik", "entur_gtfs", "entur_vehicles", "barentswatch", "openalex", "crossref", "arxiv", "nva", "ampl",
            "runner"}


def test_registry_has_every_probe_and_fetch_signature():
    import inspect
    assert set(P.PROBES) == EXPECTED
    for name, fn in P.PROBES.items():
        params = inspect.signature(fn).parameters
        assert {"fetch", "timeout", "env"} <= set(params), name


# --- network probes: ok on payload -----------------------------------------------------------------------------------

def test_overpass_counts_coastline_ways():
    r = P.probe_overpass(fetch=fake(only("overpass", OVERPASS_OK)), env={})
    assert r["ok"] is True and r["status"] == "ok" and "2 coastline" in r["detail"]
    assert "elements" in r["schema"] and "elements[].type" in r["schema"]


def test_overpass_zero_ways_is_not_ok():
    r = P.probe_overpass(fetch=fake(only("overpass", j({"elements": []}))))
    assert r["ok"] is False


def test_overpass_retries_once_on_gateway_error(monkeypatch):
    # why: the probe retries once on 502/503 (Overpass 502s a good query when its
    # queue is full and answers the same query minutes later); the test must
    # prove the retry, not wait for it.
    monkeypatch.setattr(P, "OVERPASS_RETRY_S", 0)
    answers = [Resp(502, {}, b""), OVERPASS_OK]
    f = fake(lambda u, m: answers.pop(0))
    r = P.probe_overpass(fetch=f, env={})
    assert r["ok"] is True and len(f.calls) == 2


def test_sodir_lists_layers():
    r = P.probe_sodir(fetch=fake(only("FeatureServer", SODIR_OK)))
    assert r["ok"] is True and "layers" in r["schema"] and "1 layers" in r["detail"]


@pytest.mark.parametrize("probe, url_part, dds", [
    (P.probe_nora3_wind, "arome3kmwind", DDS_NORA3_WIND),
    (P.probe_nora3_wave, "NORA3wave", DDS_NORA3_WAVE),
    (P.probe_norkyst, "norkyst800", DDS_NORKYST),
])
def test_opendap_dds_variables(probe, url_part, dds):
    f = fake(only(url_part, text(dds)))
    r = probe(fetch=f)
    assert r["ok"] is True, r["detail"]
    assert f.calls[0]["url"].endswith(".nc.dds") and f.calls[0]["method"] == "GET"


def test_dds_nested_grid_and_dataset_closing_name():
    names = P.parse_dds(DDS_NORA3_WIND)
    assert "height_grid" in names and "wind_speed" in names
    assert "arome3kmwind_1hr_202401.nc" not in names          # the dataset closing line is a file name, not a variable


def test_dds_renamed_variable_fails():
    r = P.probe_norkyst(fetch=fake(only("norkyst800", text(DDS_NORKYST.replace("u_eastward", "u_east")))))
    assert r["ok"] is False and "u_eastward" in r["detail"]


def test_stedsnavn_finds_molde_with_point():
    r = P.probe_kartverket_stedsnavn(fetch=fake(only("stedsnavn", STEDSNAVN_OK)))
    assert r["ok"] is True and "navn" in r["schema"] and "navn[].representasjonspunkt" in r["schema"]


def test_geonorge_capabilities_and_uuid_override():
    f = fake(only("capabilities", CAPS_OK))
    r = P.probe_geonorge_dtm(fetch=f, env={"OFFSIM_DTM_UUID": "11111111-2222-3333-4444-555555555555"})
    assert r["ok"] is True and "supportsPolygonSelection" in r["schema"]
    assert "11111111-2222" in f.calls[0]["url"]
    assert P.probe_geonorge_dtm(fetch=fake(only("capabilities", CAPS_OK)), env={}).get("ok") is True


def test_head_probes_read_size_and_fail_without_length():
    r = P.probe_geofabrik(fetch=fake(only("geofabrik", head(1234567890))), env={})
    assert r["ok"] is True and "1235 MB" in r["detail"]
    assert r["schema"] == ["content-length", "content-type", "last-modified"]
    r2 = P.probe_entur_gtfs(fetch=fake(only("gtfs", head(None))))
    assert r2["ok"] is False and "Content-Length" in r2["detail"]


def test_entur_vehicles_sends_client_header_and_reads_fields():
    f = fake(only("realtime/v2/vehicles", VEHICLES_OK))
    r = P.probe_entur_vehicles(fetch=f, env={})
    assert r["ok"] is True and "1 vehicles" in r["detail"]
    assert f.calls[0]["headers"]["ET-Client-Name"] == P.DEFAULT_ENTUR_CLIENT
    assert "vehicles[].vehicleId" in r["schema"] and "data" in r["schema"]
    body = json.loads(f.calls[0]["data"])
    assert body["variables"]["minLat"] < body["variables"]["maxLat"]


def test_entur_client_name_from_env():
    f = fake(only("realtime/v2/vehicles", VEHICLES_OK))
    P.probe_entur_vehicles(fetch=f, env={"ENTUR_CLIENT_NAME": "acme-tracker"})
    assert f.calls[0]["headers"]["ET-Client-Name"] == "acme-tracker"


def test_entur_graphql_errors_without_data_fail():
    r = P.probe_entur_vehicles(fetch=fake(only("vehicles", j({"errors": [{"message": "bad field"}]}))), env={})
    assert r["ok"] is False and "bad field" in r["detail"]


def test_openalex_sends_mailto_and_never_prints_it():
    f = fake(only("openalex", OPENALEX_OK))
    r = P.probe_openalex(fetch=f, env={"OFFSIM_MAILTO": SECRET_MAIL})
    assert r["ok"] is True and "polite pool" in r["detail"]
    assert "mailto=" in f.calls[0]["url"]
    assert SECRET_MAIL not in json.dumps(r)


def test_openalex_429_is_reported_not_raised():
    r = P.probe_openalex(fetch=fake(only("openalex", Resp(429, {"retry-after": "60"}, b"slow down"))), env={})
    assert r["ok"] is False and "429" in r["detail"] and "anonymous pool" in r["detail"]


def test_crossref_items_and_schema():
    r = P.probe_crossref(fetch=fake(only("crossref", CROSSREF_OK)), env={})
    assert r["ok"] is True and "message.items" not in r["schema"] and "items[].DOI" in r["schema"]


def test_arxiv_entry_ok_and_error_entry_fails():
    r = P.probe_arxiv(fetch=fake(only("arxiv", text(ATOM_OK))))
    assert r["ok"] is True and "entry.title" in r["schema"] and "opensearch:totalResults" not in r["schema"] \
        and "totalResults" in r["schema"]
    e = P.probe_arxiv(fetch=fake(only("arxiv", text(ATOM_ERROR))))
    assert e["ok"] is False and "error" in e["detail"]


def test_nva_hits():
    assert P.probe_nva(fetch=fake(only("nva", NVA_OK)))["ok"] is True


# --- skipped without secrets -------------------------------------------------------------------------------------------

def test_ampl_is_skipped_without_secret():
    r = P.probe_ampl(fetch=fake(lambda u, m: pytest.fail("no call expected")), env={})
    assert r["status"] == "skipped" and r["ok"] is None and "AMPL_LICENSE_UUID" in r["detail"]


def test_barentswatch_skipped_without_id_or_secret():
    f = fake(lambda u, m: pytest.fail("no call expected"))
    assert P.probe_barentswatch(fetch=f, env={})["status"] == "skipped"
    half = P.probe_barentswatch(fetch=f, env={"BW_CLIENT_SECRET": SECRET_BW})
    assert half["status"] == "skipped" and "BW_CLIENT_ID" in half["detail"]
    nosec = P.probe_barentswatch(fetch=f, env={"BW_CLIENT_ID": "id"})
    assert nosec["status"] == "skipped" and "BW_CLIENT_SECRET" in nosec["detail"]


def test_barentswatch_token_ok_and_no_secret_in_result():
    f = fake(only("connect/token", TOKEN_OK))
    r = P.probe_barentswatch(fetch=f, env={"BW_CLIENT_ID": "cid-x", "BW_CLIENT_SECRET": SECRET_BW})
    assert r["ok"] is True and "access_token" in r["schema"]
    dumped = json.dumps(r)
    assert SECRET_BW not in dumped and "eyJ-token" not in dumped and "cid-x" not in dumped
    assert SECRET_BW in f.calls[0]["data"].decode()             # sent to the token endpoint only


def test_ampl_success_with_fake_runner():
    def proc(cmd, timeout):
        if "amplpy.modules" in cmd:
            assert SECRET_UUID in cmd                             # passed as an argument, never printed
            return 0, "", ""
        return 0, "HiGHS 1.x banner\n" + json.dumps({"result": "solved", "obj": 10.0, "x": 2.0, "y": 2.0}) + "\n", ""
    r = P.probe_ampl(env={"AMPL_LICENSE_UUID": SECRET_UUID}, _proc=proc)
    assert r["ok"] is True and "objective 10" in r["detail"] and SECRET_UUID not in json.dumps(r)


def test_ampl_timeout_message_is_redacted():
    def proc(cmd, timeout):
        raise subprocess.TimeoutExpired(cmd, timeout)                  # str() of this includes the argv
    r = P.probe_ampl(env={"AMPL_LICENSE_UUID": SECRET_UUID}, _proc=proc)
    assert r["ok"] is False and SECRET_UUID not in json.dumps(r) and "<redacted>" in r["detail"]


def test_runner_reports_python_and_libegl():
    def proc(cmd, timeout):
        if cmd[:2] == ["dpkg", "-s"]:
            return 0, "Package: libegl1\nStatus: install ok installed\n", ""
        return 1, "", "ModuleNotFoundError: No module named 'skia'"
    r = P.probe_runner(_proc=proc)
    assert r["ok"] is True and "libegl1 installed" in r["detail"] and "skia not importable" in r["detail"]


def test_runner_fails_without_dpkg():
    def proc(cmd, timeout):
        if cmd[0] == "dpkg":
            raise FileNotFoundError("dpkg")
        return 1, "", ""
    r = P.probe_runner(_proc=proc)
    assert r["ok"] is False and "dpkg unavailable" in r["detail"]


# --- failures never raise ----------------------------------------------------------------------------------------------

NETWORK = ["overpass", "sodir", "nora3_wind", "nora3_wave", "norkyst", "kartverket_stedsnavn", "geonorge_dtm",
           "geofabrik", "entur_gtfs", "entur_vehicles", "openalex", "crossref", "arxiv", "nva"]


@pytest.mark.parametrize("name", NETWORK)
@pytest.mark.parametrize("scenario", ["timeout", "http503", "garbage"])
def test_network_probe_failures_are_results(name, scenario):
    route = {"timeout": lambda u, m: TimeoutError("timed out"),
             "http503": lambda u, m: Resp(503, {}, b"maintenance"),
             "garbage": lambda u, m: Resp(200, {}, b"\x00\xff<html>not json</html>")}[scenario]
    r = P.PROBES[name](fetch=fake(lambda u, m: route(u, m)), timeout=5, env={})
    assert r["ok"] is False and r["status"] == "fail", (name, scenario, r)
    assert r["detail"]


def test_run_probe_reports_budget_overrun(monkeypatch):
    import time

    def slow(fetch=None, timeout=60, env=None):
        time.sleep(1.0)
        return P._finish("slow", "ok", time.monotonic(), "late")
    monkeypatch.setitem(P.PROBES, "slow", slow)
    r = P.run_probe("slow", budget_s=0.2)
    assert r["ok"] is False and "budget" in r["detail"]


# --- schema, merge, markdown ---------------------------------------------------------------------------------------------

def res(name, status="ok", schema=("a", "b"), last_ok="2026-11-01"):
    e = {"name": name, "ok": status == "ok", "status": status, "latency_s": 0.1, "detail": "d", "schema": list(schema),
         "checked_utc": "2026-11-12T03:00:00Z", "last_ok": last_ok}
    e["schema_hash"] = P.schema_hash(schema) if status == "ok" else None
    return e


def test_schema_diff_detects_change_only_when_both_sides_known():
    old = [res("geofabrik", schema=("content-length",)), res("sodir", schema=("layers",))]
    new = [res("geofabrik", schema=("content-length", "etag")), res("sodir", schema=("layers",)),
           res("arxiv", schema=("feed",))]
    assert P.diff_schema(old, new) == ["geofabrik"]
    assert P.schema_delta(old, new) == {"geofabrik": {"added": ["etag"], "removed": []}}
    skipped_new = [res("geofabrik", status="skipped")]
    assert P.diff_schema(old, skipped_new) == []                       # a skip has no hash: not compared
    assert P.diff_schema({"results": old}, {"results": new}) == ["geofabrik"]


def test_failed_probe_keeps_last_good_schema_so_no_false_change(tmp_path):
    prev = [res("overpass", schema=("elements",))]
    fails = P.run_all(["overpass"], fetch=fake(lambda u, m: TimeoutError("boom")), env={},
                      out_md=tmp_path / "m.md", out_json=tmp_path / "s.json")
    assert fails[0]["status"] == "fail"
    old = json.loads((tmp_path / "s.json").read_text())["results"]
    assert P.diff_schema(prev, old) == []                              # nothing to compare against yet
    # failing run again keeps the stored hash of the last good run
    good = P.run_all(["overpass"], fetch=fake(only("overpass", OVERPASS_OK)), env={}, out_md=tmp_path / "m.md",
                     out_json=tmp_path / "s.json")
    h_good = good[0]["schema_hash"]
    again = P.run_all(["overpass"], fetch=fake(lambda u, m: TimeoutError("boom")), env={},
                      out_md=tmp_path / "m.md", out_json=tmp_path / "s.json")
    assert again[0]["schema_hash"] == h_good and again[0]["last_ok"] == good[0]["last_ok"]


def test_markdown_table_has_every_probe_and_escapes_pipes():
    entries = [res("overpass"), dict(res("sodir", status="fail"), detail="a|b")]
    md = P.render_markdown(entries, "2026-11-12T03:41:00Z")
    assert md.startswith("# Live status") and "Generated 2026-11-12T03:41:00Z" in md
    assert "| Probe | OK | Latency (s) | Last ok (UTC) | Schema hash | Detail |" in md
    for n in P.PROBES:
        assert f"| {n} |" in md
    assert "| sodir | no |" in md and "a\\|b" in md


def test_placeholder_markdown_marks_everything_not_run():
    md = P.render_markdown(None)
    assert "Placeholder" in md and md.count("| not run |") == len(P.PROBES)
    assert (ROOT / "docs/LIVE_STATUS.md").read_text().startswith("# Live status")


def test_issue_body_only_when_something_is_wrong():
    ok_entries = [res("overpass")]
    assert P.issue_body(ok_entries, [], {}) == ""
    body = P.issue_body([dict(res("sodir", status="fail"), detail="HTTP 503")], ["arxiv"],
                        {"arxiv": {"added": ["x"], "removed": []}})
    assert "| sodir | HTTP 503" in body and "arxiv: added x; removed none" in body


def test_run_all_carries_unrun_probes_and_last_ok(tmp_path):
    out_md, out_json = tmp_path / "m.md", tmp_path / "s.json"
    first = P.run_all(["geofabrik", "overpass"],
                      fetch=fake(lambda u, m: head() if "geofabrik" in u else Resp(503, {}, b"")),
                      env={}, out_md=out_md, out_json=out_json)
    by = {r["name"]: r for r in first}
    assert by["geofabrik"]["ok"] is True and by["overpass"]["ok"] is False and by["sodir"]["status"] == "not run"
    second = P.run_all(["overpass"], fetch=fake(lambda u, m: Resp(503, {}, b"")), env={},
                       out_md=out_md, out_json=out_json)
    by2 = {r["name"]: r for r in second}
    assert by2["geofabrik"]["status"] == "ok"                         # not run this time: kept
    assert by2["geofabrik"]["last_ok"] == by["geofabrik"]["last_ok"]
    assert by2["overpass"]["status"] == "fail"
    assert "| geofabrik | yes |" in out_md.read_text()


def test_run_all_rejects_unknown_names(tmp_path):
    with pytest.raises(KeyError):
        P.run_all(["nope"], fetch=fake(lambda u, m: Resp(500, {}, b"")), out_md=tmp_path / "m", out_json=None)


# --- CLI --------------------------------------------------------------------------------------------------------------

def test_cli_list_and_unknown_name(capsys):
    assert cli.main(["--list"]) == 0 and "geofabrik" in capsys.readouterr().out
    assert cli.main(["--only", "nope"]) == 2


def test_cli_strict_and_issue_body(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(P, "default_fetch", fake(lambda u, m: Resp(503, {}, b"")))
    args = ["--only", "overpass", "--out", str(tmp_path / "m.md"), "--json", str(tmp_path / "s.json"),
            "--issue-body", str(tmp_path / "issue.md")]
    assert cli.main(args) == 0                                          # not strict: exit 0
    assert "HTTP 503" in (tmp_path / "issue.md").read_text()
    assert cli.main(args + ["--strict"]) == 1
    monkeypatch.setattr(P, "default_fetch", fake(only("overpass", OVERPASS_OK)))
    assert cli.main(args) == 0
    assert not (tmp_path / "issue.md").exists()                         # all green: no issue body
    assert "1 probes: 1 ok" in capsys.readouterr().out


def test_cli_skipped_probes_do_not_fail_strict(tmp_path, monkeypatch):
    monkeypatch.delenv("AMPL_LICENSE_UUID", raising=False)
    monkeypatch.delenv("BW_CLIENT_ID", raising=False)
    assert cli.main(["--only", "ampl,barentswatch", "--out", str(tmp_path / "m.md"),
                     "--json", str(tmp_path / "s.json"), "--strict"]) == 0


# --- workflow ---------------------------------------------------------------------------------------------------------

def test_workflow_parses_with_both_triggers_and_permissions():
    wf = yaml.safe_load((ROOT / ".github/workflows/live-check.yml").read_text())
    triggers = wf.get(True) or wf.get("on")
    assert "schedule" in triggers and "workflow_dispatch" in triggers
    assert "only" in triggers["workflow_dispatch"]["inputs"]
    assert wf["permissions"] == {"contents": "write", "issues": "write"}
    assert set(wf["jobs"]) == {"probe"}
    text_ = (ROOT / ".github/workflows/live-check.yml").read_text()
    assert "offsim.live.cli" in text_ and "live/status" in text_ and "PYTHONUNBUFFERED" in text_
    assert "secrets.AMPL_LICENSE_UUID" in text_ and "OFFSIM_MAILTO" in text_
