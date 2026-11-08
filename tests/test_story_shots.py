"""Standard-pipeline shot types: section + findings, narration chosen from measurements, story.check rules.

Rendering is tiny (270x338, <= 6 frames, short spin-up); no full film is rendered here."""
import copy
import math
import shutil

import numpy as np
import pytest
from PIL import Image

from offsim.montecarlo import run_ensemble
from offsim.motion import findings, narrate, section, story
from test_montecarlo import FakeEngine, plans, setup

SIZE = (270, 338)


# ------------------------------------------------------------------------------------------ narrate
@pytest.mark.parametrize("expr", [
    "__import__('os').system('echo hi') == 0",
    "x.__class__ == 1",
    "(1).real > 0",
    "len(x) > 1",
    "open('f') == 1",
    "x[0] > 1",
    "(lambda: 1)() == 1",
    "[a for a in x] == 1",
    "min(x, key=abs) > 0",
    "x ** 2 > 1",
    "x if x else 1",
    "x in (1, 2)",
    "abs.__call__(x) > 0",
])
def test_narrate_refuses_unsafe_expressions(expr):
    with pytest.raises(narrate.NarrationError):
        narrate.evaluate(expr, {"x": 3.0})


def test_narrate_evaluates_the_allowed_language():
    v = {"a": 6.0, "b": 2.0, "name": "supported", "kpis.d": 100.0}
    assert narrate.evaluate("a / b == 3 and not (a < b)", v)
    assert narrate.evaluate("abs(b - a) >= 4 or a < 0", v)
    assert narrate.evaluate("max(a, b) - min(a, b) + 0 == 4", v)
    assert narrate.evaluate("name == 'supported'", v)
    assert narrate.evaluate("kpis.d > 99", v)                       # dotted key present in values
    assert narrate.evaluate("1 < b < 3", v)
    assert narrate.names_used("a > b and kpis.d < 1") == {"a", "b", "kpis.d"}


def test_narrate_missing_names_are_errors_never_defaults():
    with pytest.raises(narrate.NarrationError, match="not measured"):
        narrate.evaluate("zzz > 1", {"a": 1})
    with pytest.raises(narrate.NarrationError, match="attribute"):
        narrate.evaluate("a.b > 1", {"a": 1})                       # dotted but not a measured key
    with pytest.raises(narrate.NarrationError, match="not measured"):
        narrate.choose([{"text": "value {zzz:.0f}"}], {"a": 1})
    with pytest.raises(narrate.NarrationError):
        narrate.evaluate("a / 0 > 1", {"a": 1})


RULES = [{"when": "hot >= 5", "text": "reaches the deck: +{hot:.0f} C"},
         {"when": "low > 0 and hot < 5", "text": "stays {low:.0f} m above the deck"},
         {"text": "never arrives"}]


def test_choose_first_match_wins_and_default():
    assert narrate.choose(RULES, {"hot": 12.4, "low": 3.0}) == "reaches the deck: +12 C"
    assert narrate.choose(RULES, {"hot": 1.0, "low": 3.0}) == "stays 3 m above the deck"
    assert narrate.choose(RULES, {"hot": 1.0, "low": 0.0}) == "never arrives"
    with pytest.raises(narrate.NarrationError, match="no narration rule matched"):
        narrate.choose(RULES[:2], {"hot": 1.0, "low": 0.0})
    assert narrate.validate_rules(RULES[:2]) and not narrate.validate_rules(RULES)        # default required for check
    assert any("only the final" in p for p in narrate.validate_rules([{"text": "x"}, {"when": "a>1", "text": "y"}]))


def test_text_placeholders_have_no_attribute_or_index_access():
    with pytest.raises(narrate.NarrationError):
        narrate.choose([{"text": "{a.real}"}], {"a": 1.0})
    assert narrate.choose([{"text": "{k.d:.1f}"}], {"k.d": 2.25}) == "2.2"


# ------------------------------------------------------------------------------------------ synthetic ensemble
def make_report(with_ensemble=True, min_effect_in_report=False, ok=True):
    prob, world, wx = setup(6, 120)
    ens = run_ensemble(prob, None, world, FakeEngine(), wx, [0, 1, 2], variants=plans())
    ens.compare("wait_s", "better", "base")
    ens.compare("wait_s", "twin", "base")
    rep = {"status": "re-run under assumptions", "kpis": {"distance_km": 113.3, "makespan_s": 9000.0},
           "gates": {"0_provenance": {"pass": True}, "1_x": {"pass": True}, "2_x": {"pass": True}, "3_contract": {"pass": True}}}
    if with_ensemble:
        rep["ensemble"] = ens.to_report()
        if not ok:
            rep["ensemble"]["ok"] = False
    return rep, ens, wx


FAN = {"type": "findings", "kind": "fan", "seconds": 3, "kpi": "wait_s", "unit": "h", "scale": 1 / 3600, "fmt": "{:.1f}",
       "compare": ["better", "base"], "better": "lower", "min_effect": 0.2,
       "kicker": "WEATHER ENSEMBLE", "headline": {"top": "HOW LONG DO", "accent": "SHIPS", "rest": "WAIT?"},
       "narration": [{"when": "status == 'supported'", "text": "Median wait {fan.better.p50:.1f} h against {fan.base.p50:.1f} h:\n"
                                                              "{effect_pct:.0f} % better, status {status}."},
                     {"text": "Not clearly better: status {status}."}]}
PAIRED = {**FAN, "kind": "paired", "a": "better", "b": "base",
          "narration": [{"when": "status == 'supported' and mean_diff < 0", "text": "Paired over {n_pairs:.0f} runs, {rel_pct:.0f} % wait."},
                        {"text": "No clear paired difference: {status}."}]}
SEC_NARR = [{"when": "deck_excess_max > 1000000", "text": "never chosen"},
            {"when": "deck_excess_max >= 0", "text": "peak +{deck_excess_max:.2f} K\nu10 {u10:.0f} m/s hs {hs:.1f} m"},
            {"text": "default"}]


def sec_shot(**kw):
    s = {"type": "section", "seconds": 0.2, "vessel": "psv",
         "hs": {"value": 2.0, "assumption": True}, "tp": {"value": 6.5, "src": "NORA3 outer fjord, Tp mean"},
         "u10": {"value": 15, "assumption": True}, "t_exh": {"value": 520, "assumption": True},
         "kicker": "TEST  ·  SIMULATED", "headline": {"top": "WHERE DOES THE", "accent": "EXHAUST", "rest": "GO?"},
         "map": None, "narration": SEC_NARR}
    s.update(kw)
    return s


# ------------------------------------------------------------------------------------------ section
def test_flatten_gives_report_refs_and_ensemble_aliases():
    rep, ens, _ = make_report()
    flat = narrate.flatten(rep)
    assert flat["kpis.distance_km"] == 113.3
    assert flat["ensemble.wait_s.base.p50"] == ens.quantiles("wait_s").loc["base", "p50"]
    assert "ensemble.wait_s.p50" not in flat                        # several variants: no ambiguous alias
    only = narrate.flatten({"ensemble": {"quantiles": {"k": {"base": {"p50": 2.0}}}}})
    assert only["ensemble.k.p50"] == 2.0


def test_section_shot_renders_tiny_and_narration_comes_from_measurements(tmp_path):
    shot = sec_shot()
    res = section.run_section(shot, None, tmp_path / "f", fps=30, report=None, size=SIZE, spinup_steps=20, log=lambda *_: None)
    assert res["n"] == 6 and len(res["frames"]) == 6
    assert Image.open(res["frames"][0]).size == SIZE
    m = res["measured"]
    assert set(section.MEASURED_NAMES) <= set(m) and math.isfinite(m["deck_excess_max"])
    assert res["deck"][0] == f"peak +{m['deck_excess_max']:.2f} K"          # first matching rule, filled from the solver
    assert res["deck"][1] == "u10 15 m/s hs 2.0 m"
    # the other branch is chosen when the measurement says so (threshold below the measured value)
    flip = sec_shot(narration=[{"when": f"deck_excess_max < {m['deck_excess_max'] - 1}", "text": "x"}, {"text": "fallback"}])
    res2 = section.run_section(flip, None, tmp_path / "g", 30, None, SIZE, 0, spinup_steps=20, log=lambda *_: None)
    assert res2["deck"][0] == "fallback" and len(res2["frames"]) == 1
    # deterministic: same inputs, same numbers
    assert res2["measured"] == m


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")
def test_render_section_shot_writes_mp4(tmp_path):
    out = tmp_path / "s.mp4"
    section.render_section_shot(sec_shot(seconds=0.1), {}, out, 30, None, size=SIZE, spinup_steps=10, log=lambda *_: None)
    assert out.exists() and out.stat().st_size > 0 and not (tmp_path / "s_frames").exists()


def test_section_refuses_unsourced_inputs_and_missing_map_layers(tmp_path):
    bad = sec_shot(hs={"value": 2.0})
    assert any("hs" in p and "no src" in p for p in section.problems(bad))
    with pytest.raises(ValueError, match="section shot refused"):
        section.run_section(bad, None, tmp_path, 30, None, SIZE)
    assert any("narration" in p for p in section.problems(sec_shot(narration=None)))
    assert any("names not measured" in p for p in section.problems(sec_shot(narration=[{"text": "{nothing_measured:.0f}"}])))
    with pytest.raises(FileNotFoundError):
        section.run_section(sec_shot(map={"world": "no-such-world", "run": "out/none", "agent": "X"}), None, tmp_path, 30, None, SIZE)


def test_wrapper_tool_builds_the_original_gale_shot():
    import section_film
    shot = section_film.gale_shot()
    assert section.problems(shot) == []
    assert section.assumption_line(shot) == ("DRAFT: vessel geometry, exhaust temperature (520 K) and weather are assumptions; "
                                              "ship motion display-grade.")
    # the original two sentences are rules over the measurements
    hot = narrate.choose(shot["narration"], {"deck_excess_max": 9.0, "plume_seen": 1.0, "plume_min_m": 3.0})
    assert "up to +9 °C" in hot
    clear = narrate.choose(shot["narration"], {"deck_excess_max": 1.0, "plume_seen": 1.0, "plume_min_m": 3.4})
    assert "never comes lower than 3 m" in clear


# ------------------------------------------------------------------------------------------ findings
def test_fan_renders_with_spread_and_status_and_builds_in(tmp_path):
    rep, ens, _ = make_report()
    res = findings.run_findings(FAN, rep, tmp_path, fps=2, size=SIZE, log=lambda *_: None)
    assert res["n"] == 6 and len(res["frames"]) == 6
    imgs = [np.asarray(Image.open(f)) for f in res["frames"]]
    assert imgs[0].shape[:2] == (SIZE[1], SIZE[0])
    assert not np.array_equal(imgs[0], imgs[-1]) and np.array_equal(imgs[-1], imgs[-1])    # animated build-in
    q = ens.quantiles("wait_s")
    d = res["data"]
    assert d["status"] == "supported" and [r["label"] for r in d["rows"]] == ens.variants
    assert d["rows"][0]["p50"] == pytest.approx(q.loc["base", "p50"] / 3600)
    assert all(r["p10"] <= r["p50"] <= r["p90"] for r in d["rows"])           # spread travels with every number
    assert d["axis"][0] <= min(r["p10"] for r in d["rows"]) and d["axis"][1] >= max(r["p90"] for r in d["rows"])
    base_p50 = q.loc["base", "p50"] / 3600
    assert res["deck"][0] == f"Median wait {q.loc['better', 'p50'] / 3600:.1f} h against {base_p50:.1f} h:"


def test_paired_renders_with_status_word(tmp_path):
    rep, ens, _ = make_report()
    res = findings.run_findings(PAIRED, rep, tmp_path, fps=2, size=SIZE, log=lambda *_: None)
    d = res["data"]
    c = ens.compare("wait_s", "better", "base")
    assert d["mean"] == pytest.approx(c.mean / 3600) and d["ci"][1] < 0 and d["status"] == "supported"
    assert d["n_pairs"] == c.n
    assert res["deck"][0].startswith(f"Paired over {c.n} runs")
    # a twin variant (identical plan, CRN) is a zero difference and must not be called supported
    twin = findings.run_findings({**PAIRED, "a": "twin"}, rep, tmp_path / "t", fps=2, size=SIZE, log=lambda *_: None)
    assert twin["data"]["status"] != "supported" and twin["deck"][0].startswith("No clear paired difference")
    # a pre-registered decision in the report wins over the shot threshold
    rep2 = copy.deepcopy(rep)
    rep2["ensemble"]["decision"] = {"kpi": "wait_s", "compare": ["better", "base"], "status": "inconclusive", "min_effect": 0.9}
    assert findings.measure(PAIRED, rep2)[0]["status"] == "inconclusive"


def test_findings_refuse_without_a_usable_ensemble(tmp_path):
    rep, _, _ = make_report(with_ensemble=False)
    for shot in (FAN, PAIRED):
        with pytest.raises(findings.FindingsError, match="no `ensemble` block"):
            findings.run_findings(shot, rep, tmp_path, 2, size=SIZE, log=lambda *_: None)
    failed, _, _ = make_report(ok=False)
    with pytest.raises(findings.FindingsError, match="not true"):
        findings.measure(FAN, failed)
    unvalidated, _, _ = make_report()
    unvalidated["ensemble"]["validated"] = False
    with pytest.raises(findings.FindingsError, match="validate=False"):
        findings.measure(FAN, unvalidated)
    rep, _, _ = make_report()
    with pytest.raises(findings.FindingsError, match="status word"):
        findings.measure({k: v for k, v in PAIRED.items() if k != "min_effect"}, rep)
    with pytest.raises(findings.FindingsError, match="comparison"):
        findings.measure({k: v for k, v in FAN.items() if k != "compare"}, rep)          # several variants need a status
    with pytest.raises(findings.FindingsError, match="per-run rows"):
        findings.fan(rep, "wait_s", by="year")


def test_state_gantt_from_trajectory(tmp_path):
    rep, _, wx = make_report()
    prob, world, wxs = setup(1, 120)
    sim = FakeEngine().simulate(prob, plans()["base"], world, wxs[0], 0)
    shot = {**FAN, "kind": "state_gantt", "narration": [{"when": "wait_h > 0", "text": "waits {wait_h:.1f} h of {span_h:.1f} h"},
                                                         {"text": "no waiting"}]}
    res = findings.run_findings(shot, rep, tmp_path, 2, traj=sim.traj, agents=sim.agents, size=SIZE, log=lambda *_: None)
    d = res["data"]
    assert d["lanes"][0]["segments"][0][2] == "load" and "wait" in d["states"]
    assert res["values"]["wait_h"] == pytest.approx(d["totals_h"]["wait"])
    assert res["deck"][0].startswith("waits ") or res["deck"][0] == "no waiting"
    with pytest.raises(findings.FindingsError):
        findings.run_findings(shot, rep, tmp_path / "x", 2, traj=None, size=SIZE, log=lambda *_: None)


def test_weather_year_and_ghost_tracks_data_prep(tmp_path):
    rep, _, wx = make_report()
    wy = findings.weather_year(wx[:2], {"hs_m": 2.5})
    assert len(wy["years"]) == 2 and all(0 <= y["operable_frac"] <= 1 for y in wy["years"])
    prob, world, wxs = setup(1, 120)
    for k in range(3):
        d = tmp_path / f"run{k}"
        d.mkdir()
        FakeEngine().simulate(prob, plans()["base"], world, wxs[0], k).traj.to_csv(d / "trajectory.csv", index=False)
    g = findings.ghost_tracks(rep, tmp_path, n=2, highlight="run0")
    assert g["n_runs"] == 2 and g["n_available"] == 3 and g["highlight"] == "run0" and g["tracks"][0]["coords"]
    with pytest.raises(findings.FindingsError):
        findings.ghost_tracks(make_report(with_ensemble=False)[0], tmp_path)


# ------------------------------------------------------------------------------------------ story.check
@pytest.fixture
def all_tools(monkeypatch):
    monkeypatch.setattr(story, "tools", lambda: {k: True for k in ("manim", "latex", "node", "ffmpeg", "chrome", "hyperframes")})


def board(*shots):
    return {"id": "t", "run": "out/none", "scenario": "x", "format": "vertical", "shots": [copy.deepcopy(s) for s in shots]}


def test_check_accepts_section_and_findings_storyboard(all_tools):
    rep, _, _ = make_report()
    sb = board(sec_shot(seconds=4), FAN, PAIRED)
    assert story.check(sb, rep) == []
    sb["shots"][0]["type"] = "diptych"
    sb["shots"][0]["map"] = {"world": "oslofjord", "run": "out/none", "agent": "PSV-1"}
    assert story.check(sb, rep) == []                                 # alias; absent world data is not a check failure


def test_check_rejects_unsourced_section_inputs_and_bad_narration(all_tools):
    rep, _, _ = make_report()
    bad = sec_shot(seconds=4, u10={"value": 15})
    probs = story.check(board(bad), rep)
    assert any("section" in p and "u10" in p and "no src" in p for p in probs)
    no_narr = story.check(board(sec_shot(seconds=4, narration=None)), rep)
    assert any("narration rules missing" in p for p in no_narr)
    typo = story.check(board(sec_shot(seconds=4, narration=[{"when": "deck_exces_max > 1", "text": "a"}, {"text": "b"}])), rep)
    assert any("names not measured" in p for p in typo)
    no_default = story.check(board(sec_shot(seconds=4, narration=[{"when": "hs > 1", "text": "a"}])), rep)
    assert any("default" in p for p in no_default)
    assert any("diptych" in p for p in story.check(board(sec_shot(seconds=4, type="diptych")), rep))
    unsafe = story.check(board(sec_shot(seconds=4, narration=[{"when": "__import__('os')", "text": "a"}, {"text": "b"}])), rep)
    assert any("narration rule 0" in p for p in unsafe)


def test_check_rejects_findings_without_ensemble_or_status(all_tools):
    no_ens, _, _ = make_report(with_ensemble=False)
    assert any("no `ensemble` block" in p for p in story.check(board(FAN), no_ens))
    rep, _, _ = make_report()
    nostatus = {k: v for k, v in PAIRED.items() if k != "min_effect"}
    assert any("status word" in p for p in story.check(board(nostatus), rep))
    assert any("kind" in p for p in story.check(board({**FAN, "kind": "ghost_tracks"}), rep))
    assert any("unknown type" in p for p in story.check(board({"type": "nope", "seconds": 4}), rep))
    gantt = {**FAN, "kind": "state_gantt"}
    assert any("trajectory" in p for p in story.check(board(gantt), rep))


def test_check_validates_card_narration(all_tools, monkeypatch):
    rep, _, _ = make_report()
    card = {"type": "card", "seconds": 4, "kpis": [{"label": "km", "value": "report:kpis.distance_km"}],
            "narration": [{"when": "kpis.distance_km > 100", "text": "{kpis.distance_km:.0f} km sailed"}, {"text": "short run"}]}
    assert story.check(board(card), rep) == []
    card["narration"][0]["text"] = "{kpis.nothing:.0f} km sailed"
    assert any("names not measured" in p for p in story.check(board(card), rep))
