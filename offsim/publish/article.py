"""Article generator and publish stage: report.json -> markdown article -> publish bundle. No network unless asked.

    refs(report)                      flat, resolvable refs: narrate.flatten(report) plus a `derived.*` block computed from
                                      the report only (status key, gate counts, assumption sections, headline KPI with its
                                      spread, first paired comparison, paper-vs-ours row, units converted)
    build(report_path, template=...)  render offsim/publish/templates/<template>.md to a markdown file
    publish(article_path, ...)        out/<paper>/publish/{article, figures, manifest.json}; muse.ai only on request

Template syntax (markdown, YAML front matter declares `requires:` refs and `narration:` rule sets):
    {{ref:kpis.distance_km|.1f}}      a ref, optional format spec; unresolved -> ArticleError (never blank)
    {{narrate:name}}                  sentence chosen by offsim.motion.narrate.choose from `narration.name` (first matching
                                      `when` wins, final rule is the default), over the refs
    {{list:assumptions}}              the assumptions, grouped by scenario section (no indices)
    {{figures}}                       markdown images for the paths given to build(); nothing when none were given

Rules enforced at build time, not only in tests:
  1. Every number in the body traces to a ref: template and narration literals may not contain digits, and every digit
     run in the output must be derivable (str or fixed-decimal format) from a value in refs().
  2. Every `ref:` used is declared in `requires`; every required ref resolves.
  3. Refused reports: a failed gate (4_paper excepted: "did not reproduce" is a finding), a stop at a gate, synthetic
     weather / not reportable, no `paper` block. A report with assumptions needs a template that renders them.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
from pathlib import Path

import yaml

from offsim.motion import narrate

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = Path(__file__).resolve().parent / "templates"
LANGS = ("en",)

__all__ = ["ArticleError", "ArticleRefused", "refs", "check_report", "build", "publish", "load_template", "TEMPLATES"]


class ArticleError(ValueError):
    """Unresolved ref, bad template, untraceable number."""


class ArticleRefused(ArticleError):
    """The report must not be written about (failed gate, synthetic weather, no paper block)."""


# ------------------------------------------------------------------------------------------------------ refusals
def check_report(report: dict) -> None:
    if not isinstance(report, dict) or not isinstance(report.get("paper"), dict) or not report["paper"].get("id"):
        raise ArticleRefused("refused: the report has no `paper` block with an id")
    gates = report.get("gates") or {}
    if not gates:
        raise ArticleRefused("refused: the report has no gates")
    bad = [g for g, v in gates.items() if g != "4_paper" and not (v or {}).get("pass")]
    status = str(report.get("status") or "")
    if bad or status.startswith("stopped"):
        raise ArticleRefused(f"refused: gate failed ({', '.join(bad) or status}); a failed run is never written up")
    if "synthetic weather" in status or "not reportable" in status or report.get("reportable") is False:
        raise ArticleRefused(f"refused: status is {status!r}; synthetic weather results are not reportable")
    ens = report.get("ensemble")
    if isinstance(ens, dict) and (ens.get("synthetic_weather") or ens.get("ok") is False or ens.get("validated") is False):
        raise ArticleRefused("refused: the ensemble is synthetic, invalid or not ok")
    if not status:
        raise ArticleRefused("refused: the report has no status word")


# ------------------------------------------------------------------------------------------------------ refs
_STATUS_KEYS = ("reproduced", "re-run under assumptions", "did not reproduce", "not comparable")


def _strip_idx(path: str) -> list[str]:
    return [p for p in re.sub(r"\[\d+\]", "", path).strip(".").split(".") if p]


def _assumption_groups(items) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for a in items or []:
        parts = _strip_idx(str(a))
        if not parts:
            continue
        leaf = ".".join(parts[1:]) or parts[0]
        groups.setdefault(parts[0], [])
        if leaf not in groups[parts[0]]:
            groups[parts[0]].append(leaf)
    return {k: sorted(v) for k, v in sorted(groups.items())}


def _label(kpi: str) -> str:
    return re.sub(r"_(s|km|m|h)$", "", kpi).replace("_", " ")


def _scale(kpi: str) -> tuple[float, str]:
    if kpi.endswith("_s"):
        return 1 / 3600.0, "hours"
    if kpi.endswith("_km"):
        return 1.0, "km"
    return 1.0, ""


def refs(report: dict) -> dict:
    """Flat refs for templates and narration rules. Everything numeric in an article comes from here."""
    r = dict(narrate.flatten(report))
    d: dict = {}
    paper = report.get("paper") or {}
    status = str(report.get("status") or "")
    d["status_key"] = next((k for k in _STATUS_KEYS if status.startswith(k)), "other")
    d["paper_title"] = str(paper.get("title") or paper.get("id") or "")
    authors = [str(a) for a in (paper.get("authors") or [])]
    d["has_authors"] = int(bool(authors))
    d["authors_line"] = ", ".join(authors)
    d["has_doi"] = int(bool(paper.get("doi")))
    d["repo_path"] = f"offsim/papers/{paper.get('id', '')}"
    prov = report.get("provenance") or {}
    d["commit_short"] = str(prov.get("git_commit") or "")[:7]
    d["run_date"] = str(prov.get("run_utc") or "")[:10]
    d["packages_line"] = ", ".join(f"{k} {v}" for k, v in sorted((prov.get("packages") or {}).items()))
    gates = report.get("gates") or {}
    run_gates = [g for g in gates if g != "4_paper"]
    d["n_gates"] = len(run_gates)
    d["n_gates_pass"] = sum(1 for g in run_gates if (gates[g] or {}).get("pass"))
    d["gates_passed"] = ", ".join(g for g in run_gates if (gates[g] or {}).get("pass"))
    groups = _assumption_groups(report.get("assumptions"))
    d["n_assumptions"] = len(report.get("assumptions") or [])
    d["has_assumptions"] = int(d["n_assumptions"] > 0)
    d["assumption_sections"] = ", ".join(groups)
    km = (report.get("kpis") or {}).get("makespan_s")
    if isinstance(km, (int, float)):
        d["makespan_h"] = km / 3600.0
    # paper-vs-ours row (gate 4)
    det = (gates.get("4_paper") or {}).get("detail")
    rows = [x for x in det if isinstance(x, dict)] if isinstance(det, list) else []
    d["n_paper_kpis"] = len(rows)
    if rows:
        row = rows[0]
        d["paper_kpi"] = _label(str(row.get("kpi", "")))
        for k, name in (("paper", "paper_value"), ("ours", "paper_ours")):
            if isinstance(row.get(k), (int, float)):
                d[name] = row[k]
        if isinstance(row.get("rel_gap"), (int, float)):
            d["paper_gap_pct"] = row["rel_gap"] * 100
        if isinstance(row.get("rel_tol"), (int, float)):
            d["paper_tol_pct"] = row["rel_tol"] * 100
    # ensemble: headline KPI with its spread
    ens = report.get("ensemble") if isinstance(report.get("ensemble"), dict) else None
    d["has_ensemble"] = int(bool(ens and ens.get("quantiles")))
    d["has_comparison"] = 0
    if d["has_ensemble"]:
        q = ens["quantiles"]
        kpi = "makespan_s" if "makespan_s" in q else next(iter(q))
        variants = list((q[kpi] or {}).keys())
        var = "base" if "base" in variants else (variants[0] if variants else "")
        row = (q[kpi] or {}).get(var) or {}
        sc, unit = _scale(kpi)
        d.update(head_kpi=kpi, head_label=_label(kpi), head_unit=unit, head_variant=var)
        for s in ("p10", "p50", "p90", "mean"):
            if isinstance(row.get(s), (int, float)) and math.isfinite(row[s]):
                d[f"head_{s}"] = row[s] * sc
        d["weather_sources"] = ", ".join(str(s) for s in ens.get("weather_sources") or [])
        comps = ens.get("comparisons") or []
        if comps:
            c = comps[0]
            sc, unit = _scale(str(c["kpi"]))
            lo, hi = c["rel_ci95"]
            d.update(has_comparison=1, cmp_label=_label(str(c["kpi"])), cmp_a=str(c["a"]), cmp_b=str(c["b"]),
                     cmp_n=c["n_pairs"], cmp_pct=abs(c["rel_mean"]) * 100, cmp_lo_pct=lo * 100, cmp_hi_pct=hi * 100,
                     cmp_sign=(c["mean_diff"] > 0) - (c["mean_diff"] < 0),
                     cmp_excludes_zero=int(c["ci95"][0] > 0 or c["ci95"][1] < 0),
                     cmp_mean=abs(c["mean_diff"]) * sc, cmp_unit=unit)
    for k, v in d.items():
        r[f"derived.{k}"] = v
    return r


# ------------------------------------------------------------------------------------------------------ templates
def load_template(name: str, lang: str = "en") -> tuple[dict, str]:
    if lang not in LANGS:
        raise ArticleError(f"language {lang!r} is not supported (have {list(LANGS)}); add templates/<name>.{lang}.md")
    path = TEMPLATES / (f"{name}.md" if lang == "en" else f"{name}.{lang}.md")
    if not path.is_file():
        have = sorted(p.stem for p in TEMPLATES.glob("*.md"))
        raise ArticleError(f"unknown template {name!r}; have {have}")
    text = path.read_text()
    m = re.match(r"---\n(.*?)\n---\n(.*)", text, re.S)
    if not m:
        raise ArticleError(f"template {name}: YAML front matter (---) is required")
    meta = yaml.safe_load(m.group(1)) or {}
    for inc in meta.get("narration_include") or []:                    # shared rule sets; the template's own win
        shared = TEMPLATES / f"{inc}.yaml"
        if not shared.is_file():
            raise ArticleError(f"template {name}: narration_include {inc!r} not found in {TEMPLATES}")
        data = yaml.safe_load(shared.read_text()) or {}
        meta["narration"] = {**(data.get("narration") or {}), **(meta.get("narration") or {})}
        if "figure_caption" in data:
            meta.setdefault("figure_caption", data["figure_caption"])
    return meta, m.group(2)


_PH = re.compile(r"\{\{\s*(ref|narrate|list|figures)\s*(?::\s*([\w.\-]+))?\s*(?:\|\s*([^}]*?))?\s*\}\}")
_NUM = re.compile(r"\d+(?:\.\d+)?")


def _lint(meta: dict, body: str) -> list[str]:
    probs: list[str] = []
    literal = _PH.sub("", body)
    if _NUM.search(literal):
        probs.append(f"template literal text contains a number ({_NUM.search(literal).group()}); numbers come from refs")
    nar = meta.get("narration") or {}
    for name, rules in nar.items():
        probs += [f"narration {name}: {p}" for p in narrate.validate_rules(rules)]
        for i, rule in enumerate(rules):
            if _NUM.search(re.sub(r"\{[^{}]*\}", "", rule.get("text", ""))):
                probs.append(f"narration {name} rule {i}: literal number in text")
    req = set(meta.get("requires") or [])
    for m in _PH.finditer(body):
        kind, key = m.group(1), m.group(2)
        if kind == "ref" and key not in req:
            probs.append(f"ref {key!r} is used but not declared in `requires`")
        if kind == "narrate" and key not in nar:
            probs.append(f"narrate block {key!r} has no rules in front matter")
        if kind in ("ref", "narrate", "list") and not key:
            probs.append(f"{{{{{kind}:...}}}} needs a name")
    return probs


def _fmt(v, spec):
    if spec:
        try:
            return format(v, spec)
        except (ValueError, TypeError) as e:
            raise ArticleError(f"cannot format {v!r} with {spec!r}: {e}") from None
    return f"{v:g}" if isinstance(v, float) else str(v)


def _traceable_tokens(values: dict) -> set[str]:
    out: set[str] = set()
    for v in values.values():
        if isinstance(v, bool):
            continue
        if isinstance(v, str):
            out.update(_NUM.findall(v))
        elif isinstance(v, (int, float)) and math.isfinite(v):
            out.update(_NUM.findall(str(abs(v))))
            for nd in range(0, 5):
                out.update(_NUM.findall(f"{abs(v):.{nd}f}"))
    return out


def _numbers_in_body(text: str) -> list[str]:
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)          # figure links carry file names
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    return _NUM.findall(text)


def _list_assumptions(report: dict) -> str:
    groups = _assumption_groups(report.get("assumptions"))
    if not groups:
        return "- None: every value in this run is sourced."
    return "\n".join(f"- **{g}**: {', '.join(v)}" for g, v in groups.items())


def _figures_md(figures, caption_rules, values, out_dir: Path) -> str:
    lines = []
    for f in figures or []:
        p = Path(f)
        if not p.is_file():
            raise ArticleError(f"figure {f} does not exist; a figure is never invented")
        try:
            cap = narrate.choose(caption_rules, values) if caption_rules else "Still from the film of this run."
        except narrate.NarrationError as e:
            raise ArticleError(f"figure caption: {e}") from None
        rel = os.path.relpath(p.resolve(), out_dir.resolve())
        lines.append(f"![{cap}]({rel})\n\n*{cap}*")
    return "\n\n".join(lines)


def render(report: dict, meta: dict, body: str, figures=None, out_dir: Path | None = None) -> str:
    check_report(report)
    probs = _lint(meta, body)
    if probs:
        raise ArticleError("template problems: " + "; ".join(probs))
    values = refs(report)
    missing = [k for k in meta.get("requires") or [] if k not in values]
    if missing:
        raise ArticleError(f"report cannot fill template {meta.get('template', '?')!r}: missing refs {missing}")
    if report.get("assumptions") and not any(m.group(1) == "list" and m.group(2) == "assumptions" for m in _PH.finditer(body)):
        raise ArticleRefused("refused: the report has assumptions and this template renders no assumptions section")
    nar = meta.get("narration") or {}

    def sub(m):
        kind, key, spec = m.group(1), m.group(2), m.group(3)
        if kind == "ref":
            if key not in values:
                raise ArticleError(f"unresolved ref {key!r}")
            return _fmt(values[key], spec)
        if kind == "narrate":
            try:
                return narrate.choose(nar[key], values)
            except narrate.NarrationError as e:
                raise ArticleError(f"narrate:{key}: {e}") from None
        if kind == "list":
            if key != "assumptions":
                raise ArticleError(f"unknown list {key!r}")
            return _list_assumptions(report)
        return _figures_md(figures, meta.get("figure_caption"), values, out_dir or Path("."))

    text = _PH.sub(sub, body)
    text = re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"
    ok = _traceable_tokens(values)
    stray = sorted({n for n in _numbers_in_body(text) if n not in ok})
    if stray:
        raise ArticleError(f"numbers in the article that trace to no ref: {stray}")
    return text


# ------------------------------------------------------------------------------------------------------ build
def resolve_report(target) -> Path:
    t = Path(str(target))
    if t.suffix == ".json" or t.is_file():
        return t
    from offsim.studio import context
    rel = context(str(target))["report"]
    return ROOT / rel


def default_out(report_path: Path, report: dict, template: str, target_is_id: bool) -> Path:
    name = "article.md" if template == "linkedin" else ("README_ENTRY.md" if template == "readme_entry" else f"article_{template}.md")
    if target_is_id:
        return ROOT / "offsim/papers" / report["paper"]["id"] / name
    return report_path.parent / name


def build(report_path, template: str = "linkedin", out=None, figures=None, lang: str = "en") -> Path:
    """Render the article for one report and write it (plus <out>.meta.json for `publish`). Returns the path."""
    target_is_id = not (str(report_path).endswith(".json") or Path(str(report_path)).is_file())
    rp = resolve_report(report_path)
    if not rp.is_file():
        raise ArticleError(f"no report at {rp}; run `python -m offsim run <scenario>` first")
    raw = rp.read_bytes()
    report = json.loads(raw)
    meta, body = load_template(template, lang)
    meta.setdefault("template", template)
    outp = Path(out) if out else default_out(rp, report if isinstance(report, dict) and report.get("paper") else {"paper": {"id": "x"}}, template, target_is_id)
    text = render(report, meta, body, figures, outp.parent)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(text)
    side = {"paper_id": report["paper"]["id"], "template": template, "lang": lang, "status": report["status"],
            "report": str(rp), "report_sha256": hashlib.sha256(raw).hexdigest(),
            "figures": [str(Path(f)) for f in figures or []],
            "doi": report["paper"].get("doi", ""), "sources": _sources(report)}
    outp.with_name(outp.name + ".meta.json").write_text(json.dumps(side, indent=1))
    return outp


def _sources(report: dict) -> list[str]:
    prov = report.get("provenance") or {}
    src = [f"report.json (scenario sha256 {str(prov.get('scenario_sha256', ''))[:12]})", f"offsim/papers/{report['paper']['id']}"]
    if report["paper"].get("doi"):
        src.append(f"doi:{report['paper']['doi']}")
    for s in (report.get("ensemble") or {}).get("weather_sources") or []:
        src.append(f"weather:{s}")
    return src


# ------------------------------------------------------------------------------------------------------ publish
def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def publish(article_path, video=None, muse: bool = False, out_root=None) -> dict:
    """Write out/<paper>/publish/ with the article, copies of its figures and manifest.json. The video is hashed, not
    copied. muse.ai upload happens only when muse=True, a video exists and MUSE_AI_KEY is set. No other network."""
    ap = Path(article_path)
    side = ap.with_name(ap.name + ".meta.json")
    if not ap.is_file() or not side.is_file():
        raise ArticleError(f"{ap} is not an article made by `offsim article` (missing {side.name})")
    meta = json.loads(side.read_text())
    rp = Path(meta["report"])
    if rp.is_file() and _sha(rp) != meta["report_sha256"]:
        raise ArticleError("the report changed after this article was written; rebuild the article")
    if rp.is_file():
        check_report(json.loads(rp.read_text()))
    root = Path(out_root) if out_root else ROOT / "out"
    pub = root / meta["paper_id"] / "publish"
    pub.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ap, pub / ap.name)
    figs = []
    for f in meta.get("figures") or []:
        fp = Path(f)
        if not fp.is_file():
            raise ArticleError(f"figure {f} is gone; rebuild the article")
        (pub / "figures").mkdir(exist_ok=True)
        shutil.copy2(fp, pub / "figures" / fp.name)
        figs.append({"file": f"figures/{fp.name}", "sha256": _sha(fp)})
    man = {"paper_id": meta["paper_id"], "status": meta["status"], "template": meta["template"],
           "article": {"file": ap.name, "sha256": _sha(ap)}, "figures": figs, "sources": meta["sources"],
           "report_sha256": meta["report_sha256"], "video": None, "muse": {"requested": bool(muse), "result": "not requested"}}
    vp = Path(video) if video else None
    if vp and vp.is_file():
        man["video"] = {"file": str(vp), "sha256": _sha(vp)}
    if muse:
        if not (vp and vp.is_file()):
            man["muse"]["result"] = "skipped: no video file"
        elif not os.environ.get("MUSE_AI_KEY"):
            man["muse"]["result"] = "skipped: MUSE_AI_KEY not set"
        else:
            from offsim.publish import muse as _muse
            man["muse"]["result"] = _muse.upload(vp, title=meta["paper_id"], visibility="unlisted")
    (pub / "manifest.json").write_text(json.dumps(man, indent=1, default=str))
    # the funnel's publish exit file: a staged bundle, not a public post (a human still posts it)
    ap.with_name("published.json").write_text(json.dumps(
        {"paper_id": meta["paper_id"], "bundle": str(pub), "status": meta["status"], "staged": True,
         "uploaded": isinstance(man["muse"]["result"], dict)}, indent=1))
    man["bundle"] = str(pub)
    return man
