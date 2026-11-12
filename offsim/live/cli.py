"""`offsim live`: probe every external dependency once and write docs/LIVE_STATUS.md and live_status.json.

    python -m offsim.live.cli                                   # all probes (needs network)
    python -m offsim.live.cli --only overpass,geofabrik --strict
    python -m offsim.live.cli --list

Exit code is 0 unless --strict is given and a probe failed (skipped probes never fail). An unknown probe name in
--only is a usage error (exit 2). --issue-body FILE writes the text for the live-check issue only when a probe failed
or a response schema changed; otherwise the file is removed.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from offsim.live import probes as P


def _run_url() -> str | None:
    server, repo, run = (os.environ.get(k) for k in ("GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID"))
    return f"{server}/{repo}/actions/runs/{run}" if server and repo and run else None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="offsim live", description="Probe the external dependencies once (offsim/live).")
    ap.add_argument("--only", default="", help="comma list of probe names (default: all)")
    ap.add_argument("--out", default=str(P.MD_PATH), help="markdown table (default docs/LIVE_STATUS.md)")
    ap.add_argument("--json", default=str(P.JSON_PATH), help="machine-readable status (default live_status.json)")
    ap.add_argument("--issue-body", default="", metavar="FILE",
                    help="write an issue body when a probe failed or a schema changed; remove FILE otherwise")
    ap.add_argument("--strict", action="store_true", help="exit 1 when any probe failed")
    ap.add_argument("--list", action="store_true", help="print the probe names and exit")
    a = ap.parse_args(argv)

    if a.list:
        print("\n".join(P.PROBES))
        return 0
    names = [n.strip() for n in a.only.split(",") if n.strip()] or None
    unknown = [n for n in names or [] if n not in P.PROBES]
    if unknown:
        print(f"unknown probe(s): {', '.join(unknown)}; known: {', '.join(P.PROBES)}", file=sys.stderr)
        return 2

    prev = P.load_previous(a.json)
    results = P.run_all(names, out_md=Path(a.out), out_json=Path(a.json))
    ran = [r for r in results if r["name"] in (names or P.PROBES)]
    for r in ran:
        lat = "-" if r.get("latency_s") is None else f"{r['latency_s']:.2f}s"
        print(f"{r['name']:<22} {r['status']:<8} {lat:>8}  {r['detail']}")

    failed = [r for r in ran if r["status"] == "fail"]
    changed = P.diff_schema(prev, results)
    print(f"{len(ran)} probes: {sum(r['status'] == 'ok' for r in ran)} ok, {len(failed)} failed, "
          f"{sum(r['status'] == 'skipped' for r in ran)} skipped; schema changed: {', '.join(changed) or 'none'}")

    if a.issue_body:
        body = P.issue_body(ran, changed, P.schema_delta(prev, results), run_url=_run_url())
        path = Path(a.issue_body)
        if body:
            path.write_text(body)
        else:
            path.unlink(missing_ok=True)
    return 1 if (a.strict and failed) else 0


if __name__ == "__main__":
    raise SystemExit(main())
