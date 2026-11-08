# Draft notes: Tactical Helicopter Transportation Planning for Offshore Personnel on the Norwegian Continental Shelf

DRAFT ONLY. Everything here is a candidate; paper-extract confirms each value against its page (`src: p.X Table Y`) or marks it `assumption: true`.

## Source
- file: heli.pdf (sha256 a0d628e705983d8b..., 41 pages)
- DOI: 10.3390/logistics9020073; year: 2025
- authors (best effort): IrinaGribkovskaia

## Classification (rule tags, routing only)
- classes: HRP; mode: heli; region: NCS, Norway
- uncertainty: none; method: None; confidence: 0.5
- code: None; data: None

## Evidence found (count by kind)
- capacity: 1
- cost: 1
- fleet_size: 3
- instance_size: 1
- reported_kpi: 1
- service: 1
- time_window: 1

## Missing (no candidate found; check the paper by hand or fill by assumption)
- vessel speed
- demand per stop
- distances
- always by hand: stop coordinates (lon/lat), base quay, objective definition, constraints, instance files

## Files
- extract.json: full text and tables per page
- evidence.csv: all candidates
- scenario.draft.yaml: template-shaped, all values null with candidates (gate 0 must refuse it)
- timetable.draft.yaml: ferry/bus paper; schema in offsim/transit/from_paper.py

## Licence
Only open-access (CC BY etc.) figures and instance data may be redistributed. The PDF is not copied here. Record the paper's licence in `paper.licence` before using any figure or table in a film.
