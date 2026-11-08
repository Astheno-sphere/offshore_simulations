"""Any place in Norway -> a world: resolve a name/bbox to a Place and write a world spec v2.

    from offsim.worlds.place import resolve, write_world_spec, load_world_spec
    p = resolve("Ålesund")                      # built-in gazetteer (case/diacritics-insensitive)
    p = resolve("10.2,58.95,11.05,59.95")       # explicit "lon0,lat0,lon1,lat1"
    p = resolve("Namsos", fetch=my_fetch)       # not in the gazetteer -> Kartverket stedsnavn API
    write_world_spec(p, ["sea", "road", "bus"], "offsim/worlds/alesund.yaml")
    spec = load_world_spec("offsim/worlds/oslofjord.yaml")   # v1 or v2 -> v2-normalised dict

Resolution order of `resolve`: (1) 4 comma-separated numbers = bbox; (2) GAZETTEER key; (3) stedsnavn API.
`fetch` is an injectable ``url -> bytes`` (stdlib urllib by default), so everything is tested offline with fixtures.

Kartverket place names (stedsnavn), CC BY 4.0, "unverified live" (this workspace cannot reach geonorge.no):
    https://ws.geonorge.no/stedsnavn/v1/navn?sok=<name>&fuzzy=false&utkoordsys=4258&treffPerSide=5
The response is parsed defensively: hits under "navn" (or a bare list); the point is `representasjonspunkt`
{nord, øst} (alias lat/lon, nord/ost, y/x) on the hit; the name is `stedsnavn[0].skrivemåte` (or `skrivemaate`,
`navn`, `name`). Anything unparseable raises PlaceError naming what was missing.

World spec v2 (YAML; documented in docs/ARCHITECTURE.md "Worlds v2")
    version: 2
    name: alesund                       # slug; file name offsim/worlds/<name>.yaml
    place: {name, lon, lat, source}     # provenance of the centre point
    bbox: [west, south, east, north]    # WGS84
    modes: [sea, road, bus, walk, air]  # any non-empty subset
    layers: [land, coast, sealanes, roads, ...]   # DERIVED from modes by `layers_for` (written for readability)
    osm_land: true                      # v1 keys stay valid: osm_land, sodir_keywords, depth, manual, ais_*, osm_pbf_url
    sodir_keywords: []
Layers by mode: always `land`; sea -> coast, sealanes (+ depth only when requested); road/walk -> roads (+ quays, ferry
for sea); bus -> roads + gtfs; air -> helipads + aerodromes (OSM aeroway helipad|heliport, aerodrome).
A v1 YAML (no `version`) loads as modes [sea] with place derived from the bbox centre.
"""
from __future__ import annotations

import json
import re
import unicodedata
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence

import yaml

MODES = ("sea", "road", "bus", "walk", "air")
KM_PER_DEG = 111.195          # mean Earth radius 6371 km
STEDSNAVN = "https://ws.geonorge.no/stedsnavn/v1/navn"
STEDSNAVN_LICENCE = "CC BY 4.0 (Kartverket)"
DEFAULT_RADIUS_KM = 15.0
_APPROX = "approx centre (Claude, unverified); refine via stedsnavn"
UA = {"User-Agent": "offshore-simulations (github.com/Astheno-sphere/offshore_simulations)"}


class PlaceError(ValueError):
    """A place name/bbox could not be resolved or parsed."""


@dataclass(frozen=True)
class Place:
    """A resolved place: centre point, WGS84 bbox (west, south, east, north) and where the centre came from."""
    name: str
    lon: float
    lat: float
    bbox: tuple
    source: str

    def as_dict(self) -> dict:
        """The `place:` block of a world spec v2 (name, lon, lat, source)."""
        return {"name": self.name, "lon": round(self.lon, 5), "lat": round(self.lat, 5), "source": self.source}


# name -> (lon, lat, default radius_km). Centres are rough; every entry is flagged unverified.
_G = {
    "Oslo": (10.74, 59.91, 15), "Oslofjord": (10.60, 59.55, 45), "Drammen": (10.20, 59.74, 12),
    "Bergen": (5.32, 60.39, 20), "Mongstad": (5.03, 60.81, 10), "Ågotnes": (5.01, 60.40, 10),
    "Stavanger": (5.73, 58.97, 20), "Sola": (5.63, 58.88, 10), "Dusavik": (5.69, 58.99, 6),
    "Haugesund": (5.27, 59.41, 15), "Kristiansand": (8.00, 58.15, 15), "Ålesund": (6.15, 62.47, 15),
    "Molde": (7.16, 62.74, 15), "Kristiansund": (7.73, 63.11, 15), "Trondheim": (10.40, 63.43, 20),
    "Bodø": (14.40, 67.28, 15), "Tromsø": (18.96, 69.65, 15), "Hammerfest": (23.68, 70.66, 12),
    "Florø": (5.03, 61.60, 12), "Halten": (9.40, 64.20, 80),
}
GAZETTEER = {k: {"lon": v[0], "lat": v[1], "radius_km": float(v[2]), "source": _APPROX} for k, v in _G.items()}
GAZETTEER["Halten/Kristiansund offshore"] = {"lon": 8.30, "lat": 63.70, "radius_km": 90.0, "source": _APPROX}


def _fold(s: str) -> str:
    """Case- and diacritics-insensitive key: 'Ålesund' -> 'alesund', 'Tromsø' -> 'tromso'."""
    s = s.strip().lower().replace("ø", "o").replace("æ", "ae").replace("å", "a")
    s = unicodedata.normalize("NFKD", s)
    return re.sub(r"\s+", " ", "".join(c for c in s if not unicodedata.combining(c)))


_INDEX = {_fold(k): k for k in GAZETTEER}


def slugify(name: str) -> str:
    """File-system/release-safe slug: 'Ålesund' -> 'alesund', 'Halten/Kristiansund offshore' -> 'halten-kristiansund-offshore'."""
    return re.sub(r"[^a-z0-9]+", "-", _fold(name)).strip("-") or "place"


def bbox_for(lon: float, lat: float, radius_km: float) -> tuple:
    """(west, south, east, north) box of half-width `radius_km` around lon/lat; longitude span widened by 1/cos(lat)."""
    import math

    if radius_km <= 0:
        raise PlaceError("radius_km must be > 0")
    dlat = radius_km / KM_PER_DEG
    dlon = dlat / max(math.cos(math.radians(lat)), 1e-6)
    return (round(lon - dlon, 4), round(lat - dlat, 4), round(lon + dlon, 4), round(lat + dlat, 4))


def parse_bbox(text: str) -> Optional[tuple]:
    """'lon0,lat0,lon1,lat1' -> (w, s, e, n) or None when `text` is not four numbers. Raises PlaceError if invalid."""
    parts = [p for p in re.split(r"[,\s;]+", text.strip()) if p]
    if len(parts) != 4:
        return None
    try:
        w, s, e, n = (float(p) for p in parts)
    except ValueError:
        return None
    if not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
        raise PlaceError(f"bbox must be west<east, south<north within WGS84; got {text!r}")
    return (w, s, e, n)


def _default_fetch(url: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return r.read()


def _num(d: dict, *keys):
    for k in keys:
        if k in d and d[k] is not None:
            try:
                return float(d[k])
            except (TypeError, ValueError):
                pass
    return None


def parse_stedsnavn(payload, query: str = "") -> list:
    """Parse a stedsnavn response (bytes/str/dict/list) -> [{name, lon, lat, type, municipality}], hit order kept.
    Defensive: hits under 'navn' / 'treff' / bare list; coordinates from `representasjonspunkt` (nord/øst, lat/lon, y/x)."""
    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("utf-8", "replace")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as ex:
            raise PlaceError(f"stedsnavn: response is not JSON ({ex})") from ex
    hits = payload if isinstance(payload, list) else (payload.get("navn") or payload.get("treff") or [])
    out = []
    for h in hits:
        if not isinstance(h, dict):
            continue
        pt = h.get("representasjonspunkt") or h.get("punkt") or {}
        lat = _num(pt, "nord", "lat", "latitude", "y")
        lon = _num(pt, "øst", "ost", "oest", "lon", "lng", "longitude", "x")
        if lat is None or lon is None:
            continue
        names = h.get("stedsnavn")
        n0 = names[0] if isinstance(names, list) and names and isinstance(names[0], dict) else {}
        name = n0.get("skrivemåte") or n0.get("skrivemaate") or h.get("skrivemåte") or h.get("navn") or h.get("name") or query
        komm = h.get("kommuner") or []
        kn = komm[0].get("kommunenavn") if komm and isinstance(komm[0], dict) else None
        out.append({"name": str(name), "lon": lon, "lat": lat, "type": h.get("navneobjekttype"), "municipality": kn})
    return out


def stedsnavn_url(name: str) -> str:
    """The unverified-live query URL for `name` (exact match, WGS84/ETRS89 lon/lat, 5 hits)."""
    q = {"sok": name, "fuzzy": "false", "utkoordsys": "4258", "treffPerSide": "5"}
    return f"{STEDSNAVN}?{urllib.parse.urlencode(q)}"


def resolve(name_or_bbox: str, fetch: Optional[Callable[[str], bytes]] = None, radius_km: Optional[float] = None) -> Place:
    """bbox string | gazetteer key | stedsnavn name -> Place. `radius_km` overrides the default radius (gazetteer
    entry radius, or 15 km for API hits). The stedsnavn hit whose name equals the query is preferred, else the first."""
    text = str(name_or_bbox).strip()
    bb = parse_bbox(text)
    if bb:
        return Place(name="bbox", lon=round((bb[0] + bb[2]) / 2, 5), lat=round((bb[1] + bb[3]) / 2, 5), bbox=bb,
                     source="explicit bbox")
    key = _INDEX.get(_fold(text))
    if key:
        g = GAZETTEER[key]
        r = radius_km or g["radius_km"]
        return Place(key, g["lon"], g["lat"], bbox_for(g["lon"], g["lat"], r), g["source"])
    if not text:
        raise PlaceError("empty place name")
    hits = parse_stedsnavn((fetch or _default_fetch)(stedsnavn_url(text)), text)
    if not hits:
        raise PlaceError(f"stedsnavn: no place found for {text!r}")
    h = next((x for x in hits if _fold(x["name"]) == _fold(text)), hits[0])
    return Place(h["name"], h["lon"], h["lat"], bbox_for(h["lon"], h["lat"], radius_km or DEFAULT_RADIUS_KM),
                 f"Kartverket stedsnavn API ({STEDSNAVN_LICENCE}; unverified live)")


def layers_for(modes: Sequence[str], depth: bool = False) -> list:
    """World layers implied by modes (see module docstring). Order is stable; `land` always first."""
    modes = check_modes(modes)
    L = ["land"]
    if "sea" in modes:
        L += ["coast", "sealanes", "quays", "ferry"] + (["depth"] if depth else [])
    if {"road", "walk", "bus"} & set(modes):
        L += ["roads"]
    if "bus" in modes:
        L += ["gtfs"]
    if "air" in modes:
        L += ["helipads", "aerodromes"]
    return list(dict.fromkeys(L))


def check_modes(modes) -> list:
    """Normalise a list or 'sea,road' string to a validated, de-duplicated list; unknown mode -> PlaceError."""
    if isinstance(modes, str):
        modes = [m for m in re.split(r"[,\s]+", modes) if m]
    modes = list(dict.fromkeys(m.strip().lower() for m in modes))
    bad = [m for m in modes if m not in MODES]
    if bad or not modes:
        raise PlaceError(f"modes must be a non-empty subset of {MODES}; got {modes}")
    return modes


def write_world_spec(place: Place, modes: Sequence[str], path, depth: bool = False, name: Optional[str] = None) -> dict:
    """Write a world spec v2 YAML to `path` (parents created) and return the dict written."""
    modes = check_modes(modes)
    spec = {"version": 2, "name": name or slugify(place.name if place.name != "bbox" else "bbox-%.2f-%.2f" % (place.lon, place.lat)),
            "place": place.as_dict(), "bbox": [float(x) for x in place.bbox], "modes": modes,
            "layers": layers_for(modes, depth), "osm_land": True, "sodir_keywords": []}
    if depth:
        spec["depth"] = {"crs": "EPSG:4326", "emodnet": {}}
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# Generated by offsim.worlds.place (world spec v2). Centre/radius are approximate: edit bbox freely.\n"
                    + yaml.safe_dump(spec, sort_keys=False, allow_unicode=True))
    return spec


def load_world_spec(path) -> dict:
    """Load a world YAML (v1 or v2) as a v2-normalised dict. v1 (no `version`) => modes [sea], place from bbox centre,
    layers derived. All other keys (osm_land, sodir_keywords, depth, manual, ais_*, osm_pbf_url) pass through unchanged."""
    path = Path(path)
    cfg = yaml.safe_load(path.read_text()) or {}
    if "bbox" not in cfg:
        raise PlaceError(f"{path}: world spec has no bbox")
    bbox = [float(x) for x in cfg["bbox"]]
    out = dict(cfg)
    out["version"] = 2
    out["name"] = cfg.get("name") or path.stem
    out["bbox"] = bbox
    out["modes"] = check_modes(cfg.get("modes") or ["sea"])
    out.setdefault("place", {"name": out["name"], "lon": round((bbox[0] + bbox[2]) / 2, 5),
                             "lat": round((bbox[1] + bbox[3]) / 2, 5), "source": "bbox centre (v1 spec)"})
    out["layers"] = layers_for(out["modes"], depth=bool(cfg.get("depth")))
    return out
