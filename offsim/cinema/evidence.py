"""INSPECTOR for the evidence form (rules.EVIDENCE, docs/VISUAL_GRAMMAR.md section 10). Metadata only: it reads storyboard
shots marked `form: evidence` and returns violations as strings 'shot <i> (evidence): <what>'. It never renders. Shots without
`form: evidence` are ignored, so existing storyboards are unaffected. Not checked here: pixels (visual_gate.py), numbers
(contract and report refs)."""
from __future__ import annotations

from offsim.cinema.rules import EVIDENCE as E


def _words(s) -> int:
    return len(str(s).split())


def _ref_ok(item) -> bool:
    if isinstance(item, dict):
        ref = str(item.get("ref", ""))
        return ref.startswith("report:") or item.get("assumption") is True
    return False


def evidence_plan(storyboard: dict) -> list[str]:
    msgs: list[str] = []
    templates: set[str] = set()
    for i, sh in enumerate(storyboard.get("shots", [])):
        if sh.get("form") != "evidence" and sh.get("type") != "evidence":
            continue
        tag = f"shot {i} (evidence)"
        for k in E["required"]:
            if not sh.get(k):
                msgs.append(f"{tag}: missing {k!r}")
        ref = sh.get("reference") or {}
        if ref and ref.get("kind") not in E["reference_kinds"]:
            msgs.append(f"{tag}: reference kind {ref.get('kind')!r} not in {list(E['reference_kinds'])}")
        if ref and not (ref.get("source") or ref.get("ref")):
            msgs.append(f"{tag}: reference has no source")
        f = str(sh.get("finding", ""))
        if f and _words(f) > E["finding_words_max"]:
            msgs.append(f"{tag}: finding has {_words(f)} words vs max {E['finding_words_max']}")
        if f.rstrip().endswith("."):
            msgs.append(f"{tag}: finding ends with a full stop")
        h = str(sh.get("headline", ""))
        lo, hi = E["headline_words"]
        if h and not lo <= _words(h) <= hi:
            msgs.append(f"{tag}: headline has {_words(h)} words vs {lo}-{hi}")
        acc = sh.get("accent") or ""
        alo, ahi = E["accent_words"]
        if h and acc and not (alo <= _words(acc) <= ahi and acc in h):
            msgs.append(f"{tag}: accent {acc!r} must be {alo}-{ahi} words taken from the headline")
        if _words(sh.get("kicker", "")) > E["kicker_words_max"]:
            msgs.append(f"{tag}: kicker longer than {E['kicker_words_max']} words")
        limits = sh.get("limits") or []
        if len(limits) < E["limits_min"]:
            msgs.append(f"{tag}: needs at least {E['limits_min']} limit line(s) saying what the frame is not")
        method = sh.get("method") or []
        if len(method) < E["method_min"]:
            msgs.append(f"{tag}: method has {len(method)} item(s) vs min {E['method_min']}")
        for m in method:
            if not _ref_ok(m):
                msgs.append(f"{tag}: method item {m!r} needs a 'report:' ref or assumption: true")
        counters = sh.get("counters") or []
        if len(counters) > E["counters_max"]:
            msgs.append(f"{tag}: {len(counters)} counters vs max {E['counters_max']}")
        for c in counters:
            if not _ref_ok(c):
                msgs.append(f"{tag}: counter {c!r} needs a 'report:' ref")
        rs = sh.get("restyle")
        if rs is not None:
            lo2, hi2 = E["restyle_states"]
            if not lo2 <= len(rs) <= hi2:
                msgs.append(f"{tag}: restyle has {len(rs)} states vs {lo2}-{hi2}")
        ex = sh.get("explode")
        if ex is not None:
            if len(ex) < E["explode_layers_min"] or not all(isinstance(x, dict) and x.get("label") for x in ex):
                msgs.append(f"{tag}: explode needs >= {E['explode_layers_min']} labelled layers")
        cam = sh.get("camera") or {}
        bad = [k for k in E["camera_keys_forbidden"] if cam.get(k)]
        if bad:
            msgs.append(f"{tag}: camera must be locked, found {bad}")
        pal = sh.get("palette")
        if pal is not None and set(pal) != set(E["palette_roles"]):
            msgs.append(f"{tag}: palette roles must be exactly {list(E['palette_roles'])}, got {sorted(pal)}")
        if sh.get("palette_name") is not None:
            from offsim.cinema.look import PALETTES
            if sh["palette_name"] not in PALETTES:
                msgs.append(f"{tag}: palette_name {sh['palette_name']!r} not in {sorted(PALETTES)}")
        if sh.get("template"):
            templates.add(str(sh["template"]))
    if len(templates) > E["template_per_film"]:
        msgs.append(f"film: {len(templates)} templates {sorted(templates)} vs {E['template_per_film']} per film")
    return msgs
