# Project Status: DamSight

**Current Phase:** Milestone 2 Close-out Complete  
**Last Updated:** September 19, 2026  
**Active Conda Environment:** `damsight` (Python 3.11.16, ANUGA 4.0.0 installs natively on Windows from conda-forge; env = damsight (py3.11))  
**Test Suite Status:** 35 / 35 Passing (`pytest -v`)  
**Linter & Type Checking Status:** Ruff (Clean), Black (Formatted), MyPy (`solvers/base.py` Clean)  

---

## 1. Milestones Overview

| Milestone | Scope | Status | Notes |
|---|---|---|---|
| **Milestone 0** | Repo layout, v2 config schema, `TODO_VERIFY` tracking, Makefile & tasks | **COMPLETE** | Schema v2, site_a.yaml, 16 config tests passing. |
| **Milestone 1** | Data ingestion, DEM priority-flood conditioning, land cover, WorldPop, OSM, Manning lookup | **COMPLETE** | Offline mode, grid alignment, audit logging in `report.json`. |
| **Milestone 2** | Froehlich (1995/2008) breach equations, broad-crested weir hydrograph, level-pool drawdown | **COMPLETE** | Analytical worked examples, mass conservation, smooth recession decay. |
| **Pre-M3 Follow-up** | Preflight, linting, GDAL nodata bug, allow_unverified guard, fabrication purge, warnings filter, synthetic figure | **COMPLETE** | All 8 tasks implemented and verified. No M3 work started. |
| **Milestone 3** | Hydrodynamic Solvers: ANUGA (guaranteed) and Delft3D FM (time-boxed) | **NOT STARTED** | Pending user instruction to begin Milestone 3. |

---

## 2. Pre-M3 Follow-up Achievements

1. **Preflight & Tooling Verification:**
   - Captured verbatim CLI outputs for Python, where, ANUGA import, ruff, black, mypy, and make.
   - Pinned `python=3.11` in `environment.yml` and `requires-python = ">=3.11,<3.13"` in `pyproject.toml`.
   - Added `ruff`, `black`, `mypy`, `pytest` to dev dependencies.
   - Added `scripts/tasks.ps1` mirroring every Makefile target for Windows environments lacking native `make`.
   - Configured UTF-8 encoding across all file operations.

2. **Linting & Code Quality:**
   - Resolved all 159 Ruff issues across `src/`, `tests/`, and `scripts/`.
   - Reformatted entire codebase to Black specification (100-character line length).
   - Created `src/damsight/solvers/base.py` defining `Solver`, `RunDir`, `RunResult`, and `Outputs` protocols, fully type-checked with MyPy.

3. **NoData Bug Elimination:**
   - Identified root cause of GDAL warning (`Value 0 ... changed to 1.4013e-45`): `dst_nodata=0.0` in `src/damsight/data/exposure.py`.
   - Explicitly assigned nodata per layer: `-9999.0` for float rasters (DEM, population, Manning), `255` for uint8 ESA WorldCover.
   - Added `test_population_zeros_preserved_and_exact_void_count` in `tests/test_data.py`: verifies 30 valid zeros are preserved, 20 real voids are counted exactly (void percentage before: 0.0%, after: 20.0%).

4. **Config Schema & Unverified Guard (`allow_unverified`):**
   - Restored 4 v1 test functions adapted to v2: `test_missing_required_field_site_id_fails`, `test_missing_required_solver_fails`, `test_invalid_non_numeric_and_non_todo_field_fails`, and `test_invalid_bbox_length_fails`.
   - Implemented `allow_unverified` guard: functions consuming physical values (`consume_dam_parameters`, `consume_physical_parameter`) raise `ValueError` on `TODO_VERIFY` or `{verified: false}` unless `allow_unverified=True`, in which case outputs carry `data_status="unverified"`.
   - Enforced `config.dam` requiring explicit `dam_id` via `config.get_dam(dam_id)` when multiple dams exist and scenario A2 has no `breach_dam`.
   - Verified `configs/sites/site_a.yaml` loads with `data_status.dam_parameters == "unverified"`.

5. **Fabrication Purge:**
   - Removed fabricated physical defaults from `src/`:
     - `crest_elevation_m: float = 100.0` in `generate_breach_hydrograph` (now required).
     - `cd_rect: float = 1.70` and `cd_tri: float = 1.35` in `generate_breach_hydrograph` (now required).
     - `dead_storage_m3: float = 0.0` in `StageStorageCurve` (now required).
     - `default_manning: float = 0.040` in `generate_landcover_and_manning` (now required).
     - `cell_size_m: float = 30.0` and `max_fill_depth: float = 15.0` in `fill_depressions_priority_flood` and `condition_and_save_dem` (now required).
   - Renamed real dam test fixture names to `SYNTHETIC_TEST_DAM`.

6. **Targeted Warning Filters:**
   - Configured targeted `filterwarnings` entries in `pyproject.toml` for `rasterio.transform` and `affine` `PendingDeprecationWarning` regarding matrix multiplication operator (`@` vs `*`).
   - Documented upstream provenance in `ASSUMPTIONS.md` (Section 5).

7. **Hydrograph Simulation & Visual Reporting:**
   - Replaced `docs/SLIDE_FIGURES/hydrograph_site_a.png` with `docs/SLIDE_FIGURES/hydrograph_SYNTHETIC_example.png`.
   - Added prominent disclaimer banner stamping `"SYNTHETIC INPUTS, NOT MACHHU-II"` and all input parameters on figure.
   - Verified script strictly uses synthetic inputs and does not read site_a dam values.
   - Simulation extends until discharge drops below 1% of peak ($Q < 0.01 \times Q_{\text{peak}}$):
     - Residual above-invert volume: **0.107%** ($26,814.7\text{ m}^3 / 25,000,000.0\text{ m}^3$)
     - Fraction of above-invert storage drained: **99.89%** ($24,973,186.0\text{ m}^3 / 25,000,000.0\text{ m}^3$)
     - Final stage: **55.99 m** (invert: 55.00 m)
     - First clamp binding step: **None (0 clamp events)**
     - Peak outflow: **10,969.9 m³/s**
   - Added unit tests `test_hydrograph_recession_limb_decays_without_discontinuity` and `test_hydrograph_tail_asymptotic_recession_and_clamp_invariance` in `tests/test_breach.py`.
   - ANUGA 4.0.0 installs natively on Windows from conda-forge; env = damsight (py3.11).

8. **Repository Tracking:**
   - Renamed `agents.md` to `AGENTS.md` via two-step git mv.
