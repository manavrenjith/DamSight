# DamSight: Demo Build Specification v2 (for the coding agent)

**Project:** DamSight, SIH 2026 PS #161 (NTRO), Dam Break Inundation Modelling Using Hydrodynamic Modelling of any River
**Audience:** you, the coding agent. This document says what to build for the final demo, in what order, and how to know each part is done.
**First actions:** read this whole file, write `docs/PLAN.md` restating the plan in your own words, then start Milestone 0.

---

## 0. Ground rules (non-negotiable)

1. **Correctness over polish.** A wrong but pretty flood map is worse than none. Never fabricate physical results.
2. **Label everything synthetic, approximate, defaulted or unverified**, in code, outputs and the UI. Keep `ASSUMPTIONS.md` listing every assumption, source, and any number you could not verify.
3. **Do not hard-code facts you have not verified** (dam dimensions, reservoir volumes, historical discharges, casualty figures). Put them in `configs/sites/*.yaml` with `source:` and `verified: false` until reconciled. Use `TODO_VERIFY` for unknowns.
4. **Solver abstraction.** The pipeline must not depend on one solver. Implement adapters behind one interface (Section 7.4).
5. **Precompute for the demo.** The live demo must never depend on a long simulation or a network call succeeding. Ship precomputed results in `demo_data/`.
6. **Small commits, tests per module, and a working `make demo` at every milestone.**
7. **The UI must be honest.** Show uncertainty as ranges, label the ML surrogate and its error, label hypothetical scenarios, and show data-status badges.
8. **Blockers:** record in `BLOCKERS.md`, apply the fallback from Section 11, and continue. Do not stall.
9. **Secrets:** never commit credentials, keys or project identifiers. Read them from environment variables (Section 7.9).
10. **Read the manuals.** For Delft3D FM, DualSPHysics, PySPH and ANUGA, use the official documentation for exact keyword and API names. Do not guess them.

---

## 1. What the problem statement requires, and where it is met

Requirements taken from the PS text:

| PS requirement | Where it is met in this project |
|---|---|
| Automatically simulate dam-break or water-release flooding and identify inundated area in the lower catchment | Modules 7.2 to 7.5, pipeline in `scripts/run_site.py` |
| Framework built from hydrological data, DEM and satellite imagery of any river | Config-driven ingestion (7.2), generic site config (Section 6) |
| Dam break AND river blockage / natural dam analysis | Breach module variants (7.3), Site B (Section 5), satellite watch (7.9) |
| Use SPH and Delft3D models and compare scenarios | Solver adapters (7.4) and `solvers/compare.py` |
| Sudden water surge and loss and damage analysis | Depth-damage and exposure (7.6 outputs, 7.8 evacuation table) |
| Customized tool to generate scenarios from different input datasets | Pluggable data loaders, user-supplied DEM and hydrograph files (7.2, 7.3) |
| Dashboard (GUI) for inputs and outputs, large data, export to .shp or .kml | Dashboard (7.13), export (7.11) |
| Near-real-time flood analysis through Google Earth Engine with open data | Satellite watch and Sentinel-1 flood mapping (7.9, 7.10) |
| Final demo on any Indian river and dam with open data | Site A: Machhu-I / Machhu-II (Section 5) |

Everything else (ensemble, surrogate, evacuation, cascade) is added differentiation. It must never come at the cost of the rows above.

---

## 2. Demo story (about 3 to 4 minutes)

1. **Watch.** A Himalayan map shows a satellite-detected lake or blockage ranked by risk (Site B).
2. **Pick a site and scenario.** Site A (Machhu chain), breach type and reservoir level.
3. **Physics result.** Flood wave animates on a time slider, with depth, arrival time and hazard layers.
4. **Uncertainty.** Flood **probability** layer and per-settlement **arrival-time ranges**.
5. **Instant what-if.** Sliders drive the surrogate and the map updates in seconds, with an error badge.
6. **Decision output.** Evacuation panel: cut-off roads and closure times, trapped villages, ranked by urgency.
7. **Solver comparison.** Delft3D FM vs ANUGA (and SPH near-field where achieved), plus piping vs overtopping.
8. **Cascade.** Machhu-I upstream release into Machhu-II: does the downstream dam overtop? Labelled HYPOTHETICAL for A2.
9. **Validation.** Simulated vs reference extent with scores, plus the analytical benchmark result.
10. **Export.** .shp, .kml, GeoTIFF.

---

## 3. Scope tiers

| Tier | Feature |
|---|---|
| **MUST** | Data ingestion for the Site A reach |
| **MUST** | Breach hydrograph (Froehlich-based) with mass-conservation test |
| **MUST** | ANUGA far-field solver end to end (the guaranteed working solver) |
| **MUST** | Analytical dam-break benchmark (Ritter dry bed, Stoker wet bed) run on every solver adapter |
| **MUST** | Dashboard with time slider, layers, exports (.shp, .kml, GeoTIFF) |
| **MUST** | Validation panel, honest about which reference was used |
| **MUST (time-boxed)** | Delft3D FM adapter: build inputs, run through DIMR, collect rasters. Time-box in Milestone M4. Fallback in Section 11. |
| **SHOULD** | Ensemble to probability and arrival-time ranges |
| **SHOULD** | Evacuation feasibility (trapped villages, closure times) |
| **SHOULD** | ML surrogate with live sliders (single reach) |
| **SHOULD** | Satellite watch with live Earth Engine plus cached fallback (Site B) |
| **SHOULD** | SPH near-field on a small reach or benchmark, coupled into the far-field where achievable |
| **SHOULD** | Cascade module (Machhu-I to Machhu-II) |
| **COULD** | Site C: Periyar chain, Kerala 2018, Sentinel-1 validated release-and-routing case |
| **COULD** | Scenario comparison polish, extra export formats |

**Non-goals:** production authentication, real-time streaming, mobile apps, generic automatic meshing for arbitrary rivers beyond the demo sites, claims of predictive accuracy on unseen rivers.

**Priority rule:** finish all MUST items before starting any SHOULD item. If time runs short, cut in this order: Site C, SPH coupling, surrogate polish, cascade polish.

---

## 4. Decisions (frozen) and open items

### 4.1 Decided. Do not re-ask.

| # | Topic | Decision |
|---|---|---|
| D1 | Main demo site | Machhu-I / Machhu-II chain on the Machhu river, Morbi region, Gujarat (Section 5). |
| D2 | Cascade case | Real dam chain. A1 is a hindcast of the 1979 Machhu-II overtopping failure. A2 is a hypothetical upstream release or failure, labelled HYPOTHETICAL. |
| D3 | Validation | Both, if time allows: historical record for Site A (Sentinel-1 cannot be used for 1979), Sentinel-1 for satellite-era events (Site C, Kerala 2018). |
| D4 | Data honesty | All Machhu figures stay `verified: false` until reconciled. Public sources disagree. |
| D5 | Earth Engine | Available. Non-commercial registration, **Community quota tier (150 EECU-hours)**. Live detection enabled, cached fallback retained. |
| D6 | Delft3D FM | Proceed. Time-boxed setup, benchmark first, ANUGA remains the guaranteed solver. |
| D7 | Differentiators | Probabilistic maps, ML surrogate, evacuation feasibility, cascade failure, satellite-triggered natural-dam watch. |

### 4.2 Open. Ask the user once at the start of M0, then continue using the default.

| # | Question | Default if unanswered | Affects |
|---|---|---|---|
| O1 | Hardware: CPU cores, RAM, NVIDIA GPU? | Assume CPU-only, 8 cores, 16 GB RAM. Ensemble of 100 members on a coarse mesh. SPH restricted to a tiny benchmark. | Ensemble size, SPH scope, mesh resolution |
| O2 | Source of the 1979 inundation reference (published map or study)? | Do not invent one. Validate against documented checkpoints (reported depths and timing at Morbi) and label it a qualitative sanity check, not an F1/IoU score. | Validation (M6) |

If an answer arrives later, update `ASSUMPTIONS.md` and re-run only the affected stages. Never present a default as a confirmed fact.

---

## 5. Sites

Configure in `configs/sites/*.yaml`. Do not invent numbers.

### Site A: Machhu-I / Machhu-II (main demo and cascade)
- A real two-dam chain. Public case studies describe storm flow reaching Machhu Dam I first and then Machhu Dam II downstream, and Machhu II overtopping and failing on 11 August 1979.
- Machhu II is an earthen embankment, so the Froehlich embankment breach formulas are applicable. Morbi lies a few km downstream. The terrain is relatively gentle, which suits a 30 m DEM.
- **A1 (hindcast, validation):** reproduce the 1979 overtopping failure of Machhu II and compare with the historical record.
- **A2 (cascade what-if, HYPOTHETICAL):** upstream Machhu-I failure or large release routed into Machhu-II, testing whether it overtops. As far as public sources show, Machhu-I did not fail in 1979, so never present A2 as history.
- **Data caveat:** sources disagree on the 1979 flows and capacities (for example about 196,000 cfs passed against 200,000 to 220,000 cusecs of design capacity, inflow estimates of about 400,000 cusecs, and a CWC slide giving an observed peak near 16,300 m3/s). Casualty estimates also vary widely. Record every figure with its source, keep `verified: false`, and never put a single number on a slide or in the UI without its source.

### Site B: Rishiganga / Chamoli, Uttarakhand, February 2021 (natural-dam and satellite-watch demo)
- Steep terrain. Use for lake or blockage detection and a river-blockage breach scenario. State the 30 m DEM limitation clearly.
- Live Earth Engine detection, with a cached detection shipped for offline use.

### Site C (COULD): Periyar chain, Kerala, August 2018
- Chain: Mullaperiyar, Idukki, Bhoothathankettu, with Idamalayar joining. Satellite-era, so a Sentinel-1 flood extent can validate it. A CAG audit reports spill contributions to downstream flows on 14 to 18 August 2018, which can check cascade routing.
- **Model as operational release and routing only, not breach.** Idukki is an arch dam and Mullaperiyar is a masonry gravity dam, so the embankment breach formulas do not apply.
- **Mullaperiyar safety is a sensitive inter-state issue.** Do not produce or display failure predictions for it. Frame everything as release scenarios.
- Steep terrain limits accuracy of a 30 m DEM. State this.

---

## 6. Config schema (single source of truth)

`configs/sites/<site_id>.yaml`

```yaml
site_id: site_a
name: "Machhu-I / Machhu-II chain"
type: cascade                   # dam | natural_blockage | cascade
data_status:                    # shown as UI badges
  dam_parameters: unverified    # verified | unverified | synthetic | defaulted
crs: EPSG:32643                 # projected CRS for the reach; confirm per site
aoi: {bbox: [TODO, TODO, TODO, TODO]}      # lon/lat
dams:
  - id: machhu_1
    role: upstream
    location: [TODO, TODO]
    crest_elevation_m: TODO_VERIFY
    dam_height_m: TODO_VERIFY
    reservoir_volume_m3: TODO_VERIFY
    stage_storage_csv: data/site_a/machhu1_stage_storage.csv    # optional
    dam_type: embankment
    source: "TODO: cite"
  - id: machhu_2
    role: downstream
    location: [TODO, TODO]
    crest_elevation_m: TODO_VERIFY
    dam_height_m: TODO_VERIFY
    reservoir_volume_m3: TODO_VERIFY
    stage_storage_csv: data/site_a/machhu2_stage_storage.csv
    dam_type: embankment
    spillway_capacity_m3s: TODO_VERIFY
    source: "TODO: cite"
scenarios:
  - {id: A1_hindcast_1979, kind: hindcast, breach_dam: machhu_2, breach_type: overtopping}
  - {id: A2_cascade_whatif, kind: hypothetical, upstream_release_from: machhu_1}
inputs:
  dem: {source: copernicus_30m, path: null}   # copernicus_30m | srtm_30m | aster | user_file
  landcover: esa_worldcover
  population: worldpop
  buildings: osm                              # fallback: open_buildings
  roads: osm
reference_events:
  - {name: "Machhu-II 1979", type: historical, extent: null, source: "TODO: user to supply (open item O2)"}
solver:
  far_field: delft3dfm          # delft3dfm | anuga | precomputed
  baseline: anuga               # always available
  near_field: none              # none | pysph | dualsphysics
  mesh_resolution_m: 30
ensemble:
  n_members: 100
  parameters:                   # ASSUMPTIONS: document and expose in the UI
    breach_width: {sigma_ln: 0.3}
    formation_time: {sigma_ln: 0.4}
    peak_outflow: {sigma_ln: 0.3}
    reservoir_level_m: {range: [TODO_low, TODO_high]}
evacuation:
  walking_speed_kmh: 4.0
  vehicle_speed_kmh: 30.0
  road_closure_depth_m: 0.3
  safety_margin_min: 10
```

---

## 7. Modules

### 7.1 Repository layout

```
damsight/
  README.md  ASSUMPTIONS.md  BLOCKERS.md  Makefile  pyproject.toml  environment.yml
  configs/sites/*.yaml
  docs/{PLAN.md,DEMO_SCRIPT.md,PERFORMANCE.md,DELFT3D_NOTES.md,SLIDE_FIGURES/}
  src/damsight/
    data/ breach/ solvers/ ensemble/ surrogate/ evac/ cascade/ watch/ validate/ export/ api/
  webapp/                     # React + Vite + MapLibre GL
  demo_data/                  # precomputed results shipped with the repo
  tests/  scripts/            # run_site.py, precompute_demo.py, benchmarks/
```

### 7.2 Data ingestion (`data/`)
- Fetch and clip the DEM (Copernicus 30 m preferred; SRTM, ASTER or user file as alternatives), ESA WorldCover, WorldPop, OSM roads, buildings and places.
- Reproject to the site CRS, resample to a common grid, cache to `cache/<site_id>/`.
- Manning's n from a documented WorldCover lookup table `data/manning_lookup.csv`; cite the source in `ASSUMPTIONS.md`.
- Terrain conditioning: log every change; do not carve channels unless the config asks for it.
- **Acceptance:** `python scripts/run_site.py --site site_a --stage ingest` writes aligned rasters and `report.json` (CRS, resolution, extent, void percentage). Tests cover alignment and no-data handling.
- **Offline:** use cached files; if none, raise a clear error naming the missing dataset and where to place it.

### 7.3 Breach model (`breach/`)
- Froehlich (2008), SI units, as commonly stated:
  - `B_avg = 0.27 * Ko * Vw^0.32 * hb^0.04` with Ko = 1.3 (overtopping), 1.0 (piping)
  - `t_f = 63.2 * sqrt(Vw / (g * hb^2))` seconds
  - Froehlich (1995) peak outflow: `Qp = 0.607 * Vw^0.295 * hw^1.24`
  - **Verify against the papers**, document units and citations in `ASSUMPTIONS.md`, and add a unit test from a worked example if available.
- Hydrograph: weir flow through a growing trapezoidal breach with level-pool drawdown from the stage-storage curve. Outflow volume must never exceed stored volume (test this).
- Output `hydrograph.csv` (time_s, discharge_m3s) plus metadata JSON.
- Natural-dam variant (landslide, moraine, ice): separate parameter set, faster overtopping-erosion breach, marked illustrative unless sourced.
- Release-only mode (for Site C): spillway or gate release hydrographs from supplied data, no breach.

### 7.4 Solver adapters (`solvers/`)

Interface in `base.py`:

```python
class Solver(Protocol):
    def prepare(self, site, hydrograph, mesh_resolution_m) -> RunDir: ...
    def run(self, run_dir) -> RunResult: ...
    def collect(self, run_dir) -> Outputs   # rasters below
```

**Outputs contract:** on the site grid, same CRS and no-data value: `max_depth.tif`, `max_velocity.tif`, `arrival_time.tif` (seconds since breach start, first time depth > 0.1 m), `hazard.tif`, `depth_t{NNN}.tif`, plus `run_meta.json` (solver, version, mesh, runtime, mass-balance error, warnings).

**Every adapter must pass the analytical benchmark** in `scripts/benchmarks/`: an idealized flat rectangular channel dam break compared with the Ritter (dry bed) and Stoker (wet bed) solutions for front position and depth. Store results in `docs/PERFORMANCE.md`.

1. **`anuga_solver` (MUST, guaranteed).** Build the domain from the DEM, apply Manning's n, set the hydrograph as an inflow at the dam, write rasters. Fail the run if mass-balance error exceeds the configured tolerance. Prefer conda-forge for installation.
2. **`delft3dfm_solver` (MUST, time-boxed).**
   - **Obtain:** download the Delft3D FM Suite 2D3D (Hydro-Morphodynamics distribution, currently release 2026.01) from Deltares' own download pages. **Read the licence and registration terms first.** Never use third-party download sites. Do not commit binaries.
   - **Time-box:** half a day to run a bundled tutorial or example to completion. Record the outcome in `docs/DELFT3D_NOTES.md`. If it fails, apply the fallback in Section 11.
   - **Python tooling:** `dfm_tools` (pre and post-processing, built on hydrolib-core, xarray and xugrid) and the HydroMT-Delft3D FM plugin (model building). Install from conda-forge and pip. Use them where helpful; do not depend on features you have not verified.
   - **Adapter:** generate the unstructured mesh with bed levels from the DEM, Manning roughness, the breach hydrograph as the upstream discharge boundary, an open downstream boundary, and output settings; run through DIMR; rasterize the map output with xugrid to the outputs contract.
   - **Dam-break specifics to handle and document:** small enough time step for the sharp front (CFL control), dry-cell threshold, wet/dry handling, and initial conditions. Take exact keyword names from the D-Flow FM manual, not from memory.
3. **`pysph_solver` or `dualsphysics_solver` (SHOULD, scoped).**
   - Near-field only: the breach and the first stretch downstream (a short reach or an idealized geometry). Use DualSPHysics if an NVIDIA GPU is available, otherwise PySPH at coarse particle size.
   - Pass the 2D dam-break column benchmark against published or analytical front positions.
   - Coupling: convert SPH outflow at a defined cross-section into a hydrograph for the far-field solver; check mass conservation across the hand-off. State the coupling assumptions.
4. **`precomputed`.** Loads results from `demo_data/<site_id>/` following the outputs contract. Universal fallback for the demo.

**Solver comparison** (`solvers/compare.py`): difference rasters and metrics (extent overlap, peak depth difference, arrival-time difference at settlements) between two solvers on the same reach, plus benchmark results.

### 7.5 Ensemble and uncertainty (`ensemble/`)
- `sampler.py`: Latin Hypercube (scipy.stats.qmc or SALib) over breach width, formation time, peak outflow, reservoir level and breach type; log-normal multiplicative uncertainty around the empirical estimate. Sigma values are **assumptions**: document and expose them in the UI.
- `runner.py`: parallel runs (Dask, Ray or `concurrent.futures`) on a coarse mesh; skip failed members and log them. Members use the guaranteed solver (ANUGA) unless Delft3D FM is proven fast enough.
- `aggregate.py`: `p_flood.tif`, `depth_p50.tif`, `depth_p90.tif`, `arrival_p10.tif`, `arrival_p50.tif`, and a per-settlement table with arrival and depth ranges.
- **Acceptance:** at least 100 members (or fewer if hardware-limited, stated in the UI). Sanity tests: probabilities in [0,1], p10 arrival <= p50 arrival.

### 7.6 ML surrogate (`surrogate/`)
- Train on ensemble members: input parameters to downsampled output rasters (or fixed sample points).
- Baseline: PCA on the output rasters plus gradient boosting, random forest or Gaussian process on the coefficients. Escalate to a small MLP or U-Net only if the baseline fails.
- Hold out 20 percent. Report depth RMSE, extent IoU and arrival-time MAE in `surrogate_report.json`; show the headline numbers in the UI.
- Guard rails: flag `out_of_range: true` outside the training hull and fall back to the nearest precomputed scenario with a warning.
- UI text: "Trained on physics simulations for this reach only. Not valid for other rivers."
- **Acceptance:** prediction under 3 seconds for a full-reach map. If accuracy is not useful, say so in the UI and label the feature experimental. Do not hide it.

### 7.7 Cascade module (`cascade/`)
- Route the upstream hydrograph (lag and attenuation, for example Muskingum, or a solver-derived hydrograph at a section) into the downstream reservoir. Update its level via the stage-storage curve.
- If the level exceeds the downstream crest, trigger an overtopping breach via the breach module and continue.
- Output sequential hydrographs, a combined flood map and `cascade_triggered: true/false`.
- **Acceptance:** with synthetic dams, a small release does not trigger the downstream dam and a large release does. Scenario A1 reproduces the documented Machhu-II overtopping mechanism qualitatively. Scenario A2 is labelled HYPOTHETICAL.

### 7.8 Evacuation feasibility (`evac/`)
Inputs: p10 and p50 arrival rasters, max depth, OSM road graph (OSMnx, cached), settlement points, `evacuation` config.
1. Safe zones: cells not flooded in the P90 depth scenario plus a buffer (or a height above the local flood surface); road-graph nodes inside are targets. Allow user-defined shelters.
2. Edge closure time: earliest p10 arrival at which depth exceeds `road_closure_depth_m` anywhere along the edge; infinite if never flooded.
3. Time-dependent earliest-arrival routing from each settlement to a safe node, requiring entry time to each edge to be less than closure time minus `safety_margin_min`. Walking and vehicle variants.
4. Classes: `can_evacuate` (latest departure time and route), `tight`, `trapped` (no feasible route: needs air, boat or vertical evacuation).
5. Outputs: `evacuation.geojson` and `evacuation_table.csv` (population, arrival range, max depth, class, `data_confidence`).
- **Acceptance:** unit tests on a small synthetic graph with a known trapped node and a known feasible node. Note the dependence on OSM completeness in the UI.

### 7.9 Satellite watch (`watch/`)
- **Credentials.** Earth Engine access exists (non-commercial, Community tier, 150 EECU-hours). Read the Cloud project ID from `EE_PROJECT`; **never hard-code or commit it**. Default to the user's personal login (`earthengine authenticate`, then `ee.Initialize(project=os.environ["EE_PROJECT"])`). Support an optional service account via `EE_SERVICE_ACCOUNT` and `EE_KEY_FILE` for unattended runs; keys stay out of the repo (`.gitignore`).
- **Quota discipline:** clip every query to the AOI, do heavy work server-side, download only results, avoid large exports, and cache all detections locally.
- `gee_detect.py`: detect new surface water in an AOI from Sentinel-1 VV backscatter change (before and after) and optionally Sentinel-2 NDWI, masking permanent water with JRC Global Surface Water. Output polygons with area and detection date.
- `volume.py`: estimate lake volume from polygon and DEM by filling from the lake bed to an assumed outlet elevation; document the method and uncertainty.
- `risk.py`: transparent risk score (volume, dam type, downstream exposure within N km); show the formula in the UI.
- **Fallback:** ship `demo_data/watch/sample_detection.geojson` for Site B, marked as a cached detection with its date. The demo must never call Earth Engine live.
- **Acceptance:** with credentials the script runs on Site B; without them it clearly states it is using cached data.

### 7.10 Validation (`validate/`)
- `metrics.py`: precision, recall, F1, IoU between simulated extent (max depth above threshold) and a reference extent, plus an agreement / false positive / false negative map.
- **Site A:** historical reference (open item O2). Until a real reference is supplied, run checkpoint comparison only and label it a qualitative sanity check, not an F1/IoU score.
- **Site C or another satellite-era event:** Sentinel-1 derived flood extent via Earth Engine, or a user-supplied reference GeoJSON.
- Mesh-sensitivity check at 2 or 3 resolutions, and the analytical benchmark results, in `validation_report.json`.
- Show results exactly as computed, including poor scores. Record any parameter tuning in `ASSUMPTIONS.md`.

### 7.11 Export (`export/`)
- `.shp` (zipped, with `.prj`), `.kml` and GeoTIFF of inundation polygons (from a depth threshold), depth classes and settlement impact points, using rasterio.features.shapes and GeoPandas. Attributes: depth class, arrival p10 and p50, hazard class.
- `overlays.py`: colour-mapped PNG overlays with WGS84 bounds per layer and time step, so the web map needs no tile server.
- **Acceptance:** exports open in QGIS and Google Earth (state how you verified) with the correct CRS.

### 7.12 API (`api/`, FastAPI)
- `GET /sites`, `GET /sites/{id}` (including data-status flags)
- `GET /sites/{id}/layers` (layers, time steps, overlay URLs, bounds)
- `GET /sites/{id}/settlements`
- `POST /sites/{id}/surrogate/predict` (returns overlay URL, summary stats, `out_of_range`)
- `GET /sites/{id}/validation`, `GET /watch/detections`, `GET /sites/{id}/export?format=shp|kml|geotiff`
- Serve static overlays from `demo_data/`; enable CORS for local development.

### 7.13 Dashboard (`webapp/`, React + Vite + MapLibre GL)
Layout: map in the centre, controls on the left, results on the right.
- Site and scenario controls (breach type, reservoir level, breach width; sliders call the surrogate).
- Layer toggles: max depth, arrival time, hazard, flood probability, evacuation status.
- Time slider with play button (preload overlays).
- Settlement panel: ranked table (arrival range, depth range, population, evacuation class) with click-to-zoom.
- Evacuation layer: routes, cut-off segments with closure times, trapped villages highlighted.
- Compare view: two maps side by side (solver A vs B, or breach type A vs B) with a difference summary and benchmark results.
- Validation panel: agreement map and scores, or the qualitative-checkpoint label.
- Watch panel: detected lakes ranked by risk, with "Simulate breach" loading the matching precomputed scenario.
- Cascade toggle with the HYPOTHETICAL badge for A2.
- Export buttons.
- Badges: data status (verified, unverified, synthetic, defaulted), surrogate accuracy, "Precomputed" or "Live" per result.
- Design: high contrast and readable on a projector, colour-blind-safe palettes, distinct scales for depth and arrival time.
- **Acceptance:** everything loads from `demo_data/` with no network. Report initial load and layer-switch times.

---

## 8. Data contracts

```
demo_data/<site_id>/
  meta.json
  hydrograph_<scenario>.csv
  rasters/<scenario>/{max_depth,max_velocity,arrival_time,hazard}.tif
  rasters/<scenario>/depth_t000.tif ... depth_tNNN.tif
  ensemble/{p_flood,depth_p50,depth_p90,arrival_p10,arrival_p50}.tif
  overlays/<layer>/<scenario>/*.png + bounds.json
  evacuation/{evacuation.geojson,evacuation_table.csv}
  surrogate/{model.pkl,surrogate_report.json,training_ranges.json}
  validation/validation_report.json
  benchmarks/{ritter_stoker_results.json,plots/}
  exports/<scenario>.{zip,kml}
demo_data/watch/sample_detection.geojson
```

All rasters: same grid per site, GeoTIFF, deflate or LZW compression, explicit no-data.

---

## 9. Milestones (in order; each ends with a working demo state)

| # | Milestone | Definition of done |
|---|---|---|
| M0 | Repo, environment, plan, config schema; ask O1 and O2 once | `make setup` works, `docs/PLAN.md` written, site config validates |
| M1 | Ingestion for Site A | Aligned rasters, `report.json`, tests pass |
| M2 | Breach hydrograph | Unit tests including mass conservation pass |
| M3 | ANUGA far-field end to end plus analytical benchmark | Rasters for Site A, mass balance reported, Ritter/Stoker comparison saved |
| M4 | **Delft3D FM time-box (half a day)** | Tutorial runs, or the fallback is applied and logged in `DELFT3D_NOTES.md` |
| M5 | Exports and minimal dashboard | Time slider and .shp/.kml/GeoTIFF download from precomputed data |
| M6 | Validation panel | Scores or qualitative checkpoints (per O2), mesh-sensitivity report, benchmark results |
| M7 | Delft3D FM adapter end to end (if M4 succeeded) | Site A rasters from Delft3D, benchmark passed, comparison with ANUGA |
| M8 | Ensemble and probability layer | `p_flood` and arrival ranges per settlement |
| M9 | Evacuation feasibility | Classification and route layer, tests pass |
| M10 | Surrogate with sliders | Held-out accuracy shown in the UI, out-of-range guard works |
| M11 | Satellite watch (live plus cached) and Site B scenario | Detection panel and "Simulate breach" |
| M12 | Cascade (Machhu-I to Machhu-II) | A1 hindcast and A2 hypothetical with correct triggering test |
| M13 | SPH near-field benchmark and coupling (scoped) | Benchmark passed and outflow hand-off checked, or documented fallback |
| M14 | Site C (optional) | Release-and-routing case validated against Sentinel-1 |
| M15 | Demo hardening | `make demo` runs offline, demo script rehearsed, README complete |

---

## 10. Demo hardening and deployment

- `make precompute` runs heavy stages and writes `demo_data/`. `make demo` starts the API and web app using only `demo_data/`.
- `docs/DEMO_SCRIPT.md`: step-by-step walkthrough of Section 2 with exact clicks.
- `docs/SLIDE_FIGURES/`: screenshots of the key views (probability map, evacuation view, solver comparison, validation, benchmark plots).
- A health page shows which results are precomputed vs live and any warnings.
- `docs/PERFORMANCE.md`: runtime per stage, hardware, mesh sizes, ensemble size, benchmark results. These back up feasibility claims.
- **Deployment story (for slides):** dashboard and API are containerized (Docker Compose) and cloud-ready; simulations run as queued jobs on CPU or GPU workers; for sensitive use the stack can run fully on-premise with local copies of the data. For the demo: precomputed results plus, optionally, one small live run.

---

## 11. Fallbacks (apply automatically, log in BLOCKERS.md)

| Problem | Fallback |
|---|---|
| Delft3D FM will not install, licence unclear, or tutorial fails in the time-box | Keep the input generator and documented run instructions, run the far-field with ANUGA, and present the Delft3D adapter honestly as "inputs generated, validated on the benchmark only" or "not run" |
| Delft3D FM unstable on steep terrain | Coarsen the mesh, shorten the reach, tune the time step and dry threshold, and document; else use ANUGA for that site |
| PySPH or DualSPHysics too slow or unstable | Restrict to a tiny near-field benchmark, or drop and say so |
| ANUGA fails on a steep DEM | Coarsen the mesh, lightly smooth the DEM with logging, or shorten the reach |
| Earth Engine quota reached or credentials fail | Use the cached detection; never call Earth Engine during the demo |
| OSM roads sparse | Flag low confidence; accept a user-supplied roads file |
| Surrogate inaccurate | Show as experimental with its measured error, or snap to the nearest precomputed scenario |
| Ensemble too slow | Reduce members and mesh resolution; state the count in the UI |
| No 1979 reference extent supplied | Use documented checkpoints and label the result qualitative |
| No satellite-era reference available | Use a published extent or Sentinel-1 for another event and state the limitation |

---

## 12. Environment and commands

- Python 3.11; conda-forge (mamba) for geospatial, ANUGA and Delft3D Python tooling; Node 20 for the webapp.
- Provide `environment.yml` and a `Dockerfile` (do not bundle solver binaries whose licences are unconfirmed).
- Environment variables: `EE_PROJECT` (required for live Earth Engine), optional `EE_SERVICE_ACCOUNT`, `EE_KEY_FILE`. Provide `.env.example` with placeholders only.
- Makefile targets: `setup`, `ingest`, `run-site`, `benchmark`, `ensemble`, `surrogate`, `evac`, `precompute`, `demo`, `test`, `lint`.
- Tests: pytest with small synthetic fixtures (tiny DEM, toy graph, analytical benchmark) so tests run in seconds without network.
- Lint and format: ruff and black; type-check the interfaces in `solvers/base.py`.

---

## 13. Definition of done

- [ ] `make demo` runs offline and shows all MUST and SHOULD features on Site A.
- [ ] Each PS requirement in Section 1 is demonstrably met, or its fallback is documented honestly.
- [ ] Every result is labelled precomputed or live; every unverified, defaulted or hypothetical input is flagged.
- [ ] Analytical benchmark results are shown for each solver that ran.
- [ ] Validation results are shown exactly as computed, including which reference was used.
- [ ] Surrogate accuracy is displayed, with an out-of-range guard.
- [ ] Exports open correctly in QGIS and Google Earth.
- [ ] No credentials, keys or project identifiers are committed.
- [ ] `ASSUMPTIONS.md`, `BLOCKERS.md`, `DELFT3D_NOTES.md`, `DEMO_SCRIPT.md` and `PERFORMANCE.md` are complete and honest.
- [ ] A new developer can go from clone to demo using only the README.