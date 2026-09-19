# DamSight: Project Implementation & Engineering Plan

**Problem Statement:** Smart India Hackathon 2026 — PS #161 (NTRO): Dam Break Inundation Modelling  
**Document Purpose:** Restating the architectural blueprint, milestone roadmap, component specifications, and comprehensive risk analysis in our own words based on `docs/SPEC.md`.

---

## 1. Executive Summary & Core Philosophy

DamSight is an end-to-end computational pipeline and interactive decision-support web application for dam-break flood wave simulation, risk exposure mapping, and emergency evacuation planning. The system bridges rigorous hydrodynamic physics (shallow-water 2D equations, empirical breach mechanics) with rapid-response intelligence (machine learning surrogates, time-dependent routing, and satellite-based hazard detection).

### Non-Negotiable Ground Rules
1. **Physical Correctness Over Cosmetic Polish:** A visually impressive flood boundary that violates mass balance or hydrodynamics is catastrophic in emergency planning. We never fabricate physical results.
2. **Mandatory Honesty Flagging (`data_status`):** Every synthetic boundary, approximate parameter, and unverified dam dimension must be explicitly tagged (`verified`, `unverified`, or `synthetic`) across data pipelines, database models, and web UI components. All assumptions are tracked in `ASSUMPTIONS.md`.
3. **Strict Verification Hygiene:** Unverified parameters are never hardcoded from unvalidated memory. They reside in configuration files tagged with `source` and `TODO_VERIFY`.
4. **Solver Decoupling & Extensibility:** Solvers are abstracted behind a unified interface protocol (`prepare`, `run`, `collect`). If a specialized solver cannot run in a target deployment environment, the system gracefully falls back to supported solvers or precomputed simulation runs.
5. **Zero-Failure Live Demo Architecture:** Live presentations must never depend on long-running simulations or brittle network calls. All intensive hydrodynamic simulations are precomputed and packaged in `demo_data/`. Live surrogate inference runs sub-second; live solver runs are optional enhancements with offline fallback.
6. **Transparent Machine Learning:** The ML surrogate is explicitly demarcated as an approximation trained only on the specific modeled reach, displaying its validation error (RMSE, IoU, arrival-time MAE) and enforcing out-of-distribution parameter guards.

---

## 2. Interactive Demo Narrative (The 3–4 Minute Story)

1. **Watch Stage (Himalayan Lake & Blockage Detection):**  
   The operator views a high-altitude AOI (Site B, Rishiganga / Chamoli 2021). The system highlights a satellite-detected proglacial or landslide-dammed lake, displaying estimated volume, bounding geometry, and an automated downstream hazard exposure score.
2. **Site & Scenario Selection:**  
   The operator switches to Site A (main demo dam, e.g., Machhu-II), selecting breach mechanism (overtopping vs. piping), initial reservoir stage, and geotechnical breach parameters.
3. **High-Fidelity Hydrodynamic Simulation:**  
   The animated flood wave propagates down-valley. The UI provides continuous time scrubbing, rendering synchronized layers of water depth ($h$), velocity ($v$), hazard rating ($h \times v$), and wave front arrival times ($t_{\text{arrival}}$).
4. **Probabilistic Uncertainty Exploration:**  
   The operator toggles the ensemble probability layer ($P_{\text{flood}}$) generated from Latin Hypercube parameter sampling. Downstream settlements display arrival-time confidence bounds ($10^{\text{th}}$ percentile earliest plausible to $50^{\text{th}}$ percentile median).
5. **Real-Time "What-If" Analysis (Surrogate Slider):**  
   Dragging breach width and reservoir storage sliders updates the flood footprint in under a second via a calibrated PCA + Gradient Boosted surrogate model. A confidence badge informs the user of surrogate error bounds.
6. **Evacuation Decision Support:**  
   The evacuation analysis identifies road network inundation cut-off times. Villages are classified dynamically:
   - `can_evacuate`: Viable egress route before road closure.
   - `tight`: Evacuation feasible only if departure occurs within a tight window ($< N$ minutes).
   - `trapped`: All evacuation paths cut off prior to escape; designated for priority airborne or vertical rescue.
7. **Cross-Solver & Multi-Scenario Comparison:**  
   Split-screen view contrasts near-field hydrodynamic effects (or piping vs. overtopping breach dynamics) with spatial difference metrics.
8. **Cascade Failure Demonstration (Site C):**  
   A coupled upstream dam breach propagates downstream, dynamically elevating the secondary reservoir level and triggering secondary spillway overtopping or breach failure (clearly labelled hypothetical).
9. **Empirical Validation Panel:**  
   Simulated flood footprints are benchmarked against historical or Sentinel-1 satellite SAR observations, rendering precision, recall, F1, and IoU scores alongside mesh sensitivity metrics.
10. **Multi-Format Decision Artifact Export:**  
    One-click export of GIS packages: Shapefiles (`.shp` with `.prj`), Google Earth Keyhole Markup (`.kml`), and analysis-ready GeoTIFFs.

---

## 3. System Architecture & Data Flow

```
+-----------------------------------------------------------------------------------+
|                                 Configs & Inputs                                  |
|   configs/sites/<site>.yaml (AOI, Dam Dimensions, Ingest Sources, Solver Specs)   |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| 1. Ingestion Engine (src/damsight/data/)                                          |
|    - DEM (Copernicus 30m / SRTM), ESA WorldCover, WorldPop, OSM Networks          |
|    - Grid alignment, reprojection to projected UTM CRS, Manning's n synthesis     |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| 2. Geotechnical Breach Hydrograph (src/damsight/breach/)                          |
|    - Froehlich (1995/2008) parametric breach geometry & formation time            |
|    - Stage-storage level pool drawdown, mass conservation validation              |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| 3. Hydrodynamic Simulation Subsystem (src/damsight/solvers/)                      |
|    - Solver Protocol Interface: prepare() -> run() -> collect()                   |
|    - ANUGA 2D Shallow Water Solver (Primary far-field)                            |
|    - Delft3D FM / PySPH Adapters (Near-field / multi-solver)                      |
|    - Precomputed Results Adapter (Zero-dependency fallback)                       |
+-----------------------------------------------------------------------------------+
             |                                                  |
             v                                                  v
+---------------------------+                      +--------------------------------+
| 4. Ensemble & Uncertainty |                      | 5. Spatial Analytics & Support |
|    (src/damsight/ensemble)|                      |    - Evacuation Routing (evac) |
|    - Latin Hypercube (QMC)|                      |    - Cascade Routing (cascade) |
|    - p_flood, p10, p50    |                      |    - Satellite Watch (watch)   |
+---------------------------+                      |    - Validation vs SAR/History |
             |                                     +--------------------------------+
             v                                                  |
+---------------------------+                                   |
| 6. Fast Surrogate Model   |                                   |
|    (src/damsight/surrogate|                                   |
|    - PCA + GBDT / GP      |                                   |
|    - Sub-second what-if   |                                   |
+---------------------------+                                   |
             |                                                  |
             +--------------------+-----------------------------+
                                  |
                                  v
+-----------------------------------------------------------------------------------+
| 7. Distribution & Presentation Layer                                              |
|    - Export Engine (GeoTIFF, Shapefile, KML, Bounds-aligned PNG overlays)         |
|    - FastAPI REST Server (src/damsight/api/)                                      |
|    - Interactive Web Dashboard (webapp/: React + Vite + MapLibre GL)             |
+-----------------------------------------------------------------------------------+
```

---

## 4. Scope Tiers

| Tier | Module / Capability | Strategy & Fallback |
|---|---|---|
| **MUST** | Automated Data Ingestion (DEM, Land Cover, Exposure) | Local disk caching, offline synthetic fallbacks. |
| **MUST** | Breach Parameterization & Mass-Conserving Hydrograph | Froehlich empirical equations, rigorous mass checks. |
| **MUST** | 2D Shallow Water Hydrodynamic Solver (ANUGA) | Verified solver wrapper; precomputed runs packaged in repo. |
| **MUST** | Interactive Web Dashboard with Time Scrubbing & Export | React + MapLibre GL with pre-rendered PNG overlays. |
| **MUST** | Validation Framework (F1, IoU, Precision, Recall) | Automated comparison against historical flood extents. |
| **SHOULD** | Probabilistic Ensemble (LHS, $P_{\text{flood}}$, Arrival ranges) | Coarse-grid parallelization across 100+ members. |
| **SHOULD** | Evacuation Accessibility Routing & Settlement Triage | Time-dependent Dijkstra over OSM road network. |
| **SHOULD** | Instantaneous ML Surrogate with Parametric Sliders | PCA + GBDT/RF with strict parameter hull bounds. |
| **SHOULD** | Multi-Scenario / Multi-Solver Split Comparison | Differential raster analysis and tabular summaries. |
| **COULD** | SPH Near-Field Hydrodynamic Coupling (PySPH) | Small benchmark reach; fallback to documented analytical model. |
| **COULD** | Delft3D Flexible Mesh Input Adapter | Config generator and CLI runner; fallback to ANUGA/precomputed. |
| **COULD** | Live Satellite Water Extraction (Google Earth Engine) | Live GEE pipeline when keys are present; cached GeoJSON offline. |
| **COULD** | Cascading Multi-Reservoir Breach Routing | Two-dam coupled system on Site A river reach. |

---

## 5. Milestone Delivery Roadmap

### Milestone 0: Project Baseline, Environment & Verified Config Schema
- **Deliverables:** Repo scaffold (Section 5.1), `pyproject.toml`, `environment.yml`, multi-target `Makefile`, Pydantic configuration loader with strict `TODO_VERIFY` warning telemetry, `configs/sites/site_a.yaml` populated without unverified guesses, comprehensive unit tests.
- **Definition of Done:** `pytest tests/test_config.py` passes cleanly; invalid configs are rejected; `TODO_VERIFY` fields trigger traceable warnings without crashing; `make setup` and skeleton targets function.

### Milestone 1: Data Ingestion & Terrain Conditioning (Site A)
- **Deliverables:** Automated download, reprojection, and clipping of 30m DEM, ESA WorldCover, OSM road and building vectors, and WorldPop datasets. Automated derivation of Manning's roughness raster. Sink filling and hydrological conditioning.
- **Definition of Done:** `python scripts/run_site.py --site site_a --stage ingest` generates aligned GeoTIFFs in `cache/site_a/` and an audit `report.json`.

### Milestone 2: Breach Dynamics & Hydrograph Formulation
- **Deliverables:** Analytical Froehlich (1995/2008) breach parameters (width, development time, peak discharge). Reservoir drawdown stage-storage level pool routing. Natural dam landslide variant.
- **Definition of Done:** Mass balance conservation tests pass ($\int Q(t) dt \le V_{\text{stored}}$); unit tests confirm mathematical parity with published worked examples.

### Milestone 3: 2D Hydrodynamic Modeling Pipeline (ANUGA)
- **Deliverables:** ANUGA solver adapter translating domain DEM, Manning roughness, boundary conditions, and breach hydrograph into time-stamped hydraulic rasters ($h(x,y,t), v(x,y,t), t_{\text{arrival}}(x,y)$). Mass conservation tracking.
- **Definition of Done:** Automated execution generates standard output rasters (`max_depth.tif`, `arrival_time.tif`, etc.) with mass balance error logged and bounded below configured threshold.

### Milestone 4: Export Engine & Base Web Dashboard
- **Deliverables:** Conversion of simulation rasters into GeoTIFF, Shapefile (with `.prj`), KML, and web-ready georeferenced PNG overlays. React + Vite + MapLibre GL frontend with layer toggle and time slider.
- **Definition of Done:** Web dashboard boots offline, serving precomputed Site A runs with responsive time scrubbing and error-free GIS downloads.

### Milestone 5: Validation Engine & Mesh Sensitivity
- **Deliverables:** Spatial raster comparison toolkit evaluating simulated boundaries against ground truth (F1, IoU, Cohen's kappa). Multi-resolution grid sensitivity pipeline (e.g., 15m, 30m, 60m).
- **Definition of Done:** Generation of `validation_report.json` rendered transparently in the web UI without parameter tuning bias.

### Milestone 6: Probabilistic Ensemble & Risk Analytics
- **Deliverables:** Latin Hypercube sampler varying breach geometry and reservoir head. Batch parallel simulation execution over coarsened domains. Aggregator computing $P_{\text{flood}}$, $P_{10}$, and $P_{50}$ arrival surfaces.
- **Definition of Done:** 100+ member run completes; aggregate statistics verify that $P_{10}(\text{arrival}) \le P_{50}(\text{arrival})$ across all wet cells.

### Milestone 7: Dynamic Evacuation Feasibility & Settlement Triage
- **Deliverables:** Integration of OSM road network graph with time-evolving flood boundaries. Time-dependent Dijkstra solver identifying road inundation cut-offs and classifying settlement evacuation viability (`can_evacuate`, `tight`, `trapped`).
- **Definition of Done:** Output of `evacuation.geojson` and prioritized evacuation priority table verified against synthetic benchmark network.

### Milestone 8: Rapid Machine Learning Surrogate
- **Deliverables:** Dimensionality reduction (spatial PCA) + gradient boosting regressor trained on ensemble results. Sub-second inference for arbitrary parameter slider inputs within trained convex hull. Out-of-bounds parameter warning guard.
- **Definition of Done:** Inference latency $< 1.0\text{s}$; held-out validation RMSE and IoU displayed candidly in UI; out-of-range slider values safely flagged.

### Milestone 9: Satellite Detection & Natural Dam Pipeline (Site B)
- **Deliverables:** Google Earth Engine SAR/optical water detection script (Chamoli / Rishiganga). Elevation-volume estimation and downstream hazard ranking. Cached fallback for offline execution.
- **Definition of Done:** Web UI displays detected high-altitude water body and initiates breach scenario with one click.

### Milestone 10: Multi-Solver Comparison (SPH / Delft3D FM)
- **Deliverables:** Solver adapter for Delft3D FM / PySPH near-field simulation or documented fallback adapter. Side-by-side raster differencing in UI.
- **Definition of Done:** Comparative view displays spatial divergence and statistical deltas between alternative formulation and standard 2D shallow-water runs.

### Milestone 11: Cascading Failure Modeling (Site C)
- **Deliverables:** Coupled hydraulic routing connecting upstream breach outflow into downstream reservoir stage-storage pool. Dynamic overtopping trigger logic.
- **Definition of Done:** Automated test proves that sub-critical release preserves downstream integrity while super-critical release triggers secondary cascade failure.

### Milestone 12: Demonstration Hardening & Operational Readiness
- **Deliverables:** Full offline rehearsal of 4-minute demo script, complete documentation (`ASSUMPTIONS.md`, `BLOCKERS.md`, `PERFORMANCE.md`, `DEMO_SCRIPT.md`), automated end-to-end regression tests.
- **Definition of Done:** Clean clone builds and launches full interactive demo via `make demo` with zero internet connectivity.

---

## 6. Comprehensive Risk Assessment & Mitigation Strategies

```
+---------------------------------------------------------------------------------------------+
|                                     RISK MATRIX OVERVIEW                                    |
+------------------------------------+-----------+------------+-------------------------------+
| Risk Description                   | Likelihood| Impact     | Mitigation Strategy           |
+------------------------------------+-----------+------------+-------------------------------+
| 1. Hydrodynamic Solver Instability | Medium    | Critical   | Strict CFL limits, mesh       |
|    or Windows Installation Failure |           |            | coarsening, precomputed runs. |
+------------------------------------+-----------+------------+-------------------------------+
| 2. Spatial Data Sparsity & Coarse  | High      | Major      | DEM smoothing, OSM confidence |
|    Terrain Resolution (30m)        |           |            | flags, user-supplied GIS.     |
+------------------------------------+-----------+------------+-------------------------------+
| 3. Computational Bottlenecks in    | High      | Major      | Coarsened ensemble meshes,    |
|    Ensemble Simulation             |           |            | multi-core parallelization.   |
+------------------------------------+-----------+------------+-------------------------------+
| 4. ML Surrogate Inaccuracy &       | Medium    | Moderate   | Fallback to nearest neighbor  |
|    Out-of-Distribution Drift       |           |            | physics run; visible error.   |
+------------------------------------+-----------+------------+-------------------------------+
| 5. Incomplete Road Graphs in Rural | High      | Major      | Graph snapping, connectivity  |
|    Himalayan/Indian Reaches        |           |            | audits, manual egress nodes.  |
+------------------------------------+-----------+------------+-------------------------------+
| 6. Live Presentation Latency /     | Medium    | Critical   | 100% precomputed demo assets, |
|    Network Outages                 |           |            | zero runtime network calls.   |
+------------------------------------+-----------+------------+-------------------------------+
```

### Risk 1: Hydrodynamic Solver Portability and Numerical Convergence
- **Specific Vulnerability:** ANUGA and C-based hydrodynamic solvers often encounter compilation or C-extension compatibility issues on native Windows platforms, or numerical blow-ups (CFL violations) on steep Himalayan river reaches.
- **Mitigation:**
  - Package dependencies via standardized Conda-forge recipes and Docker containers.
  - Structure solver calls through the abstract `Solver` interface.
  - Implement a `precomputed` solver adapter that transparently serves verified runs stored in `demo_data/site_a/` whenever native binaries are unavailable or fail numerical tolerances.
  - On steep topography, apply adaptive time-stepping and modest elevation gradient conditioning.

### Risk 2: Coarse Topographical Resolution and Bathymetry Inaccuracies
- **Specific Vulnerability:** 30-meter DEMs (Copernicus / SRTM) blur narrow river gorges and fail to represent below-water river bathymetry, causing artificial damming or excessive lateral flood spreading.
- **Mitigation:**
  - Document all DEM conditioning transparently in `ASSUMPTIONS.md`.
  - Provide synthetic channel carving options where documented.
  - For Site A, select a documented reach (such as Machhu-II / Morbi plain) where 30m resolution accurately captures the alluvial floodplain morphology.

### Risk 3: Computational Run-Time of 100+ Member Ensemble
- **Specific Vulnerability:** Full 2D hydrodynamic simulation of 100 to 200 members at 30m resolution could take dozens of hours, far exceeding development and validation budgets.
- **Mitigation:**
  - Decouple ensemble resolution: run the single high-fidelity demonstration run at fine resolution (e.g., 30m), but execute ensemble members on a coarsened grid (e.g., 60m–90m) using `concurrent.futures` / Ray parallelization.
  - Precompute and persist all ensemble percentile grids (`p_flood.tif`, `arrival_p10.tif`, `arrival_p50.tif`) in `demo_data/`.

### Risk 4: Machine Learning Surrogate Fidelity and Generalization
- **Specific Vulnerability:** Non-linear hyperbolic shallow-water dynamics are notoriously challenging for spatial regression; surrogates may generate physically nonsensical negative depths or fail on unseen parameter combinations.
- **Mitigation:**
  - Restrict surrogate target domain to spatial PCA decomposition with gradient boosted trees or Gaussian process regressors.
  - Enforce hard non-negativity clipping ($h \ge 0$).
  - Calculate the multidimensional convex hull of training parameters; if an incoming slider query is outside the hull, immediately set `out_of_range: true` and either snap to the nearest precomputed scenario or display an explicit warning badge in the web UI.
  - Prominently post the model disclaimer: *"Trained on physics simulations for this reach only. Not valid for other rivers."*

### Risk 5: Road Graph Disconnection in Evacuation Modeling
- **Specific Vulnerability:** OpenStreetMap (OSM) highway coverage in rural or mountainous Indian districts can have disconnected segments, missing bridges, or dead-ends, incorrectly classifying reachable villages as trapped.
- **Mitigation:**
  - Implement graph cleaning: extract largest connected components, snap settlement centroids to the nearest routable road edge within a maximum radius.
  - Include an explicit `data_confidence` score in `evacuation_table.csv` flagging settlements where road density is below threshold.
  - Allow user-defined evacuation shelter points or egress boundary exits.

### Risk 6: Network and Authentication Failures During Live Demo
- **Specific Vulnerability:** Live calls to Google Earth Engine, OSM Overpass API, or elevation tile servers will fail if internet access is degraded or credentials expire during presentation.
- **Mitigation:**
  - Rule 5 enforcement: all assets for the 4-minute demo sequence reside locally in `demo_data/`.
  - Web application communicates with local FastAPI backend serving local GeoTIFFs, PNG overlays, and GeoJSON files.
  - Zero external HTTP requests are made during default `make demo` execution.

---

## 7. Verification and Testing Discipline

Every module must be defended by automated tests that execute locally in seconds without internet connectivity:
1. **Synthetic Spatial Fixtures:** Tests utilize tiny synthetic DEMs (e.g., $20 \times 20$ cell grids with known slope) and toy road networks with pre-determined trapped/feasible nodes.
2. **Mass Conservation Invariants:** Breach hydrograph total volume must not exceed initial reservoir storage ($\int Q dt \le V_0 \pm \epsilon$).
3. **Statistical Invariants:** Ensemble percentile calculations must guarantee $P_{10}(\text{arrival}) \le P_{50}(\text{arrival})$ everywhere.
4. **Configuration Validation:** Unverified placeholders (`TODO_VERIFY`) must be cleanly flagged as Python warnings without halting execution; missing mandatory structural fields must throw explicit validation errors.
5. **Contract Enforcement:** All raster outputs must conform to the unified CRS, spatial bounds, and resolution defined in the site configuration.
