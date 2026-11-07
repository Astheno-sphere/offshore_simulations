"""BarentsWatch AIS API client (spec + thin stdlib implementation). Runs on Actions or a laptop only: the Claude
workspace cannot reach BarentsWatch.

Auth: OAuth2 client credentials. Env BW_CLIENT_ID, BW_CLIENT_SECRET (register a client at
https://www.barentswatch.no/minside/ ; GitHub secrets of the same names for the workflow).
    POST https://id.barentswatch.no/connect/token
         grant_type=client_credentials & client_id & client_secret & scope=ais
    -> {"access_token", "expires_in", "token_type": "Bearer"}

Endpoints (all UNVERIFIED LIVE: paths and field names come from the public BarentsWatch AIS API documentation as
recalled; nothing here has run against the real service. Check https://live.ais.barentswatch.no/index.html and
https://historic.ais.barentswatch.no/index.html and fix BASE_* / PATHS before trusting any output):
    latest   GET  https://live.ais.barentswatch.no/v1/latest/combined?...      current position per vessel
    historic GET  https://historic.ais.barentswatch.no/v1/historic/mmsiAisPositions/{mmsi}/{from}/{to}   ISO-8601 UTC
    area     POST https://live.ais.barentswatch.no/v1/combined  (streaming NDJSON; geometry filter)  -- not implemented

Records are normalised to the offsim.traffic.ais schema (mmsi, timestamp, lon, lat, sog, cog, ship_type) by
`normalise_records`, so `ais.load_ais(pd.DataFrame(records))` works unchanged.

Injectable fetch: every network call goes through `fetch(url, headers, data) -> bytes`; tests pass a fake. The
default is urllib. Licence: NLOD 2.0 (credit "Kystverket / BarentsWatch"); confirm on the terms page.
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from typing import Callable

TOKEN_URL = "https://id.barentswatch.no/connect/token"
BASE_LIVE = "https://live.ais.barentswatch.no"            # unverified live
BASE_HISTORIC = "https://historic.ais.barentswatch.no"    # unverified live
PATHS = {                                                 # unverified live
    "latest": "/v1/latest/combined",
    "historic": "/v1/historic/mmsiAisPositions/{mmsi}/{start}/{end}",
}
UA = {"User-Agent": "offshore-simulations (github.com/Astheno-sphere/offshore_simulations)"}

Fetch = Callable[[str, dict, "bytes | None"], bytes]


def default_fetch(url: str, headers: dict | None = None, data: bytes | None = None, timeout: int = 120) -> bytes:
    req = urllib.request.Request(url, data=data, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def credentials_available(env=None) -> bool:
    """True when BW_CLIENT_ID and BW_CLIENT_SECRET are both set (the workflow skips BarentsWatch otherwise)."""
    env = os.environ if env is None else env
    return bool(env.get("BW_CLIENT_ID") and env.get("BW_CLIENT_SECRET"))


class BarentsWatch:
    def __init__(self, client_id: str | None = None, client_secret: str | None = None, fetch: Fetch = default_fetch,
                 token_url: str = TOKEN_URL, clock: Callable[[], float] = time.time):
        self.client_id = client_id or os.environ.get("BW_CLIENT_ID", "")
        self.client_secret = client_secret or os.environ.get("BW_CLIENT_SECRET", "")
        if not (self.client_id and self.client_secret):
            raise RuntimeError("BW_CLIENT_ID / BW_CLIENT_SECRET not set")
        self._fetch, self.token_url, self._clock = fetch, token_url, clock
        self._token, self._expires = None, 0.0

    def token(self) -> str:
        """Client-credentials token, cached until 60 s before expiry."""
        if self._token and self._clock() < self._expires - 60:
            return self._token
        body = urllib.parse.urlencode({"grant_type": "client_credentials", "client_id": self.client_id,
                                       "client_secret": self.client_secret, "scope": "ais"}).encode()
        js = json.loads(self._fetch(self.token_url, {"Content-Type": "application/x-www-form-urlencoded"}, body))
        self._token = js["access_token"]
        self._expires = self._clock() + float(js.get("expires_in", 3600))
        return self._token

    def _get_json(self, url: str):
        return json.loads(self._fetch(url, {"Authorization": f"Bearer {self.token()}", "Accept": "application/json"}, None))

    def latest(self) -> list:
        """Latest position of every vessel (unverified live endpoint). Normalised records."""
        return normalise_records(self._get_json(BASE_LIVE + PATHS["latest"]))

    def historic(self, mmsi: int, start_utc: str, end_utc: str) -> list:
        """Positions of one vessel between two ISO-8601 UTC instants (unverified live endpoint). Normalised records."""
        path = PATHS["historic"].format(mmsi=int(mmsi), start=urllib.parse.quote(start_utc), end=urllib.parse.quote(end_utc))
        return normalise_records(self._get_json(BASE_HISTORIC + path))


def normalise_records(js) -> list:
    """BarentsWatch JSON (list of dicts, or {"features": [...]}) -> list of dicts with the ais.load_ais schema.
    Accepts camelCase names (mmsi, msgtime, latitude, longitude, speedOverGround, courseOverGround, shipType)."""
    if isinstance(js, dict):
        js = js.get("features") or js.get("data") or []
    out = []
    for r in js:
        r = r.get("properties", r) | ({"geometry": r["geometry"]} if isinstance(r, dict) and "geometry" in r else {})
        lon, lat = r.get("longitude"), r.get("latitude")
        g = r.get("geometry")
        if (lon is None or lat is None) and isinstance(g, dict) and g.get("coordinates"):
            lon, lat = g["coordinates"][:2]
        if r.get("mmsi") is None or lon is None or lat is None:
            continue
        out.append({"mmsi": int(r["mmsi"]), "timestamp": r.get("msgtime") or r.get("timestamp"), "lon": float(lon),
                    "lat": float(lat), "sog": r.get("speedOverGround", r.get("sog")),
                    "cog": r.get("courseOverGround", r.get("cog")), "ship_type": r.get("shipType", r.get("ship_type"))})
    return out


def main(argv=None) -> int:
    """`python -m offsim.traffic.barentswatch --latest OUT.json`: skip quietly (exit 0) without credentials."""
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--latest", metavar="OUT", help="write the latest positions (normalised) to OUT (unverified live)")
    a = ap.parse_args(argv)
    if not credentials_available():
        print("BW_CLIENT_ID / BW_CLIENT_SECRET not set: skipping BarentsWatch")
        return 0
    if a.latest:
        recs = BarentsWatch().latest()
        with open(a.latest, "w") as fh:
            json.dump({"source": "BarentsWatch AIS (unverified live endpoint)", "licence": "NLOD 2.0",
                       "credit": "Kystverket / BarentsWatch", "fetched_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                       "records": recs}, fh)
        print(f"{len(recs)} positions -> {a.latest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
