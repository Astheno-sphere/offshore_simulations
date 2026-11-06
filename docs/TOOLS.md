# Tool catalog

Generated from [`catalog/tools.yaml`](../catalog/tools.yaml) by `tools/catalog_build.py`; edit the YAML, not this file.
63 tools · 9 tested · 4 installed · 23 candidate · 4 manual · 23 watch.

**status** tested = ran here with a recorded result · installed = installs, not exercised · candidate = fits a planned step · manual = order/download by hand · watch = not on the plan yet.  
**runs** here = Claude workspace · actions = GitHub runner (open internet) · laptop · browser.  
**licence** `check` = not verified: read it before copying anything. GPL code runs as a separate process, never imported.

## Needed for the first paper (priority: now)

| Tool | Layer | Status | Runs | Role |
|---|---|---|---|---|
| [OpenStreetMap coastline via Overpass](https://overpass-api.de) | world | tested | actions | Land polygons for every world (offsim/worlds/fetch_world.py + coast.py). |
| [Norwegian Offshore Directorate FactMaps (WGS84 FeatureServer)](https://factmaps.sodir.no/api/rest/services/Factmaps/FactMapsWGS84/FeatureServer) | world | installed | actions | Installations, fields, pipelines, wells on the Norwegian shelf; synced daily. Credit 'Norwegian Offshore Directorate'. |
| [Kystverket Historic AIS (HAIS)](https://hais.kystverket.no/) | traffic | manual | browser | Order PSV/ferry tracks by area, time, ship type; GeoParquet link. Validates speeds, port times, route shapes. |
| [PyVRP](https://github.com/PyVRP/PyVRP) | solver | tested | here | State-of-the-art HGS for CVRP/VRPTW/PDP/multi-depot/multi-trip. Wrapped in offsim/solve/pyvrp_adapter.py. |
| [opt-model (Pyomo + HiGHS)](https://github.com/Astheno-sphere/computational_Logistics/tree/main/skills/opt-model) | solver | tested | here | Exact MIPs from papers; certifies heuristic plans on small instances (test_opt_model.py). |
| [SimPy](https://gitlab.com/team-simpy/simpy) | simulation | tested | here | Discrete-event core of offsim/sim/replay.py: berths, helidecks, time windows. |
| [deck.gl (TripsLayer](https://github.com/visgl/deck.gl) | render | tested | here | 2.5D animated trails; headless Chrome + SwiftShader works here (offsim/render_deck). |
| [FFmpeg](https://ffmpeg.org) | video | tested | here | Frames to H.264 (veryfast preset). |
| [computational_Logistics skills](https://github.com/Astheno-sphere/computational_Logistics/tree/main/skills) | skills | tested | here | Sister repo: visual-narrative house style, vrp-solve cross-check pattern, knowledge-bank catalog of 1,800+ skills. |

## world

_Geography the scenario runs in (land, depth, lanes, installations)_

| Tool | Licence | Status | Runs | Priority | Role |
|---|---|---|---|---|---|
| [Norwegian Offshore Directorate FactMaps (WGS84 FeatureServer)](https://factmaps.sodir.no/api/rest/services/Factmaps/FactMapsWGS84/FeatureServer) | NLOD-2.0 | installed | actions | now | Installations, fields, pipelines, wells on the Norwegian shelf; synced daily. Credit 'Norwegian Offshore Directorate'. |
| [OpenStreetMap coastline via Overpass](https://overpass-api.de) | ODbL-1.0 | tested | actions | now | Land polygons for every world (offsim/worlds/fetch_world.py + coast.py). |
| [Kartverket Sjøkart – Dybdedata](https://data.norge.no/en/datasets/48cc18ef-1317-3ddd-9ca4-a06d8ffa0196) | open (Kartverket terms) | manual | laptop | next | Depth areas and contours; not approved for navigation. Lanes and seabed relief. |
| [Kystverket reference routes for navigation](https://data.norge.no/en/datasets/00014e4a-0be4-3fac-868c-ede03b09ce5c/reference-routes-for-navigation) | NLOD-2.0 | manual | actions | next | Fairway graph so vessels follow lanes, not straight lines. |
| [NGU bathymetry Oslofjorden 1 m grid](https://www.geonorge.no/geonetworktest/srv/api/records/80321d12-119e-4d0c-886b-4b087843b688) | check | manual | laptop | later | High-resolution seabed for inner Oslofjord hero shots. |
| [OpenStreetMap-Ship-Routing](https://github.com/sibmr/OpenStreetMap-Ship-Routing) | check | watch | here | later | Ocean routing graph built from OSM; reference for our own lane graph. |
| [searoute-py](https://github.com/genthalili/searoute-py) | Apache-2.0 | installed | here | later | Shortest global sea route for long-haul legs; its README says visualisation, not navigation. |

## traffic

_Real vessel movements (AIS) to validate simulated routes and speeds_

| Tool | Licence | Status | Runs | Priority | Role |
|---|---|---|---|---|---|
| [Kystverket Historic AIS (HAIS)](https://hais.kystverket.no/) | open | manual | browser | now | Order PSV/ferry tracks by area, time, ship type; GeoParquet link. Validates speeds, port times, route shapes. |
| [MovingPandas](https://github.com/movingpandas/movingpandas) | BSD-3-Clause | installed | here | next | Trajectory cleaning, stop detection, speed profiles; compares AIS with our contract rows. |
| [AISdb (Dalhousie MERIDIAN)](https://pypi.org/project/aisdb/) | check | watch | here | later | SQLite AIS store with cleaning, interpolation, depth/shore joins; heavy if HAIS GeoParquet suffices. |
| [Datasets of AIS trajectories from Danish waters](https://github.com/KristofferOlesen/Datasets-of-AIS-Trajectories-from-Danish-Waters) | BSD-3-Clause | watch | here | later | Ready filtered AIS sets for testing trajectory code without ordering data. |
| [pyais](https://github.com/M0r13n/pyais) | MIT | candidate | here | later | Decode raw NMEA AIS (AIVDM) if we ever take a raw stream instead of GeoParquet. |

## metocean

_Wind, waves, currents; weather windows for operations_

| Tool | Licence | Status | Runs | Priority | Role |
|---|---|---|---|---|---|
| [metocean-api (MET Norway)](https://github.com/MET-OM/metocean-api) | check | candidate | actions | next | Time series from NORA3 wind/wave hindcast (and ERA5) at a point: weather windows for PSV, crane and helideck operations. |
| [Copernicus Marine Toolbox](https://github.com/mercator-ocean/copernicus-marine-toolbox) | check | candidate | actions | later | Subset currents/waves (NetCDF/Zarr) beyond the Nordic domain; needs free login. |
| [MET Norway oceanforecast API](https://api.met.no/doc/oceanforecast/datamodel) | CC-BY-4.0 (MET terms) | candidate | actions | later | Forecast Hs, wave direction, currents for live-looking scenarios. |
| [metocean-stats (MET Norway)](https://github.com/MET-OM/metocean-stats) | check | candidate | actions | later | Operability statistics (Hs exceedance, windows) from those series. |
| [OpenDrift (MET Norway)](https://github.com/OpenDrift/opendrift) | check | watch | here | later | Drift of objects/spills; a different video genre (emergency response logistics). |

## solver

_Exact and heuristic optimisation for routing and scheduling_

| Tool | Licence | Status | Runs | Priority | Role |
|---|---|---|---|---|---|
| [opt-model (Pyomo + HiGHS)](https://github.com/Astheno-sphere/computational_Logistics/tree/main/skills/opt-model) | MIT | tested | here | now | Exact MIPs from papers; certifies heuristic plans on small instances (test_opt_model.py). |
| [PyVRP](https://github.com/PyVRP/PyVRP) | MIT | tested | here | now | State-of-the-art HGS for CVRP/VRPTW/PDP/multi-depot/multi-trip. Wrapped in offsim/solve/pyvrp_adapter.py. |
| [ALNS (N-Wouda)](https://github.com/N-Wouda/ALNS) | MIT | candidate | here | next | Adaptive large neighbourhood search framework: re-implement a paper's metaheuristic faithfully when PyVRP cannot express it. |
| [Google OR-Tools](https://github.com/google/or-tools) | Apache-2.0 | installed | here | next | Independent second routing solver; CP-SAT for scheduling and synchronisation (helicopter papers). |
| [jsprit](https://github.com/graphhopper/jsprit) | Apache-2.0 | watch | laptop | later | Java toolkit for rich VRPs; reference implementation in older papers. |
| [RL4CO](https://github.com/ai4co/rl4co) | MIT | watch | actions | later | Learned routing heuristics; for papers that use RL. |
| [Timefold Solver](https://github.com/TimefoldAI/timefold-solver) | Apache-2.0 | watch | laptop | later | Java/Kotlin planning engine (vehicle routing, crew rostering); if a paper needs rich scheduling. |
| [VROOM](https://github.com/VROOM-Project/vroom) | BSD-2-Clause | watch | here | later | Fast C++ VRP engine with JSON API; good for big instances and quick baselines. |

## weather-routing

_Route optimisation through forecast weather_

| Tool | Licence | Status | Runs | Priority | Role |
|---|---|---|---|---|---|
| [52North WeatherRoutingTool](https://github.com/52North/WeatherRoutingTool) | MIT | candidate | here | later | Fuel-optimal routes through weather; MIT so it can sit in our pipeline. |
| [SIMROUTE](https://github.com/ManelGrifoll/SIMROUTE) | GPL | watch | here | later | A* weather routing with CMEMS (Ocean Engineering 2022). Separate process only. |
| [VISIR-2](https://zenodo.org/records/15497175) | GPL | watch | here | later | Graph-search weather routing with currents/waves/wind (GMD 2024). Separate process only. |
| [weather-routing-benchmark](https://github.com/AhmedAredah/weather-routing-benchmark) | CC-BY-4.0 | watch | here | later | Instance-matched benchmark for weather-routing papers. |

## simulation

_Time, queues, failures, weather delays (discrete-event, agent-based, vessel dynamics)_

| Tool | Licence | Status | Runs | Priority | Role |
|---|---|---|---|---|---|
| [SimPy](https://gitlab.com/team-simpy/simpy) | MIT | tested | here | now | Discrete-event core of offsim/sim/replay.py: berths, helidecks, time windows. |
| [Mesa](https://github.com/projectmesa/mesa) | check | watch | here | later | Agent-based models (crew, workers, fleets with behaviour). |
| [port-simulation (spartalab)](https://github.com/spartalab/port-simulation) | MIT | watch | here | later | DES of a port; reference for supply-base quay modelling. |
| [PythonVehicleSimulator (Fossen)](https://github.com/cybergalactic/PythonVehicleSimulator) | MIT | candidate | here | later | Physical OSV model (supply.py, L=76.2 m, thrusters): DP and approach times when a paper needs them. |
| [salabim](https://github.com/salabim/salabim) | MIT | candidate | here | later | DES with built-in 2D/3D animation and video export; quick explainer clips of queues at a base. |

## offshore-energy

_Domain models for offshore wind/oil and gas logistics_

| Tool | Licence | Status | Runs | Priority | Role |
|---|---|---|---|---|---|
| [ORBIT (NREL)](https://github.com/WISDEM/ORBIT) | check | candidate | here | next | SimPy installation logistics of offshore wind (WTIV, feeders, port cranes, weather delays) — sustainable-energy logistics videos. |
| [WOMBAT (NREL)](https://github.com/NLRWindSystems/WOMBAT) | Apache-2.0 | candidate | here | next | SimPy O&M simulation of offshore wind farms (CTVs, failures, weather); validated vs Dinwoodie and IEA Task 26. Ready source of O&M vessel scenarios. |
| [WAVES (offshore wind lifecycle)](https://github.com/NatLabRockies/WAVES) | Apache-2.0 | watch | here | later | Lifecycle wrapper combining installation and O&M models. |

## emissions

_Fuel, energy and emissions from vessel activity_

| Tool | Licence | Status | Runs | Priority | Role |
|---|---|---|---|---|---|
| [cetos (RISE Maritime)](https://github.com/RISE-Maritime/cetos) | check | candidate | here | next | Fuel per IMO Fourth GHG Study, batteries/hydrogen/hybrid systems, AIS to voyage profiles: CO2 per plan, electric PSV what-ifs. |
| [poeminv (Navisense)](https://pypi.org/project/poeminv/) | check | watch | here | later | Port emission inventories from tracks (transit, manoeuvring, hotelling). |

## render

_Maps and 3D scenes from validated trajectories_

| Tool | Licence | Status | Runs | Priority | Role |
|---|---|---|---|---|---|
| [deck.gl (TripsLayer](https://github.com/visgl/deck.gl) | MIT | tested | here | now | 2.5D animated trails; headless Chrome + SwiftShader works here (offsim/render_deck). |
| [Blender as Python module (bpy 5.2)](https://pypi.org/project/bpy/) | GPL | tested | actions | later | Low-poly 3D hero shots. Here: Workbench 1.4 s, Cycles 4 s per 640x360 frame. Separate process. |
| [BlenderGIS](https://github.com/domlysz/BlenderGIS) | GPL-3.0 | candidate | laptop | later | Import DEM, shapefiles, OSM into Blender. |
| [kepler.gl](https://github.com/keplergl/kepler.gl) | MIT | watch | browser | later | Drag-and-drop exploration of trajectories before scripting a video. |
| [lonboard](https://github.com/developmentseed/lonboard) | check | watch | here | later | deck.gl from Python/Jupyter with TripsLayer from MovingPandas; interactive exploration. |

## video

_Assembling frames, captions and explainers into posts_

| Tool | Licence | Status | Runs | Priority | Role |
|---|---|---|---|---|---|
| [FFmpeg](https://ffmpeg.org) | LGPL/GPL | tested | here | now | Frames to H.264 (veryfast preset). |
| [Remotion](https://github.com/remotion-dev/remotion) | Remotion licence (free for individuals/small teams) | tested | here | next | Title cards, captions, compositing map clips with charts. Works here with system Chrome. |
| [Manim Community](https://github.com/ManimCommunity/manim) | MIT | candidate | here | later | Animated maths: show the model (objective, constraints) before the map. |

## assets

_Free 3D models and textures for the cartoony look_

| Tool | Licence | Status | Runs | Priority | Role |
|---|---|---|---|---|---|
| [Kenney Watercraft Kit](https://kenney-assets.itch.io/watercraft-kit) | CC0 | candidate | here | later | 45+ low-poly boats/ships in glTF: the cartoony vessel set. |
| [Poly Haven](https://polyhaven.com) | CC0 | watch | here | later | CC0 HDRIs and textures for sea/sky lighting in Blender. |
| [Quaternius LowPoly Ship Pack](https://opengameart.org/content/lowpoly-ship-pack) | CC0 | candidate | here | later | Additional CC0 ships in the same visual register. |

## design

_Visual systems and UI for maritime displays_

| Tool | Licence | Status | Runs | Priority | Role |
|---|---|---|---|---|---|
| [OpenBridge web components](https://github.com/Ocean-Industries-Concept-Lab/openbridge-webcomponents) | check | candidate | here | later | Maritime bridge UI design system (Norwegian Ocean Industries Concept Lab): instrument-style overlays that read 'offshore' at a glance. |

## mcp

_Connectors that let Claude drive desktop tools_

| Tool | Licence | Status | Runs | Priority | Role |
|---|---|---|---|---|---|
| [QGIS MCP](https://github.com/jjsantos01/qgis_mcp) | check | candidate | laptop | next | Claude drives QGIS: inspect Kartverket depth and Sodir layers before packaging a world. |
| [BlenderMCP](https://github.com/ahujasid/blender-mcp) | MIT | candidate | laptop | later | Claude drives Blender on your machine (scene setup, materials, Poly Haven assets). |
| [OpenStreetMap MCP server](https://github.com/jagan-shanmugam/open-streetmap-mcp) | MIT | watch | laptop | later | Geocoding and Overpass queries from Claude (ports, bases, heliports). |
| [Rhino MCP (your existing setup)](https://github.com/Astheno-sphere/claude-mcp-servers) | check | watch | laptop | later | Already connected for the Molde/Kristiansund model; Grasshopper stills if wanted. |

## skills

_Claude Code skills that encode know-how_

| Tool | Licence | Status | Runs | Priority | Role |
|---|---|---|---|---|---|
| [computational_Logistics skills](https://github.com/Astheno-sphere/computational_Logistics/tree/main/skills) | MIT | tested | here | now | Sister repo: visual-narrative house style, vrp-solve cross-check pattern, knowledge-bank catalog of 1,800+ skills. |
| [remotion-dev/skills (remotion-best-practices)](https://github.com/remotion-dev/skills) | check | candidate | here | next | Frame-driven animation rules and a maps module for Remotion. |
| [SimPy skill (k-dense-ai/scientific-agent-skills)](https://github.com/k-dense-ai/scientific-agent-skills) | check | candidate | here | next | SimPy patterns (resources, containers, stores) for new process models. |
| [anthropics/skills (frontend-design](https://github.com/anthropics/skills) | check | watch | here | later | Design discipline for the README site and overlays. |

## benchmarks

_Instances and papers to reproduce_

| Tool | Licence | Status | Runs | Priority | Role |
|---|---|---|---|---|---|
| [Nafstad et al. 2020, offshore helicopter flight scheduling (C&OR, CC BY)](https://ntnuopen.ntnu.no/ntnu-xmlui/handle/11250/2722282) | CC-BY-4.0 | candidate | here | next | Norwegian shelf, heterogeneous fleet, multi-depot, multi-trip, synchronisation: needs OR-Tools CP-SAT or a MIP, not PyVRP alone. |
| [vrplib](https://github.com/PyVRP/VRPLIB) | check | candidate | here | next | Read/write VRPLIB and Solomon instances; regression-test the adapter on known optima. |
| [Lubnina & Kochetov 2024, periodic pickup-delivery helicopter routing (YUJOR)](https://yujor.fon.bg.ac.rs/index.php/yujor/article/view/1297) | check | watch | here | later | VNS with split demands; reports 5-10% cost reduction. |
| [MIRPLib.jl](https://github.com/rafaelmartinelli/MIRPLib.jl) | MIT | watch | laptop | later | Maritime inventory routing instances (Julia). |
