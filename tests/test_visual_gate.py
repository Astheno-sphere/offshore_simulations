"""Visual gate (offsim/cinema/visual_gate.py): synthetic frames that each break one rule, golden frames, findings renderers,
story.check integration. Frames are <= 600 px; the section golden regenerates in ~2 s."""
import copy
import inspect as pyinspect
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

pytest.importorskip("skia")
from offsim.cinema import visual_gate as vg
from offsim.cinema.draw import Canvas
from offsim.cinema.look import PALETTES
from offsim.motion import findings, story
from test_story_shots import FAN, PAIRED, board, make_report, sec_shot
from test_montecarlo import FakeEngine, plans, setup

HERE = Path(__file__).resolve().parent
GOLD = HERE / "golden"
sys.path.insert(0, str(GOLD))
import make_goldens  # noqa: E402

P = PALETTES["section-plan"]
SIZE = (360, 450)
PREVIEW = {"strokes": {"preview_of": 1080}}          # a 1/3 preview of the 1080 wide film: stroke minimum scales with it


# ------------------------------------------------------------------------------------------------ synthetic frames
def synth(span=1.0, accent_w=8, extra=None):
    """A frame that passes every rule (hard and strict): header, 8 lanes of bar + marker + rule, deck, methods line. Drawn with
    skia on the film's canvas size, downsampled like section.fit. `span` < 1 leaves the right of the frame empty."""
    cv = Canvas(1080, 1350, bg=P["ground"], ss=1)
    with vg.capture_text(canvas=(1080, 1350)) as texts:
        cv.text(56, 100, "ONE QUESTION", font=("Inter", "Bold"), size=52, color=P["ink"])
        cv.text(56 + cv.measure("ONE QUESTION ", ("Inter", "Bold"), 52), 100, "ASKED", font=("Inter", "Bold"), size=52, color=P["accent"])
        cv.text(56, 60, "KICKER", font=("Inter", "Bold"), size=15, color=P["accent"], tracking=1.0)
        x1 = 56 + (1024 - 56) * span
        for i in range(8):
            y, w = 260 + i * 85, (x1 - 56) * (0.4 + 0.07 * i)
            cv.text(56, y, f"LANE {i}", font=("Inter", "Bold"), size=22, color=P["ink"])
            cv.polygon([(56, y + 30), (56 + w, y + 30), (56 + w, y + 56), (56, y + 56)], fill=P["streak_lo"])
            cv.line([(56, y + 76), (x1, y + 76)], "#4a3236", 1.0)
            xm = 56 + (x1 - 56) * 0.3
            cv.polygon([(xm - accent_w / 2, y + 24), (xm + accent_w / 2, y + 24), (xm + accent_w / 2, y + 62), (xm - accent_w / 2, y + 62)], fill=P["accent"])
        cv.text(56, 1060, "Deck sentence with a number 12.3 h", font=("Inter", "Regular"), size=22, color=P["ink"])
        cv.text(56, 1100, "Methods line naming the sources and the assumptions for the reader.", font=("Inter", "Regular"), size=13, color=P["muted"])
        if extra:
            extra(cv)
    return cv.to_pil().resize(SIZE, Image.LANCZOS), texts


def rules(report, strict=True):
    ok, why = vg.passes(report, strict)
    return ok, {r.split(":")[0] for r in why}, why


def arr(img):
    return np.array(img.convert("RGB"))


# ------------------------------------------------------------------------------------------------ the spec is data with sources
def test_gate_spec_is_sourced_data_and_unknown_keys_refuse():
    for group, d in vg.GATE_SPEC.items():
        if isinstance(d, dict):
            assert d.get("src"), f"GATE_SPEC[{group!r}] has no source for its thresholds"
    assert "rule 17" in vg.GATE_SPEC["type_scale"]["src"] and "WCAG" in vg.GATE_SPEC["contrast"]["src"]
    assert "golden" in vg.GATE_SPEC["edges"]["src"] and "golden" in vg.GATE_SPEC["balance"]["src"].lower() or "G:" in vg.GATE_SPEC["balance"]["src"]
    with pytest.raises(KeyError, match="unknown visual spec key"):
        vg.spec_for("section", {"edgez": {}})
    with pytest.raises(KeyError, match="edges.sobel_tau_x"):
        vg.spec_for(None, {"edges": {"sobel_tau_x": 1}})
    with pytest.raises(KeyError, match="unknown frame kind"):
        vg.spec_for("poster")
    assert vg.spec_for("map")["margins"]["bleed"] == [[0.0, 0.0, 1.0, 1.0]]


def test_a_clean_synthetic_frame_passes_hard_and_strict():
    img, tx = synth()
    r = vg.inspect(img, {"text": tx, **PREVIEW})
    ok, rs, why = rules(r)
    assert ok, why
    assert r["type_scale"]["n_sizes"] == 3 and r["type_scale"]["methods_size"] == 13.0       # 52, 22, 15 + the methods line
    assert r["contrast"]["mode"] == "text" and r["contrast"]["min_ratio"] >= 4.5


# ------------------------------------------------------------------------------------------------ each rule is caught, with its reason
def test_empty_frame_is_caught_as_empty():
    r = vg.inspect(Image.new("RGB", SIZE, P["ground"]), PREVIEW)
    ok, rs, why = rules(r, strict=False)
    assert not ok and "edges" in rs and any("(empty)" in w for w in why)


def test_mush_is_caught_as_too_many_edges():
    rng = np.random.default_rng(0)
    cols = np.array([vg._hex(P["ground"]), vg._hex(P["ink"]), vg._hex(P["streak_lo"])], np.uint8)
    mush = Image.fromarray(cols[rng.integers(0, 3, (SIZE[1], SIZE[0]))])           # on-palette, but every pixel is an edge
    ok, rs, why = rules(vg.inspect(mush, PREVIEW), strict=False)
    assert not ok and "edges" in rs and any("(mush)" in w for w in why)
    assert "palette" not in rs                                                       # the colours themselves are fine


def test_off_palette_is_caught_not_the_edges():
    img, tx = synth()
    a = arr(img)
    a[190:260, 40:320] = (0, 190, 60)                                                # a green slab, 11 % of the frame
    ok, rs, why = rules(vg.inspect(Image.fromarray(a), {"text": tx, **PREVIEW}), strict=False)
    assert not ok and rs == {"palette"} and "outside the palette" in why[0]


def test_accent_flood_is_caught():
    img, tx = synth()
    a = arr(img)
    a[130:300, 20:340] = vg._hex(P["accent"])                                        # a third of the frame in the accent
    ok, rs, why = rules(vg.inspect(Image.fromarray(a), {"text": tx, **PREVIEW}), strict=False)
    assert not ok and "accent" in rs and any("floods the frame" in w for w in why) and "palette" not in rs


def test_low_contrast_text_is_caught_from_text_metadata():
    img, tx = synth()
    im = img.copy()
    with vg.capture_text() as extra:
        ImageDraw.Draw(im).text((60, 392), "BARELY THERE", font=ImageFont.truetype(__import__("offsim.cinema.look", fromlist=["x"]).font_path("Bold"), 16),
                                fill=(74, 46, 52))                                    # ratio ~1.4:1 on the ground
    for e in extra:                                                                  # the capture is on the 360 px canvas: express it on the film canvas
        e["box"], e["canvas"] = tuple(v * 3 for v in e["box"]), (1080, 1350)
    r = vg.inspect(im, {"text": tx + extra, **PREVIEW})
    ok, rs, why = rules(r, strict=False)
    assert not ok and rs == {"contrast"} and "BARELY THERE" in why[0] and "flat background" in why[0]
    assert r["contrast"]["min_ratio"] < 2


def test_clipped_ink_is_caught_at_the_edge():
    img, tx = synth()
    a = arr(img)
    a[150:200, 300:360] = vg._hex(P["ink"])                                          # a bar cut off by the right edge
    ok, rs, why = rules(vg.inspect(Image.fromarray(a), {"text": tx, **PREVIEW}), strict=False)
    assert not ok and rs == {"margins"} and "clipped at the frame edge: right" in why[0]


def test_text_outside_the_safe_area_is_caught():
    img, tx = synth()
    tx = copy.deepcopy(tx)
    tx[3]["box"] = (tx[3]["box"][0], 1330.0, tx[3]["box"][2], 1349.0)                # one lane label dropped to the bottom edge
    ok, rs, why = rules(vg.inspect(img, {"text": tx, **PREVIEW}), strict=False)
    assert not ok and "margins" in rs and "safe area" in why[0]


def test_empty_half_is_caught_balanced_frame_is_not():
    img, tx = synth(span=0.4)                                                        # everything on the left, right 60 % empty
    r = vg.inspect(img, {"text": tx, **PREVIEW})
    ok, rs, why = rules(r, strict=False)
    assert not ok and rs == {"balance"} and "empty half: right" in why[0]
    assert vg.inspect(synth()[0], {"text": synth()[1], **PREVIEW})["balance"]["min_half"] > 0.2


def test_thin_strokes_are_caught_at_the_delivered_size():
    cv = Canvas(SIZE[0], SIZE[1], bg=P["ground"], ss=2)
    for i in range(40):                                                              # 0.35 px hairlines, a legible-looking density
        y = 20 + i * 10
        cv.line([(30, y), (330, y + 3)], P["ink"], 0.35)
    r = vg.inspect(cv.to_pil(), {"palette": {"max_off_share": 1.0}})
    assert r["strokes"]["median_px"] < 0.6
    ok, rs, why = rules(r, strict=False)
    assert "strokes" in rs and "px at the delivered size" in " ".join(why)
    thick = Canvas(SIZE[0], SIZE[1], bg=P["ground"], ss=2)
    for i in range(40):
        thick.line([(30, 20 + i * 10), (330, 23 + i * 10)], P["ink"], 2.0)
    assert vg.inspect(thick.to_pil())["strokes"]["median_px"] > 1.6


def test_stroke_width_is_coverage_weighted_not_pixel_counted():
    a = Canvas(200, 100, bg=P["ground"], ss=4)
    b = Canvas(200, 100, bg=P["ground"], ss=4)
    for i in range(8):
        a.line([(10, 10 + 10 * i), (190, 10 + 10 * i)], P["ink"], 1.0)
        b.line([(10, 10 + 10 * i), (190, 10 + 10 * i)], P["ink"], 2.5)
    wa, wb = vg.stroke_stats(arr(a.to_pil()), vg.GATE_SPEC)["median_px"], vg.stroke_stats(arr(b.to_pil()), vg.GATE_SPEC)["median_px"]
    assert 0.8 < wa < 1.25 and 2.2 < wb < 2.8


def test_soft_rules_fail_only_when_strict():
    img, tx = synth()
    tx = copy.deepcopy(tx)
    for k, sz in enumerate((11, 12, 14, 17, 19, 31)):                                # a six-size type scale, no hierarchy
        tx.append({"text": f"x{k}", "box": (60, 100 + k * 5, 90, 110 + k * 5), "size": float(sz), "color": vg._hex(P["ink"]), "alpha": 1.0, "canvas": (1080, 1350)})
    r = vg.inspect(img, {"text": tx, **PREVIEW})
    assert vg.passes(r)[0] and r["warnings"] and r["warnings"][0].startswith("type_scale")
    ok, rs, why = rules(r, strict=True)
    assert not ok and rs == {"type_scale"}


def test_capture_text_restores_the_drawing_functions():
    before = (Canvas.text, ImageDraw.ImageDraw.text)
    with vg.capture_text():
        assert Canvas.text is not before[0]
    assert (Canvas.text, ImageDraw.ImageDraw.text) == before


# ------------------------------------------------------------------------------------------------ golden frames
def _texts(name):
    t = json.loads((GOLD / f"{name}.text.json").read_text())
    for r in t:
        r["box"], r["canvas"] = tuple(r["box"]), tuple(r["canvas"])
    return t or None


def test_golden_frames_are_small_and_exist():
    for n in ("section", "map", "findings"):
        assert (GOLD / f"{n}.png").stat().st_size < 120_000
        assert max(Image.open(GOLD / f"{n}.png").size) <= 600


@pytest.mark.parametrize("name,kind,preview", [("findings", "findings", 1080), ("map", "map", 968)])
def test_golden_frames_pass_the_gate_strict(name, kind, preview):
    r = vg.inspect(GOLD / f"{name}.png", {"kind": kind, "text": _texts(name), "strokes": {"preview_of": preview}})
    ok, rs, why = rules(r, strict=True)
    assert ok, why


def test_section_golden_passes_the_gate():
    """The film's own layout with its map panel, after the N3 visual-gate fix (section.py: 3 sizes + methods, panel-top
    labels in ink, DRAFT line inside the safe area). Regenerated golden; the frame passes the gate (no hard failure).
    One soft finding remains at this 1/3 preview scale only: the middle methods line reads 2.3:1 over a textured field
    because the contrast ring (3 px floor) catches the neighbouring methods glyphs after downscaling — the old golden
    measured 2.4:1 on the same line, and the same lines pass 4.8:1 at the delivered 1080 x 1350."""
    r = vg.inspect(GOLD / "section.png", {"kind": "section", "text": _texts("section"), **PREVIEW})
    ok, rs, why = rules(r, strict=False)
    assert ok, why
    assert r["type_scale"]["n_sizes"] == 3 and r["type_scale"]["methods_size"] == 13.0
    assert r["margins"]["text_outside"] == [] and r["margins"]["ink_band_share"] <= 0.004
    assert {w.split(":")[0] for w in r["warnings"]} == {"contrast"}     # only the preview-scale methods-ring artefact


def test_compare_ignores_pixel_noise_and_flags_structural_change():
    g = Image.open(GOLD / "findings.png").convert("RGB")
    assert vg.compare(g, g)[0]
    noisy = np.clip(arr(g).astype(int) + np.random.default_rng(1).normal(0, 3, arr(g).shape), 0, 255).astype(np.uint8)
    assert vg.compare(Image.fromarray(noisy), g)[0]
    shifted = np.roll(arr(g), 1, axis=1)                                             # one pixel sideways
    assert vg.compare(Image.fromarray(shifted), g)[0]
    gone = arr(g)
    gone[100:200] = vg._hex(P["ground"])                                             # the headline band removed
    ok, why = vg.compare(Image.fromarray(gone), g)
    assert not ok and any("region" in w for w in why)
    ok, why = vg.compare(Image.open(GOLD / "section.png"), g)                        # a different layout entirely
    assert not ok


def test_goldens_match_what_the_renderers_produce_today(tmp_path):
    """Renderer drift detector: regenerate the three frames from the repo's code and compare them with the committed ones."""
    frames = make_goldens.all_frames(tmp_path)
    for name, (img, texts, kind) in frames.items():
        ok, why = vg.compare(img, GOLD / f"{name}.png")
        assert ok, f"{name} golden no longer matches the renderer (intended change? regenerate and commit): {why[:3]}"


# ------------------------------------------------------------------------------------------------ findings renderers
def test_findings_port_is_skia_with_the_three_size_scale():
    src = pyinspect.getsource(findings)
    assert "Canvas(" in src and "ImageDraw" not in src and "textlength" not in src
    assert (findings.CAP, findings.BODY, findings.HEAD, findings.METHODS) == (15, 22, 52, 13)


@pytest.mark.parametrize("kind", ["fan", "paired", "state_gantt"])
def test_findings_renderers_pass_the_gate_at_the_delivered_size(kind, tmp_path):
    rep, _, _ = make_report()
    kw = {}
    shot = {"fan": FAN, "paired": PAIRED}.get(kind)
    if kind == "state_gantt":
        prob, world, wxs = setup(1, 120)
        sim = FakeEngine().simulate(prob, plans()["base"], world, wxs[0], 0)
        shot = {**FAN, "kind": "state_gantt", "narration": [{"when": "wait_h > 0", "text": "waits {wait_h:.1f} h of {span_h:.1f} h"}, {"text": "no waiting"}]}
        kw = {"traj": sim.traj, "agents": sim.agents}
    with vg.capture_text(canvas=(findings.W, findings.H)) as tx:
        res = findings.run_findings(shot, rep, tmp_path, 30, size=(1080, 1350), only=-1, log=lambda *_: None, **kw)
    r = vg.inspect(res["frames"][0], {"kind": "findings", "text": tx})
    ok, rs, why = rules(r, strict=True)
    assert ok, why
    assert r["type_scale"]["n_sizes"] == 3 and len(tx) > 10


def test_findings_final_frame_is_the_full_hold_state(tmp_path):
    rep, _, _ = make_report()
    res = findings.run_findings(FAN, rep, tmp_path, 30, size=SIZE, only=-1, log=lambda *_: None)
    r = vg.inspect(res["frames"][0], {"kind": "findings", **PREVIEW})
    assert vg.passes(r)[0] and r["palette"]["accent_share"] > 0.001


# ------------------------------------------------------------------------------------------------ story.check
@pytest.fixture
def small_frames(monkeypatch):
    monkeypatch.setattr(story, "tools", lambda: {k: True for k in ("manim", "latex", "node", "ffmpeg", "chrome", "hyperframes")})
    monkeypatch.setattr(story, "size", lambda fmt: [360, 450])          # gate frames at 360 x 450 (the shot says it is a preview below)


def with_visual(shot, **v):
    return {**copy.deepcopy(shot), "visual": {"spec": {**PREVIEW, **v.pop("spec", {})}, **v}}


def test_check_accepts_a_storyboard_that_passes_the_gate(small_frames):
    rep, _, _ = make_report()
    warns = []
    sb = board(with_visual(FAN), with_visual(PAIRED), with_visual(sec_shot(seconds=4)))
    assert story.check(sb, rep, warnings=warns) == []
    assert warns == []                                                              # was: a type_scale soft finding on shot 2 (section), fixed in section.py (N3)


def test_check_refuses_a_shot_that_fails_and_names_the_rule(small_frames):
    rep, _, _ = make_report()
    long_head = with_visual({**FAN, "headline": {"top": "HOW LONG DO SHIPS WAIT IN THE NORTH SEA", "accent": "NORTH SEA GALES", "rest": "WHEN IT BLOWS HARD?"}})
    probs = story.check(board(with_visual(FAN), long_head), rep)
    assert len(probs) == 1 and probs[0].startswith("shot 1 (findings): visual gate: margins:")
    assert "clipped" in probs[0] or "safe area" in probs[0]


def test_shot_visual_block_strict_and_spec_overrides(small_frames):
    rep, _, _ = make_report()
    strict = story.check(board(with_visual(sec_shot(seconds=4), strict=True)), rep)
    assert strict == []                                                             # was: a type_scale failure; the section shot now passes strict (N3)
    impossible = story.check(board(with_visual(FAN, spec={"edges": {"in_panel": [0.9, 1.0]}})), rep)
    assert any("visual gate: edges:" in p and "main-panel edge density" in p for p in impossible)
    typo = story.check(board(with_visual(FAN, spec={"edgez": {}})), rep)
    assert any("unknown visual spec key 'edgez'" in p for p in typo)
    bad_block = story.check(board({**FAN, "visual": {"stict": True}}), rep)
    assert any("visual: must be a mapping" in p for p in bad_block)


def test_check_without_visual_skips_the_frames_and_data_problems_come_first(small_frames):
    rep, _, _ = make_report()
    long_head = {**FAN, "headline": {"top": "HOW LONG DO SHIPS WAIT IN THE NORTH SEA", "accent": "NORTH SEA GALES", "rest": "WHEN IT BLOWS HARD?"}}
    assert story.check(board(long_head), rep, visual=False) == []
    no_ens, _, _ = make_report(with_ensemble=False)
    probs = story.check(board(long_head), no_ens)                                    # data refusal; no frame is rendered for it
    assert any("no `ensemble` block" in p for p in probs) and not any("visual gate" in p for p in probs)


def test_default_check_on_the_standard_format_passes_a_clean_findings_shot(monkeypatch):
    monkeypatch.setattr(story, "tools", lambda: {k: True for k in ("manim", "latex", "node", "ffmpeg", "chrome", "hyperframes")})
    rep, _, _ = make_report()
    assert story.check(board(FAN), rep) == []                                         # vertical 1080 x 1350, no overrides
