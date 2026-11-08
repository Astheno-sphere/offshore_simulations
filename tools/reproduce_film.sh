#!/usr/bin/env bash
# Reproduce the section + map film from a clean clone. Any agent or human: run from the repo root.
#   bash tools/reproduce_film.sh            -> out/film/psv_section.mp4 (1080x1350, 5 s)
set -euo pipefail
pip install -q -r requirements.txt -r requirements-physics.txt -c constraints.txt
command -v ffmpeg >/dev/null || { echo "need ffmpeg (apt install ffmpeg)"; exit 1; }
[ -f /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf ] || { echo "need DejaVu fonts (apt install fonts-dejavu-core)"; exit 1; }
# data is never committed: pull the Oslofjord world from the repo's GitHub release (land.geojson)
[ -f data/worlds/oslofjord/land.geojson ] || python -m offsim.worlds.fetch_world --pull oslofjord
python -m offsim run offsim/papers/demo-oslofjord-supply/scenario.yaml          # gated route for the map
python -m pytest -q tests/test_physics.py                                        # physics + craft rules must pass
PYTHONPATH=. python tools/section_film.py --out out/film/psv_section.mp4
