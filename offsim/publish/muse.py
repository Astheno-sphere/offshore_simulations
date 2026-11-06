"""Upload a finished film to muse.ai (hosting only: muse.ai stores, transcodes and serves video; it does not
run our code). API: POST https://muse.ai/api/files/upload, header `Key: <MUSE_AI_KEY>`, multipart field
`file`, optional `collection`, `visibility` (public | unlisted | private). Key from env MUSE_AI_KEY
(GitHub Actions secret). Uses only the standard library.
"""
import json
import mimetypes
import os
import uuid
import urllib.request
from pathlib import Path

ENDPOINT = "https://muse.ai/api/files/upload"


def upload(path, title=None, visibility="unlisted", collection=None, key=None, timeout=900):
    key = key or os.environ.get("MUSE_AI_KEY")
    if not key:
        raise RuntimeError("MUSE_AI_KEY not set (add it as a GitHub Actions secret)")
    path = Path(path)
    boundary = uuid.uuid4().hex
    parts = []

    def field(name, value):
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())

    field("visibility", visibility)
    if collection:
        field("collection", collection)
    if title:
        field("title", title)
    ctype = mimetypes.guess_type(path.name)[0] or "video/mp4"
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
                 f"Content-Type: {ctype}\r\n\r\n".encode() + path.read_bytes() + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    req = urllib.request.Request(ENDPOINT, data=b"".join(parts), method="POST",
                                 headers={"Key": key, "Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")
