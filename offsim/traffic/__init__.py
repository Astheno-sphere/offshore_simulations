"""AIS traffic (L0 data): real vessel movements used to calibrate and validate simulations.

    offsim.traffic.ais          load HAIS GeoParquet/CSV, tracks, stops, port calls, calibration, compare_to_sim
    offsim.traffic.barentswatch BarentsWatch AIS API client spec (Actions/laptop only)

Needs requirements-gis.txt (movingpandas); the module imports are lazy so `import offsim.traffic` is cheap.
"""
