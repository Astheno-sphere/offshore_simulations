"""Live probes: one small check per external dependency, so the weekly live-check workflow shows which hosts still
answer, in the shape the code expects. Stdlib only: the job installs pyyaml and amplpy and nothing else.

    from offsim.live.probes import PROBES, run_all
    results = run_all(["overpass", "geofabrik"], fetch=my_fake)     # tests inject fetch; the workflow uses urllib

Contract. Every probe is `probe_x(fetch=None, timeout=60, env=None)` and returns one result dict:
    {name, ok, status, latency_s, detail, schema, checked_utc}
- ok: True or False; None when skipped. status: "ok" | "fail" | "skipped".
- schema: sorted top-level keys or variable names seen in the answer. run_all adds schema_hash (a hash of schema).
  A failing probe keeps the schema of its last good run, so a timeout never looks like a schema change.
- A probe never raises. Timeouts, HTTP errors and garbage bodies become ok False with a short detail.
- Secrets (AMPL_LICENSE_UUID, BW_CLIENT_SECRET, tokens, OFFSIM_MAILTO) never reach detail, logs or files.

fetch: injectable `fetch(url, method="GET", data=None, headers=None, timeout=60) -> Resp(status, headers, body)`.
The default (urllib) returns HTTP error statuses as a Resp instead of raising. Network errors raise, and the probe
records them. Every probe uses one fixed, small request (one record, a tiny box, or a HEAD) and is UNVERIFIED LIVE
until the first live-check run has logged it (docs/LIVE_STATUS.md).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, NamedTuple, Optional

ROOT = Path(__file__).resolve().parents[2]
MD_PATH = ROOT / "docs" / "LIVE_STATUS.md"
JSON_PATH = ROOT / "live_status.json"
BUDGET_S = 120.0                                  # wall budget per probe in run_all
USER_AGENT = "offsim-live-check/1.0"
DEFAULT_ENTUR_CLIENT = "offsim-livecheck"         # ET-Client-Name when ENTUR_CLIENT_NAME is unset (company-application)


class Resp(NamedTuple):
    status: int
    headers: dict          # lower-case header names
    body: bytes


def default_fetch(url, method="GET", data=None, headers=None, timeout=60) -> Resp:
    """urllib request. HTTP error statuses come back as Resp; network errors (timeouts, DNS) raise."""
    req = urllib.request.Request(url, data=data, method=method, headers={"User-Agent": USER_AGENT, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = b"" if method == "HEAD" else r.read(8 << 20)
            return Resp(r.status, {k.lower(): v for k, v in r.headers.items()}, body)
    except urllib.error.HTTPError as e:
        body = b""
        if method != "HEAD":
            try:
                body = e.read(1 << 16)
            except OSError:
                body = b""
        return Resp(e.code, {k.lower(): v for k, v in (e.headers or {}).items()}, body)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _getter(fetch, timeout):
    f = fetch or default_fetch          # resolved per call, so tests can swap default_fetch

    def call(url, method="GET", data=None, headers=None):
        return f(url, method=method, data=data, headers=headers, timeout=timeout)
    return call


def _http_problem(resp: Resp) -> Optional[str]:
    if 200 <= resp.status < 300:
        return None
    if resp.status == 429:
        return f"HTTP 429 (rate limited; Retry-After {resp.headers.get('retry-after', 'absent')})"
    return f"HTTP {resp.status}"


def _json(resp: Resp):
    try:
        return json.loads(resp.body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as e:
        raise ValueError(f"body is not JSON ({len(resp.body)} bytes)") from e


def _keys(js) -> list:
    return list(js.keys()) if isinstance(js, dict) else []


def _schema_json(js, path=()) -> list:
    """Top-level keys, plus the keys of the first record of the list at `path` (named '<last>[].<key>')."""
    out = _keys(js)
    node = js
    for k in path:
        node = node.get(k) if isinstance(node, dict) else None
    if path and isinstance(node, list) and node and isinstance(node[0], dict):
        out += [f"{path[-1]}[].{k}" for k in node[0]]
    return out


def _scrub(text, secrets=()) -> str:
    text = str(text)
    for s in secrets:
        if s:
            text = text.replace(s, "<redacted>")
    return text


def _finish(name, status, started, detail, schema=()) -> dict:
    return {"name": name, "ok": {"ok": True, "fail": False, "skipped": None}[status], "status": status,
            "latency_s": round(time.monotonic() - started, 3), "detail": " ".join(str(detail).split())[:500],
            "schema": sorted({str(s) for s in schema}), "checked_utc": _now()}


def _run(name, body, skip=None, secrets=()) -> dict:
    """Run body() -> (ok, detail, schema). A skip reason short-circuits. Any exception becomes a failed result."""
    started = time.monotonic()
    if skip:
        return _finish(name, "skipped", started, f"skipped: {skip}")
    try:
        ok, detail, schema = body()
    except Exception as e:  # noqa: BLE001 - a probe reports its failure and never raises
        return _finish(name, "fail", started, _scrub(f"{type(e).__name__}: {e}", secrets))
    return _finish(name, "ok" if ok else "fail", started, _scrub(detail, secrets), schema)


def _int(v) -> Optional[int]:
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


# --- overpass --------------------------------------------------------------------------------------------------
OVERPASS = "https://overpass-api.de/api/interpreter"
OVERPASS_RETRY_S = 5.0                                 # one retry on a 502/503 waits this long (tests set it to 0)
MOLDE_COAST = (62.72, 7.10, 62.76, 7.20)          # south, west, north, east (Overpass order): a few km of coast


def probe_overpass(fetch=None, timeout=60, env=None) -> dict:
    s, w, n, e = MOLDE_COAST
    q = f'[out:json][timeout:25];way["natural"="coastline"]({s},{w},{n},{e});out ids;'

    def body():
        get = _getter(fetch, timeout)
        # Overpass answers a good query with 502/503 when its queue is full and
        # the same query succeeds minutes later (verified 2026-11-13: two full
        # live runs 502'd in <1 s, two standalone runs returned 57 ways in
        # ~30-40 s). One retry on a gateway error only, so a momentary overload
        # does not open a false live-check issue; the shape check below is
        # unchanged, and a persistent 502/503 still fails.
        r = None
        for attempt in (1, 2):
            r = get(OVERPASS, method="POST", data=urllib.parse.urlencode({"data": q}).encode(),
                    headers={"Content-Type": "application/x-www-form-urlencoded"})
            if r.status not in (502, 503) or attempt == 2:
                break
            time.sleep(OVERPASS_RETRY_S)
        if (bad := _http_problem(r)):
            return False, bad, []
        js = _json(r)
        els = js.get("elements") if isinstance(js, dict) else None
        if not isinstance(els, list):
            return False, "no elements list in the answer", _schema_json(js)
        ok = len(els) > 0
        detail = f"{len(els)} coastline ways in the Molde box" + ("" if ok else " (expected at least 1)")
        return ok, detail, _schema_json(js, ("elements",))
    return _run("overpass", body)


# --- sodir (FactMaps FeatureServer) ----------------------------------------------------------------------------
SODIR = "https://factmaps.sodir.no/api/rest/services/Factmaps/FactMapsWGS84/FeatureServer"


def probe_sodir(fetch=None, timeout=60, env=None) -> dict:
    def body():
        r = _getter(fetch, timeout)(f"{SODIR}?f=json")
        if (bad := _http_problem(r)):
            return False, bad, []
        js = _json(r)
        layers = js.get("layers") if isinstance(js, dict) else None
        if not isinstance(layers, list) or not layers:
            return False, "no layers in the FeatureServer metadata", _keys(js)
        return True, f"{len(layers)} layers listed", _keys(js)
    return _run("sodir", body)


# --- METOCEAN (OPeNDAP .dds: variable names only, no data) -----------------------------------------------------
THREDDS = "https://thredds.met.no/thredds/dodsC"
# One fixed sample file per product (January 2024), same URL patterns as offsim/weather/fetch.py; `expect` are the
# native variables that module reads, so a rename shows up as a failure, not as a silent gap.
METOCEAN = {
    "nora3_wind": (f"{THREDDS}/nora3_subset_atmos/wind_hourly_v2/arome3kmwind_1hr_202401.nc",
                   {"wind_speed", "wind_direction"}),
    "nora3_wave": (f"{THREDDS}/nora3_subset_wave/wave_tser/202401_NORA3wave_sub_time_unlimited.nc",
                   {"hs", "tp", "thq"}),
    "norkyst": (f"{THREDDS}/romshindcast/norkyst_v3/zdepth/2024/01/norkyst800-20240110.nc",
                {"u_eastward", "v_northward"}),
}
_DDS_TYPE = re.compile(r"^\s*(?:Float32|Float64|Int8|UInt8|Byte|Int16|UInt16|Int32|UInt32|Int64|UInt64|Url|String)"
                       r"\s+(\w+)")
_DDS_OPEN = re.compile(r"^\s*(?:Grid|Structure|Sequence)\s*\{")
_DDS_CLOSE = re.compile(r"^\s*\}\s*(\w+)\s*;")


def parse_dds(text: str) -> list:
    """Variable names of an OPeNDAP DDS: base-type declarations, plus the names of grids and structures (named on
    their closing line). The dataset's own closing line carries the file name and is not a variable."""
    if not re.search(r"^\s*Dataset\s*\{", text, re.M):
        raise ValueError("not a DDS (no Dataset block)")
    names, depth = [], 0
    for line in text.splitlines():
        close = _DDS_CLOSE.match(line)
        if close:
            if depth:
                depth -= 1
                names.append(close.group(1))
            continue
        if _DDS_OPEN.match(line):
            depth += 1
            continue
        m = _DDS_TYPE.match(line)
        if m:
            names.append(m.group(1))
    return sorted(set(names))


def _dds_probe(name, fetch, timeout):
    url, expect = METOCEAN[name]

    def body():
        r = _getter(fetch, timeout)(url + ".dds")
        if (bad := _http_problem(r)):
            return False, bad, []
        names = parse_dds(r.body.decode("utf-8", "replace"))
        missing = sorted(expect - set(names))
        if missing:
            return False, f"variables missing: {', '.join(missing)}", names
        return True, f"{len(names)} variables, all {len(expect)} expected present", names
    return _run(name, body)


def probe_nora3_wind(fetch=None, timeout=60, env=None) -> dict:
    return _dds_probe("nora3_wind", fetch, timeout)


def probe_nora3_wave(fetch=None, timeout=60, env=None) -> dict:
    return _dds_probe("nora3_wave", fetch, timeout)


def probe_norkyst(fetch=None, timeout=60, env=None) -> dict:
    return _dds_probe("norkyst", fetch, timeout)


# --- Kartverket place names and DTM ----------------------------------------------------------------------------
STEDSNAVN = "https://ws.geonorge.no/stedsnavn/v1/navn"
GEONORGE_API = "https://nedlasting.geonorge.no/api"
GEONORGE_DTM_UUID = "fd851873-f363-46f9-9fc6-bb1b403575df"   # Kartverket DTM 10, as in offsim/worlds/oslofjord.yaml


def probe_kartverket_stedsnavn(fetch=None, timeout=60, env=None) -> dict:
    url = STEDSNAVN + "?" + urllib.parse.urlencode(
        {"sok": "Molde", "fuzzy": "false", "utkoordsys": "4258", "treffPerSide": "5"})

    def body():
        r = _getter(fetch, timeout)(url)
        if (bad := _http_problem(r)):
            return False, bad, []
        js = _json(r)
        hits = js.get("navn") if isinstance(js, dict) else None
        if not isinstance(hits, list) or not hits:
            return False, "no hits for Molde", _keys(js)
        with_point = [h for h in hits if isinstance(h, dict) and isinstance(h.get("representasjonspunkt"), dict)]
        return bool(with_point), f"{len(hits)} hits for Molde, {len(with_point)} with a point", _schema_json(js, ("navn",))
    return _run("kartverket_stedsnavn", body)


def probe_geonorge_dtm(fetch=None, timeout=60, env=None) -> dict:
    env = os.environ if env is None else env
    uuid = (env.get("OFFSIM_DTM_UUID") or "").strip() or GEONORGE_DTM_UUID
    url = f"{GEONORGE_API}/capabilities/{urllib.parse.quote(uuid)}"

    def body():
        r = _getter(fetch, timeout)(url)
        if (bad := _http_problem(r)):
            return False, bad, []
        js = _json(r)
        if not isinstance(js, dict) or not js:
            return False, "empty capabilities answer", []
        return True, f"capabilities answered; polygon selection {js.get('supportsPolygonSelection')}", _keys(js)
    return _run("geonorge_dtm", body)


# --- downloads (HEAD only: size and headers, no file body) -----------------------------------------------------
GEOFABRIK = "https://download.geofabrik.de/europe/norway-latest.osm.pbf"      # offsim/worlds/osm.py GEOFABRIK_NORWAY
ENTUR_GTFS = "https://storage.googleapis.com/marduk-production/outbound/gtfs/rb_norway-aggregated-gtfs.zip"
_HEAD_KEYS = ("content-length", "content-type", "last-modified")


def _head_probe(name, url, fetch, timeout, label):
    def body():
        r = _getter(fetch, timeout)(url, method="HEAD")
        if (bad := _http_problem(r)):
            return False, bad, []
        seen = sorted(h for h in _HEAD_KEYS if h in r.headers)
        size = _int(r.headers.get("content-length"))
        if not size:
            return False, "no Content-Length header", seen
        return True, f"{label} {size / 1e6:.0f} MB, last-modified {r.headers.get('last-modified', 'unknown')}", seen
    return _run(name, body)


def probe_geofabrik(fetch=None, timeout=60, env=None) -> dict:
    return _head_probe("geofabrik", GEOFABRIK, fetch, timeout, "norway-latest.osm.pbf")


def probe_entur_gtfs(fetch=None, timeout=60, env=None) -> dict:
    return _head_probe("entur_gtfs", ENTUR_GTFS, fetch, timeout, "aggregated GTFS zip")


# --- entur realtime (GraphQL POST, ET-Client-Name required) ----------------------------------------------------
ENTUR_VEHICLES = "https://api.entur.io/realtime/v2/vehicles/graphql"
VEHICLES_QUERY = ("query V($minLat: Float!, $minLon: Float!, $maxLat: Float!, $maxLon: Float!) "
                  "{ vehicles(boundingBox: {minLat: $minLat, minLon: $minLon, maxLat: $maxLat, maxLon: $maxLon}) "
                  "{ vehicleId line { lineRef publicCode } serviceJourney { id } lastUpdated "
                  "location { latitude longitude } delay bearing speed } }")
OSLO_CENTRE_BOX = {"minLat": 59.88, "minLon": 10.70, "maxLat": 59.95, "maxLon": 10.85}


def client_name(env) -> str:
    return (env.get("ENTUR_CLIENT_NAME") or "").strip() or DEFAULT_ENTUR_CLIENT


def probe_entur_vehicles(fetch=None, timeout=60, env=None) -> dict:
    env = os.environ if env is None else env
    headers = {"ET-Client-Name": client_name(env), "Content-Type": "application/json", "Accept": "application/json"}
    payload = json.dumps({"query": VEHICLES_QUERY, "variables": OSLO_CENTRE_BOX}).encode()

    def body():
        r = _getter(fetch, timeout)(ENTUR_VEHICLES, method="POST", data=payload, headers=headers)
        if (bad := _http_problem(r)):
            return False, bad, []
        js = _json(r)
        if not isinstance(js, dict):
            return False, "answer is not a JSON object", []
        data = js.get("data")
        if js.get("errors") and not data:
            msg = "; ".join(str(e.get("message", e)) if isinstance(e, dict) else str(e) for e in js["errors"])
            return False, f"GraphQL errors: {msg}", _schema_json(js)
        vehicles = data.get("vehicles") if isinstance(data, dict) else None
        if not isinstance(vehicles, list):
            return False, "no data.vehicles list", _schema_json(js)
        # An empty list is a valid answer (night, quiet box); field names then come from the top level only.
        return True, f"{len(vehicles)} vehicles in the Oslo box", _schema_json(js, ("data", "vehicles"))
    return _run("entur_vehicles", body)


# --- barentswatch (token only; skipped without credentials) ----------------------------------------------------
BW_TOKEN = "https://id.barentswatch.no/connect/token"


def probe_barentswatch(fetch=None, timeout=60, env=None) -> dict:
    env = os.environ if env is None else env
    cid = (env.get("BW_CLIENT_ID") or "").strip()
    secret = (env.get("BW_CLIENT_SECRET") or "").strip()
    if not cid:
        return _run("barentswatch", None, skip="BW_CLIENT_ID not set")
    if not secret:
        return _run("barentswatch", None, skip="BW_CLIENT_SECRET not set")
    form = urllib.parse.urlencode({"grant_type": "client_credentials", "client_id": cid,
                                   "client_secret": secret, "scope": "ais"}).encode()

    def body():
        r = _getter(fetch, timeout)(BW_TOKEN, method="POST", data=form,
                                    headers={"Content-Type": "application/x-www-form-urlencoded"})
        if (bad := _http_problem(r)):
            return False, bad, []
        js = _json(r)
        if not isinstance(js, dict) or not js.get("access_token"):
            return False, "no access_token in the answer", _keys(js)
        return True, f"token issued (expires_in {js.get('expires_in', 'unknown')} s)", _keys(js)
    return _run("barentswatch", body, secrets=(cid, secret))


# --- literature sources (same query shapes as offsim/feed/sources.py) ------------------------------------------
OPENALEX = "https://api.openalex.org/works"
CROSSREF = "https://api.crossref.org/works"
ARXIV = "https://export.arxiv.org/api/query"
NVA = "https://api.nva.unit.no/search/resources"
ATOM = "{http://www.w3.org/2005/Atom}"


def probe_openalex(fetch=None, timeout=60, env=None) -> dict:
    env = os.environ if env is None else env
    mail = (env.get("OFFSIM_MAILTO") or "").strip()
    params = {"filter": "from_publication_date:2025-01-01,title_and_abstract.search:offshore", "per-page": 1}
    if mail:
        params["mailto"] = mail
    url = OPENALEX + "?" + urllib.parse.urlencode(params)
    pool = "polite pool" if mail else "anonymous pool (OFFSIM_MAILTO not set)"

    def body():
        r = _getter(fetch, timeout)(url)
        if (bad := _http_problem(r)):
            return False, f"{bad} on the {pool}", []
        js = _json(r)
        results = js.get("results") if isinstance(js, dict) else None
        if not isinstance(results, list):
            return False, "no results list", _keys(js)
        if not results:
            return False, f"zero records for the probe query on the {pool}", _schema_json(js, ("results",))
        return True, f"{len(results)} record on the {pool}", _schema_json(js, ("results",))
    return _run("openalex", body, secrets=(mail,) if mail else ())


def probe_crossref(fetch=None, timeout=60, env=None) -> dict:
    env = os.environ if env is None else env
    mail = (env.get("OFFSIM_MAILTO") or "").strip()
    params = {"rows": 1, "query.bibliographic": "offshore logistics", "filter": "from-pub-date:2025-01-01"}
    if mail:
        params["mailto"] = mail
    url = CROSSREF + "?" + urllib.parse.urlencode(params)

    def body():
        r = _getter(fetch, timeout)(url)
        if (bad := _http_problem(r)):
            return False, bad, []
        js = _json(r)
        items = (js.get("message") or {}).get("items") if isinstance(js, dict) else None
        if not isinstance(items, list):
            return False, "no message.items list", _keys(js)
        return bool(items), f"{len(items)} item", _schema_json(js, ("message", "items"))
    return _run("crossref", body, secrets=(mail,) if mail else ())


def probe_arxiv(fetch=None, timeout=60, env=None) -> dict:
    url = ARXIV + "?" + urllib.parse.urlencode({"search_query": "all:offshore", "start": 0, "max_results": 1,
                                                 "sortBy": "submittedDate", "sortOrder": "descending"})

    def body():
        r = _getter(fetch, timeout)(url)
        if (bad := _http_problem(r)):
            return False, bad, []
        root = ET.fromstring(r.body)
        schema = sorted({c.tag.split("}")[-1] for c in root})
        if not root.tag.endswith("feed"):
            return False, f"root element is {root.tag.split('}')[-1]}, not feed", schema
        entries = root.findall(ATOM + "entry")
        if not entries:
            return False, "feed has no entry", schema
        first = entries[0]
        if "/abs/" not in (first.findtext(ATOM + "id") or ""):
            title = (first.findtext(ATOM + "title") or "").strip()
            return False, f"entry is an arXiv error, not a paper: {title}", schema
        schema += [f"entry.{c.tag.split('}')[-1]}" for c in first]
        return True, f"{len(entries)} entry with an abs id", schema
    return _run("arxiv", body)


def probe_nva(fetch=None, timeout=60, env=None) -> dict:
    url = NVA + "?" + urllib.parse.urlencode({"query": "offshore", "results": 1})

    def body():
        r = _getter(fetch, timeout)(url)
        if (bad := _http_problem(r)):
            return False, bad, []
        js = _json(r)
        key = "hits" if isinstance(js, dict) and "hits" in js else "results"
        hits = js.get(key) if isinstance(js, dict) else None
        if not isinstance(hits, list):
            return False, "no hits list", _keys(js)
        return bool(hits), f"{len(hits)} hit", _schema_json(js, (key,))
    return _run("nva", body)


# --- ampl (licence activation + a 2-variable LP with HiGHS; skipped without the secret) -----------------------
AMPL_LP = r"""
import json
from amplpy import AMPL
a = AMPL()
a.set_option("solver", "highs")
a.eval("var x >= 0; var y >= 0; maximize z: 3*x + 2*y; subject to c1: x + y <= 4; subject to c2: x <= 2;")
a.solve()
print(json.dumps({"result": a.get_value("solve_result"), "obj": a.get_objective("z").value(),
                  "x": a.get_variable("x").value(), "y": a.get_variable("y").value()}))
"""
AMPL_EXPECT_OBJ = 10.0                            # x = 2, y = 2


def _subprocess(cmd, timeout):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout, r.stderr


def _last(text: str) -> str:
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    return lines[-1] if lines else ""


def probe_ampl(fetch=None, timeout=60, env=None, _proc=None) -> dict:
    env = os.environ if env is None else env
    uuid = (env.get("AMPL_LICENSE_UUID") or "").strip()
    if not uuid:
        return _run("ampl", None, skip="AMPL_LICENSE_UUID not set")
    run = _proc or _subprocess

    def body():
        rc, out, err = run([sys.executable, "-I", "-m", "amplpy.modules", "activate", uuid], timeout)
        if rc != 0:
            return False, f"licence activation failed (exit {rc}): {_last(err or out)}", []
        rc, out, err = run([sys.executable, "-I", "-c", AMPL_LP], timeout)
        if rc != 0:
            return False, f"LP solve failed (exit {rc}): {_last(err)}", []
        res = json.loads(_last(out))
        ok = res.get("result") == "solved" and abs(float(res["obj"]) - AMPL_EXPECT_OBJ) < 1e-6
        return ok, (f"HiGHS LP: {res.get('result')}, objective {float(res['obj']):.6g} "
                    f"(expected {AMPL_EXPECT_OBJ:g})"), sorted(res)
    return _run("ampl", body, secrets=(uuid,))


# --- runner (the Actions image: python, libegl1 for skia and OCP) ----------------------------------------------
def probe_runner(fetch=None, timeout=60, env=None, _proc=None) -> dict:
    run = _proc or _subprocess

    def body():
        notes = {"python": f"{sys.version_info.major}.{sys.version_info.minor}"}
        py_ok = sys.version_info >= (3, 10)
        try:
            rc, out, _ = run(["dpkg", "-s", "libegl1"], min(timeout, 30))
            egl = rc == 0 and "install ok installed" in out
            notes["libegl1"] = "installed" if egl else "missing"
        except OSError:
            egl = False
            notes["libegl1"] = "dpkg unavailable"
        for mod in ("skia", "OCP"):
            try:
                rc, _, _ = run([sys.executable, "-I", "-c", f"import {mod}"], min(timeout, 60))
                notes[mod] = "importable" if rc == 0 else "not importable"
            except (OSError, subprocess.SubprocessError) as e:
                notes[mod] = f"import check failed ({type(e).__name__})"
        detail = "; ".join(f"{k} {v}" if k == "python" else (f"libegl1 {v}" if k == "libegl1" else f"{k} {v}")
                           for k, v in notes.items())
        if not py_ok:
            detail += " (python older than 3.10)"
        return py_ok and egl, detail, ["dpkg:libegl1", "import:OCP", "import:skia", "python"]
    return _run("runner", body)


# --- registry, budgeted runs, status files ---------------------------------------------------------------------
PROBES: dict = {
    "overpass": probe_overpass, "sodir": probe_sodir, "nora3_wind": probe_nora3_wind,
    "nora3_wave": probe_nora3_wave, "norkyst": probe_norkyst, "kartverket_stedsnavn": probe_kartverket_stedsnavn,
    "geonorge_dtm": probe_geonorge_dtm, "geofabrik": probe_geofabrik, "entur_gtfs": probe_entur_gtfs,
    "entur_vehicles": probe_entur_vehicles, "barentswatch": probe_barentswatch, "openalex": probe_openalex,
    "crossref": probe_crossref, "arxiv": probe_arxiv, "nva": probe_nva, "ampl": probe_ampl, "runner": probe_runner,
}


def run_probe(name, fetch=None, env=None, budget_s: float = BUDGET_S, timeout: int = 60) -> dict:
    """One probe in a daemon thread with a wall budget. Over budget = failed result (the thread is abandoned)."""
    if name not in PROBES:
        raise KeyError(f"unknown probe {name!r}")
    box: dict = {}

    def target():
        try:
            box["r"] = PROBES[name](fetch=fetch, timeout=timeout, env=env)
        except BaseException as e:  # noqa: BLE001 - keep the thread's failure in the result
            box["r"] = _finish(name, "fail", started, f"{type(e).__name__}: {e}")
    started = time.monotonic()
    t = threading.Thread(target=target, name=f"probe-{name}", daemon=True)
    t.start()
    t.join(budget_s)
    if t.is_alive():
        return _finish(name, "fail", started, f"exceeded the {budget_s:g} s wall budget")
    return box["r"]


def schema_hash(schema) -> str:
    return hashlib.sha256(json.dumps(sorted(schema)).encode()).hexdigest()[:16]


def load_previous(path) -> Optional[list]:
    """Result list of an earlier live_status.json, or None when there is none or it does not parse."""
    try:
        js = json.loads(Path(path).read_text())
    except (OSError, ValueError, TypeError):
        return None
    res = js.get("results") if isinstance(js, dict) else js
    if not isinstance(res, list):
        return None
    return [r for r in res if isinstance(r, dict) and r.get("name")]


def _not_run(name) -> dict:
    return {"name": name, "ok": None, "status": "not run", "latency_s": None, "detail": "", "schema": [],
            "schema_hash": None, "last_ok": None, "checked_utc": None}


def _merge(new: dict, prev: Optional[dict]) -> dict:
    """Fresh result plus carried-over facts: the schema and last ok date of the last good run."""
    prev = prev or {}
    if new["status"] == "ok":
        schema, h, last_ok = new["schema"], schema_hash(new["schema"]), (new["checked_utc"] or "")[:10]
    else:
        schema, h, last_ok = prev.get("schema") or [], prev.get("schema_hash"), prev.get("last_ok")
    return {**new, "schema": schema, "schema_hash": h, "last_ok": last_ok}


def run_all(names=None, *, fetch=None, env=None, budget_s: float = BUDGET_S, timeout: int = 60,
            out_md=MD_PATH, out_json=JSON_PATH) -> list:
    """Run the named probes (default all). Probes not run this time keep their last result from live_status.json.
    Writes live_status.json ({generated_utc, results}) and the markdown table. Returns the merged list in PROBES order."""
    wanted = list(PROBES) if not names else list(dict.fromkeys(names))
    unknown = [n for n in wanted if n not in PROBES]
    if unknown:
        raise KeyError(f"unknown probe(s): {', '.join(unknown)}; known: {', '.join(PROBES)}")
    prev = {r["name"]: r for r in (load_previous(out_json) if out_json else None) or []}
    fresh = {n: run_probe(n, fetch=fetch, env=env, budget_s=budget_s, timeout=timeout) for n in wanted}
    merged = []
    for n in PROBES:
        if n in fresh:
            merged.append(_merge(fresh[n], prev.get(n)))
        elif n in prev:
            merged.append(prev[n])
        else:
            merged.append(_not_run(n))
    generated = _now()
    if out_json:
        Path(out_json).parent.mkdir(parents=True, exist_ok=True)
        Path(out_json).write_text(json.dumps({"generated_utc": generated, "results": merged}, indent=1) + "\n")
    if out_md:
        Path(out_md).parent.mkdir(parents=True, exist_ok=True)
        Path(out_md).write_text(render_markdown(merged, generated))
    return merged


def _entries(x) -> list:
    if isinstance(x, dict):
        x = x.get("results") or []
    return [e for e in x or [] if isinstance(e, dict) and e.get("name")]


def diff_schema(old, new) -> list:
    """Names of probes whose schema hash differs between two runs (lists of results or live_status payloads).
    A probe with no hash on either side (never ran, or never ok) is not compared."""
    o = {e["name"]: e.get("schema_hash") for e in _entries(old)}
    n = {e["name"]: e.get("schema_hash") for e in _entries(new)}
    return sorted(k for k, h in n.items() if h and o.get(k) and o[k] != h)


def schema_delta(old, new) -> dict:
    """For each probe in diff_schema: the keys added and removed."""
    o = {e["name"]: e for e in _entries(old)}
    n = {e["name"]: e for e in _entries(new)}
    return {k: {"added": sorted(set(n[k].get("schema") or []) - set(o[k].get("schema") or [])),
                "removed": sorted(set(o[k].get("schema") or []) - set(n[k].get("schema") or []))}
            for k in diff_schema(old, new)}


_OK_WORD = {"ok": "yes", "fail": "no", "skipped": "skipped", "not run": "not run"}


def _cell(text) -> str:
    return " ".join(str(text or "-").replace("|", "\\|").split()) or "-"


def render_markdown(entries=None, generated_utc: Optional[str] = None) -> str:
    """docs/LIVE_STATUS.md. With no entries (or no generated time) it is the placeholder: every probe 'not run'."""
    by = {e["name"]: e for e in entries or []}
    head = ["# Live status: external dependencies", ""]
    if generated_utc:
        head.append(f"Generated {generated_utc} by `python -m offsim.live.cli` (weekly workflow `live-check`).")
    else:
        head.append("Placeholder: no live run is recorded yet. The weekly `live-check` workflow writes this table "
                    "on branch `live/status`, with the machine-readable copy in `live_status.json`.")
    head += ["", "A probe that needs a secret reports skipped. A schema hash that changes between runs means a response "
             "key or variable was renamed or removed; the live-check issue then lists the keys added and removed.", ""]
    rows = ["| Probe | OK | Latency (s) | Last ok (UTC) | Schema hash | Detail |", "|---|---|---|---|---|---|"]
    for n in PROBES:
        e = by.get(n) or _not_run(n)
        lat = "-" if e.get("latency_s") is None else f"{e['latency_s']:.2f}"
        rows.append("| " + " | ".join([n, _OK_WORD.get(e.get("status"), str(e.get("status"))), lat,
                                       _cell(e.get("last_ok")), _cell(e.get("schema_hash")), _cell(e.get("detail"))])
                    + " |")
    return "\n".join(head + rows) + "\n"


def issue_body(entries, changed=(), delta=None, run_url: Optional[str] = None) -> str:
    """Issue text for the live-check issue; empty string when nothing failed and no schema changed."""
    failed = [e for e in entries if e.get("status") == "fail"]
    delta = delta or {}
    if not failed and not changed:
        return ""
    lines = ["Automated live-check report. Full table: docs/LIVE_STATUS.md on branch `live/status`.", ""]
    if run_url:
        lines += [f"Run: {run_url}", ""]
    if failed:
        lines += ["## Failing probes", "", "| Probe | Detail | Last ok (UTC) |", "|---|---|---|"]
        lines += [f"| {e['name']} | {_cell(e.get('detail'))} | {_cell(e.get('last_ok'))} |" for e in failed]
        lines.append("")
    if changed:
        lines += ["## Response schema changed", ""]
        for n in changed:
            d = delta.get(n, {})
            lines.append(f"- {n}: added {', '.join(d.get('added', [])) or 'none'}; "
                         f"removed {', '.join(d.get('removed', [])) or 'none'}")
        lines.append("")
    lines.append("Skipped probes (missing secrets) are not counted here.")
    return "\n".join(lines) + "\n"
