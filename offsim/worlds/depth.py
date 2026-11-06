"""Map depth: terrain + bathymetry → mesh, baked hillshade, isobaths. Defined interfaces (not built).
Spec: docs/VISUAL_SPEC.md §2. Fetch on Actions; process with rasterio/GDAL + pydelatin; render offline.

Sources by priority (mosaic order): NGU 1 m (inner Oslofjord) > Kartverket seabed 5/25 m > Kartverket seabed 50 m /
DTM10 land > EMODnet 1/16' (~115 m, North Sea) > GEBCO (gaps only).
Datums: land NN2000; Kartverket seabed = sjøkartnull (chart datum); EMODnet = LAT (MSL variant exists).
Convert to one vertical datum BEFORE merging; clip land with the OSM coastline polygon (MHW), not the 0 m contour.
"""

TIERS = {
    # name: (grid m, land exaggeration, sea exaggeration, mesh max_error m)
    "fjord": (50, 3.0, 5.0, 2.0),          # Oslofjord-wide
    "port": (10, 1.5, 2.0, 1.0),           # ~5x5 km close-ups (5 m or NGU 1 m at sea)
    "shelf": (115, 4.0, 30.0, 5.0),        # North Sea off Stavanger; 25–40x or trenches read flat
}
TEXTURE_MAX_PX = 4096                      # SwiftShader MAX_TEXTURE_SIZE is typically 8192; stay at half
ISOBATHS_M = {"fjord": [10, 20, 50, 100, 200, 300], "port": [5, 10, 20, 50], "shelf": [50, 100, 200, 300, 500, 700]}


def merge_dem(sources: list, bbox: tuple, crs: str, out_cog: str, datum: str = "NN2000") -> dict:
    """Reproject, datum-shift, mosaic by priority with 3–5 cell feathering, burn coastline at 0 m;
    COG bands: elevation, bathy_mask, source_id. Returns a manifest entry with every source licence."""
    raise NotImplementedError


def terrain_mesh(cog: str, tier: str) -> dict:
    """pydelatin TIN (max_error per TIERS) → {positions (lon, lat, z·exaggeration), indices, normals}; 150–400k triangles."""
    raise NotImplementedError


def hillshade_texture(cog: str, tier: str, azimuth: float = 315, altitude: float = 35) -> str:
    """gdaldem -multidirectional hillshade × depth/elevation tint (shallow teal → navy; land muted grey-green),
    baked PNG ≤ TEXTURE_MAX_PX, for BitmapLayer or mesh texture (cheaper than runtime lighting on SwiftShader)."""
    raise NotImplementedError


def isobaths(cog: str, tier: str) -> str:
    """gdal_contour on a Gaussian-smoothed copy, simplified to 0.5 cell, lines < 1 km dropped, every 5th bold,
    depth labels → GeoJSON for PathLayer (CAD-style)."""
    raise NotImplementedError
