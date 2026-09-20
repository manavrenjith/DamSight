"""Tests for hydrodynamic solver adapter (AnugaSolver).

Adheres to AGENTS.md testing discipline:
- Pre-set pass thresholds written into tests before execution.
- Tests include:
  - C1: Mass balance including boundary outflow (V_final = V_init + V_in - V_out)
        with independent SWW volume computation:
        (i) closed domain,
        (ii) Inlet_operator with triangular hydrograph into dry basin (diff < 1e-3 m3),
        (iii) transmissive outlet where water leaves domain (V_out > 0),
        (iv) FORCED VIOLATION (inlet scaled 1.02 vs tally 1.00 fails under standard 1% tol).
  - C2: Inlet_operator hydrograph test (named test_inlet_operator_triangular_hydrograph_dry_basin).
  - C3: Lake-at-rest C-property over >= 100 s: max |v| < 1e-3 m/s and stage drift < 1e-3 m.
  - C4: Stoker shock arrival time: |t_sim - t_exact| <= yieldstep + dx/s; nodata where never wet.
  - Same-typed argument swap sensitivity.
"""

from __future__ import annotations

import json
from pathlib import Path

import netCDF4
import numpy as np
import pandas as pd
import pytest
import rasterio
from scipy.integrate import trapezoid

from damsight.solvers.analytical import stoker_solution
from damsight.solvers.anuga_solver import AnugaSolver


def test_lake_at_rest_c_property_100s(tmp_path: Path):
    """Lake-at-rest C-property verification over irregular bathymetry for >= 100 seconds (C3).

    Gates:
    - max |v| < 1e-3 m/s
    - max stage drift < 1e-3 m
    """
    GATE_MAX_V = 1e-3  # m/s
    GATE_STAGE_DRIFT = 1e-3  # m

    solver = AnugaSolver()

    # Irregular bathymetry: sinusoidal bed variation between 0.7m and 1.3m
    def bumpy_bed(x: np.ndarray, y: np.ndarray) -> np.ndarray:
        return 1.0 + 0.3 * np.sin(2.0 * np.pi * x / 100.0)

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
        "boundary_type": "reflective",
        "duration_s": 100.0,
        "yieldstep_s": 20.0,
    }

    run_dir = solver.prepare(
        spec,
        mesh_resolution_m=10.0,
        boundary_type="reflective",
        run_dir=tmp_path / "lake_at_rest_100s",
    )
    domain = run_dir.extra["domain"]

    domain.set_quantity("elevation", bumpy_bed)
    domain.set_quantity("stage", 2.0)

    res = solver.run(run_dir, yieldstep=20.0, finaltime=100.0)
    assert res.success is True

    # Check stage drift from netCDF SWW output
    sww_path = run_dir.path / "simulation.sww"
    nc = netCDF4.Dataset(str(sww_path), "r")
    stage_c = np.array(nc.variables["stage_c"][:])
    nc.close()

    stage_drift = float(np.max(np.abs(stage_c - 2.0)))

    # Compute max velocity across all cells at final time
    h = np.maximum(
        domain.quantities["stage"].centroid_values - domain.quantities["elevation"].centroid_values,
        1e-6,
    )
    u = domain.quantities["xmomentum"].centroid_values / h
    v = domain.quantities["ymomentum"].centroid_values / h
    speed = np.sqrt(u**2 + v**2)
    max_v = float(np.max(speed))

    assert (
        max_v < GATE_MAX_V
    ), f"Lake-at-rest max |v| = {max_v:.4e} m/s exceeded gate {GATE_MAX_V:.4e} m/s"
    assert (
        stage_drift < GATE_STAGE_DRIFT
    ), f"Lake-at-rest stage drift = {stage_drift:.4e} m exceeded gate {GATE_STAGE_DRIFT:.4e} m"


def test_mass_balance_closed_domain(tmp_path: Path):
    """Verify mass balance in a closed domain (C1-i).

    Domain volume is computed independently from SWW output (stage - elevation) * area.
    Error must remain < 1e-4.
    """
    solver = AnugaSolver(mass_balance_tolerance=0.01)
    spec = {
        "type": "channel",
        "length_m": 100.0,
        "width_m": 20.0,
        "dam_x_m": 50.0,
        "h_left_m": 4.0,
        "h_right_m": 1.0,
        "manning_n": 0.0,
        "b_left": "reflective",
        "b_right": "reflective",
        "boundary_type": "reflective",
        "duration_s": 5.0,
    }
    run_dir = solver.prepare(
        spec,
        mesh_resolution_m=10.0,
        boundary_type="reflective",
        run_dir=tmp_path / "mb_closed",
    )
    res = solver.run(run_dir, yieldstep=1.0, finaltime=5.0)

    assert res.success is True
    assert res.mass_balance_error < 1e-4, f"Closed domain error {res.mass_balance_error:.2e} >= 1e-4"
    assert res.extra["outflow_volume_m3"] == 0.0


def test_inlet_operator_triangular_hydrograph_dry_basin(tmp_path: Path):
    """Verify Inlet_operator with triangular hydrograph into dry basin (C1-ii, C2).

    Domain volume increase equals integral of Q dt within 1e-3 m3.
    """
    solver = AnugaSolver(mass_balance_tolerance=0.01)

    t_h = np.array([0.0, 5.0, 10.0])
    q_h = np.array([0.0, 20.0, 0.0])
    df_h = pd.DataFrame({"time_s": t_h, "discharge_m3s": q_h})
    integral_q = 0.5 * 10.0 * 20.0  # 100.0 m3

    spec = {
        "type": "channel",
        "length_m": 100.0,
        "width_m": 20.0,
        "dam_x_m": 0.0,
        "h_left_m": 0.0,
        "h_right_m": 0.0,
        "manning_n": 0.03,
        "b_left": "reflective",
        "b_right": "reflective",
        "boundary_type": "reflective",
        "duration_s": 10.0,
    }
    run_dir = solver.prepare(
        spec,
        hydrograph=df_h,
        mesh_resolution_m=10.0,
        dam_location=[10.0, 10.0],
        inlet_radius_m=10.0,
        boundary_type="reflective",
        run_dir=tmp_path / "mb_inlet",
    )
    res = solver.run(run_dir, yieldstep=1.0, finaltime=10.0)

    assert res.success is True
    vol_final = res.extra["final_volume_m3"]
    vol_diff = abs(vol_final - integral_q)
    assert vol_diff < 1e-3, f"Inlet volume diff {vol_diff:.4e} m3 exceeded gate 1e-3 m3 (final={vol_final:.4f}, expected={integral_q:.4f})"


def test_mass_balance_transmissive_outlet(tmp_path: Path):
    """Verify mass balance with transmissive outlet where water leaves domain (C1-iii).

    V_final = V_init + V_in - V_out must hold within 1e-4.
    Includes independent outflow check: integrate SWW x-momentum across the last
    cell row over time (trapezoid) and compare with get_boundary_flux_integral() within 2%.
    """
    solver = AnugaSolver(mass_balance_tolerance=0.01)
    spec = {
        "type": "channel",
        "length_m": 100.0,
        "width_m": 20.0,
        "dam_x_m": 50.0,
        "h_left_m": 4.0,
        "h_right_m": 0.0,
        "manning_n": 0.0,
        "b_left": "reflective",
        "b_right": "transmissive",
        "boundary_type": "transmissive",
        "duration_s": 15.0,
    }
    run_dir = solver.prepare(
        spec,
        mesh_resolution_m=10.0,
        boundary_type="transmissive",
        run_dir=tmp_path / "mb_trans",
    )
    res = solver.run(run_dir, yieldstep=1.0, finaltime=15.0)

    assert res.success is True
    assert res.extra["outflow_volume_m3"] > 50.0, f"Water should have left domain, got V_out={res.extra['outflow_volume_m3']}"
    assert res.mass_balance_error < 1e-4, f"Transmissive domain error {res.mass_balance_error:.2e} >= 1e-4"

    # Independent outflow check:
    # Read simulation.sww and locate triangles forming the outlet boundary (edge at x=100.0m)
    sww_path = run_dir.path / "simulation.sww"
    nc = netCDF4.Dataset(str(sww_path), "r")
    x_pts = np.array(nc.variables["x"][:])
    y_pts = np.array(nc.variables["y"][:])
    vols = np.array(nc.variables["volumes"][:])
    time_arr = np.array(nc.variables["time"][:])
    xmom = np.array(nc.variables["xmomentum_c"][:])  # (timesteps, n_triangles)
    nc.close()

    # Locate triangles with an edge on the downstream boundary (x == length_m == 100.0)
    outlet_tri_dys = []
    for tri in range(vols.shape[0]):
        pts = vols[tri]
        xs = x_pts[pts]
        if np.sum(np.isclose(xs, 100.0)) == 2:
            ys_at_100 = y_pts[pts][np.isclose(xs, 100.0)]
            dy = float(abs(ys_at_100[1] - ys_at_100[0]))
            outlet_tri_dys.append((tri, dy))

    assert len(outlet_tri_dys) > 0, "Must find outlet boundary triangles at x=100m"

    # Compute instantaneous outflow discharge Q(t) = sum(xmomentum * dy)
    q_out_t = np.zeros(len(time_arr))
    for tri, dy in outlet_tri_dys:
        q_out_t += xmom[:, tri] * dy

    # Integrate outflow over time via trapezoid rule
    v_out_sww = float(trapezoid(q_out_t, time_arr))
    anuga_bnd_flux = abs(float(res.extra["boundary_flux_integral"]))

    # Compare independent SWW trapezoid integration with ANUGA get_boundary_flux_integral() within 2%
    rel_diff = abs(v_out_sww - anuga_bnd_flux) / anuga_bnd_flux
    assert rel_diff < 0.02, (
        f"Independent SWW outflow ({v_out_sww:.2f} m3) differs from ANUGA boundary flux "
        f"({anuga_bnd_flux:.2f} m3) by {rel_diff:.4%}, which exceeds the 2% threshold"
    )


def test_forced_violation_inlet_mass_imbalance_fails(tmp_path: Path):
    """Verify forced violation: inlet hydrograph scaled 1.02 vs tally 1.00 (C1-iv).

    The run must fail (success=False) under standard 1.0% tolerance.
    """
    solver = AnugaSolver(mass_balance_tolerance=0.01)

    t_h = np.array([0.0, 5.0, 10.0])
    q_h = np.array([0.0, 20.0, 0.0])
    # Inlet applies hydrograph scaled by 1.02
    df_h_scaled = pd.DataFrame({"time_s": t_h, "discharge_m3s": q_h * 1.02})

    spec = {
        "type": "channel",
        "length_m": 100.0,
        "width_m": 20.0,
        "dam_x_m": 0.0,
        "h_left_m": 0.0,
        "h_right_m": 0.0,
        "b_left": "reflective",
        "b_right": "reflective",
        "boundary_type": "reflective",
        "duration_s": 10.0,
    }
    # Tally uses 1.00 (scale factor 1.0 / 1.02)
    run_dir = solver.prepare(
        spec,
        hydrograph=df_h_scaled,
        mesh_resolution_m=10.0,
        dam_location=[10.0, 10.0],
        inlet_radius_m=10.0,
        tally_inflow_scale=(1.0 / 1.02),
        boundary_type="reflective",
        run_dir=tmp_path / "mb_forced_violation",
    )
    res = solver.run(run_dir, yieldstep=1.0, finaltime=10.0)

    assert res.success is False, "Run must fail (success=False) when inlet imbalance exceeds 1% tolerance"
    assert res.mass_balance_error > 0.015, f"Expected error > 1.5%, got {res.mass_balance_error:.4%}"
    assert len(res.warnings) > 0
    assert "exceeded configured tolerance" in res.warnings[0]


def test_stoker_arrival_time_shock_speed(tmp_path: Path):
    """Verify arrival time using Stoker shock with constant speed s (C4).

    Analytical arrival: t = (x - x0) / s.
    Gate: |arrival_sim - arrival_exact| <= yieldstep + dx/s at every wetted cell
    away from the initial discontinuity. Nodata where never wet.
    Includes verification of collect()'s arrival_time.tif at cell centres.
    REGRESSION GUARD (set after seeing benchmark results of 0.8584 s):
    Max error in arrival_time.tif <= 2*yieldstep (1.0 s).
    """
    res_m = 10.0
    yieldstep_s = 0.5
    hL = 10.0
    hR = 2.0
    x0 = 500.0
    finaltime = 15.0

    solver = AnugaSolver()
    spec = {
        "type": "channel",
        "length_m": 1000.0,
        "width_m": 20.0,
        "dam_x_m": x0,
        "h_left_m": hL,
        "h_right_m": hR,
        "manning_n": 0.0,
        "duration_s": finaltime,
        "yieldstep_s": yieldstep_s,
        "boundary_type": "transmissive",
    }

    # Stoker exact solution shock speed
    _, _, meta = stoker_solution(np.array([x0]), t=1.0, x0=x0, hL=hL, hR=hR)
    s = meta["shock_speed"]
    hm = meta["hm"]

    # Arrival threshold: 20% elevation above downstream pool hR
    arrival_thresh = hR + 0.2 * (hm - hR)

    run_dir = solver.prepare(
        spec,
        mesh_resolution_m=res_m,
        arrival_threshold_m=arrival_thresh,
        boundary_type="transmissive",
        run_dir=tmp_path / "stoker_arrival",
    )
    res = solver.run(run_dir, yieldstep=yieldstep_s, finaltime=finaltime)
    assert res.success is True

    # Read SWW directly for cell-by-cell verification
    sww_path = run_dir.path / "simulation.sww"
    nc = netCDF4.Dataset(str(sww_path), "r")
    x_pts = np.array(nc.variables["x"][:])
    vols = np.array(nc.variables["volumes"][:])
    time_arr = np.array(nc.variables["time"][:])
    stage_c = np.array(nc.variables["stage_c"][:])
    elev_c = np.array(nc.variables["elevation_c"][:])
    nc.close()

    xc = (x_pts[vols[:, 0]] + x_pts[vols[:, 1]] + x_pts[vols[:, 2]]) / 3.0
    depth_c = np.maximum(0.0, stage_c - elev_c)

    arrival_sim = np.full(len(xc), -9999.0, dtype=np.float32)
    for i in range(len(xc)):
        hits = np.where(depth_c[:, i] > arrival_thresh)[0]
        if len(hits) > 0:
            arrival_sim[i] = time_arr[hits[0]]

    # Away from initial discontinuity: x > x0 + 2 * dx
    wetted_mask = (arrival_sim >= 0.0) & (xc > x0 + 2.0 * res_m)
    xc_wet = xc[wetted_mask]
    arr_sim_wet = arrival_sim[wetted_mask]
    arr_exact_wet = (xc_wet - x0) / s

    gate_error = yieldstep_s + res_m / s
    diff = np.abs(arr_sim_wet - arr_exact_wet)
    max_diff = float(np.max(diff))

    assert np.all(
        diff <= gate_error
    ), f"Max arrival diff {max_diff:.4f} s exceeded gate {gate_error:.4f} s (yieldstep + dx/s)"

    # Cells never reached by the shock wave must have nodata (-9999.0)
    unwetted_mask = xc > (x0 + s * finaltime + 2.0 * res_m)
    assert np.any(unwetted_mask), "Must have unwetted cells beyond the shock wave front"
    assert np.all(
        arrival_sim[unwetted_mask] == -9999.0
    ), "Cells never reached by shock wave must have nodata (-9999.0)"

    # Verify collect()'s arrival_time.tif GeoTIFF
    outputs = solver.collect(run_dir)
    assert outputs.arrival_time_tif.exists()
    assert outputs.run_meta_json.exists()

    # Verify run_meta.json contains boundary_type and arrival_threshold_m override
    with open(outputs.run_meta_json, "r", encoding="utf-8") as f:
        meta_json = json.load(f)
    assert meta_json["boundary_type"] == "transmissive"
    assert meta_json["arrival_threshold_m"] == arrival_thresh

    with rasterio.open(outputs.arrival_time_tif) as src:
        arr_tif = src.read(1)
        nodata = src.nodata
        transform = src.transform
        height, width = arr_tif.shape

        cols, rows = np.meshgrid(np.arange(width), np.arange(height))
        xs, _ = rasterio.transform.xy(transform, rows, cols, offset="center")
        xs = np.array(xs).reshape(height, width)

    assert nodata == -9999.0

    # Raster cells away from discontinuity and before shock front
    shock_front = x0 + s * finaltime
    wetted_tif_mask = (arr_tif != nodata) & (xs > x0 + 2.0 * res_m) & (xs < shock_front - res_m)
    xs_wet_tif = xs[wetted_tif_mask]
    arr_wet_tif = arr_tif[wetted_tif_mask]
    arr_exact_tif = (xs_wet_tif - x0) / s

    diff_tif = np.abs(arr_wet_tif - arr_exact_tif)
    max_diff_tif = float(np.max(diff_tif))

    # Gate: within yieldstep + dx/s
    assert np.all(
        diff_tif <= gate_error
    ), f"arrival_time.tif max diff {max_diff_tif:.4f} s exceeded gate {gate_error:.4f} s"

    # REGRESSION GUARD: max error <= 2 * yieldstep
    assert (
        max_diff_tif <= 2.0 * yieldstep_s
    ), f"arrival_time.tif max diff {max_diff_tif:.4f} s exceeded regression guard {2.0 * yieldstep_s:.4f} s"

    # Check that cells beyond the shock wave are nodata
    beyond_shock = xs > (shock_front + 2.0 * res_m)
    assert np.any(beyond_shock), "Must have cells beyond shock in arrival_time.tif"
    assert np.all(
        arr_tif[beyond_shock] == nodata
    ), "Cells beyond shock in arrival_time.tif must be nodata (-9999.0)"


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
        "b_left": "reflective",
        "b_right": "reflective",
        "boundary_type": "reflective",
        "duration_s": 5.0,
        "yieldstep_s": 0.5,
    }

    run_dir = solver.prepare(
        spec,
        mesh_resolution_m=10.0,
        boundary_type="reflective",
        run_dir=tmp_path / "ramp_run",
    )
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
    assert meta["boundary_type"] == "reflective"
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


def test_prepare_omitting_boundary_type_raises(tmp_path: Path):
    """Verify that omitting boundary_type in prepare() raises ValueError (G2)."""
    solver = AnugaSolver()
    spec = {
        "type": "channel",
        "length_m": 100.0,
        "width_m": 20.0,
        "dam_x_m": 50.0,
        "h_left_m": 4.0,
        "h_right_m": 0.0,
    }
    with pytest.raises(ValueError, match="boundary_type"):
        solver.prepare(spec, mesh_resolution_m=10.0, run_dir=tmp_path / "missing_bnd")


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
        "boundary_type": "reflective",
        "duration_s": 1.0,
    }
    rd_normal = solver.prepare(
        spec_normal,
        mesh_resolution_m=10.0,
        boundary_type="reflective",
        run_dir=tmp_path / "swap_norm",
    )
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
        "boundary_type": "reflective",
        "duration_s": 1.0,
    }
    rd_swapped = solver.prepare(
        spec_swapped,
        mesh_resolution_m=10.0,
        boundary_type="reflective",
        run_dir=tmp_path / "swap_inv",
    )
    d_swapped = rd_swapped.extra["domain"]
    st_swapped = d_swapped.quantities["stage"].centroid_values

    # At x < 50m: normal has stage 10.0, swapped has stage 0.0
    mask_left = xc_norm < 40.0
    assert np.allclose(st_norm[mask_left], 10.0)
    assert np.allclose(st_swapped[mask_left], 0.0)
    assert not np.allclose(
        st_norm, st_swapped
    ), "Swapped arguments (h_left, h_right) must produce inverted domain state"
