"""Narration chosen from measurements: the on-screen sentence is picked by rules over numbers, never hand-written.

    rules = [{"when": "deck_excess_max >= 5", "text": "... up to +{deck_excess_max:.0f} degC ..."},
             {"when": "plume_seen > 0",        "text": "... never lower than {plume_min_m:.0f} m ..."},
             {"text": "default sentence"}]          # a final rule without `when` is the default
    text = choose(rules, values)                    # first matching rule wins

`values` is a flat dict (`flatten(report)` for report refs, plus whatever the shot measured). `when` is evaluated by
a small SAFE evaluator on the ast (no eval): names, numbers, strings, comparisons, and/or/not, + - * /, and the
calls abs/min/max. Anything else (attribute access, subscripts, other calls, lambdas, comprehensions) is refused.
A dotted name (`kpis.distance_km`) is accepted only when that exact dotted key exists in `values`.
A name used in `when` or in `{name:fmt}` that is not in `values` is an error, never a silent default.
`text` placeholders use `{name:fmt}` with the same dotted names; there is no attribute or index access in them.
"""
from __future__ import annotations

import ast
import math
import operator
import re

__all__ = ["NarrationError", "choose", "flatten", "names_used", "validate_rules", "evaluate"]


class NarrationError(ValueError):
    """Bad rule, unsafe expression, or a name that was not measured."""


_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
_CMP = {ast.Lt: operator.lt, ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge,
        ast.Eq: operator.eq, ast.NotEq: operator.ne}
_FUNCS = {"abs": abs, "min": min, "max": max}
_PLACEHOLDER = re.compile(r"\{([A-Za-z_][\w.]*)(?::([^{}]*))?\}")


def _dotted(node):
    """'a.b.c' for a Name / Attribute chain of plain names, else None."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def _parse(expr: str):
    if not isinstance(expr, str) or not expr.strip():
        raise NarrationError(f"empty `when` expression: {expr!r}")
    try:
        return ast.parse(expr.strip(), mode="eval").body
    except SyntaxError as e:
        raise NarrationError(f"cannot parse `when` {expr!r}: {e.msg}") from None


def _walk(node, values, names):
    """Evaluate node against values (dict) or, when values is None, only collect the names used into `names`."""
    ev = values is not None
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float, str, bool)):
            return node.value
        raise NarrationError(f"constant {node.value!r} not allowed")
    if isinstance(node, (ast.Name, ast.Attribute)):
        key = _dotted(node)
        if key is None:
            raise NarrationError("attribute access is not allowed")
        if key.split(".")[0].startswith("_") or any(p.startswith("_") for p in key.split(".")):
            raise NarrationError(f"name {key!r} not allowed")
        if isinstance(node, ast.Attribute) and key not in (values or {}) and ev:
            raise NarrationError(f"attribute access is not allowed ({key!r} is not a measured value)")
        names.add(key)
        if not ev:
            return None
        if key not in values:
            raise NarrationError(f"name {key!r} was not measured (have {sorted(values)[:12]}...)")
        return values[key]
    if isinstance(node, ast.BoolOp):
        vals = []
        for v in node.values:
            r = _walk(v, values, names)
            vals.append(r)
            if ev and ((isinstance(node.op, ast.And) and not r) or (isinstance(node.op, ast.Or) and r)):
                # short-circuit for the value, but still collect names of the remaining operands
                for rest in node.values[node.values.index(v) + 1:]:
                    _walk(rest, None, names)
                return r
        return vals[-1] if ev else None
    if isinstance(node, ast.UnaryOp):
        x = _walk(node.operand, values, names)
        if isinstance(node.op, ast.Not):
            return (not x) if ev else None
        if isinstance(node.op, ast.USub):
            return -x if ev else None
        if isinstance(node.op, ast.UAdd):
            return +x if ev else None
        raise NarrationError(f"operator {type(node.op).__name__} not allowed")
    if isinstance(node, ast.BinOp):
        if type(node.op) not in _BIN:
            raise NarrationError(f"operator {type(node.op).__name__} not allowed")
        a, b = _walk(node.left, values, names), _walk(node.right, values, names)
        if not ev:
            return None
        try:
            return _BIN[type(node.op)](a, b)
        except (ZeroDivisionError, TypeError) as e:
            raise NarrationError(f"cannot compute: {e}") from None
    if isinstance(node, ast.Compare):
        left = _walk(node.left, values, names)
        out = True
        for op, comp in zip(node.ops, node.comparators):
            if type(op) not in _CMP:
                raise NarrationError(f"comparison {type(op).__name__} not allowed")
            right = _walk(comp, values, names)
            if ev:
                try:
                    out = out and bool(_CMP[type(op)](left, right))
                except TypeError as e:
                    raise NarrationError(f"cannot compare: {e}") from None
            left = right
        return out if ev else None
    if isinstance(node, ast.Call):
        if not (isinstance(node.func, ast.Name) and node.func.id in _FUNCS) or node.keywords:
            raise NarrationError("only abs(), min(), max() may be called")
        args = [_walk(a, values, names) for a in node.args]
        if not args:
            raise NarrationError(f"{node.func.id}() needs arguments")
        return _FUNCS[node.func.id](*args) if ev else None
    raise NarrationError(f"{type(node).__name__} is not allowed in a `when` expression")


def evaluate(expr: str, values: dict):
    """Safe evaluation of one `when` expression."""
    return _walk(_parse(expr), values, set())


def names_used(expr: str) -> set[str]:
    """Names an expression refers to (also validates that it only uses allowed syntax)."""
    names: set[str] = set()
    _walk(_parse(expr), None, names)
    return names


def _fmt_names(text: str) -> set[str]:
    return {m.group(1) for m in _PLACEHOLDER.finditer(text)}


def render_text(text: str, values: dict) -> str:
    def sub(m):
        key, spec = m.group(1), m.group(2) or ""
        if key not in values:
            raise NarrationError(f"text placeholder {{{key}}} was not measured")
        try:
            return format(values[key], spec)
        except (ValueError, TypeError) as e:
            raise NarrationError(f"cannot format {key}={values[key]!r} with {spec!r}: {e}") from None
    return _PLACEHOLDER.sub(sub, text)


def validate_rules(rules, known: set[str] | None = None, need_default: bool = True) -> list[str]:
    """Static check of a rule list; returns problems (empty = ok). With `known`, every name must be in it."""
    probs: list[str] = []
    if not isinstance(rules, list) or not rules:
        return ["narration rules missing: a list of {when, text} with a final default {text} is required"]
    for i, r in enumerate(rules):
        if not isinstance(r, dict) or not isinstance(r.get("text"), str) or not r["text"].strip():
            probs.append(f"narration rule {i}: needs a text")
            continue
        used = _fmt_names(r["text"])
        if "when" in r:
            try:
                used |= names_used(r["when"])
            except NarrationError as e:
                probs.append(f"narration rule {i}: {e}")
        elif i != len(rules) - 1:
            probs.append(f"narration rule {i}: only the final rule may omit `when` (it is the default)")
        if known is not None:
            miss = sorted(u for u in used if u not in known)
            if miss:
                probs.append(f"narration rule {i}: names not measured: {miss}")
    if need_default and isinstance(rules[-1], dict) and "when" in rules[-1]:
        probs.append("narration rules need a final default rule (no `when`)")
    return probs


def choose(rules: list[dict], values: dict) -> str:
    """First rule whose `when` holds wins; a rule without `when` always matches (the default)."""
    bad = [p for p in validate_rules(rules, need_default=False) if "narration rule" in p and "only the final" not in p]
    if bad:
        raise NarrationError("; ".join(bad))
    for r in rules:
        if "when" not in r or evaluate(r["when"], values):
            return render_text(r["text"], values)
    raise NarrationError("no narration rule matched and there is no default rule")


def flatten(report: dict, prefix: str = "") -> dict:
    """Dotted flat view of a report: {"kpis.distance_km": 113.3, "ensemble.wait_s.base.p50": ...}. Numbers, bools and
    strings only (NaN/None dropped); lists are skipped. For an ensemble block, `ensemble.<kpi>.<stat>` is also given
    when the KPI has a single variant (`ensemble.<kpi>.<variant>.<stat>` is always given)."""
    out: dict = {}

    def rec(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                rec(v, f"{path}.{k}" if path else str(k))
        elif isinstance(node, bool) or isinstance(node, str):
            out[path] = node
        elif isinstance(node, (int, float)) and math.isfinite(node):
            out[path] = node

    rec(report, prefix)
    ens = report.get("ensemble") if isinstance(report, dict) else None
    if isinstance(ens, dict) and isinstance(ens.get("quantiles"), dict):
        pre = f"{prefix}." if prefix else ""
        for kpi, by_var in ens["quantiles"].items():
            if not isinstance(by_var, dict):
                continue
            for v, row in by_var.items():
                if isinstance(row, dict):
                    for stat, x in row.items():
                        if isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x):
                            out[f"{pre}ensemble.{kpi}.{v}.{stat}"] = x
                            if len(by_var) == 1:
                                out[f"{pre}ensemble.{kpi}.{stat}"] = x
    return out
