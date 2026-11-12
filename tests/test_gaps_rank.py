"""Gap scout (W6): no-code needs evidence, ranking with four written factors, synonym dedupe, review verdicts that survive
regeneration, and an experiment skeleton that loads and invents no number. Offline; capabilities are passed in."""
import re
from pathlib import Path

import pytest
import yaml

from offsim.research import experiment
from offsim.research import gaps as G
from offsim.research import review as R
from offsim.research import tags as T

ROOT = Path(__file__).resolve().parents[1]
CAPS = {"solvers": {"pyvrp": {"CVRP"}, "whelp": {"WFPPP"}},
        "engines": {"replay": {"CVRP", "VRPTW"}, "air": {"WFPPP"}, "openclsim": {"CVRP"}, "wombat": {"WIND-OM"}}}


def _tag(pid, classes, mode, region, unc="none", code=None, data=None, statement=None, confidence=0.5):
    return {"paper_id": pid, "classes": classes, "mode": mode, "region": region, "uncertainty": unc,
            "code": code, "data": data, "code_statement": statement, "method": "heuristic", "kpis": ["makespan_s"],
            "tagged_by": "rule", "confidence": confidence}


def _by(gaps, kind, cls, mode):
    return next(g for g in gaps if (g["kind"], g["class"], g["mode"]) == (kind, cls, mode))


# --- no-code only with evidence ------------------------------------------------------------------------------------

def test_silent_records_never_make_a_no_code_gap():
    tags = [_tag(f"p{i}", ["WIND-OM"], ["ctv"], ["NCS"], "weather") for i in range(3)]
    suppressed = []
    gaps = G.find_gaps(tags, caps=CAPS, suppressed=suppressed)
    assert not any(g["kind"] == "no-code" for g in gaps)
    assert suppressed == [{"cell": "WIND-OM/ctv", "papers": 3,
                           "reason": "3 of 3 records state nothing about code or data"}]


def test_no_code_gap_when_every_record_states_unavailability_and_says_why():
    tags = [_tag(f"p{i}", ["WIND-OM"], ["ctv"], ["NCS"], "weather", statement="unavailable") for i in range(3)]
    g = _by(G.find_gaps(tags, caps=CAPS), "no-code", "WIND-OM", "ctv")
    assert g["papers"] == ["p0", "p1", "p2"]
    assert "unavailable" in g["factor_notes"]["evidence"] and "unavailable" in g["why"]


def test_one_linked_paper_closes_no_code_even_with_statements():
    tags = [_tag("a", ["WIND-OM"], ["ctv"], ["NCS"], "weather", statement="unavailable"),
            _tag("b", ["WIND-OM"], ["ctv"], ["NCS"], "weather", code="https://github.com/x/y"),
            _tag("c", ["WIND-OM"], ["ctv"], ["NCS"], "weather", statement="unavailable")]
    assert not any(g["kind"] == "no-code" for g in G.find_gaps(tags, caps=CAPS))


def test_tagger_reads_availability_statements_only():
    said = T.tag({"id": "x", "title": "Crew transfer routing", "abstract": "The dataset is not publicly available."})
    req = T.tag({"id": "y", "title": "Crew transfer routing", "abstract": "Data available on request."})
    silent = T.tag({"id": "z", "title": "Crew transfer routing", "abstract": "We route crew transfer vessels."})
    assert said["code_statement"] == "unavailable" and req["code_statement"] == "unavailable"
    assert silent["code_statement"] is None


# --- ranking -------------------------------------------------------------------------------------------------------

def test_feasible_norwegian_gap_ranks_above_infeasible_foreign_one():
    feasible_no = [_tag(f"n{i}", ["CVRP"], ["truck"], ["NCS"]) for i in range(2)]
    infeasible_uk = [_tag(f"u{i}", ["PDP"], ["heli"], ["UK"]) for i in range(5)]   # more papers, more support
    gaps = G.find_gaps(feasible_no + infeasible_uk, caps=CAPS, root=ROOT)
    top_ids = [g["gap_id"] for g in gaps]
    nor = _by(gaps, "no-uncertainty", "CVRP", "truck")
    foreign = _by(gaps, "no-uncertainty", "PDP", "heli")
    assert top_ids.index(nor["gap_id"]) < top_ids.index(foreign["gap_id"])
    assert nor["factors"]["feasibility"] == 1.0          # pyvrp covers CVRP, replay covers CVRP, NCS world exists
    assert foreign["factors"]["feasibility"] == 0.0      # no solver, no engine for PDP, UK has no world
    assert nor["factors"]["score"] > foreign["factors"]["score"]


def test_every_gap_carries_four_factors_and_their_product():
    tags = [_tag(f"p{i}", ["WFPPP"], ["heli"], ["NCS"]) for i in range(3)]
    for g in G.find_gaps(tags, caps=CAPS, root=ROOT):
        f = g["factors"]
        assert set(f) == {"support", "novelty", "feasibility", "audience", "score"}
        assert all(0 <= f[k] <= 1 for k in ("support", "novelty", "feasibility", "audience"))
        assert f["score"] == pytest.approx(f["support"] * f["novelty"] * f["feasibility"] * f["audience"], abs=1e-3)
        assert set(g["factor_notes"]) >= {"support", "novelty", "feasibility", "audience"}


def test_support_saturates_and_audience_is_explained():
    tags = [_tag(f"p{i}", ["CVRP"], ["psv"], ["NCS"]) for i in range(8)]
    g = _by(G.find_gaps(tags, caps=CAPS, root=ROOT), "no-uncertainty", "CVRP", "psv")
    assert g["factors"]["support"] == 1.0
    assert g["factors"]["audience"] == 1.0 and "editorial weight" in g["factor_notes"]["audience"]


def test_feasibility_needs_registered_solver_engine_and_reachable_data():
    assert G.world_reachable("NCS", ROOT) and not G.world_reachable("UK", ROOT) and not G.world_reachable("none", ROOT)
    no_solver = {"solvers": {}, "engines": CAPS["engines"]}
    tags = [_tag(f"p{i}", ["CVRP"], ["truck"], ["NCS"]) for i in range(2)]
    g = _by(G.find_gaps(tags, caps=no_solver, root=ROOT), "no-uncertainty", "CVRP", "truck")
    assert g["factors"]["feasibility"] == pytest.approx(2 / 3, abs=1e-3)
    assert "none covers CVRP" in g["factor_notes"]["feasibility"]


# --- dedupe --------------------------------------------------------------------------------------------------------

def test_synonym_classes_collapse_into_one_gap_with_the_union_of_papers():
    tags = [_tag("p1", ["WFPPP"], ["heli"], ["NCS"]), _tag("p2", ["WFPPP"], ["heli"], ["NCS"]),
            _tag("p2", ["HRP"], ["heli"], ["NCS"]), _tag("p3", ["HRP"], ["heli"], ["NCS"])]
    gaps = G.find_gaps(tags, caps=CAPS, root=ROOT)
    hrp = [g for g in gaps if g["kind"] == "no-uncertainty" and g["mode"] == "heli"]
    assert len(hrp) == 1
    assert hrp[0]["gap_id"] == "no-uncertainty-hrp-heli" and hrp[0]["engine"] == "air"
    assert hrp[0]["papers"] == ["p1", "p2", "p3"] and hrp[0]["support"] == 3
    assert hrp[0]["synonyms"] == ["WFPPP"]


# --- review verdicts ----------------------------------------------------------------------------------------------

def _write_gaps(tmp_path, gaps):
    p = tmp_path / "gaps.yaml"
    G.write_gaps(gaps, p)
    return p


def test_review_verdicts_survive_regeneration(tmp_path):
    tags = [_tag(f"p{i}", ["CVRP"], ["truck"], ["NCS"]) for i in range(2)]
    tags += [_tag("q1", ["PDP"], ["heli"], ["UK"]), _tag("q2", ["PDP"], ["heli"], ["UK"])]
    gaps_path = _write_gaps(tmp_path, G.find_gaps(tags, caps=CAPS, root=ROOT))
    review = tmp_path / "review.yaml"
    review.write_text(R.REVIEW_HEADER)
    R.add_review("no-uncertainty-cvrp-truck", "drop", "not for us", gaps_path=gaps_path, review_path=review,
                 now="2026-11-01T00:00:00Z")
    R.add_review("no-uncertainty-pdp-heli", "take", "film this", gaps_path=gaps_path, review_path=review,
                 now="2026-11-01T00:00:00Z")

    def regenerate(extra=()):
        fresh = G.find_gaps([*tags, *extra], caps=CAPS, root=ROOT)
        R.apply_reviews(fresh, R.load_reviews(review))
        return {g["gap_id"]: g for g in fresh}

    g = regenerate()
    assert g["no-uncertainty-cvrp-truck"]["status"] == "dropped"
    assert "no new papers since" in g["no-uncertainty-cvrp-truck"]["why"]
    assert g["no-uncertainty-pdp-heli"]["status"] == "take"

    g = regenerate(extra=[_tag("p9", ["CVRP"], ["truck"], ["NCS"])])
    assert g["no-uncertainty-cvrp-truck"]["status"] == "open"
    assert g["no-uncertainty-cvrp-truck"]["review"]["reopened"] is True
    assert g["no-uncertainty-cvrp-truck"]["review"]["new_papers"] == ["p9"]
    assert "Reopened: 1 papers" in g["no-uncertainty-cvrp-truck"]["why"]
    assert g["no-uncertainty-pdp-heli"]["status"] == "take"


def test_review_file_is_only_appended_and_gaps_never_write_it(tmp_path):
    tags = [_tag(f"p{i}", ["CVRP"], ["truck"], ["NCS"]) for i in range(2)]
    tags_path = tmp_path / "tags.jsonl"
    tags_path.write_text("".join(__import__("json").dumps(t) + "\n" for t in tags))
    gaps_path = _write_gaps(tmp_path, G.find_gaps(tags, caps=CAPS, root=ROOT))
    review = tmp_path / "review.yaml"
    review.write_text(R.REVIEW_HEADER)
    R.add_review("no-uncertainty-cvrp-truck", "later", "wait for weather", gaps_path=gaps_path, review_path=review,
                 now="2026-11-01T00:00:00Z")
    R.add_review("no-uncertainty-cvrp-truck", "drop", "second thoughts", gaps_path=gaps_path, review_path=review,
                 now="2026-11-02T00:00:00Z")
    before = review.read_bytes()
    assert before.startswith(R.REVIEW_HEADER.encode())
    G.main(["--tags", str(tags_path), "--out", str(tmp_path / "out.yaml"), "--review", str(review)])
    assert review.read_bytes() == before
    assert R.load_reviews(review)["no-uncertainty-cvrp-truck"]["verdict"] == "drop"   # last entry wins
    with pytest.raises(ValueError):
        R.add_review("no-uncertainty-cvrp-truck", "maybe", "x", gaps_path=gaps_path, review_path=review)
    with pytest.raises(ValueError):
        R.add_review("no-uncertainty-cvrp-truck", "take", "  ", gaps_path=gaps_path, review_path=review)


# --- experiment skeleton -------------------------------------------------------------------------------------------

def _numbers(obj):
    if isinstance(obj, bool):
        return []
    if isinstance(obj, (int, float)):
        return [obj]
    if isinstance(obj, dict):
        return [n for v in obj.values() for n in _numbers(v)]
    if isinstance(obj, list):
        return [n for v in obj for n in _numbers(v)]
    return []


def test_draft_writes_a_loadable_skeleton_with_no_invented_number(tmp_path):
    tags = [_tag("10.1/abc.1", ["CVRP"], ["truck"], ["NCS"], "none", confidence=0.7),
            _tag("10.1/abc.2", ["CVRP"], ["truck"], ["NCS"], "none", confidence=0.4)]
    gaps_path = _write_gaps(tmp_path, G.find_gaps(tags, caps=CAPS, root=ROOT))
    out = R.draft("no-uncertainty-cvrp-truck", gaps_path=gaps_path, root=tmp_path)
    assert out == tmp_path / "offsim" / "papers" / "10-1-abc-1" / "experiment.yaml"   # highest-confidence paper
    exp = experiment.load(out)
    assert exp.gap_id == "no-uncertainty-cvrp-truck" and exp.hypothesis is None
    doc = yaml.safe_load(out.read_text())
    assert _numbers(doc) == []                       # no hypothesis number, no threshold, no seed count
    assert doc["decision"]["min_effect"] is None and doc["decision"]["better"] is None
    assert doc["variants"]["paper"]["solver"] is None and doc["variants"]["paper"]["engine"] == "replay"
    assert doc["ensemble"]["seeds"] is None
    assert {a["path"] for a in doc["assumptions"]} >= {"variants.paper.engine", "decision.kpi"}
    with pytest.raises(FileExistsError):
        R.draft("no-uncertainty-cvrp-truck", gaps_path=gaps_path, root=tmp_path)


def test_draft_refuses_unknown_gap_and_list_hides_dropped(tmp_path):
    tags = [_tag(f"p{i}", ["CVRP"], ["truck"], ["NCS"]) for i in range(2)]
    gaps_path = _write_gaps(tmp_path, G.find_gaps(tags, caps=CAPS, root=ROOT))
    with pytest.raises(KeyError):
        R.draft("no-such-gap", gaps_path=gaps_path, root=tmp_path)
    gaps = yaml.safe_load(gaps_path.read_text())["gaps"]
    gaps[0]["status"] = "dropped"
    table = R.format_table(gaps)
    assert "no-uncertainty-cvrp-truck" not in table and "no gaps to show" in table
    assert "no-uncertainty-cvrp-truck" in R.format_table(gaps, show_all=True)


def test_slug_is_a_safe_directory_name():
    assert R.paper_slug("10.1016/j.ejor.2016.05.059") == "10-1016-j-ejor-2016-05-059"
    assert re.fullmatch(r"[a-z0-9-]+", R.paper_slug("nva:0198e7cb3706-9bfcc7b8")) is not None
