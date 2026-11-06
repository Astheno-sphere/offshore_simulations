"""Catalog: catalog/tools.yaml -> docs/TOOLS.md, plus a search.

    python tools/catalog_build.py                 # regenerate docs/TOOLS.md
    python tools/catalog_build.py --find weather  # search name, role, layer, id
    python tools/catalog_build.py --now           # what the first paper needs
"""
import argparse
import sys
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "catalog/tools.yaml"
OUT = ROOT / "docs/TOOLS.md"
STATUS = ("tested", "installed", "candidate", "manual", "watch")
RUNS = ("here", "actions", "laptop", "browser")
PRIORITY = ("now", "next", "later")
FIELDS = ("id", "name", "url", "layer", "licence", "status", "runs", "priority", "role")


def load():
    return yaml.safe_load(SRC.read_text())


def problems(cat):
    out, seen = [], set()
    for t in cat["tools"]:
        miss = [f for f in FIELDS if not t.get(f)]
        if miss:
            out.append(f"{t.get('id')}: missing {miss}")
        if t.get("id") in seen:
            out.append(f"{t['id']}: duplicate id")
        seen.add(t.get("id"))
        if t.get("layer") not in cat["layers"]:
            out.append(f"{t.get('id')}: unknown layer {t.get('layer')}")
        for f, ok in (("status", STATUS), ("runs", RUNS), ("priority", PRIORITY)):
            if t.get(f) not in ok:
                out.append(f"{t.get('id')}: {f}={t.get(f)} not in {ok}")
        if not str(t.get("url", "")).startswith("https://"):
            out.append(f"{t.get('id')}: url must be https")
    return out


def render(cat):
    tools = cat["tools"]
    st = Counter(t["status"] for t in tools)
    lines = ["# Tool catalog", "",
             "Generated from [`catalog/tools.yaml`](../catalog/tools.yaml) by `tools/catalog_build.py`; edit the YAML, not this file.",
             f"{len(tools)} tools · " + " · ".join(f"{st[s]} {s}" for s in STATUS) + ".", "",
             "**status** tested = ran here with a recorded result · installed = installs, not exercised · candidate = fits a planned step · "
             "manual = order/download by hand · watch = not on the plan yet.  ",
             "**runs** here = Claude workspace · actions = GitHub runner (open internet) · laptop · browser.  ",
             "**licence** `check` = not verified: read it before copying anything. GPL code runs as a separate process, never imported.", "",
             "## Needed for the first paper (priority: now)", "",
             "| Tool | Layer | Status | Runs | Role |", "|---|---|---|---|---|"]
    lines += [f"| [{t['name']}]({t['url']}) | {t['layer']} | {t['status']} | {t['runs']} | {t['role']} |"
              for t in tools if t["priority"] == "now"]
    for layer, desc in cat["layers"].items():
        sel = [t for t in tools if t["layer"] == layer]
        if not sel:
            continue
        lines += ["", f"## {layer}", "", f"_{desc}_", "", "| Tool | Licence | Status | Runs | Priority | Role |", "|---|---|---|---|---|---|"]
        order = {p: i for i, p in enumerate(PRIORITY)}
        for t in sorted(sel, key=lambda t: (order[t["priority"]], t["name"].lower())):
            lines.append(f"| [{t['name']}]({t['url']}) | {t['licence']} | {t['status']} | {t['runs']} | {t['priority']} | {t['role']} |")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--find")
    ap.add_argument("--now", action="store_true")
    ap.add_argument("--check", action="store_true", help="exit 1 if docs/TOOLS.md is stale or the YAML is invalid")
    a = ap.parse_args()
    cat = load()
    errs = problems(cat)
    if errs:
        print("\n".join(errs))
        sys.exit(1)
    if a.find or a.now:
        q = (a.find or "").lower()
        for t in cat["tools"]:
            hay = " ".join(str(t[f]) for f in FIELDS).lower()
            if (a.now and t["priority"] == "now") or (q and q in hay):
                print(f"[{t['layer']}/{t['status']}/{t['priority']}] {t['name']} — {t['url']}\n    {t['role']}")
        return
    text = render(cat)
    if a.check:
        sys.exit(0 if OUT.exists() and OUT.read_text() == text else 1)
    OUT.write_text(text)
    print(f"wrote {OUT.relative_to(ROOT)} ({len(cat['tools'])} tools)")


if __name__ == "__main__":
    main()
