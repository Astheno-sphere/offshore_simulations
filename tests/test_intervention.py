"""The `intervention` shot kind (docs/VISUAL_GRAMMAR.md): physics tested as physics, streaks, the shot's refusals, the frame-budget gate, and
the pair that is the point of the package: our old `section` golden FAILS the frame budget judged as an intervention frame, and the
intervention stills PASS it. The physical margins asserted here are the ones coordination/reports/V1.md quotes."""
import copy
import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

pytest.importorskip("skia")
from offsim.cinema import rules
from offsim.cinema import visual_gate as vg
from offsim.motion import intervention as iv
from offsim.motion import narrate, story
from offsim.physics import masks
from offsim.physics.fluid2d import wind_profile
from offsim.physics.panel2d import PanelSolver, Subject
from offsim.physics.streaks import FieldStreaks

HERE = Path(__file__).resolve().parent
GOLD = HERE / "golden"
ROOT = HERE.parent
SB = ROOT / "offsim/papers/irinagribkovskaia-2025-tactical-helicopter/storyboard.intervention.yaml"

NX, NZ, DX, U = 100, 50, 0.5, 4.0                      # a 50 m x 25 m test panel; 4 m/s wind


def world():
    w = np.zeros((NX, NZ), bool)
    w[:, :2] = True                                    # the sea
    w[30:38, 2:16] = True                              # a 4 m x 7 m block: the platform
    return w


def solver(seed=1, subject=None, turbulence=0.08, **kw):
    z = (np.arange(NZ) + 0.5) * DX
    s = PanelSolver(NX, NZ, DX, world(), wind_profile(np.maximum(z - 1.0, 0.5), U), seed=seed, turbulence=turbulence, top="lid", **kw)
    if subject is not None:
        s.set_subject(subject)
    return s


def subject():
    """A body 5 m downwind of the block: solid cells and a downward momentum source above it (a helicopter, in small)."""
    solid = np.zeros((NX, NZ), bool)
    solid[48:56, 2:8] = True
    fz = np.zeros((NX, NZ))
    fz[46:58, 9:11] = -30.0
    return Subject("test subject", solid=solid, accel=(np.zeros((NX, NZ)), fz))


def run(s, seconds, dt=0.02):
    for _ in range(int(round(seconds / dt))):
        s.step(dt)


def mean_speed(s, seconds, box, dt=0.02):
    acc = []
    for _ in range(int(round(seconds / dt))):
        s.step(dt)
        uc, wc = s.cell_velocity()
        acc.append(np.hypot(uc, wc))
    m = np.mean(acc, axis=0)
    return m, m[box]


WAKE = (slice(58, 90), slice(2, 20))


# ------------------------------------------------------------------------------------------------ physics (not visual)
def test_mass_is_conserved_to_round_off():
    """Tolerance: max |div u| <= 1e-8 1/s on every fluid cell (the pressure solve is direct), and inflow flux = outflow flux to 1e-10 relative."""
    s = solver(subject=subject())
    run(s, 6.0)
    assert s.max_divergence() <= 1e-8
    fin, fout = s.net_flux()
    assert abs(fin - fout) <= 1e-10 * fin and fin > 0


def test_velocity_is_zero_inside_solid_cells_and_on_their_faces():
    s = solver(subject=subject())
    run(s, 4.0)
    assert np.all(s.u[~s.uo] == 0.0) and np.all(s.w[~s.wo] == 0.0)
    uc, wc = s.cell_velocity()
    assert np.all(uc[s.solid] == 0.0) and np.all(wc[s.solid] == 0.0)
    assert s.solid[48:56, 2:8].all() and s.solid[30:38, 2:16].all()


def test_the_subject_changes_the_wake_by_a_stated_margin():
    """Time-mean speed in the wake box with the subject on vs off differs by >= 15 % of the wind speed (measured: see the V1 report)."""
    on = solver(subject=subject())
    off = solver()
    run(on, 6.0), run(off, 6.0)
    m_on, w_on = mean_speed(on, 6.0, WAKE)
    m_off, w_off = mean_speed(off, 6.0, WAKE)
    fluid = ~(on.solid | off.solid)[WAKE]
    diff = np.abs(w_on - w_off)[fluid].mean() / U
    assert diff >= 0.15, diff


def test_switching_off_mid_run_converges_toward_the_subject_off_field():
    """The solver keeps running through the switch (schedule at t = 6 s). In a viscous, steady wake (nu = 1 m2/s, no inflow noise) the RMS speed
    difference to the subject-off run, taken just before the switch, falls to at most a third 12 s later (measured 0.52 -> 0.06 m/s).
    At the film's own low viscosity the wake sheds and decorrelates, so convergence there is statistical, not pointwise (V1 report)."""
    on, off = solver(subject=subject(), turbulence=0.0, nu=1.0), solver(turbulence=0.0, nu=1.0)
    on.schedule(6.0, None)
    run(on, 5.9), run(off, 5.9)
    fluid = ~(subject().solid | on.world | off.world)[WAKE]

    def dist():
        a, b = np.hypot(*on.cell_velocity())[WAKE], np.hypot(*off.cell_velocity())[WAKE]
        return float(np.sqrt(((a - b)[fluid] ** 2).mean()))
    d0 = dist()
    run(on, 12.0), run(off, 12.0)
    d1 = dist()
    assert on.subject is None
    assert d0 > 0.2 and d1 <= d0 / 3.0, (d0, d1)


def test_runs_are_deterministic_for_a_seed_and_differ_between_seeds():
    a, b, c = solver(seed=3), solver(seed=3), solver(seed=4)
    for s in (a, b, c):
        run(s, 3.0)
    assert np.array_equal(a.u, b.u) and np.array_equal(a.w, b.w)
    assert not np.array_equal(a.u, c.u)


def test_heat_source_rises_and_porous_region_drags():
    z = (np.arange(NZ) + 0.5) * DX
    hot = np.zeros((NX, NZ), bool)
    hot[20:24, 2:4] = True
    s = PanelSolver(NX, NZ, DX, np.zeros((NX, NZ), bool), np.full(NZ, 0.2), seed=1, turbulence=0.0, top="lid")
    s.set_subject(Subject("fire", heat=(hot, 600.0)))
    run(s, 4.0)
    uc, wc = s.cell_velocity()
    assert wc[18:30, 6:20].mean() > 0.05                # buoyant plume rises
    crown = np.zeros((NX, NZ), bool)
    crown[40:50, 5:15] = True
    p = PanelSolver(NX, NZ, DX, np.zeros((NX, NZ), bool), np.full(NZ, 2.0), seed=1, turbulence=0.0, top="lid")
    q = PanelSolver(NX, NZ, DX, np.zeros((NX, NZ), bool), np.full(NZ, 2.0), seed=1, turbulence=0.0, top="lid")
    p.set_subject(Subject("tree", porous=(crown, 3.0)))
    run(p, 4.0), run(q, 4.0)
    assert p.cell_velocity()[0][40:50, 5:15].mean() < 0.8 * q.cell_velocity()[0][40:50, 5:15].mean()


def test_pockets_closed_to_the_outflow_are_filled():
    m = np.zeros((20, 12), bool)
    m[5:10, 2:8] = True
    m[6:9, 3:7] = False                                # a sealed cavity inside the block
    assert masks.fill_pockets(m)[7, 5] and not masks.fill_pockets(m)[2, 5]


# ------------------------------------------------------------------------------------------------ streaks
def test_streaks_fill_the_panel_never_cross_a_solid_and_never_freeze():
    s = solver(subject=subject())
    run(s, 5.0)
    fs = FieldStreaks(s.solid, DX, n=1500, tail=10, seed=2, px_per_m=9.0)
    for _ in range(60):
        run(s, 1 / 30, dt=1 / 60)
        fs.advance(s.u, s.w, 1 / 30)
    h = fs.hist[fs.drawn()]
    assert len(h) > 1000
    for a in range(h.shape[1] - 1):                    # every drawn segment, sampled 5 times, lies in fluid cells
        p0, p1 = h[:, a], h[:, a + 1]
        ok = np.isfinite(p0[:, 0]) & np.isfinite(p1[:, 0])
        for t in np.linspace(0, 1, 5):
            q = (p0 * (1 - t) + p1 * t)[ok]
            i, k = np.clip(q[:, 0].astype(int), 0, NX - 1), np.clip(q[:, 1].astype(int), 0, NZ - 1)
            assert not s.solid[i, k].any()
    m = fs.measure()
    assert m["cover"] >= rules.FRAME_BUDGET["field_cover_min"] and m["static"] <= rules.FRAME_BUDGET["field_static_max"]


def test_streak_length_is_proportional_to_speed():
    s = solver()
    run(s, 5.0)
    fs = FieldStreaks(s.solid, DX, n=3000, tail=6, seed=5, px_per_m=9.0)
    for _ in range(20):
        run(s, 1 / 30, dt=1 / 60)
        fs.advance(s.u, s.w, 1 / 30)
    d = fs.drawn()
    uc, wc = s.cell_velocity()
    p = fs.p[d]
    spd = np.hypot(uc, wc)[np.clip(p[:, 0].astype(int), 0, NX - 1), np.clip(p[:, 1].astype(int), 0, NZ - 1)]
    length = np.hypot(*(fs.hist[d][:, 0] - fs.hist[d][:, 1]).T) * DX / (1 / 30)      # m/s travelled between the last two frames
    assert np.corrcoef(spd, length)[0, 1] > 0.9


# ------------------------------------------------------------------------------------------------ the shot: refusals and derivations
def shot():
    import yaml
    return copy.deepcopy(next(x for x in yaml.safe_load(SB.read_text())["shots"] if x["type"] == "intervention"))


def view(hours=48):
    rep = {"measured": {"flights_planned": 19.0}, "gates": {"0_provenance": {"pass": True}}, "status": "x"}
    return iv.weather_view(rep, {"weather": {"synthetic": {"n": 1, "hours": hours, "seed": 1}}})


def test_the_storyboard_shot_is_valid_and_draft_by_construction():
    v = view()
    assert iv.problems(shot(), v) == []
    assert v["weather"]["synthetic"] == 1 and iv.is_draft(shot(), v)


def test_literal_forcing_is_refused():
    s = shot()
    s["forcing"]["cases"][0]["wind"] = 5.0
    p = iv.problems(s, view())
    assert any("report: ref" in x and "literal" in x for x in p), p


def test_forcing_refs_resolve_against_the_runs_weather_not_invented_numbers():
    v = view()
    lo, hi = iv.resolve_ref("report:weather.q10.wind_mps", v), iv.resolve_ref("report:weather.max.wind_mps", v)
    assert lo < hi and hi == max(h["wind_mps"] for h in v["weather"]["hour"].values())
    s = shot()
    s["forcing"]["cases"][1]["wind"] = "report:weather.hour.9999.wind_mps"
    assert any("9999" in x for x in iv.problems(s, v))


def test_a_report_ref_to_nothing_is_refused():
    s = shot()
    s["forcing"]["cases"][1]["hs"] = "report:weather.nonexistent.hs_m"
    assert any("nonexistent" in x for x in iv.problems(s, view()))


def test_grammar_limits_are_enforced_from_rules():
    v = view()
    s = shot()
    s["headline"][0]["text"] = "THE S-92 MAKES ITS VERY OWN WIND ON DECK |TODAY|"
    assert any("words" in x for x in iv.problems(s, v))
    s = shot()
    s["body"][0]["text"] = " ".join(["word"] * (rules.INTERVENTION["body_words_max"] + 1))
    assert any("body" in x and "words" in x for x in iv.problems(s, v))
    s = shot()
    s["forcing"]["cases"].append(dict(s["forcing"]["cases"][0]))
    assert any("exactly 2 cases" in x for x in iv.problems(s, v))
    s = shot()
    s["seconds"] = 40
    assert any("film length" in x for x in iv.problems(s, v))
    s = shot()
    s["camera"] = {"zoom": 1}
    s["chart"] = {}
    assert any("no camera" in x and "chart" in x for x in iv.problems(s, v))
    s = shot()
    s["chips"]["states"] = ["a", "b"]
    assert any("chips.states" in x for x in iv.problems(s, v))
    s = shot()
    s["kicker"] = "{flights:.0f} FLIGHTS"
    assert any("{status}" in x for x in iv.problems(s, v))


def test_a_not_synthetic_sourced_shot_is_not_draft():
    s = shot()
    s["forcing"]["direction"] = {"value": "from_left", "src": "NORA3 wind direction"}
    s["subject_params"] = {k: {**x, "assumption": False, "src": "data sheet"} for k, x in s["subject_params"].items()}
    assert iv.is_draft(s, {"weather": {"synthetic": 0}}) is False
    assert iv.is_draft(s, {"weather": {"synthetic": 1}}) is True


def test_acts_and_event_dim_come_from_rules():
    a = iv.acts(20.0)
    assert a["before"] == (0.0, 8.0) and a["event"] == (8.0, 11.0) and a["after"] == (11.0, 20.0)
    lo, hi = rules.INTERVENTION["event_dim"]
    ds = [iv.dim_at(t, 20.0) for t in np.linspace(0, 20, 401)]
    assert ds[0] == 1.0 and ds[-1] == 1.0 and lo <= min(ds) <= hi and iv.dim_at(9.5, 20.0) == min(ds)
    assert [iv.state_index(t, 20.0) for t in (0, 7.9, 8.0, 10.9, 11.0, 19.9)] == [0, 0, 1, 1, 2, 2]


def test_story_registers_the_kind_and_refuses_literal_forcing():
    import yaml
    sb = yaml.safe_load(SB.read_text())
    rep = {"gates": {"0_provenance": {"pass": True}}, "measured": {"flights_planned": 19.0}, "status": "x"}
    probs = story.check(sb, rep, visual=False)
    assert [p for p in probs if "intervention" in p and "forcing" in p] == []
    sb["shots"][0]["forcing"]["cases"][0]["wind"] = 5.0
    probs = story.check(sb, rep, visual=False)
    assert any("intervention" in p and "report: ref" in p for p in probs), probs
    assert "intervention" in story.SHOT_TYPES and "intervention" in story.VISUAL_FRAME_SHOTS


# ------------------------------------------------------------------------------------------------ the frame budget
def texts_of(name):
    t = json.loads((GOLD / f"{name}.text.json").read_text())
    for r in t:
        r["box"], r["canvas"] = tuple(r["box"]), tuple(r["canvas"])
    return t


def judge(name, meta=None, **over):
    m = json.loads((GOLD / f"{name}.meta.json").read_text()) if meta is None else meta
    return vg.inspect(GOLD / f"{name}.png", {"kind": "intervention", "text": texts_of(name), "meta": m, "strokes": {"preview_of": 1080}, **over})


ACTS = ("before", "event", "after")
BUDGET_RULES = {"scene_height", "caption_height", "text_roles", "forbidden", "saturated_hues", "scale_figures", "field_cover", "field_static"}


def failed(r):
    return {f["rule"] for f in r["findings"] if not f["ok"] and f["severity"] == vg.HARD}


def test_frame_budget_numbers_are_read_from_rules_not_repeated():
    sp = vg.spec_for("intervention")
    for k, v in rules.FRAME_BUDGET.items():
        assert sp["frame_budget"][k] == v
    src = Path(vg.__file__).read_text()
    for lit in ("0.65", "0.28", "0.85"):
        assert f'"scene_height_min": {lit}' not in src and f'"field_cover_min": {lit}' not in src


@pytest.mark.parametrize("act", ACTS)
def test_our_intervention_stills_pass_the_frame_budget(act):
    r = judge(f"intervention_{act}")
    ok, why = vg.passes(r, strict=False)
    assert ok, why
    fb = r["frame_budget"]
    assert fb["scene_height"] >= rules.FRAME_BUDGET["scene_height_min"] and fb["caption_height"] <= rules.FRAME_BUDGET["caption_height_max"]
    assert fb["text_roles"] <= rules.FRAME_BUDGET["text_roles_max"] and fb["forbidden"] == [] and len(fb["saturated_hues"]) <= 1
    assert min(fb["scale_figures"]) >= rules.FRAME_BUDGET["scale_figures_min"]
    assert min(fb["field_cover"]) >= rules.FRAME_BUDGET["field_cover_min"] and max(fb["field_static"]) <= rules.FRAME_BUDGET["field_static_max"]


def test_the_old_section_golden_fails_the_frame_budget_judged_as_an_intervention_frame():
    """The point of the package: the dashboard-with-a-small-animation fails every budget rule that a frame can fail without metadata."""
    t = json.loads((GOLD / "section.text.json").read_text())
    for r in t:
        r["box"], r["canvas"] = tuple(r["box"]), tuple(r["canvas"])
    r = vg.inspect(GOLD / "section.png", {"kind": "intervention", "text": t, "strokes": {"preview_of": 1080}})
    ok, why = vg.passes(r, strict=False)
    assert not ok
    bad = failed(r)
    assert {"scene_height", "caption_height", "text_roles", "forbidden", "scale_figures", "field_cover", "field_static"} <= bad, bad
    assert r["frame_budget"]["scene_height"] < rules.FRAME_BUDGET["scene_height_min"]
    assert r["frame_budget"]["caption_height"] > rules.FRAME_BUDGET["caption_height_max"]
    assert {"chart", "footnote", "readout_row"} <= set(r["frame_budget"]["forbidden"])
    assert any(w.startswith("scene_height: scene panels take") for w in why)         # a stable message


def test_each_budget_rule_fails_alone_with_its_own_message():
    base = json.loads((GOLD / "intervention_before.meta.json").read_text())
    cases = {
        "scale_figures": ({**base, "scale_figures": [3, 1]}, "panel 2 holds 1 scale figures"),
        "field_cover": ({**base, "field": [{"cover": 0.5, "static": 0.0}, base["field"][1]]}, "covers 50% of panel 1"),
        "field_static": ({**base, "field": [base["field"][0], {"cover": 0.99, "static": 0.02}]}, "does not move between frames"),
        "forbidden": ({**base, "elements": ["scene_panel", "colour_bar"]}, "colour_bar"),
    }
    for rule, (meta, msg) in cases.items():
        r = judge("intervention_before", meta)
        assert failed(r) & BUDGET_RULES == {rule}, (rule, failed(r))
        assert any(msg in f["msg"] for f in r["findings"] if f["rule"] == rule)


def test_text_roles_and_saturated_hues_are_measured_from_the_frame():
    """An extra footnote paragraph and a second saturated hue in an otherwise clean frame are each caught."""
    from offsim.cinema.draw import Canvas
    img = Image.open(GOLD / "intervention_before.png").convert("RGB").resize((1080, 1350), Image.BICUBIC)
    cv = Canvas(1080, 1350, bg=None, ss=1)
    with vg.capture_text(canvas=(1080, 1350)) as extra:
        for k, y in enumerate((1180, 1205, 1230, 1255, 1280)):
            cv.text(56, y, f"EXTRA ROLE {k}" + "x" * (7 * k), font=("Inter", "Regular"), size=[13, 18, 24, 30, 36][k], color="#f2e9df")
        cv.polygon([(900, 1100), (1000, 1100), (1000, 1140), (900, 1140)], fill="#2f7fbf")             # a blue block: a second saturated hue
    over = cv.to_pil()
    img.paste(over, (0, 0), over)
    meta = json.loads((GOLD / "intervention_before.meta.json").read_text())
    r = vg.inspect(img, {"kind": "intervention", "text": texts_of("intervention_before") + extra, "meta": meta})
    assert {"text_roles", "saturated_hues"} <= failed(r)
    assert len(r["frame_budget"]["saturated_hues"]) == 2


def test_the_gate_names_what_a_frame_without_metadata_lacks():
    r = vg.inspect(GOLD / "intervention_before.png", {"kind": "intervention", "text": texts_of("intervention_before"), "strokes": {"preview_of": 1080}})
    msgs = {f["rule"]: f["msg"] for f in r["findings"] if not f["ok"]}
    assert "declares none" in msgs["scale_figures"] and "no field coverage" in msgs["field_cover"] and "no static share" in msgs["field_static"]


# ------------------------------------------------------------------------------------------------ the world and the stills themselves
@pytest.fixture(scope="module")
def stills():
    return {a: (Image.open(GOLD / f"intervention_{a}.png").convert("RGB"), json.loads((GOLD / f"intervention_{a}.meta.json").read_text())) for a in ACTS}


def test_the_three_stills_are_one_per_act_and_the_event_is_dimmed(stills):
    assert [stills[a][1]["act"] for a in ACTS] == list(ACTS)
    lo, hi = rules.INTERVENTION["event_dim"]
    assert stills["before"][1]["dim"] == 1.0 == stills["after"][1]["dim"] and lo <= stills["event"][1]["dim"] <= hi
    for a in ACTS:
        assert stills[a][0].size == (360, 450)


def test_the_world_is_cad_at_true_scale_from_qa_passed_assets():
    from offsim.assets.cad import qa
    reg = qa.registry()
    assert all(reg[n]["status"] == "qa-pass" for n in ("platform_jacket", "s92", "person"))
    w = iv.build_world()
    assert w["world"].shape == (iv.G0.nx, iv.G0.nz) and w["s92_solid"].sum() > 100
    assert abs(w["rotor"]["r"] * 2 - 17.17) < 0.1                                  # the S-92 rotor diameter, from the solid
    assert all(abs(p["height_m"] - 1.75) < 0.02 for p in w["persons"]) and len(w["persons"]) >= 2
    assert not (w["s92_solid"] & ~np.zeros_like(w["s92_solid"])).sum() == 0 and not (w["s92_solid"] & w["world"] & ~w["s92_solid"]).any()


def test_dry_run_frame_builds_from_report_refs_and_passes_the_gate():
    """End to end at the dry-run size: forcing resolved from the weather refs, both cases solved, one frame drawn, the gate judges it."""
    import yaml
    sb = yaml.safe_load(SB.read_text())
    import tempfile
    rep = {"gates": {"0_provenance": {"pass": True}}, "measured": {"flights_planned": 19.0}, "status": "x"}
    with tempfile.TemporaryDirectory() as tmp:
        res = iv.run_intervention(sb["shots"][0], sb, rep, tmp, quick=True, scenario=yaml.safe_load((ROOT / sb["scenario"]).read_text()), log=lambda *_: None)
        ok, why, r = iv.gate_frame(Image.open(res["frames"][0]).convert("RGB"), res["texts"][0], res["meta"][0])
    assert res["draft"] and "DRAFT" in res["text"]["kicker"]
    assert [round(c.u10, 3) for c in res["cases"]][0] < [round(c.u10, 3) for c in res["cases"]][1]
    assert ok, why
