"""fetch_world --probe-depth: prints verbatim what the endpoints offer, decides nothing, and every section survives another's failure.
All endpoints are fakes injected into the function; nothing here touches the network."""
import io
import zipfile

import pytest

from offsim.worlds import fetch_world as fw


def _zip(member=b"II*\x00rest"):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("dtm.tif", member)
    return b.getvalue()


def _json(path, *a, **k):
    if path.startswith("/capabilities/"):
        return {"supportsPolygonSelection": True, "formats": ["DEM "]}
    if path.startswith("/codelists/format/"):
        return [{"name": "DEM "}]
    raise AssertionError(path)


CAPS = ('<wcs:Capabilities xmlns:wcs="x"><wcs:CoverageId>emodnet__mean_2022</wcs:CoverageId>'
        '<wcs:CoverageId>emodnet__mean_2024</wcs:CoverageId></wcs:Capabilities>')


def _fetch(url, data=None, timeout=0):
    if "GetCapabilities" in url:
        return CAPS.encode()
    if "DescribeCoverage" in url:
        return b'<Envelope axisLabels="Lat Long"/>'
    return _zip()


def _order(uuid, line, wait_s=0, poll_s=0):
    assert line["formats"] == [{"name": "DEM "}]                          # the FIRST codelist name, trailing space and all
    return {"referenceNumber": "R1", "files": [{"fileName": "a.zip", "status": "ReadyForDownload", "downloadUrl": "https://x/dl/a.zip?token=SECRET"}]}


def test_the_transcript_shows_the_trailing_space_the_file_list_the_magic_bytes_and_the_coverage_ids():
    lines = fw.probe_depth("oslofjord", out=lambda *_: None, get_json=_json, fetch=_fetch, order=_order)
    t = "\n".join(lines)
    assert "'DEM '" in t                                                   # repr keeps the trailing space visible
    assert "https://x/dl/a.zip" in t and "SECRET" not in t                 # the query string (a token) is never printed
    assert "b'II*\\x00'" in t and "is_tiff=True" in t and "dtm.tif" in t   # outer zip, then the member's own magic
    assert "emodnet__mean_2022" in t and "picker would choose: emodnet__mean_2024" in t and "axisLabels" in t
    assert "FAILED" not in t


def test_a_failing_section_is_reported_and_the_others_still_run():
    def bad(path, *a, **k):
        raise RuntimeError("geonorge down")
    lines = fw.probe_depth("oslofjord", out=lambda *_: None, get_json=bad, fetch=_fetch, order=_order)
    t = "\n".join(lines)
    assert "SECTION (a) FAILED: RuntimeError geonorge down" in t and "SECTION (b) FAILED" in t     # (b) has no format names to order
    assert "emodnet__mean_2024" in t                                        # (c) still ran


def test_the_probe_does_not_touch_the_acceptance_rule():
    """kartverket_dtm still refuses a format list with no GeoTIFF name: acceptance of 'DEM ' waits for the probe transcript."""
    import inspect
    src = inspect.getsource(fw.kartverket_dtm)
    assert 're.search(r"tif", n, re.I)' in src and "endpoint unverified: no GeoTIFF format in" in src
