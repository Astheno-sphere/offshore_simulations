"""Evidence form inspector (offsim/cinema/evidence.py, rules.EVIDENCE)."""
import copy

from offsim.cinema.evidence import evidence_plan

GOOD = {
    "type": "map", "form": "evidence", "seconds": 8, "template": "ev1",
    "kicker": "Bergen replay", "headline": "Sea state cancels the flights", "accent": "Sea state",
    "finding": "grid A is denser than grid B in every winter",
    "reference": {"kind": "map", "source": "OSM bergen-ncs"},
    "limits": ["replay on assumed positions, one weather point"],
    "method": [{"label": "NORA3 DJF 24 winters", "ref": "report:measured.winters"}, {"label": "limit", "assumption": True}],
    "counters": [{"label": "infeasible days", "ref": "report:measured.infeasible_days"}],
    "restyle": ["satellite", "colour", "oblique", "stripped"],
    "explode": [{"label": "land"}, {"label": "sea"}, {"label": "plan"}],
    "camera": {}, "palette": {"ground": "#000", "accent": "#fa0", "comparison": "#58a"},
}


def sb(*shots):
    return {"shots": [copy.deepcopy(s) for s in shots]}


def test_good_shot_passes_and_non_evidence_ignored():
    assert evidence_plan(sb(GOOD, {"type": "card", "seconds": 3})) == []


def test_missing_reference_and_limits_refused():
    bad = {k: v for k, v in GOOD.items() if k not in ("reference", "limits")}
    msgs = evidence_plan(sb(bad))
    assert any("missing 'reference'" in m for m in msgs) and any("missing 'limits'" in m for m in msgs)


def test_method_item_without_ref_refused():
    bad = copy.deepcopy(GOOD); bad["method"] = [{"label": "x"}, {"label": "y", "ref": "typed 3.6"}]
    assert sum("needs a 'report:' ref" in m for m in evidence_plan(sb(bad))) == 2


def test_camera_must_be_locked():
    bad = copy.deepcopy(GOOD); bad["camera"] = {"zoom": 0.2}
    assert any("camera must be locked" in m for m in evidence_plan(sb(bad)))


def test_counters_headline_finding_limits_of_words():
    bad = copy.deepcopy(GOOD)
    bad["counters"] = [{"ref": "report:a"}] * 4
    bad["headline"] = "A very long headline that goes on for far too many words"
    bad["finding"] = "word " * 15
    msgs = evidence_plan(sb(bad))
    assert any("counters vs max" in m for m in msgs) and any("headline has" in m for m in msgs) and any("finding has" in m for m in msgs)


def test_two_templates_in_one_film_refused():
    other = copy.deepcopy(GOOD); other["template"] = "ev2"
    assert any("templates" in m for m in evidence_plan(sb(GOOD, other)))


def test_restyle_and_explode_bounds_and_palette_roles():
    bad = copy.deepcopy(GOOD); bad["restyle"] = ["a", "b"]; bad["explode"] = [{"label": "x"}]; bad["palette"] = {"ground": 1, "accent": 2}
    msgs = evidence_plan(sb(bad))
    assert any("restyle has" in m for m in msgs) and any("explode needs" in m for m in msgs) and any("palette roles" in m for m in msgs)


def test_renderer_draws_good_shot_and_refuses_bad(tmp_path):
    import pytest
    from offsim.motion.evidence import render_evidence
    shot = copy.deepcopy(GOOD); shot.update({"kicker": "Kick", "body": "Short body.", "source": "src", "handle": "@h"})
    img = render_evidence(shot, {"report:measured.infeasible_days": "172"}, None, "amber-black", draft="Draft")
    assert img.size == (1080, 1350)
    with pytest.raises(KeyError):
        render_evidence(shot, {}, None)                       # a counter with no resolved value never renders
    bad = copy.deepcopy(shot); bad["limits"] = []
    with pytest.raises(ValueError):
        render_evidence(bad, {"report:measured.infeasible_days": "1"})


def test_every_palette_has_the_same_keys():
    from offsim.cinema.look import PALETTES
    keys = set(PALETTES["amber-black"])
    for name, pal in PALETTES.items():
        if name != "section-plan":
            assert set(pal) == keys, name
