"""Tests for hydrodynamic solver adapter (AnugaSolver).

Adheres to AGENTS.md testing discipline:
- Pre-set pass thresholds written into tests before execution.
- Tests include: lake-at-rest (C-property), mass balance conservation, arrival time raster on a synthetic ramp.
- Output contract validation (rasters, run_meta.json).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio

from damsight.solvers.anuga_solver import AnugaSolver


def test_lake_at_rest_c_property(tmp_path: Path):
    """Lake-at-rest C-property verification over irregular non-flat bathymetry.

    Pre-set pass threshold:
    Max velocity magnitude max |v| must remain strictly below 1e-4 m/s.
    """
    PASS_THRESHOLD_MAX_V = 1e-4  # m/s (pre-set threshold)

    solver = AnugaSolver()

    # Irregular non-flat bathymetry: sinusoidal bed variation between 0.7m and 1.3m
    def bumpy_bed(x: np.ndarray, y: np.ndarray) -> np.ndarray:
        return 1.0 + 0.3 * np.sin(2.0 * np.pi * x / 100.0)

    # Rectangular domain with reflective boundaries
    spec = {
        "type": "channel",
        "length_m": 100.0,
        "width_m": 40.0,
        "dam_x_m": 50.0,
        "h_left_m": 2.0,
        "h_right_m": 2.0,
        "manning_n": 0.03,
        "b_left": "reflective",
        "b_right": "reflective",
        "duration_s": 3.0,
        "yieldstep_s": 1.0,
    }

    run_dir = solver.prepare(spec, mesh_resolution_m=10.0, run_dir=tmp_path / "lake_at_rest")
    domain = run_dir.extra["domain"]

    # Set irregular bed elevation and uniform water level H = 2.0 m
    domain.set_quantity("elevation", bumpy_bed)
    domain.set_quantity("stage", 2.0)

    res = solver.run(run_dir, yieldstep=1.0, finaltime=3.0)
    assert res.success is True

    # Compute max velocity across all cells at final time
    h = np.maximum(
        domain.quantities["stage"].centroid_values - domain.quantities["elevation"].centroid_values,
        1e-6,
    )
    u = domain.quantities["xmomentum"].centroid_values / h
    v = domain.quantities["ymomentum"].centroid_values / h
    speed = np.sqrt(u**2 + v**2)
    max_v = float(np.max(speed))

    # Pre-set assertion: well-balanced C-property
    assert (
        max_v < PASS_THRESHOLD_MAX_V
    ), f"Lake-at-rest velocity {max_v:.4e} m/s exceeded pre-set threshold {PASS_THRESHOLD_MAX_V} m/s"


def test_mass_balance_conservation_and_configured_tolerance_failure(tmp_path: Path):
    """Verify mass balance error computation and failure behavior when error exceeds tolerance.

    Pre-set pass threshold:
    Mass balance error must be < 1e-4 under normal operation.
    When tolerance is set to an impossibly low threshold, the run must fail (success=False).
    """
    PASS_TOLERANCE = 1e-4

    # 1. Normal run with tolerance 0.05
    solver = AnugaSolver(mass_balance_tolerance=0.05)
    spec = {
        "type": "channel",
        "length_m": 200.0,
        "width_m": 20.0,
        "dam_x_m": 100.0,
        "h_left_m": 5.0,
        "h_right_m": 1.0,
        "manning_n": 0.0,
        "b_left": "reflective",
        "b_right": "reflective",
        "duration_s": 5.0,
        "yieldstep_s": 1.0,
    }

    run_dir = solver.prepare(spec, mesh_resolution_m=10.0, run_dir=tmp_path / "mb_pass")
    res = solver.run(run_dir, yieldstep=1.0, finaltime=5.0)

    assert res.success is True
    assert (
        res.mass_balance_error < PASS_TOLERANCE
    ), f"Mass balance error {res.mass_balance_error:.2e} exceeded pre-set threshold {PASS_TOLERANCE}"
    assert len(res.warnings) == 0

    # 2. Strict run with negative tolerance (-1.0): run MUST fail (success=False)
    strict_solver = AnugaSolver(mass_balance_tolerance=-1.0)
    run_dir_strict = strict_solver.prepare(
        spec, mesh_resolution_m=10.0, run_dir=tmp_path / "mb_fail"
    )
    res_strict = strict_solver.run(run_dir_strict, yieldstep=1.0, finaltime=5.0)

    assert res_strict.success is False, "Run must fail (success=False) when error exceeds tolerance"
    assert len(res_strict.warnings) > 0
    assert "exceeded configured tolerance" in res_strict.warnings[0]


def test_arrival_time_raster_on_synthetic_ramp(tmp_path: Path):
    """Verify arrival_time raster on a synthetic ramp (first time depth > 0.1 m; nodata if never).

    Pre-set pass criteria:
    - Flooded cells have 0.0 <= arrival_time <= final_time.
    - Upstream cells arrive earlier than downstream cells.
    - Cells never reached by the flood wave retain nodata (-9999.0).
    - GeoTIFF outputs contract rasters and run_meta.json are successfully written.
    """
    solver = AnugaSolver()

    # Ramp: 200m channel with water initially at x <= 40m, releasing down the ramp
    spec = {
        "type": "channel",
        "length_m": 200.0,
        "width_m": 20.0,
        "dam_x_m": 40.0,
        "h_left_m": 3.0,
        "h_right_m": 0.0,
        "manning_n": 0.03,
        "duration_s": 5.0,
        "yieldstep_s": 0.5,
    }

    run_dir = solver.prepare(spec, mesh_resolution_m=10.0, run_dir=tmp_path / "ramp_run")
    res = solver.run(run_dir, yieldstep=0.5, finaltime=5.0)
    assert res.success is True

    outputs = solver.collect(run_dir)

    # 1. Output files contract check
    assert outputs.max_depth_tif.exists()
    assert outputs.max_velocity_tif.exists()
    assert outputs.arrival_time_tif.exists()
    assert outputs.hazard_tif.exists()
    assert outputs.run_meta_json.exists()

    # 2. Check run_meta.json
    with open(outputs.run_meta_json, "r", encoding="utf-8") as f:
        meta = json.load(f)
    assert meta["solver"] == "anuga"
    assert meta["version"] == "4.0.0"
    assert meta["install_method"] == "conda-forge"
    assert meta["mesh_resolution_m"] == 10.0
    assert meta["runtime_s"] >= 0.0
    assert meta["mass_balance_error"] >= 0.0

    # 3. Check arrival_time raster properties
    with rasterio.open(outputs.arrival_time_tif) as src:
        arr = src.read(1)
        nodata = src.nodata

    with rasterio.open(outputs.max_depth_tif) as src:
        depth = src.read(1)

    assert nodata == -9999.0

    # Wet cells (depth > 0.1 m) must have arrived between 0 and 5 seconds
    wet_mask = depth > 0.1
    assert np.any(wet_mask), "Flood wave must have inundated some cells"
    wet_arrival = arr[wet_mask]
    assert np.all(wet_arrival >= 0.0), "Wet cells must have non-negative arrival time"
    assert np.all(wet_arrival <= 5.0), "Arrival time cannot exceed simulation duration"

    # Monotonic wave propagation: cell near x=50m must arrive earlier than cell near x=80m
    # Pixel coordinates along channel centerline (row 0 or 1)
    col_x50 = 5  # x ≈ 50m
    col_x80 = 8  # x ≈ 80m
    t_arr_50 = arr[0, col_x50]
    t_arr_80 = arr[0, col_x80]
    if t_arr_50 != -9999.0 and t_arr_80 != -9999.0:
        assert (
            t_arr_50 <= t_arr_80
        ), f"Wave must reach x=50m ({t_arr_50}s) before or at x=80m ({t_arr_80}s)"

    # Dry cells near the end of the channel (x=190m) must strictly be nodata (-9999.0)
    col_dry = arr.shape[1] - 1  # near x=200m
    assert (
        arr[0, col_dry] == nodata
    ), f"Dry cell at far end must retain nodata ({nodata}), got {arr[0, col_dry]}"


def test_solver_same_type_argument_swap_sensitivity(tmp_path: Path):
    """Verify solver preparation fails or produces distinct spatial state if same-typed arguments are swapped."""
    solver = AnugaSolver()

    # Normal order: h_left=10.0, h_right=0.0
    spec_normal = {
        "type": "channel",
        "length_m": 100.0,
        "width_m": 20.0,
        "dam_x_m": 50.0,
        "h_left_m": 10.0,
        "h_right_m": 0.0,
        "duration_s": 1.0,
    }
    rd_normal = solver.prepare(spec_normal, mesh_resolution_m=10.0, run_dir=tmp_path / "swap_norm")
    d_norm = rd_normal.extra["domain"]
    xc_norm = d_norm.get_centroid_coordinates()[:, 0]
    st_norm = d_norm.quantities["stage"].centroid_values

    # Swapped order: h_left=0.0, h_right=10.0
    spec_swapped = {
        "type": "channel",
        "length_m": 100.0,
        "width_m": 20.0,
        "dam_x_m": 50.0,
        "h_left_m": 0.0,
        "h_right_m": 10.0,
        "duration_s": 1.0,
    }
    rd_swapped = solver.prepare(spec_swapped, mesh_resolution_m=10.0, run_dir=tmp_path / "swap_inv")
    d_swapped = rd_swapped.extra["domain"]
    st_swapped = d_swapped.quantities["stage"].centroid_values

    # At x < 50m: normal has stage 10.0, swapped has stage 0.0
    mask_left = xc_norm < 40.0
    assert np.allclose(st_norm[mask_left], 10.0)
    assert np.allclose(st_swapped[mask_left], 0.0)
    assert not np.allclose(
        st_norm, st_swapped
    ), "Swapped arguments (h_left, h_right) must produce inverted domain state"
