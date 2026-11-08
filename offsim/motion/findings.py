"""Finding shots: how a *result* is shown, as opposed to the operation (map shots). docs/VISUAL_SPEC.md section 9.

A map shot shows what one run did. A finding shot shows what the ensemble says. Every value comes from
report["ensemble"] (offsim.montecarlo.Ensemble.to_report) or, for `state_gantt`, the run's trajectory; a finding shot
refuses a report without an ensemble that is `ok` and was validated.

Data functions (pure, no drawing; each returns a dict with `kind`):
    ghost_tracks(report, ensemble_dir, n=40, highlight=None)  data prep for the map renderer (N runs at low alpha under
                         one highlighted run). Convention: <ensemble_dir>/<run_id>/trajectory.csv.
    fan(report, kpi, by="variant", scale=1.0)       P10-P90 band (P25-P75 when the report has it) and P50 per variant,
                         one shared axis. `by="year"` needs per-run rows that the report does not carry: refused.
    paired(report, kpi, a, b, better="lower", min_effect=None, scale=1.0)   a - b over (year, seed) pairs: mean and
                         bootstrap 95% CI, relative effect, status word (supported | not supported | inconclusive).
    state_gantt(traj, weather=None, agents=None)    per vessel: states over time, Hs strip under it.
    weather_year(weather_years, limits)            daily operable fraction per year (which winters drive the P90).

Shot (storyboard `type: findings`):
    - type: findings
      kind: fan | paired | state_gantt
      seconds: 6
      kpi: wait_s            unit: h     scale: 0.000277778      fmt: "{:.1f}"      # display units only
      compare: [better, base]  better: lower  min_effect: 0.2    # fan (several variants) and paired: status word
      a: better  b: base                                          # paired (or `compare`)
      kicker / headline {top, accent, rest} / narration: [rules]  # rules choose the deck from the measured values

Rules: one axis for all variants; whenever a single number is on screen its spread is on screen with it; every
comparison carries its status word (from ensemble["decision"] when present, else from `min_effect` with
offsim.research.experiment.decide: the threshold is pre-registered in the storyboard, never chosen to fit); numbers
fade in once the build-in has finished, so nothing on screen is an interpolated, un-sourced value; the build-in is
animated over the shot seconds with a final hold. Palette and furniture are the section-plan look.
Narration values (besides flatten(report)): fan: fan.<variant>.<p10|p25|p50|p75|p90|mean|n>, fan.lo, fan.hi, and the
status values below when `compare` is given; paired: mean_diff, ci_lo, ci_hi, rel_pct, rel_lo_pct, rel_hi_pct,
effect_pct, min_effect_pct, n_pairs, status; state_gantt: <state>_h per state (0 when absent), wait_share, n_agents,
span_h. KPI values are in display units (scale applied).
"""
from __future__ import annotations

import math
import re
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw

from offsim.motion import narrate
from offsim.motion.section import P, encode, fit, font

W, H = 1080, 1350
KINDS = ("fan", "paired", "state_gantt")
DATA_ONLY_KINDS = ("ghost_tracks", "weather_year")
STATES = ("load", "sail", "dp", "wait", "unload", "idle")
STATE_COLORS = {"sail": "#846a5d", "load": "#c9a98c", "unload": "#e0c7ad", "dp": "#a78466", "wait": P["accent"], "idle": "#4a3236"}
STATUS_WORDS = ("supported", "not supported", "inconclusive")


class FindingsError(ValueError):
    """A finding shot refused: no ensemble, a failed ensemble, a missing status, or an unsupported request."""


# ----------------------------------------------------------------------------------------------- data
def _ens(report) -> dict:
    e = report.get("ensemble") if isinstance(report, dict) else None
    if not isinstance(e, dict):
        raise FindingsError("report has no `ensemble` block: finding shots read only report['ensemble'] "
                            "(run offsim.montecarlo and put Ensemble.to_report() into report['ensemble'])")
    if e.get("ok") is not True:
        raise FindingsError("report['ensemble'].ok is not true (contract failures or no valid runs): nothing downstream may use it")
    if e.get("validated") is False:
        raise FindingsError("report['ensemble'] was run with validate=False: it must not feed a render")
    return e


def _num(x, what):
    if not isinstance(x, (int, float)) or isinstance(x, bool) or not math.isfinite(x):
        raise FindingsError(f"{what} is missing or not finite in the ensemble report")
    return float(x)


def _nice_axis(lo, hi, n=5):
    span = max(hi - lo, 1e-9)
    raw = span / n
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    a, b = math.floor(lo / step) * step, math.ceil(hi / step) * step
    ticks = [a + i * step for i in range(int(round((b - a) / step)) + 1)]
    return a, b, ticks


def oriented(rel_mean, rel_ci, better):
    """Relative effect signed so positive = better (same convention as offsim.research.run_experiment)."""
    if better not in ("lower", "higher"):
        raise FindingsError(f"better must be lower|higher, got {better!r}")
    return (rel_mean, tuple(rel_ci)) if better == "higher" else (-rel_mean, (-rel_ci[1], -rel_ci[0]))


def _comparison(e, kpi, a, b):
    for c in e.get("comparisons") or []:
        if c.get("kpi") == kpi and c.get("a") == a and c.get("b") == b:
            return c
    raise FindingsError(f"the ensemble report has no comparison of {kpi!r} {a!r} vs {b!r}; run ens.compare(...) before to_report()")


def status_for(report, kpi, a, b, better="lower", min_effect=None) -> dict:
    """Status word of a comparison: the report's pre-registered decision if it is for this comparison, else computed
    from the paired relative effect and the storyboard's `min_effect`. Refuses when neither exists."""
    e = _ens(report)
    c = _comparison(e, kpi, a, b)
    eff, ci = oriented(_num(c.get("rel_mean"), "rel_mean"), [_num(x, "rel_ci95") for x in c["rel_ci95"]], better)
    dec = e.get("decision")
    if isinstance(dec, dict) and dec.get("kpi") == kpi and list(dec.get("compare") or []) == [a, b] and dec.get("status") in STATUS_WORDS:
        return {"status": dec["status"], "effect": eff, "ci": ci, "min_effect": dec.get("min_effect"), "n_pairs": c.get("n_pairs"),
                "source": "ensemble.decision"}
    if min_effect is None:
        raise FindingsError(f"comparison {a!r} vs {b!r} on {kpi!r} needs its status word: give `min_effect` "
                            "(pre-registered) or an ensemble.decision for it")
    from offsim.research.experiment import decide
    return {"status": decide(eff, ci, float(min_effect)), "effect": eff, "ci": ci, "min_effect": float(min_effect),
            "n_pairs": c.get("n_pairs"), "source": "storyboard min_effect"}


def fan(report, kpi, by="variant", scale=1.0, axis=None) -> dict:
    e = _ens(report)
    if by != "variant":
        raise FindingsError(f"fan by={by!r} needs per-run rows, which report['ensemble'] does not carry; only by='variant'")
    if kpi not in (e.get("kpis") or []) or kpi not in (e.get("quantiles") or {}):
        raise FindingsError(f"kpi {kpi!r} not in the ensemble report; have {e.get('kpis')}")
    rows = []
    for v in e["variants"]:
        q = e["quantiles"][kpi].get(v)
        if not q:
            raise FindingsError(f"no quantiles for variant {v!r} on {kpi!r}")
        row = {"label": v, **{s: _num(q.get(s), f"{kpi}.{v}.{s}") * scale for s in ("p10", "p50", "p90")}}
        row["mean"] = _num(q.get("mean"), f"{kpi}.{v}.mean") * scale
        row["n"] = int(_num(q.get("n"), f"{kpi}.{v}.n"))
        for s in ("p25", "p75"):
            if q.get(s) is not None:
                row[s] = _num(q[s], f"{kpi}.{v}.{s}") * scale
        rows.append(row)
    lo = min(0.0, min(r["p10"] for r in rows))
    hi = max(r["p90"] for r in rows)
    a0, a1, ticks = _nice_axis(*(axis if axis else (lo, hi * 1.05)))
    return {"kind": "fan", "kpi": kpi, "by": by, "rows": rows, "axis": (a0, a1), "ticks": ticks}


def paired(report, kpi, a, b, better="lower", min_effect=None, scale=1.0) -> dict:
    e = _ens(report)
    c = _comparison(e, kpi, a, b)
    st = status_for(report, kpi, a, b, better, min_effect)
    ci = [_num(x, "ci95") * scale for x in c["ci95"]]
    diffs = [float(r["diff"]) * scale for r in c.get("diffs", []) if isinstance(r, dict) and r.get("diff") is not None]
    mean = _num(c.get("mean_diff"), "mean_diff") * scale
    m = max([abs(mean), abs(ci[0]), abs(ci[1])] + [abs(x) for x in diffs]) * 1.15 or 1.0
    a0, a1, ticks = _nice_axis(-m, m)
    return {"kind": "paired", "kpi": kpi, "a": a, "b": b, "better": better, "mean": mean, "ci": ci,
            "rel": _num(c.get("rel_mean"), "rel_mean"), "rel_ci": [_num(x, "rel_ci95") for x in c["rel_ci95"]],
            "n_pairs": int(c.get("n_pairs") or len(diffs)), "diffs": diffs, "status": st["status"], "effect": st["effect"],
            "effect_ci": list(st["ci"]), "min_effect": st["min_effect"], "status_source": st["source"],
            "axis": (-max(abs(a0), abs(a1)), max(abs(a0), abs(a1))), "ticks": ticks}


def state_gantt(traj, weather=None, agents=None) -> dict:
    """States over time per agent from a trajectory (each row's state holds until the agent's next row)."""
    if traj is None or len(traj) == 0 or not {"agent_id", "t", "state"} <= set(traj.columns):
        raise FindingsError("state_gantt needs a trajectory with agent_id, t, state")
    cls = {}
    if agents is not None and "agent_id" in agents.columns and "cls" in agents.columns:
        cls = dict(zip(agents["agent_id"], agents["cls"]))
    lanes, totals = [], {}
    for aid, g in traj.sort_values("t").groupby("agent_id", sort=False):
        t, s = g["t"].to_numpy(float), g["state"].astype(str).to_numpy()
        segs = []
        for i in range(len(t) - 1):
            if t[i + 1] <= t[i]:
                continue
            if segs and segs[-1][2] == s[i] and abs(segs[-1][1] - t[i]) < 1e-9:
                segs[-1][1] = float(t[i + 1])
            else:
                segs.append([float(t[i]), float(t[i + 1]), s[i]])
        for a0, a1, st in segs:
            totals[st] = totals.get(st, 0.0) + (a1 - a0) / 3600.0
        lanes.append({"agent": str(aid), "label": f"{aid}" + (f"  ({cls[aid]})" if aid in cls else ""),
                      "segments": [tuple(x) for x in segs]})
    t0, t1 = float(traj["t"].min()), float(traj["t"].max())
    hs = None
    if weather is not None and len(weather):
        if not {"t", "hs_m"} <= set(weather.columns):
            raise FindingsError("weather needs columns t, hs_m")
        w = weather[(weather["t"] >= t0) & (weather["t"] <= t1)]
        hs = list(zip(w["t"].astype(float), w["hs_m"].astype(float)))
    return {"kind": "state_gantt", "lanes": lanes, "t0": t0, "t1": t1, "totals_h": totals,
            "states": [s for s in STATES if s in totals] + sorted(s for s in totals if s not in STATES), "hs": hs}


def ghost_tracks(report, ensemble_dir, n=40, highlight=None) -> dict:
    """Data prep for the map renderer: up to n evenly spaced runs' tracks (one polyline per agent)."""
    _ens(report)
    files = sorted(Path(ensemble_dir).rglob("trajectory.csv"))
    if not files:
        raise FindingsError(f"no <run>/trajectory.csv under {ensemble_dir}")
    pick = files if len(files) <= n else [files[int(i)] for i in np.linspace(0, len(files) - 1, n)]
    tracks = []
    for f in pick:
        tr = pd.read_csv(f)
        for aid, g in tr.sort_values("t").groupby("agent_id", sort=False):
            tracks.append({"id": f.parent.name, "agent": str(aid), "coords": [[float(x), float(y)] for x, y in zip(g["lon"], g["lat"])]})
    return {"kind": "ghost_tracks", "n_runs": len(pick), "n_available": len(files), "tracks": tracks,
            "highlight": highlight if highlight in {t["id"] for t in tracks} else None}


def weather_year(weather_years, limits) -> dict:
    """Daily operable fraction per weather year: hour operable when every column in `limits` is <= its limit."""
    if not weather_years or not limits:
        raise FindingsError("weather_year needs weather years and limits, e.g. {'hs_m': 2.5}")
    out = []
    for w in weather_years:
        df = w.df
        ok = np.ones(len(df), bool)
        for col, lim in limits.items():
            if col not in df.columns:
                raise FindingsError(f"weather has no column {col!r}")
            ok &= df[col].to_numpy(float) <= float(lim)
        day = (df["t"].to_numpy(float) // 86400).astype(int)
        fr = [float(ok[day == d].mean()) for d in sorted(set(day))]
        out.append({"year": w.year, "source": w.source, "operable_frac": float(ok.mean()), "days": fr})
    return {"kind": "weather_year", "limits": dict(limits), "years": out}


# ----------------------------------------------------------------------------------------------- measure
def measure(shot, report, traj=None, weather=None, agents=None):
    """(data, values): the chart's data and the flat narration values. Raises FindingsError when refused."""
    kind = shot.get("kind")
    if kind not in KINDS:
        raise FindingsError(f"findings kind {kind!r} not renderable here; have {list(KINDS)} "
                            f"({list(DATA_ONLY_KINDS)} are data prep for other renderers)")
    scale = float(shot.get("scale", 1.0))
    vals = dict(narrate.flatten(report))
    if kind == "state_gantt":
        data = state_gantt(traj, weather, agents)
        tot = sum(data["totals_h"].values())
        vals.update({f"{s}_h": data["totals_h"].get(s, 0.0) for s in STATES})
        vals.update({"wait_share": (data["totals_h"].get("wait", 0.0) / tot) if tot else 0.0, "n_agents": float(len(data["lanes"])),
                     "span_h": (data["t1"] - data["t0"]) / 3600.0})
        return data, vals
    _ens(report)
    kpi = shot.get("kpi")
    if not kpi:
        raise FindingsError("findings shot needs `kpi`")
    better, min_eff = shot.get("better", "lower"), shot.get("min_effect")
    if kind == "fan":
        data = fan(report, kpi, shot.get("by", "variant"), scale, shot.get("axis"))
        for r in data["rows"]:
            for s in ("p10", "p25", "p50", "p75", "p90", "mean", "n"):
                if s in r:
                    vals["fan." + re.sub(r"\W", "_", r["label"]) + "." + s] = r[s]
        vals["fan.lo"], vals["fan.hi"] = data["axis"]
        comp = shot.get("compare")
        if len(data["rows"]) > 1 and not comp:
            raise FindingsError("a fan of several variants is a comparison: give `compare: [a, b]` (+ `min_effect`) so it carries its status word")
        if comp:
            st = status_for(report, kpi, comp[0], comp[1], better, min_eff)
            data["status"], data["compare"] = st["status"], list(comp)
            data["effect"], data["effect_ci"], data["min_effect"] = st["effect"], list(st["ci"]), st["min_effect"]
            vals.update({"status": st["status"], "effect_pct": 100 * st["effect"], "effect_lo_pct": 100 * st["ci"][0],
                         "effect_hi_pct": 100 * st["ci"][1], "n_pairs": float(st["n_pairs"] or 0)})
        return data, vals
    cmp_ = shot.get("compare") or [None, None]
    a, b = shot.get("a") or cmp_[0], shot.get("b") or cmp_[1]
    if not (a and b):
        raise FindingsError("paired shot needs `a` and `b` (or `compare: [a, b]`)")
    data = paired(report, kpi, a, b, better, min_eff, scale)
    vals.update({"mean_diff": data["mean"], "ci_lo": data["ci"][0], "ci_hi": data["ci"][1], "rel_pct": 100 * data["rel"],
                 "rel_lo_pct": 100 * data["rel_ci"][0], "rel_hi_pct": 100 * data["rel_ci"][1], "effect_pct": 100 * data["effect"],
                 "min_effect_pct": 100 * float(data["min_effect"]) if data["min_effect"] is not None else float("nan"),
                 "n_pairs": float(data["n_pairs"]), "status": data["status"]})
    return data, vals


def problems(shot, report, traj_available=True):
    """Static validation used by story.check (no drawing): kind, ensemble, status word, narration names."""
    probs = []
    if shot.get("kind") not in KINDS:
        return [f"kind {shot.get('kind')!r}: have {list(KINDS)}"]
    if not (isinstance(shot.get("seconds"), (int, float)) and shot["seconds"] > 0):
        probs.append("seconds: needs a positive number")
    if not shot.get("kicker"):
        probs.append("kicker: missing")
    hl = shot.get("headline")
    if not (isinstance(hl, dict) and all(isinstance(hl.get(x), str) and hl.get(x) for x in ("top", "accent", "rest"))):
        probs.append("headline: needs {top, accent, rest}")
    try:
        if shot["kind"] == "state_gantt":
            if not traj_available:
                raise FindingsError("state_gantt needs the run's trajectory.csv")
            known = set(narrate.flatten(report)) | {f"{s}_h" for s in STATES} | {"wait_share", "n_agents", "span_h"}
        else:
            _, vals = measure(shot, report)
            known = set(vals)
    except FindingsError as e:
        return probs + [str(e)]
    probs += narrate.validate_rules(shot.get("narration"), known)
    return probs


# ----------------------------------------------------------------------------------------------- drawing
def _ease(u):
    u = min(max(u, 0.0), 1.0)
    return u * u * (3 - 2 * u)


def _hex(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _mix(c, a):
    g, f = _hex(P["ground"]), _hex(c) if isinstance(c, str) else c
    return tuple(int(g[i] + (f[i] - g[i]) * a) for i in range(3))


def _fade(u, start=0.55, end=0.8):
    return min(max((u - start) / (end - start), 0.0), 1.0)


def _methods(report, shot):
    e = report.get("ensemble") or {}
    lines = []
    if e:
        yrs = e.get("years")
        lines.append(f"Ensemble: {e.get('n_valid')}/{e.get('n_runs')} valid runs (every run passed offsim.contract), variants {', '.join(e.get('variants') or [])}; "
                     f"seeds {e.get('seeds')}, weather years {yrs}; engine {', '.join(e.get('engines') or [])}.")
        lines.append("Weather: " + (", ".join(e.get("weather_sources") or []) or "none") +
                     ("  ·  SYNTHETIC weather" if e.get("synthetic_weather") else "") +
                     "  ·  Bands are P10-P90 over runs; comparisons are paired on (year, seed), bootstrap 95% CI.")
    else:
        lines.append("Trajectory from the gated run (offsim.contract); states as recorded by the engine.")
    lines.append(f"Run status from the corrector: {report.get('status', 'n/a')}.")
    return lines


def _frame(shot, report, deck, status=None):
    img = Image.new("RGB", (W, H), P["ground"])
    d = ImageDraw.Draw(img)
    d.text((56, 44), shot["kicker"], font=font(17, True), fill=P["accent"])
    hf, hl = font(52, True), shot["headline"]
    d.text((56, 76), hl["top"], font=hf, fill=P["ink"])
    d.text((56, 136), hl["accent"], font=hf, fill=P["accent"])
    d.text((56 + d.textlength(hl["accent"] + " ", font=hf), 136), hl["rest"], font=hf, fill=P["ink"])
    d.text((W - 56 - d.textlength("offshore_simulations", font=font(15, True)), 46), "offshore_simulations", font=font(15, True), fill=P["muted"])
    yb = 1010
    for i, line in enumerate(deck):
        d.text((56, yb + 30 * i), line, font=font(22), fill=P["ink"])
    for i, line in enumerate(_methods(report, shot)):
        d.text((56, yb + 90 + 18 * i), line, font=font(13), fill=P["muted"])
    return img, d


def _axis(d, a0, a1, ticks, y, x0, x1, label, fmt="{:g}"):
    d.line([(x0, y), (x1, y)], fill=P["muted"], width=1)
    for t in ticks:
        x = x0 + (x1 - x0) * (t - a0) / (a1 - a0)
        d.line([(x, y), (x, y + 6)], fill=P["muted"], width=1)
        d.text((x - d.textlength(fmt.format(t), font=font(13)) / 2, y + 10), fmt.format(t), font=font(13), fill=P["muted"])
        d.line([(x, 250), (x, y)], fill="#4a3236", width=1)
    if label:
        d.text((x1 - d.textlength(label, font=font(13, True)), y + 30), label, font=font(13, True), fill=P["muted"])


def _status_badge(d, status, x, y, a):
    if a <= 0:
        return
    col = P["accent"] if status == "supported" else P["ink"]
    d.text((x, y), "STATUS", font=font(14, True), fill=_mix(P["muted"], a))
    d.text((x, y + 20), status.upper(), font=font(44, True), fill=_mix(col, a))


def draw_fan(data, u, shot, report, deck):
    img, d = _frame(shot, report, deck)
    rows, (a0, a1) = data["rows"], data["axis"]
    x0, x1, ytop, ybot = 56, W - 56, 262, 840
    lane = min(110, (ybot - ytop - 20) / max(len(rows), 1))
    px = lambda v: x0 + (x1 - x0) * (v - a0) / (a1 - a0)
    unit, fmt = shot.get("unit", ""), shot.get("fmt", "{:.1f}")
    _axis(d, a0, a1, data["ticks"], ybot, x0, x1, f"{data['kpi']} ({unit})" if unit else data["kpi"], "{:g}")
    e, fa = _ease(u), _fade(u)
    for i, r in enumerate(rows):
        y = ytop + i * lane
        d.text((x0, y), r["label"].upper(), font=font(17, True), fill=P["ink"])
        by = y + 30
        grow = lambda lo, mid, hi: (mid - (mid - lo) * e, mid + (hi - mid) * e)
        l10, h90 = grow(r["p10"], r["p50"], r["p90"])
        d.rectangle([px(l10), by, px(h90), by + 26], fill=_mix(P["streak_lo"], 0.9))
        if "p25" in r and "p75" in r:
            l25, h75 = grow(r["p25"], r["p50"], r["p75"])
            d.rectangle([px(l25), by, px(h75), by + 26], fill=_mix(P["streak_hi"], 0.95))
        d.rectangle([px(r["p50"]) - 2, by - 8, px(r["p50"]) + 2, by + 34], fill=P["accent"])
        if fa > 0:
            txt = f"P50 {fmt.format(r['p50'])}  ·  P10–P90 {fmt.format(r['p10'])}–{fmt.format(r['p90'])} {unit}  ·  n={r['n']}"
            d.text((x1 - d.textlength(txt, font=font(15)), y + 2), txt, font=font(15), fill=_mix(P["muted"], fa))
    if "status" in data:
        a, b = data["compare"]
        d.text((x0, 900), f"{a.upper()} VS {b.upper()}", font=font(14, True), fill=P["muted"])
        _status_badge(d, data["status"], x0, 922, _fade(u, 0.7, 0.95))
        if _fade(u, 0.7, 0.95) > 0:
            t = (f"effect {100 * data['effect']:+.0f} % (95% CI {100 * data['effect_ci'][0]:+.0f} to {100 * data['effect_ci'][1]:+.0f} %), "
                 f"positive = better; threshold {100 * float(data['min_effect']):.0f} %")
            d.text((x0 + 330, 944), t, font=font(15), fill=_mix(P["muted"], _fade(u, 0.7, 0.95)))
    return img


def draw_paired(data, u, shot, report, deck):
    img, d = _frame(shot, report, deck)
    a0, a1 = data["axis"]
    x0, x1, ybot = 56, W - 56, 700
    px = lambda v: x0 + (x1 - x0) * (v - a0) / (a1 - a0)
    unit, fmt = shot.get("unit", ""), shot.get("fmt", "{:.1f}")
    _axis(d, a0, a1, data["ticks"], ybot, x0, x1, f"paired difference {data['a']} − {data['b']} ({unit})" if unit else f"paired difference {data['a']} − {data['b']}", "{:g}")
    d.line([(px(0), 250), (px(0), ybot)], fill=P["ink"], width=2)
    d.text((px(0) + 8, 252), "no difference", font=font(13), fill=P["muted"])
    arrow = "← lower is better" if data["better"] == "lower" else "higher is better →"
    ax = x0 if data["better"] == "lower" else x1 - d.textlength(arrow, font=font(13, True))
    d.text((ax, 252), arrow, font=font(13, True), fill=P["muted"])
    e = _ease(u)
    diffs = data["diffs"]
    show = int(len(diffs) * min(1.0, u / 0.7))
    for i, v in enumerate(diffs[:show]):               # strip: one dot per (year, seed) pair, jittered by index
        d.ellipse([px(v) - 4, 330 + (i % 7) * 12 - 4, px(v) + 4, 330 + (i % 7) * 12 + 4], fill=_mix(P["streak_hi"], 0.8))
    m, lo, hi = data["mean"], data["ci"][0], data["ci"][1]
    yb = 520
    d.rectangle([px(m - (m - lo) * e), yb - 8, px(m + (hi - m) * e), yb + 8], fill=_mix(P["streak_lo"], 0.95))
    d.polygon([(px(m), yb - 18), (px(m) + 12, yb), (px(m), yb + 18), (px(m) - 12, yb)], fill=P["accent"])
    fa = _fade(u)
    if fa > 0:
        d.text((x0, 580), "MEAN DIFFERENCE", font=font(14, True), fill=_mix(P["muted"], fa))
        d.text((x0, 600), f"{fmt.format(m)} {unit}   (95% CI {fmt.format(lo)} to {fmt.format(hi)})", font=font(26, True), fill=_mix(P["ink"], fa))
        d.text((x0, 640), f"relative to {data['b']}: {100 * data['rel']:+.0f} % (95% CI {100 * data['rel_ci'][0]:+.0f} to {100 * data['rel_ci'][1]:+.0f} %)  ·  n = {data['n_pairs']} pairs (year × seed)",
               font=font(15), fill=_mix(P["muted"], fa))
    fs = _fade(u, 0.7, 0.95)
    d.text((x0, 780), f"{data['a'].upper()} VS {data['b'].upper()}", font=font(14, True), fill=P["muted"])
    _status_badge(d, data["status"], x0, 802, fs)
    if fs > 0:
        mn = f"{100 * float(data['min_effect']):.0f} %" if data["min_effect"] is not None else "n/a"
        d.text((x0 + 380, 826), f"effect {100 * data['effect']:+.0f} % (CI {100 * data['effect_ci'][0]:+.0f} to {100 * data['effect_ci'][1]:+.0f} %), positive = better; threshold {mn}",
               font=font(15), fill=_mix(P["muted"], fs))
    return img


def draw_gantt(data, u, shot, report, deck):
    img, d = _frame(shot, report, deck)
    t0, t1 = data["t0"], data["t1"]
    x0, x1, ytop = 56, W - 56, 290
    lanes = data["lanes"][:10]
    lh = min(56, 440 / max(len(lanes), 1))
    px = lambda t: x0 + (x1 - x0) * (t - t0) / max(t1 - t0, 1e-9)
    cut = t0 + (t1 - t0) * _ease(u)
    lx = 262
    for s in data["states"]:                                 # legend
        c = STATE_COLORS.get(s, P["muted"])
        d.rectangle([x0, lx - 0, x0 + 14, lx + 14], fill=c)
        d.text((x0 + 22, lx - 2), s.upper(), font=font(13, True), fill=P["ink"])
        x0_ = x0 + 22 + d.textlength(s.upper(), font=font(13, True)) + 26
        x0 = x0_ if x0_ < W - 150 else 56
    x0 = 56
    for i, ln in enumerate(lanes):
        y = ytop + i * lh
        d.text((x0, y - 2), ln["label"], font=font(14, True), fill=P["ink"])
        for a, b, s in ln["segments"]:
            if a >= cut:
                continue
            d.rectangle([px(a), y + 20, px(min(b, cut)), y + 20 + lh * 0.45], fill=STATE_COLORS.get(s, P["muted"]))
    yb = ytop + len(lanes) * lh + 10
    if data["hs"]:
        hs = [h for _, h in data["hs"]]
        hmax = max(hs) or 1.0
        d.text((x0, yb), "Hs, m", font=font(13, True), fill=P["muted"])
        pts = [(px(t), yb + 120 - 90 * h / hmax) for t, h in data["hs"] if t <= cut]
        if len(pts) > 1:
            d.line(pts, fill=P["streak_hi"], width=2)
        yb += 130
    hrs = (t1 - t0) / 3600.0
    step = next(s for s in (1, 2, 4, 6, 12, 24, 48, 96, 168, 336, 720, 1e9) if hrs / s <= 8)
    d.line([(x0, yb + 8), (x1, yb + 8)], fill=P["muted"], width=1)
    k = 0.0
    while k <= hrs + 1e-9:
        x = px(t0 + k * 3600)
        d.line([(x, yb + 8), (x, yb + 14)], fill=P["muted"], width=1)
        d.text((x - 8, yb + 18), f"{k:g}", font=font(13), fill=P["muted"])
        k += step
    d.text((x1 - d.textlength("hours into the run", font=font(13, True)), yb + 38), "hours into the run", font=font(13, True), fill=P["muted"])
    d.line([(px(cut), ytop - 10), (px(cut), yb + 8)], fill=P["accent"], width=2)
    return img


DRAW = {"fan": draw_fan, "paired": draw_paired, "state_gantt": draw_gantt}


def deck_lines(rules, values):
    lines = narrate.choose(rules, values).split("\n")
    if len(lines) > 2:
        raise narrate.NarrationError("the deck text has at most two lines")
    return lines + [""] * (2 - len(lines))


def run_findings(shot, report, frames_dir, fps=30, traj=None, weather=None, agents=None, size=None, only=None, log=print):
    """Render the findings frames. `only` = frame index (negative counts from the end). Returns
    {"n", "frames", "values", "deck", "data"}. Refuses (FindingsError) without a usable ensemble."""
    bad = problems(shot, report, traj is not None)
    if bad:
        raise FindingsError("findings shot refused:\n  " + "\n  ".join(bad))
    data, vals = measure(shot, report, traj, weather, agents)
    deck = deck_lines(shot["narration"], vals)
    log("narration: " + " ".join(deck))
    frames_dir = Path(frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)
    n = max(1, int(float(shot["seconds"]) * fps))
    idx = range(n) if only is None else [only % n]
    files = []
    for i in idx:
        u = min(1.0, (i + 1) / (0.8 * n))                  # build-in over the first 80 %, then hold
        img = DRAW[shot["kind"]](data, u, shot, report, deck)
        if size and tuple(size) != (W, H):
            img = fit(img, size)
        p = frames_dir / f"f{i:04d}.png"
        img.save(p)
        files.append(p)
    return {"n": n, "frames": files, "values": vals, "deck": deck, "data": data}


def render_findings_shot(shot, sb, out_mp4, fps=30, report=None, traj=None, weather=None, agents=None, size=None,
                         frames_dir=None, keep_frames=False, log=print):
    out = Path(out_mp4)
    out.parent.mkdir(parents=True, exist_ok=True)
    fd = Path(frames_dir) if frames_dir else out.with_name(out.stem + "_frames")
    res = run_findings(shot, report, fd, fps, traj, weather, agents, size, None, log)
    encode(fd, out, fps)
    if not keep_frames:
        shutil.rmtree(fd, ignore_errors=True)
    log(f"{out} {res['n']} frames")
    return res
