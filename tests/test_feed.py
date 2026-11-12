"""Feed sources, dedupe, run CLI, rule tagger and gap finder. Offline: every API answer is a recorded fixture
in tests/fixtures/feed/ (synthetic content, real response shapes)."""
import json
import urllib.parse

import pandas as pd
import yaml

from conftest import ROOT
from offsim.feed import run as R
from offsim.feed import sources as S
from offsim.research import gaps as G
from offsim.research import tags as T

FIX = ROOT / "tests/fixtures/feed"
SINCE = "2015-01-01"
ROUTES = {"api.openalex.org": "openalex.json", "api.crossref.org": "crossref.json",
          "export.arxiv.org": "arxiv.xml", "api.nva.unit.no": "nva.json"}


def fixture(name):
    return (FIX / name).read_bytes()


class Fake:
    """Records every URL and answers with the fixture whose host appears in it."""

    def __init__(self, answers=None):
        self.answers = answers or {}
        self.urls = []

    def __call__(self, url):
        self.urls.append(url)
        for key, name in self.answers.items():
            if key in url:
                return fixture(name)
        raise AssertionError("no fixture for " + url)


def qs(url):
    return urllib.parse.parse_qs(urllib.parse.urlparse(url).query)


def route_all(url):
    for host, name in ROUTES.items():
        if host in url:
            return fixture(name)
    raise AssertionError(url)


# ---------- sources ----------

def test_openalex_parses_fixture_and_builds_filter(monkeypatch):
    monkeypatch.setenv("OFFSIM_MAILTO", "research@example.org")
    fake = Fake({"api.openalex.org": "openalex.json"})
    recs = S.openalex("offshore supply vessel", SINCE, fetch=fake)
    q = qs(fake.urls[0])
    assert q["filter"] == ["from_publication_date:2015-01-01,title_and_abstract.search:offshore supply vessel"]
    assert q["mailto"] == ["research@example.org"]
    assert [r["id"] for r in recs] == ["10.1234/psv.2019.001", "10.1234/ctv.2021.042", "openalex:W9000000003"]
    psv = recs[0]
    assert psv["abstract"].startswith("Offshore supply vessels serve platforms")
    assert psv["abstract"].endswith("psv-routing.")
    assert psv["year"] == 2019 and psv["authors"] == ["Test Author One", "Test Author Two"]
    assert psv["venue"] == "Test Journal of Maritime Logistics"
    assert psv["oa_url"] == "https://example.org/psv-2019.pdf" and psv["source"] == "openalex"
    assert psv["fetched_utc"].endswith("Z")
    assert recs[1]["oa_url"] is None
    assert recs[2]["abstract"] == "" and recs[2]["venue"] is None


def test_openalex_author_query_and_no_mailto_without_env(monkeypatch):
    monkeypatch.delenv("OFFSIM_MAILTO", raising=False)
    fake = Fake({"api.openalex.org": "openalex.json"})
    S.openalex("author:Fagerholt", SINCE, fetch=fake)
    q = qs(fake.urls[0])
    assert q["filter"][0].endswith("authorships.author.display_name.search:Fagerholt")
    assert "mailto" not in q


def test_crossref_strips_jats_and_filters_by_date():
    fake = Fake({"api.crossref.org": "crossref.json"})
    recs = S.crossref("helicopter crew", SINCE, fetch=fake)
    assert "from-pub-date:2015-01-01" in qs(fake.urls[0])["filter"][0]
    assert [r["id"] for r in recs] == ["10.1234/psv.2019.001", "10.1234/cargo.2016.007"]  # 1999 and untitled dropped
    heli = recs[1]
    assert "<" not in heli["abstract"]
    assert "We solve a vehicle routing problem with time windows by column generation." in heli["abstract"]
    assert heli["authors"] == ["Test Author Four"] and heli["year"] == 2016 and heli["oa_url"] is None
    S.crossref("author:Halskau", SINCE, fetch=fake)
    assert "query.author" in qs(fake.urls[-1])


def test_arxiv_parses_atom_and_skips_errors_and_old_entries():
    fake = Fake({"export.arxiv.org": "arxiv.xml"})
    recs = S.arxiv("ferry", SINCE, fetch=fake)
    assert qs(fake.urls[0])["search_query"] == ["all:ferry"]
    assert [r["id"] for r in recs] == ["arXiv:2301.01234", "arXiv:2006.00042"]
    f = recs[0]
    assert f["year"] == 2023 and f["authors"] == ["Test Author Five", "Test Author Six"]
    assert f["abstract"].startswith("We schedule an electric passenger ferry") and "  " not in f["abstract"]
    assert f["oa_url"] == "http://arxiv.org/pdf/2301.01234v2" and f["venue"] == "arXiv"
    assert recs[1]["venue"] == "Test Operations Journal 12 (2020)"
    S.arxiv("offshore supply vessel", SINCE, fetch=fake)
    assert qs(fake.urls[-1])["search_query"] == ["all:offshore AND all:supply AND all:vessel"]
    S.arxiv("author:Gribkovskaia", SINCE, fetch=fake)
    assert qs(fake.urls[-1])["search_query"] == ["au:Gribkovskaia"]


def test_nva_is_defensive_about_missing_fields():
    fake = Fake({"api.nva.unit.no": "nva.json"})
    recs = S.nva("ferry", fetch=fake)
    assert [r["id"] for r in recs] == ["10.1234/nva.2021.9", "nva:67890"]  # the hit without a title is skipped
    assert recs[0]["venue"] == "Test Norwegian Transport Journal" and recs[0]["authors"] == ["Test Author Nine"]
    assert recs[1]["abstract"] == "" and recs[1]["authors"] == [] and recs[1]["year"] == 2018


def test_arxiv_doi_is_canonicalised():
    assert S._canon("10.48550/arxiv.2301.01234", "x") == "arXiv:2301.01234"
    assert S._doi("https://doi.org/10.1016/J.EJOR.2019.01.001") == "10.1016/j.ejor.2019.01.001"


# ---------- dedupe ----------

def test_dedupe_by_doi_arxiv_id_and_title():
    everything = (S.openalex("x", SINCE, fetch=Fake({"api.openalex.org": "openalex.json"}))
                  + S.crossref("x", SINCE, fetch=Fake({"api.crossref.org": "crossref.json"}))
                  + S.arxiv("x", SINCE, fetch=Fake({"export.arxiv.org": "arxiv.xml"}))
                  + S.nva("x", fetch=Fake({"api.nva.unit.no": "nva.json"})))
    kept = S.dedupe(everything)
    ids = [r["id"] for r in kept]
    assert len(ids) == len(set(ids)) == 7
    assert ids.count("10.1234/psv.2019.001") == 1          # upper-case DOI in Crossref is the same paper
    assert "openalex:W9000000003" in ids                   # same title on arXiv: the first (OpenAlex) wins
    assert "arXiv:2006.00042" not in ids
    assert "arXiv:2301.01234" in ids


# ---------- run CLI ----------

def test_run_appends_only_new_records(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "_get", route_all)
    queries = tmp_path / "q.yaml"
    queries.write_text(yaml.safe_dump({"queries": ["offshore supply vessel", "ferry"]}))
    out = tmp_path / "feed.jsonl"
    args = ["--queries", str(queries), "--out", str(out), "--since", SINCE, "--pause", "0"]
    assert R.main(args) == 0
    first = out.read_text().splitlines()
    assert len(first) == 7
    assert R.main(args) == 0
    assert out.read_text().splitlines() == first            # rerun adds nothing
    assert {json.loads(l)["source"] for l in first} == {"openalex", "crossref", "arxiv", "nva"}


def test_run_survives_a_failing_source(tmp_path, monkeypatch, capsys):
    def flaky(url):
        if "api.crossref.org" in url:
            raise OSError("blocked in this environment")
        return route_all(url)
    monkeypatch.setattr(S, "_get", flaky)
    queries = tmp_path / "q.yaml"
    queries.write_text(yaml.safe_dump({"queries": ["ferry"], "sources": ["crossref", "arxiv"]}))
    out = tmp_path / "feed.jsonl"
    assert R.main(["--queries", str(queries), "--out", str(out), "--pause", "0"]) == 0
    assert "feed warning" in capsys.readouterr().err
    assert all(json.loads(l)["source"] == "arxiv" for l in out.read_text().splitlines())


def test_repo_queries_file_is_valid():
    queries, _ = R.load_queries(ROOT / "papers/queries.yaml")
    assert len(queries) >= 8 and "author:Fagerholt" in queries and "PSV routing weather" in queries


def test_workflow_parses():
    wf = yaml.safe_load((ROOT / ".github/workflows/papers.yml").read_text())
    assert set(wf["jobs"]) == {"feed"} and "schedule" in wf[True] and "workflow_dispatch" in wf[True]


# ---------- tagger ----------

PSV = {"id": "10.1234/psv.2019.001",
       "title": "Robust planning of offshore supply vessel routes under weather uncertainty",
       "abstract": "Offshore supply vessels serve platforms on the Norwegian continental shelf. We formulate a "
                   "pickup and delivery problem with time windows and solve it exactly by branch-and-price under "
                   "forecast weather windows. Code is at https://github.com/example/psv-routing."}
CTV = {"id": "10.1234/ctv.2021.042",
       "title": "Crew transfer vessel dispatching for offshore wind farm maintenance with failures",
       "abstract": "Crew transfer vessels support operation and maintenance of wind farms in the German North Sea. "
                   "We simulate turbine failures with discrete-event simulation and compare dispatch heuristics."}
FERRY = {"id": "arXiv:2301.01234", "title": "Electric ferry timetabling with charging under simulation",
         "abstract": "We schedule an electric passenger ferry fleet with charging constraints in the Oslofjord. "
                     "Ferry timetables are evaluated by a discrete-event simulation. Data is archived at "
                     "https://zenodo.org/records/1234567."}


def test_tagger_psv_routing_weather_exact_with_code():
    t = T.tag(PSV)
    assert {"PSV-PDP", "PDP"} <= set(t["classes"])
    assert t["mode"] == ["psv"] and "NCS" in t["region"]
    assert t["uncertainty"] == "weather" and t["method"] == "exact"
    assert t["code"] == "https://github.com/example/psv-routing" and t["data"] is None
    assert t["tagged_by"] == "rule" and 0 < t["confidence"] <= 0.9


def test_tagger_ctv_failures_hybrid_no_code():
    t = T.tag(CTV)
    assert {"CREW-ROUTE", "WIND-OM"} <= set(t["classes"])
    assert t["mode"] == ["ctv"] and t["region"] == ["North Sea"]
    assert t["uncertainty"] == "failure" and t["method"] == "hybrid"
    assert t["code"] is None and t["data"] is None


def test_tagger_ferry_oslofjord_simulation_with_data():
    t = T.tag(FERRY)
    assert t["classes"] == ["FERRY-SCHED"] and t["mode"] == ["ferry"] and t["region"] == ["Oslofjord"]
    assert t["method"] == "simulation" and t["uncertainty"] == "none"
    assert t["data"] == "https://zenodo.org/records/1234567" and t["code"] is None


def test_tagger_edge_cases():
    empty = T.tag({"id": "x", "title": "Cooking pasta", "abstract": ""})
    assert empty["classes"] == [] and empty["confidence"] == 0.0 and empty["region"] == ["none"]
    funder = T.tag({"id": "y", "title": "Vehicle routing with time windows",
                    "abstract": "Funded by the Norwegian Research Council."})
    assert "Norway" not in funder["region"] and funder["region"] == ["none"]


# ---------- gaps ----------

def _tag(pid, classes, mode, region, unc, code=None, data=None, statement=None):
    return {"paper_id": pid, "classes": classes, "mode": mode, "region": region, "uncertainty": unc,
            "code": code, "data": data, "code_statement": statement, "method": "heuristic", "kpis": [],
            "tagged_by": "rule", "confidence": 0.5}


def test_no_norway_gap_on_constructed_set():
    tags = [
        _tag("a", ["PSV-PDP"], ["psv"], ["UK"], "weather", code="https://github.com/x/y"),
        _tag("b", ["PSV-PDP"], ["psv"], ["Brazil"], "demand"),
        _tag("c", ["PSV-PDP"], ["psv"], ["none"], "multiple", data="https://zenodo.org/x"),
        _tag("d", ["FERRY-SCHED"], ["ferry"], ["Oslofjord"], "none"),   # one paper: below min_support
    ]
    gaps = G.find_gaps(tags, min_support=2)
    kinds = {(g["kind"], g["class"], g["mode"]) for g in gaps}
    assert ("no-norway", "PSV-PDP", "psv") in kinds
    assert ("no-uncertainty", "PSV-PDP", "psv") not in kinds      # weather and demand present
    assert ("no-code", "PSV-PDP", "psv") not in kinds             # a has code, c has data
    assert not any(g["class"] == "FERRY-SCHED" for g in gaps)
    g = next(g for g in gaps if g["kind"] == "no-norway")
    assert g["papers"] == ["a", "b", "c"] and g["support"] == 3
    assert g["gap_id"] == "no-norway-psv-pdp-psv"
    assert g["engine"] == "openclsim" and g["status"] == "open"


def test_norway_present_closes_no_norway_gap_and_deterministic_wind_om_is_flagged():
    tags = [
        _tag("a", ["PSV-PDP"], ["psv"], ["NCS"], "weather", code="https://github.com/x/y"),
        _tag("b", ["PSV-PDP"], ["psv"], ["UK"], "demand", code="https://github.com/x/z"),
        # why: no-code now needs the record to state its code/data availability; silent abstracts prove nothing
        _tag("e", ["WIND-OM"], ["ctv"], ["Baltic"], "none", statement="unavailable"),
        _tag("f", ["WIND-OM"], ["ctv"], ["Baltic"], "none", statement="unavailable"),
    ]
    kinds = {(g["kind"], g["class"]) for g in G.find_gaps(tags)}
    assert ("no-norway", "PSV-PDP") not in kinds
    assert ("no-uncertainty", "WIND-OM") in kinds and ("no-code", "WIND-OM") in kinds
    wind = next(g for g in G.find_gaps(tags) if g["class"] == "WIND-OM" and g["kind"] == "no-code")
    assert wind["engine"] == "wombat"


def test_gap_table_counts_and_write_round_trip(tmp_path):
    tags = [_tag("a", ["PSV-PDP"], ["psv"], ["UK"], "weather"), _tag("b", ["PSV-PDP"], ["psv"], ["UK"], "weather")]
    df = G.gap_table(tags)
    assert isinstance(df, pd.DataFrame) and list(df.columns) == G.COLUMNS
    assert int(df.loc[0, "n"]) == 2
    assert G.gap_table([]).empty
    p = tmp_path / "gaps.yaml"
    G.write_gaps(G.find_gaps(tags), p)
    assert yaml.safe_load(p.read_text())["gaps"][0]["kind"] == "no-norway"


def test_tags_cli_reads_feed(tmp_path):
    feed = tmp_path / "feed.jsonl"
    feed.write_text("\n".join(json.dumps(r) for r in (PSV, CTV, FERRY)) + "\n")
    out = tmp_path / "tags.jsonl"
    assert T.main(["--feed", str(feed), "--out", str(out)]) == 0
    rows = [json.loads(l) for l in out.read_text().splitlines()]
    assert [r["paper_id"] for r in rows] == [PSV["id"], CTV["id"], FERRY["id"]]
