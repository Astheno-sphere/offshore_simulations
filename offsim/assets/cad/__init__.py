"""CAD-grade assets: every vessel, aircraft, vehicle, person, tree and building is an exact solid at real scale,
drawn as a hidden-line projection (the Rhino Make2D / CAD drafting look), not a hand-placed sprite.

Contract (offsim/assets/cad/base.py): an asset module exposes `build(**params) -> AssetModel`; the drawing module
projects it (`offsim.assets.cad.drawing.project`) into classed polylines (silhouette, visible, hidden, section) that
`offsim.cinema.draw` renders with the line-weight hierarchy. Registry: `offsim/assets/cad/registry.yaml`.
"""
