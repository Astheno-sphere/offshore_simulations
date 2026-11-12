"""Article generator and publish stage: offline, no network, every number traced to a ref."""
import copy
import json
import re
import shlex
from pathlib import Path

import pytest
import yaml

from conftest import ROOT
from offsim.__main__ import build_parser, main
from offsim.motion import narrate
from offsim.pipeline import run
from offsim.publish import article
from offsim.studio import conductor, context, load_funnel

DEMO = ROOT / "offsim/papers/demo-oslofjord-supply/scenario.yaml"
NUM = re.compile(r"\d+(?:\.\d+)?")


@pytest.fixture(scope="module")
def demo_report(tmp_path_factory):
    d = tmp_path_factory.mktemp("demo")
    sc = yaml.safe_load(DEMO.read_text())
    sc["world"] = "none"                                    # CI has no fetched world
    (d / "s.yaml").write_text(yaml.safe_dump(sc))
    run(d / "s.yaml", d / "out", seconds=1)
    return d / "out/report.json"


def ensemble_block(rel=-0.12, ci=(-0.2, -0.04), mean=-2400.0, aci=(-4000.0, -800.0)):
    q = lambda p10, p50, p90: {"p10": p10, "p50": p50, "p90": p90, "mean": p50, "n": 12}
    return {"ok": True, "validated": True, "n_runs": 24, "n_valid": 24, "variants": ["base", "alt"], "seeds": [1, 2],
            "years": [2019, 2020], "engines": ["replay"], "weather_sources": ["MET Norway NorKyst"],
            "synthetic_weather": False, "kpis": ["makespan_s"],
            "quantiles": {"makespan_s": {"base": q(18000, 20000, 25000), "alt": q(16000, 17600, 22000)}},
            "comparisons": [{"kpi": "makespan_s", "a": "alt", "b": "base", "n_pairs": 12, "mean_diff": mean,
                             "ci95": list(aci), "rel_mean": rel, "rel_ci95": list(ci), "n_boot": 100, "boot_seed": 0}],
            "failures": []}


@pytest.fixture
def rep(demo_report):
    return json.loads(demo_report.read_text())


def write(tmp_path, r, name="report.json"):
    p = tmp_path / name
    p.write_text(json.dumps(r))
    return p


# ---------------------------------------------------------------------------------------------------- rendering
def test_linkedin_article_from_the_demo_report(demo_report, tmp_path):
    out = article.build(demo_report, "linkedin", out=tmp_path / "a.md")
    text = out.read_text()
    assert "Single run, no ensemble" in text and "not comparable" in text
    assert "**Assumptions.**" in text and "- **fleet**" in text
    assert 180 <= len(text.split()) <= 250, len(text.split())
    assert (tmp_path / "a.md.meta.json").is_file()


def test_other_templates_render_and_length(demo_report, rep, tmp_path):
    t = article.build(demo_report, "thought", out=tmp_path / "t.md").read_text()
    assert 600 <= len(t.split()) <= 900, len(t.split())
    r = article.build(demo_report, "readme_entry", out=tmp_path / "r.md").read_text()
    assert r.startswith("### demo-oslofjord-supply") and len(r.split()) < 120
    rep["ensemble"] = ensemble_block()
    p = write(tmp_path, rep)
    for tpl, lo, hi in (("linkedin", 180, 250), ("thought", 600, 900)):
        n = len(article.build(p, tpl, out=tmp_path / f"e_{tpl}.md").read_text().split())
        assert lo <= n <= hi, (tpl, n)


def test_every_number_traces_to_a_ref(demo_report, rep, tmp_path):
    rep["ensemble"] = ensemble_block()
    p = write(tmp_path, rep)
    for report_path in (demo_report, p):
        values = article.refs(json.loads(Path(report_path).read_text()))
        ok = article._traceable_tokens(values)
        for tpl in ("linkedin", "thought", "readme_entry"):
            text = article.build(report_path, tpl, out=tmp_path / f"{tpl}.md").read_text()
            body = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
            stray = [n for n in NUM.findall(body) if n not in ok]
            assert not stray, (tpl, stray)
            assert NUM.findall(body)                              # the check is not vacuous


def test_template_literals_carry_no_digits():
    for path in article.TEMPLATES.glob("*.md"):
        meta, body = article.load_template(path.stem)
        assert not article._lint(meta, body), path.name
        assert not NUM.search(article._PH.sub("", body)), path.name


def test_stray_number_in_a_template_is_an_error(rep):
    meta = {"requires": ["paper.id"], "template": "x"}
    with pytest.raises(article.ArticleError, match="number"):
        article.render(rep, meta, "Reduced by 12% {{ref:paper.id}} {{list:assumptions}}")


def test_untraceable_output_number_is_caught_at_build(rep, monkeypatch):
    monkeypatch.setattr(article, "_traceable_tokens", lambda values: set())
    with pytest.raises(article.ArticleError, match="trace to no ref"):
        article.render(rep, {"requires": ["kpis.distance_km"], "template": "x"}, "{{ref:kpis.distance_km}} {{list:assumptions}}")


def test_unresolved_placeholder_raises_never_blank(rep):
    meta = {"requires": ["kpis.nope"], "template": "x"}
    with pytest.raises(article.ArticleError, match="missing refs"):
        article.render(rep, meta, "{{ref:kpis.nope}} {{list:assumptions}}")
    meta = {"requires": [], "template": "x"}
    with pytest.raises(article.ArticleError, match="not declared"):
        article.render(rep, meta, "{{ref:kpis.distance_km}} {{list:assumptions}}")
    meta = {"requires": ["kpis.distance_km"], "template": "x"}
    with pytest.raises(article.ArticleError, match="no rules"):
        article.render(rep, meta, "{{narrate:ghost}} {{list:assumptions}}")
    bad = {"requires": [], "template": "x", "narration": {"n": [{"when": "ensemble.zzz > 1", "text": "a"}, {"text": "b"}]}}
    with pytest.raises(article.ArticleError, match="measured"):
        article.render(rep, bad, "{{narrate:n}} {{list:assumptions}}")


# ---------------------------------------------------------------------------------------------------- refusals
def test_failed_gate_report_is_refused(rep, tmp_path):
    rep["gates"]["1_plan"]["pass"] = False
    with pytest.raises(article.ArticleRefused, match="gate failed"):
        article.build(write(tmp_path, rep), out=tmp_path / "a.md")
    assert not (tmp_path / "a.md").exists()


def test_did_not_reproduce_is_a_finding_not_a_refusal(rep, tmp_path):
    rep["status"] = "did not reproduce"
    rep["gates"]["4_paper"] = {"pass": False, "detail": [{"kpi": "distance_km", "paper": 100.0, "ours": 114.6,
                                                         "rel_gap": 0.146, "rel_tol": 0.05, "pass": False}]}
    text = article.build(write(tmp_path, rep), out=tmp_path / "a.md").read_text()
    assert "did not reproduce" in text.lower() and "114.6" in text and "100.0" in text


def test_synthetic_weather_and_not_reportable_refused(rep, tmp_path):
    a = dict(rep, status="re-run under assumptions (synthetic weather, not reportable)")
    with pytest.raises(article.ArticleRefused, match="synthetic"):
        article.build(write(tmp_path, a), out=tmp_path / "a.md")
    b = dict(rep, reportable=False)
    with pytest.raises(article.ArticleRefused, match="not reportable"):
        article.build(write(tmp_path, b, "b.json"), out=tmp_path / "b.md")
    c = dict(rep, ensemble=dict(ensemble_block(), synthetic_weather=True))
    with pytest.raises(article.ArticleRefused, match="synthetic"):
        article.build(write(tmp_path, c, "c.json"), out=tmp_path / "c.md")


def test_stopped_and_paperless_reports_refused(rep, tmp_path):
    with pytest.raises(article.ArticleRefused, match="gate"):
        article.build(write(tmp_path, dict(rep, status="stopped at gate 1_plan"), "s.json"), out=tmp_path / "s.md")
    nop = {k: v for k, v in rep.items() if k != "paper"}
    with pytest.raises(article.ArticleRefused, match="paper"):
        article.build(write(tmp_path, nop, "n.json"), out=tmp_path / "n.md")


def test_assumptions_need_a_section(rep):
    meta = {"requires": ["paper.id"], "template": "x"}
    assert rep["assumptions"]
    with pytest.raises(article.ArticleRefused, match="assumptions"):
        article.render(rep, meta, "{{ref:paper.id}}")
    ok = dict(rep, assumptions=[])
    assert "demo-oslofjord-supply" in article.render(ok, meta, "{{ref:paper.id}}")


# ---------------------------------------------------------------------------------------------------- narration
def test_narration_picks_the_sentence_the_ensemble_supports(rep):
    meta, _ = article.load_template("linkedin")
    rules = meta["narration"]["answer"]

    def pick(**kw):
        r = copy.deepcopy(rep)
        r["ensemble"] = ensemble_block(**kw)
        return narrate.choose(rules, article.refs(r))

    assert "lowers makespan by 12.0%" in pick()                                    # CI excludes zero, alt is lower
    inconclusive = pick(rel=-0.02, ci=(-0.1, 0.05), mean=-400.0, aci=(-2000.0, 700.0))
    assert "Inconclusive" in inconclusive and "lowers" not in inconclusive
    r = copy.deepcopy(rep)
    r["ensemble"] = ensemble_block()
    r["ensemble"]["comparisons"] = []
    assert "median of 5.6 hours" in narrate.choose(rules, article.refs(r))        # 20000 s
    assert "Single run, no ensemble" in narrate.choose(rules, article.refs(rep))


def test_raising_comparison_and_status_sentences(rep):
    meta, _ = article.load_template("linkedin")
    r = copy.deepcopy(rep)
    r["ensemble"] = ensemble_block(rel=0.12, ci=(0.04, 0.2), mean=2400.0, aci=(800.0, 4000.0))
    assert "raises makespan by 12.0%" in narrate.choose(meta["narration"]["answer"], article.refs(r))
    r["status"] = "reproduced"
    r["gates"]["4_paper"] = {"pass": True, "detail": [{"kpi": "distance_km", "paper": 100.0, "ours": 100.4,
                                                       "rel_gap": 0.004, "rel_tol": 0.01, "pass": True}]}
    assert narrate.choose(meta["narration"]["status_line"], article.refs(r)).startswith("Status: reproduced.")


# ---------------------------------------------------------------------------------------------------- figures
def test_figures_become_image_links_with_ref_captions(demo_report, tmp_path):
    fig = tmp_path / "frame.png"
    fig.write_bytes(b"\x89PNG")
    text = article.build(demo_report, "linkedin", out=tmp_path / "a.md", figures=[fig]).read_text()
    assert "![Still from the film of this run. Status: not comparable (no reported KPIs).](frame.png)" in text
    with pytest.raises(article.ArticleError, match="never invented"):
        article.build(demo_report, "linkedin", out=tmp_path / "b.md", figures=[tmp_path / "ghost.png"])


# ---------------------------------------------------------------------------------------------------- publish
def test_publish_writes_manifest_and_never_touches_the_network(demo_report, tmp_path, monkeypatch):
    import socket
    import urllib.request

    def boom(*a, **k):
        raise AssertionError("network used")
    monkeypatch.setattr(socket, "socket", boom)
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    monkeypatch.setenv("MUSE_AI_KEY", "k")
    fig = tmp_path / "f.png"
    fig.write_bytes(b"png")
    film = tmp_path / "film.mp4"
    film.write_bytes(b"mp4")
    art = article.build(demo_report, "linkedin", out=tmp_path / "pap/article.md", figures=[fig])
    man = article.publish(art, video=film, muse=False, out_root=tmp_path / "out")
    pub = tmp_path / "out/demo-oslofjord-supply/publish"
    m = json.loads((pub / "manifest.json").read_text())
    assert (pub / "article.md").is_file() and (pub / "figures/f.png").is_file()
    assert m["status"] == "not comparable (no reported KPIs)" and m["article"]["sha256"] and m["figures"][0]["sha256"]
    assert m["video"]["sha256"] and m["muse"]["result"] == "not requested" and man["bundle"] == str(pub)
    assert json.loads((tmp_path / "pap/published.json").read_text())["staged"] is True


def test_muse_only_when_requested_and_keyed(demo_report, tmp_path, monkeypatch):
    from offsim.publish import muse
    calls = []
    monkeypatch.setattr(muse, "upload", lambda *a, **k: calls.append((a, k)) or {"id": "x"})
    film = tmp_path / "film.mp4"
    film.write_bytes(b"mp4")
    art = article.build(demo_report, "linkedin", out=tmp_path / "p/article.md")
    monkeypatch.delenv("MUSE_AI_KEY", raising=False)
    m = article.publish(art, video=film, muse=True, out_root=tmp_path / "o")
    assert not calls and "MUSE_AI_KEY" in m["muse"]["result"]
    monkeypatch.setenv("MUSE_AI_KEY", "k")
    article.publish(art, video=film, muse=False, out_root=tmp_path / "o")
    assert not calls
    m = article.publish(art, video=film, muse=True, out_root=tmp_path / "o")
    assert len(calls) == 1 and m["muse"]["result"] == {"id": "x"}


def test_publish_refuses_a_stale_article(demo_report, tmp_path):
    rp = tmp_path / "report.json"
    rp.write_text(demo_report.read_text())
    art = article.build(rp, "linkedin", out=tmp_path / "a.md")
    r = json.loads(rp.read_text())
    r["kpis"]["distance_km"] = 1.0
    rp.write_text(json.dumps(r))
    with pytest.raises(article.ArticleError, match="changed"):
        article.publish(art, out_root=tmp_path / "o")
    with pytest.raises(article.ArticleError, match="not an article"):
        article.publish(tmp_path / "x.md", out_root=tmp_path / "o")


# ---------------------------------------------------------------------------------------------------- CLI and funnel
def test_cli_article_and_publish_parse(capsys):
    with pytest.raises(SystemExit) as e:
        main(["article", "--help"])
    assert e.value.code == 0 and "--template" in capsys.readouterr().out
    a = build_parser().parse_args(["article", "x", "--template", "thought", "--figure", "a.png", "--figure", "b.png"])
    assert a.template == "thought" and a.figure == ["a.png", "b.png"]
    assert build_parser().parse_args(["publish", "x", "--muse"]).muse is True


def test_cli_article_writes_file_and_refuses_with_exit_2(demo_report, tmp_path, rep, capsys):
    out = tmp_path / "x.md"
    assert main(["article", str(demo_report), "--out", str(out)]) == 0 and out.is_file()
    bad = dict(rep, status="stopped at gate 1_plan")
    assert main(["article", str(write(tmp_path, bad, "bad.json")), "--out", str(tmp_path / "y.md")]) == 2
    assert "refused" in capsys.readouterr().err
    assert main(["article", str(tmp_path / "missing.json"), "--out", str(tmp_path / "z.md")]) == 2


def test_funnel_article_and_publish_are_real_and_resolve():
    stages = {s["id"]: s for s in load_funnel()}
    for sid in ("article", "publish"):
        s = stages[sid]
        assert not s.get("planned") and s["command"]
        cmd = conductor.render(s["command"], context("demo-oslofjord-supply"))
        argv = shlex.split(cmd)
        assert argv[:3] == ["python", "-m", "offsim"] and "{" not in cmd
        ns = build_parser().parse_args(argv[3:])
        assert ns.cmd == sid
    assert stages["article"]["exit"] == {"file": ["{paper_dir}/article.md"]}
    assert stages["publish"]["kind"] == "decide" and stages["publish"]["exit"] == {"file": ["{paper_dir}/published.json"]}
